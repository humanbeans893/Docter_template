"""Every study's helpers and experiment templates are still copies of projects/_template's.

tests/study_kit/ tests projects/_template's src/utils/ and experiments/{_template,
_import_template}/ once. That covers every study only while each study's copies equal the
template's: byte for byte in src/utils/ (a study may add modules of its own there), and in the
experiment templates after the <study> substitution tools/new_study.py does (study_text).
"""

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "projects" / "_template"
STUDIES = sorted(
    path.parent for path in (ROOT / "projects").glob("*/config.py") if path.parent != TEMPLATE
)
UTILS = ("src", "utils")
COPIED = (UTILS, ("experiments", "_template"), ("experiments", "_import_template"))
FIX = (
    "Helpers and experiment templates are changed in projects/_template first (tests/study_kit/ "
    "tests them there), then copied to every study. A change made only in a study belongs in "
    "projects/_template too"
)


@pytest.fixture(scope="module")
def new_study(load_module_by_path):
    return load_module_by_path(ROOT / "tools" / "new_study.py", "new_study_for_copies")


def copied_files(new_study, study: Path) -> set[Path]:
    """The files make study copies into these areas (no caches or experiment outputs).

    Only these areas are walked: a study's data/, result/ and experiment outputs may be
    large or hold symlinks to storage elsewhere, and none of them is a copy.
    """
    files: set[Path] = set()
    problems: list[str] = []
    for area in COPIED:
        if study.joinpath(*area).is_dir():
            files.update(new_study.skeleton_files(study, problems, under=Path(*area)))
    assert not problems, "make study copies files, not symlinks:\n" + "\n".join(problems)
    return files


def plan_for(new_study, template: Path, study: Path):
    return new_study.Plan(
        name=study.name,
        readme_title="<Study title>",  # the copied areas never name the study's title
        chapter_title=None,
        chapter_number=None,
        template_dir=template,
        study_dir=study,
    )


def drift(new_study, template: Path, study: Path) -> list[str]:
    """How ``study``'s copies differ from ``template``'s, one line each with the fix."""
    plan = plan_for(new_study, template, study)
    expected = copied_files(new_study, template)
    present = copied_files(new_study, study)
    problems: list[str] = []
    for relative in sorted(expected):
        source = f"projects/{template.name}/{relative.as_posix()}"
        target = f"projects/{study.name}/{relative.as_posix()}"
        if relative not in present:
            problems.append(f"{target} is missing: copy {source} there")
            continue
        text = new_study.study_text(plan, relative)
        wanted = (template / relative).read_bytes() if text is None else text.encode("utf-8")
        if (study / relative).read_bytes() != wanted:
            filled = "" if text is None else f" with <study> = {study.name}"
            problems.append(f"{target} differs from {source}: copy {source} there{filled}")
    for relative in sorted(present - expected):
        if relative.parts[:2] != UTILS:  # a study may add modules of its own to src/utils/
            problems.append(
                f"projects/{study.name}/{relative.as_posix()} is not in "
                f"projects/{template.name}: add it there or remove it"
            )
    return problems


@pytest.mark.parametrize("study", STUDIES, ids=lambda path: path.name)
def test_helpers_and_experiment_templates_are_copies_of_the_template(new_study, study: Path):
    problems = drift(new_study, TEMPLATE, study)
    assert not problems, f"{FIX}:\n" + "\n".join(f"  - {problem}" for problem in problems)


def test_drift_is_reported_file_by_file(new_study, tmp_path: Path):
    template = tmp_path / "projects" / "_template"
    for area in COPIED:
        shutil.copytree(TEMPLATE.joinpath(*area), template.joinpath(*area))
    study = tmp_path / "projects" / "demo"
    plan = plan_for(new_study, template, study)
    for relative in copied_files(new_study, template):  # as make study copies them
        target = study / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        text = new_study.study_text(plan, relative)
        if text is None:
            shutil.copyfile(template / relative, target)
        else:
            target.write_text(text, encoding="utf-8")
    (study / "src" / "utils" / "geodesy.py").write_text("R = 6371.0\n", encoding="utf-8")
    assert drift(new_study, template, study) == []

    (study / "src" / "utils" / "figures.py").write_text("# edited here only\n", encoding="utf-8")
    (study / "experiments" / "_template" / "run.py").unlink()
    (study / "experiments" / "_template" / "notes.md").write_text("x\n", encoding="utf-8")
    run_py = template / "experiments" / "_import_template" / "run.py"
    run_py.write_text(run_py.read_text(encoding="utf-8") + "# <study>\n", encoding="utf-8")

    assert drift(new_study, template, study) == [
        "projects/demo/experiments/_import_template/run.py differs from "
        "projects/_template/experiments/_import_template/run.py: copy "
        "projects/_template/experiments/_import_template/run.py there with <study> = demo",
        "projects/demo/experiments/_template/run.py is missing: copy "
        "projects/_template/experiments/_template/run.py there",
        "projects/demo/src/utils/figures.py differs from projects/_template/src/utils/figures.py: "
        "copy projects/_template/src/utils/figures.py there",
        "projects/demo/experiments/_template/notes.md is not in projects/_template: add it there "
        "or remove it",
    ]
