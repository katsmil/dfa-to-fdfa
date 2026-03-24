import networkx as nx
from collections import defaultdict

"""
MODULE: Dominator Analysis Toolkit
==================================

This module contains the core logic for extracting hierarchical structures
within Strongly Connected Components (SCCs).

The Virtual Root Strategy:
--------------------------
In complex automata, loops can have multiple entry points or be interconnected
via cross-edges.

By introducing a __VIRTUAL_ROOT__ per SCC:
1. We isolate the SCC from the rest of the graph.
2. All 'Entry Points' (nodes reachable from outside the SCC) are treated
   as direct children of the Virtual Root.
3. Parallel structures within an SCC are seen as siblings in the dominator
   tree, instead of forcing a hierarchy.
"""

def get_scc_dominators(G, scc_nodes):
    """Creates a virtual root above all entry nodes of the SCC."""
    S = G.subgraph(scc_nodes).copy()
    
    entries = {node for node in scc_nodes 
               if any(pred not in scc_nodes for pred in G.predecessors(node))}
    
    if not entries:
        entries = {min(scc_nodes)}

    v_root = "__VIRTUAL_ROOT__"
    S.add_node(v_root)
    for entry in entries:
        S.add_edge(v_root, entry)

    return nx.immediate_dominators(S, v_root), v_root

def get_maximal_regions(G, scc_nodes):
    """Computes all maximal dominator regions within an SCC."""
    idom, v_root = get_scc_dominators(G, scc_nodes)
    
    # Build dominator sets
    dom_map = defaultdict(set)
    for n in scc_nodes:
        curr = n
        while curr in idom:
            if curr != v_root:
                dom_map[n].add(curr)
            if curr == idom[curr] or idom[curr] == v_root:
                break
            curr = idom[curr]

    # Form initial regions
    candidates = {}
    for d in scc_nodes:
        region = {n for n in scc_nodes if d in dom_map[n]}
        if len(region) > 1:
            candidates[d] = region

    # Filter for maximality
    sorted_candidates = sorted(candidates.items(), key=lambda x: len(x[1]), reverse=True)
    final_regions = {}
    for head, region in sorted_candidates:
        if not any(region.issubset(ext) and region != ext for ext in final_regions.values()):
            final_regions[head] = region
            
    return final_regions