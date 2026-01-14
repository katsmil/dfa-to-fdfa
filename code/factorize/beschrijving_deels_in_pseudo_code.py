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

def _edge_signature(data):
    """
    Maak een deterministische signatuur van edge-attributes zodat we kunnen vergelijken
    of een transitie in de master aanwezig is die overeenkomt met een transitie in de slave.
    Pas dit aan als je alleen op 'label' wil vergelijken.
    """
    if data is None:
        return ()
    try:
        # data komt vaak als dict uit pydot; sorteren maakt vergelijking deterministisch
        return tuple(sorted(data.items()))
    except Exception:
        # fallback: probeer attribute-access of return lege handtekening
        try:
            return tuple(sorted(getattr(data, "items", lambda: [])()))
        except Exception:
            return ()

def apply_factorization(G, results):
    """
    Past factorisatie toe op graaf G op basis van de gevonden herhalende structuren.
    Deze versie behoudt gedrag dat vanuit slave-frontiers naar buiten gaat of dat
    intern is maar niet wordt afgedekt door de corresponderende master.
    """
    for i, res in enumerate(results):
        master_start, slave_start = res['start_nodes']

        # Sets en mapping zoals in jouw oorspronkelijke code
        slave_nodes = {p[1] for p in res['all_pairs']}
        master_nodes = {p[0] for p in res['all_pairs']}
        slave_to_master_map = {p[1]: p[0] for p in res['all_pairs']}

        print(f"[{i+1}] Factoriseren: vervang slave-start {slave_start} door RC -> master-start {master_start} (slave size={len(slave_nodes)})")

        # Maak RC-knop
        rc_node_id = f"RC_{slave_start}"
        # Zorg dat we niet per ongeluk een bestaand RC knoop overschrijven
        if rc_node_id in G.nodes:
            print(f"  - Let op: {rc_node_id} bestaat al; hergebruiken.")
        else:
            G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', label=f"RC\n(to {master_start})")

        # 1) Omleiden inkomende transities naar slave_start -> RC (zoals eerder)
        in_edges = list(G.in_edges(slave_start, data=True))
        for u, v, data in in_edges:
            if u in slave_nodes:
                # inkomende vanuit binnen de te verwijderen structuur: laten we die even
                # voor wat het is (interne recursie of interne edges worden verwijderd later).
                continue
            # Voeg edge toe: bron -> RC
            G.add_edge(u, rc_node_id, **(data or {}))

        # 2) Frontiers: voor elk frontier-paar starten we een gecontroleerde verkenning
        frontiers = list(res.get('frontiers', []))
        for pair in frontiers:
            if not (isinstance(pair, (list, tuple)) and len(pair) >= 2):
                continue
            master_frontier_node, slave_frontier_node = pair[0], pair[1]
            print(f"  - Verwerk frontier-paar master:{master_frontier_node} <-> slave:{slave_frontier_node}")

            # BFS vanaf de slave_frontier binnen de slave-subgraph; we werken op snapshot van out-edges
            queue = deque([slave_frontier_node])
            visited = set()
            preserved_map = {}  # slave_node -> gekloonde node onder RC (naam)

            # check of er transities zijn in de slave frontier node die niet voorkomen in de master frontiernode
            # for all outedges in slave frontier node check
            # if transitie exists in master frontier node
            #     continue
            # else
            #    add transition to RC node with target node attached.
            #    add targetnode of that transition to the queue for the recursive build up of all transitions and nodes behind it.

            # daarna gaan we de queue in en controleren alle transities en nodes erachter.
            while queue:
                u = queue.popleft()
                if u in visited:
                    continue
                visited.add(u)

                # Neem snapshot van uitgaande edges om veilig te zijn terwijl we de graf aanpassen
                out_edges = list(G.out_edges(u, data=True))
                for _, v, data in out_edges:
                    sig = _edge_signature(data)

                    # STOPCONDITIE A: transitie terug naar het begin van de te vervangen substructuur
                    # if de targetnode is de startnode van de slave structure, dan moet er een transitie tussen de node 
                    # nu gecontroleer wordt en de nieuwe RC node toegevoegd worden.

                    # STOPCONDITIE B: transitie naar buiten de slave-substructuur
                    # dan moet de transitie dus wel gemaakt worden tussen de node die nu wordt gecontroleerd en die node die buiten de substructuur ligt.
                    # if v not in slave_nodes:
                    #     # Extern gedrag moet behouden worden: voeg RC -> extern toe
                    #     print(f"    - Externe transitie ontdekt: {u} -> {v} (label={data.get('label','?')}). Voeg RC -> {v} toe.")
                    #     G.add_edge(rc_node_id, v, **(data or {}))
                    #     continue

                    # Gelden de stopcondities niet, dan moet de transite alsnog toegevoegd alsook de target node
                    # plus de targetnode moet toegevoegd worden aan queue.

           # als de queue leeg is dan denk ik dat we al het unieke gedrag van de te vervangen substructuur behouden hebben.         

            # Visualiseer return-lijn: master frontier -> RC (zoals in jouw oorspronkelijke script)
            if master_frontier_node in G.nodes:
                G.add_edge(master_frontier_node, rc_node_id, style='dashed', color='red', label='return', constraint='false')

        # 3) Voeg CALL connectie RC -> master_start toe (zoals eerder)
        G.add_edge(rc_node_id, master_start, style='dashed', color='blue', label='call', constraint='false')

        # 4) Opruimen: verwijder originele slave nodes (indien nog aanwezig)
        # Zorg dat we alleen bestaande nodes verwijderen om KeyErrors te vermijden
        to_remove = [n for n in slave_nodes if n in G.nodes]
        if to_remove:
            print(f"  - Verwijder oorspronkelijke slave-nodes: {len(to_remove)} knopen")
            G.remove_nodes_from(to_remove)
        else:
            print("  - Geen slave-nodes meer te verwijderen (mogelijk eerder bewerkt)")

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