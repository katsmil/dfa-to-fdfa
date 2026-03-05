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
        G.add_node(sub_mapping[orig_node], cluster=cluster_name, label=f"S{j}")

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


# ---------------------------------------------------------------------------
# INSTANTIE VERVANGING
# ---------------------------------------------------------------------------

def _build_instance_mapping(loc: MatchLocation,
                              sub_mapping: Dict[str, str]) -> Dict[str, str]:
    """Koppelt concrete nodes van deze instantie aan SUB-nodes via positievolgorde."""
    return {loc_node: sub_mapping[cn]
            for loc_node, cn in zip(loc.all_nodes, sub_mapping.keys())}


def _process_exits(G: nx.MultiDiGraph,
                    loc: MatchLocation,
                    instance_mapping: Dict[str, str],
                    rc_id: str):
    """
    Handelt transities af die de subroutine verlaten.
    Itereert alleen loc.frontiers — nodes met externe uitgaande edges.
    """
    dispatch_map = defaultdict(dict)
    instance_nodes = set(loc.all_nodes)

    for frontier_node in loc.frontiers:
        sub_node = instance_mapping[frontier_node]
        for _, target, data in list(G.out_edges(frontier_node, data=True)):
            label = data.get('label')
            if target not in instance_nodes:
                dispatch_map[label][sub_node] = target
                if not G.has_edge(rc_id, target, key=label):
                    G.add_edge(rc_id, target, label=label, key=label)
                G.nodes[sub_node].update({
                    "peripheries": 2,
                    "fillcolor": "lightblue",
                    "style": "filled",
                })

    G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

    visual_rows = [f'"{l}": {", ".join(nodes.keys())}'
                   for l, nodes in dispatch_map.items()]
    mapping_str = "\\n".join(visual_rows)
    if mapping_str:
        G.nodes[rc_id]['label'] = f"{G.nodes[rc_id]['label']}\\n[{mapping_str}]"


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
    """
    Past factorisatie toe op alle kandidaat-structuren.

    strict_filter=True  (EquivalenceClosure):    harde filter, hele groep
                                                 afwijzen bij eerste ongeldige locatie.
    strict_filter=False (NoEquivalenceClosure):  zachte filter, ongeldige locaties
                                                 overslaan en rest committen.
    """
    processed_nodes: Set[str] = set()
    nodes_to_remove: Set[str] = set()
    _filter = _filter_strict if strict_filter else _filter_soft

    print(f"Start factorisatie met {len(results)} kandidaat-structuren...")

    for sub_id, sub in enumerate(results):
        sub_name = f"subroutine_{sub_id}"
        sub_mapping = {node: f"SUB_{sub_id}_{j}"
                       for j, node in enumerate(sub.canonical_nodes)}

        valid_locations, is_group_valid = _filter(G, sub, sub_mapping, processed_nodes)

        if is_group_valid and len(valid_locations) >= 2:
            _create_subroutine_structure(G, sub, sub_id)

            for loc, instance_mapping in valid_locations:
                _replace_instance_with_rc(G, loc, sub_name, instance_mapping)
                nodes_to_remove.update(loc.all_nodes)
                processed_nodes.update(loc.all_nodes)

            print(f"Succes: {sub_name} gefactoriseerd op {len(valid_locations)} locaties.")
        elif not is_group_valid:
            print(f"Overgeslagen: {sub_name} bevat ongeldige of overlappende locaties.")

    G.remove_nodes_from(nodes_to_remove)
    return G


# ---------------------------------------------------------------------------
# OPSLAAN
# ---------------------------------------------------------------------------

def save_dot(G: nx.MultiDiGraph, filename: str):
    try:
        nx.drawing.nx_pydot.write_dot(G, filename)
        print(f"Gefactoriseerde graaf opgeslagen: {filename}")
    except Exception as e:
        print(f"Fout bij opslaan: {e}")