"""Write tables and in-text values for the thesis into the study's TABLE_DIR.

``write_latex_table`` writes a DataFrame as a booktabs table (``<name>.tex``)
plus its numbers as ``<name>.csv``; ``write_latex_values`` writes named
numbers for the text as ``\\defvalue`` lines (``<name>.tex``) plus
``<name>.csv``. Both write a ``<name>.provenance.json`` sidecar (script,
experiment, time, git commit, sha256 of each written file, optional keys such
as ``reproducibility`` and ``sources``) that ``tools/thesis_check.py`` reads.
A script that builds a table from files another run wrote
(``result/tables/*.csv``, ``data/processed/NNN_<slug>/``) names them with
``sources=[...]`` so the checker can follow them back to that experiment.

Inside ``experiment.start()`` the files go to the run's ``out/staged/`` and
reach ``result/`` when a full run completes (see experiment.py); outside a run
(a ``scripts/`` promotion script) they are written to ``result/`` at once.
Inside a run the sidecar also records the run (start time, seed, parameter
hash), names must start with ``<study>-``, and each name is written once.

The ``.tex`` and ``.csv`` files carry no time and no commit, so regenerating
from the same code gives the same bytes; only the sidecar changes. The commit
a file is credited to is the one the run started from (the run record inside
an experiment; outside a run, the git state when this module is imported, so
import it at the top of the script). If the code changes during the run (a
commit, or an uncommitted edit), the sidecar records the start commit as
uncommitted code and a warning says so. Only code counts (this study's
``src/``, ``scripts/``, ``config.py`` and ``experiments/**/*.py``, and the
repository's ``config.py``, ``pyproject.toml`` and ``uv.lock``); prose and
every study's ``result/`` never do.

The table emitter is hand-rolled rather than ``DataFrame.to_latex`` so the
output stays stable across pandas versions and fully under our control.
Tables are ready for ``\\input`` from ``draft/`` chapters::

    \\input{../projects/<study>/result/tables/<name>.tex}

Values files are registered once in ``draft/values.tex``
(``\\ThesisValues{../projects/<study>/result/tables/<name>}``) so every value
is defined before the abstracts, and are used in the text as
``\\val{<name>-<key>}``.

This module loads only ``experiment.py`` beside it, by file path, so tests can
still load it by path.
"""

import csv
import hashlib
import importlib.util
import json
import math
import numbers
import os
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

_LATEX_SPECIALS = {
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

CORE_KEYS = (
    "artifact",
    "kind",
    "study",
    "script",
    "experiment",
    "created",
    "git_commit",
    "git_dirty",
    "run",
    "files",
)
REPRODUCIBILITY_LEVELS = ("R1", "R2", "R3")

# Value keys become part of a TeX control-sequence name and of \val{...}.
VALUE_KEY_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Study names may contain "_" (tools/new_study.py), so values-file names may too.
VALUES_NAME_RE = re.compile(r"^[a-z0-9_]+(?:-[a-z0-9_]+)*$")
# What siunitx \num parses reliably; "12,345" or "12.3%" would not typeset as intended.
NUMBER_RE = re.compile(r"^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def escape_latex(value) -> str:
    """Escape LaTeX special characters in ``value`` (converted to str)."""
    return "".join(_LATEX_SPECIALS.get(ch, ch) for ch in str(value))


def _load_experiment_module():
    """This study's experiment.py, loaded by file path: one module per file per process.

    run.py imports it as src.utils.experiment and tests load modules by path under
    unique names; both end up with the module registered under experiment.UTILS_KEY.
    """
    path = Path(__file__).resolve().with_name("experiment.py")
    key = f"_thesis_utils:{path}"
    module = sys.modules.get(key)
    if module is None:
        spec = importlib.util.spec_from_file_location(key, path)
        assert spec is not None and spec.loader is not None, f"Cannot load {path}"
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[key]
            raise
    return module


_experiment = _load_experiment_module()
# The commit and code state when the helpers were imported (None outside git).
GIT_AT_START = _experiment.GIT_AT_START


def _git_state(cfg) -> dict:
    """``git_commit`` / ``git_dirty`` for a sidecar (experiment.artifact_git_state)."""
    return _experiment.artifact_git_state(cfg)


def _running_script(cfg) -> tuple[str, str | None]:
    """``(script, experiment)`` for a sidecar (experiment.running_script).

    Inside a run both come from the run record; outside a run ``script`` is the
    running script (repo-relative in the repository) and ``experiment`` is None,
    and a ``run.py`` under ``experiments/<name>/`` that writes outside
    ``experiment.start()`` is refused.
    """
    return _experiment.running_script(cfg)


def _run_key(cfg) -> dict:
    """``{"run": {started, seed, params_sha256}}`` inside a run, else nothing."""
    run = _experiment.run_identity(cfg)
    return {} if run is None else {"run": run}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path, repo_root: Path) -> str:
    """Repo-relative POSIX path when ``path`` lies in the repo, else the absolute path."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _check_name(name: str) -> None:
    assert isinstance(name, str) and name, f"name must be a non-empty string, got: {name!r}"
    assert "/" not in name and "\\" not in name, (
        f"name must be a bare file stem without directories, got: {name!r}"
    )
    assert "." not in name, f"name must not contain an extension, got: {name!r}"


def _check_extra(extra) -> dict:
    """Validate the optional provenance mapping before anything is written."""
    if extra is None:
        return {}
    assert isinstance(extra, Mapping), f"provenance must be a mapping, got: {type(extra)!r}"
    extra = dict(extra)
    clashes = sorted(set(extra) & set(CORE_KEYS))
    assert not clashes, f"provenance keys {clashes} are set by the helper itself; rename them"
    if "reproducibility" in extra:
        assert extra["reproducibility"] in REPRODUCIBILITY_LEVELS, (
            f"provenance['reproducibility'] must be one of {REPRODUCIBILITY_LEVELS}, "
            f"got: {extra['reproducibility']!r}"
        )
    if "sources" in extra:
        sources = extra["sources"]
        assert isinstance(sources, list | tuple), "provenance['sources'] must be a list"
        for item in sources:
            assert isinstance(item, Mapping) and isinstance(item.get("path"), str), (
                "each source must be {'path': <repo-relative str>, 'sha256': <hex>}, "
                f"got: {item!r}"
            )
            assert isinstance(item.get("sha256"), str) and _SHA256_RE.match(item["sha256"]), (
                f"source {item['path']!r} needs a lowercase 64-hex 'sha256' "
                "(src.utils.provenance.source_entry computes both)"
            )
        extra["sources"] = [dict(item) for item in sources]
    try:
        json.dumps(extra)
    except TypeError as exc:
        raise AssertionError(
            f"provenance must be JSON-serialisable (use str paths): {exc}"
        ) from None
    return extra


def _source_entries(sources, cfg) -> list[dict]:
    """``sources=``: the files an artifact was made from, as ``{"path", "sha256"}`` entries.

    A path (``str`` or ``Path``) must name an existing file; it is recorded
    repo-relative when it lies in the repository, with its sha256. A mapping is
    an entry that is already complete (e.g. from
    ``src.utils.provenance.source_entry``, which can reuse a verified hash).
    """
    if sources is None:
        return []
    assert isinstance(sources, list | tuple), (
        f"sources must be a list of paths, got: {type(sources).__name__}"
    )
    entries = []
    for item in sources:
        if isinstance(item, str | os.PathLike):
            path = Path(item)
            assert path.is_file(), f"source file does not exist: {path}"
            entries.append(
                {"path": _display_path(path, Path(cfg.REPO_ROOT)), "sha256": _sha256(path)}
            )
        else:
            entries.append(item)
    return _check_extra({"sources": entries})["sources"]


def _with_sources(extra: dict, entries: list[dict]) -> dict:
    if entries:
        extra["sources"] = [*extra.get("sources", []), *entries]
    return extra


def _provenance(name: str, kind: str, cfg) -> dict:
    script, experiment = _running_script(cfg)
    return {
        "artifact": name,
        "kind": kind,
        "study": Path(cfg.STUDY_ROOT).name,
        "script": script,
        "experiment": experiment,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        **_git_state(cfg),
        **_run_key(cfg),
    }


def _header(core: dict) -> str:
    """First line of a generated ``.tex``: no time and no commit (those are in the sidecar)."""
    dirty = ", code-dirty" if core["git_dirty"] is True else ""
    return f"% Generated by {core['script']}{dirty} -- do not edit by hand."


def _write_sidecar(table_dir: Path, name: str, written: list[Path], core: dict, extra: dict):
    sidecar = {**core, "files": {path.name: _sha256(path) for path in written}, **extra}
    path = table_dir / f"{name}.provenance.json"
    path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_latex_table(
    df,
    name: str,
    cfg,
    *,
    caption: str | None = None,
    label: str | None = None,
    index: bool = False,
    float_format=r"{:.3g}".format,
    sources=None,
    provenance=None,
) -> Path:
    """Write ``df`` as ``TABLE_DIR/<name>.tex`` (booktabs) and return the path.

    ``name`` must be a bare stem (no directory, no extension). With a
    ``caption`` the tabular is wrapped in a ``table`` environment and ``label``
    defaults to ``tab:<name>``. ``caption`` is LaTeX source (math such as
    ``$n$`` works): write ``\\%``, ``\\&``, ``\\#`` yourself or pass
    ``escape_latex(text)``; an unescaped ``%``, ``&`` or ``#`` is refused.
    ``index=True`` includes the index as leading column(s). Floats go through
    ``float_format`` before LaTeX escaping. The unformatted numbers are also
    written to ``<name>.csv`` (the machine-readable source a reviewer checks
    the table against), with a ``<name>.provenance.json`` sidecar. ``sources``
    lists the files the table is built from (paths, hashed here), so
    ``make check`` can follow them to the experiment that made them;
    ``provenance`` adds optional keys. Inside a run the files are staged and
    the staged ``.tex`` path is returned.
    """
    _check_name(name)
    if caption is not None:
        assert isinstance(caption, str), f"caption must be a str, got: {caption!r}"
        bad = re.search(r"(?<!\\)[%&#]", caption)
        assert bad is None, (
            f"caption {caption!r} has an unescaped {bad.group()!r}; the caption is LaTeX: "
            f"write \\{bad.group()} or pass escape_latex(text)"
        )
    extra = _with_sources(_check_extra(provenance), _source_entries(sources, cfg))

    frame = df.reset_index() if index else df
    assert len(frame.columns) > 0, "DataFrame has no columns to write"

    def fmt_cell(value) -> str:
        if isinstance(value, float):
            return escape_latex(float_format(value))
        return escape_latex(value)

    alignment = "".join("r" if dtype.kind in "iuf" else "l" for dtype in frame.dtypes)
    header = " & ".join(escape_latex(col) for col in frame.columns)
    body = [
        " & ".join(fmt_cell(value) for value in row) + r" \\"
        for row in frame.itertuples(index=False)
    ]

    core = _provenance(name, "table", cfg)  # first: it refuses a run.py outside start()
    lines = [_header(core)]
    if caption is not None:
        label = label if label is not None else f"tab:{name}"
        lines += [
            r"\begin{table}[tbp]",
            r"\centering",
            rf"\caption{{{caption}}}",
            rf"\label{{{label}}}",
        ]
    lines += [rf"\begin{{tabular}}{{{alignment}}}", r"\toprule", header + r" \\", r"\midrule"]
    lines += body
    lines += [r"\bottomrule", r"\end{tabular}"]
    if caption is not None:
        lines += [r"\end{table}"]

    table_dir = _experiment.artifact_dir(cfg, "tables", name, "table")
    table_dir.mkdir(parents=True, exist_ok=True)
    out = table_dir / f"{name}.tex"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    csv_path = table_dir / f"{name}.csv"
    frame.to_csv(csv_path, index=False)
    _write_sidecar(table_dir, name, [out, csv_path], core, extra)
    return out


def _is_integral(value) -> bool:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _is_real(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _format_number(key: str, value, fmt) -> tuple[str, str]:
    """Return (TeX text, raw CSV text) for one number of ``key``."""
    if _is_integral(value):
        return str(int(value)), str(int(value))
    assert _is_real(value), (
        f"value {key!r} must be an int, float, str or (value, uncertainty) tuple, "
        f"got {type(value).__name__}: {value!r}"
    )
    number = float(value)
    assert math.isfinite(number), f"value {key!r} is not finite: {value!r}"
    assert fmt is not None, (
        f"value {key!r} is a float: say how to round it, e.g. formats={{{key!r}: '{{:.2f}}'}} "
        "or default_format='{:.3g}'"
    )
    try:
        text = fmt.format(number)
    except (ValueError, KeyError, IndexError) as exc:
        raise AssertionError(f"format {fmt!r} for value {key!r} is not usable: {exc}") from None
    assert NUMBER_RE.match(text), (
        f"format {fmt!r} turned value {key!r} into {text!r}, which \\num cannot typeset; "
        "use a plain spec such as '{:.2f}' or '{:.3g}' (no thousands separators or %)"
    )
    return text, repr(number)


def write_latex_values(
    values, name: str, cfg, *, formats=None, default_format=None, sources=None, provenance=None
) -> Path:
    """Write named numbers for the text as ``TABLE_DIR/<name>.tex`` and return the path.

    Each key becomes ``\\val{<name>-<key>}`` in the thesis (register the file in
    ``draft/values.tex``), so no result is typed by hand. Values are ints
    (written as is), floats (rounded with ``formats[key]`` or
    ``default_format``, ``str.format`` specs like ``"{:.2f}"``; one of them is
    required), ``(value, uncertainty)`` tuples (written as ``v +- u``) or
    strings (``\\deftextvalue``, LaTeX-escaped). The raw values go to
    ``<name>.csv`` and a ``<name>.provenance.json`` sidecar records the source;
    ``sources`` lists the files the values are computed from (paths, hashed
    here), as in ``write_latex_table``. Inside a run the files are staged and
    the staged ``.tex`` path is returned.
    """
    _check_name(name)
    assert VALUES_NAME_RE.match(name), (
        f"values name must be lowercase letters, digits, '_' and '-' (e.g. 'study1-main'), "
        f"got: {name!r}"
    )
    assert isinstance(values, Mapping) and values, "values must be a non-empty mapping"
    formats = dict(formats or {})
    unknown = sorted(set(formats) - set(values))
    assert not unknown, f"formats names keys that are not in values: {unknown}"
    for spec in [*formats.values(), default_format]:
        assert spec is None or isinstance(spec, str), (
            f"formats are str.format specs such as '{{:.2f}}', got: {spec!r}"
        )
    extra = _with_sources(_check_extra(provenance), _source_entries(sources, cfg))

    bad_keys = [key for key in values if not (isinstance(key, str) and VALUE_KEY_RE.match(key))]
    assert not bad_keys, (
        f"value keys must be lowercase letters and digits joined by '-', got: {bad_keys}"
    )

    tex_lines: list[str] = []
    csv_rows: list[tuple[str, str, str]] = []
    for key in sorted(values):
        full = f"{name}-{key}"
        value = values[key]
        fmt = formats.get(key, default_format)
        if isinstance(value, str):
            assert value.strip(), f"text value {key!r} is empty"
            assert "\n" not in value and "\r" not in value, (
                f"text value {key!r} must be a single line"
            )
            tex_lines.append(rf"\deftextvalue{{{full}}}{{{escape_latex(value)}}}")
            csv_rows.append((full, value, ""))
        elif isinstance(value, tuple):
            assert len(value) == 2, (
                f"value {key!r}: a tuple must be (value, uncertainty), got {len(value)} items"
            )
            (center_tex, center_raw), (spread_tex, spread_raw) = (
                _format_number(key, item, fmt) for item in value
            )
            assert float(value[1]) >= 0, f"value {key!r}: the uncertainty must not be negative"
            tex_lines.append(rf"\defvalue{{{full}}}{{{center_tex} +- {spread_tex}}}")
            csv_rows.append((full, center_raw, spread_raw))
        else:
            text, raw = _format_number(key, value, fmt)
            tex_lines.append(rf"\defvalue{{{full}}}{{{text}}}")
            csv_rows.append((full, raw, ""))

    core = _provenance(name, "values", cfg)  # first: it refuses a run.py outside start()
    table_dir = _experiment.artifact_dir(cfg, "tables", name, "values")
    table_dir.mkdir(parents=True, exist_ok=True)
    out = table_dir / f"{name}.tex"
    out.write_text("\n".join([_header(core), *tex_lines]) + "\n", encoding="utf-8")
    csv_path = table_dir / f"{name}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["key", "value", "uncertainty"])
        writer.writerows(csv_rows)
    _write_sidecar(table_dir, name, [out, csv_path], core, extra)
    return out
