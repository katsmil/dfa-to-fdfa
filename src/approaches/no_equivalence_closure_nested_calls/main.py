import sys
import networkx as nx
from pathlib import Path

from approaches.no_equivalence_closure.analyze import run_analysis
from approaches.shared.factorize import apply_factorization, save_dot


def factorize(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    2-pass factorization (nested calls):
      Pass 1 — factorize the full original graph.
      Pass 2 — find common patterns within the generated SUB_* blueprints
               and factorize those as well.
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
