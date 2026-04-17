import networkx as nx
from collections import defaultdict
from typing import List, Tuple, Set, Dict

from approaches.shared.base_analyzer import BaseSubstructureAnalyzer
from approaches.shared.factorize import _is_accepting_node
from approaches.shared.shared_types import MatchLocation, BlueprintSubstructure, SubstructureMatch

from approaches.shared.shared_utils import build_signature_buckets

# ---------------------------------------------------------------------------
# HELPER CLASSES
# ---------------------------------------------------------------------------

class EquivalenceClosure:
    """
    Tracks which nodes are already grouped together.

    Example (from input/miscellaneous/commonState.dot):
    - Suppose we match a1 with b1, and a2 with b2.
    - After add_equivalence("a1", "b1") and add_equivalence("a2", "b2"),
      the groups are {a1, b1} and {a2, b2} (all other nodes are alone).
    - are_equivalent("a1", "b1") -> True
    - are_equivalent("a1", "a2") -> False
    - If later we also match b1 with a2, then the groups merge and
      {a1, b1, a2, b2} becomes one group (transitive closure grows).
    - Calling _find("b2") returns the shared group leader (root) for
      all nodes in that merged group.
    - Because of that, are_equivalent("a1", "b2") is True, so a later
      comparison between a1 and b2 will be skipped.
    """
    def __init__(self, elements: List[str]):
        # Each node starts in its own group.
        self.parent = {e: e for e in elements}

    def _find(self, x: str) -> str:
        # Find the group leader (root) and shorten the path.
        if self.parent[x] != x:
            self.parent[x] = self._find(self.parent[x])
        return self.parent[x]

    def add_equivalence(self, x: str, y: str):
        # Merge the groups of x and y.
        root_x, root_y = self._find(x), self._find(y)
        if root_x != root_y:
            self.parent[root_x] = root_y

    def are_equivalent(self, x: str, y: str) -> bool:
        # True if x and y are already in the same group.
        return self._find(x) == self._find(y)


# ---------------------------------------------------------------------------
# ANALYSIS ENGINE
# ---------------------------------------------------------------------------

class SubstructureAnalyzer(BaseSubstructureAnalyzer):
    """
    Extends the base analyzer with an EquivalenceClosure to avoid re-matching
    already-paired nodes. This variant aims to maximize runtime efficiency.
    """

    def __init__(self, G: nx.DiGraph, min_overlap: int = 1):
        super().__init__(G, min_overlap)
        # Tracks matched nodes so we avoid re-matching equivalent pairs.
        self.equivalence_closure = EquivalenceClosure(list(G.nodes()))


# ---------------------------------------------------------------------------
# AGGREGATION & PRIORITIZATION
# ---------------------------------------------------------------------------

def _aggregate_blueprint_results(matches: List[SubstructureMatch], analyzer: BaseSubstructureAnalyzer) -> List[BlueprintSubstructure]:
    """
    Combine raw pairwise matches into unique BlueprintSubstructure objects.
    Deduplicate locations that map to the same set of nodes.
    """
    structure_registry: Dict[tuple, List[SubstructureMatch]] = defaultdict(list)

    # Group raw matches by identical blueprint structure and accepting profile.
    for m in matches:
        # Use the blueprint edge set as a stable key for identical structures.
        edges_tuple = tuple(sorted(
            (e.source_idx, e.target_idx, e.label) for e in m.blueprint_edges
        ))
        acceptance_tuple = tuple(
            _is_accepting_node(analyzer.G, n)
            for n in m.nodes_a_ordered
        )
        key = (edges_tuple, acceptance_tuple)
        structure_registry[key].append(m)

    final_results = []

    # For each unique structure, collect all concrete locations where it occurs.
    for key, related_matches in structure_registry.items():
        first_m = related_matches[0]
        seen_location_keys: Set[tuple] = set()
        locations: List[MatchLocation] = []

        def _add_location(start, nodes, internals, frontiers):
            # Avoid adding the same location twice when it appears in multiple matches.
            key = tuple(sorted(nodes))
            if key not in seen_location_keys:
                seen_location_keys.add(key)
                locations.append(MatchLocation(
                    start_node=start,
                    all_nodes=nodes,
                    internals=internals,
                    frontiers=frontiers,
                ))

        # Add both sides of each match as locations for this structure.
        for m in related_matches:
            # Each match yields two concrete locations: side A and side B.
            _add_location(m.start_nodes[0], m.nodes_a_ordered, m.internals_a, m.frontiers_a)
            _add_location(m.start_nodes[1], m.nodes_b_ordered, m.internals_b, m.frontiers_b)

        final_results.append(BlueprintSubstructure(
            blueprint_nodes=first_m.nodes_a_ordered,
            overlap_size=len(first_m.nodes_a_ordered),
            locations=tuple(locations),
            blueprint_edges=first_m.blueprint_edges,
        ))

    return final_results


def _calculate_savings(sub: BlueprintSubstructure) -> int:
    """Estimated node savings if this blueprint is factored out."""
    k = len(sub.locations)
    return sub.overlap_size * (k - 1) if k >= 2 else 0


def _prioritize_candidates(candidates: List[BlueprintSubstructure]) -> List[BlueprintSubstructure]:
    """
    Rank candidates by estimated savings (highest first).
    Ties are broken by overlap size (larger overlap first).
    """
    scored = [
        (savings, s)
        for s in candidates
        if (savings := _calculate_savings(s)) > 0
    ]
    scored.sort(key=lambda x: (x[0], x[1].overlap_size), reverse=True)
    return [s for _, s in scored]


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[BlueprintSubstructure]:
    """Find and rank repeated substructures using equivalence-closure pruning."""
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    # Bucket nodes by signature so we only compare plausible candidates.
    buckets = build_signature_buckets(analyzer)

    raw_results: List[SubstructureMatch] = []
    compared: Set[Tuple[str, str]] = set()

    # Compare nodes only within the same signature bucket.
    for candidates in buckets.values():
        if len(candidates) < 2:
            continue
        # Generate all unique unordered pairs inside the bucket.
        for i, n1 in enumerate(candidates):
            for n2 in candidates[i + 1:]:
                # Skip pairs already known to be equivalent or compared.
                if analyzer.equivalence_closure.are_equivalent(n1, n2):
                    continue
                pair_id = tuple(sorted((n1, n2)))
                # Skip pairs we've already compared in a different order.
                if pair_id in compared:
                    continue
                compared.add(pair_id)

                # Compute maximal overlap; if found, register all paired nodes as equivalent.
                match = analyzer._find_maximal_overlap(n1, n2)
                if match:
                    # Merge all paired nodes to avoid re-matching them later.
                    for a, b in match.all_pairs:
                        analyzer.equivalence_closure.add_equivalence(a, b)
                    raw_results.append(match)

    # Aggregate duplicate structures and prioritize by estimated savings.
    return _prioritize_candidates(_aggregate_blueprint_results(raw_results, analyzer))
