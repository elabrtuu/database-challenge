import re
import unicodedata

import pandas as pd

DASHES = "‐‑‒–—−" # = all types of possible dashes
DASH_PATTERN = re.compile(f"[{DASHES}]")

BUNDLE_SEPARATOR = re.compile(r"\s*(?:,\s*and\s+|\s+and\s+|/+|\+|,)\s*") # = all possible separators

# explicit stop-list of terms found in data --> extracted into ites own column instead of being trashed:
SPEC_PATTERNS = {
    "storage": re.compile(r"\b\d+\s?(?:GB|TB)\b", re.IGNORECASE),
    "packaging": re.compile(r"\b(?:Starter Kit|Refurbished|Bundle|Dual-SIM)\b", re.IGNORECASE),
    "revision": re.compile(r"\bRev[A-Z]\b")
}

COMPONENT_SEPARATOR = re.compile(r"\s*(?:\+|;|,|/|&|\band\b)\s*") # = all types of delimiters

#found a couple actual words that need translating, gonna implement w llm later:
COMPONENT_TRANSLATIONS = {
    "Kern": ("Core", "de"),
    "Netz": ("Grid", "de"),
    "Gewebe": ("Fabric", "de"),
    "Modul": ("Module", "de"),
    "Bouclier": ("Shield", "fr"),
    "Lien": ("Link", "fr"),
    "Matriz": ("Matrix", "es"),
    "Rayo": ("Beam", "es"),
}

CANONICAL_DELIMITER = " | "

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

# splitting model name into its individual products:
def split_bundle(name: str) -> list[str]:
    pieces = [p.strip() for p in BUNDLE_SEPARATOR.split(name)]
    # dropping empty pieces in return:
    return [p for p in pieces if p] 

# return one row per product keeping link to its source record + position:
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

# splitting one product piece into its base name + spec terms removed from it:
def strip_specs(piece: str) -> dict:
    result = {}
    base = piece

    for field, pattern in SPEC_PATTERNS.items():
        found = pattern.findall(base)
        result[field] = " ".join(found) or None
        base = pattern.sub(" ", base)

    result["base_name"] = re.sub(r"\s+", " ", base).strip()

    return result

# base_name + storage + packaging + revision columns:
def add_base_names(products: pd.DataFrame) -> pd.DataFrame:
    products = products.copy()
    extracted = pd.DataFrame(products["product_piece"].map(strip_specs).tolist(), index=products.index)

    return pd.concat([products, extracted], axis=1)

# TEMPORARY: trying manually by code and seeing if maybe LLM can do better later

# mapping lowercased component name to canonical spelling from component_list.json:
def load_vocabulary(path) -> dict[str, str]:
    import json

    with open(path) as f:
        return {c.lower(): c for c in json.load(f)}

# translating component name into eng:
def translate_component(name: str) -> str:
    return " ".join(COMPONENT_TRANSLATIONS.get(w, (w,))[0] for w in name.split())

# splitting + translating + validating component list against canonical vocab:
def normalize_components(text: str | None, vocabulary: dict[str, str]) -> dict:
    # check if missing values arrive as None/NaN:
    if not isinstance(text, str) or not text:
        return {"components": None, "unmatched_components": None, "component_count": 0}

    canonical, unmatched = [], []

    for raw_piece in COMPONENT_SEPARATOR.split(text):
        if not raw_piece:
            continue

        english = translate_component(raw_piece)
        match = vocabulary.get(english.lower())

        if match:
            canonical.append(match)
        else:
            unmatched.append(raw_piece) # = to be reviewed

    canonical = sorted(set(canonical))

    return {
        "components": CANONICAL_DELIMITER.join(canonical) or None,
        "unmatched_components": CANONICAL_DELIMITER.join(unmatched) or None,
        "component_count": len(canonical),
    }

# adding canonical components + unmatched pieces + count to each record:
def add_canonical_components(records: pd.DataFrame, vocabulary: dict[str, str]) -> pd.DataFrame:
    records = records.copy()
    results = records["components_norm"].map(lambda t: normalize_components(t, vocabulary))
    extracted = pd.DataFrame(results.tolist(), index=records.index)

    return pd.concat([records, extracted], axis=1)


if __name__ == "__main__":
    from src.load import load_all, DATA_DIR

    records = add_normalized_columns(load_all())
    vocabulary = load_vocabulary(DATA_DIR / "component_list.json")
    records = add_canonical_components(records, vocabulary)

    changed = records["raw_model_name"] != records["model_name_norm"]
    print(f"Model names changed by normalization {changed.sum():,} of {len(records):,}")

    examples = records.loc[changed & (records["raw_model_name"].str.len() < 60)]
    print(examples[["raw_model_name", "model_name_norm"]].head(5).to_string(index=False))

    products = explode_bundles(records)
    bundles = records["model_name_norm"].map(split_bundle).map(len) > 1

    print(f"{bundles.sum():,} bundle records converted into {len(products):,} product rows")
    print(products.groupby("source_market")["bundle_size"].agg(["max", "mean"]).round(2))

    products = add_base_names(products)
    stripped = products["base_name"] != products["product_piece"]

    print(f"\nSpecs removed from {stripped.sum():,} of {len(products):,} product rows")
    print(f"Distinct names: {products['product_piece'].nunique():,} pieces -> "
          f"{products['base_name'].nunique():,} base names")
 
    cols = ["product_piece", "base_name", "storage", "packaging", "revision"]
    print(products.loc[stripped, cols].sample(6, random_state=1).to_string(index=False))

    has_input = records["components_norm"].notna()
    flagged = records["unmatched_components"].notna()

    print(f"\nStep 5: components normalized for {has_input.sum():,} records "
          f"({flagged.sum():,} with unmatched pieces)")
    
    foreign_words = r"\b(?:" + "|".join(COMPONENT_TRANSLATIONS) + r")\b"
    translated = records["components_norm"].str.contains(foreign_words, na=False)

    print(records.loc[translated, ["components_norm", "components"]].head(6).to_string(index=False))
 
    canonical_values = set(vocabulary.values())
    all_components = records["components"].dropna().str.split(CANONICAL_DELIMITER, regex=False).explode()

    # additional checks for text normalization:
    assert len(records) == 52_314, "row count changed"
    assert records["model_name_norm"].notna().all(), "empty model name after normalization"
    assert not records["model_name_norm"].str.contains(f"[{DASHES}]").any(), "special dash left"

    # additional checks for bundling:
    assert products["source_record_id"].nunique() == len(records), "a source record was lost"
    assert products["product_piece"].notna().all() and (products["product_piece"] != "").all()
    assert not products["product_piece"].str.contains(r"/|\+|,|\band\b").any(), "separator left"
    assert products["source_product_id"].is_unique

    # additional checks for stripping specs:
    assert (products["base_name"] != "").all(), "a name became empty after stripping"
    leftover = products["base_name"].str.contains(r"\d+\s?(?:GB|TB)|Dual-SIM|Starter Kit|Refurbished|Bundle|Rev[A-Z]\b")
    assert not leftover.any(), "spec term left in base_name"

    # additional checks for normalizing components:
    assert all_components.isin(canonical_values).all(), "component not in vocabulary"
    assert (records.loc[has_input & ~flagged, "component_count"] > 0).all(), "components lost"

    print("All additional checks pass")


