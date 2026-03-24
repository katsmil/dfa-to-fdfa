"""
ALGORITHM: Natural Loop Isomorphism Detector
============================================

This script finds isomorphic structures by identifying Natural Loops.
A Natural Loop of a back-edge (m→n),
where n dominates m,
is the set of nodes x such that n dominates x
and a path exists from x to m that does not pass through n.


Core steps:
1. SCC Isolation: Analysis per strongly connected component.
2. Virtual Root: For local dominator computation within the SCC.
3. Back-Edge Detection: Looks for transitions returning to a dominator.
4. Loop Body Reconstruction: Finds all nodes that are part of that specific loop.
5. Isomorphism Grouping: Compares found loops via NetworkX (topology + labels).
"""

import networkx as nx
from collections import defaultdict
from utils.graph_utils import read_dot

def get_all_dominators(idoms):
    """Convert immediate dominators to a full set per node."""
    all_doms = defaultdict(set)
    for node in idoms:
        curr = node
        while curr in idoms:
            all_doms[node].add(curr)
            parent = idoms[curr]
            
            # Stop condition: we are at a root (node dominates itself)
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

        # Create a local copy for dominator analysis
        S = G.subgraph(scc).copy()
        
        # Find entries
        entries = {n for n in scc if any(p not in scc for p in G.predecessors(n))}
        if not entries: entries = {min(scc)}
        
        # Place Virtual Root (acts as aggregate)
        v_root = "__VIRTUAL_ROOT__"
        S.add_node(v_root)
        for e in entries: S.add_edge(v_root, e)

        # 2. Dominator berekening
        idoms = nx.immediate_dominators(S, v_root)
        all_doms = get_all_dominators(idoms)

        # 3. Search for Back-Edges and identify Natural Loops
        for tail, header in S.edges():
            # Skip the virtual root
            if header == v_root: 
                continue
            
            # A back-edge exists if the 'header' dominates the 'tail'
            if header in all_doms[tail]:
                # Found a back-edge!
                # Reconstruct the loop body: all nodes that can reach
                # the tail without passing through the header.
                loop_nodes = {header, tail}
                stack = [tail]
                
                while stack:
                    curr = stack.pop()
                    for pred in S.predecessors(curr):
                        # Stop at the header and the virtual root
                        if pred not in loop_nodes and pred != v_root:
                            loop_nodes.add(pred)
                            stack.append(pred)
                
                # Store the loop for isomorphism check
                all_found_loops.append({
                    'header': header,
                    'nodes': loop_nodes,
                    'structure': G.subgraph(loop_nodes).copy()
                })

    # 4. Isomorphism Grouping via NetworkX
    groups = []
    # Filter first for unique node sets to avoid duplicate loops (with multiple back-edges)
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
                
                # Check whether labels also match, both on edges and on nodes
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

    print(f"\n--- Analysis Results: {dot_file} ---")
    if not isomorphic_groups:
        print("No isomorphic loops found.")
    
    for i, group in enumerate(isomorphic_groups, 1):
        print(f"\nIsomorfe Groep {i} (Aantal: {len(group)}):")
        for item in group:
            print(f"  - Header Node: {item['header']}")
            print(f"    Body Nodes:  {sorted(list(item['nodes']))}")