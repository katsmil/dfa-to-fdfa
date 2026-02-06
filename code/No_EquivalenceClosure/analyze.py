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
    all_nodes: Tuple[str, ...] # In exacte BFS volgorde

@dataclass
class CanonicalSubstructure:
    structure_hash: str
    overlap_size: int
    locations: List[MatchLocation]
    blueprint_edges: List[BlueprintEdge]
    nodes_count: int

class SubstructureAnalyzer:
    def __init__(self, G: nx.MultiDiGraph, min_overlap: int = 2):
        self.G = G
        self.min_overlap = min_overlap

    def get_node_signature(self, node: str) -> tuple:
        # Basis kenmerken van een node voor bucketing
        is_accepting = self.G.nodes[node].get('shape') == 'doublecircle'
        edges = sorted([(d.get('label'), v) for _, v, d in self.G.out_edges(node, data=True)])
        return (is_accepting, tuple([(l, v == node) for l, v in edges]))

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[Dict]:
        queue = deque([(start_a, start_b)])
        visited_pairs = [] # Behoudt BFS volgorde: Index 0 is Start
        pair_set = set()

        while queue:
            pair = queue.popleft()
            if pair in pair_set: continue
            n1, n2 = pair

            # Check of ze lokaal bisimilair zijn
            sig1 = self.get_node_signature(n1)
            sig2 = self.get_node_signature(n2)
            
            if sig1 == sig2:
                visited_pairs.append(pair)
                pair_set.add(pair)
                
                e1 = {d['label']: v for _, v, d in self.G.out_edges(n1, data=True)}
                e2 = {d['label']: v for _, v, d in self.G.out_edges(n2, data=True)}
                
                for label, next_n1 in e1.items():
                    if label in e2:
                        queue.append((next_n1, e2[label]))

        if len(visited_pairs) < self.min_overlap:
            return None

        # Bouw Blueprint op basis van de A-kant (n1) van de paren
        nodes_a = [p[0] for p in visited_pairs]
        node_to_idx = {node: i for i, node in enumerate(nodes_a)}
        blueprint_edges = []
        
        for idx, n1 in enumerate(nodes_a):
            for _, target, d in self.G.out_edges(n1, data=True):
                if target in node_to_idx:
                    blueprint_edges.append(BlueprintEdge(idx, node_to_idx[target], d['label']))

        return {
            'nodes_a': tuple(nodes_a),
            'nodes_b': tuple([p[1] for p in visited_pairs]),
            'blueprint_edges': list(set(blueprint_edges))
        }

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[CanonicalSubstructure]:
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    buckets = defaultdict(list)
    for node in G.nodes():
        buckets[analyzer.get_node_signature(node)].append(node)
    
    structure_registry = defaultdict(set)
    blueprint_store = {}

    for signature, nodes in buckets.items():
        nodes.sort()
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                match = analyzer.find_maximal_overlap(nodes[i], nodes[j])
                if match:
                    # De hash wordt bepaald door de blueprint transities
                    edges_tuple = tuple(sorted([(e.source_idx, e.target_idx, e.label) for e in match['blueprint_edges']]))
                    struct_hash = hash(edges_tuple)
                    
                    structure_registry[struct_hash].add(MatchLocation(match['nodes_a'][0], match['nodes_a']))
                    structure_registry[struct_hash].add(MatchLocation(match['nodes_b'][0], match['nodes_b']))
                    blueprint_store[struct_hash] = match['blueprint_edges']

    results = []
    for s_hash, locations in structure_registry.items():
        edges = blueprint_store[s_hash]
        loc_list = list(locations)
        results.append(CanonicalSubstructure(
            structure_hash=str(s_hash),
            overlap_size=len(loc_list[0].all_nodes),
            locations=loc_list,
            blueprint_edges=edges,
            nodes_count=len(loc_list[0].all_nodes)
        ))
    
    return sorted(results, key=lambda x: (x.overlap_size * len(x.locations)), reverse=True)