import networkx as nx
from typing import List, Set, Dict
from collections import defaultdict
from analyze import CanonicalSubstructure, MatchLocation


# --- SUBROUTINE LOGICA ---

def create_subroutine_structure(G: nx.DiGraph, sub: CanonicalSubstructure, sub_id: int):
    """
    Bouwt de abstracte subroutine op basis van het CanonicalSubstructure object.

    Naamgevingsconventie (uniform):
      cluster:  subroutine_{sub_id}
      nodes:    SUB_{sub_id}_{j}   waarbij j = positie in sub.canonical_nodes
      labels:   S0, S1, S2, ...
      entry:    sub.canonical_nodes[0] → SUB_{sub_id}_0 → label S0

    sub.canonical_nodes is een LIST — volgorde is gegarandeerd door BFS in analyze.py.
    canonical_nodes[0] is altijd de entry node.
    """
    cluster_name = f"subroutine_{sub_id}"

    # Positie j in de lijst → SUB_{sub_id}_{j}
    sub_mapping = {node: f"SUB_{sub_id}_{j}" for j, node in enumerate(sub.canonical_nodes)}

    # Voeg subroutine nodes toe met label S0, S1, S2, ...
    for j, orig_node in enumerate(sub.canonical_nodes):
        sub_node = sub_mapping[orig_node]
        G.add_node(sub_node, cluster=cluster_name, label=f"S{j}")

    # Dummy startpijl naar entry node (altijd canonical_nodes[0] = S0)
    canonical_start = sub.canonical_nodes[0]
    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, sub_mapping[canonical_start])

    # Bouw interne edges vanuit de originele graaf
    canonical_set = set(sub.canonical_nodes)  # alleen voor membership check
    for orig_node in sub.canonical_nodes:
        sub_source = sub_mapping[orig_node]
        for _, orig_target, data in list(G.out_edges(orig_node, data=True)):
            if orig_target in canonical_set:
                G.add_edge(sub_source, sub_mapping[orig_target], **data)

    return cluster_name, sub_mapping


# --- FACTORISATIE KERN ---

def _is_valid_entry_structure(G: nx.DiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
    """Controleert of de structuur alleen via start_node wordt binnengegaan."""
    for node in instance_nodes:
        if node == start_node:
            continue
        for source, _ in G.in_edges(node):
            if source not in instance_nodes:
                return False
    return True


def _process_exits(G: nx.DiGraph, loc: MatchLocation, sub_map: Dict[str, str], rc_id: str):
    """
    Handelt transities af die de subroutine verlaten.

    Gebruikt loc.frontiers uit MatchLocation — deze zijn al bepaald door analyze.py.
    Bouwt de uitvoerbare dispatch map: δret(rc_id, frontier_sub_node, symbol) → target
    """
    dispatch_map = defaultdict(dict)  # dispatch_map[symbol][sub_frontier_node] = target
    instance_nodes = set(loc.all_nodes)

    # Alleen frontier nodes hebben externe uitgaande transities
    for frontier_node in loc.frontiers:
        sub_node = sub_map[frontier_node]

        for _, target, data in list(G.out_edges(frontier_node, data=True)):
            label = data.get('label')
            if target not in instance_nodes:
                # δret(rc_id, sub_node, label) = target
                dispatch_map[label][sub_node] = target

                # Edge van RC naar target in hoofdgraaf
                if not G.has_edge(rc_id, target, key=label):
                    G.add_edge(rc_id, target, label=label, key=label)

                # Markeer frontier node in subroutine (visueel + semantisch)
                G.nodes[sub_node].update({
                    "peripheries": 2,
                    "fillcolor": "lightblue",
                    "style": "filled"
                })

    # Sla de uitvoerbare dispatch map op als node attribuut
    # Structuur: { symbol: { sub_frontier_node: target_node } }
    G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

    # Visueel label met dispatch tabel
    visual_rows = [
        f'"{l}": {", ".join(nodes.keys())}'
        for l, nodes in dispatch_map.items()
    ]
    mapping_str = "\\n".join(visual_rows)
    if mapping_str:
        G.nodes[rc_id]['label'] = f"{G.nodes[rc_id]['label']}\\n[{mapping_str}]"


def _replace_instance_with_rc(G: nx.DiGraph,
                               loc: MatchLocation,
                               subroutine_name: str,
                               sub_mapping: Dict[str, str]):
    """
    Vervangt een instantie van de subroutine door een RC node.
    Gebruikt loc.start_node als expliciete entry node.
    """
    rc_node_id = f"RC_{loc.start_node}"

    if not G.has_node(rc_node_id):
        G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange',
                   label=f"RC: {subroutine_name}")

    # 1. Inkomende edges ombuigen naar RC node
    instance_nodes = set(loc.all_nodes)
    for u, v, data in list(G.in_edges(loc.start_node, data=True)):
        if u not in instance_nodes:
            G.add_edge(u, rc_node_id, **data)

    # 2. Exits verwerken en dispatch map opbouwen
    _process_exits(G, loc, sub_mapping, rc_node_id)


def apply_factorization(G: nx.DiGraph, results: List[CanonicalSubstructure]):
    all_nodes_to_remove = set()
    processed_nodes = set()

    for sub_id, sub in enumerate(results):
        # sub.canonical_nodes is een LIST — canonical_nodes[0] is de entry node
        cluster_name = f"subroutine_{sub_id}"
        sub_name = cluster_name  # RC label: "RC: subroutine_0"

        # Bouw sub_mapping op basis van de geordende canonical_nodes lijst
        # canonical_nodes[j] → SUB_{sub_id}_{j}
        global_sub_mapping = {node: f"SUB_{sub_id}_{j}"
                               for j, node in enumerate(sub.canonical_nodes)}

        # --- STAP 1: PRE-SCAN (validatie van de gehele groep) ---
        valid_locations_to_process = []
        is_group_valid = True

        for loc in sub.locations:
            # Check globale overlap met eerder gecommitte subroutines
            if any(n in processed_nodes for n in loc.all_nodes):
                is_group_valid = False
                break

            # loc.start_node is de expliciete entry node van deze instantie
            if _is_valid_entry_structure(G, loc.start_node, set(loc.all_nodes)):
                # Bouw instance mapping: loc.all_nodes positie-voor-positie aan canonical_nodes
                # zip werkt correct omdat analyze.py BFS-volgorde bewaart in beide lijsten
                instance_mapping = {loc_node: global_sub_mapping[cn]
                                    for loc_node, cn in zip(loc.all_nodes, sub.canonical_nodes)}
                valid_locations_to_process.append((loc, instance_mapping))
            else:
                is_group_valid = False
                break

        # --- STAP 2: COMMIT (alleen als de hele groep valide is) ---
        if is_group_valid and len(valid_locations_to_process) >= 2:
            # Geef het CanonicalSubstructure object mee — niet losse parameters
            create_subroutine_structure(G, sub, sub_id)

            for loc, instance_mapping in valid_locations_to_process:
                _replace_instance_with_rc(G, loc, sub_name, instance_mapping)
                all_nodes_to_remove.update(loc.all_nodes)
                processed_nodes.update(loc.all_nodes)

            print(f"Succes: {sub_name} gefactoriseerd op {len(valid_locations_to_process)} locaties.")
        else:
            if not is_group_valid:
                print(f"Overgeslagen: {sub_name} bevat ongeldige of overlappende locaties.")

    G.remove_nodes_from(all_nodes_to_remove)
    return G


def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")