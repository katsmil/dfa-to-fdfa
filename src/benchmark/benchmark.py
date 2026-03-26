"""
VARIANT-AGNOSTIC BENCHMARK SUITE
=================================

This framework tests all variants (EquivalenceClosure, NoEquivalenceClosure, and NestedCalls)
on the same inputs and collects metrics.
"""

import time
import networkx as nx
from dataclasses import dataclass
from typing import List, Tuple
import json
import sys
import os

# Add project root to Python path so imports work correctly
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # Should be .../src/
if project_root not in sys.path:
    sys.path.insert(0, project_root)

language_preservation_dir = os.path.join(project_root, "language_preservation")
if language_preservation_dir not in sys.path:
    sys.path.insert(0, language_preservation_dir)

from approaches.no_equivalence_closure.main import factorize as _factorize_no_eq
from approaches.equivalence_closure.main import factorize as _factorize_eq
from approaches.no_equivalence_closure_nested_calls.main import factorize as _factorize_nested

VARIANT_FACTORIZE = {
    'NoEquivalenceClosure': _factorize_no_eq,
    'EquivalenceClosure':   _factorize_eq,
    'NestedCalls':          _factorize_nested,
}

def count_real_nodes(G: nx.MultiDiGraph) -> int:
    """Count nodes, excluding dummy start nodes (__start_*)."""
    return sum(1 for node in G.nodes() if not str(node).startswith('__start_'))

def count_real_edges(G: nx.MultiDiGraph) -> int:
    """Count edges, excluding edges from/to dummy start nodes."""
    count = 0
    for u, v, key, data in G.edges(data=True, keys=True):
        if not str(u).startswith('__start_') and not str(v).startswith('__start_'):
            count += 1
    return count

@dataclass
class BenchmarkResult:
    """Metrics measured for all variants"""
    # Timing
    total_time: float
    
    # Effectiveness
    nodes_before: int
    nodes_after: int
    edges_before: int
    edges_after: int
    
    # Quality
    compression_ratio: float  # nodes_after / nodes_before

    # Correctness
    language_preserved: bool  # Via targeted language preservation testing
    determinism_check: bool   # No duplicate labels on nodes other than RC nodes

    # Details from language preservation testing
    language_mismatches: List[str]

class BenchmarkSuite:
    """
    Tests all variants on identical inputs.
    """
    
    def __init__(self):
        self.results = {
            'NoEquivalenceClosure': [],
            'EquivalenceClosure': [],
            'NestedCalls': []
        }
    
    def run_benchmark(self, graph: nx.MultiDiGraph, name: str, variant: str):
        """Run one test for one variant"""
        
        # PRE-METRICS (excluding dummy nodes)
        nodes_before = count_real_nodes(graph)
        edges_before = count_real_edges(graph)

        factorize_fn = VARIANT_FACTORIZE[variant]
        graph_copy = graph.copy()

        start_total = time.time()
        factored_graph = factorize_fn(graph_copy)
        total_time = time.time() - start_total
        
        # POST-METRICS (excluding dummy nodes)
        nodes_after = count_real_nodes(factored_graph)
        edges_after = count_real_edges(factored_graph)
        
        # CORRECTNESS CHECK
        language_ok, mismatches = self.verify_language_preservation(graph, factored_graph)
        determinism_ok = self.verify_determinism(factored_graph)
        
        result = BenchmarkResult(
            total_time=total_time,
            nodes_before=nodes_before,
            nodes_after=nodes_after,
            edges_before=edges_before,
            edges_after=edges_after,
            compression_ratio=1.0 - (nodes_after / nodes_before) if nodes_before > 0 else 0.0,
            language_preserved=language_ok,
            language_mismatches=mismatches,
            determinism_check=determinism_ok
        )
        
        self.results[variant].append({
            'graph_name': name,
            'result': result
        })
        
        return result
    
    def verify_language_preservation(self, G_orig: nx.MultiDiGraph,
                                     G_fact: nx.MultiDiGraph) -> Tuple[bool, List[str]]:
        """
        Test whether both automata accept the same language.
        Uses targeted testing: exercises every reachable state with
        both an accept and reject suffix.
        """
        try:
            from language_preservation.targeted_language_preservation import (
                verify_language_preservation_targeted
            )
        except Exception as e:
            print(f"⚠️  Warning: could not import targeted language preservation: {e}")
            return True, []

        try:
            all_match, all_cases = verify_language_preservation_targeted(G_orig, G_fact)
            mismatches = [tc.summary(show_trace=False) for tc in all_cases if tc.is_mismatch]
            if not all_match:
                print(f"⚠️  Language preservation: {len(mismatches)} mismatch(es) found.")
            return all_match, mismatches
        except Exception as e:
            print(f"⚠️  Error while running language preservation tests: {e}")
            return False, [f"Error running tests: {e}"]
        
    
    def verify_determinism(self, G: nx.MultiDiGraph) -> bool:
        """
        Check that there are no duplicate labels on non-RC nodes.
        RC nodes may appear visually non-deterministic (that is normal in a factored DFA).
        All other nodes must not have duplicate outgoing labels.
        """
        for node in G.nodes():
            if not 'RC' in str(node):  # Skip RC nodes
                labels = [d.get('label') for _, _, d in G.out_edges(node, data=True)]
                if len(labels) != len(set(labels)):
                    return False  # Duplicate found on non-RC node!
        return True
    
    def generate_comparison_report(self) -> str:
        """Create a comparison report between all three variants"""
        report = []
        report.append("=" * 80)
        report.append("BENCHMARK COMPARISON: NoEquivalenceClosure vs EquivalenceClosure vs NestedCalls")
        report.append("=" * 80)

        # Compare per test case
        for i, test_name in enumerate([r['graph_name'] for r in self.results['NoEquivalenceClosure']]):
            no_eq = self.results['NoEquivalenceClosure'][i]['result']
            eq = self.results['EquivalenceClosure'][i]['result']
            nested = self.results['NestedCalls'][i]['result']

            report.append(f"\n📊 Test: {test_name}")
            report.append("-" * 80)

            # SPEED
            report.append(f"\n⏱️  PERFORMANCE:")
            report.append(f"  NoEquiv:  {no_eq.total_time:.3f}s")
            report.append(f"  Equiv:    {eq.total_time:.3f}s")
            report.append(f"  Nested:   {nested.total_time:.3f}s")
            speedup = no_eq.total_time / eq.total_time if eq.total_time > 0 else 0
            report.append(f"  → Speedup (NoEquiv/Equiv): {speedup:.2f}x {'🚀' if speedup > 1 else ''}")

            # EFFECTIVENESS
            report.append(f"\n📦 COMPRESSION:")
            report.append(f"  NoEquiv:  {no_eq.nodes_before} → {no_eq.nodes_after} nodes ({no_eq.compression_ratio:.1%})")
            report.append(f"  Equiv:    {eq.nodes_before} → {eq.nodes_after} nodes ({eq.compression_ratio:.1%})")
            report.append(f"  Nested:   {nested.nodes_before} → {nested.nodes_after} nodes ({nested.compression_ratio:.1%})")

            ratios = {'NoEquiv': no_eq.compression_ratio, 'Equiv': eq.compression_ratio, 'Nested': nested.compression_ratio}
            best = max(ratios, key=ratios.get)
            report.append(f"  → Best compression: {best}")

            # CORRECTNESS
            report.append(f"\n✅ CORRECTNESS:")
            report.append(f"  NoEquiv:  Language OK: {no_eq.language_preserved}, Determinism: {no_eq.determinism_check}")
            if not no_eq.language_preserved and no_eq.language_mismatches:
                report.append(f"    → Mismatches (sample up to 2):")
                for m in no_eq.language_mismatches[:2]:
                    report.append(f"      - {m.splitlines()[3] if '\n' in m else m}")

            report.append(f"  Equiv:    Language OK: {eq.language_preserved}, Determinism: {eq.determinism_check}")
            if not eq.language_preserved and eq.language_mismatches:
                report.append(f"    → Mismatches (sample up to 2):")
                for m in eq.language_mismatches[:2]:
                    report.append(f"      - {m.splitlines()[3] if '\n' in m else m}")

            report.append(f"  Nested:   Language OK: {nested.language_preserved}, Determinism: {nested.determinism_check}")
            if not nested.language_preserved and nested.language_mismatches:
                report.append(f"    → Mismatches (sample up to 2):")
                for m in nested.language_mismatches[:2]:
                    report.append(f"      - {m.splitlines()[3] if '\n' in m else m}")

        return "\n".join(report)
    
    def save_results(self, filename: str = "benchmark_results.json"):
        """Save all raw data for later analysis"""
        # Convert dataclasses to dict for JSON serialization
        json_data = {}
        for variant, results in self.results.items():
            json_data[variant] = []
            for r in results:
                result_dict = {
                    'graph_name': r['graph_name'],
                    'total_time': r['result'].total_time,
                    'nodes_before': r['result'].nodes_before,
                    'nodes_after': r['result'].nodes_after,
                    'compression_ratio': r['result'].compression_ratio,
                    'language_preserved': r['result'].language_preserved,
                    'language_mismatch_count': len(r['result'].language_mismatches) if r['result'].language_mismatches else 0,
                    'language_mismatch_sample': r['result'].language_mismatches[:3] if r['result'].language_mismatches else [],
                    'determinism_check': r['result'].determinism_check
                }
                json_data[variant].append(result_dict)
        
        with open(filename, 'w') as f:
            json.dump(json_data, f, indent=2)


def load_graph(input_file: str) -> nx.MultiDiGraph:
    """Load a DOT file as a NetworkX MultiDiGraph."""
    try:
        # nx_pydot.read_dot returns a graph; we cast it to MultiDiGraph
        graph = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(input_file))
        return graph
    except Exception as e:
        print(f"❌ Error reading file '{input_file}': {e}")
        raise


def load_test_configs_from_directory(directory: str, label_prefix: str = "") -> List[Tuple[str, str]]:
    """
    Load all .dot files from a directory as test configs.
    Returns a list of (name, filepath) tuples.
    """
    import glob
    
    # Find all .dot files in the directory
    dot_files = sorted(glob.glob(os.path.join(directory, "*.dot")))
    
    configs = []
    for filepath in dot_files:
        # Extract filename without extension
        filename = os.path.basename(filepath)
        name = os.path.splitext(filename)[0]
        
        # Optionally add prefix
        if label_prefix:
            name = f"{label_prefix}_{name}"
        
        configs.append((name, filepath))
    
    return configs


# EXAMPLE USAGE
if __name__ == "__main__":
    suite = BenchmarkSuite()
    
    # ============================================
    # TEST CONFIGURATIONS - CHOOSE BELOW
    # ============================================
    # Change TEST_MODE to switch between test scenarios:
    # - 'miscellaneous'    : Small, fast tests (miscellaneous examples)
    # - 'real_world'       : Larger real-world examples (url_parser, etc.)
    # - 'test_automata'    : All deel_*.dot files from input/test_automata/
    # - 'custom'           : Custom list - add your own tests here
    TEST_MODE = 'real_world'  # ← CHANGE THIS LINE
    
    if TEST_MODE == 'miscellaneous':
        # Small test cases for quick feedback
        test_configs = [
            ("bigSmall", "/Users/milcokats/Projects/Compression Cyclic DFA/input/miscellaneous/bigSmall.dot"),
            ("differentEntries", "/Users/milcokats/Projects/Compression Cyclic DFA/input/miscellaneous/differentEntries.dot"),
            ("fourComponents", "/Users/milcokats/Projects/Compression Cyclic DFA/input/miscellaneous/fourComponents.dot"),
            ("multipleExits2", "/Users/milcokats/Projects/Compression Cyclic DFA/input/miscellaneous/multipleExits2.dot"),
            ("commonState", "/Users/milcokats/Projects/Compression Cyclic DFA/input/miscellaneous/commonState.dot")
        ]
        print("📊 Mode: QUICK (small test cases)")
        
    elif TEST_MODE == 'real_world':
        # Larger real-world examples
        test_configs = [
            ("url-parser", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-parser.dot"),
            ("url-53", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-53-reduced-percent.dot"),
            ("url-170", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-170-reduced-https.dot"),
            ("url-271", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-271-reduced-ipv6-noslash.dot"),
            ("url-442", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-442-reduced-ipv6.dot"),
            # Add more large files here:
            # ("other_large", "/path/to/other_large.dot"),
        ]
        print("📊 Mode: REAL_WORLD (real-world examples)")
        
    elif TEST_MODE == 'test_automata':
        # All test_automata examples (deel_1.dot to deel_11.dot)
        test_automata_dir = "/Users/milcokats/Projects/Compression Cyclic DFA/input/test_automata"
        test_configs = load_test_configs_from_directory(test_automata_dir)
        print("📊 Mode: TEST_AUTOMATA (deel_1.dot - deel_11.dot)")
        
    elif TEST_MODE == 'custom':
        # Assemble your own combination
        test_configs = [
            ("bigSmall", "/Users/milcokats/Projects/Compression Cyclic DFA/input/miscellaneous/bigSmall.dot"),
            ("url_parser", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world_examples/url_parser.dot"),
            # Add your test cases here
        ]
        print("📊 Mode: CUSTOM (custom selection)")
    
    else:
        raise ValueError(f"Unknown TEST_MODE: {TEST_MODE}")
    
    print(f"Tests: {len(test_configs)}")
    print("="*80)
    
    for name, path in test_configs:
        print(f"\n{'='*80}")
        print(f"Loading & Testing: {name}")
        print(f"Path: {path}")
        print('='*80)
        
        try:
            # Load the graph
            graph = load_graph(path)
            print(f"✓ Graph loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
            
            # Run all three variants
            print("\n  Testing NoEquivalenceClosure...")
            result_no_eq = suite.run_benchmark(graph, name, 'NoEquivalenceClosure')
            print(f"  ✓ Completed: {result_no_eq.nodes_before} → {result_no_eq.nodes_after} nodes ({result_no_eq.compression_ratio:.1%})")

            print("\n  Testing EquivalenceClosure...")
            result_eq = suite.run_benchmark(graph, name, 'EquivalenceClosure')
            print(f"  ✓ Completed: {result_eq.nodes_before} → {result_eq.nodes_after} nodes ({result_eq.compression_ratio:.1%})")

            print("\n  Testing NestedCalls...")
            result_nested = suite.run_benchmark(graph, name, 'NestedCalls')
            print(f"  ✓ Completed: {result_nested.nodes_before} → {result_nested.nodes_after} nodes ({result_nested.compression_ratio:.1%})")
            
        except Exception as e:
            print(f"\n❌ Error testing {name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Generate report at the end
    if suite.results['NoEquivalenceClosure']:
        print("\n" + suite.generate_comparison_report())
        suite.save_results()
        print(f"\n✓ Results saved to benchmark_results.json")
    else:
        print("\n⚠️  No results to report.")
