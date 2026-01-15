import networkx as nx
from collections import deque

def _get_out_labels(G, node):
    """Hulpfunctie om labels van uitgaande transities te verzamelen."""
    return {data.get('label'): target for _, target, data in G.out_edges(node, data=True)}

def create_recursive_call_node(G, factored_start, canonical_start):
    """Maakt de oranje RC-knoop aan die de substructuur vervangt."""
    rc_node_id = f"RC_{factored_start}"
    G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange', 
               label=f"RC\n(to {canonical_start})")
    return rc_node_id

def redirect_external_entries_to_rc(G, factored_start, factored_nodes, rc_node_id):
    """Leidt alle inkomende transities van buiten de te factoriseren set om naar de RC."""
    in_edges = list(G.in_edges(factored_start, data=True))
    for u, v, data in in_edges:
        if u not in factored_nodes:
            G.add_edge(u, rc_node_id, **(data or {}))

def handle_frontier_divergence(G, factored_to_canonical_map, factored_nodes, factored_start, rc_node_id):
    """
    Checkt de frontiers op afwijkend gedrag t.o.v. de canonical en initialiseert 
    de queue voor het behouden van unieke paden.
    """
    preserved_nodes = set()
    queue = deque()
    
    for f_node, c_node in factored_to_canonical_map.items():
        f_out = _get_out_labels(G, f_node)
        c_out = _get_out_labels(G, c_node)
        
        for label, f_target in f_out.items():
            # REGEL 1: Externe exits naar de omgeving
            if f_target not in factored_nodes:
                G.add_edge(rc_node_id, f_target, label=label)
                continue
            
            # REGEL 2: Interne unieke transities (Divergentie)
            if label not in c_out:
                if f_target == factored_start:
                    G.add_edge(rc_node_id, rc_node_id, label=label)
                else:
                    G.add_edge(rc_node_id, f_target, label=label)
                    if f_target not in preserved_nodes:
                        preserved_nodes.add(f_target)
                        queue.append(f_target)
    
    return preserved_nodes, queue

def traverse_and_preserve_unique_paths(G, queue, preserved_nodes, factored_nodes, factored_start, rc_node_id):
    """Verkent recursief alle paden die behouden moeten blijven binnen de factored structuur."""
    visited_in_bfs = set()
    while queue:
        u = queue.popleft()
        if u in visited_in_bfs: continue
        visited_in_bfs.add(u)
        
        edges = list(G.out_edges(u, data=True))
        for _, v, data in edges:
            if v == factored_start:
                # Pad leidt terug naar start: ombuigen naar RC
                G.remove_edge(u, v)
                G.add_edge(u, rc_node_id, **data)
            elif v in factored_nodes:
                # Intern pad: toevoegen aan behoud-set
                if v not in preserved_nodes:
                    preserved_nodes.add(v)
                    queue.append(v)
            # Externe transities vanuit behouden nodes blijven automatisch bestaan

def add_call_return_edges(G, rc_node_id, canonical_start, frontiers):
    """Voegt de visuele call (blauw) en return (rood) lijnen toe tussen master en RC."""
    G.add_edge(rc_node_id, canonical_start, style='dashed', color='blue', label='call', constraint='false')
    for canonical_frontier, _ in frontiers:
        G.add_edge(canonical_frontier, rc_node_id, style='dashed', color='red', label='return', constraint='false')

def cleanup_redundant_factored_nodes(G, factored_nodes, preserved_nodes):
    """Verwijdert de nodes van de factored structuur die niet uniek bleken te zijn."""
    nodes_to_remove = factored_nodes - preserved_nodes
    G.remove_nodes_from(nodes_to_remove)

def apply_factorization(G, results):
    """
    De hoofdloop van het factorisatieproces.
    """
    for i, res in enumerate(results):
        canonical_start, factored_start = res['start_nodes']
        factored_nodes = {p[1] for p in res['all_pairs']}
        factored_to_canonical_map = {p[1]: p[0] for p in res['all_pairs']}
        
        print(f"[{i+1}] Start factorisatie voor: {factored_start}")

        # Stap 1: Infrastructuur
        rc_node_id = create_recursive_call_node(G, factored_start, canonical_start)
        redirect_external_entries_to_rc(G, factored_start, factored_nodes, rc_node_id)

        # Stap 2: Identificeer uniek gedrag (Frontier divergentie)
        preserved_nodes, queue = handle_frontier_divergence(
            G, factored_to_canonical_map, factored_nodes, factored_start, rc_node_id
        )

        # Stap 3: Behoud unieke paden (Recursieve verkenning)
        traverse_and_preserve_unique_paths(
            G, queue, preserved_nodes, factored_nodes, factored_start, rc_node_id
        )

        # Stap 4: Koppeling & Opruimen
        add_call_return_edges(G, rc_node_id, canonical_start, res.get('frontiers', []))
        cleanup_redundant_factored_nodes(G, factored_nodes, preserved_nodes)

    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")