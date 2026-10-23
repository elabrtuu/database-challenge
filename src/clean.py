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


if __name__ == "__main__":
    from src.load import load_all

    records = add_normalized_columns(load_all())

    changed = records["raw_model_name"] != records["model_name_norm"]
    print(f"Model names changed by normalization {changed.sum():,} of {len(records):,}")

    examples = records.loc[changed & (records["raw_model_name"].str.len() < 60)]
    print(examples[["raw_model_name", "model_name_norm"]].head(5).to_string(index=False))

    # additional checks:
    assert len(records) == 52_314, "row count changed"
    assert records["model_name_norm"].notna().all(), "empty model name after normalization"
    assert not records["model_name_norm"].str.contains(f"[{DASHES}]").any(), "special dash left"

    print("All additional checks pass")


