from src.clean import normalize_text, split_bundle

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