from dataclasses import dataclass
from typing import Tuple


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

    Tuple instead of List so MatchLocation is hashable (required for set usage in run_analysis).
    """
    start_node: str
    all_nodes: Tuple[str, ...]
    internals: Tuple[str, ...]
    frontiers: Tuple[str, ...]


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