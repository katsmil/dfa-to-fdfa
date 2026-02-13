"""
LANGUAGE PRESERVATION TESTING
==============================

Test of de gefactoriseerde automaat dezelfde taal accepteert als het origineel.
Dit is essentieel voor je correctheidsbewijs en variant-onafhankelijk.
"""

import networkx as nx
import random
from typing import List, Set, Tuple, Optional
from collections import deque

class DFAExecutor:
    """
    Voert strings uit op een (gefactoriseerde) DFA.
    Ondersteunt zowel normale DFA als DFA met RC nodes en stack.
    """
    
    def __init__(self, G: nx.MultiDiGraph):
        self.G = G
        self.start_node = self._find_start_node()
        self.accepting_nodes = self._find_accepting_nodes()
    
    def _find_start_node(self) -> str:
        """Vind de startnode (in-degree 0, of heeft 'start' attribuut)"""
        for node in self.G.nodes():
            if self.G.in_degree(node) == 0:
                return node
            if self.G.nodes[node].get('start') == True:
                return node
        # Fallback: eerste node
        return list(self.G.nodes())[0]
    
    def _find_accepting_nodes(self) -> Set[str]:
        """Vind accepting states (doublecircle shape)"""
        return {
            node for node in self.G.nodes()
            if self.G.nodes[node].get('shape') == 'doublecircle'
        }
    
    def execute(self, input_string: List[str]) -> Tuple[bool, str]:
        """
        Voer een string uit op de automaat.
        
        Returns:
            (accepted: bool, trace: str) - of de string geaccepteerd wordt en executie trace
        """
        current = self.start_node
        stack = []  # Voor RC calls
        trace = [f"Start: {current}"]
        
        for symbol in input_string:
            # Check of current een RC node is
            if 'RC' in current:
                # CALL: Push op stack en spring naar subroutine
                subroutine_start = self._get_subroutine_entry(current)
                if subroutine_start:
                    stack.append(current)
                    current = subroutine_start
                    trace.append(f"  CALL {current} (stack: {len(stack)})")
            
            # Probeer transitie te nemen
            next_node = self._take_transition(current, symbol)
            
            if next_node is None:
                # Geen transitie beschikbaar
                # Check of we in een frontier zijn en moeten returnen
                if stack and self._is_frontier(current):
                    # RETURN: Pop stack en probeer vanaf RC
                    rc_node = stack.pop()
                    trace.append(f"  RETURN to {rc_node}")
                    next_node = self._take_transition(rc_node, symbol)
                    
                    if next_node is None:
                        trace.append(f"  REJECT: No transition for '{symbol}' from {rc_node}")
                        return False, "\n".join(trace)
                else:
                    trace.append(f"  REJECT: No transition for '{symbol}' from {current}")
                    return False, "\n".join(trace)
            
            current = next_node
            trace.append(f"  '{symbol}' → {current}")
        
        # Check of we in accepting state zijn
        accepted = current in self.accepting_nodes
        trace.append(f"\nFinal: {current} ({'ACCEPT' if accepted else 'REJECT'})")
        
        return accepted, "\n".join(trace)
    
    def _take_transition(self, node: str, symbol: str) -> Optional[str]:
        """Vind de target node voor een transitie met gegeven label"""
        for _, target, data in self.G.out_edges(node, data=True):
            if data.get('label') == symbol:
                return target
        return None
    
    def _get_subroutine_entry(self, rc_node: str) -> Optional[str]:
        """
        Vind de entry node van de subroutine die bij deze RC hoort.
        In de gefactoriseerde graaf zijn dit de nodes met cluster attribuut.
        """
        # Zoek naar nodes in dezelfde cluster
        for node in self.G.nodes():
            node_data = self.G.nodes[node]
            if 'cluster' in node_data and 'subroutine' in node_data['cluster']:
                # Dit is waarschijnlijk de entry (vaak index 0)
                if node.endswith('_0'):
                    return node
        return None
    
    def _is_frontier(self, node: str) -> bool:
        """Check of een node een frontier is (accepting + heeft externe exits)"""
        if node not in self.accepting_nodes:
            return False
        # In de gefactoriseerde graaf zijn frontiers accepting nodes in subroutines
        return 'SUB_' in node


class LanguagePreservationTester:
    """
    Test of factorisatie de taal behoudt via random walk testing.
    """
    
    def __init__(self, G_original: nx.MultiDiGraph, G_factored: nx.MultiDiGraph):
        self.executor_orig = DFAExecutor(G_original)
        self.executor_fact = DFAExecutor(G_factored)
        self.alphabet = self._extract_alphabet(G_original)
    
    def _extract_alphabet(self, G: nx.MultiDiGraph) -> List[str]:
        """Verzamel alle unieke labels in de graaf"""
        labels = set()
        for _, _, data in G.edges(data=True):
            if 'label' in data:
                labels.add(data['label'])
        return sorted(labels)
    
    def generate_random_strings(self, count: int = 100, max_length: int = 20) -> List[List[str]]:
        """Genereer random test strings"""
        strings = []
        for _ in range(count):
            length = random.randint(1, max_length)
            string = [random.choice(self.alphabet) for _ in range(length)]
            strings.append(string)
        return strings
    
    def test_equivalence(self, test_strings: Optional[List[List[str]]] = None, 
                        verbose: bool = False) -> Tuple[bool, List[str]]:
        """
        Test of beide automaten equivalent zijn op de gegeven strings.
        
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
                    f"String: {' '.join(string)}\n"
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
        """Voer uitgebreide test uit en genereer rapport"""
        print(f"🧪 Testing language preservation with {num_tests} random strings...")
        
        test_strings = self.generate_random_strings(count=num_tests)
        all_match, mismatches = self.test_equivalence(test_strings, verbose=False)
        
        report = []
        report.append("\n" + "="*80)
        report.append("LANGUAGE PRESERVATION TEST RESULTS")
        report.append("="*80)
        report.append(f"Total tests: {num_tests}")
        report.append(f"Passed: {num_tests - len(mismatches)}")
        report.append(f"Failed: {len(mismatches)}")
        
        if all_match:
            report.append("\n✅ SUCCESS: All tests passed! Language is preserved.")
        else:
            report.append(f"\n❌ FAILURE: {len(mismatches)} mismatches found!")
            report.append("\nFirst 3 mismatches:")
            for mismatch in mismatches[:3]:
                report.append(mismatch)
        
        return "\n".join(report)


# VOORBEELD GEBRUIK
if __name__ == "__main__":
    # Laad beide versies
    G_original = nx.nx_pydot.read_dot("input/joshua/bigSmall.dot")
    G_factored = nx.nx_pydot.read_dot("output/bigSmall_factorized.dot")
    
    # Test equivalentie
    tester = LanguagePreservationTester(G_original, G_factored)
    report = tester.run_comprehensive_test(num_tests=1000)
    print(report)