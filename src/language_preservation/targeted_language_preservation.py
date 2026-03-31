"""
TARGETED LANGUAGE PRESERVATION TESTING
=======================================

Targeted variant of language equivalence testing.

Strategy:
  For each state s in the original DFA:
    1. Compute the shortest path (BFS) from the start state to s  → prefix
    2. Find a path from s to an accepting state                   → accept suffix
    3. Find a path from s to a non-accepting/dead state           → reject suffix
    4. Execute prefix + suffix on the factored DFA
    5. Compare the outcome against the expected result; any deviation is a mismatch

Reuses DFAExecutor from dfa_executor.py for FDFA execution,
including RC node and call stack support.
"""

import json
import networkx as nx
from datetime import datetime
from pathlib import Path
from typing import List, Set, Tuple, Optional, Dict
from collections import deque

from dfa_executor import DFAExecutor, find_start_node, find_accepting_nodes


# ---------------------------------------------------------------------------
# Graph analysis helpers for the original DFA
# ---------------------------------------------------------------------------

def _strip_wrapping_quotes(label: str) -> str:
    s = str(label).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def _extract_labeled_transitions(G: nx.MultiDiGraph) -> Dict[str, Dict[str, str]]:
    """
    Build a transition table {node: {symbol: target}} for the original DFA.
    Multi-labels ('a,b') are split into individual symbol entries.
    Epsilon transitions (no label) are skipped.
    """
    table: Dict[str, Dict[str, str]] = {n: {} for n in G.nodes()}
    for u, v, data in G.edges(data=True):
        label = data.get('label')
        if not label:
            continue
        if isinstance(label, str):
            # Strip a single pair of surrounding quotes (pydot artifact).
            # This avoids stripping escaped quotes inside the label.
            label = _strip_wrapping_quotes(label)
        for sym in [s.strip() for s in label.split(',')]:
            if sym:
                table[u][sym] = v
    return table

def _resolve_epsilon_targets(G: nx.MultiDiGraph) -> Dict[str, str]:
    """
    Map each node to the first node reachable via only unlabeled edges that
    has labeled outgoing edges (or to the last reachable node if none exist).

    Example:
      A -ε-> B -ε-> C -a-> D   =>   A->C, B->C, C->C
      E -ε-> F  (no labeled out) =>   E->F, F->F
    """
    cache: Dict[str, str] = {}

    def resolve(node: str) -> str:
        if node in cache:
            return cache[node]

        visited = set()
        cur = node
        while cur not in visited:
            visited.add(cur)
            has_labeled = any(
                data.get('label') for _, _, data in G.out_edges(cur, data=True)
            )
            if has_labeled:
                cache[node] = cur
                return cur
            for _, tgt, data in G.out_edges(cur, data=True):
                if not data.get('label') and tgt not in visited:
                    cur = tgt
                    break
            else:
                break

        cache[node] = cur
        return cur

    for n in G.nodes():
        resolve(n)

    return cache


def _bfs_shortest_paths(table: Dict[str, Dict[str, str]],
                         start: str,
                         epsilon_target_map: Dict[str, str]) -> Dict[str, List[str]]:
    """
    BFS from start; returns the shortest path to each reachable state
    as a list of symbols.

    Epsilon transitions do not consume input, so skipping them via the
    precomputed target map must not append any symbol to the path.
    """
    # paths[node] = list of symbols to reach that node
    paths: Dict[str, List[str]] = {start: []}
    queue: deque = deque([start])

    real_start = epsilon_target_map.get(start, start)
    if real_start != start:
        paths[real_start] = []
        queue.appendleft(real_start)

    while queue:
        node = queue.popleft()
        current_path = paths[node]

        for sym, target in table.get(node, {}).items():
            real_target = epsilon_target_map.get(target, target)
            if real_target not in paths:
                paths[real_target] = current_path + [sym]
                queue.append(real_target)

    return paths


def _find_suffix_to_accept(node: str,
                            table: Dict[str, Dict[str, str]],
                            accepting: Set[str]) -> Optional[List[str]]:
    """
    BFS from node; returns the shortest sequence of symbols leading to an
    accepting state. Returns None if no accepting state is reachable.
    """
    if node in accepting:
        return []

    visited: Dict[str, List[str]] = {node: []}
    queue: deque = deque([node])

    while queue:
        cur = queue.popleft()
        for sym, tgt in table.get(cur, {}).items():
            if tgt not in visited:
                new_path = visited[cur] + [sym]
                if tgt in accepting:
                    return new_path
                visited[tgt] = new_path
                queue.append(tgt)

    return None


def _find_suffix_to_reject(node: str,
                            table: Dict[str, Dict[str, str]],
                            accepting: Set[str]) -> Optional[List[str]]:
    """
    BFS from node; returns the shortest sequence of symbols leading to a
    non-accepting state, or a symbol for which no transition exists — both
    count as reject.

    Returns None if all reachable paths lead to accepting states.
    """
    if node not in accepting:
        # Node itself is already rejecting
        return []

    # Compute the full alphabet once outside the BFS loop.
    # This is necessary because we also want to check for missing transitions, e.g. non existing symbols in alphabet
    # (Avoid recomputing per iteration)
    all_syms = set(sym for trans in table.values() for sym in trans.keys())

    visited: Dict[str, List[str]] = {node: []}
    queue: deque = deque([node])

    while queue:
        cur = queue.popleft()

        # Try a symbol for which no transition is defined → immediate reject
        defined_syms = set(table.get(cur, {}).keys())
        dead_syms = all_syms - defined_syms
        if dead_syms:
            return visited[cur] + [sorted(dead_syms)[0]]

        for sym, tgt in table.get(cur, {}).items():
            if tgt not in visited:
                new_path = visited[cur] + [sym]
                if tgt not in accepting:
                    return new_path
                visited[tgt] = new_path
                queue.append(tgt)

    return None


# ---------------------------------------------------------------------------
# Test case
# ---------------------------------------------------------------------------

class TestCase:
    """A single test case: prefix + suffix, expected outcome, and FDFA result."""

    def __init__(self,
                 state: str,
                 prefix: List[str],
                 suffix: List[str],
                 suffix_kind: str,           # 'accept' or 'reject'
                 expected: bool,
                 accepted_fact: bool,
                 trace_fact: str):
        self.state = state
        self.prefix = prefix
        self.suffix = suffix
        self.suffix_kind = suffix_kind
        self.expected = expected
        self.accepted_fact = accepted_fact
        self.trace_fact = trace_fact

    @property
    def full_string(self) -> List[str]:
        return self.prefix + self.suffix

    @property
    def is_mismatch(self) -> bool:
        return self.expected != self.accepted_fact

    def summary(self, show_trace: bool = True) -> str:
        string_str = ' '.join(self.full_string) if self.full_string else '(empty)'
        status = 'MISMATCH' if self.is_mismatch else 'PASS'
        lines = [
            f"{'='*80}",
            f"{status}  state={self.state}  suffix={self.suffix_kind}",
            f"{'='*80}",
            f"  String   : {string_str}",
            f"  Prefix   : {' '.join(self.prefix) or '(empty)'}",
            f"  Suffix   : {' '.join(self.suffix) or '(empty)'}",
            f"  Original : {'ACCEPT' if self.expected else 'REJECT'}",
            f"  Factored : {'ACCEPT' if self.accepted_fact else 'REJECT'}",
        ]
        if show_trace:
            lines.append(f"\n  --- Factored trace ---\n{self.trace_fact}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize this test case to a JSON-compatible dict."""
        return {
            "state":        self.state,
            "suffix_kind":  self.suffix_kind,
            "prefix":       self.prefix,
            "suffix":       self.suffix,
            "full_string":  self.full_string,
            "original":     "ACCEPT" if self.expected else "REJECT",
            "factored":     "ACCEPT" if self.accepted_fact else "REJECT",
            "passed":       not self.is_mismatch,
            "trace":        self.trace_fact,
        }


# ---------------------------------------------------------------------------
# TargetedLanguagePreservationTester
# ---------------------------------------------------------------------------

class TargetedLanguagePreservationTester:
    """
    Targeted tester that iterates over every state in the original DFA and
    tests both an accept suffix and a reject suffix from each state.
    """

    def __init__(self, G_original: nx.MultiDiGraph, G_factored: nx.MultiDiGraph):
        self.G_orig = G_original
        self.executor_fact = DFAExecutor(G_factored)

        # Build helper structures on the original DFA
        self._table = _extract_labeled_transitions(G_original)
        self._start = find_start_node(G_original)
        self._accepting = find_accepting_nodes(G_original)
        self._all_nodes = set(G_original.nodes())

        # Shortest paths from start to every reachable state
        epsilon_target_map = _resolve_epsilon_targets(G_original)
        self._prefixes = _bfs_shortest_paths(self._table, self._start, epsilon_target_map)

        # Alphabet = all symbols present in the transition table
        self.alphabet = sorted({
            sym for trans in self._table.values() for sym in trans.keys()
        })

    # ------------------------------------------------------------------
    # Test generation and execution
    # ------------------------------------------------------------------

    def _build_test_case(self,
                          state: str,
                          prefix: List[str],
                          suffix: List[str],
                          suffix_kind: str,
                          expected: bool) -> TestCase:
        """
        Submit prefix+suffix to the FDFA and wrap the result as a TestCase.

        The expected outcome is already known from construction:
        the BFS prefix is guaranteed to reach `state`, and the suffix is
        deliberately chosen to produce an accept or reject outcome.
        """
        full = prefix + suffix
        acc_fact, trace_fact = self.executor_fact.execute(full)

        return TestCase(
            state=state,
            prefix=prefix,
            suffix=suffix,
            suffix_kind=suffix_kind,
            expected=expected,
            accepted_fact=acc_fact,
            trace_fact=trace_fact,
        )

    def run(self, states: Optional[Set[str]] = None) -> Tuple[bool, List[TestCase]]:
        """
        Run targeted tests for all reachable states, or a given subset.

        Args:
            states: optional set of state names to test; tests all reachable
                    states if None.

        Returns:
            (all_match: bool, all_cases: List[TestCase])
        """
        all_cases: List[TestCase] = []

        prefixes = {s: p for s, p in self._prefixes.items()
                    if states is None or s in states}

        for state, prefix in sorted(prefixes.items()):
            # --- accept suffix ---
            accept_suffix = _find_suffix_to_accept(state, self._table, self._accepting)
            if accept_suffix is not None:
                tc = self._build_test_case(state, prefix, accept_suffix, 'accept', expected=True)
                all_cases.append(tc)

            # --- reject suffix ---
            reject_suffix = _find_suffix_to_reject(state, self._table, self._accepting)
            if reject_suffix is not None:
                tc = self._build_test_case(state, prefix, reject_suffix, 'reject', expected=False)
                all_cases.append(tc)

        all_match = all(not tc.is_mismatch for tc in all_cases)
        return all_match, all_cases

    def run_report(self, verbose: bool = False,
                   states: Optional[Set[str]] = None) -> Tuple[str, List[TestCase]]:
        """
        Run all tests and return a readable report together with all test cases.

        Args:
            verbose: if True, show the factored trace for passing tests as well;
                     traces for mismatches are always shown.
            states:  optional subset of states to test (tests all if None).

        Returns:
            (report: str, all_cases: List[TestCase])
        """
        num_states = len(self._prefixes)
        unreachable_orig = len(self._all_nodes) - num_states

        print(f"🎯 Targeted testing: {num_states} reachable states "
              f"(+ {unreachable_orig} unreachable in original)...")

        all_match, all_cases = self.run(states=states)
        mismatches = [tc for tc in all_cases if tc.is_mismatch]

        report = []
        report.append("\n" + "="*80)
        report.append("TARGETED LANGUAGE PRESERVATION TEST RESULTS")
        report.append("="*80)
        report.append(f"States analysed (original DFA) : {num_states}")
        report.append(f"Unreachable states (original)  : {unreachable_orig}")
        report.append(f"Tests executed                 : {len(all_cases)}")
        report.append(f"Mismatches                     : {len(mismatches)}")
        report.append("\n--- All executed tests ---")
        for tc in all_cases:
            # Always show trace on mismatch; only show on pass when verbose
            show_trace = tc.is_mismatch or verbose
            report.append(tc.summary(show_trace=show_trace))

        if all_match:
            report.append("\n✅ SUCCESS: All targeted tests passed. Language is preserved.")
        else:
            report.append(f"\n❌ FAILURE: {len(mismatches)} mismatch(es) found!")

        return "\n".join(report), all_cases

    def write_json(self,
                   orig_path: str,
                   fact_path: str,
                   all_cases: List[TestCase],
                   output_path: str = "language_preservation_result.json") -> None:
        """
        Write already-computed test results to a JSON file, overwriting any
        existing content. Defaults to language_preservation_result.json in
        the working directory.

        Args:
            orig_path:  path to the original DOT file (stored as metadata)
            fact_path:  path to the factored DOT file (stored as metadata)
            all_cases:  test cases returned by run_report()
            output_path: destination file path
        """
        num_states = len(self._prefixes)
        unreachable_orig = len(self._all_nodes) - num_states
        mismatches = [tc for tc in all_cases if tc.is_mismatch]
        all_match = len(mismatches) == 0

        result = {
            "timestamp":  datetime.now().isoformat(timespec="seconds"),
            "original":   orig_path,
            "factored":   fact_path,
            "summary": {
                "states_analysed":    num_states,
                "unreachable_states": unreachable_orig,
                "tests_executed":     len(all_cases),
                "mismatches":         len(mismatches),
                "passed":             all_match,
            },
            "cases": [tc.to_dict() for tc in all_cases],
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        print(f"📄 Results written to {output_path}")


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def verify_language_preservation_targeted(
        G_original: nx.MultiDiGraph,
        G_factored: nx.MultiDiGraph,
) -> Tuple[bool, List[TestCase]]:
    """
    Convenience wrapper for targeted language equivalence testing from other modules.

    Returns:
        (all_match, all_cases)
    """
    tester = TargetedLanguagePreservationTester(G_original, G_factored)
    return tester.run()


def compare_graphs_on_string(G_original: nx.MultiDiGraph, G_factored: nx.MultiDiGraph,
                             input_string, verbose: bool = True) -> dict:
    """
    Compare two automata on a single input string.

    Args:
        G_original:   original DFA as a NetworkX MultiDiGraph
        G_factored:   factored DFA as a NetworkX MultiDiGraph
        input_string: string like 'a x x a' or a list of symbols ['a','x','x','a']
        verbose:      print traces and results

    Returns:
        dict with acceptance booleans and traces for both automata.
    """
    if isinstance(input_string, str):
        symbols = input_string.split()
    else:
        symbols = []
        for item in input_string:
            symbols.extend(str(item).split())

    exec_orig = DFAExecutor(G_original)
    exec_fact = DFAExecutor(G_factored)

    acc_orig, trace_orig = exec_orig.execute(symbols)
    acc_fact, trace_fact = exec_fact.execute(symbols)

    result = {
        'string': ''.join(symbols),
        'accepted_original': acc_orig,
        'accepted_factored': acc_fact,
        'trace_original': trace_orig,
        'trace_factored': trace_fact,
    }

    if verbose:
        print(f"String  : {result['string']}")
        print(f"Original: {'ACCEPT' if acc_orig else 'REJECT'}")
        print(result['trace_original'])
        print(f"\nFactored: {'ACCEPT' if acc_fact else 'REJECT'}")
        print(result['trace_factored'])

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Usage: python targeted_language_preservation.py <orig.dot> <factored.dot> [--string axxa] [-v] [--states q0,q3,q7]
    if len(sys.argv) >= 3:
        orig_path = sys.argv[1]
        fact_path = sys.argv[2]
        verbose = '-v' in sys.argv or '--verbose' in sys.argv

        G_original = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(orig_path))
        G_factored = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(fact_path))

        if '--string' in sys.argv:
            # Single string comparison mode
            idx = sys.argv.index('--string')
            if idx + 1 < len(sys.argv):
                input_str = sys.argv[idx + 1].split()
                compare_graphs_on_string(G_original, G_factored, input_str, verbose=True)
        else:
            # Targeted testing mode
            states = None
            if '--states' in sys.argv:
                idx = sys.argv.index('--states')
                if idx + 1 < len(sys.argv):
                    states = set(s.strip() for s in sys.argv[idx + 1].split(',') if s.strip())

            tester = TargetedLanguagePreservationTester(G_original, G_factored)
            report, all_cases = tester.run_report(verbose=verbose, states=states)
            print(report)
            tester.write_json(orig_path, fact_path, all_cases)

    else:
        # Fallback for local testing
        G_original = nx.nx_pydot.read_dot("input/test_automata/deel_8.dot")
        G_factored = nx.nx_pydot.read_dot("output/deel_8_factorized.dot")

        tester = TargetedLanguagePreservationTester(G_original, G_factored)
        report, _ = tester.run_report()
        print(report)
