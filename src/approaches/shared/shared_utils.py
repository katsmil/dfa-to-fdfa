from collections import defaultdict
from typing import Dict, List, Set, Tuple

from approaches.shared.shared_types import MatchLocation


def count_non_overlapping_locations(locations: List[MatchLocation]) -> int:
    """
    Counts the number of 'independent' occurrences of a substructure.

    Because matches can share nodes (overlap), the total number of locations
    often gives an overly optimistic picture of the savings. This function uses
    a greedy selection to determine how many matches can be placed without
    sharing nodes with each other.

    Logic:
    1. Sort locations by start_node for a deterministic result.
    2. Iterate through locations and claim the nodes of a match only if
       none of that match's nodes are already claimed by an earlier match.
    3. Count only the matches that are completely free of overlap.

    Args:
        locations: A collection of found MatchLocation objects.

    Returns:
        int: The number of disjoint (non-overlapping) locations.
    """
    count = 0
    claimed: Set[str] = set()
    for loc in sorted(locations, key=lambda l: l.start_node):
        loc_nodes = set(loc.all_nodes)
        if not loc_nodes & claimed:
            count += 1
            claimed |= loc_nodes
    return count


def get_internals_and_frontiers(analyzer, nodes: Tuple[str, ...]) -> Tuple[Tuple, Tuple]:
    """
    Splits the nodes of a match into internals and frontiers.

    - internals: nodes with no outgoing external edges (all targets lie within the match)
    - frontiers: nodes with at least one outgoing external edge

    Args:
        analyzer: An instance of BaseSubstructureAnalyzer (for _get_edges_cached).
        nodes:    Ordered tuple of node names within the match.

    Returns:
        Tuple of (internals, frontiers), both as tuples of node names.
    """
    nodes_set = set(nodes)
    internals, frontiers = [], []
    for n in nodes:
        has_external = any(
            t not in nodes_set
            for t in analyzer._get_edges_cached(n).values()
        )
        if has_external:
            frontiers.append(n)
        else:
            internals.append(n)
    return tuple(internals), tuple(frontiers)

def build_signature_buckets(analyzer) -> Dict[tuple, List[str]]:
    buckets = defaultdict(list)
    for node in analyzer.G.nodes():
        buckets[analyzer._get_node_signature(node)].append(node)
    return {k: sorted(v) for k, v in buckets.items() if len(v) >= 2}