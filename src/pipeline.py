# src/pipeline.py
#
# WHY THIS FILE EXISTS:
# sanctions.py  — individual scoring algorithms
# blocking.py   — candidate generation
# pipeline.py   — puts it all together into one system
#
# This file:
# 1. Takes the full sanctions database
# 2. Builds a blocking index
# 3. For each record, finds candidates via blocking
# 4. Scores each candidate pair
# 5. Makes a decision on each pair
# 6. Measures performance against ground truth
#
# This is the file you would show a recruiter and say:
# "This is the full end-to-end pipeline."

import sys
import os

# WHY THESE PATH ADDITIONS:
# pipeline.py needs to import from:
# - src/sanctions.py  (scoring functions)
# - src/blocking.py   (blocking functions)
# - data/synthetic_sanctions.py (dataset)
# Python needs to know where to find these files

sys.path.append(os.path.dirname(__file__))
sys.path.append(
    os.path.join(os.path.dirname(__file__), '..', 'data')
)

from sanctions import score_records
from blocking  import (
    build_blocking_index,
    get_candidates,
    generate_blocking_keys
)
from synthetic_sanctions import (
    SANCTIONS_RECORDS,
    GROUND_TRUTH_CLUSTERS,
    get_true_matches_for
)


# ============================================================
# STEP 1 — NORMALISE RECORD FOR SCORING
# ============================================================

def normalise_for_scoring(record):
    """
    Converts a full sanctions record into the simple
    format that score_records() expects.

    WHY THIS STEP:
    Our synthetic records have many fields:
    id, source, aliases, notes, etc.
    Our scorer only needs: name, dob, country, passport.

    This function extracts only what the scorer needs.
    This is called the "adapter pattern" — converting
    one data format into another that a function expects.
    """
    return {
        'name':     record.get('name'),
        'dob':      record.get('dob'),
        'country':  record.get('country'),
        'passport': record.get('passport'),
        'aliases':  record.get('aliases', []) or [],
    }


# ============================================================
# STEP 2 — RUN THE FULL PIPELINE ON ONE TRANSACTION
# ============================================================

def run_pipeline(transaction, records, index,
                 records_by_id, threshold_block=0.85,
                 threshold_review=0.65):
    """
    Runs the full sanctions matching pipeline
    for one incoming transaction.

    Steps:
    1. Generate blocking keys for transaction
    2. Retrieve candidates from index
    3. Score each candidate
    4. Make decision on each candidate
    5. Return ranked results

    WHY RETURN ALL RESULTS NOT JUST MATCHES:
    Compliance systems need an audit trail.
    Every comparison must be logged — even clears.
    Regulators can ask: "Why did you clear this transaction?"
    We need to show the score and reasoning.

    Parameters:
    threshold_block:  score >= this → AUTO BLOCK
    threshold_review: score >= this → MANUAL REVIEW
    below threshold_review          → CLEAR
    """
    results = []

    # Step 1 + 2: Get candidates via blocking
    candidates = get_candidates(
        transaction, index, records_by_id
    )

    # Step 3 + 4: Score each candidate
    for candidate_id in candidates:
         # Skip self-comparison
        if candidate_id == transaction.get('id'):
            continue

        candidate = records_by_id[candidate_id]

        # Normalise both records for scoring
        txn_normalised = normalise_for_scoring(transaction)
        cnd_normalised = normalise_for_scoring(candidate)

        # Score the pair
        score, decision, explanation, breakdown = score_records(
            txn_normalised, cnd_normalised
        )

        results.append({
            'candidate_id':  candidate_id,
            'candidate_name': candidate['name'],
            'source':        candidate['source'],
            'score':         score,
            'decision':      decision,
            'explanation':   explanation,
            'breakdown':     breakdown,
        })

    # Sort by score — highest first
    # WHY: analysts should see the strongest matches first
    results.sort(key=lambda x: x['score'], reverse=True)

    return results


# ============================================================
# STEP 3 — EVALUATE AGAINST GROUND TRUTH
# ============================================================

def evaluate_pipeline(records, ground_truth_clusters,
                      threshold_block=0.85,
                      threshold_review=0.65):
    """
    Runs the full pipeline against ALL record pairs
    and measures performance against ground truth.

    WHY WE NEED GROUND TRUTH:
    Without knowing the correct answers, we cannot
    tell if our system is working or not.
    Ground truth lets us calculate:
    - How many true matches did we catch? (Recall)
    - How many of our flags were correct? (Precision)
    - Overall balance of both? (F1)

    A match is defined as:
    decision == "AUTO BLOCK" or "MANUAL REVIEW"
    WHY: both represent "the system thinks these might
    be the same person" — a human reviews both.
    Only "CLEAR" means the system dismissed the pair.
    """

    # Build blocking index
    records_by_id = {r['id']: r for r in records}
    index = build_blocking_index(records)

    # Track counts for metrics
    true_positives  = 0   # correctly flagged true matches
    false_positives = 0   # incorrectly flagged non-matches
    false_negatives = 0   # missed true matches
    true_negatives  = 0   # correctly cleared non-matches

    # Track detailed results for reporting
    missed_matches = []
    false_alarms   = []
    caught_matches = []

    # Build set of all true match pairs for quick lookup
    true_pairs = set()
    for cluster in ground_truth_clusters:
        cluster_list = list(cluster)
        for i in range(len(cluster_list)):
            for j in range(i+1, len(cluster_list)):
                pair = tuple(sorted(
                    [cluster_list[i], cluster_list[j]]
                ))
                true_pairs.add(pair)

    # Run pipeline for every record as if it were
    # an incoming transaction being checked
    scored_pairs = set()

    for record in records:
        results = run_pipeline(
            record, records, index, records_by_id,
            threshold_block, threshold_review
        )

        for result in results:
            # Build pair ID — sorted so we don't double count
            pair = tuple(sorted(
                [record['id'], result['candidate_id']]
            ))

            # Skip if already scored this pair
            if pair in scored_pairs:
                continue
            scored_pairs.add(pair)

             # Skip self-comparison — a record against itself
            # WHY: blocking retrieves the record itself as a
            # candidate because it shares all its own keys
            # A record is always identical to itself — skip it
            if record['id'] == result['candidate_id']:
                continue

            is_true_match = pair in true_pairs
            is_flagged    = result['decision'] != "CLEAR"

            if is_true_match and is_flagged:
                true_positives += 1
                caught_matches.append({
                    'pair':     pair,
                    'score':    result['score'],
                    'decision': result['decision']
                })

            elif is_true_match and not is_flagged:
                false_negatives += 1
                missed_matches.append({
                    'pair':  pair,
                    'score': result['score'],
                })

            elif not is_true_match and is_flagged:
                false_positives += 1
                false_alarms.append({
                    'pair':     pair,
                    'score':    result['score'],
                    'decision': result['decision']
                })

            else:
                true_negatives += 1

    # Calculate metrics
    precision = (
        true_positives /
        (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )

    recall = (
        true_positives /
        (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )

    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        'true_positives':  true_positives,
        'false_positives': false_positives,
        'false_negatives': false_negatives,
        'true_negatives':  true_negatives,
        'precision':       precision,
        'recall':          recall,
        'f1':              f1,
        'caught_matches':  caught_matches,
        'missed_matches':  missed_matches,
        'false_alarms':    false_alarms,
    }


# ============================================================
# MAIN — RUN AND DISPLAY RESULTS
# ============================================================

if __name__ == "__main__":

    print("=" * 55)
    print("SANCTIONS MATCHING PIPELINE")
    print("=" * 55)

    # Build index once
    records_by_id = {r['id']: r for r in SANCTIONS_RECORDS}
    index = build_blocking_index(SANCTIONS_RECORDS)

    # ── Demo: One transaction through the pipeline ────────
    print()
    print("DEMO: Single Transaction")
    print("-" * 55)

    demo_transaction = {
        'id':       'TXN-DEMO',
        'name':     'Osama Bin Ladin',
        'aliases':  [],
        'dob':      '1957',
        'country':  'Saudi Arabia',
        'passport': None
    }

    print(f"Transaction: {demo_transaction['name']}")
    print(f"DOB: {demo_transaction['dob']}")
    print(f"Country: {demo_transaction['country']}")
    print()

    results = run_pipeline(
        demo_transaction, SANCTIONS_RECORDS,
        index, records_by_id
    )

    print(f"Candidates checked: {len(results)}")
    print()
    print("Top matches:")
    print()

    for r in results[:3]:
        print(f"  Candidate: {r['candidate_id']} — "
              f"{r['candidate_name']} ({r['source']})")
        print()
        # Print each line of explanation indented
        for line in r['explanation'].split('\n'):
            print(f"    {line}")
        print()
        print("  " + "-" * 51)
        print()

    # ── Full evaluation against ground truth ─────────────
    print()
    print("=" * 55)
    print("FULL PIPELINE EVALUATION")
    print("=" * 55)

    metrics = evaluate_pipeline(
        SANCTIONS_RECORDS,
        GROUND_TRUTH_CLUSTERS
    )

    print()
    print("CONFUSION MATRIX:")
    print(f"  True Positives:  {metrics['true_positives']:3}"
          f"  ← correctly flagged true matches")
    print(f"  False Positives: {metrics['false_positives']:3}"
          f"  ← false alarms (innocent pairs flagged)")
    print(f"  False Negatives: {metrics['false_negatives']:3}"
          f"  ← MISSED true matches (dangerous)")
    print(f"  True Negatives:  {metrics['true_negatives']:3}"
          f"  ← correctly cleared non-matches")

    print()
    print("PERFORMANCE METRICS:")
    print(f"  Precision: {metrics['precision']:.2f}"
          f"  (of all flags, how many were correct?)")
    print(f"  Recall:    {metrics['recall']:.2f}"
          f"  (of all true matches, how many caught?)")
    print(f"  F1 Score:  {metrics['f1']:.2f}"
          f"  (balance of precision and recall)")

    # ── Show missed matches — most important ─────────────
    if metrics['missed_matches']:
        print()
        print("⚠️  MISSED MATCHES (False Negatives):")
        for m in metrics['missed_matches']:
            print(f"  {m['pair']}  score: {m['score']:.2f}")
        print("  → These sanctioned pairs slipped through")
    else:
        print()
        print("✅ No missed matches — all true pairs caught")

    # ── Show false alarms ─────────────────────────────────
    if metrics['false_alarms']:
        print()
        print("ℹ️  FALSE ALARMS (False Positives):")
        for f in metrics['false_alarms'][:5]:
            print(f"  {f['pair']}  "
                  f"score: {f['score']:.2f}  "
                  f"{f['decision']}")
        if len(metrics['false_alarms']) > 5:
            print(f"  ... and "
                  f"{len(metrics['false_alarms'])-5} more")

    # ── Compliance assessment ─────────────────────────────
    print()
    print("=" * 55)
    print("COMPLIANCE ASSESSMENT")
    print("=" * 55)

    if metrics['recall'] == 1.0:
        print("✅ RECALL: 1.00 — no sanctioned pairs missed")
    else:
        missed = metrics['false_negatives']
        print(f"❌ RECALL: {metrics['recall']:.2f}"
              f" — {missed} sanctioned pairs MISSED")
        print("   THIS IS A COMPLIANCE FAILURE")

    if metrics['precision'] >= 0.50:
        print(f"✅ PRECISION: {metrics['precision']:.2f}"
              f" — acceptable false alarm rate")
    else:
        print(f"⚠️  PRECISION: {metrics['precision']:.2f}"
              f" — too many false alarms")
        print("   Analysts will be overwhelmed")

    print()
    print(f"Overall F1: {metrics['f1']:.2f}")