"""Checks tools/new_experiment.py (make experiment / make experiment-import) on a copied study."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKIP = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache")
DATE = "2026-01-02"
HEADER = "| # | slug | 一行で | 状態 | 論文 | 由来 |"


@pytest.fixture(scope="module")
def new_experiment(repo_root, load_module_by_path):
    return load_module_by_path(repo_root / "tools" / "new_experiment.py", "new_experiment_test")


@pytest.fixture()
def repo(tmp_path, repo_root) -> Path:
    """projects/_template copied as the study `alpha`, plus the template itself."""
    root = tmp_path / "repo"
    template = repo_root / "projects" / "_template"
    shutil.copytree(template, root / "projects" / "alpha", ignore=SKIP)
    shutil.copytree(
        template / "experiments", root / "projects" / "_template" / "experiments", ignore=SKIP
    )
    for name in ("config.py", "pyproject.toml"):
        shutil.copy2(repo_root / name, root / name)
    return root


def experiments_dir(repo: Path) -> Path:
    return repo / "projects" / "alpha" / "experiments"


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def rows(repo: Path) -> list[str]:
    lines = (experiments_dir(repo) / "EXP_SUMMARY.md").read_text(encoding="utf-8").splitlines()
    start = lines.index(HEADER)
    table = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        table.append(line)
    return table


def run(new_experiment, repo, *argv):
    return new_experiment.main([*argv, "--date", DATE], root=repo)


def test_numbers_rows_and_placeholders(new_experiment, repo, capsys):
    assert run(new_experiment, repo, "alpha", "baseline_fit") == 0
    assert run(new_experiment, repo, "alpha", "second_try", "--summary", "  閾値を変える  ") == 0

    # The row starts open and empty: --summary is the question, not the answer.
    assert rows(repo) == [
        "| 001 | baseline_fit | (実行前) | 進行中 | — | 新規 |",
        "| 002 | second_try | (実行前) | 進行中 | — | 新規 |",
    ]
    first = experiments_dir(repo) / "001_baseline_fit"
    assert sorted(p.relative_to(first).as_posix() for p in first.rglob("*") if p.is_file()) == [
        "README.md",
        "out/.gitkeep",
        "params.py",
        "run.py",
        "summary.md",
    ]
    readme = (first / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# 001_baseline_fit: <")
    assert f"- **日付**: {DATE}" in readme and "YYYY-MM-DD" not in readme
    card = (first / "summary.md").read_text(encoding="utf-8")
    assert card.startswith("# 001_baseline_fit: <")
    assert "- **状態**: 進行中" in card
    for path in first.glob("*.*"):
        body = path.read_text(encoding="utf-8")
        assert "NNN_<slug>" not in body and "<study>" not in body, path
    second = experiments_dir(repo) / "002_second_try"
    for name in ("summary.md", "README.md"):
        title = (second / name).read_text(encoding="utf-8").splitlines()[0]
        assert title == "# 002_second_try: 閾値を変える", name
    run_py = (first / "run.py").read_text(encoding="utf-8")
    assert "projects/alpha/experiments/001_baseline_fit/run.py" in run_py
    assert "--smoke" in run_py
    out = capsys.readouterr().out
    command = "uv run python projects/alpha/experiments/001_baseline_fit/run.py"
    assert f"{command} --smoke" in out
    assert "summary.md" in out
    assert not [p for p in experiments_dir(repo).iterdir() if p.name.startswith(".")]


def test_numbers_continue_after_directories_and_archived_rows(new_experiment, repo):
    (experiments_dir(repo) / "007_old").mkdir()
    assert run(new_experiment, repo, "alpha", "after_dir") == 0
    archive = experiments_dir(repo) / "EXP_ARCHIVE.md"
    archive.write_text(
        archive.read_text(encoding="utf-8") + "| 010 | archived | x | 完了 | — | 新規 |\n",
        encoding="utf-8",
    )
    assert run(new_experiment, repo, "alpha", "after_archive") == 0

    assert (experiments_dir(repo) / "008_after_dir").is_dir()
    assert (experiments_dir(repo) / "011_after_archive").is_dir()
    assert [row.split(" | ")[0] for row in rows(repo)] == ["| 008", "| 011"]


def test_run_outputs_in_the_template_are_not_copied(new_experiment, repo):
    """A run of the template itself leaves its record, smoke/ and staged/ in out/."""
    out = experiments_dir(repo) / "_template" / "out"
    (out / "params_used.json").write_text("{}\n")
    for leftover in ("smoke/x", "staged/x"):
        (out / leftover).parent.mkdir(parents=True, exist_ok=True)
        (out / leftover).write_text("old run\n")
    (experiments_dir(repo) / "_template" / "__pycache__").mkdir()
    (experiments_dir(repo) / "_template" / "__pycache__" / "run.cpython-311.pyc").write_bytes(b"x")

    assert run(new_experiment, repo, "alpha", "clean_copy") == 0

    target = experiments_dir(repo) / "001_clean_copy"
    assert [p.name for p in (target / "out").iterdir()] == [".gitkeep"]
    assert not (target / "__pycache__").exists()


def test_import_uses_the_import_template(new_experiment, repo, capsys):
    argv = ["alpha", "logger_drift", "--import", "--from", "/old place/results"]
    argv += ["--legacy-id", "oldrepo@1a2b3c4:exp/012_drift", "--summary", "旧ロガーのドリフト"]

    assert run(new_experiment, repo, *argv) == 0

    # The legacy id and the summary stay out of the row.
    assert rows(repo) == ["| 001 | logger_drift | (実行前) | 進行中 | — | 取り込み |"]
    target = experiments_dir(repo) / "001_logger_drift"
    params = (target / "params.py").read_text(encoding="utf-8")
    assert 'config.RAW_DATA_DIR / "legacy" / "logger-drift"' in params
    readme = (target / "README.md").read_text(encoding="utf-8")
    card = (target / "summary.md").read_text(encoding="utf-8")
    assert (
        readme.splitlines()[0] == card.splitlines()[0] == "# 001_logger_drift: 旧ロガーのドリフト"
    )
    assert "- **元の実験**: `oldrepo@1a2b3c4:exp/012_drift`" in readme
    origin = "- 元の実験: `oldrepo@1a2b3c4:exp/012_drift`"
    assert f"{origin}(元の summary.md の状態と言えないことを確かめる)" in card.splitlines()
    assert "## 残りの手順" in card and "- [ ] " in card
    assert "<source>" not in readme and "<source>" not in params
    assert "- [ ] " not in readme  # the checklist lives in the card (残りの手順)
    assert readme.count("## 取り込み元とコマンド") == 1
    assert readme.count("作成時に `tools/new_experiment.py` が書いたものです") == 1
    section = readme.split("## 取り込み元とコマンド", 1)[1].split("\n## ", 1)[0]
    assert "<PATH>/ projects/alpha/data/raw/legacy/logger-drift/" in section
    assert "> projects/alpha/experiments/001_logger_drift/inputs.sha256" in section
    command = "uv run python projects/alpha/experiments/001_logger_drift/run.py"
    assert f"{command} --smoke\n" in section and f"{command}\n" in section
    assert "/old place" not in readme  # a host path never reaches the repository
    assert "## 訂正・追記" in readme.split("## 取り込み元とコマンド", 1)[1]
    out = capsys.readouterr().out
    assert "'/old place/results/' projects/alpha/data/raw/legacy/logger-drift/" in out
    assert "mkdir -p projects/alpha/data/raw/legacy/logger-drift" in out
    assert "sha256sum) > projects/alpha/experiments/001_logger_drift/inputs.sha256" in out
    assert f"{command} --smoke" in out
    assert "Tick 残りの手順 in projects/alpha/experiments/001_logger_drift/summary.md" in out


def test_a_readme_without_the_commands_section_gets_one(new_experiment):
    """A README whose 取り込み元とコマンド section was removed gets it back with the commands."""
    readme = new_experiment.add_commands("# x\n\n## 訂正・追記\n\nなし\n", "- commands\n")

    assert readme == (
        "# x\n\n## 取り込み元とコマンド\n\n"
        f"{new_experiment.COMMANDS_INTRO}\n\n- commands\n\n## 訂正・追記\n\nなし\n"
    )
    assert "<PATH>" in new_experiment.COMMANDS_INTRO
    # Without 訂正・追記 the section goes at the end.
    assert new_experiment.add_commands("# x\n", "- commands\n") == (
        f"# x\n\n## 取り込み元とコマンド\n\n{new_experiment.COMMANDS_INTRO}\n\n- commands\n"
    )
    # An existing section keeps its text and gets the commands at its end.
    existing = "# x\n\n## 取り込み元とコマンド\n\nintro\n\n## 訂正・追記\n\nなし\n"
    assert new_experiment.add_commands(existing, "- commands\n") == (
        "# x\n\n## 取り込み元とコマンド\n\nintro\n\n- commands\n\n## 訂正・追記\n\nなし\n"
    )


def test_the_import_template_has_the_commands_section(new_experiment, repo_root):
    """make experiment-import fills this section; the intro is the one the tool would add."""
    template = repo_root / "projects" / "_template" / "experiments" / "_import_template"
    readme = (template / "README.md").read_text(encoding="utf-8")
    assert readme.count("\n## 取り込み元とコマンド\n") == 1
    intro = readme.split("\n## 取り込み元とコマンド\n", 1)[1].split("\n## ", 1)[0].strip()
    assert intro == new_experiment.COMMANDS_INTRO
    assert "\n- 元の実験: " in (template / "summary.md").read_text(encoding="utf-8")


def test_import_with_an_explicit_source(new_experiment, repo, capsys):
    argv = ["alpha", "old_maps", "--import", "--source", "maps_2019-07"]

    assert run(new_experiment, repo, *argv) == 0

    params = (experiments_dir(repo) / "001_old_maps" / "params.py").read_text(encoding="utf-8")
    assert '"legacy" / "maps_2019-07"' in params
    assert "<PATH>/ projects/alpha/data/raw/legacy/maps_2019-07/" in capsys.readouterr().out


def test_dry_run_writes_nothing(new_experiment, repo, capsys):
    before = snapshot(repo)

    assert run(new_experiment, repo, "alpha", "baseline_fit", "--dry-run") == 0
    assert run(new_experiment, repo, "alpha", "old_runs", "--import", "--dry-run") == 0

    assert snapshot(repo) == before
    assert "| 001 | old_runs |" in capsys.readouterr().out


def drop_header(repo):
    index = experiments_dir(repo) / "EXP_SUMMARY.md"
    index.write_text(index.read_text(encoding="utf-8").replace(HEADER, "| # | slug |"))


def duplicate_header(repo):
    index = experiments_dir(repo) / "EXP_SUMMARY.md"
    index.write_text(index.read_text(encoding="utf-8") + f"\n{HEADER}\n|---|---|---|---|---|---|\n")


def drop_card(repo):
    (experiments_dir(repo) / "_template" / "summary.md").unlink()


def drop_card_title(repo):
    card = experiments_dir(repo) / "_template" / "summary.md"
    card.write_text(card.read_text(encoding="utf-8").replace("<問いを短く>", "問い"))


def drop_card_origin(repo):
    card = experiments_dir(repo) / "_import_template" / "summary.md"
    lines = card.read_text(encoding="utf-8").splitlines(keepends=True)
    card.write_text("".join(line for line in lines if not line.startswith("- 元の実験:")))


@pytest.mark.parametrize(
    ("argv", "damage"),
    [
        (["_template", "baseline_fit"], None),
        (["alpha", "Bad-Slug"], None),
        (["alpha", "trailing_"], None),
        (["alpha", "a" * 41], None),
        (["alpha", "x", "--summary", "a | b"], None),
        (["alpha", "x", "--summary", "two\nlines"], None),
        (["alpha", "x", "--source", "elsewhere"], None),
        (["alpha", "x", "--import", "--source", "Bad Name"], None),
        (["alpha", "x", "--import", "--legacy-id", "a|b"], None),
        (["ghost", "x"], None),
        (["alpha", "x"], drop_header),
        (["alpha", "x"], duplicate_header),
        (["alpha", "x"], drop_card),
        (["alpha", "x", "--summary", "問い"], drop_card_title),
        (
            ["alpha", "x", "--import", "--legacy-id", "r@1a2b3c4:experiments/001_x"],
            drop_card_origin,
        ),
    ],
)
def test_refuses_without_writing_anything(new_experiment, repo, argv, damage, capsys):
    if damage is not None:
        damage(repo)
    before = snapshot(repo)

    assert run(new_experiment, repo, *argv) == 1

    assert snapshot(repo) == before
    assert "nothing was written" in capsys.readouterr().err


def test_names_that_break_the_line_limit_are_refused(new_experiment, repo, capsys):
    """A long study name plus a long slug would put run.py over ruff's line length."""
    study = "b" * 40
    shutil.move(repo / "projects" / "alpha", repo / "projects" / study)
    before = snapshot(repo)

    assert run(new_experiment, repo, study, "a" * 40) == 1

    assert snapshot(repo) == before
    assert "shorten the slug" in capsys.readouterr().err


def test_a_reused_slug_is_refused(new_experiment, repo, capsys):
    assert run(new_experiment, repo, "alpha", "baseline_fit") == 0
    before = snapshot(repo)

    assert run(new_experiment, repo, "alpha", "baseline_fit") == 1

    assert snapshot(repo) == before
    assert "already used" in capsys.readouterr().err


def test_a_failure_while_writing_rolls_back(new_experiment, repo, monkeypatch, capsys):
    before = snapshot(repo)
    real_replace = os.replace

    def replace(source, target):
        if Path(source).is_dir():
            raise OSError("simulated failure")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)

    assert run(new_experiment, repo, "alpha", "baseline_fit") == 1

    monkeypatch.undo()
    assert snapshot(repo) == before
    assert not [p for p in experiments_dir(repo).iterdir() if p.name.startswith(".")]
    capsys.readouterr()


def run_script(repo: Path, script: Path, *argv: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("THESIS_EXPERIMENT_RUN", None)
    return subprocess.run(
        [sys.executable, str(script), *argv],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_experiments_run_and_pass_lint(new_experiment, repo):
    assert run(new_experiment, repo, "alpha", "baseline_fit") == 0
    assert run(new_experiment, repo, "alpha", "old_runs", "--import") == 0
    fresh = experiments_dir(repo) / "001_baseline_fit"
    imported = experiments_dir(repo) / "002_old_runs"

    result = run_script(repo, fresh / "run.py", "--smoke")
    assert result.returncode == 0, result.stderr
    smoke = record(fresh / "out" / "smoke" / "params_used.json")
    assert (smoke["status"], smoke["smoke"]) == ("completed", True)
    result = run_script(repo, fresh / "run.py")
    assert result.returncode == 0, result.stderr
    full = record(fresh / "out" / "params_used.json")
    assert (full["status"], full["smoke"], full["experiment"]) == (
        "completed",
        False,
        "001_baseline_fit",
    )
    assert full["script"] == "projects/alpha/experiments/001_baseline_fit/run.py"
    result = run_script(repo, imported / "run.py", "--smoke")
    assert result.returncode != 0
    assert "legacy/old-runs" in result.stderr and "inputs.sha256" in result.stderr

    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff is not installed here (it is in the project container)")
    lint = subprocess.run(
        [ruff, "check", "--no-cache", str(fresh), str(imported)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr

    # Case D (only a publication survives) and /external leave `import config` unused.
    params = imported / "params.py"
    text = params.read_text(encoding="utf-8")
    default = 'SOURCE_DIR = config.RAW_DATA_DIR / "legacy" / "old-runs"'
    assert default in text
    for source_dir in ("None", 'Path("/external/old-runs")'):
        params.write_text(text.replace(default, f"SOURCE_DIR = {source_dir}"), encoding="utf-8")
        lint = subprocess.run(
            [ruff, "check", "--no-cache", str(params)],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        assert lint.returncode == 0, source_dir + lint.stdout + lint.stderr
