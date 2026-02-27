import networkx as nx
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Set, Tuple, List, Dict, Optional


# ---------------------------------------------------------------------------
# DATASTRUCTUREN
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BlueprintEdge:
    """Een interne edge in de abstracte subroutine, uitgedrukt als indices."""
    source_idx: int
    target_idx: int
    label: str

@dataclass(frozen=True)
class MatchLocation:
    """Representeert één specifieke plek waar de structuur is gevonden."""
    start_node: str       # Expliciete entry node van deze instantie
    all_nodes: List[str]  # Volgorde komt overeen met canonical_nodes in CanonicalSubstructure
    internals: List[str]
    frontiers: List[str]

@dataclass(frozen=True)
class CanonicalSubstructure:
    """
    De 'blauwdruk' van de herhaling.
    
    canonical_nodes[0] is ALTIJD de entry node (BFS-volgorde van de eerste gevonden match).
    blueprint_edges beschrijft de interne topologie als indices in canonical_nodes —
    onafhankelijk van welke concrete nodes de subroutine invullen.
    """
    canonical_nodes: List[str]
    overlap_size: int
    locations: List[MatchLocation]
    blueprint_edges: List[BlueprintEdge]  # Topologie als indices, zelfde als algoritme 1

@dataclass(frozen=True)
class SubstructureMatch:
    """Representeert een strikt bisimilaire match."""
    start_nodes: Tuple[str, str]
    overlap_size: int
    internals: Set[Tuple[str, str]]
    frontiers: Set[Tuple[str, str]]
    all_pairs: Set[Tuple[str, str]]
    # BFS-geordende A-kant nodes (start_a is index 0) — nodig voor blueprint reconstructie
    nodes_a_ordered: Tuple[str, ...]
    blueprint_edges: List[BlueprintEdge]


# ---------------------------------------------------------------------------
# HULPKLASSEN
# ---------------------------------------------------------------------------

class DFAUtils:
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


# ---------------------------------------------------------------------------
# ANALYSE ENGINE
# ---------------------------------------------------------------------------

class SubstructureAnalyzer:
    """
    BFS-gebaseerde bisimilariteitsanalyse met EquivalenceClosure-optimalisatie.

    Slaat blueprint_edges op in SubstructureMatch zodat aggregate_canonical_results
    op dezelfde topologie-gebaseerde hash kan werken als algoritme 1.
    """

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

    def get_node_signature(self, node: str) -> Tuple:
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
        visited_pairs = []   # BFS-volgorde: visited_pairs[0] = (start_a, start_b)
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

        # Blueprint edges berekenen op basis van BFS-volgorde van A-kant
        # visited_pairs is in BFS-volgorde, dus visited_pairs[0] = (start_a, start_b)
        nodes_a_ordered = tuple(n1 for n1, n2 in visited_pairs)
        node_to_idx = {node: i for i, node in enumerate(nodes_a_ordered)}

        blueprint_edges = []
        for i, (u_a, _) in enumerate(visited_pairs):
            for label, t_a in self._get_edges_cached(u_a).items():
                if t_a in node_to_idx:
                    blueprint_edges.append(BlueprintEdge(i, node_to_idx[t_a], label))

        return SubstructureMatch(
            start_nodes=(start_a, start_b),
            overlap_size=len(visited_pairs),
            internals=internals,
            frontiers=frontiers,
            all_pairs=set(visited_pairs),
            nodes_a_ordered=nodes_a_ordered,      # BFS-volgorde bewaard
            blueprint_edges=list(set(blueprint_edges))
        )


# ---------------------------------------------------------------------------
# AGGREGATIE
# ---------------------------------------------------------------------------

def aggregate_canonical_results(matches: List[SubstructureMatch]) -> List[CanonicalSubstructure]:
    """
    Groepeert matches op canonieke structuur via blueprint-gebaseerde hash.

    Zelfde aanpak als algoritme 1: de edges_tuple (gesorteerde interne topologie)
    is de hash — niet de concrete node-namen. Hierdoor worden locaties gegroepeerd
    op structuurvorm, ongeacht welke nodes toevallig de A-kant waren.

    canonical_nodes = de A-kant nodes van de eerste match voor deze blueprint,
    in BFS-volgorde (canonical_nodes[0] = entry node).
    """
    # edges_tuple → lijst van matches met dezelfde topologie
    structure_registry: Dict[tuple, List[SubstructureMatch]] = defaultdict(list)

    for m in matches:
        edges_tuple = tuple(sorted(
            (e.source_idx, e.target_idx, e.label)
            for e in m.blueprint_edges
        ))
        structure_registry[edges_tuple].append(m)

    final_results = []

    for edges_tuple, related_matches in structure_registry.items():
        first_m = related_matches[0]

        # canonical_nodes = BFS-geordende A-kant van de eerste match
        # nodes_a_ordered[0] = start_a = entry node (gegarandeerd)
        canonical_nodes = list(first_m.nodes_a_ordered)
        canonical_start = canonical_nodes[0]

        # Intern/frontier classificatie op basis van eerste match A-kant
        canonical_internals = [p[0] for p in first_m.internals]
        canonical_frontiers  = [p[0] for p in first_m.frontiers]

        seen_location_keys: Set[tuple] = set()
        locations = []

        def _add_location(start: str, nodes: List[str], internals: List[str], frontiers: List[str]):
            key = tuple(sorted(nodes))
            if key not in seen_location_keys:
                seen_location_keys.add(key)
                locations.append(MatchLocation(
                    start_node=start,
                    all_nodes=nodes,
                    internals=internals,
                    frontiers=frontiers
                ))

        # Voeg A-kant en B-kant van elke match toe als afzonderlijke locaties
        for m in related_matches:
            pair_map_a_to_b = {n1: n2 for n1, n2 in m.all_pairs}
            pair_map_b_to_a = {n2: n1 for n1, n2 in m.all_pairs}

            # A-kant: positie-voor-positie via nodes_a_ordered
            a_nodes   = list(m.nodes_a_ordered)
            a_start   = m.start_nodes[0]
            a_int_set = {p[0] for p in m.internals}
            a_fro_set = {p[0] for p in m.frontiers}
            _add_location(
                a_start,
                a_nodes,
                [n for n in a_nodes if n in a_int_set],
                [n for n in a_nodes if n in a_fro_set]
            )

            # B-kant: gespiegeld via pair_map, zelfde positie-volgorde als A-kant
            b_nodes = [pair_map_a_to_b[n] for n in m.nodes_a_ordered]
            b_start = m.start_nodes[1]
            b_int_set = {p[1] for p in m.internals}
            b_fro_set = {p[1] for p in m.frontiers}
            _add_location(
                b_start,
                b_nodes,
                [n for n in b_nodes if n in b_int_set],
                [n for n in b_nodes if n in b_fro_set]
            )

        final_results.append(CanonicalSubstructure(
            canonical_nodes=canonical_nodes,
            overlap_size=len(canonical_nodes),
            locations=locations,
            blueprint_edges=first_m.blueprint_edges   # topologie is identiek voor alle matches in groep
        ))

    return final_results


# ---------------------------------------------------------------------------
# PRIORITERING & ENTRY POINT
# ---------------------------------------------------------------------------

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