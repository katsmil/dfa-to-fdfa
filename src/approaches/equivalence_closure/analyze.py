import networkx as nx
from collections import defaultdict
from dataclasses import dataclass
from typing import Set, Tuple, List, Dict

from approaches.shared.base_analyzer import BaseSubstructureAnalyzer
from approaches.shared.shared_types import MatchLocation, BlueprintSubstructure, BlueprintEdge
from approaches.shared.shared_utils import build_signature_buckets

# ---------------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubstructureMatch:
    start_nodes: Tuple[str, str]
    overlap_size: int
    internals: Set[Tuple[str, str]]
    frontiers: Set[Tuple[str, str]]
    all_pairs: Set[Tuple[str, str]]
    nodes_a_ordered: Tuple[str, ...]
    blueprint_edges: List[BlueprintEdge]


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
    Version 1: uses EquivalenceClosure
    """

    def __init__(self, G: nx.DiGraph, min_overlap: int = 1):
        super().__init__(G, min_overlap)
        self.equivalence_closure = EquivalenceClosure(list(G.nodes()))

    def _build_match_output(self, start_a, start_b, visited_pairs, blueprint_edges):
        nodes_in_a = {n1 for n1, _ in visited_pairs}
        internals, frontiers = set(), set()

        for n1, n2 in visited_pairs:
            has_external = any(t not in nodes_in_a for t in self._get_edges_cached(n1).values())
            (frontiers if has_external else internals).add((n1, n2))
        
        return SubstructureMatch(
            start_nodes=(start_a, start_b),
            overlap_size=len(visited_pairs),
            internals=internals,
            frontiers=frontiers,
            all_pairs=set(visited_pairs),
            nodes_a_ordered=tuple(n1 for n1, _ in visited_pairs),
            blueprint_edges=blueprint_edges,
        )


# ---------------------------------------------------------------------------
# AGGREGATION & PRIORITIZATION
# ---------------------------------------------------------------------------

def _aggregate_blueprint_results(matches: List[SubstructureMatch]) -> List[BlueprintSubstructure]:
    structure_registry: Dict[tuple, List[SubstructureMatch]] = defaultdict(list)

    for m in matches:
        edges_tuple = tuple(sorted(
            (e.source_idx, e.target_idx, e.label) for e in m.blueprint_edges
        ))
        structure_registry[edges_tuple].append(m)

    final_results = []

    for edges_tuple, related_matches in structure_registry.items():
        first_m = related_matches[0]
        blueprint_nodes = list(first_m.nodes_a_ordered)

        seen_location_keys: Set[tuple] = set()
        locations = []

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
            pair_map = {n1: n2 for n1, n2 in m.all_pairs}
            a_nodes = list(m.nodes_a_ordered)
            a_int = {p[0] for p in m.internals}
            a_fro = {p[0] for p in m.frontiers}
            _add_location(
                m.start_nodes[0], a_nodes,
                [n for n in a_nodes if n in a_int],
                [n for n in a_nodes if n in a_fro],
            )

            b_nodes = [pair_map[n] for n in m.nodes_a_ordered]
            b_int = {p[1] for p in m.internals}
            b_fro = {p[1] for p in m.frontiers}
            _add_location(
                m.start_nodes[1], b_nodes,
                [n for n in b_nodes if n in b_int],
                [n for n in b_nodes if n in b_fro],
            )

        final_results.append(BlueprintSubstructure(
            blueprint_nodes=blueprint_nodes,
            overlap_size=len(blueprint_nodes),
            locations=tuple(locations),
            blueprint_edges=first_m.blueprint_edges,
        ))

    return final_results

def _calculate_savings(sub: BlueprintSubstructure) -> int:
    k = len(sub.locations)
    return sub.overlap_size * (k - 1) if k >= 2 else 0


def _prioritize_candidates(candidates: List[BlueprintSubstructure]) -> List[BlueprintSubstructure]:
    scored = [(_calculate_savings(s), s) for s in candidates if _calculate_savings(s) > 0]
    scored.sort(key=lambda x: (x[0], x[1].overlap_size), reverse=True)
    return [s for _, s in scored]

# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[BlueprintSubstructure]:
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    buckets = build_signature_buckets(analyzer)

    raw_results = []
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