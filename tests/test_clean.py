from src.clean import normalize_text

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