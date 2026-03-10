# DFA Compressie Benaderingen

Dit project vergelijkt twee benaderingen voor het comprimeren van algemene automaten door herhaalde substructuren te detecteren en te factoriseren.

---

## 📁 Mappenstructuur

```
code/
├── approaches/                 # Experimentele implementaties
│   ├── equivalence_closure/
│   └── no_equivalence_closure/
├── shared/                     # Gedeelde utilities
├── tools/                      # Standalone scripts
├── benchmark/                  # Variant-agnostisch test framework
├── language_preservation/      # Test op taalbehoud
│   └── language_preservation.py
├── archive/                    # Oud experimenteel werk
└── APPROACHES.md               # Dit bestand
```

---

## 🔬 Benadering 1: Equivalence Closure

**Locatie**: `approaches/equivalence_closure/`

### Wat doet het?
Zoekt naar **grote bisimilaire substructuren** in lineaire tijd door equivalentieklassen (equivalence closure) te berekenen. Dit maakt het efficiënt om grote overlappende patronen te vinden.

### Entry Point
```bash
python approaches/equivalence_closure/main.py <input.dot>
```

### Subvarianten
- **Optimized** (`optimized/`): Geoptimaliseerde implementatie
- **(TODO) Exclusive Frontiers** (`(TODO)exclusive_frontiers/`): Experimenteel (niet actief)

### Karakteristieken
- ✅ Lineaire tijd complexiteit
- ✅ Grote structuren bij voorkeur
- ✅ Efficciënt voor massive automaten
- ⚠️ Kan minder kleine optimalisaties vinden

---

## 🔬 Benadering 2: No Equivalence Closure

**Locatie**: `approaches/no_equivalence_closure/`

### Wat doet het?
Onderzoekt herhaalde structuren **zonder equivalentieklassen** te berekenen. Biedt meer granulaire controle over welke substructuren te accepteren/weigeren.

### Entry Points
```bash
# Exclusive Frontiers (optimized versie)
python approaches/no_equivalence_closure/exclusive_frontiers/optimized/main.py <input.dot>

# Exclusive Frontiers (basis)
python approaches/no_equivalence_closure/exclusive_frontiers/main.py <input.dot>

# Hybrid Frontiers (experimenteel)
python approaches/no_equivalence_closure/hybrid_frontiers/main.py <input.dot>
```

### Subvarianten
- **Exclusive Frontiers Optimized** (`exclusive_frontiers/optimized/`): Geoptimaliseerde versie - AANBEVOLEN
- **Exclusive Frontiers** (`exclusive_frontiers/`): Basisimplementatie
- **Hybrid Frontiers** (`hybrid_frontiers/`): Experimenteel - testing

### Karakteristieken
- ✅ Fijnere controle over structuren
- ✅ Kan kleine en grote substructuren balanceren
- ⚠️ Potentieel langzamer dan Equivalence Closure
- ⚠️ Afhankelijk van heuristieken en prioriteitslijsten

---

## 📊 Benchmarking


Beide benaderingen kunnen objectief met elkaar vergeleken worden:

```bash
python benchmark/benchmark.py
```

Dit framework:
- Draait beide varianten op dezelfde testgegevens
- Verzamelt timing metrics (analyse, factorisatie)
- Verzamelt compressie-effectiviteit (nodes/edges voor/na)
- Valideert correctheid (bisimilariteit behouden)

**Output**: `benchmark_results.json`

---

## 🧪 Language Preservation

**Locatie**: `language_preservation/language_preservation.py`

Dit script test of de gefactoriseerde automaat dezelfde taal accepteert als het origineel. Dit is essentieel voor correctheidsbewijs en variant-onafhankelijk.

### Gebruik
```bash
python language_preservation/language_preservation.py <orig.dot> <factored.dot> <string>
```
Je kunt hiermee controleren of de factorisatie geen fouten introduceert. Het script accepteert een origineel .dot-bestand, een gefactoreerd .dot-bestand en een input string.

---

## 🛠️ Shared Utilities

**Locatie**: `shared/`

Gedeelde code die door beide benaderingen gebruikt wordt:
- `graph_utils.py`: Graph-manipulatie helperfuncties
- `dominator_analysis.py`: Dominator tree analyse
- `utils/`: Algemene nutsfuncties

Deze modules worden niet duplicated - beiden importeren ze van dezelfde plaats.

---

## 📦 Archive

**Locatie**: `archive/`

Bevat oud experimenteel werk:
- `earlier_iterations/`: Eerste implementatievarianten
- `bisimilar_wip/`: WIP bisimilarity detection
- `factorize_wip/`: WIP factorisatie engine
- `analysis_metrics/`: Oude metrics verzameling

Dit is **read-only** - verwijs hiernaar alleen als je de geschiedenis nodig hebt.

---

## 🚀 Quick Start

### Wil je beide benaderingen testen?
```bash
cd code/
python benchmark/benchmark.py
```

### Wil je alleen Equivalence Closure testen?
```bash
cd code/
python approaches/equivalence_closure/main.py input/your_graph.dot
```

### Wil je alleen No Equivalence Closure testen?
```bash
cd code/
python approaches/no_equivalence_closure/exclusive_frontiers/optimized/main.py input/your_graph.dot
```

---

## 📝 Welke variant kiezen?

| Criterium         | Equivalence Closure         | No Equivalence Closure         |
|-------------------|----------------------------|-------------------------------|
| Snelheid          | Lineair, snel              | Langzamer                     |
| Compressie        | Grote structuren           | Fijn-granulair, meer winst    |
| Complexiteit      | Simpel                     | Meer heuristieken             |
| Kleine automaten  | Minder optimaal            | Zeer geschikt                 |
| Grote automaten   | Zeer geschikt              | Minder optimaal               |

---

## 🔍 Voor Ontwikkelaars

### Import Structuur
Alle imports zijn **relatief** binnen hun respectievelijke benadering:
```python
# In equivalence_closure/:
from analyze import run_analysis
from factorize import apply_factorization

# In no_equivalence_closure/:
from analyze import run_analysis
from factorize import apply_factorization
```

Geen absolute paden - dit maakt subvarianten eenvoudig om te testen.

### Gedeelde Code
Als je functies van `shared/` nodig hebt, moet je ze toevoegen aan:
```python
from shared.graph_utils import *
from shared.dominator_analysis import *
```

### Nieuwe Variant Toevoegen?
1. Maak folder onder `approaches/your_new_variant/`
2. Maak `main.py`, `analyze.py`, `factorize.py`
3. Volg hetzelfde interface als bestaande varianten
4. Update `benchmark/benchmark.py` om de variant te testen
5. Dokumenteer in dit bestand

---
