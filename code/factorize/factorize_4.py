import networkx as nx
from pathlib import Path
from collections import deque

def get_matching_edge_in_master(u_slave, v_slave, label, slave_to_master, G):
    """
    Controleert of de master-structuur een equivalente edge heeft.
    """
    if u_slave not in slave_to_master or v_slave not in slave_to_master:
        return False
    
    u_master = slave_to_master[u_slave]
    v_master = slave_to_master[v_slave]
    
    # Check of er een edge is tussen de master nodes met hetzelfde label
    if G.has_edge(u_master, v_master):
        edge_data = G.get_edge_data(u_master, v_master)
        # NetworkX DiGraph: edge_data is een dict attributes
        return edge_data.get('label') == label
    return False

def get_nodes_to_preserve(G, slave_nodes, slave_start, slave_to_master):
    """
    Bepaalt welke slave-nodes behouden moeten blijven.
    Regel: Behoud knopen die bereikbaar zijn via een unieke (divergente) transitie,
    maar stop met 'behouden' als het pad terugkeert naar de slave_start.
    """
    preserved_nodes = set()
    queue = []

    # Stap 1: Vind de 'ingangen' (roots) van het unieke gedrag
    for u in slave_nodes:
        for _, v, data in G.out_edges(u, data=True):
            if v in slave_nodes:
                label = data.get('label')
                # Als deze interne transitie NIET in de master zit (divergentie)
                if not get_matching_edge_in_master(u, v, label, slave_to_master, G):
                    # We behouden de 'target' v, tenzij v de start is (dan wordt het een loop op RC)
                    if v != slave_start and v not in preserved_nodes:
                        preserved_nodes.add(v)
                        queue.append(v)
    
    # Stap 2: Voeg transitieve afsluiting toe (alles wat volgt op de unieke tak moet ook blijven)
    idx = 0
    while idx < len(queue):
        curr = queue[idx]
        idx += 1
        
        for _, neighbor, _ in G.out_edges(curr, data=True):
            # Als de buurman in de slave set zit, moeten we hem waarschijnlijk ook houden
            # zodat het pad intact blijft.
            if neighbor in slave_nodes:
                # CRUCIALE CHECK: Als het pad terugloopt naar de start, stoppen we met behouden.
                # Die edge wordt later omgebogen naar de RC.
                if neighbor == slave_start:
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
        master_start, slave_start = res['start_nodes']
        slave_nodes = {p[1] for p in res['all_pairs']}
        # Mapping nodig voor de initiële vergelijking
        slave_to_master_map = {p[1]: p[0] for p in res['all_pairs']}
        
        print(f"[{i+1}] Analyse frontier-divergentie voor slave-start: {slave_start}")

        # 1. Maak de RC-knoop aan
        rc_node_id = f"RC_{slave_start}"
        G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', 
                   label=f"RC\n(to {master_start})")

        # 2. Omleiden inkomende transities van buitenaf naar RC
        in_edges = list(G.in_edges(slave_start, data=True))
        for u, v, data in in_edges:
            if u not in slave_nodes:
                G.add_edge(u, rc_node_id, **(data or {}))

        # 3. Frontier-check & Queue opbouw
        preserved_nodes = set()
        queue = deque()
        
        # We kijken naar alle paren die als 'match' zijn geïdentificeerd (frontiers)
        for s_node, m_node in slave_to_master_map.items():
            s_out = _get_out_labels(G, s_node)
            m_out = _get_out_labels(G, m_node)
            
            for label, s_target in s_out.items():
                # Als de master deze transitie NIET heeft, is het uniek gedrag
                if label not in m_out:
                    # Bepaal waar de RC heen moet wijzen
                    if s_target == slave_start:
                        # Directe loop terug naar het begin
                        # G.add_edge(rc_node_id, rc_node_id, label=label)
                        continue
                    if s_target not in slave_nodes:
                        # Transitie naar buiten de structuur
                        G.add_edge(rc_node_id, s_target, label=label)
                    else:
                        # Uniek intern pad: koppel aan RC en start verkenning
                        print(f"  - Unieke transitie gevonden: {s_node} --({label})--> {s_target}. Koppelen aan RC.")
                        G.add_edge(rc_node_id, s_target, label=label)
                        if s_target not in preserved_nodes:
                            preserved_nodes.add(s_target)
                            queue.append(s_target)

        # 4. Recursieve controle van de achterliggende toestanden (BFS)
        visited_in_bfs = set()
        while queue:
            u = queue.popleft()
            if u in visited_in_bfs: continue
            visited_in_bfs.add(u)
            
            # Kopieer uitgaande edges voor analyse
            edges = list(G.out_edges(u, data=True))
            for _, v, data in edges:
                # STOPCONDITIE A: Terug naar de start van de structuur
                if v == slave_start:
                    print(f"    - Stopconditie A: Loop van {u} naar start omgeleid naar {rc_node_id}")
                    G.remove_edge(u, v)
                    G.add_edge(u, rc_node_id, **data)
                
                # STOPCONDITIE B: Naar buiten de slave-structuur
                elif v not in slave_nodes:
                    # Deze pijl laten we gewoon staan (v is extern)
                    print(f"    - Stopconditie B: Transitie {u} -> {v} (extern) behouden.")
                    pass
                
                # DOORGAAN: Intern pad binnen de slave structuur
                elif v in slave_nodes:
                    if v not in preserved_nodes:
                        preserved_nodes.add(v)
                        queue.append(v)

        # 5. Call & Return lijnen voor visualisatie
        G.add_edge(rc_node_id, master_start, style='dashed', color='blue', label='call', constraint='false')
        for m_f, s_f in res.get('frontiers', []):
            G.add_edge(m_f, rc_node_id, style='dashed', color='red', label='return', constraint='false')

        # 6. Opruimen: Verwijder alleen de nodes die NIET bewaard zijn
        nodes_to_remove = slave_nodes - preserved_nodes
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
    #G_orig = nx.DiGraph(nx.drawing.nx_pydot.read_dot(input_file))
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