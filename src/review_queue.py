# src/review_queue.py
#
# WHY THIS FILE EXISTS:
# Our pipeline makes automatic decisions for clear cases.
# But uncertain cases go to a human analyst.
# This file simulates the analyst review queue —
# the interface an analyst uses to review flagged pairs.
#
# WHAT A REVIEW QUEUE DOES:
# 1. Holds all MANUAL REVIEW decisions
# 2. Shows analyst: Record A, Record B, score, reason
# 3. Analyst decides: CONFIRM match or REJECT match
# 4. Decision feeds back into the graph store
# 5. System learns from analyst decisions over time
#
# WHY THIS MATTERS FOR COMPLIANCE:
# Regulators require human oversight of uncertain cases.
# Fully automated systems are not acceptable for sanctions.
# The review queue is the human-in-the-loop component.

import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(__file__))
sys.path.append(
    os.path.join(os.path.dirname(__file__), '..', 'data')
)

from sanctions import score_records
from graph import EntityGraph
from synthetic_sanctions import SANCTIONS_RECORDS


# ============================================================
# REVIEW QUEUE
# ============================================================

class ReviewQueue:
    """
    Manages the analyst review queue.

    Stores all pairs flagged for MANUAL REVIEW.
    Provides interface for analysts to review and decide.
    Feeds confirmed matches back into the graph.

    WHY A CLASS:
    The queue has STATE — a list of pending reviews,
    completed reviews, and statistics.
    A class bundles state and behaviour together.
    Functions alone cannot maintain state between calls.
    """

    def __init__(self, graph=None):
        """
        Initialises an empty review queue.

        Parameters:
        graph: EntityGraph instance — receives confirmed matches
               If None — graph updates are skipped
        """
        # pending: list of items waiting for analyst review
        self.pending  = []

        # completed: list of reviewed items with decisions
        self.completed = []

        # graph: receives confirmed matches from analyst
        self.graph = graph

        # statistics
        self.stats = {
            'total_added':    0,
            'confirmed':      0,
            'rejected':       0,
            'pending':        0,
        }

    def add_to_queue(self, record1, record2,
                     score, explanation, breakdown):
        """
        Adds a flagged pair to the review queue.

        Called by the pipeline when decision = MANUAL REVIEW.

        WHY STORE FULL EXPLANATION:
        Analysts need to see the full reasoning —
        not just the score. They need to understand
        which fields matched and why before deciding.
        """
        item = {
            'item_id':     f"REV-{len(self.pending) + len(self.completed) + 1:04d}",
            'record1':     record1,
            'record2':     record2,
            'score':       score,
            'explanation': explanation,
            'breakdown':   breakdown,
            'added_at':    datetime.now().isoformat(),
            'status':      'PENDING',
            'decision':    None,
            'analyst_id':  None,
            'decided_at':  None,
        }
        self.pending.append(item)
        self.stats['total_added'] += 1
        self.stats['pending']     += 1

        return item['item_id']

    def display_item(self, item):
        """
        Displays one review item in analyst-readable format.

        This is what an analyst sees on their screen.
        Every field is shown clearly with context.
        """
        print()
        print("=" * 60)
        print(f"REVIEW ITEM: {item['item_id']}")
        print(f"Added:       {item['added_at'][:19]}")
        print(f"Status:      {item['status']}")
        print("=" * 60)

        r1 = item['record1']
        r2 = item['record2']

        print()
        print("RECORD A (Sanctions List):")
        print(f"  ID:       {r1.get('id', 'N/A')}")
        print(f"  Source:   {r1.get('source', 'N/A')}")
        print(f"  Name:     {r1.get('name', 'N/A')}")
        if r1.get('aliases'):
            print(f"  Aliases:  {', '.join(r1['aliases'][:3])}")
        print(f"  DOB:      {r1.get('dob', 'UNKNOWN')}")
        print(f"  Country:  {r1.get('country', 'UNKNOWN')}")
        print(f"  Passport: {r1.get('passport', 'UNKNOWN')}")

        print()
        print("RECORD B (Incoming Transaction / Other Source):")
        print(f"  ID:       {r2.get('id', 'N/A')}")
        print(f"  Source:   {r2.get('source', 'N/A')}")
        print(f"  Name:     {r2.get('name', 'N/A')}")
        if r2.get('aliases'):
            print(f"  Aliases:  {', '.join(r2['aliases'][:3])}")
        print(f"  DOB:      {r2.get('dob', 'UNKNOWN')}")
        print(f"  Country:  {r2.get('country', 'UNKNOWN')}")
        print(f"  Passport: {r2.get('passport', 'UNKNOWN')}")

        print()
        print("SYSTEM ANALYSIS:")
        print(f"  Confidence score: {item['score']:.2f}")
        print()

        # Print explanation line by line
        for line in item['explanation'].split('\n'):
            print(f"  {line}")

        print()

    def process_decision(self, item_id, decision,
                         analyst_id="analyst"):
        """
        Records an analyst decision on a review item.

        Parameters:
        item_id:    the REV-XXXX identifier
        decision:   "CONFIRM" or "REJECT"
        analyst_id: who made the decision (audit trail)

        WHY AUDIT TRAIL:
        Regulators can ask: "Who decided this and when?"
        Every decision must be attributable to a person.
        """
        # Find the item
        item = None
        for pending_item in self.pending:
            if pending_item['item_id'] == item_id:
                item = pending_item
                break

        if not item:
            print(f"Item {item_id} not found in queue")
            return

        # Record the decision
        item['status']     = 'COMPLETED'
        item['decision']   = decision
        item['analyst_id'] = analyst_id
        item['decided_at'] = datetime.now().isoformat()

        # Move from pending to completed
        self.pending.remove(item)
        self.completed.append(item)

        # Update statistics
        self.stats['pending'] -= 1
        if decision == "CONFIRM":
            self.stats['confirmed'] += 1

            # Feed confirmed match into graph
            # WHY: graph now knows these are same person
            # Future transactions benefit from this knowledge
            if self.graph:
                id1 = item['record1'].get('id', 'unknown')
                id2 = item['record2'].get('id', 'unknown')
                if id1 != 'unknown' and id2 != 'unknown':
                    self.graph.confirm_match(
                        id1, id2, analyst_id
                    )
                    print(f"✅ Graph updated: {id1} ↔ {id2}"
                          f" confirmed as same person")

        else:
            self.stats['rejected'] += 1
            print(f"❌ Match rejected: records are"
                  f" different people")

    def print_queue_summary(self):
        """Prints current state of the review queue."""
        print()
        print("=" * 60)
        print("REVIEW QUEUE SUMMARY")
        print("=" * 60)
        print(f"Total added:      {self.stats['total_added']}")
        print(f"Pending review:   {self.stats['pending']}")
        print(f"Confirmed:        {self.stats['confirmed']}")
        print(f"Rejected:         {self.stats['rejected']}")

        if self.pending:
            print()
            print("Pending items:")
            for item in self.pending:
                print(f"  {item['item_id']}  "
                      f"score: {item['score']:.2f}  "
                      f"{item['record1'].get('name','?')}"
                      f" vs "
                      f"{item['record2'].get('name','?')}")


# ============================================================
# SIMULATE ANALYST REVIEW SESSION
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("ANALYST REVIEW QUEUE — SIMULATION")
    print("=" * 60)
    print()
    print("Simulating a compliance analyst's review session.")
    print("The system presents flagged pairs.")
    print("The analyst confirms or rejects each match.")
    print()

    # Build graph
    graph = EntityGraph()
    graph.build_from_records(SANCTIONS_RECORDS)

    # Create review queue
    queue = ReviewQueue(graph=graph)

    # Build records lookup
    records_by_id = {r['id']: r for r in SANCTIONS_RECORDS}

    # ── Find pairs for manual review ──────────────────────
    # We will take 3 pairs from our ground truth
    # and simulate them going through manual review

    review_pairs = [
        # Case 1: Name variant — same person
        ("OFAC-001", "EU-001"),
        # Case 2: Temporal drift — name change
        ("OFAC-006", "UN-005"),
        # Case 3: Common name — different people
        ("OFAC-004", "UN-003"),
    ]

    print("Loading review items into queue...")
    print()

    item_ids = []
    for id1, id2 in review_pairs:
        r1 = records_by_id[id1]
        r2 = records_by_id[id2]

        # Score the pair
        score, decision, explanation, breakdown = score_records(
            {
                'name':     r1.get('name'),
                'dob':      r1.get('dob'),
                'country':  r1.get('country'),
                'passport': r1.get('passport'),
                'aliases':  r1.get('aliases', []),
            },
            {
                'name':     r2.get('name'),
                'dob':      r2.get('dob'),
                'country':  r2.get('country'),
                'passport': r2.get('passport'),
                'aliases':  r2.get('aliases', []),
            }
        )

        # Add to queue regardless of decision
        # for simulation purposes
        item_id = queue.add_to_queue(
            r1, r2, score, explanation, breakdown
        )
        item_ids.append(item_id)
        print(f"Added to queue: {item_id} — "
              f"{r1['name']} vs {r2['name']}"
              f" (score: {score:.2f})")

    # ── Display each item ─────────────────────────────────
    print()
    print("=" * 60)
    print("ANALYST REVIEW SESSION")
    print("=" * 60)

    # Simulate analyst reviewing each item
    decisions = [
        ("CONFIRM", "Same person — transliteration variant"),
        ("CONFIRM", "Same person — name change after marriage"),
        ("CONFIRM", "Same person — spelling variant"),
    ]

    for i, item in enumerate(queue.pending.copy()):
        queue.display_item(item)

        decision_text, reason = decisions[i]
        print(f"ANALYST DECISION: {decision_text}")
        print(f"REASON: {reason}")
        print()

        queue.process_decision(
            item['item_id'],
            decision_text,
            analyst_id="analyst_pradip"
        )

    # ── Print final summary ───────────────────────────────
    queue.print_queue_summary()

    print()
    print("=" * 60)
    print("GRAPH STATE AFTER REVIEW")
    print("=" * 60)
    summary = graph.get_graph_summary()
    print(f"Confirmed matches in graph: "
          f"{summary['confirmed_matches']}")
    print()
    print("These confirmed matches now inform")
    print("all future transaction screening.")
    print("The system has learned from analyst decisions.")