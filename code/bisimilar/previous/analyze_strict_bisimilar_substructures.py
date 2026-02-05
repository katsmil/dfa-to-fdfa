import networkx as nx
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Set, Tuple, List, Dict, Optional

@dataclass(frozen=True)
class SubstructureMatch:
    """Representeert een zuivere bisimilaire match."""
    start_nodes: Tuple[str, str]
    overlap_size: int
    internals: Set[Tuple[str, str]]   # Volledig bisimilaire kern (alle buren ook bisimilair)
    frontiers: Set[Tuple[str, str]]   # Volledig bisimilaire uitgang (buren vallen buiten match)
    all_pairs: Set[Tuple[str, str]]   # De som van internals + frontiers

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

    def get_node_signature(self, node: str) -> Tuple[bool, Tuple[str, ...]]:
        """Bepaalt de bucket op basis van status en uitgaande labels."""
        labels = sorted(DFAUtils.get_labeled_edges(self.G, node).keys())
        return (DFAUtils.is_accepting(self.G, node), tuple(labels))

    def _check_strict_match(self, n1: str, n2: str) -> bool:
        """Controleert of twee nodes lokaal identiek gedrag vertonen."""
        if DFAUtils.is_accepting(self.G, n1) != DFAUtils.is_accepting(self.G, n2):
            return False
        e1, e2 = DFAUtils.get_labeled_edges(self.G, n1), DFAUtils.get_labeled_edges(self.G, n2)
        return set(e1.keys()) == set(e2.keys())

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[SubstructureMatch]:
        """Verkent de maximale bisimilaire set via BFS."""
        if not self._check_strict_match(start_a, start_b):
            return None

        queue = deque([(start_a, start_b)])
        bisimilar_pairs: Set[Tuple[str, str]] = set()

        # 1. BFS: Verzamel alle paren die aan de bisimulatie-eis voldoen
        while queue:
            pair = queue.popleft()
            if pair in bisimilar_pairs:
                continue

            n1, n2 = pair
            if self._check_strict_match(n1, n2):
                bisimilar_pairs.add(pair)
                self.equivalence_closure.add_equivalence(n1, n2)
                
                e1, e2 = DFAUtils.get_labeled_edges(self.G, n1), DFAUtils.get_labeled_edges(self.G, n2)
                for label in e1:
                    queue.append((e1[label], e2[label]))

        if len(bisimilar_pairs) < self.min_overlap:
            return None

        # 2. Categoriseer: Welke bisimilaire paren zijn internals en welke frontiers?
        internals: Set[Tuple[str, str]] = set()
        frontiers: Set[Tuple[str, str]] = set()

        for p in bisimilar_pairs:
            n1, n2 = p
            e1, e2 = DFAUtils.get_labeled_edges(self.G, n1), DFAUtils.get_labeled_edges(self.G, n2)
            
            # Een paar is frontier als het naar een paar wijst dat NIET bisimilair is
            is_frontier = any((e1[lbl], e2[lbl]) not in bisimilar_pairs for lbl in e1)
            
            if is_frontier:
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

def _filter_redundant_matches(results: List[SubstructureMatch]) -> List[SubstructureMatch]:
    """Behoudt alleen de grootste unieke bisimilaire sets."""
    sorted_res = sorted(results, key=lambda x: x.overlap_size, reverse=True)
    unique_matches: List[SubstructureMatch] = []

    for current in sorted_res:
        # Check of deze set bisimilaire paren al onderdeel is van een grotere set
        if not any(current.all_pairs.issubset(u.all_pairs) for u in unique_matches):
            unique_matches.append(current)
    return unique_matches

def run_analysis(dot_file: str, min_size: int = 2) -> List[SubstructureMatch]:
    """Hoofdfunctie voor de analyse van de graaf."""
    G = nx.nx_pydot.read_dot(dot_file)
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)

    # Buckets vullen voor efficiëntie
    buckets = defaultdict(list)
    for node in G.nodes():
        buckets[analyzer.get_node_signature(node)].append(node)

    raw_results = []
    compared = set()

    for candidates in buckets.values():
        for i, n1 in enumerate(candidates):
            for n2 in candidates[i+1:]:
                if analyzer.equivalence_closure.are_equivalent(n1, n2):
                    continue
                
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared: continue
                compared.add(pair_id)

                match = analyzer.find_maximal_overlap(n1, n2)
                if match:
                    raw_results.append(match)

    return _filter_redundant_matches(raw_results)