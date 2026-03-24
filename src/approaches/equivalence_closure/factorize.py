import networkx as nx
from typing import List, Set, Dict
from collections import defaultdict
from analyze import CanonicalSubstructure, MatchLocation


# ---------------------------------------------------------------------------
# SUBROUTINE LOGIC
# ---------------------------------------------------------------------------

def create_subroutine_structure(G: nx.DiGraph, sub: CanonicalSubstructure, sub_id: int):
    """
    Builds the abstract subroutine based on the CanonicalSubstructure object.

    Naming convention (uniform with algorithm 1):
      cluster:  subroutine_{sub_id}
      nodes:    SUB_{sub_id}_{j}   where j = position in sub.canonical_nodes
      labels:   S0, S1, S2, ...
      entry:    sub.canonical_nodes[0] → SUB_{sub_id}_0 → label S0

    Internal edges are built via sub.blueprint_edges (index-based),
    NOT via graph lookup. This fully decouples subroutine construction from
    the concrete nodes in the original graph.
    """
    cluster_name = f"subroutine_{sub_id}"

    # Position j in canonical_nodes → SUB_{sub_id}_{j}
    sub_mapping = {node: f"SUB_{sub_id}_{j}" for j, node in enumerate(sub.canonical_nodes)}

    # Add subroutine nodes with labels S0, S1, S2, ...
    for j, orig_node in enumerate(sub.canonical_nodes):
        G.add_node(sub_mapping[orig_node], cluster=cluster_name, label=f"S{j}")

    # Dummy start arrow to entry node (canonical_nodes[0] = S0)
    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, sub_mapping[sub.canonical_nodes[0]])

    # Build internal edges via blueprint_edges (indices → SUB nodes)
    # Fully decoupled from the original graph
    idx_to_sub = {j: sub_mapping[node] for j, node in enumerate(sub.canonical_nodes)}
    for edge in sub.blueprint_edges:
        src = idx_to_sub[edge.source_idx]
        tgt = idx_to_sub[edge.target_idx]
        if not G.has_edge(src, tgt):
            G.add_edge(src, tgt, label=edge.label)

    return cluster_name, sub_mapping


# ---------------------------------------------------------------------------
# FACTORIZATION CORE
# ---------------------------------------------------------------------------

def _is_valid_entry_structure(G: nx.DiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
    """Checks whether the structure is entered only via start_node."""
    for node in instance_nodes:
        if node == start_node:
            continue
        for source, _ in G.in_edges(node):
            if source not in instance_nodes:
                return False
    return True


def _process_exits(G: nx.DiGraph, loc: MatchLocation, sub_map: Dict[str, str], rc_id: str):
    """
    Handles transitions that exit the subroutine.

    Uses loc.frontiers from MatchLocation — determined by analyze.py.
    Builds the executable dispatch map: δret(rc_id, frontier_sub_node, symbol) → target
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

    # Store executable dispatch map as node attribute
    G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

    # Visual label
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
    Replaces an instance of the subroutine with an RC node.
    Uses loc.start_node as the explicit entry node.
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
        # canonical_nodes[0] is the entry node (BFS-order guaranteed by analyze.py)
        sub_name = f"subroutine_{sub_id}"

        # global_sub_mapping: canonical_nodes[j] → SUB_{sub_id}_{j}
        global_sub_mapping = {node: f"SUB_{sub_id}_{j}"
                               for j, node in enumerate(sub.canonical_nodes)}

        # --- STEP 1: PRE-SCAN ---
        valid_locations_to_process = []
        is_group_valid = True

        for loc in sub.locations:
            if any(n in processed_nodes for n in loc.all_nodes):
                is_group_valid = False
                break

            if _is_valid_entry_structure(G, loc.start_node, set(loc.all_nodes)):
                # Positional mapping: loc.all_nodes[j] → SUB_{sub_id}_{j}
                instance_mapping = {loc_node: global_sub_mapping[cn]
                                    for loc_node, cn in zip(loc.all_nodes, sub.canonical_nodes)}
                valid_locations_to_process.append((loc, instance_mapping))
            else:
                is_group_valid = False
                break

        # --- STEP 2: COMMIT ---
        if is_group_valid and len(valid_locations_to_process) >= 2:
            # Build subroutine via CanonicalSubstructure object (including blueprint_edges)
            create_subroutine_structure(G, sub, sub_id)

            for loc, instance_mapping in valid_locations_to_process:
                _replace_instance_with_rc(G, loc, sub_name, instance_mapping)
                all_nodes_to_remove.update(loc.all_nodes)
                processed_nodes.update(loc.all_nodes)

            print(f"Success: {sub_name} factorized at {len(valid_locations_to_process)} locations.")
        else:
            if not is_group_valid:
                print(f"Skipped: {sub_name} contains invalid or overlapping locations.")

    G.remove_nodes_from(all_nodes_to_remove)
    return G


def save_dot(G, filename):
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Factorized graph saved as: {filename}")