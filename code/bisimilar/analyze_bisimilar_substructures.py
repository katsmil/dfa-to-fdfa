from collections import defaultdict
from dataclasses import dataclass
from typing import Set, Tuple, List, Dict, Optional
import networkx as nx

"""
ALGORITME: DFA Factorisatie via Maximale Bisimulatie & Frontier Detectie
========================================================================

Dit script identificeert herhalende substructuren in een DFA die gefactoriseerd kunnen worden. 
Het is specifiek ontworpen als voorbereidingsstap voor 
het bouwen van een Recursive Transition Network (RTN) of een Recursieve Automaat (RA).

KERNMERKEN:
1. Signature Hashing (De "Buckets" maken)
   -------------------------------
   Kandidaten voor equivalentie worden gegroepeerd in buckets op basis van:
   - De 'accepting' status (is_doublecircle).
   - De exacte set uitgaande transitie-labels (gesorteerd).
   Dit reduceert de zoekruimte van O(n²) naar bijna lineair in de praktijk.

2. Maximale Bisimilaire Overlap & Frontier Detectie
   ---------------------------------------------------
   Vanuit kandidaten in dezelfde bucket verkent het algoritme parallel de graaf.
   - Internals (Strict Match): Knopen die identiek gedrag en acceptatie vertonen.
   - Frontiers: De eerste knopenparen waar het gedrag divergeert of waar de 
     structuur stopt. Deze dienen als exit-punten voor recursie.

3. e(R) Sluiting (Hopcroft-Karp Optimalisatie)
   -------------------------------
   Tijdens de analyse wordt een Union-Find (Disjoint Set) structuur bijgehouden.
   Zodra twee knopen als equivalent zijn geïdentificeerd, worden ze in de sluiting 
   opgenomen. Latere analyses skippen paren die al bewezen equivalent zijn.

4. Post-verwerking: Redundantie Filtering & Minimum Size
   ---------------------------------------------------
   - Alleen matches met een minimale omvang (default: 3) worden behouden.
   - Overlappende resultaten worden gefilterd: als Match A een subset is 
     van Match B, wordt alleen de grootste (Match B) gerapporteerd.

THEORETISCHE WERKING (Stack-gebaseerd):
Tijdens de executie van de resulterende recursieve automaat dienen de 'Frontier Nodes' als 
momenten waarop de stack gecontroleerd moet worden. Als in een frontier-toestand een input 
niet verwerkt kan worden, wordt het stack-frame gepopt en keert de uitvoering terug naar 
de call-site (de context van de aanroeper).
"""

@dataclass(frozen=True)
class SubstructureMatch:
    """
    Representeert een gevonden herhalende structuur tussen twee startpunten.
    Dit is het resultaat van het analyse-proces.
    """
    start_nodes: Tuple[str, str]
    overlap_size: int
    internals: Set[Tuple[str, str]]   # De bisimilaire 'body'
    frontiers: Set[Tuple[str, str]]   # De punten waar gedrag divergeert
    all_pairs: Set[Tuple[str, str]]   # De volledige verzameling van de match

class DFAUtils:
    """Hulpmiddelen voor het analyseren van DFA-eigenschappen in NetworkX."""
    
    @staticmethod
    def is_accepting(G: nx.DiGraph, node: str) -> bool:
        data = G.nodes[node]
        return data.get('shape') == 'doublecircle' or data.get('accepting') == 'true'

    @staticmethod
    def get_labeled_edges(G: nx.DiGraph, node: str) -> Dict[str, str]:
        """Geeft een dictionary van label -> target_node."""
        return {d['label']: v for _, v, d in G.out_edges(node, data=True) if 'label' in d}

class EquivalenceClosure:
    """Implementatie van Hopcroft-Karp e(R) voor equivalentie-sluitingen."""
    def __init__(self, elements: List[str]):
        self.parent = {e: e for e in elements}

    def _find(self, x: str) -> str:
        if self.parent[x] != x:
            self.parent[x] = self._find(self.parent[x])
        return self.parent[x]

    def add_equivalence(self, x: str, y: str) -> bool:
        root_x, root_y = self._find(x), self._find(y)
        if root_x != root_y:
            self.parent[root_x] = root_y
            return True
        return False

    def are_equivalent(self, x: str, y: str) -> bool:
        return self._find(x) == self._find(y)

class SubstructureAnalyzer:
    """
    Verantwoordelijk voor het detecteren van maximale bisimilaire overlap 
    in een DFA. Deze engine muteert de graaf niet.
    """
    
    def __init__(self, G: nx.DiGraph, min_overlap: int = 3):
        self.G = G
        self.min_overlap = min_overlap
        # De closure helpt om redundantie tijdens de analyse te voorkomen (HK-opt)
        self.equivalence_closure = EquivalenceClosure(list(G.nodes()))

    def get_node_signature(self, node: str) -> Tuple[bool, Tuple[str, ...]]:
        """Berekent de signature (accepting status + uitgaande labels)."""
        labels = sorted(DFAUtils.get_labeled_edges(self.G, node).keys())
        return (DFAUtils.is_accepting(self.G, node), tuple(labels))

    def _check_strict_match(self, n1: str, n2: str) -> bool:
        """Controleert of twee nodes lokaal identiek gedrag vertonen."""
        if DFAUtils.is_accepting(self.G, n1) != DFAUtils.is_accepting(self.G, n2):
            return False
        
        edges1 = DFAUtils.get_labeled_edges(self.G, n1)
        edges2 = DFAUtils.get_labeled_edges(self.G, n2)
        return set(edges1.keys()) == set(edges2.keys())

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[SubstructureMatch]:
        """
        Verkent vanuit twee startpunten hoe ver de gelijkenis reikt.
        Identificeert zowel de interne match als de frontier-punten.
        """
        if not self._check_strict_match(start_a, start_b):
            return None

        stack = [(start_a, start_b)]
        visited_strict: Set[Tuple[str, str]] = set()
        all_reached: Set[Tuple[str, str]] = {(start_a, start_b)}

        while stack:
            n1, n2 = stack.pop()
            if (n1, n2) in visited_strict:
                continue

            if self._check_strict_match(n1, n2):
                visited_strict.add((n1, n2))
                self.equivalence_closure.add_equivalence(n1, n2)
                
                # Verken de opvolgers voor elke transitie
                e1 = DFAUtils.get_labeled_edges(self.G, n1)
                e2 = DFAUtils.get_labeled_edges(self.G, n2)
                for label, next1 in e1.items():
                    next2 = e2[label]
                    pair = (next1, next2)
                    all_reached.add(pair)
                    if pair not in visited_strict:
                        stack.append(pair)

        # De frontiers zijn alle bereikte paren die niet in de 'strict' set zitten
        frontiers = all_reached - visited_strict
        
        return SubstructureMatch(
            start_nodes=(start_a, start_b),
            overlap_size=len(all_reached),
            internals=visited_strict,
            frontiers=frontiers,
            all_pairs=all_reached
        )

def run_analysis(dot_file: str, min_size: int = 3) -> List[SubstructureMatch]:
    """Orchestreert het volledige analyse-proces op een DOT bestand."""
    G = nx.DiGraph(nx.drawing.nx_pydot.read_dot(dot_file))
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    
    result2 = G.out_edges('s0', data=True)
    result = analyzer.get_node_signature('s0')

    # 1. Groepeer op signature om vergelijkingsruimte te verkleinen
    buckets = defaultdict(list)
    for node in G.nodes():
        buckets[analyzer.get_node_signature(node)].append(node)

    raw_results = []
    compared = set()

    # 2. Analyseer paren binnen de buckets
    for candidates in buckets.values():
        for i, n1 in enumerate(candidates):
            for n2 in candidates[i+1:]:
                if analyzer.equivalence_closure.are_equivalent(n1, n2):
                    continue
                
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared: continue
                compared.add(pair_id)

                match = analyzer.find_maximal_overlap(n1, n2)
                if match and match.overlap_size >= analyzer.min_overlap:
                    raw_results.append(match)

    # 3. Filter overlap tussen gevonden matches
    return _filter_redundant_matches(raw_results)

def _filter_redundant_matches(results: List[SubstructureMatch]) -> List[SubstructureMatch]:
    """Zorgt dat we niet dezelfde (of kleinere) patronen dubbel rapporteren."""
    sorted_res = sorted(results, key=lambda x: x.overlap_size, reverse=True)
    unique_matches: List[SubstructureMatch] = []

    for current in sorted_res:
        if not any(current.all_pairs.issubset(u.all_pairs) for u in unique_matches):
            unique_matches.append(current)
    return unique_matches