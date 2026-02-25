"""
LANGUAGE PRESERVATION TESTING
==============================

Test of de gefactoriseerde automaat dezelfde taal accepteert als het origineel.
Dit is essentieel voor correctheidsbewijs en variant-onafhankelijk.
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
        self.G = self._normalize_labels(G)
        self.start_node = self._find_start_node()
        # Volg epsilon-transities naar de echte start node
        self.start_node = self._follow_epsilon_transitions(self.start_node)
        self.accepting_nodes = self._find_accepting_nodes()
    
    def _follow_epsilon_transitions(self, node: str) -> str:
        """Volg epsilon-transities (transities zonder label) tot we een labeled node bereiken"""
        visited = set()
        current = node
        
        while current not in visited:
            visited.add(current)
            # Zoek transities zonder label (epsilon-transities)
            epsilon_target = None
            has_labeled = False
            
            for _, target, data in self.G.out_edges(current, data=True):
                if 'label' not in data or data.get('label') is None:
                    epsilon_target = target
                else:
                    has_labeled = True
            
            # Als deze node labeled edges heeft, dit is onze echte start
            if has_labeled:
                return current
            
            # Anders volgen we de epsilon-transitie
            if epsilon_target and epsilon_target not in visited:
                current = epsilon_target
            else:
                break
        
        return current
    
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
        """Vind accepting states (doublecircle shape of peripheries=2)"""
        accepting = set()
        for node in self.G.nodes():
            nd = self.G.nodes[node]
            # Check for doublecircle shape
            if nd.get('shape') == 'doublecircle':
                accepting.add(node)
            # Also check for peripheries=2 (used in factored graphs)
            elif nd.get('peripheries') == 2 or nd.get('peripheries') == '2':
                accepting.add(node)
        return accepting
    
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
        
        # Volg epsilon-transities naar accepting state
        current = self._follow_epsilon_to_accepting(current)
        
        # Check of we in accepting state zijn
        # If the accepting node belongs to a subroutine, it should not count
        # as accepting for the whole automaton — subroutine accepting states
        # are frontiers that only allow returning to the caller.
        accepted = False
        if current in self.accepting_nodes:
            nd = self.G.nodes.get(current, {})
            cluster = nd.get('cluster')
            if not (isinstance(cluster, str) and 'subroutine' in cluster):
                accepted = True
        trace.append(f"\nFinal: {current} ({'ACCEPT' if accepted else 'REJECT'})")
        
        return accepted, "\n".join(trace)
    
    def _follow_epsilon_to_accepting(self, node: str) -> str:
        """Volg epsilon-transities tot we een accepting node vinden (of geen epsilon meer)"""
        visited = set()
        current = node
        
        while current not in visited:
            visited.add(current)
            
            if current in self.accepting_nodes:
                return current
            
            # Zoek epsilon-transities
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
    
    def _take_transition(self, node: str, symbol: str) -> Optional[str]:
        """Vind de target node voor een transitie met gegeven label, en volg epsilon-transities"""
        for _, target, data in self.G.out_edges(node, data=True):
            if data.get('label') == symbol:
                # Volg epsilon-transities van target totdat we een node met labeled outgoing vinden
                return self._follow_epsilon_transitions(target)
        return None
    
    def _get_subroutine_entry(self, rc_node: str) -> Optional[str]:
        """
        Vind de entry node van de subroutine die bij deze RC hoort.
        In de gefactoriseerde graaf zijn dit de nodes met cluster attribuut.
        """
        # Probeer eerst de clusternaam uit het RC label te halen (bijv. 'subroutine_1')
        node_data = self.G.nodes.get(rc_node, {})
        label = node_data.get('label', '')
        cluster_name = None
        if isinstance(label, str) and 'subroutine' in label:
            # zoek naar woord 'subroutine_<id>' in label
            parts = label.replace('\n', ' ').split()
            for p in parts:
                if p.startswith('subroutine'):
                    cluster_name = p
                    break

        # Als we een clusternaam hebben, zoek naar node met precies die cluster
        if cluster_name:
            for node in self.G.nodes():
                nd = self.G.nodes[node]
                if nd.get('cluster') == cluster_name and str(node).endswith('_0'):
                    return node

        # Fallback: zoek naar nodes die een cluster attribuut bevatten met 'subroutine'
        for node in self.G.nodes():
            nd = self.G.nodes[node]
            cluster = nd.get('cluster')
            if isinstance(cluster, str) and 'subroutine' in cluster and str(node).endswith('_0'):
                return node

        return None
    
    def _is_frontier(self, node: str) -> bool:
        """Check of een node een frontier is (accepting + heeft externe exits)"""
        if node not in self.accepting_nodes:
            return False

        # Controleer of deze node behoort tot een subroutine via node attribuut
        nd = self.G.nodes.get(node, {})
        cluster = nd.get('cluster')
        if isinstance(cluster, str) and 'subroutine' in cluster:
            return True

        # Fallback: sommige nodes gebruiken naamconventie 'SUB_<...>'
        if 'SUB_' in str(node):
            return True

        return False

    def _normalize_labels(self, G: nx.MultiDiGraph) -> nx.MultiDiGraph:
        """
        Clean up edge labels: remove extra quotes and normalize whitespace.
        This handles cases where labels are stored as '"a"' instead of 'a'.
        """
        import copy
        G_norm = copy.deepcopy(G)
        
        for u, v, key, data in G_norm.edges(keys=True, data=True):
            if 'label' in data:
                label = data['label']
                # Convert to string if not already
                if not isinstance(label, str):
                    label = str(label)
                # Remove surrounding quotes if they exist
                if len(label) >= 2 and ((label[0] == '"' and label[-1] == '"') or 
                                        (label[0] == "'" and label[-1] == "'")):
                    label = label[1:-1]
                # Strip whitespace
                label = label.strip()
                # Update the edge label
                G_norm[u][v][key]['label'] = label
        
        return G_norm


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


def verify_language_preservation(G_original: nx.MultiDiGraph, G_factored: nx.MultiDiGraph,
                                 num_tests: int = 200, max_length: int = 20,
                                 verbose: bool = False) -> Tuple[bool, List[str]]:
    """
    Convenience wrapper to run randomized language-preservation tests from other modules.

    Returns (all_match, mismatches)
    """
    tester = LanguagePreservationTester(G_original, G_factored)

    # If there is no alphabet (no labeled edges) we still want to compare
    # acceptance for the empty string; in that case build a single empty test.
    if not tester.alphabet:
        test_strings = [[]]
    else:
        test_strings = tester.generate_random_strings(count=num_tests, max_length=max_length)

    all_match, mismatches = tester.test_equivalence(test_strings, verbose=verbose)
    return all_match, mismatches


def compare_graphs_on_string(G_original: nx.MultiDiGraph, G_factored: nx.MultiDiGraph,
                             input_string, verbose: bool = True) -> dict:
    """
    Compare two graphs on a single input string.

    Args:
        G_original: original DFA as a NetworkX MultiDiGraph
        G_factored: factored DFA as a NetworkX MultiDiGraph
        input_string: either a string like 'axxa' or a list of symbols ['a','x','x','a']
        verbose: when True print traces and results

    Returns a dict with acceptance booleans and traces for both graphs.
    """
    # Normalize input_string to list of symbols
    if isinstance(input_string, str):
        symbols = list(input_string)
    else:
        symbols = list(input_string)

    exec_orig = DFAExecutor(G_original)
    exec_fact = DFAExecutor(G_factored)

    acc_orig, trace_orig = exec_orig.execute(symbols)
    acc_fact, trace_fact = exec_fact.execute(symbols)

    result = {
        'string': ''.join(symbols),
        'accepted_original': acc_orig,
        'accepted_factored': acc_fact,
        'trace_original': trace_orig,
        'trace_factored': trace_fact
    }

    if verbose:
        print(f"String: {result['string']}")
        print(f"Original: {'ACCEPT' if acc_orig else 'REJECT'}")
        print(result['trace_original'])
        print('\nFactored: ' + ('ACCEPT' if acc_fact else 'REJECT'))
        print(result['trace_factored'])

    return result


# VOORBEELD GEBRUIK
if __name__ == "__main__":
    import sys

    # CLI: python language_preservation.py <orig.dot> <factored.dot> <string>
    if len(sys.argv) >= 4:
        orig_path = sys.argv[1]
        fact_path = sys.argv[2]
        input_str = sys.argv[3]

        G_original = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(orig_path))
        G_factored = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(fact_path))

        compare_graphs_on_string(G_original, G_factored, input_str, verbose=True)
    else:
        # fallback example
        G_original = nx.nx_pydot.read_dot("input/test_automata/deel_8.dot")
        G_factored = nx.nx_pydot.read_dot("output/deel_8_factorized.dot")
        tester = LanguagePreservationTester(G_original, G_factored)
        report = tester.run_comprehensive_test(num_tests=1000)
        print(report)