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

# CRITICAL FIX: Add project root to Python path
# This must happen BEFORE any custom imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # Should be .../code/

# Use insert(0) to give priority to our modules
sys.path.insert(0, project_root)

# Debug: Verify paths (comment out after testing)
print(f"DEBUG: Current dir: {current_dir}")
print(f"DEBUG: Project root (added to path): {project_root}")
print(f"DEBUG: Looking for modules in: {project_root}")

@dataclass
class BenchmarkResult:
    """Metrics die voor beide varianten gemeten worden"""
    # Timing
    analysis_time: float
    factorization_time: float
    total_time: float
    
    # Effectiviteit
    structures_found: int
    total_locations: int
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
        
        # PRE-METRICS
        nodes_before = graph.number_of_nodes()
        edges_before = graph.number_of_edges()
        
        # ANALYSIS PHASE
        start_analysis = time.time()
        try:
            if variant == 'NoEquivalenceClosure':
                from No_EquivalenceClosure.exclusive_frontiers.optimized.analyze import run_analysis
                structures = run_analysis(graph.copy(), min_size=2)
            else:
                from EquivalenceClosure.optimized.analyze import run_analysis as run_analysis_eq
                structures = run_analysis_eq(graph.copy(), min_size=2)
        except ImportError as e:
            print(f"\n❌ Import Error in {variant}:")
            print(f"   {e}")
            print(f"\n   Expected module path from: {project_root}")
            if variant == 'NoEquivalenceClosure':
                expected = os.path.join(project_root, "No_EquivalenceClosure", "exclusive_frontiers", "optimized", "analyze.py")
            else:
                expected = os.path.join(project_root, "EquivalenceClosure", "optimized", "analyze.py")
            print(f"   Looking for: {expected}")
            print(f"   File exists: {os.path.exists(expected)}")
            raise
            
        analysis_time = time.time() - start_analysis
        
        # FACTORIZATION PHASE
        start_fact = time.time()
        if variant == 'NoEquivalenceClosure':
            from No_EquivalenceClosure.exclusive_frontiers.optimized.factorize import apply_factorization
            factored_graph = apply_factorization(graph.copy(), structures)
        else:
            from EquivalenceClosure.optimized.factorize import apply_factorization as apply_eq
            factored_graph = apply_eq(graph.copy(), structures)
        factorization_time = time.time() - start_fact
        
        total_time = time.time() - start_total
        
        # POST-METRICS
        nodes_after = factored_graph.number_of_nodes()
        edges_after = factored_graph.number_of_edges()
        
        # KWALITEITSMETRICS
        if structures:
            largest = max(s.overlap_size for s in structures)
            avg_size = sum(s.overlap_size for s in structures) / len(structures)
            # effective_sum = sum(s.effective_count for s in structures)
        else:
            largest = 0
            avg_size = 0
            effective_sum = 0
        
        # CORRECTHEIDSCHECK (zie functie hieronder)
        language_ok = self.verify_language_preservation(graph, factored_graph)
        determinism_ok = self.verify_determinism(factored_graph)
        
        result = BenchmarkResult(
            analysis_time=analysis_time,
            factorization_time=factorization_time,
            total_time=total_time,
            structures_found=len(structures),
            total_locations=sum(len(s.locations) for s in structures),
            nodes_before=nodes_before,
            nodes_after=nodes_after,
            edges_before=edges_before,
            edges_after=edges_after,
            compression_ratio=nodes_after / nodes_before if nodes_before > 0 else 1.0,
            largest_structure_size=largest,
            avg_structure_size=avg_size,
            # effective_count_sum=effective_sum,
            language_preserved=language_ok,
            determinism_check=determinism_ok
        )
        
        self.results[variant].append({
            'graph_name': name,
            'result': result
        })
        
        return result
    
    def verify_language_preservation(self, G_orig: nx.MultiDiGraph, 
                                     G_fact: nx.MultiDiGraph) -> bool:
        """
        Test of beide automaten dezelfde strings accepteren.
        Gebruik random walk testing (zie implementatie hieronder).
        """
        # TODO: Implementeer random walk generator + acceptance check
        return True  # Placeholder
    
    def verify_determinism(self, G: nx.MultiDiGraph) -> bool:
        """
        Check dat er geen duplicate labels op RC nodes zijn.
        Dit moet voor beide varianten gelden!
        """
        for node in G.nodes():
            if 'RC' in str(node):  # Convert to string to handle different node types
                labels = [d.get('label') for _, _, d in G.out_edges(node, data=True)]
                if len(labels) != len(set(labels)):
                    return False  # Duplicate gevonden!
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
            
            better_compression = "NoEquiv" if no_eq.compression_ratio < eq.compression_ratio else "Equiv"
            report.append(f"  → Better compression: {better_compression}")
            
            # KWALITEIT
            report.append(f"\n🎯 QUALITY:")
            report.append(f"  NoEquiv:  {no_eq.structures_found} structures, {no_eq.total_locations} locations")
            report.append(f"  Equiv:    {eq.structures_found} structures, {eq.total_locations} locations")
            
            # CORRECTHEID
            report.append(f"\n✅ CORRECTNESS:")
            report.append(f"  NoEquiv:  Language OK: {no_eq.language_preserved}, Determinism: {no_eq.determinism_check}")
            report.append(f"  Equiv:    Language OK: {eq.language_preserved}, Determinism: {eq.determinism_check}")
        
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


# VOORBEELDGEBRUIK
if __name__ == "__main__":
    suite = BenchmarkSuite()
    
    # Test configurations
    test_configs = [
        ("bigSmall", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/bigSmall.dot"),
        ("differentEntries", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/differentEntries.dot"),
        ("fourComponents", "/Users/milcokats/Projects/Compression Cyclic DFA/input/joshua/fourComponents.dot")
    ]
    
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