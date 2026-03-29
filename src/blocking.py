# src/blocking.py
#
# WHY BLOCKING EXISTS:
# Without blocking, matching one transaction against
# 10,000 sanctions records = 10,000 full comparisons.
# Each comparison runs 5 algorithms = 50,000 operations.
# For 1M daily transactions = 50 billion operations.
# Impossible at production scale.
#
# Blocking reduces candidates BEFORE scoring.
# It uses fast, simple rules to eliminate records
# that are PROVABLY too different to be the same person.
#
# CRITICAL RULE:
# A blocking rule must NEVER eliminate a true match.
# It can only eliminate impossible candidates.
# Speed is worthless if we miss sanctioned entities.
#
# HOW WE MEASURE BLOCKING QUALITY:
# Reduction ratio — how many candidates were eliminated?
# Pair completeness — did we keep all true matches?
# Both matter. Good blocking maximises reduction
# while keeping pair completeness at 100%.

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__)))

from sanctions import soundex


# ============================================================
# BLOCKING KEY GENERATORS
# ============================================================
# A blocking key is a fast-to-compute signature.
# Records with the same blocking key go into the same bucket.
# We only compare records within the same bucket.

def phonetic_blocking_key(name):
    """
    Generates a phonetic blocking key from a name.

    WHY PHONETIC FOR BLOCKING:
    Soundex encodes similar-sounding names to same code.
    "Usama" and "Osama" both encode to U/O250.
    We use first 2 chars of Soundex to make buckets
    broad enough to catch variants.

    WHY FIRST TOKEN ONLY:
    We use the first word of the name for the key.
    "Usama Bin Laden" → key from "Usama" → U250
    "Osama Bin Ladin" → key from "Osama" → O250
    We keep both U25 and O25 prefixes to handle
    Arabic vowel transliteration.

    Returns a set of blocking keys — not just one.
    WHY SET: one record can belong to multiple buckets
    to ensure we never miss a true match.
    """
    if not name:
        return set()

    # Take first token (first word of name)
    first_token = name.strip().split()[0]

    # Get full Soundex code
    code = soundex(first_token)

    keys = set()

    # Key 1: Full Soundex code
    # WHY: catches exact phonetic matches
    keys.add(f"PHONETIC:{code}")

    # Key 2: Numeric part only (digits after first letter)
    # WHY: "Usama" → U250, "Osama" → O250
    # Different first letter — same numeric pattern
    # Arabic vowels transliterate differently (U vs O)
    # Numeric part alone catches these variants
    if len(code) > 1:
        keys.add(f"PHONETICNUM:{code[1:]}")

    return keys


def country_blocking_key(country):
    """
    Generates a country blocking key.

    WHY COUNTRY AS BLOCKING KEY:
    A sanctioned Syrian national is very unlikely
    to be confused with a Peruvian businessman.
    Country narrows the candidate pool significantly.

    WHY WE INCLUDE UNKNOWN:
    If country is missing from either record,
    we cannot use it to eliminate candidates.
    Records with unknown country go into every bucket.
    """
    if not country:
        return {"COUNTRY:UNKNOWN"}

    normalised = country.lower().strip()
    return {f"COUNTRY:{normalised}"}


def dob_year_blocking_key(dob, tolerance=2):
    """
    Generates DOB year bucket keys with tolerance.

    WHY ±2 YEAR WINDOW:
    DOB errors and evasion tactics mean the same person
    can appear with DOB varying by up to 2 years.
    We create a bucket for each year in the tolerance window.

    Example: DOB 1957 with tolerance 2
    → buckets: DOB:1955, DOB:1956, DOB:1957, DOB:1958, DOB:1959
    A record with DOB 1958 falls in DOB:1958 bucket
    → candidate for comparison ✅

    WHY RETURN MULTIPLE KEYS:
    We want this record to appear in all nearby year buckets
    so it is a candidate for any transaction within ±2 years.
    """
    if not dob:
        return {"DOB:UNKNOWN"}

    try:
        year = int(str(dob)[:4])
    except (ValueError, TypeError):
        return {"DOB:UNKNOWN"}

    keys = set()
    for offset in range(-tolerance, tolerance + 1):
        keys.add(f"DOB:{year + offset}")

    return keys


def generate_blocking_keys(record):
    """
    Generates ALL blocking keys for one record.

    A record belongs to multiple buckets simultaneously.
    This ensures maximum recall — we never miss a match
    just because two records are in different single buckets.

    Returns a set of all blocking keys for this record.
    """
    keys = set()

    # Phonetic keys from primary name
    name = record.get('name', '')
    keys.update(phonetic_blocking_key(name))

    # Phonetic keys from each alias
    # WHY: a transaction might use an alias not the primary name
    # If we only index the primary name, alias matches are missed
    for alias in record.get('aliases', []):
        keys.update(phonetic_blocking_key(alias))

    # Country key
    keys.update(country_blocking_key(record.get('country')))

    # DOB year key
    keys.update(dob_year_blocking_key(record.get('dob')))

    return keys


# ============================================================
# BLOCKING INDEX
# ============================================================
# An index is a data structure that makes lookups fast.
# We build it once from the full sanctions database.
# Then for each incoming transaction, we look up
# its blocking keys and retrieve candidates instantly.
#
# Structure:
# {
#   "PHONETIC:U250": ["OFAC-001", "UN-001"],
#   "COUNTRY:saudi arabia": ["OFAC-001", "UN-001", "EU-001"],
#   "DOB:1957": ["OFAC-001", "UN-001", "EU-001"],
#   ...
# }

def build_blocking_index(records):
    """
    Builds a blocking index from a list of records.

    WHY BUILD ONCE:
    Building the index is O(n) — we do it once.
    Looking up candidates is O(1) — instant.
    This is much better than rebuilding for every transaction.

    WHY DICTIONARY:
    Dictionary lookup is O(1) in Python.
    blocking_key → list of record IDs that have this key.
    Given a transaction's blocking keys, we retrieve
    all candidate record IDs in constant time.
    """
    # index maps: blocking_key → list of record IDs
    index = {}

    for record in records:
        record_id = record['id']
        keys      = generate_blocking_keys(record)

        for key in keys:
            if key not in index:
                index[key] = []
            index[key].append(record_id)

    return index


def get_candidates(transaction, index, records_by_id):
    """
    Given an incoming transaction, returns candidate
    record IDs that should be scored against it.

    Process:
    1. Generate blocking keys for the transaction
    2. Look up each key in the index
    3. Collect all record IDs found
    4. Return unique set of candidates

    WHY SET FOR CANDIDATES:
    A record might appear in multiple matching buckets.
    Using a set automatically deduplicates — we score
    each candidate exactly once.
    """
    # Generate blocking keys for the transaction
    transaction_keys = generate_blocking_keys(transaction)

    # Collect all candidates across all matching buckets
    candidates = set()

    for key in transaction_keys:
        if key in index:
            # Add all record IDs from this bucket
            for record_id in index[key]:
                candidates.add(record_id)

    return candidates


def measure_blocking_quality(records, ground_truth_clusters):
    """
    Measures how well blocking performs.

    TWO METRICS:
    1. Reduction Ratio — what % of pairs were eliminated?
       Higher is better (less work for scoring step)

    2. Pair Completeness — what % of true match pairs
       were kept as candidates?
       Must be 1.0 (100%) — we cannot miss true matches

    WHY BOTH MATTER:
    Reduction ratio alone: could keep all pairs → no reduction
    Pair completeness alone: could keep all pairs → 100% complete
    Both together: tells us we eliminated non-matches
                   while keeping all true matches
    """
    # Build index
    index = build_blocking_index(records)
    records_by_id = {r['id']: r for r in records}

    total_pairs        = 0
    candidate_pairs    = 0
    true_match_pairs   = 0
    caught_match_pairs = 0

    # Count all possible pairs
    n = len(records)
    total_possible_pairs = n * (n - 1) // 2

    # Find all true match pairs from ground truth
    true_pairs = set()
    for cluster in ground_truth_clusters:
        cluster_list = list(cluster)
        for i in range(len(cluster_list)):
            for j in range(i + 1, len(cluster_list)):
                pair = tuple(sorted([cluster_list[i],
                                     cluster_list[j]]))
                true_pairs.add(pair)

    # Check which pairs blocking keeps as candidates
    kept_pairs    = set()
    caught_truths = set()

    for i, record in enumerate(records):
        candidates = get_candidates(record, index, records_by_id)

        for candidate_id in candidates:
            if candidate_id != record['id']:
                pair = tuple(sorted([record['id'], candidate_id]))
                kept_pairs.add(pair)

    # Check which true pairs were caught
    for pair in true_pairs:
        if pair in kept_pairs:
            caught_truths.add(pair)

    # Calculate metrics
    reduction_ratio   = 1 - (len(kept_pairs) / total_possible_pairs)
    pair_completeness = len(caught_truths) / len(true_pairs) \
                        if true_pairs else 1.0

    return {
        'total_possible_pairs': total_possible_pairs,
        'candidate_pairs':      len(kept_pairs),
        'true_match_pairs':     len(true_pairs),
        'caught_match_pairs':   len(caught_truths),
        'reduction_ratio':      reduction_ratio,
        'pair_completeness':    pair_completeness,
    }


# ============================================================
# TEST THE BLOCKING SYSTEM
# ============================================================

if __name__ == "__main__":

    import sys
    sys.path.append(
        os.path.join(os.path.dirname(__file__), '..', 'data')
    )
    from synthetic_sanctions import (
        SANCTIONS_RECORDS,
        GROUND_TRUTH_CLUSTERS,
        get_record_by_id
    )

    print("=" * 55)
    print("BLOCKING INDEX TEST")
    print("=" * 55)

    # Build the index
    records_by_id = {r['id']: r for r in SANCTIONS_RECORDS}
    index = build_blocking_index(SANCTIONS_RECORDS)

    print(f"Records indexed:  {len(SANCTIONS_RECORDS)}")
    print(f"Blocking buckets: {len(index)}")
    print()

    # Show blocking keys for one record
    record = get_record_by_id("OFAC-001")
    keys   = generate_blocking_keys(record)
    print(f"Blocking keys for OFAC-001 ({record['name']}):")
    for key in sorted(keys):
        print(f"  {key}")

    print()
    print("=" * 55)
    print("CANDIDATE RETRIEVAL TEST")
    print("=" * 55)

    # Simulate an incoming transaction
    incoming_transaction = {
        'id':       'TXN-001',
        'name':     'Osama Bin Ladin',
        'aliases':  [],
        'dob':      '1957-06-15',
        'country':  'Saudi Arabia',
        'passport': None
    }

    candidates = get_candidates(
        incoming_transaction, index, records_by_id
    )

    print(f"Incoming transaction: {incoming_transaction['name']}")
    print(f"Candidates retrieved: {len(candidates)}")
    print()
    print("Candidate records:")
    for cid in sorted(candidates):
        r = records_by_id[cid]
        print(f"  {cid}: {r['name']} ({r['source']})")

    print()
    print("=" * 55)
    print("BLOCKING QUALITY METRICS")
    print("=" * 55)

    metrics = measure_blocking_quality(
        SANCTIONS_RECORDS, GROUND_TRUTH_CLUSTERS
    )

    print(f"Total possible pairs:  {metrics['total_possible_pairs']}")
    print(f"Candidate pairs kept:  {metrics['candidate_pairs']}")
    print(f"True match pairs:      {metrics['true_match_pairs']}")
    print(f"True pairs caught:     {metrics['caught_match_pairs']}")
    print()
    print(f"Reduction ratio:       "
          f"{metrics['reduction_ratio']:.1%}")
    print(f"Pair completeness:     "
          f"{metrics['pair_completeness']:.1%}")

    print()
    if metrics['pair_completeness'] == 1.0:
        print("✅ All true matches kept — blocking is safe")
    else:
        missed = (metrics['true_match_pairs']
                  - metrics['caught_match_pairs'])
        print(f"❌ WARNING: {missed} true matches eliminated")
        print("   Blocking rules need adjustment")

    if metrics['reduction_ratio'] > 0.5:
        print("✅ Good reduction — eliminated >50% of pairs")
    else:
        print("⚠️  Low reduction — blocking rules too loose")