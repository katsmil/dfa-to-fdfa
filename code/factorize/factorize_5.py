import networkx as nx
from pathlib import Path
from collections import deque

def get_matching_edge_in_canonical(u_factored, v_factored, label, factored_to_canonical, G):
    """
    Controleert of de canonical-structuur een equivalente edge heeft.
    """
    if u_factored not in factored_to_canonical or v_factored not in factored_to_canonical:
        return False
    
    u_canonical = factored_to_canonical[u_factored]
    v_canonical = factored_to_canonical[v_factored]
    
    # Check of er een edge is tussen de canonical nodes met hetzelfde label
    if G.has_edge(u_canonical, v_canonical):
        edge_data = G.get_edge_data(u_canonical, v_canonical)
        return edge_data.get('label') == label
    return False

def get_nodes_to_preserve(G, factored_nodes, factored_start, factored_to_canonical):
    """
    Bepaalt welke factored-nodes behouden moeten blijven.
    Regel: Behoud knopen die bereikbaar zijn via een unieke (divergente) transitie,
    maar stop met 'behouden' als het pad terugkeert naar de factored_start.
    """
    preserved_nodes = set()
    queue = []

    # Stap 1: Vind de 'ingangen' (roots) van het unieke gedrag
    for u in factored_nodes:
        for _, v, data in G.out_edges(u, data=True):
            if v in factored_nodes:
                label = data.get('label')
                # Als deze interne transitie NIET in de canonical zit (divergentie)
                if not get_matching_edge_in_canonical(u, v, label, factored_to_canonical, G):
                    if v != factored_start and v not in preserved_nodes:
                        preserved_nodes.add(v)
                        queue.append(v)
    
    # Stap 2: Voeg transitieve afsluiting toe
    idx = 0
    while idx < len(queue):
        curr = queue[idx]
        idx += 1
        
        for _, neighbor, _ in G.out_edges(curr, data=True):
            if neighbor in factored_nodes:
                if neighbor == factored_start:
                    continue
                if neighbor not in preserved_nodes:
                    preserved_nodes.add(neighbor)
                    queue.append(neighbor)
                
    return preserved_nodes

def _get_out_labels(G, node):
    """Handige hulpfunctie om labels van uitgaande transities te verzamelen."""
    return {data.get('label'): target for _, target, data in G.out_edges(node, data=True)}

def apply_factorization(G, results):
    """
    Factoriseert de graaf door bij de frontiers te beginnen en uniek gedrag 
    recursief te behouden en aan de RC te koppelen.
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
                # REGEL 1: Externe transities
                if f_target not in factored_nodes:
                    print(f"  - Externe exit: {f_node} --({label})--> {f_target}. Toegevoegd aan RC.")
                    G.add_edge(rc_node_id, f_target, label=label)
                    continue
                
                # REGEL 2: Interne unieke transities
                if label not in c_out:
                    if f_target == factored_start:
                        # Loop op RC
                        G.add_edge(rc_node_id, rc_node_id, label=label)
                    else:
                        print(f"  - Unieke interne transitie: {f_node} --({label})--> {f_target}. Start behoud-pad.")
                        G.add_edge(rc_node_id, f_target, label=label)
                        if f_target not in preserved_nodes:
                            preserved_nodes.add(f_target)
                            queue.append(f_target)

        # 4. Recursieve BFS
        visited_in_bfs = set()
        while queue:
            u = queue.popleft()
            if u in visited_in_bfs:
                continue
            visited_in_bfs.add(u)
            
            edges = list(G.out_edges(u, data=True))
            for _, v, data in edges:
                # STOP A: terug naar start
                if v == factored_start:
                    print(f"    - Stop A: {u} -> start omgeleid naar {rc_node_id}")
                    G.remove_edge(u, v)
                    G.add_edge(u, rc_node_id, **data)
                
                # STOP B: extern
                elif v not in factored_nodes:
                    print(f"    - Stop B: {u} -> {v} extern, behouden.")
                    pass
                
                # INTERN pad
                else:
                    if v not in preserved_nodes:
                        preserved_nodes.add(v)
                        queue.append(v)

        # 5. Call & Return
        G.add_edge(rc_node_id, canonical_start, style='dashed', color='blue', label='call', constraint='false')
        for c_f, f_f in res.get('frontiers', []):
            G.add_edge(c_f, rc_node_id, style='dashed', color='red', label='return', constraint='false')

        # 6. Opruimen
        nodes_to_remove = factored_nodes - preserved_nodes
        G.remove_nodes_from(nodes_to_remove)

    return G

def save_dot(G, filename):
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")

if __name__ == "__main__":
    import sys
    # Probeer imports
    try:
        from bisimilar._extended_with_frontier_detection import analyze_graph_factorization
    except ImportError:
        try:
             from bisimilar._extended_with_frontier_detection import analyze_graph_factorization
        except:
             print("Kan analyze_graph_factorization niet importeren.")
             sys.exit(1)

    if len(sys.argv) < 2:
        print("Gebruik: python factorisatie.py <graph.dot>")
        sys.exit(1)

    input_file = sys.argv[1]
    G_orig = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(input_file))

    # 1. Analyse
    results = analyze_graph_factorization(input_file)
        
    if not results:
        print("Geen factorisatie mogelijk.")
    else:
        print(f"Gevonden structuren: {len(results)}")
        # 2. Factorisatie
        G_factorized = apply_factorization(G_orig, results)
        
        # 3. Opslaan
        output_folder = Path("output")
        output_folder.mkdir(parents=True, exist_ok=True)
        input_path = Path(input_file)
        output_dot = output_folder / (input_path.stem + "_factorized.dot")

        save_dot(G_factorized, str(output_dot))