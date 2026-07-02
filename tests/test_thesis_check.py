"""Self-verification of tools/thesis_check.py.

(a) The pristine template manuscript must produce zero errors.
(b) A synthetic broken draft must trigger each check, proving the checker
    actually fires when agents rely on it as a quality gate.
"""

import pytest


@pytest.fixture(scope="module")
def thesis_check(repo_root, load_module_by_path):
    return load_module_by_path(repo_root / "tools" / "thesis_check.py", "thesis_check_under_test")


def codes(findings, severity=None):
    return {f.code for f in findings if severity is None or f.severity == severity}


def test_pristine_template_has_no_errors(thesis_check, repo_root):
    findings = thesis_check.run_checks(repo_root / "draft", with_log=False)

    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"template draft/ should be error-free, got: {errors}"


def test_synthetic_broken_draft_triggers_each_check(thesis_check, tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "orphan-figure.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "reference.bib").write_text(
        "@article{used2020key, title={T}, author={A}, year={2020}}\n"
        "@article{unused2021key, title={U}, author={B}, year={2021}}\n"
        "@article{used2020key, title={Dup}, author={C}, year={2020}}\n"
    )
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\graphicspath{{figures/}}\n"
        "\\begin{document}\n"
        "\\section{One}\\label{sec:one}\n"
        "\\section{Dup}\\label{sec:one}\n"
        "\\label{badlabel}\n"
        "\\ref{sec:missing}\n"
        "\\cite{used2020key} \\cite{ghost2019key}\n"
        "\\includegraphics{missing-figure}\n"
        "\\begin{figure}\\includegraphics{orphan-figure}\\label{fig:never-referenced}\\end{figure}\n"
        "% TODO: rewrite this section\n"
        "\\todo{check the units}\n"
        "% \\input{disabled-file-must-not-be-followed}\n"
        "\\bibliography{reference}\n"
        "\\end{document}\n"
    )

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    assert "E1" in codes(findings, "error")  # \ref{sec:missing}
    assert "E2" in codes(findings, "error")  # duplicate sec:one
    assert "E3" in codes(findings, "error")  # \cite{ghost2019key}
    assert "E4" in codes(findings, "error")  # missing-figure
    assert "E5" not in codes(findings, "error")  # commented \input not followed
    assert "W1" in codes(findings, "warning")  # duplicate bib key
    assert "W2" in codes(findings, "warning")  # unused2021key
    assert "W4" in codes(findings, "warning")  # fig:never-referenced
    assert "W5" in codes(findings, "warning")  # badlabel prefix
    todos = [f for f in findings if f.code == "I1"]
    assert len(todos) == 2  # one \todo + one % TODO


def test_missing_include_is_reported(thesis_check, tmp_path):
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n\\input{does-not-exist}\n\\begin{document}\\end{document}\n"
    )

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    assert "E5" in codes(findings, "error")


def test_duplicate_figure_basenames_across_dirs(thesis_check, tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "figures" / "shadow.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "other" / "shadow.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\graphicspath{{figures/}{other/}}\n"
        "\\begin{document}\\includegraphics{shadow}\\end{document}\n"
    )

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    assert "W6" in codes(findings, "warning")
    assert codes(findings, "error") == set()
