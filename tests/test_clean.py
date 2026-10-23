from src.clean import (normalize_text, split_bundle, strip_specs, normalize_components, load_vocabulary,
strip_brand_suffix, detect_generic)

from src.load import DATA_DIR

VOCAB = load_vocabulary(DATA_DIR / "component_list.json")

# found one interesting hyphen, so have to make sure that that one specifically works
def test_special_hyphen():
    assert normalize_text("AstraCam 512GB Dual‑SIM") == "AstraCam 512GB Dual-SIM"

def test_whitespace():
    assert normalize_text("  SenseBook   Plus ") == "SenseBook Plus"
    assert normalize_text("SenseBook\tPlus") == "SenseBook Plus"

def test_keeps_case_and_accents():
    assert normalize_text("Nightfall Electronics Sàrl") == "Nightfall Electronics Sàrl"

def test_empty_values():
    assert normalize_text(None) is None
    assert normalize_text("") is None
    assert normalize_text("   ") is None

# bundling tests added (retrieved direct examples from README):
def test_not_a_bundle():
    assert split_bundle("AzureRouter SE Ultra 64GB Starter Kit") == ["AzureRouter SE Ultra 64GB Starter Kit"]
 
def test_readme_bundles():
    assert split_bundle("SolPhone Mini Ultra and CoreBook Pro Max") == ["SolPhone Mini Ultra", "CoreBook Pro Max"]
    assert split_bundle("RubyHub / VectorWatch Max Ultra 1TB Bundle") == ["RubyHub", "VectorWatch Max Ultra 1TB Bundle"]
    assert split_bundle("HelioCam 1TB Dual-SIM/SonicBuds Mini") == ["HelioCam 1TB Dual-SIM", "SonicBuds Mini"]
    assert split_bundle("ZenithCam/TerraStand Mini Edge 1TB Refurbished/EchoPhone 256GB Dual-SIM") == [
        "ZenithCam", "TerraStand Mini Edge 1TB Refurbished", "EchoPhone 256GB Dual-SIM"]
 

def test_extra_separators_found_in_data():
    assert split_bundle("SignalCam 256GB Bundle + MiraPhone 128GB Dual-SIM") == [
        "SignalCam 256GB Bundle", "MiraPhone 128GB Dual-SIM"]
    assert split_bundle("SenseBook Plus, SparkDock, and OrionWatch Plus") == [
        "SenseBook Plus", "SparkDock", "OrionWatch Plus"]
 
 
def test_double_slash_gives_no_empty_piece():
    assert split_bundle("SignalBeam Ultra SE//SonicBuds Mini") == ["SignalBeam Ultra SE", "SonicBuds Mini"]


# stripping specs + packaging tests added:
def test_readme_spec_examples():
    assert strip_specs("AzureRouter SE Ultra 64GB Starter Kit")["base_name"] == "AzureRouter SE Ultra"
    assert strip_specs("AstraCam 512GB Dual-SIM")["base_name"] == "AstraCam"
    assert strip_specs("AuroraCam 1TB Starter Kit")["base_name"] == "AuroraCam"
 
 
def test_specs_are_kept_as_attributes():
    result = strip_specs("VectorWatch Max Ultra 1TB Bundle")
    assert result == {"storage": "1TB", "packaging": "Bundle", "revision": None,
                      "base_name": "VectorWatch Max Ultra"}
 
 
def test_revision_tag():
    result = strip_specs("SolPad Gen Edge RevA")
    assert result["base_name"] == "SolPad Gen Edge"
    assert result["revision"] == "RevA"
 
 
def test_specs_in_the_middle_of_a_name():
    assert strip_specs("Ruby Signal Grid 256GB Dual-SIM Nightfall")["base_name"] == "Ruby Signal Grid Nightfall"
 
 
def test_clean_name_unchanged():
    assert strip_specs("SenseBook Plus")["base_name"] == "SenseBook Plus"

# component normalization testing:
def components(text):
    return normalize_components(text, VOCAB)["components"]
 
 
def test_readme_translations():
    assert components("Sierra Kern") == "Sierra Core"
    assert components("Magenta Bouclier Mesh") == "Magenta Shield Mesh"
    assert components("Slate Matriz") == "Slate Matrix"
    assert components("Teal Lien") == "Teal Link"
 
 
def test_netz_and_rayo_follow_other_markets():
    assert components("Lyra Netz Pulse") == "Lyra Grid Pulse"
    assert components("Quanta Rayo") == "Quanta Beam"
 
 
def test_all_delimiters_give_same_result():
    expected = "Indigo Core | Lyra Kernel"
    for text in ["Indigo Core; Lyra Kernel", "Indigo Core + Lyra Kernel", "Indigo Core, Lyra Kernel",
                 "Indigo Core / Lyra Kernel", "Indigo Core and Lyra Kernel", "Indigo Core & Lyra Kernel",
                 "Lyra Kernel; Indigo Core"]:
        assert components(text) == expected
 
 
def test_readme_multi_component_with_translation():
    assert components("Magenta Lien Gewebe & Sonic Bouclier Kernel") == "Magenta Link Fabric | Sonic Shield Kernel"
 
 
def test_unknown_component_is_flagged_not_guessed():
    result = normalize_components("Indigo Core + Unobtanium Widget", VOCAB)
    assert result["components"] == "Indigo Core"
    assert result["unmatched_components"] == "Unobtanium Widget"
 
 
def test_missing_components():
    assert normalize_components(None, VOCAB)["components"] is None
    assert normalize_components(float("nan"), VOCAB)["component_count"] == 0


# brand suffixes + generic product testing:
BRANDS = {"GoldenGate", "Ironwood", "Springboard", "Starlight", "Seabird", "Copperline", "BlueRiver"}
 
 
def test_readme_generic_examples():
    for name, brand, component in [("Vega Beam GoldenGate", "GoldenGate", "Vega Beam"),
                                   ("Atlas Fabric Kernel BlueRiver", "BlueRiver", "Atlas Fabric Kernel"),
                                   ("Silver Kernel Beam Copperline", "Copperline", "Silver Kernel Beam")]:
        clean = strip_brand_suffix(name, brand, BRANDS)["model_name_clean"]
        assert clean == component
        assert detect_generic(clean, VOCAB) == component
 
 
def test_brand_on_a_real_model_name():
    result = strip_brand_suffix("GoldenCam Ironwood", "Ironwood", BRANDS)
    assert result["model_name_clean"] == "GoldenCam"
    assert detect_generic("GoldenCam", VOCAB) is None
 
 
def test_reseller_code_own_and_other_company():
    own = strip_brand_suffix("Indigo Core SpringboarPF", "Springboard", BRANDS)
    assert own["model_name_clean"] == "Indigo Core" and own["reseller_code"] == "PF"
 
    other = strip_brand_suffix("EchoPhone StarlightLU", "Seabird", BRANDS)
    assert other["model_name_clean"] == "EchoPhone" and other["reseller_brand"] == "Starlight"
 
 
def test_tier_words_are_not_brands():
    assert strip_brand_suffix("AzureRouter SE Ultra", "Skylark", BRANDS)["model_name_clean"] == "AzureRouter SE Ultra"
 
 
def test_generic_is_case_insensitive():
    assert detect_generic("Sierra matrix Node", VOCAB) == "Sierra Matrix Node"