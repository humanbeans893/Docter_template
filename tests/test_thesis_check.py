"""Self-verification of tools/thesis_check.py.

(a) The pristine template manuscript must produce zero errors in every document.
(b) Synthetic drafts must trigger each check, proving the checker actually fires
    when agents rely on it as a quality gate.
"""

import ast
import hashlib
import json
import re
import shlex
import subprocess
import sys

import pytest


@pytest.fixture(scope="module")
def thesis_check(repo_root, load_module_by_path):
    return load_module_by_path(repo_root / "tools" / "thesis_check.py", "thesis_check_under_test")


def codes(findings, severity=None):
    return {f.code for f in findings if severity is None or f.severity == severity}


def of(findings, code):
    return [f for f in findings if f.code == code]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def sidecar(artifact, **overrides):
    """A provenance sidecar as the study helpers write it, for ``artifact``."""
    data = {
        "artifact": artifact.stem,
        "kind": "figure" if artifact.suffix in {".png", ".pdf"} else "values",
        "study": "s1",
        "script": "projects/s1/scripts/make.py",
        "experiment": None,
        "created": "2026-01-01T00:00:00+00:00",
        "git_commit": "abc1234",
        "git_dirty": False,
        "files": {artifact.name: sha256(artifact)},
    }
    data.update(overrides)
    write(artifact.with_name(f"{artifact.stem}.provenance.json"), json.dumps(data))
    return data


@pytest.fixture()
def repo(tmp_path):
    """A repo-shaped tmp tree: draft/ plus projects/s1/ with result/ and experiments/ indexes.

    The index holds every status word and two words that are not status words (置換 and
    取り込み済, earlier vocabulary of this repository), which W14 must flag.
    """
    (tmp_path / "draft" / "figures").mkdir(parents=True)
    for area in ("figures", "tables"):
        (tmp_path / "projects" / "s1" / "result" / area).mkdir(parents=True)
    write(
        tmp_path / "projects" / "s1" / "experiments" / "EXP_SUMMARY.md",
        "# index\n\n| # | slug | 一行で | 状態 | 論文 | 由来 |\n|---|---|---|---|---|---|\n"
        "| 001 | good_run | ok | 完了 | ch:s1 | 新規 |\n"
        "| 002 | bad_run | wrong | 撤回(2026-01-02、→ 004_redo) | — | 新規 |\n"
        "| 004 | redo | ok | 完了 | ch:s1 | 新規 |\n"
        "| 005 | bold_bad | wrong | **撤回(2026-01-03)** | — | 新規 |\n"
        "| 006 | replaced | ok | 置き換え(2026-01-04、→ 004_redo) | — | 新規 |\n"
        "| 007 | old_word | ok | 置換(→004) | — | 新規 |\n"
        "| 008 | open | (実行前) | 進行中 | — | 新規 |\n"
        "| 009 | fixed | ok | 訂正(2026-01-05) | ch:s1 | 新規 |\n"
        "| 012 | past_import | ok | 取り込み済 | — | 取り込み(R2) |\n",
    )
    write(
        tmp_path / "projects" / "s1" / "experiments" / "EXP_ARCHIVE.md",
        "| # | slug | 一行で | 状態 | 論文 | 由来 |\n|---|---|---|---|---|---|\n"
        "| 003 | old_run | ok | 完了 | — | 新規 |\n"
        "| 010 | archived_bad | x | 撤回(2026-01-06) | — | 新規 |\n",
    )
    return tmp_path


def draft_main(repo, body, preamble=""):
    """draft/main.tex reading figures from draft/figures/ and the study's result/figures/."""
    return write(
        repo / "draft" / "main.tex",
        "\\documentclass{article}\n"
        "\\graphicspath{{figures/}{../projects/s1/result/figures/}}\n"
        f"{preamble}"
        "\\begin{document}\n"
        f"{body}"
        "\\end{document}\n",
    )


def figure(repo, name, data=b"\x89PNG\r\n"):
    path = repo / "projects" / "s1" / "result" / "figures" / name
    path.write_bytes(data)
    return path


# --- Pristine template ------------------------------------------------------------------------


@pytest.mark.parametrize("main_name", ["main.tex", "review.tex", "supplementary.tex"])
def test_pristine_template_has_no_errors(thesis_check, repo_root, main_name):
    findings = thesis_check.run_checks(repo_root / "draft", main_name=main_name, with_log=False)

    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"template draft/{main_name} should be error-free, got: {errors}"


def test_pristine_template_all_documents_have_no_errors(thesis_check, repo_root):
    findings = thesis_check.run_all(repo_root / "draft", with_log=False)

    assert [f for f in findings if f.severity == "error"] == []


# --- Existing checks --------------------------------------------------------------------------


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


def test_cite_in_a_document_without_bibliography_says_so(thesis_check, tmp_path):
    """E3 names the missing \\bibliography instead of blaming the .bib file."""
    (tmp_path / "reference.bib").write_text("@article{a2020, title={A}, year={2020}}\n")
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\citet{a2020}\n\\end{document}\n"
    )

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    assert [f.message for f in of(findings, "E3")] == [
        "cited key 'a2020' but this document has no \\bibliography"
    ]


def test_missing_include_is_reported(thesis_check, tmp_path):
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n\\input{does-not-exist}\n\\begin{document}\\end{document}\n"
    )

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    assert "E5" in codes(findings, "error")


def test_commands_wrapped_over_lines_are_matched(thesis_check, repo):
    write(
        repo / "draft" / "reference.bib",
        "@article{a2020, title={A}, year={2020}}\n@article{b2021, title={B}, year={2021}}\n",
    )
    sidecar(figure(repo, "s1-wrapped.png"), experiment="002_bad_run")
    draft_main(
        repo,
        "\\citep[see][p.~3]{a2020,\n  b2021, ghost2019} and \\cref{fig:s1-wrapped,%\n"
        "  fig:missing}.\n"
        "\\begin{figure}\n\\includegraphics[width=0.8\\linewidth,\n  trim=0 0 0 0, clip]\n"
        "  {s1-wrapped}\n\\label{fig:s1-wrapped}\n\\end{figure}\n"
        "\\bibliography{reference}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert codes(findings) & {"W2", "W3", "W4"} == set(), findings
    # Reported at the line where the command starts.
    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "E3")] == ["main.tex:4"]
    assert "ghost2019" in of(findings, "E3")[0].message
    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "E1")] == ["main.tex:5"]
    # The wrapped figure still gets its provenance checks.
    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "W14")] == ["s1-wrapped.png"]


@pytest.mark.parametrize(
    ("source", "keys"),
    [
        ("\\citep[see][p.~5]{b,c}", ["b,c"]),
        ("\\Citet{a}", ["a"]),
        ("\\citeauthor*{a}", ["a"]),
        ("\\nocite{*}", ["*"]),
        ("\\citestyle{plainnat}", []),
        ("\\setcitestyle{square,numbers}", []),
        ("\\citetext{see also the manual}", []),
        ("\\DeclareCiteCommand{\\cite}{a}{b}{c}", []),
    ],
)
def test_only_citation_commands_give_keys(thesis_check, source, keys):
    assert [m.group(1) for m in thesis_check.RE_CITE.finditer(source)] == keys


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
    write(tmp_path / "figures" / "README.md", "| ファイル |\n|---|\n| `shadow.png` |\n")

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    assert "W6" in codes(findings, "warning")
    assert codes(findings, "error") == set()


def test_submission_mode_rejects_placeholders_and_todos(thesis_check, tmp_path):
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\input{thesis-config}\n"
        "\\begin{document}\\todo{write abstract}\\end{document}\n"
    )
    required = sorted(thesis_check.REQUIRED_METADATA)
    (tmp_path / "thesis-config.tex").write_text(
        "\n".join(f"\\newcommand{{\\{name}}}{{Dissertation Title}}" for name in required)
    )

    draft_findings = thesis_check.run_checks(tmp_path, with_log=False)
    submission_findings = thesis_check.run_checks(tmp_path, with_log=False, submission=True)

    assert "W8" in codes(draft_findings, "warning")
    assert "I1" in codes(draft_findings, "info")
    assert "E6" in codes(submission_findings, "error")
    assert "E7" in codes(submission_findings, "error")


def test_metadata_may_be_wrapped_over_lines(thesis_check, tmp_path):
    required = sorted(thesis_check.REQUIRED_METADATA - {"ThesisTitleEN", "ThesisTitleJA"})
    write(
        tmp_path / "thesis-config.tex",
        "% Metadata\n"
        "\\newcommand{\\ThesisTitleEN}{%\n  A Long Title About\n  Coastal \\textit{Sediment}}\n"
        "\\newcommand{\\ThesisTitleJA}{%\n  博士論文題目}\n"
        + "".join(f"\\newcommand{{\\{name}}}{{Set}}\n" for name in required[1:]),
    )
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\input{thesis-config}\n\\begin{document}\\end{document}\n",
    )

    e6 = {
        f.message.split()[0]: f.location.rsplit("/", 1)[-1]
        for f in thesis_check.run_checks(tmp_path, with_log=False, submission=True)
        if f.code == "E6"
    }

    # The wrapped real title is read whole; the wrapped placeholder is still caught where it
    # is defined; a missing definition points at thesis-config.tex, where it belongs.
    assert e6 == {
        "\\ThesisTitleJA": "thesis-config.tex:5",
        f"\\{required[0]}": "thesis-config.tex:1",
    }


# --- Build log --------------------------------------------------------------------------------


def test_bare_ref_and_duplicate_anchor_are_reported(thesis_check, tmp_path):
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\begin{document}\\section{A}\\label{sec:a}\\ref{sec:a}\\end{document}\n"
    )
    write(
        tmp_path / "build" / "main" / "main.log",
        "warning  (pdf backend): ignoring duplicate destination with the name 'page.1'\n",
    )

    findings = thesis_check.run_checks(tmp_path)

    assert "W7" in codes(findings, "warning")
    assert "W9" in codes(findings, "warning")


def test_undefined_citations_in_the_log_are_reported(thesis_check, tmp_path):
    """natbib (preamble.tex) words the warning differently from the LaTeX kernel."""
    write(tmp_path / "main.tex", "\\documentclass{article}\n\\begin{document}\\end{document}\n")
    write(
        tmp_path / "build" / "main" / "main.log",
        "Package natbib Warning: Citation `doe2021missing' on page 4 undefined on input line 66.\n"
        "LaTeX Warning: Citation `roe2019' on page 5 undefined on input line 70.\n"
        "Package natbib Warning: There were undefined citations.\n",
    )

    messages = sorted(f.message for f in of(thesis_check.run_checks(tmp_path), "I2"))

    assert messages == [
        "undefined citation 'doe2021missing' in last build",
        "undefined citation 'roe2019' in last build",
    ]


def test_log_is_read_from_the_job_build_directory(thesis_check, tmp_path):
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\\end{document}\n"
    )
    (tmp_path / "review.tex").write_text("\\input{main.tex}\n")
    (tmp_path / "main.log").write_text("! Stale log in draft/ must be ignored.\n")
    write(
        tmp_path / "build" / "review" / "review.log",
        "./chapters/02-study1.tex:12: Undefined control sequence.\n"
        "Overfull \\hbox (1.0pt too wide) in paragraph at lines 3--4\n",
    )

    main_findings = thesis_check.run_checks(tmp_path)
    review_findings = thesis_check.run_checks(tmp_path, main_name="review.tex")

    missing = of(main_findings, "I2")
    assert len(missing) == 1 and "build/main/main.log" in missing[0].message
    assert "make pdf" in missing[0].message
    errors = [f for f in of(review_findings, "I2") if f.severity == "error"]
    assert len(errors) == 1
    assert errors[0].location.endswith("chapters/02-study1.tex:12")
    assert "Undefined control sequence" in errors[0].message
    assert "W10" in codes(review_findings, "warning")


# --- Graphics resolution and provenance -------------------------------------------------------


def test_graphics_resolution_is_extension_major(thesis_check, tmp_path):
    draft = tmp_path / "draft"
    (draft / "figures").mkdir(parents=True)
    (draft / "x.png").write_bytes(b"png")
    (draft / "figures" / "x.pdf").write_bytes(b"pdf")
    (draft / "figures" / "y.jpg").write_bytes(b"jpg")
    (draft / "figures" / "y.PNG").write_bytes(b"PNG")
    dirs = [draft, (draft / "figures").resolve()]

    assert thesis_check.resolve_graphic("x", dirs) == (draft / "figures" / "x.pdf").resolve()
    assert thesis_check.resolve_graphic("x.png", dirs) == (draft / "x.png").resolve()
    assert thesis_check.resolve_graphic("y", dirs) == (draft / "figures" / "y.jpg").resolve()
    assert thesis_check.resolve_graphic("z", dirs) is None


def test_generated_figure_without_or_with_stale_sidecar_is_w11(thesis_check, repo):
    figure(repo, "s1-nosidecar.png")
    good = figure(repo, "s1-good.png")
    sidecar(good)
    stale = figure(repo, "s1-stale.png")
    sidecar(stale)
    stale.write_bytes(b"edited by hand")
    draft_main(
        repo,
        "\\includegraphics{s1-nosidecar}\\includegraphics{s1-good}\\includegraphics{s1-stale}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    w11 = {f.location.rsplit("/", 1)[-1]: f.message for f in of(findings, "W11")}
    assert set(w11) == {"s1-nosidecar.png", "s1-stale.png"}
    assert "save_figure" in w11["s1-nosidecar.png"]
    assert "differs" in w11["s1-stale.png"]
    assert codes(findings, "error") == set()


def test_shadowed_png_is_not_the_included_figure(thesis_check, repo):
    """graphicx takes the .pdf, so the provenance check must look at the .pdf."""
    png = figure(repo, "s1-both.png")
    sidecar(png)
    figure(repo, "s1-both.pdf", b"%PDF-1.5 stale")
    draft_main(repo, "\\includegraphics{s1-both}\n")

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "W11")] == ["s1-both.pdf"]


def test_hand_made_figure_must_be_in_the_ledger(thesis_check, repo):
    figures = repo / "draft" / "figures"
    (figures / "listed.pdf").write_bytes(b"%PDF")
    (figures / "unlisted.png").write_bytes(b"png")
    write(
        figures / "README.md",
        "| ファイル | 内容 |\n|---|---|\n| `listed.pdf` | schematic |\n",
    )
    draft_main(repo, "\\includegraphics{listed}\\includegraphics{unlisted}\n")

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "W11")] == ["unlisted.png"]


def test_table_and_values_inputs_need_sidecars(thesis_check, repo):
    tables = repo / "projects" / "s1" / "result" / "tables"
    write(tables / "s1-summary.tex", "\\begin{tabular}{l}x\\end{tabular}\n")
    values = write(tables / "s1-main.tex", "% Generated\n\\defvalue{s1-main-n}{12}\n")
    sidecar(values, kind="values")
    write(repo / "draft" / "values.tex", "\\ThesisValues{../projects/s1/result/tables/s1-main}\n")
    draft_main(
        repo,
        "\\input{../projects/s1/result/tables/s1-summary}\n\\val{s1-main-n}\n",
        preamble="\\input{values}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "W11")] == ["s1-summary.tex"]
    assert "write_latex_table" in of(findings, "W11")[0].message
    assert codes(findings, "error") == set()


def test_r3_artifacts_are_listed(thesis_check, repo):
    old = figure(repo, "s1-old-map.png")
    sidecar(
        old,
        reproducibility="R3",
        sources=[{"path": "projects/s1/data/raw/legacy/old/map.png", "sha256": "0" * 64}],
        license="own work",
        note="instrument output",
    )
    values = write(
        repo / "projects" / "s1" / "result" / "tables" / "s1-old-transcribed.tex",
        "\\defvalue{s1-old-transcribed-rmse}{0.42}\n",
    )
    sidecar(values, kind="values", reproducibility="R3", transcribed_from="smith2024, Table 2")
    write(
        repo / "draft" / "values.tex",
        "\\ThesisValues{../projects/s1/result/tables/s1-old-transcribed}\n",
    )
    draft_main(
        repo, "\\includegraphics{s1-old-map}\\val{s1-old-transcribed-rmse}\n", "\\input{values}\n"
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    messages = sorted(f.message for f in of(findings, "I3"))
    assert len(messages) == 2
    assert "legacy/old/map.png" in messages[0] and "own work" in messages[0]
    assert "smith2024, Table 2" in messages[1]
    assert all(f.severity == "info" for f in of(findings, "I3"))


def test_artifacts_from_withdrawn_or_unknown_experiments_are_w14(thesis_check, repo):
    for name, experiment in [
        ("s1-good.png", "001_good_run"),
        ("s1-archived.png", "003_old_run"),
        ("s1-withdrawn.png", "002_bad_run"),
        ("s1-unknown.png", "011_ghost"),
        ("s1-script.png", None),
    ]:
        sidecar(figure(repo, name), experiment=experiment)
    draft_main(
        repo,
        "".join(
            f"\\includegraphics{{s1-{n}}}\n"
            for n in ("good", "archived", "withdrawn", "unknown", "script")
        ),
    )

    draft_findings = thesis_check.run_checks(repo / "draft", with_log=False)
    final_findings = thesis_check.run_checks(repo / "draft", with_log=False, submission=True)

    flagged = sorted(f.location.rsplit("/", 1)[-1] for f in of(draft_findings, "W14"))
    assert flagged == ["s1-unknown.png", "s1-withdrawn.png"]
    assert {f.severity for f in of(draft_findings, "W14")} == {"warning"}
    assert {f.severity for f in of(final_findings, "W14")} == {"error"}
    assert any("撤回" in f.message for f in of(draft_findings, "W14"))


def test_w14_follows_sources_to_the_experiment_behind_them(thesis_check, repo):
    """A promotion script in scripts/ has no experiment of its own: W14 follows `sources`."""
    s1 = repo / "projects" / "s1"
    tables = s1 / "result" / "tables"
    for name, experiment in [("s1-bad-fit", "002_bad_run"), ("s1-good-fit", "001_good_run")]:
        csv = write(tables / f"{name}.csv", "x,y\n1,2\n")
        sidecar(csv, kind="table", experiment=experiment, script="projects/s1/experiments/x/run.py")
    # A script read the withdrawn CSV and wrote another one: the chain is followed.
    derived = write(tables / "s1-derived.csv", "x\n1\n")
    sidecar(derived, kind="table", sources=[{"path": "projects/s1/result/tables/s1-bad-fit.csv"}])
    looped = write(tables / "s1-loop.csv", "x\n1\n")
    sidecar(looped, kind="table", sources=[{"path": "projects/s1/result/tables/s1-loop.csv"}])
    write(s1 / "data" / "processed" / "002_bad_run" / "grid.nc", "x")
    write(s1 / "experiments" / "002_bad_run" / "out" / "fit.csv", "x\n1\n")
    for name, source in [
        ("bad", "projects/s1/result/tables/s1-bad-fit.csv"),
        ("good", "projects/s1/result/tables/s1-good-fit.csv"),
        ("derived", "projects/s1/result/tables/s1-derived.csv"),
        ("processed", "projects/s1/data/processed/002_bad_run/grid.nc"),
        ("out", "projects/s1/experiments/002_bad_run/out/fit.csv"),
        ("legacy", "projects/s1/data/raw/legacy/old/map.png"),
        ("loop", "projects/s1/result/tables/s1-loop.csv"),
    ]:
        sidecar(figure(repo, f"s1-from-{name}.png"), sources=[{"path": source, "sha256": "0"}])
    names = ("bad", "good", "derived", "processed", "out", "legacy", "loop")
    draft_main(repo, "".join(f"\\includegraphics{{s1-from-{n}}}\n" for n in names))

    draft_findings = thesis_check.run_checks(repo / "draft", with_log=False)
    final_findings = thesis_check.run_checks(repo / "draft", with_log=False, submission=True)

    flagged = sorted(f.location.rsplit("/", 1)[-1] for f in of(draft_findings, "W14"))
    assert flagged == [
        "s1-from-bad.png",
        "s1-from-derived.png",
        "s1-from-out.png",
        "s1-from-processed.png",
    ]
    assert all("002_bad_run" in f.message for f in of(draft_findings, "W14"))
    assert all("through its source" in f.message for f in of(draft_findings, "W14"))
    assert {f.severity for f in of(final_findings, "W14")} == {"error"}


@pytest.mark.parametrize(
    ("experiment", "flagged", "words"),
    [
        ("001_good_run", None, ()),
        ("009_fixed", None, ()),
        ("002_bad_run", "blocked", ("'撤回(2026-01-02、→ 004_redo)'", "/EXP_SUMMARY.md;")),
        ("005_bold_bad", "blocked", ("'**撤回(2026-01-03)**'",)),
        ("006_replaced", "blocked", ("'置き換え(2026-01-04、→ 004_redo)'",)),
        ("007_old_word", "not a status word", ("'置換(→004)'",)),
        ("012_past_import", "not a status word", ("'取り込み済'",)),
        (
            "008_open",
            "no conclusion yet",
            ("状態 進行中 in projects/s1/experiments/EXP_SUMMARY.md",),
        ),
        ("010_archived_bad", "blocked", ("projects/s1/experiments/EXP_ARCHIVE.md",)),
        ("011_missing", "no row", ("projects/s1/experiments/EXP_SUMMARY.md or EXP_ARCHIVE.md",)),
    ],
)
def test_w14_reads_the_status_word(thesis_check, repo, experiment, flagged, words):
    """完了 and 訂正 pass; 撤回・中止・置き換え, 進行中, other words and missing rows are W14."""
    sidecar(figure(repo, "s1-x.png"), experiment=experiment)
    draft_main(repo, "\\includegraphics{s1-x}\n")

    w14 = of(thesis_check.run_checks(repo / "draft", with_log=False), "W14")
    final = of(thesis_check.run_checks(repo / "draft", with_log=False, submission=True), "W14")

    if flagged is None:
        assert w14 == [] and final == []
        return
    assert len(w14) == 1 and w14[0].severity == "warning"
    assert [f.severity for f in final] == ["error"]
    message = w14[0].message
    assert message.startswith(f"s1-x.png comes from experiment {experiment}, ")
    if flagged == "blocked":
        assert "whose status is '" in message
    elif flagged == "not a status word":
        assert "is not a status word (進行中・完了・中止・訂正・撤回・置き換え;" in message
    else:
        assert flagged in message
    assert all(word in message for word in words), message
    card = f"projects/s1/experiments/{experiment}/summary.md"
    assert (card in message) is (flagged != "no row"), message
    if flagged == "no conclusion yet":
        assert message.endswith(
            f"-- write the answer in {card} and the index row, or remove it from the text"
        )
    else:
        assert message.endswith(
            "-- regenerate it from a valid experiment or remove it from the text"
        )


def test_status_words_are_research_templates_six(thesis_check):
    assert thesis_check.STATUS_WORDS == ("進行中", "完了", "中止", "訂正", "撤回", "置き換え")
    assert not hasattr(thesis_check, "INVALID_STATUS_PREFIXES")
    status_word = thesis_check.status_word
    assert status_word(" **撤回(2026-01-03)** ") == "撤回"
    assert status_word("_置き換え(2026-01-04、→ 004_redo)_") == "置き換え"
    assert status_word("完了") == "完了"
    for cell in ("置換(→004)", "取り込み済", "", "(実行前)", "done"):
        assert status_word(cell) is None, cell


def test_w14_follows_a_promoted_csv(thesis_check, repo):
    """run.promote() gives a CSV a kind "file" sidecar; a scripts/ figure that read it is W14."""
    tables = repo / "projects" / "s1" / "result" / "tables"
    csv = write(tables / "s1-fit.csv", "x,y\n1,2\n")
    sidecar(
        csv,
        kind="file",
        experiment="002_bad_run",
        script="projects/s1/experiments/002_bad_run/run.py",
    )
    sidecar(
        figure(repo, "s1-plot.png"),
        script="projects/s1/scripts/plot.py",
        sources=[{"path": "projects/s1/result/tables/s1-fit.csv", "sha256": sha256(csv)}],
    )
    draft_main(repo, "\\includegraphics{s1-plot}\n")

    w14 = of(thesis_check.run_checks(repo / "draft", with_log=False), "W14")

    assert len(w14) == 1, w14
    assert w14[0].location.endswith("projects/s1/result/figures/s1-plot.png")
    assert "comes from experiment 002_bad_run, whose status is '撤回" in w14[0].message
    assert "(through its source projects/s1/result/tables/s1-fit.csv)" in w14[0].message


@pytest.mark.parametrize(
    "state",
    [{"git_dirty": True}, {"git_dirty": "unknown"}, {"git_commit": "unknown"}],
)
def test_artifacts_from_uncommitted_code_are_w15(thesis_check, repo, state):
    sidecar(figure(repo, "s1-dirty.png"), **state)
    draft_main(repo, "\\includegraphics{s1-dirty}\n")

    draft_findings = thesis_check.run_checks(repo / "draft", with_log=False)
    final_findings = thesis_check.run_checks(repo / "draft", with_log=False, submission=True)

    assert [f.severity for f in of(draft_findings, "W15")] == ["warning"]
    assert [f.severity for f in of(final_findings, "W15")] == ["error"]


def test_result_files_without_study_prefix_are_w16(thesis_check, repo):
    sidecar(figure(repo, "overview.png"))
    write(repo / "projects" / "s1" / "result" / "tables" / "s1-ok.csv", "a\n1\n")
    (repo / "projects" / "s1" / "result" / "figures" / ".gitkeep").write_bytes(b"")
    draft_main(repo, "\\includegraphics{overview}\n")

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    w16 = sorted(f.location.rsplit("/", 1)[-1] for f in of(findings, "W16"))
    assert w16 == ["overview.png", "overview.provenance.json"]


def test_reading_from_experiments_or_data_is_e10(thesis_check, repo):
    out = repo / "projects" / "s1" / "experiments" / "001_good_run" / "out"
    out.mkdir(parents=True)
    (out / "fig.png").write_bytes(b"png")
    write(out / "table.tex", "x\n")
    write(repo / "projects" / "s1" / "data" / "processed" / "t.tex", "y\n")
    draft_main(
        repo,
        "\\includegraphics{../projects/s1/experiments/001_good_run/out/fig}\n"
        "\\input{../projects/s1/experiments/001_good_run/out/table}\n"
        "\\input{../projects/s1/data/processed/t}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert len(of(findings, "E10")) == 3
    assert {f.location.rsplit(":", 1)[-1] for f in of(findings, "E10")} == {"4", "5", "6"}


# --- Generated values -------------------------------------------------------------------------

VALUES_MACROS = (
    "\\newcommand{\\defvalue}[2]{\\expandafter\\gdef\\csname thesisvalue@#1\\endcsname{#2}}\n"
    "\\newcommand{\\deftextvalue}[2]{\\defvalue{#1}{#2}}\n"
    "\\newcommand{\\rawval}[1]{\\csname thesisvalue@#1\\endcsname}\n"
    "\\newcommand{\\val}[1]{\\csname thesisvalue@#1\\endcsname}\n"
)


def test_values_undefined_duplicate_and_late_definitions(thesis_check, tmp_path):
    write(
        tmp_path / "values.tex",
        VALUES_MACROS + "\\defvalue{s1-main-n}{12}\n\\deftextvalue {s1-main-site}{Bay}\n"
        "\\defvalue{s1-main-n}{13}\n",
    )
    write(tmp_path / "chapter.tex", "\\defvalue{s1-late-x}{1}\n\\val{s1-late-x}\n")
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\input{values}\n\\begin{document}\n"
        "\\val{s1-main-n} \\rawval {s1-main-site} \\val{s1-ghost} \\valqty{s1-main-n}{\\metre}\n"
        "\\input{chapter}\n\\end{document}\n",
    )

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    e8 = of(findings, "E8")
    assert len(e8) == 1 and "'s1-ghost'" in e8[0].message
    assert e8[0].location.endswith("main.tex:4")
    w12 = of(findings, "W12")
    assert len(w12) == 1 and "'s1-main-n'" in w12[0].message
    e11 = of(findings, "E11")
    assert len(e11) == 1 and e11[0].location.endswith("chapter.tex:1")
    assert not [f for f in findings if "#" in f.message and f.code in {"E8", "W12"}]


def test_registered_values_file_missing_is_w17_not_e5(thesis_check, tmp_path):
    write(tmp_path / "values.tex", VALUES_MACROS + "\\ThesisValues{../projects/s1/x/s1-main}\n")
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\input{values}\n\\begin{document}\\end{document}\n",
    )

    draft_findings = thesis_check.run_checks(tmp_path, with_log=False)
    final_findings = thesis_check.run_checks(tmp_path, with_log=False, submission=True)

    assert "E5" not in codes(draft_findings)
    assert [f.severity for f in of(draft_findings, "W17")] == ["warning"]
    assert [f.severity for f in of(final_findings, "W17")] == ["error"]


def test_registered_values_file_defines_keys_before_the_document(thesis_check, repo):
    values = write(
        repo / "projects" / "s1" / "result" / "tables" / "s1-main.tex",
        "% Generated by x\n\\defvalue{s1-main-n}{12}\n",
    )
    sidecar(values, kind="values")
    write(
        repo / "draft" / "values.tex",
        VALUES_MACROS + "\\ThesisValues{../projects/s1/result/tables/s1-main}\n",
    )
    draft_main(repo, "\\val{s1-main-n}\n", preamble="\\input{values}\n")

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert codes(findings) & {"E5", "E8", "E11", "W11", "W12", "W17"} == set()


# --- Bibliography -----------------------------------------------------------------------------


def test_duplicate_dois_and_verified_field(thesis_check, tmp_path):
    write(
        tmp_path / "reference.bib",
        "@article{smith2020ocean,\n  title = {A},\n  doi = {10.1000/ABC},\n"
        "  verified = {2026-01-02, doi:10.1000/abc},\n}\n"
        "@article{smith2020oceans,\n  title = {A again},\n  doi = {https://doi.org/10.1000/abc},\n"
        "  verified = {yesterday},\n}\n"
        "@book{lee2019book, title={B}, year={2019}}\n",
    )
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\begin{document}\n"
        "\\cite{smith2020ocean,smith2020oceans,lee2019book}\n\\bibliography{reference}\n"
        "\\end{document}\n",
    )

    draft_findings = thesis_check.run_checks(tmp_path, with_log=False)
    final_findings = thesis_check.run_checks(tmp_path, with_log=False, submission=True)

    w13 = of(draft_findings, "W13")
    assert len(w13) == 1 and "10.1000/abc" in w13[0].message
    i4 = {f.message.split("'")[1]: f for f in of(draft_findings, "I4")}
    assert set(i4) == {"smith2020oceans", "lee2019book"}
    assert "malformed" in i4["smith2020oceans"].message
    assert {f.severity for f in i4.values()} == {"info"}
    assert {f.severity for f in of(final_findings, "I4")} == {"error"}


# --- Front matter (submission) ----------------------------------------------------------------


def test_empty_front_matter_is_e9_in_submission(thesis_check, tmp_path):
    front = tmp_path / "frontmatter"
    write(
        front / "abstract-en.tex",
        "\\chapter*{Abstract}\n\\phantomsection\n\\addcontentsline{toc}{chapter}{Abstract}\n\n"
        "\\todo[inline]{Replace {this} note.}\n% A comment.\n\\vspace{1em}\n"
        "\\noindent\\textbf{Keywords:} \\ThesisKeywordsEN\n",
    )
    write(front / "abstract-ja.tex", "\\chapter*{和文要旨}\n本研究は、海洋の混合を調べた。\n")
    write(front / "acknowledgments.tex", "\\chapter*{Acknowledgments}\n\\todo{thank}\n")
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\begin{document}\n\\input{frontmatter/abstract-ja}\n"
        "\\input{frontmatter/abstract-en}\n\\input{frontmatter/acknowledgments}\n"
        "\\end{document}\n",
    )

    draft_findings = thesis_check.run_checks(tmp_path, with_log=False)
    final_findings = thesis_check.run_checks(tmp_path, with_log=False, submission=True)

    assert "E9" not in codes(draft_findings)
    flagged = sorted(f.location.rsplit("/", 1)[-1] for f in of(final_findings, "E9"))
    assert flagged == ["abstract-en.tex", "acknowledgments.tex"]


def test_printed_optional_page_with_template_text_is_e9_in_submission(thesis_check, tmp_path):
    front = tmp_path / "frontmatter"
    page = "\\chapter*{{{0}}}\n% Lines ending in `% thesis:placeholder` are template text.\n{1}\n"
    marked = "Replace this text. % thesis:placeholder"
    write(front / "declaration.tex", page.format("Declaration", marked))
    write(front / "publications.tex", page.format("Publications", f"Real list.\n{marked}"))
    write(front / "abbreviations.tex", page.format("Abbreviations", "ABC: written by me."))
    write(front / "symbols.tex", page.format("Symbols", marked))
    write(
        tmp_path / "thesis-config.tex",
        "".join(
            f"\\newif\\ifThesisInclude{name}\n\\ThesisInclude{name}{state}\n"
            for name, state in [
                ("Declaration", "true"),
                ("Publications", "false"),
                ("Abbreviations", "true"),
                ("Symbols", "false"),
            ]
        )
        + "\\ThesisIncludePublicationstrue % the last setting wins\n"
        + "% \\ThesisIncludeSymbolstrue\n",
    )
    write(
        tmp_path / "main.tex",
        "\\documentclass{book}\n\\input{thesis-config}\n\\begin{document}\n"
        + "".join(
            f"\\ifThesisInclude{name}\n  \\input{{frontmatter/{name.lower()}}}\n\\fi\n"
            for name in ("Declaration", "Publications", "Abbreviations", "Symbols")
        )
        + "\\end{document}\n",
    )

    draft_findings = thesis_check.run_checks(tmp_path, with_log=False)
    final_findings = thesis_check.run_checks(tmp_path, with_log=False, submission=True)

    assert "E9" not in codes(draft_findings)
    flagged = sorted(f.location.rsplit("/", 1)[-1] for f in of(final_findings, "E9"))
    assert flagged == ["declaration.tex:3", "publications.tex:4"]
    assert "\\ThesisIncludeDeclarationfalse" in of(final_findings, "E9")[0].message


# --- --all, --list-generators, CLI ------------------------------------------------------------


def test_all_merges_documents(thesis_check, tmp_path):
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "only-supplementary.png").write_bytes(b"png")
    (tmp_path / "figures" / "unused.png").write_bytes(b"png")
    write(
        tmp_path / "figures" / "README.md",
        "| ファイル |\n|---|\n| only-supplementary.png |\n| unused.png |\n",
    )
    shared = "\\documentclass{article}\n\\graphicspath{{figures/}}\n\\begin{document}\n"
    write(tmp_path / "main.tex", shared + "% TODO: shared note\n\\end{document}\n")
    write(tmp_path / "review.tex", "\\input{main.tex}\n")
    write(
        tmp_path / "supplementary.tex",
        shared + "\\includegraphics{only-supplementary}\n\\end{document}\n",
    )

    findings = thesis_check.run_all(tmp_path, with_log=False)

    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "W3")] == ["unused.png"]
    assert len(of(findings, "I1")) == 1  # main and review share the TODO


def makefile_command(repo_root, target):
    """The argv of a Makefile target whose recipe is one command."""
    lines = (repo_root / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{target}:"))
    recipe = []
    for line in lines[start + 1 :]:
        if not line.startswith("\t"):
            break
        recipe.append(line.strip().lstrip("@"))
    assert len(recipe) == 1, f"make {target} is expected to run one command: {recipe}"
    return shlex.split(recipe[0])


def test_check_final_checks_both_final_documents_as_one(thesis_check, repo_root, repo, capsys):
    """make check-final: a figure only the thesis (or only the supplement) uses is not W3."""
    argv = makefile_command(repo_root, "check-final")
    assert argv[:2] == ["python3", "tools/thesis_check.py"]
    mains = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--main"]
    assert mains == ["submission.tex", "supplementary.tex"]
    flags = [arg for arg in argv[2:] if arg != "--main" and arg not in mains]
    assert {"--submission", "--strict"} <= set(flags)
    for name in ("s1-thesis-only.png", "s1-supplement-only.png"):
        sidecar(figure(repo, name))
    write(
        repo / "draft" / "thesis-config.tex",
        "".join(f"\\newcommand{{\\{n}}}{{Set}}\n" for n in sorted(thesis_check.REQUIRED_METADATA)),
    )
    draft_main(repo, "\\includegraphics{s1-thesis-only}\n", preamble="\\input{thesis-config}\n")
    write(repo / "draft" / "submission.tex", "\\def\\ThesisFinalBuild{1}\n\\input{main.tex}\n")
    supplement = (repo / "draft" / "main.tex").read_text(encoding="utf-8")
    write(
        repo / "draft" / "supplementary.tex",
        supplement.replace("s1-thesis-only", "s1-supplement-only"),
    )

    assert thesis_check.main(argv[2:], root=repo) == 0, capsys.readouterr().out
    assert "Checked: " in capsys.readouterr().out
    # Checked one at a time (the old recipe), each document flags the other's figure.
    assert thesis_check.main(["--main", "supplementary.tex", *flags], root=repo) == 1
    assert "s1-thesis-only.png: [W3]" in capsys.readouterr().out
    # A figure neither document includes still fails the final check.
    sidecar(figure(repo, "s1-orphan.png"))
    assert thesis_check.main(argv[2:], root=repo) == 1
    out = capsys.readouterr().out
    assert "s1-orphan.png: [W3]" in out and "s1-thesis-only.png: [W3]" not in out


def test_list_generators_prints_sorted_unique_commands(thesis_check, repo):
    for name, script in [
        ("s1-b.png", "projects/s1/scripts/b.py"),
        ("s1-a.png", "projects/s1/experiments/001_good_run/run.py"),
        ("s1-a2.png", "projects/s1/experiments/001_good_run/run.py"),
        ("s1-pytest.png", "/opt/venv/bin/pytest"),
    ]:
        sidecar(figure(repo, name), script=script)
        if not script.startswith("/"):
            write(repo / script, "print()\n")
    figure(repo, "s1-nosidecar.png")
    draft_main(
        repo,
        "".join(
            f"\\includegraphics{{{n}}}\n"
            for n in ("s1-b", "s1-a", "s1-a2", "s1-pytest", "s1-nosidecar")
        ),
    )
    for name in ("review.tex", "supplementary.tex"):
        write(repo / "draft" / name, "\\input{main.tex}\n")

    lines = thesis_check.list_generators(repo / "draft")

    run = "docker compose exec research-template uv run python"
    assert lines[:2] == [
        f"{run} projects/s1/experiments/001_good_run/run.py --overwrite",
        f"{run} projects/s1/scripts/b.py",
    ]
    assert all(line.startswith("#") for line in lines[2:]) and len(lines) == 4


def test_list_generators_puts_upstream_generators_first(thesis_check, repo):
    """Each generator comes after the generators of the files it read, all the way up.

    a_plot.py reads s1-mid.csv, which b_mid.py made from s1-fit.csv, which c_fit.py made
    from experiment 001's data/processed/ output: alphabetical order would be the reverse.
    """
    s1 = repo / "projects" / "s1"
    tables = s1 / "result" / "tables"
    for script in ("scripts/a_plot.py", "scripts/b_mid.py", "scripts/c_fit.py"):
        write(s1 / script, "print()\n")
    write(s1 / "experiments" / "001_good_run" / "run.py", "print()\n")
    fit = write(tables / "s1-fit.csv", "x\n1\n")
    sidecar(
        fit,
        kind="file",
        script="projects/s1/scripts/c_fit.py",
        sources=[{"path": "projects/s1/data/processed/001_good_run/grid.nc", "sha256": "0"}],
    )
    mid = write(tables / "s1-mid.csv", "x\n1\n")
    sidecar(
        mid,
        kind="file",
        script="projects/s1/scripts/b_mid.py",
        sources=[{"path": "projects/s1/result/tables/s1-fit.csv", "sha256": sha256(fit)}],
    )
    sidecar(
        figure(repo, "s1-joint.png"),
        script="projects/s1/scripts/a_plot.py",
        sources=[{"path": "projects/s1/result/tables/s1-mid.csv", "sha256": sha256(mid)}],
    )
    sidecar(figure(repo, "s1-direct.png"), script="projects/s1/scripts/b_mid.py")
    draft_main(repo, "\\includegraphics{s1-joint}\n\\includegraphics{s1-direct}\n")

    lines = thesis_check.list_generators(repo / "draft", ("main.tex",))

    run = "docker compose exec research-template uv run python"
    assert lines == [
        f"{run} projects/s1/experiments/001_good_run/run.py --overwrite",
        f"{run} projects/s1/scripts/c_fit.py",
        f"{run} projects/s1/scripts/b_mid.py",
        f"{run} projects/s1/scripts/a_plot.py",
    ]


def test_list_generators_notes_generators_that_read_each_other(thesis_check, repo):
    s1 = repo / "projects" / "s1"
    tables = s1 / "result" / "tables"
    for script in ("a_first.py", "x_one.py", "y_two.py", "z_last.py"):
        write(s1 / "scripts" / script, "print()\n")
    for name, script, source in [
        ("s1-one.csv", "x_one.py", "s1-two.csv"),
        ("s1-two.csv", "y_two.py", "s1-one.csv"),
        ("s1-first.csv", "a_first.py", None),
    ]:
        sources = [{"path": f"projects/s1/result/tables/{source}"}] if source else []
        if script == "x_one.py":
            sources.append({"path": "projects/s1/result/tables/s1-first.csv"})
        sidecar(
            write(tables / name, "x\n1\n"),
            kind="file",
            script=f"projects/s1/scripts/{script}",
            sources=sources,
        )
    sidecar(
        figure(repo, "s1-last.png"),
        script="projects/s1/scripts/z_last.py",
        sources=[{"path": "projects/s1/result/tables/s1-one.csv"}],
    )
    draft_main(repo, "\\includegraphics{s1-last}\n")

    lines = thesis_check.list_generators(repo / "draft", ("main.tex",))

    run = "docker compose exec research-template uv run python"
    assert lines == [
        f"{run} projects/s1/scripts/a_first.py",
        f"{run} projects/s1/scripts/x_one.py",
        f"{run} projects/s1/scripts/y_two.py",
        f"{run} projects/s1/scripts/z_last.py",
        "# generators read each other's outputs: "
        "projects/s1/scripts/x_one.py, projects/s1/scripts/y_two.py",
    ]


def test_cli_exit_codes(thesis_check, repo_root, tmp_path, capsys):
    assert thesis_check.main(["--all", "--no-log"], root=repo_root) == 0
    assert thesis_check.main(["--list-generators"], root=repo_root) == 0
    assert thesis_check.main(["--main", "nope.tex"], root=repo_root) == 2
    write(tmp_path / "draft" / "main.tex", "\\documentclass{article}\n\\ref{sec:x}\n")
    assert thesis_check.main(["--no-log"], root=tmp_path) == 1
    capsys.readouterr()


@pytest.mark.parametrize(
    "tool",
    [
        "thesis_check.py",
        "new_study.py",
        "new_experiment.py",
        "archive_thesis.py",
        "public_repo_check.py",
    ],
)
def test_host_tools_stop_with_one_line_on_old_python(repo_root, tool):
    """The host python3 may be too old (macOS /usr/bin/python3 is 3.9): one line, no traceback."""
    path = repo_root / "tools" / tool
    # The file must parse on the old grammar, and the guard must run before any definition
    # (an `X | None` annotation is a TypeError on 3.9).
    tree = ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 9))
    guard = next(
        i
        for i, node in enumerate(tree.body)
        if isinstance(node, ast.If) and "sys.version_info" in ast.unparse(node.test)
    )
    assert all(
        isinstance(node, ast.Import | ast.ImportFrom)
        or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        for node in tree.body[:guard]
    ), f"{tool}: only the docstring and imports may come before the version check"

    old_python = (
        "import runpy, sys\n"
        "sys.version_info = (3, 9, 6, 'final', 0)\n"
        "sys.version = '3.9.6 (default)'\n"
        "runpy.run_path(sys.argv[1], run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", old_python, str(path), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr == f"{tool}: needs python3 3.10 or newer, not 3.9.6\n"
    assert result.stdout == ""


# --- Integration with the study helpers -------------------------------------------------------


def test_sidecars_written_by_the_study_helpers_are_accepted(
    thesis_check, repo_root, load_module_by_path, tmp_path
):
    """The checker reads exactly the files save_figure / write_latex_* / import_figure write."""
    import shutil
    from types import SimpleNamespace

    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    pd = pytest.importorskip("pandas")
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    import matplotlib.pyplot as plt

    utils = repo_root / "projects" / "_template" / "src" / "utils"
    figures = load_module_by_path(utils / "figures.py", "figures_for_thesis_check")
    tables = load_module_by_path(utils / "tables.py", "tables_for_thesis_check")
    root = tmp_path / "repo"
    study = root / "projects" / "s1"
    cfg = SimpleNamespace(
        REPO_ROOT=root,
        STUDY_ROOT=study,
        FIGURE_DIR=study / "result" / "figures",
        TABLE_DIR=study / "result" / "tables",
        VISUALIZATION={"dpi": 20, "format": "png", "font": {"family": "DejaVu Sans", "size": 8}},
    )
    # The real macros, without the thesis's own registrations: their files are not copied.
    values = re.sub(
        r"^[ \t]*\\ThesisValues\s*\{.*\n",
        "",
        (repo_root / "draft" / "values.tex").read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    write(
        root / "draft" / "values.tex",
        values + "\\ThesisValues{../projects/s1/result/tables/s1-main}\n",
    )
    write(
        root / "draft" / "main.tex",
        "\\documentclass{article}\n"
        "\\graphicspath{{figures/}{../projects/s1/result/figures/}}\n"
        "\\input{values}\n\\begin{document}\n"
        "\\includegraphics{s1-overview}\\includegraphics{s1-old-map}\n"
        "\\input{../projects/s1/result/tables/s1-summary}\n"
        "\\val{s1-main-n} \\val{s1-main-rmse} \\rawval{s1-main-site}\n"
        "\\end{document}\n",
    )
    legacy = study / "data" / "raw" / "legacy" / "old" / "map.png"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"\x89PNG old")
    identity = ["-c", "user.name=t", "-c", "user.email=t@users.noreply.github.com"]
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "draft"]):
        subprocess.run(["git", *identity, "-C", str(root), *args], check=True, capture_output=True)

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    figures.save_figure(fig, "s1-overview", cfg)
    figures.import_figure(legacy, "s1-old-map", cfg, note="instrument output", license="own work")
    tables.write_latex_table(pd.DataFrame({"site": ["A"], "rmse": [0.41]}), "s1-summary", cfg)
    tables.write_latex_values(
        {"n": 12, "rmse": 0.4132, "site": "Bay"}, "s1-main", cfg, formats={"rmse": "{:.2f}"}
    )

    findings = thesis_check.run_checks(root / "draft", with_log=False)

    assert codes(findings, "error") == set(), findings
    assert codes(findings) & {"W11", "W12", "W14", "W15", "W16", "W17"} == set(), findings
    r3 = of(findings, "I3")
    assert len(r3) == 1 and "projects/s1/data/raw/legacy/old/map.png" in r3[0].message
    notes = thesis_check.list_generators(root / "draft", ("main.tex",))
    assert notes and all(line.startswith("# ") for line in notes)  # pytest is not a repo script


def test_undefined_quantity_value_is_reported(thesis_check, tmp_path):
    write(tmp_path / "values.tex", VALUES_MACROS + "\\defvalue{s1-main-depth}{12.5}\n")
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\input{values}\n\\begin{document}\n"
        "\\valqty{s1-main-depth}{\\metre} \\valqty {s1-main-width}{\\metre}\n\\end{document}\n",
    )

    e8 = of(thesis_check.run_checks(tmp_path, with_log=False), "E8")

    assert len(e8) == 1 and "'s1-main-width'" in e8[0].message
