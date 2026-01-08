"""
ALGORITME: Factorisatie van Cyclische DFA's via Maximale Bisimulatie
====================================================================

Dit script identificeert herhalende substructuren in een DFA die gefactoriseerd samengevoegd kunnen worden.
Het algoritme werkt door equivalent gedrag tussen knopen te vinden,
ongeacht of deze zich in een lus (SCC) of een lineair pad (acyclisch karakter) bevinden.

Het proces verloopt in drie hoofdstappen:

1. Signature Hashing (De "Buckets" maken)
   -------------------------------
   Om een volledige kwadratische complexiteit te voorkomen bij het vergelijken
   van alle knopen, berekenen we eerst een lokale 'handtekening' voor elke knoop.
   Deze handtekening bestaat uit de gesorteerde lijst van labels van uitgaande 
   transities. Alleen knopen met identieke handtekeningen (die in dezelfde 'emmer' 
   vallen) zijn kandidaat om een equivalente structuur te starten. 
   Deze signatuur maken is O(n) complex.

2. Frontier Bisimulatie (Zoeken naar Maximale Overlap)
   ---------------------------------------------------
   Voor elk paar kandidaten uit dezelfde emmer starten we een parallelle
   verkenning door de graaf. We controleren stap voor stap:
   - Of de knopen dezelfde 'accepting' status hebben (eindtoestand vs normaal).
   - Of de uitgaande transities (labels) exact overeenkomen.
   
   In plaats van enkel "Ja/Nee" te antwoorden bij de eerste fout, verzamelt 
   dit proces alle knopenparen die equivalent zijn *totdat* er een mismatch 
   optreedt of tot er geen opvolgers meer zijn. 
   Dit levert de grootst mogelijke equivalente substructuur op.

3. Subset Filtering (Redundantie Verwijdering)
   -------------------------------------------
   ook losse (kleinere) structuren kunnen gevonden worden, maar die zijn vervat in grotere gehelen.
   Deze kleinere gehelen moeten gefilterd worden.
   (Bijv:   Structuur 1:
            Startpunten: 1 <-> 11
            Omvang van de overlap: 3 toestanden
            Equivalente paren:
                - 1 matches met 11
                - 2 matches met 12
                - 3 matches met 13
            ------------------------------
            Structuur 2:
            Startpunten: a_B1 <-> b_K1
            Omvang van de overlap: 2 toestanden
            Equivalente paren:
                - a_B1 matches met b_K1
                - a_C1 matches met b_L1
            ------------------------------
            Structuur 3:
            Startpunten: 2 <-> 12
            Omvang van de overlap: 2 toestanden
            Equivalente paren:
                - 2 matches met 12
                - 3 matches met 13
            ------------------------------)
   
   Om dit op te lossen:
   - Sorteren we alle gevonden matches van groot naar klein.
   - Behouden we een match alleen als de set van equivalente paren géén
     deelverzameling (subset) is van een reeds gevonden grotere structuur.
   
Dit garandeert dat we alleen de maximale, unieke te factoriseren delen overhouden.
"""

from collections import defaultdict
import networkx as nx

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
        
        # Structuur mismatch → STOP en geef visited terug
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

def filter_redundant_results(results):
    """
    Verwijdert resultaten die volledig omsloten worden door grotere resultaten.
    Bijvoorbeeld: als resultaat A {(2,12), (3,13)} vindt, en resultaat B
    vindt {(1,11), (2,12), (3,13)}, dan wordt A verwijderd.
    """
    # Stap 1: Sorteer op grootte (grootste eerst)
    # Dit is cruciaal: we willen de grootste structuren als 'basis' houden.
    sorted_results = sorted(results, key=lambda x: x['overlap_size'], reverse=True)
    
    kept_results = []
    
    for current in sorted_results:
        current_pairs = current['matched_pairs']
        is_subset = False
        
        # Stap 2: Check of deze set paren al bestaat in een groter resultaat dat we hebben bewaard
        for kept in kept_results:
            # issubset controleert wiskundig of alle paren van current ook in kept zitten
            if current_pairs.issubset(kept['matched_pairs']):
                is_subset = True
                break
        
        # Stap 3: Alleen toevoegen als het geen deelverzameling is
        if not is_subset:
            kept_results.append(current)
            
    return kept_results

def analyze_graph_factorization(dot_file):
    G_raw = nx.drawing.nx_pydot.read_dot(dot_file)
    G = nx.DiGraph(G_raw) 

    nodes = list(G.nodes())
    results = []
    signatures = defaultdict(list)

    # Stap 1: Handtekening maken (Signature)
    for n in nodes:
        # Haal alle labels van uitgaande edges op
        # We gebruiken data['label'] uit de edge data
        out_labels = []
        for _, v, data in G.out_edges(n, data=True):
            if 'label' in data:
                out_labels.append(data['label'])
        
        if out_labels:
            sig = tuple(sorted(out_labels))
            signatures[sig].append(n)

    # Stap 2: Paarsgewijs vergelijken op basis van de signature
    # Dit vangt zowel de u-v-w paden als SCC structuren
    compared_pairs = set()

    for sig, candidate_nodes in signatures.items():
        for i in range(len(candidate_nodes)):
            for j in range(i + 1, len(candidate_nodes)):
                n1, n2 = candidate_nodes[i], candidate_nodes[j]
                
                # Voorkom dubbel werk
                pair_id = tuple(sorted((n1, n2)))
                if pair_id in compared_pairs:
                    continue
                compared_pairs.add(pair_id)

                overlap = find_maximal_bisimilar_overlap(G, n1, n2)
                
                if len(overlap) >= 2: # Minimaal 2 knopen voor interessante factorisatie
                    results.append({
                        'start_nodes': (n1, n2),
                        'overlap_size': len(overlap),
                        'matched_pairs': overlap
                    })

    final_results = filter_redundant_results(results)

    return final_results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Gebruik: python script.py <graph.dot>")
        print("Bijvoorbeeld: python bisim.py automaat.dot")
        sys.exit(1)

    dot_file = sys.argv[1]

    print(f"--- Analyse van DFA factorisatie: {dot_file} ---")
    results = analyze_graph_factorization(dot_file)

    if not results:
        print("Geen factoriseerbare overlap gevonden tussen verschillende delen van de graaf.")
    else:
        print(f"Totaal aantal gevonden overeenkomstige structuren: {len(results)}\n")
        
        for i, r in enumerate(results, 1):
            n1, n2 = r['start_nodes']
            print(f"Structuur {i}:")
            print(f"  Startpunten: {n1} <-> {n2}")
            print(f"  Omvang van de overlap: {r['overlap_size']} toestanden")
            
            # Print de individuele matches overzichtelijk
            print("  Equivalente paren:")
            # We sorteren de paren even voor een logische volgorde in de print
            sorted_pairs = sorted(list(r['matched_pairs']))
            for pair in sorted_pairs:
                print(f"    - {pair[0]} matches met {pair[1]}")
            print("-" * 30)