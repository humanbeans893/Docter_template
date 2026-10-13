"""Shared fixtures for this study's own tests.

Tests here check what this study adds (its src/ and scripts/); test_study_config.py is the
first one. The helpers in src/utils/ and the experiment templates are copies of
projects/_template's and are tested once for every study in the repository's tests/study_kit/.

Self-contained on purpose: no repo-root imports, so the study keeps testing cleanly after
being copied or extracted from the monorepo. Load this study's modules with
``load_module_by_path`` under study-unique names: every study ships identically named
``config.py`` / ``src`` modules and the monorepo pytest run must not let them collide in
``sys.modules``.
"""

import importlib.util
from pathlib import Path

import pytest

STUDY_ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    """Load ``path`` as a module registered under the unique ``name``."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"Cannot load module from {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def study_root() -> Path:
    return STUDY_ROOT


@pytest.fixture(scope="session")
def load_module_by_path():
    return load_module


@pytest.fixture(scope="session")
def study_cfg():
    return load_module(STUDY_ROOT / "config.py", f"{STUDY_ROOT.name}_config_under_test")
