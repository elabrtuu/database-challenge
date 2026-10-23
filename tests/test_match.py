import pandas as pd

from src.match import compact_key, find_typo_candidates

VOCAB = {"vega module": "Vega Module", "slate module link": "Slate Module Link"}

def make_products(names):
    return pd.DataFrame({"model_name_clean": names, "is_duplicate": False})


def test_misplaced_space_gives_same_compact_key():
    assert compact_key("model::heli opad gen edge") == compact_key("model::heliopad gen edge")


def test_typo_found_and_tier_word_variant_ignored():
    names = ["OpalPhone Mini Gen"] * 5 + ["OpalPhone Max Gen"] * 5 + ["OtalPhone Minz Gen"]
    candidates = find_typo_candidates(make_products(names), VOCAB)
    assert len(candidates) == 1 
    assert candidates[0]["name"] == "otalphone minz gen"
    assert candidates[0]["candidate"] == "opalphone mini gen"


def test_typo_of_a_component():
    names = ["Vega Mxdule"] + ["Vega Beam"] * 5 + ["Vega Core"] * 5
    candidates = find_typo_candidates(make_products(names), VOCAB)
    assert candidates[0]["candidate"] == "vega module"
    assert candidates[0]["candidate_is_component"]


def test_extra_tag_is_dropped():
    names = ["Slate Module Link FP"] + ["Slate Beam"] * 5 + ["Aero Module Link"] * 5
    candidates = find_typo_candidates(make_products(names), VOCAB)
    assert candidates[0]["candidate"] == "slate module link"
    assert candidates[0]["type"] == "extra_word"


def test_common_names_produce_no_candidates():
    names = ["TerraBeam Pro Max"] * 5 + ["TealBeam Pro Max"] * 5 # = similar but both common
    assert find_typo_candidates(make_products(names), VOCAB) == []