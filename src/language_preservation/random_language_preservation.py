"""
LANGUAGE PRESERVATION TESTING - RANDOM VARIANT
===============================================

Tests whether the factored automaton accepts the same language as the original,
using randomly generated input strings.

This is the non-targeted variant of language equivalence testing.
See targeted_language_preservation.py for the targeted variant.
"""

import networkx as nx
import random
from typing import List, Tuple, Optional

from dfa_executor import DFAExecutor


# ---------------------------------------------------------------------------
# LanguagePreservationTester
# ---------------------------------------------------------------------------

class LanguagePreservationTester:
    """
    Tests whether factorization preserves the language via random string testing.
    """

    def __init__(self, G_original: nx.MultiDiGraph, G_factored: nx.MultiDiGraph):
        self.executor_orig = DFAExecutor(G_original)
        self.executor_fact = DFAExecutor(G_factored)
        self.alphabet = self._extract_alphabet(G_original)

    def _extract_alphabet(self, G: nx.MultiDiGraph) -> List[str]:
        """Collect all unique edge labels in the graph."""
        labels = set()
        for _, _, data in G.edges(data=True):
            if 'label' in data:
                labels.add(data['label'])
        return sorted(labels)

    def generate_random_strings(self, count: int = 100, max_length: int = 20) -> List[List[str]]:
        """Generate random test strings over the alphabet."""
        strings = []
        for _ in range(count):
            length = random.randint(1, max_length)
            string = [random.choice(self.alphabet) for _ in range(length)]
            strings.append(string)
        return strings

    def test_equivalence(self, test_strings: Optional[List[List[str]]] = None,
                         verbose: bool = False) -> Tuple[bool, List[str]]:
        """
        Test whether both automata agree on all given strings.

        Returns:
            (all_match: bool, mismatches: List[str])
        """
        if test_strings is None:
            test_strings = self.generate_random_strings()

        mismatches = []

        for i, string in enumerate(test_strings):
            accepted_orig, trace_orig = self.executor_orig.execute(string)
            accepted_fact, trace_fact = self.executor_fact.execute(string)

            if accepted_orig != accepted_fact:
                mismatch_report = (
                    f"\n{'='*80}\n"
                    f"MISMATCH #{len(mismatches) + 1}\n"
                    f"{'='*80}\n"
                    f"String  : {' '.join(string)}\n"
                    f"Original: {'ACCEPT' if accepted_orig else 'REJECT'}\n"
                    f"Factored: {'ACCEPT' if accepted_fact else 'REJECT'}\n"
                )

                if verbose:
                    mismatch_report += f"\nOriginal trace:\n{trace_orig}\n"
                    mismatch_report += f"\nFactored trace:\n{trace_fact}\n"

                mismatches.append(mismatch_report)

            if verbose and i % 10 == 0:
                print(f"Tested {i+1}/{len(test_strings)} strings...")

        return len(mismatches) == 0, mismatches

    def run_comprehensive_test(self, num_tests: int = 1000) -> str:
        """Run a comprehensive test and return a report."""
        print(f"🧪 Testing language preservation with {num_tests} random strings...")

        test_strings = self.generate_random_strings(count=num_tests)
        all_match, mismatches = self.test_equivalence(test_strings, verbose=False)

        report = []
        report.append("\n" + "="*80)
        report.append("LANGUAGE PRESERVATION TEST RESULTS")
        report.append("="*80)
        report.append(f"Total tests : {num_tests}")
        report.append(f"Passed      : {num_tests - len(mismatches)}")
        report.append(f"Failed      : {len(mismatches)}")

        if all_match:
            report.append("\n✅ SUCCESS: All tests passed! Language is preserved.")
        else:
            report.append(f"\n❌ FAILURE: {len(mismatches)} mismatches found!")
            report.append("\nFirst 3 mismatches:")
            for mismatch in mismatches[:3]:
                report.append(mismatch)

        return "\n".join(report)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def verify_language_preservation(G_original: nx.MultiDiGraph, G_factored: nx.MultiDiGraph,
                                  num_tests: int = 200, max_length: int = 20,
                                  verbose: bool = False) -> Tuple[bool, List[str]]:
    """
    Convenience wrapper for randomized language equivalence testing from other modules.

    Returns:
        (all_match, mismatches)
    """
    tester = LanguagePreservationTester(G_original, G_factored)

    if not tester.alphabet:
        test_strings = [[]]
    else:
        test_strings = tester.generate_random_strings(count=num_tests, max_length=max_length)

    all_match, mismatches = tester.test_equivalence(test_strings, verbose=verbose)
    return all_match, mismatches


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    # Usage: python language_preservation_random.py <orig.dot> <factored.dot>
    if len(sys.argv) == 3:
        orig_path = sys.argv[1]
        fact_path = sys.argv[2]

        G_original = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(orig_path))
        G_factored = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(fact_path))

        tester = LanguagePreservationTester(G_original, G_factored)
        report = tester.run_comprehensive_test(num_tests=1000)
        print(report)

    else:
        # Fallback for local testing
        G_original = nx.nx_pydot.read_dot("input/test_automata/deel_8.dot")
        G_factored = nx.nx_pydot.read_dot("output/deel_8_factorized.dot")
        tester = LanguagePreservationTester(G_original, G_factored)
        report = tester.run_comprehensive_test(num_tests=1000)
        print(report)