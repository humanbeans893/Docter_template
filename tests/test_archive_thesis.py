"""Checks tools/archive_thesis.py (make archive) on a throwaway git repository."""

import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

GIT_IDENTITY = ["-c", "user.name=Thesis Test", "-c", "user.email=test@users.noreply.github.com"]

if shutil.which("git") is None:
    pytest.skip("git is not installed", allow_module_level=True)


@pytest.fixture(scope="module")
def archive_thesis(repo_root, load_module_by_path):
    return load_module_by_path(repo_root / "tools" / "archive_thesis.py", "archive_thesis_test")


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *GIT_IDENTITY, "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def write(path: Path, content: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def repo(tmp_path, repo_root) -> Path:
    """A committed, tagged thesis with one generated figure, raw data and built PDFs."""
    root = tmp_path / "thesis"
    root.mkdir()
    shutil.copy2(repo_root / ".gitignore", root / ".gitignore")
    write(
        root / "draft" / "main.tex",
        "\\documentclass{article}\n\\graphicspath{{../projects/s1/result/figures/}}\n"
        "\\begin{document}\\includegraphics{s1-map}\\end{document}\n",
    )
    write(root / "draft" / "review.tex", "\\input{main.tex}\n")
    write(root / "draft" / "supplementary.tex", "\\documentclass{article}\n")
    write(root / "projects" / "s1" / "scripts" / "make_map.py", "print('map')\n")
    write(root / "projects" / "s1" / "experiments" / "001_fit" / "run.py", "print('fit')\n")
    # The figure is drawn from a CSV that experiment 001 promoted (run.promote()).
    fit = write(root / "projects" / "s1" / "result" / "tables" / "s1-fit.csv", "x\n1\n")
    fit_sidecar = {
        "artifact": "s1-fit",
        "kind": "file",
        "script": "projects/s1/experiments/001_fit/run.py",
        "experiment": "001_fit",
        "git_commit": "abc1234",
        "git_dirty": False,
        "files": {"s1-fit.csv": sha256(fit)},
    }
    write(fit.with_name("s1-fit.provenance.json"), json.dumps(fit_sidecar))
    figure = write(root / "projects" / "s1" / "result" / "figures" / "s1-map.png", b"png")
    sidecar = {
        "artifact": "s1-map",
        "script": "projects/s1/scripts/make_map.py",
        "experiment": None,
        "git_commit": "abc1234",
        "git_dirty": False,
        "files": {"s1-map.png": sha256(figure)},
        "sources": [{"path": "projects/s1/result/tables/s1-fit.csv", "sha256": sha256(fit)}],
    }
    write(figure.with_name("s1-map.provenance.json"), json.dumps(sidecar))
    write(root / "projects" / "s1" / "data" / "raw" / ".gitkeep", b"")
    write(root / "projects" / "s1" / "data" / "raw" / "obs.csv", "t,x\n0,1\n")
    write(root / "projects" / "s1" / "data" / "raw" / "legacy" / "old" / "m.png", b"old")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "thesis")
    git(root, "tag", "v1")
    write(root / "draft" / "submission.pdf", b"%PDF submission")
    write(root / "draft" / "supplementary.pdf", b"%PDF supplementary")
    return root


def test_archives_the_tagged_submission(archive_thesis, repo, capsys):
    assert archive_thesis.main(["--tag", "v1"], root=repo) == 0

    dist = repo / "dist" / "v1"
    assert sorted(p.name for p in dist.iterdir()) == [
        "SHA256SUMS",
        "data-manifest.tsv",
        "generators.txt",
        "source.tar",
        "submission.pdf",
        "supplementary.pdf",
    ]
    sums = dict(
        reversed(line.split("  ", 1)) for line in (dist / "SHA256SUMS").read_text().splitlines()
    )
    assert set(sums) == {p.name for p in dist.iterdir()} - {"SHA256SUMS"}
    assert all(sha256(dist / name) == digest for name, digest in sums.items())

    manifest = (dist / "data-manifest.tsv").read_text().splitlines()
    raw = repo / "projects" / "s1" / "data" / "raw"
    assert manifest[0] == "path\tsize\tsha256"
    assert manifest[1:] == [
        f"projects/s1/data/raw/.gitkeep\t0\t{sha256(raw / '.gitkeep')}",
        f"projects/s1/data/raw/legacy/old/m.png\t3\t{sha256(raw / 'legacy' / 'old' / 'm.png')}",
        f"projects/s1/data/raw/obs.csv\t8\t{sha256(raw / 'obs.csv')}",
    ]
    # Upstream first; a completed experiment is rerun only with --overwrite.
    run = "docker compose exec research-template uv run python"
    assert (dist / "generators.txt").read_text() == (
        f"{run} projects/s1/experiments/001_fit/run.py --overwrite\n"
        f"{run} projects/s1/scripts/make_map.py\n"
    )
    with tarfile.open(dist / "source.tar") as tar:
        names = set(tar.getnames())
    assert "v1/draft/main.tex" in names
    assert "v1/projects/s1/data/raw/obs.csv" not in names  # raw data is not in Git
    assert git(repo, "status", "--porcelain") == ""  # dist/ is git-ignored
    assert "dist/v1" in capsys.readouterr().out


def dirty_tracked_file(repo):
    (repo / "draft" / "main.tex").write_text("changed\n")


def untracked_file(repo):
    (repo / "notes.txt").write_text("draft notes\n")


def missing_tag(repo):
    git(repo, "tag", "-d", "v1")


def tag_behind_head(repo):
    (repo / "draft" / "supplementary.tex").write_text("\\documentclass{report}\n")
    git(repo, "commit", "-q", "-am", "later edit")


def missing_pdf(repo):
    (repo / "draft" / "supplementary.pdf").unlink()


def existing_archive(repo):
    (repo / "dist" / "v1").mkdir(parents=True)


@pytest.mark.parametrize(
    "damage",
    [
        dirty_tracked_file,
        untracked_file,
        missing_tag,
        tag_behind_head,
        missing_pdf,
        existing_archive,
    ],
)
def test_refuses_and_writes_nothing(archive_thesis, repo, damage, capsys):
    damage(repo)
    had_dist = (repo / "dist").exists()
    before = sorted(p.relative_to(repo) for p in (repo / "dist").rglob("*")) if had_dist else []

    assert archive_thesis.main(["--tag", "v1"], root=repo) == 1

    after = sorted(p.relative_to(repo) for p in (repo / "dist").rglob("*")) if had_dist else []
    assert (repo / "dist").exists() == had_dist and after == before
    assert "nothing was archived" in capsys.readouterr().err


def test_refuses_an_invalid_tag_name(archive_thesis, repo, capsys):
    assert archive_thesis.main(["--tag", "bad..name"], root=repo) == 1
    assert not (repo / "dist").exists()
    capsys.readouterr()
