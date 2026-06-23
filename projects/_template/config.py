"""Configuration for a single study (self-contained).

All paths resolve under THIS study directory, so a study can be copied or
extracted without rewiring. Shared, study-independent constants
(``GEO`` / ``RANDOM`` / ``VISUALIZATION``) are imported from the repo-root
``config.py`` to avoid duplication.

To start a new study, copy the whole ``projects/_template/`` directory to
``projects/<your-study-name>/``.
"""

import sys
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parent
REPO_ROOT = STUDY_ROOT.parents[1]  # projects/<study>/ -> repo root

# Make the repo-root shared config importable however this module is invoked.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import GEO, RANDOM, VISUALIZATION  # noqa: E402  shared constants

# --- Study-local paths (mirror the original single-study layout) ---
DATA_DIR = STUDY_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INTERIM_DATA_DIR = DATA_DIR / "interim"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

RESULT_DIR = STUDY_ROOT / "result"
FIGURE_DIR = RESULT_DIR / "figures"
TABLE_DIR = RESULT_DIR / "tables"
ANIMATION_DIR = RESULT_DIR / "animations"

__all__ = [
    "GEO",
    "RANDOM",
    "VISUALIZATION",
    "STUDY_ROOT",
    "REPO_ROOT",
    "DATA_DIR",
    "RAW_DATA_DIR",
    "INTERIM_DATA_DIR",
    "PROCESSED_DATA_DIR",
    "RESULT_DIR",
    "FIGURE_DIR",
    "TABLE_DIR",
    "ANIMATION_DIR",
]
