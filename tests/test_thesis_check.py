"""Self-verification of tools/thesis_check.py.

(a) The pristine template manuscript must produce zero errors in every document.
(b) Synthetic drafts must trigger each check, proving the checker actually fires
    when agents rely on it as a quality gate.
"""

import ast
import json
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


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def repo(tmp_path):
    """A repo-shaped tmp tree: draft/figures/ and projects/s1/{figures,tables}/."""
    (tmp_path / "draft" / "figures").mkdir(parents=True)
    for area in ("figures", "tables"):
        (tmp_path / "projects" / "s1" / area).mkdir(parents=True)
    write(tmp_path / "research.json", '{"research": []}\n')
    return tmp_path


def draft_main(repo, body, preamble=""):
    """draft/main.tex reading figures from draft/figures/ and projects/ (as the template)."""
    return write(
        repo / "draft" / "main.tex",
        "\\documentclass{article}\n"
        "\\graphicspath{{figures/}{../projects/}}\n"
        f"{preamble}"
        "\\begin{document}\n"
        f"{body}"
        "\\end{document}\n",
    )


def figure(repo, name, data=b"\x89PNG\r\n"):
    path = repo / "projects" / "s1" / "figures" / name
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
    (repo / "draft" / "figures" / "s1-wrapped.png").write_bytes(b"png")
    draft_main(
        repo,
        "\\citep[see][p.~3]{a2020,\n  b2021, ghost2019} and \\cref{fig:s1-wrapped,%\n"
        "  fig:missing}.\n"
        "\\begin{figure}\n\\includegraphics[width=0.8\\linewidth,\n  trim=0 0 0 0, clip]\n"
        "  {s1-wrapped}\n\\label{fig:s1-wrapped}\n\\end{figure}\n"
        "\\bibliography{reference}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert codes(findings) & {"E4", "W2", "W3", "W4"} == set(), findings
    # Reported at the line where the command starts.
    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "E3")] == ["main.tex:4"]
    assert "ghost2019" in of(findings, "E3")[0].message
    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "E1")] == ["main.tex:5"]


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
        "./chapters/study1.tex:12: Undefined control sequence.\n"
        "Overfull \\hbox (1.0pt too wide) in paragraph at lines 3--4\n",
    )

    main_findings = thesis_check.run_checks(tmp_path)
    review_findings = thesis_check.run_checks(tmp_path, main_name="review.tex")

    missing = of(main_findings, "I2")
    assert len(missing) == 1 and "build/main/main.log" in missing[0].message
    assert "make pdf" in missing[0].message
    errors = [f for f in of(review_findings, "I2") if f.severity == "error"]
    assert len(errors) == 1
    assert errors[0].location.endswith("chapters/study1.tex:12")
    assert "Undefined control sequence" in errors[0].message
    assert "W10" in codes(review_findings, "warning")


# --- Figures ----------------------------------------------------------------------------------


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


def test_hand_made_figures_need_a_use_and_a_ledger_row(thesis_check, repo):
    """W3 and W11 are for draft/figures/ only: projects/<id>/figures/ may hold unused copies."""
    figures = repo / "draft" / "figures"
    for name in ("listed.pdf", "unlisted.png", "orphan.pdf"):
        (figures / name).write_bytes(b"%PDF")
    write(
        figures / "README.md",
        "| ファイル | 内容 |\n|---|---|\n| `listed.pdf` | a |\n| figures/orphan.pdf | b |\n",
    )
    figure(repo, "orphan.png")  # same name, but it does not use draft/figures/orphan.pdf
    figure(repo, "not-used-yet.png")
    draft_main(
        repo,
        "\\includegraphics{listed}\\includegraphics{unlisted}\n"
        "\\includegraphics{s1/figures/orphan}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "W11")] == ["unlisted.png"]
    assert [f.location.rsplit("/", 1)[-1] for f in of(findings, "W3")] == ["orphan.pdf"]
    assert codes(findings, "error") == set()


def test_wrapper_macros_are_read_at_each_use(thesis_check, repo):
    """A \\newcommand that hands its parameters to \\includegraphics, \\label, \\cref or \\cite
    is checked where it is used, with its arguments filled in; its definition is not a use."""
    for name in ("s1-good", "s1-left", "s1-right", "s1-map", "s1-withdrawn"):
        (repo / "draft" / "figures" / f"{name}.png").write_bytes(b"png")
    write(repo / "draft" / "reference.bib", "@book{known,\n  title = {T},\n}\n")
    draft_main(
        repo,
        "\\studyfig{s1-good}{Good.} \\figref{s1-good}\n"
        "\\studyfig[0.8]{s1-withdrawn}{A\n  wrapped \\emph{caption}.}\n"
        "\\figref{s1-withdrawn} \\figref{s1-typo} \\mycite{known} \\mycite{unknown}\n"
        "\\figpair{s1-left}{s1-right} \\cref{fig:s1-left,fig:s1-right}\n"
        "\\sitemap{s1-map} \\cref{fig:s1-sites} \\oldref{s1-good} \\oldref{s1-left}\n"
        "\\bibliography{reference}\n",
        preamble="\\newcommand{\\studyfig}[3][0.6]{\\begin{figure}"
        "\\includegraphics[width=#1\\linewidth]{#2}\\caption{#3}\\label{fig:#2}\\end{figure}}\n"
        "\\newcommand{\\figref}[1]{Figure~\\cref{fig:#1}}\n"
        "\\newcommand\\mycite[1]{\\citep{#1}}\n"
        "\\newcommand*{\\figpair}[2]{\\studyfig{#1}{Left.}\n  \\studyfig{#2}{Right.}}\n"
        "\\newcommand{\\sitemap}[1]{\\includegraphics{#1}\\label{fig:s1-sites}}\n"
        "\\newcommand{\\oldref}[1]{Figure~\\ref{fig:#1}}\n"
        "\\def\\deffig#1{\\includegraphics{#1}}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    def where(code):
        return [f.location.rsplit("/", 1)[-1] for f in of(findings, code)]

    assert [f.message for f in of(findings, "E1")] == ["reference to undefined label 'fig:s1-typo'"]
    assert where("E1") == ["main.tex:15"]
    assert ["'unknown'" in f.message for f in of(findings, "E3")] == [True]
    assert codes(findings) & {"E2", "E4", "W3", "W4"} == set(), findings
    # A bare \ref in a wrapper is reported once, at its definition.
    assert where("W7") == ["main.tex:9"]
    # A macro the checker cannot expand is named, not read as a figure called '#1'.
    assert where("I6") == ["main.tex:10"]
    assert of(findings, "I6")[0].message.startswith("\\includegraphics{#1} sits in a macro")


def test_unexpandable_macros_are_named_by_their_command(thesis_check, repo):
    """I6 names the command as written in the macro (\\cref, \\nameref, \\citep, ...)."""
    draft_main(
        repo,
        "No figures.\n",
        preamble="\\def\\seefig#1{\\cref{fig:#1}}\n"
        "\\def\\seename#1{\\nameref{sec:#1}}\n"
        "\\def\\seerange#1#2{\\Crefrange*{fig:#1}{fig:#2}}\n"
        "\\def\\mycite#1{\\citep[p.~1]{#1}}\n"
        "\\def\\myval#1{\\valqty{#1}}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)
    messages = [f.message for f in of(findings, "I6")]

    assert [message.split(" sits in a macro")[0] for message in messages] == [
        "\\cref{fig:#1}",
        "\\nameref{sec:#1}",
        "\\Crefrange*{fig:#1}",
        "\\citep{#1}",
        "\\valqty{#1}",
    ]


@pytest.mark.parametrize(
    ("source", "keys"),
    [
        ("\\cref{fig:a,fig:b}", ["fig:a,fig:b"]),
        ("\\Cref*{fig:a}", ["fig:a"]),
        ("\\eqref{eq:a} \\autoref*{sec:a}", ["eq:a", "sec:a"]),
        ("\\cpageref{fig:a} \\Cpageref{fig:b}", ["fig:a", "fig:b"]),
        ("\\labelcref{fig:a} \\labelcpageref{fig:b}", ["fig:a", "fig:b"]),
        ("\\namecref{fig:a} \\nameCrefs{fig:b} \\lcnamecref{fig:c}", ["fig:a", "fig:b", "fig:c"]),
        ("\\nameref{sec:a} \\Nameref{sec:b} \\subref*{fig:a}", ["sec:a", "sec:b", "fig:a"]),
        (
            "\\vref{fig:a} \\Vref{fig:b} \\vpageref[above][below]{fig:c}",
            ["fig:a", "fig:b", "fig:c"],
        ),
        ("\\crefrange{fig:a}{fig:c}", ["fig:a", "fig:c"]),
        (
            "\\Crefrange*{fig:a} {fig:c} \\cpagerefrange{tab:a}{tab:b}",
            ["fig:a", "fig:c", "tab:a", "tab:b"],
        ),
        ("\\crefname{figure}{Fig.}{Figs.} \\Crefname{table}{Table}{Tables}", []),
        ("\\creflabelformat{equation}{#2(#1)#3} \\crefformat{x}{y}", []),
    ],
)
def test_reference_commands_give_keys(thesis_check, source, keys):
    found = [
        (match.start(), key)
        for regex in (thesis_check.RE_REF, thesis_check.RE_REF_RANGE)
        for match in regex.finditer(source)
        for key in match.groups()
    ]
    assert [key for _, key in sorted(found)] == keys


def test_cleveref_ranges_page_and_name_references_are_references(thesis_check, tmp_path):
    """Labels referred to only through \\crefrange, \\cpageref, \\labelcref or \\nameref are
    referenced (no W4); an undefined key inside a range is E1."""
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\begin{document}\n"
        + "".join(f"\\begin{{figure}}\\label{{fig:{n}}}\\end{{figure}}\n" for n in "abcefg")
        + "\\begin{table}\\label{tab:d}\\end{table}\n"
        "\\Crefrange{fig:a}{fig:b} on \\cpageref{fig:c}; \\labelcref{tab:d}, \\nameref{fig:e},\n"
        "\\namecref{fig:f} \\cpagerefrange{fig:g}\n  {fig:a} \\crefrange{fig:ghost1}{fig:a}\n"
        "\\end{document}\n",
    )

    findings = thesis_check.run_checks(tmp_path, with_log=False)

    assert of(findings, "W4") == []
    assert [(f.message, f.location.rsplit("/", 1)[-1]) for f in of(findings, "E1")] == [
        ("reference to undefined label 'fig:ghost1'", "main.tex:12")
    ]


def test_files_outside_the_repository_or_under_external_are_e10(
    thesis_check, repo, tmp_path_factory
):
    """The thesis uses copies in projects/<id>/, never a research repository's own files."""
    research = tmp_path_factory.mktemp("research-repo")
    (research / "fig.png").write_bytes(b"png")
    write(research / "table.tex", "x\n")
    write(repo / "external" / "copy" / "values.tex", "\\defvalue{r-x}{1}\n")
    (repo / "external" / "link").symlink_to(research)
    write(repo / "projects" / "s1" / "tables" / "ok.tex", "y\n")
    draft_main(
        repo,
        f"\\includegraphics{{{research}/fig}}\n"
        "\\input{../external/link/table}\n"
        "\\input{../external/copy/values}\n"
        "\\input{../projects/s1/tables/ok}\n",
        preamble="\\graphicspath{{../external/copy/}}\n",
    )

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert sorted(f.location.rsplit(":", 1)[-1] for f in of(findings, "E10")) == [
        "3",
        "5",
        "6",
        "7",
    ]


def research_row(**fields):
    return {
        "id": "s1",
        "title": "Study one",
        "chapter": "draft/chapters/02-s1.tex",
        "source": "s1-research@0123abcd",
        "paper": "",
        "paper_status": "",
        "status": "執筆中",
        **fields,
    }


def test_research_json_matches_projects_and_main(thesis_check, repo):
    write(repo / "draft" / "chapters" / "02-s1.tex", "\\chapter{One}\\label{ch:s1}\n")
    write(repo / "draft" / "chapters" / "03-s2.tex", "\\chapter{Two}\\label{ch:s2}\n")
    (repo / "projects" / "s2").mkdir()
    draft_main(repo, "\\include{chapters/02-s1}\n% \\include{chapters/03-s2}\n")
    research = repo / "research.json"

    def e12(data):
        write(research, data if isinstance(data, str) else json.dumps({"research": data}))
        return [
            f.message for f in of(thesis_check.run_checks(repo / "draft", with_log=False), "E12")
        ]

    assert e12([research_row(), research_row(id="s2", chapter="", status="構想")]) == []
    assert e12(
        [
            research_row(),
            research_row(chapter=""),
            research_row(id="S-3", chapter=""),
            research_row(id="s2", chapter="draft/chapters/03-s2.tex"),
            research_row(id="s4", chapter="draft/chapters/04-s4.tex", source="../s4@0123abcd"),
            research_row(id="s5", chapter="", status="done", paper_status="published"),
            {"id": "s6", "title": "No other fields"},
        ]
    ) == [
        "entry 2 ('s1'): id 's1' is listed twice",
        "entry 3 ('S-3'): id must match [a-z][a-z0-9_]*",
        "entry 4 ('s2'): draft/main.tex does not include draft/chapters/03-s2.tex",
        "entry 5 ('s4'): projects/s4/ does not exist -- cp -r projects/_template projects/s4",
        "entry 5 ('s4'): source must be <repo>@<sha> (or empty), never a host path",
        "entry 5 ('s4'): chapter draft/chapters/04-s4.tex does not exist",
        "entry 6 ('s5'): projects/s5/ does not exist -- cp -r projects/_template projects/s5",
        "entry 6 ('s5'): status must be one of 構想 | 取り込み済み | 執筆中 | 完成",
        "entry 6 ('s5'): paper_status must be one of 出版済み | 採録 | 投稿中 | 準備中 or empty",
        "entry 7 ('s6'): needs exactly the string fields "
        "id, title, chapter, source, paper, paper_status, status",
    ]
    assert e12("{not json")[0].startswith("research.json is unreadable: ")
    assert e12("[]") == ['research.json must be {"research": [...]}, a list of entries']


# --- Values -----------------------------------------------------------------------------------

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
    write(repo / "projects" / "s1" / "values.tex", "% From x\n\\deftextvalue{s1-n}{12}\n")
    write(repo / "draft" / "values.tex", VALUES_MACROS + "\\ThesisValues{../projects/s1/values}\n")
    draft_main(repo, "\\val{s1-n}\n", preamble="\\input{values}\n")

    findings = thesis_check.run_checks(repo / "draft", with_log=False)

    assert codes(findings) & {"E5", "E8", "E10", "E11", "W12", "W17"} == set()


# --- Bibliography -----------------------------------------------------------------------------


def test_duplicate_dois_and_verified_field(thesis_check, tmp_path):
    write(
        tmp_path / "reference.bib",
        "@article{smith2020ocean,\n  title = {A},\n  doi = {10.1000/ABC},\n"
        "  verified = {2026-01-02, doi:10.1000/abc},\n}\n"
        "@article{smith2020oceans,\n  title = {A again},\n  doi = {https://doi.org/10.1000/abc},\n"
        "  verified = {yesterday},\n}\n"
        "@book{lee2019book, title={B}, year={2019}}\n"
        "@unpublished{me2026draft, verified = {2026-01-02, research@0123abcd:paper/main.tex}}\n",
    )
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\begin{document}\n"
        "\\cite{smith2020ocean,smith2020oceans,lee2019book,me2026draft}\n"
        "\\bibliography{reference}\n"
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


# --- --all, CLI -------------------------------------------------------------------------------


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


def test_cli_exit_codes(thesis_check, repo_root, tmp_path, capsys):
    assert thesis_check.main(["--all", "--no-log"], root=repo_root) == 0
    assert thesis_check.main(["--main", "nope.tex"], root=repo_root) == 2
    write(tmp_path / "draft" / "main.tex", "\\documentclass{article}\n\\ref{sec:x}\n")
    assert thesis_check.main(["--no-log"], root=tmp_path) == 1
    capsys.readouterr()


@pytest.mark.parametrize(
    "tool",
    [
        "thesis_check.py",
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


def test_undefined_quantity_value_is_reported(thesis_check, tmp_path):
    write(tmp_path / "values.tex", VALUES_MACROS + "\\defvalue{s1-main-depth}{12.5}\n")
    write(
        tmp_path / "main.tex",
        "\\documentclass{article}\n\\input{values}\n\\begin{document}\n"
        "\\valqty{s1-main-depth}{\\metre} \\valqty {s1-main-width}{\\metre}\n\\end{document}\n",
    )

    e8 = of(thesis_check.run_checks(tmp_path, with_log=False), "E8")

    assert len(e8) == 1 and "'s1-main-width'" in e8[0].message
