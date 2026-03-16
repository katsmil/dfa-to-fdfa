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
    Representeert één specifieke plek waar de subroutine-structuur gevonden is.

    - start_node:  entry node van deze instantie
    - all_nodes:   volgorde correspondeert positie-voor-positie met
                   CanonicalSubstructure.canonical_nodes
    - internals:   nodes zonder uitgaande externe edges
    - frontiers:   nodes met minstens één uitgaande externe edge

    Tuple ipv List zodat MatchLocation hashbaar is (nodig voor set-gebruik in run_analysis).
    """
    start_node: str
    all_nodes: Tuple[str, ...]
    internals: Tuple[str, ...]
    frontiers: Tuple[str, ...]


@dataclass(frozen=True)
class CanonicalSubstructure:
    """
    De blauwdruk van een herhalende deelstructuur.

    - canonical_nodes[0] is ALTIJD de entry node (BFS-volgorde eerste match)
    - blueprint_edges beschrijft de topologie als indices in canonical_nodes,
      onafhankelijk van concrete node-namen
    """
    canonical_nodes: Tuple[str, ...]
    overlap_size: int
    locations: Tuple[MatchLocation, ...]
    blueprint_edges: Tuple[BlueprintEdge, ...]