"""Shared fixtures for this study's tests.

Self-contained on purpose: no repo-root imports, so the study keeps testing
cleanly after being copied or extracted from the monorepo. Modules are loaded
by explicit file path under study-unique names because every study ships
identically named ``config.py`` / ``src`` modules and the monorepo pytest run
must not let them collide in ``sys.modules``.
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


@pytest.fixture(scope="session")
def figures_mod():
    return load_module(
        STUDY_ROOT / "src" / "utils" / "figures.py", f"{STUDY_ROOT.name}_figures_under_test"
    )


@pytest.fixture(scope="session")
def tables_mod():
    return load_module(
        STUDY_ROOT / "src" / "utils" / "tables.py", f"{STUDY_ROOT.name}_tables_under_test"
    )
