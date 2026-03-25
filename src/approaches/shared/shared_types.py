from dataclasses import dataclass
from typing import FrozenSet, Tuple


@dataclass(frozen=True)
class BlueprintEdge:
    source_idx: int
    target_idx: int
    label: str


@dataclass(frozen=True)
class MatchLocation:
    """
    Represents one specific location where the subroutine structure was found.

    - start_node:  entry node of this instance
    - all_nodes:   order corresponds position-for-position with
                   BlueprintSubstructure.blueprint_nodes
    - internals:   nodes with no outgoing external edges
    - frontiers:   nodes with at least one outgoing external edge
    """
    start_node: str
    all_nodes: Tuple[str, ...]
    internals: Tuple[str, ...]
    frontiers: Tuple[str, ...]


@dataclass(frozen=True)
class SubstructureMatch:
    """
    The result of a single pairwise BFS match between two start nodes.

    - start_nodes:      the two entry nodes that were compared
    - overlap_size:     number of matched node pairs
    - internals_a/b:    nodes with no outgoing external edges (A- and B-side)
    - frontiers_a/b:    nodes with at least one outgoing external edge (A- and B-side)
    - all_pairs:        the full set of (a, b) node pairs found by BFS
    - nodes_a_ordered:  BFS-ordered node names for the A-side
    - nodes_b_ordered:  BFS-ordered node names for the B-side
    - blueprint_edges:  topology of the match as index-based edges
    """
    start_nodes:     Tuple[str, str]
    overlap_size:    int
    internals_a:     Tuple[str, ...]
    frontiers_a:     Tuple[str, ...]
    internals_b:     Tuple[str, ...]
    frontiers_b:     Tuple[str, ...]
    all_pairs:       FrozenSet[Tuple[str, str]]
    nodes_a_ordered: Tuple[str, ...]
    nodes_b_ordered: Tuple[str, ...]
    blueprint_edges: Tuple[BlueprintEdge, ...]


@dataclass(frozen=True)
class BlueprintSubstructure:
    """
    The blueprint of a subcomponent.

    - blueprint_nodes[0] is ALWAYS the entry node (BFS-order of first match)
    - blueprint_edges describes the topology as indices into blueprint_nodes,
      independent of concrete node names
    """
    blueprint_nodes: Tuple[str, ...]
    overlap_size: int
    locations: Tuple[MatchLocation, ...]
    blueprint_edges: Tuple[BlueprintEdge, ...]