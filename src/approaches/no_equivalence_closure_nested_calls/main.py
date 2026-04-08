import sys
import networkx as nx
from pathlib import Path

from approaches.no_equivalence_closure.analyze import run_analysis
from approaches.shared.factorize import apply_factorization, save_dot


def factorize(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Fixed-point factorization (nested calls):
      Pass 1 — factorize the full original graph.
      Pass 2+ — repeatedly run analysis only on the subgraph restricted to
                SUB_* nodes (only the created subcomponents), until no
                additional changes are produced.
    """
    G = G.copy()

    def _node_snapshot(graph: nx.MultiDiGraph) -> set:
        return set(graph.nodes())

    # Pass 1 (full graph)
    results = run_analysis(G)
    before = _node_snapshot(G)
    if results:
        G = apply_factorization(G, results)

    # Pass 2+ (SUB_* only) until fixed point
    while True:
        sub_nodes = [n for n in G.nodes() if str(n).startswith('SUB_')]
        # 1) No SUB_* nodes => nothing to analyze for nested compression.
        if not sub_nodes:
            break
        G_sub = nx.MultiDiGraph(G.subgraph(sub_nodes))
        results_new = run_analysis(G_sub)
        # 2) Analysis found no valid repeating structures => fixed point reached.
        if not results_new:
            break
        before = _node_snapshot(G)
        G_next = apply_factorization(G, results_new)
        # 3) Factorization produced no graph change (e.g. all candidates invalid,
        #    intra_conflict, or <2 valid occurrences) => fixed point reached.
        if _node_snapshot(G_next) == before:
            break
        G = G_next

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
