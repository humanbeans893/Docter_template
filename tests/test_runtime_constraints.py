"""Checks the runtime rules of AGENTS.md (実行環境) from inside the project container.

Project Python runs in Docker, the environment and tool state stay off the bind-mounted
repository, files written in the container belong to the host user, and the raw data of
every study is read-only inside the container. Nothing here writes to raw data. CI runs the
tests outside the project container, so only the checks of the files (docker-compose*.yml,
.claude/settings.json) run there.
"""

import json
import os
import re
import sys
from pathlib import Path

import pytest

in_container = pytest.mark.skipif(
    os.environ.get("CI") == "true", reason="CI runs outside the project container"
)

ROOT = Path(__file__).resolve().parents[1]
STUDIES = sorted(path.parent for path in (ROOT / "projects").glob("*/config.py"))
RAW_MOUNT_HINT = (
    "add its read-only bind block to docker-compose.yml above `# thesis:raw-mounts:end` "
    "(tools/new_study.py writes it; copy the block of another study), then run `make up`. "
    "make up recreates the container and stops running jobs: check `docker compose top`, "
    "STATE.md and experiments/JOBS.md first."
)


@in_container
def test_python_runs_in_docker() -> None:
    assert Path("/.dockerenv").is_file(), (
        "Run project Python and tests in Docker: make test, or "
        "docker compose exec research-template uv run pytest"
    )


@in_container
@pytest.mark.parametrize("directory", [ROOT, *STUDIES], ids=lambda p: p.name)
def test_no_virtualenv_in_the_repository(directory: Path) -> None:
    # lexists: a symlink to an environment elsewhere counts too.
    found = [name for name in (".venv", "venv") if os.path.lexists(directory / name)]
    assert not found, (
        f"Virtualenv in the repository: {[str(directory / name) for name in found]}. "
        "Remove it: the environment lives in the image at /opt/venv (make lock && make build)"
    )


@in_container
def test_project_environment_is_the_image_environment() -> None:
    assert "UV_PROJECT_ENVIRONMENT" in os.environ, (
        "UV_PROJECT_ENVIRONMENT is not set (see docker-compose.yml and the Dockerfile)"
    )
    environment = Path(os.environ["UV_PROJECT_ENVIRONMENT"]).resolve()
    assert Path(sys.prefix).resolve() == environment, (
        f"Python runs from {sys.prefix}, not from UV_PROJECT_ENVIRONMENT={environment}: "
        "use uv run inside the container"
    )
    assert not environment.is_relative_to(ROOT), (
        f"UV_PROJECT_ENVIRONMENT={environment} is inside the bind-mounted repository"
    )


RUNTIME_STATE_VARIABLES = (
    "HOME",
    "UV_CACHE_DIR",
    "MPLCONFIGDIR",
    "PYTHONPYCACHEPREFIX",
    "RUFF_CACHE_DIR",
)


@in_container
@pytest.mark.parametrize("variable", RUNTIME_STATE_VARIABLES)
def test_runtime_state_stays_outside_the_repository(variable: str) -> None:
    assert variable in os.environ, f"{variable} is not set (see docker-compose.yml)"
    path = Path(os.environ[variable])
    assert path.is_absolute() and not path.resolve().is_relative_to(ROOT), (
        f"{variable}={path} must be an absolute path outside the repository, or tool state is "
        "written back to the host (see docker-compose.yml)"
    )


@in_container
def test_container_user_owns_the_repository() -> None:
    owner = ROOT.stat().st_uid
    assert os.getuid() == owner, (
        f"The container runs as uid {os.getuid()}, but the repository belongs to uid {owner}: "
        "files written in the container would not belong to you. Start it with make up (the "
        "Makefile exports UID and GID for docker-compose.yml `user:` and the image build)"
    )


@in_container
@pytest.mark.parametrize("study", STUDIES, ids=lambda p: p.name)
def test_raw_data_is_read_only(study: Path) -> None:
    raw = study / "data" / "raw"
    assert raw.is_dir(), f"projects/{study.name}/data/raw is missing: restore it with its .gitkeep"
    assert os.statvfs(raw).f_flag & os.ST_RDONLY, (
        f"projects/{study.name}/data/raw is writable in the container: {RAW_MOUNT_HINT}"
    )


@in_container
def test_external_files_are_read_only_when_mounted() -> None:
    # docker-compose.files.yml in COMPOSE_FILE (.env) mounts EXTERNAL_FILES_DIR at /external.
    external = Path("/external")
    if external.exists():
        assert os.statvfs(external).f_flag & os.ST_RDONLY, (
            "/external is writable: keep read_only: true in docker-compose.files.yml"
        )


# --- The files that set up the container (these run in CI too) ------------------------------
CONTAINER_FILES = sorted([*ROOT.glob("docker-compose*.yml"), ROOT / "Dockerfile"])


@pytest.mark.parametrize("path", CONTAINER_FILES, ids=lambda p: p.name)
def test_container_publishes_no_ports(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    published = re.findall(r"^\s*(?:ports\s*:|EXPOSE\b)", text, re.MULTILINE)
    assert not published, (
        f"{path.name} publishes a port. The container publishes no ports: a fixed host port "
        "clashes with other projects' containers on the first start."
    )
    # The template has no notebook server: no service, port or setting for one.
    assert not re.search(r"jupyter", text, re.IGNORECASE), f"{path.name} mentions Jupyter"


def test_python_output_is_unbuffered() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert re.search(r'^\s+PYTHONUNBUFFERED:\s*"1"\s*$', compose, re.MULTILINE), (
        'Keep PYTHONUNBUFFERED: "1" in the environment of docker-compose.yml: without it the '
        "stage progress of a run under docker compose exec -T or in a log file shows only at exit"
    )


@pytest.mark.parametrize("override", ["docker-compose.gpu.yml", "docker-compose.files.yml"])
def test_overrides_are_enabled_once_in_compose_file(override: str) -> None:
    # A -f on one command is lost on the next plain `make up` (and make test's automatic start).
    header = (ROOT / override).read_text(encoding="utf-8").split("services:")[0]
    assert re.search(rf"COMPOSE_FILE=docker-compose\.yml:\S*{re.escape(override)}", header), (
        f"The header of {override} must say how to list it in COMPOSE_FILE in the local .env"
    )


def test_host_python_environments_are_denied() -> None:
    # AGENTS.md: project Python runs in Docker; the stdlib tools in tools/ (python3) and
    # uvx pre-commit stay allowed on the host.
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
    }
    assert required <= deny, f"missing deny rules: {sorted(required - deny)}"
    assert not deny & {"Bash(python3 *)", "Bash(python3:*)", "Bash(uvx *)", "Bash(uvx:*)"}, (
        "host python3 (tools/) and uvx pre-commit must stay allowed"
    )
