import networkx as nx
from pathlib import Path

def apply_factorization(G, results):
    """
    Past factorisatie toe op graaf G op basis van de gevonden herhalende structuren.
    
    Argumenten:
    G -- De originele NetworkX DiGraph (wordt in-place aangepast)
    results -- De lijst met dictionaries output van het bisimulatie-algoritme.
    """
    
    # We itereren door de resultaten. 
    # LET OP: In een productie-omgeving zou je moeten checken of resultaten elkaar 
    # niet overlappen/vernietigen. We gaan er nu vanuit dat de filter-functie
    # unieke, niet-overlappende structuren heeft overgelaten.
    for i, res in enumerate(results):
        # 1. Identificeer Master (links) en Slave (rechts)
        # We kiezen conventioneel de linker knoop van de start_nodes als de 'In-place' master.
        master_start, slave_start = res['start_nodes']
        
        # Maak sets voor snelle lookup
        slave_nodes = {p[1] for p in res['all_pairs']}
        master_nodes = {p[0] for p in res['all_pairs']}
        
        # Mapping van slave->master om later de frontiers te kunnen koppelen
        slave_to_master_map = {p[1]: p[0] for p in res['all_pairs']}
        
        print(f"Factoriseren structuur {i+1}: Vervang {slave_start} (en {len(slave_nodes)-1} anderen) door RC -> {master_start}")

        # 2. Maak de RC (Recursive Call) toestand aan
        # We geven hem een unieke naam en een andere vorm voor visualisatie
        rc_node_id = f"RC_{slave_start}" 
        G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', label=f"RC\n(to {master_start})")

        # 3. Omleiden van INKOMENDE transities
        # Alle pijlen die naar het begin van de slave-structuur wezen, 
        # moeten nu naar de RC toestand wijzen.
        in_edges = list(G.in_edges(slave_start, data=True))
        for u, v, data in in_edges:
            # Als de inkomende pijl vanuit de slave-structuur zelf komt (recursie binnen structuur),
            # negeren we die hier even (wordt verwijderd of intern opgelost).
            if u in slave_nodes:
                continue
            
            # Voeg edge toe: Bron -> RC
            G.add_edge(u, rc_node_id, **data)

        # 4. Gedrag behouden: Transities NAAR BUITEN verplaatsen (Frontier Logic)
        # We moeten controleren of de slave-knopen (vooral de frontiers) transities hebben
        # naar knopen die GEEN onderdeel zijn van de te verwijderen structuur.
        # Deze transities moeten nu vertrekken vanuit de RC toestand.
        
        for slave_node in slave_nodes:
            out_edges = list(G.out_edges(slave_node, data=True))
            for _, target, data in out_edges:
                
                # Situatie A: De transitie blijft binnen de slave structuur.
                # Deze mag weg, want de master structuur handelt dit intern af via de Call.
                if target in slave_nodes:
                    continue
                
                # Situatie B: De transitie gaat naar buiten! (Divergent gedrag)
                # Bijv: slave_frontier -> 'cross' -> externe_node
                # We moeten deze transitie behouden door hem aan de RC te hangen.
                # De RC fungeert hier als het 'return address' dat meteen doorrolt naar de volgende staat.
                print(f"  - Behoud extern gedrag: {data.get('label', 'unlabeled')} van {slave_node} verplaatst naar {rc_node_id}")
                G.add_edge(rc_node_id, target, **data)

        # 5. Visuele verbindingen voor de Recursieve Automaat
        
        # A. De CALL (Stippellijn van RC naar Master Start)
        G.add_edge(rc_node_id, master_start, style='dashed', color='blue', label='call', constraint='false')
        
        # B. De RETURN (Stippellijnen van Master Frontiers terug naar RC)
        # Dit visualiseert dat als de master in een frontier komt, hij terugkeert naar de context van RC.
        for slave_frontier in res['frontiers']:
            # We moeten de corresponderende MASTER frontier vinden
            # De frontier in results is een tuple (master_node, slave_node)
            # Maar results['frontiers'] is een set van tuples. Even zoeken:
            
            # Omdat 'frontiers' in de result set {(m, s), ...} formaat heeft:
            if isinstance(slave_frontier, tuple):
                 master_frontier_node = slave_frontier[0]
            else:
                 # Fallback mocht de data anders gestructureerd zijn
                 continue

            # Voeg dashed return line toe
            # constraint=false zorgt dat dot de layout niet verpest door deze terugkoppeling
            G.add_edge(master_frontier_node, rc_node_id, style='dashed', color='red', label='return', constraint='false')

        # 6. Opruimen: Verwijder de oude slave structuur
        G.remove_nodes_from(slave_nodes)

    return G

# --- Hulpfunctie om het resultaat op te slaan ---
def save_dot(G, filename):
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")

if __name__ == "__main__":
    # DIT GEDEELTE SIMULEERT DE INTEGRATIE MET JOUW VORIGE SCRIPT
    
    # 1. We hebben de graaf en results nodig. 
    # In een echte run importeer je analyze_graph_factorization uit je vorige file.
    # Voor nu neem ik aan dat 'G' en 'results' beschikbaar zijn of hieronder geladen worden.
    
    import sys
    # Importeer functies uit je vorige script (ervan uitgaande dat dat 'bisimulation.py' heet)
    try:
        from bisimilar._extended_with_frontier_detection import analyze_graph_factorization
    except ImportError:
        print("Zorg dat 'bisimulation.py' (je vorige script) in dezelfde map staat.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Gebruik: python factorisatie.py <graph.dot>")
        sys.exit(1)

    input_file = sys.argv[1]
    
    # 1. Analyseer en vind structuren
    # We lezen de graaf opnieuw in om zeker te zijn dat we het origineel hebben
    G_orig = nx.DiGraph(nx.drawing.nx_pydot.read_dot(input_file))
    
    # Haal de analyse resultaten op
    results = analyze_graph_factorization(input_file)
        
    if not results:
        print("Geen factorisatie mogelijk.")
    else:
        # Print resultaat verkenning repeterende substructuren
        print(f"Totaal aantal unieke structuren gevonden: {len(results)}\n")
        
        for i, r in enumerate(results, 1):
            print(f"Structuur {i}:")
            print(f"  Start: {r['start_nodes'][0]} <-> {r['start_nodes'][1]}")
            print(f"  Grootte: {r['overlap_size']} paren")
            print(f"  Interne paren (Strict Bisimilair):")
            for p in sorted(list(r['internals'])):
                print(f"    - {p}")
            print(f"  Frontier paren (Stack-Pop locaties):")
            for p in sorted(list(r['frontiers'])):
                print(f"    - {p}")
            print("-" * 40)

        # 2. Pas factorisatie toe
        G_factorized = apply_factorization(G_orig, results)
        
        # 3. Sla resultaat op
        # Zorg ervoor dat de output folder bestaat
        output_folder = Path("output")
        output_folder.mkdir(parents=True, exist_ok=True)

        input_path = Path(input_file)

        # Genereer output bestandsnaam op basis van input (zonder map en zonder .dot)
        output_dot = output_folder / (input_path.stem + "_factorized.dot")

        save_dot(G_factorized, str(output_dot))