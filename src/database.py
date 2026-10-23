import sqlite3
from pathlib import Path

import pandas as pd

from src.clean import (CANONICAL_DELIMITER, COMPONENT_SEPARATOR, COMPONENT_TRANSLATIONS, build_manufacturer_tables, translate_component)
from src.match import run_matching

DB_PATH = Path(__file__).resolve().parent.parent / "outputs" / "catalog.db"

SCHEMA = """
-- manufacturers = one group per brand; every raw legal-entity string kept as an alias
CREATE TABLE manufacturer (
    manufacturer_id     INTEGER PRIMARY KEY,
    manufacturer_group  TEXT NOT NULL UNIQUE
);

CREATE TABLE manufacturer_alias (
    manufacturer_alias_id  INTEGER PRIMARY KEY,
    raw_manufacturer       TEXT NOT NULL UNIQUE,
    manufacturer_id        INTEGER NOT NULL REFERENCES manufacturer(manufacturer_id),
    manufacturer_division  TEXT,
    legal_form             TEXT,
    legal_region           TEXT
);

-- components = canonical English vocabulary + localized variants seen in feeds
CREATE TABLE component (
    component_id  INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE
);

CREATE TABLE component_alias (
    alias         TEXT PRIMARY KEY,
    component_id  INTEGER NOT NULL REFERENCES component(component_id),
    language      TEXT
);

-- source data = one row per original catalog row --> raw text untouched
CREATE TABLE source_record (
    source_record_id            TEXT PRIMARY KEY,
    source_market               TEXT NOT NULL,
    source_row                  INTEGER NOT NULL,
    raw_model_name              TEXT NOT NULL,
    raw_core_components         TEXT,
    raw_manufacturer_of_record  TEXT,
    manufacturer_alias_id       INTEGER REFERENCES manufacturer_alias(manufacturer_alias_id),
    is_duplicate                INTEGER NOT NULL
);

-- components as listed on a record --> for bundles = describe the whole bundle
CREATE TABLE record_component (
    source_record_id  TEXT NOT NULL REFERENCES source_record(source_record_id),
    component_id      INTEGER NOT NULL REFERENCES component(component_id),
    PRIMARY KEY (source_record_id, component_id)
);

-- one row per product after bundle splitting + every cleaning step kept
CREATE TABLE source_product (
    source_product_id  TEXT PRIMARY KEY,
    source_record_id   TEXT NOT NULL REFERENCES source_record(source_record_id),
    bundle_position    INTEGER NOT NULL,
    bundle_size        INTEGER NOT NULL,
    product_piece      TEXT NOT NULL,     -- after bundle split
    base_name          TEXT NOT NULL,     -- after removing specs
    storage            TEXT,
    packaging          TEXT,
    revision           TEXT,
    model_name_clean   TEXT NOT NULL,     -- after removing brand / reseller suffix
    brand_suffix       TEXT,
    reseller_brand     TEXT,
    reseller_code      TEXT
);

-- global product identity everything links to
CREATE TABLE canonical_model (
    canonical_model_id  INTEGER PRIMARY KEY,
    canonical_name      TEXT NOT NULL,
    is_generic          INTEGER NOT NULL,
    manufacturer_id     INTEGER REFERENCES manufacturer(manufacturer_id),   -- set for generic products
    market_count        INTEGER NOT NULL,
    markets             TEXT NOT NULL
);

CREATE TABLE model_link (
    source_product_id   TEXT PRIMARY KEY REFERENCES source_product(source_product_id),
    canonical_model_id  INTEGER NOT NULL REFERENCES canonical_model(canonical_model_id),
    match_method        TEXT NOT NULL CHECK (match_method IN ('exact', 'normalized', 'llm', 'needs_review')),
    confidence          REAL NOT NULL,
    match_reason        TEXT
);

CREATE TABLE model_component (
    canonical_model_id  INTEGER NOT NULL REFERENCES canonical_model(canonical_model_id),
    component_id        INTEGER NOT NULL REFERENCES component(component_id),
    PRIMARY KEY (canonical_model_id, component_id)
);

CREATE INDEX idx_link_model ON model_link(canonical_model_id);
CREATE INDEX idx_product_record ON source_product(source_record_id);
CREATE INDEX idx_model_name ON canonical_model(canonical_name);
"""

LANGUAGE_BY_WORD = {word: lang for word, (_, lang) in COMPONENT_TRANSLATIONS.items()}

# turning pipeline output into one df per database table:
def build_tables(products: pd.DataFrame, canonical: pd.DataFrame, links: pd.DataFrame, vocabulary: dict[str, str]) -> dict[str, pd.DataFrame]:
    manufacturers, aliases = build_manufacturer_tables(products)
    aliases = aliases.reset_index(drop=True)
    aliases["manufacturer_alias_id"] = range(1, len(aliases) + 1)

    components = pd.DataFrame({"name": sorted(vocabulary.values())})
    components["component_id"] = range(1, len(components) + 1)
    component_id = dict(zip(components["name"], components["component_id"]))

    # source_record = one row per original row:
    records = products.drop_duplicates("source_record_id").merge(
        aliases[["raw_manufacturer", "manufacturer_alias_id"]],
        left_on="raw_manufacturer_of_record", right_on="raw_manufacturer", how="left")
    source_record = records[["source_record_id", "source_market", "source_row", "raw_model_name",
                             "raw_core_components", "raw_manufacturer_of_record",
                             "manufacturer_alias_id", "is_duplicate"]]

    # record_component + component_alias from normalized component lists:
    record_component, alias_rows = [], {}
    
    for rid, raw, canon in zip(records["source_record_id"], records["components_norm"], records["components"]):
        if isinstance(canon, str):
            for name in canon.split(CANONICAL_DELIMITER):
                record_component.append((rid, component_id[name]))

        if isinstance(raw, str):
            for piece in filter(None, COMPONENT_SEPARATOR.split(raw)):
                english = vocabulary.get(translate_component(piece).lower())
                foreign = [w for w in piece.split() if w in LANGUAGE_BY_WORD]

                if english and foreign:
                    alias_rows[piece] = (component_id[english], LANGUAGE_BY_WORD[foreign[0]])

    record_component = pd.DataFrame(sorted(set(record_component)), columns=["source_record_id", "component_id"])
    component_alias = pd.DataFrame([(a, c, l) for a, (c, l) in alias_rows.items()],
                                   columns=["alias", "component_id", "language"])

    source_product = products[["source_product_id", "source_record_id", "bundle_position", "bundle_size",
                               "product_piece", "base_name", "storage", "packaging", "revision",
                               "model_name_clean", "brand_suffix", "reseller_brand", "reseller_code"]]

    group_to_id = dict(zip(manufacturers["manufacturer_group"], manufacturers["manufacturer_id"]))
    canonical_model = canonical.assign(manufacturer_id=canonical["manufacturer_group"].map(group_to_id))[
        ["canonical_model_id", "canonical_name", "is_generic", "manufacturer_id", "market_count", "markets"]]

    # model_component = from non-bundle rows only since a bundle's components can't be assigned to one product
    # --> + the component that defines each generic product:
    single = products[(products["bundle_size"] == 1) & products["components"].notna()]
    pairs = {(m, component_id[c]) for m, comps in zip(single["canonical_model_id"], single["components"])
             for c in comps.split(CANONICAL_DELIMITER)}
    generic = products[products["is_generic"]]
    pairs |= {(m, component_id[c]) for m, c in zip(generic["canonical_model_id"], generic["generic_component"])}
    model_component = pd.DataFrame(sorted(pairs), columns=["canonical_model_id", "component_id"])

    return {
        "manufacturer": manufacturers,
        "manufacturer_alias": aliases[["manufacturer_alias_id", "raw_manufacturer", "manufacturer_id",
                                       "manufacturer_division", "legal_form", "legal_region"]],
        "component": components[["component_id", "name"]],
        "component_alias": component_alias,
        "source_record": source_record,
        "record_component": record_component,
        "source_product": source_product,
        "canonical_model": canonical_model,
        "model_link": links[["source_product_id", "canonical_model_id", "match_method",
                             "confidence", "match_reason"]],
        "model_component": model_component,
    }

# creating schema + inserting every table:
def write_database(tables: dict[str, pd.DataFrame], path: Path = DB_PATH) -> None:
    path.parent.mkdir(exist_ok=True)
    path.unlink(missing_ok=True)

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(SCHEMA)

        for name, df in tables.items(): # dict order = parents before children
            df.to_sql(name, conn, if_exists="append", index=False)
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()

        assert not problems, f"foreign key violations: {problems[:5]}"


EXAMPLE_QUERY = """
SELECT cm.canonical_name, sr.source_market, sr.raw_model_name, ml.match_method, ml.confidence
FROM canonical_model cm
JOIN model_link ml     ON ml.canonical_model_id = cm.canonical_model_id
JOIN source_product sp ON sp.source_product_id = ml.source_product_id
JOIN source_record sr  ON sr.source_record_id = sp.source_record_id
WHERE cm.canonical_name = ?
ORDER BY sr.source_market
LIMIT 12
"""


if __name__ == "__main__":
    from src.load import DATA_DIR
    from src.clean import load_vocabulary

    products, canonical, links, judged = run_matching()
    products = products.merge(canonical[["canonical_model_id"]], on="canonical_model_id")
    vocabulary = load_vocabulary(DATA_DIR / "component_list.json")
    tables = build_tables(products, canonical, links, vocabulary)
    write_database(tables)

    print(f"\nDatabase written to {DB_PATH.relative_to(DB_PATH.parent.parent)}")

    for name, df in tables.items():
        print(f"  {name:20} {len(df):>7,} rows")

    with sqlite3.connect(DB_PATH) as conn:
        print("\nEvery market's raw name for one canonical model:")
        print(pd.read_sql(EXAMPLE_QUERY, conn, params=["OpalPhone Mini Gen"]).to_string(index=False))
        print("\nComponent aliases:")
        print(pd.read_sql("SELECT a.alias, c.name, a.language FROM component_alias a "
                          "JOIN component c USING (component_id) LIMIT 5", conn).to_string(index=False))
        
    print("\nForeign keys valid, all checks pass")