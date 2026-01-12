import networkx as nx

def create_rtn_subautomaton(G, overlap_result):
    """
    Extraheert een subautomaat en markeert entry/exit punten.
    """
    pairs = overlap_result['matched_pairs']
    sub_nodes = [p[0] for p in pairs] # We gebruiken de 'linker' set als template
    
    # Maak de sub-automaat
    sub_G = G.subgraph(sub_nodes).copy()
    
    # Bepaal exit-punten (nodes in de overlap die wijzen naar nodes buiten de overlap)
    exit_points = []
    for node in sub_nodes:
        out_edges = G.out_edges(node, data=True)
        for _, target, data in out_edges:
            if target not in sub_nodes:
                exit_points.append((node, target, data['label']))
                
    return sub_G, exit_points

def factorize_graph(G, overlap_result):
    """
    Bouwt de hoofdgraaf om naar een RTN structuur.
    """
    sub_G, exits = create_rtn_subautomaton(G, overlap_result)
    n1, n2 = overlap_result['start_nodes']
    
    # 1. Maak een CALL node naar de sub-automaat
    # 2. Verwijder de dubbele paden uit G
    # 3. Verbind de RETURN paden
    
    # Dit is de plek waar je de logica van RTN implementeert:
    # In plaats van directe transities, gebruik je een stack-gebaseerde aanpak
    # of een gemarkeerde 'Call' node in de DOT-file.
    pass