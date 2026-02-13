import networkx as nx
from utils.graph_utils import read_dot

def is_accepting(G, node):
    """
    Hulpfunctie om te bepalen of een node een eindtoestand is.
    Pas dit aan op basis van jouw DOT-attributen!
    """
    # Veelvoorkomend in DOT: shape='doublecircle' voor eindtoestanden
    node_data = G.nodes[node]
    return node_data.get('shape') == 'doublecircle' or node_data.get('accepting') == 'true'

def find_maximal_bisimilar_overlap(G, start_a, start_b):
    """
    Vindt de grootste bisimilaire overlap tussen twee structuren.
    Edges zonder 'label' attribuut worden genegeerd.
    Retourneert: set van paren (n1, n2) die bisimilair zijn bevonden
    """
    stack = [(start_a, start_b)]
    equivalent_pairs = set()
    visited = set()
    
    while stack:
        n1, n2 = stack[-1]
        
        if (n1, n2) in visited:
            stack.pop()
            continue

        # We nemen (n1,n2) op als voorlopig equivalent
        visited.add((n1, n2))

        if is_accepting(G, n1) != is_accepting(G, n2):
            # De een is accepterend, de ander niet -> geen bisimulatie mogelijk
            return equivalent_pairs
        
        # skip edges zonder label
        edges1 = {d['label']: v 
                  for _, v, d in G.out_edges(n1, data=True) 
                  if 'label' in d}
        edges2 = {d['label']: v 
                  for _, v, d in G.out_edges(n2, data=True) 
                  if 'label' in d}
        
        # ❗ Structuur mismatch → STOP en geef visited terug
        if set(edges1.keys()) != set(edges2.keys()):
            return equivalent_pairs
        
        # 3. Als we hier komen, is dit specifieke paar bisimulair
        equivalent_pairs.add((n1, n2))

        # Voeg opvolgers toe
        has_unvisited = False
        for char in edges1.keys():
            next1, next2 = edges1[char], edges2[char]
            if (next1, next2) not in visited:
                stack.append((next1, next2))
                has_unvisited = True
        
        if not has_unvisited:
            stack.pop()
    
    # Alles afgewerkt zonder mismatch → volledige overlap
    return equivalent_pairs

def find_entry_nodes(G, scc):
    entries = set()
    for n in scc:
        for u, v in G.in_edges(n):
            if u not in scc:
                entries.add(n)
                break
    return entries

def pick_highest_degree_node(G, scc):
    return max(scc, key=lambda n: G.degree(n))

def pick_start_node(G, scc):
    entries = find_entry_nodes(G, scc)
    
    if entries:
        # Neem gewoon één entry node (bijv. die met hoogste degree)
        return max(entries, key=lambda n: G.degree(n))
    else:
        # Geen entry nodes → neem node met hoogste degree in de SCC
        return pick_highest_degree_node(G, scc)


def analyze_scc_pairs(dot_file):
    # G = read_dot(dot_file)
    G = nx.drawing.nx_pydot.read_dot(dot_file)
    sccs = list(nx.strongly_connected_components(G))
    
    results = []
    # Vergelijk SCCs paarsgewijs
    for i in range(len(sccs)):
        for j in range(i + 1, len(sccs)):
            scc_a = sccs[i]
            scc_b = sccs[j]
            
            # Pak startpunten (bijv. de node met de laagste graad of entry node)
            entry_a = pick_start_node(G, scc_a)
            entry_b = pick_start_node(G, scc_b)
            
            overlap = find_maximal_bisimilar_overlap(G, entry_a, entry_b)
            
            if len(overlap) > 1: # Alleen boeiend als er meer dan 1 node matcht
                results.append({
                    'pair': (entry_a, entry_b),
                    'overlap_size': len(overlap),
                    'nodes': overlap,
                    'scc_a': scc_a,
                    'scc_b': scc_b
                })
    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Gebruik: python script.py <graph.dot>")
        print("Bijvoorbeeld: python bisim.py automaat.dot")
        sys.exit(1)

    dot_file = sys.argv[1]

    print(f"Graph laden uit: {dot_file}")
    results = analyze_scc_pairs(dot_file)

    if not results:
        print("Geen interessante bisimulaire overlaps gevonden.")
    else:
        print("Gevonden bisimulaire overlaps:\n")
        for r in results:
            print(f"SCC-paar {r['pair']}:")
            print(f"  Overlap grootte: {r['overlap_size']}")
            print(f"  Nodes: {r['nodes']}")
            print()
