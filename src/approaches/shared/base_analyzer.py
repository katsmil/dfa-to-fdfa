import networkx as nx
from collections import deque
from typing import Dict, Tuple, List, Optional, Set, Any
from approaches.shared.shared_types import BlueprintEdge

class BaseSubstructureAnalyzer:
    """
    Shared BFS core for bisimilarity analysis.

    Subclasses must implement:
      - _build_match_output(...) → determines the return type (SubstructureMatch or dict)

    The full BFS loop, validation, and blueprint construction live here and are NOT overridden.
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
        Accepting is determined by 'shape' == 'doublecircle'. Shared by all subclasses.
        """
        if node not in self._sig_cache:
            is_accepting = self.G.nodes[node].get('shape') == 'doublecircle'
            edges = self._get_edges_cached(node)
            sig_edges = sorted([(label, target == node) for label, target in edges.items()])
            self._sig_cache[node] = (is_accepting, tuple(sig_edges))
        return self._sig_cache[node]

    # ------------------------------------------------------------------
    # BFS CORE  (shared, not to be overridden)
    # ------------------------------------------------------------------

    def _find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[Any]:
        if start_a == start_b:
            return None

        queue = deque([(start_a, start_b)])
        visited_pairs: List[Tuple[str, str]] = []
        pair_mapping: Dict[str, str] = {}   # a → b
        reverse_mapping: Dict[str, str] = {}  # b → a
        nodes_in_a: Set[str] = set()
        nodes_in_b: Set[str] = set()

        while queue:
            n1, n2 = queue.popleft()
            if n1 in pair_mapping:
                continue
            if n1 == n2:
                continue
            if n1 in nodes_in_b or n2 in nodes_in_a:
                return None
            if self._get_node_signature(n1) != self._get_node_signature(n2):
                continue

            e1 = self._get_edges_cached(n1)
            e2 = self._get_edges_cached(n2)

            # Incoming validation
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

            # Outgoing validation
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
                else:
                    if t_a is not None and t_b is not None and t_b in nodes_in_b:
                        return None

            # Accept pair
            visited_pairs.append((n1, n2))
            pair_mapping[n1] = n2
            reverse_mapping[n2] = n1
            nodes_in_a.add(n1)
            nodes_in_b.add(n2)

            for label in e1:
                if label in e2:
                    queue.append((e1[label], e2[label]))

        if len(visited_pairs) < self.min_overlap:
            return None

        # Blueprint edges
        nodes_a = [p[0] for p in visited_pairs]
        node_to_idx = {node: i for i, node in enumerate(nodes_a)}
        blueprint_edges = list({
            BlueprintEdge(i, node_to_idx[t_a], label)
            for i, (u_a, _) in enumerate(visited_pairs)
            for label, t_a in self._get_edges_cached(u_a).items()
            if t_a in node_to_idx
        })

        return self._build_match_output(start_a, start_b, visited_pairs, blueprint_edges)

    # ------------------------------------------------------------------
    # ABSTRACT  (subclass must implement)
    # ------------------------------------------------------------------

    def _build_match_output(self, start_a: str, start_b: str,
                             visited_pairs: List[Tuple[str, str]],
                             blueprint_edges: List[BlueprintEdge]) -> Any:
        raise NotImplementedError