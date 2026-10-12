"""Repo-level shared configuration for the dissertation.

Holds the shared locations and two thesis-wide constants that every study's
``projects/<study>/config.py`` re-exports:

- ``VISUALIZATION``: the figure appearance (dpi, format, font) shared by all
  chapters, so every chapter looks alike. It never changes a number.
- ``GEO``: physical constants.

Any value that can change a result (the seed, data selection, thresholds,
model settings) goes into the experiment's ``params.py``, never here: editing
a shared file must never change a finished experiment.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Shared manuscript location (the integrated thesis).
DRAFT_DIR = REPO_ROOT / "draft"
PROJECTS_DIR = REPO_ROOT / "projects"

# Physical constants shared by all studies.
GEO = {
    "earth_radius_m": 6_371_000.0,
}

# Figure appearance shared by all chapters (presentation only, never a number).
VISUALIZATION = {
    "dpi": 300,
    "format": "png",
    "font": {
        "family": "DejaVu Sans",
        "size": 12,
    },
}
