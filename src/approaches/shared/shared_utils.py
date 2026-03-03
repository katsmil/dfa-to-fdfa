from typing import List, Set, Tuple

from approaches.shared.shared_types import MatchLocation


def count_non_overlapping_locations(locations: List[MatchLocation]) -> int:
    """
    Berekent het aantal 'onafhankelijke' voorkomens van een substructuur.

    Omdat matches nodes kunnen delen (overlap), geeft het totale aantal locaties
    vaak een te optimistisch beeld van de besparing. Deze functie gebruikt een
    'greedy' selectie om te bepalen hoeveel matches er geplaatst kunnen worden
    zonder dat ze nodes met elkaar delen.

    Logica:
    1. Sorteer locaties op start_node voor een deterministisch resultaat.
    2. Loop door de locaties en claim de nodes van een match alleen als
       geen enkele node van die match al door een eerdere match is geclaimd.
    3. Tel alleen de matches die volledig vrij zijn van overlap.

    Args:
        locations: Een verzameling van gevonden MatchLocation objecten.

    Returns:
        int: Het aantal disjuncte (niet-overlappende) locaties.
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
    Splitst de nodes van een match in internals en frontiers.

    - internals: nodes zonder uitgaande externe edges (alle targets liggen binnen de match)
    - frontiers: nodes met minstens één uitgaande externe edge

    Args:
        analyzer: Een instantie van BaseSubstructureAnalyzer (voor _get_edges_cached).
        nodes:    Geordende tuple van node-namen binnen de match.

    Returns:
        Tuple van (internals, frontiers), beide als tuple van node-namen.
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