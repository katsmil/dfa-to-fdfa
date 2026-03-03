import networkx as nx
from collections import defaultdict, deque
from typing import Set, Tuple, List, Dict, Optional

from approaches.shared.base_analyzer import BaseSubstructureAnalyzer
from approaches.shared.shared_types import MatchLocation, CanonicalSubstructure, BlueprintEdge
from approaches.shared.shared_utils import count_non_overlapping_locations, get_internals_and_frontiers

# ---------------------------------------------------------------------------
# ANALYSE ENGINE
# ---------------------------------------------------------------------------

class SubstructureAnalyzer(BaseSubstructureAnalyzer):
    """
    Versie 3: twee-fase BFS (discovery + validatie gescheiden).

    Omdat de algoritmische structuur afwijkt van de fused BFS in de base class,
    wordt find_maximal_overlap hier overriden.

    Geen validatie van incoming edges; controle op structurele validiteit gebeurt
    in de separate fase 2 middels een check op de outgoing edges van de gevonden nodes.
    Incoming edges hoeven niet apart gecheckt te worden,
    omdat fase 2 de structurele consistentie volledig afdekt via de outgoing edges.

    Geërfd van base class: _edge_cache, _sig_cache, _get_edges_cached, get_node_signature.
    Niet geërfd: find_maximal_overlap (andere structuur), _build_match_output (niet nodig).
    """

    def _find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[Dict]:
        if start_a == start_b:
            return None

        # --- FASE 1: BFS Discovery ---
        queue = deque([(start_a, start_b)])
        visited_pairs: List[Tuple[str, str]] = []
        pair_set: Set[Tuple[str, str]] = set()
        nodes_in_a: Set[str] = set()
        nodes_in_b: Set[str] = set()

        while queue:
            pair = queue.popleft()
            if pair in pair_set:
                continue

            n1, n2 = pair

            if n1 == n2:
                continue
            if n1 in nodes_in_b or n2 in nodes_in_a:
                return None
            if self._get_node_signature(n1) != self._get_node_signature(n2):
                continue

            visited_pairs.append(pair)
            pair_set.add(pair)
            nodes_in_a.add(n1)
            nodes_in_b.add(n2)

            e1 = self._get_edges_cached(n1)
            e2 = self._get_edges_cached(n2)
            for label in e1:
                if label in e2:
                    queue.append((e1[label], e2[label]))

        if len(visited_pairs) < self.min_overlap:
            return None

        # --- FASE 2: Structuurvalidatie ---
        pair_mapping = dict(visited_pairs)   # a → b
        nodes_a = [p[0] for p in visited_pairs]
        node_to_idx = {node: i for i, node in enumerate(nodes_a)}
        blueprint_edges = []

        for i, (u_a, u_b) in enumerate(visited_pairs):
            out_a = self._get_edges_cached(u_a)
            out_b = self._get_edges_cached(u_b)

            for label in set(out_a.keys()) | set(out_b.keys()):
                t_a = out_a.get(label)
                t_b = out_b.get(label)
                is_internal_a = t_a in node_to_idx

                if is_internal_a:
                    # B moet naar de gemapte partner van t_a gaan
                    if t_b != pair_mapping.get(t_a):
                        return None
                    blueprint_edges.append(BlueprintEdge(i, node_to_idx[t_a], label))
                else:
                    # Als A extern gaat, mag B nooit intern gaan
                    if t_b in nodes_in_b:
                        return None

        return {
            'start_a': start_a,
            'start_b': start_b,
            'nodes_a': tuple(nodes_a),
            'nodes_b': tuple(p[1] for p in visited_pairs),
            'blueprint_edges': list(set(blueprint_edges)),
        }

    def _build_match_output(self, start_a, start_b, visited_pairs, blueprint_edges):
        # Bewust niet geïmplementeerd: deze variant retourneert direct vanuit
        # _find_maximal_overlap en maakt geen gebruik van de base class interface.
        pass


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[CanonicalSubstructure]:
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)

    buckets: Dict[tuple, List[str]] = defaultdict(list)
    for node in G.nodes():
        buckets[analyzer._get_node_signature(node)].append(node)
    buckets = {k: sorted(v) for k, v in buckets.items() if len(v) >= 2}


    structure_registry: Dict[tuple, Set[MatchLocation]] = defaultdict(set)
    blueprint_store: Dict[tuple, List[BlueprintEdge]] = {}

    for nodes in buckets.values():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                match = analyzer._find_maximal_overlap(nodes[i], nodes[j])
                if not match:
                    continue

                edges_tuple = tuple(sorted(
                    (e.source_idx, e.target_idx, e.label)
                    for e in match['blueprint_edges']
                ))

                internals_a, frontiers_a = get_internals_and_frontiers(analyzer, match['nodes_a'])
                internals_b, frontiers_b = get_internals_and_frontiers(analyzer,match['nodes_b'])

                structure_registry[edges_tuple].add(
                    MatchLocation(
                        start_node=match['start_a'],
                        all_nodes=match['nodes_a'],
                        internals=internals_a,
                        frontiers=frontiers_a,
                    )
                )
                structure_registry[edges_tuple].add(
                    MatchLocation(
                        start_node=match['start_b'],
                        all_nodes=match['nodes_b'],
                        internals=internals_b,
                        frontiers=frontiers_b,
                    )
                )

                if edges_tuple not in blueprint_store:
                    blueprint_store[edges_tuple] = match['blueprint_edges']

    results = []
    for edges_tuple, locations in structure_registry.items():
        loc_list = list(locations)
        canonical_nodes = loc_list[0].all_nodes
        results.append(CanonicalSubstructure(
            canonical_nodes=canonical_nodes,
            overlap_size=len(loc_list[0].all_nodes),
            locations=tuple(loc_list),
            blueprint_edges=blueprint_store[edges_tuple],
        ))

    eff = count_non_overlapping_locations
    return sorted(
        results,
        key=lambda x: (x.overlap_size * eff(x.locations), x.overlap_size),
        reverse=True,
    )