import sys
import networkx as nx
from pathlib import Path

from approaches.equivalence_closure.analyze import run_analysis
from approaches.shared.factorize import apply_factorization, save_dot


def factorize(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """1-pass factorisatie met equivalentiesluiting."""
    G = G.copy()
    results = run_analysis(G)
    return apply_factorization(G, results)


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
    output_dot = output_folder / (Path(input_file).stem + "_EqClosure.dot")
    save_dot(G_factorized, str(output_dot))
    print(f"Opgeslagen: {output_dot}")


if __name__ == "__main__":
    main()