import networkx as nx
from collections import defaultdict
from typing import List, Tuple, Dict, Set

from approaches.shared.base_analyzer import BaseSubstructureAnalyzer
from approaches.shared.factorize import _is_accepting_node
from approaches.shared.shared_types import MatchLocation, BlueprintSubstructure, BlueprintEdge, SubstructureMatch
from approaches.shared.shared_utils import count_non_overlapping_locations, build_signature_buckets

# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def run_analysis(G: nx.MultiDiGraph, min_size: int = 2) -> List[BlueprintSubstructure]:
    """
    Find repeating substructures in G and group them by blueprint topology.
    Returns a list of unique BlueprintSubstructure objects, sorted by compression potential.
    This variant does exhaustive matching (no equivalence pruning), which typically
    yields higher compression at the cost of runtime.
    """
    analyzer = BaseSubstructureAnalyzer(G, min_overlap=min_size)
    buckets = build_signature_buckets(analyzer)

    # structure_registry: group all found locations by their blueprint topology (edges_tuple)
    structure_registry: Dict[tuple, Set[MatchLocation]] = defaultdict(set)
    # blueprint_store: stores the edge structure for each blueprint key
    # Example key (edges_tuple) from input/miscellaneous/bigSmall.dot:
    #   ((0, 1, "1"), (1, 2, "2"), (2, 3, "3"))
    # Example value (Tuple[BlueprintEdge, ...]):
    #   (BlueprintEdge(0, 1, "1"), BlueprintEdge(1, 2, "2"), BlueprintEdge(2, 3, "3"))
    blueprint_store: Dict[tuple, Tuple[BlueprintEdge, ...]] = {}
    # blueprint_nodes_store: stores the node names (as tuple) for each blueprint
    # Example key (edges_tuple) from input/miscellaneous/bigSmall.dot:
    #   ((0, 1, "1"), (1, 2, "2"), (2, 3, "3"))
    # Example value (Tuple[str, ...]):
    #   ("a1", "a2", "a3", "c1")
    blueprint_nodes_store: Dict[tuple, Tuple[str, ...]] = {}

    # For each bucket (signature group), compare all pairs to find maximal overlaps
    for nodes in buckets.values():
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                match: SubstructureMatch = analyzer._find_maximal_overlap(nodes[i], nodes[j])
                if not match:
                    continue

                # edges_tuple identifies the blueprint topology (structure, not node names)
                edges_tuple = tuple(sorted(
                    (e.source_idx, e.target_idx, e.label)
                    for e in match.blueprint_edges
                ))
                acceptance_tuple = tuple(
                    _is_accepting_node(analyzer.G, n)
                    for n in match.nodes_a_ordered
                )
                key = (edges_tuple, acceptance_tuple)

                # Add both A- and B-side locations to the registry for this blueprint
                structure_registry[key].add(MatchLocation(
                    start_node=match.start_nodes[0],
                    all_nodes=match.nodes_a_ordered,
                    internals=match.internals_a,
                    frontiers=match.frontiers_a,
                ))
                structure_registry[key].add(MatchLocation(
                    start_node=match.start_nodes[1],
                    all_nodes=match.nodes_b_ordered,
                    internals=match.internals_b,
                    frontiers=match.frontiers_b,
                ))

                # Store the blueprint structure and node order (only once per blueprint)
                if key not in blueprint_store:
                    blueprint_store[key] = match.blueprint_edges
                    blueprint_nodes_store[key] = match.nodes_a_ordered

    results = []
    # Build BlueprintSubstructure objects for each unique blueprint
    for key, locations in structure_registry.items():
        loc_tuple = tuple(locations)
        results.append(BlueprintSubstructure(
            blueprint_nodes=blueprint_nodes_store[key],
            overlap_size=len(loc_tuple[0].all_nodes),
            locations=loc_tuple,
            blueprint_edges=blueprint_store[key],
        ))

    eff = count_non_overlapping_locations

    # Sort by (overlap_size * non-overlapping locations), descending
    return sorted(
        results,
        key=lambda x: (x.overlap_size * eff(x.locations), x.overlap_size),
        reverse=True,
    )
