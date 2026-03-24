# import networkx as nx
# from collections import defaultdict
# from typing import List, Set, Dict
# from analyze import CanonicalSubstructure

# def create_subroutine_structure(G: nx.MultiDiGraph, sub: CanonicalSubstructure, sub_id: int):
#     """
#     Builds the abstract subroutine based on the blueprint.
#     """
#     cluster_name = f"subroutine_{sub_id}"
#     # Index 0 is ALWAYS the entry node (guaranteed by Analysis BFS)
#     sub_mapping = {node: f"SUB_{sub_id}_{j}" for j, node in enumerate(sub.canonical_nodes)}

#     for i, sub_node in sub_mapping.items():
#         G.add_node(sub_node, cluster=cluster_name, label=f"S{i}")

#     # Dummy start arrow to S0
#     start_dummy = f"__start_{cluster_name}"
#     G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
#     G.add_edge(start_dummy, sub_mapping[0])

#     # Build internal transitions strictly according to blueprint
#     for edge in sub.blueprint_edges:
#         G.add_edge(sub_mapping[edge.source_idx], sub_mapping[edge.target_idx], label=edge.label)

#     return cluster_name, sub_mapping

# def _process_exits(G: nx.MultiDiGraph, instance_nodes: Set[str], sub_map: Dict[str, str], rc_id: str):
#     """Handles transitions that exit the subroutine."""
#     dispatch_map = defaultdict(dict)  # dispatch_map[symbol][sub_frontier_node] = target
    
#     for inst_node in instance_nodes:
#         sub_node = sub_map[inst_node]
#         for _, target, data in list(G.out_edges(inst_node, data=True)):
#             label = data.get('label')
#             if target not in instance_nodes:
#                 # δret(rc, sub_frontier_node, symbol) = target
#                 dispatch_map[label][sub_node] = target
                
#                 # Edge from RC to target in main graph
#                 if not G.has_edge(rc_id, target, key=label):
#                     G.add_edge(rc_id, target, label=label, key=label)
                
#                 # Mark frontier nodes in subroutine
#                 G.nodes[sub_node].update({
#                     "peripheries": 2,
#                     "fillcolor": "lightblue",
#                     "style": "filled"
#                 })

#     # --- Store the EXECUTABLE dispatch map as a node attribute ---
#     # Structure: { symbol: { sub_frontier_node: target_node } }
#     G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

#     # --- Visual label with dispatch table ---
#     visual_rows = [
#         f'"{l}": {", ".join(nodes.keys())}'
#         for l, nodes in dispatch_map.items()
#     ]
#     mapping_str = "\\n".join(visual_rows)
#     if mapping_str:
#         G.nodes[rc_id]['label'] = f"{G.nodes[rc_id]['label']}\\n[{mapping_str}]"

# def apply_factorization(G: nx.MultiDiGraph, results: List[CanonicalSubstructure]):
#     """
#     Applies factorization. Filters each location for overlap (global and local) and validity.
#     Commits only if >= 2 valid locations remain.
#     """
#     processed_nodes = set() # Tracks which nodes have ALREADY been removed by earlier subroutines
#     nodes_to_remove = set()

#     print(f"Starting factorization with {len(results)} candidate structures...")

#     for i, sub in enumerate(results):
#         sub_id = i
#         valid_locations_to_process = []
        
#         # Tracks which nodes we claim for THIS specific subroutine (to prevent internal overlap)
#         nodes_in_current_batch = set()

#         # --- FILTER PHASE ---
#         for loc in sub.locations:
#             loc_nodes_set = set(loc.all_nodes)

#             # CHECK 1: Global Overlap
#             # Is any of these nodes already used in a PREVIOUS factorization?
#             if any(n in processed_nodes for n in loc_nodes_set):
#                 continue

#             # CHECK 2: Local Overlap
#             # Does this location overlap with one we JUST approved in this loop?
#             if any(n in nodes_in_current_batch for n in loc_nodes_set):
#                 continue

#             # CHECK 3: Valid Entry?
#             # Can the graph be cleanly cut here?
#             if not _is_valid_entry_structure(G, loc.start_node, loc_nodes_set):
#                 continue

#             # If we reach here, the location is valid and free.
#             valid_locations_to_process.append(loc)
#             nodes_in_current_batch.update(loc_nodes_set)

#         # --- COMMIT PHASE ---
#         # We only build if we have at least 2 valid locations remaining
#         if len(valid_locations_to_process) >= 2:
#             # 1. Really build the subroutine into the graph
#             cluster_name, sub_mapping = create_subroutine_structure(G, sub, sub_id)
            
#             print(f"  > Subroutine {sub_id} applied at {len(valid_locations_to_process)} locations.")

#             for loc in valid_locations_to_process:
#                 rc_id = f"RC_{loc.start_node}"
#                 G.add_node(rc_id, shape='box', style='filled', fillcolor='orange', label=f"RC: {cluster_name}")
                
#                 # Mapping: Real Node -> Subroutine Node (via Index)
#                 instance_map = {node_name: sub_mapping[idx] for idx, node_name in enumerate(loc.all_nodes)}
                
#                 # 2. Redirect incoming transitions to the RC node
#                 for u, v, data in list(G.in_edges(loc.start_node, data=True)):
#                     if u not in loc.all_nodes:
#                         G.add_edge(u, rc_id, **data)
                
#                 # 3. Process exits and update dispatch table
#                 _process_exits(G, set(loc.all_nodes), instance_map, rc_id)
            
#             # 4. Only now add these nodes to the global processed list
#             processed_nodes.update(nodes_in_current_batch)
#             nodes_to_remove.update(nodes_in_current_batch)
#         else:
#             # If after filtering < 2 remain, we do nothing with this group
#             pass

#     # Clean up all replaced nodes in one go
#     G.remove_nodes_from(nodes_to_remove)
#     return G

# # Helper for validation
# def _is_valid_entry_structure(G: nx.MultiDiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
#     """
#     Checks whether the structure is entered only via start_node.
#     """
#     for node in instance_nodes:
#         if node == start_node:
#             continue
#         for source, _ in G.in_edges(node):
#             if source not in instance_nodes:
#                 return False
#     return True

# def save_dot(G: nx.MultiDiGraph, filename: str):
#     try:
#         nx.drawing.nx_pydot.write_dot(G, filename)
#         print(f"Factorized graph saved: {filename}")
#     except Exception as e:
#         print(f"Error saving file: {e}")


import networkx as nx
from collections import defaultdict
from typing import List, Set, Dict
from analyze import CanonicalSubstructure

def create_subroutine_structure(G: nx.MultiDiGraph, sub: CanonicalSubstructure, sub_id: int):
    """
    Builds the abstract subroutine based on the blueprint.
    """
    cluster_name = f"subroutine_{sub_id}"
    # Index 0 is ALWAYS the entry node (guaranteed by Analysis BFS)
    sub_mapping = {i: f"SUB_{sub_id}_{i}" for i in range(sub.nodes_count)}

    for i, sub_node in sub_mapping.items():
        G.add_node(sub_node, cluster=cluster_name, label=f"S{i}")

    # Dummy start arrow to S0
    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, sub_mapping[0])

    # Build internal transitions strictly according to blueprint
    for edge in sub.blueprint_edges:
        G.add_edge(sub_mapping[edge.source_idx], sub_mapping[edge.target_idx], label=edge.label)

    return cluster_name, sub_mapping

def _process_exits(G: nx.MultiDiGraph, instance_nodes: Set[str], sub_map: Dict[str, str], rc_id: str):
    """Handles transitions that exit the subroutine."""
    dispatch_map = defaultdict(dict)  # dispatch_map[symbol][sub_frontier_node] = target
    
    for inst_node in instance_nodes:
        sub_node = sub_map[inst_node]
        for _, target, data in list(G.out_edges(inst_node, data=True)):
            label = data.get('label')
            if target not in instance_nodes:
                # δret(rc, sub_frontier_node, symbol) = target
                dispatch_map[label][sub_node] = target
                
                # Edge from RC to target in main graph
                if not G.has_edge(rc_id, target, key=label):
                    G.add_edge(rc_id, target, label=label, key=label)
                
                # Mark frontier nodes in subroutine
                G.nodes[sub_node].update({
                    "peripheries": 2,
                    "fillcolor": "lightblue",
                    "style": "filled"
                })

    # --- Store the EXECUTABLE dispatch map as a node attribute ---
    # Structure: { symbol: { sub_frontier_node: target_node } }
    G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

    # --- Visual label with dispatch table ---
    visual_rows = [
        f'"{l}": {", ".join(nodes.keys())}'
        for l, nodes in dispatch_map.items()
    ]
    mapping_str = "\\n".join(visual_rows)
    if mapping_str:
        G.nodes[rc_id]['label'] = f"{G.nodes[rc_id]['label']}\\n[{mapping_str}]"

def apply_factorization(G: nx.MultiDiGraph, results: List[CanonicalSubstructure]):
    """
    Applies factorization. Filters each location for overlap (global and local) and validity.
    Commits only if >= 2 valid locations remain.
    """
    processed_nodes = set()  # Tracks which nodes have already been removed by earlier subroutines
    nodes_to_remove = set()

    print(f"Starting factorization with {len(results)} candidate structures...")

    for i, sub in enumerate(results):
        sub_id = i
        valid_locations_to_process = []
        
        # Tracks which nodes we claim for THIS specific subroutine (to prevent internal overlap)
        nodes_in_current_batch = set()

        # --- FILTER PHASE ---
        for loc in sub.locations:
            loc_nodes_set = set(loc.all_nodes)

            # CHECK 1: Global Overlap
            # Is any of these nodes already used in a PREVIOUS factorization?
            if any(n in processed_nodes for n in loc_nodes_set):
                continue

            # CHECK 2: Local Overlap
            # Does this location overlap with one we JUST approved in this loop?
            if any(n in nodes_in_current_batch for n in loc_nodes_set):
                continue

            # CHECK 3: Valid Entry?
            # Can the graph be cleanly cut here?
            if not _is_valid_entry_structure(G, loc.start_node, loc_nodes_set):
                continue

            # If we reach here, the location is valid and free.
            valid_locations_to_process.append(loc)
            nodes_in_current_batch.update(loc_nodes_set)

        # --- COMMIT PHASE ---
        # We only build if we have at least 2 valid locations remaining
        if len(valid_locations_to_process) >= 2:
            # 1. Really build the subroutine into the graph
            cluster_name, sub_mapping = create_subroutine_structure(G, sub, sub_id)
            
            print(f"  > Subroutine {sub_id} applied at {len(valid_locations_to_process)} locations.")

            for loc in valid_locations_to_process:
                rc_id = f"RC_{loc.start_node}"
                G.add_node(rc_id, shape='box', style='filled', fillcolor='orange', label=f"RC: {cluster_name}")
                
                # Mapping: Real Node -> Subroutine Node (via Index)
                instance_map = {node_name: sub_mapping[idx] for idx, node_name in enumerate(loc.all_nodes)}
                
                # 2. Redirect incoming transitions to the RC node
                for u, v, data in list(G.in_edges(loc.start_node, data=True)):
                    if u not in loc.all_nodes:
                        G.add_edge(u, rc_id, **data)
                
                # 3. Process exits and update dispatch table
                _process_exits(G, set(loc.all_nodes), instance_map, rc_id)
            
            # 4. Only now add these nodes to the global processed list
            processed_nodes.update(nodes_in_current_batch)
            nodes_to_remove.update(nodes_in_current_batch)
        else:
            # If after filtering < 2 remain, we do nothing with this group
            pass

    # Clean up all replaced nodes in one go
    G.remove_nodes_from(nodes_to_remove)
    return G

# Helper for validation
def _is_valid_entry_structure(G: nx.MultiDiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
    """
    Checks whether the structure is entered only via start_node.
    """
    for node in instance_nodes:
        if node == start_node:
            continue
        for source, _ in G.in_edges(node):
            if source not in instance_nodes:
                return False
    return True

def save_dot(G: nx.MultiDiGraph, filename: str):
    try:
        nx.drawing.nx_pydot.write_dot(G, filename)
        print(f"Factorized graph saved: {filename}")
    except Exception as e:
        print(f"Error saving file: {e}")