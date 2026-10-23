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

# found a couple actual words that need translating:
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

RESELLER_PATTERN = re.compile(r"([A-Z][a-z]{3,})([A-Z]{2})") # = to handle reseller cases

LEGAL_FORM_REGION = {
    "Inc.": "US", "LLC": "US",
    "AG": "CH/DE", "GmbH": "CH/DE", "Sàrl": "CH",
    "S.L.": "ES", "S.A.": "ES", "S.L.U.": "ES", "S.A.U.":"ES", "SL": "ES",
    "BV": "NL"
}

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

# This following portion could also be implemented using LLM integration, but I chose
# to do it by code for cost + speed effectiveness:

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

# get brand word of a manufacturer:
def manufacturer_brand(manufacturer: str | float | None) -> str | None:
    if not isinstance(manufacturer, str) or not manufacturer:
        return None

    return manufacturer.split()[0]

# removing trailing brand suffix from a product name:
def strip_brand_suffix(name: str, brand: str | None, known_brands: set[str]) -> dict:
    result = {"model_name_clean": name, "brand_suffix": None, "reseller_brand": None, "reseller_code": None}
    words = name.split()

    # to avoid stripping name down too much:
    if len(words) < 2:
        return result

    last = words[-1]

    if brand and last.lower() == brand.lower():
        result.update(model_name_clean=" ".join(words[:-1]), brand_suffix=last)
        return result

    reseller = RESELLER_PATTERN.fullmatch(last)

    if reseller:
        owner = next((b for b in known_brands if b.startswith(reseller.group(1))), None)
        if owner: # = only strip if prefix is a known company
            result.update(model_name_clean=" ".join(words[:-1]), brand_suffix=last, reseller_brand=owner, reseller_code=reseller.group(2))

    return result

# return canonical component if the name is only comprised of component:
def detect_generic(name: str, vocabulary: dict[str, str]) -> str | None:
    if not isinstance(name, str):
        return None
    
    return vocabulary.get(name.lower())

# adding model_name_clean + brand suffix + reseller code + generic product columns:
def add_generic_flags(products: pd.DataFrame, vocabulary: dict[str, str]) -> pd.DataFrame:
    products = products.copy()
    products["manufacturer_brand"] = products["manufacturer_norm"].map(manufacturer_brand)

    known_brands = set(products["manufacturer_brand"].dropna())
    stripped = [strip_brand_suffix(n, b, known_brands) for n, b in zip(products["base_name"], products["manufacturer_brand"])]
    products = pd.concat([products, pd.DataFrame(stripped, index=products.index)], axis=1)
    products["generic_component"] = products["model_name_clean"].map(lambda n: detect_generic(n, vocabulary))
    products["is_generic"] = products["generic_component"].notna()

    return products

# splitting model names into brand + division + legal form:
def parse_manufacturer(manufacturer: str | float | None) -> dict:
    empty = {"manufacturer_group": None, "manufacturer_division": None, "legal_form": None, "legal_region": None}

    if not isinstance(manufacturer, str) or not manufacturer:
        return empty

    words = manufacturer.split()
    legal_form = words[-1] if words[-1] in LEGAL_FORM_REGION else None
    core = words[:-1] if legal_form else words

    return {
        "manufacturer_group": core[0], # brand = group of related entities
        "manufacturer_division": " ".join(core[1:]) or None,
        "legal_form": legal_form,
        "legal_region": LEGAL_FORM_REGION.get(legal_form),
    }

# building manufacturer table + alias table:
def build_manufacturer_tables(products:pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = products["raw_manufacturer_of_record"].dropna().unique()
    aliases = pd.DataFrame([{"raw_manufacturer": m, **parse_manufacturer(normalize_text(m))} for m in raw])
    groups = sorted(aliases["manufacturer_group"].dropna().unique())
    manufacturers = pd.DataFrame({"manufacturer_id": range(1, len(groups) + 1), "manufacturer_group": groups})
    aliases = aliases.merge(manufacturers, on="manufacturer_group", how="left")

    return manufacturers, aliases.sort_values("raw_manufacturer", ignore_index=True)



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
    print(f"Distinct names: {products['product_piece'].nunique():,} pieces into "
          f"{products['base_name'].nunique():,} base names")
 
    cols = ["product_piece", "base_name", "storage", "packaging", "revision"]
    print(products.loc[stripped, cols].sample(6, random_state=1).to_string(index=False))

    # ---- normalizing components:

    has_input = records["components_norm"].notna()
    flagged = records["unmatched_components"].notna()

    print(f"\nComponents normalized for {has_input.sum():,} records "
          f"({flagged.sum():,} with unmatched pieces)")
    
    foreign_words = r"\b(?:" + "|".join(COMPONENT_TRANSLATIONS) + r")\b"
    translated = records["components_norm"].str.contains(foreign_words, na=False)

    print(records.loc[translated, ["components_norm", "components"]].head(6).to_string(index=False))
 
    canonical_values = set(vocabulary.values())
    all_components = records["components"].dropna().str.split(CANONICAL_DELIMITER, regex=False).explode()

    # ---- handling generic names:

    products = add_generic_flags(products, vocabulary)

    print(f"\nBrand suffixes removed from {products['brand_suffix'].notna().sum():,} product rows "
          f"({products['reseller_code'].notna().sum():,} with reseller codes)")
    print(f"Generic products: {products['is_generic'].sum():,}")
    print(f"Distinct names: {products['base_name'].nunique():,} base names into "
          f"{products['model_name_clean'].nunique():,} clean names")
    
    cols = ["base_name", "model_name_clean", "brand_suffix", "reseller_code", "generic_component"]
    print(products.loc[products["brand_suffix"].notna(), cols].sample(6, random_state=3).to_string(index=False))

    # ---- normalizing manufacturers:

    manufacturers, manufacturer_aliases = build_manufacturer_tables(products)
    print(f"\n{len(manufacturer_aliases):,} raw manufacturer strings into "
          f"{len(manufacturers):,} manufacturer groups")
    print(manufacturer_aliases[manufacturer_aliases["manufacturer_group"] == "ElectroPulse"].to_string(index=False))
 

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

    # additional checks for generic name handling:
    assert (products["model_name_clean"] != "").all(), "a name became empty after brand stripping"
    last_word = products["model_name_clean"].str.split().str[-1]
    assert not last_word.str.fullmatch(RESELLER_PATTERN.pattern).any(), "reseller code left"
    generic = products[products["is_generic"] & products["components"].notna()]
    agrees = [g in c.split(CANONICAL_DELIMITER) for g, c in zip(generic["generic_component"], generic["components"])]
    print(f"Generic component agrees with the record's components: {sum(agrees):,} of {len(agrees):,}")

    # additional checks for manufacturer normalization:
    assert manufacturer_aliases["manufacturer_group"].notna().all(), "manufacturer without a group"
    assert manufacturer_aliases["legal_form"].notna().all(), "unknown legal form"
    assert manufacturer_aliases["raw_manufacturer"].is_unique

    print("All additional checks pass")


