import networkx as nx

def get_natural_loops(G, root):
    """
    Vindt alle natural loops in de graaf gebaseerd op back edges.
    Een back edge (n, d) bestaat als d de node n domineert.
    """
    # 1. Bereken alle dominators (niet alleen immediate)
    # nx.immediate_dominators geeft een boom, we maken er een set per node van
    idoms = nx.immediate_dominators(G, root)
    
    def get_all_dominators(node):
        doms = {node}
        curr = node
        while curr in idoms and idoms[curr] != curr:
            curr = idoms[curr]
            doms.add(curr)
        return doms

    all_doms = {n: get_all_dominators(n) for n in G.nodes()}

    loops = []

    # 2. Zoek naar back edges: (u, v) waarbij v u domineert
    for u, v in G.edges():
        if v in all_doms[u]:
            # We hebben een back edge gevonden! v is de header, u is de tail.
            
            # 3. Reconstructie van de loop body:
            # Alle knopen die u kunnen bereiken zonder via v te gaan.
            loop_nodes = {v, u}
            stack = [u]
            while stack:
                curr = stack.pop()
                for pred in G.predecessors(curr):
                    if pred not in loop_nodes:
                        loop_nodes.add(pred)
                        stack.append(pred)
            
            loops.append({
                'header': v,
                'nodes': loop_nodes
            })
            
    return loops