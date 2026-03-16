import pydot
import networkx as nx
from networkx.algorithms import isomorphism
from itertools import combinations

"""
ALGORITME BESCHRIJVING: SCC ISOMORPHISM CHECKER
==============================================

Dit script identificeert niet alleen Strongly Connected Components (SCC's), 
maar vergelijkt ze ook onderling om te bepalen of ze "isomorf" zijn. 

Isomorfie in deze context betekent dat twee subgrafen exact dezelfde 
topologische structuur hebben én dat de labels op de verbindingen (edges) 
overeenkomen.

Het proces werkt als volgt:

1. SCC EXTRACTIE & FILTERING
   - Het script zoekt alle SCC's in de graaf.
   - Het negeert 'triviale' SCC's (losse knopen zonder lus naar zichzelf). 
     Alleen clusters van 2 of meer knopen worden meegenomen voor vergelijking.

2. SUBGRAAF CONSTRUCTIE
   - Voor elke interessante SCC wordt een tijdelijke, op zichzelf staande 
     subgraaf gemaakt (`subgraph().copy()`).

3. ISOMORFISME VALIDATIE (VF2 Algoritme)
   - Het script gebruikt het VF2-algoritme (via `DiGraphMatcher`) om paren 
     SCC's te vergelijken.
   - Syntactische check: Is de vorm van de graaf gelijk (aantal knopen en pijlen)?
   - Semantische check: Komt de data op de pijlen (zoals de "label" attribute) 
     exact overeen? We gebruiken hiervoor `categorical_edge_match`.

4. RESULTAAT
   - Het script rapporteert welke groepen knopen structureel identiek zijn, 
     wat helpt bij het opsporen van gedupliceerde logica of herhalende patronen 
     in complexe systemen.
"""

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
