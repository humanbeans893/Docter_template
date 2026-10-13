"""Configuration for a single study (self-contained).

All paths resolve under THIS study directory, so a study can be copied or
extracted without rewiring. The two thesis-wide constants are loaded from the
repo-root ``config.py`` by explicit file path (this module is itself imported
as ``config``, so a name-based ``from config import ...`` would be a circular
self-import): ``VISUALIZATION``, the figure appearance shared by all chapters
(it never changes a number), and ``GEO``, physical constants. Any value that
can change a result (the seed, data selection, thresholds, model settings)
belongs in the experiment's ``params.py``, never here.

Start a new study with ``make study`` (``tools/new_study.py``), which copies
``projects/_template/`` and registers the study with the thesis build.

``PROJECT_ROOT`` / ``DATA_ROOT`` / ``EXPERIMENTS_DIR`` repeat research-template's
names for the same locations, so experiment code ported from a
research-template repository finds them; ``EXP_DIR`` is the older
research-template name of ``EXPERIMENTS_DIR``.
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

# Numbered experiments (experiments/NNN_<slug>/), see experiments/README.md.
EXPERIMENTS_DIR = STUDY_ROOT / "experiments"

# research-template names for the same locations (EXP_DIR: its older name).
PROJECT_ROOT = STUDY_ROOT
DATA_ROOT = RAW_DATA_DIR
EXP_DIR = EXPERIMENTS_DIR

__all__ = [
    "ANIMATION_DIR",
    "DATA_DIR",
    "DATA_ROOT",
    "EXPERIMENTS_DIR",
    "EXP_DIR",
    "FIGURE_DIR",
    "GEO",
    "INTERIM_DATA_DIR",
    "PROCESSED_DATA_DIR",
    "PROJECT_ROOT",
    "RAW_DATA_DIR",
    "REPO_ROOT",
    "RESULT_DIR",
    "STUDY_ROOT",
    "TABLE_DIR",
    "VISUALIZATION",
]
