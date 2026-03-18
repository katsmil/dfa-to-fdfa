import sys
import networkx as nx
from pathlib import Path
from analyze import run_analysis
from approaches.shared.factorize import apply_factorization, save_dot
# from factorize import apply_factorization, save_dot

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
    
    # 3. Toepassen van factorisatie
    G_factorized = apply_factorization(G_orig, results, strict_filter=False)
    
    # 4. Resultaat opslaan
    output_folder = Path("output")
    output_folder.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_file)
    output_dot = output_folder / (input_path.stem + "_COMBINED.dot")
    save_dot(G_factorized, str(output_dot))

if __name__ == "__main__":
    main()