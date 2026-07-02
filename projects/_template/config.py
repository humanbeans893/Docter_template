"""Configuration for a single study (self-contained).

All paths resolve under THIS study directory, so a study can be copied or
extracted without rewiring. Shared, study-independent constants
(``GEO`` / ``RANDOM`` / ``VISUALIZATION``) are loaded from the repo-root
``config.py`` by explicit file path: this module is itself imported as
``config``, so a name-based ``from config import ...`` would be a circular
self-import.

To start a new study, copy the whole ``projects/_template/`` directory to
``projects/<your-study-name>/``.
"""

import importlib.util
from pathlib import Path

STUDY_ROOT = Path(__file__).resolve().parent
REPO_ROOT = STUDY_ROOT.parents[1]  # projects/<study>/ -> repo root

_spec = importlib.util.spec_from_file_location("_dissertation_root_config", REPO_ROOT / "config.py")
assert _spec is not None and _spec.loader is not None, (
    f"Cannot load repo-root config.py from {REPO_ROOT}"
)
_root_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_root_config)

GEO = _root_config.GEO
RANDOM = _root_config.RANDOM
VISUALIZATION = _root_config.VISUALIZATION

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
    "ANIMATION_DIR",
    "DATA_DIR",
    "FIGURE_DIR",
    "GEO",
    "INTERIM_DATA_DIR",
    "PROCESSED_DATA_DIR",
    "RANDOM",
    "RAW_DATA_DIR",
    "REPO_ROOT",
    "RESULT_DIR",
    "STUDY_ROOT",
    "TABLE_DIR",
    "VISUALIZATION",
]
