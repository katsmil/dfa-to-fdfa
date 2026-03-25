import networkx as nx
from collections import defaultdict
from typing import List, Tuple, Set, Dict

from approaches.shared.base_analyzer import BaseSubstructureAnalyzer
from approaches.shared.shared_types import MatchLocation, BlueprintSubstructure, SubstructureMatch

from approaches.shared.shared_utils import build_signature_buckets

# ---------------------------------------------------------------------------
# HELPER CLASSES
# ---------------------------------------------------------------------------

class EquivalenceClosure:
    def __init__(self, elements: List[str]):
        self.parent = {e: e for e in elements}

    def _find(self, x: str) -> str:
        if self.parent[x] != x:
            self.parent[x] = self._find(self.parent[x])
        return self.parent[x]

    def add_equivalence(self, x: str, y: str):
        root_x, root_y = self._find(x), self._find(y)
        if root_x != root_y:
            self.parent[root_x] = root_y

    def are_equivalent(self, x: str, y: str) -> bool:
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
        self.equivalence_closure = EquivalenceClosure(list(G.nodes()))


# ---------------------------------------------------------------------------
# AGGREGATION & PRIORITIZATION
# ---------------------------------------------------------------------------

def _aggregate_blueprint_results(matches: List[SubstructureMatch]) -> List[BlueprintSubstructure]:
    """
    Combine all raw matches into unique BlueprintSubstructure objects.
    """
    structure_registry: Dict[tuple, List[SubstructureMatch]] = defaultdict(list)

    for m in matches:
        edges_tuple = tuple(sorted(
            (e.source_idx, e.target_idx, e.label) for e in m.blueprint_edges
        ))
        structure_registry[edges_tuple].append(m)

    final_results = []

    for edges_tuple, related_matches in structure_registry.items():
        first_m = related_matches[0]
        seen_location_keys: Set[tuple] = set()
        locations: List[MatchLocation] = []

        def _add_location(start, nodes, internals, frontiers):
            key = tuple(sorted(nodes))
            if key not in seen_location_keys:
                seen_location_keys.add(key)
                locations.append(MatchLocation(
                    start_node=start,
                    all_nodes=nodes,
                    internals=internals,
                    frontiers=frontiers,
                ))

        for m in related_matches:
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
    k = len(sub.locations)
    return sub.overlap_size * (k - 1) if k >= 2 else 0


def _prioritize_candidates(candidates: List[BlueprintSubstructure]) -> List[BlueprintSubstructure]:
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
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    buckets = build_signature_buckets(analyzer)

    raw_results: List[SubstructureMatch] = []
    compared: Set[Tuple[str, str]] = set()

    for candidates in buckets.values():
        if len(candidates) < 2:
            continue
        for i, n1 in enumerate(candidates):
            for n2 in candidates[i + 1:]:
                if analyzer.equivalence_closure.are_equivalent(n1, n2):
                    continue
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared:
                    continue
                compared.add(pair_id)

                match = analyzer._find_maximal_overlap(n1, n2)
                if match:
                    for a, b in match.all_pairs:
                        analyzer.equivalence_closure.add_equivalence(a, b)
                    raw_results.append(match)

    return _prioritize_candidates(_aggregate_blueprint_results(raw_results))