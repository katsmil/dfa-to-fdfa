import networkx as nx
from collections import defaultdict

"""
ALGORITME BESCHRIJVING: ISOMORPHISM
====================================================

Dit script identificeert structureel identieke (isomorfe) subgrafen binnen een 
grotere gerichte graaf (zoals een control flow graph). Het doel is om patronen 
te vinden die zich herhalen, zelfs als de knoop-namen verschillen.

Het algoritme werkt in 4 fasen:

1. PRE-PROCESSING (DOT -> Graaf & SCCs)
   - De graaf wordt ingelezen en edge-labels worden bewaard.
   - De graaf wordt opgesplitst in Strongly Connected Components (SCCs). 
     We zoeken alleen naar patronen binnen deze cyclische clusters.

2. DOMINATOR REGIO EXTRACTIE
   - Binnen een SCC berekenen we de 'dominator tree'.
   - Voor elke knoop D bepalen we de regio die hij domineert (alle knopen die 
     onbereikbaar zijn zonder eerst door D te gaan).
   - *Maximaliteits-filter*: We filteren geneste regio's weg. Als regio X 
     volledig vervat zit in regio Y (bijv. een kleine lus binnen een grotere lus), 
     behouden we alleen de grootste regio Y. Dit zorgt voor logische groepering 
     op het hoogste niveau.

3. CANONICAL HASHING
   - Om te bepalen of twee regio's identiek zijn, berekenen we een unieke hash.
   - De hash is gebaseerd op de *structuur* en de *labels van de edges*.
   - Dit gebeurt iteratief: elke knoop beschrijft zichzelf aan de hand van zijn 
     uitgaande edges en de buren. Na N iteraties vormt dit een unieke handtekening.

4. GROEPERING
   - Regio's met exact dezelfde hash worden gegroepeerd.
   - Groepen groter dan 1 worden gerapporteerd als isomorfe duplicaten.
"""

# ============================================================
# DOT -> NetworkX DiGraph
# ============================================================

def read_dot(path):
    g = nx.drawing.nx_pydot.read_dot(path)
    G = nx.DiGraph()

    for u, v, data in g.edges(data=True):
        label = data.get("label", "")
        if isinstance(label, str):
            label = label.strip('"')
        G.add_edge(u, v, label=label)

    return G


# ============================================================
# Canonical hashing voor gelabelde subgrafen
# ============================================================
# iterations is in feite een depth
def canonical_hash(G, nodes, iterations=10):
    """
    Compute a canonical, label-sensitive structural hash for a subgraph.

    Nodes are treated as anonymous; only edge labels and structure matter.
    """

    # 1. Initial description: all nodes look the same
    description = {node: "()" for node in nodes}

    # 2. Iteratively refine descriptions using outgoing edges
    for _ in range(iterations):
        description = refine_descriptions(G, nodes, description)

    # 3. Canonical form: sorted multiset of node descriptions
    return tuple(sorted(description.values()))

def refine_descriptions(G, nodes, description):
    new_description = {}

    for node in nodes:
        edges = outgoing_edges(G, node, nodes, description)
        new_description[node] = format_node(edges)

    return new_description

def refine_descriptions(G, nodes, description):
    new_description = {}

    for node in nodes:
        edges = outgoing_edges(G, node, nodes, description)
        new_description[node] = format_node(edges)

    return new_description

def outgoing_edges(G, node, nodes, description):
    edges = []

    for succ in G.successors(node):
        if succ in nodes:
            label = G[node][succ].get("label", "")
            edges.append((label, description[succ]))

    return sorted(edges)

def format_node(edges):
    if not edges:
        return "()"

    parts = [f"{label}:{desc}" for label, desc in edges]
    return "(" + ",".join(parts) + ")"


# ============================================================
# Dominator-regio extractie
# ============================================================
# Elke node domineert zichzelf
import networkx as nx

def dominator_regions(G, start, scc):
    # 1. Bereken immediate dominators
    idom = nx.immediate_dominators(G, start)

    # 2. Bereken voor elke knoop de set van ALLE dominators (niet alleen immediate)
    dom = {}
    for n in scc:
        dom[n] = set()
        cur = n
        # Loop terug omhoog in de dominator boom
        while cur in idom:
            dom[n].add(cur)
            if cur == idom[cur]: # Stop bij de root
                break
            cur = idom[cur]

    # 3. Bouw alle mogelijke regio's (kandidaten)
    candidates = {}
    for d in scc:
        # Een regio voor dominator 'd' bevat alle knopen 'n' waarvoor 'd' een dominator is
        region = {n for n in scc if d in dom[n]}
        if len(region) > 1:
            candidates[d] = region

    # 4. FILTER: Behoud alleen de maximale regio's
    # We sorteren op grootte (grootste eerst). Als een regio een subset is van
    # een regio die we al hebben opgeslagen, gooien we hem weg.
    final_regions = {}
    
    # Sorteer kandidaten op lengte van de set (descending)
    sorted_candidates = sorted(candidates.items(), key=lambda item: len(item[1]), reverse=True)

    for d, region in sorted_candidates:
        is_subset = False
        for existing_region in final_regions.values():
            if region.issubset(existing_region):
                is_subset = True
                break
        
        if not is_subset:
            final_regions[d] = region

    return final_regions


# ============================================================
# Hoofdalgoritme
# ============================================================

def find_isomorphic_components(dot_file, start):
    G = read_dot(dot_file)

    components = []

    for scc in nx.strongly_connected_components(G):
        if len(scc) < 2:
            continue
        if start not in G:
            continue

        regions = dominator_regions(G, start, scc)

        for entry, nodes in regions.items():
            H = G.subgraph(nodes)
            h = canonical_hash(H, nodes)
            components.append((entry, nodes, h))

    groups = defaultdict(list)
    for entry, nodes, h in components:
        groups[h].append((entry, nodes))

    return [g for g in groups.values() if len(g) > 1]


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Gebruik: python dominator.py <file.dot> <startnode>")
        sys.exit(1)

    dot_file = sys.argv[1]
    start = sys.argv[2]

    groups = find_isomorphic_components(dot_file, start)

    for i, group in enumerate(groups, 1):
        print(f"\nIsomorfe groep {i}:")
        for entry, nodes in group:
            print(f"  entry = {entry}, nodes = {sorted(nodes)}")
