import pydot
import networkx as nx
from networkx.algorithms import isomorphism
from itertools import combinations


def load_graph(dot_file: str) -> nx.DiGraph:
    graphs = pydot.graph_from_dot_file(dot_file)
    if not graphs:
        raise ValueError("Geen graph gevonden in DOT file")

    return nx.DiGraph(nx.nx_pydot.from_pydot(graphs[0]))


def compute_scc_subgraphs(G: nx.DiGraph):
    """
    Geeft een lijst van (scc_nodes, scc_subgraph)
    """
    sccs = list(nx.strongly_connected_components(G))
    result = []

    for nodes in sccs:
        if len(nodes) > 1:  # enkel interessante SCC's, hier wordt denk ik bedoeld non-trivial scc
            sub = G.subgraph(nodes).copy()
            result.append((nodes, sub))

    return result


def sccs_are_isomorphic(G1: nx.DiGraph, G2: nx.DiGraph) -> bool:
    """
    Controleert structurele + gedragsisomorfie
    (edge labels moeten overeenkomen)
    """

    edge_match = isomorphism.categorical_edge_match("label", None)

    matcher = isomorphism.DiGraphMatcher(
        G1,
        G2,
        edge_match=edge_match
    )

    return matcher.is_isomorphic()


def main():
    G = load_graph("Input/example2.dot")

    sccs = compute_scc_subgraphs(G)

    print(f"Gevonden {len(sccs)} niet-triviale SCC's\n")

    for idx, (nodes, _) in enumerate(sccs, start=1):
        print(f"SCC {idx}: {sorted(nodes)}")
    print()

    print("Isomorphic-checks:\n")

    for (i, (nodes1, sg1)), (j, (nodes2, sg2)) in combinations(enumerate(sccs, 1), 2):
        iso = sccs_are_isomorphic(sg1, sg2)

        print(f"SCC {i} ↔ SCC {j}: {'ISOMORF' if iso else 'niet isomorf'}")

        if iso:
            print(f"  {sorted(nodes1)} ≅ {sorted(nodes2)}")

    print("\nKlaar.")


if __name__ == "__main__":
    main()

# GraphMatcher/DiGraphMatcher
# 
# The GraphMatcher and DiGraphMatcher are responsible for matching graphs or directed graphs in a predetermined manner.
# This usually means a check for an isomorphism, though other checks are also possible. 
# For example, a subgraph of one graph can be checked for isomorphism to a second graph.

# Matching is done via syntactic feasibility. 
# It is also possible to check for semantic feasibility. 
# Feasibility, then, is defined as the logical AND of the two functions.

# To include a semantic check, the (Di)GraphMatcher class should be subclassed, and the semantic_feasibility function should be redefined. 
# By default, the semantic feasibility function always returns True.
# The effect of this is that semantics are not considered in the matching of G1 and G2.
