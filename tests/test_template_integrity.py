"""Structural guardrails: studies, manuscript and their registrations stay in sync.

`make study` (tools/new_study.py) copies projects/_template and registers the new study in
draft/preamble.tex, draft/supplementary.tex and docker-compose.yml. These tests keep that
trustworthy: every study (and _template itself) has the full skeleton and config, the
markers the tools edit exist, and every registration names an existing study and back.
"""

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DRAFT = REPO_ROOT / "draft"

EXPECTED_DIRS = [
    "data/raw",
    "data/interim",
    "data/processed",
    "src/utils",
    "src/models",
    "src/methods",
    "src/analysis",
    "scripts",
    "result/figures",
    "result/tables",
    "result/animations",
    "tests",
    "experiments",
    "experiments/_template",
    "experiments/_template/out",
    "experiments/_import_template",
    "experiments/_import_template/out",
]
EXPECTED_FILES = [
    "config.py",
    "README.md",
    "data/README.md",
    # docker-compose.yml mounts data/raw with create_host_path: false, and git keeps the
    # empty directory of a fresh clone only through this file.
    "data/raw/.gitkeep",
    "src/utils/figures.py",
    "src/utils/tables.py",
    "src/utils/provenance.py",
    "src/utils/experiment.py",
    "tests/conftest.py",
    "experiments/README.md",
    "experiments/EXP_SUMMARY.md",
    "experiments/EXP_ARCHIVE.md",
    "experiments/JOBS.md",
    *(
        f"experiments/{template}/{name}"
        for template in ("_template", "_import_template")
        for name in ("summary.md", "README.md", "run.py", "params.py", "out/.gitkeep")
    ),
]
EXPECTED_CONFIG_ATTRS = [
    # Thesis-wide figure appearance and physical constants from the repo-root config.py.
    "GEO",
    "VISUALIZATION",
    "STUDY_ROOT",
    "REPO_ROOT",
    "DATA_DIR",
    "RAW_DATA_DIR",
    "INTERIM_DATA_DIR",
    "PROCESSED_DATA_DIR",
    "RESULT_DIR",
    "FIGURE_DIR",
    "TABLE_DIR",
    "ANIMATION_DIR",
    "EXPERIMENTS_DIR",
    # research-template names, so code ported from such a repository runs unchanged
    # (EXP_DIR: research-template's older name of EXPERIMENTS_DIR).
    "PROJECT_ROOT",
    "DATA_ROOT",
    "EXP_DIR",
]
# Values that can change a result live in each experiment's params.py, never in a shared
# config.py (AGENTS.md, 実験): editing a shared file must not change a finished experiment.
REMOVED_CONFIG_ATTRS = ["RANDOM"]
# What an experiment's params.py must not read: the shared seed or the environment.
SHARED_RESULT_SOURCES = {("config", "RANDOM"), ("os", "environ"), ("os", "getenv")}

STUDY_CHAPTERS_MARKER = "% thesis:study-chapters:end"
VALUES_MARKER = "% thesis:values:end"
RAW_MOUNTS_MARKER = "# thesis:raw-mounts:end"
STUDY_FIGURE_DIR = re.compile(r"\.\./projects/([^/{}]+)/result/figures/")
RAW_SOURCE = re.compile(r"\./projects/([^/]+)/data/raw/?")


def studies() -> list[Path]:
    return sorted(p.parent for p in (REPO_ROOT / "projects").glob("*/config.py"))


def study_names() -> set[str]:
    return {study.name for study in studies()}


def code_lines(path: Path) -> list[str]:
    """Lines of a TeX file without comments (an escaped \\% stays)."""
    text = path.read_text(encoding="utf-8")
    return [re.sub(r"(?<!\\)%.*", "", line).rstrip() for line in text.splitlines()]


def count_marker(path: Path, marker: str) -> int:
    return sum(line.strip() == marker for line in path.read_text(encoding="utf-8").splitlines())


@pytest.mark.parametrize("study", studies(), ids=lambda p: p.name)
def test_study_skeleton_is_complete(study: Path):
    for directory in EXPECTED_DIRS:
        assert (study / directory).is_dir(), f"{study.name} is missing {directory}/"
    for file in EXPECTED_FILES:
        assert (study / file).is_file(), f"{study.name} is missing {file}"


@pytest.mark.parametrize("study", studies(), ids=lambda p: p.name)
def test_study_config_loads_with_all_attributes(study: Path, load_module_by_path):
    cfg = load_module_by_path(study / "config.py", f"integrity_{study.name}_config")

    for attr in EXPECTED_CONFIG_ATTRS:
        assert hasattr(cfg, attr), f"{study.name}/config.py is missing {attr}"
    for attr in REMOVED_CONFIG_ATTRS:
        assert not hasattr(cfg, attr), (
            f"{study.name}/config.py still has {attr}: pin it in each experiment's params.py"
        )
    assert cfg.STUDY_ROOT == study
    assert cfg.REPO_ROOT == REPO_ROOT
    assert cfg.PROJECT_ROOT == cfg.STUDY_ROOT
    assert cfg.EXPERIMENTS_DIR == study / "experiments" and cfg.EXPERIMENTS_DIR.is_dir()
    assert cfg.EXP_DIR == cfg.EXPERIMENTS_DIR
    assert cfg.DATA_ROOT == cfg.RAW_DATA_DIR


def shared_result_reads(path: Path) -> list[str]:
    """`config.RANDOM`, `os.environ` and `os.getenv` read in the code (docstrings ignored)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if (node.value.id, node.attr) in SHARED_RESULT_SOURCES:
                found.append(f"{node.value.id}.{node.attr} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom) and node.module in ("os", "config"):
            found += [
                f"from {node.module} import {alias.name} (line {node.lineno})"
                for alias in node.names
                if (node.module, alias.name) in SHARED_RESULT_SOURCES or alias.name == "*"
            ]
    return found


def module_values(tree: ast.Module, name: str) -> list[ast.expr]:
    """What ``name`` is bound to at module level (``X = ...`` or ``X: T = ...``)."""
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if [getattr(target, "id", None) for target in node.targets] == [name]:
                values.append(node.value)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if getattr(node.target, "id", None) == name:
                values.append(node.value)
    return values


def string_keys(node: ast.expr) -> list[str] | None:
    """The keys of a dict display whose keys are all string literals, else None."""
    if not isinstance(node, ast.Dict):
        return None
    keys = [key.value if isinstance(key, ast.Constant) else None for key in node.keys]
    return keys if all(isinstance(key, str) for key in keys) else None


@pytest.mark.parametrize("template", ["_template", "_import_template"])
@pytest.mark.parametrize("study", studies(), ids=lambda p: p.name)
def test_experiment_templates_pin_their_values(study: Path, template: str):
    # make experiment copies these: a seed or setting read from a shared config.py or the
    # environment would let one edit silently change every finished experiment, and
    # experiment.start() refuses a params.py without SEED, PARAMS and (for --smoke) SMOKE.
    path = study / "experiments" / template / "params.py"
    where = path.relative_to(REPO_ROOT).as_posix()
    found = shared_result_reads(path)
    assert not found, (
        f"{where} reads {found}: pin every value that can change a result in params.py itself "
        "(make experiment copies it into every new experiment)"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    seeds = module_values(tree, "SEED")
    assert len(seeds) == 1 and isinstance(seeds[0], ast.Constant) and type(seeds[0].value) is int, (
        f"{where} must pin the seed once, SEED = <integer>: make experiment copies it"
    )
    params = module_values(tree, "PARAMS")
    keys = string_keys(params[0]) if len(params) == 1 else None
    assert keys is not None, (
        f"{where} must define PARAMS once as a dict display with string keys, every value that "
        "can change the result: make experiment copies it"
    )
    smoke = module_values(tree, "SMOKE")
    smoke_keys = string_keys(smoke[0]) if len(smoke) == 1 else None
    assert smoke_keys is not None, (
        f"{where} must define SMOKE once as a dict display with string keys, the values of a "
        "--smoke run ({} keeps PARAMS): make experiment copies it"
    )
    assert set(smoke_keys) <= set(keys), (
        f"{where}: SMOKE keys missing from PARAMS: {sorted(set(smoke_keys) - set(keys))} "
        "(make experiment copies it, and experiment.start() refuses them under --smoke)"
    )


def test_root_agent_and_public_repository_contract():
    assert (REPO_ROOT / "AGENTS.md").is_file()
    assert (REPO_ROOT / "CLAUDE.md").is_file()
    assert "@AGENTS.md" in (REPO_ROOT / "CLAUDE.md").read_text()
    assert not (REPO_ROOT / ".claude" / "CLAUDE.md").exists()
    assert not (REPO_ROOT / ".codex" / "AGENTS.md").exists()

    for path in (
        "LICENSE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        ".github/CODEOWNERS",
        ".github/dependabot.yml",
        ".github/workflows/ci.yml",
    ):
        assert (REPO_ROOT / path).is_file(), f"public repository contract is missing {path}"


def test_dissertation_frontmatter_contract():
    for path in (
        "thesis-config.tex",
        "submission.tex",
        "review.tex",
        "compile.sh",
        "values.tex",
        "figures/README.md",
        "chapters/_chapter-template.tex",
        "chapters/_background-template.tex",
        "frontmatter/abstract-en.tex",
        "frontmatter/abstract-ja.tex",
        "frontmatter/declaration.tex",
        "frontmatter/publications.tex",
        "frontmatter/abbreviations.tex",
        "frontmatter/symbols.tex",
        "SUBMISSION_CHECKLIST.md",
    ):
        assert (DRAFT / path).is_file(), f"dissertation front matter is missing {path}"

    main = (DRAFT / "main.tex").read_text()
    assert "english" in main.splitlines()[1]
    assert "\\pagenumbering{roman}" in main
    assert "\\pagenumbering{arabic}" in main


def test_markers_the_tools_edit_exist_once():
    # tools/new_study.py inserts the chapter include above the main.tex marker; study code
    # registers generated values files above the values.tex marker.
    for path, marker in (
        (DRAFT / "main.tex", STUDY_CHAPTERS_MARKER),
        (DRAFT / "values.tex", VALUES_MARKER),
        (REPO_ROOT / "docker-compose.yml", RAW_MOUNTS_MARKER),
    ):
        count = count_marker(path, marker)
        assert count == 1, f"{path.relative_to(REPO_ROOT)} must contain `{marker}` once ({count})"


def test_generated_values_are_loaded_before_the_document():
    # The abstracts come before the chapters, so every \val must be defined in the preamble.
    preamble = [line.strip() for line in code_lines(DRAFT / "preamble.tex") if line.strip()]
    assert preamble and preamble[-1] == "\\input{values}", (
        "draft/preamble.tex must end with \\input{values}"
    )
    supplementary = [line.strip() for line in code_lines(DRAFT / "supplementary.tex")]
    assert "\\begin{document}" in supplementary, "draft/supplementary.tex has no \\begin{document}"
    body = supplementary.index("\\begin{document}")
    assert "\\input{values}" in supplementary[:body], (
        "draft/supplementary.tex must \\input{values} before \\begin{document}"
    )


def test_partial_review_build_hook_is_in_main():
    # bash draft/compile.sh review --only <chapter> defines \ThesisIncludeOnly.
    main = [line.strip() for line in code_lines(DRAFT / "main.tex")]
    assert "\\ifdefined\\ThesisIncludeOnly\\includeonly{\\ThesisIncludeOnly}\\fi" in main, (
        "draft/main.tex needs \\ifdefined\\ThesisIncludeOnly\\includeonly{\\ThesisIncludeOnly}\\fi"
    )


def graphicspath_line(path: Path) -> str:
    lines = [line.strip() for line in code_lines(path) if line.strip().startswith("\\graphicspath")]
    assert len(lines) == 1, (
        f"draft/{path.name} must have exactly one \\graphicspath line (found {len(lines)}): "
        "tools/new_study.py edits that single line"
    )
    return lines[0]


def graphicspath_dirs(path: Path) -> list[str]:
    line = graphicspath_line(path)
    match = re.fullmatch(r"\\graphicspath\{((?:\{[^{}]*\})+)\}", line)
    assert match, (
        f"draft/{path.name}: keep the graphicspath on one line, "
        f"\\graphicspath{{{{figures/}}{{../projects/<study>/result/figures/}}}}: {line}"
    )
    return re.findall(r"\{([^{}]*)\}", match.group(1))


def test_graphicspath_registers_every_study_and_nothing_else():
    preamble, supplementary = DRAFT / "preamble.tex", DRAFT / "supplementary.tex"
    assert graphicspath_line(preamble) == graphicspath_line(supplementary), (
        "draft/preamble.tex and draft/supplementary.tex must have the same \\graphicspath line"
    )
    dirs = graphicspath_dirs(preamble)
    assert "figures/" in dirs, "\\graphicspath must list figures/ (hand-made figures)"
    twice = sorted({d for d in dirs if dirs.count(d) > 1})
    assert not twice, f"\\graphicspath lists these twice: {twice}"

    problems, listed = [], []
    for directory in dirs:
        if directory == "figures/":
            continue
        match = STUDY_FIGURE_DIR.fullmatch(directory)
        if not match:
            problems.append(f"{directory}: only ../projects/<study>/result/figures/ belongs here")
            continue
        listed.append(match.group(1))
        if not (REPO_ROOT / "projects" / match.group(1) / "config.py").is_file():
            problems.append(f"{directory}: projects/{match.group(1)}/config.py does not exist")
        elif not (DRAFT / directory).is_dir():
            problems.append(f"{directory}: the directory does not exist")
    assert not problems, "\\graphicspath in draft/preamble.tex:\n" + "\n".join(problems)

    # _template is copied, never built into the thesis.
    expected = study_names() - {"_template"}
    assert set(listed) == expected, (
        f"\\graphicspath and the studies differ: missing {sorted(expected - set(listed))}, "
        f"extra {sorted(set(listed) - expected)} (tools/new_study.py registers a study; "
        "projects/README.md lists the steps to remove one)"
    )


def bind_blocks(lines: list[str]) -> list[tuple[int, dict[str, str]]]:
    """Long-syntax `- type: bind` volume entries as (line number, flattened keys)."""
    blocks = []
    for number, line in enumerate(lines):
        start = re.match(r"^(\s*)-\s+type:\s*bind\s*$", line)
        if not start:
            continue
        indent, fields = len(start.group(1)), {}
        for inner in lines[number + 1 :]:
            if inner.strip() and len(inner) - len(inner.lstrip()) <= indent:
                break
            item = re.match(r"^\s*([A-Za-z_]+):\s*(.*?)\s*(?:#.*)?$", inner)
            if item:
                fields[item.group(1)] = item.group(2).strip("\"'")
        blocks.append((number + 1, fields))
    return blocks


def test_raw_data_mounts_register_every_study_read_only():
    compose = REPO_ROOT / "docker-compose.yml"
    lines = compose.read_text(encoding="utf-8").splitlines()
    short = [
        n + 1
        for n, line in enumerate(lines)
        if re.match(r"^\s*-\s+['\"]?\./projects/[^:]*/data/raw", line)
    ]
    assert not short, (
        f"docker-compose.yml lines {short}: mount data/raw with the long syntax "
        "(type: bind, read_only: true, bind: create_host_path: false)"
    )
    markers = [n + 1 for n, line in enumerate(lines) if line.strip() == RAW_MOUNTS_MARKER]
    assert markers, f"docker-compose.yml has no `{RAW_MOUNTS_MARKER}` line"
    marker = markers[0]

    problems, listed = [], []
    for number, fields in bind_blocks(lines):
        match = RAW_SOURCE.fullmatch(fields.get("source", ""))
        if not match:
            continue
        study = match.group(1)
        listed.append(study)
        where = f"docker-compose.yml:{number} ({fields['source']})"
        if not (REPO_ROOT / "projects" / study / "config.py").is_file():
            problems.append(f"{where}: projects/{study}/config.py does not exist")
        if fields.get("target") != f"/workspace/projects/{study}/data/raw":
            problems.append(f"{where}: target must be /workspace/projects/{study}/data/raw")
        if fields.get("read_only") != "true":
            problems.append(f"{where}: needs read_only: true")
        if fields.get("create_host_path") != "false":
            problems.append(f"{where}: needs bind: create_host_path: false")
        if number > marker:
            problems.append(f"{where}: keep raw-mount blocks above `{RAW_MOUNTS_MARKER}`")
    assert not problems, "\n".join(problems)

    twice = sorted({study for study in listed if listed.count(study) > 1})
    assert not twice, f"docker-compose.yml mounts the raw data of these studies twice: {twice}"
    expected = study_names()
    assert set(listed) == expected, (
        f"docker-compose.yml raw mounts and the studies differ: missing "
        f"{sorted(expected - set(listed))}, extra {sorted(set(listed) - expected)} "
        "(tools/new_study.py adds the block; projects/README.md lists the steps to remove one)"
    )


def test_thesis_plan_has_the_conclusion_row_new_chapters_go_before():
    plan = (REPO_ROOT / "docs" / "thesis-plan.md").read_text(encoding="utf-8").splitlines()
    rows = [line for line in plan if line.startswith("|") and "chapters/99-conclusion.tex" in line]
    assert len(rows) == 1, (
        "docs/thesis-plan.md needs exactly one chapter-map row for chapters/99-conclusion.tex: "
        f"tools/new_study.py inserts new chapter rows before it (found {len(rows)})"
    )


def guide_documents() -> list[Path]:
    """The Markdown that tells people and agents what to run (raw data excluded)."""
    found = {REPO_ROOT / name for name in ("README.md", "AGENTS.md", "CONTRIBUTING.md", "STATE.md")}
    for pattern in ("docs/**/*.md", ".claude/skills/*/SKILL.md", ".agents/skills/*/SKILL.md"):
        found.update(REPO_ROOT.glob(pattern))
    for pattern in ("projects/**/*.md", "draft/**/*.md"):
        found.update(path for path in REPO_ROOT.glob(pattern) if "raw" not in path.parts)
    return sorted(path for path in found if path.is_file())


def test_session_save_skill_is_removed():
    # It wrote project state to Claude's memory and the git-ignored .claude/sessions/, which
    # Codex and other clones cannot read; STATE.md (write-handoff) is the handoff (AGENTS.md).
    for path in (".claude/skills/session-save", ".agents/skills/session-save"):
        assert not (REPO_ROOT / path).exists(), f"{path} was removed: hand off with write-handoff"
    mentions = [
        str(path.relative_to(REPO_ROOT))
        for path in guide_documents()
        if "session-save" in path.read_text(encoding="utf-8")
    ]
    assert not mentions, f"These still refer to the removed session-save skill: {mentions}"


FENCED_CODE = re.compile(r"^\s*```[^\n]*\n(.*?)^\s*```", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`([^`\n]+)`")
MAKE_COMMAND = re.compile(r"\bmake((?:[ \t]+[a-z][a-z0-9-]*)+)")


def test_documents_name_only_existing_make_targets():
    # A removed target (make up-gpu / up-files, replaced by COMPOSE_FILE in .env) that a
    # document still names fails only when someone follows it. Commands are read from code
    # spans and code blocks; `make study NAME=x` stops at the variable.
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", makefile, re.MULTILINE))
    unknown = []
    for path in guide_documents():
        text = path.read_text(encoding="utf-8")
        code = [*FENCED_CODE.findall(text), *INLINE_CODE.findall(FENCED_CODE.sub("", text))]
        for span in code:
            for command in MAKE_COMMAND.finditer(span):
                unknown += [
                    f"{path.relative_to(REPO_ROOT)}: make {word}"
                    for word in command.group(1).split()
                    if word not in targets
                ]
    assert not unknown, "These documents name make targets the Makefile does not have:\n" + (
        "\n".join(sorted(set(unknown)))
    )


def test_reference_manager_connection_is_removed():
    # References come from draft/reference.bib only (docs/integrations.md).
    for path in (
        ".claude/skills/zotero-connect",
        ".claude/scripts/zotero-forward.py",
        ".mcp.json.example",
    ):
        assert not (REPO_ROOT / path).exists(), f"{path} belongs to the removed Zotero connection"
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    targets = re.findall(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", makefile, re.MULTILINE)
    removed = [target for target in targets if "zotero" in target.lower() or target == "bib"]
    assert not removed, f"Makefile still has the removed targets {removed}"
    for path in ("docker-compose.yml", ".claude/settings.json"):
        text = (REPO_ROOT / path).read_text(encoding="utf-8").lower()
        assert "zotero" not in text, f"{path} still refers to Zotero"
