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

        # FASE 1+2 GEFUSEERD: BFS met inline validatie (inkomend + uitgaand)
        queue = deque([(start_a, start_b)])
        visited_pairs = [] 
        pair_set = set()
        pair_mapping = {}  # a -> b
        reverse_mapping = {} # b -> a (NIEUW: nodig voor de n2 check)
        nodes_in_a = set()
        nodes_in_b = set()
        node_to_idx = {}  # a -> index
        blueprint_edges = []

        while queue:
            pair = queue.popleft()
            if pair in pair_set: continue
            
            n1, n2 = pair

            # 1. IDENTITEITS CHECK
            if n1 == n2: 
                continue

            # 2. INTERNE OVERLAP CHECK
            if n1 in nodes_in_b or n2 in nodes_in_a: 
                return None

            if self.get_node_signature(n1) == self.get_node_signature(n2):
                e1 = self._get_edges_cached(n1)
                e2 = self._get_edges_cached(n2)
                
                # ===== VALIDATIE VOORDAT WE ACCEPTEREN =====
                
                # CHECK INKOMEND n1: Predecessors die al in overlap zitten
                for pred_a in self.G.predecessors(n1):
                    if pred_a in pair_mapping:
                        pred_b = pair_mapping[pred_a]
                        pred_edges_a = self._get_edges_cached(pred_a)
                        pred_edges_b = self._get_edges_cached(pred_b)
                        
                        for label, target_a in pred_edges_a.items():
                            if target_a == n1:
                                target_b = pred_edges_b.get(label)
                                if target_b != n2:
                                    return None  # Inkomend n1 niet consistent
                
                # CHECK INKOMEND n2: Predecessors die al in overlap zitten
                for pred_b in self.G.predecessors(n2):
                    if pred_b in reverse_mapping:
                        pred_a = reverse_mapping[pred_b]
                        pred_edges_a = self._get_edges_cached(pred_a)
                        pred_edges_b = self._get_edges_cached(pred_b)
                        
                        for label, target_b in pred_edges_b.items():
                            if target_b == n2:
                                target_a = pred_edges_a.get(label)
                                if target_a != n1:
                                    return None  # Inkomend n2 niet consistent
                
                # CHECK UITGAAND: Uniformiteit + Targets
                all_labels = set(e1.keys()) | set(e2.keys())

                for label in all_labels:
                    t_a = e1.get(label)
                    t_b = e2.get(label)

                    is_internal_a = t_a is not None and t_a in nodes_in_a
                    is_internal_b = t_b is not None and t_b in nodes_in_b

                    # Uniformiteit: beide intern of beide extern
                    if (is_internal_a and not is_internal_b) or (not is_internal_a and is_internal_b):
                        return None

                    # Targets: interne edges naar gemapte partners (controle op bestaande mapping)
                    if is_internal_a:
                        expected_t_b = pair_mapping.get(t_a)
                        if t_b != expected_t_b:
                            return None
                    else:
                        if t_a is not None and t_b is not None and t_b in nodes_in_b:
                            return None

                # ===== ALLES OK - ACCEPTEER PAAR =====
                idx = len(visited_pairs)
                visited_pairs.append(pair)
                pair_set.add(pair)
                pair_mapping[n1] = n2
                reverse_mapping[n2] = n1  # Registreer de b -> a mapping
                nodes_in_a.add(n1)
                nodes_in_b.add(n2)
                node_to_idx[n1] = idx
                
                # Queue volgende
                for label in e1:
                    if label in e2:
                        queue.append((e1[label], e2[label]))

        if len(visited_pairs) < self.min_overlap:
            return None

        # BOUW NU DE BLUEPRINT EDGES OP BASIS VAN DE VOLLEDIGE MATCHSET
        pair_mapping = dict(visited_pairs)  # a -> b
        nodes_a = [p[0] for p in visited_pairs]
        node_to_idx = {node: i for i, node in enumerate(nodes_a)}
        blueprint_edges = []

        for i, (u_a, u_b) in enumerate(visited_pairs):
            out_a = self._get_edges_cached(u_a)

            for label, t_a in out_a.items():
                if t_a in node_to_idx:
                    blueprint_edges.append(BlueprintEdge(i, node_to_idx[t_a], label))

        return {
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
                        MatchLocation(match['nodes_a'][0], match['nodes_a'])
                    )
                    structure_registry[edges_tuple].add(
                        MatchLocation(match['nodes_b'][0], match['nodes_b'])
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
