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


# ============================================================
# Dominator-regio extractie
# ============================================================

def dominator_regions(G, start, scc):
    idom = nx.immediate_dominators(G, start)

    # volledige dominatorsets afleiden uit idom
    dom = {}
    for n in scc:
        dom[n] = set()
        cur = n
        while cur in idom:
            dom[n].add(cur)
            if cur == idom[cur]:
                break
            cur = idom[cur]

    regions = {}
    for d in scc:
        region = {n for n in scc if d in dom[n]}
        if len(region) > 1:
            regions[d] = region

    return regions


# ============================================================
# Hoofdalgoritme
# ============================================================

def find_isomorphic_components(dot_file, start):
    G = read_dot(dot_file)

    components = []

    for scc in nx.strongly_connected_components(G):
        if len(scc) < 2:
            continue
        if start not in G:
            continue

        regions = dominator_regions(G, start, scc)

        for entry, nodes in regions.items():
            H = G.subgraph(nodes)
            h = canonical_hash(H, nodes)
            components.append((entry, nodes, h))

    groups = defaultdict(list)
    for entry, nodes, h in components:
        groups[h].append((entry, nodes))

    return [g for g in groups.values() if len(g) > 1]


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Gebruik: python dominator.py <file.dot> <startnode>")
        sys.exit(1)

    dot_file = sys.argv[1]
    start = sys.argv[2]

    groups = find_isomorphic_components(dot_file, start)

    for i, group in enumerate(groups, 1):
        print(f"\nIsomorfe groep {i}:")
        for entry, nodes in group:
            print(f"  entry = {entry}, nodes = {sorted(nodes)}")
