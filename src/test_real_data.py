# src/test_real_data.py
#
# WHY THIS FILE EXISTS:
# Tests our full pipeline against real OFAC data.
# Simulates 5 incoming transactions and screens them
# against all 18,699 real sanctions records.

import sys
import os
sys.path.append(os.path.dirname(__file__))
sys.path.append(
    os.path.join(os.path.dirname(__file__), '..', 'data')
)

from ingest import load_records
from blocking import build_blocking_index, get_candidates
from sanctions import score_records


def screen_transaction(transaction, records,
                       index, records_by_id):
    """
    Screens one transaction against full sanctions database.
    Returns top matches above threshold.
    """
    candidates = get_candidates(
        transaction, index, records_by_id
    )

    results = []
    for candidate_id in candidates:
        if candidate_id == transaction.get('id'):
            continue

        candidate      = records_by_id[candidate_id]
        txn_normalised = {
            'name':     transaction.get('name'),
            'dob':      transaction.get('dob'),
            'country':  transaction.get('country'),
            'passport': transaction.get('passport'),
            'aliases':  transaction.get('aliases', []),
        }
        cnd_normalised = {
            'name':     candidate.get('name'),
            'dob':      candidate.get('dob'),
            'country':  candidate.get('country'),
            'passport': candidate.get('passport'),
            'aliases':  candidate.get('aliases', []),
        }

        score, decision, explanation, _ = score_records(
            txn_normalised, cnd_normalised
        )

        if decision != "CLEAR":
            results.append({
                'id':       candidate_id,
                'name':     candidate['name'],
                'score':    score,
                'decision': decision,
            })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results, len(candidates)


if __name__ == "__main__":

    print("=" * 60)
    print("REAL OFAC DATA — PIPELINE TEST")
    print("=" * 60)

    # Load real OFAC records
    print()
    print("Loading real OFAC records...")
    records = load_records("data/ofac_records.json")

    if not records:
        print("No records found.")
        print("Run: python src/ingest.py first")
        sys.exit(1)

    print(f"Loaded {len(records):,} real sanctions records")

    # Build blocking index
    print("Building blocking index...")
    records_by_id = {r['id']: r for r in records}
    index = build_blocking_index(records)
    print(f"Index built: {len(index):,} blocking buckets")

    # Test transactions
    test_transactions = [
        {
            'id':      'TXN-001',
            'name':    'Osama Bin Laden',
            'dob':     '1957',
            'country': 'Saudi Arabia',
            'passport': None,
            'aliases': [],
        },
        {
            'id':      'TXN-002',
            'name':    'Muammar Gaddafi',
            'dob':     '1942',
            'country': 'Libya',
            'passport': None,
            'aliases': [],
        },
        {
            'id':      'TXN-003',
            'name':    'Ali Hassan',
            'dob':     None,
            'country': 'Iraq',
            'passport': None,
            'aliases': [],
        },
        {
            'id':      'TXN-004',
            'name':    'John Smith',
            'dob':     '1980',
            'country': 'United Kingdom',
            'passport': None,
            'aliases': [],
        },
        {
            'id':      'TXN-005',
            'name':    'Mohammad Al-Zawahiri',
            'dob':     '1960',
            'country': 'Egypt',
            'passport': None,
            'aliases': [],
        },
    ]

    print()
    print("=" * 60)
    print("SCREENING TRANSACTIONS")
    print("=" * 60)

    for txn in test_transactions:
        print()
        print(f"Transaction: {txn['name']}")
        print(f"  DOB: {txn['dob']}  "
              f"Country: {txn['country']}")

        matches, candidates_checked = screen_transaction(
            txn, records, index, records_by_id
        )

        print(f"  Candidates checked: {candidates_checked}"
              f" of {len(records):,}")

        if matches:
            print(f"  ⚠️  MATCHES FOUND: {len(matches)}")
            for m in matches[:3]:
                print(f"    → {m['id']:15} "
                      f"{m['name'][:35]:35} "
                      f"score: {m['score']:.2f} "
                      f"{m['decision']}")
        else:
            print(f"  ✅ CLEAR — no matches above threshold")