import networkx as nx
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Set, Tuple, List, Dict, Optional

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
        """
        Bepaalt de bucket op basis van status én het type uitgaande transitie.
        Signature format: (is_accepting, ((label, is_self_loop), ...))
        """
        edges = DFAUtils.get_labeled_edges(self.G, node)
        
        # We bouwen een lijst van (label, is_self_loop) tuples
        descriptors = []
        for label, target in edges.items():
            is_self_loop = (target == node)
            descriptors.append((label, is_self_loop))
            
        # Sorteren is cruciaal om (('a', True), ('b', False)) gelijk te stellen 
        # aan andere nodes met dezelfde structuur, ongeacht invoervolgorde.
        descriptors.sort() 
        
        return (DFAUtils.is_accepting(self.G, node), tuple(descriptors))

    def _check_strict_match(self, n1: str, n2: str) -> bool:
        """
        Controleert of twee nodes lokaal identiek gedrag vertonen.
        Nu ook uitgebreid met de self-loop check voor consistentie tijdens BFS.
        """
        if DFAUtils.is_accepting(self.G, n1) != DFAUtils.is_accepting(self.G, n2):
            return False
            
        e1 = DFAUtils.get_labeled_edges(self.G, n1)
        e2 = DFAUtils.get_labeled_edges(self.G, n2)
        
        # 1. Check of de labels exact overeenkomen
        if set(e1.keys()) != set(e2.keys()):
            return False
            
        # # 2. Check of de structuur (self-loop vs progressie) overeenkomt per label
        # for label, target1 in e1.items():
        #     target2 = e2[label]
        #     is_self1 = (target1 == n1)
        #     is_self2 = (target2 == n2)
            
        #     if is_self1 != is_self2:
        #         return False
                
        return True

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[SubstructureMatch]:
        # 1. Initiële match check
        if start_a == start_b or not self._check_strict_match(start_a, start_b):
            return None

        # 2. BFS om de volledige bisimilaire set te vinden
        queue = deque([(start_a, start_b)])
        bisimilar_pairs: Set[Tuple[str, str]] = set()
        
        # We houden de sets van nodes voor beide kanten bij voor de frontier check
        nodes_in_a: Set[str] = set()
        nodes_in_b: Set[str] = set()

        while queue:
            pair = queue.popleft()
            if pair in bisimilar_pairs:
                continue

            n1, n2 = pair
            if n1 == n2:
                continue

            if self._check_strict_match(n1, n2):
                bisimilar_pairs.add(pair)
                nodes_in_a.add(n1)
                nodes_in_b.add(n2)
                self.equivalence_closure.add_equivalence(n1, n2)
                
                e1, e2 = DFAUtils.get_labeled_edges(self.G, n1), DFAUtils.get_labeled_edges(self.G, n2)
                for label in e1:
                    queue.append((e1[label], e2[label]))

        if len(bisimilar_pairs) < self.min_overlap:
            return None

        # 3. Dual-Sided Frontier Detectie & Determinisme Check
        internals: Set[Tuple[str, str]] = set()
        frontiers: Set[Tuple[str, str]] = set()
        
        # We moeten de exits voor beide kanten apart controleren op NDM
        exits_a: Dict[str, str] = {} # label -> target_outside_a
        exits_b: Dict[str, str] = {} # label -> target_outside_b

        for p in bisimilar_pairs:
            n1, n2 = p
            edges1 = DFAUtils.get_labeled_edges(self.G, n1)
            edges2 = DFAUtils.get_labeled_edges(self.G, n2)
            
            # Een paar is een frontier als n1 de set A verlaat OF n2 de set B verlaat
            is_frontier_a = any(target not in nodes_in_a for target in edges1.values())
            is_frontier_b = any(target not in nodes_in_b for target in edges2.values())

            if is_frontier_a or is_frontier_b:
                frontiers.add(p)
                
                # Check NDM voor kant A
                for label, target in edges1.items():
                    if target not in nodes_in_a:
                        if label in exits_a and exits_a[label] != target:
                            return None # NDM gevaar in structuur A
                        exits_a[label] = target
                
                # Check NDM voor kant B
                for label, target in edges2.items():
                    if target not in nodes_in_b:
                        if label in exits_b and exits_b[label] != target:
                            return None # NDM gevaar in structuur B
                        exits_b[label] = target
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

    # Alleen buckets met minstens 2 nodes
    buckets = {k: v for k, v in buckets.items() if len(v) >= 2} 

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