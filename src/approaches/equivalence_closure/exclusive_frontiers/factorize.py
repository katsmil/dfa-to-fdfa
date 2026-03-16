import networkx as nx
from typing import List, Set, Dict
from collections import defaultdict
from analyze import CanonicalSubstructure, MatchLocation


# ---------------------------------------------------------------------------
# SUBROUTINE LOGICA
# ---------------------------------------------------------------------------

def create_subroutine_structure(G: nx.DiGraph, sub: CanonicalSubstructure, sub_id: int):
    """
    Bouwt de abstracte subroutine op basis van het CanonicalSubstructure object.

    Naamgevingsconventie (uniform met algoritme 1):
      cluster:  subroutine_{sub_id}
      nodes:    SUB_{sub_id}_{j}   waarbij j = positie in sub.canonical_nodes
      labels:   S0, S1, S2, ...
      entry:    sub.canonical_nodes[0] → SUB_{sub_id}_0 → label S0

    Interne edges worden gebouwd via sub.blueprint_edges (index-gebaseerd),
    NIET via graph-lookup. Dit ontkoppelt de subroutineopbouw volledig van
    de concrete nodes in de originele graaf.
    """
    cluster_name = f"subroutine_{sub_id}"

    # Positie j in canonical_nodes → SUB_{sub_id}_{j}
    sub_mapping = {node: f"SUB_{sub_id}_{j}" for j, node in enumerate(sub.canonical_nodes)}

    # Voeg subroutine nodes toe met label S0, S1, S2, ...
    for j, orig_node in enumerate(sub.canonical_nodes):
        G.add_node(sub_mapping[orig_node], cluster=cluster_name, label=f"S{j}")

    # Dummy startpijl naar entry node (canonical_nodes[0] = S0)
    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, sub_mapping[sub.canonical_nodes[0]])

    # Bouw interne edges via blueprint_edges (indices → SUB-nodes)
    # Volledig ontkoppeld van de originele graaf
    idx_to_sub = {j: sub_mapping[node] for j, node in enumerate(sub.canonical_nodes)}
    for edge in sub.blueprint_edges:
        src = idx_to_sub[edge.source_idx]
        tgt = idx_to_sub[edge.target_idx]
        if not G.has_edge(src, tgt):
            G.add_edge(src, tgt, label=edge.label)

    return cluster_name, sub_mapping


# ---------------------------------------------------------------------------
# FACTORISATIE KERN
# ---------------------------------------------------------------------------

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

    Gebruikt loc.frontiers uit MatchLocation — bepaald door analyze.py.
    Bouwt de uitvoerbare dispatch map: δret(rc_id, frontier_sub_node, symbol) → target
    """
    dispatch_map = defaultdict(dict)  # dispatch_map[symbol][sub_frontier_node] = target
    instance_nodes = set(loc.all_nodes)

    for frontier_node in loc.frontiers:
        sub_node = sub_map[frontier_node]

        for _, target, data in list(G.out_edges(frontier_node, data=True)):
            label = data.get('label')
            if target not in instance_nodes:
                # δret(rc_id, sub_node, label) = target
                dispatch_map[label][sub_node] = target

                if not G.has_edge(rc_id, target, key=label):
                    G.add_edge(rc_id, target, label=label, key=label)

                G.nodes[sub_node].update({
                    "peripheries": 2,
                    "fillcolor": "lightblue",
                    "style": "filled"
                })

    # Sla uitvoerbare dispatch map op als node attribuut
    G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

    # Visueel label
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

    instance_nodes = set(loc.all_nodes)
    for u, v, data in list(G.in_edges(loc.start_node, data=True)):
        if u not in instance_nodes:
            G.add_edge(u, rc_node_id, **data)

    _process_exits(G, loc, sub_mapping, rc_node_id)


# ---------------------------------------------------------------------------
# APPLY
# ---------------------------------------------------------------------------

def apply_factorization(G: nx.DiGraph, results: List[CanonicalSubstructure]):
    all_nodes_to_remove = set()
    processed_nodes = set()

    for sub_id, sub in enumerate(results):
        # canonical_nodes[0] is de entry node (BFS-volgorde gegarandeerd door analyze.py)
        sub_name = f"subroutine_{sub_id}"

        # global_sub_mapping: canonical_nodes[j] → SUB_{sub_id}_{j}
        global_sub_mapping = {node: f"SUB_{sub_id}_{j}"
                               for j, node in enumerate(sub.canonical_nodes)}

        # --- STAP 1: PRE-SCAN ---
        valid_locations_to_process = []
        is_group_valid = True

        for loc in sub.locations:
            if any(n in processed_nodes for n in loc.all_nodes):
                is_group_valid = False
                break

            if _is_valid_entry_structure(G, loc.start_node, set(loc.all_nodes)):
                # Positie-voor-positie koppeling: loc.all_nodes[j] → SUB_{sub_id}_{j}
                instance_mapping = {loc_node: global_sub_mapping[cn]
                                    for loc_node, cn in zip(loc.all_nodes, sub.canonical_nodes)}
                valid_locations_to_process.append((loc, instance_mapping))
            else:
                is_group_valid = False
                break

        # --- STAP 2: COMMIT ---
        if is_group_valid and len(valid_locations_to_process) >= 2:
            # Subroutine bouwen via CanonicalSubstructure object (inclusief blueprint_edges)
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
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")