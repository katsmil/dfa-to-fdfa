import networkx as nx
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Set, Tuple, List, Dict, Optional

@dataclass(frozen=True)
class MatchLocation:
    """Representeert één specifieke plek waar de structuur is gevonden."""
    all_nodes: List[str]
    internals: List[str]
    frontiers: List[str]

@dataclass(frozen=True)
class CanonicalSubstructure:
    """De 'blauwdruk' van de herhaling."""
    canonical_nodes: List[str]  # De nodes in de hoofdautomaat (te vervangen)
    overlap_size: int
    locations: List[MatchLocation] # Alle plekken waar deze structuur voorkomt

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
    """Engine voor het detecteren van bisimilaire overlap via BFS."""
    
    def __init__(self, G: nx.DiGraph, min_overlap: int = 1):
        self.G = G
        self.min_overlap = min_overlap
        self.equivalence_closure = EquivalenceClosure(list(G.nodes()))

    def get_node_signature(self, node: str) -> Tuple[bool, Tuple[Tuple[str, bool], ...]]:
        edges = DFAUtils.get_labeled_edges(self.G, node)
        descriptors = []
        for label, target in edges.items():
            is_self_loop = (target == node)
            descriptors.append((label, is_self_loop))
        descriptors.sort() 
        return (DFAUtils.is_accepting(self.G, node), tuple(descriptors))

    def _check_strict_match(self, n1: str, n2: str) -> bool:
        if DFAUtils.is_accepting(self.G, n1) != DFAUtils.is_accepting(self.G, n2):
            return False
        e1 = DFAUtils.get_labeled_edges(self.G, n1)
        e2 = DFAUtils.get_labeled_edges(self.G, n2)
        if set(e1.keys()) != set(e2.keys()):
            return False
        return True

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[SubstructureMatch]:
        if start_a == start_b or not self._check_strict_match(start_a, start_b):
            return None

        queue = deque([(start_a, start_b)])
        bisimilar_pairs: Set[Tuple[str, str]] = set()
        
        # We houden nog steeds sets bij voor determinisme binnen de match,
        # maar we blokkeren niet langer op basis van bereikbaarheid.
        nodes_in_a: Set[str] = set()
        nodes_in_b: Set[str] = set()

        while queue:
            pair = queue.popleft()
            if pair in bisimilar_pairs:
                continue

            n1, n2 = pair
            # Een node mag nooit met zichzelf matchen (identiteit is geen herhaling)
            if n1 == n2:
                return None 

            if self._check_strict_match(n1, n2):
                bisimilar_pairs.add(pair)
                nodes_in_a.add(n1)
                nodes_in_b.add(n2)
                
                e1, e2 = DFAUtils.get_labeled_edges(self.G, n1), DFAUtils.get_labeled_edges(self.G, n2)
                for label in e1:
                    queue.append((e1[label], e2[label]))

        if len(bisimilar_pairs) < self.min_overlap:
            return None

        internals: Set[Tuple[str, str]] = set()
        frontiers: Set[Tuple[str, str]] = set()
        
        for p in bisimilar_pairs:
            n1, n2 = p
            edges1 = DFAUtils.get_labeled_edges(self.G, n1)
            is_frontier_a = any(target not in nodes_in_a for target in edges1.values())
            
            if is_frontier_a:
                frontiers.add(p)
            else:
                internals.add(p)

        return SubstructureMatch(
            start_nodes=(start_a, start_b),
            overlap_size=len(bisimilar_pairs),
            internals=internals,
            frontiers=frontiers,
            all_pairs=bisimilar_pairs
        )

def aggregate_canonical_results(matches: List[SubstructureMatch]) -> List[CanonicalSubstructure]:
    groups = defaultdict(list)
    for m in matches:
        key = tuple(sorted(list(set(n1 for n1, n2 in m.all_pairs))))
        groups[key].append(m)

    final_results = []
    
    for canonical_key, related_matches in groups.items():
        canonical_nodes = list(canonical_key)
        first_m = related_matches[0]
        
        # 1. Bepaal welke van de canonical_nodes internals/frontiers zijn
        # We kijken naar de A-kant van de eerste match
        canonical_internals = [p[0] for p in first_m.internals]
        canonical_frontiers = [p[0] for p in first_m.frontiers]

        # 2. VOEG DE CANONICAL LOCATIE ZELF TOE
        # Dit zorgt ervoor dat ook de 'bron' wordt vervangen door een RC node.
        locations = [
            MatchLocation(
                all_nodes=canonical_nodes,
                internals=canonical_internals,
                frontiers=canonical_frontiers
            )
        ]
        
        # Houd bij welke sets nodes we al hebben (om duplicaten te voorkomen)
        seen_location_keys = {tuple(sorted(canonical_nodes))}

        # 3. Voeg de andere gevonden locaties toe
        for m in related_matches:
            pair_map = {n1: n2 for n1, n2 in m.all_pairs}
            loc_nodes = [pair_map[cn] for cn in canonical_nodes]
            
            loc_key = tuple(sorted(loc_nodes))
            if loc_key not in seen_location_keys:
                locations.append(MatchLocation(
                    all_nodes=loc_nodes,
                    internals=[pair_map[cn] for cn in canonical_nodes if cn in canonical_internals],
                    frontiers=[pair_map[cn] for cn in canonical_nodes if cn in canonical_frontiers]
                ))
                seen_location_keys.add(loc_key)

        final_results.append(CanonicalSubstructure(
            canonical_nodes=canonical_nodes,
            overlap_size=len(canonical_nodes),
            locations=locations
        ))

    return final_results

# def _filter_redundant_matches(results: List[SubstructureMatch]) -> List[SubstructureMatch]:
#     sorted_res = sorted(results, key=lambda x: x.overlap_size, reverse=True)
#     unique_matches: List[SubstructureMatch] = []
#     for current in sorted_res:
#         if not any(current.all_pairs.issubset(u.all_pairs) for u in unique_matches):
#             unique_matches.append(current)
#     return unique_matches

# --- Voeg deze functies toe aan je analyse bestand ---

def calculate_savings(sub: CanonicalSubstructure) -> int:
    """
    Berekent de 'winst' in termen van nodes.
    Formule: (Oud aantal nodes) - (Nieuw aantal nodes)
    Oud = grootte_patroon * aantal_keer_gebruikt
    Nieuw = grootte_patroon (de blauwdruk) + aantal_keer_gebruikt (de RC nodes)
    """
    n = sub.overlap_size
    k = len(sub.locations)
    if k < 2: return -9999 # Factorisatie heeft geen zin bij 1 locatie
    return (n * k) - (n + k)

def prioritize_candidates(candidates: List[CanonicalSubstructure]) -> List[CanonicalSubstructure]:
    """
    Sorteert kandidaten op economische impact zonder conflicten hard te filteren.
    Dit creëert een 'wenslijst' voor de factorisatie.
    """
    # 1. Bereken scores en filter verliesgevende opties direct weg
    scored_candidates = []
    for sub in candidates:
        score = calculate_savings(sub)
        if score > 0:
            scored_candidates.append((score, sub))

    # 2. Sorteer: hoogste score eerst. 
    # Bij gelijke score kan lengte (overlap_size) de tie-breaker zijn.
    scored_candidates.sort(key=lambda x: (x[0], x[1].overlap_size), reverse=True)

    # 3. Geef alleen de structuren terug (zonder de score wrapper)
    return [sub for score, sub in scored_candidates]

def run_analysis(dot_file: str, min_size: int = 2) -> List[CanonicalSubstructure]:
    G = nx.nx_pydot.read_dot(dot_file)
    G = nx.relabel_nodes(G, {n: n.strip('"') for n in G.nodes()})
    
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    buckets = defaultdict(list)
    for node in G.nodes():
        buckets[analyzer.get_node_signature(node)].append(node)
    
    raw_results = []
    compared = set()
    
    for candidates in buckets.values():
        for i, n1 in enumerate(candidates):
            for n2 in candidates[i+1:]:
                # if analyzer.equivalence_closure.are_equivalent(n1, n2):
                #     continue
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared: continue
                compared.add(pair_id)
                match = analyzer.find_maximal_overlap(n1, n2)
                if match:
                    raw_results.append(match)

    # Stap 1: Aggregeren (inclusief self-locatie)
    canonical_candidates = aggregate_canonical_results(raw_results)
    
    # Stap 2: Prioriteren (Nieuwe logica: geen harde filtering)
    priority_plan = prioritize_candidates(canonical_candidates)
    
    return priority_plan