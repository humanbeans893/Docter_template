"""Fixtures for the study kit tests: projects/_template's helpers and experiment templates.

Every study's src/utils/ and experiments/{_template,_import_template}/ are copies of
projects/_template's (tests/test_study_copies.py checks it), so these tests run once, against
projects/_template, and cover every study. Modules are loaded by explicit file path under
unique names, as the helpers expect (every study ships identically named src modules).
"""

from pathlib import Path

import pytest

# The study every other study copies its helpers and experiment templates from.
TEMPLATE_STUDY = Path(__file__).resolve().parents[2] / "projects" / "_template"
UTILS = TEMPLATE_STUDY / "src" / "utils"


@pytest.fixture(scope="session")
def study_root() -> Path:
    """projects/_template: the helpers in its src/utils/ and its experiment templates."""
    return TEMPLATE_STUDY


@pytest.fixture(scope="session")
def figures_mod(load_module_by_path):
    return load_module_by_path(UTILS / "figures.py", "study_kit_figures_under_test")


@pytest.fixture(scope="session")
def tables_mod(load_module_by_path):
    return load_module_by_path(UTILS / "tables.py", "study_kit_tables_under_test")


@pytest.fixture(scope="session")
def provenance_mod(load_module_by_path):
    return load_module_by_path(UTILS / "provenance.py", "study_kit_provenance_under_test")


@pytest.fixture(scope="session")
def experiment_mod(figures_mod):
    """src/utils/experiment.py as the helpers see it (one module per file per process)."""
    return figures_mod._experiment
