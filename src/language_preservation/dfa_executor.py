"""
DFA EXECUTOR
============

Shared execution engine for (factored) DFAs.
Supports both plain DFAs and DFAs with RC nodes and a call stack
(the result of the factorization algorithm).

Imported by:
  - language_preservation_random.py
  - targeted_language_preservation.py
"""

import copy
import ast
import networkx as nx
from typing import List, Set, Tuple, Optional



# ---------------------------------------------------------------------------
# Module-level graph helpers (also used by targeted_language_preservation.py)
# ---------------------------------------------------------------------------

def find_start_node(G: nx.MultiDiGraph) -> str:
    """Find the start node of a DFA graph (in-degree 0, or has a 'start' attribute)."""
    for node in G.nodes():
        if G.in_degree(node) == 0:
            return node
        if G.nodes[node].get('start') == True:
            return node
    return list(G.nodes())[0]


def find_accepting_nodes(G: nx.MultiDiGraph) -> Set[str]:
    """Find accepting states in a DFA graph (doublecircle shape, peripheries=2,
    or originally_accepting=True for internal SUB nodes in factored graphs)."""
    accepting = set()
    for node in G.nodes():
        nd = G.nodes[node]
        shape = str(nd.get('shape', '')).strip().strip('"').strip("'")
        peripheries = str(nd.get('peripheries', '')).strip().strip('"').strip("'")
        originally = str(nd.get('originally_accepting', '')).strip().strip('"').strip("'").lower()
        if shape == 'doublecircle':
            accepting.add(node)
        elif peripheries == '2':
            accepting.add(node)
        elif originally == 'true':
            accepting.add(node)
    return accepting


class DFAExecutor:
    """
    Executes strings on a (factored) DFA.
    Supports both plain DFAs and DFAs with RC nodes and a call stack.
    """

    def __init__(self, G: nx.MultiDiGraph):
        self.G = self._normalize_labels(G)
        self.G = self._normalize_node_attributes(self.G)
        self.start_node = self._find_start_node()
        self.start_node = self._follow_epsilon_transitions(self.start_node)
        self.accepting_nodes = self._find_accepting_nodes()   # input-accepting states
        self.frontier_nodes = self._find_frontier_nodes()     # control-flow return points

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    def _follow_epsilon_transitions(self, node: str) -> str:
        """Follow epsilon transitions (unlabeled edges) until a node with labeled outgoing edges is reached."""
        visited = set()
        current = node

        while current not in visited:
            visited.add(current)
            epsilon_target = None
            has_labeled = False

            for _, target, data in self.G.out_edges(current, data=True):
                if 'label' not in data or data.get('label') is None:
                    epsilon_target = target
                else:
                    has_labeled = True

            if has_labeled:
                return current

            if epsilon_target and epsilon_target not in visited:
                current = epsilon_target
            else:
                break

        return current

    def _find_start_node(self) -> str:
        """Find the start node (in-degree 0, or has a 'start' attribute)."""
        return find_start_node(self.G)

    def _find_accepting_nodes(self) -> Set[str]:
        """
        Nodes where execution terminates and the input is accepted.

        - Outside subcomponents: doublecircle or peripheries=2 (original DFA convention).
        - Inside subcomponents (SUB_* / cluster 'subroutine_*'): only if
          originally_accepting=True.  A bare peripheries=2 inside a subcomponent
          signals a frontier (control-flow return point), NOT input acceptance.
        """
        accepting = set()
        for node in self.G.nodes():
            nd = self.G.nodes[node]
            in_subroutine = (
                'subroutine' in str(nd.get('cluster', ''))
                or 'SUB_' in str(node)
            )
            if in_subroutine:
                originally = str(nd.get('originally_accepting', '')).strip().strip('"').strip("'").lower()
                if originally == 'true':
                    accepting.add(node)
            else:
                shape = str(nd.get('shape', '')).strip().strip('"').strip("'")
                peripheries = str(nd.get('peripheries', '')).strip().strip('"').strip("'")
                if shape == 'doublecircle' or peripheries == '2':
                    accepting.add(node)
        return accepting

    def _find_frontier_nodes(self) -> Set[str]:
        """
        Nodes that can return control flow to their RC caller.

        A frontier is a subcomponent-context node (SUB_* / cluster 'subroutine_*')
        marked peripheries=2 by _process_exits.  Nested RC nodes that inherited
        peripheries=2 from a replaced instance node are included via their
        cluster attribute.
        """
        frontier = set()
        for node in self.G.nodes():
            nd = self.G.nodes[node]
            peripheries = str(nd.get('peripheries', '')).strip().strip('"').strip("'")
            if peripheries != '2':
                continue
            in_subroutine = (
                'subroutine' in str(nd.get('cluster', ''))
                or 'SUB_' in str(node)
            )
            if in_subroutine:
                frontier.add(node)
        return frontier

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, input_string: List[str]) -> Tuple[bool, str]:
        """
        Execute a string on the automaton.

        Returns:
            (accepted: bool, trace: str)
        """
        current = self.start_node
        stack = []
        trace = [f"Start: {current}"]

        for symbol in input_string:
            # Chain nested calls: if current is an RC node (or lands on one after
            # entering a subcomponent), keep entering subcomponents until we reach a
            # plain state that can take a normal transition.
            while 'RC' in str(current):
                subcomponent_start = self._get_subcomponent_entry(current)
                if subcomponent_start:
                    stack.append(current)
                    current = subcomponent_start
                    trace.append(f"  CALL {current} (stack depth: {len(stack)})")
                else:
                    break
            next_node = self._take_transition(current, symbol)

            if next_node is None:
                if stack and self._is_frontier(current):
                    # Pop through transparent RC frames (empty dispatch_map) until
                    # a frame can dispatch, or the stack is exhausted.
                    # An RC node with an empty dispatch is a "tail-call" node:
                    # the called subcomponent absorbed all continuation routing,
                    # so the return propagates directly to the outer caller.
                    dispatched = False
                    while stack:
                        rc_node = stack.pop()
                        next_node = self._dispatch(rc_node, current, symbol)
                        if next_node is not None:
                            trace.append(f"  RETURN via δret({rc_node}, {current}, '{symbol}') → {next_node}")
                            dispatched = True
                            break
                        else:
                            trace.append(f"  (return through {rc_node})")
                            # If the RC node itself is a frontier of its parent
                            # subcomponent (peripheries=2), it becomes the new
                            # current frontier point for the outer caller.
                            if self._is_frontier(rc_node):
                                current = rc_node

                    if not dispatched:
                        trace.append(f"  REJECT: δret(..., {current}, '{symbol}') undefined on all stack frames")
                        return False, "\n".join(trace)
                else:
                    trace.append(
                        f"  REJECT: δint({current}, '{symbol}') undefined "
                        f"(no internal transition; not at frontier)"
                    )
                    return False, "\n".join(trace)

            current = next_node
            trace.append(f"  '{symbol}' → {current}")

        # If input ends on an RC node, follow epsilon CALLs into subcomponents.
        # This may chain: RC_outer → SUB_x_0 → RC_inner → SUB_y_0 → ...
        # We stop when the current node is no longer an RC node.
        # Acceptance is decided by originally_accepting on the final node reached.
        while 'RC' in str(current):
            subcomponent_start = self._get_subcomponent_entry(current)
            if not subcomponent_start:
                break
            stack.append(current)
            current = subcomponent_start
            trace.append(f"  CALL {current} (stack depth: {len(stack)}) [end-of-input]")

        current = self._follow_epsilon_to_accepting(current)

        accepted = current in self.accepting_nodes
        trace.append(f"\nFinal: {current} ({'ACCEPT' if accepted else 'REJECT'})")

        return accepted, "\n".join(trace)

    # ------------------------------------------------------------------
    # Transition helpers
    # ------------------------------------------------------------------

    def _take_transition(self, node: str, symbol: str) -> Optional[str]:
        """Find the target node for a transition with the given label."""
        for _, target, data in self.G.out_edges(node, data=True):
            label = data.get('label')
            if label is None:
                continue
            symbols = [s.strip() for s in label.split(',')]
            if symbol in symbols:
                return self._follow_epsilon_transitions(target)
        return None

    def _dispatch(self, rc_node: str, frontier_node: str, symbol: str) -> Optional[str]:
        """δret(rc_node, frontier_node, symbol) → target."""
        nd = self.G.nodes.get(rc_node, {})
        dispatch_map = nd.get('dispatch_map', {})

        if isinstance(dispatch_map, str):
            try:
                dispatch_map = ast.literal_eval(dispatch_map)
            except (ValueError, SyntaxError):
                return None

        def strip_quotes(s: str) -> str:
            s = s.strip()
            while len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
                s = s[1:-1].strip()
            return s

        normalized_map = {strip_quotes(k): v for k, v in dispatch_map.items()}
        symbol_map = normalized_map.get(symbol, {})

        if isinstance(symbol_map, dict):
            return symbol_map.get(frontier_node)

        return None

    def _get_subcomponent_entry(self, rc_node: str) -> Optional[str]:
        """Find the entry node of the subcomponent associated with this RC node."""
        nd = self.G.nodes.get(rc_node, {})
        label = str(nd.get('label', '')).strip().strip('"').strip("'")
        if not label.startswith('RC:'):
            return None
        cluster_name = label[3:].strip()
        start_dummy = f"__start_{cluster_name}"
        if self.G.has_node(start_dummy):
            for _, target in self.G.out_edges(start_dummy):
                return self._follow_epsilon_transitions(target)
        return None

    def _is_frontier(self, node: str) -> bool:
        return node in self.frontier_nodes

    def _follow_epsilon_to_accepting(self, node: str) -> str:
        """Follow epsilon transitions until an accepting node is reached."""
        visited = set()
        current = node

        while current not in visited:
            visited.add(current)

            if current in self.accepting_nodes:
                return current

            epsilon_target = None
            for _, target, data in self.G.out_edges(current, data=True):
                if 'label' not in data or data.get('label') is None:
                    epsilon_target = target
                    break

            if epsilon_target and epsilon_target not in visited:
                current = epsilon_target
            else:
                break

        return current

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_labels(self, G: nx.MultiDiGraph) -> nx.MultiDiGraph:
        """Remove extra quotes and normalize whitespace in edge labels."""
        G_norm = copy.deepcopy(G)

        for u, v, key, data in G_norm.edges(keys=True, data=True):
            if 'label' in data:
                label = data['label']
                if not isinstance(label, str):
                    label = str(label)
                if len(label) >= 2 and ((label[0] == '"' and label[-1] == '"') or
                                        (label[0] == "'" and label[-1] == "'")):
                    label = label[1:-1]
                label = label.strip()
                G_norm[u][v][key]['label'] = label

        return G_norm

    def _normalize_node_attributes(self, G: nx.MultiDiGraph) -> nx.MultiDiGraph:
        """Strip surrounding quotes from node attribute values (pydot artifact)."""
        G_norm = copy.deepcopy(G)

        for node in G_norm.nodes():
            nd = G_norm.nodes[node]
            for attr in list(nd.keys()):
                val = nd[attr]
                if isinstance(val, str):
                    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or
                                          (val[0] == "'" and val[-1] == "'")):
                        nd[attr] = val[1:-1]

        return G_norm