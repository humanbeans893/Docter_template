"""Checks the run harness (src/utils/experiment.py) and how the helpers stage through it.

A run records what produced it, --smoke and a failed run never touch result/, a completed
run is not overwritten by accident, mistakes in names stop at the call, and what reaches
result/ arrives all at once (even across a kill) with sidecars that name the run. Ported
from research-template's tests/test_experiment_harness.py, with Docter's staging, journal
and D3/D4 git rules.
"""

import fcntl
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pytest

PARAMS = SimpleNamespace(SEED=1, PARAMS={"n": 100}, SMOKE={"n": 2})
CLEAN = {"commit": "a" * 40, "short": "aaaaaaa", "dirty": []}
VIZ = {"dpi": 72, "format": "png", "font": {"family": "DejaVu Sans", "size": 10}}
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.fixture(autouse=True)
def no_active_run(monkeypatch, experiment_mod):
    monkeypatch.delenv(experiment_mod.RUN_ENV, raising=False)
    monkeypatch.setattr(experiment_mod, "_WARNED", set())  # every test sees its warnings


@pytest.fixture
def cfg(tmp_path, monkeypatch, experiment_mod):
    """A study ``demo`` in a repository at tmp_path/repo, with a clean git state."""
    monkeypatch.setattr(experiment_mod, "git_state", lambda *args, **kwargs: dict(CLEAN))
    study = tmp_path / "repo" / "projects" / "demo"
    (study / "experiments").mkdir(parents=True)
    return SimpleNamespace(
        REPO_ROOT=tmp_path / "repo",
        STUDY_ROOT=study,
        FIGURE_DIR=study / "result" / "figures",
        TABLE_DIR=study / "result" / "tables",
        PROCESSED_DATA_DIR=study / "data" / "processed",
        VISUALIZATION=VIZ,
    )


@pytest.fixture
def run_file(cfg) -> str:
    return str(cfg.STUDY_ROOT / "experiments" / "001_toy" / "run.py")  # need not exist


@pytest.fixture
def start(experiment_mod, cfg):
    """``experiment.start`` bound to the fake study's config."""

    def start(run_file, params, argv):
        return experiment_mod.start(str(run_file), params, argv, cfg=cfg)

    return start


def _record(run_file, *parts: str) -> dict:
    path = Path(run_file).parent.joinpath("out", *parts, "params_used.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _where(flags: list[str]) -> tuple[str, ...]:
    """The record's place below out/ for these flags."""
    return ("smoke",) if "--smoke" in flags else ()


def _sidecar(directory: Path, name: str) -> dict:
    return json.loads((directory / f"{name}.provenance.json").read_text(encoding="utf-8"))


def _figure():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    return fig


def _files(directory: Path) -> dict[str, str]:
    return {path.name: path.read_text() for path in sorted(directory.iterdir())}


def _hidden(root: Path) -> list[str]:
    return sorted(path.name for path in root.rglob(".*")) if root.exists() else []


def _hermetic_study(tmp_path: Path, study_root: Path) -> Path:
    """This study's config and src/ in a fresh repository layout (no git)."""
    repo = tmp_path / "copy"
    study = repo / "projects" / study_root.name
    study.mkdir(parents=True)
    shutil.copy2(study_root.parents[1] / "config.py", repo / "config.py")
    shutil.copy2(study_root / "config.py", study / "config.py")
    shutil.copytree(study_root / "src", study / "src", ignore=shutil.ignore_patterns("__pycache__"))
    return study


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *GIT_ID, *args], check=True, capture_output=True, text=True
    )
    return done.stdout


@pytest.fixture
def committed(tmp_path):
    """A committed repository with the study ``demo`` (the real git_state)."""
    repo = tmp_path / "repo"
    for name, text in {
        "config.py": "X = 1\n",
        "pyproject.toml": "[project]\n",
        "docs/notes.md": "notes\n",
        "projects/demo/config.py": "Y = 1\n",
        "projects/demo/src/analysis.py": "x = 1\n",
        "projects/demo/experiments/EXP_SUMMARY.md": "index\n",
        "projects/demo/experiments/001_toy/run.py": "pass\n",
        "projects/demo/experiments/001_toy/params.py": "SEED = 1\n",
        "projects/demo/experiments/001_toy/summary.md": "card\n",
    }.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "initial")
    study = repo / "projects" / "demo"
    return SimpleNamespace(
        REPO_ROOT=repo,
        STUDY_ROOT=study,
        FIGURE_DIR=study / "result" / "figures",
        TABLE_DIR=study / "result" / "tables",
        PROCESSED_DATA_DIR=study / "data" / "processed",
        VISUALIZATION=VIZ,
    )


def _git_fields(directory: Path, name: str) -> tuple:
    sidecar = _sidecar(directory, name)
    return sidecar["git_commit"], sidecar["git_dirty"]


# --- research-template's tests, ported ------------------------------------------------


def test_smoke_applies_its_values_and_publishes_nothing(start, tables_mod, cfg, run_file):
    out = Path(run_file).parent / "out"
    with start(run_file, PARAMS, ["--smoke"]) as run:
        assert run.params == {"n": 2} and run.smoke and run.seed == 1
        staged = tables_mod.write_latex_values({"n": 2}, "demo-main", cfg)
        assert staged == out / "smoke" / "staged" / "tables" / "demo-main.tex"
        run.out("demo-t.csv").write_text("x\n1\n", encoding="utf-8")
        dest = run.promote("demo-t.csv")
        assert dest == cfg.TABLE_DIR / "demo-t.csv" and not dest.exists()
    record = _record(run_file, "smoke")
    assert (record["status"], record["smoke"], record["params"]) == ("completed", True, {"n": 2})
    assert record["staged"] == ["tables/demo-main", "tables/demo-t"]
    assert (record["promoted"], record["removed"]) == ([], [])
    assert not (out / "smoke" / "staged" / "tables" / "demo-t.csv").exists(), "never copied"
    assert not (cfg.STUDY_ROOT / "result").exists(), "a smoke run never writes result/"
    assert not (out / "params_used.json").exists(), "nor the full run's record"


def test_a_completed_full_run_is_not_overwritten_without_the_flag(start, cfg, run_file):
    with start(run_file, PARAMS, []) as run:
        run.stage("only stage")
    record = _record(run_file)
    assert list(record) == [
        "experiment", "study", "status", "smoke", "argv", "script", "pid", "started", "seed",
        "params", "params_sha256", "git", "python", "uv_lock_sha256", "stages", "staged",
        "promoted", "removed", "code_state", "finished", "elapsed_s",
    ]  # fmt: skip
    assert (record["status"], record["seed"], record["git"]["commit"]) == ("completed", 1, "a" * 40)
    assert (record["experiment"], record["study"]) == ("001_toy", "demo")
    assert record["script"] == "projects/demo/experiments/001_toy/run.py"
    assert list(record["git"]) == ["commit", "short", "dirty", "code_paths"]
    assert [stage["title"] for stage in record["stages"]] == ["only stage"]
    assert record["code_state"] == "clean"
    with pytest.raises(AssertionError, match=r"holds a completed run from .*--overwrite"):
        with start(run_file, PARAMS, []):
            pass
    assert _record(run_file)["started"] == record["started"]
    with start(run_file, PARAMS, ["--overwrite"]):
        pass
    assert _record(run_file)["argv"] == ["--overwrite"]


def test_a_rerun_clears_what_the_earlier_run_left(start, cfg, run_file, capsys):
    out = Path(run_file).parent / "out"
    out.mkdir(parents=True)
    (out / ".gitkeep").write_text("", encoding="utf-8")
    with start(run_file, PARAMS, []) as run:
        run.out("kept.csv").write_text("1\n", encoding="utf-8")
        run.out("figures/stale.png").write_text("x", encoding="utf-8")
    with start(run_file, PARAMS, ["--smoke"]) as run:
        run.out("smoke.csv").write_text("1\n", encoding="utf-8")
    capsys.readouterr()
    with start(run_file, PARAMS, ["--overwrite"]) as run:
        assert not (out / "figures").exists() and not (out / "kept.csv").exists()
        assert (out / "smoke" / "smoke.csv").is_file(), "a full run leaves out/smoke/ alone"
        run.out("kept.csv").write_text("2\n", encoding="utf-8")
    assert "cleared 3 entries left in projects/demo/experiments/001_toy/out" in (
        capsys.readouterr().out
    )
    assert sorted(path.name for path in out.iterdir()) == [
        ".gitkeep", ".lock", "kept.csv", "params_used.json", "smoke"
    ]  # fmt: skip


def test_files_no_recorded_run_wrote_need_the_flag(start, cfg, run_file):
    out = Path(run_file).parent / "out"
    out.mkdir(parents=True)
    (out / "manual.csv").write_text("1\n", encoding="utf-8")
    with pytest.raises(AssertionError, match=r"files that no recorded run wrote: \['manual.csv'\]"):
        with start(run_file, PARAMS, []):
            pass
    assert (out / "manual.csv").is_file()
    with start(run_file, PARAMS, ["--overwrite"]):
        pass
    assert not (out / "manual.csv").exists()


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("../escape.csv", "is not a file under projects/demo/experiments/001_toy/out"),
        ("/tmp/escape.csv", "is not a file under"),
        (".", "is not a file under"),
        ("staged/x.csv", "out/staged belongs to the harness"),
        ("params_used.json", "out/params_used.json belongs to the harness"),
        ("params_used.json.part", "belongs to the harness"),
        (".lock", "belongs to the harness"),
        ("smoke/x.csv", "out/smoke belongs to the harness"),
    ],
)
def test_outputs_cannot_leave_the_output_directory(start, cfg, run_file, name, message):
    with start(run_file, PARAMS, []) as run:
        with pytest.raises(AssertionError, match=message):
            run.out(name)
        with pytest.raises(AssertionError, match=message):
            run.promote(name)
    assert _record(run_file)["status"] == "completed"


def test_a_failed_run_is_recorded_and_can_be_rerun(start, cfg, run_file):
    for error in (RuntimeError("boom"), KeyboardInterrupt(), SystemExit(0)):
        with pytest.raises(type(error)):
            with start(run_file, PARAMS, []) as run:
                run.out("partial.csv").write_text("1\n", encoding="utf-8")
                raise error
        record = _record(run_file)
        assert record["status"] == "failed" and type(error).__name__ in record["error"]
        assert "finished" in record and record["promoted"] == []
    with start(run_file, PARAMS, []):
        assert not (Path(run_file).parent / "out" / "partial.csv").exists()
    assert _record(run_file)["status"] == "completed"


def test_a_dead_run_recorded_as_running_is_cleared(start, cfg, run_file, capsys):
    out = Path(run_file).parent / "out"
    out.mkdir(parents=True)
    (out / "params_used.json").write_text(json.dumps({"status": "running", "started": "t0"}))
    (out / "partial.csv").write_text("1\n", encoding="utf-8")
    with start(run_file, PARAMS, []):
        assert not (out / "partial.csv").exists()
    assert "the run started t0 died without recording its end" in capsys.readouterr().out
    assert _record(run_file)["status"] == "completed"


def test_a_live_run_holds_its_output_directory(start, cfg, run_file):
    out = Path(run_file).parent / "out"
    out.mkdir(parents=True)
    (out / "live.csv").write_text("1\n", encoding="utf-8")
    with open(out / ".lock", "w") as other_run:
        fcntl.flock(other_run, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(AssertionError, match=r"Another run is using .*001_toy/out: wait"):
            with start(run_file, PARAMS, ["--overwrite"]):
                pass
        with start(run_file, PARAMS, ["--smoke"]):  # the smoke directory has its own lock
            pass
    assert (out / "live.csv").is_file()


def test_publication_happens_only_when_the_run_completes(start, tables_mod, cfg, run_file):
    with pytest.raises(RuntimeError):
        with start(run_file, PARAMS, []) as run:
            tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
            run.out("demo-points.csv").write_text("x\n1\n", encoding="utf-8")
            run.promote("demo-points.csv")
            raise RuntimeError("a later stage fails")
    assert not cfg.TABLE_DIR.exists(), "a failed run must not reach result/"
    failed = _record(run_file)
    assert (failed["staged"], failed["promoted"]) == (
        ["tables/demo-main", "tables/demo-points"],
        [],
    )
    with start(run_file, PARAMS, []) as run:
        tables_mod.write_latex_values({"n": 2}, "demo-main", cfg)
        run.out("demo-points.csv").write_text("x\n2\n", encoding="utf-8")
        dest = run.promote("demo-points.csv")
        assert not cfg.TABLE_DIR.exists(), "published at completion"
        run.out("demo-points.csv").write_text("x\n3\n", encoding="utf-8")  # read at the end
    assert dest.read_text() == "x\n3\n"
    assert (cfg.TABLE_DIR / "demo-main.tex").read_text().splitlines()[1:] == [
        r"\defvalue{demo-main-n}{2}"
    ]
    assert _hidden(cfg.STUDY_ROOT / "result") == [], "no .part, .previous or journal left"
    assert _record(run_file)["promoted"] == [
        "projects/demo/result/tables/demo-main.csv",
        "projects/demo/result/tables/demo-main.tex",
        "projects/demo/result/tables/demo-points.csv",
    ]


def test_uncommitted_code_is_published_as_uncommitted(
    experiment_mod, start, tables_mod, cfg, run_file, monkeypatch, capsys
):
    dirty = {**CLEAN, "dirty": ["?? projects/demo/src/x.py"]}
    monkeypatch.setattr(experiment_mod, "git_state", lambda *args, **kwargs: dict(dirty))
    with start(run_file, PARAMS, []) as run:
        tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
        run.out("demo-points.csv").write_text("x\n1\n", encoding="utf-8")
        run.promote("demo-points.csv")
    for name in ("demo-main", "demo-points"):
        assert _git_fields(cfg.TABLE_DIR, name) == ("aaaaaaa", True)
    header = (cfg.TABLE_DIR / "demo-main.tex").read_text().splitlines()[0]
    assert header.endswith(", code-dirty -- do not edit by hand.")
    record = _record(run_file)
    assert (record["status"], record["code_state"]) == ("completed", "uncommitted")
    assert record["git"]["dirty"] == ["?? projects/demo/src/x.py"]
    err = capsys.readouterr().err
    assert "recorded as uncommitted code (make check W15)" in err
    assert "started from uncommitted code (projects/demo/src/x.py)" in err


def test_smoke_values_must_be_parameters(start, cfg, run_file):
    for params, message in (
        (SimpleNamespace(SEED=1, PARAMS={"n": 1}, SMOKE={"m": 1}), r"SMOKE keys missing .*\['m'\]"),
        (SimpleNamespace(SEED=1, PARAMS={"n": 1}), r"--smoke needs params\.SMOKE"),
        (
            SimpleNamespace(SEED=1, PARAMS={"n": 1}, SMOKE=[("n", 1)]),
            r"--smoke needs params\.SMOKE",
        ),
    ):
        with pytest.raises(AssertionError, match=message):
            with start(run_file, params, ["--smoke"]):
                pass
    with start(run_file, SimpleNamespace(SEED=1, PARAMS={"n": 1}), []):  # a full run needs none
        pass


def test_a_run_stopped_by_sigterm_is_recorded_as_failed(tmp_path, study_root):
    study = _hermetic_study(tmp_path, study_root)
    target = study / "experiments" / "001_sleeper"
    target.mkdir(parents=True)
    (target / "run.py").write_text(
        "import sys, time, types\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n"
        "import config\n"
        "from src.utils import experiment\n"
        "params = types.SimpleNamespace(SEED=1, PARAMS={})\n"
        "with experiment.start(__file__, params):\n"
        "    print('ready', flush=True)\n"
        "    time.sleep(60)\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [sys.executable, str(target / "run.py")],
        cwd=study.parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    for line in process.stdout:
        if line.strip() == "ready":
            break
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=30) == 128 + signal.SIGTERM
    record = json.loads((target / "out" / "params_used.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed" and "finished" in record
    assert record["error"].rstrip().endswith("SystemExit: 143")
    assert record["script"] == f"projects/{study.name}/experiments/001_sleeper/run.py"


def test_code_that_changes_during_the_run_marks_what_follows(
    experiment_mod, start, tables_mod, cfg, run_file, monkeypatch, capsys
):
    states = [dict(CLEAN)]
    monkeypatch.setattr(experiment_mod, "git_state", lambda *args, **kwargs: dict(states[-1]))
    with start(run_file, PARAMS, []) as run:
        tables_mod.write_latex_values({"n": 1}, "demo-before", cfg)
        run.out("demo-early.csv").write_text("x\n1\n", encoding="utf-8")
        run.promote("demo-early.csv")  # promoted now, checked against git when published
        states.append({**CLEAN, "dirty": [" M projects/demo/src/x.py"]})
        tables_mod.write_latex_values({"n": 1}, "demo-after", cfg)
    assert _git_fields(cfg.TABLE_DIR, "demo-before") == ("aaaaaaa", False)
    assert _git_fields(cfg.TABLE_DIR, "demo-after") == ("aaaaaaa", True)
    assert _git_fields(cfg.TABLE_DIR, "demo-early") == ("aaaaaaa", True)
    assert _record(run_file)["code_state"] == "changed_during_run"
    assert "the code changed during the run" in capsys.readouterr().err


def test_publication_is_all_or_none(experiment_mod, start, cfg, run_file, monkeypatch):
    cfg.TABLE_DIR.mkdir(parents=True)
    for name in ("demo-a.csv", "demo-b.csv"):
        (cfg.TABLE_DIR / name).write_text("old\n", encoding="utf-8")
    journal = cfg.STUDY_ROOT / "result" / ".publication.json"
    real_replace = os.replace
    seen = []

    def failing_replace(source, dest):
        name = Path(source).name
        if name.startswith(".demo-b.csv.") and name.endswith(".part"):
            seen.append(journal.is_file())
            raise OSError("disk full")
        return real_replace(source, dest)

    monkeypatch.setattr(experiment_mod.os, "replace", failing_replace)
    with pytest.raises(OSError, match="disk full"):
        with start(run_file, PARAMS, []) as run:
            for name in ("demo-a.csv", "demo-b.csv"):
                run.out(name).write_text("new\n", encoding="utf-8")
                run.promote(name)
    assert seen == [True], "the journal is written before anything in place changes"
    assert _files(cfg.TABLE_DIR) == {"demo-a.csv": "old\n", "demo-b.csv": "old\n"}
    assert _hidden(cfg.STUDY_ROOT / "result") == [], "no journal, part or backup is left"
    record = _record(run_file)
    assert (record["status"], record["promoted"], record["removed"]) == ("failed", [], [])


@pytest.mark.parametrize("content", [b'{"status": "runn', b"[]", b"{}", b"\xff\xfe"])
def test_an_unreadable_record_needs_the_flag(start, cfg, run_file, content):
    out = Path(run_file).parent / "out"
    out.mkdir(parents=True)
    (out / "params_used.json").write_bytes(content)
    with pytest.raises(AssertionError, match=r"params_used\.json is unreadable: .*--overwrite"):
        with start(run_file, PARAMS, []):
            pass
    with start(run_file, PARAMS, ["--overwrite"]):
        pass
    assert _record(run_file)["status"] == "completed"


# --- Docter: staging, publication and the run identity -----------------------------


def test_params_are_checked_before_anything_is_cleared(start, cfg, run_file):
    out = Path(run_file).parent / "out"
    with start(run_file, PARAMS, []) as run:
        run.out("kept.csv").write_text("1\n", encoding="utf-8")
    for params, message in (
        (SimpleNamespace(PARAMS={}), r"must pin SEED = <int> \(e\.g\. SEED = 42\), got None"),
        (SimpleNamespace(SEED=True, PARAMS={}), "must pin SEED"),
        (SimpleNamespace(SEED=1), r"must define PARAMS = \{\.\.\.\}"),
        (SimpleNamespace(SEED=1, PARAMS=[1]), "must define PARAMS"),
    ):
        with pytest.raises(AssertionError, match=message):
            with start(run_file, params, ["--overwrite"]):
                pass
        assert (out / "kept.csv").is_file()
        assert _record(run_file)["status"] == "completed"


def test_every_sidecar_names_the_experiment_and_the_run(
    experiment_mod, start, figures_mod, tables_mod, cfg, run_file
):
    with start(run_file, PARAMS, []) as run:
        figures_mod.save_figure(_figure(), "demo-overview", cfg)
        tables_mod.write_latex_table(pd.DataFrame({"x": [1, 2]}), "demo-table", cfg)
        run.out("demo-points.csv").write_text("x\n1\n", encoding="utf-8")
        run.promote("demo-points.csv")
    record = _record(run_file)
    assert record["params_sha256"] == experiment_mod.params_sha256(1, {"n": 100})
    for directory, name, kind in (
        (cfg.FIGURE_DIR, "demo-overview", "figure"),
        (cfg.TABLE_DIR, "demo-table", "table"),
        (cfg.TABLE_DIR, "demo-points", "file"),
    ):
        sidecar = _sidecar(directory, name)
        assert list(sidecar) == [
            "artifact", "kind", "study", "script", "experiment", "created", "git_commit",
            "git_dirty", "run", "files",
        ]  # fmt: skip
        assert (sidecar["artifact"], sidecar["kind"], sidecar["study"]) == (name, kind, "demo")
        assert sidecar["experiment"] == "001_toy"
        assert sidecar["script"] == "projects/demo/experiments/001_toy/run.py"
        assert sidecar["run"] == {
            "started": record["started"],
            "seed": 1,
            "params_sha256": record["params_sha256"],
        }
        assert (sidecar["git_commit"], sidecar["git_dirty"]) == ("aaaaaaa", False)
    assert _sidecar(cfg.TABLE_DIR, "demo-points")["files"] == {
        "demo-points.csv": hashlib.sha256(b"x\n1\n").hexdigest()
    }
    header = (cfg.TABLE_DIR / "demo-table.tex").read_text().splitlines()[0]
    assert (
        header == "% Generated by projects/demo/experiments/001_toy/run.py -- do not edit by hand."
    )
    assert record["staged"] == ["figures/demo-overview", "tables/demo-points", "tables/demo-table"]


def test_a_rerun_removes_what_this_experiment_no_longer_publishes(
    start, tables_mod, cfg, run_file, capsys
):
    with start(run_file, PARAMS, []):
        tables_mod.write_latex_values({"n": 1}, "demo-a", cfg)
        tables_mod.write_latex_values({"n": 1}, "demo-b", cfg)
    with start(cfg.STUDY_ROOT / "experiments" / "002_other" / "run.py", PARAMS, []):
        tables_mod.write_latex_values({"n": 1}, "demo-other", cfg)  # another experiment's
    tables_mod.write_latex_values({"n": 1}, "demo-script", cfg)  # a scripts/ artifact: no run
    capsys.readouterr()
    with start(run_file, PARAMS, ["--overwrite"]):
        tables_mod.write_latex_values({"n": 2}, "demo-a", cfg)
    assert sorted({path.name.split(".")[0] for path in cfg.TABLE_DIR.iterdir()}) == [
        "demo-a",
        "demo-other",
        "demo-script",
    ]
    assert not (cfg.TABLE_DIR / "demo-b.tex").exists()
    assert _record(run_file)["removed"] == [
        "projects/demo/result/tables/demo-b.csv",
        "projects/demo/result/tables/demo-b.tex",
    ]
    out = capsys.readouterr().out
    assert "removed projects/demo/result/tables/demo-b.tex (this experiment no longer" in out


def test_publication_replaces_the_whole_artifact(start, figures_mod, cfg, run_file, capsys):
    cfg.FIGURE_DIR.mkdir(parents=True)
    cfg.TABLE_DIR.mkdir(parents=True)
    (cfg.FIGURE_DIR / "demo-overview.pdf").write_bytes(b"%PDF old")
    (cfg.FIGURE_DIR / "demo-overviewx.pdf").write_bytes(b"%PDF another figure")
    (cfg.TABLE_DIR / "demo-points.json").write_text("[]\n", encoding="utf-8")
    old = {
        "artifact": "demo-points",
        "kind": "file",
        "study": "demo",
        "experiment": "000_old",
        "files": {"demo-points.json": "0" * 64},
    }
    (cfg.TABLE_DIR / "demo-points.provenance.json").write_text(json.dumps(old), encoding="utf-8")
    with start(run_file, PARAMS, []) as run:
        figures_mod.save_figure(_figure(), "demo-overview", cfg)
        run.out("demo-points.csv").write_text("x\n1\n", encoding="utf-8")
        run.promote("demo-points.csv")
    assert sorted(path.name for path in cfg.FIGURE_DIR.iterdir()) == [
        "demo-overview.png", "demo-overview.provenance.json", "demo-overviewx.pdf"
    ]  # fmt: skip
    assert sorted(path.name for path in cfg.TABLE_DIR.iterdir()) == [
        "demo-points.csv", "demo-points.provenance.json"
    ]  # fmt: skip
    assert _record(run_file)["removed"] == [
        "projects/demo/result/figures/demo-overview.pdf",
        "projects/demo/result/tables/demo-points.json",
    ]
    assert "demo-overview.pdf (replaced by another format)" in capsys.readouterr().out


@pytest.mark.parametrize("flags", [["--smoke"], []])
def test_kind_clashes_stop_at_the_call(start, tables_mod, cfg, run_file, flags):
    tables_mod.write_latex_table(pd.DataFrame({"x": [1]}), "demo-main", cfg)  # outside a run
    tables_mod.write_latex_values({"n": 1}, "demo-v", cfg)
    with start(run_file, PARAMS, flags) as run:
        with pytest.raises(AssertionError, match=r"'demo-main' in .* already holds a table"):
            tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
        run.out("demo-v.csv").write_text("1\n", encoding="utf-8")
        with pytest.raises(AssertionError, match=r"'demo-v' in .* already holds a values"):
            run.promote("demo-v.csv")
    assert _sidecar(cfg.TABLE_DIR, "demo-main")["kind"] == "table"
    assert _sidecar(cfg.TABLE_DIR, "demo-v")["kind"] == "values"
    assert _record(run_file, *_where(flags))["staged"] == []


@pytest.mark.parametrize("flags", [["--smoke"], []])
def test_names_without_the_study_prefix_stop_at_the_call(
    start, figures_mod, tables_mod, cfg, run_file, flags
):
    fig = _figure()
    with start(run_file, PARAMS, flags) as run:
        for write in (
            lambda: tables_mod.write_latex_values({"n": 1}, "main", cfg),
            lambda: tables_mod.write_latex_table(pd.DataFrame({"x": [1]}), "other-main", cfg),
            lambda: figures_mod.save_figure(fig, "overview", cfg, close=False),
        ):
            with pytest.raises(AssertionError, match=r"names in result/ start with 'demo-' .*W16"):
                write()
        assert not (run.out_dir / "staged").exists(), "nothing is staged"
    plt.close(fig)
    assert not cfg.TABLE_DIR.exists() and not cfg.FIGURE_DIR.exists()


@pytest.mark.parametrize("flags", [["--smoke"], []])
def test_an_artifact_is_written_once_per_run(start, figures_mod, tables_mod, cfg, run_file, flags):
    twice = "is written twice in this run: give each artifact its own name"
    fig = _figure()
    with start(run_file, PARAMS, flags) as run:
        tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
        with pytest.raises(AssertionError, match=f"demo-main {twice}"):
            tables_mod.write_latex_table(pd.DataFrame({"x": [1]}), "demo-main", cfg)
        run.out("demo-main.csv").write_text("1\n", encoding="utf-8")
        with pytest.raises(AssertionError, match=f"demo-main {twice}"):
            run.promote("demo-main.csv")
        run.out("demo-points.csv").write_text("1\n", encoding="utf-8")
        run.promote("demo-points.csv")
        with pytest.raises(AssertionError, match=f"demo-points {twice}"):
            run.promote("demo-points.csv")
        with pytest.raises(AssertionError, match=f"demo-points {twice}"):
            tables_mod.write_latex_values({"n": 1}, "demo-points", cfg)
        figures_mod.save_figure(fig, "demo-fig", cfg, close=False)
        with pytest.raises(AssertionError, match=f"demo-fig {twice}"):
            figures_mod.save_figure(fig, "demo-fig", cfg, close=False)
        run.out("grid.nc").write_text("1\n", encoding="utf-8")
        run.promote("grid.nc", dest_dir=cfg.PROCESSED_DATA_DIR / run.name)
        with pytest.raises(AssertionError, match=f"001_toy/grid.nc {twice}"):
            run.promote("grid.nc", dest_dir=cfg.PROCESSED_DATA_DIR / run.name)
    plt.close(fig)
    record = _record(run_file, *_where(flags))
    assert record["status"] == "completed"
    assert record["staged"] == [
        "figures/demo-fig", "tables/demo-main", "tables/demo-points", "processed/grid.nc"
    ]  # fmt: skip
    if not flags:
        assert (cfg.TABLE_DIR / "demo-main.tex").is_file()
        assert (cfg.TABLE_DIR / "demo-points.csv").read_text() == "1\n"


def test_a_template_publishes_nothing(experiment_mod, start, figures_mod, tables_mod, cfg):
    template = cfg.STUDY_ROOT / "experiments" / "_template" / "run.py"
    with start(template, PARAMS, ["--smoke"]) as run:  # a template may smoke
        tables_mod.write_latex_values({"n": 1}, "demo-a", cfg)
        figures_mod.save_figure(_figure(), "demo-b", cfg)
        run.out("demo-c.csv").write_text("1\n", encoding="utf-8")
        run.promote("demo-c.csv")
    record = _record(template, "smoke")
    assert record["status"] == "completed"
    assert record["staged"] == ["figures/demo-b", "tables/demo-a", "tables/demo-c"]
    message = "_template is a template and publishes nothing: create an experiment with make"
    with pytest.raises(AssertionError, match=message):
        with start(template, PARAMS, []):
            tables_mod.write_latex_values({"n": 1}, "demo-a", cfg)
    with pytest.raises(AssertionError, match=message):
        with start(template, PARAMS, []) as run:
            run.out("demo-c.csv").write_text("1\n", encoding="utf-8")
            run.promote("demo-c.csv")
    with start(template, PARAMS, []) as run:  # a full run that publishes nothing completes
        run.out("x.csv").write_text("1\n", encoding="utf-8")
    assert _record(template)["status"] == "completed"
    assert not cfg.TABLE_DIR.exists() and not cfg.FIGURE_DIR.exists()


def test_promote_destinations_are_checked(start, cfg, run_file):
    with start(run_file, PARAMS, []) as run:
        for name in ("demo-a.csv", "demo-a.b.csv", "other-a.csv"):
            run.out(name).write_text("1\n", encoding="utf-8")
        for dest in (
            cfg.FIGURE_DIR,
            cfg.REPO_ROOT / "projects" / "other" / "result" / "tables",
            cfg.PROCESSED_DATA_DIR,
            cfg.PROCESSED_DATA_DIR / "002_other",
            cfg.STUDY_ROOT / "experiments" / "001_toy",
        ):
            with pytest.raises(AssertionError, match=r"run\.promote\(\) writes to result/tables/"):
                run.promote("demo-a.csv", dest_dir=dest)
        for name in ("demo-a.b.csv", "other-a.csv"):
            with pytest.raises(
                AssertionError, match=r"<study>-<what>\.<ext> name with no other dot"
            ):
                run.promote(name)
        with pytest.raises(AssertionError, match=r"demo-missing\.csv does not exist: write it"):
            run.promote("demo-missing.csv")
        assert run.promote("demo-a.csv", dest_dir=cfg.TABLE_DIR) == cfg.TABLE_DIR / "demo-a.csv"
    assert sorted(path.name for path in cfg.TABLE_DIR.iterdir()) == [
        "demo-a.csv", "demo-a.provenance.json"
    ]  # fmt: skip


def test_large_outputs_replace_the_experiments_processed_directory(start, cfg, run_file, capsys):
    target = cfg.PROCESSED_DATA_DIR / "001_toy"
    target.mkdir(parents=True)
    (target / "stale.csv").write_text("old\n", encoding="utf-8")
    with start(run_file, PARAMS, ["--smoke"]) as run:
        run.out("grid/a.csv").write_text("smoke\n", encoding="utf-8")
        run.promote("grid/a.csv", dest_dir=target / "grid")
    assert _files(target) == {"stale.csv": "old\n"}, "--smoke never publishes"
    assert _record(run_file, "smoke")["staged"] == ["processed/grid/a.csv"]
    with start(run_file, PARAMS, []) as run:
        run.out("grid/a.csv").write_text("full\n", encoding="utf-8")
        assert run.promote("grid/a.csv", dest_dir=target / "grid") == target / "grid" / "a.csv"
        run.out("b.nc").write_text("b\n", encoding="utf-8")
        run.promote("b.nc", dest_dir=cfg.PROCESSED_DATA_DIR / run.name)
    assert sorted(path.relative_to(target).as_posix() for path in target.rglob("*")) == [
        "b.nc", "grid", "grid/a.csv"
    ]  # fmt: skip
    assert (target / "grid" / "a.csv").read_text() == "full\n"
    record = _record(run_file)
    assert record["promoted"] == ["projects/demo/data/processed/001_toy/"]
    assert record["staged"] == ["processed/b.nc", "processed/grid/a.csv"]
    assert _hidden(cfg.PROCESSED_DATA_DIR) == []
    capsys.readouterr()
    with start(run_file, PARAMS, ["--overwrite"]):  # promotes nothing there: kept
        pass
    assert (target / "b.nc").is_file()
    assert "001_toy is from an earlier run; this run promoted nothing there" in (
        capsys.readouterr().out
    )
    assert _record(run_file)["promoted"] == []


def test_an_interrupted_publication_is_rolled_back(start, cfg, run_file, capsys):
    # A publication killed in its swap: demo-a replaced (its old bytes in the backup),
    # demo-new created, demo-gone moved to its backup, demo-c not reached (its part is
    # there), and data/processed/001_toy swapped for the new directory.
    tables, processed = cfg.TABLE_DIR, cfg.PROCESSED_DATA_DIR
    tables.mkdir(parents=True)
    for name, text in {
        "demo-a.csv": "new\n",
        ".demo-a.csv.4242.previous": "old\n",
        "demo-new.csv": "new\n",
        ".demo-gone.csv.4242.previous": "gone\n",
        "demo-c.csv": "old c\n",
        ".demo-c.csv.4242.part": "half\n",
        ".gitkeep": "",
    }.items():
        (tables / name).write_text(text, encoding="utf-8")
    (processed / "001_toy").mkdir(parents=True)
    (processed / "001_toy" / "new.nc").write_text("new\n", encoding="utf-8")
    (processed / ".001_toy.4242.previous").mkdir()
    (processed / ".001_toy.4242.previous" / "old.nc").write_text("old\n", encoding="utf-8")

    def rel(path: Path) -> str:
        return path.relative_to(cfg.REPO_ROOT).as_posix()

    def entry(directory: Path, name: str, backup: bool = True) -> dict:
        previous = rel(directory / f".{name}.4242.previous") if backup else None
        return {"target": rel(directory / name), "backup": previous}

    journal = {
        "pid": 4242,
        "experiment": "001_toy",
        "entries": [
            entry(tables, "demo-gone.csv"),  # removals first, then the writes
            entry(tables, "demo-a.csv"),
            entry(tables, "demo-new.csv", backup=False),
            entry(tables, "demo-c.csv"),
        ],
        "processed": {
            **entry(processed, "001_toy"),
            "source": rel(Path(run_file).parent / "out" / "staged" / "processed"),
        },
    }
    (cfg.STUDY_ROOT / "result" / ".publication.json").write_text(json.dumps(journal))
    with start(run_file, PARAMS, []):  # every full run recovers first
        pass
    assert _files(tables) == {
        ".gitkeep": "",
        "demo-a.csv": "old\n",
        "demo-c.csv": "old c\n",
        "demo-gone.csv": "gone\n",
    }
    assert sorted(path.relative_to(processed).as_posix() for path in processed.rglob("*")) == [
        "001_toy", "001_toy/old.nc"
    ]  # fmt: skip
    assert not (cfg.STUDY_ROOT / "result" / ".publication.json").exists()
    out = capsys.readouterr().out
    assert "note: restored projects/demo/result/tables/demo-a.csv (publication killed)" in out
    assert "note: removed projects/demo/result/tables/demo-new.csv (publication killed)" in out


def test_leftovers_of_a_committed_publication_are_cleaned(experiment_mod, cfg, capsys):
    # Killed before its journal was written, or after its commit point: no journal.
    tables, processed = cfg.TABLE_DIR, cfg.PROCESSED_DATA_DIR
    tables.mkdir(parents=True)
    for name, text in {
        "demo-a.csv": "new\n",
        ".demo-a.csv.4242.previous": "old\n",
        ".demo-b.csv.4242.part": "half\n",
        ".gitkeep": "",
    }.items():
        (tables / name).write_text(text, encoding="utf-8")
    (cfg.STUDY_ROOT / "result" / ".publication.json.4242.part").write_text("{", encoding="utf-8")
    (processed / ".001_toy.4242.previous").mkdir(parents=True)
    (processed / ".001_toy.4242.previous" / "old.nc").write_text("old\n", encoding="utf-8")
    notes = experiment_mod.recover_interrupted_publication(cfg)
    assert _files(tables) == {".gitkeep": "", "demo-a.csv": "new\n"}
    assert list(processed.iterdir()) == []
    assert sorted(path.name for path in (cfg.STUDY_ROOT / "result").iterdir()) == ["tables"]
    backup = "projects/demo/result/tables/.demo-a.csv.4242.previous"
    assert f"removed {backup} (publication killed)" in notes
    assert len(notes) == 4 and capsys.readouterr().out.count("note: removed") == 4


def test_a_stage_reaches_the_record_when_it_starts(start, cfg, run_file, capsys):
    with start(run_file, PARAMS, []) as run:
        run.stage("load")
        on_disk = _record(run_file)
        assert (on_disk["status"], [s["title"] for s in on_disk["stages"]]) == ("running", ["load"])
        run.stage("fit")
        run.log("rmse 0.4")
    assert [s["title"] for s in _record(run_file)["stages"]] == ["load", "fit"]
    out = capsys.readouterr().out
    assert "[001_toy] full run -> projects/demo/experiments/001_toy/out" in out
    assert "[001_toy] 2. fit (t = " in out and "    rmse 0.4 (" in out
    assert "[001_toy] completed in " in out


def test_the_run_is_announced_only_while_it_runs(
    experiment_mod, start, figures_mod, cfg, run_file, monkeypatch
):
    record_path = Path(run_file).parent / "out" / "params_used.json"
    with start(run_file, PARAMS, []):
        assert os.environ[experiment_mod.RUN_ENV] == str(record_path)
        assert experiment_mod.active_run(cfg)["status"] == "running"
        with pytest.raises(AssertionError, match="runs do not nest"):
            with start(run_file, PARAMS, ["--smoke"]):
                pass
    assert experiment_mod.RUN_ENV not in os.environ
    assert experiment_mod.active_run(cfg) is None and experiment_mod.run_identity(cfg) is None
    monkeypatch.setenv(experiment_mod.RUN_ENV, str(record_path))  # a stale value
    fig = _figure()
    with pytest.raises(AssertionError, match="names a run that is not running: unset it"):
        figures_mod.save_figure(fig, "demo-x", cfg)
    plt.close(fig)
    assert not cfg.FIGURE_DIR.exists()


def test_a_foreign_or_unreadable_run_record_is_refused(
    experiment_mod, tables_mod, cfg, tmp_path, monkeypatch
):
    other = cfg.REPO_ROOT / "projects" / "other" / "experiments" / "001_x" / "out"
    other.mkdir(parents=True)
    script = "projects/other/experiments/001_x/run.py"
    (other / "params_used.json").write_text(json.dumps({"status": "running", "script": script}))
    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    for value, message in (
        (other / "params_used.json", f"{script} belongs to another study than demo"),
        (tmp_path / "missing.json", "names no readable run record"),
        (tmp_path / "list.json", r"names no readable run record \(not a JSON object\)"),
    ):
        monkeypatch.setenv(experiment_mod.RUN_ENV, str(value))
        with pytest.raises(AssertionError, match=message):
            tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
    assert not cfg.TABLE_DIR.exists()


def test_an_experiment_script_must_run_through_the_harness(
    figures_mod, tables_mod, cfg, monkeypatch
):
    for name in ("001_toy", "_template"):
        script = cfg.STUDY_ROOT / "experiments" / name / "run.py"
        monkeypatch.setattr(sys, "argv", [str(script)])
        message = (
            f"projects/demo/experiments/{name}/run.py writes results outside "
            r"experiment\.start\(\): wrap its body in `with experiment\.start\(__file__, params\)"
        )
        fig = _figure()
        with pytest.raises(AssertionError, match=message):
            figures_mod.save_figure(fig, "demo-overview", cfg)
        plt.close(fig)
        with pytest.raises(AssertionError, match=message):
            tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
    assert not cfg.FIGURE_DIR.exists() and not cfg.TABLE_DIR.exists()
    # A scripts/ promotion script writes to result/ at once, credited to itself.
    monkeypatch.setattr(sys, "argv", [str(cfg.STUDY_ROOT / "scripts" / "promote.py")])
    assert tables_mod.write_latex_values({"n": 1}, "demo-main", cfg) == (
        cfg.TABLE_DIR / "demo-main.tex"
    )
    sidecar = _sidecar(cfg.TABLE_DIR, "demo-main")
    assert (sidecar["script"], sidecar["experiment"]) == ("projects/demo/scripts/promote.py", None)
    assert "run" not in sidecar


def test_the_helpers_and_the_harness_share_one_module(
    figures_mod, tables_mod, experiment_mod, tmp_path, study_root
):
    assert figures_mod._experiment is tables_mod._experiment is experiment_mod
    assert sys.modules[experiment_mod.UTILS_KEY] is experiment_mod
    assert figures_mod.GRAPHICS_EXTENSIONS is experiment_mod.GRAPHICS_EXTENSIONS
    study = _hermetic_study(tmp_path, study_root)
    for first in ("experiment", "figures", "tables"):  # run.py's import order, and others
        code = (
            f"import sys; sys.path.insert(0, {str(study)!r}); "
            f"from src.utils import {first}; "
            "from src.utils import experiment, figures, tables; "
            "print(experiment is figures._experiment is tables._experiment, "
            "sys.modules[experiment.UTILS_KEY] is experiment)"
        )
        done = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            cwd=study,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        assert done.stdout.split() == ["True", "True"], first


def test_a_rerun_from_the_same_code_gives_the_same_bytes(
    start, figures_mod, tables_mod, cfg, run_file
):
    def run(flags):
        with start(run_file, PARAMS, flags) as run:
            figures_mod.save_figure(_figure(), "demo-overview", cfg)
            tables_mod.write_latex_table(pd.DataFrame({"x": [1.5]}), "demo-table", cfg)
            run.out("demo-points.csv").write_text("x\n1.5\n", encoding="utf-8")
            run.promote("demo-points.csv")
        return {
            path.name: path.read_bytes()
            for directory in (cfg.FIGURE_DIR, cfg.TABLE_DIR)
            for path in directory.iterdir()
            if not path.name.endswith(".provenance.json")
        }

    first = run([])
    assert sorted(first) == [
        "demo-overview.png", "demo-points.csv", "demo-table.csv", "demo-table.tex"
    ]  # fmt: skip
    assert run(["--overwrite"]) == first


def test_the_config_comes_from_run_py(experiment_mod, cfg, run_file, monkeypatch):
    monkeypatch.setitem(sys.modules, "config", cfg)  # what `import config` in run.py did
    with experiment_mod.start(run_file, PARAMS, []) as run:
        assert (run.study, run.name) == ("demo", "001_toy")
    assert _record(run_file)["study"] == "demo"
    other = SimpleNamespace(REPO_ROOT=cfg.REPO_ROOT, STUDY_ROOT=cfg.REPO_ROOT / "projects" / "x")
    monkeypatch.setitem(sys.modules, "config", other)
    with pytest.raises(AssertionError, match=r"001_toy/run\.py is not in projects/x/experiments/"):
        with experiment_mod.start(run_file, PARAMS, ["--overwrite"]):
            pass
    for config in (SimpleNamespace(STUDY_ROOT=cfg.STUDY_ROOT), None):
        if config is None:
            monkeypatch.delitem(sys.modules, "config")
        else:
            monkeypatch.setitem(sys.modules, "config", config)
        with pytest.raises(AssertionError, match=r"keep `import config` at the top of run\.py"):
            with experiment_mod.start(run_file, PARAMS, ["--overwrite"]):
                pass
    assert _record(run_file)["status"] == "completed"


@needs_git
def test_a_prose_commit_during_the_run_does_not_mark_the_artifacts(
    experiment_mod, tables_mod, committed, capsys
):
    cfg = committed
    run_file = cfg.STUDY_ROOT / "experiments" / "001_toy" / "run.py"
    start_commit = git(cfg.REPO_ROOT, "rev-parse", "--short", "HEAD").strip()
    with experiment_mod.start(str(run_file), PARAMS, [], cfg=cfg) as run:
        (cfg.REPO_ROOT / "docs" / "notes.md").write_text("edited\n", encoding="utf-8")
        (run_file.parent / "summary.md").write_text("answer\n", encoding="utf-8")
        git(cfg.REPO_ROOT, "commit", "-qam", "prose during the run")
        tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
        run.out("demo-points.csv").write_text("x\n1\n", encoding="utf-8")
        run.promote("demo-points.csv")
    for name in ("demo-main", "demo-points"):
        assert _git_fields(cfg.TABLE_DIR, name) == (start_commit, False)
    record = _record(run_file)
    assert (record["git"]["short"], record["git"]["dirty"]) == (start_commit, [])
    assert record["code_state"] == "clean"
    assert "changed during the run" not in capsys.readouterr().err


@needs_git
def test_a_code_commit_during_the_run_marks_them(experiment_mod, tables_mod, committed, capsys):
    cfg = committed
    run_file = cfg.STUDY_ROOT / "experiments" / "001_toy" / "run.py"
    start_commit = git(cfg.REPO_ROOT, "rev-parse", "--short", "HEAD").strip()
    with experiment_mod.start(str(run_file), PARAMS, [], cfg=cfg) as run:
        tables_mod.write_latex_values({"n": 1}, "demo-before", cfg)
        run.out("demo-points.csv").write_text("x\n1\n", encoding="utf-8")
        run.promote("demo-points.csv")
        (cfg.STUDY_ROOT / "src" / "analysis.py").write_text("x = 2\n", encoding="utf-8")
        git(cfg.REPO_ROOT, "commit", "-qam", "code during the run")
        tables_mod.write_latex_values({"n": 1}, "demo-after", cfg)
    assert _git_fields(cfg.TABLE_DIR, "demo-before") == (start_commit, False)
    assert _git_fields(cfg.TABLE_DIR, "demo-after") == (start_commit, True)
    assert _git_fields(cfg.TABLE_DIR, "demo-points") == (start_commit, True)
    assert _record(run_file)["code_state"] == "changed_during_run"
    assert "the code changed during the run" in capsys.readouterr().err


# --- More of the same guarantees ------------------------------------------------------


@needs_git
def test_a_new_experiment_created_during_the_run_counts_as_code(
    experiment_mod, tables_mod, committed
):
    # D3: every experiments/**/*.py of the study is code, so make the next experiment
    # before a long run (experiments/README.md).
    cfg = committed
    run_file = cfg.STUDY_ROOT / "experiments" / "001_toy" / "run.py"
    with experiment_mod.start(str(run_file), PARAMS, [], cfg=cfg):
        tables_mod.write_latex_values({"n": 1}, "demo-before", cfg)
        new = cfg.STUDY_ROOT / "experiments" / "002_next" / "run.py"
        new.parent.mkdir()
        new.write_text("pass\n", encoding="utf-8")
        tables_mod.write_latex_values({"n": 1}, "demo-after", cfg)
    assert _git_fields(cfg.TABLE_DIR, "demo-before")[1] is False
    assert _git_fields(cfg.TABLE_DIR, "demo-after")[1] is True
    assert _record(run_file)["code_state"] == "changed_during_run"


def test_flags_other_than_smoke_and_overwrite_stop_before_anything_exists(start, run_file):
    for argv, code in ((["--n", "3"], 2), (["-h"], 0)):
        with pytest.raises(SystemExit) as excinfo:
            with start(run_file, PARAMS, argv):
                pass
        assert excinfo.value.code == code
    assert not Path(run_file).parent.exists()


def test_without_git_the_run_and_its_artifacts_say_unknown(
    experiment_mod, start, tables_mod, cfg, run_file, monkeypatch, capsys
):
    monkeypatch.setattr(experiment_mod, "git_state", lambda *args, **kwargs: None)
    with start(run_file, PARAMS, []):
        tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
    record = _record(run_file)
    assert (record["git"]["commit"], record["code_state"]) == (None, "unknown")
    assert record["git"]["dirty"] == ["(git cannot tell: no work tree or commit)"]
    assert _git_fields(cfg.TABLE_DIR, "demo-main") == ("unknown", "unknown")
    assert "could not read git state" in capsys.readouterr().err


def test_what_reaches_staged_without_the_helpers_fails_the_publication(
    start, tables_mod, cfg, run_file
):
    message = r"out/staged/tables/ holds \['demo-x.csv'\], which no sidecar lists"
    with pytest.raises(AssertionError, match=message):
        with start(run_file, PARAMS, []) as run:
            tables_mod.write_latex_values({"n": 1}, "demo-main", cfg)
            (run.out_dir / "staged" / "tables" / "demo-x.csv").write_text("1\n", encoding="utf-8")
    # A hand-made set is held to the helpers' rules when it is published.
    with pytest.raises(AssertionError, match="names in result/ start with 'demo-'"):
        with start(run_file, PARAMS, []) as run:
            staged = run.out_dir / "staged" / "tables"
            staged.mkdir(parents=True)
            (staged / "x.csv").write_text("1\n", encoding="utf-8")
            sidecar = {"artifact": "x", "kind": "file", "files": {"x.csv": "0" * 64}}
            (staged / "x.provenance.json").write_text(json.dumps(sidecar), encoding="utf-8")
    assert not cfg.TABLE_DIR.exists()
    assert _record(run_file)["status"] == "failed"


def test_publications_in_one_study_take_turns(experiment_mod, cfg):
    result = cfg.STUDY_ROOT / "result"
    result.mkdir(parents=True)
    finished = threading.Event()

    def recover():
        experiment_mod.recover_interrupted_publication(cfg)
        finished.set()

    holder = os.open(result, os.O_RDONLY)  # another process publishing in this study
    thread = threading.Thread(target=recover)
    try:
        fcntl.flock(holder, fcntl.LOCK_EX)
        thread.start()
        assert not finished.wait(0.3), "a second publication waits for the first"
    finally:
        os.close(holder)
    thread.join(timeout=10)
    assert finished.is_set()
