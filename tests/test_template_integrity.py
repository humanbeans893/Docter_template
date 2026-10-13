"""Small sanity checks of the template that make check (tools/thesis_check.py E12) does not
cover: the research template agents copy, and the two lines they edit to wire a research in."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "draft"


def code_lines(path: Path) -> list[str]:
    """The lines of a TeX file without comments."""
    text = path.read_text(encoding="utf-8")
    return [re.sub(r"(?<!\\)%.*", "", line).strip() for line in text.splitlines()]


def test_research_template_is_complete():
    # Agents copy projects/_template to projects/<id>/ (AGENTS.md 研究を取り込む).
    assert (ROOT / "research.json").is_file()
    template = ROOT / "projects" / "_template"
    for name in ("README.md", "values.tex"):
        assert (template / name).is_file(), f"projects/_template/{name} is missing"
    for name in ("figures", "tables"):
        assert (template / name).is_dir(), f"projects/_template/{name}/ is missing"


def test_figures_are_found_in_draft_figures_and_projects():
    # Chapters write \includegraphics{<id>/figures/<name>}; the two documents agree.
    for name in ("preamble.tex", "supplementary.tex"):
        lines = [line for line in code_lines(DRAFT / name) if line.startswith("\\graphicspath")]
        assert lines == ["\\graphicspath{{figures/}{../projects/}}"], f"draft/{name}: {lines}"


def test_values_files_are_registered_above_one_marker():
    # Each research's values.tex is registered with \ThesisValues above this marker.
    text = (DRAFT / "values.tex").read_text(encoding="utf-8")
    assert text.count("% thesis:values:end") == 1
