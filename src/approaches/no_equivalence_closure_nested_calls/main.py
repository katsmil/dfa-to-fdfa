import sys
import networkx as nx
from pathlib import Path

from approaches.no_equivalence_closure.analyze import run_analysis
from approaches.shared.factorize import apply_factorization, save_dot
from approaches.shared.shared_types import MatchLocation, CanonicalSubstructure


def _recompute_frontiers(results, G_full):
    """
    Herbereken internals/frontiers voor elke MatchLocation op basis van de volledige graaf.

    run_analysis draait op G_sub (alleen SUB_* nodes). Daarin ontbreken twee soorten
    'externe' edges:
      1. Edges naar hoofdautomaat-nodes (suffix-geval: SUB_x_last heeft geen blueprint-edges)
      2. Edges naar andere SUB_* nodes buiten de match (midden-geval: SUB_x_mid → SUB_x_next)

    Voor geval 1: geen externe edges → frontier leeg → dispatch_map leeg →
                  executor handelt het af via transparant doorborrelen.
    Voor geval 2: externe edge aanwezig in G_full → frontier correct gedetecteerd →
                  _process_exits vult dispatch_map met de juiste interne vervolgnode.
    """
    patched = []
    for sub in results:
        patched_locs = []
        for loc in sub.locations:
            nodes_set = set(loc.all_nodes)
            internals, frontiers = [], []
            for n in loc.all_nodes:
                has_external = any(
                    t not in nodes_set
                    for _, t, _ in G_full.out_edges(n, data=True)
                )
                (frontiers if has_external else internals).append(n)
            patched_locs.append(MatchLocation(
                start_node=loc.start_node,
                all_nodes=loc.all_nodes,
                internals=tuple(internals),
                frontiers=tuple(frontiers),
            ))
        patched.append(CanonicalSubstructure(
            canonical_nodes=sub.canonical_nodes,
            overlap_size=sub.overlap_size,
            locations=tuple(patched_locs),
            blueprint_edges=sub.blueprint_edges,
        ))
    return patched


def factorize(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    2-pass factorisatie (nested calls):
      Pass 1 — factoriseer de volledige originele graaf.
      Pass 2 — zoek gemeenschappelijke patronen binnen de gegenereerde SUB_*-blauwdrukken
               en factoriseer die ook.
    """
    G = G.copy()

    # Pass 1
    results = run_analysis(G)
    G = apply_factorization(G, results)

    # Pass 2
    sub_nodes = [n for n in G.nodes() if str(n).startswith('SUB_')]
    if sub_nodes:
        G_sub = nx.MultiDiGraph(G.subgraph(sub_nodes))
        results2 = run_analysis(G_sub)
        if results2:
            results2 = _recompute_frontiers(results2, G)
            G = apply_factorization(G, results2)

    return G


def main():
    if len(sys.argv) < 2:
        print("Gebruik: python main.py <graph.dot>")
        sys.exit(1)

    input_file = sys.argv[1]

    try:
        G_orig = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(input_file))
    except Exception as e:
        print(f"Fout bij inlezen bestand: {e}")
        sys.exit(1)

    G_factorized = factorize(G_orig)

    output_folder = Path("output")
    output_folder.mkdir(parents=True, exist_ok=True)
    output_dot = output_folder / (Path(input_file).stem + "_NESTED.dot")
    save_dot(G_factorized, str(output_dot))
    print(f"Opgeslagen: {output_dot}")


if __name__ == "__main__":
    main()
