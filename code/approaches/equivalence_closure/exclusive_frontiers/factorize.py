import networkx as nx 
from typing import List, Set, Dict
from collections import defaultdict
from analyze import CanonicalSubstructure

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

# def _process_transitions_and_update_subroutine(
#     G: nx.DiGraph,
#     instance_nodes: Set[str],
#     sub_mapping: Dict[str, str],
#     rc_node_id: str
# ):
#     """
#     Bouwt de interne mapping op de RC node.
#     Mapping structuur: { label: { SUB_node_id: target_node_in_main } }
#     """
#     # De interne dispatch tabel
#     # We gebruiken de sub_node ID's voor de mapping
#     dispatch_map = defaultdict(dict)

#     for inst_node in instance_nodes:
#         sub_node = sub_mapping.get(inst_node)
#         if not sub_node: continue
        
#         for _, target, data in list(G.out_edges(inst_node, data=True)):
#             label = data.get("label")
#             if not label: continue

#             # EXIT: Transitie naar buiten de subroutine-instantie
#             if target not in instance_nodes:
#                 # Cruciaal: We mappen de label aan de SUB_node ID
#                 dispatch_map[label][sub_node] = target
                
#                 # Voeg de transitie toe aan de RC node (puur label)
#                 if not G.has_edge(rc_node_id, target, key=label):
#                     G.add_edge(rc_node_id, target, label=label, key=label)

#                 # Update de status van de subroutine-node
#                 G.nodes[sub_node].update({
#                     "peripheries": 2, "status": "accepting",
#                     "fillcolor": "lightblue", "style": "filled",
#                 })
            
#             # # INTERN: De interne logica van de subroutine (blueprint)
#             # else:
#             #     sub_target = sub_mapping.get(target)
#             #     sub_out_labels = _get_out_labels(G, sub_node)
#             #     if label not in sub_out_labels and sub_target:
#             #         G.add_edge(sub_node, sub_target, **data)

#     # Sla de map op als attribuut (voor de stack-machine logica)
#     G.nodes[rc_node_id]['dispatch_map'] = dict(dispatch_map)

#     # Visuele weergave op de RC node voor de DOT-file
#     visual_map = []
#     for label, sub_nodes_dict in dispatch_map.items():
#         # Sorteer de SUB_ namen voor een consistente weergave
#         sub_names = ", ".join(sorted(sub_nodes_dict.keys()))
#         # Gebruik dubbele quotes rond het label voor de duidelijkheid
#         visual_map.append(f'"{label}": {sub_names}')
    
#     # Gebruik \n in plaats van | voor een verticale lijst
#     mapping_str = "\\n".join(visual_map)
#     current_label = G.nodes[rc_node_id].get('label', 'RC')
    
#     # We zetten de mapping tussen vierkante haken op nieuwe regels
#     G.nodes[rc_node_id]['label'] = f"{current_label}\\n[{mapping_str}]"

def _process_exits(G: nx.MultiDiGraph, instance_nodes: Set[str], sub_map: Dict[str, str], rc_id: str):
    """Handelt transities af die de subroutine verlaten."""
    dispatch_map = defaultdict(dict)  # dispatch_map[symbol][sub_frontier_node] = target
    
    for inst_node in instance_nodes:
        sub_node = sub_map[inst_node]
        for _, target, data in list(G.out_edges(inst_node, data=True)):
            label = data.get('label')
            if target not in instance_nodes:
                # δret(rc, sub_frontier_node, symbol) = target
                dispatch_map[label][sub_node] = target
                
                # Edge van RC naar target in hoofdgraaf
                if not G.has_edge(rc_id, target, key=label):
                    G.add_edge(rc_id, target, label=label, key=label)
                
                # Markeer frontier nodes in subroutine
                G.nodes[sub_node].update({
                    "peripheries": 2,
                    "fillcolor": "lightblue",
                    "style": "filled"
                })

    # --- Sla de UITVOERBARE dispatch map op als node attribuut ---
    # Structuur: { symbol: { sub_frontier_node: target_node } }
    G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

    # --- Visueel label met dispatch tabel ---
    visual_rows = [
        f'"{l}": {", ".join(nodes.keys())}'
        for l, nodes in dispatch_map.items()
    ]
    mapping_str = "\\n".join(visual_rows)
    if mapping_str:
        G.nodes[rc_id]['label'] = f"{G.nodes[rc_id]['label']}\\n[{mapping_str}]"

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
    _process_exits(G, instance_nodes, sub_mapping, rc_node_id)

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

def apply_factorization(G: nx.DiGraph, results: List[CanonicalSubstructure]):
    all_nodes_to_remove = set()
    processed_nodes = set() 

    for i, sub in enumerate(results):
        base_start_node = sub.canonical_nodes[0]
        sub_name = f"Sub_{base_start_node}"
        
        # Mapping voorbereiden voor validatie
        global_sub_mapping = {node: f"SUB_{base_start_node}_{node}" for node in sub.canonical_nodes}
        
        # --- STAP 1: PRE-SCAN (Validatie van de gehele groep) ---
        valid_locations_to_process = []
        is_group_valid = True

        for loc in sub.locations:
            # Check overlap
            if any(n in processed_nodes for n in loc.all_nodes):
                # Als een locatie al (deels) bezet is, is dit hele patroon niet meer optimaal
                is_group_valid = False
                break
            
            start_node = loc.all_nodes[0]
            instance_nodes = set(loc.all_nodes)
            current_mapping = dict(zip(loc.all_nodes, 
                                       [global_sub_mapping[cn] for cn in sub.canonical_nodes]))

            # Check technische validiteit
            if _is_valid_entry_structure(G, start_node, instance_nodes) and \
               _is_deterministic_with_subroutine(G, instance_nodes, current_mapping):
                valid_locations_to_process.append((start_node, instance_nodes, current_mapping))
            else:
                # Eén locatie is ongeldig -> we wijzen de hele groep af
                is_group_valid = False
                break

        # --- STAP 2: COMMIT (Alleen als de hele groep valide is) ---
        if is_group_valid and len(valid_locations_to_process) >= 2:
            # Nu pas bouwen we de subroutine fysiek in de graaf
            create_subroutine_structure(
                G, 
                set(sub.canonical_nodes), 
                i, 
                base_start_node
            )

            for start_node, instance_nodes, current_mapping in valid_locations_to_process:
                _replace_instance_with_rc(
                    G, 
                    start_node, 
                    instance_nodes, 
                    sub_name, 
                    current_mapping
                )
                
                all_nodes_to_remove.update(instance_nodes)
                processed_nodes.update(instance_nodes)
            
            print(f"Succes: Structuur {sub_name} gefactoriseerd op {len(valid_locations_to_process)} locaties.")
        else:
            # Groep afgewezen: nodes blijven 'vrij' voor volgende items op de prio-lijst
            if not is_group_valid:
                print(f"Overgeslagen: Structuur {sub_name} bevat ongeldige of overlappende locaties.")

    G.remove_nodes_from(all_nodes_to_remove)
    return G

def save_dot(G, filename):
    """Slaat de graaf op als DOT-bestand."""
    nx.drawing.nx_pydot.write_dot(G, filename)
    print(f"Gefactoriseerde graaf opgeslagen als: {filename}")
