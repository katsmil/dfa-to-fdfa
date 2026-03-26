import networkx as nx
from collections import deque
from typing import Dict, Tuple, List, Optional, Set

from approaches.shared.shared_types import BlueprintEdge, SubstructureMatch
from approaches.shared.shared_utils import get_internals_and_frontiers


class BaseSubstructureAnalyzer:
    """
    Shared BFS core for bisimilarity analysis.
    Subclasses may extend __init__ (for example, to add EquivalenceClosure)
    The full BFS loop, validation, blueprint construction, and match output all
    live here and are not intended to be overridden.
    """

    def __init__(self, G: nx.MultiDiGraph, min_overlap: int = 2):
        self.G = G
        self.min_overlap = min_overlap
        self._edge_cache: Dict[str, Dict[str, str]] = {}
        self._sig_cache: Dict[str, Tuple] = {}

    # ------------------------------------------------------------------
    # CACHING
    # ------------------------------------------------------------------

    def _get_edges_cached(self, node: str) -> Dict[str, str]:
        if node not in self._edge_cache:
            self._edge_cache[node] = {
                d.get('label'): v
                for _, v, d in self.G.out_edges(node, data=True)
            }
        return self._edge_cache[node]

    def _get_node_signature(self, node: str) -> tuple:
        """
        Returns a tuple (is_accepting, sorted_edges) used to compare two nodes for bisimilarity.
        Accepting is determined by 'shape' == 'doublecircle'.
        A self-loop vs. non-self target produces a different signature.
        """
        if node not in self._sig_cache:
            is_accepting = self.G.nodes[node].get('shape') == 'doublecircle'
            edges = self._get_edges_cached(node)
            sig_edges = sorted([(label, target == node) for label, target in edges.items()])
            self._sig_cache[node] = (is_accepting, tuple(sig_edges))
        return self._sig_cache[node]

    # ------------------------------------------------------------------
    # MATCH OUTPUT
    # ------------------------------------------------------------------

    def _build_match_output(self, start_a: str, start_b: str,
                             matched_pairs: List[Tuple[str, str]],
                             blueprint_edges: List[BlueprintEdge]) -> SubstructureMatch:
        nodes_a = tuple(n1 for n1, _ in matched_pairs)
        nodes_b = tuple(n2 for _, n2 in matched_pairs)

        internals_a, frontiers_a = get_internals_and_frontiers(self, nodes_a)
        internals_b, frontiers_b = get_internals_and_frontiers(self, nodes_b)

        return SubstructureMatch(
            start_nodes=(start_a, start_b),
            overlap_size=len(matched_pairs),
            internals_a=internals_a,
            frontiers_a=frontiers_a,
            internals_b=internals_b,
            frontiers_b=frontiers_b,
            all_pairs=frozenset(matched_pairs),
            nodes_a_ordered=nodes_a,
            nodes_b_ordered=nodes_b,
            blueprint_edges=tuple(blueprint_edges),
        )

    # ------------------------------------------------------------------
    # BFS CORE
    # ------------------------------------------------------------------

    def _find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[SubstructureMatch]:
        if start_a == start_b:
            return None

        queue = deque([(start_a, start_b)])
        matched_pairs: List[Tuple[str, str]] = []
        pair_mapping: Dict[str, str] = {}    # a → b
        reverse_mapping: Dict[str, str] = {} # b → a
        nodes_in_a: Set[str] = set()
        nodes_in_b: Set[str] = set()

        while queue:
            n1, n2 = queue.popleft()
            # Skip pairs that reuse an already-matched node on either side.
            if n1 in pair_mapping or n2 in reverse_mapping:
                continue
            # Reject identical nodes (self-pair).
            if n1 == n2:
                continue
            # Prevent crossing: a node from one side can't map into the other side's set.
            if n1 in nodes_in_b or n2 in nodes_in_a:
                return None
            # Must have identical signatures to be comparable.
            if self._get_node_signature(n1) != self._get_node_signature(n2):
                continue

            e1 = self._get_edges_cached(n1)
            e2 = self._get_edges_cached(n2)

            # Incoming validation (part of partial isomorphism check))
            for pred_a in self.G.predecessors(n1):
                if pred_a in pair_mapping:
                    pred_b = pair_mapping[pred_a]
                    for label, target_a in self._get_edges_cached(pred_a).items():
                        if target_a == n1 and self._get_edges_cached(pred_b).get(label) != n2:
                            return None

            for pred_b in self.G.predecessors(n2):
                if pred_b in reverse_mapping:
                    pred_a = reverse_mapping[pred_b]
                    for label, target_b in self._get_edges_cached(pred_b).items():
                        if target_b == n2 and self._get_edges_cached(pred_a).get(label) != n1:
                            return None

            # Outgoing validation: preserve labeled outgoing structure (part of partial isomorphism check).
            for label in set(e1.keys()) | set(e2.keys()):
                t_a = e1.get(label)
                t_b = e2.get(label)
                is_internal_a = t_a is not None and t_a in nodes_in_a
                is_internal_b = t_b is not None and t_b in nodes_in_b
                if is_internal_a != is_internal_b:
                    return None
                if is_internal_a:
                    if t_b != pair_mapping.get(t_a):
                        return None

            # Accept pair
            matched_pairs.append((n1, n2))
            pair_mapping[n1] = n2
            reverse_mapping[n2] = n1
            nodes_in_a.add(n1)
            nodes_in_b.add(n2)

            for label in e1:
                if label in e2:
                    queue.append((e1[label], e2[label]))

        if len(matched_pairs) < self.min_overlap:
            return None

        # Blueprint edges
        nodes_a = [p[0] for p in matched_pairs]
        node_to_idx = {node: i for i, node in enumerate(nodes_a)}
        blueprint_edges = list({
            BlueprintEdge(i, node_to_idx[t_a], label)
            for i, (u_a, _) in enumerate(matched_pairs)
            for label, t_a in self._get_edges_cached(u_a).items()
            if t_a in node_to_idx
        })

        return self._build_match_output(start_a, start_b, matched_pairs, blueprint_edges)
