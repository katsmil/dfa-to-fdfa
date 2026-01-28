import networkx as nx 
from typing import List, Set, Dict, Tuple 
from collections import deque 
from dataclasses import dataclass 

# Importeer je match-klasse (of gebruik deze definitie als je alles in één file wilt) 
@dataclass(frozen=True) 
class SubstructureMatch: 
    start_nodes: Tuple[str, str] 
    overlap_size: int 
    internals: Set[Tuple[str, str]]     # <-- BISIMILAIRE KERN (gebruik dit)
    frontiers: Set[Tuple[str, str]]     # <-- Divergerende frontier-paren
    all_pairs: Set[Tuple[str, str]] 

# --- HULPFUNCTIES --- 


def _get_out_labels(G: nx.DiGraph, node: str) -> Dict[str, str]: 
    """Geeft een dictionary van label -> target_node.""" 
    return {data.get('label'): target for _, target, data in G.out_edges(node, data=True) if 'label' in data} 

# --- BIBLIOTHEEK LOGICA --- 

def create_external_library_structure(G: nx.DiGraph, canonical_nodes: Set[str], cluster_id: int, canonical_start: str):
    """
    Maakt een losstaande kopie van enkel de canonical (bisimilaire) kern.
    - canonical_nodes: strikt de interne (bisimilaire) nodes, geen frontiers.
    - markeert als accepterend: knopen in canonical_nodes die geen uitgaande edges
      naar andere canonical_nodes hebben. Als er geen zulke knopen zijn (bv. cyclisch),
      markeer canonical_start als accepting.
    Retourneert (cluster_name, mapping).
    """
    mapping = {node: f"EXT_{canonical_start}_{node}" for node in canonical_nodes}
    cluster_name = f"cluster_{canonical_start}_{cluster_id}"

    # Voeg gekopieerde nodes toe
    for orig_node, ext_node in mapping.items():
        attrs = G.nodes[orig_node].copy() if orig_node in G.nodes else {}
        attrs['cluster'] = cluster_name
        attrs['label'] = f"{orig_node}"
        # (geen peripheries/status setten hier — doen we na bepalen van terminal nodes)
        G.add_node(ext_node, **attrs)

    # start dummy (indien start in mapping)
    if canonical_start in mapping:
        start_dummy = f"__start_{cluster_name}"
        G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
        try:
            G.add_edge(start_dummy, mapping[canonical_start], key="0")
        except TypeError:
            G.add_edge(start_dummy, mapping[canonical_start])

    # Kopieer interne edges (alleen tussen canonical nodes)
    for orig_node in canonical_nodes:
        ext_source = mapping[orig_node]
        for _, orig_target, data in list(G.out_edges(orig_node, data=True)):
            if orig_target in canonical_nodes:
                ext_target = mapping[orig_target]
                edge_attrs = data.copy()
                # LAYOUT FIX: Voorkom spaghetti bij cycli
                if orig_target == canonical_start or orig_node == orig_target:
                    edge_attrs['constraint'] = 'false'
                try:
                    G.add_edge(ext_source, ext_target, **edge_attrs)
                except TypeError:
                    G.add_edge(ext_source, ext_target)

    # Bepaal terminale node(s) binnen de canonical set:
    terminal_nodes = set()
    for n in canonical_nodes:
        # als n geen uitgaande edge naar een andere canonical node heeft -> terminal
        has_out_to_canonical = any(t in canonical_nodes for _, t, _ in G.out_edges(n, data=True))
        if not has_out_to_canonical:
            terminal_nodes.add(n)
    # Als geen terminal nodes (bv. cyclisch), gebruik canonical_start als accepting
    if not terminal_nodes and canonical_start in canonical_nodes:
        terminal_nodes = {canonical_start}

    # Markeer terminal nodes in de EXTERNAL kopie als accepting (visual)
    for t in terminal_nodes:
        ext = mapping[t]
        attrs = G.nodes[ext].copy()
        attrs['peripheries'] = 2
        attrs['status'] = 'accepting'
        attrs['fillcolor'] = 'lightblue'
        # update node attrs
        G.nodes[ext].update(attrs)

    return cluster_name, mapping

# --- DIVERGENTIE & UNIEK GEDRAG --- 

def _preserve_unique_behavior(G: nx.DiGraph, start_node: str, instance_nodes: Set[str], canonical_map: Dict[str, str], rc_node_id: str):
    """
    Identificeert gedrag dat afwijkt van de canonical (library) versie
    en zorgt dat deze paden behouden blijven vanuit de RC node.
    canonical_map: map van instance_node -> lib_node (de lib_node is meestal EXT_... kopie)
    instance_nodes: set met instance node namen (de nodes die we overwegen te verwijderen)
    """
    preserved_nodes = set()
    queue = deque()
    # 1. Scan alle nodes in de instance op afwijkingen t.o.v. de library 
    for inst_node, lib_node in canonical_map.items():
        # Als de lib-node niet bestaat (defensief), skip
        if not G.has_node(inst_node) or not G.has_node(lib_node):
            continue
        inst_out = _get_out_labels(G, inst_node)
        lib_out = _get_out_labels(G, lib_node)
        for label, inst_target in inst_out.items():
            # A: Externe transities (altijd behouden) -> RC -> extern target
            if inst_target not in instance_nodes:
                # behoud externe exit vanuit de RC
                G.add_edge(rc_node_id, inst_target, label=label)
                continue
            # B: Interne afwijking (label bestaat niet in de library)
            if label not in lib_out:
                if inst_target == start_node:
                    # Terug naar eigen start wordt een loop op de RC 
                    G.add_edge(rc_node_id, rc_node_id, label=label)
                else:
                    # Nieuw uniek intern pad: RC -> inst_target
                    G.add_edge(rc_node_id, inst_target, label=label)
                if inst_target not in preserved_nodes:
                    preserved_nodes.add(inst_target)
                    queue.append(inst_target)

    # 2. BFS: Loop de unieke paden af en behoud de benodigde nodes 
    visited_in_bfs = set()
    while queue:
        u = queue.popleft()
        if u in visited_in_bfs: 
            continue
        visited_in_bfs.add(u)
        edges = list(G.out_edges(u, data=True))
        for _, v, data in edges:
            if v == start_node:
                # Verwijs terug naar de proxy 
                G.add_edge(u, rc_node_id, **data)
            elif v not in instance_nodes:
                # Externe exit vanaf een uniek pad blijft staan (geen extra actie)
                pass
            else:
                if v not in preserved_nodes:
                    preserved_nodes.add(v)
                    queue.append(v)
    return preserved_nodes

# --- FACTORISATIE KERN --- 
def _is_valid_entry_structure(G: nx.DiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
    """
    Controleert of de enige ingang van buiten de 'instance_nodes' naar de 'start_node' gaat.
    Als een andere node in 'instance_nodes' een inkomende edge heeft van buiten de set, 
    is de structuur niet geschikt voor zuivere factorisatie.
    """
    for node in instance_nodes:
        if node == start_node:
            continue
            
        # Kijk naar alle inkomende edges van deze interne node
        for source, _ in G.in_edges(node):
            if source not in instance_nodes:
                # Oeps: een 'jump-in' van buitenaf naar een niet-start node
                return False
    return True

def _replace_instance_with_rc(G: nx.DiGraph,
                             start_node: str,
                             instance_nodes: Set[str],
                             substructure_name: str,
                             canonical_map: Dict[str, str]) -> Set[str]:
    """
    Vervangt een instance door een RC node. 
    Nu met de garantie dat alleen de start_node externe inkomende edges heeft.
    """
    rc_node_id = f"RC_{start_node}"

    if not G.has_node(rc_node_id):
        G.add_node(rc_node_id,
                   shape='box',
                   style='filled',
                   fillcolor='orange',
                   label=f"CALL: {substructure_name}")

    # 1) Omleiding: Alleen de inkomende edges naar de START node hoeven we om te buigen
    in_edges_start = list(G.in_edges(start_node, data=True))
    for u, v, data in in_edges_start:
        if u not in instance_nodes:
            try:
                G.add_edge(u, rc_node_id, **(data.copy() if isinstance(data, dict) else {}))
            except TypeError:
                G.add_edge(u, rc_node_id)

    # 2) Uniek gedrag (exits van de frontier nodes) afhandelen
    # Omdat we nu weten dat alle interne nodes (behalve start) geen externe in-edges hebben,
    # kunnen we veilig de exits van de frontier nodes naar de RC node verplaatsen.
    preserved = _preserve_unique_behavior(G, start_node, instance_nodes, canonical_map, rc_node_id)

    return instance_nodes - preserved


def apply_factorization(G: nx.DiGraph, results: List[SubstructureMatch]):
    """
    Hoofdfunctie voor factorisatie met Single-Entry validatie.
    """
    processed_canonicals = set()
    all_nodes_to_remove = set()
    
    sorted_results = sorted(results, key=lambda x: x.overlap_size, reverse=True)

    for i, res in enumerate(sorted_results):
        canonical_start, factored_start = res.start_nodes
        nodes_a = {p[0] for p in res.all_pairs}
        nodes_b = {p[1] for p in res.all_pairs}

        sub_name = f"Sub_{canonical_start}"

        # --- VALIDATIE STAP ---
        # We checken beide kanten. Als een kant niet voldoet aan de Single Entry regel,
        # skippen we die specifieke factorisatie.
        
        # 1. Behandel de Canonical kant (de Library blueprint)
        if canonical_start not in processed_canonicals:
            if _is_valid_entry_structure(G, canonical_start, nodes_a):
                cluster_name, ext_mapping = create_external_library_structure(G, nodes_a, i, canonical_start)
                canonical_to_ext_map = {node: ext_mapping[node] for node in nodes_a}
                
                to_remove_a = _replace_instance_with_rc(G, canonical_start, nodes_a, sub_name, canonical_to_ext_map)
                all_nodes_to_remove.update(to_remove_a)
                processed_canonicals.add(canonical_start)
            else:
                # Optioneel: log dat je deze overslaat
                print(f"Skipping factorization of {canonical_start}: contains external jumps to internal nodes.")

        # 2. Behandel de Factored kant (de kopie)
        if G.has_node(factored_start):
            if _is_valid_entry_structure(G, factored_start, nodes_b):
                factored_to_ext_map = {fact: f"EXT_{canonical_start}_{canon}" for canon, fact in res.all_pairs}
                
                to_remove_b = _replace_instance_with_rc(G, factored_start, nodes_b, sub_name, factored_to_ext_map)
                all_nodes_to_remove.update(to_remove_b)
            else:
                print(f"Skipping factorization of {factored_start}: contains external jumps to internal nodes.")

    G.remove_nodes_from(all_nodes_to_remove)
    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")
