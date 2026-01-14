import networkx as nx
from pathlib import Path

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

def apply_factorization(G, results):
    """
    Past factorisatie toe waarbij uniek intern gedrag behouden blijft en correct wordt omgeleid.
    """
    nodes_to_remove_total = set()

    # Sorteer resultaten om index-issues te voorkomen, en verwerk ze
    for i, res in enumerate(results):
        master_start, slave_start = res['start_nodes']
        slave_nodes = {p[1] for p in res['all_pairs']}
        slave_to_master_map = {p[1]: p[0] for p in res['all_pairs']}
        
        print(f"Factoriseren structuur {i+1}: Master={master_start}, Slave_Start={slave_start}")

        # 1. Bepaal welke nodes we MOETEN houden (L1, M1 etc.)
        # Dit zijn knopen die bereikbaar zijn via afwijkend gedrag
        nodes_to_preserve = get_nodes_to_preserve(G, slave_nodes, slave_start, slave_to_master_map)
        if nodes_to_preserve:
            print(f"  - Behoud unieke interne nodes: {nodes_to_preserve}")

        # 2. Maak RC node
        rc_node_id = f"RC_{slave_start}" 
        G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', label=f"RC\n(to {master_start})")

        # 3. Omleiden INKOMENDE transities (naar de hele structuur)
        in_edges = list(G.in_edges(slave_start, data=True))
        for u, v, data in in_edges:
            # Negeer self-loops of loops binnen de slave set voor nu (worden bij stap 4 behandeld)
            if u in slave_nodes: 
                continue
            G.add_edge(u, rc_node_id, **data)

        # 4. Verwerken van UITGAANDE transities
        # We itereren over alle knopen in de orginele slave structuur
        
        for u in slave_nodes:
            out_edges = list(G.out_edges(u, data=True))
            
            for _, v, data in out_edges:
                label = data.get('label', 'unlabeled')
                
                # --- SCENARIO A: Bron 'u' wordt VERWIJDERD (bijv. K1, L1a) ---
                if u not in nodes_to_preserve:
                    # 1. Naar Extern: Koppel aan RC (cross transitions)
                    if v not in slave_nodes:
                        print(f"  - Verplaats extern gedrag ({label}): {u}->{v} wordt {rc_node_id}->{v}")
                        G.add_edge(rc_node_id, v, **data)
                    
                    # 2. Naar een BEHOUDEN slave node: Koppel aan RC (de 'h' transitie)
                    # Dit is de fix: omdat 'u' weggaat, neemt RC de transitie naar de behouden 'v' over.
                    elif v in nodes_to_preserve:
                        print(f"  - Verplaats uniek intern gedrag ({label}): {u}->{v} wordt {rc_node_id}->{v}")
                        G.add_edge(rc_node_id, v, **data)
                        
                    # 3. Naar een VERWIJDERDE slave node:
                    # Normaal gedrag (master dekt dit). Maar check op divergentie naar START.
                    elif v == slave_start:
                         # Als dit een divergente edge was naar start (zeldzaam), wordt het RC->RC
                         if not get_matching_edge_in_master(u, v, label, slave_to_master_map, G):
                             G.add_edge(rc_node_id, rc_node_id, **data)
                    else:
                        # Dit is interne structuur die gedekt wordt door master -> verwijderen
                        pass 

                # --- SCENARIO B: Bron 'u' wordt BEHOUDEN (bijv. L1, M1) ---
                else:
                    # De node 'u' blijft bestaan. We moeten checken waar zijn pijlen heen gaan.
                    
                    # 1. Naar de VERWIJDERDE slave start (bijv. M1 -> K1, de 'u' back loop)
                    if v == slave_start:
                        print(f"  - Omleiden return-loop ({label}): {u}->{v} wordt {u}->{rc_node_id}")
                        # Verwijder oude edge (want v gaat weg), voeg nieuwe toe naar RC
                        if G.has_edge(u, v):
                            # Let op: remove_edge kan fout gaan als we itereren, maar we itereren over een list(out_edges) copy
                            G.remove_edge(u, v) 
                        G.add_edge(u, rc_node_id, **data)
                    
                    # 2. Naar een andere VERWIJDERDE node (niet start)
                    elif v in slave_nodes and v not in nodes_to_preserve:
                         # Dit is lastig: u blijft, v gaat weg. 
                         # Dit impliceert dat u -> v een transitie was die matchte met master.
                         # Omdat u bewaard is (vanwege uniek pad), maar nu terugkeert naar 'standaard' pad (v),
                         # moeten we v eigenlijk OOK bewaren (zoals in get_nodes_to_preserve stap 2).
                         # Als get_nodes_to_preserve goed werkt, komt dit scenario theoretisch niet voor,
                         # omdat v dan ook in preserved zou zitten.
                         pass
                    
                    # 3. Naar Extern of naar andere Behouden node:
                    # Niets doen, deze edge blijft gewoon bestaan.
                    else:
                        pass

        # 5. Visuele verbindingen (Call & Return)
        G.add_edge(rc_node_id, master_start, style='dashed', color='blue', label='call', constraint='false')
        
        for slave_frontier in res['frontiers']:
            if isinstance(slave_frontier, tuple):
                 master_frontier_node = slave_frontier[0]
                 # Voeg return lines toe voor visualisatie
                 G.add_edge(master_frontier_node, rc_node_id, style='dashed', color='red', label='return', constraint='false')

        # 6. Markeer knopen voor verwijdering
        to_remove = slave_nodes - nodes_to_preserve
        nodes_to_remove_total.update(to_remove)

    # 7. Definitieve verwijdering
    # Check eerst of nodes nog bestaan voordat we ze removen (voor veiligheid)
    nodes_to_remove_existing = [n for n in nodes_to_remove_total if G.has_node(n)]
    G.remove_nodes_from(nodes_to_remove_existing)
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
    G_orig = nx.DiGraph(nx.drawing.nx_pydot.read_dot(input_file))
    
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