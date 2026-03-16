import networkx as nx
from collections import defaultdict

# ============================================================
# DOT -> NetworkX DiGraph
# ============================================================

def read_dot(path):
    g = nx.drawing.nx_pydot.read_dot(path)
    G = nx.DiGraph()

    for u, v, data in g.edges(data=True):
        label = data.get("label", "")
        if isinstance(label, str):
            label = label.strip('"')
        G.add_edge(u, v, label=label)

    return G


# ============================================================
# Canonical hashing voor gelabelde subgrafen
# ============================================================
# iterations is in feite een depth
def canonical_hash(G, nodes, iterations=10):
    """
    Compute a canonical, label-sensitive structural hash for a subgraph.

    Nodes are treated as anonymous; only edge labels and structure matter.
    """

    # 1. Initial description: all nodes look the same
    description = {node: "()" for node in nodes}

    # 2. Iteratively refine descriptions using outgoing edges
    for _ in range(iterations):
        description = refine_descriptions(G, nodes, description)

    # 3. Canonical form: sorted multiset of node descriptions
    return tuple(sorted(description.values()))

def refine_descriptions(G, nodes, description):
    new_description = {}

    for node in nodes:
        edges = outgoing_edges(G, node, nodes, description)
        new_description[node] = format_node(edges)

    return new_description

def outgoing_edges(G, node, nodes, description):
    edges = []

    for succ in G.successors(node):
        if succ in nodes:
            label = G[node][succ].get("label", "")
            edges.append((label, description[succ]))

    return sorted(edges)

def format_node(edges):
    if not edges:
        return "()"

    parts = [f"{label}:{desc}" for label, desc in edges]
    return "(" + ",".join(parts) + ")"

def get_candidate_roots(G, scc):
    """
    Bepaalt welke knopen als 'root' (startpunt) moeten dienen voor dominator analyse.
    """
    candidates = set()
    
    # HEURISTIEK 1: Externe Entry Points
    # Knopen in de SCC die een inkomende edge hebben van buiten de SCC
    for node in scc:
        for predecessor in G.predecessors(node):
            if predecessor not in scc:
                candidates.add(node)
                break # 1 externe edge is genoeg om kandidaat te zijn
    
    # HEURISTIEK 3 (Fallback/Exhaustive): 
    # Als er geen externe entries zijn (bijv. de SCC is de hele graaf), 
    # of om interne lussen te vinden, kunnen we alle knopen proberen.
    # Voor optimalisatie: kies knopen met in-degree > 1 (potentiële loop headers).
    if not candidates:
        # Fallback: probeer alle knopen (of filter op in_degree > 1)
        # Voor research doeleinden is 'alle knopen' het veiligst om patronen te vinden.
        candidates = scc
    
    return list(candidates)

def dominator_regions_for_root(G, root, scc_nodes):
    """
    Berekent dominator regio's gegeven een SPECIFIEKE root binnen de SCC.
    We bouwen een subgraph die alleen bestaat uit de SCC nodes + de gekozen root.
    """
    # Maak een subgraaf van alleen de SCC om 'vervuiling' van buitenaf te voorkomen
    # bij het berekenen van paden.
    scc_subgraph = G.subgraph(scc_nodes).copy()
    
    # Check: is de root wel bereikbaar? (In een SCC is alles bereikbaar vanuit alles,
    # maar voor de zekerheid).
    if root not in scc_subgraph:
        return {}

    # 1. Immediate Dominators berekenen VANAF de gekozen root
    # Note: nx.immediate_dominators werkt op de hele graaf, maar we willen het 
    # beperken tot de flow binnen de SCC vanaf de root.
    try:
        idom = nx.immediate_dominators(scc_subgraph, root)
    except nx.NetworkXError:
        # Kan gebeuren als de graaf niet volledig verbonden is zoals verwacht
        return {}

    # 2. Bouw de volledige dominator sets
    dom = {n: set() for n in scc_nodes}
    for n in scc_nodes:
        if n not in idom: continue # Onbereikbaar vanaf root
        curr = n
        while curr != root:
            dom[n].add(curr)
            if curr not in idom or idom[curr] == curr:
                break
            curr = idom[curr]
        dom[n].add(root) # Root domineert altijd

    # 3. Maximal Regions logic (deze had je al, iets compacter hier):
    regions = {}
    
    # Voor elke mogelijke 'header' (dominator), wat domineert hij?
    # We keren de map om: header -> list of dominated nodes
    header_to_region = defaultdict(set)
    for node, dominators in dom.items():
        for d in dominators:
            header_to_region[d].add(node)

    # Filteren: alleen regio's groter dan 1 knoop
    candidates = {h: r for h, r in header_to_region.items() if len(r) > 1}
    
    # Maximaliteits-filter (zoals in jouw code)
    final_regions = {}
    sorted_candidates = sorted(candidates.items(), key=lambda x: len(x[1]), reverse=True)
    
    for head, region in sorted_candidates:
        is_subset = False
        for existing in final_regions.values():
            if region < existing: # Strict subset check
                is_subset = True
                break
        if not is_subset:
            final_regions[head] = region
            
    return final_regions

def find_isomorphic_components(dot_file):
    G = read_dot(dot_file)
    
    # Lijst van (RootNode, RegionNodes, Hash)
    all_components = []

    # Stap 1: Loop over SCCs
    for scc in nx.strongly_connected_components(G):
        if len(scc) < 2: continue
        
        # Stap 2: Bepaal mogelijke startpunten (Roots) voor deze SCC
        roots = get_candidate_roots(G, scc)
        
        print(f"SCC size {len(scc)} processing roots: {roots}")

        # Stap 3: Voor elke mogelijke root, bereken dominators
        for root in roots:
            regions = dominator_regions_for_root(G, root, scc)
            
            for entry, nodes in regions.items():
                # entry is de 'header' van de dominator regio
                # nodes zijn de knopen in die regio
                
                # Maak subgraaf voor hashing
                H = G.subgraph(nodes)
                # Hash genereren
                h = canonical_hash(H, nodes)
                
                # Sla op. We voegen 'root' toe aan de data om te weten 
                # vanuit welk perspectief we dit vonden.
                all_components.append({
                    'scc_root_perspective': root,
                    'region_entry': entry,
                    'nodes': nodes,
                    'hash': h
                })

    # Stap 4: Groeperen
    groups = defaultdict(list)
    for comp in all_components:
        groups[comp['hash']].append(comp)

    return [g for g in groups.values() if len(g) > 1]

# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys
    # Geen startnode argument meer nodig!
    if len(sys.argv) != 2:
        print("Gebruik: python dominator.py <file.dot>")
        sys.exit(1)

    dot_file = sys.argv[1]
    groups = find_isomorphic_components(dot_file)

    print(f"\n--- Resultaten ---")
    for i, group in enumerate(groups, 1):
        print(f"\nIsomorfe Groep {i} (Hash: {group[0]['hash'][0:10]}...):")
        for item in group:
            print(f"  - Gevonden in SCC (perspectief root {item['scc_root_perspective']})")
            print(f"    Region Entry: {item['region_entry']}")
            print(f"    Nodes: {sorted(list(item['nodes']))}")