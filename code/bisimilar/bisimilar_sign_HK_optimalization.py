from collections import defaultdict
import networkx as nx

class EquivalenceClosure:
    """
    Implementatie van de reflexieve, symmetrische en transitieve afsluiting e(R).
    Gebruikt de Union-Find datastructuur voor optimale performance.
    """
    def __init__(self, elements):
        # Reflexiviteit: elk element e is initieel equivalent aan zichzelf (e ~ e)
        self.parent = {e: e for e in elements}

    def _find_representative(self, x):
        """Zoekt de 'leider' van de equivalentieklasse."""
        if self.parent[x] != x:
            self.parent[x] = self._find_representative(self.parent[x]) 
        return self.parent[x]

    def add_equivalence(self, x, y):
        """Voegt het paar (x, y) toe aan de relatie R en update de afsluiting e(R)."""
        rootX = self._find_representative(x)
        rootY = self._find_representative(y)
        if rootX != rootY:
            self.parent[rootX] = rootY
            return True 
        return False 

    def is_equivalent(self, x, y):
        """Checkt of (x, y) ∈ e(R) (behoren ze tot dezelfde klasse?)."""
        return self._find_representative(x) == self._find_representative(y)

# -----------------------------------------------------------

def is_accepting(G, node):
    node_data = G.nodes[node]
    return node_data.get('shape') == 'doublecircle' or node_data.get('accepting') == 'true'

def find_maximal_bisimilar_overlap(G, start_a, start_b, closure_eR):
    """
    Vindt de overlap en gebruikt de EquivalenceClosure om takken af te snijden 
    die via de HK-inductie al bewezen equivalent zijn.
    """
    stack = [(start_a, start_b)]
    equivalent_pairs = set()
    visited = set()
    
    if closure_eR.is_equivalent(start_a, start_b):
        return {(start_a, start_b)}

    while stack:
        n1, n2 = stack.pop()
        
        if (n1, n2) in visited:
            continue
        visited.add((n1, n2))

        # --- HK OPTIMALISATIE: e(R) check ---
        if closure_eR.is_equivalent(n1, n2):
            equivalent_pairs.add((n1, n2))
            continue 
        # ------------------------------------

        if is_accepting(G, n1) != is_accepting(G, n2):
            continue 
        
        edges1 = {d['label']: v for _, v, d in G.out_edges(n1, data=True) if 'label' in d}
        edges2 = {d['label']: v for _, v, d in G.out_edges(n2, data=True) if 'label' in d}
        
        if set(edges1.keys()) != set(edges2.keys()):
            continue
        
        # Lokale match gevonden: voeg toe aan R en update de afsluiting e(R)
        equivalent_pairs.add((n1, n2))
        closure_eR.add_equivalence(n1, n2)

        for char in edges1.keys():
            next1, next2 = edges1[char], edges2[char]
            if (next1, next2) not in visited:
                stack.append((next1, next2))
    
    return equivalent_pairs

def filter_redundant_results(results):
    sorted_results = sorted(results, key=lambda x: x['overlap_size'], reverse=True)
    kept_results = []
    
    for current in sorted_results:
        current_pairs = current['matched_pairs']
        is_subset = False
        for kept in kept_results:
            if current_pairs.issubset(kept['matched_pairs']):
                is_subset = True
                break
        if not is_subset:
            kept_results.append(current)
    return kept_results

def analyze_graph_factorization(dot_file):
    G_raw = nx.drawing.nx_pydot.read_dot(dot_file)
    G = nx.DiGraph(G_raw) 
    nodes = list(G.nodes())
    results = []
    signatures = defaultdict(list)

    # Stap 1: Signature Hashing
    for n in nodes:
        out_labels = [data['label'] for _, v, data in G.out_edges(n, data=True) if 'label' in data]
        if out_labels:
            sig = tuple(sorted(out_labels))
            signatures[sig].append(n)

    # Initialiseer de Equivalence Closure e(R)
    closure_eR = EquivalenceClosure(nodes)
    compared_pairs = set()

    # Stap 2: Pairwise Comparison
    for sig, candidate_nodes in signatures.items():
        for i in range(len(candidate_nodes)):
            for j in range(i + 1, len(candidate_nodes)):
                n1, n2 = candidate_nodes[i], candidate_nodes[j]
                
                # Top-level HK pruning
                if closure_eR.is_equivalent(n1, n2):
                    continue
                
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared_pairs:
                    continue
                compared_pairs.add(pair_id)

                overlap = find_maximal_bisimilar_overlap(G, n1, n2, closure_eR)
                
                if len(overlap) >= 2: 
                    results.append({
                        'start_nodes': (n1, n2),
                        'overlap_size': len(overlap),
                        'matched_pairs': overlap
                    })

    return filter_redundant_results(results)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Gebruik: python script.py <graph.dot>")
        sys.exit(1)

    dot_file = sys.argv[1]
    print(f"--- Analyse van DFA factorisatie met HK-optimalisatie (e(R)) ---")
    print(f"Bestand: {dot_file}\n")
    
    results = analyze_graph_factorization(dot_file)

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