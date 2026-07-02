"""Tests for src/utils/tables.py using a throwaway fake config."""

from types import SimpleNamespace

import pandas as pd
import pytest


@pytest.fixture()
def fake_cfg(tmp_path, study_root):
    return SimpleNamespace(
        TABLE_DIR=tmp_path / "tables",
        STUDY_ROOT=study_root,
        REPO_ROOT=study_root.parents[1],
    )


def test_write_latex_table_emits_booktabs_with_escaping(tables_mod, fake_cfg):
    df = pd.DataFrame({"site_name": ["A_1", "B%"], "value": [1.23456, 2.0]})

    out = tables_mod.write_latex_table(
        df, "example-summary", fake_cfg, caption="Example summary", label="tab:example"
    )

    text = out.read_text()
    assert out == fake_cfg.TABLE_DIR / "example-summary.tex"
    assert "\\toprule" in text and "\\midrule" in text and "\\bottomrule" in text
    assert r"site\_name" in text and r"A\_1" in text and r"B\%" in text
    assert "\\caption{Example summary}" in text and "\\label{tab:example}" in text
    assert "1.23" in text  # float_format applied ({:.3g})
    assert "do not edit by hand" in text


def test_label_defaults_to_table_stem_when_caption_given(tables_mod, fake_cfg):
    df = pd.DataFrame({"x": [1]})

    out = tables_mod.write_latex_table(df, "example-default-label", fake_cfg, caption="C")

    assert "\\label{tab:example-default-label}" in out.read_text()


def test_bare_tabular_without_caption(tables_mod, fake_cfg):
    df = pd.DataFrame({"x": [1]})

    text = tables_mod.write_latex_table(df, "example-bare", fake_cfg).read_text()

    assert "\\begin{tabular}" in text
    assert "\\begin{table}" not in text and "\\caption" not in text


def test_rejects_directories_and_extensions(tables_mod, fake_cfg):
    df = pd.DataFrame({"x": [1]})
    with pytest.raises(AssertionError):
        tables_mod.write_latex_table(df, "sub/example", fake_cfg)
    with pytest.raises(AssertionError):
        tables_mod.write_latex_table(df, "example.tex", fake_cfg)
