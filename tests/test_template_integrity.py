"""Structural guardrails: every study (and _template itself) stays a valid copy.

These tests are what keeps `cp -r projects/_template projects/<new-study>`
trustworthy: run `pytest` right after copying and a green result means the
skeleton, config, and helpers all arrived intact.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_DIRS = [
    "data/raw",
    "data/interim",
    "data/processed",
    "src/utils",
    "src/models",
    "src/methods",
    "src/analysis",
    "scripts",
    "result/figures",
    "result/tables",
    "result/animations",
    "tests",
]
EXPECTED_FILES = [
    "config.py",
    "README.md",
    "data/README.md",
    "src/utils/figures.py",
    "src/utils/tables.py",
    "tests/conftest.py",
]
EXPECTED_CONFIG_ATTRS = [
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


def studies() -> list[Path]:
    return sorted(p.parent for p in (REPO_ROOT / "projects").glob("*/config.py"))


@pytest.mark.parametrize("study", studies(), ids=lambda p: p.name)
def test_study_skeleton_is_complete(study: Path):
    for directory in EXPECTED_DIRS:
        assert (study / directory).is_dir(), f"{study.name} is missing {directory}/"
    for file in EXPECTED_FILES:
        assert (study / file).is_file(), f"{study.name} is missing {file}"


@pytest.mark.parametrize("study", studies(), ids=lambda p: p.name)
def test_study_config_loads_with_all_attributes(study: Path, load_module_by_path):
    cfg = load_module_by_path(study / "config.py", f"integrity_{study.name}_config")

    for attr in EXPECTED_CONFIG_ATTRS:
        assert hasattr(cfg, attr), f"{study.name}/config.py is missing {attr}"
    assert cfg.STUDY_ROOT == study
    assert cfg.REPO_ROOT == REPO_ROOT
