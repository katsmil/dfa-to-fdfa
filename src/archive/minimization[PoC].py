import pydot
import sys
from automata.fa.dfa import DFA
from collections import defaultdict


def parse_dot(dot_string):
    graphs = pydot.graph_from_dot_data(dot_string)
    graph = graphs[0]

    states = set()
    final_states = set()
    transitions = defaultdict(dict)
    alphabet = set()
    initial_state = None

    # Nodes
    for node in graph.get_nodes():
        name = node.get_name().strip('"')
        if name in ("node", "graph"):
            continue

        states.add(name)

        if node.get_shape() == "doublecircle":
            final_states.add(name)

    # Edges
    for edge in graph.get_edges():
        src = edge.get_source().strip('"')
        dst = edge.get_destination().strip('"')
        label = edge.get_label()

        if src == "__start0":
            initial_state = dst
            continue

        if label is None:
            continue

        for sym in label.strip('"').split(","):
            sym = sym.strip()
            alphabet.add(sym)
            transitions[src][sym] = dst

    if initial_state is None:
        raise ValueError("Startstaat niet gevonden (__start0 ontbreekt)")

    return states, alphabet, transitions, initial_state, final_states



def make_total_dfa(states, alphabet, transitions, initial_state, final_states):
    sink = "sink"
    states = set(states)
    states.add(sink)

    for state in states:
        if state not in transitions:
            transitions[state] = {}

        for sym in alphabet:
            if sym not in transitions[state]:
                transitions[state][sym] = sink

    transitions[sink] = {sym: sink for sym in alphabet}

    return DFA(
        states=states,
        input_symbols=alphabet,
        transitions=dict(transitions),
        initial_state=initial_state,
        final_states=final_states
    )


def dfa_to_dot(dfa, graph_name="Minimized_DFA"):
    graph = pydot.Dot(graph_name, graph_type="digraph", rankdir="LR")

    start_node = pydot.Node("__start0", shape="none", label="")
    graph.add_node(start_node)
    graph.add_edge(pydot.Edge("__start0", dfa.initial_state))

    for state in dfa.states:
        if state in dfa.final_states:
            node = pydot.Node(state, shape="doublecircle", style="filled", fillcolor="lightpink")
        elif state == "sink":
            node = pydot.Node(state, shape="box", fillcolor="lightgrey")
        else:
            node = pydot.Node(state, shape="circle")
        graph.add_node(node)

    edge_labels = defaultdict(list)
    for src, trans in dfa.transitions.items():
        for sym, dst in trans.items():
            edge_labels[(src, dst)].append(sym)

    for (src, dst), symbols in edge_labels.items():
        label = ",".join(sorted(symbols))
        graph.add_edge(pydot.Edge(src, dst, label=label))

    return graph


def minimize_dot_dfa(dot_string):
    states, alphabet, transitions, start, finals = parse_dot(dot_string)
    dfa = make_total_dfa(states, alphabet, transitions, start, finals)
    return dfa.minify()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Gebruik: python {sys.argv[0]} <file.dot>")
        sys.exit(1)

    dot_file_path = sys.argv[1]

    try:
        with open(dot_file_path, 'r') as f:
            dot_content = f.read()

        minified_dfa = minimize_dot_dfa(dot_content)

        print(f"\n--- Minimalisatie Resultaten: {dot_file_path} ---")
        print(f"Aantal states na minimalisatie: {len(minified_dfa.states)}")
        print(f"States: {minified_dfa.states}")

        out_path = dot_file_path.replace(".dot", "_minimized.dot")
        dfa_to_dot(minified_dfa).write_raw(out_path)

        print(f"Minimized DFA opgeslagen als: {out_path}")

    except FileNotFoundError:
        print(f"Fout: Bestand '{dot_file_path}' niet gevonden.")
    except Exception as e:
        print(f"Er is een fout opgetreden: {e}")
