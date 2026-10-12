"""Checks the handoff structure that lets Claude Code and Codex resume from files alone.

See AGENTS.md (セッション状態と引き継ぎ, 実験). Only what can be enforced mechanically is
checked: the handoff documents exist, the always-read ones stay within their character
budgets and their index rows stay short, every study's experiment directories match its
index one to one, each experiment's card (summary.md) is short and says the status of its
index row, the experiment procedure is the same in every study, both agents can load the
skills and the mirrored ones agree, the docs use this repository's conventions instead of
research-template's, and experiment outputs stay out of git.
"""

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUDIES = sorted(path.parent for path in (ROOT / "projects").glob("*/config.py"))


def _load_thesis_check():
    """tools/thesis_check.py, whose W14 reads the same status words this file checks."""
    spec = importlib.util.spec_from_file_location(
        "thesis_check_for_repo_structure", ROOT / "tools" / "thesis_check.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_thesis_check = _load_thesis_check()
# The status words (AGENTS.md 実験), defined once in tools/thesis_check.py: the index's 状態
# cell and the card's 状態 line start with one of them.
STATUSES = _thesis_check.STATUS_WORDS
status_word = _thesis_check.status_word
OPEN = _thesis_check.OPEN_STATUS

HANDOFF_DOCUMENTS = (
    "AGENTS.md",
    "CLAUDE.md",
    "STATE.md",
    "docs/thesis-plan.md",
    "docs/guardrails.md",
    "docs/ideas.md",
    "docs/launch-checklist.md",
    "docs/research-log.md",
    "docs/importing-past-results.md",
    "docs/feedback/_template.md",
)
EXPERIMENT_TEMPLATES = ("_template", "_import_template")
STUDY_EXPERIMENT_FILES = (
    "experiments/README.md",
    "experiments/EXP_SUMMARY.md",
    "experiments/EXP_ARCHIVE.md",
    "experiments/JOBS.md",
    *(
        f"experiments/{template}/{name}"
        for template in EXPERIMENT_TEMPLATES
        for name in ("README.md", "summary.md", "run.py", "params.py", "out/.gitkeep")
    ),
)

# Character budgets of the files read at the start of every session (AGENTS.md,
# セッション状態と引き継ぎ). Characters, not lines: long lines defeat a line count.
ALWAYS_READ_BUDGETS = {
    ROOT / "STATE.md": 6_000,
    ROOT / "docs" / "thesis-plan.md": 8_000,
    ROOT / "docs" / "guardrails.md": 8_000,
    **{study / "experiments" / "EXP_SUMMARY.md": 10_000 for study in STUDIES},
}
# One experiment per index row; its detail belongs in the experiment's summary.md or README.md.
INDEX_ROW_MAX_CHARS = 200

# The experiment index (EXP_SUMMARY.md) and its archive (EXP_ARCHIVE.md) share one table.
INDEX_FILES = ("EXP_SUMMARY.md", "EXP_ARCHIVE.md")
INDEX_HEADER = "| # | slug | 一行で | 状態 | 論文 | 由来 |"
INDEX_SEPARATOR = re.compile(r"\|(?:\s*:?-{3,}:?\s*\|){6}")
INDEX_ROW = re.compile(r"^\|\s*[0-9]+\s*\|")
EXPERIMENT_NAME = re.compile(r"[0-9]{3}_[a-z0-9]+(?:_[a-z0-9]+)*")
# 由来: new, an import in progress, or a closed import with its reproducibility.
ORIGIN = re.compile(r"新規|取り込み(?:\(R[123](?:\+R[123])*\))?")
OPEN_IMPORT = "取り込み"
OPEN_IMPORT_STATUSES = (OPEN, "中止")

# Each experiment's card: its current conclusion, read before an experiment is relied on.
CARD = "summary.md"
CARD_MAX_LINES = 50
CARD_MAX_CHARS = 3_000
CARD_STATUS = re.compile(r"^- \*\*状態\*\*:(.*)$", re.MULTILINE)
PLACEHOLDER = re.compile(r"<[^<>\n]+>")
OPEN_STEPS = re.compile(r"^## 残りの手順\s*$", re.MULTILINE)

# Claude Code reads .claude/skills/, Codex reads .agents/skills/.
SKILL_DIRS = (ROOT / ".claude" / "skills", ROOT / ".agents" / "skills")
MIRRORED_SKILLS = ("write-handoff", "import-results", "thesis-check", "research-log")

# research-template conventions that do not exist here (AGENTS.md, 単一の正本): decision
# records are docs/decisions/NNNN-<slug>.md from _adr-template.md, research logs are entries
# in docs/research-log.md, and there is no docs/templates/.
FOREIGN_CONVENTIONS = re.compile(r"decision-(?:NNN|[0-9]{3})|docs/templates/")


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:  # a fixture outside the repository
        return path.as_posix()


def study_id(study: Path) -> str:
    return study.name


def test_every_study_is_found() -> None:
    names = [study.name for study in STUDIES]
    assert "_template" in names, f"projects/_template/config.py is missing (found {names})"


def test_handoff_documents_exist() -> None:
    missing = [path for path in HANDOFF_DOCUMENTS if not (ROOT / path).is_file()]
    assert not missing, f"Missing handoff documents: {missing}"


@pytest.mark.parametrize("study", STUDIES, ids=study_id)
def test_study_has_the_experiment_skeleton(study: Path) -> None:
    missing = [path for path in STUDY_EXPERIMENT_FILES if not (study / path).is_file()]
    assert not missing, f"projects/{study.name} is missing {missing} (copy them from _template)"


@pytest.mark.parametrize(
    ("path", "budget"), ALWAYS_READ_BUDGETS.items(), ids=[rel(p) for p in ALWAYS_READ_BUDGETS]
)
def test_always_read_documents_stay_within_budget(path: Path, budget: int) -> None:
    n_chars = len(path.read_text(encoding="utf-8"))
    assert n_chars <= budget, (
        f"{rel(path)} has {n_chars} characters (budget {budget}, read every session; long "
        "lines do not help): move detail to the files it links to (older decisions to "
        "docs/research-log.md or docs/decisions/, an experiment's detail to its summary.md or "
        "README.md, EXP_SUMMARY.md rows of finished experiments the thesis does not use to "
        "EXP_ARCHIVE.md)"
    )


@pytest.mark.parametrize("study", STUDIES, ids=study_id)
def test_index_rows_stay_one_short_line(study: Path) -> None:
    path = study / "experiments" / "EXP_SUMMARY.md"
    long = [
        f"{rel(path)}:{number}: {len(line)} characters: {line[:40]}..."
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if INDEX_ROW.match(line) and len(line) > INDEX_ROW_MAX_CHARS
    ]
    assert not long, (
        f"Index rows are at most {INDEX_ROW_MAX_CHARS} characters: move detail to the "
        "experiment's summary.md or README.md (the reason for a status lives in its summary.md)\n"
        + "\n".join(long)
    )


def index_rows(path: Path) -> list[list[str]]:
    """Cells of each experiment row of the one table in an index file; asserts its shape."""
    name = rel(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    headers = [n for n, line in enumerate(lines) if line.strip() == INDEX_HEADER]
    assert len(headers) == 1, (
        f"{name} must contain the header line `{INDEX_HEADER}` exactly once "
        f"(found {len(headers)}): tools/new_experiment.py appends rows to that table"
    )
    separator = headers[0] + 1
    assert separator < len(lines) and INDEX_SEPARATOR.fullmatch(lines[separator].strip()), (
        f"{name}: the line after the header must be the separator |---|---|---|---|---|---|"
    )
    end = separator + 1
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    stray = [
        n + 1 for n, line in enumerate(lines) if INDEX_ROW.match(line) and not separator < n < end
    ]
    assert not stray, f"{name}: rows outside the table at lines {stray}; keep one contiguous table"
    rows = []
    for number, line in enumerate(lines[separator + 1 : end], start=separator + 2):
        text = line.strip()
        assert INDEX_ROW.match(text) and text.endswith("|"), (
            f"{name}:{number}: every table row is one experiment `| NNN | slug | ... |`: {text}"
        )
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", text)[1:-1]]
        assert len(cells) == 6, f"{name}:{number}: {len(cells)} cells, the header has 6: {text}"
        rows.append(cells)
    return rows


def indexed_name(row: list[str]) -> str:
    return f"{row[0]}_{row[1].strip('`')}"


def experiment_dirs(study: Path) -> list[Path]:
    # Every directory except the templates and hidden or cache ones is an experiment.
    experiments = study / "experiments"
    return sorted(
        p for p in experiments.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
    )


def index_problems(path: Path) -> list[str]:
    """Rows of one index file whose name, 状態 or 由来 breaks AGENTS.md 実験."""
    problems = []
    for row in index_rows(path):
        name = indexed_name(row)
        if not EXPERIMENT_NAME.fullmatch(name):
            problems.append(f"{rel(path)}: `{row[0]} | {row[1]}` is not NNN | lower_snake_slug")
        word = status_word(row[3])
        if word is None:
            problems.append(
                f"{rel(path)}: {name} 状態 `{row[3]}` must start with one of {STATUSES}, "
                "optionally followed by (YYYY-MM-DD、→ NNN_<slug>) (experiments/README.md)"
            )
        origin = row[5]
        if not ORIGIN.fullmatch(origin):
            problems.append(
                f"{rel(path)}: {name} 由来 `{origin}` must be 新規, 取り込み, or a closed import "
                "with its reproducibility such as 取り込み(R2) or 取り込み(R2+R3)"
            )
        elif origin == OPEN_IMPORT and word is not None and word not in OPEN_IMPORT_STATUSES:
            problems.append(
                f"{rel(path)}: {name} is {word} but its 由来 is still `{OPEN_IMPORT}`: a closed "
                "import names its reproducibility, e.g. 取り込み(R2) (only 進行中 or 中止 keep "
                f"`{OPEN_IMPORT}`)"
            )
    return problems


@pytest.mark.parametrize("study", STUDIES, ids=study_id)
def test_experiment_index_tables_are_well_formed(study: Path) -> None:
    problems = [
        problem
        for index in INDEX_FILES
        for problem in index_problems(study / "experiments" / index)
    ]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("study", STUDIES, ids=study_id)
def test_experiment_directories_match_the_index(study: Path) -> None:
    where = f"projects/{study.name}/experiments"
    names = [path.name for path in experiment_dirs(study)]
    misnamed = [name for name in names if not EXPERIMENT_NAME.fullmatch(name)]
    assert not misnamed, f"{where}: directories must be NNN_<lower_snake_slug>: {misnamed}"
    numbers = [name[:3] for name in names]
    reused = sorted({number for number in numbers if numbers.count(number) > 1})
    assert not reused, f"{where}: experiment numbers used twice: {reused}"

    rows = [row for index in INDEX_FILES for row in index_rows(study / "experiments" / index)]
    row_numbers = [row[0] for row in rows]
    twice = sorted({number for number in row_numbers if row_numbers.count(number) > 1})
    assert not twice, (
        f"{where}: numbers listed twice in EXP_SUMMARY.md and EXP_ARCHIVE.md together: {twice}"
    )
    listed = sorted(indexed_name(row) for row in rows)
    assert listed == names, (
        f"{where}: directories and the rows of EXP_SUMMARY.md + EXP_ARCHIVE.md differ: "
        f"{sorted(set(listed) ^ set(names))}"
    )
    for required in ("README.md", CARD):
        lacking = [
            path.name
            for path in experiment_dirs(study)
            if required not in {child.name for child in path.iterdir()}  # exact case, also on macOS
        ]
        assert not lacking, f"{where}: experiments without {required}: {lacking}"


def template_placeholders(study: Path) -> set[str]:
    """The placeholders of a study's two template cards (``<slug>`` is filled at creation)."""
    found: set[str] = set()
    for template in EXPERIMENT_TEMPLATES:
        path = study / "experiments" / template / CARD
        if path.is_file():
            found |= set(PLACEHOLDER.findall(path.read_text(encoding="utf-8")))
    return found - {"<slug>"}


def card_size_problems(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    n_lines, n_chars = len(text.splitlines()), len(text)
    if n_lines <= CARD_MAX_LINES and n_chars <= CARD_MAX_CHARS:
        return []
    return [
        f"{rel(path)}: {n_lines} lines and {n_chars} characters (at most {CARD_MAX_LINES} and "
        f"{CARD_MAX_CHARS}): the card holds the current conclusion; move detail to README.md"
    ]


def card_problems(study: Path) -> list[str]:
    """Cards that are too long or disagree with their index row (the index is canonical)."""
    experiments = study / "experiments"
    rows = {
        indexed_name(row): row for index in INDEX_FILES for row in index_rows(experiments / index)
    }
    placeholders = template_placeholders(study)
    problems = []
    for directory in experiment_dirs(study):
        path = directory / CARD
        row = rows.get(directory.name)
        if not path.is_file() or row is None:
            continue  # test_experiment_directories_match_the_index names it
        text = path.read_text(encoding="utf-8")
        problems += card_size_problems(path)
        lines = CARD_STATUS.findall(text)
        if len(lines) != 1:
            problems.append(
                f"{rel(path)}: needs exactly one `- **状態**: <word>` line, found {len(lines)}"
            )
            continue
        word = status_word(lines[0])
        if word is None or word != status_word(row[3]):
            problems.append(
                f"{rel(path)}: 状態 `{lines[0].strip()}` must start with the word of its index "
                f"row, `{row[3]}` (one of {STATUSES}; fix the card and the row in one commit)"
            )
            continue
        if word == OPEN:
            continue
        left = sorted(placeholder for placeholder in placeholders if placeholder in text)
        if left:
            shown = ", ".join(p if len(p) <= 24 else f"{p[:20]}…>" for p in left)
            problems.append(
                f"{rel(path)}: 状態 {word}, but template placeholders remain: {shown} -- write "
                "them (or なし)"
            )
        if OPEN_STEPS.search(text):
            problems.append(
                f"{rel(path)}: 状態 {word}, but `## 残りの手順` is still there -- remove it when "
                "the import closes"
            )
    return problems


@pytest.mark.parametrize("study", STUDIES, ids=study_id)
def test_each_card_is_short_and_agrees_with_its_index_row(study: Path) -> None:
    problems = card_problems(study)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("study", STUDIES, ids=study_id)
def test_template_cards_start_open_and_fit(study: Path) -> None:
    for template in EXPERIMENT_TEMPLATES:
        path = study / "experiments" / template / CARD
        assert not card_size_problems(path), card_size_problems(path)
        lines = CARD_STATUS.findall(path.read_text(encoding="utf-8"))
        assert len(lines) == 1 and status_word(lines[0]) == OPEN, (
            f"{rel(path)}: a new experiment starts with exactly one `- **状態**: {OPEN}` line "
            f"(found {lines})"
        )


@pytest.mark.parametrize(
    "study", [study for study in STUDIES if study.name != "_template"], ids=study_id
)
def test_experiment_readmes_are_the_same_in_every_study(study: Path) -> None:
    # The procedure and the harness behaviour are written once (AGENTS.md 実験 holds the rules):
    # every study's copy is projects/_template's with the study name filled in.
    template = ROOT / "projects" / "_template" / "experiments" / "README.md"
    expected = template.read_text(encoding="utf-8").replace("<study>", study.name)
    path = study / "experiments" / "README.md"
    assert path.read_text(encoding="utf-8") == expected, (
        f"{rel(path)} differs from {rel(template)} (with <study> = {study.name}): change the "
        "procedure in the template and copy it to every study; study-specific notes go to "
        f"projects/{study.name}/README.md"
    )


def write_index(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = [INDEX_HEADER, "|---|---|---|---|---|---|", *rows]
    path.write_text("# index\n\n" + "\n".join(table) + "\n", encoding="utf-8")


@pytest.fixture()
def fake_study(tmp_path: Path) -> Path:
    """A study with this repository's template cards and an empty archive."""
    study = tmp_path / "s1"
    for template in EXPERIMENT_TEMPLATES:
        card = ROOT / "projects" / "_template" / "experiments" / template / CARD
        target = study / "experiments" / template / CARD
        target.parent.mkdir(parents=True)
        shutil.copy2(card, target)
    write_index(study / "experiments" / "EXP_ARCHIVE.md", [])
    return study


def test_index_checks_reject_unknown_words_and_open_imports(fake_study: Path) -> None:
    rows = {
        # earlier words of this repository, and other words, are not status words
        "001": "| 001 | old_word | x | 置換(→006) | — | 新規 |",
        "002": "| 002 | old_done | x | 取り込み済 | — | 取り込み(R2) |",
        "003": "| 003 | other_word | x | done | — | 取り込み |",
        # a closed import names its reproducibility
        "004": "| 004 | closed | x | 完了 | — | 取り込み |",
        "005": "| 005 | bad_level | x | 完了 | — | 取り込み(R4) |",
        "011": "| 011 | withdrawn_open | x | 撤回(2026-01-04) | — | 取り込み |",
        # accepted
        "006": "| 006 | bold | x | **撤回(2026-01-02、→ 007_open)** | — | 新規 |",
        "007": "| 007 | open | (実行前) | 進行中 | — | 取り込み |",
        "008": "| 008 | both | x | 完了 | ch:s1 | 取り込み(R2+R3) |",
        "009": "| 009 | stopped | x | 中止 | — | 取り込み |",
        "010": "| 010 | fixed | x | 訂正(2026-01-03) | ch:s1 | 新規 |",
        "012": "| 012 | replaced | x | 置き換え(2026-01-05、→ 008_both) | — | 新規 |",
    }
    index = fake_study / "experiments" / "EXP_SUMMARY.md"
    write_index(index, list(rows.values()))

    problems = index_problems(index)

    flagged = sorted({re.search(r" (\d{3})_", problem).group(1) for problem in problems})
    assert flagged == ["001", "002", "003", "004", "005", "011"], problems
    assert sum("must start with one of" in problem for problem in problems) == 3


def test_card_checks_reject_disagreeing_long_and_unfinished_cards(fake_study: Path) -> None:
    experiments = fake_study / "experiments"
    template_card = (experiments / "_template" / CARD).read_text(encoding="utf-8")
    import_card = (experiments / "_import_template" / CARD).read_text(encoding="utf-8")
    finished = "# {name}: 問い\n\n- **状態**: {status}\n\n## 答え\n\n言えること。\n"
    cards = {
        "001_done": ("完了", finished.format(name="001_done", status="完了")),
        "002_stale": ("完了", template_card),  # still 進行中 in the card
        "003_withdrawn": (
            "撤回(2026-01-02、→ 001_done)",
            finished.format(name="003_withdrawn", status="**撤回(2026-01-02、→ 001_done)**"),
        ),
        "004_unfilled": ("完了", template_card.replace("- **状態**: 進行中", "- **状態**: 完了")),
        "005_import": ("完了", import_card.replace("- **状態**: 進行中", "- **状態**: 完了")),
        "006_open": ("進行中", template_card),
        "007_long": (
            "完了",
            finished.format(name="007_long", status="完了") + "行\n" * CARD_MAX_LINES,
        ),
        "008_twice": ("完了", finished.format(name="008_twice", status="完了") * 2),
        "009_old_word": ("置換(→001)", finished.format(name="009_old_word", status="置換")),
    }
    rows = []
    for name, (status, text) in cards.items():
        (experiments / name).mkdir()
        (experiments / name / CARD).write_text(text, encoding="utf-8")
        number, slug = name.split("_", 1)
        rows.append(f"| {number} | {slug} | x | {status} | — | 新規 |")
    write_index(experiments / "EXP_SUMMARY.md", rows)

    problems = card_problems(fake_study)

    def about(name: str) -> list[str]:
        return [problem for problem in problems if f"/{name}/{CARD}" in problem]

    for name in ("001_done", "003_withdrawn", "006_open"):
        assert not about(name), about(name)
    assert any("must start with the word of its index row" in p for p in about("002_stale"))
    assert any("placeholders remain" in p for p in about("004_unfilled"))
    assert any("placeholders remain" in p for p in about("005_import"))
    assert any("残りの手順" in p for p in about("005_import"))
    assert any("move detail to README.md" in p for p in about("007_long"))
    assert any("exactly one" in p for p in about("008_twice"))
    assert any("must start with the word" in p for p in about("009_old_word"))


def test_template_study_has_no_experiments() -> None:
    # make study copies projects/_template: experiments there would leak into every new study.
    template = ROOT / "projects" / "_template"
    dirs = [path.name for path in experiment_dirs(template)]
    rows = [
        indexed_name(row)
        for index in INDEX_FILES
        for row in index_rows(template / "experiments" / index)
    ]
    assert not dirs and not rows, (
        f"projects/_template/experiments must stay empty (directories {dirs}, index rows {rows})"
    )


def skill_files() -> list[Path]:
    return sorted(path for directory in SKILL_DIRS for path in directory.glob("*/SKILL.md"))


def test_skills_declare_frontmatter() -> None:
    # Codex does not load a skill without YAML frontmatter, and Claude Code needs the
    # description to know when to use one.
    skills = skill_files()
    assert skills, "No skills found"
    for path in skills:
        name = rel(path)
        match = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.DOTALL)
        assert match, f"{name} has no YAML frontmatter"
        assert re.search(rf"^name: {re.escape(path.parent.name)}$", match.group(1), re.MULTILINE), (
            f"{name}: frontmatter name must be {path.parent.name}"
        )
        assert re.search(r"^description: \S", match.group(1), re.MULTILINE), (
            f"{name}: frontmatter has no description"
        )


def skill_tree(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def test_mirrored_skills_are_identical_for_both_agents() -> None:
    claude, codex = SKILL_DIRS
    missing = [
        rel(directory / name / "SKILL.md")
        for name in MIRRORED_SKILLS
        for directory in SKILL_DIRS
        if not (directory / name / "SKILL.md").is_file()
    ]
    assert not missing, f"Skills both agents use are missing: {missing}"
    shared = sorted(
        path.name for path in claude.iterdir() if path.is_dir() and (codex / path.name).is_dir()
    )
    differing = [name for name in shared if skill_tree(claude / name) != skill_tree(codex / name)]
    assert not differing, (
        f"Keep .agents/skills/<name>/ byte-identical to .claude/skills/<name>/ for: {differing}"
    )


def convention_scanned_files() -> list[Path]:
    files = [ROOT / name for name in ("AGENTS.md", "README.md", "STATE.md")]
    files += sorted((ROOT / "docs").rglob("*.md"))
    for directory in SKILL_DIRS:
        files += sorted(directory.rglob("*.md"))
    for study in STUDIES:
        experiments = study / "experiments"
        files += sorted(
            path
            for path in experiments.rglob("*")
            if path.is_file()
            and path.suffix in {".md", ".py"}
            and not {"out", "__pycache__"} & set(path.relative_to(experiments).parts)
        )
    return [path for path in files if path.is_file()]


def test_docs_use_this_repositorys_conventions() -> None:
    found = [
        f"{rel(path)}:{number}: {match.group(0)}"
        for path in convention_scanned_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        for match in FOREIGN_CONVENTIONS.finditer(line)
    ]
    assert not found, (
        "research-template conventions that do not exist here (decision records are "
        "docs/decisions/NNNN-<slug>.md from _adr-template.md, research logs are entries in "
        "docs/research-log.md, there is no docs/templates/):\n" + "\n".join(found)
    )


def git_work_tree() -> bool:
    if shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def git_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in (0, 1), f"git check-ignore failed: {result.stderr.strip()}"
    return result.returncode == 0


@pytest.mark.skipif(not git_work_tree(), reason="git is unavailable or this is not a work tree")
def test_experiment_outputs_are_git_ignored() -> None:
    # A rename or an edit that misses .gitignore makes every out/ committable, silently.
    ignored = ["projects/_template/experiments/_template/out/x.png"]
    tracked = []
    for study in STUDIES:
        base = f"projects/{study.name}"
        probe = f"{base}/experiments/999_probe"
        ignored += [
            *(
                f"{probe}/out/{name}"
                for name in (
                    "table.csv",
                    "fig/a.png",
                    "params_used.json",
                    ".lock",
                    "smoke/params_used.json",
                    "staged/figures/a.png",
                )
            ),
            # The import verification cache and promoted large outputs.
            f"{base}/data/interim/999_probe/inputs_verified.json",
            f"{base}/data/processed/999_probe/grid.nc",
        ]
        tracked += [
            *(f"{base}/experiments/{template}/out/.gitkeep" for template in EXPERIMENT_TEMPLATES),
            f"{probe}/out/.gitkeep",
            f"{probe}/README.md",
            f"{probe}/summary.md",
            f"{probe}/inputs.sha256",
            # docker-compose.yml mounts data/raw with create_host_path: false; a fresh clone
            # only has the directory through this file.
            f"{base}/data/raw/.gitkeep",
        ]
    # A publication killed midway leaves temporaries that git status must show until the next
    # full run in the study repairs them (the template publishes nothing; demo is a new study).
    for name in {study.name for study in STUDIES if study.name != "_template"} | {"demo"}:
        tracked += [
            f"projects/{name}/result/{area}/.{name}-x.{ext}.123.{suffix}"
            for area, ext in (("figures", "png"), ("tables", "csv"))
            for suffix in ("part", "previous")
        ]
        tracked.append(f"projects/{name}/result/.publication.json")
    wrongly_tracked = [path for path in ignored if not git_ignored(path)]
    assert not wrongly_tracked, f"Not git-ignored (fix .gitignore): {wrongly_tracked}"
    wrongly_ignored = [path for path in tracked if git_ignored(path)]
    assert not wrongly_ignored, f"Must stay committable (fix .gitignore): {wrongly_ignored}"
