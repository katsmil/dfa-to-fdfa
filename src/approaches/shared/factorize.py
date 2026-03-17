import networkx as nx
from collections import defaultdict
from typing import List, Set, Dict, Tuple

from approaches.shared.shared_types import MatchLocation, CanonicalSubstructure


# ---------------------------------------------------------------------------
# SUBROUTINE BOUWEN
# ---------------------------------------------------------------------------

def _create_subroutine_structure(G: nx.MultiDiGraph,
                                 sub: CanonicalSubstructure,
                                 sub_id: int) -> Tuple[str, Dict[str, str]]:
    """
    Bouwt de abstracte subroutine in G op basis van CanonicalSubstructure.

    sub_mapping: canonical_node_naam → SUB_{sub_id}_{j}
    canonical_nodes[0] is gegarandeerd de entry node (BFS-volgorde uit analyze.py).
    Interne edges worden gebouwd via blueprint_edges (index-gebaseerd),
    volledig ontkoppeld van de originele graaf.
    """
    cluster_name = f"subroutine_{sub_id}"
    sub_mapping = {node: f"SUB_{sub_id}_{j}"
                   for j, node in enumerate(sub.canonical_nodes)}

    for j, orig_node in enumerate(sub.canonical_nodes):
        originally_accepting = _is_accepting_node(G, orig_node)
        G.add_node(sub_mapping[orig_node],
                   cluster=cluster_name,
                   label=f"S{j}",
                   originally_accepting=originally_accepting)

    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0",
               cluster=cluster_name)
    G.add_edge(start_dummy, sub_mapping[sub.canonical_nodes[0]])

    idx_to_sub = {j: sub_mapping[node] for j, node in enumerate(sub.canonical_nodes)}
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
    Strips surrounding quotes to handle both shape="doublecircle" and shape=doublecircle.
    """
    shape = str(G.nodes[node].get('shape', '')).strip().strip('"').strip("'")
    peripheries = str(G.nodes[node].get('peripheries', '')).strip().strip('"').strip("'")
    return shape == 'doublecircle' or peripheries == '2'


# ---------------------------------------------------------------------------
# INSTANTIE VERVANGING
# ---------------------------------------------------------------------------

def _build_instance_mapping(loc: MatchLocation,
                              sub_mapping: Dict[str, str]) -> Dict[str, str]:
    """Koppelt concrete nodes van deze instantie aan SUB-nodes via positievolgorde."""
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
    Handles transitions that exit the subroutine.
    Iterates over loc.frontiers — nodes with external outgoing edges.

    Edge label strategy:
    - If all frontier nodes can trigger a transition: label is just the symbol.
    - If only a subset of frontier nodes can trigger it: append [SUB_x_y, ...]
      to make the context-dependency visible.
    The RC node label is NOT modified — dispatch info lives on the edges.
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
    groups: Dict[tuple, list] = defaultdict(list)
    for symbol, sub_to_target in dispatch_map.items():
        triggering = frozenset(sub_to_target.keys())
        target = next(iter(sub_to_target.values()))
        groups[(triggering, target)].append(symbol)

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
    """Vervangt één instantie van de subroutine door een RC node."""
    rc_id = f"RC_{loc.start_node}"

    if not G.has_node(rc_id):
        G.add_node(rc_id, shape='box', style='filled', fillcolor='orange',
                   label=f"RC: {sub_name}")

    instance_nodes = set(loc.all_nodes)
    for u, v, data in list(G.in_edges(loc.start_node, data=True)):
        if u not in instance_nodes:
            G.add_edge(u, rc_id, **data)

    _process_exits(G, loc, instance_mapping, rc_id)


def _update_dispatch_maps(G: nx.MultiDiGraph,
                           replaced_by: Dict[str, str],
                           rc_nodes_with_dispatch: Set[str]):
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
    """
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


# ---------------------------------------------------------------------------
# VALIDATIE
# ---------------------------------------------------------------------------

def _is_valid_entry_structure(G: nx.MultiDiGraph,
                                start_node: str,
                                instance_nodes: Set[str]) -> bool:
    """Controleert of de structuur alleen via start_node wordt binnengegaan."""
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

def _filter_strict(G: nx.MultiDiGraph,
                    sub: CanonicalSubstructure,
                    sub_mapping: Dict[str, str],
                    processed_nodes: Set[str]) -> Tuple[List, bool]:
    """
    Harde filter (EquivalenceClosure): bij eerste ongeldige locatie
    wordt de hele groep afgewezen. --> werd eerder toegepast bij EquivalenceClosure variant.
    """
    valid = []
    for loc in sub.locations:
        if any(n in processed_nodes for n in loc.all_nodes):
            return [], False
        if not _is_valid_entry_structure(G, loc.start_node, set(loc.all_nodes)):
            return [], False
        valid.append((loc, _build_instance_mapping(loc, sub_mapping)))
    return valid, True


def _filter_soft(G: nx.MultiDiGraph,
                  sub: CanonicalSubstructure,
                  sub_mapping: Dict[str, str],
                  processed_nodes: Set[str]) -> Tuple[List, bool]:
    """
    Zachte filter (NoEquivalenceClosure): ongeldige (namelijk incoming edges op nodes <> startnode)
    of overlappende locaties (want al eerder gefactoriseerd) worden overgeslagen, 
    de rest wordt wel geprobeerd.
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
        valid.append((loc, _build_instance_mapping(loc, sub_mapping)))
        nodes_in_batch.update(loc_nodes)

    return valid, True  # groep altijd geldig; commit-beslissing via len(valid) >= 2


# ---------------------------------------------------------------------------
# APPLY
# ---------------------------------------------------------------------------

def apply_factorization(G: nx.MultiDiGraph,
                         results: List[CanonicalSubstructure],
                         strict_filter: bool = True) -> nx.MultiDiGraph:
    processed_nodes: Set[str] = set()
    nodes_to_remove: Set[str] = set()
    replaced_by: Dict[str, str] = {}
    rc_nodes_with_dispatch: Set[str] = set()
    _filter = _filter_strict if strict_filter else _filter_soft

    for sub_id, sub in enumerate(results):
        sub_name = f"subroutine_{sub_id}"
        sub_mapping = {node: f"SUB_{sub_id}_{j}"
                       for j, node in enumerate(sub.canonical_nodes)}

        valid_locations, is_group_valid = _filter(G, sub, sub_mapping, processed_nodes)

        if is_group_valid and len(valid_locations) >= 2:
            _create_subroutine_structure(G, sub, sub_id)

            for loc, instance_mapping in valid_locations:
                rc_id = f"RC_{loc.start_node}"
                _replace_instance_with_rc(G, loc, sub_name, instance_mapping)
                rc_nodes_with_dispatch.add(rc_id)

                for original_node in loc.all_nodes:
                    replaced_by[original_node] = rc_id

                nodes_to_remove.update(loc.all_nodes)
                processed_nodes.update(loc.all_nodes)

    G.remove_nodes_from(nodes_to_remove)
    _update_dispatch_maps(G, replaced_by, rc_nodes_with_dispatch)

    return G

# ---------------------------------------------------------------------------
# OPSLAAN
# ---------------------------------------------------------------------------

# def save_dot(G: nx.MultiDiGraph, filename: str):
#     try:
#         nx.drawing.nx_pydot.write_dot(G, filename)
#         print(f"Gefactoriseerde graaf opgeslagen: {filename}")
#     except Exception as e:
#         print(f"Fout bij opslaan: {e}")

def save_dot(G: nx.MultiDiGraph, filename: str):
    # 1. Maak een tijdelijke DiGraph voor de export
    export_G = nx.DiGraph()

    # Neem globale graaf-attributen over (zoals name="bigSmall")
    export_G.graph.update(G.graph)

    # 2. Kopieer nodes en maak dicts veilig voor DOT
    for node, data in G.nodes(data=True):
        clean_attrs = {}
        for k, v in data.items():
            if isinstance(v, dict):
                clean_attrs[k] = str(v)
            elif v is not None:
                clean_attrs[k] = str(v).strip('"')
        export_G.add_node(node, **clean_attrs)

    # 3. Verzamel ALLE unieke edges en hun attributen
    all_unique_edges = set()
    edge_groups = defaultdict(list)
    edge_metadata = {}

    for u, v, data in G.edges(data=True):
        all_unique_edges.add((u, v))
        
        # Verzamel labels als ze bestaan
        if 'label' in data:
            edge_groups[(u, v)].append(str(data['label']).strip('"'))
        
        # Bewaar overige metadata (van de eerste edge die we zien)
        if (u, v) not in edge_metadata:
            edge_metadata[(u, v)] = {k: val for k, val in data.items() if k != 'label'}

    # 4. Voeg alle edges toe aan de nieuwe graaf
    for u, v in all_unique_edges:
        labels = edge_groups.get((u, v), [])
        meta = edge_metadata.get((u, v), {})
        
        if labels:
            # Combineer labels met een komma
            combined_label = ",".join(sorted(set(labels)))
            export_G.add_edge(u, v, label=combined_label, **meta)
        else:
            # Voeg edge toe zonder label (zoals __start0 -> q0)
            export_G.add_edge(u, v, **meta)

    # 5. Opslaan via pydot
    try:
        pd_graph = nx.drawing.nx_pydot.to_pydot(export_G)
        pd_graph.write_raw(filename)
        print(f"Gefactoriseerde graaf succesvol opgeslagen: {filename}")
    except Exception as e:
        print(f"Fout bij opslaan: {e}")