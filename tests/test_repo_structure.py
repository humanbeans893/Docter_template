"""Small guards for what agents read (AGENTS.md): the always-read documents stay within their
character budgets, Claude Code and Codex load the same skills, the thesis-check skill explains
exactly the findings of tools/thesis_check.py, and the documents name only make targets and
tools that exist. Facts are checked (a file, a code, a target), never wording.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Read at the start of every session. Characters, not lines: long lines defeat a line count.
ALWAYS_READ_BUDGETS = {"STATE.md": 6_000, "docs/thesis-plan.md": 8_000, "docs/guardrails.md": 8_000}

# Claude Code reads .claude/skills/, Codex reads .agents/skills/ (review-* are Claude Code only).
CLAUDE_SKILLS = ROOT / ".claude" / "skills"
CODEX_SKILLS = ROOT / ".agents" / "skills"
MIRRORED_SKILLS = ("add-research", "research-log", "thesis-check", "write-handoff")


@pytest.mark.parametrize(("name", "budget"), ALWAYS_READ_BUDGETS.items())
def test_always_read_documents_stay_within_budget(name: str, budget: int) -> None:
    n_chars = len((ROOT / name).read_text(encoding="utf-8"))
    assert n_chars <= budget, (
        f"{name} has {n_chars} characters (budget {budget}, read every session): move detail "
        "to docs/research-log.md, docs/decisions/ or projects/<id>/README.md"
    )


def skill_files() -> list[Path]:
    return sorted([*CLAUDE_SKILLS.glob("*/SKILL.md"), *CODEX_SKILLS.glob("*/SKILL.md")])


def test_skills_declare_frontmatter() -> None:
    # Codex does not load a skill without YAML frontmatter; Claude Code needs the description.
    for path in skill_files():
        match = re.match(r"---\n(.*?)\n---\n", path.read_text(encoding="utf-8"), re.DOTALL)
        front = match.group(1) if match else ""
        assert re.search(rf"^name: {re.escape(path.parent.name)}$", front, re.MULTILINE), path
        assert re.search(r"^description: \S", front, re.MULTILINE), path


def skill_tree(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_codex_skills_mirror_claude_skills() -> None:
    names = sorted(path.name for path in CODEX_SKILLS.iterdir() if path.is_dir())
    assert names == sorted(MIRRORED_SKILLS), f".agents/skills/ must hold {MIRRORED_SKILLS}"
    differing = [
        name
        for name in names
        if not (CLAUDE_SKILLS / name).is_dir()
        or skill_tree(CLAUDE_SKILLS / name) != skill_tree(CODEX_SKILLS / name)
    ]
    assert not differing, f"Keep .agents/skills/<name>/ identical to .claude/skills/: {differing}"


SKILL_CODE_CELL = re.compile(r"^\|\s*([EWI][0-9]+(?:\s*/\s*[EWI][0-9]+)*)\s*\|", re.MULTILINE)


def test_thesis_check_skill_explains_every_finding_code() -> None:
    source = (ROOT / "tools" / "thesis_check.py").read_text(encoding="utf-8")
    documented = set(re.findall(r"^  ([EWI][0-9]+) ", ast.get_docstring(ast.parse(source)), re.M))
    emitted = set(re.findall(r'"([EWI][0-9]+)"', source))
    assert documented == emitted, (
        f"tools/thesis_check.py: the docstring's Checks list and the reported codes differ: "
        f"undocumented {sorted(emitted - documented)}, not reported {sorted(documented - emitted)}"
    )
    for directory in (CLAUDE_SKILLS, CODEX_SKILLS):
        text = (directory / "thesis-check" / "SKILL.md").read_text(encoding="utf-8")
        explained = {
            code.strip() for cell in SKILL_CODE_CELL.findall(text) for code in cell.split("/")
        }
        missing, stale = sorted(documented - explained), sorted(explained - documented)
        assert not missing and not stale, (
            f"{directory.relative_to(ROOT)}/thesis-check/SKILL.md: the table needs one row per "
            f"code of tools/thesis_check.py; missing {missing}, stale {stale}"
        )


def documents() -> list[Path]:
    found = {ROOT / name for name in ("AGENTS.md", "CONTRIBUTING.md", "README.md", "STATE.md")}
    for pattern in ("docs/**/*.md", "draft/**/*.md", "projects/**/*.md", ".*/skills/*/SKILL.md"):
        found.update(ROOT.glob(pattern))
    return sorted(path for path in found if path.is_file())


# `make <target>` in inline code, or at the start of a line of a code block.
MAKE_COMMAND = re.compile(r"(?:`|^[ \t]*)make ([a-z][a-z0-9-]*)", re.MULTILINE)
TOOL = re.compile(r"\btools/([a-z_]+\.py)")


def test_documents_name_only_existing_make_targets_and_tools() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, re.MULTILINE))
    tools = {path.name for path in (ROOT / "tools").glob("*.py")}
    stale = set()
    for path in documents():
        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT)
        stale |= {f"{name}: make {t}" for t in MAKE_COMMAND.findall(text) if t not in targets}
        stale |= {f"{name}: tools/{t}" for t in TOOL.findall(text) if t not in tools}
    assert not stale, "Documents name removed commands or tools:\n" + "\n".join(sorted(stale))
