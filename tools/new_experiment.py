#!/usr/bin/env python3
"""Create projects/<study>/experiments/NNN_<slug>/ from the study's template and index it.

    make experiment STUDY=study1 SLUG=baseline_fit [SUMMARY='question in a few words']
    make experiment-import STUDY=study1 SLUG=logger_drift SOURCE=logger-drift_runs_2026-07 \\
        [FROM=<path of the past files>] [LEGACY_ID=<repo>@<sha>:experiments/012_drift]
    python3 tools/new_experiment.py STUDY SLUG [--import [--source NAME] [--from PATH]
        [--legacy-id ID]] [--summary TEXT] [--date YYYY-MM-DD] [--dry-run]

NNN is one more than the highest number used by an experiment directory or a row of
experiments/EXP_SUMMARY.md or experiments/EXP_ARCHIVE.md. The copy of
experiments/_template/ (or, with --import, experiments/_import_template/) gets NNN_<slug>,
the study name, the date, the question (--summary) as the title of summary.md and
README.md and (import) the source name filled in, and the row
`| NNN | slug | (実行前) | 進行中 | — | 新規 |` (import: 由来 取り込み) is added at the end of
the table under the `| # | slug | 一行で | 状態 | 論文 | 由来 |` header of EXP_SUMMARY.md.

With --import the README gets this experiment's commands under 取り込み元とコマンド and the
card a 残りの手順 checklist, and the commands the USER runs on the host to copy the past
files into data/raw/legacy/<source>/ are printed (agents never write into data/raw/).
Every precondition is checked first; the directory appears only when everything is
written. Stdlib only, so it runs on the host (python3 3.10 or newer).
"""

import argparse
import datetime
import os
import re
import shlex
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# The host python3 runs this file; stop with one line instead of a TypeError on old ones.
if sys.version_info < (3, 10):  # noqa: UP036
    sys.exit(f"{Path(__file__).name}: needs python3 3.10 or newer, not {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parents[1]

STUDY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
SLUG_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")
MAX_SLUG_LENGTH = 40
# ruff's line-length (pyproject.toml): a long study name plus a long slug can push the
# run command in run.py past it.
LINE_LIMIT = 100
SOURCE_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
EXPERIMENT_DIR_RE = re.compile(r"(\d{3})_(.+)")
INDEX_ROW_RE = re.compile(r"^\|\s*(\d{3})\s*\|\s*([^|]*?)\s*\|")
INDEXES = ("EXP_SUMMARY.md", "EXP_ARCHIVE.md")
HEADER = ["#", "slug", "一行で", "状態", "論文", "由来"]
DATE_LINE_RE = re.compile(r"^(- \*\*日付\*\*: )YYYY-MM-DD", re.MULTILINE)
ORIGIN_LINE_RE = re.compile(r"^- \*\*元の実験\*\*:.*$", re.MULTILINE)
PLACE_LINE_RE = re.compile(r"^- \*\*元の場所\*\*:.*$", re.MULTILINE)
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
SKIP_NAMES = {".DS_Store"}
# The 一行で cell of a new row: the gist of the answer is written after the full run.
NO_SUMMARY = "(実行前)"
# The card: the experiment's current conclusion (AGENTS.md 実験).
CARD = "summary.md"
# The title line of the card and of the README after NNN_<slug> is filled: `--summary`
# replaces its placeholder (first match only).
CARD_TITLE_RE = re.compile(r"^(# \S+: )<[^<>\n]+>$", re.MULTILINE)
README_TITLE_RE = CARD_TITLE_RE
CARD_ORIGIN_RE = re.compile(r"^- 元の実験: .*$", re.MULTILINE)
RSYNC = (
    "rsync -a --copy-unsafe-links --exclude .git --exclude .venv --exclude __pycache__ "
    "--exclude .DS_Store --exclude '._*'"
)
RUN = "docker compose exec research-template uv run python"
COMMANDS_HEADING = "## 取り込み元とコマンド"
# The first line of that section in experiments/_import_template/README.md.
COMMANDS_INTRO = (
    "作成時に `tools/new_experiment.py` が書いたものです"
    "(ホストの絶対パスは書かず `<PATH>` とします)。"
)


class PlanError(Exception):
    """One or more preconditions failed; nothing has been written."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Plan:
    study: str
    name: str  # NNN_<slug>
    template_dir: Path
    target: Path
    index: Path
    index_text: str
    row: str
    source: str | None
    files: list[Path] = field(default_factory=list)


def show(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def skeleton_files(template_dir: Path, problems: list[str]) -> list[Path]:
    """Template files without caches or run outputs (out/ keeps only .gitkeep)."""
    files: list[Path] = []
    for path in sorted(template_dir.rglob("*")):
        relative = path.relative_to(template_dir)
        if SKIP_DIRS.intersection(relative.parts) or path.name in SKIP_NAMES:
            continue
        if path.is_symlink():
            problems.append(f"{relative.as_posix()}: the experiment template has a symlink")
            continue
        if path.is_dir() or path.suffix in {".pyc", ".pyo"}:
            continue
        if "out" in relative.parts[:-1] and path.name != ".gitkeep":
            continue
        files.append(relative)
    return files


def insert_row(text: str, row: str, label: str) -> str:
    """Append ``row`` to the table that starts at the unique EXP_SUMMARY header line."""
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if table_cells(line) == HEADER]
    if len(hits) != 1:
        header = "| " + " | ".join(HEADER) + " |"
        raise PlanError([f"{label}: expected the header '{header}' once, found {len(hits)}"])
    end = hits[0]
    while end + 1 < len(lines) and lines[end + 1].lstrip().startswith("|"):
        end += 1
    if not lines[end].endswith("\n"):
        lines[end] += "\n"
    return "".join(lines[: end + 1]) + row + "\n" + "".join(lines[end + 1 :])


def used_numbers(experiments_dir: Path) -> tuple[set[int], set[str]]:
    """Numbers and slugs taken by experiment directories and index rows."""
    numbers: set[int] = set()
    slugs: set[str] = set()
    for path in experiments_dir.iterdir():
        match = EXPERIMENT_DIR_RE.fullmatch(path.name)
        if match:
            numbers.add(int(match.group(1)))
            slugs.add(match.group(2))
    for name in INDEXES:
        index = experiments_dir / name
        if not index.is_file():
            continue
        for line in index.read_text(encoding="utf-8").splitlines():
            match = INDEX_ROW_RE.match(line)
            if match:
                numbers.add(int(match.group(1)))
                slugs.add(match.group(2))
    return numbers, slugs


def commands_block(study: str, name: str, source: str) -> str:
    """This experiment's commands under 取り込み元とコマンド. Never the host path: <PATH>."""
    raw = f"projects/{study}/data/raw/legacy/{source}"
    target = f"projects/{study}/experiments/{name}"
    return f"""\
- 取り込み元: `{raw}/`(`params.py` の `SOURCE_DIR`)
- コピー(利用者がホストの端末で実行する。エージェントは実行しない):

  ```bash
  mkdir -p {raw}
  {RSYNC} \\
    <PATH>/ {raw}/
  ```

- マニフェストの生成(raw を読むだけなので、エージェントが実行してよい):

  ```bash
  (cd {raw} && find . -type f ! -name .gitkeep -print0 \\
    | LC_ALL=C sort -z | xargs -0 sha256sum) > {target}/inputs.sha256
  ```

- 検証・再生成・照合(Docker の中で。smoke の後に本実行):

  ```bash
  {RUN} {target}/run.py --smoke
  {RUN} {target}/run.py
  ```
"""


def add_commands(readme: str, block: str) -> str:
    """Put the commands at the end of 取り込み元とコマンド, or add the whole section."""
    lines = readme.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip() == COMMANDS_HEADING]
    if starts:
        end = starts[0] + 1
        while end < len(lines) and not lines[end].startswith("## "):
            end += 1
        body = "".join(lines[:end]).rstrip("\n") + "\n\n" + block
        rest = "".join(lines[end:])
        return body + ("\n" + rest if rest else "")
    commands = block.rstrip("\n")
    section = f"{COMMANDS_HEADING}\n\n{COMMANDS_INTRO}\n\n{commands}\n"
    for i, line in enumerate(lines):
        if line.rstrip() == "## 訂正・追記":
            return "".join(lines[:i]) + section + "\n" + "".join(lines[i:])
    return readme.rstrip("\n") + "\n\n" + section


def set_origin(readme: str, legacy_id: str, label: str) -> str:
    line = f"- **元の実験**: `{legacy_id}`"
    if ORIGIN_LINE_RE.search(readme):
        return ORIGIN_LINE_RE.sub(lambda _: line, readme, count=1)
    if PLACE_LINE_RE.search(readme):
        return PLACE_LINE_RE.sub(lambda match: f"{match.group(0)}\n{line}", readme, count=1)
    raise PlanError([f"{label}: no '- **元の場所**:' or '- **元の実験**:' line to fill"])


def set_card_origin(card: str, legacy_id: str) -> str:
    line = f"- 元の実験: `{legacy_id}`(元の summary.md の状態と言えないことを確かめる)"
    text, count = CARD_ORIGIN_RE.subn(lambda _: line, card, count=1)
    if not count:
        raise PlanError([f"{CARD}: no '- 元の実験:' line to fill with --legacy-id"])
    return text


def set_title(text: str, title: str, label: str, pattern: re.Pattern = CARD_TITLE_RE) -> str:
    """Replace the placeholder of the `# NNN_<slug>: <...>` title line by ``title``."""
    text, count = pattern.subn(lambda match: match.group(1) + title, text, count=1)
    if not count:
        raise PlanError([f"{label}: no '# NNN_<slug>: <...>' title line to fill with --summary"])
    return text


def check_text(value: str | None, option: str, problems: list[str]) -> None:
    if value is not None and ("|" in value or "\n" in value or "\r" in value):
        problems.append(f"{option} must be one line without '|'")


def make_plan(args: argparse.Namespace, root: Path) -> Plan:
    study, slug = args.study, args.slug
    if study == "_template":
        raise PlanError(
            [
                "projects/_template is the template for new studies, not a study: create one "
                "with `TITLE='...' make study NAME=<study>` and add experiments there"
            ]
        )
    problems: list[str] = []
    if not STUDY_RE.fullmatch(study):
        problems.append(f"study name {study!r} is not a directory name under projects/")
    if not SLUG_RE.fullmatch(slug) or len(slug) > MAX_SLUG_LENGTH:
        problems.append(
            f"slug {slug!r} must be lower_snake_case ASCII (a-z, 0-9, _), at most "
            f"{MAX_SLUG_LENGTH} characters, e.g. baseline_fit"
        )
    if not args.import_ and (args.source or args.from_path or args.legacy_id):
        problems.append("--source, --from and --legacy-id belong to --import")
    source = None
    if args.import_:
        source = args.source or slug.replace("_", "-")
        if not SOURCE_RE.fullmatch(source):
            problems.append(
                f"source {source!r} must be lowercase letters, digits, '-' and '_' "
                "(e.g. logger-drift_runs_2026-07)"
            )
    check_text(args.summary, "--summary", problems)
    check_text(args.legacy_id, "--legacy-id", problems)
    if args.legacy_id is not None and ("`" in args.legacy_id or not args.legacy_id.strip()):
        problems.append("--legacy-id must be non-empty, without backquotes")
    if args.from_path is not None and ("\n" in args.from_path or "\r" in args.from_path):
        problems.append("--from must be one line")
    if problems:
        raise PlanError(problems)

    experiments_dir = root / "projects" / study / "experiments"
    template_dir = experiments_dir / ("_import_template" if args.import_ else "_template")
    index = experiments_dir / "EXP_SUMMARY.md"
    if not experiments_dir.is_dir():
        raise PlanError(
            [f"projects/{study}/experiments does not exist (create studies with make study)"]
        )
    for required in ("README.md", CARD):
        if not (template_dir / required).is_file():
            problems.append(f"{show(template_dir, root)}/{required} does not exist")
    if not index.is_file():
        raise PlanError([*problems, f"{show(index, root)} does not exist"])

    numbers, slugs = used_numbers(experiments_dir)
    if slug in slugs:
        problems.append(f"slug {slug!r} is already used in projects/{study}/experiments")
    number = max(numbers, default=0) + 1
    if number > 999:
        problems.append("experiment numbers have three digits and 999 is used")
    name = f"{number:03d}_{slug}"
    target = experiments_dir / name
    if target.exists():
        problems.append(f"{show(target, root)} already exists")

    # The summary and the legacy id go into summary.md and README.md, never into the row:
    # 一行で holds the gist of the answer once the experiment has one.
    origin = "取り込み" if args.import_ else "新規"
    row = f"| {number:03d} | {slug} | {NO_SUMMARY} | 進行中 | — | {origin} |"
    index_text = index.read_text(encoding="utf-8")
    try:
        index_text = insert_row(index_text, row, show(index, root))
    except PlanError as exc:
        problems.extend(exc.problems)
    plan = Plan(study, name, template_dir, target, index, index_text, row, source)
    if template_dir.is_dir():
        plan.files = skeleton_files(template_dir, problems)
    if problems:
        raise PlanError(problems)
    return plan


def render(plan: Plan, relative: Path, text: str, args: argparse.Namespace, date: str) -> str:
    text = text.replace("NNN_<slug>", plan.name).replace("<study>", plan.study)
    if plan.source is not None:
        text = text.replace("<source>", plan.source)
    summary = (args.summary or "").strip()
    legacy_id = (args.legacy_id or "").strip()
    if relative.as_posix() == "README.md":
        text = DATE_LINE_RE.sub(lambda match: match.group(1) + date, text)
        if summary:
            text = set_title(text, summary, "README.md", README_TITLE_RE)
        if plan.source is not None:
            if legacy_id:
                text = set_origin(text, legacy_id, "README.md")
            text = add_commands(text, commands_block(plan.study, plan.name, plan.source))
    elif relative.as_posix() == CARD:
        if summary:
            text = set_title(text, summary, CARD)
        if plan.source is not None and legacy_id:
            text = set_card_origin(text, legacy_id)
    return text


def long_lines(text: str) -> int:
    return sum(len(line) > LINE_LIMIT for line in text.splitlines())


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    if path.exists():
        shutil.copymode(path, tmp)
    os.replace(tmp, path)


def apply(plan: Plan, contents: dict[Path, str | None]) -> None:
    """Build the directory beside its target, update the index, then move it into place."""
    staging = Path(tempfile.mkdtemp(prefix=f".{plan.name}.", suffix=".tmp", dir=plan.target.parent))
    original = plan.index.read_bytes()
    index_written = False
    try:
        for relative, text in contents.items():
            source, destination = plan.template_dir / relative, staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if text is None:
                shutil.copy2(source, destination)
            else:
                destination.write_text(text, encoding="utf-8")
                shutil.copymode(source, destination)
        (staging / "out").mkdir(exist_ok=True)
        (staging / "out" / ".gitkeep").touch()
        index_written = True
        write_atomic(plan.index, plan.index_text.encode("utf-8"))
        os.replace(staging, plan.target)
    except BaseException:
        if index_written:
            write_atomic(plan.index, original)
        shutil.rmtree(staging, ignore_errors=True)
        raise


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("study", help="study directory under projects/ (e.g. study1)")
    parser.add_argument("slug", help="lower_snake_case, e.g. baseline_fit")
    parser.add_argument(
        "--import",
        dest="import_",
        action="store_true",
        help="import a past result (experiments/_import_template; 由来 取り込み)",
    )
    parser.add_argument(
        "--source",
        help="name under data/raw/legacy/ for the past files (default: the slug with - for _)",
    )
    parser.add_argument(
        "--from",
        dest="from_path",
        help="where the past files are now (only printed in the user's copy command)",
    )
    parser.add_argument(
        "--legacy-id",
        help=(
            "the old experiment id for README and summary.md, <repo>@<sha>:experiments/NNN_x "
            "(older research-template: exp/NNN_x)"
        ),
    )
    parser.add_argument(
        "--summary", help="the question in a few words: the title of summary.md and README.md"
    )
    parser.add_argument(
        "--date",
        type=datetime.date.fromisoformat,
        default=None,
        help="date written into the README, YYYY-MM-DD (default: today)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    args = parse_args(argv)
    try:
        plan = make_plan(args, root)
        date = (args.date or datetime.date.today()).isoformat()
        contents: dict[Path, str | None] = {}
        for relative in plan.files:
            if relative.suffix in {".md", ".py"}:
                text = (plan.template_dir / relative).read_text(encoding="utf-8")
                contents[relative] = render(plan, relative, text, args, date)
                if relative.suffix == ".py" and long_lines(contents[relative]) > long_lines(text):
                    where = f"{plan.study}/experiments/{plan.name}/{relative.as_posix()}"
                    raise PlanError(
                        [f"{where} would get a line over {LINE_LIMIT} characters: shorten the slug"]
                    )
            else:
                contents[relative] = None
    except PlanError as exc:
        print("error: nothing was written:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    target = show(plan.target, root)
    print(f"New experiment {target}/ from {show(plan.template_dir, root)}/")
    print(f"  index row in {show(plan.index, root)}:")
    print(f"    {plan.row}")
    if args.dry_run:
        print("Dry run: nothing was written.")
    else:
        try:
            apply(plan, contents)
        except Exception as exc:
            print(f"error: {exc}; nothing was changed", file=sys.stderr)
            return 1
        print(f"Created {target}/ and its index row.")

    run = f"{RUN} {target}/run.py"
    if plan.source is None:
        print("Next:")
        print(
            "  1. Write 問い and 判定の規則 in summary.md and set params.py (SEED, PARAMS, SMOKE);"
        )
        print("     commit them with run.py and any changed code before the full run.")
        print(f"  2. Smoke run: {run} --smoke")
        print(f"  3. Full run:  {run}")
        return 0
    raw = f"projects/{plan.study}/data/raw/legacy/{plan.source}"
    origin = "<PATH>/"
    if args.from_path:
        origin = shlex.quote(args.from_path.rstrip("/") + "/")
    print()
    print("1. The USER copies the past files on the host (agents never run this; data/raw/ is")
    print("   read-only in Docker and protected by the hook):")
    print(f"     mkdir -p {raw}")
    print(f"     {RSYNC} {origin} {raw}/")
    print("2. Generate the manifest (reads raw only, an agent may run it):")
    print(
        f"     (cd {raw} && find . -type f ! -name .gitkeep -print0 | LC_ALL=C sort -z "
        f"| xargs -0 sha256sum) > {target}/inputs.sha256"
    )
    print(f"3. Fill the 由来 section of {target}/README.md (ask the user; never an absolute")
    print(f"   host path) and add a legacy entry to projects/{plan.study}/data/README.md.")
    print("4. Implement run.py and run it with --smoke; then commit run.py, params.py,")
    print("   inputs.sha256 and any changed code, and run it without --smoke:")
    print(f"     {run} --smoke")
    print(f"     {run}")
    print(f"Tick 残りの手順 in {target}/summary.md as you go.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
