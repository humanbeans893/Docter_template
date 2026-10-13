#!/usr/bin/env python3
"""Static consistency checks for the dissertation manuscript.

Stdlib only, so it runs identically on the host (``python3`` 3.10 or newer:
``python3 tools/thesis_check.py``, what ``make check`` runs) and inside Docker
(``uv run python tools/thesis_check.py``).

The scan follows the ``\\input``/``\\include``/``\\ThesisValues`` graph reachable from
the root file, in the order TeX reads it (comment-stripped, so disabled
``% \\include{...}`` lines are ignored). Citations, references, figures, value uses and
the thesis metadata may be wrapped over several lines (``\\citep{a,`` / ``  b}``);
\\label, \\graphicspath and the other commands are matched on one line. A macro defined
with \\newcommand (\\renewcommand, \\providecommand, \\DeclareRobustCommand) that hands
its parameters to \\includegraphics, \\label, \\ref/\\cref, \\cite or \\val
(``\\newcommand{\\studyfig}[2]{...\\includegraphics{#1}...\\label{fig:#1}}``) is read
where it is used, with the arguments filled in; its definition is not a use.

Usage:
  python3 tools/thesis_check.py                 # draft/main.tex + draft/build/main/main.log
  python3 tools/thesis_check.py --all           # main.tex, review.tex, supplementary.tex
  python3 tools/thesis_check.py --main submission.tex --main supplementary.tex \\
      --submission --strict                    # make check-final: both checked as one
  python3 tools/thesis_check.py --list-generators   # scripts that regenerate every artifact

Several documents (--all, or --main given more than once) are checked as one: a figure
or bib entry that any of them uses counts as used.

Severities:
  error   (exit 1)  broken cross-references, citations, figures, values or provenance
  warning (exit 1 with --strict) hygiene issues worth fixing before submission
  info    TODO inventory, compile-log findings, R3 artifacts, unverified bib entries

Checks:
  E1 \\ref/\\cref/\\crefrange/\\cpageref/\\labelcref/\\nameref/... target has no matching \\label
  E2 duplicate \\label keys
  E3 \\cite key missing from the bibliography (.bib), or the document has no \\bibliography
  E4 \\includegraphics file not found in draft/ or any \\graphicspath directory
  E5 \\input/\\include/\\bibliography file missing on disk
  E6 required thesis metadata is missing or still a placeholder (submission mode)
  E7 TODO/FIXME remains (submission mode)
  E8 \\val/\\valqty/\\rawval key that no \\defvalue/\\deftextvalue defines
  E9 abstract or acknowledgments without body text, or an optional front-matter page
     switched on in thesis-config.tex that still has its template text (submission mode)
  E10 figure, \\input or \\ThesisValues target under projects/*/experiments/ or
      projects/*/data/
  E11 value defined only after \\begin{document} (register its file in draft/values.tex)
  E12 a publication killed midway: projects/<study>/result/.publication.json is left, so
      result/ and data/processed/ may mix old and new artifacts (the next full run of an
      experiment in that study rolls it back; an unreadable journal is repaired by hand,
      from git)
  W1 duplicate bibliography keys
  W2 bibliography entries never cited
  W3 hand-made figure file never included: one in draft/figures/ (or another \\graphicspath
     directory outside the studies' result/figures/), or a file in result/figures/ that no
     sidecar lists; an unused generated figure is I5 instead
  W4 fig:/tab: labels never referenced
  W5 labels not following the prefix convention (ch:/sec:/subsec:/fig:/tab:/eq:/alg:/app:)
  W6 identical figure basenames in multiple \\graphicspath directories (shadowing)
  W7 bare \\ref usage instead of \\cref
  W8 required thesis metadata still contains a template placeholder
  W9 duplicate PDF page anchors in the last build
  W10 overfull boxes in the last build
  W11 provenance: a generated figure, table or values file without its sidecar
      (<name>.provenance.json) or whose sha256 differs from it; a hand-made figure in
      draft/figures/ missing from draft/figures/README.md
  W12 the same value key defined more than once
  W13 two bibliography entries with the same DOI
  W14 artifact from an experiment that is withdrawn, stopped or replaced, that has no
      conclusion yet (進行中), whose status is not a status word, or that has no row in
      EXP_SUMMARY.md/EXP_ARCHIVE.md (error with --submission). Besides the sidecar's own
      experiment, the `sources` it records are followed: a generated file with its own
      sidecar (a result/tables/*.csv a promotion script read, and so on) and a file under
      projects/<study>/data/processed/NNN_<slug>/ or experiments/NNN_<slug>/
  W15 artifact generated from uncommitted or unknown code (error with --submission); the
      generated files in its `sources` are followed as for W14 (a scripts/ figure drawn
      from a CSV that a run with uncommitted code promoted)
  W16 file in projects/<study>/result/{figures,tables}/ not named <study>-...
  W17 values file registered with \\ThesisValues not generated yet (error with --submission)
  W18 temporaries of a killed publication (.<name>.<pid>.part/.previous) left in a
      study's result/ or data/processed/ (error with --submission)
  I1 TODO/FIXME inventory (\\todo{...} and %-comments)
  I2 findings from draft/build/<job>/<job>.log (errors, undefined references/citations)
  I3 artifacts included as-is or transcribed (reproducibility R3)
  I4 bibliography entries without a valid `verified` field (error with --submission)
  I5 generated figures in a study's result/figures/ that no checked document includes,
     per experiment or script (an experiment's diagnostics, a withdrawn experiment's figure)
  I6 \\includegraphics, \\label, \\ref, \\cite or \\val with a macro parameter (#1) in a
     macro the checker cannot expand (\\def, \\NewDocumentCommand, ...): what it places is
     not checked
"""

import argparse
import bisect
import hashlib
import json
import re
import shlex
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

# The host python3 runs this file; stop with one line instead of a TypeError on old ones.
if sys.version_info < (3, 10):  # noqa: UP036
    sys.exit(f"{Path(__file__).name}: needs python3 3.10 or newer, not {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parents[1]
# The documents `--all` checks (submission.tex is main.tex in final mode).
ALL_MAINS = ("main.tex", "review.tex", "supplementary.tex")

LABEL_PREFIX = re.compile(r"^(ch|sec|subsec|fig|tab|eq|alg|app):")
# graphicx (LuaTeX driver) tries these for an extension-less \includegraphics, in this
# order, and for each extension the current directory before every \graphicspath entry.
GRAPHICS_EXTENSIONS = (".pdf", ".png", ".jpg", ".mps", ".jpeg", ".jbig2", ".jb2", ".eps")
GRAPHICS_SEARCH_ORDER = GRAPHICS_EXTENSIONS + tuple(ext.upper() for ext in GRAPHICS_EXTENSIONS)
# The make target that writes each job's log (draft/compile.sh).
LOG_COMMANDS = {
    "main": "make pdf",
    "review": "make pdf-review",
    "submission": "make pdf-final",
    "supplementary": "make supplementary",
}
FRONT_MATTER_BODIES = (
    "frontmatter/abstract-en.tex",
    "frontmatter/abstract-ja.tex",
    "frontmatter/acknowledgments.tex",
)
# Optional pages main.tex prints only under \ifThesisInclude<flag> (set in thesis-config.tex).
# Their template text carries a `% thesis:placeholder` comment until it is replaced.
OPTIONAL_FRONT_MATTER = {
    "frontmatter/declaration.tex": "Declaration",
    "frontmatter/publications.tex": "Publications",
    "frontmatter/abbreviations.tex": "Abbreviations",
    "frontmatter/symbols.tex": "Symbols",
}
# The status words of an experiment (AGENTS.md 実験): the 状態 cell of its index row and the
# 状態 line of its summary.md start with one of them. tests/test_repo_structure.py imports
# STATUS_WORDS and status_word(), so the check and the test cannot drift apart.
STATUS_WORDS = ("進行中", "完了", "中止", "訂正", "撤回", "置き換え")
# Artifacts of these experiments must not reach the thesis (W14).
BLOCKED_STATUSES = ("撤回", "中止", "置き換え")
# An experiment without a conclusion yet (W14 as well: write its summary.md first).
OPEN_STATUS = "進行中"
EXPERIMENT_INDEXES = ("EXP_SUMMARY.md", "EXP_ARCHIVE.md")
GENERATOR_COMMAND = "docker compose exec research-template uv run python"

REQUIRED_METADATA = {
    "ThesisTitleEN",
    "ThesisTitleJA",
    "ThesisAuthorEN",
    "ThesisAuthorJA",
    "ThesisDegreeEN",
    "ThesisDegreeJA",
    "ThesisUniversityEN",
    "ThesisUniversityJA",
    "ThesisGraduateSchoolEN",
    "ThesisGraduateSchoolJA",
    "ThesisDepartmentEN",
    "ThesisDepartmentJA",
    "ThesisSupervisorEN",
    "ThesisSupervisorJA",
    "ThesisSubmissionDateEN",
    "ThesisSubmissionDateJA",
    "ThesisKeywordsEN",
    "ThesisKeywordsJA",
}
PLACEHOLDER_VALUES = {
    "Dissertation Title",
    "博士論文題目",
    "Author Name",
    "著者名",
    "博士（専門分野）",
    "University Name",
    "大学名",
    "Graduate School Name",
    "研究科名",
    "Department Name",
    "専攻名",
    "Supervisor Name",
    "指導教員名",
    "July 2026",
    "2026年7月",
    "keyword one; keyword two; keyword three",
    "キーワード1；キーワード2；キーワード3",
}

RE_INCLUDE_EDGE = re.compile(r"\\(input|include|ThesisValues)\s*\{([^{}]+)\}")
RE_BEGIN_DOCUMENT = re.compile(r"\\begin\s*\{document\}")
RE_LABEL = re.compile(r"\\label\{([^}]+)\}")
# The commands that refer to labels, one key or a comma list (LaTeX, amsmath, hyperref,
# cleveref, varioref, subcaption) ...
RE_REF = re.compile(
    r"\\(?:ref|eqref|pageref|autoref|[nN]ameref|subref|[cC]ref|[cC]pageref|labelc(?:page)?ref"
    r"|(?:lc)?name[cC]refs?|[vV]ref|vpageref|fullref)\*?(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}"
)
# ... and those that take the two ends of a range (\crefrange{fig:a}{fig:c}).
RE_REF_RANGE = re.compile(
    r"\\[cCvV](?:page)?refrange\*?(?:\s*\[[^\]]*\]){0,2}"
    r"\s*\{([^}]+)\}\s*\{([^}]+)\}"
)
RE_BARE_REF = re.compile(r"\\ref\*?\{([^}]+)\}")
# natbib's \citetext takes free text and \citestyle a style name: neither takes keys.
RE_CITE = re.compile(
    r"\\(?!(?:citetext|citestyle)(?![a-zA-Z]))(?:[cC]ite[a-zA-Z]*|nocite)\*?"
    r"(?:\s*\[[^\]]*\]){0,2}\s*\{([^{}]+)\}"
)
RE_GRAPHICS = re.compile(r"\\includegraphics\*?(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}")
RE_BIBLIOGRAPHY = re.compile(r"\\bibliography\{([^}]+)\}")
RE_GRAPHICSPATH = re.compile(r"\\graphicspath\{((?:\s*\{[^{}]*\}\s*)+)\}")
RE_TODO_CMD = re.compile(r"\\todo(?:\[[^\]]*\])?\{([^}]*)")
RE_TODO_COMMENT = re.compile(r"%.*?\b(TODO|FIXME)\b[:\s]*(.*)")
# The value is the balanced {...} group after it (it may span lines).
RE_METADATA = re.compile(r"\\newcommand\s*\{\\(Thesis[A-Za-z]+)\}\s*(?=\{)")
RE_INCLUDE_FLAG = re.compile(r"\\ThesisInclude([A-Za-z]+)(true|false)(?![A-Za-z])")
RE_PLACEHOLDER_MARK = re.compile(r"%\s*thesis:placeholder\s*")
# Generated values (draft/values.tex). Keys with `#` are the macro definitions themselves.
RE_VALUE_USE = re.compile(r"\\(?:val|valqty|rawval)\s*\{([^{}]+)\}")
RE_VALUE_DEF = re.compile(r"\\(?:def|deftext)value\s*\{([^{}]+)\}")
# A macro definition the checker can expand at each use: \newcommand{\name}[n][default]{body}
# (or \newcommand\name..., \renewcommand, \providecommand, \DeclareRobustCommand, starred).
RE_NEWCOMMAND = re.compile(
    r"\\(?:(?:re|provide)?newcommand|DeclareRobustCommand)\*?\s*"
    r"(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))\s*(?:\[\s*([1-9])\s*\])?\s*"
)
RE_PARAMETER = re.compile(r"#([1-9])")
# The command a match of one of the patterns above starts with (I6 names it as written).
RE_COMMAND_NAME = re.compile(r"\\[A-Za-z@]+\*?")
# Leftovers of a run's publication (projects/<study>/src/utils/experiment.py): its journal
# in result/, and .<name>.<pid>.part / .<name>.<pid>.previous beside each destination.
PUBLICATION_JOURNAL = ".publication.json"
RE_PUBLICATION_TEMP = re.compile(r"^\.(?P<name>.+)\.(?P<pid>\d+)\.(?:part|previous)$")

RE_BIB_ENTRY = re.compile(r"^\s*@(\w+)\s*\{\s*([^,\s{}]+)\s*,")
RE_VERIFIED = re.compile(r"^\d{4}-\d{2}-\d{2}\s*,\s*(?:doi|isbn|url):\S+$")
DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi.org/",
    "doi:",
)

RE_LOG_UNDEF_REF = re.compile(r"LaTeX Warning: Reference `([^']+)' on page")
# natbib (loaded by preamble.tex) reports undefined citations in its own words.
RE_LOG_UNDEF_CITE = re.compile(r"(?:LaTeX|Package natbib) Warning: Citation `([^']+)'")
RE_LOG_OVERFULL = re.compile(r"^Overfull \\[hv]box")
# `! message` or, with -file-line-error (compile.sh), `./file.tex:12: message`.
RE_LOG_ERROR = re.compile(r"^(?:! |(\S+?\.\w+):(\d+): )(.+)")
RE_LOG_DUPLICATE_ANCHOR = re.compile(r"ignoring duplicate destination with the name '([^']+)'")


@dataclass
class Finding:
    severity: str  # "error" | "warning" | "info"
    code: str
    location: str  # "path:line" (repo-relative) or ""
    message: str
    # What the finding is about (a figure stem, a bib key), for combining --all results.
    subject: str = ""


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
    for base in (REPO_ROOT, REPO_ROOT.resolve()):
        try:
            return Path(path).relative_to(base).as_posix()
        except ValueError:
            continue
    return str(path)


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_parts(path: Path, root: Path) -> tuple[str, ...]:
    """Path parts below ``root/projects`` (``(study, area, ...)``), or ``()`` outside it."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return ()
    return parts[1:] if len(parts) >= 2 and parts[0] == "projects" else ()


def in_raw_or_experiment(path: Path, root: Path) -> bool:
    parts = project_parts(path, root)
    return len(parts) >= 3 and parts[1] in {"experiments", "data"}


# --- Include graph ------------------------------------------------------------------------------


@dataclass
class Edge:
    kind: str  # "input" | "include" | "ThesisValues"
    target: Path  # the file TeX reads (resolved)
    origin: Path
    lineno: int


@dataclass
class Graph:
    files: list[Path] = field(default_factory=list)  # reading order of first visits
    edges: list[Edge] = field(default_factory=list)
    # (line, column) from which each file is inside the document body.
    doc_from: dict[Path, tuple[int, int]] = field(default_factory=dict)

    def in_document(self, path: Path, lineno: int, column: int = 0) -> bool:
        start = self.doc_from.get(path)
        return start is not None and (lineno, column) >= start


def tex_target(draft_dir: Path, target: str) -> Path:
    """The file TeX reads for ``\\input{target}`` (``.tex`` appended unless given)."""
    base = draft_dir / target
    candidate = base if target.endswith(".tex") else base.with_name(base.name + ".tex")
    if not candidate.is_file() and base.is_file():
        candidate = base
    return candidate.resolve()


def resolve_include_graph(main_tex: Path, findings: list[Finding]) -> Graph:
    """Files reachable from the root via \\input/\\include/\\ThesisValues, in reading order.

    TeX resolves every relative path against draft/ (compile.sh runs there), so children
    are resolved against the root's directory, not the including file's.
    """
    main_tex = Path(main_tex).resolve()
    draft_dir = main_tex.parent
    graph = Graph()
    seen: set[Path] = set()
    in_document = False

    def visit(path: Path, edge: Edge | None) -> None:
        nonlocal in_document
        if path in seen:
            return
        seen.add(path)
        if not path.is_file():
            # A registered values file that is not generated yet is W17, not E5.
            if edge is None or edge.kind != "ThesisValues":
                origin = f" (from {rel(edge.origin)}:{edge.lineno})" if edge else ""
                findings.append(
                    Finding("error", "E5", rel(path), f"included file does not exist{origin}")
                )
            return
        graph.files.append(path)
        if in_document:
            graph.doc_from[path] = (0, 0)
        for lineno, raw in enumerate(read_lines(path), 1):
            line = strip_comments(raw)
            events = [(m.start(), m) for m in RE_INCLUDE_EDGE.finditer(line)]
            events += [(m.start(), None) for m in RE_BEGIN_DOCUMENT.finditer(line)]
            for column, match in sorted(events, key=lambda event: event[0]):
                if match is None:
                    if not in_document:
                        in_document = True
                        graph.doc_from.setdefault(path, (lineno, column))
                    continue
                target = match.group(2).strip()
                if not target or "#" in target or "\\" in target:
                    continue  # macro arguments, not files
                child = tex_target(draft_dir, target)
                child_edge = Edge(match.group(1), child, path, lineno)
                graph.edges.append(child_edge)
                visit(child, child_edge)
                if in_document and path not in graph.doc_from:
                    graph.doc_from[path] = (lineno, column + 1)

    visit(main_tex, None)
    return graph


# --- Scan ----------------------------------------------------------------------------------------


class TexIndex:
    """Occurrences keyed by name -> list of (file, lineno)."""

    def __init__(self):
        self.labels: dict[str, list[tuple[Path, int]]] = {}
        self.refs: dict[str, list[tuple[Path, int]]] = {}
        self.bare_refs: list[tuple[str, Path, int]] = []
        self.cites: dict[str, list[tuple[Path, int]]] = {}
        self.graphics: list[tuple[str, Path, int]] = []
        self.todos: list[tuple[str, Path, int]] = []
        self.bib_names: list[str] = []
        self.graphicspath_groups: list[str] = []
        self.value_uses: list[tuple[str, Path, int]] = []
        # key -> [(file, lineno, defined after \begin{document})]
        self.value_defs: dict[str, list[tuple[Path, int, bool]]] = {}
        # (command, key with #n, file, lineno) in a macro the checker cannot expand
        self.macro_params: list[tuple[str, str, Path, int]] = []

    @staticmethod
    def _add(index: dict, key: str, where: tuple) -> None:
        index.setdefault(key, []).append(where)


def joined_text(lines: list[str]) -> tuple[str, list[int]]:
    """``lines`` joined with newlines, and the offset at which each line starts."""
    starts = [0]
    for line in lines[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    return "\n".join(lines), starts


def line_at(starts: list[int], offset: int) -> int:
    """The 1-based line of ``offset`` in a text joined by :func:`joined_text`."""
    return bisect.bisect_right(starts, offset)


# The commands whose arguments the checker reads: a macro that hands one of its parameters
# to them is a wrapper, read at each use.
READ_COMMANDS = (RE_REF, RE_REF_RANGE, RE_CITE, RE_GRAPHICS, RE_LABEL, RE_VALUE_USE)


@dataclass
class Wrapper:
    """A \\newcommand whose body hands a parameter (#1..#9) to a command the checker reads."""

    nargs: int
    default: str | None  # the default of an optional first argument, if it has one
    body: str


def _skip_space(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _in_spans(offset: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= offset < end for start, end in spans)


def find_definitions(text: str) -> list[tuple[str, Wrapper, int, int]]:
    """``(name, macro, start, end)`` of every \\newcommand with parameters in ``text``.

    A command the checker already reads by its name (a redefined \\cref, \\val, ...) is
    left out: it is read where it is used anyway.
    """
    found = []
    for match in RE_NEWCOMMAND.finditer(text):
        name = match.group(1) or match.group(2)
        nargs = int(match.group(3) or 0)
        i, default = match.end(), None
        if nargs and text.startswith("[", i):
            end = _skip_group(text, i, "[", "]")
            default, i = text[i + 1 : end - 1], _skip_space(text, end)
        if not nargs or not text.startswith("{", i):
            continue
        end = _skip_group(text, i, "{", "}")
        if not any(regex.match(f"\\{name}{{x}}{{x}}") for regex in READ_COMMANDS):
            found.append((name, Wrapper(nargs, default, text[i + 1 : end - 1]), match.start(), end))
    return found


def wrapper_names(definitions: dict[str, Wrapper]) -> set[str]:
    """The macros that hand a parameter to a command the checker reads, directly or through
    another such macro (\\newcommand{\\figpair}[2]{\\studyfig{#1}{}\\studyfig{#2}{}})."""
    names = {
        name
        for name, macro in definitions.items()
        if any(
            "#" in key
            for regex in READ_COMMANDS
            for match in regex.finditer(macro.body)
            for key in match.groups()
            if key
        )
    }
    while True:
        calls = re.compile(rf"\\(?:{'|'.join(map(re.escape, names))})(?![A-Za-z@])")
        more = {
            name
            for name, macro in definitions.items()
            if name not in names and names and calls.search(macro.body)
        }
        if not more:
            return names
        names |= more


def _group_end(text: str, i: int, opening: str, closing: str) -> int | None:
    """End of the balanced group at ``text[i]``, or None when it is not closed."""
    end = _skip_group(text, i, opening, closing)
    return end if text[end - 1 : end] == closing else None


def macro_arguments(text: str, i: int, wrapper: Wrapper) -> list[str] | None:
    """The arguments of a wrapper used just before ``text[i]``, or None if they are cut off."""
    args: list[str] = []
    if wrapper.default is not None:
        j = _skip_space(text, i)
        if text.startswith("[", j):
            end = _group_end(text, j, "[", "]")
            if end is None:
                return None
            args.append(text[j + 1 : end - 1])
            i = end
        else:
            args.append(wrapper.default)
    while len(args) < wrapper.nargs:
        j = _skip_space(text, i)
        if j >= len(text) or text[j] in "}]":
            return None
        if text[j] == "{":
            end = _group_end(text, j, "{", "}")
            if end is None:
                return None
            args.append(text[j + 1 : end - 1])
            i = end
        else:  # a single token: \macro or one character
            token = re.match(r"\\(?:[A-Za-z@]+|.)|.", text[j:], flags=re.DOTALL)
            args.append(token.group(0))
            i = j + len(token.group(0))
    return args


def expand_wrappers(
    text: str, wrappers: dict[str, Wrapper], spans: list[tuple[int, int]], depth: int = 0
) -> list[tuple[int, str]]:
    """``(offset of the use, body with its arguments filled in)`` for each wrapper use.

    Uses inside ``spans`` (the definitions) are skipped; a wrapper used in another's body
    is expanded too (a few levels deep), at the offset of the outer use.
    """
    if not wrappers or depth > 4:
        return []
    names = "|".join(re.escape(name) for name in sorted(wrappers, key=len, reverse=True))
    uses: list[tuple[int, str]] = []
    for match in re.finditer(rf"\\({names})(?![A-Za-z@])", text):
        if _in_spans(match.start(), spans):
            continue
        wrapper = wrappers[match.group(1)]
        args = macro_arguments(text, match.end(), wrapper)
        if args is None:
            continue
        body = fill_parameters(wrapper.body, args)
        uses.append((match.start(), body))
        for _, inner in expand_wrappers(body, wrappers, [], depth + 1):
            uses.append((match.start(), inner))
    return uses


def fill_parameters(body: str, args: list[str]) -> str:
    """``body`` with #1..#n replaced by ``args`` (in one pass: an argument may contain #)."""

    def argument(parameter: re.Match) -> str:
        k = int(parameter.group(1))
        return args[k - 1] if k <= len(args) else parameter.group(0)

    return RE_PARAMETER.sub(argument, body)


def scan_uses(
    index: TexIndex,
    text: str,
    path: Path,
    starts: list[int],
    spans: list[tuple[int, int]],
    *,
    at: int | None = None,
) -> None:
    """References, citations, figures and value uses in ``text`` (a comment-stripped file).

    ``spans`` are the wrapper definitions in it: not uses (only a bare \\ref there is
    reported, once). With ``at``, ``text`` is a wrapper's body expanded at that offset of
    the file: its \\label keys are read too, and everything is reported at the use's line.
    A key with a macro parameter (#1) outside a wrapper definition is I6.
    """

    def line(match: re.Match) -> int:
        return line_at(starts, match.start() if at is None else at)

    def usable(match: re.Match, key: str) -> bool:
        if at is None and _in_spans(match.start(), spans):
            return False
        if "#" in key:
            if at is None:  # named as written: \cref, \nameref, \citep, \valqty, ...
                command = RE_COMMAND_NAME.match(match.group(0))
                index.macro_params.append((command.group(0), key, path, line(match)))
            return False
        return True

    for match in RE_REF.finditer(text):
        for key in match.group(1).split(","):
            if usable(match, key.strip()):
                index._add(index.refs, key.strip(), (path, line(match)))
    for match in RE_REF_RANGE.finditer(text):
        for key in match.groups():
            if usable(match, key.strip()):
                index._add(index.refs, key.strip(), (path, line(match)))
    if at is None:  # a wrapper's bare \ref is reported once, at its definition
        for match in RE_BARE_REF.finditer(text):
            index.bare_refs.append((match.group(1).strip(), path, line(match)))
    for match in RE_CITE.finditer(text):
        for key in match.group(1).split(","):
            key = key.strip()
            if key and key != "*" and usable(match, key):
                index._add(index.cites, key, (path, line(match)))
    for match in RE_GRAPHICS.finditer(text):
        target = match.group(1).strip()
        if usable(match, target):
            index.graphics.append((target, path, line(match)))
    for match in RE_VALUE_USE.finditer(text):
        key = match.group(1).strip()
        if usable(match, key):
            index.value_uses.append((key, path, line(match)))
    if at is not None:
        for match in RE_LABEL.finditer(text):
            key = match.group(1).strip()
            if usable(match, key):
                index._add(index.labels, key, (path, line(match)))


def scan_tex(graph: Graph) -> TexIndex:
    index = TexIndex()
    files = []
    definitions: dict[str, Wrapper] = {}
    for path in graph.files:
        raws = read_lines(path)
        lines = [strip_comments(raw) for raw in raws]
        # Arguments of \cite, \ref, \includegraphics and \val are often wrapped onto the
        # next lines, so these are matched on the whole comment-stripped file and reported
        # at the line where the command starts.
        text, starts = joined_text(lines)
        found = find_definitions(text)
        for name, macro, _, _ in found:
            definitions[name] = macro  # a later \renewcommand wins, as in TeX
        files.append((path, raws, lines, text, starts, found))
    names = wrapper_names(definitions)
    wrappers = {name: definitions[name] for name in names}
    for path, raws, lines, text, starts, found in files:
        spans = [(start, end) for name, _, start, end in found if name in names]
        scan_uses(index, text, path, starts, spans)
        for offset, body in expand_wrappers(text, wrappers, spans):
            scan_uses(index, body, path, starts, [], at=offset)
        for lineno, (raw, line) in enumerate(zip(raws, lines, strict=True), 1):
            where = (path, lineno)
            for match in RE_LABEL.finditer(line):
                key = match.group(1).strip()
                if _in_spans(starts[lineno - 1] + match.start(), spans):
                    continue  # read at each use of the wrapper
                if "#" in key:
                    index.macro_params.append(("\\label", key, path, lineno))
                    continue
                index._add(index.labels, key, where)
            for match in RE_BIBLIOGRAPHY.finditer(line):
                index.bib_names.extend(name.strip() for name in match.group(1).split(","))
            for match in RE_GRAPHICSPATH.finditer(line):
                index.graphicspath_groups.append(match.group(1))
            for match in RE_VALUE_DEF.finditer(line):
                key = match.group(1).strip()
                if "#" not in key:
                    after = graph.in_document(path, lineno, match.start())
                    index._add(index.value_defs, key, (path, lineno, after))
            for match in RE_TODO_CMD.finditer(line):
                index.todos.append((match.group(1).strip() or "(todo)", path, lineno))
            comment_match = RE_TODO_COMMENT.search(raw)
            if comment_match:
                note = comment_match.group(2).strip() or comment_match.group(1)
                index.todos.append((note, path, lineno))
    return index


# --- Bibliography --------------------------------------------------------------------------------


@dataclass
class BibEntry:
    key: str
    path: Path
    lineno: int
    text: str  # the entry's source lines (comment lines dropped)


def bib_field(text: str, name: str) -> str | None:
    """Value of a BibTeX field (outer braces or quotes removed), or None."""
    pattern = rf"(?<![\w-]){name}\s*=\s*(\{{(?:[^{{}}]|\{{[^{{}}]*\}})*\}}|\"[^\"]*\"|[^,}}\s]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] + value[-1] in ("{}", '""'):
        value = value[1:-1]
    return value.strip()


def normalise_doi(value: str) -> str:
    doi = value.strip().lower()
    for prefix in DOI_PREFIXES:
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.strip()


def parse_bib(bib_paths: list[Path], findings: list[Finding]) -> list[BibEntry]:
    """Entries of the bibliography files, first occurrence per key (W1 for the rest)."""
    entries: list[BibEntry] = []
    keys: set[str] = set()

    def close(entry: BibEntry | None, body: list[str]) -> None:
        if entry is not None:
            entry.text = "\n".join(body)
            entries.append(entry)

    for bib in bib_paths:
        if not bib.exists():
            findings.append(Finding("error", "E5", rel(bib), "bibliography file does not exist"))
            continue
        current: BibEntry | None = None
        lines: list[str] = []
        for lineno, raw in enumerate(read_lines(bib), 1):
            match = RE_BIB_ENTRY.match(raw)
            if match:
                close(current, lines)
                current, lines = None, []
                entry_type, key = match.group(1).lower(), match.group(2)
                if entry_type in {"comment", "string", "preamble"}:
                    continue
                if key in keys:
                    findings.append(
                        Finding(
                            "warning", "W1", f"{rel(bib)}:{lineno}", f"duplicate bib key '{key}'"
                        )
                    )
                    continue
                keys.add(key)
                current = BibEntry(key, bib, lineno, "")
                lines = [raw[match.end() :]]
            elif current is not None and not raw.lstrip().startswith("%"):
                lines.append(raw)
        close(current, lines)
    return entries


def check_bib_fields(entries: list[BibEntry], findings: list[Finding], *, submission: bool):
    by_doi: dict[str, list[BibEntry]] = {}
    for entry in entries:
        doi = bib_field(entry.text, "doi")
        if doi:
            by_doi.setdefault(normalise_doi(doi), []).append(entry)
        verified = bib_field(entry.text, "verified")
        if verified is None:
            problem = "has no `verified` field"
        elif not RE_VERIFIED.match(verified):
            problem = f"has a malformed `verified` field '{verified}'"
        else:
            continue
        findings.append(
            Finding(
                "error" if submission else "info",
                "I4",
                f"{rel(entry.path)}:{entry.lineno}",
                f"bib entry '{entry.key}' {problem} -- check it against the original via its "
                "DOI, then add verified = {YYYY-MM-DD, doi:...} (or isbn:/url:)",
            )
        )
    for doi, same in by_doi.items():
        if len(same) > 1:
            keys = ", ".join(f"'{entry.key}'" for entry in same)
            spots = ", ".join(f"{rel(entry.path)}:{entry.lineno}" for entry in same)
            findings.append(
                Finding("warning", "W13", spots, f"bib entries {keys} share the DOI {doi}")
            )


# --- References, metadata, citations -------------------------------------------------------------


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
    for key, path, lineno in index.bare_refs:
        findings.append(
            Finding(
                "warning",
                "W7",
                f"{rel(path)}:{lineno}",
                f"bare \\ref{{{key}}} used; use \\cref instead",
            )
        )
    reported: set[tuple[Path, int]] = set()
    for command, key, path, lineno in index.macro_params:
        if (path, lineno) in reported:
            continue
        reported.add((path, lineno))
        findings.append(
            Finding(
                "info",
                "I6",
                f"{rel(path)}:{lineno}",
                f"{command}{{{key}}} sits in a macro make check cannot expand (only "
                "\\newcommand macros are read at each use), so what the macro places is not "
                "checked (figures get no provenance checks) -- define it with \\newcommand, or "
                "write the command out in the text",
            )
        )


def check_metadata(files: list[Path], findings: list[Finding], *, submission: bool) -> None:
    definitions: dict[str, tuple[str, Path, int]] = {}
    for path in files:
        # A long title is often wrapped: \newcommand{\ThesisTitleEN}{%<newline>  A long ...}
        text, starts = joined_text([strip_comments(raw) for raw in read_lines(path)])
        for match in RE_METADATA.finditer(text):
            end = _skip_group(text, match.end(), "{", "}")
            value = " ".join(text[match.end() + 1 : end - 1].split())
            definitions[match.group(1)] = (value, path, line_at(starts, match.start()))

    # A missing definition belongs in thesis-config.tex: point there when it is read.
    fallback_path = next(
        (path for path in files if path.name == "thesis-config.tex"),
        files[0] if files else REPO_ROOT / "draft" / "thesis-config.tex",
    )
    for name in sorted(REQUIRED_METADATA):
        value, path, lineno = definitions.get(name, ("", fallback_path, 1))
        if value and value not in PLACEHOLDER_VALUES:
            continue
        severity, code = ("error", "E6") if submission else ("warning", "W8")
        reason = "is empty" if not value else f"still has placeholder value '{value}'"
        findings.append(Finding(severity, code, f"{rel(path)}:{lineno}", f"\\{name} {reason}"))


def check_citations(
    index: TexIndex, bib_keys: dict[str, tuple[Path, int]], findings: list[Finding]
) -> None:
    has_bibliography = any(index.bib_names)
    for key, places in index.cites.items():
        if key not in bib_keys:
            path, lineno = places[0]
            message = (
                f"cited key '{key}' is not in the .bib file"
                if has_bibliography
                else f"cited key '{key}' but this document has no \\bibliography"
            )
            findings.append(Finding("error", "E3", f"{rel(path)}:{lineno}", message))
    for key, (bib, lineno) in bib_keys.items():
        if key not in index.cites:
            findings.append(
                Finding(
                    "warning",
                    "W2",
                    f"{rel(bib)}:{lineno}",
                    f"bib entry '{key}' is never cited",
                    subject=key,
                )
            )


# --- Figures -------------------------------------------------------------------------------------


def graphicspath_dirs(index: TexIndex, draft_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for group in index.graphicspath_groups:
        for match in re.finditer(r"\{([^{}]*)\}", group):
            entry = match.group(1).strip()
            if entry:
                directory = (draft_dir / entry).resolve()
                if directory not in dirs:
                    dirs.append(directory)
    return dirs


def resolve_graphic(target: str, search_dirs: list[Path]) -> Path | None:
    """The file graphicx includes: extension-major, draft/ before each graphicspath dir."""
    if Path(target).suffix.lower() in GRAPHICS_EXTENSIONS:
        candidates = [directory / target for directory in search_dirs]
    else:
        candidates = [
            directory / f"{target}{ext}"
            for ext in GRAPHICS_SEARCH_ORDER
            for directory in search_dirs
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


@dataclass
class UsedFigure:
    target: str
    path: Path  # resolved file
    origin: Path
    lineno: int


def read_sidecar(artifact: Path) -> dict | None:
    """The provenance sidecar beside ``artifact`` as a dict, or None (missing, unreadable)."""
    try:
        data = json.loads(
            (artifact.parent / f"{artifact.stem}.provenance.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def generated_figure(figure: Path, root: Path) -> bool:
    """A figure in a study's result/figures/ that its sidecar lists (a study helper made it)."""
    parts = project_parts(figure, root)
    if len(parts) != 4 or parts[1:3] != ("result", "figures"):
        return False
    files = (read_sidecar(figure) or {}).get("files")
    return isinstance(files, dict) and figure.name in files


def check_figures(
    index: TexIndex, draft_dir: Path, dirs: list[Path], findings: list[Finding], root: Path
) -> tuple[list[UsedFigure], set[str], list[Path]]:
    """E4/W3/W6. Returns the resolved figures, the stems the text refers to and the generated
    figures it does not include (I5, reported once every checked document is known).

    W3 is only for a figure someone placed by hand (draft/figures/, or a result/figures/
    file no sidecar lists): include it or delete it. A generated figure the text does not
    use -- a completed experiment's diagnostic panel, which its run.py publishes again on
    every rerun, or the figure of a withdrawn or replaced experiment, kept for the record --
    is listed (I5) instead of failing --strict.
    """
    search_dirs = [draft_dir, *(d for d in dirs if d != draft_dir)]
    used: list[UsedFigure] = []
    used_stems: set[str] = set()
    for target, path, lineno in index.graphics:
        target_path = Path(target)
        used_stems.add(target_path.stem if target_path.suffix else target_path.name)
        resolved = resolve_graphic(target, search_dirs)
        if resolved is None:
            findings.append(
                Finding(
                    "error",
                    "E4",
                    f"{rel(path)}:{lineno}",
                    f"figure '{target}' not found in draft/ or any \\graphicspath directory "
                    "-- generate it from the study script first",
                )
            )
            continue
        used.append(UsedFigure(target, resolved, path, lineno))

    stem_locations: dict[str, list[Path]] = {}
    unused_generated: list[Path] = []
    for directory in dirs:
        if directory == draft_dir or not directory.is_dir():
            continue
        for figure in sorted(directory.iterdir()):
            if not figure.is_file() or figure.suffix.lower() not in GRAPHICS_EXTENSIONS:
                continue
            stem_locations.setdefault(figure.stem, []).append(figure)
            if figure.stem in used_stems or figure.name in used_stems:
                continue
            if generated_figure(figure, root):
                unused_generated.append(figure.resolve())
            else:
                findings.append(
                    Finding(
                        "warning",
                        "W3",
                        rel(figure),
                        "figure file is never \\includegraphics'd -- include it, or delete it "
                        "if nothing needs it (no study helper made it)",
                        subject=figure.stem,
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
    return used, used_stems, unused_generated


def read_ledger(readme: Path) -> set[str]:
    """First-column entries of the table(s) in draft/figures/README.md."""
    names: set[str] = set()
    if not readme.is_file():
        return names
    for raw in read_lines(readme):
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cell = line.strip("|").split("|")[0].strip().strip("`").strip()
        if not cell or re.fullmatch(r":?-+:?", cell):
            continue
        for prefix in ("draft/figures/", "figures/"):
            if cell.startswith(prefix):
                cell = cell[len(prefix) :]
        names.add(cell)
    return names


def check_figure_ledger(figures_dir: Path, used: list[UsedFigure], findings: list[Finding]) -> None:
    """W11: every hand-made figure in draft/figures/ has a row in its README.md ledger."""
    figures_dir = figures_dir.resolve()
    if not figures_dir.is_dir():
        return
    candidates = {
        path.resolve()
        for path in figures_dir.iterdir()
        if path.is_file() and path.suffix.lower() in GRAPHICS_EXTENSIONS
    }
    for figure in used:
        try:
            inside = figure.path.relative_to(figures_dir).parts
        except ValueError:
            continue
        if inside and inside[0] != "src":
            candidates.add(figure.path)
    ledger = read_ledger(figures_dir / "README.md")
    for path in sorted(candidates):
        if path.name in ledger or path.relative_to(figures_dir).as_posix() in ledger:
            continue
        findings.append(
            Finding(
                "warning",
                "W11",
                rel(path),
                "hand-made figure is not in the ledger draft/figures/README.md -- add a row "
                "(file, content, author or source, how it was made, licence, where used)",
            )
        )


# --- Generated values ----------------------------------------------------------------------------


def check_values(
    index: TexIndex, graph: Graph, findings: list[Finding], *, submission: bool
) -> None:
    """E8 undefined keys, W12 duplicates, E11 late definitions, W17 missing values files."""
    for key, path, lineno in index.value_uses:
        if key not in index.value_defs:
            findings.append(
                Finding(
                    "error",
                    "E8",
                    f"{rel(path)}:{lineno}",
                    f"value '{key}' is not defined -- run the study script that writes it "
                    "(write_latex_values) and register its file in draft/values.tex",
                )
            )
    for key, places in index.value_defs.items():
        if len(places) > 1:
            spots = ", ".join(f"{rel(p)}:{n}" for p, n, _ in places)
            findings.append(
                Finding("warning", "W12", spots, f"value '{key}' is defined more than once")
            )
        for path, lineno, after in places:
            if after:
                findings.append(
                    Finding(
                        "error",
                        "E11",
                        f"{rel(path)}:{lineno}",
                        f"value '{key}' is defined after \\begin{{document}}, so the front "
                        "matter cannot use it -- register the file in draft/values.tex "
                        "(\\ThesisValues{...}) instead of \\input-ing it in a chapter",
                    )
                )
                break
    reported: set[Path] = set()
    for edge in graph.edges:
        if edge.kind != "ThesisValues" or edge.target.is_file() or edge.target in reported:
            continue
        reported.add(edge.target)
        findings.append(
            Finding(
                "error" if submission else "warning",
                "W17",
                f"{rel(edge.origin)}:{edge.lineno}",
                f"values file {rel(edge.target)} is registered but not generated yet -- run the "
                "study script that writes it (write_latex_values)",
            )
        )


def check_locations(
    graph: Graph,
    figures: list[UsedFigure],
    index: TexIndex,
    draft_dir: Path,
    root: Path,
    findings: list[Finding],
) -> None:
    """E10: the thesis reads generated files from result/, never from experiments/ or data/."""
    uses: list[tuple[Path, Path, int]] = [(e.target, e.origin, e.lineno) for e in graph.edges]
    uses += [(f.path, f.origin, f.lineno) for f in figures]
    resolved = {(f.origin, f.lineno, f.target) for f in figures}
    for target, path, lineno in index.graphics:
        if (path, lineno, target) not in resolved:
            uses.append(((draft_dir / target).resolve(), path, lineno))
    for target, origin, lineno in uses:
        if in_raw_or_experiment(target, root):
            findings.append(
                Finding(
                    "error",
                    "E10",
                    f"{rel(origin)}:{lineno}",
                    f"{rel(target)} is read from a study's experiments/ or data/ directory -- "
                    "promote it to result/ in code (save_figure / write_latex_table / "
                    "write_latex_values) and include it from there",
                )
            )


# --- Provenance ----------------------------------------------------------------------------------


@dataclass
class Artifact:
    path: Path  # the generated file TeX reads (resolved)
    kind: str  # "figure" | "table" | "values"
    study: str | None  # projects/<study>/ the file lies in
    sidecar: dict | None = None


HELPERS = {
    "figure": "save_figure (or import_figure for a past image)",
    "table": "write_latex_table",
    "values": "write_latex_values",
}


def collect_artifacts(graph: Graph, figures: list[UsedFigure], root: Path) -> list[Artifact]:
    artifacts: dict[Path, Artifact] = {}
    for figure in figures:
        parts = project_parts(figure.path, root)
        if len(parts) >= 4 and parts[1:3] == ("result", "figures"):
            artifacts.setdefault(figure.path, Artifact(figure.path, "figure", parts[0]))
    for edge in graph.edges:
        if not edge.target.is_file():
            continue
        parts = project_parts(edge.target, root)
        study = parts[0] if parts else None
        if edge.kind == "ThesisValues":
            artifacts.setdefault(edge.target, Artifact(edge.target, "values", study))
        elif len(parts) >= 4 and parts[1:3] == ("result", "tables"):
            artifacts.setdefault(edge.target, Artifact(edge.target, "table", study))
    return list(artifacts.values())


def status_word(cell: str) -> str | None:
    """The status word a 状態 cell or line starts with (Markdown emphasis ignored), or None."""
    text = cell.strip().strip("*_").strip()
    return next((word for word in STATUS_WORDS if text.startswith(word)), None)


def read_experiment_index(study_dir: Path) -> dict[str, tuple[str, str, str]]:
    """``NNN -> (slug, 状態, index file name)`` from a study's EXP_SUMMARY.md and EXP_ARCHIVE.md."""
    rows: dict[str, tuple[str, str, str]] = {}
    for name in EXPERIMENT_INDEXES:
        path = study_dir / "experiments" / name
        if not path.is_file():
            continue
        status_column: int | None = None
        for raw in read_lines(path):
            line = raw.strip()
            if not line.startswith("|"):
                status_column = None
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells[:2] == ["#", "slug"]:
                status_column = cells.index("状態") if "状態" in cells else 3
                continue
            if status_column is None or not re.fullmatch(r"\d{3}", cells[0]):
                continue
            slug = cells[1] if len(cells) > 1 else ""
            status = cells[status_column] if len(cells) > status_column else ""
            rows.setdefault(cells[0], (slug, status, name))
    return rows


# A file an experiment wrote outside result/: data/processed/NNN_<slug>/ or
# experiments/NNN_<slug>/.
RE_EXPERIMENT_PATH = re.compile(r"projects/([^/]+)/(?:data/processed|experiments)/(\d{3}_[^/]+)/")
# An experiment's entry point: the harness reruns a completed one only with --overwrite.
RE_EXPERIMENT_SCRIPT = re.compile(r"projects/[^/]+/experiments/\d{3}_[a-z0-9_]+/run\.py")


def follow_sources(sidecar: dict, root: Path) -> Iterator[tuple[str, dict | None, re.Match | None]]:
    """``(path, upstream sidecar or None, experiment match or None)`` for every recorded source.

    The one traversal of the D12 ``sources`` a sidecar records. A path under
    data/processed/NNN_<slug>/ or experiments/NNN_<slug>/ names its experiment directly
    (``match``); any other generated file is followed through its own sidecar
    (``upstream``) and that sidecar's sources in turn, each sidecar once, so a loop ends.
    """
    pending = [sidecar]
    visited: set[Path] = set()
    while pending:
        for item in pending.pop().get("sources") or []:
            path = item.get("path") if isinstance(item, dict) else None
            if not isinstance(path, str) or not path or Path(path).is_absolute():
                continue
            path = Path(path).as_posix()
            match = RE_EXPERIMENT_PATH.match(path)
            if match:
                yield path, None, match
                continue
            source = root / path
            upstream_path = (source.parent / f"{source.stem}.provenance.json").resolve()
            if upstream_path in visited:
                continue
            visited.add(upstream_path)
            try:
                upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(upstream, dict):
                yield path, upstream, None
                pending.append(upstream)


def experiment_origins(
    sidecar: dict, study: str | None, root: Path
) -> list[tuple[str | None, str, str | None]]:
    """``(study, experiment, via)`` of every experiment an artifact's numbers come from.

    The sidecar's own experiment (``via`` None), then the experiments behind the files it
    lists in ``sources`` (``via`` that path; see ``follow_sources``): a generated file with
    its own sidecar -- such as the result/tables/*.csv a promotion script in scripts/ read
    -- followed through its own sources in turn, and a file under
    data/processed/NNN_<slug>/ or experiments/NNN_<slug>/.
    """
    origins: list[tuple[str | None, str, str | None]] = []
    if sidecar.get("experiment"):
        origins.append((study or sidecar.get("study"), str(sidecar["experiment"]), None))
    for path, upstream, match in follow_sources(sidecar, root):
        if match is not None:
            origins.append((match.group(1), match.group(2), path))
        elif upstream is not None and upstream.get("experiment"):
            parts = Path(path).parts
            in_study = parts[1] if len(parts) > 2 and parts[0] == "projects" else None
            origins.append((upstream.get("study") or in_study, str(upstream["experiment"]), path))
    seen: set[tuple[str | None, str]] = set()
    unique = []
    for origin in origins:
        if origin[:2] not in seen:
            seen.add(origin[:2])
            unique.append(origin)
    return unique


def rerun_hint(script: object) -> str:
    """``script`` as it is re-run (an experiment's run.py replaces a completed run only with
    --overwrite)."""
    text = str(script)
    return f"{text} --overwrite" if RE_EXPERIMENT_SCRIPT.fullmatch(text) else text


def check_provenance(
    artifacts: list[Artifact], root: Path, findings: list[Finding], *, submission: bool
) -> None:
    """W11 sidecar and sha256, W14 experiment status, W15 git state, I3 R3 artifacts."""
    strict = "error" if submission else "warning"
    indexes: dict[str, dict[str, tuple[str, str, str]]] = {}
    for artifact in artifacts:
        location = rel(artifact.path)
        name = artifact.path.name
        sidecar_path = artifact.path.parent / f"{artifact.path.stem}.provenance.json"
        if not sidecar_path.is_file():
            findings.append(
                Finding(
                    "warning",
                    "W11",
                    location,
                    f"{artifact.kind} has no provenance sidecar ({sidecar_path.name}) -- "
                    f"generate it with {HELPERS[artifact.kind]}, not by hand",
                )
            )
            continue
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            findings.append(
                Finding("warning", "W11", location, f"{sidecar_path.name} is unreadable: {exc}")
            )
            continue
        if not isinstance(sidecar, dict):
            findings.append(
                Finding("warning", "W11", location, f"{sidecar_path.name} is not a JSON object")
            )
            continue
        artifact.sidecar = sidecar
        script = sidecar.get("script") or "the study script"

        files = sidecar.get("files")
        files = files if isinstance(files, dict) else {}
        if name not in files:
            findings.append(
                Finding(
                    "warning",
                    "W11",
                    location,
                    f"{name} is not listed in {sidecar_path.name} -- regenerate it with "
                    f"{HELPERS[artifact.kind]}",
                )
            )
        for listed, digest in sorted(files.items()):
            listed_path = artifact.path.parent / listed
            if "/" in listed or "\\" in listed or not listed_path.is_file():
                continue
            if sha256_file(listed_path) != str(digest).lower():
                findings.append(
                    Finding(
                        "warning",
                        "W11",
                        rel(listed_path),
                        f"{listed} differs from {sidecar_path.name} (edited by hand or stale) "
                        f"-- regenerate it: {script}",
                    )
                )

        # The artifact's own code, then that of every generated file it was made from (the
        # same `sources` traversal as W14): a scripts/ figure drawn from a CSV that a run
        # with uncommitted code promoted carries that run's numbers.
        upstreams = [(via, up) for via, up, _ in follow_sources(sidecar, root) if up is not None]
        for via, record in [(None, sidecar), *upstreams]:
            dirty, commit = record.get("git_dirty"), record.get("git_commit")
            if not (dirty is True or dirty == "unknown" or commit in (None, "", "unknown")):
                continue
            reason = "uncommitted code" if dirty is True else "code at an unknown commit"
            if via is None:
                detail, rerun = "", rerun_hint(script)
            else:
                detail = f" (through its source {via})"
                writer = record.get("script") or f"the script that wrote {via}"
                rerun = (
                    f"{rerun_hint(writer)}, then the scripts that read it (in the order "
                    "python3 tools/thesis_check.py --list-generators prints)"
                )
            findings.append(
                Finding(
                    strict,
                    "W15",
                    location,
                    f"{name} was generated from {reason}{detail} -- commit the code, then "
                    f"re-run {rerun} from a clean tree",
                )
            )

        for study, experiment, via in experiment_origins(sidecar, artifact.study, root):
            match = re.fullmatch(r"(\d{3})_(\S+)", str(experiment))
            problem = None
            advice = "regenerate it from a valid experiment or remove it from the text"
            if not study or match is None:
                problem = f"names experiment '{experiment}' that cannot be looked up"
            else:
                if study not in indexes:
                    indexes[study] = read_experiment_index(root / "projects" / study)
                row = indexes[study].get(match.group(1))
                where = f"projects/{study}/experiments"
                if row is None or row[0] != match.group(2):
                    problem = (
                        f"comes from experiment {experiment}, which has no row in "
                        f"{where}/EXP_SUMMARY.md or EXP_ARCHIVE.md"
                    )
                else:
                    _, cell, index_file = row
                    word = status_word(cell)
                    card = f"{where}/{experiment}/summary.md"
                    if word is None:
                        problem = (
                            f"comes from experiment {experiment}, whose status '{cell}' in "
                            f"{where}/{index_file} is not a status word "
                            f"({'・'.join(STATUS_WORDS)}; see {card})"
                        )
                    elif word in BLOCKED_STATUSES:
                        problem = (
                            f"comes from experiment {experiment}, whose status is '{cell}' "
                            f"({where}/{index_file}; see {card})"
                        )
                    elif word == OPEN_STATUS:
                        problem = (
                            f"comes from experiment {experiment}, which has no conclusion yet "
                            f"(状態 {OPEN_STATUS} in {where}/{index_file})"
                        )
                        advice = (
                            f"write the answer in {card} and the index row, or remove it "
                            "from the text"
                        )
            if problem:
                through = f" (through its source {via})" if via else ""
                findings.append(
                    Finding(strict, "W14", location, f"{name} {problem}{through} -- {advice}")
                )

        if sidecar.get("reproducibility") == "R3":
            sources = [
                str(item.get("path"))
                for item in sidecar.get("sources") or []
                if isinstance(item, dict) and item.get("path")
            ]
            origin = (
                ", ".join(sources)
                or sidecar.get("transcribed_from")
                or sidecar.get("source")
                or "source not recorded"
            )
            licence = sidecar.get("license") or "licence not recorded"
            findings.append(
                Finding(
                    "info",
                    "I3",
                    location,
                    f"{sidecar.get('artifact') or name} is included as-is or transcribed "
                    f"(R3, not regenerable): {origin}; {licence}",
                )
            )


def check_result_names(root: Path, findings: list[Finding]) -> None:
    """W16: generated files carry their study's prefix (one namespace for all studies)."""
    projects = root / "projects"
    if not projects.is_dir():
        return
    for study_dir in sorted(projects.iterdir()):
        if not study_dir.is_dir() or study_dir.name.startswith("."):
            continue
        for area in ("figures", "tables"):
            directory = study_dir / "result" / area
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir()):
                if not path.is_file() or path.name.startswith(".") or path.name == "README.md":
                    continue
                if not path.name.startswith(f"{study_dir.name}-"):
                    findings.append(
                        Finding(
                            "warning",
                            "W16",
                            rel(path),
                            f"file name does not start with '{study_dir.name}-' -- name "
                            "artifacts <study>-<what> (all studies share one namespace)",
                        )
                    )


def unused_figure_findings(figures: list[Path], root: Path) -> list[Finding]:
    """I5: generated figures no checked document includes, one line per generator.

    Not a warning: a completed experiment publishes its diagnostics again on every rerun
    (so deleting them would only show up in the regeneration check), and a withdrawn,
    stopped or replaced experiment's figures may stay for the record.
    """
    groups: dict[tuple[str, str, str], list[str]] = {}
    indexes: dict[str, dict[str, tuple[str, str, str]]] = {}
    for figure in sorted(set(figures)):
        sidecar = read_sidecar(figure) or {}
        study = project_parts(figure, root)[0]
        experiment = sidecar.get("experiment")
        if experiment:
            if study not in indexes:
                indexes[study] = read_experiment_index(root / "projects" / study)
            match = re.fullmatch(r"(\d{3})_(\S+)", str(experiment))
            row = indexes[study].get(match.group(1)) if match else None
            if row is None or match is None or row[0] != match.group(2):
                origin, word = f"experiment {experiment} (no row in its index)", None
            else:
                origin, word = f"experiment {experiment} (状態 {row[1]})", status_word(row[1])
            if word in BLOCKED_STATUSES:
                advice = (
                    "nothing regenerates them; they may stay for the record, or go with their "
                    ".provenance.json (git rm) once no text needs them"
                )
            else:
                advice = (
                    "no action needed if they are diagnostics (its run.py publishes them again "
                    "on every rerun); \\includegraphics one if the text needs it"
                )
        else:
            origin = str(sidecar.get("script") or "an unknown script")
            advice = "\\includegraphics one if the text needs it, or stop writing it"
        groups.setdefault((rel(figure.parent), origin, advice), []).append(figure.name)
    return [
        Finding(
            "info",
            "I5",
            location,
            f"{len(names)} generated figure(s) that no checked document includes, from "
            f"{origin}: {', '.join(names)} -- {advice}",
        )
        for (location, origin, advice), names in sorted(groups.items())
    ]


def journal_readable(data: object) -> bool:
    """Whether the harness can roll back a publication journal holding ``data``.

    The rule of ``_recover_locked`` in projects/<study>/src/utils/experiment.py: a JSON
    object whose ``entries`` are {target, backup} objects and whose ``processed`` is null
    or a {target, backup, source} object; targets and sources are paths, a backup a path
    or null. Anything else makes the next full run stop instead of rolling it back.
    """

    def paths(item: object, keys: tuple[str, ...]) -> bool:
        return (
            isinstance(item, dict)
            and all(key in item for key in keys)
            and all(
                isinstance(item[key], str) or (key == "backup" and item[key] is None)
                for key in keys
            )
        )

    if not isinstance(data, dict) or "processed" not in data:
        return False
    entries, processed = data.get("entries"), data["processed"]
    return (
        isinstance(entries, list)
        and all(paths(entry, ("target", "backup")) for entry in entries)
        and (processed is None or paths(processed, ("target", "backup", "source")))
    )


def check_publications(root: Path, findings: list[Finding], *, submission: bool) -> None:
    """E12 a run's publication killed midway, W18 temporaries such a kill left behind.

    The harness (projects/<study>/src/utils/experiment.py) publishes through a journal,
    result/.publication.json, and .<name>.<pid>.part / .previous files beside each
    destination; the next full run in the study rolls back or clears what a kill left.
    Until then a journal means result/ and data/processed/ may mix old and new artifacts.
    """
    projects = root / "projects"
    if not projects.is_dir():
        return
    for study_dir in sorted(projects.iterdir()):
        if not study_dir.is_dir() or study_dir.name.startswith("."):
            continue
        study = study_dir.name
        result = study_dir / "result"
        leftovers: list[Path] = []
        for directory in (
            result,
            result / "figures",
            result / "tables",
            study_dir / "data" / "processed",
        ):
            try:
                entries = sorted(directory.iterdir())
            except OSError:
                continue
            for path in entries:
                match = RE_PUBLICATION_TEMP.match(path.name)
                if match and (directory != result or match["name"] == PUBLICATION_JOURNAL[1:]):
                    leftovers.append(path)
        journal = result / PUBLICATION_JOURNAL
        if journal.exists() or journal.is_symlink():
            try:
                data = json.loads(journal.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            experiment = data.get("experiment") if isinstance(data, dict) else None
            if isinstance(experiment, str) and re.fullmatch(r"\d{3}_[a-z0-9_]+", experiment):
                who = f"experiment {experiment}"
                script = f"projects/{study}/experiments/{experiment}/run.py"
                example = f" (for example `{GENERATOR_COMMAND} {rerun_hint(script)}`)"
            else:
                who, example = "an experiment", ""
            if journal_readable(data):
                repair = (
                    f"before building, start any full run of an experiment in {study}{example}: "
                    "it rolls the publication back first"
                )
            else:
                repair = (
                    "the journal is unreadable, so a full run will not roll it back: restore "
                    f"projects/{study}/result/ from git (git status shows what changed), rename "
                    "a data/processed/.<NNN_slug>.<pid>.previous directory back if there is "
                    "one, then delete the journal and the .part/.previous temporaries"
                )
            findings.append(
                Finding(
                    "error",
                    "E12",
                    rel(journal),
                    f"a publication of {who} in {study} was killed midway, so "
                    f"projects/{study}/result/ and data/processed/ may mix its new artifacts "
                    f"with older ones ({len(leftovers)} temporary file(s) beside them) -- "
                    f"{repair}",
                )
            )
        elif leftovers:
            names = [rel(path) for path in leftovers]
            shown = ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
            findings.append(
                Finding(
                    "error" if submission else "warning",
                    "W18",
                    f"projects/{study}",
                    f"{len(names)} temporary file(s) of a killed publication left: {shown} -- "
                    "result/ is consistent (the kill came before or after the swap); the next "
                    f"full run of an experiment in {study} deletes them, or delete them by hand "
                    "while no run is publishing",
                )
            )


# --- Front matter (submission) -------------------------------------------------------------------


def _skip_group(text: str, start: int, opening: str, closing: str) -> int:
    """Index just past the balanced group that opens at ``text[start]``."""
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def remove_command(text: str, name: str) -> str:
    """Remove every ``\\name`` (and ``\\name*``) with its [..] and {..} arguments."""
    pattern = re.compile(rf"\\{name}(?![A-Za-z@])\*?")
    while True:
        match = pattern.search(text)
        if not match:
            return text
        end = match.end()
        while True:
            probe = end
            while probe < len(text) and text[probe] in " \t\n":
                probe += 1
            if probe < len(text) and text[probe] in "[{":
                closing = "]" if text[probe] == "[" else "}"
                end = _skip_group(text, probe, text[probe], closing)
            else:
                break
        text = text[: match.start()] + " " + text[end:]


def has_body_text(path: Path) -> bool:
    lines = [strip_comments(raw) for raw in read_lines(path)]
    text = "\n".join(line for line in lines if "\\ThesisKeywords" not in line)
    for name in ("chapter", "section", "addcontentsline", "todo", "vspace", "hspace"):
        text = remove_command(text, name)
    text = re.sub(r"\\[A-Za-z@]+\*?", " ", text)  # remaining control words
    return re.search(r"\w", text) is not None


def include_flags(graph: Graph) -> dict[str, bool]:
    """``\\ThesisInclude<flag>true|false`` settings in reading order (the last one wins)."""
    flags: dict[str, bool] = {}
    for path in graph.files:
        for raw in read_lines(path):
            for match in RE_INCLUDE_FLAG.finditer(strip_comments(raw)):
                flags[match.group(1)] = match.group(2) == "true"
    return flags


def check_front_matter(graph: Graph, draft_dir: Path, findings: list[Finding]) -> None:
    included = set(graph.files)
    for name in FRONT_MATTER_BODIES:
        path = (draft_dir / name).resolve()
        if path in included and not has_body_text(path):
            findings.append(
                Finding(
                    "error",
                    "E9",
                    rel(path),
                    "has no body text yet (only headings, \\todo notes or comments) -- write it "
                    "before submission",
                )
            )
    # An optional page is in the include graph whether or not it is printed: only a page
    # that thesis-config.tex switches on must have its template text replaced.
    flags = include_flags(graph)
    for name, flag in OPTIONAL_FRONT_MATTER.items():
        path = (draft_dir / name).resolve()
        if path not in included or not flags.get(flag):
            continue
        marked = [
            lineno
            for lineno, raw in enumerate(read_lines(path), 1)
            if RE_PLACEHOLDER_MARK.fullmatch(raw[len(strip_comments(raw)) :])
        ]
        if marked:
            findings.append(
                Finding(
                    "error",
                    "E9",
                    f"{rel(path)}:{marked[0]}",
                    f"is printed (\\ThesisInclude{flag}true in thesis-config.tex) but still has "
                    "the template text marked `% thesis:placeholder` -- replace that text and "
                    f"delete the marker, or set \\ThesisInclude{flag}false",
                )
            )


# --- Build log -----------------------------------------------------------------------------------


def check_log(log_path: Path, findings: list[Finding], *, draft_dir: Path | None = None) -> None:
    job = log_path.stem
    if not log_path.exists():
        command = LOG_COMMANDS.get(job, f"bash draft/compile.sh {job}")
        findings.append(
            Finding(
                "info",
                "I2",
                "",
                f"{rel(log_path)} not found -- run `{command}` first for log checks",
            )
        )
        return
    base = draft_dir if draft_dir is not None else log_path.parent
    overfull = 0
    for raw in read_lines(log_path):
        if RE_LOG_OVERFULL.match(raw):
            overfull += 1
            continue
        error_match = RE_LOG_ERROR.match(raw)
        if error_match:
            location = rel(log_path)
            if error_match.group(1):
                source = (base / error_match.group(1)).resolve()
                location = f"{rel(source)}:{error_match.group(2)}"
            findings.append(
                Finding("error", "I2", location, f"LaTeX error: {error_match.group(3)}")
            )
            continue
        duplicate_anchor = RE_LOG_DUPLICATE_ANCHOR.search(raw)
        if duplicate_anchor:
            findings.append(
                Finding(
                    "warning",
                    "W9",
                    rel(log_path),
                    f"duplicate PDF destination '{duplicate_anchor.group(1)}'",
                )
            )
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
            Finding("warning", "W10", rel(log_path), f"{overfull} overfull box(es) in last build")
        )


# --- Driver --------------------------------------------------------------------------------------


@dataclass
class Analysis:
    findings: list[Finding]
    used_stems: set[str]
    cited: set[str]
    artifacts: list[Artifact]
    # Generated figures this document does not include (I5 once all documents are known).
    unused_generated: list[Path] = field(default_factory=list)


def analyse(
    draft_dir: Path,
    *,
    main_name: str = "main.tex",
    with_log: bool = True,
    submission: bool = False,
) -> Analysis:
    draft_dir = Path(draft_dir).resolve()
    root = draft_dir.parent
    findings: list[Finding] = []
    graph = resolve_include_graph(draft_dir / main_name, findings)
    index = scan_tex(graph)

    bib_paths = [
        draft_dir / (name if name.endswith(".bib") else f"{name}.bib")
        for name in index.bib_names
        if name
    ]
    entries = parse_bib(bib_paths, findings)
    bib_keys = {entry.key: (entry.path, entry.lineno) for entry in entries}

    check_references(index, findings)
    check_metadata(graph.files, findings, submission=submission)
    check_citations(index, bib_keys, findings)
    check_bib_fields(entries, findings, submission=submission)
    figures, used_stems, unused_generated = check_figures(
        index, draft_dir, graphicspath_dirs(index, draft_dir), findings, root
    )
    check_locations(graph, figures, index, draft_dir, root, findings)
    check_values(index, graph, findings, submission=submission)
    artifacts = collect_artifacts(graph, figures, root)
    check_provenance(artifacts, root, findings, submission=submission)
    check_figure_ledger(draft_dir / "figures", figures, findings)
    check_result_names(root, findings)
    check_publications(root, findings, submission=submission)
    if submission:
        check_front_matter(graph, draft_dir, findings)
    for text, path, lineno in index.todos:
        if submission:
            findings.append(Finding("error", "E7", f"{rel(path)}:{lineno}", f"TODO: {text}"))
        else:
            findings.append(Finding("info", "I1", f"{rel(path)}:{lineno}", f"TODO: {text}"))
    if with_log:
        job = Path(main_name).stem
        check_log(draft_dir / "build" / job / f"{job}.log", findings, draft_dir=draft_dir)
    return Analysis(findings, used_stems, set(index.cites), artifacts, unused_generated)


def run_checks(
    draft_dir: Path,
    *,
    main_name: str = "main.tex",
    with_log: bool = True,
    submission: bool = False,
) -> list[Finding]:
    analysis = analyse(draft_dir, main_name=main_name, with_log=with_log, submission=submission)
    root = Path(draft_dir).resolve().parent
    return analysis.findings + unused_figure_findings(analysis.unused_generated, root)


def run_all(
    draft_dir: Path,
    *,
    main_names: tuple[str, ...] = ALL_MAINS,
    with_log: bool = True,
    submission: bool = False,
) -> list[Finding]:
    """Check several documents and merge: a figure or bib entry used by any is used."""
    analyses = [
        analyse(draft_dir, main_name=name, with_log=with_log, submission=submission)
        for name in main_names
    ]
    used_stems = set().union(*(a.used_stems for a in analyses))
    cited = set().union(*(a.cited for a in analyses))
    merged: list[Finding] = []
    seen: set[tuple[str, str, str, str]] = set()
    for analysis in analyses:
        for finding in analysis.findings:
            if finding.code == "W3" and finding.subject in used_stems:
                continue
            if finding.code == "W2" and finding.subject in cited:
                continue
            key = (finding.severity, finding.code, finding.location, finding.message)
            if key not in seen:
                seen.add(key)
                merged.append(finding)
    unused = [
        figure
        for analysis in analyses
        for figure in analysis.unused_generated
        if figure.stem not in used_stems and figure.name not in used_stems
    ]
    return merged + unused_figure_findings(unused, Path(draft_dir).resolve().parent)


def generator_command(script: str) -> str:
    """The command that regenerates what ``script`` wrote (an experiment needs --overwrite)."""
    command = f"{GENERATOR_COMMAND} {shlex.quote(script)}"
    return f"{command} --overwrite" if RE_EXPERIMENT_SCRIPT.fullmatch(script) else command


def upstream_first(before: dict[str, set[str]], notes: set[str]) -> list[str]:
    """``before`` (script -> scripts that must run first) in topological order.

    Ties are alphabetical. Scripts that read each other's outputs (a loop) are emitted
    together, alphabetically, once everything they read from outside the loop is done,
    with a note.
    """
    order: list[str] = []
    done: set[str] = set()
    while len(done) < len(before):
        remaining = sorted(script for script in before if script not in done)
        ready = [script for script in remaining if before[script] <= done]
        if ready:
            order.append(ready[0])
            done.add(ready[0])
            continue
        # Every remaining script waits for another: emit the first loop that waits for
        # nothing outside itself.
        reach: dict[str, set[str]] = {}
        for script in remaining:
            found: set[str] = set()
            pending = [script]
            while pending:
                for upstream in before[pending.pop()] - done:
                    if upstream not in found:
                        found.add(upstream)
                        pending.append(upstream)
            reach[script] = found
        for script in remaining:
            loop = {script} | {other for other in reach[script] if script in reach[other]}
            if all(before[member] - done <= loop for member in loop):
                break
        members = sorted(loop)
        notes.add(f"# generators read each other's outputs: {', '.join(members)}")
        order.extend(members)
        done.update(members)
    return order


def list_generators(draft_dir: Path, main_names: tuple[str, ...] = ALL_MAINS) -> list[str]:
    """Commands that regenerate every included artifact, upstream first, then notes.

    A script's command comes after the commands of the generators of every file it read
    (the ``sources`` its sidecars record, followed through upstream sidecars: a
    result/tables/*.csv an experiment promoted, a file under data/processed/NNN_<slug>/ or
    experiments/NNN_<slug>/ maps to that experiment's run.py); otherwise alphabetical. An
    experiment's run.py gets --overwrite (the harness refuses to replace a completed run).
    """
    draft_dir = Path(draft_dir).resolve()
    root = draft_dir.parent
    notes: set[str] = set()
    before: dict[str, set[str]] = {}  # script -> generators of the files it read
    seen: set[Path] = set()

    def usable(script, label: str) -> bool:
        if not isinstance(script, str) or not script.endswith(".py") or Path(script).is_absolute():
            notes.add(f"# {label}: generated by {script!r}, not a script in this repository")
            return False
        if not (root / script).is_file():
            notes.add(f"# {label}: generator {script} no longer exists")
            return False
        return True

    def add_reader(script: str, sidecar: dict) -> None:
        before.setdefault(script, set())
        pending = [(script, sidecar)]
        followed: set[tuple[str, str]] = set()
        while pending:
            consumer, consumed = pending.pop()
            for path, upstream, match in follow_sources(consumed, root):
                if match is not None:
                    study, experiment = match.groups()
                    generator = f"projects/{study}/experiments/{experiment}/run.py"
                else:
                    generator = upstream.get("script")
                if generator == consumer or not usable(generator, path):
                    continue
                before[consumer].add(generator)
                before.setdefault(generator, set())
                # The upstream generator read files of its own: order those too.
                if upstream is not None and (generator, path) not in followed:
                    followed.add((generator, path))
                    pending.append((generator, upstream))

    for name in main_names:
        if not (draft_dir / name).is_file():
            continue
        for artifact in analyse(draft_dir, main_name=name, with_log=False).artifacts:
            if artifact.path in seen:
                continue
            seen.add(artifact.path)
            label = rel(artifact.path)
            if artifact.sidecar is None:
                notes.add(f"# {label}: no provenance sidecar, generator unknown")
                continue
            script = artifact.sidecar.get("script")
            if usable(script, label):
                add_reader(script, artifact.sidecar)
    order = upstream_first(before, notes)
    return [generator_command(script) for script in order] + sorted(notes)


def _sort_key(finding: Finding) -> tuple:
    order = {"error": 0, "warning": 1, "info": 2}
    code = (finding.code[0], int(finding.code[1:]) if finding.code[1:].isdigit() else 0)
    path, _, line = finding.location.partition(",")[0].rpartition(":")
    place = (path, int(line)) if path and line.isdigit() else (finding.location, 0)
    return (order[finding.severity], code, place, finding.message)


def print_report(findings: list[Finding]) -> tuple[int, int]:
    findings = sorted(findings, key=_sort_key)
    counts = {"error": 0, "warning": 0, "info": 0}
    current = None
    for finding in findings:
        counts[finding.severity] += 1
        if finding.severity != current:
            current = finding.severity
            print(f"\n== {current.upper()}S ==")
        location = f"{finding.location}: " if finding.location else ""
        print(f"{location}[{finding.code}] {finding.message}")
    todos = sum(1 for f in findings if f.code in {"I1", "E7"})
    r3 = sum(1 for f in findings if f.code == "I3")
    print(
        f"\nSummary: {counts['error']} error(s), {counts['warning']} warning(s), "
        f"{todos} TODO(s), {r3} R3 artifact(s)"
    )
    return counts["error"], counts["warning"]


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--draft-dir", default="draft", help="manuscript directory (default: draft)"
    )
    which = parser.add_mutually_exclusive_group()
    which.add_argument(
        "--main",
        action="append",
        default=None,
        metavar="FILE",
        help="root TeX file (default: main.tex); give it more than once to check several "
        "documents as one, like --all (make check-final: submission.tex and supplementary.tex)",
    )
    which.add_argument(
        "--all",
        action="store_true",
        help="check main.tex, review.tex and supplementary.tex (each with its build log)",
    )
    parser.add_argument("--strict", action="store_true", help="warnings also fail the check")
    parser.add_argument(
        "--submission",
        action="store_true",
        help="final checks: placeholders, TODOs, empty front matter, W14/W15/W17/W18/I4 are errors",
    )
    parser.add_argument("--no-log", action="store_true", help="skip the build log")
    parser.add_argument(
        "--list-generators",
        action="store_true",
        help="print the command that regenerates each included figure, table and values file",
    )
    args = parser.parse_args(argv)

    draft_dir = Path(args.draft_dir)
    if not draft_dir.is_absolute():
        draft_dir = root / draft_dir
    if args.main:
        main_names: tuple[str, ...] = tuple(dict.fromkeys(args.main))
    elif args.all or args.list_generators:
        main_names = ALL_MAINS
    else:
        main_names = ("main.tex",)
    missing = [name for name in main_names if not (draft_dir / name).is_file()]
    if missing:
        for name in missing:
            print(f"error: {rel(draft_dir / name)} not found", file=sys.stderr)
        return 2

    if args.list_generators:
        for line in list_generators(draft_dir, main_names):
            print(line)
        return 0

    if len(main_names) > 1:
        print("Checked: " + ", ".join(rel(draft_dir / name) for name in main_names))
    findings = run_all(
        draft_dir, main_names=main_names, with_log=not args.no_log, submission=args.submission
    )
    errors, warnings = print_report(findings)
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
