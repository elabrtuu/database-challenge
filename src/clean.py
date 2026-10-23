import re
import unicodedata

import pandas as pd

DASHES = "‐‑‒–—−" # encompasses all types of possible dashes
DASH_PATTERN = re.compile(f"[{DASHES}]")


