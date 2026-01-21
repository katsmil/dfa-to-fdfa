from typing import List, Set
import networkx as nx
from bisimilar.analyze_bisimilar_substructures import SubstructureMatch

def create_recursive_call_node(G, factored_start, canonical_start):
    """Maakt de oranje RC-knoop aan die de substructuur vervangt."""
    rc_node_id = f"RC_{factored_start}"
    G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', 
               label=f"RC_to_{canonical_start}")
    return rc_node_id

def isolate_and_mark_substructure(G, canonical_nodes, cluster_id):
    """
    Zorgt dat de substructuur losstaat:
    1. Verwijdert transities naar buiten de substructuur.
    2. Markeert frontier nodes als 'accepting' (dubbele cirkel).
    3. Plaatst nodes in een visueel cluster voor de DOT-export.
    """
    for node in canonical_nodes:
        # Stap A: Voeg toe aan cluster voor visuele scheiding
        G.nodes[node]['cluster'] = f"cluster_{cluster_id}"
        
        # Stap B: Identificeer en isoleer frontiers
        out_edges = list(G.out_edges(node, data=True))
        is_frontier = False
        for _, target, data in out_edges:
            if target not in canonical_nodes:
                # Verwijder de transitie naar de buitenwereld
                G.remove_edge(node, target)
                is_frontier = True
        
        # Stap C: Visuele markering
        if is_frontier:
            G.nodes[node]['peripheries'] = 2 
            G.nodes[node]['status'] = 'accepting'

def create_external_library_structure(G: nx.DiGraph, canonical_nodes: set, frontier_nodes: set, cluster_id: int, canonical_start: str):
    """
    Maakt een losstaande kopie van de substructuur aan.
    De cluster_id wordt nu gebaseerd op de startnode voor betere herkenbaarheid.
    """
    mapping = {node: f"EXT_{canonical_start}_{node}" for node in canonical_nodes}
    cluster_name = f"cluster_{canonical_start}" # Cluster vernoemd naar de substructuur
    
    # 1. Voeg de nieuwe nodes toe aan de graaf
    for orig_node, ext_node in mapping.items():
        attrs = G.nodes[orig_node].copy()
        attrs['cluster'] = cluster_name
        attrs['label'] = f"{orig_node}" # Node naam binnen de sub-automaat
        
        if orig_node in frontier_nodes:
            attrs['peripheries'] = 2
            attrs['status'] = 'accepting'
            attrs['fillcolor'] = 'lightblue' 
            
        G.add_node(ext_node, **attrs)

    # 2. Voeg de START-TRANSITIE toe
    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, mapping[canonical_start], key="0")

    # 3. Voeg de INTERNE transities toe met de layout-fix
    for orig_node in canonical_nodes:
        ext_source = mapping[orig_node]
        for _, orig_target, data in G.out_edges(orig_node, data=True):
            if orig_target in canonical_nodes:
                ext_target = mapping[orig_target]
                edge_attrs = data.copy()
                
                # Layout fix voor cyclic structuren
                if orig_target == canonical_start or orig_node == orig_target:
                    edge_attrs['constraint'] = 'false'
                
                G.add_edge(ext_source, ext_target, **edge_attrs)
    
    return cluster_name

def _replace_instance_with_rc(G, start_node, instance_nodes, substructure_name):
    """
    Vervangt een set knopen door één RC-node die verwijst naar de substructuur-naam.
    """
    rc_node_id = f"RC_{start_node}"
    
    # Label verwijst nu expliciet naar de 'functie' naam
    G.add_node(rc_node_id, 
               shape='box', 
               style='filled', 
               fillcolor='orange', 
               label=f"CALL: {substructure_name}")

    # Herleid transities
    in_edges = list(G.in_edges(start_node, data=True))
    for u, v, data in in_edges:
        if u not in instance_nodes:
            G.add_edge(u, rc_node_id, **data)

    for node in instance_nodes:
        out_edges = list(G.out_edges(node, data=True))
        for _, target, data in out_edges:
            if target not in instance_nodes:
                G.add_edge(rc_node_id, target, **data)

def apply_factorization(G, results: List[SubstructureMatch]):
    processed_canonicals = set()
    all_nodes_to_remove = set()
    
    for i, res in enumerate(results):
        canonical_start, factored_start = res.start_nodes
        canonical_nodes = {pair[0] for pair in res.all_pairs}
        factored_nodes = {pair[1] for pair in res.all_pairs}
        canonical_frontiers = {pair[0] for pair in res.frontiers}
        
        # We definiëren een duidelijke naam voor deze bibliotheek-structuur
        sub_name = f"Sub_{canonical_start}"

        if canonical_start not in processed_canonicals:
            # 1. Maak de externe bibliotheek
            create_external_library_structure(G, canonical_nodes, canonical_frontiers, i, canonical_start)
            
            # 2. Vervang de bron-structuur door een CALL naar de sub_name
            _replace_instance_with_rc(G, canonical_start, canonical_nodes, sub_name)
            
            all_nodes_to_remove.update(canonical_nodes)
            processed_canonicals.add(canonical_start)

        # 3. Vervang de kopie-structuur door een CALL naar diezelfde sub_name
        _replace_instance_with_rc(G, factored_start, factored_nodes, sub_name)
        all_nodes_to_remove.update(factored_nodes)

    G.remove_nodes_from(all_nodes_to_remove)
    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")