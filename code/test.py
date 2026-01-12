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

def is_accepting(G, node):
    node_data = G.nodes[node]
    return node_data.get('shape') == 'doublecircle' or node_data.get('accepting') == 'true'

def get_exit_points(G, matched_pairs):
    """
    Identificeert transities die de overlap verlaten.
    Dit zijn de 'return' paden voor je RTN.
    """
    exit_points = []
    # Maak sets van de individuele nodes in de overlap voor snelle lookup
    nodes_in_overlap_a = {p[0] for p in matched_pairs}
    nodes_in_overlap_b = {p[1] for p in matched_pairs}

    for (u, v) in matched_pairs:
        edges_u = {d['label']: target for _, target, d in G.out_edges(u, data=True)}
        edges_v = {d['label']: target for _, target, d in G.out_edges(v, data=True)}
        
        # We kijken naar labels die beide hebben
        common_labels = set(edges_u.keys()) & set(edges_v.keys())
        for label in common_labels:
            next_u = edges_u[label]
            next_v = edges_v[label]
            
            # Als de opvolgers NIET in de overlap zitten, is dit een exit point
            if (next_u, next_v) not in matched_pairs:
                exit_points.append({
                    'source_pair': (u, v),
                    'label': label,
                    'return_to': (next_u, next_v)
                })
    return exit_points

def find_maximal_bisimilar_overlap(G, start_a, start_b, closure_eR):
    # Stack bevat paren die we nog moeten controleren op 'uitbreidbaarheid' (strikte bisimulariteit)
    stack = [(start_a, start_b)]
    
    # Dit is de set die we teruggeven: alle knopen in de structuur, INCLUSIEF de randen (q2/q8)
    structure_pairs = set()
    
    # We houden bij welke paren we al 'strikt' hebben gecheckt om oneindige lussen te voorkomen
    visited_strict = set()

    # Eerste check: zijn de startknopen zelf wel een potentiële match?
    # Zo niet, dan is er geen structuur om te beginnen.
    if is_accepting(G, start_a) != is_accepting(G, start_b):
        return set()
    
    # Controleer initieel de labels van de startknopen
    edges_start_a = {d['label'] for _, _, d in G.out_edges(start_a, data=True) if 'label' in d}
    edges_start_b = {d['label'] for _, _, d in G.out_edges(start_b, data=True) if 'label' in d}
    if edges_start_a != edges_start_b:
        return set()

    # Als de start goed is, voegen we hem toe en beginnen we
    structure_pairs.add((start_a, start_b))

    while stack:
        n1, n2 = stack.pop()

        if (n1, n2) in visited_strict:
            continue
        
        # Haal uitgaande transities op
        edges1 = {d['label']: v for _, v, d in G.out_edges(n1, data=True) if 'label' in d}
        edges2 = {d['label']: v for _, v, d in G.out_edges(n2, data=True) if 'label' in d}

        # STRIKTE CHECK:
        # Om een 'interne' knoop van de structuur te zijn (waarvandaan we verder recursen),
        # moeten de uitgaande labels en acceptance status exact gelijk zijn.
        is_strict_match = (
            is_accepting(G, n1) == is_accepting(G, n2) and 
            set(edges1.keys()) == set(edges2.keys())
        )

        if is_strict_match:
            # Ze zijn strikt gelijk:
            # 1. Markeer als bezocht voor recursie
            visited_strict.add((n1, n2))
            
            # 2. Update de closure (alleen voor strikte matches!)
            closure_eR.add_equivalence(n1, n2)
            
            # 3. Bekijk de kinderen
            for label in edges1.keys():
                next1 = edges1[label]
                next2 = edges2[label]
                next_pair = (next1, next2)

                # BELANGRIJKSTE WIJZIGING:
                # Omdat de transitie (n1->next1) en (n2->next2) identiek is (zelfde label),
                # hoort het doelpaar (next1, next2) bij de structuur, ZELFS als ze daarna verschillen.
                structure_pairs.add(next_pair)

                # We voegen ze toe aan de stack om te kijken of de structuur NOG verder gaat.
                # De check of ze strikt zijn gebeurt pas als we ze van de stack poppen.
                if next_pair not in visited_strict:
                    stack.append(next_pair)
        
        # Als het GEEN strikte match is (bv q2/q8 in Ristov fig 2), doen we niets.
        # Het paar zit al in 'structure_pairs' (toegevoegd door de parent),
        # maar we gaan niet verder recursen en voegen ze niet toe aan closure_eR.

    return structure_pairs

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

                overlap = find_maximal_bisimilar_overlap(G, n1, n2, closure_eR)
                
                if len(overlap) >= 2: 
                    # NIEUW: Bereken de exit points voor deze specifieke overlap
                    exits = get_exit_points(G, overlap)
                    
                    results.append({
                        'start_nodes': (n1, n2),
                        'overlap_size': len(overlap),
                        'matched_pairs': overlap,
                        'exit_points': exits
                    })

    # Filter redundante resultaten
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