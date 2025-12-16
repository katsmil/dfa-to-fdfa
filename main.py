import pydot, networkx as nx

graphs = pydot.graph_from_dot_file("/Input/example.dot")
pydot_graph = graphs[0]
G = nx.DiGraph(nx.nx_pydot.from_pydot(pydot_graph))

scc = list(nx.strongly_connected_components(G))
print(scc)
