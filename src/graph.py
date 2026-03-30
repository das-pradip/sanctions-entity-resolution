# src/graph.py
#
# WHY THIS FILE EXISTS:
# Our scoring pipeline treats every comparison independently.
# It has no memory of past decisions.
# A graph store gives the system memory.
#
# WHAT A GRAPH IS:
# A graph has two things:
# - Nodes: represent entities (sanctioned people)
# - Edges: represent connections between entities
#
# Example:
# Node: FATIMA-AL-HASSAN
#   └── edge: SAME_DOB → Node: FATIMA-AL-RASHIDI
#   └── edge: SAME_COUNTRY → Node: FATIMA-AL-RASHIDI
#   └── edge: CONFIRMED_MATCH (analyst verified 2018)
#
# WHY GRAPH NOT DATABASE TABLE:
# A table stores attributes OF an entity.
# A graph stores RELATIONSHIPS BETWEEN entities.
# Relationships are first-class citizens in a graph.
# This makes it natural to ask:
# "Who is connected to this person and how?"
#
# In production: Neo4j is the industry standard graph database
# Here: we build a simple graph using Python dictionaries
# to teach the concept before introducing Neo4j

import json
from datetime import datetime


# ============================================================
# GRAPH DATA STRUCTURE
# ============================================================

class EntityGraph:
    """
    A simple in-memory graph of sanctioned entities.

    Nodes: sanctioned entity records
    Edges: connections between entities

    Edge types:
    - SAME_PERSON: confirmed by analyst — same entity
    - SAME_DOB: share identical date of birth
    - SAME_COUNTRY: share same country
    - SAME_PASSPORT: share passport number
    - ALIAS_OF: one name is alias of another
    - TEMPORAL_DRIFT: same person, name changed over time

    WHY TYPED EDGES:
    Not all connections mean the same thing.
    SAME_PASSPORT is stronger evidence than SAME_COUNTRY.
    Typed edges let us weight connections differently
    when traversing the graph for matches.
    """

    def __init__(self):
        # nodes: entity_id → entity data
        # WHY DICTIONARY: O(1) lookup by entity ID
        self.nodes = {}

        # edges: entity_id → list of connections
        # WHY ADJACENCY LIST not MATRIX:
        # Most entity pairs are NOT connected
        # Matrix would be mostly empty — wasteful
        # Adjacency list only stores actual connections
        self.edges = {}

        # confirmed_matches: set of (id1, id2) tuples
        # analyst-verified same-person pairs
        self.confirmed_matches = set()

    # ── Node operations ───────────────────────────────────

    def add_node(self, entity_id, entity_data):
        """
        Adds a sanctioned entity to the graph.

        WHY STORE FULL DATA:
        When we traverse the graph to find related entities,
        we need access to all their attributes —
        not just their ID.
        """
        self.nodes[entity_id] = {
            'id':       entity_id,
            'data':     entity_data,
            'added_at': datetime.now().isoformat()
        }

        # Initialise empty edge list for this node
        if entity_id not in self.edges:
            self.edges[entity_id] = []

    def get_node(self, entity_id):
        """Returns node data for an entity ID."""
        return self.nodes.get(entity_id)

    # ── Edge operations ───────────────────────────────────

    def add_edge(self, id1, id2, edge_type, confidence=1.0,
                 reason=""):
        """
        Adds a directed edge between two entities.

        WHY DIRECTED:
        We add edges in both directions explicitly.
        id1 → id2 and id2 → id1
        This makes traversal simpler — we always look
        at outgoing edges regardless of direction.

        Parameters:
        edge_type:  string describing the connection type
        confidence: 0.0 to 1.0 — how strong is this link
        reason:     human readable explanation
        """
        # Add edge from id1 to id2
        self._add_directed_edge(id1, id2, edge_type,
                                confidence, reason)
        # Add reverse edge from id2 to id1
        self._add_directed_edge(id2, id1, edge_type,
                                confidence, reason)

    def _add_directed_edge(self, from_id, to_id, edge_type,
                           confidence, reason):
        """Adds one directed edge."""
        if from_id not in self.edges:
            self.edges[from_id] = []

        # Check if edge already exists — update confidence
        for edge in self.edges[from_id]:
            if (edge['to'] == to_id and
                    edge['type'] == edge_type):
                # Update existing edge with higher confidence
                edge['confidence'] = max(
                    edge['confidence'], confidence
                )
                return

        # Add new edge
        self.edges[from_id].append({
            'to':         to_id,
            'type':       edge_type,
            'confidence': confidence,
            'reason':     reason,
            'added_at':   datetime.now().isoformat()
        })

    def get_connections(self, entity_id):
        """
        Returns all entities connected to this one.

        Returns list of dicts with:
        - connected_id: the other entity's ID
        - edge_type: how they are connected
        - confidence: strength of connection
        - reason: why they were connected
        """
        return self.edges.get(entity_id, [])

    # ── Confirmed matches ─────────────────────────────────

    def confirm_match(self, id1, id2, analyst_id="system"):
        """
        Records an analyst-confirmed match between
        two entity records.

        WHY THIS IS IMPORTANT:
        When an analyst confirms two records are the
        same person — that knowledge must be stored.
        Future transactions can then be checked against
        this confirmed graph — not just the raw scoring.

        This is how the system learns over time.
        """
        pair = tuple(sorted([id1, id2]))
        self.confirmed_matches.add(pair)

        # Add strong SAME_PERSON edge
        self.add_edge(
            id1, id2,
            edge_type  = "SAME_PERSON",
            confidence = 1.0,
            reason     = f"Confirmed by analyst: {analyst_id}"
        )

    def is_confirmed_match(self, id1, id2):
        """Returns True if these two records are
        confirmed by an analyst as same person."""
        pair = tuple(sorted([id1, id2]))
        return pair in self.confirmed_matches

    # ── Graph building ────────────────────────────────────

    def build_from_records(self, records):
        """
        Builds the graph from a list of sanctions records.

        Step 1: Add all records as nodes
        Step 2: Create edges for shared attributes

        Shared attributes that create edges:
        - Same country → SAME_COUNTRY edge
        - Same DOB year → SAME_DOB edge
        - Same passport → SAME_PASSPORT edge
        - Alias match → ALIAS_OF edge

        WHY BUILD EDGES FROM SHARED ATTRIBUTES:
        These connections are the graph's memory.
        When a new name appears with a known DOB+country
        combination — the graph surfaces the connection
        even before the scoring algorithm sees it.
        """
        # Step 1: Add all nodes
        for record in records:
            self.add_node(record['id'], record)

        # Step 2: Create edges for shared attributes
        n = len(records)
        for i in range(n):
            for j in range(i+1, n):
                r1 = records[i]
                r2 = records[j]

                self._create_attribute_edges(r1, r2)

    def _create_attribute_edges(self, r1, r2):
        """
        Creates edges between two records if they
        share significant attributes.
        """
        id1 = r1['id']
        id2 = r2['id']

        # ── Passport match ────────────────────────────
        p1 = r1.get('passport')
        p2 = r2.get('passport')
        if p1 and p2 and p1.upper() == p2.upper():
            self.add_edge(
                id1, id2,
                edge_type  = "SAME_PASSPORT",
                confidence = 1.0,
                reason     = f"Identical passport: {p1}"
            )

        # ── DOB match ─────────────────────────────────
        dob1 = r1.get('dob')
        dob2 = r2.get('dob')
        if dob1 and dob2:
            try:
                year1 = int(str(dob1)[:4])
                year2 = int(str(dob2)[:4])
                if abs(year1 - year2) <= 2:
                    self.add_edge(
                        id1, id2,
                        edge_type  = "SAME_DOB",
                        confidence = 0.8,
                        reason     = f"DOB within 2 years:"
                                     f" {dob1} vs {dob2}"
                    )
            except (ValueError, TypeError):
                pass

        # ── Country match ─────────────────────────────
        c1 = r1.get('country')
        c2 = r2.get('country')
        if c1 and c2 and c1.lower() == c2.lower():
            self.add_edge(
                id1, id2,
                edge_type  = "SAME_COUNTRY",
                confidence = 0.5,
                reason     = f"Same country: {c1}"
            )

        # ── Alias match ───────────────────────────────
        # Check if any alias of r1 appears in r2's names
        aliases1 = r1.get('aliases', []) or []
        aliases2 = r2.get('aliases', []) or []
        name2    = r2.get('name', '')
        name1    = r1.get('name', '')

        all_names2 = [name2] + aliases2
        for alias in aliases1:
            for name in all_names2:
                if (alias and name and
                        alias.lower() == name.lower()):
                    self.add_edge(
                        id1, id2,
                        edge_type  = "ALIAS_OF",
                        confidence = 0.9,
                        reason     = f"Alias match:"
                                     f" '{alias}'"
                    )

    # ── Graph querying ────────────────────────────────────

    def find_related_entities(self, entity_id,
                               min_confidence=0.5):
        """
        Returns all entities related to this one
        above a minimum confidence threshold.

        WHY THIS IS POWERFUL:
        When a new transaction comes in and partially
        matches an entity — we can find ALL entities
        connected to that one in the graph.

        Example:
        Transaction matches OFAC-001 (Usama Bin Laden)
        Graph traversal finds: UN-001, EU-001
        All three are returned as candidates
        even if the transaction only matched one directly.
        """
        related = []
        for edge in self.get_connections(entity_id):
            if edge['confidence'] >= min_confidence:
                related.append({
                    'entity_id':  edge['to'],
                    'edge_type':  edge['type'],
                    'confidence': edge['confidence'],
                    'reason':     edge['reason'],
                    'node_data':  self.get_node(
                                      edge['to']
                                  )
                })

        # Sort by confidence — strongest connections first
        related.sort(
            key=lambda x: x['confidence'], reverse=True
        )
        return related

    def get_graph_summary(self):
        """Returns statistics about the graph."""
        total_edges = sum(
            len(edges) for edges in self.edges.values()
        )
        edge_types = {}
        for edges in self.edges.values():
            for edge in edges:
                t = edge['type']
                edge_types[t] = edge_types.get(t, 0) + 1

        return {
            'total_nodes':      len(self.nodes),
            'total_edges':      total_edges // 2,
            'confirmed_matches': len(self.confirmed_matches),
            'edge_types':       edge_types,
        }


# ============================================================
# TEST THE GRAPH
# ============================================================

if __name__ == "__main__":

    import sys
    import os
    sys.path.append(
        os.path.join(os.path.dirname(__file__), '..', 'data')
    )
    from synthetic_sanctions import (
        SANCTIONS_RECORDS,
        GROUND_TRUTH_CLUSTERS
    )

    print("=" * 55)
    print("BUILDING ENTITY GRAPH")
    print("=" * 55)

    # Build graph from all sanctions records
    graph = EntityGraph()
    graph.build_from_records(SANCTIONS_RECORDS)

    # Print summary
    summary = graph.get_graph_summary()
    print(f"Nodes (entities):  {summary['total_nodes']}")
    print(f"Edges (links):     {summary['total_edges']}")
    print(f"Edge types:")
    for edge_type, count in summary['edge_types'].items():
        print(f"  {edge_type:20} {count//2} pairs")

    print()
    print("=" * 55)
    print("GRAPH CONNECTIONS FOR OFAC-001")
    print("(Usama Bin Laden)")
    print("=" * 55)

    connections = graph.find_related_entities("OFAC-001")
    for conn in connections:
        node = conn['node_data']
        name = node['data']['name'] if node else 'unknown'
        print(f"  → {conn['entity_id']:10} {name:35}")
        print(f"    via: {conn['edge_type']:20}"
              f" confidence: {conn['confidence']:.2f}")
        print(f"    why: {conn['reason']}")
        print()

    print()
    print("=" * 55)
    print("CONFIRMING ANALYST MATCHES")
    print("=" * 55)

    # Simulate analyst confirming matches from ground truth
    confirmed = 0
    for cluster in GROUND_TRUTH_CLUSTERS:
        cluster_list = list(cluster)
        for i in range(len(cluster_list)):
            for j in range(i+1, len(cluster_list)):
                graph.confirm_match(
                    cluster_list[i],
                    cluster_list[j],
                    analyst_id="analyst_pradip"
                )
                confirmed += 1

    print(f"Analyst confirmed: {confirmed} match pairs")
    print(f"Graph confirmed:   "
          f"{graph.get_graph_summary()['confirmed_matches']}"
          f" pairs stored")

    print()
    print("=" * 55)
    print("TEMPORAL DRIFT TEST")
    print("=" * 55)
    print()
    print("Scenario: Fatima AL-HASSAN changed name to")
    print("          AL-RASHIDI after marriage.")
    print("          Different passport.")
    print("          Can graph find the connection?")
    print()

    # Check if graph connects these two
    connections = graph.find_related_entities("OFAC-006")
    found_un005 = False
    for conn in connections:
        if conn['entity_id'] == 'UN-005':
            found_un005 = True
            print(f"✅ Graph found connection:")
            print(f"   OFAC-006 (AL-HASSAN) → UN-005 (AL-RASHIDI)")
            print(f"   via: {conn['edge_type']}")
            print(f"   why: {conn['reason']}")
            print(f"   confidence: {conn['confidence']:.2f}")

    if not found_un005:
        print("❌ Graph did not find connection")
        print("   These records share DOB and country")
        print("   Check edge creation logic")