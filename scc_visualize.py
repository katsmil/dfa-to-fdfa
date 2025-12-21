import itertools
import sys
from pathlib import Path

import pydot
import networkx as nx

"""
ALGORITME BESCHRIJVING: SCC VISUALIZER & COLORIZER
==================================================

Dit script analyseert een gerichte graaf (DOT-formaat) en identificeert de 
'Strongly Connected Components' (SCC's). Een SCC is een deel van de graaf 
waarin elke knoop bereikbaar is vanaf elke andere knoop binnen diezelfde 
component (een cyclus of een groep overlappende cycli).

Het proces verloopt in 3 stappen:

1. SCC ANALYSE (Tarjan of Kosaraju algoritme via NetworkX)
   - Het script zoekt naar groepen knopen die samen gesloten lussen vormen.
   - Knopen die geen deel uitmaken van een cyclus worden elk als een 
     afzonderlijke SCC (van 1 knoop) beschouwd.

2. KLEURCODERING
   - Elke unieke SCC krijgt een eigen kleur toegewezen uit een kleurenpalet.
   - Dit helpt de gebruiker om in één oogopslag te zien welke knopen 
     onderling verbonden zijn en waar de "logische blokken" in de flow zitten.

3. VISUALISATIE EXPORT
   - Het script genereert een nieuw .dot-bestand in de map 'Output/'.
   - De oorspronkelijke structuur en labels blijven behouden, maar de knopen 
     worden ingekleurd op basis van hun SCC-lidmaatschap.
   - Er wordt een instructie geprint om de DOT-file om te zetten naar een 
     afbeelding (PNG) via Graphviz.
"""

def load_graph(dot_file: str) -> nx.DiGraph:
    graphs = pydot.graph_from_dot_file(dot_file)
    if not graphs:
        raise ValueError("Geen graph gevonden in DOT file")

    pydot_graph = graphs[0]
    return nx.DiGraph(nx.nx_pydot.from_pydot(pydot_graph))


def compute_sccs(G: nx.DiGraph):
    return list(nx.strongly_connected_components(G))


def visualize_sccs(G: nx.DiGraph, sccs, output_dot: Path):
    colors = itertools.cycle([
        "lightblue",
        "lightgreen",
        "lightyellow",
        "orange",
        "pink",
        "violet",
        "lightsalmon",
        "lightgray",
    ])

    node_to_color = {}

    for comp in sccs:
        color = next(colors)
        for node in comp:
            node_to_color[node] = color

    dot = pydot.Dot(
        graph_type="digraph",
        rankdir="LR"
    )

    # Nodes
    for node in G.nodes():
        dot.add_node(
            pydot.Node(
                node,
                style="filled",
                fillcolor=node_to_color.get(node, "white"),
                label=node,
            )
        )

    # Edges
    # for src, dst in G.edges():
    #     dot.add_edge(pydot.Edge(src, dst))

    for src, dst, data in G.edges(data=True):
        label = data.get("label")

        edge_kwargs = {}
        if label:
            edge_kwargs["label"] = label

        dot.add_edge(pydot.Edge(src, dst, **edge_kwargs))


    dot.write(str(output_dot))


def print_sccs(sccs):
    print(f"Gevonden SCC's: {len(sccs)}\n")
    for i, comp in enumerate(sccs, start=1):
        print(f"SCC {i} ({len(comp)} nodes):")
        for node in sorted(comp):
            print(f"  - {node}")
        print()


def main():
    if len(sys.argv) < 2:
        print("Gebruik: python scc_visualize.py <input.dot>")
        sys.exit(1)

    input_dot = sys.argv[1]
    input_path = Path(input_dot)

    # Zorg ervoor dat de Output folder bestaat
    output_folder = Path("Output")
    output_folder.mkdir(parents=True, exist_ok=True)

    # Genereer output bestandsnaam op basis van input
    output_dot = output_folder / (input_path.stem + "_colored.dot")

    print(f"Inlezen van: {input_dot}")
    G = load_graph(input_dot)

    print(f"Nodes: {G.number_of_nodes()}, edges: {G.number_of_edges()}")

    sccs = compute_sccs(G)
    print_sccs(sccs)

    visualize_sccs(G, sccs, output_dot)

    print(f"SCC-visualisatie geschreven naar: {output_dot}")
    print("Render met:")
    print(f"  dot -Tpng {output_dot} -o {output_folder / 'scc_colored.png'}")


if __name__ == "__main__":
    main()
