import networkx as nx
from utils.graph_utils import read_dot
from analysis.dominator_analysis import get_maximal_regions

"""
ALGORITME: Dominator-Based Isomorphism Detector
===============================================

Dit script identificeert herhalende (isomorfe) structuren binnen een gerichte graaf (DFA/Control Flow Graph).

Kernstappen:
1. SCC-Isolatie: De graaf wordt opgedeeld in Strongly Connected Components.
2. Dominator Analyse: Binnen elke SCC worden regio's gevormd op basis van de 
   'Virtual Root Dominator' methode. Dit isoleert lussen met meerdere ingangen.
3. Maximale Regio's: Alleen de grootste logische structuren worden behouden 
   (geen fragmenten die al onderdeel zijn van een grotere regio).
4. Isomorfie Check (NetworkX): 
   In plaats van handmatige hashing gebruiken we `nx.is_isomorphic`.
   Eerst wordt een pre-check gedaan op het aantal knopen en randen voor snelheid.
   https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.isomorphism.is_isomorphic.html#networkx.algorithms.isomorphism.is_isomorphic

Gebruik:
    python isomorphism_detector.py <pad_naar_file.dot>
"""

def find_isomorphic_components(dot_file):
    G = read_dot(dot_file)
    all_components = []

    # 1. Analyse per SCC
    for scc in nx.strongly_connected_components(G):
        if len(scc) < 2:
            continue

        regions = get_maximal_regions(G, scc)

        for entry, nodes in regions.items():
            all_components.append({
                'entry': entry,
                'nodes': nodes,
                'structure': G.subgraph(nodes).copy()
            })

    # 2. Isomorfie Groepering
    groups = []
    for comp in all_components:
        found = False
        for group in groups:
            ref = group[0]
            # Pre-checks voor snelheid
            if (comp['structure'].number_of_nodes() == ref['structure'].number_of_nodes() and
                comp['structure'].number_of_edges() == ref['structure'].number_of_edges()):
                
                # Check of labels ook overeenkomen, dit kan op edges en op nodes
                em = lambda e1, e2: e1.get('label') == e2.get('label')
                #nm = lambda n1, n2: n1.get('label') == n2.get('label')
                if nx.is_isomorphic(comp['structure'], ref['structure'], edge_match=em):
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

    print(f"\n--- Analyse Resultaten ---")
    if not isomorphic_groups:
        print("Geen isomorfe dominator-regio's gevonden.")
    
    for i, group in enumerate(isomorphic_groups, 1):
        print(f"\nIsomorfe Groep {i}:")
        for item in group:
            print(f"  - Entry: {item['entry']}")
            print(f"    Nodes: {sorted(list(item['nodes']))}")