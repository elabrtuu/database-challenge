import re
import unicodedata

import pandas as pd

DASHES = "‐‑‒–—−" # encompasses all types of possible dashes
DASH_PATTERN = re.compile(f"[{DASHES}]")

# standardizing characters + whitespace while keeping case and accents:
def normalize_text(text: str | None) -> str | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None

    text = unicodedata.normalize("NFKC", str(text))
    text = DASH_PATTERN.sub("-", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None

# adding norm columns next to raw ones:
def add_normalized_columns(records: pd.DataFrame) -> pd.DataFrame:
    records = records.copy()
    records["model_name_norm"] = records["raw_model_name"].map(normalize_text)
    records["components_norm"] = records["raw_core_components"].map(normalize_text)
    records["manufacturer_norm"] = records["raw_manufacturer_of_record"].map(normalize_text)

    return records

BUNDLE_SEPARATOR = re.compile(r"\s*(?:,\s*and\s+|\s+and\s+|/+|\+|,)\s*") # = all possible separators

# splitting model name into its individual products:
def split_bundle(name: str) -> list[str]:
    pieces = [p.strip() for p in BUNDLE_SEPARATOR.split(name)]
    # dropping empty pieces in return:
    return [p for p in pieces if p] 

# we want to return one row per product keeping link to its source record + position:
def explode_bundles(records: pd.DataFrame) -> pd.DataFrame:
    products = records.copy()
    products["product_piece"] = products["model_name_norm"].map(split_bundle)
    products["bundle_size"] = products["product_piece"].map(len)
    products["is_bundle"] = products["bundle_size"] > 1

    products = products.explode("product_piece", ignore_index=True)
    products["bundle_position"] = products.groupby("source_record_id").cumcount() + 1
    products["source_product_id"] = (
        products["source_record_id"] + "-p" + products["bundle_position"].astype(str)
    )

    return products



if __name__ == "__main__":
    from src.load import load_all

    records = add_normalized_columns(load_all())

    changed = records["raw_model_name"] != records["model_name_norm"]
    print(f"Model names changed by normalization {changed.sum():,} of {len(records):,}")

    examples = records.loc[changed & (records["raw_model_name"].str.len() < 60)]
    print(examples[["raw_model_name", "model_name_norm"]].head(5).to_string(index=False))

    # additional checks for text normalization:
    assert len(records) == 52_314, "row count changed"
    assert records["model_name_norm"].notna().all(), "empty model name after normalization"
    assert not records["model_name_norm"].str.contains(f"[{DASHES}]").any(), "special dash left"

    products = explode_bundles(records)
    bundles = records["model_name_norm"].map(split_bundle).map(len) > 1

    print(f"{bundles.sum():,} bundle records converted into {len(products):,} product rows")
    print(products.groupby("source_market")["bundle_size"].agg(["max", "mean"]).round(2))

    # additional checks for bundling:
    assert products["source_record_id"].nunique() == len(records), "a source record was lost"
    assert products["product_piece"].notna().all() and (products["product_piece"] != "").all()
    assert not products["product_piece"].str.contains(r"/|\+|,|\band\b").any(), "separator left"
    assert products["source_product_id"].is_unique

    print("All additional checks pass")


