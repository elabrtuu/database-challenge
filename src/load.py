import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# listing each source file, market code + CSV separator:
SOURCES = {
    "EU": ("final_market_a_eu_catalog.csv", ";"),
    "US": ("final_market_b_us_catalog.csv", ","),
    "ES": ("final_market_c_es_catalog.csv", ","),
    "CH": ("final_market_d_ch_catalog.csv", ","),
}

COLUMNS = ["model_name", "core_components", "manufacturer_of_record"]

# loading market file as raw text:
def load_market(market: str, filename: str, sep: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / filename, sep=sep, dtype=str, keep_default_na=False)

    # if no core components, add as empty so all markets can share one schema:
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[COLUMNS].rename(columns={c: f"raw_{c}" for c in COLUMNS})
    df["source_market"] = market
    df["source_row"] = range(1, len(df) + 1) # = row num in original file
    df["source_record_id"] = market + "-" + df["source_row"].astype(str)

    return df

# loading every market into one table:
def load_all() -> pd.DataFrame:
    frames = [load_market(m, f, sep) for m, (f, sep) in SOURCES.items()]
    records = pd.concat(frames, ignore_index=True)

    # flagging for traceability purposes:
    raw_cols = [f"raw_{c}" for c in COLUMNS]
    records["is_duplicate"] = records.duplicated(subset=["source_market"] + raw_cols, keep="first")

    return records[["source_record_id", "source_market", "source_row", *raw_cols, "is_duplicate"]]

# loading canonical english component vocab:
def load_components() -> list[str]:
    return json.loads((DATA_DIR / "component_list.json").read_text())


if __name__ == "__main__":
    records = load_all()
    components = load_components()

    print(f"Loaded {len(records):,} records and {len(components):,} canonical components\n")

    summary = records.groupby("source_market").agg(
        rows = ("source_record_id", "count"),
        duplicates = ("is_duplicate", "sum"),
        missing_components = ("raw_core_components", lambda s: s.isna().sum()),
    )

    print(summary, "\n")
    print(records.sample(5, random_state=0).to_string(index=False))
