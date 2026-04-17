import sys
import networkx as nx
from pathlib import Path

from approaches.no_equivalence_closure.analyze import run_analysis
from approaches.shared.factorize import apply_factorization, save_dot


def factorize(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    2-pass factorization (nested calls):
      Pass 1 — factorize the full original graph.
      Pass 2 — run analysis only on the subgraph restricted to SUB_* nodes
               (only the created subcomponents).
    """
    G = G.copy()

    # Pass 1
    results = run_analysis(G)
    G = apply_factorization(G, results)

    # Pass 2 — nested factorisation should stay within the same outer subroutine
    # cluster. Factoring all SUB_* nodes globally can merge repeated patterns from
    # different call contexts and break acceptance semantics for nested calls.
    sub_nodes_by_cluster = {}
    for n, data in G.nodes(data=True):
        if str(n).startswith('SUB_'):
            cluster = data.get('cluster')
            sub_nodes_by_cluster.setdefault(cluster, []).append(n)

    for cluster, sub_nodes in sub_nodes_by_cluster.items():
        # A cluster must contain at least two SUB instances to be worth
        # analyzing for repeated patterns. Single-node clusters cannot compress.
        if len(sub_nodes) < 2:
            continue
        G_sub = nx.MultiDiGraph(G.subgraph(sub_nodes))
        results2 = run_analysis(G_sub)
        if results2:
            G = apply_factorization(G, results2)

    return G


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <graph.dot>")
        sys.exit(1)

    input_file = sys.argv[1]

    try:
        G_orig = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(input_file))
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    G_factorized = factorize(G_orig)

    output_folder = Path("output")
    output_folder.mkdir(parents=True, exist_ok=True)
    output_dot = output_folder / (Path(input_file).stem + "_NESTED.dot")
    save_dot(G_factorized, str(output_dot))
    print(f"Saved: {output_dot}")


if __name__ == "__main__":
    main()
