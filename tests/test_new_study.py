"""Checks tools/new_study.py (make study) on a copy of the real files it edits."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

MARKER = "% thesis:study-chapters:end"
MOUNT_MARKER = "# thesis:raw-mounts:end"
SKIP = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache")


@pytest.fixture(scope="module")
def new_study(repo_root, load_module_by_path):
    return load_module_by_path(repo_root / "tools" / "new_study.py", "new_study_under_test")


@pytest.fixture(scope="module")
def thesis_check(repo_root, load_module_by_path):
    return load_module_by_path(repo_root / "tools" / "thesis_check.py", "thesis_check_for_study")


@pytest.fixture()
def repo(tmp_path, repo_root) -> Path:
    """The files the tool reads and edits, copied from this repository."""
    root = tmp_path / "repo"
    draft = repo_root / "draft"

    def draft_outputs(directory, names):
        # Build directory and built PDFs are outputs; hand-made figures stay.
        if Path(directory) == draft:
            return {name for name in names if name == "build" or name.endswith(".pdf")}
        return SKIP(directory, names)

    shutil.copytree(draft, root / "draft", ignore=draft_outputs)
    shutil.copytree(
        repo_root / "projects" / "_template", root / "projects" / "_template", ignore=SKIP
    )
    (root / "docs").mkdir()
    for name in ("docker-compose.yml", "config.py", "pyproject.toml", "docs/thesis-plan.md"):
        shutil.copy2(repo_root / name, root / name)
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def graphicspath_line(path: Path) -> str:
    lines = [line for line in text(path).splitlines() if line.startswith("\\graphicspath")]
    assert len(lines) == 1, f"{path.name} must keep one \\graphicspath line"
    return lines[0]


def next_chapter(repo: Path, offset: int = 0) -> str:
    """NN of the next study chapter: after the highest one below 99 in the copied draft."""
    numbers = [
        int(path.name[:2])
        for path in (repo / "draft" / "chapters").glob("[0-9][0-9]-*.tex")
        if path.name[:2] != "99"
    ]
    return f"{max(numbers, default=0) + 1 + offset:02d}"


def errors(thesis_check, repo: Path) -> set[tuple[str, str]]:
    findings = thesis_check.run_all(repo / "draft", with_log=False)
    return {(f.code, f.message) for f in findings if f.severity == "error"}


def test_creates_the_study_and_registers_it(new_study, thesis_check, repo, capsys):
    template = repo / "projects" / "_template"
    nn = next_chapter(repo)
    main_before = text(repo / "draft" / "main.tex").splitlines()
    # The copy has the thesis's chapters but not its studies' results: compare, do not expect 0.
    errors_before = errors(thesis_check, repo)

    assert new_study.main(["demo", "--title", "Effects of A & B_1"], root=repo) == 0

    study = repo / "projects" / "demo"
    readme = text(study / "README.md")
    assert readme.startswith("# Effects of A & B_1\n\n")
    assert "template-only" not in readme and "\n\n\n" not in readme
    for path in [
        study / "README.md",
        study / "data" / "README.md",
        *study.glob("experiments/**/*"),
    ]:
        if path.suffix in {".md", ".py"}:
            body = text(path)
            assert "<study>" not in body and "<Study title>" not in body, path
            assert "template-only" not in body, path
    run_py = text(study / "experiments" / "_template" / "run.py")
    assert "projects/demo/experiments/NNN_<slug>/run.py" in run_py
    # The procedure is the same in every study: the template's, with the name filled.
    assert text(study / "experiments" / "README.md") == text(
        template / "experiments" / "README.md"
    ).replace("<study>", "demo")
    # src/ and tests/ are copied unchanged; data/ and result/ only keep their skeleton.
    for area in ("src", "tests"):
        for path in (template / area).rglob("*.py"):
            assert (study / path.relative_to(template)).read_bytes() == path.read_bytes()
    for area in ("data", "result"):
        kept = {p.name for p in (study / area).rglob("*") if p.is_file()}
        assert kept <= {".gitkeep", "README.md"}, kept
    assert (study / "data" / "raw" / ".gitkeep").is_file()
    assert not list(study.rglob("__pycache__"))

    chapter = text(repo / "draft" / "chapters" / f"{nn}-demo.tex")
    assert chapter.startswith("\\chapter{Effects of A \\& B\\_1}\n\\label{ch:demo}\n")
    assert "template-only" not in chapter and "<study>" not in chapter
    assert "\\label{sec:demo-summary}" in chapter

    at = main_before.index(MARKER)
    include = f"\\include{{chapters/{nn}-demo}}"
    assert text(repo / "draft" / "main.tex").splitlines() == [
        *main_before[:at],
        include,
        *main_before[at:],
    ]
    for name in ("preamble.tex", "supplementary.tex"):
        line = graphicspath_line(repo / "draft" / name)
        assert line.endswith("{../projects/demo/result/figures/}}"), line

    compose = text(repo / "docker-compose.yml").splitlines()
    end = next(i for i, line in enumerate(compose) if MOUNT_MARKER in line)
    assert compose[end - 6 : end] == [
        "      - type: bind",
        "        source: ./projects/demo/data/raw",
        "        target: /workspace/projects/demo/data/raw",
        "        read_only: true",
        "        bind:",
        "          create_host_path: false",
    ]

    plan = text(repo / "docs" / "thesis-plan.md").splitlines()
    conclusion = next(i for i, line in enumerate(plan) if "chapters/99-conclusion.tex" in line)
    row = plan[conclusion - 1]
    assert row.startswith(f"| `ch:demo` | `chapters/{nn}-demo.tex` | `projects/demo` |")
    header = next(line for line in plan if line.startswith("| 章ラベル"))
    assert row.count("|") == header.count("|")

    leftovers = [
        p for p in repo.rglob("*") if p.name.endswith(".tmp") or p.name.startswith(".demo")
    ]
    assert leftovers == []
    assert errors(thesis_check, repo) - errors_before == set()
    assert "make up" in capsys.readouterr().out


def test_second_study_is_numbered_after_the_first(new_study, repo):
    first, second = next_chapter(repo), next_chapter(repo, 1)
    assert new_study.main(["demo", "--title", "Demo"], root=repo) == 0
    assert new_study.main(["more_data", "--title", "More"], root=repo) == 0

    main_lines = text(repo / "draft" / "main.tex").splitlines()
    at = main_lines.index(MARKER)
    assert main_lines[at - 2 : at] == [
        f"\\include{{chapters/{first}-demo}}",
        f"\\include{{chapters/{second}-more_data}}",
    ]
    plan = text(repo / "docs" / "thesis-plan.md")
    assert plan.index("`ch:demo`") < plan.index("`ch:more_data`") < plan.index("`ch:conclusion`")
    assert graphicspath_line(repo / "draft" / "preamble.tex").endswith(
        "{../projects/demo/result/figures/}{../projects/more_data/result/figures/}}"
    )


def test_title_tex_is_inserted_unchanged(new_study, repo):
    nn = next_chapter(repo)
    assert new_study.main(["demo", "--title-tex", r"Effects of $\alpha$"], root=repo) == 0

    chapter = text(repo / "draft" / "chapters" / f"{nn}-demo.tex")
    assert chapter.startswith("\\chapter{Effects of $\\alpha$}\n")


def test_study_without_chapter(new_study, repo):
    before = snapshot(repo)

    assert new_study.main(["synthesis", "--no-chapter"], root=repo) == 0

    after = snapshot(repo)
    assert not list((repo / "draft" / "chapters").glob("*-synthesis.tex"))
    for unchanged in ("draft/main.tex", "docs/thesis-plan.md"):
        assert after[unchanged] == before[unchanged]
    assert "../projects/synthesis/result/figures/" in graphicspath_line(
        repo / "draft" / "supplementary.tex"
    )
    assert "./projects/synthesis/data/raw" in text(repo / "docker-compose.yml")
    assert text(repo / "projects" / "synthesis" / "README.md").startswith("# synthesis\n")


def test_dry_run_writes_nothing(new_study, repo, capsys):
    before = snapshot(repo)
    nn = next_chapter(repo)

    assert new_study.main(["demo", "--title", "Demo", "--dry-run"], root=repo) == 0

    assert snapshot(repo) == before
    out = capsys.readouterr().out
    assert f"draft/chapters/{nn}-demo.tex" in out and "Dry run" in out


def break_main_marker(repo):
    path = repo / "draft" / "main.tex"
    path.write_text(text(path).replace(MARKER + "\n", ""), encoding="utf-8")


def break_compose_marker(repo):
    path = repo / "docker-compose.yml"
    path.write_text(text(path).replace(MOUNT_MARKER, "# end"), encoding="utf-8")


def duplicate_graphicspath(repo):
    path = repo / "draft" / "preamble.tex"
    path.write_text(text(path) + "\\graphicspath{{figures/}}\n", encoding="utf-8")


def split_graphicspath(repo):
    path = repo / "draft" / "supplementary.tex"
    path.write_text(
        text(path).replace("\\graphicspath{{figures/}", "\\graphicspath{{figures/}\n"),
        encoding="utf-8",
    )


def drop_conclusion_row(repo):
    path = repo / "docs" / "thesis-plan.md"
    lines = [line for line in text(path).splitlines(keepends=True) if "99-conclusion" not in line]
    path.write_text("".join(lines), encoding="utf-8")


def experiment_in_template(repo):
    (repo / "projects" / "_template" / "experiments" / "001_stray").mkdir()


def existing_study(repo):
    (repo / "projects" / "demo").mkdir()


def break_template_index(repo):
    path = repo / "projects" / "_template" / "experiments" / "EXP_SUMMARY.md"
    path.write_text(text(path).replace("| 論文 | 由来 |", "|"), encoding="utf-8")


@pytest.mark.parametrize(
    "damage",
    [
        break_main_marker,
        break_compose_marker,
        duplicate_graphicspath,
        split_graphicspath,
        drop_conclusion_row,
        experiment_in_template,
        existing_study,
        break_template_index,
    ],
)
def test_refuses_without_writing_anything(new_study, repo, damage, capsys):
    damage(repo)
    before = snapshot(repo)

    assert new_study.main(["demo", "--title", "Demo"], root=repo) == 1

    assert snapshot(repo) == before
    assert "nothing was written" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["_template", "--title", "T"],
        ["Demo", "--title", "T"],
        ["1demo", "--title", "T"],
        ["demo-two", "--title", "T"],
        ["demo_", "--title", "T"],
        ["demo", "--title", "A | B"],
        ["demo", "--title", "two\nlines"],
        ["demo", "--title", "  "],
        ["demo", "--title-tex", "\\textbf{open"],
        ["demo"],
    ],
)
def test_refuses_bad_names_and_titles(new_study, repo, argv, capsys):
    before = snapshot(repo)

    assert new_study.main(argv, root=repo) == 1

    assert snapshot(repo) == before
    capsys.readouterr()


def test_title_and_title_tex_are_exclusive(new_study, repo):
    with pytest.raises(SystemExit):
        new_study.main(["demo", "--title", "A", "--title-tex", "B"], root=repo)


def test_a_failure_while_writing_rolls_everything_back(new_study, repo, monkeypatch, capsys):
    before = snapshot(repo)
    real_replace = os.replace

    def replace(source, target):
        if Path(source).is_dir():
            raise OSError("simulated failure")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)

    assert new_study.main(["demo", "--title", "Demo"], root=repo) == 1

    monkeypatch.undo()
    assert snapshot(repo) == before
    assert not [p for p in (repo / "projects").iterdir() if p.name.startswith(".")]
    assert "rolled back" in capsys.readouterr().err


def test_the_new_study_passes_its_own_tests_and_lint(new_study, repo):
    assert new_study.main(["demo", "--title", "Demo"], root=repo) == 0
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "projects/demo"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert tests.returncode == 0, tests.stdout + tests.stderr

    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff is not installed here (it is in the project container)")
    lint = subprocess.run(
        [ruff, "check", "--no-cache", "projects/demo"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr
