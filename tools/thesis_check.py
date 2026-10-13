#!/usr/bin/env python3
"""Static consistency checks for the dissertation manuscript and research.json.

Stdlib only, so it runs on the host (``python3`` 3.10 or newer); ``make check`` runs
``python3 tools/thesis_check.py --all``.

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

Several documents (--all, or --main given more than once) are checked as one: a figure
or bib entry that any of them uses counts as used.

Severities:
  error   (exit 1)  broken cross-references, citations, figures, values or research.json
  warning (exit 1 with --strict) hygiene issues worth fixing before submission
  info    TODO inventory, compile-log findings, unverified bib entries

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
  E10 figure, \\input or \\ThesisValues target or \\graphicspath directory outside the
      repository or under external/ (copy the file into projects/<id>/)
  E11 value defined only after \\begin{document} (register its file in draft/values.tex)
  E12 research.json unreadable or of the wrong shape or fields, a bad or duplicate id, a
      missing projects/<id>/, or a chapter that does not exist or main.tex does not include
  W1 duplicate bibliography keys
  W2 bibliography entries never cited
  W3 file in draft/figures/ that no checked document includes
  W4 fig:/tab: labels never referenced
  W5 labels not following the prefix convention (ch:/sec:/subsec:/fig:/tab:/eq:/alg:/app:)
  W7 bare \\ref usage instead of \\cref
  W8 required thesis metadata still contains a template placeholder
  W9 duplicate PDF page anchors in the last build
  W10 overfull boxes in the last build
  W11 hand-made figure in draft/figures/ missing from draft/figures/README.md
  W12 the same value key defined more than once
  W13 two bibliography entries with the same DOI
  W17 values file registered with \\ThesisValues does not exist (error with --submission)
  I1 TODO/FIXME inventory (\\todo{...} and %-comments)
  I2 findings from draft/build/<job>/<job>.log (errors, undefined references/citations)
  I4 bibliography entries without a valid `verified` field (error with --submission)
  I6 \\includegraphics, \\label, \\ref, \\cite or \\val with a macro parameter (#1) in a
     macro the checker cannot expand (\\def, \\NewDocumentCommand, ...): what it places is
     not checked
"""

import argparse
import bisect
import json
import re
import sys
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
# research.json (AGENTS.md 研究を取り込む): one entry per research work, in chapter order.
RESEARCH_FIELDS = ("id", "title", "chapter", "source", "paper", "paper_status", "status")
RESEARCH_STATUSES = ("構想", "取り込み済み", "執筆中", "完成")
PAPER_STATUSES = ("", "出版済み", "採録", "投稿中", "準備中")
RE_RESEARCH_ID = re.compile(r"[a-z][a-z0-9_]*")
# <repo>@<sha>: the research repository's name (as in external/<repo>) and commit, never a path.
RE_SOURCE = re.compile(r"\w[\w.-]*@[0-9a-f]{7,64}")

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
# Value definitions and uses. Keys with `#` are the macro definitions themselves.
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

RE_BIB_ENTRY = re.compile(r"^\s*@(\w+)\s*\{\s*([^,\s{}]+)\s*,")
# doi:/isbn:/url: for published work; <repo>@<sha>:<path> for the author's own unpublished paper,
# checked against its manuscript in the research repository (AGENTS.md 文献).
RE_VERIFIED = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s*,\s*(?:(?:doi|isbn|url):\S+|[^\s@]+@[0-9a-f]{7,64}:\S+)$"
)
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
            # A registered values file that does not exist yet is W17, not E5.
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
        self.graphicspath_groups: list[tuple[str, Path, int]] = []  # (group, file, lineno)
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
                index.graphicspath_groups.append((match.group(1), path, lineno))
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
                "DOI, then add verified = {YYYY-MM-DD, doi:...} (or isbn:/url:, or "
                "<repo>@<sha>:<path> for your own unpublished paper)",
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
                "checked -- define it with \\newcommand, or write the command out in the text",
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


def graphicspath_dirs(index: TexIndex, draft_dir: Path) -> dict[Path, tuple[Path, int]]:
    """Each \\graphicspath directory (resolved, in order) and the file and line setting it."""
    dirs: dict[Path, tuple[Path, int]] = {}
    for group, path, lineno in index.graphicspath_groups:
        for match in re.finditer(r"\{([^{}]*)\}", group):
            entry = match.group(1).strip()
            if entry:
                dirs.setdefault((draft_dir / entry).resolve(), (path, lineno))
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


def check_figures(
    index: TexIndex, draft_dir: Path, dirs: list[Path], findings: list[Finding]
) -> list[UsedFigure]:
    """E4/W3. Returns the resolved figures.

    W3 is only for draft/figures/ (hand-made figures): the figures copied into
    projects/<id>/figures/ may wait there for the chapter that uses them.
    """
    search_dirs = [draft_dir, *(d for d in dirs if d != draft_dir)]
    used: list[UsedFigure] = []
    for target, path, lineno in index.graphics:
        resolved = resolve_graphic(target, search_dirs)
        if resolved is None:
            findings.append(
                Finding(
                    "error",
                    "E4",
                    f"{rel(path)}:{lineno}",
                    f"figure '{target}' not found in draft/ or any \\graphicspath directory "
                    "-- copy it into projects/<id>/figures/ (or draft/figures/) first",
                )
            )
            continue
        used.append(UsedFigure(target, resolved, path, lineno))

    used_paths = {figure.path for figure in used}
    hand_made = draft_dir / "figures"
    for figure in sorted(hand_made.iterdir()) if hand_made.is_dir() else []:
        if not figure.is_file() or figure.suffix.lower() not in GRAPHICS_EXTENSIONS:
            continue
        if figure.resolve() not in used_paths:
            findings.append(
                Finding(
                    "warning",
                    "W3",
                    rel(figure),
                    "figure file is never \\includegraphics'd -- include it, or delete it "
                    "(and its row in draft/figures/README.md) if nothing needs it",
                    subject=str(figure.resolve()),
                )
            )
    return used


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
        path
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


# --- Values --------------------------------------------------------------------------------------


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
                    f"value '{key}' is not defined -- add it to projects/<id>/values.tex "
                    "(registered in draft/values.tex with \\ThesisValues)",
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
                f"values file {rel(edge.target)} is registered but does not exist -- copy "
                "projects/_template/values.tex there, or remove the \\ThesisValues line",
            )
        )


def check_locations(
    graph: Graph,
    figures: list[UsedFigure],
    dirs: dict[Path, tuple[Path, int]],
    root: Path,
    findings: list[Finding],
) -> None:
    """E10: the thesis reads only files in this repository, never a research repository's."""
    uses = [(e.target, e.origin, e.lineno) for e in graph.edges]
    uses += [(f.path, f.origin, f.lineno) for f in figures]
    uses += [(directory, origin, lineno) for directory, (origin, lineno) in dirs.items()]
    for target, origin, lineno in uses:
        if target.is_relative_to(root) and not target.is_relative_to(root / "external"):
            continue
        findings.append(
            Finding(
                "error",
                "E10",
                f"{rel(origin)}:{lineno}",
                f"{rel(target)} is outside the repository or under external/ -- copy the "
                "file into projects/<id>/ and use it from there",
            )
        )


# --- research.json -------------------------------------------------------------------------------


def check_research(root: Path, draft_dir: Path, findings: list[Finding]) -> None:
    """E12: research.json lists each research once, with its projects/<id>/ and chapter."""
    path = root / "research.json"
    if not path.is_file():
        if draft_dir.name == "draft":
            findings.append(Finding("error", "E12", rel(path), "research.json is missing"))
        return

    def report(message: str) -> None:
        findings.append(Finding("error", "E12", rel(path), message))

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report(f"research.json is unreadable: {exc}")
        return
    entries = data.get("research") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        report('research.json must be {"research": [...]}, a list of entries')
        return
    included = set(resolve_include_graph(draft_dir / "main.tex", []).files)
    seen: set[str] = set()
    for number, entry in enumerate(entries, 1):
        given = entry.get("id") if isinstance(entry, dict) else None
        name = f"entry {number}" + (f" ({given!r})" if isinstance(given, str) else "")
        if (
            not isinstance(entry, dict)
            or set(entry) != set(RESEARCH_FIELDS)
            or not all(isinstance(value, str) for value in entry.values())
        ):
            report(f"{name}: needs exactly the string fields {', '.join(RESEARCH_FIELDS)}")
            continue
        rid, chapter = entry["id"], entry["chapter"]
        if not RE_RESEARCH_ID.fullmatch(rid):
            report(f"{name}: id must match [a-z][a-z0-9_]*")
        elif rid in seen:
            report(f"{name}: id {rid!r} is listed twice")
        elif not (root / "projects" / rid).is_dir():
            report(
                f"{name}: projects/{rid}/ does not exist -- cp -r projects/_template projects/{rid}"
            )
        seen.add(rid)
        if entry["status"] not in RESEARCH_STATUSES:
            report(f"{name}: status must be one of {' | '.join(RESEARCH_STATUSES)}")
        if entry["paper_status"] not in PAPER_STATUSES:
            report(f"{name}: paper_status must be one of {' | '.join(PAPER_STATUSES[1:])} or empty")
        if entry["source"] and not RE_SOURCE.fullmatch(entry["source"]):
            report(f"{name}: source must be <repo>@<sha> (or empty), never a host path")
        if not chapter:
            continue
        if not (root / chapter).is_file():
            report(f"{name}: chapter {chapter} does not exist")
        elif (root / chapter).resolve() not in included:
            report(f"{name}: draft/main.tex does not include {chapter}")


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
    used_paths: set[str]
    cited: set[str]


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
    dirs = graphicspath_dirs(index, draft_dir)
    figures = check_figures(index, draft_dir, list(dirs), findings)
    check_locations(graph, figures, dirs, root, findings)
    check_values(index, graph, findings, submission=submission)
    check_figure_ledger(draft_dir / "figures", figures, findings)
    check_research(root, draft_dir, findings)
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
    return Analysis(findings, {str(figure.path) for figure in figures}, set(index.cites))


def run_checks(
    draft_dir: Path,
    *,
    main_name: str = "main.tex",
    with_log: bool = True,
    submission: bool = False,
) -> list[Finding]:
    return analyse(
        draft_dir, main_name=main_name, with_log=with_log, submission=submission
    ).findings


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
    used_paths = set().union(*(a.used_paths for a in analyses))
    cited = set().union(*(a.cited for a in analyses))
    merged: list[Finding] = []
    seen: set[tuple[str, str, str, str]] = set()
    for analysis in analyses:
        for finding in analysis.findings:
            if finding.code == "W3" and finding.subject in used_paths:
                continue
            if finding.code == "W2" and finding.subject in cited:
                continue
            key = (finding.severity, finding.code, finding.location, finding.message)
            if key not in seen:
                seen.add(key)
                merged.append(finding)
    return merged


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
    print(f"\nSummary: {counts['error']} error(s), {counts['warning']} warning(s), {todos} TODO(s)")
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
        help="final checks: placeholders, TODOs, empty front matter; W17 and I4 are errors",
    )
    parser.add_argument("--no-log", action="store_true", help="skip the build log")
    args = parser.parse_args(argv)

    draft_dir = Path(args.draft_dir)
    if not draft_dir.is_absolute():
        draft_dir = root / draft_dir
    if args.main:
        main_names: tuple[str, ...] = tuple(dict.fromkeys(args.main))
    elif args.all:
        main_names = ALL_MAINS
    else:
        main_names = ("main.tex",)
    missing = [name for name in main_names if not (draft_dir / name).is_file()]
    if missing:
        for name in missing:
            print(f"error: {rel(draft_dir / name)} not found", file=sys.stderr)
        return 2

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
