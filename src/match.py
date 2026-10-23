import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from rapidfuzz.distance import Levenshtein

from src.clean import (CANONICAL_DELIMITER, add_base_names, add_canonical_components, add_generic_flags,
                        add_normalized_columns, explode_bundles, load_vocabulary)
from src.load import DATA_DIR, load_all

CACHE_PATH = Path(__file__).resolve().parent.parent / "outputs" / "llm_judgements.json"
RARE_WORD_MAX_COUNT = 3 # = consider a word seen this rarely across all names as a typo suspect
MAX_EDIT_DISTANCE = 2 # = max char edits between a rare word + its replacement
LLM_MIN_CONFIDENCE = 0.8 # = below this products are kept separate + flagged

# building a cleaned product table:
def build_products() -> tuple[pd.DataFrame, dict[str, str]]:
    vocabulary = load_vocabulary(DATA_DIR / "component_list.json")
    records = add_canonical_components(add_normalized_columns(load_all()), vocabulary)
    products = add_generic_flags(add_base_names(explode_bundles(records)), vocabulary)

    return products, vocabulary

# ---- 1. we look at keys:

# identifying whether generic products are identified by component + manuf or by their name:
def exact_key(row) -> str:
    if row.is_generic:
        return f"generic::{row.generic_component.lower()}::{row.manufacturer_brand.lower()}"
    
    return f"model::{row.model_name_clean.lower()}"

# same key with all spaces removes to avoid splitting product:
def compact_key(key: str) -> str:
    kind, _, rest = key.partition("::")

    return f"{kind}::{rest.replace(' ', '')}"

# ---- 2. we then find typo candidates by code to setup for LLM:

def find_typo_candidates(products: pd.DataFrame, vocabulary: dict[str, str]) -> list[dict]:
    product_names = set(products["model_name_clean"].str.lower())
    unique_rows = products[~products["is_duplicate"]] # = bc they would inflate the counts
    word_counts = Counter(w for n in unique_rows["model_name_clean"].str.lower() for w in n.split())
    rare = {w for w, c, in word_counts.items() if c <= RARE_WORD_MAX_COUNT}

    # possible targets = existing product names + canonical components:
    all_names = product_names | set(vocabulary)
    by_length: dict[int, list[str]] = {}

    for n in all_names:
        by_length.setdefault(len(n.split()), []).append(n)

    candidates = []

    for name in sorted(product_names):
        words = name.split()
        rare_positions = [i for i, w in enumerate(words) if w in rare]

        if not rare_positions:
            continue

        best = None

        # checking for same length --> only rare words may differ each by a few char edits
        for other in by_length.get(len(words), []):
            if other == name:
                continue

            other_words = other.split()
            diffs = [i for i in range(len(words)) if words[i] != other_words[i]]

            if not diffs or any(i not in rare_positions for i in diffs):
                continue

            if any(other_words[i] in rare for i in diffs):
                continue

            distance = sum(Levenshtein.distance(words[i], other_words[i]) for i in diffs)

            if all (Levenshtein.distance(words[i], other_words[i]) <= MAX_EDIT_DISTANCE for i in diffs):
                if best is None or distance < best["edit_distance"]:
                    best = {"name": name, "candidate": other, "edit_distance": distance, "type": "typo"}

        # checking for rare word as an extra tag --> dropping it gives us existing name
        if best is None:
            dropped = " ".join(w for i, w in enumerate(words) if i not in rare_positions)

            if dropped and dropped in all_names:
                best = {"name": name, "candidate": dropped, "edit_distance": None, "type": "extra_word"}

        if best:
            best["candidate_is_component"] = best["candidate"] in vocabulary
            candidates.append(best)

    return candidates

# providing context for the LLM (markets, manufacturers, components seen w name):
def candidate_evidence(products: pd.DataFrame, name: str, vocabulary: dict[str, str]) -> dict:
    rows = products[products["model_name_clean"].str.lower() == name]
    components = set()

    for c in rows["components"].dropna():
        components.update(c.split(CANONICAL_DELIMITER))

    return {
        "name": rows["model_name_clean"].iloc[0] if len(rows) else vocabulary.get(name, name),
        "is_canonical_component_name": name in vocabulary,
        "markets": sorted(rows["source_market"].unique()),
        "manufacturers": sorted(rows["manufacturer_norm"].dropna().unique())[:5],
        "components": sorted(components)[:10],
        "row_count": int(len(rows)),
    }

# ---- 3. LLM judge portion:

JUDGE_PROMPT = """
You are matching consumer electrics products across market catalogs.
Decide whether two catalog names refer to the same product.

Rules:
- Tier words (Mini, Max, Pro, Plus, Ultra, Air, Lite, Edge, Gen, SE) distinguish real variants.
  A different tier word means a different product; a misspelled one does not.
- Typos, misplaced spaces and stray tags can make the same product look different.
- Shared components and manufacturers are strong evidence; a different product family is strong evidence against.
 
Name A (suspected error):
{a}
 
Name B (existing product):
{b}
 
Respond with JSON only, no other text:
{{"same_product": true or false, "confidence": number between 0 and 1, "reason": "one short sentence"}}
"""

def load_cache() -> dict:
    return json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}

def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False))

def ask_llm(a: dict, b: dict, model: str | None = None) -> dict:
    import os

    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()

    model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI()
    prompt = JUDGE_PROMPT.format(a=json.dumps(a, indent=2), b=json.dumps(b, indent=2))
    response = client.chat.completions.create(
        model = model,
        messages = [{"role": "user", "content": prompt}],
        response_format = {"type": "json_object"},
    )

    text = response.choices[0].message.content.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    verdict = json.loads(text)

    return {"same_product": bool(verdict["same_product"]),
            "confidence": float(verdict["confidence"]),
            "reason": str(verdict["reason"]), "model": model}

def judge_candidates(products: pd.DataFrame, candidates: list[dict], vocabulary: dict[str, str]) -> list[dict]:
    cache = load_cache()

    for c in candidates:
        cache_key = f"{c['name']} || {c['candidate']}"

        if cache_key not in cache:
            try:
                cache[cache_key] = ask_llm(candidate_evidence(products, c["name"], vocabulary),
                                           candidate_evidence(products, c["candidate"], vocabulary))
            except Exception as error: # = no key, network error, or bad json
                print(f"  LLM unavailable for '{c['name']}': {error}")
                cache[cache_key] = None

        c["verdict"] = cache[cache_key]

    save_cache({k: v for k, v in cache.items() if v is not None})
    
    return candidates

# ---- 4. move on to building canonical models + links

def build_canonical_models(products: pd.DataFrame, judged: list[dict], vocabulary: dict[str, str]):
    products = products.copy()
    products["key"] = products.apply(exact_key, axis=1)
    products["match_method"] = "exact"
    products["confidence"] = 1.0
    products["match_reason"] = None
 
    # (2) merging keys that are identical once spaces are removed:
    products["compact"] = products["key"].map(compact_key)
    popular = products.groupby("compact")["key"].agg(lambda s: s.value_counts().index[0])
    target = products["compact"].map(popular)
    moved = target != products["key"]
    products.loc[moved, ["match_method", "confidence"]] = ["normalized", 0.95]
    products["key"] = target
 
    # (3) applying LLM verdicts:
    name_to_key = products.drop_duplicates("model_name_clean").set_index(products.drop_duplicates("model_name_clean")["model_name_clean"].str.lower())["key"]

    for c in judged:
        v = c.get("verdict")
        rows = products["model_name_clean"].str.lower() == c["name"]

        if v and v["same_product"] and v["confidence"] >= LLM_MIN_CONFIDENCE:
            if c["candidate_is_component"]: # = typo of a component -> generic product
                component = vocabulary[c["candidate"]]
                products.loc[rows, "key"] = ("generic::" + c["candidate"] + "::" + products.loc[rows, "manufacturer_brand"].str.lower())
                products.loc[rows, ["generic_component", "is_generic"]] = [component, True]
            else:
                products.loc[rows, "key"] = name_to_key[c["candidate"]]
            products.loc[rows, ["match_method", "confidence", "match_reason"]] = ["llm", v["confidence"], v["reason"]]
        else:
            reason = v["reason"] if v else "LLM not available; kept separate"
            confidence = v["confidence"] if v else 0.0
            products.loc[rows, ["match_method", "confidence", "match_reason"]] = ["needs_review", confidence, reason]
 
    # --> canonical models = one per key, named after most common spelling of its trusted members:
    trusted = products[products["match_method"].isin(["exact", "normalized"])]
    display = trusted.groupby("key")["model_name_clean"].agg(lambda s: s.value_counts().index[0])
    keys = sorted(products["key"].unique())

    canonical = pd.DataFrame({"key": keys})
    canonical["canonical_model_id"] = range(1, len(canonical) + 1)
    canonical["canonical_name"] = canonical["key"].map(display)

    first = products.drop_duplicates("key").set_index("key")

    canonical["canonical_name"] = canonical["canonical_name"].fillna(canonical["key"].map(first["model_name_clean"]))
    canonical["is_generic"] = canonical["key"].str.startswith("generic::")

    # generic products = named after their canonical component:
    generic_names = canonical.loc[canonical["is_generic"], "key"].str.split("::").str[1].map(vocabulary)
    canonical.loc[canonical["is_generic"], "canonical_name"] = generic_names
    canonical["manufacturer_group"] = canonical["key"].map(first["manufacturer_brand"]).where(canonical["is_generic"])

    stats = products.groupby("key").agg(market_count=("source_market", "nunique"),
                                        markets=("source_market", lambda s: ",".join(sorted(s.unique()))),
                                        source_product_count=("source_product_id", "count"))
    
    canonical = canonical.join(stats, on="key")
 
    products = products.merge(canonical[["key", "canonical_model_id"]], on="key", how="left")
    links = products[["source_product_id", "source_record_id", "canonical_model_id",
                      "match_method", "confidence", "match_reason"]]
    
    return products, canonical, links

def run_matching(use_llm: bool = True):
    products, vocabulary = build_products()
    products["key"] = products.apply(exact_key, axis=1)

    candidates = find_typo_candidates(products, vocabulary)
    judged = judge_candidates(products, candidates, vocabulary) if use_llm else candidates
    products, canonical, links = build_canonical_models(products, judged, vocabulary)

    return products, canonical, links, judged


if __name__ == "__main__":
    products, canonical, links, judged = run_matching()
 
    print(f"\n{len(links):,} product rows into {len(canonical):,} canonical models")
    print(links["match_method"].value_counts().to_string(), "\n")
    print(f"Canonical models found in 2+ markets: {(canonical['market_count'] >= 2).sum():,}  "
          f"(all 4 markets: {(canonical['market_count'] == 4).sum():,})")
    print(f"Generic canonical models: {canonical['is_generic'].sum():,}\n")
 
    print("Typo candidates and LLM verdicts:")

    for c in judged:
        v = c.get("verdict") or {}
        print(f"  {c['name']!r:28} -> {c['candidate']!r:28} [{c['type']}] "
              f"same={v.get('same_product')} conf={v.get('confidence')} | {v.get('reason')}")
 
    # additional checks:
    assert links["source_product_id"].is_unique, "a product was linked twice"
    assert links["canonical_model_id"].notna().all(), "a product has no canonical model"
    assert len(links) == len(products)

    print("\nAll additional checks pass")
