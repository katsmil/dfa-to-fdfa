import networkx as nx

def read_dot(path):
    """Reads a DOT file and converts it to a NetworkX DiGraph."""
    g = nx.drawing.nx_pydot.read_dot(path)
    G = nx.DiGraph()

    for u, v, data in g.edges(data=True):
        label = data.get("label", "")
        if isinstance(label, str):
            label = label.strip('"')
        G.add_edge(u, v, label=label)

    return G