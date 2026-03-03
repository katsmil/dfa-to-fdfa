from typing import List, Set
import networkx as nx
from bisimilar.analyze_ext_bisimilar_substructures import SubstructureMatch

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
    Maakt een losstaande kopie van de substructuur aan met een geforceerde LR-layout.
    """
    # 1. Maak een mapping van originele naam naar 'externe' naam
    mapping = {node: f"EXT_{cluster_id}_{node}" for node in canonical_nodes}
    cluster_name = f"cluster_{cluster_id}"
    
    # 2. Voeg de nieuwe nodes toe aan de graaf
    for orig_node, ext_node in mapping.items():
        attrs = G.nodes[orig_node].copy()
        attrs['cluster'] = cluster_name
        attrs['label'] = f"Sub: {orig_node}"
        
        # Markeer frontier nodes uit de analyse als accepting (dubbele cirkel)
        if orig_node in frontier_nodes:
            attrs['peripheries'] = 2
            attrs['status'] = 'accepting'
            attrs['fillcolor'] = 'lightblue' 
            
        G.add_node(ext_node, **attrs)

    # 3. Voeg de START-TRANSITIE toe (zorgt dat de startnode links komt)
    start_dummy = f"__start_EXT_{cluster_id}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, mapping[canonical_start], key="0")

    # 4. Voeg alleen de INTERNE transities toe met layout-correcties
    for orig_node in canonical_nodes:
        ext_source = mapping[orig_node]
        for _, orig_target, data in G.out_edges(orig_node, data=True):
            if orig_target in canonical_nodes:
                ext_target = mapping[orig_target]
                
                # Kopieer de edge data (label, etc.)
                edge_attrs = data.copy()

                # --- LAYOUT LOGICA ---
                # Als een transitie terugwijst naar de start OF een zelf-loop is, 
                # zetten we constraint op false. Hierdoor dwingt deze pijl de 
                # doelknoop niet naar een 'latere' positie (rechts).
                if orig_target == canonical_start or orig_node == orig_target:
                    edge_attrs['constraint'] = 'false'
                
                G.add_edge(ext_source, ext_target, **edge_attrs)

def apply_factorization(G, results: List[SubstructureMatch]):
    processed_canonicals = set()
    
    for i, res in enumerate(results):
        canonical_start, factored_start = res.start_nodes
        factored_nodes = {pair[1] for pair in res.all_pairs}
        canonical_nodes = {pair[0] for pair in res.all_pairs}
        
        # Haal de set van alle canonical nodes op die als frontier dienen
        # Dit zijn de eerste elementen uit de paren in res.frontiers
        canonical_frontiers = {pair[0] for pair in res.frontiers}

        # STAP 1: RC node in hoofdautomaat
        rc_node_id = f"RC_{factored_start}"
        G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', label=f"RC_to_{canonical_start}")

        # Herleid entries naar RC
        for u, v, data in list(G.in_edges(factored_start, data=True)):
            if u not in factored_nodes:
                G.add_edge(u, rc_node_id, **data)

        # Herleid exits van de instance naar de rest van de hoofdautomaat
        for f_node in factored_nodes:
            for _, target, data in list(G.out_edges(f_node, data=True)):
                if target not in factored_nodes:
                    G.add_edge(rc_node_id, target, **data)

        # STAP 2: Maak de EXTERNE structuur aan
        if canonical_start not in processed_canonicals:
            # We geven nu de canonical_frontiers mee aan de functie
            create_external_library_structure(G, canonical_nodes, canonical_frontiers, i, canonical_start)
            processed_canonicals.add(canonical_start)

        # STAP 3: Verwijder de oude 'factored' instance
        nodes_to_remove = [n for n in factored_nodes if n not in canonical_nodes]
        G.remove_nodes_from(nodes_to_remove)

    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")