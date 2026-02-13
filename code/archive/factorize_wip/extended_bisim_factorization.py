import networkx as nx
from typing import List, Set, Dict, Tuple
from collections import deque
from dataclasses import dataclass

# Importeer je match-klasse (of gebruik deze definitie als je alles in één file wilt)
@dataclass(frozen=True)
class SubstructureMatch:
    start_nodes: Tuple[str, str]
    overlap_size: int
    internals: Set[Tuple[str, str]]
    frontiers: Set[Tuple[str, str]]
    all_pairs: Set[Tuple[str, str]]

# --- HULPFUNCTIES ---

def _get_out_labels(G: nx.DiGraph, node: str) -> Dict[str, str]:
    """Geeft een dictionary van label -> target_node."""
    return {data.get('label'): target for _, target, data in G.out_edges(node, data=True) if 'label' in data}

# --- BIBLIOTHEEK LOGICA ---

def create_external_library_structure(G: nx.DiGraph, canonical_nodes: set, frontier_nodes: set, cluster_id: int, canonical_start: str):
    """
    Maakt een losstaande kopie van de substructuur aan in een visueel cluster.
    Bevat layout-fixes voor cyclische structuren.
    """
    mapping = {node: f"EXT_{canonical_start}_{node}" for node in canonical_nodes}
    cluster_name = f"cluster_{canonical_start}"
    
    # 1. Voeg de nieuwe nodes toe aan het cluster
    for orig_node, ext_node in mapping.items():
        attrs = G.nodes[orig_node].copy()
        attrs['cluster'] = cluster_name
        attrs['label'] = f"{orig_node}" 
        
        if orig_node in frontier_nodes:
            attrs['peripheries'] = 2
            attrs['status'] = 'accepting'
            attrs['fillcolor'] = 'lightblue' 
            
        G.add_node(ext_node, **attrs)

    # 2. Voeg de formele START-TRANSITIE toe (pijl uit het niets)
    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, mapping[canonical_start], key="0")

    # 3. Voeg de INTERNE transities toe
    for orig_node in canonical_nodes:
        ext_source = mapping[orig_node]
        for _, orig_target, data in G.out_edges(orig_node, data=True):
            if orig_target in canonical_nodes:
                ext_target = mapping[orig_target]
                edge_attrs = data.copy()
                
                # LAYOUT FIX: Voorkom spaghetti bij cycli
                if orig_target == canonical_start or orig_node == orig_target:
                    edge_attrs['constraint'] = 'false'
                
                G.add_edge(ext_source, ext_target, **edge_attrs)
    
    return cluster_name

# --- DIVERGENTIE & UNIEK GEDRAG ---

def _preserve_unique_behavior(G: nx.DiGraph, start_node: str, instance_nodes: Set[str], canonical_map: Dict[str, str], rc_node_id: str):
    """
    Identificeert gedrag dat afwijkt van de canonical (library) versie 
    en zorgt dat deze paden behouden blijven vanuit de RC node.
    """
    preserved_nodes = set()
    queue = deque()
    
    # 1. Scan alle nodes in de instance op afwijkingen t.o.v. de library
    for inst_node, lib_node in canonical_map.items():
        inst_out = _get_out_labels(G, inst_node)
        lib_out = _get_out_labels(G, lib_node)
        
        for label, inst_target in inst_out.items():
            # A: Externe transities (altijd behouden)
            if inst_target not in instance_nodes:
                G.add_edge(rc_node_id, inst_target, label=label)
                continue
            
            # B: Interne afwijking (label bestaat niet in de library)
            if label not in lib_out:
                if inst_target == start_node:
                    # Terug naar eigen start wordt een loop op de RC
                    G.add_edge(rc_node_id, rc_node_id, label=label)
                else:
                    # Nieuw uniek intern pad
                    G.add_edge(rc_node_id, inst_target, label=label)
                    if inst_target not in preserved_nodes:
                        preserved_nodes.add(inst_target)
                        queue.append(inst_target)

    # 2. BFS: Loop de unieke paden af en behoud de benodigde nodes
    visited_in_bfs = set()
    while queue:
        u = queue.popleft()
        if u in visited_in_bfs: continue
        visited_in_bfs.add(u)
        
        edges = list(G.out_edges(u, data=True))
        for _, v, data in edges:
            if v == start_node:
                # Verwijs terug naar de proxy
                G.add_edge(u, rc_node_id, **data)
            elif v not in instance_nodes:
                pass # Externe exit vanaf een uniek pad blijft staan
            else:
                if v not in preserved_nodes:
                    preserved_nodes.add(v)
                    queue.append(v)
                    
    return preserved_nodes

# --- FACTORISATIE KERN ---

def _replace_instance_with_rc(G: nx.DiGraph, start_node: str, instance_nodes: Set[str], substructure_name: str, canonical_map: Dict[str, str]):
    """
    Vervangt een complete instance door een RC node (CALL) en regelt de transities.
    """
    rc_node_id = f"RC_{start_node}"
    
    # Voeg de proxy node toe
    G.add_node(rc_node_id, 
               shape='box', 
               style='filled', 
               fillcolor='orange', 
               label=f"CALL: {substructure_name}")

    # Herleid alle INKOMENDE transities van de buitenwereld naar de RC
    in_edges = list(G.in_edges(start_node, data=True))
    for u, v, data in in_edges:
        if u not in instance_nodes:
            G.add_edge(u, rc_node_id, **data)

    # Behoud uniek gedrag en krijg de set van nodes die NIET verwijderd mogen worden
    preserved = _preserve_unique_behavior(G, start_node, instance_nodes, canonical_map, rc_node_id)
    
    # Geef de nodes terug die veilig verwijderd kunnen worden
    return instance_nodes - preserved

def apply_factorization(G: nx.DiGraph, results: List[SubstructureMatch]):
    """
    Hoofdfunctie voor factorisatie.
    Verwerkt zowel de canonical als de factored kopieën.
    """
    processed_canonicals = set()
    all_nodes_to_remove = set()
    
    # Sorteer resultaten op grootte (optioneel, voor stabiliteit)
    sorted_results = sorted(results, key=lambda x: x.overlap_size, reverse=True)

    for i, res in enumerate(sorted_results):
        canonical_start, factored_start = res.start_nodes
        
        # Datasets voor deze specifieke match
        c_nodes = {pair[0] for pair in res.all_pairs}
        f_nodes = {pair[1] for pair in res.all_pairs}
        
        # Mappings voor divergentie-check
        factored_to_lib_map = {pair[1]: pair[0] for pair in res.all_pairs}
        canonical_to_lib_map = {pair[0]: pair[0] for pair in res.all_pairs} # Identity map
        
        sub_name = f"Sub_{canonical_start}"

        # 1. Behandel de CANONICAL (Library) instance
        if canonical_start not in processed_canonicals:
            canonical_frontiers = {pair[0] for pair in res.frontiers}
            
            # Maak de externe weergave
            create_external_library_structure(G, c_nodes, canonical_frontiers, i, canonical_start)
            
            # Vervang de bron in de hoofdautomaat (met behoud van uniek gedrag)
            to_remove = _replace_instance_with_rc(G, canonical_start, c_nodes, sub_name, canonical_to_lib_map)
            all_nodes_to_remove.update(to_remove)
            processed_canonicals.add(canonical_start)

        # 2. Behandel de FACTORED (Kopie) instance
        # Controleer of de startnode nog bestaat (kan weg zijn door eerdere overlap-verwijdering)
        if G.has_node(factored_start):
            to_remove = _replace_instance_with_rc(G, factored_start, f_nodes, sub_name, factored_to_lib_map)
            all_nodes_to_remove.update(to_remove)

    # 3. Definitieve opschoning
    G.remove_nodes_from(all_nodes_to_remove)
    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")