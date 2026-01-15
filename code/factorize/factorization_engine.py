import networkx as nx
from collections import deque

def get_matching_edge_in_canonical(u_factored, v_factored, label, factored_to_canonical, G):
    """Controleert of de canonical-structuur een equivalente edge heeft."""
    if u_factored not in factored_to_canonical or v_factored not in factored_to_canonical:
        return False
    
    u_canonical = factored_to_canonical[u_factored]
    v_canonical = factored_to_canonical[v_factored]
    
    if G.has_edge(u_canonical, v_canonical):
        # Bij een MultiDiGraph geeft get_edge_data een dict van dicts terug
        edge_data = G.get_edge_data(u_canonical, v_canonical)
        if isinstance(edge_data, dict):
            # Check labels in alle parallelle edges
            return any(d.get('label') == label for d in edge_data.values())
    return False

def _get_out_labels(G, node):
    """Hulpfunctie om labels van uitgaande transities te verzamelen."""
    return {data.get('label'): target for _, target, data in G.out_edges(node, data=True)}

def apply_factorization(G, results):
    """
    Factoriseert de automaat rekening houdend met uniek gedrag van de factored substructuur
    """
    for i, res in enumerate(results):
        canonical_start, factored_start = res['start_nodes']
        factored_nodes = {p[1] for p in res['all_pairs']}
        factored_to_canonical_map = {p[1]: p[0] for p in res['all_pairs']}
        
        print(f"[{i+1}] Analyse frontier-divergentie voor factored-start: {factored_start}")

        # 1. Maak de RC-knoop aan
        rc_node_id = f"RC_{factored_start}"
        G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', 
                   label=f"RC\n(to {canonical_start})")

        # 2. Omleiden inkomende transities van buitenaf naar RC
        in_edges = list(G.in_edges(factored_start, data=True))
        for u, v, data in in_edges:
            if u not in factored_nodes:
                G.add_edge(u, rc_node_id, **(data or {}))

        # 3. Frontier-check & Queue opbouw
        preserved_nodes = set()
        queue = deque()
        
        for f_node, c_node in factored_to_canonical_map.items():
            f_out = _get_out_labels(G, f_node)
            c_out = _get_out_labels(G, c_node)
            
            for label, f_target in f_out.items():
                # REGEL 1: Externe transities (Exits naar omgeving)
                if f_target not in factored_nodes:
                    print(f"  - Externe exit: {f_node} --({label})--> {f_target}. Toegevoegd aan RC.")
                    G.add_edge(rc_node_id, f_target, label=label)
                    continue
                
                # REGEL 2: Interne unieke transities (Divergentie)
                if label not in c_out:
                    if f_target == factored_start:
                        G.add_edge(rc_node_id, rc_node_id, label=label)
                    else:
                        print(f"  - Unieke interne transitie: {f_node} --({label})--> {f_target}. Start behoud-pad.")
                        G.add_edge(rc_node_id, f_target, label=label)
                        if f_target not in preserved_nodes:
                            preserved_nodes.add(f_target)
                            queue.append(f_target)

        # 4. Recursieve BFS voor behoud van unieke paden
        visited_in_bfs = set()
        while queue:
            u = queue.popleft()
            if u in visited_in_bfs: continue
            visited_in_bfs.add(u)
            
            edges = list(G.out_edges(u, data=True))
            for _, v, data in edges:
                if v == factored_start:
                    print(f"    - Stop A: {u} -> start omgeleid naar {rc_node_id}")
                    G.remove_edge(u, v)
                    G.add_edge(u, rc_node_id, **data)
                elif v not in factored_nodes:
                    print(f"    - Stop B: {u} -> {v} extern, behouden.")
                    pass
                else:
                    if v not in preserved_nodes:
                        preserved_nodes.add(v)
                        queue.append(v)

        # 5. Call & Return lijnen
        G.add_edge(rc_node_id, canonical_start, style='dashed', color='blue', label='call', constraint='false')
        for c_f, f_f in res.get('frontiers', []):
            G.add_edge(c_f, rc_node_id, style='dashed', color='red', label='return', constraint='false')

        # 6. Opruimen van niet-gebruikte nodes
        nodes_to_remove = factored_nodes - preserved_nodes
        G.remove_nodes_from(nodes_to_remove)

    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")