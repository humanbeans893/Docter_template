#!/usr/bin/env python3
"""Static consistency checks for the dissertation manuscript.

Stdlib only, so it runs identically inside Docker (``uv run python
tools/thesis_check.py``) and on the host (``python3 tools/thesis_check.py``).

The scan is line-based over the ``\\input``/``\\include`` graph reachable from
``draft/main.tex`` (comment-stripped, so disabled ``% \\include{...}`` lines
are ignored). Multiline commands are matched only on their first line — an
accepted limitation for a linter that must never block a build.

Severities:
  error   (exit 1)  broken cross-references, missing citations or figures
  warning (exit 1 with --strict) hygiene issues worth fixing before submission
  info    TODO inventory and compile-log findings

Checks:
  E1 \\ref/\\cref/... target has no matching \\label
  E2 duplicate \\label keys
  E3 \\cite key missing from the bibliography (.bib)
  E4 \\includegraphics file not found in any \\graphicspath directory
  E5 \\input/\\include/\\bibliography file missing on disk
  W1 duplicate bibliography keys
  W2 bibliography entries never cited
  W3 figure files in \\graphicspath directories never included
  W4 fig:/tab: labels never referenced
  W5 labels not following the prefix convention (ch:/sec:/subsec:/fig:/tab:/eq:/alg:/app:)
  W6 identical figure basenames in multiple \\graphicspath directories (shadowing)
  I1 TODO/FIXME inventory (\\todo{...} and %-comments)
  I2 findings from draft/main.log (undefined references/citations, overfull boxes)
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

LABEL_PREFIX = re.compile(r"^(ch|sec|subsec|fig|tab|eq|alg|app):")
FIGURE_EXTENSIONS = (".png", ".pdf", ".jpg", ".jpeg", ".eps")

RE_INPUT = re.compile(r"\\(?:input|include)\{([^}]+)\}")
RE_LABEL = re.compile(r"\\label\{([^}]+)\}")
RE_REF = re.compile(r"\\(?:ref|eqref|pageref|autoref|vref|[cC]ref)\*?\{([^}]+)\}")
RE_CITE = re.compile(r"\\(?:[cC]ite[a-zA-Z]*|nocite)\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}")
RE_GRAPHICS = re.compile(r"\\includegraphics\*?(?:\[[^\]]*\])?\{([^}]+)\}")
RE_BIBLIOGRAPHY = re.compile(r"\\bibliography\{([^}]+)\}")
RE_GRAPHICSPATH = re.compile(r"\\graphicspath\{((?:\s*\{[^{}]*\}\s*)+)\}")
RE_TODO_CMD = re.compile(r"\\todo(?:\[[^\]]*\])?\{([^}]*)")
RE_TODO_COMMENT = re.compile(r"%.*?\b(TODO|FIXME)\b[:\s]*(.*)")
RE_BIB_ENTRY = re.compile(r"^\s*@(\w+)\s*\{\s*([^,\s{}]+)\s*,")

RE_LOG_UNDEF_REF = re.compile(r"LaTeX Warning: Reference `([^']+)' on page")
RE_LOG_UNDEF_CITE = re.compile(r"LaTeX Warning: Citation `([^']+)'")
RE_LOG_OVERFULL = re.compile(r"^Overfull \\hbox")
RE_LOG_ERROR = re.compile(r"^! (.+)")


@dataclass
class Finding:
    severity: str  # "error" | "warning" | "info"
    code: str
    location: str  # "path:line" (repo-relative) or ""
    message: str


def strip_comments(line: str) -> str:
    """Drop everything from the first unescaped ``%`` to the end of the line."""
    out = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\":
            out.append(line[i : i + 2])
            i += 2
            continue
        if ch == "%":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class TexIndex:
    """Occurrences keyed by name -> list of (file, lineno)."""

    def __init__(self):
        self.labels: dict[str, list[tuple[Path, int]]] = {}
        self.refs: dict[str, list[tuple[Path, int]]] = {}
        self.cites: dict[str, list[tuple[Path, int]]] = {}
        self.graphics: list[tuple[str, Path, int]] = []
        self.todos: list[tuple[str, Path, int]] = []
        self.bib_names: list[str] = []
        self.graphicspath_groups: list[str] = []

    @staticmethod
    def _add(index: dict, key: str, where: tuple[Path, int]) -> None:
        index.setdefault(key, []).append(where)


def resolve_include_graph(main_tex: Path, findings: list[Finding]) -> list[Path]:
    """Files reachable from main.tex via \\input/\\include (depth-first)."""
    base = main_tex.parent
    ordered: list[Path] = []
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        if path in seen:
            return
        seen.add(path)
        if not path.exists():
            findings.append(Finding("error", "E5", rel(path), "included file does not exist"))
            return
        ordered.append(path)
        for raw in path.read_text(errors="replace").splitlines():
            line = strip_comments(raw)
            for match in RE_INPUT.finditer(line):
                target = match.group(1).strip()
                child = base / (target if target.endswith(".tex") else f"{target}.tex")
                visit(child)

    visit(main_tex)
    return ordered


def scan_tex(files: list[Path]) -> TexIndex:
    index = TexIndex()
    for path in files:
        for lineno, raw in enumerate(path.read_text(errors="replace").splitlines(), 1):
            line = strip_comments(raw)
            where = (path, lineno)
            for match in RE_LABEL.finditer(line):
                index._add(index.labels, match.group(1).strip(), where)
            for match in RE_REF.finditer(line):
                for key in match.group(1).split(","):
                    index._add(index.refs, key.strip(), where)
            for match in RE_CITE.finditer(line):
                for key in match.group(1).split(","):
                    key = key.strip()
                    if key and key != "*":
                        index._add(index.cites, key, where)
            for match in RE_GRAPHICS.finditer(line):
                index.graphics.append((match.group(1).strip(), path, lineno))
            for match in RE_BIBLIOGRAPHY.finditer(line):
                index.bib_names.extend(name.strip() for name in match.group(1).split(","))
            for match in RE_GRAPHICSPATH.finditer(line):
                index.graphicspath_groups.append(match.group(1))
            for match in RE_TODO_CMD.finditer(line):
                index.todos.append((match.group(1).strip() or "(todo)", path, lineno))
            comment_match = RE_TODO_COMMENT.search(raw)
            if comment_match:
                text = comment_match.group(2).strip() or comment_match.group(1)
                index.todos.append((text, path, lineno))
    return index


def parse_bib(bib_paths: list[Path], findings: list[Finding]) -> dict[str, tuple[Path, int]]:
    keys: dict[str, tuple[Path, int]] = {}
    for bib in bib_paths:
        if not bib.exists():
            findings.append(Finding("error", "E5", rel(bib), "bibliography file does not exist"))
            continue
        for lineno, raw in enumerate(bib.read_text(errors="replace").splitlines(), 1):
            match = RE_BIB_ENTRY.match(raw)
            if not match:
                continue
            entry_type, key = match.group(1).lower(), match.group(2)
            if entry_type in {"comment", "string", "preamble"}:
                continue
            if key in keys:
                findings.append(
                    Finding("warning", "W1", f"{rel(bib)}:{lineno}", f"duplicate bib key '{key}'")
                )
            else:
                keys[key] = (bib, lineno)
    return keys


def graphicspath_dirs(index: TexIndex, draft_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for group in index.graphicspath_groups:
        for match in re.finditer(r"\{([^{}]*)\}", group):
            entry = match.group(1).strip()
            if entry:
                dirs.append((draft_dir / entry).resolve())
    return dirs or [draft_dir]


def check_references(index: TexIndex, findings: list[Finding]) -> None:
    for key, places in index.labels.items():
        if len(places) > 1:
            spots = ", ".join(f"{rel(p)}:{n}" for p, n in places)
            findings.append(Finding("error", "E2", spots, f"label '{key}' defined more than once"))
        if not LABEL_PREFIX.match(key):
            path, lineno = places[0]
            findings.append(
                Finding(
                    "warning",
                    "W5",
                    f"{rel(path)}:{lineno}",
                    f"label '{key}' lacks a ch:/sec:/subsec:/fig:/tab:/eq:/alg:/app: prefix",
                )
            )
    for key, places in index.refs.items():
        if key not in index.labels:
            path, lineno = places[0]
            findings.append(
                Finding(
                    "error", "E1", f"{rel(path)}:{lineno}", f"reference to undefined label '{key}'"
                )
            )
    for key, places in index.labels.items():
        if key.startswith(("fig:", "tab:")) and key not in index.refs:
            path, lineno = places[0]
            findings.append(
                Finding(
                    "warning", "W4", f"{rel(path)}:{lineno}", f"label '{key}' is never referenced"
                )
            )


def check_citations(
    index: TexIndex, bib_keys: dict[str, tuple[Path, int]], findings: list[Finding]
) -> None:
    for key, places in index.cites.items():
        if key not in bib_keys:
            path, lineno = places[0]
            findings.append(
                Finding(
                    "error",
                    "E3",
                    f"{rel(path)}:{lineno}",
                    f"cited key '{key}' is not in the .bib file",
                )
            )
    for key, (bib, lineno) in bib_keys.items():
        if key not in index.cites:
            findings.append(
                Finding(
                    "warning", "W2", f"{rel(bib)}:{lineno}", f"bib entry '{key}' is never cited"
                )
            )


def check_figures(index: TexIndex, dirs: list[Path], findings: list[Finding]) -> None:
    used_stems: set[str] = set()
    for target, path, lineno in index.graphics:
        target_path = Path(target)
        candidates: list[Path] = []
        if target_path.suffix:
            used_stems.add(target_path.stem)
            candidates = [d / target for d in dirs]
        else:
            used_stems.add(target_path.name)
            candidates = [d / f"{target}{ext}" for d in dirs for ext in FIGURE_EXTENSIONS]
        if not any(c.exists() for c in candidates):
            findings.append(
                Finding(
                    "error",
                    "E4",
                    f"{rel(path)}:{lineno}",
                    f"figure '{target}' not found under any \\graphicspath directory "
                    "-- generate it from the study script first",
                )
            )

    stem_locations: dict[str, list[Path]] = {}
    for directory in dirs:
        if not directory.is_dir():
            continue
        for figure in sorted(directory.iterdir()):
            if figure.suffix.lower() not in FIGURE_EXTENSIONS:
                continue
            stem_locations.setdefault(figure.stem, []).append(figure)
            if figure.stem not in used_stems and figure.name not in used_stems:
                findings.append(
                    Finding(
                        "warning", "W3", rel(figure), "figure file is never \\includegraphics'd"
                    )
                )
    for stem, paths in stem_locations.items():
        parents = {p.parent for p in paths}
        if len(parents) > 1:
            spots = ", ".join(rel(p) for p in paths)
            findings.append(
                Finding(
                    "warning",
                    "W6",
                    spots,
                    f"figure basename '{stem}' exists in multiple directories",
                )
            )


def check_log(log_path: Path, findings: list[Finding]) -> None:
    if not log_path.exists():
        findings.append(
            Finding(
                "info", "I2", "", f"{rel(log_path)} not found — run `make pdf` first for log checks"
            )
        )
        return
    overfull = 0
    for raw in log_path.read_text(errors="replace").splitlines():
        if RE_LOG_OVERFULL.match(raw):
            overfull += 1
            continue
        error_match = RE_LOG_ERROR.match(raw)
        if error_match:
            findings.append(
                Finding("error", "I2", rel(log_path), f"LaTeX error: {error_match.group(1)}")
            )
            continue
        for regex, label in ((RE_LOG_UNDEF_REF, "reference"), (RE_LOG_UNDEF_CITE, "citation")):
            match = regex.search(raw)
            if match:
                findings.append(
                    Finding(
                        "warning",
                        "I2",
                        rel(log_path),
                        f"undefined {label} '{match.group(1)}' in last build",
                    )
                )
    if overfull:
        findings.append(
            Finding("info", "I2", rel(log_path), f"{overfull} overfull \\hbox in last build")
        )


def run_checks(
    draft_dir: Path, *, main_name: str = "main.tex", with_log: bool = True
) -> list[Finding]:
    findings: list[Finding] = []
    files = resolve_include_graph(draft_dir / main_name, findings)
    index = scan_tex(files)

    bib_paths = [draft_dir / f"{name}.bib" for name in index.bib_names]
    bib_keys = parse_bib(bib_paths, findings)

    check_references(index, findings)
    check_citations(index, bib_keys, findings)
    check_figures(index, graphicspath_dirs(index, draft_dir), findings)
    for text, path, lineno in index.todos:
        findings.append(Finding("info", "I1", f"{rel(path)}:{lineno}", f"TODO: {text}"))
    if with_log:
        check_log(draft_dir / f"{Path(main_name).stem}.log", findings)
    return findings


def print_report(findings: list[Finding]) -> tuple[int, int]:
    order = {"error": 0, "warning": 1, "info": 2}
    findings = sorted(findings, key=lambda f: (order[f.severity], f.code, f.location))
    counts = {"error": 0, "warning": 0, "info": 0}
    current = None
    for finding in findings:
        counts[finding.severity] += 1
        if finding.severity != current:
            current = finding.severity
            print(f"\n== {current.upper()}S ==")
        location = f"{finding.location}: " if finding.location else ""
        print(f"{location}[{finding.code}] {finding.message}")
    todos = sum(1 for f in findings if f.code == "I1")
    print(f"\nSummary: {counts['error']} error(s), {counts['warning']} warning(s), {todos} TODO(s)")
    return counts["error"], counts["warning"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--draft-dir", default="draft", help="manuscript directory (default: draft)"
    )
    parser.add_argument("--main", default="main.tex", help="root TeX file (default: main.tex)")
    parser.add_argument("--strict", action="store_true", help="warnings also fail the check")
    parser.add_argument("--no-log", action="store_true", help="skip main.log parsing")
    args = parser.parse_args(argv)

    draft_dir = Path(args.draft_dir)
    if not draft_dir.is_absolute():
        draft_dir = REPO_ROOT / draft_dir
    if not (draft_dir / args.main).exists():
        print(f"error: {rel(draft_dir / args.main)} not found", file=sys.stderr)
        return 2

    findings = run_checks(draft_dir, main_name=args.main, with_log=not args.no_log)
    errors, warnings = print_report(findings)
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
