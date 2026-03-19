"""
Validatie: factoreer elk testbestand en controleer taalpreservatie.
Draait volledig in-process (geen subprocessen) zodat er geen timeout-issues zijn.

Gebruik:
  python3 src/language_preservation/run_validation_nested_calls.py                  → test alle subfolders van input/
  python3 src/language_preservation/run_validation_nested_calls.py test_automata    → alleen die subfolder(s)
  python3 src/language_preservation/run_validation_nested_calls.py miscellaneous real_world
"""

import sys
import io
from pathlib import Path

# ---------------------------------------------------------------------------
# Paden instellen zodat alle imports werken
# ---------------------------------------------------------------------------
SRC        = Path(__file__).parent.parent          # src/
INPUT_ROOT = SRC.parent / "input"
OUTPUT_DIR = SRC.parent / "output"
ANALYZE_DIR = SRC / "approaches/no_equivalence_closure"

for p in [str(SRC), str(ANALYZE_DIR), str(SRC / "language_preservation")]:
    if p not in sys.path:
        sys.path.insert(0, p)

import networkx as nx
from analyze import run_analysis
from approaches.shared.factorize import apply_factorization, save_dot
from approaches.shared.shared_types import MatchLocation, CanonicalSubstructure
from targeted_language_preservation import TargetedLanguagePreservationTester

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers (overgenomen uit main.py)
# ---------------------------------------------------------------------------

def _recompute_frontiers(results, G_full):
    patched = []
    for sub in results:
        patched_locs = []
        for loc in sub.locations:
            nodes_set = set(loc.all_nodes)
            internals, frontiers = [], []
            for n in loc.all_nodes:
                has_external = any(
                    t not in nodes_set
                    for _, t, _ in G_full.out_edges(n, data=True)
                )
                (frontiers if has_external else internals).append(n)
            patched_locs.append(MatchLocation(
                start_node=loc.start_node,
                all_nodes=loc.all_nodes,
                internals=tuple(internals),
                frontiers=tuple(frontiers),
            ))
        patched.append(CanonicalSubstructure(
            canonical_nodes=sub.canonical_nodes,
            overlap_size=sub.overlap_size,
            locations=tuple(patched_locs),
            blueprint_edges=sub.blueprint_edges,
        ))
    return patched


def factorize(dot_file: Path) -> nx.MultiDiGraph:
    G_orig = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(str(dot_file)))
    results = run_analysis(G_orig)
    G_factorized = apply_factorization(G_orig, results, strict_filter=False)

    sub_nodes = [n for n in G_factorized.nodes() if str(n).startswith('SUB_')]
    if sub_nodes:
        G_sub = nx.MultiDiGraph(G_factorized.subgraph(sub_nodes))
        results2 = run_analysis(G_sub)
        if results2:
            results2 = _recompute_frontiers(results2, G_factorized)
            G_factorized = apply_factorization(G_factorized, results2, strict_filter=False)

    return G_factorized


# ---------------------------------------------------------------------------
# Welke subfolders testen?
# ---------------------------------------------------------------------------

if len(sys.argv) > 1:
    subfolders = [INPUT_ROOT / name for name in sys.argv[1:]]
else:
    subfolders = sorted(
        p for p in INPUT_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith('.')
    )


def test_folder(folder: Path) -> list:
    dot_files = sorted(folder.glob("*.dot"))
    if not dot_files:
        return []

    results = []
    for dot_file in dot_files:
        name = dot_file.stem
        output_dot = OUTPUT_DIR / f"{name}_NESTED.dot"
        # Stap 1: factorizeer
        try:
            G_orig = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(str(dot_file)))
            G_factorized = factorize(dot_file)
            save_dot(G_factorized, str(output_dot))
        except Exception as e:
            print(f"  [{folder.name}] {name} ... FOUT (factorizatie)")
            results.append((name, "FOUT (factorizatie mislukt)", str(e)))
            continue

        # Stap 2: taalpreservatie-test
        try:
            # Herlaad gefactoriseerde graaf vanuit DOT zodat attributen genormaliseerd zijn
            G_fact_reloaded = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(str(output_dot)))
            tester = TargetedLanguagePreservationTester(G_orig, G_fact_reloaded)
            # Suppress de print van de tester
            _old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            all_match, all_cases = tester.run()
            sys.stdout = _old_stdout
        except Exception as e:
            sys.stdout = _old_stdout if '_old_stdout' in dir() else sys.stdout
            print(f"  [{folder.name}] {name} ... FOUT (test)")
            results.append((name, "FOUT (test mislukt)", str(e)))
            continue

        n_tests = len(all_cases)
        mismatches = [tc for tc in all_cases if tc.is_mismatch]

        if all_match:
            results.append((name, f"✅ PASSED ({n_tests} tests)", ""))
        else:
            print(f"  [{folder.name}] {name} ... ❌ FAILED ({len(mismatches)} mismatches)")
            detail = "\n".join(tc.summary(show_trace=True) for tc in mismatches[:3])
            results.append((name, f"❌ FAILED ({len(mismatches)} mismatches)", detail))

    return results


# Verwerk alle subfolders
all_results = []  # (folder_name, name, status, detail)
for folder in subfolders:
    if not folder.is_dir():
        print(f"⚠️  Map niet gevonden: {folder}")
        continue
    folder_results = test_folder(folder)
    if not folder_results:
        continue
    for entry in folder_results:
        all_results.append((folder.name,) + entry)

# Samenvatting per sectie
print()
current_folder = None
for folder_name, name, status, detail in all_results:
    if folder_name != current_folder:
        if current_folder is not None:
            print()
        print("=" * 60)
        print(f"  {folder_name}")
        print("=" * 60)
        current_folder = folder_name
    print(f"  {name:<35}  {status}")
    if detail and "FAILED" in status:
        # Toon eerste mismatch-blok
        lines = detail.splitlines()
        for i, line in enumerate(lines):
            if "MISMATCH" in line:
                print("    " + "\n    ".join(lines[i:i+10]))
                break

total  = len(all_results)
passed = sum(1 for *_, s, __ in all_results if "PASSED" in s)
failed = total - passed
print()
print("=" * 60)
print(f"  TOTAAL: {total}  |  ✅ {passed}  |  ❌ {failed}")
print("=" * 60)
