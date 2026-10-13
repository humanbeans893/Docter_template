#!/usr/bin/env python3
"""Create a study from projects/_template/ and register it with the thesis.

    TITLE='Study 2: Effects' make study NAME=study2
    python3 tools/new_study.py study2 --title "Study 2: Effects" [--dry-run]
    python3 tools/new_study.py study2 --title-tex 'Effects of \\(\\alpha\\)'
    python3 tools/new_study.py synthesis --no-chapter

It does, all or nothing:
  1. copies the skeleton of projects/_template/ to projects/NAME/ (code, documents,
     experiment templates, the starter tests/; no data, results or outputs), drops the
     template-only blocks of its Markdown files and fills <study> / <Study title> in
     README.md, data/README.md and experiments/;
  2. writes draft/chapters/NN-NAME.tex from draft/chapters/_chapter-template.tex
     (NN = next creation number; the printed chapter order is main.tex's order);
  3. adds \\include{chapters/NN-NAME} above `% thesis:study-chapters:end` in draft/main.tex;
  4. appends {../projects/NAME/result/figures/} to the one-line \\graphicspath of
     draft/preamble.tex and draft/supplementary.tex;
  5. adds the read-only bind mount of projects/NAME/data/raw above
     `# thesis:raw-mounts:end` in docker-compose.yml;
  6. adds a row for ch:NAME before the conclusion row of the chapter map in
     docs/thesis-plan.md.
--no-chapter (a study whose results feed other chapters) skips 2, 3 and 6.

The study's tests/ holds its own tests (test_study_config.py to start). The helpers in
src/utils/ and the experiment templates stay copies of projects/_template's: they are
tested once in tests/study_kit/, and tests/test_study_copies.py checks every copy.

Every precondition is checked before anything is written; a failure while writing
restores every file. --dry-run prints the plan and writes nothing. Stdlib only, so it
runs on the host (python3 3.10 or newer).
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# The host python3 runs this file; stop with one line instead of a TypeError on old ones.
if sys.version_info < (3, 10):  # noqa: UP036
    sys.exit(f"{Path(__file__).name}: needs python3 3.10 or newer, not {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parents[1]

NAME_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
MAX_NAME_LENGTH = 40
CHAPTER_MARKER = "% thesis:study-chapters:end"
MOUNT_MARKER = "# thesis:raw-mounts:end"
CONCLUSION_FILE = "chapters/99-conclusion.tex"
# The experiment index of every study (tools/new_experiment.py inserts rows under it).
INDEX_HEADER = ["#", "slug", "一行で", "状態", "論文", "由来"]
TEX_BLOCK_BEGIN = "% template-only:begin"
TEX_BLOCK_END = "% template-only:end"
MD_BLOCK = re.compile(
    r"<!-- template-only:begin -->.*?<!-- template-only:end -->[ \t]*\n(?:[ \t]*\n)?",
    re.DOTALL,
)
GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)*)\}")
# Caches and editor state never belong in a new study.
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
SKIP_NAMES = {".DS_Store"}
LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
# Columns of the chapter map in docs/thesis-plan.md filled for a new chapter.
PLAN_DEFAULTS = {"研究段階": "構想", "執筆状況": "構想"}


class PlanError(Exception):
    """One or more preconditions failed; nothing has been written."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Plan:
    name: str
    readme_title: str
    chapter_title: str | None  # LaTeX; None with --no-chapter
    chapter_number: str | None
    template_dir: Path
    study_dir: Path
    files: list[Path] = field(default_factory=list)  # relative to template_dir
    writes: dict[Path, str] = field(default_factory=dict)  # new or edited file -> content
    steps: list[str] = field(default_factory=list)


def strip_comments(line: str) -> str:
    """Drop everything from the first unescaped ``%`` (same offsets as ``line``)."""
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "%":
            return line[:i]
        i += 1
    return line


def escape_latex(text: str) -> str:
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


def braces_balanced(text: str) -> bool:
    depth = 0
    i = 0
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth < 0:
            return False
        i += 1
    return depth == 0


def show(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def skeleton_files(template_dir: Path, problems: list[str], under: Path = Path()) -> list[Path]:
    """Files a new study starts with: code, documents and templates; no data or outputs.

    ``under`` walks only that part of ``template_dir``; the paths stay relative to
    ``template_dir`` (tests/test_study_copies.py walks only a study's copied areas).
    """
    files: list[Path] = []
    for path in sorted((template_dir / under).rglob("*")):
        relative = path.relative_to(template_dir)
        parts = relative.parts
        if SKIP_DIRS.intersection(parts) or path.name in SKIP_NAMES:
            continue
        if path.is_symlink():
            problems.append(f"{show(path, template_dir.parents[1])}: the template has a symlink")
            continue
        if path.is_dir() or path.suffix in {".pyc", ".pyo"}:
            continue
        if "out" in parts[:-1] and path.name != ".gitkeep":
            continue  # experiment outputs
        if parts[0] in {"data", "result"} and path.name not in {".gitkeep", "README.md"}:
            continue  # data and generated results stay with their study
        files.append(relative)
    return files


def fill_placeholders(relative: Path) -> bool:
    """Only the study's own documents and experiment templates name the study."""
    posix = relative.as_posix()
    return posix in {"README.md", "data/README.md"} or (
        relative.parts[0] == "experiments" and relative.suffix in {".md", ".py"}
    )


def transform(relative: Path, text: str, plan: Plan) -> str:
    if relative.suffix == ".md":
        text = MD_BLOCK.sub("", text)
    if fill_placeholders(relative):
        text = text.replace("<study>", plan.name).replace("<Study title>", plan.readme_title)
    return text


def chapter_text(template: str, name: str, title: str, problems: list[str]) -> str:
    lines: list[str] = []
    skipping = False
    for line in template.splitlines(keepends=True):
        stripped = line.strip()
        if stripped == TEX_BLOCK_BEGIN:
            skipping = True
        elif stripped == TEX_BLOCK_END:
            skipping = False
        elif not skipping:
            lines.append(line)
    if skipping:
        problems.append(f"draft/chapters/_chapter-template.tex: '{TEX_BLOCK_BEGIN}' is not closed")
    return "".join(lines).replace("<study>", name).replace("<Study title>", title)


def insert_above_marker(text: str, marker: str, new_lines: list[str], label: str) -> str:
    """Insert ``new_lines`` above the unique marker line, with the marker's indentation."""
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if marker in line]
    if len(hits) != 1:
        raise PlanError([f"{label}: expected one line with '{marker}', found {len(hits)}"])
    at = hits[0]
    indent = re.match(r"[ \t]*", lines[at]).group(0)
    block = "".join(f"{indent}{line}\n" for line in new_lines)
    return "".join(lines[:at]) + block + "".join(lines[at:])


def add_graphicspath(text: str, entry: str, label: str) -> str:
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if "\\graphicspath" in strip_comments(line)]
    if len(hits) != 1:
        raise PlanError([f"{label}: expected one \\graphicspath line, found {len(hits)}"])
    line = lines[hits[0]]
    match = GRAPHICSPATH_RE.search(strip_comments(line))
    if match is None:
        raise PlanError([f"{label}: the \\graphicspath{{...}} must be complete on one line"])
    if f"{{{entry}}}" in match.group(1):
        raise PlanError([f"{label}: \\graphicspath already lists {entry}"])
    closing = match.end() - 1
    lines[hits[0]] = f"{line[:closing]}{{{entry}}}{line[closing:]}"
    return "".join(lines)


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def add_plan_row(text: str, values: dict[str, str], label: str) -> str:
    """Insert a chapter-map row before the row whose ファイル cell is the conclusion."""
    lines = text.splitlines(keepends=True)
    hits: list[tuple[int, list[str]]] = []
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|") or CONCLUSION_FILE not in line:
            continue
        top = i
        while top > 0 and lines[top - 1].lstrip().startswith("|"):
            top -= 1
        header = table_cells(lines[top])
        cells = table_cells(line)
        if "ファイル" in header and top != i:
            column = header.index("ファイル")
            if column < len(cells) and CONCLUSION_FILE in cells[column]:
                hits.append((i, header))
    if len(hits) != 1:
        raise PlanError(
            [
                f"{label}: expected one table row whose ファイル cell is {CONCLUSION_FILE}, "
                f"found {len(hits)}"
            ]
        )
    at, header = hits[0]
    row = "| " + " | ".join(values.get(name, "") for name in header) + " |\n"
    return "".join(lines[:at]) + row + "".join(lines[at:])


def read(path: Path, root: Path, problems: list[str]) -> str | None:
    if not path.is_file():
        problems.append(f"{show(path, root)} does not exist")
        return None
    return path.read_text(encoding="utf-8")


def plan_edit(plan: Plan, path: Path, root: Path, problems: list[str], edit, step: str) -> None:
    """Apply ``edit`` to the planned content of ``path``, collecting refusals."""
    text = plan.writes.get(path)
    if text is None:
        text = read(path, root, problems)
    if text is None:
        return
    try:
        plan.writes[path] = edit(text)
    except PlanError as exc:
        problems.extend(exc.problems)
        return
    plan.steps.append(f"edit   {show(path, root)}: {step}")


def make_plan(args: argparse.Namespace, root: Path) -> Plan:
    name = args.name
    if name == "_template":
        raise PlanError(["_template is the template itself; choose a name such as study2"])
    if not NAME_RE.fullmatch(name) or len(name) > MAX_NAME_LENGTH:
        raise PlanError(
            [
                f"study name {name!r} must be lower_snake_case ASCII starting with a letter "
                f"(at most {MAX_NAME_LENGTH} characters), e.g. study2 or coastal_mixing"
            ]
        )
    problems: list[str] = []
    title = args.title if args.title is not None else args.title_tex
    if title is not None:
        if not title.strip():
            problems.append("the title is empty")
        if "|" in title or "\n" in title or "\r" in title:
            problems.append("the title must be one line without '|' (it goes into tables)")
        if args.title_tex is not None and not braces_balanced(title):
            problems.append("--title-tex has unbalanced braces")
    elif not args.no_chapter:
        problems.append(
            "give --title (or --title-tex), or --no-chapter for a study without a chapter"
        )
    if problems:
        raise PlanError(problems)

    projects = root / "projects"
    draft = root / "draft"
    chapter = not args.no_chapter
    chapter_title = None
    if chapter:
        chapter_title = escape_latex(args.title) if args.title is not None else args.title_tex
    plan = Plan(
        name=name,
        readme_title=(title or name).strip(),
        chapter_title=chapter_title.strip() if chapter_title else None,
        chapter_number=None,
        template_dir=projects / "_template",
        study_dir=projects / name,
    )

    if plan.study_dir.exists():
        problems.append(f"projects/{name} already exists")
    if not plan.template_dir.is_dir():
        problems.append("projects/_template does not exist")
    else:
        experiments_dir = plan.template_dir / "experiments"
        if not experiments_dir.is_dir():
            problems.append("projects/_template/experiments does not exist")
        else:
            numbered = sorted(
                p.name for p in experiments_dir.iterdir() if re.match(r"\d{3}_", p.name)
            )
            if numbered:
                problems.append(
                    f"projects/_template/experiments has experiments ({', '.join(numbered)}); "
                    "the template must stay empty -- move them to a study"
                )
            index = experiments_dir / "EXP_SUMMARY.md"
            found = 0
            if index.is_file():
                lines = index.read_text(encoding="utf-8").splitlines()
                found = sum(table_cells(line) == INDEX_HEADER for line in lines)
            if found != 1:
                problems.append(
                    "projects/_template/experiments/EXP_SUMMARY.md must have the header "
                    f"'| {' | '.join(INDEX_HEADER)} |' once (found {found}): make experiment adds "
                    "rows there"
                )
        plan.files = skeleton_files(plan.template_dir, problems)
    plan.steps.append(f"create projects/{name}/ ({len(plan.files)} files from projects/_template/)")

    figures_entry = f"../projects/{name}/result/figures/"
    if chapter:
        chapters = draft / "chapters"
        numbers = [
            int(path.name[:2])
            for path in chapters.glob("[0-9][0-9]-*.tex")
            if path.name[:2] != "99"
        ]
        number = max(numbers, default=0) + 1
        if number >= 99:
            problems.append("no chapter number left below 99 (draft/chapters/99-*.tex)")
        plan.chapter_number = f"{number:02d}"
        chapter_file = f"chapters/{plan.chapter_number}-{name}.tex"
        chapter_path = draft / chapter_file
        if chapter_path.exists():
            problems.append(f"draft/{chapter_file} already exists")
        template = read(chapters / "_chapter-template.tex", root, problems)
        if template is not None:
            plan.writes[chapter_path] = chapter_text(template, name, plan.chapter_title, problems)
            plan.steps.append(f"create draft/{chapter_file} (from _chapter-template.tex)")
        include = f"\\include{{{chapter_file[:-4]}}}"
        plan_edit(
            plan,
            draft / "main.tex",
            root,
            problems,
            lambda text: insert_above_marker(text, CHAPTER_MARKER, [include], "draft/main.tex"),
            f"{include} above {CHAPTER_MARKER}",
        )
    for tex in ("preamble.tex", "supplementary.tex"):
        plan_edit(
            plan,
            draft / tex,
            root,
            problems,
            lambda text, tex=tex: add_graphicspath(text, figures_entry, f"draft/{tex}"),
            f"\\graphicspath += {{{figures_entry}}}",
        )

    raw = f"projects/{name}/data/raw"

    def add_mount(text: str) -> str:
        if re.search(rf"\./{re.escape(raw)}(?:\s*$|:)", text, flags=re.MULTILINE):
            raise PlanError([f"docker-compose.yml already mounts ./{raw}"])
        block = [
            "- type: bind",
            f"  source: ./{raw}",
            f"  target: /workspace/{raw}",
            "  read_only: true",
            "  bind:",
            "    create_host_path: false",
        ]
        return insert_above_marker(text, MOUNT_MARKER, block, "docker-compose.yml")

    plan_edit(
        plan, root / "docker-compose.yml", root, problems, add_mount, f"read-only mount of {raw}"
    )
    if chapter:
        values = {
            "章ラベル": f"`ch:{name}`",
            "ファイル": f"`chapters/{plan.chapter_number}-{name}.tex`",
            "スタディ": f"`projects/{name}`",
            **PLAN_DEFAULTS,
        }
        plan_edit(
            plan,
            root / "docs" / "thesis-plan.md",
            root,
            problems,
            lambda text: add_plan_row(text, values, "docs/thesis-plan.md"),
            f"chapter-map row for ch:{name} above the conclusion",
        )
    if problems:
        raise PlanError(problems)
    return plan


def write_atomic(path: Path, data: bytes) -> None:
    """Write via ``<file>.tmp`` + ``os.replace`` so a reader never sees half a file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


def study_text(plan: Plan, relative: Path) -> str | None:
    """The text projects/NAME/<relative> starts with; None for a file copied byte for byte.

    tests/test_study_copies.py compares every study's helpers and experiment templates with
    this, so they stay what this tool would copy today.
    """
    if relative.suffix == ".md" or fill_placeholders(relative):
        return transform(relative, (plan.template_dir / relative).read_text(encoding="utf-8"), plan)
    return None


def build_study(plan: Plan, target: Path) -> None:
    for relative in plan.files:
        source = plan.template_dir / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        text = study_text(plan, relative)
        if text is not None:
            destination.write_text(text, encoding="utf-8")
            shutil.copymode(source, destination)
        else:
            shutil.copy2(source, destination)


def apply(plan: Plan) -> None:
    """Write everything; on any failure restore the edited files and remove the new ones."""
    staging = Path(
        tempfile.mkdtemp(prefix=f".{plan.name}.", suffix=".tmp", dir=plan.study_dir.parent)
    )
    journal: list[tuple[Path, bytes | None]] = []
    try:
        build_study(plan, staging)
        for path, text in plan.writes.items():
            journal.append((path, path.read_bytes() if path.exists() else None))
            write_atomic(path, text.encode("utf-8"))
        os.replace(staging, plan.study_dir)
    except BaseException:
        for path, original in reversed(journal):
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    write_atomic(path, original)
            except OSError as exc:
                print(f"warning: could not restore {path}: {exc}", file=sys.stderr)
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("name", help="study name, lower_snake_case (e.g. study2)")
    titles = parser.add_mutually_exclusive_group()
    titles.add_argument("--title", help="chapter title as plain text (LaTeX-escaped)")
    titles.add_argument("--title-tex", help="chapter title as LaTeX, inserted unchanged")
    parser.add_argument(
        "--no-chapter",
        action="store_true",
        help="no chapter of its own (registers figures and the raw mount only)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    args = parse_args(argv)
    try:
        plan = make_plan(args, root)
    except PlanError as exc:
        print("error: nothing was written:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    heading = f"New study '{plan.name}'"
    if plan.chapter_number:
        heading += f" (chapter file {plan.chapter_number}: {plan.chapter_title})"
    else:
        heading += " (no chapter)"
    print(heading)
    for step in plan.steps:
        print(f"  {step}")
    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0

    try:
        apply(plan)
    except Exception as exc:
        print(f"error: {exc}; every change was rolled back", file=sys.stderr)
        return 1

    raw = f"projects/{plan.name}/data/raw"
    print(f"Created projects/{plan.name}/ and registered it with the thesis.")
    print("Next:")
    print(
        "  1. Check that no job is running (docker compose top, STATE.md, "
        "projects/*/experiments/JOBS.md),"
    )
    print(f"     then run `make up` (docker compose up -d) to mount {raw} read-only.")
    print(f"  2. make test (tests of the study's own code go to projects/{plan.name}/tests/;")
    print("     its src/utils/ helpers and experiment templates are tested in tests/study_kit/)")
    if plan.chapter_number:
        print(
            f"  3. Fill in projects/{plan.name}/README.md and the ch:{plan.name} row of "
            "docs/thesis-plan.md."
        )
    else:
        print(
            f"  3. Fill in projects/{plan.name}/README.md (which chapters use its results) and "
            "docs/thesis-plan.md."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
