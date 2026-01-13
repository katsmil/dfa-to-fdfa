from collections import defaultdict
import networkx as nx

class EquivalenceClosure:
    def __init__(self, elements):
        self.parent = {e: e for e in elements}

    def _find_representative(self, x):
        if self.parent[x] != x:
            self.parent[x] = self._find_representative(self.parent[x]) 
        return self.parent[x]

    def add_equivalence(self, x, y):
        rootX = self._find_representative(x)
        rootY = self._find_representative(y)
        if rootX != rootY:
            self.parent[rootX] = rootY
            return True 
        return False 

    def is_equivalent(self, x, y):
        return self._find_representative(x) == self._find_representative(y)

def filter_redundant_results(results):
    # Sorteer op overlap_size (grootste eerst)
    sorted_results = sorted(results, key=lambda x: x['overlap_size'], reverse=True)
    kept_results = []
    
    for current in sorted_results:
        # We vergelijken de volledige set van paren (internals + frontiers)
        current_pairs = current['all_pairs']
        is_subset = False
        
        for kept in kept_results:
            # Als alle paren in de huidige set al voorkomen in een grotere set,
            # dan is resultaat redundant.
            if current_pairs.issubset(kept['all_pairs']):
                is_subset = True
                break
        
        if not is_subset:
            kept_results.append(current)
            
    return kept_results

def is_accepting(G, node):
    node_data = G.nodes[node]
    return node_data.get('shape') == 'doublecircle' or node_data.get('accepting') == 'true'

def find_maximal_bisimilar_overlap(G, start_a, start_b, closure_eR):
    stack = [(start_a, start_b)]
    
    # We houden bij welke paren 'strikt' bisimilair zijn (de interne structuur)
    visited_strict = set()
    
    # We houden alle paren bij die bereikt worden (inclusief de randen)
    all_reached_pairs = set()

    # Validatie van de start
    if is_accepting(G, start_a) != is_accepting(G, start_b):
        return None
    
    edges_start_a = {d['label'] for _, _, d in G.out_edges(start_a, data=True) if 'label' in d}
    edges_start_b = {d['label'] for _, _, d in G.out_edges(start_b, data=True) if 'label' in d}
    
    # Als de start al verschilt, is er helemaal geen overlap
    if edges_start_a != edges_start_b:
        return None

    all_reached_pairs.add((start_a, start_b))

    while stack:
        n1, n2 = stack.pop()

        if (n1, n2) in visited_strict:
            continue
        
        edges1 = {d['label']: v for _, v, d in G.out_edges(n1, data=True) if 'label' in d}
        edges2 = {d['label']: v for _, v, d in G.out_edges(n2, data=True) if 'label' in d}

        is_strict_match = (
            is_accepting(G, n1) == is_accepting(G, n2) and 
            set(edges1.keys()) == set(edges2.keys())
        )

        if is_strict_match:
            visited_strict.add((n1, n2))
            closure_eR.add_equivalence(n1, n2)
            
            for label in edges1.keys():
                next1 = edges1[label]
                next2 = edges2[label]
                next_pair = (next1, next2)

                all_reached_pairs.add(next_pair)
                
                # We pushen hem op de stack om te zien of hij ook strikt is.
                if next_pair not in visited_strict:
                    stack.append(next_pair)
        
        # Als is_strict_match False is, dan is dit paar een 'Frontier'.
        # We doen niets (niet op stack, niet in closure), maar hij zit wel in all_reached_pairs.

    # Nu kunnen we de frontiers afleiden door het verschil te nemen
    frontier_pairs = all_reached_pairs - visited_strict
    
    return {
        'internal_pairs': visited_strict,
        'frontier_pairs': frontier_pairs,
        'all_pairs': all_reached_pairs
    }

def analyze_graph_factorization(dot_file):
    G_raw = nx.drawing.nx_pydot.read_dot(dot_file)
    G = nx.DiGraph(G_raw) 
    nodes = list(G.nodes())
    results = []
    signatures = defaultdict(list)

    for n in nodes:
        out_labels = [data['label'] for _, v, data in G.out_edges(n, data=True) if 'label' in data]
        if out_labels:
            sig = tuple(sorted(out_labels))
            signatures[sig].append(n)

    closure_eR = EquivalenceClosure(nodes)
    compared_pairs = set()

    for sig, candidate_nodes in signatures.items():
        for i in range(len(candidate_nodes)):
            for j in range(i + 1, len(candidate_nodes)):
                n1, n2 = candidate_nodes[i], candidate_nodes[j]
                if closure_eR.is_equivalent(n1, n2): continue
                
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared_pairs: continue
                compared_pairs.add(pair_id)

                result = find_maximal_bisimilar_overlap(G, n1, n2, closure_eR)
                
                # Check of er resultaat is en of de overlap groot genoeg is, 
                # bij een te kleine overlap loont de factorisatie niet
                if result and len(result['all_pairs']) > 2: 
                    
                    results.append({
                        'start_nodes': (n1, n2),
                        'overlap_size': len(result['all_pairs']),
                        'internals': result['internal_pairs'],
                        'frontiers': result['frontier_pairs'], # DEZE zijn belangrijk voor de stack logica
                        'all_pairs': result['all_pairs']
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
            print(f"Structuur {i}:")
            print(f"  Start: {r['start_nodes'][0]} <-> {r['start_nodes'][1]}")
            print(f"  Grootte: {r['overlap_size']} paren")
            print(f"  Interne paren (Strict Bisimilair):")
            for p in sorted(list(r['internals'])):
                print(f"    - {p}")
            print(f"  Frontier paren (Stack-Pop locaties):")
            for p in sorted(list(r['frontiers'])):
                print(f"    - {p}")
            print("-" * 40)