import networkx as nx
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Set, Tuple, List, Dict, Optional

@dataclass(frozen=True)
class BlueprintEdge:
    source_idx: int
    target_idx: int
    label: str

@dataclass(frozen=True)
class MatchLocation:
    start_node: str
    all_nodes: Tuple[str, ...]

@dataclass
class CanonicalSubstructure:
    structure_hash: str
    overlap_size: int
    locations: List[MatchLocation]
    blueprint_edges: List[BlueprintEdge]
    nodes_count: int
    effective_count: int

class SubstructureAnalyzer:
    def __init__(self, G: nx.MultiDiGraph, min_overlap: int = 2):
        self.G = G
        self.min_overlap = min_overlap
        self._edge_cache = {}
        self._sig_cache = {}

    def _get_edges_cached(self, node: str) -> Dict[str, str]:
        if node not in self._edge_cache:
            self._edge_cache[node] = {
                d.get('label'): v for _, v, d in self.G.out_edges(node, data=True)
            }
        return self._edge_cache[node]

    def get_node_signature(self, node: str) -> tuple:
        if node not in self._sig_cache:
            is_accepting = self.G.nodes[node].get('shape') == 'doublecircle'
            edges = self._get_edges_cached(node)
            # Signature kijkt naar labels en of een pijl een self-loop is
            sig_edges = sorted([(l, v == node) for l, v in edges.items()])
            self._sig_cache[node] = (is_accepting, tuple(sig_edges))
        return self._sig_cache[node]

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[Dict]:
        if start_a == start_b:
            return None

        # FASE 1: BFS Discovery
        queue = deque([(start_a, start_b)])
        visited_pairs = [] 
        pair_set = set()
        nodes_in_a = set()
        nodes_in_b = set()

        while queue:
            pair = queue.popleft()
            if pair in pair_set: continue
            
            n1, n2 = pair

            # 1. IDENTITEITS CHECK: Als de BFS bij dezelfde node uitkomt, 
    #       # stopt de bisimilaire overlap hier.
            if n1 == n2: 
                continue

            # 2. INTERNE OVERLAP CHECK: 
    #       # Voorkom dat kant A van de match nodes van kant B gaat bevatten en vice versa.
    #       # Dit voorkomt dat een pad dat in zichzelf draait als "herhaling" wordt gezien.
            if n1 in nodes_in_b or n2 in nodes_in_a: 
                return None

            if self.get_node_signature(n1) == self.get_node_signature(n2):
                visited_pairs.append(pair)
                pair_set.add(pair)
                nodes_in_a.add(n1)
                nodes_in_b.add(n2)
                
                e1 = self._get_edges_cached(n1)
                e2 = self._get_edges_cached(n2)
                
                # Alleen verder zoeken op gemeenschappelijke labels
                for label in e1:
                    if label in e2:
                        queue.append((e1[label], e2[label]))

        if len(visited_pairs) < self.min_overlap:
            return None

        # FASE 2: Validatie van Structuur & Non-determinisme
        pair_mapping = dict(visited_pairs) # a -> b
        nodes_a = [p[0] for p in visited_pairs]
        node_to_idx = {node: i for i, node in enumerate(nodes_a)}
        blueprint_edges = []
        
        for i, (u_a, u_b) in enumerate(visited_pairs):
            out_a = self._get_edges_cached(u_a)
            out_b = self._get_edges_cached(u_b)
            
            # Controleer alle labels van beide kanten
            all_labels = set(out_a.keys()) | set(out_b.keys())
            
            for label in all_labels:
                t_a = out_a.get(label)
                t_b = out_b.get(label)
                
                # Is de transitie aan de A-kant intern aan de gevonden match?
                is_internal_a = t_a in node_to_idx
                
                if is_internal_a:
                    # B MOET naar de partner van t_a gaan
                    expected_t_b = pair_mapping.get(t_a)
                    if t_b != expected_t_b:
                        return None # non-determinisme gedetecteerd
                    
                    # Voeg toe aan blueprint (we gebruiken set later voor deduplicatie)
                    blueprint_edges.append(BlueprintEdge(i, node_to_idx[t_a], label))
                else:
                    # Als A extern gaat, mag B NOOIT naar een interne node gaan met dit label
                    if t_b in nodes_in_b:
                        return None # Grens-discrepantie

        return {
            'start_a': start_a,
            'start_b': start_b,
            'nodes_a': tuple(nodes_a),
            'nodes_b': tuple([p[1] for p in visited_pairs]),
            'blueprint_edges': list(set(blueprint_edges))
        }

def _calculate_effective_count(locations: List[MatchLocation]) -> int:
    count = 0
    claimed_nodes = set()
    for loc in sorted(locations, key=lambda l: l.start_node):
        loc_nodes = set(loc.all_nodes)
        if not loc_nodes & claimed_nodes:
            count += 1
            claimed_nodes |= loc_nodes
    return count

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[CanonicalSubstructure]:
    """
    Verschillende locaties met dezelfde structurele blueprint worden
    gegroepeerd onder dezelfde structure_hash. De edges_tuple fungeert als
    canonical identifier voor de structuur.
    """
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    
    # Bucketing: alleen nodes met >= 2 exemplaren
    buckets = defaultdict(list)
    for node in G.nodes():
        buckets[analyzer.get_node_signature(node)].append(node)
    buckets = {k: sorted(v) for k, v in buckets.items() if len(v) >= 2}

    structure_registry = defaultdict(set)  # edges_tuple -> {MatchLocations}
    blueprint_store = {}  # edges_tuple -> [BlueprintEdge]

    for signature, nodes in buckets.items():
        # Voor zeer grote buckets: limiteer of sample
        # if len(nodes) > 100:
        #     continue
            
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                match = analyzer.find_maximal_overlap(nodes[i], nodes[j])
                if match:
                    # CANONICAL HASH: gebaseerd op blueprint structuur
                    # Twee matches met dezelfde edges_tuple zijn identiek!
                    edges_tuple = tuple(sorted([
                        (e.source_idx, e.target_idx, e.label) 
                        for e in match['blueprint_edges']
                    ]))
                    
                    # Voeg beide locaties toe onder deze canonical hash
                    structure_registry[edges_tuple].add(
                        MatchLocation(match['start_a'], match['nodes_a'])
                    )
                    structure_registry[edges_tuple].add(
                        MatchLocation(match['start_b'], match['nodes_b'])
                    )
                    
                    # Blueprint hoeft maar 1x opgeslagen
                    if edges_tuple not in blueprint_store:
                        blueprint_store[edges_tuple] = match['blueprint_edges']

    # Converteer naar output formaat
    results = []
    for edges_tuple, locations in structure_registry.items():
        loc_list = list(locations)
        eff_count = _calculate_effective_count(loc_list)
        
        results.append(CanonicalSubstructure(
            structure_hash=str(hash(edges_tuple)),
            overlap_size=len(loc_list[0].all_nodes),
            locations=loc_list,
            blueprint_edges=blueprint_store[edges_tuple],
            nodes_count=len(loc_list[0].all_nodes),
            effective_count=eff_count
        ))
    
    return sorted(
        results, 
        key=lambda x: (x.overlap_size * x.effective_count, x.overlap_size), 
        reverse=True
    )