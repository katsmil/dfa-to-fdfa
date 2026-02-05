import networkx as nx 
from typing import List, Set, Dict
from collections import defaultdict
from bisimilar.previous.analyzer_0 import SubstructureMatch

# --- HULPFUNCTIES --- 
def _get_out_labels(G: nx.DiGraph, node: str) -> Dict[str, str]: 
    """Geeft een dictionary van label -> target_node.""" 
    return {data.get('label'): target for _, target, data in G.out_edges(node, data=True) if 'label' in data} 

# --- SUBROUTINE LOGICA --- 
def create_subroutine_structure(G: nx.DiGraph, 
                                canonical_nodes: Set[str],
                                cluster_id: int, 
                                canonical_start: str):
    """Initialiseert de externe subroutine structuur."""
    sub_mapping = {node: f"SUB_{canonical_start}_{node}" for node in canonical_nodes}
    cluster_name = f"subroutine_{canonical_start}_{cluster_id}"

    for orig_node, sub_node in sub_mapping.items():
        attrs = G.nodes[orig_node].copy() if orig_node in G.nodes else {}
        attrs.update({'cluster': cluster_name, 'label': f"{orig_node}"})
        G.add_node(sub_node, **attrs)

    if canonical_start in sub_mapping:
        start_dummy = f"__start_{cluster_name}"
        G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
        G.add_edge(start_dummy, sub_mapping[canonical_start])

    # Initiële interne edges op basis van de blueprint
    for orig_node in canonical_nodes:
        sub_source = sub_mapping[orig_node]
        for _, orig_target, data in list(G.out_edges(orig_node, data=True)):
            if orig_target in canonical_nodes:
                G.add_edge(sub_source, sub_mapping[orig_target], **data)

    return cluster_name, sub_mapping

# --- FACTORISATIE KERN --- 
def _is_valid_entry_structure(G: nx.DiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
    for node in instance_nodes:
        if node == start_node:
            continue
        for source, _ in G.in_edges(node):
            if source not in instance_nodes:
                return False
    return True

def _process_transitions_and_update_subroutine(
    G: nx.DiGraph,
    instance_nodes: Set[str],
    sub_mapping: Dict[str, str],
    rc_node_id: str
):
    """Verwerkt transities en werkt de subroutine-definitie bij."""
    # Set om bij te houden welke (label, target) we al hebben toegevoegd aan deze RC node
    processed_exits = set()

    for inst_node in instance_nodes:
        sub_node = sub_mapping.get(inst_node)
        if not sub_node:
            continue

        sub_out_labels = _get_out_labels(G, sub_node)

        for _, target, data in list(G.out_edges(inst_node, data=True)):
            label = data.get("label")
            if not label: continue

            # EXIT: Transitie naar buiten de instantie
            if target not in instance_nodes:
                # Check of we deze specifieke uitgang (label + doel) al getekend hebben vanaf de RC
                exit_id = (label, target)
                if exit_id not in processed_exits:
                    G.add_edge(rc_node_id, target, **data)
                    processed_exits.add(exit_id)

                # Update de status van de subroutine-node (idempotent)
                G.nodes[sub_node].update({
                    "peripheries": 2, "status": "accepting",
                    "fillcolor": "lightblue", "style": "filled",
                })

            # INTERN: Voeg pad toe aan subroutine indien nieuw
            else:
                if label not in sub_out_labels:
                    sub_target = sub_mapping.get(target)
                    if sub_target:
                        G.add_edge(sub_node, sub_target, **data)
                        sub_out_labels[label] = sub_target

def _replace_instance_with_rc(G: nx.DiGraph,
                             start_node: str,
                             instance_nodes: Set[str],
                             subroutine_name: str,
                             sub_mapping: Dict[str, str]) -> Set[str]:
    rc_node_id = f"RC_{start_node}"

    if not G.has_node(rc_node_id):
        G.add_node(rc_node_id, shape='box', style='filled', fillcolor='orange',
                   label=f"RC: {subroutine_name}")

    # 1. Inkomende edges ombuigen
    for u, v, data in list(G.in_edges(start_node, data=True)):
        if u not in instance_nodes:
            G.add_edge(u, rc_node_id, **data)

    # 2. Exits naar RC verplaatsen en subroutine verrijken
    _process_transitions_and_update_subroutine(G, instance_nodes, sub_mapping, rc_node_id)

    return instance_nodes

def _is_deterministic_with_subroutine(G: nx.DiGraph, 
                                     instance_nodes: Set[str], 
                                     sub_mapping: Dict[str, str]) -> bool:
    for inst_node in instance_nodes:
        sub_node = sub_mapping.get(inst_node)
        if not G.has_node(sub_node):
            continue

        sub_out_labels = _get_out_labels(G, sub_node)
        inst_out_edges = _get_out_labels(G, inst_node)

        for label, inst_target in inst_out_edges.items():
            if inst_target in instance_nodes:
                sub_target_of_inst = sub_mapping.get(inst_target)
                if label in sub_out_labels:
                    if sub_out_labels[label] != sub_target_of_inst:
                        return False
    return True

def apply_factorization(G: nx.DiGraph, results: List[SubstructureMatch]):
    all_nodes_to_remove = set()
    processed_starts = set() 
    
    groups = defaultdict(list)
    for res in results:
        groups[res.start_nodes[0]].append(res)
        
    sorted_canonicals = sorted(groups.keys(), key=lambda k: groups[k][0].overlap_size, reverse=True)

    for i, canonical_start in enumerate(sorted_canonicals):
        matches = groups[canonical_start]
        sub_name = f"Sub_{canonical_start}"
        nodes_blueprint = {p[0] for p in matches[0].all_pairs}
        
        if _is_valid_entry_structure(G, canonical_start, nodes_blueprint):
            # 1. Initialiseer de Subroutine (Blauwdruk)
            _, global_sub_mapping = create_subroutine_structure(G, nodes_blueprint, i, canonical_start)
            
            for m in matches:
                for idx, start_node in enumerate(m.start_nodes):
                    if start_node not in processed_starts:
                        current_nodes = {p[idx] for p in m.all_pairs}
                        current_mapping = {p[idx]: global_sub_mapping[p[0]] for p in m.all_pairs}
                        
                        if _is_valid_entry_structure(G, start_node, current_nodes):
                            if _is_deterministic_with_subroutine(G, current_nodes, current_mapping):
                                to_rem = _replace_instance_with_rc(G, start_node, current_nodes, sub_name, current_mapping)
                                all_nodes_to_remove.update(to_rem)
                                processed_starts.add(start_node)
                            else:
                                print(f"Skipping instantie {start_node}: veroorzaakt nondeterminisme in subroutine.")

    G.remove_nodes_from(all_nodes_to_remove)
    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")
