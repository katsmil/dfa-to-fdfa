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


def main():
    if len(sys.argv) < 2:
        print("Gebruik: python main.py <graph.dot>")
        sys.exit(1)

    input_file = sys.argv[1]

    # 1. Inlezen (Gebruik MultiDiGraph voor behoud van alle transities)
    try:
        G_orig = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(input_file))
    except Exception as e:
        print(f"Fout bij inlezen bestand: {e}")
        sys.exit(1)

    # 2. Analyse van substructuren
    results = run_analysis(G_orig)

    if not results:
        print("Geen factorisatie mogelijk.")
    else:
        print(f"Gevonden structuren: {len(results)}")

    # 3. Eerste run: factoriseer de originele graaf
    G_factorized = apply_factorization(G_orig, results, strict_filter=False)

    # 4. Tweede run: zoek gemeenschappelijke patronen binnen de subroutine-blauwdrukken
    sub_nodes = [n for n in G_factorized.nodes() if str(n).startswith('SUB_')]
    if sub_nodes:
        G_sub = nx.MultiDiGraph(G_factorized.subgraph(sub_nodes))
        results2 = run_analysis(G_sub)
        if results2:
            results2 = _recompute_frontiers(results2, G_factorized)
            print(f"  Tweede run: {len(results2)} gemeenschappelijke structuur(en) gevonden in subroutines")
            G_factorized = apply_factorization(G_factorized, results2, strict_filter=False,
                                               check_dispatch_signatures=False)
        else:
            print("  Tweede run: geen gemeenschappelijke structuren gevonden in subroutines")

    # 5. Resultaat opslaan
    output_folder = Path("output")
    output_folder.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_file)
    output_dot = output_folder / (input_path.stem + "_NoEqClosure_Nested.dot")
    save_dot(G_factorized, str(output_dot))

if __name__ == "__main__":
    main()