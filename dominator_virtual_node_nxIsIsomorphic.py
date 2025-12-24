import networkx as nx
from collections import defaultdict

"""
ALGORITME: Multi-Entry SCC Dominator Isomorphism [scc_distinct_preheader_entries.dot]
================================================

Het algoritme is specifiek ontworpen om herhalende patronen in lussen te vinden, 
zelfs als deze met elkaar verbonden zijn door kruisverwijzingen (cross-edges).

1. SCC-Isolatie & Entry Point Detectie:
   De graaf wordt eerst verdeeld in Strongly Connected Components (SCC's).
   Per SCC worden de 'Entry Points' geïdentificeerd: knopen die van buiten de 
   SCC worden aangestuurd (entry edges afkomend van pre-headers).

2. Virtual Root Dominator Analyse (Lurale Isolatie):
   Om te voorkomen dat de ene loop de andere onterecht domineert via 
   kruispaden (bijv. D1 -> B2), introduceert het algoritme een tijdelijke 
   'Virtual Root' per SCC. Deze virtuele bron wijst direct naar alle Entry 
   Points. Hierdoor worden parallelle lussen als 'siblings' behandeld in de 
   dominator-boom in plaats van als hiërarchische kinderen. 
   --> nog de vraag waarom niet altijd gekozen moeten worden voor het absolute
       beginpunt van de graaf.

3. Maximale Dominator Regio's:
   Voor elke knoop wordt de set van alle knopen die hij domineert bepaald. 
   We filteren op 'Maximale Regio's' om te voorkomen dat we kleine fragmenten 
   vinden die al onderdeel zijn van een grotere logische structuur.

4. Label-Sensitive Canonical Hashing:
   Elke gevonden regio wordt vertaald naar een structurele hash. Hierbij zijn 
   knoopnamen irrelevant, maar zijn de edge-labels en de topologische 
   verbindingen leidend. Regio's met dezelfde hash zijn isomorf.
"""

# ============================================================
# DOT -> NetworkX DiGraph
# ============================================================

def read_dot(path):
    # Gebruik pydot om de dot file te parsen
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

def canonical_hash(G, nodes, iterations=10):
    description = {node: "()" for node in nodes}
    for _ in range(iterations):
        description = refine_descriptions(G, nodes, description)
    return tuple(sorted(description.values()))

def refine_descriptions(G, nodes, description):
    new_description = {}
    for node in nodes:
        edges = []
        for succ in G.successors(node):
            if succ in nodes:
                label = G[node][succ].get("label", "")
                edges.append((label, description[succ]))
        
        sorted_edges = sorted(edges)
        if not sorted_edges:
            new_description[node] = "()"
        else:
            parts = [f"{label}:{desc}" for label, desc in sorted_edges]
            new_description[node] = "(" + ",".join(parts) + ")"
    return new_description

# ============================================================
# Virtual Root & Dominator Logica
# ============================================================

def get_scc_dominators(G, scc_nodes):
    """
    Creëert een virtuele root boven alle ingangen van de SCC.
    Dit voorkomt dat de ene loop de andere 'domineert' via cross-edges.
    """
    S = G.subgraph(scc_nodes).copy()
    
    # Vind knopen met inkomende lijnen van BUITEN de SCC
    entries = set()
    for node in scc_nodes:
        for pred in G.predecessors(node):
            if pred not in scc_nodes:
                entries.add(node)
    
    # Fallback als de SCC geen externe ingangen heeft (bv. hele graaf is SCC, 
    # of lexicografisch een node aanwijzen als root
    # misschien beter om hier een node aan te wijzen met een zekere indegree)
    if not entries:
        entries = {min(scc_nodes)}

    v_root = "__VIRTUAL_ROOT__"
    S.add_node(v_root)
    for entry in entries:
        S.add_edge(v_root, entry)

    idom = nx.immediate_dominators(S, v_root)
    return idom, v_root

def filter_maximal_regions(candidates):
    """
    Verwijder regio's die volledig vervat zijn in een grotere regio.
    """
    final_regions = {}
    # Sorteer op grootte van de set (grootste eerst)
    sorted_items = sorted(candidates.items(), key=lambda x: len(x[1]), reverse=True)

    for head, region in sorted_items:
        is_subset = False
        for existing in final_regions.values():
            if region.issubset(existing) and region != existing:
                is_subset = True
                break
        if not is_subset:
            final_regions[head] = region
    return final_regions

# ============================================================
# Hoofdalgoritme
# ============================================================

def find_isomorphic_components(dot_file):
    G = read_dot(dot_file)
    all_components = []

    for scc in nx.strongly_connected_components(G):
        if len(scc) < 2:
            continue

        # 1. Bereken dominators met de Virtual Root truc
        idom, v_root = get_scc_dominators(G, scc)

        # 2. Bouw volledige dominator sets per knoop
        dom_map = defaultdict(set)
        for n in scc:
            curr = n
            while curr in idom:
                if curr != v_root:
                    dom_map[n].add(curr)
                if curr == idom[curr] or idom[curr] == v_root:
                    break
                curr = idom[curr]

        # 3. Groepeer knopen per dominator (regio-vorming)
        candidates = {}
        for d in scc:
            region = {n for n in scc if d in dom_map[n]}
            if len(region) > 1:
                candidates[d] = region

        # 4. Maximaliteits-filter
        final_regions = filter_maximal_regions(candidates)

        # 5. Hash de regio's voor isomorfie-check
        for entry, nodes in final_regions.items():
            H = G.subgraph(nodes)
            all_components.append({
                'entry': entry,
                'nodes': nodes,
                'structure': H
            })

    # 6. Groeperen op basis van isomorfie
    isomorphic_groups = []
    
    for comp in all_components:
        found_match = False
        
        for group in isomorphic_groups:
            # Pak de eerste graaf uit de groep als referentie
            reference_comp = group[0]
            
            # Snelle pre-check: hebben ze hetzelfde aantal knopen/edges?
            # Dit versnelt het proces aanzienlijk.
            if (comp['structure'].number_of_nodes() == reference_comp['structure'].number_of_nodes() and
                comp['structure'].number_of_edges() == reference_comp['structure'].number_of_edges()):
                
                # De eigenlijke NetworkX isomorfie check
                if nx.is_isomorphic(comp['structure'], reference_comp['structure']):
                    group.append(comp)
                    found_match = True
                    break
        
        if not found_match:
            # Start een nieuwe groep voor deze unieke structuur
            isomorphic_groups.append([comp])

    # 7. Filteren: alleen groepen teruggeven die meer dan één component bevatten
    return [g for g in isomorphic_groups if len(g) > 1]
    
    #en dan ieder element in de lijst van all_components met elkaar vergelijk 
    #middels de isomorfie check van networkx?

    """ # 6. Groeperen op basis van de hash
    groups = defaultdict(list)
    for comp in all_components:
        groups[comp['hash']].append(comp)

    # Alleen groepen met meer dan 1 exemplaar zijn interessant (isomorfie)
    return [g for g in groups.values() if len(g) > 1] """

# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Gebruik: python dominator.py <file.dot>")
        sys.exit(1)

    dot_file = sys.argv[1]
    isomorphic_groups = find_isomorphic_components(dot_file)

    print(f"\n--- Analyse Resultaten ---")
    if not isomorphic_groups:
        print("Geen isomorfe dominator-regio's gevonden.")
    
    for i, group in enumerate(isomorphic_groups, 1):
        print(f"\nIsomorfe Groep {i}:")
       # print(f"  Hash: {group[0]['hash'][0][:15]}...") 
        for item in group:
            print(f"  - Entry: {item['entry']}")
            print(f"    Nodes: {sorted(list(item['nodes']))}")