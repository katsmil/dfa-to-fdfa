# import networkx as nx
# from collections import defaultdict
# from typing import List, Set, Dict
# from analyze import CanonicalSubstructure

# def create_subroutine_structure(G: nx.MultiDiGraph, sub: CanonicalSubstructure, sub_id: int):
#     """
#     Bouwt de abstracte subroutine op basis van de blueprint.
#     """
#     cluster_name = f"subroutine_{sub_id}"
#     # Index 0 is ALTIJD de entry node (gegarandeerd door Analyse BFS)
#     sub_mapping = {node: f"SUB_{sub_id}_{j}" for j, node in enumerate(sub.canonical_nodes)}

#     for i, sub_node in sub_mapping.items():
#         G.add_node(sub_node, cluster=cluster_name, label=f"S{i}")

#     # Dummy start pijl naar S0
#     start_dummy = f"__start_{cluster_name}"
#     G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
#     G.add_edge(start_dummy, sub_mapping[0])

#     # Bouw interne transities strikt volgens blueprint
#     for edge in sub.blueprint_edges:
#         G.add_edge(sub_mapping[edge.source_idx], sub_mapping[edge.target_idx], label=edge.label)

#     return cluster_name, sub_mapping

# def _process_exits(G: nx.MultiDiGraph, instance_nodes: Set[str], sub_map: Dict[str, str], rc_id: str):
#     """Handelt transities af die de subroutine verlaten."""
#     dispatch_map = defaultdict(dict)  # dispatch_map[symbol][sub_frontier_node] = target
    
#     for inst_node in instance_nodes:
#         sub_node = sub_map[inst_node]
#         for _, target, data in list(G.out_edges(inst_node, data=True)):
#             label = data.get('label')
#             if target not in instance_nodes:
#                 # δret(rc, sub_frontier_node, symbol) = target
#                 dispatch_map[label][sub_node] = target
                
#                 # Edge van RC naar target in hoofdgraaf
#                 if not G.has_edge(rc_id, target, key=label):
#                     G.add_edge(rc_id, target, label=label, key=label)
                
#                 # Markeer frontier nodes in subroutine
#                 G.nodes[sub_node].update({
#                     "peripheries": 2,
#                     "fillcolor": "lightblue",
#                     "style": "filled"
#                 })

#     # --- Sla de UITVOERBARE dispatch map op als node attribuut ---
#     # Structuur: { symbol: { sub_frontier_node: target_node } }
#     G.nodes[rc_id]['dispatch_map'] = dict(dispatch_map)

#     # --- Visueel label met dispatch tabel ---
#     visual_rows = [
#         f'"{l}": {", ".join(nodes.keys())}'
#         for l, nodes in dispatch_map.items()
#     ]
#     mapping_str = "\\n".join(visual_rows)
#     if mapping_str:
#         G.nodes[rc_id]['label'] = f"{G.nodes[rc_id]['label']}\\n[{mapping_str}]"

# def apply_factorization(G: nx.MultiDiGraph, results: List[CanonicalSubstructure]):
#     """
#     Past factorisatie toe. Filtert per locatie op overlap (globaal én lokaal) en geldigheid.
#     Commit alleen als er >= 2 geldige locaties overblijven.
#     """
#     processed_nodes = set() # Houdt bij welke nodes AL VERWIJDERD zijn door eerdere subroutines
#     nodes_to_remove = set()

#     print(f"Start factorisatie met {len(results)} kandidaat-structuren...")

#     for i, sub in enumerate(results):
#         sub_id = i
#         valid_locations_to_process = []
        
#         # Houdt bij welke nodes we claimen voor DEZE specifieke subroutine (om interne overlap te voorkomen)
#         nodes_in_current_batch = set()

#         # --- FILTER FASE ---
#         for loc in sub.locations:
#             loc_nodes_set = set(loc.all_nodes)

#             # CHECK 1: Globale Overlap
#             # Is een van deze nodes al gebruikt in een VORIGE factorisatie?
#             if any(n in processed_nodes for n in loc_nodes_set):
#                 continue

#             # CHECK 2: Lokale Overlap
#             # Overlapt deze locatie met een locatie die we Zojuist in deze lus hebben goedgekeurd?
#             if any(n in nodes_in_current_batch for n in loc_nodes_set):
#                 continue

#             # CHECK 3: Valide Entry?
#             # Kan de graaf hier netjes losgeknipt worden?
#             if not _is_valid_entry_structure(G, loc.start_node, loc_nodes_set):
#                 continue

#             # Als we hier zijn, is de locatie geldig en vrij.
#             valid_locations_to_process.append(loc)
#             nodes_in_current_batch.update(loc_nodes_set)

#         # --- COMMIT FASE ---
#         # We gaan pas bouwen als we minimaal 2 valide locaties overhouden
#         if len(valid_locations_to_process) >= 2:
#             # 1. Bouw de subroutine 'echt' in de graaf
#             cluster_name, sub_mapping = create_subroutine_structure(G, sub, sub_id)
            
#             print(f"  > Subroutine {sub_id} toegepast op {len(valid_locations_to_process)} locaties.")

#             for loc in valid_locations_to_process:
#                 rc_id = f"RC_{loc.start_node}"
#                 G.add_node(rc_id, shape='box', style='filled', fillcolor='orange', label=f"RC: {cluster_name}")
                
#                 # Mapping: Echte Node -> Subroutine Node (via Index)
#                 instance_map = {node_name: sub_mapping[idx] for idx, node_name in enumerate(loc.all_nodes)}
                
#                 # 2. Buig inkomende transities om naar de RC node
#                 for u, v, data in list(G.in_edges(loc.start_node, data=True)):
#                     if u not in loc.all_nodes:
#                         G.add_edge(u, rc_id, **data)
                
#                 # 3. Verwerk exits en update dispatch table
#                 _process_exits(G, set(loc.all_nodes), instance_map, rc_id)
            
#             # 4. Nu pas voegen we deze nodes toe aan de globale processed lijst
#             processed_nodes.update(nodes_in_current_batch)
#             nodes_to_remove.update(nodes_in_current_batch)
#         else:
#             # Als er na filtering < 2 overblijven, doen we niets met deze groep
#             pass

#     # Ruim alle vervangen nodes in één keer op
#     G.remove_nodes_from(nodes_to_remove)
#     return G

# # Helper voor validatie (uit je eerdere snippets)
# def _is_valid_entry_structure(G: nx.MultiDiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
#     """
#     Controleert of de structuur alleen via de start_node wordt binnengegaan.
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
#         print(f"Gefactoriseerde graaf opgeslagen: {filename}")
#     except Exception as e:
#         print(f"Fout bij opslaan: {e}")


import networkx as nx
from collections import defaultdict
from typing import List, Set, Dict
from analyze import CanonicalSubstructure

def create_subroutine_structure(G: nx.MultiDiGraph, sub: CanonicalSubstructure, sub_id: int):
    """
    Bouwt de abstracte subroutine op basis van de blueprint.
    """
    cluster_name = f"subroutine_{sub_id}"
    # Index 0 is ALTIJD de entry node (gegarandeerd door Analyse BFS)
    sub_mapping = {i: f"SUB_{sub_id}_{i}" for i in range(sub.nodes_count)}

    for i, sub_node in sub_mapping.items():
        G.add_node(sub_node, cluster=cluster_name, label=f"S{i}")

    # Dummy start pijl naar S0
    start_dummy = f"__start_{cluster_name}"
    G.add_node(start_dummy, label="", shape="none", width="0", height="0", cluster=cluster_name)
    G.add_edge(start_dummy, sub_mapping[0])

    # Bouw interne transities strikt volgens blueprint
    for edge in sub.blueprint_edges:
        G.add_edge(sub_mapping[edge.source_idx], sub_mapping[edge.target_idx], label=edge.label)

    return cluster_name, sub_mapping

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

def apply_factorization(G: nx.MultiDiGraph, results: List[CanonicalSubstructure]):
    """
    Past factorisatie toe. Filtert per locatie op overlap (globaal én lokaal) en geldigheid.
    Commit alleen als er >= 2 geldige locaties overblijven.
    """
    processed_nodes = set() # Houdt bij welke nodes AL VERWIJDERD zijn door eerdere subroutines
    nodes_to_remove = set()

    print(f"Start factorisatie met {len(results)} kandidaat-structuren...")

    for i, sub in enumerate(results):
        sub_id = i
        valid_locations_to_process = []
        
        # Houdt bij welke nodes we claimen voor DEZE specifieke subroutine (om interne overlap te voorkomen)
        nodes_in_current_batch = set()

        # --- FILTER FASE ---
        for loc in sub.locations:
            loc_nodes_set = set(loc.all_nodes)

            # CHECK 1: Globale Overlap
            # Is een van deze nodes al gebruikt in een VORIGE factorisatie?
            if any(n in processed_nodes for n in loc_nodes_set):
                continue

            # CHECK 2: Lokale Overlap
            # Overlapt deze locatie met een locatie die we Zojuist in deze lus hebben goedgekeurd?
            if any(n in nodes_in_current_batch for n in loc_nodes_set):
                continue

            # CHECK 3: Valide Entry?
            # Kan de graaf hier netjes losgeknipt worden?
            if not _is_valid_entry_structure(G, loc.start_node, loc_nodes_set):
                continue

            # Als we hier zijn, is de locatie geldig en vrij.
            valid_locations_to_process.append(loc)
            nodes_in_current_batch.update(loc_nodes_set)

        # --- COMMIT FASE ---
        # We gaan pas bouwen als we minimaal 2 valide locaties overhouden
        if len(valid_locations_to_process) >= 2:
            # 1. Bouw de subroutine 'echt' in de graaf
            cluster_name, sub_mapping = create_subroutine_structure(G, sub, sub_id)
            
            print(f"  > Subroutine {sub_id} toegepast op {len(valid_locations_to_process)} locaties.")

            for loc in valid_locations_to_process:
                rc_id = f"RC_{loc.start_node}"
                G.add_node(rc_id, shape='box', style='filled', fillcolor='orange', label=f"RC: {cluster_name}")
                
                # Mapping: Echte Node -> Subroutine Node (via Index)
                instance_map = {node_name: sub_mapping[idx] for idx, node_name in enumerate(loc.all_nodes)}
                
                # 2. Buig inkomende transities om naar de RC node
                for u, v, data in list(G.in_edges(loc.start_node, data=True)):
                    if u not in loc.all_nodes:
                        G.add_edge(u, rc_id, **data)
                
                # 3. Verwerk exits en update dispatch table
                _process_exits(G, set(loc.all_nodes), instance_map, rc_id)
            
            # 4. Nu pas voegen we deze nodes toe aan de globale processed lijst
            processed_nodes.update(nodes_in_current_batch)
            nodes_to_remove.update(nodes_in_current_batch)
        else:
            # Als er na filtering < 2 overblijven, doen we niets met deze groep
            pass

    # Ruim alle vervangen nodes in één keer op
    G.remove_nodes_from(nodes_to_remove)
    return G

# Helper voor validatie (uit je eerdere snippets)
def _is_valid_entry_structure(G: nx.MultiDiGraph, start_node: str, instance_nodes: Set[str]) -> bool:
    """
    Controleert of de structuur alleen via de start_node wordt binnengegaan.
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
        print(f"Gefactoriseerde graaf opgeslagen: {filename}")
    except Exception as e:
        print(f"Fout bij opslaan: {e}")