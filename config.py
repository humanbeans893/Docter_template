"""Repo-level shared configuration for the dissertation.

Holds only constants and paths that are common across all studies. Each study
defines its own data/result paths in ``projects/<study>/config.py`` and imports
the shared constants below.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Shared manuscript location (the integrated thesis).
DRAFT_DIR = REPO_ROOT / "draft"
PROJECTS_DIR = REPO_ROOT / "projects"

# Study-independent constants shared by all studies.
GEO = {
    "earth_radius_m": 6_371_000.0,
}

RANDOM = {
    "default_seed": 42,
}

VISUALIZATION = {
    "dpi": 300,
    "format": "png",
    "font": {
        "family": "DejaVu Sans",
        "size": 12,
    },
}
