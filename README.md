# Beyond Minimality: Compressing DFAs Through Substructure Extraction

> **Master's Thesis** — Milco Kats, Open Universiteit

This repository contains the implementation accompanying the master's thesis *"Beyond Minimality: Compressing DFAs Through Substructure Extraction"*. It provides several approaches for analysing and compressing general DFAs by detecting and factoring out recurring substructures. Running the compression algorithm produces a so-called Factored DFA (FDFA).

## Project structure

```plaintext
Compression Cyclic DFA/
│
├── input/
│   ├── miscellaneous/      # Small hand-crafted test automata
│   ├── real_world/         # Larger real-world DFAs (URL parsers, etc.)
│   └── test_automata/      # Systematic test cases (deel_1.dot - deel_11.dot)
│
├── src/
│   ├── approaches/
│   │   ├── shared/                               # Shared base classes and utilities
│   │   ├── equivalence_closure/                  # Variant 1: with equivalence closure
│   │   ├── no_equivalence_closure/               # Variant 2: without equivalence closure
│   │   └── no_equivalence_closure_nested_calls/  # Variant 3: two-pass nested factorization
│   ├── benchmark/
│   │   └── benchmark.py                          # Variant-agnostic benchmark suite
│   ├── language_preservation/
│   │   ├── run_validation.py                     # Validates language preservation across all variants
│   │   ├── targeted_language_preservation.py     # Targeted test generator
│   │   └── random_language_preservation.py       # Random test generator
│
├── benchmark_results.json          # Benchmark output (generated)
├── language_preservation_result.json # Language preservation output (generated)
└── README.md
```

## Approaches

All three variants share the same base analysis and factorization infrastructure in `src/approaches/shared/`. They differ in how matching candidates are selected:

### Variant overview
- **EquivalenceClosure** (`src/approaches/equivalence_closure/`): Uses a union-find structure to propagate equivalences between matched nodes across BFS iterations. Faster convergence for large automata.
- **NoEquivalenceClosure** (`src/approaches/no_equivalence_closure/`): Compares all candidate pairs directly without equivalence tracking. Tends to yield better net compression.
- **NestedCalls** (`src/approaches/no_equivalence_closure_nested_calls/`): Two-pass variant — first factorizes the original automaton, then searches for recurring patterns within the generated blueprint layer itself.

## Usage

Run the scripts directly from the repository root (there is no `launch.json` in the repo).

### Factorize a single DFA
```bash
python3 src/approaches/equivalence_closure/main.py input/miscellaneous/bigSmall.dot
python3 src/approaches/no_equivalence_closure/main.py input/miscellaneous/bigSmall.dot
python3 src/approaches/no_equivalence_closure_nested_calls/main.py input/miscellaneous/bigSmall.dot
```

Outputs are written to `output/` with suffixes `_EqClosure.dot`, `_NoEqClosure.dot`, and `_NESTED.dot`.

## Extra tools

### Language Preservation
The script `src/language_preservation/run_validation.py` verifies that the factorized automaton accepts the same language as the original.

Run all input subfolders:
```bash
python3 src/language_preservation/run_validation.py
```

Run specific subfolders:

```bash
python3 src/language_preservation/run_validation.py real_world test_automata miscellaneous
```

### Benchmark
The script `src/benchmark/benchmark.py` runs a variant-agnostic benchmark, testing all three variants on the same inputs and collecting metrics for compression ratio, runtime, and correctness. Configure the `TEST_MODE` variable at the bottom of the file to select the input set. Note: the current test lists inside `benchmark.py` use absolute paths — update them if your repo lives elsewhere.

---
Folders such as `output/` contain generated files and are not relevant for running the project.
