import networkx as nx
from utils.graph_utils import read_dot
from analysis.dominator_analysis import get_maximal_regions

"""
ALGORITHM: Dominator-Based Isomorphism Detector
===============================================

This script identifies recurring (isomorphic) structures within a directed graph (DFA/Control Flow Graph).

Core steps:
1. SCC Isolation: The graph is partitioned into Strongly Connected Components.
2. Dominator Analysis: Within each SCC, regions are formed using the
   'Virtual Root Dominator' method. This isolates loops with multiple entry points.
3. Maximal Regions: Only the largest logical structures are retained
   (no fragments that are already part of a larger region).
4. Isomorphism Check (NetworkX):
   Instead of manual hashing we use `nx.is_isomorphic`.
   A pre-check on node and edge counts is done first for speed.
   https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.isomorphism.is_isomorphic.html#networkx.algorithms.isomorphism.is_isomorphic

Usage:
    python isomorphism_detector.py <path_to_file.dot>
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
            # Pre-checks for speed
            if (comp['structure'].number_of_nodes() == ref['structure'].number_of_nodes() and
                comp['structure'].number_of_edges() == ref['structure'].number_of_edges()):
                
                # Check whether labels also match — this applies to both edges and nodes
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
        print(f"Usage: python {sys.argv[0]} <file.dot>")
        sys.exit(1)

    dot_file = sys.argv[1]
    isomorphic_groups = find_isomorphic_components(dot_file)

    print(f"\n--- Analysis Results ---")
    if not isomorphic_groups:
        print("No isomorphic dominator regions found.")
    
    for i, group in enumerate(isomorphic_groups, 1):
        print(f"\nIsomorfe Groep {i}:")
        for item in group:
            print(f"  - Entry: {item['entry']}")
            print(f"    Nodes: {sorted(list(item['nodes']))}")