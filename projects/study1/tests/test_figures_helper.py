"""Tests for src/utils/figures.py using a throwaway fake config."""

import json
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")  # headless backend; must precede pyplot import

import matplotlib.pyplot as plt
import pytest


@pytest.fixture()
def fake_cfg(tmp_path, study_root):
    return SimpleNamespace(
        VISUALIZATION={"dpi": 72, "format": "png", "font": {"family": "DejaVu Sans", "size": 10}},
        FIGURE_DIR=tmp_path / "figures",
        STUDY_ROOT=study_root,
        REPO_ROOT=study_root.parents[1],
    )


def test_save_figure_writes_png_and_provenance_sidecar(figures_mod, fake_cfg):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])

    written = figures_mod.save_figure(fig, "example-line", fake_cfg)

    assert written == [fake_cfg.FIGURE_DIR / "example-line.png"]
    assert written[0].exists()
    sidecar = fake_cfg.FIGURE_DIR / "example-line.provenance.json"
    provenance = json.loads(sidecar.read_text())
    assert provenance["figure"] == "example-line"
    assert {"study", "script", "created", "git_commit", "git_dirty"} <= set(provenance)


def test_save_figure_respects_explicit_formats(figures_mod, fake_cfg):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 0])

    written = figures_mod.save_figure(fig, "example-both", fake_cfg, formats=["png", "pdf"])

    assert [p.suffix for p in written] == [".png", ".pdf"]
    assert all(p.exists() for p in written)


def test_save_figure_rejects_directories_and_extensions(figures_mod, fake_cfg):
    fig, _ax = plt.subplots()
    try:
        with pytest.raises(AssertionError):
            figures_mod.save_figure(fig, "sub/example", fake_cfg)
        with pytest.raises(AssertionError):
            figures_mod.save_figure(fig, "example.png", fake_cfg)
    finally:
        plt.close(fig)


def test_apply_visualization_defaults_sets_rcparams(figures_mod, fake_cfg):
    figures_mod.apply_visualization_defaults(fake_cfg)
    assert matplotlib.rcParams["savefig.dpi"] == 72
    assert matplotlib.rcParams["font.size"] == 10
