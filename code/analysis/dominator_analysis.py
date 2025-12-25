import networkx as nx
from collections import defaultdict

"""
MODULE: Dominator Analysis Toolkit
==================================

Deze module bevat de kernlogica voor het extraheren van hiërarchische structuren
binnen Strongly Connected Components (SCC's).

De Virtual Root Strategie:
--------------------------
In complexe automaten kunnen lussen meerdere ingangen hebben of onderling verbonden 
zijn via cross-edges.

Door een __VIRTUAL_ROOT__ per SCC te introduceren:
1. Isoleren we de SCC van de rest van de graaf.
2. Worden alle 'Entry Points' (knopen die van buiten de SCC bereikbaar zijn) 
   als directe kinderen van de Virtual Root behandeld.
3. Worden parallelle structuren binnen een SCC als 'siblings' (broers/zussen) 
   gezien in de dominator-boom, in plaats van een geforceerde hiërarchie.
"""

def get_scc_dominators(G, scc_nodes):
    """Creëert een virtuele root boven alle ingangen van de SCC."""
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
    """Berekent alle maximale dominator-regio's binnen een SCC."""
    idom, v_root = get_scc_dominators(G, scc_nodes)
    
    # Bouw dominator sets
    dom_map = defaultdict(set)
    for n in scc_nodes:
        curr = n
        while curr in idom:
            if curr != v_root:
                dom_map[n].add(curr)
            if curr == idom[curr] or idom[curr] == v_root:
                break
            curr = idom[curr]

    # Vorm initiële regio's
    candidates = {}
    for d in scc_nodes:
        region = {n for n in scc_nodes if d in dom_map[n]}
        if len(region) > 1:
            candidates[d] = region

    # Filter op maximaliteit
    sorted_candidates = sorted(candidates.items(), key=lambda x: len(x[1]), reverse=True)
    final_regions = {}
    for head, region in sorted_candidates:
        if not any(region.issubset(ext) and region != ext for ext in final_regions.values()):
            final_regions[head] = region
            
    return final_regions