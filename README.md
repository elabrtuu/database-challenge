# Cross-Market Catalog Unification Task
completed by Ela Bartu

### Background:
This algorithm links consumer electronics products across four given market catalogs (EU, US, Spain, and Switzerland) through their model/trade names. It does this while keeping every original string traceable.

**Result:** 52,314 source rows with 80,936 individual products (after splitting bundles) are converted into **31,273 canonical models**, of which **1,303 appear in two or more markets and 179 in all four**. Moreover, all 27 examples from the case-study brief are reproduced correctly and every link records how it was made.

## How to run:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python -m pytest
python -m src.database
python -m src.evaluate
```

### Project structure:

```
src/
    load.py         // reads all markets; adds traceability IDs
    clean.py        // normalization; bundles; specs; components; brands; manufacturers
    match.py        // tiered matching + LLM judge = canonical models
    database.py     // relational SQLite model with enforced foreign keys
tests/
outputs/
```

## Approach:

Each step was designed to add columns and never overwrite, so any canonical model can be traced back to the exact row and file it came from.

1. Load: reading all four files, giving each row an ID, flagging duplicated instead of dropping them
2. Normalize text: unicode NFKC, replacing special dashes, collapsing whitespace
3. Split bundles: having one row per product with position + bundle size
4. Strip specs: removing storage + packaging + revision tags from the name, all kept as attribute columns
5. Components: split on six delimiters, translating localized words, validating against given `component_list.json`
6. Brands & generics: stripping trailing brand/reseller suffix, detecting generic "component + brand" products in the process
7. Manufacturers: parsing into brand group + division + legal form
8. Matching: exact -> normalized -> LLM-judged typo candidates
9. Database: 10 table SQLite model with foreign keys and constraints

## Relational data model:

```
manufacturer 1──* manufacturer_alias 1──* source_record 1──* source_product 1──1 model_link *──1 canonical_model
                                               │                                                     │
component 1──* component_alias                 └──* record_component *──1 component 1──* model_component
```

**What each table holds:**
- `source_record`: original rows, untouched raw text strings
- `source_product`: one product per row after bundle split; every intermediate cleaning result kept
- `canonical_model`: the global product identity
- `model_link`: product → canonical model, with `match_method`, `confidence`, `match_reason`
- `component` / `component_alias`: canonical vocabulary and localized variants with language
- `record_component`: components as listed on each record
- `model_component`: components per canonical model
- `manufacturer` / `manufacturer_alias`: brand groups and raw legal entities

## My process/steps taken:
1. Read through project files
2. Write out everything I retained + need to know
3. Think through main parts of algorithm that I need to hit (= got 3 main parts)
4. Identify complications based on given data —> things I need to keep in mind + assess
5. Think about how AI can come into this and make a better solution than code
6. Create step by step plan taking every detail into account —> keeping in mind main goals for code
7. Determine tests to be ran to test functionality at the end —> python tests
8. Setup venv + download dependencies, packages, libraries
9. Completing steps highlighted under "Approach"


