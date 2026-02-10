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
    effective_count: int  # Nieuw: Aantal niet-overlappende locaties

class SubstructureAnalyzer:
    def __init__(self, G: nx.MultiDiGraph, min_overlap: int = 2):
        self.G = G
        self.min_overlap = min_overlap

    def get_node_signature(self, node: str) -> tuple:
        # Basis kenmerken van een node voor bucketing
        is_accepting = self.G.nodes[node].get('shape') == 'doublecircle'
        edges = sorted([(d.get('label'), v) for _, v, d in self.G.out_edges(node, data=True)])
        return (is_accepting, tuple([(l, v == node) for l, v in edges]))

    # def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[Dict]:
    #     # EXPLICIETE CHECK: Starten op dezelfde node heeft geen zin
    #     if start_a == start_b:
    #         return None

    #     queue = deque([(start_a, start_b)])
    #     visited_pairs = [] 
    #     pair_set = set()
        
    #     # Houd bij welke nodes aan welke "kant" van de vergelijking zitten
    #     nodes_in_a = set()
    #     nodes_in_b = set()

    #     while queue:
    #         pair = queue.popleft()
    #         if pair in pair_set: continue
            
    #         n1, n2 = pair
            
    #         # 1. IDENTITEITS CHECK: Als de BFS bij dezelfde node uitkomt, 
    #         # stopt de bisimilaire overlap hier.
    #         if n1 == n2:
    #             continue

    #         # 2. INTERNE OVERLAP CHECK: 
    #         # Voorkom dat kant A van de match nodes van kant B gaat bevatten en vice versa.
    #         # Dit voorkomt dat een pad dat in zichzelf draait als "herhaling" wordt gezien.
    #         if n1 in nodes_in_b or n2 in nodes_in_a:
    #             return None

    #         # Check of ze lokaal bisimilair zijn
    #         sig1 = self.get_node_signature(n1)
    #         sig2 = self.get_node_signature(n2)
            
    #         if sig1 == sig2:
    #             visited_pairs.append(pair)
    #             pair_set.add(pair)
    #             nodes_in_a.add(n1)
    #             nodes_in_b.add(n2)
                
    #             e1 = {d.get('label'): v for _, v, d in self.G.out_edges(n1, data=True)}
    #             e2 = {d.get('label'): v for _, v, d in self.G.out_edges(n2, data=True)}
                
    #             # Labels matchen
    #             for label in sorted(e1.keys()):
    #                 if label in e2:
    #                     queue.append((e1[label], e2[label]))

    #     if len(visited_pairs) < self.min_overlap:
    #         return None

    #     # Bouw Blueprint op basis van de A-kant (n1) van de paren
    #     nodes_a = [p[0] for p in visited_pairs]
    #     node_to_idx = {node: i for i, node in enumerate(nodes_a)}
    #     blueprint_edges = []
        
    #     for idx, n1 in enumerate(nodes_a):
    #         for _, target, d in self.G.out_edges(n1, data=True):
    #             if target in node_to_idx:
    #                 blueprint_edges.append(BlueprintEdge(idx, node_to_idx[target], d.get('label')))

    #     return {
    #         'nodes_a': tuple(nodes_a),
    #         'nodes_b': tuple([p[1] for p in visited_pairs]),
    #         'blueprint_edges': list(set(blueprint_edges))
    #     }

    def find_maximal_overlap(self, start_a: str, start_b: str) -> Optional[Dict]:
        # EXPLICIETE CHECK: Starten op dezelfde node heeft geen zin
        if start_a == start_b:
            return None

        queue = deque([(start_a, start_b)])
        visited_pairs = [] 
        pair_set = set()
        
        # Houd bij welke nodes aan welke "kant" van de vergelijking zitten
        nodes_in_a = set()
        nodes_in_b = set()

        while queue:
            pair = queue.popleft()
            if pair in pair_set: continue
            
            n1, n2 = pair
            
            # 1. IDENTITEITS CHECK: Als de BFS bij dezelfde node uitkomt, 
            # stopt de bisimilaire overlap hier.
            if n1 == n2:
                continue

            # 2. INTERNE OVERLAP CHECK: 
            # Voorkom dat kant A van de match nodes van kant B gaat bevatten en vice versa.
            # Dit voorkomt dat een pad dat in zichzelf draait als "herhaling" wordt gezien.
            if n1 in nodes_in_b or n2 in nodes_in_a:
                return None

            # Check of ze lokaal bisimilair zijn
            sig1 = self.get_node_signature(n1)
            sig2 = self.get_node_signature(n2)
            
            if sig1 == sig2:
                visited_pairs.append(pair)
                pair_set.add(pair)
                nodes_in_a.add(n1)
                nodes_in_b.add(n2)
                
                e1 = {d.get('label'): v for _, v, d in self.G.out_edges(n1, data=True)}
                e2 = {d.get('label'): v for _, v, d in self.G.out_edges(n2, data=True)}
                
                # Labels matchen
                for label in sorted(e1.keys()):
                    if label in e2:
                        queue.append((e1[label], e2[label]))

        if len(visited_pairs) < self.min_overlap:
            return None

        # Bouw Blueprint op basis van de A-kant (n1) van de paren
        pair_mapping = dict(visited_pairs)
        nodes_a = [p[0] for p in visited_pairs]
        node_to_idx = {node: i for i, node in enumerate(nodes_a)}
        blueprint_edges = []
        
        for idx, n1 in enumerate(nodes_a):
            for _, target, d in self.G.out_edges(n1, data=True):
                if target in node_to_idx:
                    blueprint_edges.append(BlueprintEdge(idx, node_to_idx[target], d.get('label')))

        for i, (u_a, u_b) in enumerate(visited_pairs):
            # Pak alle transities van beide nodes
            out_a = {d.get('label'): v for _, v, d in self.G.out_edges(u_a, data=True)}
            out_b = {d.get('label'): v for _, v, d in self.G.out_edges(u_b, data=True)}
            
            # We moeten elk label controleren dat bij minstens één van de twee voorkomt
            all_labels = set(out_a.keys()) | set(out_b.keys())
            
            for label in all_labels:
                t_a = out_a.get(label)
                t_b = out_b.get(label)
                
                # Check of de transitie aan de A-kant binnen de match valt
                is_internal_a = t_a in node_to_idx
                
                if is_internal_a:
                    # CRUCIALE CHECK: Als A intern gaat, MOET B naar de exacte partner van t_a gaan
                    expected_t_b = pair_mapping.get(t_a)
                    
                    if t_b != expected_t_b:
                        # NON-DETERMINISME: 
                        # Ofwel B gaat met dit label naar buiten, of naar een andere interne node.
                        return None 
                    
                    # Als het klopt, is dit een legitieme edge voor onze subroutine blueprint
                    blueprint_edges.append(BlueprintEdge(i, node_to_idx[t_a], label))
                else:
                    # Als A naar buiten gaat met dit label...
                    # ...dan mag B met datzelfde label NOOIT naar een interne node gaan.
                    if t_b in pair_mapping.values():
                        return None # Discrepantie in subroutine-grenzen            
        
        return {
            'nodes_a': tuple(nodes_a),
            'nodes_b': tuple([p[1] for p in visited_pairs]),
            'blueprint_edges': list(set(blueprint_edges))
        }
    
def _calculate_effective_count(locations: List[MatchLocation]) -> int:
    count = 0
    claimed_nodes = set()
    # Sorteer op start_node voor een voorspelbare greedy selectie
    for loc in sorted(locations, key=lambda l: l.start_node):
        if not any(n in claimed_nodes for n in loc.all_nodes):
            count += 1
            claimed_nodes.update(loc.all_nodes)
    return count

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[CanonicalSubstructure]:
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    buckets = defaultdict(list)
    for node in G.nodes():
        buckets[analyzer.get_node_signature(node)].append(node)
    buckets = {k: v for k, v in buckets.items() if len(v) >= 2} 

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
        
        # Bereken de effectieve count voor de prioriteit
        eff_count = _calculate_effective_count(loc_list)
        
        results.append(CanonicalSubstructure(
            structure_hash=str(s_hash),
            overlap_size=len(loc_list[0].all_nodes),
            locations=loc_list,
            blueprint_edges=edges,
            nodes_count=len(loc_list[0].all_nodes),
            effective_count=eff_count
        ))
    
    # Sortering op basis van de nieuwe effective_count
    #return sorted(results, key=lambda x: (x.overlap_size * x.effective_count), reverse=True)
    return sorted(results, 
              key=lambda x: (x.overlap_size * x.effective_count, x.overlap_size), 
              reverse=True)