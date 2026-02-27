import networkx as nx
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Set, Tuple, List, Dict, Optional

@dataclass(frozen=True)
class MatchLocation:
    """Representeert één specifieke plek waar de structuur is gevonden."""
    start_node: str          # Expliciete entry node van deze instantie
    all_nodes: List[str]     # Volgorde komt overeen met canonical_nodes in CanonicalSubstructure
    internals: List[str]
    frontiers: List[str]

@dataclass(frozen=True)
class CanonicalSubstructure:
    """De 'blauwdruk' van de herhaling."""
    canonical_nodes: List[str]   # canonical_nodes[0] is ALTIJD de entry node (BFS-volgorde)
    overlap_size: int
    locations: List[MatchLocation]

@dataclass(frozen=True)
class SubstructureMatch:
    """Representeert een strikt bisimilaire match."""
    start_nodes: Tuple[str, str]
    overlap_size: int
    internals: Set[Tuple[str, str]]
    frontiers: Set[Tuple[str, str]]
    all_pairs: Set[Tuple[str, str]]

class DFAUtils:
    """Hulpmiddelen voor het analyseren van DFA-eigenschappen."""
    @staticmethod
    def is_accepting(G: nx.DiGraph, node: str) -> bool:
        data = G.nodes[node]
        return data.get('shape') == 'doublecircle' or data.get('accepting') == 'true'

    @staticmethod
    def get_labeled_edges(G: nx.DiGraph, node: str) -> Dict[str, str]:
        return {d['label']: v for _, v, d in G.out_edges(node, data=True) if 'label' in d}

class EquivalenceClosure:
    """Union-Find voor Hopcroft-Karp equivalentie-sluitingen."""
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

class SubstructureAnalyzer:
    def __init__(self, G: nx.DiGraph, min_overlap: int = 1):
        self.G = G
        self.min_overlap = min_overlap
        self.equivalence_closure = EquivalenceClosure(list(G.nodes()))
        self._signature_cache: Dict[str, Tuple] = {}
        self._edge_cache: Dict[str, Dict[str, str]] = {}
        self._accepting_cache: Dict[str, bool] = {}

    def _get_edges_cached(self, node: str) -> Dict[str, str]:
        if node not in self._edge_cache:
            self._edge_cache[node] = DFAUtils.get_labeled_edges(self.G, node)
        return self._edge_cache[node]

    def _is_accepting_cached(self, node: str) -> bool:
        if node not in self._accepting_cache:
            self._accepting_cache[node] = DFAUtils.is_accepting(self.G, node)
        return self._accepting_cache[node]

    def get_node_signature(self, node: str) -> Tuple[bool, Tuple[Tuple[str, bool], ...]]:
        if node in self._signature_cache:
            return self._signature_cache[node]
        edges = self._get_edges_cached(node)
        descriptors = sorted([(label, target == node) for label, target in edges.items()])
        sig = (self._is_accepting_cached(node), tuple(descriptors))
        self._signature_cache[node] = sig
        return sig

    def _check_strict_match(self, n1: str, n2: str) -> bool:
        return self.get_node_signature(n1) == self.get_node_signature(n2)

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[SubstructureMatch]:
        if start_a == start_b:
            return None

        queue = deque([(start_a, start_b)])
        visited_pairs = []
        pair_set = set()
        pair_mapping = {}
        reverse_mapping = {}
        nodes_in_a = set()
        nodes_in_b = set()

        while queue:
            n1, n2 = queue.popleft()
            if (n1, n2) in pair_set:
                continue
            if n1 == n2:
                continue
            if n1 in nodes_in_b or n2 in nodes_in_a:
                return None
            if not self._check_strict_match(n1, n2):
                continue

            e1 = self._get_edges_cached(n1)
            e2 = self._get_edges_cached(n2)

            # Inkomende validatie
            for pred_a in self.G.predecessors(n1):
                if pred_a in pair_mapping:
                    pred_b = pair_mapping[pred_a]
                    pred_edges_a = self._get_edges_cached(pred_a)
                    pred_edges_b = self._get_edges_cached(pred_b)
                    for label, target_a in pred_edges_a.items():
                        if target_a == n1 and pred_edges_b.get(label) != n2:
                            return None

            for pred_b in self.G.predecessors(n2):
                if pred_b in reverse_mapping:
                    pred_a = reverse_mapping[pred_b]
                    pred_edges_a = self._get_edges_cached(pred_a)
                    pred_edges_b = self._get_edges_cached(pred_b)
                    for label, target_b in pred_edges_b.items():
                        if target_b == n2 and pred_edges_a.get(label) != n1:
                            return None

            # Uitgaande validatie
            all_labels = set(e1.keys()) | set(e2.keys())
            for label in all_labels:
                t_a = e1.get(label)
                t_b = e2.get(label)
                is_internal_a = t_a is not None and t_a in nodes_in_a
                is_internal_b = t_b is not None and t_b in nodes_in_b
                if (is_internal_a and not is_internal_b) or (not is_internal_a and is_internal_b):
                    return None
                if is_internal_a:
                    if t_b != pair_mapping.get(t_a):
                        return None
                else:
                    if t_a is not None and t_b is not None and t_b in nodes_in_b:
                        return None

            # Accepteer paar
            visited_pairs.append((n1, n2))
            pair_set.add((n1, n2))
            pair_mapping[n1] = n2
            reverse_mapping[n2] = n1
            nodes_in_a.add(n1)
            nodes_in_b.add(n2)

            for label in e1:
                if label in e2:
                    queue.append((e1[label], e2[label]))

        if len(visited_pairs) < self.min_overlap:
            return None

        # Classificatie: intern vs frontier
        internals = set()
        frontiers = set()
        for n1, n2 in visited_pairs:
            out1 = self._get_edges_cached(n1)
            has_external = any(t not in nodes_in_a for t in out1.values())
            if has_external:
                frontiers.add((n1, n2))
            else:
                internals.add((n1, n2))

        return SubstructureMatch(
            start_nodes=(start_a, start_b),
            overlap_size=len(visited_pairs),
            internals=internals,
            frontiers=frontiers,
            all_pairs=set(visited_pairs)
        )


def aggregate_canonical_results(matches: List[SubstructureMatch]) -> List[CanonicalSubstructure]:
    """
    Groepeert matches op canonieke structuur.

    BELANGRIJK: canonical_nodes bewaart de BFS-volgorde van de A-kant,
    zodat canonical_nodes[0] altijd de entry node (start_a) is.
    De B-kant locatie krijgt dezelfde positie-voor-positie volgorde via pair_map.
    """
    # Key: BFS-geordende tuple van A-kant nodes (NIET gesorteerd)
    groups = defaultdict(list)
    for m in matches:
        # visited_pairs volgorde = BFS-volgorde, start_a is eerste
        # Reconstrueer BFS-volgorde via start_nodes[0] als ankerpunt
        a_nodes_ordered = [n1 for n1, n2 in sorted(
            m.all_pairs,
            key=lambda p: (p[0] != m.start_nodes[0], p[0])
        )]
        key = tuple(a_nodes_ordered)
        groups[key].append(m)

    final_results = []

    for canonical_key, related_matches in groups.items():
        # canonical_nodes[0] = start_a = entry node (gegarandeerd door key-opbouw)
        canonical_nodes = list(canonical_key)
        canonical_start = canonical_nodes[0]

        first_m = related_matches[0]
        canonical_internals = [p[0] for p in first_m.internals]
        canonical_frontiers  = [p[0] for p in first_m.frontiers]

        # Locatie A (de canonieke zijde zelf)
        locations = [
            MatchLocation(
                start_node=canonical_start,
                all_nodes=canonical_nodes,
                internals=canonical_internals,
                frontiers=canonical_frontiers
            )
        ]
        seen_location_keys = {tuple(sorted(canonical_nodes))}

        for m in related_matches:
            pair_map = {n1: n2 for n1, n2 in m.all_pairs}

            # B-kant nodes in dezelfde volgorde als canonical_nodes (positie-voor-positie)
            loc_nodes    = [pair_map[cn] for cn in canonical_nodes]
            loc_start    = pair_map[canonical_start]     # expliciete start node B-kant
            loc_internals = [pair_map[cn] for cn in canonical_internals]
            loc_frontiers = [pair_map[cn] for cn in canonical_frontiers]

            loc_key = tuple(sorted(loc_nodes))
            if loc_key not in seen_location_keys:
                locations.append(MatchLocation(
                    start_node=loc_start,
                    all_nodes=loc_nodes,
                    internals=loc_internals,
                    frontiers=loc_frontiers
                ))
                seen_location_keys.add(loc_key)

        final_results.append(CanonicalSubstructure(
            canonical_nodes=canonical_nodes,
            overlap_size=len(canonical_nodes),
            locations=locations
        ))

    return final_results


def calculate_savings(sub: CanonicalSubstructure) -> int:
    n = sub.overlap_size
    k = len(sub.locations)
    if k < 2:
        return 0
    return n * (k - 1)


def prioritize_candidates(candidates: List[CanonicalSubstructure]) -> List[CanonicalSubstructure]:
    scored = [(calculate_savings(sub), sub) for sub in candidates if calculate_savings(sub) > 0]
    scored.sort(key=lambda x: (x[0], x[1].overlap_size), reverse=True)
    return [sub for _, sub in scored]


def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[CanonicalSubstructure]:
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    buckets = defaultdict(list)

    for node in G.nodes():
        buckets[analyzer.get_node_signature(node)].append(node)

    raw_results = []
    compared = set()

    for candidates in buckets.values():
        if len(candidates) < 2:
            continue
        for i, n1 in enumerate(candidates):
            for n2 in candidates[i+1:]:
                if analyzer.equivalence_closure.are_equivalent(n1, n2):
                    continue
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared:
                    continue
                compared.add(pair_id)

                match = analyzer.find_maximal_overlap(n1, n2)
                if match:
                    for a, b in match.all_pairs:
                        analyzer.equivalence_closure.add_equivalence(a, b)
                    raw_results.append(match)

    canonical_candidates = aggregate_canonical_results(raw_results)
    return prioritize_candidates(canonical_candidates)