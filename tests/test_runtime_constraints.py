"""Checks the environment rules of AGENTS.md: Python runs in the project container, and its
environment and tool state stay off the bind-mounted repository. CI runs outside the project
container, so only the file checks run there."""

import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="CI runs outside the container")
def test_runs_in_the_container_with_state_outside_the_repository() -> None:
    assert Path("/.dockerenv").is_file(), "Run the tests in Docker: make test"
    assert not Path(sys.prefix).resolve().is_relative_to(ROOT), (
        f"Python runs from {sys.prefix} inside the repository: the environment lives in the "
        "image at /opt/venv (make lock && make build)"
    )
    for variable in ("HOME", "UV_CACHE_DIR", "PYTHONPYCACHEPREFIX", "RUFF_CACHE_DIR"):
        path = Path(os.environ.get(variable, "."))
        assert path.is_absolute() and not path.resolve().is_relative_to(ROOT), (
            f"{variable} must be an absolute path outside the repository (docker-compose.yml)"
        )
    assert os.getuid() == ROOT.stat().st_uid, (
        "The container does not run as the owner of the repository: start it with make up"
    )


@pytest.mark.parametrize("name", ["docker-compose.yml", "Dockerfile"])
def test_container_publishes_no_ports_and_no_notebook(name: str) -> None:
    text = (ROOT / name).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:ports\s*:|EXPOSE\b)", text, re.MULTILINE), (
        f"{name} publishes a port: it clashes with other projects' containers"
    )
    assert not re.search(r"jupyter", text, re.IGNORECASE), f"{name} mentions Jupyter"


def test_agent_permissions() -> None:
    # Project Python runs in Docker (host python3 runs only the stdlib tools/), the research
    # repositories linked under external/ are never written from here, and .env stays unread.
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = set(settings["permissions"]["deny"])
    required = {
        "Bash(python *)",
        "Bash(python3 -m venv*)",
        "Bash(python3 -m pip*)",
        "Bash(pip *)",
        "Bash(pip3 *)",
        "Bash(virtualenv *)",
        "Bash(uv *)",
        "Edit(external/**)",
        "Write(external/**)",
        "Read(.env)",
    }
    assert required <= deny, f"missing deny rules: {sorted(required - deny)}"
    assert not deny & {"Bash(python3 *)", "Bash(python3:*)", "Bash(uvx *)", "Bash(uvx:*)"}, (
        "host python3 (tools/) and uvx pre-commit must stay allowed"
    )
