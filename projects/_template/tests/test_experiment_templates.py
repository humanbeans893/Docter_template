"""Run the experiment templates end to end in a hermetic copy of this study.

The copy reproduces the layout the templates rely on (repo-root config.py +
projects/<study>/{config.py, src/, experiments/{_template,_import_template}}) inside
tmp_path, so the runs never touch this study's data/, result/ or experiments/. Tests that
check what the provenance records say about the code commit the copy first (commit_all).
"""

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKIP = shutil.ignore_patterns("__pycache__", "out")
TEMPLATES = ("_template", "_import_template")
GIT_ID = ("-c", "user.name=test", "-c", "user.email=test@example.invalid")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
# Placeholder of the import template's regeneration step, filled by the tests below.
ACTUAL = "actual: dict[str, float] = {}"
REFERENCE = '{"rmse": {"value": 0.42, "atol": 0.005, "source": "smith2024ocean, Table 2"}}'
# How run.py's write-outputs comments show a call (fill_in uncomments them).
EXAMPLE = "        #   "


def clean_env() -> dict[str, str]:
    """This environment without a running experiment or another repository's git settings."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key != "THESIS_EXPERIMENT_RUN"
    }
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


@pytest.fixture()
def study(tmp_path, study_root) -> Path:
    repo = tmp_path / "repo"
    copy = repo / "projects" / study_root.name
    copy.mkdir(parents=True)
    shutil.copy2(study_root.parents[1] / "config.py", repo / "config.py")
    shutil.copy2(study_root / "config.py", copy / "config.py")
    shutil.copytree(study_root / "src", copy / "src", ignore=SKIP)
    for name in TEMPLATES:
        target = copy / "experiments" / name
        shutil.copytree(study_root / "experiments" / name, target, ignore=SKIP)
        (target / "out").mkdir()
        (target / "out" / ".gitkeep").write_bytes(b"")  # as committed, without earlier outputs
    return copy


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *GIT_ID, *args],
        env=clean_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def commit_all(study: Path) -> Path:
    """Commit the whole copy, as AGENTS.md asks before a full run. Returns the repository."""
    repo = study.parents[1]
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "code", "--allow-empty")
    return repo


def instantiate(study: Path, template: str, name: str, replacements=()) -> Path:
    """Copy an experiment template and fill its placeholders, as make experiment does."""
    target = study / "experiments" / name
    shutil.copytree(study / "experiments" / template, target)
    applied = set()
    for path in target.rglob("*"):
        if path.suffix in {".py", ".md"}:
            text = path.read_text(encoding="utf-8")
            text = text.replace("NNN_<slug>", name).replace("<study>", study.name)
            for old, new in replacements:
                if old in text:
                    applied.add(old)
                    text = text.replace(old, new)
            path.write_text(text, encoding="utf-8")
    missing = [old for old, _ in replacements if old not in applied]
    assert not missing, f"{template} no longer contains {missing}"
    return target


def set_params(exp: Path, **values: str) -> None:
    """Replace `NAME = ...` lines of params.py (one line each), as a user edits them."""
    path = exp / "params.py"
    lines = path.read_text(encoding="utf-8").splitlines()
    for name, value in values.items():
        hits = [i for i, line in enumerate(lines) if line.startswith((f"{name} ", f"{name}:"))]
        assert len(hits) == 1, f"params.py has {len(hits)} lines assigning {name}"
        lines[hits[0]] = f"{name} = {value}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(exp_dir: Path, *flags: str) -> subprocess.CompletedProcess:
    script = exp_dir / "run.py"
    return subprocess.run(
        [sys.executable, str(script), *flags],
        cwd=script.parents[4],  # the repository root, as in the documented command
        env=clean_env(),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def record(exp_dir: Path, *, smoke: bool = False) -> dict:
    out = exp_dir / "out" / "smoke" if smoke else exp_dir / "out"
    return json.loads((out / "params_used.json").read_text(encoding="utf-8"))


def files_under(directory: Path) -> set[Path]:
    if not directory.exists():
        return set()
    return {path for path in directory.rglob("*") if path.is_file()}


def write_legacy_tree(root: Path) -> dict[str, bytes]:
    files = {
        "metrics.csv": b"site,rmse\nA,0.42\n",
        "figs/map.png": b"\x89PNG not really",
        "logs/2024/run.log": b"done\n",
    }
    for name, content in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(content)
    (root / ".gitkeep").write_bytes(b"")
    return files


def write_manifest(manifest: Path, files: dict[str, bytes]) -> None:
    """The output of `find . -type f ! -name .gitkeep | LC_ALL=C sort | xargs sha256sum`."""
    lines = [f"{hashlib.sha256(files[name]).hexdigest()}  ./{name}" for name in sorted(files)]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_experiment_template_runs_smoke_then_full(study):
    exp = instantiate(study, "_template", "001_first_try")
    before = files_under(study)

    smoke = run(exp, "--smoke")

    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    written = files_under(study) - before
    assert written and all(path.is_relative_to(exp / "out" / "smoke") for path in written)
    used = record(exp, smoke=True)
    assert (used["status"], used["smoke"], used["params"]) == ("completed", True, {"n_samples": 10})
    assert "1. load and check inputs" in smoke.stdout

    full = run(exp)

    assert full.returncode == 0, full.stdout + full.stderr
    used = record(exp)
    assert (used["status"], used["seed"], used["smoke"]) == ("completed", 42, False)
    assert used["params"] == {"n_samples": 1_000}
    assert used["script"] == f"projects/{study.name}/experiments/001_first_try/run.py"
    assert [stage["title"] for stage in used["stages"]] == [
        "load and check inputs",
        "compute",
        "write outputs",
    ]
    assert (exp / "out" / "sample_mean.csv").is_file()
    assert record(exp, smoke=True)["status"] == "completed"  # a full run leaves out/smoke/

    again = run(exp)

    assert again.returncode != 0 and "--overwrite" in again.stderr
    assert record(exp)["started"] == used["started"]  # the completed run is untouched


def test_the_template_runs_in_place_and_writes_only_to_its_out(study):
    template = study / "experiments" / "_template"
    before = files_under(study)

    result = run(template, "--smoke")

    assert result.returncode == 0, result.stdout + result.stderr
    written = files_under(study) - before
    assert written and all(path.is_relative_to(template / "out" / "smoke") for path in written)
    assert record(template, smoke=True)["status"] == "completed"


@pytest.mark.parametrize("template", TEMPLATES)
def test_templates_import_the_harness_and_helpers_when_the_run_starts(study_root, template):
    # The commit a result is credited to is read when these are imported, so they are
    # imported at the top of run.py, not inside main() at the end of a long run.
    path = study_root / "experiments" / template / "run.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "src.utils"
        for alias in node.names
    }
    assert {"experiment", "figures", "tables"} <= top


def fill_in(exp: Path) -> Path:
    """Write the tables run.py's comments show, as a user does: uncomment them, define names."""
    path = exp / "run.py"
    lines: list[str] = []
    open_call = False
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        example = line[len(EXAMPLE) :] if line.startswith(EXAMPLE) else ""
        if example.startswith("tables.") or open_call:
            open_call = example.rstrip().endswith("(") or (open_call and example != ")\n")
            line = line.replace("#   ", "", 1)
        lines.append(line)
        if line.strip() == 'run.stage("write outputs")':
            lines.append("        n, rmse = int(sample.size), float(sample.std())\n")
    text = "".join(lines)
    assert text.count("\n        tables.write_latex_") == 2, "run.py no longer shows both calls"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_experiment_template_passes_lint_before_and_after_it_is_filled_in(study, study_root):
    # make lint and the CI run ruff over every experiment: the template must pass both
    # untouched and once its tables are written as its comments show (no stale noqa).
    ruff = shutil.which("ruff")
    pyproject = study_root.parents[1] / "pyproject.toml"
    if ruff is None or not pyproject.is_file():
        pytest.skip("ruff or the repository's pyproject.toml is not here")
    repo = study.parents[1]
    shutil.copy2(pyproject, repo / "pyproject.toml")  # the repository's lint rules
    untouched = instantiate(study, "_template", "001_untouched") / "run.py"
    filled = fill_in(instantiate(study, "_template", "002_filled"))

    for command in (["check"], ["format", "--check"]):
        lint = subprocess.run(
            [ruff, *command, "--no-cache", str(untouched), str(filled)],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert lint.returncode == 0, " ".join(command) + "\n" + lint.stdout + lint.stderr

    smoke = run(filled.parent, "--smoke")  # and the filled-in run works
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    assert record(filled.parent, smoke=True)["staged"] == [
        f"tables/{study.name}-main",
        f"tables/{study.name}-summary",
    ]


def test_import_template_refuses_to_run_before_files_are_registered(study):
    exp = instantiate(study, "_import_template", "001_past_run", [("<source>", "old-run")])

    result = run(exp, "--smoke")

    assert result.returncode != 0
    copy = (study / "data" / "raw" / "legacy" / "old-run").resolve()
    assert f"copy the past files to {copy}" in result.stderr
    assert "generate the manifest with" in result.stderr and "sha256sum" in result.stderr
    assert record(exp, smoke=True)["status"] == "failed"
    assert not (exp / "inputs.sha256").exists()


def test_import_template_verifies_a_nested_legacy_tree_once(study):
    exp = instantiate(study, "_import_template", "001_past_run", [("<source>", "old-run")])
    legacy = study / "data" / "raw" / "legacy" / "old-run"
    files = write_legacy_tree(legacy)
    write_manifest(exp / "inputs.sha256", files)

    full = run(exp)

    assert full.returncode == 0, full.stdout + full.stderr
    assert "3 past files match inputs.sha256" in full.stdout
    # The verification is kept outside out/, which every run clears.
    cache = study / "data" / "interim" / "001_past_run" / "inputs_verified.json"
    verified = json.loads(cache.read_text(encoding="utf-8"))
    assert set(verified["files"]) == set(files)
    assert verified["files"]["logs/2024/run.log"]["sha256"] == hashlib.sha256(b"done\n").hexdigest()
    stamp = (cache.stat().st_ino, cache.stat().st_mtime_ns)

    smoke = run(exp, "--smoke")

    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    assert (cache.stat().st_ino, cache.stat().st_mtime_ns) == stamp  # nothing hashed again

    (legacy / "metrics.csv").write_bytes(b"changed\n")
    tampered = run(exp, "--overwrite")  # the first full run completed

    assert tampered.returncode != 0
    assert "sha256 differs" in tampered.stderr
    assert record(exp)["status"] == "failed"


@needs_git
def test_import_template_publishes_transcribed_values_as_r3(study):
    exp = instantiate(study, "_import_template", "002_paper_table")
    set_params(
        exp,
        SOURCE_DIR="None",
        TRANSCRIBED='{"rmse": 0.42, "n": 120}',
        TRANSCRIBED_SOURCE='"smith2024ocean, Table 2"',
        TRANSCRIBED_FORMATS='{"rmse": "{:.2f}"}',
    )
    commit_all(study)
    result_dir = study / "result"

    smoke = run(exp, "--smoke")

    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    assert not files_under(result_dir)  # a smoke run publishes nothing

    full = run(exp)

    assert full.returncode == 0, full.stdout + full.stderr
    name = f"{study.name}-paper-table-transcribed"
    tables = result_dir / "tables"
    tex = (tables / f"{name}.tex").read_text(encoding="utf-8").splitlines()
    assert "code-dirty" not in tex[0]
    assert tex[1:] == [rf"\defvalue{{{name}-n}}{{120}}", rf"\defvalue{{{name}-rmse}}{{0.42}}"]
    sidecar = json.loads((tables / f"{name}.provenance.json").read_text(encoding="utf-8"))
    assert (sidecar["kind"], sidecar["reproducibility"]) == ("values", "R3")
    assert sidecar["transcribed_from"] == "smith2024ocean, Table 2"
    assert sidecar["experiment"] == "002_paper_table"
    assert sidecar["script"] == f"projects/{study.name}/experiments/002_paper_table/run.py"
    used = record(exp)
    assert (sidecar["git_commit"], sidecar["git_dirty"]) == (used["git"]["short"], False)
    assert sidecar["run"] == {
        "started": used["started"],
        "seed": 42,
        "params_sha256": used["params_sha256"],
    }
    assert used["code_state"] == "clean"
    assert used["promoted"] == [
        f"projects/{study.name}/result/tables/{name}.{ext}" for ext in ("csv", "tex")
    ]


def test_import_template_publishes_nothing_when_the_crosscheck_fails(study):
    exp = instantiate(
        study,
        "_import_template",
        "003_mismatch",
        [(ACTUAL, 'actual: dict[str, float] = {"rmse": 0.5}')],
    )
    set_params(
        exp,
        SOURCE_DIR="None",
        TRANSCRIBED='{"n": 120}',
        TRANSCRIBED_SOURCE='"smith2024ocean, Table 2"',
        REFERENCE_VALUES=REFERENCE,
    )

    result = run(exp)

    assert result.returncode != 0
    assert "crosscheck failed" in result.stderr and "rmse: 0.5 vs 0.42" in result.stderr
    assert not files_under(study / "result")  # nothing, not even the transcribed (R3) values
    used = record(exp)
    assert (used["status"], used["promoted"]) == ("failed", [])
    assert "crosscheck failed" in used["error"]


def test_import_template_publishes_the_crosscheck_after_it_passes(study):
    exp = instantiate(
        study,
        "_import_template",
        "004_match",
        [(ACTUAL, 'actual: dict[str, float] = {"rmse": 0.4231}')],
    )
    set_params(
        exp,
        SOURCE_DIR="None",
        TRANSCRIBED='{"n": 120}',
        TRANSCRIBED_SOURCE='"smith2024ocean, Table 2"',
        REFERENCE_VALUES=REFERENCE,
    )

    result = run(exp)

    assert result.returncode == 0, result.stdout + result.stderr
    tables = study / "result" / "tables"
    name = f"{study.name}-match-crosscheck"
    rows = (tables / f"{name}.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("key,actual,reference,")
    assert rows[1].startswith("rmse,0.4231,0.42,")
    sidecar = json.loads((tables / f"{name}.provenance.json").read_text(encoding="utf-8"))
    assert (sidecar["kind"], sidecar["experiment"]) == ("file", "004_match")
    assert (tables / f"{study.name}-match-transcribed.tex").is_file()
    assert f"projects/{study.name}/result/tables/{name}.csv" in record(exp)["promoted"]


@needs_git
def test_a_full_run_from_uncommitted_code_is_published_as_uncommitted(study):
    exp = instantiate(study, "_import_template", "005_dirty")
    set_params(
        exp,
        SOURCE_DIR="None",
        TRANSCRIBED='{"n": 120}',
        TRANSCRIBED_SOURCE='"smith2024ocean, Table 2"',
    )
    repo = commit_all(study)
    (study / "src" / "x.py").write_text("X = 1\n", encoding="utf-8")  # not committed

    result = run(exp)

    assert result.returncode == 0, result.stdout + result.stderr  # D4: recorded, not refused
    assert "W15" in result.stderr
    name = f"{study.name}-dirty-transcribed"
    tables = study / "result" / "tables"
    sidecar = json.loads((tables / f"{name}.provenance.json").read_text(encoding="utf-8"))
    assert sidecar["git_dirty"] is True
    assert ", code-dirty" in (tables / f"{name}.tex").read_text(encoding="utf-8").splitlines()[0]
    used = record(exp)
    assert used["git"]["commit"] == git(repo, "rev-parse", "HEAD").strip()
    assert sidecar["git_commit"] == used["git"]["short"]  # the commit the run started from
    assert used["code_state"] == "uncommitted"
    assert any(line.endswith(f"projects/{study.name}/src/x.py") for line in used["git"]["dirty"])
