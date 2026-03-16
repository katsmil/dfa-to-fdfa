# Compression general DFA

Dit project bevat verschillende benaderingen voor het analyseren en comprimeren van algemene DFA’s. Hieronder vind je een overzicht van de relevante folderstructuur en uitleg over het gebruik van de verschillende approaches. Het draaien van het compressie algoritme geeft als resultaat een zogeheten Factored DFA.

## Projectstructuur

```plaintext
Compression Cyclic DFA/
│
├── input/
│   └── ...         # Voorbeeld- en testbestanden
│
├── src/
│   ├── approaches/
│   │   ├── equivalence_closure/
│   │   │   └── ... # Benaderingen met Equivalence Closure
│   │   └── no_equivalence_closure/
│   │       └── ... # Benaderingen zonder Equivalence Closure
│   └── shared/
│       └── ...     # Gedeelde code en utilities
│   ├── benchmark/
│   │   └── benchmark.py   # benchmark
│   ├── language_preservation/
│   │   └── language_preservation.py   # Test op taalbehoud
│
└── README.md       # Projectdocumentatie
```

## Approaches

  Te vinden in: `src/approaches/equivalence_closure/`  
  Hier worden algoritmes gebruikt die de equivalentie-closure toepassen bij het analyseren van DFA’s.

  Te vinden in: `src/approaches/no_equivalence_closure/`  
  Hier worden algoritmes gebruikt die geen equivalentie-closure toepassen.

### Variant toelichting
- **EquivalenceClosure**: De snelle variant. Deze approach is geoptimaliseerd voor snelheid en levert snelle resultaten.
- **NoEquivalenceClosure**: Deze variant geeft de beste netto compressie winst, maar is minder snel dan EquivalenceClosure.

## Gebruik

De verschillende onderdelen van het project zijn te starten via de configuraties in `launch.json`. 

1. Open `launch.json` in VS Code.
2. Kies een configuratie die overeenkomt met de gewenste approach (met of zonder Equivalence Closure).
3. Start de configuratie om het bijbehorende script uit te voeren.

Hiermee kun je eenvoudig de verschillende analysemethoden testen en vergelijken.

## Extra tools

### Language Preservation
Het script `src/language_preservation/language_preservation.py` test of de gefactoriseerde automaat dezelfde taal accepteert als het origineel. Dit is essentieel voor correctheidsbewijs en variant-onafhankelijk. Je kunt dit script draaien via de configuratie "🧪 Language Preservation Tester" in `launch.json`. Hiermee kun je controleren of de factorisatie geen fouten introduceert.

### Benchmark
Het script `src/benchmark/benchmark.py` voert een variant-agnostische benchmark uit. Hiermee worden beide varianten (EquivalenceClosure en NoEquivalenceClosure) getest op dezelfde inputs en worden metrics verzameld zoals compressie, snelheid en correctheid. Start dit script via de configuratie "📊 Benchmark (beide varianten)" in `launch.json`.

---
Folders zoals `output/`, `output_fases_combined/`, etc. bevatten gegenereerde bestanden en zijn niet relevant voor het gebruik van het project.
