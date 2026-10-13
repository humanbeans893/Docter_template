"""Tests for src/utils/figures.py using a throwaway fake config."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")  # headless backend; must precede pyplot import

import matplotlib.pyplot as plt
import pytest

CORE_KEYS = {
    "artifact",
    "kind",
    "study",
    "script",
    "experiment",
    "created",
    "git_commit",
    "git_dirty",
    "files",
}


@pytest.fixture()
def fake_cfg(tmp_path, study_root):
    return SimpleNamespace(
        VISUALIZATION={"dpi": 72, "format": "png", "font": {"family": "DejaVu Sans", "size": 10}},
        FIGURE_DIR=tmp_path / "figures",
        STUDY_ROOT=study_root,
        REPO_ROOT=study_root.parents[1],
    )


def line_figure():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    return fig


def sidecar(cfg, name):
    return json.loads((cfg.FIGURE_DIR / f"{name}.provenance.json").read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_save_figure_writes_png_and_provenance_sidecar(figures_mod, fake_cfg):
    written = figures_mod.save_figure(line_figure(), "example-line", fake_cfg)

    assert written == [fake_cfg.FIGURE_DIR / "example-line.png"]
    assert written[0].exists()
    provenance = sidecar(fake_cfg, "example-line")
    assert set(provenance) == CORE_KEYS
    assert provenance["artifact"] == "example-line"
    assert provenance["kind"] == "figure"
    assert provenance["study"] == fake_cfg.STUDY_ROOT.name
    assert provenance["experiment"] is None  # the test runner is not an experiment
    assert provenance["files"] == {"example-line.png": sha256(written[0])}


def test_save_figure_respects_explicit_formats(figures_mod, fake_cfg):
    written = figures_mod.save_figure(
        line_figure(), "example-both", fake_cfg, formats=["png", "pdf"]
    )

    assert [p.suffix for p in written] == [".png", ".pdf"]
    assert all(p.exists() for p in written)
    assert set(sidecar(fake_cfg, "example-both")["files"]) == {
        "example-both.png",
        "example-both.pdf",
    }


def test_save_figure_merges_optional_provenance(figures_mod, fake_cfg):
    source = {"path": "projects/x/data/raw/legacy/a/metrics.csv", "sha256": "0" * 64}
    figures_mod.save_figure(
        line_figure(),
        "example-r2",
        fake_cfg,
        provenance={"reproducibility": "R2", "sources": [source], "note": "redrawn"},
    )

    provenance = sidecar(fake_cfg, "example-r2")
    assert provenance["reproducibility"] == "R2"
    assert provenance["sources"] == [source]
    assert provenance["note"] == "redrawn"


@pytest.mark.parametrize(
    "provenance",
    [
        {"script": "spoofed.py"},
        {"files": {}},
        {"run": {"seed": 1}},
        {"reproducibility": "R4"},
        {"sources": [{"path": "a.csv"}]},
        {"sources": [{"path": "a.csv", "sha256": "xyz"}]},
        {"note": object()},
    ],
)
def test_save_figure_rejects_bad_provenance_before_writing(figures_mod, fake_cfg, provenance):
    fig = line_figure()
    try:
        with pytest.raises(AssertionError):
            figures_mod.save_figure(fig, "example-bad", fake_cfg, provenance=provenance)
    finally:
        plt.close(fig)
    assert not (fake_cfg.FIGURE_DIR / "example-bad.png").exists()


def test_save_figure_rejects_directories_and_extensions(figures_mod, fake_cfg):
    fig, _ax = plt.subplots()
    try:
        with pytest.raises(AssertionError):
            figures_mod.save_figure(fig, "sub/example", fake_cfg)
        with pytest.raises(AssertionError):
            figures_mod.save_figure(fig, "example.png", fake_cfg)
        with pytest.raises(AssertionError):
            figures_mod.save_figure(fig, "example", fake_cfg, formats=[".png"])
    finally:
        plt.close(fig)


def test_save_figure_removes_stale_siblings(figures_mod, fake_cfg, capsys):
    figures_mod.save_figure(line_figure(), "example-switch", fake_cfg, formats=["pdf"])
    (fake_cfg.FIGURE_DIR / "example-switch.EPS").write_text("old")
    (fake_cfg.FIGURE_DIR / "example-switch-other.pdf").write_text("unrelated")

    figures_mod.save_figure(line_figure(), "example-switch", fake_cfg, formats=["png"])

    names = sorted(p.name for p in fake_cfg.FIGURE_DIR.iterdir())
    assert names == [
        "example-switch-other.pdf",
        "example-switch.png",
        "example-switch.provenance.json",
    ]
    err = capsys.readouterr().err
    assert "removed stale example-switch.pdf" in err
    assert "removed stale example-switch.EPS" in err


def test_save_figure_warns_about_large_files(figures_mod, fake_cfg, monkeypatch, capsys):
    monkeypatch.setattr(figures_mod, "MAX_FILE_BYTES", 10)

    figures_mod.save_figure(line_figure(), "example-large", fake_cfg)

    assert "example-large.png is" in capsys.readouterr().err


def test_experiment_and_script_come_from_the_run(
    figures_mod, experiment_mod, tmp_path, monkeypatch
):
    monkeypatch.delenv(experiment_mod.RUN_ENV, raising=False)
    study = tmp_path / "projects" / "demo"
    script = study / "experiments" / "007_demo_run" / "run.py"
    script.parent.mkdir(parents=True)
    cfg = SimpleNamespace(
        VISUALIZATION={"dpi": 72, "format": "png", "font": {"family": "DejaVu Sans", "size": 10}},
        FIGURE_DIR=study / "result" / "figures",
        TABLE_DIR=study / "result" / "tables",
        STUDY_ROOT=study,
        REPO_ROOT=tmp_path,
    )
    params = SimpleNamespace(SEED=1, PARAMS={})

    with experiment_mod.start(str(script), params, [], cfg=cfg):
        figures_mod.save_figure(line_figure(), "demo-overview", cfg)

    provenance = sidecar(cfg, "demo-overview")
    assert provenance["experiment"] == "007_demo_run"
    assert provenance["script"] == "projects/demo/experiments/007_demo_run/run.py"
    assert set(provenance) == CORE_KEYS | {"run"}


def test_scripts_are_not_experiments_and_experiments_need_the_harness(
    figures_mod, experiment_mod, tmp_path, monkeypatch
):
    monkeypatch.delenv(experiment_mod.RUN_ENV, raising=False)
    study = tmp_path / "projects" / "demo"
    cfg = SimpleNamespace(
        VISUALIZATION={"dpi": 72, "format": "png", "font": {"family": "DejaVu Sans", "size": 10}},
        FIGURE_DIR=study / "result" / "figures",
        STUDY_ROOT=study,
        REPO_ROOT=tmp_path,
    )
    monkeypatch.setattr(sys, "argv", [str(study / "scripts" / "promote.py")])
    assert figures_mod._running_script(cfg) == ("projects/demo/scripts/promote.py", None)
    for name in ("_template", "007_demo_run"):
        monkeypatch.setattr(sys, "argv", [str(study / "experiments" / name / "run.py")])
        with pytest.raises(AssertionError, match=r"outside experiment\.start\(\)"):
            figures_mod._running_script(cfg)
        fig = line_figure()
        try:
            with pytest.raises(AssertionError, match=r"outside experiment\.start\(\)"):
                figures_mod.save_figure(fig, "demo-overview", cfg)
        finally:
            plt.close(fig)
    assert not cfg.FIGURE_DIR.exists()


def test_import_figure_copies_as_r3_with_source_hash(figures_mod, fake_cfg, tmp_path):
    source = tmp_path / "old" / "Map.PNG"
    source.parent.mkdir()
    source.write_bytes(b"\x89PNG fake image bytes")

    out = figures_mod.import_figure(
        source, "example-old-map", fake_cfg, note="raw data lost", license="own work"
    )

    assert out == fake_cfg.FIGURE_DIR / "example-old-map.png"
    assert out.read_bytes() == source.read_bytes()
    provenance = sidecar(fake_cfg, "example-old-map")
    assert provenance["kind"] == "figure"
    assert provenance["reproducibility"] == "R3"
    assert provenance["note"] == "raw data lost"
    assert provenance["license"] == "own work"
    assert provenance["sources"] == [{"path": str(source.resolve()), "sha256": sha256(source)}]
    assert provenance["files"] == {"example-old-map.png": sha256(out)}


def test_import_figure_replaces_a_stale_sibling(figures_mod, fake_cfg, tmp_path):
    figures_mod.save_figure(line_figure(), "example-swap", fake_cfg, formats=["pdf"])
    source = tmp_path / "scan.jpg"
    source.write_bytes(b"jpeg bytes")

    figures_mod.import_figure(source, "example-swap", fake_cfg, note="scan", license="own work")

    assert not (fake_cfg.FIGURE_DIR / "example-swap.pdf").exists()
    assert (fake_cfg.FIGURE_DIR / "example-swap.jpg").exists()


def test_import_figure_converts_tiff_on_request(figures_mod, fake_cfg, tmp_path):
    from PIL import Image

    source = tmp_path / "scope.tif"
    Image.new("RGB", (4, 3), (200, 10, 10)).save(source)
    with pytest.raises(AssertionError, match="convert_to_png"):
        figures_mod.import_figure(source, "example-scope", fake_cfg, note="n", license="l")

    out = figures_mod.import_figure(
        source, "example-scope", fake_cfg, note="n", license="l", convert_to_png=True
    )

    assert out.suffix == ".png"
    with Image.open(out) as image:
        assert image.size == (4, 3)
    assert sidecar(fake_cfg, "example-scope")["converted_from"] == ".tif"


def test_import_figure_rejects_bad_input(figures_mod, fake_cfg, tmp_path, monkeypatch):
    good = tmp_path / "fig.png"
    good.write_bytes(b"png")
    text = tmp_path / "fig.txt"
    text.write_text("not an image")
    ok = {"note": "why", "license": "own work"}

    with pytest.raises(AssertionError, match="does not exist"):
        figures_mod.import_figure(tmp_path / "missing.png", "example-x", fake_cfg, **ok)
    with pytest.raises(AssertionError, match="must be a file"):
        figures_mod.import_figure(tmp_path, "example-x", fake_cfg, **ok)
    with pytest.raises(AssertionError, match="unsupported"):
        figures_mod.import_figure(text, "example-x", fake_cfg, **ok)
    with pytest.raises(AssertionError):
        figures_mod.import_figure(good, "example-x.png", fake_cfg, **ok)
    with pytest.raises(AssertionError, match="note"):
        figures_mod.import_figure(good, "example-x", fake_cfg, note=" ", license="own work")
    with pytest.raises(AssertionError, match="license"):
        figures_mod.import_figure(good, "example-x", fake_cfg, note="why", license="")
    with pytest.raises(AssertionError, match="set by the helper"):
        figures_mod.import_figure(
            good, "example-x", fake_cfg, provenance={"reproducibility": "R2"}, **ok
        )
    monkeypatch.setattr(figures_mod, "MAX_FILE_BYTES", 2)
    with pytest.raises(AssertionError, match="1 MB"):
        figures_mod.import_figure(good, "example-x", fake_cfg, **ok)
    assert not fake_cfg.FIGURE_DIR.exists() or not any(fake_cfg.FIGURE_DIR.iterdir())


def test_apply_visualization_defaults_sets_rcparams(figures_mod, fake_cfg):
    figures_mod.apply_visualization_defaults(fake_cfg)
    assert matplotlib.rcParams["savefig.dpi"] == 72
    assert matplotlib.rcParams["font.size"] == 10


def test_save_figure_sources_records_the_files_it_was_drawn_from(figures_mod, tmp_path):
    # A promotion script in scripts/ names the CSV it read, so make check can follow it
    # back to the experiment that wrote it.
    study = tmp_path / "projects" / "demo"
    csv_path = study / "result" / "tables" / "demo-fit.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("x,y\n1,2\n")
    cfg = SimpleNamespace(
        VISUALIZATION={"dpi": 72, "format": "png", "font": {"family": "DejaVu Sans", "size": 10}},
        FIGURE_DIR=study / "result" / "figures",
        STUDY_ROOT=study,
        REPO_ROOT=tmp_path,
    )

    figures_mod.save_figure(line_figure(), "demo-fit", cfg, sources=[csv_path])

    assert sidecar(cfg, "demo-fit")["sources"] == [
        {"path": "projects/demo/result/tables/demo-fit.csv", "sha256": sha256(csv_path)}
    ]
    fig = line_figure()
    try:
        with pytest.raises(AssertionError, match="does not exist"):
            figures_mod.save_figure(fig, "demo-missing", cfg, sources=[tmp_path / "gone.csv"])
    finally:
        plt.close(fig)
    assert not (cfg.FIGURE_DIR / "demo-missing.png").exists()


def test_figure_files_carry_no_time_and_no_commit(figures_mod, fake_cfg, monkeypatch):
    from PIL import Image

    def save(commit):
        monkeypatch.setattr(
            figures_mod, "_git_state", lambda cfg: {"git_commit": commit, "git_dirty": False}
        )
        written = figures_mod.save_figure(
            line_figure(), "example-same", fake_cfg, formats=["png", "pdf", "svg", "eps"]
        )
        return {path.suffix: path.read_bytes() for path in written}

    first = save("aaaaaaa")
    second = save("fffffff")  # another commit (and maybe another second)

    assert second == first
    provenance = sidecar(fake_cfg, "example-same")
    assert provenance["git_commit"] == "fffffff"  # the commit lives in the sidecar only
    with Image.open(fake_cfg.FIGURE_DIR / "example-same.png") as image:
        assert image.text == {"Software": f"{provenance['study']}: {provenance['script']}"}
    assert b"/CreationDate" not in first[".pdf"]
    assert b"<dc:date>" not in first[".svg"]
    assert b"%%CreationDate: Thu Jan 01 00:00:00 1970" in first[".eps"]


def test_import_figure_names_the_verified_original_of_a_derived_copy(
    figures_mod, fake_cfg, tmp_path
):
    # A resized image or one frame of an animation is written under out/ first; the sidecar
    # must still name the original that the manifest verified.
    original = {"path": "projects/demo/data/raw/legacy/old/animation.gif", "sha256": "b" * 64}
    frame = tmp_path / "out" / "frame5.png"
    frame.parent.mkdir()
    frame.write_bytes(b"\x89PNG frame five")
    ok = {"note": "frame 5 of animation.gif, written by run.py", "license": "own work"}

    figures_mod.import_figure(frame, "example-frame", fake_cfg, sources=[original], **ok)
    provenance = sidecar(fake_cfg, "example-frame")
    assert provenance["sources"] == [original]
    assert provenance["copied"] == {"path": str(frame.resolve()), "sha256": sha256(frame)}

    figures_mod.import_figure(
        frame, "example-frame2", fake_cfg, provenance={"sources": [original]}, **ok
    )
    assert sidecar(fake_cfg, "example-frame2")["sources"] == [original]

    with pytest.raises(AssertionError, match="sha256"):
        figures_mod.import_figure(
            frame, "example-bad", fake_cfg, sources=[{"path": "a.gif", "sha256": "x"}], **ok
        )
    with pytest.raises(AssertionError, match="set by the helper"):
        figures_mod.import_figure(
            frame, "example-bad", fake_cfg, provenance={"copied": "spoofed"}, **ok
        )
    assert not (fake_cfg.FIGURE_DIR / "example-bad.png").exists()


GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *GIT_ID, *args], check=True, capture_output=True, text=True
    )
    return done.stdout


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_figures_are_credited_to_the_code_the_run_started_from(
    tmp_path, load_module_by_path, capsys
):
    repo = tmp_path
    for name, text in {
        ".gitignore": "__pycache__/\n*.py[cod]\n",  # as in the real repository
        "draft/chapters/ch.tex": "text\n",
        "projects/demo/src/analysis.py": "x = 1\n",
        "projects/other/result/figures/other-map.png": "old\n",
    }.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    target = repo / "projects" / "demo" / "src" / "utils" / "figures.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    for name in ("figures.py", "experiment.py"):  # figures.py loads experiment.py beside it
        source = Path(__file__).resolve().parents[1] / "src" / "utils" / name
        shutil.copyfile(source, target.with_name(name))
    git(repo, "init", "-q")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "initial")
    start = git(repo, "rev-parse", "--short", "HEAD").strip()
    module = load_module_by_path(target, f"{tmp_path.name}_figures_run")  # the run starts
    study = repo / "projects" / "demo"
    cfg = SimpleNamespace(
        VISUALIZATION={"dpi": 72, "format": "png", "font": {"family": "DejaVu Sans", "size": 10}},
        FIGURE_DIR=study / "result" / "figures",
        STUDY_ROOT=study,
        REPO_ROOT=repo,
    )

    # Prose and another study's regenerated figure, committed or not, change nothing.
    (repo / "projects" / "other" / "result" / "figures" / "other-map.png").write_text("new\n")
    (repo / "draft" / "chapters" / "ch.tex").write_text("edited\n")
    git(repo, "commit", "-qam", "prose and other results")
    (repo / "draft" / "chapters" / "ch.tex").write_text("edited again\n")
    module.save_figure(line_figure(), "demo-before", cfg)
    assert (
        sidecar(cfg, "demo-before")["git_commit"],
        sidecar(cfg, "demo-before")["git_dirty"],
    ) == (
        start,
        False,
    )

    (study / "src" / "analysis.py").write_text("x = 2\n")
    git(repo, "commit", "-qam", "code changed during the run")
    module.save_figure(line_figure(), "demo-after", cfg)
    assert (sidecar(cfg, "demo-after")["git_commit"], sidecar(cfg, "demo-after")["git_dirty"]) == (
        start,
        True,
    )
    assert "the code changed during the run" in capsys.readouterr().err
