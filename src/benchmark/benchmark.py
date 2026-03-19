"""
VARIANT-AGNOSTIC BENCHMARK SUITE
=================================

Dit framework test beide varianten (EquivalenceClosure en NoEquivalenceClosure)
op dezelfde inputs en verzamelt objectieve metrics.
"""

import time
import networkx as nx
from dataclasses import dataclass
from typing import List, Dict, Tuple
import json
import sys
import os

from approaches.shared import factorize as shared_factorize

# CRITICAL FIX: Add project root to Python path
# This must happen BEFORE any custom imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # Should be .../src/
# Ensure project root is importable so we can `import language_preservation...`
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Also add the language_preservation directory so that
# targeted_language_preservation.py can find dfa_executor.py via direct import
language_preservation_dir = os.path.join(project_root, "language_preservation")
if language_preservation_dir not in sys.path:
    sys.path.insert(0, language_preservation_dir)

# Setup variant module loaders
def load_variant_module(variant: str, module_name: str, analyze_module=None):
    """
    Laad dynamisch een analyze/factorize module voor een variant.
    Dit vermijdt relative import problemen door modules in sys.modules in te spuiten.
    
    Args:
        variant: 'NoEquivalenceClosure' or 'EquivalenceClosure'
        module_name: 'analyze' or 'factorize'
        analyze_module: (optional) Al geladen analyze module (nodig voor factorize)
    """
    if module_name == 'factorize':
        # Altijd de gedeelde factorize gebruiken
        return shared_factorize
    # Voor analyze blijft variant-specifiek
    import importlib.util
    if variant == 'NoEquivalenceClosure':
        module_path = os.path.join(
            project_root, "approaches", "no_equivalence_closure", 
            f"{module_name}.py"
        )
    else:  # EquivalenceClosure
        module_path = os.path.join(
            project_root, "approaches", "equivalence_closure", 
            f"{module_name}.py"
        )
    module_name_unique = f"{variant}_{module_name}"
    spec = importlib.util.spec_from_file_location(module_name_unique, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name_unique] = module
    if module_name == 'factorize' and analyze_module is not None:
        sys.modules['analyze'] = analyze_module
    spec.loader.exec_module(module)
    return module

def count_real_nodes(G: nx.MultiDiGraph) -> int:
    """Tel aantal nodes, exclusief dummy start nodes (__start_*)."""
    return sum(1 for node in G.nodes() if not str(node).startswith('__start_'))

def count_real_edges(G: nx.MultiDiGraph) -> int:
    """Tel aantal edges, exclusief edges van/naar dummy start nodes."""
    count = 0
    for u, v, key, data in G.edges(data=True, keys=True):
        if not str(u).startswith('__start_') and not str(v).startswith('__start_'):
            count += 1
    return count

@dataclass
class BenchmarkResult:
    """Metrics die voor beide varianten gemeten worden"""
    # Timing
    analysis_time: float
    factorization_time: float
    total_time: float
    
    # Effectiviteit
    structures_found: int
    # total_locations: int
    nodes_before: int
    nodes_after: int
    edges_before: int
    edges_after: int
    
    # Kwaliteit
    compression_ratio: float  # nodes_after / nodes_before
    largest_structure_size: int
    avg_structure_size: float
    # effective_count_sum: int  # Som van alle effective_counts
    
    # Correctheid
    language_preserved: bool  # Via random walk testing
    determinism_check: bool   # Geen duplicate labels op RC nodes
    # Details from language preservation testing
    language_mismatches: List[str]

class BenchmarkSuite:
    """
    Test beide varianten op identieke inputs.
    Onafhankelijk van welke variant je kiest, deze data is nuttig.
    """
    
    def __init__(self):
        self.results = {
            'NoEquivalenceClosure': [],
            'EquivalenceClosure': []
        }
    
    def run_benchmark(self, graph: nx.MultiDiGraph, name: str, variant: str):
        """Run één test voor één variant"""
        
        start_total = time.time()
        
        # PRE-METRICS (exclusief dummy nodes)
        nodes_before = count_real_nodes(graph)
        edges_before = count_real_edges(graph)
        
        # ANALYSIS PHASE
        start_analysis = time.time()
        try:
            analyze_module = load_variant_module(variant, 'analyze')
            structures = analyze_module.run_analysis(graph.copy(), min_size=2)
        except Exception as e:
            print(f"\n❌ Error loading analyze module for {variant}:")
            print(f"   {e}")
            raise
            
        analysis_time = time.time() - start_analysis
        
        # FACTORIZATION PHASE
        start_fact = time.time()
        try:
            # Gebruik altijd de gedeelde factorize
            factored_graph = shared_factorize.apply_factorization(
                graph.copy(),
                structures,
                # strict_filter=(variant == 'EquivalenceClosure')
                strict_filter=False
            )
        except Exception as e:
            print(f"\n❌ Error loading factorize module for {variant}:")
            print(f"   {e}")
            raise
        factorization_time = time.time() - start_fact
        
        total_time = time.time() - start_total
        
        # POST-METRICS (exclusief dummy nodes)
        nodes_after = count_real_nodes(factored_graph)
        edges_after = count_real_edges(factored_graph)
        
        # KWALITEITSMETRICS
        if structures:
            largest = max(s.overlap_size for s in structures)
            avg_size = sum(s.overlap_size for s in structures) / len(structures)
            # effective_sum = sum(s.effective_count for s in structures)
        else:
            largest = 0
            avg_size = 0
            # effective_sum = 0
        
        # CORRECTHEIDSCHECK (zie functie hieronder)
        language_ok, mismatches = self.verify_language_preservation(graph, factored_graph)
        determinism_ok = self.verify_determinism(factored_graph)
        
        result = BenchmarkResult(
            analysis_time=analysis_time,
            factorization_time=factorization_time,
            total_time=total_time,
            structures_found=len(structures),
            # total_locations=sum(len(s.locations) for s in structures),
            nodes_before=nodes_before,
            nodes_after=nodes_after,
            edges_before=edges_before,
            edges_after=edges_after,
            compression_ratio=1.0 - (nodes_after / nodes_before) if nodes_before > 0 else 0.0,
            largest_structure_size=largest,
            avg_structure_size=avg_size,
            # effective_count_sum=effective_sum,
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
    
    # def verify_determinism(self, G: nx.MultiDiGraph) -> bool:
    #     """
    #     Check dat er geen duplicate labels op RC nodes zijn.
    #     Dit moet voor beide varianten gelden!
    #     """
    #     for node in G.nodes():
    #         if 'RC' in str(node):  # Convert to string to handle different node types
    #             labels = [d.get('label') for _, _, d in G.out_edges(node, data=True)]
    #             if len(labels) != len(set(labels)):
    #                 return False  # Duplicate gevonden!
    #     return True
    
    def verify_determinism(self, G: nx.MultiDiGraph) -> bool:
        """
        Check dat er geen duplicate labels op non-RC nodes zijn.
        RC nodes mogen visueel nondeterministisch lijken (dat is normaal in een gefactorde DFA).
        Alle andere nodes mogen geen duplicate outgoing labels hebben.
        """
        for node in G.nodes():
            if not 'RC' in str(node):  # Sla RC nodes over
                labels = [d.get('label') for _, _, d in G.out_edges(node, data=True)]
                if len(labels) != len(set(labels)):
                    return False  # Duplicate gevonden op niet-RC node!
        return True
    
    def generate_comparison_report(self) -> str:
        """Maak een vergelijkingsrapport tussen beide varianten"""
        report = []
        report.append("=" * 80)
        report.append("BENCHMARK COMPARISON: EquivalenceClosure vs NoEquivalenceClosure")
        report.append("=" * 80)
        
        # Per testcase vergelijken
        for i, test_name in enumerate([r['graph_name'] for r in self.results['NoEquivalenceClosure']]):
            no_eq = self.results['NoEquivalenceClosure'][i]['result']
            eq = self.results['EquivalenceClosure'][i]['result']
            
            report.append(f"\n📊 Test: {test_name}")
            report.append("-" * 80)
            
            # SNELHEID
            report.append(f"\n⏱️  PERFORMANCE:")
            report.append(f"  NoEquiv:  {no_eq.total_time:.3f}s (analysis: {no_eq.analysis_time:.3f}s)")
            report.append(f"  Equiv:    {eq.total_time:.3f}s (analysis: {eq.analysis_time:.3f}s)")
            speedup = no_eq.total_time / eq.total_time if eq.total_time > 0 else 0
            report.append(f"  → Speedup: {speedup:.2f}x {'🚀' if speedup > 1 else ''}")
            
            # EFFECTIVITEIT
            report.append(f"\n📦 COMPRESSION:")
            report.append(f"  NoEquiv:  {no_eq.nodes_before} → {no_eq.nodes_after} nodes ({no_eq.compression_ratio:.1%})")
            report.append(f"  Equiv:    {eq.nodes_before} → {eq.nodes_after} nodes ({eq.compression_ratio:.1%})")
            
            better_compression = "NoEquiv" if no_eq.compression_ratio > eq.compression_ratio else "Equiv"
            report.append(f"  → Better compression: {better_compression}")
            
            # # KWALITEIT
            # report.append(f"\n🎯 QUALITY:")
            # report.append(f"  NoEquiv:  {no_eq.structures_found} structures, {no_eq.total_locations} locations")
            # report.append(f"  Equiv:    {eq.structures_found} structures, {eq.total_locations} locations")
            
            # CORRECTHEID
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
        
        return "\n".join(report)
    
    def save_results(self, filename: str = "benchmark_results.json"):
        """Sla alle ruwe data op voor latere analyse"""
        # Convert dataclasses to dict voor JSON serialization
        json_data = {}
        for variant, results in self.results.items():
            json_data[variant] = []
            for r in results:
                result_dict = {
                    'graph_name': r['graph_name'],
                    'analysis_time': r['result'].analysis_time,
                    'factorization_time': r['result'].factorization_time,
                    'total_time': r['result'].total_time,
                    'structures_found': r['result'].structures_found,
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
    """Laadt een DOT bestand in als een NetworkX MultiDiGraph."""
    try:
        # nx_pydot.read_dot geeft een graph terug; we casten hem naar MultiDiGraph
        graph = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(input_file))
        return graph
    except Exception as e:
        print(f"❌ Fout bij inlezen bestand '{input_file}': {e}")
        raise


def load_test_configs_from_directory(directory: str, label_prefix: str = "") -> List[Tuple[str, str]]:
    """
    Laadt alle .dot files uit een directory als test configs.
    Retourneert een list van (name, filepath) tuples.
    """
    import glob
    
    # Vind alle .dot files in de directory
    dot_files = sorted(glob.glob(os.path.join(directory, "*.dot")))
    
    configs = []
    for filepath in dot_files:
        # Extract filename without extension
        filename = os.path.basename(filepath)
        name = os.path.splitext(filename)[0]
        
        # Voeg optioneel prefix toe
        if label_prefix:
            name = f"{label_prefix}_{name}"
        
        configs.append((name, filepath))
    
    return configs


# VOORBEELDGEBRUIK
if __name__ == "__main__":
    suite = BenchmarkSuite()
    
    # ============================================
    # TEST CONFIGURATIONS - KIES HIERONDER
    # ============================================
    # Wijzig TEST_MODE om te switchen tussen test scenarios:
    # - 'joshua'           : Kleine, snelle testen (joshua voorbeelden)
    # - 'real_world'           : Grotere real-world voorbeelden (url_parser, etc.)
    # - 'test_automata'   : Alle deel_*.dot files uit input/test_automata/
    # - 'custom'          : Aangepaste list - voeg je eigen testen toe
    TEST_MODE = 'real_world'  # ← WIJZIG DEZE LIJN
    
    if TEST_MODE == 'joshua':
        # Kleine testcases voor snelle feedback
        test_configs = [
            ("bigSmall", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/bigSmall.dot"),
            ("differentEntries", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/differentEntries.dot"),
            ("fourComponents", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/fourComponents.dot"),
            ("multipleExits2", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/multipleExits2.dot"),
            ("commonState", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/commonState.dot")
        ]
        print("📊 Mode: QUICK (kleine testcases)")
        
    elif TEST_MODE == 'real_world':
        # Grotere real-world voorbeelden
        test_configs = [
            # ("url-parser", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world_examples/url-parser.dot"),
            ("url-53", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-53-reduced-percent.dot"),
            ("url-170", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-170-reduced-https.dot"),
            ("url-271", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-271-reduced-ipv6-noslash.dot"),
            ("url-442", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world/url-442-reduced-ipv6.dot"),
            # Voeg hier meer grote files toe:
            # ("other_large", "/path/to/other_large.dot"),
        ]
        print("📊 Mode: REAL_WORLD (real-world voorbeelden)")
        
    elif TEST_MODE == 'test_automata':
        # Alle test_automata voorbeelden (deel_1.dot t/m deel_11.dot)
        test_automata_dir = "/Users/milcokats/Projects/Compression Cyclic DFA/input/test_automata"
        test_configs = load_test_configs_from_directory(test_automata_dir)
        print("📊 Mode: TEST_AUTOMATA (deel_1.dot - deel_11.dot)")
        
    elif TEST_MODE == 'custom':
        # Zelf je combinatie samenstellen
        test_configs = [
            ("bigSmall", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/bigSmall.dot"),
            ("url_parser", "/Users/milcokats/Projects/Compression Cyclic DFA/input/real_world_examples/url_parser.dot"),
            # Voeg je test cases hier toe
        ]
        print("📊 Mode: CUSTOM (zelf samengesteld)")
    
    else:
        raise ValueError(f"Onbekende TEST_MODE: {TEST_MODE}")
    
    print(f"Tests: {len(test_configs)}")
    print("="*80)
    
    for name, path in test_configs:
        print(f"\n{'='*80}")
        print(f"Loading & Testing: {name}")
        print(f"Path: {path}")
        print('='*80)
        
        try:
            # Laad de graaf
            graph = load_graph(path)
            print(f"✓ Graph loaded: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
            
            # Run beide varianten
            print("\n  Testing NoEquivalenceClosure...")
            result_no_eq = suite.run_benchmark(graph, name, 'NoEquivalenceClosure')
            print(f"  ✓ Completed: {result_no_eq.structures_found} structures found")
            
            print("\n  Testing EquivalenceClosure...")
            result_eq = suite.run_benchmark(graph, name, 'EquivalenceClosure')
            print(f"  ✓ Completed: {result_eq.structures_found} structures found")
            
        except Exception as e:
            print(f"\n❌ Error testing {name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Genereer rapport aan het eind
    if suite.results['NoEquivalenceClosure']:
        print("\n" + suite.generate_comparison_report())
        suite.save_results()
        print(f"\n✓ Results saved to benchmark_results.json")
    else:
        print("\n⚠️  Geen resultaten om te rapporteren.")