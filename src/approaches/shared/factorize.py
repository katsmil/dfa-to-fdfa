import networkx as nx
from collections import defaultdict
from typing import List, Set, Dict, Tuple, Optional

from approaches.shared.shared_types import MatchLocation, BlueprintSubstructure


# ---------------------------------------------------------------------------
# BUILD SUBCOMPONENT
# ---------------------------------------------------------------------------

def _create_subcomponent_structure(G: nx.MultiDiGraph,
                                 sub: BlueprintSubstructure,
                                 sub_id: int) -> Tuple[str, Dict[str, str]]:
    """
    Builds the subcomponent in G based on the BlueprintSubstructure.

    sub_mapping: blueprint_node_name → SUB_{sub_id}_{j}
    blueprint_nodes[0] is guaranteed to be the entry node (BFS-order from analyze.py).
    Internal edges are built via blueprint_edges (index-based),
    fully decoupled from the original graph.
    """
    cluster_name = f"subroutine_{sub_id}"
    sub_mapping = {node: f"SUB_{sub_id}_{j}"
                   for j, node in enumerate(sub.blueprint_nodes)}

    for j, orig_node in enumerate(sub.blueprint_nodes):
        originally_accepting = _is_accepting_node(G, orig_node)
        G.add_node(sub_mapping[orig_node],
                   cluster=cluster_name,
                   label=f"sub{sub_id}.{j}",
                   originally_accepting=originally_accepting)

    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0",
               cluster=cluster_name)
    G.add_edge(start_dummy, sub_mapping[sub.blueprint_nodes[0]])

    idx_to_sub = {j: sub_mapping[node] for j, node in enumerate(sub.blueprint_nodes)}
    existing_edges: set = set()
    for edge in sub.blueprint_edges:
        src = idx_to_sub[edge.source_idx]
        tgt = idx_to_sub[edge.target_idx]
        key = (src, tgt, edge.label)
        if key not in existing_edges:
            G.add_edge(src, tgt, label=edge.label)
            existing_edges.add(key)

    return cluster_name, sub_mapping



def _is_accepting_node(G: nx.MultiDiGraph, node: str) -> bool:
    """
    Returns True if the node was an accepting state in G.
    If the node was already tagged by a previous factorization run (via the
    'originally_accepting' attribute), that value is used directly. 
    Otherwise, the 'shape' attribute is checked for 'doublecircle' to determine accepting status.
    Or peripheries=2 is also accepted as an alternative marker for accepting states.
    """
    nd = G.nodes[node]
    oa = nd.get('originally_accepting')
    if oa is not None:
        return str(oa).strip().strip('"').strip("'").lower() == 'true'
    shape = str(nd.get('shape', '')).strip().strip('"').strip("'")
    peripheries = str(nd.get('peripheries', '')).strip().strip('"').strip("'")
    return shape == 'doublecircle' or peripheries == '2'


# ---------------------------------------------------------------------------
# INSTANCE REPLACEMENT
# ---------------------------------------------------------------------------

def _build_instance_mapping(loc: MatchLocation,
                              sub_mapping: Dict[str, str]) -> Dict[str, str]:
    """Maps concrete nodes of this instance to SUB-nodes via positional order."""
    return {loc_node: sub_mapping[cn]
            for loc_node, cn in zip(loc.all_nodes, sub_mapping.keys())}


def _strip_label_quotes(label: str) -> str:
    """Strip surrounding quotes from a DOT label value (pydot artifact)."""
    s = str(label).strip()
    while len(s) >= 2 and s[0] in ('"\'') and s[-1] in ('"\''):
        s = s[1:-1].strip()
    return s


def _process_exits(G: nx.MultiDiGraph,
                    loc: MatchLocation,
                    instance_mapping: Dict[str, str],
                    rc_id: str):
    """
    Handles transitions that exit the subcomponent.
    Iterates over loc.frontiers — nodes with external outgoing edges.

    Edge label strategy:
    - If all frontier nodes can trigger a transition: label is just the symbol.
    - If only a subset of frontier nodes can trigger it: append [SUB_x_y, ...]
      to make the context-dependency visible.
    The RC node label is NOT modified — dispatch info lives on the edges.

    The resulting dispatch_map has the structure:
        { label: { SUB_x_y: target_node, ... }, ... }
    Example:
        {
            "a": {"SUB_0_1": "q5", "SUB_0_2": "q7"},
            "b": {"SUB_0_1": "q3"}
        }
    Here "a" is triggered by two frontier nodes going to different targets,
    "b" only by SUB_0_1 — which causes a [SUB_0_1] annotation on that edge.
    """
    dispatch_map = defaultdict(dict)
    instance_nodes = set(loc.all_nodes)

    # Step 1: collect dispatch map and mark frontier SUB nodes
    for frontier_node in loc.frontiers:
        sub_node = instance_mapping[frontier_node]
        for _, target, data in list(G.out_edges(frontier_node, data=True)):
            label = _strip_label_quotes(data.get('label', ''))
            if target not in instance_nodes:
                dispatch_map[label][sub_node] = target
                G.nodes[sub_node].update({
                    "peripheries": 2,
                    "fillcolor": "lightblue",
                    "style": "filled",
                })

    G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

    # Step 2: full set of frontier SUB nodes
    all_frontier_subs = set(
        sub for sub_to_target in dispatch_map.values()
        for sub in sub_to_target.keys()
    )

    # Step 3: group symbols by (triggering frontiers, target)
    #
    # Example:
    #   dispatch_map['i'] = {SUB_0_3: 16, SUB_0_4: 17}
    # becomes two groups:
    #   (frontiers={SUB_0_3}, target=16) -> ['i']
    #   (frontiers={SUB_0_4}, target=17) -> ['i']
    # which later yields two edges:
    #   i [SUB_0_3] -> 16
    #   i [SUB_0_4] -> 17
    groups: Dict[tuple, list] = defaultdict(list)
    for symbol, sub_to_target in dispatch_map.items():
        target_to_frontiers: Dict[str, Set[str]] = defaultdict(set)
        for sub_node, target in sub_to_target.items():
            target_to_frontiers[target].add(sub_node)
        for target, frontiers in target_to_frontiers.items():
            groups[(frozenset(frontiers), target)].append(symbol)

    # Step 4: add edges — annotate only when a subset of frontiers triggers the transition
    for (triggering_frontiers, target), symbols in groups.items():
        combined_symbols = ",".join(sorted(symbols))
        if triggering_frontiers == all_frontier_subs:
            edge_label = combined_symbols
        else:
            frontier_str = ", ".join(sorted(triggering_frontiers))
            edge_label = f"{combined_symbols} [{frontier_str}]"

        if not G.has_edge(rc_id, target, key=edge_label):
            G.add_edge(rc_id, target, label=edge_label, key=edge_label)


def _replace_instance_with_rc(G: nx.MultiDiGraph,
                                loc: MatchLocation,
                                sub_name: str,
                                instance_mapping: Dict[str, str]):
    """Replaces one instance of the substructure with an RC node."""
    rc_id = f"RC_{loc.start_node}"

    if not G.has_node(rc_id):
        rc_attrs = dict(shape='box', style='filled', fillcolor='orange',
                        label=f"RC: {sub_name}")
        # Inherit cluster from the replaced start node (needed for second-iteration nesting)
        start_cluster = G.nodes[loc.start_node].get('cluster')
        if start_cluster:
            rc_attrs['cluster'] = start_cluster
            # peripheries=2 is only set after _process_exits (see below).
        G.add_node(rc_id, **rc_attrs)

    # Redirect incoming edges from outside the instance to the RC node.
    instance_nodes = set(loc.all_nodes)
    for u, v, data in list(G.in_edges(loc.start_node, data=True)):
        if u not in instance_nodes:
            G.add_edge(u, rc_id, **data)

    _process_exits(G, loc, instance_mapping, rc_id)

    # If nested inside a parent subcomponent, inherit frontier status from
    # any replaced instance node that was itself a frontier (peripheries=2).
    parent_cluster = G.nodes[rc_id].get('cluster')
    if parent_cluster:
        for orig_node in loc.all_nodes:
            if G.has_node(orig_node):
                p = str(G.nodes[orig_node].get('peripheries', '')).strip().strip('"').strip("'")
                if p == '2':
                    G.nodes[rc_id].update({'peripheries': 2})
                    break


def _update_dispatch_maps(G: nx.MultiDiGraph,
                           replaced_by: Dict[str, str],
                           rc_nodes_with_dispatch: Set[str],
                           frontier_key_replacements: Optional[Dict[str, str]] = None):
    """
    After all factorisation steps, some dispatch map targets may have been
    replaced by RC nodes. For example, if RC_s12 originally pointed to s42,
    and s42 was later factorised into RC_s42, the dispatch map of RC_s12 must
    be updated to point to RC_s42 instead.

    For each RC node, this function:
      1. Updates the dispatch map: replaces any target that was factorised
         with the RC node that replaced it.
      2. Removes the old edge to the original target.
      3. Adds a new edge to the RC node that replaced it, preserving the
         existing edge label exactly — no label modification is needed because
         the transition semantics (which symbol, which frontier) are unchanged.

    Additionally, if frontier_key_replacements is provided (used in second-run
    factorization of blueprint nodes), it updates dispatch_map KEYS across ALL
    RC nodes. This is needed when frontier SUB blueprint nodes are removed and
    replaced by nodes from a new inner subcomponent: the callers of the outer
    subcomponent need their frontier-key references updated to the new SUB nodes.
    """
    # Update dispatch_map targets + edges for RC nodes whose targets were factorised.
    for node in rc_nodes_with_dispatch:
        data = G.nodes[node]
        if 'dispatch_map' not in data:
            continue

        dispatch_map = data['dispatch_map']

        for label, sub_to_target in dispatch_map.items():
            for sub_node, target in list(sub_to_target.items()):
                if target in replaced_by:
                    new_target = replaced_by[target]

                    # Step 1: update the dispatch map entry to point to the new RC node.
                    sub_to_target[sub_node] = new_target

                    # Step 2 & 3: remove the old edge and add a new one to the RC node.
                    # Edge keys may be "symbol" or "symbol [SUB_x_y]" depending on
                    # whether the transition was triggered by all frontiers or a subset.
                    # We match on the symbol prefix (before any " [") to find the right edges,
                    # then re-add them with the exact same label so no annotation is lost.
                    if G.has_edge(node, target):
                        keys_to_remove = [
                            k for k, d in G[node][target].items()
                            if _strip_label_quotes(d.get('label', '')).split(' [')[0]
                               == _strip_label_quotes(label)
                        ]
                        for k in keys_to_remove:
                            old_edge_label = G[node][target][k].get('label', label)
                            G.remove_edge(node, target, key=k)
                            if not G.has_edge(node, new_target, key=k):
                                G.add_edge(node, new_target,
                                           label=old_edge_label, key=k)

    # Second pass: frontier nodes inside SUB_* may be replaced by a new inner RC node.
    # Update dispatch_map keys so outer RC nodes still point to the correct frontier.
    if frontier_key_replacements:
        for node, node_data in G.nodes(data=True):
            if 'dispatch_map' not in node_data:
                continue
            dm = node_data['dispatch_map']
            if not isinstance(dm, dict):
                continue
            for label, sub_to_target in list(dm.items()):
                keys_to_swap = [
                    (old_k, frontier_key_replacements[old_k])
                    for old_k in list(sub_to_target.keys())
                    if old_k in frontier_key_replacements and old_k != frontier_key_replacements[old_k]
                ]
                for old_key, new_key in keys_to_swap:
                    target = sub_to_target.pop(old_key)
                    sub_to_target[new_key] = target


# ---------------------------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------------------------

def _is_valid_entry_structure(G: nx.MultiDiGraph,
                                start_node: str,
                                instance_nodes: Set[str]) -> bool:
    """Checks whether the structure is entered only via start_node."""
    for node in instance_nodes:
        if node == start_node:
            continue
        for source, _ in G.in_edges(node):
            if source not in instance_nodes:
                return False
    return True


# ---------------------------------------------------------------------------
# FILTERING
# ---------------------------------------------------------------------------

def _build_dispatch_signatures(G: nx.MultiDiGraph) -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Build a nested map per RC node: {label: {frontier_node: target}}.

    Used in _filter_locations to check whether two candidate nodes are
    referenced by the SAME RC node with DIFFERENT exit targets for the same
    label. In that case, merging them would corrupt the dispatch_map of that
    RC node (two frontier keys become one, but the targets differ).

    Nodes referenced by different RC nodes are always safe to merge — each
    outer RC node retains its own dispatch entry.
    """
    import ast as _ast
    rc_dispatch: Dict[str, Dict[str, Dict[str, str]]] = {}
    for rc_node, data in G.nodes(data=True):
        dm = data.get('dispatch_map')
        if dm is None:
            continue
        if isinstance(dm, str):
            try:
                dm = _ast.literal_eval(dm.strip().strip('"'))
            except Exception:
                continue
        if not isinstance(dm, dict):
            continue
        rc_dispatch[rc_node] = {}
        for label, sub_to_target in dm.items():
            if not isinstance(sub_to_target, dict):
                continue
            rc_dispatch[rc_node][label] = dict(sub_to_target)
    return rc_dispatch


def _filter_locations(G: nx.MultiDiGraph,
                  sub: BlueprintSubstructure,
                  sub_mapping: Dict[str, str],
                  processed_nodes: Set[str],
                  dispatch_signatures: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None) -> List:
    """
    Filters the locations of a subcomponent pattern. Invalid or overlapping
    locations are skipped; the rest are tried.

    dispatch_signatures check: a location is rejected if an outer RC node
    references two or more nodes from that same location as frontier keys for
    the same label but with different targets. Replacing them with a single RC
    node would collapse those distinct exit paths into one, corrupting the
    dispatch map of that outer RC node.
    """
    valid = []
    nodes_in_batch: Set[str] = set()

    for loc in sub.locations:
        loc_nodes = set(loc.all_nodes)
        if any(n in processed_nodes for n in loc_nodes):
            continue
        if any(n in nodes_in_batch for n in loc_nodes):
            continue
        if not _is_valid_entry_structure(G, loc.start_node, loc_nodes):
            continue

        if dispatch_signatures is not None:
            intra_conflict = False
            for rc_node_map in dispatch_signatures.values():
                for label, frontier_to_target in rc_node_map.items():
                    # Collect all targets for nodes in this location
                    targets_in_loc = {
                        n: t for n, t in frontier_to_target.items()
                        if n in loc_nodes
                    }
                    if len(set(targets_in_loc.values())) > 1:
                        intra_conflict = True
                        break
                if intra_conflict:
                    break
            if intra_conflict:
                continue

        valid.append((loc, _build_instance_mapping(loc, sub_mapping)))
        nodes_in_batch.update(loc_nodes)

    return valid


# ---------------------------------------------------------------------------
# APPLY
# ---------------------------------------------------------------------------

def apply_factorization(G: nx.MultiDiGraph,
                         results: List[BlueprintSubstructure]) -> nx.MultiDiGraph:
    processed_nodes: Set[str] = set()
    nodes_to_remove: Set[str] = set()
    replaced_by: Dict[str, str] = {}
    rc_nodes_with_dispatch: Set[str] = set()
    frontier_key_replacements: Dict[str, str] = {}  # instance node → RC node that replaced it (for updating dispatch_map keys in outer RC nodes)
    sub_node_peripheries: Dict[str, str] = {}       # loc_node → sub_node (peripheries propagation)

    dispatch_signatures: Optional[Dict[str, Dict[str, str]]] = _build_dispatch_signatures(G)

    # Determine starting sub_id to avoid name collisions with SUB_ nodes
    # already present in G from a previous apply_factorization call.
    existing_sub_ids: set = set()
    for node in G.nodes():
        s = str(node)
        if s.startswith('SUB_'):
            parts = s.split('_')
            if len(parts) >= 3:
                try:
                    existing_sub_ids.add(int(parts[1]))
                except ValueError:
                    pass
    sub_id_start = (max(existing_sub_ids) + 1) if existing_sub_ids else 0

    for sub_id_offset, sub in enumerate(results):
        sub_id = sub_id_start + sub_id_offset
        sub_name = f"subroutine_{sub_id}"
        sub_mapping = {node: f"SUB_{sub_id}_{j}"
                       for j, node in enumerate(sub.blueprint_nodes)}

        valid_locations = _filter_locations(
            G, sub, sub_mapping, processed_nodes, dispatch_signatures)

        # Only factorize if the substructure occurs at least twice — otherwise there is nothing to compress.
        if len(valid_locations) >= 2:
            _create_subcomponent_structure(G, sub, sub_id)

            for loc, instance_mapping in valid_locations:
                rc_id = f"RC_{loc.start_node}"
                _replace_instance_with_rc(G, loc, sub_name, instance_mapping)
                rc_nodes_with_dispatch.add(rc_id)

                # Track which concrete nodes are replaced by this RC node.
                # Used to update dispatch_map KEYS in outer RC nodes: the old
                # frontier keys (e.g. SUB_29_1, SUB_29_2) are replaced by the
                # nested RC node (e.g. RC_SUB_29_1) which acts as the new
                # frontier of the parent subcomponent.
                for loc_node in loc.all_nodes:
                    frontier_key_replacements[loc_node] = rc_id

                # Separate mapping used to propagate peripheries=2 to the
                # blueprint SUB nodes of the inner subcomponent. These nodes
                # inherited their frontier status from the blueprint nodes they
                # replaced, but _process_exits cannot detect it (blueprint nodes
                # have no graph-level external edges — those live in dispatch_maps).
                for loc_node, sub_node in instance_mapping.items():
                    sub_node_peripheries[loc_node] = sub_node

                for original_node in loc.all_nodes:
                    replaced_by[original_node] = rc_id

                nodes_to_remove.update(loc.all_nodes)
                processed_nodes.update(loc.all_nodes)

    # Propagate peripheries=2 to the blueprint SUB nodes of inner subcomponents.
    # Blueprint nodes have no graph-level external edges (those are in dispatch_maps),
    # so _process_exits cannot mark them as frontiers. We recover the frontier
    # status from the original SUB nodes they replaced.
    for old_node, new_sub_node in sub_node_peripheries.items():
        if G.has_node(old_node) and G.has_node(new_sub_node):
            old_peripheries = G.nodes[old_node].get('peripheries')
            if old_peripheries == 2 or str(old_peripheries).strip('"') == '2':
                G.nodes[new_sub_node].update({
                    "peripheries": 2,
                    "fillcolor": "lightblue",
                    "style": "filled",
                })

    G.remove_nodes_from(nodes_to_remove)
    _update_dispatch_maps(G, replaced_by, rc_nodes_with_dispatch,
                          frontier_key_replacements if frontier_key_replacements else None)

    return G

# ---------------------------------------------------------------------------
# SAVE
# ---------------------------------------------------------------------------


def save_dot(G: nx.MultiDiGraph, filename: str):
    # 1. Create a temporary DiGraph for export
    export_G = nx.DiGraph()

    # Copy global graph attributes (e.g. name="bigSmall")
    export_G.graph.update(G.graph)

    # 2. Copy nodes and make dicts safe for DOT
    for node, data in G.nodes(data=True):
        clean_attrs = {}
        for k, v in data.items():
            if isinstance(v, dict):
                clean_attrs[k] = str(v)
            elif v is not None:
                clean_attrs[k] = str(v).strip('"')
        export_G.add_node(node, **clean_attrs)

    # 3. Collect ALL unique edges and their attributes
    all_unique_edges = set()
    edge_groups = defaultdict(list)
    edge_metadata = {}

    for u, v, data in G.edges(data=True):
        all_unique_edges.add((u, v))
        
        # Collect labels if they exist
        if 'label' in data:
            edge_groups[(u, v)].append(str(data['label']).strip('"'))
        
        # Store remaining metadata (from the first edge we encounter)
        if (u, v) not in edge_metadata:
            edge_metadata[(u, v)] = {k: val for k, val in data.items() if k != 'label'}

    # 4. Add all edges to the new graph
    for u, v in all_unique_edges:
        labels = edge_groups.get((u, v), [])
        meta = edge_metadata.get((u, v), {})
        
        if labels:
            # Combine labels with a comma
            combined_label = ",".join(sorted(set(labels)))
            export_G.add_edge(u, v, label=combined_label, **meta)
        else:
            # Add edge without label (e.g. __start0 -> q0)
            export_G.add_edge(u, v, **meta)

    # 5. Save via pydot
    try:
        pd_graph = nx.drawing.nx_pydot.to_pydot(export_G)
        pd_graph.write_raw(filename)
        print(f"Factorized graph saved successfully: {filename}")
    except Exception as e:
        print(f"Error saving file: {e}")
