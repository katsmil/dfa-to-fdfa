"""
Validation: factorize each test file via all three variants and check language preservation.
Runs entirely in-process (no subprocesses) to avoid timeout issues.

Usage:
  python3 src/language_preservation/run_validation.py                  → test all subfolders of input/
  python3 src/language_preservation/run_validation.py test_automata    → only that subfolder(s)
  python3 src/language_preservation/run_validation.py miscellaneous real_world → multiple subfolders
"""

import sys
import io
from pathlib import Path

# ---------------------------------------------------------------------------
# Set up paths so all imports work
# ---------------------------------------------------------------------------
SRC        = Path(__file__).parent.parent   # src/
INPUT_ROOT = SRC.parent / "input"
OUTPUT_DIR = SRC.parent / "output"

for p in [str(SRC), str(SRC / "language_preservation")]:
    if p not in sys.path:
        sys.path.insert(0, p)

import networkx as nx
from approaches.no_equivalence_closure.main import factorize as factorize_noeq
from approaches.equivalence_closure.main import factorize as factorize_eq
from approaches.no_equivalence_closure_nested_calls.main import factorize as factorize_nested
from approaches.shared.factorize import save_dot
from targeted_language_preservation import TargetedLanguagePreservationTester

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VARIANTS = [
    ("NoEqClosure", factorize_noeq,    "_NoEqClosure.dot"),
    ("EqClosure",   factorize_eq,      "_EqClosure.dot"),
    ("Nested",      factorize_nested,  "_NESTED.dot"),
]

# ---------------------------------------------------------------------------
# What subfolders to test? By default, all. Or specify one or more as command-line arguments.
# ---------------------------------------------------------------------------

if len(sys.argv) > 1:
    raw = sys.argv[1:]
    if len(raw) == 1 and ' ' in raw[0]:
        raw = raw[0].split()
    subfolders = [INPUT_ROOT / name for name in raw]
else:
    subfolders = sorted(
        p for p in INPUT_ROOT.iterdir()
        if p.is_dir() and not p.name.startswith('.')
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_variant(G_orig: nx.MultiDiGraph, output_dot: Path, factorize_fn) -> tuple:
    """Factorize and test one variant. Returns (status, detail)."""
    try:
        G_factorized = factorize_fn(G_orig)
        save_dot(G_factorized, str(output_dot))
    except Exception as e:
        return f"ERROR (fact.)", str(e)

    _old_stdout = sys.stdout
    try:
        G_fact_reloaded = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(str(output_dot)))
        tester = TargetedLanguagePreservationTester(G_orig, G_fact_reloaded)
        sys.stdout = io.StringIO()
        all_match, all_cases = tester.run()
        sys.stdout = _old_stdout
    except Exception as e:
        sys.stdout = _old_stdout
        return f"ERROR (test)", str(e)

    mismatches = [tc for tc in all_cases if tc.is_mismatch]
    if all_match:
        return f"✅ ({len(all_cases)})", ""
    else:
        detail = "\n".join(tc.summary(show_trace=True) for tc in mismatches[:3])
        return f"❌ ({len(mismatches)})", detail


def test_folder(folder: Path) -> list:
    dot_files = sorted(folder.glob("*.dot"))
    if not dot_files:
        return []

    results = []
    for dot_file in dot_files:
        name = dot_file.stem
        try:
            G_orig = nx.MultiDiGraph(nx.drawing.nx_pydot.read_dot(str(dot_file)))
        except Exception as e:
            results.append((name, "ERROR (read)", "ERROR (read)", "ERROR (read)", str(e), "", ""))
            continue

        statuses = []
        details = []
        for _, fn, suffix in VARIANTS:
            output_dot = OUTPUT_DIR / f"{name}{suffix}"
            status, detail = _run_variant(G_orig, output_dot, fn)
            statuses.append(status)
            details.append(detail)

        results.append((name, *statuses, *details))

    return results


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

all_results = []
for folder in subfolders:
    if not folder.is_dir():
        print(f"⚠️  Directory not found: {folder}")
        continue
    folder_results = test_folder(folder)
    for entry in folder_results:
        all_results.append((folder.name,) + entry)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
COL = 16
HDR = f"  {'file':<35}  {'NoEqClosure':>{COL}}  {'EqClosure':>{COL}}  {'Nested':>{COL}}"
SEP = "─" * (35 + 3 * (COL + 2) + 4)

print()
current_folder = None
for row in all_results:
    folder_name, name = row[0], row[1]
    noeq, eq, nested = row[2], row[3], row[4]
    noeq_det, eq_det, nested_det = row[5], row[6], row[7]

    if folder_name != current_folder:
        if current_folder is not None:
            print()
        print("=" * len(SEP))
        print(f"  {folder_name}")
        print("=" * len(SEP))
        print(HDR)
        print(SEP)
        current_folder = folder_name

    print(f"  {name:<35}  {noeq:>{COL}}  {eq:>{COL}}  {nested:>{COL}}")

    for label, detail in [("NoEqClosure", noeq_det), ("EqClosure", eq_det), ("Nested", nested_det)]:
        if detail and ("FAILED" in detail or "FOUT" in detail or "MISMATCH" in detail):
            lines = detail.splitlines()
            for i, line in enumerate(lines):
                if "MISMATCH" in line or "FOUT" in line:
                    print(f"    [{label}] " + "\n    ".join(lines[i:i+10]))
                    break

total  = len(all_results)
passed = sum(1 for r in all_results if all("✅" in r[i] for i in [2, 3, 4]))
print()
print("=" * len(SEP))
print(f"  TOTAL: {total} files  |  ✅ all 3 OK: {passed}  |  ❌ at least 1 error: {total - passed}")
print("=" * len(SEP))

