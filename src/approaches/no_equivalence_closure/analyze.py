import networkx as nx
from collections import defaultdict
from typing import List, Tuple, Dict, Set

from approaches.shared.base_analyzer import BaseSubstructureAnalyzer
from approaches.shared.shared_types import MatchLocation, BlueprintSubstructure, BlueprintEdge
from approaches.shared.shared_utils import count_non_overlapping_locations, get_internals_and_frontiers, build_signature_buckets

# ---------------------------------------------------------------------------
# ANALYSIS ENGINE
# ---------------------------------------------------------------------------

class SubstructureAnalyzer(BaseSubstructureAnalyzer):
    """
    Minimal subclass for the NoEquivalenceClosure approach.
    This variant aims to maximize net gain compression.
    """

    def _build_match_output(self, start_a, start_b, visited_pairs, blueprint_edges):
        nodes_a = tuple(p[0] for p in visited_pairs)
        nodes_b = tuple(p[1] for p in visited_pairs)

        internals_a, frontiers_a = get_internals_and_frontiers(self, nodes_a)
        internals_b, frontiers_b = get_internals_and_frontiers(self, nodes_b)

        return {
            'start_a': start_a,
            'start_b': start_b,
            'nodes_a': nodes_a,
            'nodes_b': nodes_b,
            'internals_a': internals_a,
            'frontiers_a': frontiers_a,
            'internals_b': internals_b,
            'frontiers_b': frontiers_b,
            'blueprint_edges': blueprint_edges,
        }

# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[BlueprintSubstructure]:
    """
    Find repeating substructures in G and group them by blueprint topology.
    Returns a list of unique BlueprintSubstructure objects, sorted by compression potential.
    """
    analyzer = SubstructureAnalyzer(G, min_overlap=min_size)
    buckets = build_signature_buckets(analyzer)

    # structure_registry: group all found locations by their blueprint topology (edges_tuple)
    structure_registry: Dict[tuple, Set[MatchLocation]] = defaultdict(set)
    # blueprint_store: stores the edge structure (as BlueprintEdge tuples) for each blueprint
    blueprint_store: Dict[tuple, Tuple[BlueprintEdge, ...]] = {}
    # blueprint_nodes_store: stores the node names (as tuple) for each blueprint
    blueprint_nodes_store: Dict[tuple, Tuple[str, ...]] = {}

    # For each bucket (signature group), compare all pairs to find maximal overlaps
    for nodes in buckets.values():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                match = analyzer._find_maximal_overlap(nodes[i], nodes[j])
                if not match:
                    continue

                # edges_tuple identifies the blueprint topology (structure, not node names)
                edges_tuple = tuple(sorted(
                    (e.source_idx, e.target_idx, e.label)
                    for e in match['blueprint_edges']
                ))

                # Add both A- and B-side locations to the registry for this blueprint
                structure_registry[edges_tuple].add(MatchLocation(
                    start_node=match['start_a'],
                    all_nodes=match['nodes_a'],
                    internals=match['internals_a'],
                    frontiers=match['frontiers_a'],
                ))
                structure_registry[edges_tuple].add(MatchLocation(
                    start_node=match['start_b'],
                    all_nodes=match['nodes_b'],
                    internals=match['internals_b'],
                    frontiers=match['frontiers_b'],
                ))

                # Store the blueprint structure and node order (only once per blueprint)
                if edges_tuple not in blueprint_store:
                    blueprint_store[edges_tuple] = tuple(match['blueprint_edges'])
                    blueprint_nodes_store[edges_tuple] = match['nodes_a']

    results = []
    # Build BlueprintSubstructure objects for each unique blueprint
    for edges_tuple, locations in structure_registry.items():
        loc_tuple = tuple(locations)
        results.append(BlueprintSubstructure(
            blueprint_nodes=blueprint_nodes_store[edges_tuple],
            overlap_size=len(loc_tuple[0].all_nodes),
            locations=loc_tuple,
            blueprint_edges=blueprint_store[edges_tuple],
        ))

    eff = count_non_overlapping_locations
    
    # Sort by (overlap_size * non-overlapping locations), descending
    return sorted(
        results,
        key=lambda x: (x.overlap_size * eff(x.locations), x.overlap_size),
        reverse=True,
    )