import sys
import argparse
from pathlib import Path
from bisimilar.bisimilar_sign_HK_optimalization import analyze_graph_factorization

def run_bisimilar_sign_hk(input_file: str):
    print(f"Running Bisimilar Sign + HK Optimalization met input: {input_file}")
    print(f"--- Analyse van DFA factorisatie met HK-optimalisatie (e(R)) ---")
    print(f"Bestand: {input_file}\n")
    
    results = analyze_graph_factorization(input_file)
    
    if not results:
        print("Geen factoriseerbare overlap gevonden.")
    else:
        print(f"Totaal aantal unieke structuren gevonden: {len(results)}\n")
        
        for i, r in enumerate(results, 1):
            n1, n2 = r['start_nodes']
            print(f"Structuur {i}:")
            print(f"  Start-equivalentie: {n1} <-> {n2}")
            print(f"  Grootte van geaccepteerde overlap: {r['overlap_size']} paren")
            print("  Gevonden paren in deze klasse:")
            
            sorted_pairs = sorted(list(r['matched_pairs']), key=lambda x: str(x[0]))
            for pair in sorted_pairs:
                print(f"    - {pair[0]} matches met {pair[1]}")
            print("-" * 40)


def main():
    parser = argparse.ArgumentParser(
        description="Hoofdprogramma voor bisimilar algoritmes"
    )
    
    parser.add_argument(
        "mode",
        choices=["bisimilar-hk", "andere-mode", "list"],
        help="Welk algoritme/mode wil je uitvoeren?"
    )
    
    parser.add_argument(
        "input_file",
        nargs="?",  # Optioneel voor 'list' mode
        help="Input bestand pad"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # Controleer of input file bestaat (behalve voor list mode)
    if args.mode != "list":
        if not args.input_file:
            parser.error(f"mode '{args.mode}' vereist een input_file")
        
        input_path = Path(args.input_file)
        if not input_path.exists():
            print(f"Error: Input file '{args.input_file}' niet gevonden!")
            sys.exit(1)
    
    if args.mode == "bisimilar-hk":
        run_bisimilar_sign_hk(args.input_file)
    
    # elif args.mode == "andere-mode":
    #     run_andere_module(args.input_file)
    
    elif args.mode == "list":
        print("Beschikbare modes:")
        print("  - bisimilar-hk: Bisimilar Sign + HK Optimalization")
        print("  - andere-mode: Beschrijving van andere mode")
    
    print("\nKlaar!")


if __name__ == "__main__":
    main()