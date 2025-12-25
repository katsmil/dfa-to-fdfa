"""
ALGORITME: Natural Loop Isomorphism Detector
============================================

Dit script vindt isomorfe structuren door Natural Loops te identificeren.  
Een Natural Loop van een back-edge (m→n), 
waarbij n de knoop m domineert, 
is de verzameling knopen x zodanig dat n de knoop x domineert 
en er een pad bestaat van x naar m dat n niet passeert.


Kernstappen:
1. SCC-Isolatie: Analyse per sterk verbonden component.
2. Virtual Root: Garandeert lokale dominator-berekening binnen de SCC.
3. Back-Edge Detectie: Zoekt naar transities die terugkeren naar een dominator.
4. Loop Body Reconstructie: Vindt alle knopen die deel uitmaken van die specifieke lus.
5. Isomorfie Groepering: Vergelijkt de gevonden lussen middels NetworkX (topologie + labels).
"""

import networkx as nx
from collections import defaultdict
from utils.graph_utils import read_dot

def get_all_dominators(idoms):
    """Zet immediate dominators om naar een volledige set per knoop."""
    all_doms = defaultdict(set)
    for node in idoms:
        curr = node
        while curr in idoms:
            all_doms[node].add(curr)
            parent = idoms[curr]
            
            # Stopconditie: we zijn bij een root (knoop domineert zichzelf)
            if parent == curr:
                break
                
            curr = parent
    return all_doms

def find_isomorphic_components(dot_file):
    G = read_dot(dot_file)
    all_found_loops = []

    # 1. Analyse per SCC
    for scc in nx.strongly_connected_components(G):
        if len(scc) < 2:
            continue

        # Maak een lokale kopie voor dominator analyse
        S = G.subgraph(scc).copy()
        
        # Entries vinden
        entries = {n for n in scc if any(p not in scc for p in G.predecessors(n))}
        if not entries: entries = {min(scc)}
        
        # Virtual Root plaatsen (soort van aggregaat)
        v_root = "__VIRTUAL_ROOT__"
        S.add_node(v_root)
        for e in entries: S.add_edge(v_root, e)

        # 2. Dominator berekening
        idoms = nx.immediate_dominators(S, v_root)
        all_doms = get_all_dominators(idoms)

        # 3. Zoek Back-Edges en identificeer Natural Loops
        for tail, header in S.edges():
            # Sla de virtuele root over
            if header == v_root: 
                continue
            
            # Een back-edge bestaat als de 'header' de 'tail' domineert
            if header in all_doms[tail]:
                # We hebben een back-edge gevonden! 
                # Reconstrueer de loop body: alle nodes die de tail kunnen 
                # bereiken zonder de header te passeren.
                loop_nodes = {header, tail}
                stack = [tail]
                
                while stack:
                    curr = stack.pop()
                    for pred in S.predecessors(curr):
                        # Stop bij de header en de virtual root
                        if pred not in loop_nodes and pred != v_root:
                            loop_nodes.add(pred)
                            stack.append(pred)
                
                # Sla de lus op voor isomorfie-check
                all_found_loops.append({
                    'header': header,
                    'nodes': loop_nodes,
                    'structure': G.subgraph(loop_nodes).copy()
                })

    # 4. Isomorfie Groepering middels NetworkX
    groups = []
    # Filter eerst op unieke node-sets om dubbele lussen (bij meerdere back-edges) te voorkomen
    unique_loops = []
    seen_sets = []
    for l in all_found_loops:
        if l['nodes'] not in seen_sets:
            unique_loops.append(l)
            seen_sets.append(l['nodes'])

    for comp in unique_loops:
        found = False
        for group in groups:
            ref = group[0]
            # Snelheids-checks: aantal nodes en edges
            if (comp['structure'].number_of_nodes() == ref['structure'].number_of_nodes() and
                comp['structure'].number_of_edges() == ref['structure'].number_of_edges()):
                
                # Match op topologie + labels (knoop & edge)
                nm = lambda n1, n2: n1.get('label') == n2.get('label')
                em = lambda e1, e2: e1.get('label') == e2.get('label')
                
                if nx.is_isomorphic(comp['structure'], ref['structure'], node_match=nm, edge_match=em):
                    group.append(comp)
                    found = True
                    break
        if not found:
            groups.append([comp])

    return [g for g in groups if len(g) > 1]

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print(f"Gebruik: python {sys.argv[0]} <file.dot>")
        sys.exit(1)

    dot_file = sys.argv[1]
    isomorphic_groups = find_isomorphic_components(dot_file)

    print(f"\n--- Analyse Resultaten: {dot_file} ---")
    if not isomorphic_groups:
        print("Geen isomorfe lussen gevonden.")
    
    for i, group in enumerate(isomorphic_groups, 1):
        print(f"\nIsomorfe Groep {i} (Aantal: {len(group)}):")
        for item in group:
            print(f"  - Header Node: {item['header']}")
            print(f"    Body Nodes:  {sorted(list(item['nodes']))}")