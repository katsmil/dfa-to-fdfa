import networkx as nx
from collections import defaultdict
from typing import List, Set, Dict, Tuple, Optional

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
                   label=f"sub{sub_id}.{j}",
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
    If the node was already tagged by a previous factorization run (via the
    'originally_accepting' attribute), that value is used directly — this
    prevents peripheries=2 frontier markers from being misread as accepting
    states during the second run.
    """
    nd = G.nodes[node]
    oa = nd.get('originally_accepting')
    if oa is not None:
        return str(oa).strip().strip('"').strip("'").lower() == 'true'
    shape = str(nd.get('shape', '')).strip().strip('"').strip("'")
    peripheries = str(nd.get('peripheries', '')).strip().strip('"').strip("'")
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
        rc_attrs = dict(shape='box', style='filled', fillcolor='orange',
                        label=f"RC: {sub_name}")
        # Erf cluster over van de vervangen startnode (nodig voor tweede-iteratie nesting)
        start_cluster = G.nodes[loc.start_node].get('cluster')
        if start_cluster:
            rc_attrs['cluster'] = start_cluster
            # peripheries=2 wordt pas gezet na _process_exits (zie hieronder).
        G.add_node(rc_id, **rc_attrs)

    instance_nodes = set(loc.all_nodes)
    for u, v, data in list(G.in_edges(loc.start_node, data=True)):
        if u not in instance_nodes:
            G.add_edge(u, rc_id, **data)

    _process_exits(G, loc, instance_mapping, rc_id)

    # Een geneste RC node is alleen een frontier van zijn moeder-subroutine als
    # minstens één van de vervangen instance-nodes zelf al frontier was
    # (peripheries=2). De RC node neemt dan de frontier-rol van die node over.
    #
    # Let op: als de dispatch-target van deze RC node een frontier is, wordt de
    # RC node zelf NIET frontier — de controle keert terug naar de aanroeper
    # vanuit die frontier-node, niet vanuit de RC node.
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
    replaced by nodes from a new inner subroutine: the callers of the outer
    subroutine need their frontier-key references updated to the new SUB nodes.
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

    # Update dispatch_map KEYS for all RC nodes when blueprint frontier nodes were
    # removed and replaced by nodes from a new inner subroutine (second-run case).
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

def _build_dispatch_signatures(G: nx.MultiDiGraph) -> Dict[str, Dict[str, str]]:
    """
    Bouw per node een 'dispatch signature': {symbol: target} over alle RC nodes
    waarvan de dispatch_map deze node als frontier-key bevat.

    Twee nodes die dezelfde canonicale positie in een subroutine innemen mogen
    alleen samengevoegd worden als hun dispatch-signaturen identiek zijn.
    Anders zou het samenvoegen informatie vernietigen in de dispatch_map van de
    aanroepende RC node.
    """
    import ast as _ast
    signatures: Dict[str, Dict[str, str]] = {}
    for _, data in G.nodes(data=True):
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
        for sym, sub_to_target in dm.items():
            if not isinstance(sub_to_target, dict):
                continue
            for frontier_node, target in sub_to_target.items():
                signatures.setdefault(frontier_node, {})[sym] = target
    return signatures


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
                  processed_nodes: Set[str],
                  dispatch_signatures: Optional[Dict[str, Dict[str, str]]] = None) -> Tuple[List, bool]:
    """
    Zachte filter (NoEquivalenceClosure): ongeldige of overlappende locaties worden
    overgeslagen, de rest wordt geprobeerd.

    Extra check (dispatch_signatures): twee locaties mogen alleen samengevoegd worden
    als voor elke canonicale positie de bijbehorende nodes identieke dispatch-signaturen
    hebben in alle aanroepende RC nodes. Zo niet, dan zijn de nodes functioneel
    onderscheidbaar en mag samenvoeging de dispatch_map van aanroepers niet beschadigen.
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

        # Dispatch-signature check: elke node in deze locatie moet dezelfde
        # dispatch-signature hebben als de corresponderende node in de eerste
        # reeds geaccepteerde locatie (of de canonical nodes als er nog geen is).
        if dispatch_signatures is not None and valid:
            first_nodes = valid[0][0].all_nodes
            compatible = True
            for ref_node, cand_node in zip(first_nodes, loc.all_nodes):
                ref_sig  = dispatch_signatures.get(ref_node,  {})
                cand_sig = dispatch_signatures.get(cand_node, {})
                if ref_sig != cand_sig:
                    compatible = False
                    break
            if not compatible:
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
    frontier_key_replacements: Dict[str, str] = {}  # loc_node → rc_id  (dispatch_map key updates)
    sub_node_peripheries: Dict[str, str] = {}       # loc_node → sub_node (peripheries propagation)
    _filter = _filter_strict if strict_filter else _filter_soft

    # Pre-compute dispatch signatures for the incompatibility check in _filter_soft.
    # Only needed for the soft filter; computed once over the current graph state.
    dispatch_signatures: Optional[Dict[str, Dict[str, str]]] = (
        _build_dispatch_signatures(G) if not strict_filter else None
    )

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
                       for j, node in enumerate(sub.canonical_nodes)}

        valid_locations, is_group_valid = _filter(
            G, sub, sub_mapping, processed_nodes, dispatch_signatures
        ) if not strict_filter else _filter(G, sub, sub_mapping, processed_nodes)

        if is_group_valid and len(valid_locations) >= 2:
            _create_subroutine_structure(G, sub, sub_id)

            for loc, instance_mapping in valid_locations:
                rc_id = f"RC_{loc.start_node}"
                _replace_instance_with_rc(G, loc, sub_name, instance_mapping)
                rc_nodes_with_dispatch.add(rc_id)

                # Track which concrete nodes are replaced by this RC node.
                # Used to update dispatch_map KEYS in outer RC nodes: the old
                # frontier keys (e.g. SUB_29_1, SUB_29_2) are replaced by the
                # nested RC node (e.g. RC_SUB_29_1) which acts as the new
                # frontier of the parent subroutine.
                for loc_node in loc.all_nodes:
                    frontier_key_replacements[loc_node] = rc_id

                # Separate mapping used to propagate peripheries=2 to the
                # canonical SUB nodes of the inner subroutine.  These nodes
                # inherited their frontier status from the blueprint nodes they
                # replaced, but _process_exits cannot detect it (blueprint nodes
                # have no graph-level external edges — those live in dispatch_maps).
                for loc_node, sub_node in instance_mapping.items():
                    sub_node_peripheries[loc_node] = sub_node

                for original_node in loc.all_nodes:
                    replaced_by[original_node] = rc_id

                nodes_to_remove.update(loc.all_nodes)
                processed_nodes.update(loc.all_nodes)

    # Propagate peripheries=2 to the canonical SUB nodes of inner subroutines.
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