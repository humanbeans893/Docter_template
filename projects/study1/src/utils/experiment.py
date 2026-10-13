"""Run harness and run identity for this study's experiments.

Every experiment's ``run.py`` wraps its body in::

    with experiment.start(__file__, params) as run:
        ...

research-template's call: ``start`` reads this study's ``config`` (the module
``run.py`` imported as ``config``; tests pass ``cfg=``). It parses ``--smoke`` /
``--overwrite`` (nothing else), holds a lock on the output directory (``out/``
or ``out/smoke/``), refuses to replace a completed run without ``--overwrite``,
checks ``params.py`` (``SEED``, ``PARAMS``, ``SMOKE``) before anything is
cleared, clears what an earlier run left there, and keeps
``out/params_used.json`` (the run record) up to date: at the start, at every
``run.stage()`` and at the end. SIGTERM, SIGHUP and Ctrl-C are recorded as a
failed run, except once publication starts swapping files into place: then the
signal waits until the run is recorded as completed, and acts after that.
``sys.exit(0)`` inside the body is recorded as failed (as in research-template).

While the run is active, ``THESIS_EXPERIMENT_RUN`` names its record. The
helpers in ``figures.py`` and ``tables.py`` then write into the run's
``out/staged/`` instead of ``result/``, and ``run.promote()`` names a
``run.out()`` file for ``result/tables/`` or ``data/processed/NNN_<slug>/`` (with
``sources=``, as for the helpers, when it was made from another run's files).
Names, kinds and destinations are checked at the call, also under ``--smoke``,
so a mistake surfaces in seconds. Only a full run whose body completes
publishes, all or none: under a per-study lock and through a journal
(``result/.publication.json``), so a publication killed midway is rolled back
by the next full run in the study. Publication replaces each artifact of the
same name as a whole (an old ``.pdf`` beside a new ``.png`` goes) and removes
what this experiment published before and no longer publishes. A failed,
interrupted or ``--smoke`` run never changes ``result/`` or ``data/processed/``.

This module is also the one place that says which code an artifact depends on
(``code_pathspec``: this study's ``src/``, ``scripts/``, ``config.py`` and
``experiments/**/*.py``, and the repository's ``config.py``, ``pyproject.toml``
and ``uv.lock``; never bytecode), which commit a run started from, and which run
is active (``active_run``). Code that is not committed when the run starts, or that
changes during it, never stops the run: what it writes is recorded with the
start commit and ``git_dirty: true``, with a warning (``make check`` W15).
``run.promote()`` files are checked when they are published, the helpers'
artifacts when they are written. The helpers load this file by file path
(``UTILS_KEY``), so the run record, every sidecar and ``make check`` agree.

Stdlib only, with no sibling imports, so tests can load it by file path.

Port of research-template's src/utils/experiment.py (e4d3960 .. b5327f2) to the
multi-study layout: paths are relative to the repository root, git runs there,
and the helpers stage what research-template's ``run.promote()`` copied.
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

RECORD = "params_used.json"
LOCK = ".lock"
SMOKE_DIR = "smoke"
STAGED = "staged"  # out[/smoke]/staged/{figures,tables,processed}/
JOURNAL = ".publication.json"  # STUDY_ROOT/result/<JOURNAL> while a publication is in flight
RUN_ENV = "THESIS_EXPERIMENT_RUN"  # path of the running record while a run is active
EXPERIMENTS = "experiments"
EXPERIMENT_NAME_RE = re.compile(r"^\d{3}_[a-z0-9]+(?:_[a-z0-9]+)*$")
AREAS = ("figures", "tables")
SIDECAR_SUFFIX = ".provenance.json"
# Extensions graphicx tries for an extension-less \includegraphics, in its order.
GRAPHICS_EXTENSIONS = (".pdf", ".png", ".jpg", ".mps", ".jpeg", ".jbig2", ".jb2", ".eps")
MAX_FILE_BYTES = 1_000_000  # tracked files over 1 MB are refused (tools/public_repo_check.py)

# Code whose uncommitted changes make an artifact unreproducible (research-template's
# CODE_PATHS): this study's code, its experiments' *.py and the shared environment.
# Prose (draft/, docs/, *.md, STATE.md) and every study's result/ never count.
STUDY_CODE_PATHS = ("src", "scripts", "config.py")
STUDY_CODE_GLOB = f"{EXPERIMENTS}/**/*.py"
REPO_CODE_PATHS = ("config.py", "pyproject.toml", "uv.lock")
# Bytecode is never code: Python writes it beside the sources wherever no .gitignore
# (or PYTHONPYCACHEPREFIX) keeps it out of git's sight.
NOT_CODE_GLOBS = ("**/__pycache__/**", "**/*.pyc")

# The key under which figures.py / tables.py load this file (their
# _load_experiment_module): one module per file per process.
UTILS_KEY = f"_thesis_utils:{Path(__file__).resolve()}"

_GLOB_SPECIALS_RE = re.compile(r"([*?\[\\])")
# Publication temporaries beside a destination: .<name>.<pid>.part / .<name>.<pid>.previous
_TEMP_RE = re.compile(r"^\.(?P<name>.+)\.(?P<pid>\d+)\.(?P<kind>part|previous)$")
_EXTENSION_RE = re.compile(r"[A-Za-z0-9]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Turned into a failed run, except from the swap until the run is recorded (Run._hold).
_STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


# --- Which code, which commit -------------------------------------------------


def code_pathspec(repo_root: Path, study_root: Path) -> list[str] | None:
    """Git pathspecs of the code an artifact depends on; None for a study outside the repo."""
    try:
        rel = Path(study_root).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return None
    prefix = "" if rel == "." else f"{rel}/"
    glob_prefix = _GLOB_SPECIALS_RE.sub(r"\\\1", prefix)
    return [
        *(f":(literal){prefix}{name}" for name in STUDY_CODE_PATHS),
        f":(glob){glob_prefix}{STUDY_CODE_GLOB}",
        *(f":(literal){name}" for name in REPO_CODE_PATHS),
        *(f":(exclude,glob){pattern}" for pattern in NOT_CODE_GLOBS),
    ]


_WARNED: set[str] = set()


def _warn_once(message: str) -> None:
    if message not in _WARNED:
        _WARNED.add(message)
        print(message, file=sys.stderr, flush=True)


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False
    )


def git_state(repo_root: Path, study_root: Path, *, quiet: bool = False) -> dict | None:
    """``{"commit", "short", "dirty"}`` (dirty: sorted porcelain lines of uncommitted code).

    None when git cannot tell (no work tree, no commit, no git).
    """
    pathspec = code_pathspec(repo_root, study_root)
    status_args = ["status", "--porcelain", "--untracked-files=all"]
    if pathspec is not None:
        status_args += ["--", *pathspec]
    elif not quiet:  # a study outside the repository: the whole tree counts
        _warn_once(f"warning: {study_root} is outside {repo_root}; every uncommitted file counts")
    try:
        head = _git(repo_root, "rev-parse", "HEAD")
        short = _git(repo_root, "rev-parse", "--short", "HEAD")
        status = _git(repo_root, *status_args)
    except OSError:
        return None
    if head.returncode or short.returncode or status.returncode:
        return None
    return {
        "commit": head.stdout.strip(),
        "short": short.stdout.strip(),
        "dirty": sorted(line for line in status.stdout.splitlines() if line.strip()),
    }


def same_code(repo_root: Path, study_root: Path, old: str, new: str) -> bool:
    """True when the code paths are identical in commits ``old`` and ``new``."""
    pathspec = code_pathspec(repo_root, study_root)
    try:
        diff = _git(repo_root, "diff", "--quiet", old, new, "--", *(pathspec or ["."]))
    except OSError:
        return False
    return diff.returncode == 0


def _start_snapshot() -> dict | None:
    """The git state when this module is imported, for the study this file belongs to."""
    try:
        study_root = Path(__file__).resolve().parents[2]  # <study>/src/utils/<this>.py
        repo_root = study_root.parents[1]  # projects/<study>/ -> repo root
    except IndexError:
        return None
    state = git_state(repo_root, study_root, quiet=True)
    return None if state is None else {**state, "roots": (repo_root, study_root)}


# Outside a run (a scripts/ promotion script), an artifact is credited to the commit at
# import, i.e. when the script started: import the helpers at the top of the script.
_START = _start_snapshot()
# The commit and code state when this module was imported (None outside git).
GIT_AT_START = (
    None if _START is None else {"git_commit": _START["short"], "git_dirty": bool(_START["dirty"])}
)


def _changed(repo_root: Path, study_root: Path, start: dict, now: dict) -> bool:
    """True when the code moved since ``start``: a commit that touches code, or other edits."""
    moved = now["commit"] != start["commit"] and not same_code(
        repo_root, study_root, start["commit"], now["commit"]
    )
    return moved or sorted(now["dirty"]) != sorted(start["dirty"])


def artifact_git_state(cfg) -> dict:
    """``git_commit`` / ``git_dirty`` for a sidecar: the code the run started from.

    The start is the active run's record or, outside a run, the state when this module
    was imported. If the code changed since then (a commit that touches code, or an
    uncommitted edit) or was already uncommitted then, the start commit is recorded
    with ``git_dirty: true`` and a warning says so (D4). Provenance is metadata, not
    data: without git it degrades to ``"unknown"`` with a warning instead of failing
    the write (``make check`` W15 flags it).
    """
    repo_root, study_root = Path(cfg.REPO_ROOT), Path(cfg.STUDY_ROOT)
    now = git_state(repo_root, study_root)
    if now is None:
        print(f"warning: could not read git state under {repo_root}", file=sys.stderr)
        return {"git_commit": "unknown", "git_dirty": "unknown"}
    run = active_run(cfg)
    if run is not None:
        start = run.get("git") or {}
        if start.get("commit") is None:
            return {"git_commit": "unknown", "git_dirty": "unknown"}
    elif _START is not None and _START["roots"] == (repo_root.resolve(), study_root.resolve()):
        start = _START
    else:
        return {"git_commit": now["short"], "git_dirty": bool(now["dirty"])}
    if _changed(repo_root, study_root, start, now):
        _warn_once(
            f"warning: the code changed during the run (it started at {start['short']}"
            f"{', uncommitted' if start['dirty'] else ''}; now {now['short']}"
            f"{', uncommitted' if now['dirty'] else ''}), so these results are recorded as "
            "uncommitted code: commit, then rerun from a clean tree"
        )
        return {"git_commit": start["short"], "git_dirty": True}
    if start["dirty"]:
        files = [line[3:] for line in start["dirty"]]
        shown = ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
        _warn_once(
            f"warning: this run started from uncommitted code ({shown}), so its results are "
            "recorded as uncommitted code: commit, then rerun"
        )
        return {"git_commit": start["short"], "git_dirty": True}
    return {"git_commit": start["short"], "git_dirty": False}


# --- Which run is active ------------------------------------------------------


def _display(path, repo_root) -> str:
    """Repo-relative POSIX path when ``path`` lies in the repo, else the absolute path."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(repo_root).resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _read_json(path: Path) -> dict | None:
    """A JSON object read from ``path``, or None when it is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def active_run(cfg) -> dict | None:
    """The record of the run active in this process (or a parent process), or None."""
    value = os.environ.get(RUN_ENV)
    if not value:
        return None
    path = Path(value)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        raise AssertionError(
            f"{RUN_ENV}={value} names no readable run record ({exc}): "
            "unset it unless an experiment is running"
        ) from None
    assert record.get("status") == "running", (
        f"{RUN_ENV}={value} names a run that is not running: unset it"
    )
    experiments = (Path(cfg.STUDY_ROOT) / EXPERIMENTS).resolve()
    assert path.resolve().is_relative_to(experiments), (
        f"the running experiment {record.get('script')} belongs to another study than "
        f"{Path(cfg.STUDY_ROOT).name}: a study never calls another study's helpers"
    )
    return record


def run_identity(cfg) -> dict | None:
    """``{"started", "seed", "params_sha256"}`` of the active run (a sidecar's ``run``)."""
    run = active_run(cfg)
    if run is None:
        return None
    return {"started": run["started"], "seed": run["seed"], "params_sha256": run["params_sha256"]}


def running_script(cfg) -> tuple[str, str | None]:
    """``(script, experiment)`` for a sidecar.

    Inside a run both come from the run record (``experiment`` is None for a template).
    Outside a run ``script`` is ``sys.argv[0]`` (repo-relative when it lies in the
    repository) and ``experiment`` is None; a script below ``experiments/<name>/`` must
    write through ``start()`` instead, and is refused.
    """
    run = active_run(cfg)
    if run is not None:
        name = run.get("experiment") or ""
        return run["script"], name if EXPERIMENT_NAME_RE.match(name) else None
    argv0 = sys.argv[0] if sys.argv and sys.argv[0] else ""
    if not argv0 or argv0 == "-c":
        return "unknown", None
    resolved = Path(argv0).resolve()
    try:
        script = resolved.relative_to(Path(cfg.REPO_ROOT).resolve()).as_posix()
    except ValueError:
        script = argv0
    try:
        parts = resolved.relative_to((Path(cfg.STUDY_ROOT) / EXPERIMENTS).resolve()).parts
    except ValueError:
        parts = ()
    assert len(parts) < 2, (
        f"{script} writes results outside experiment.start(): wrap its body in "
        "`with experiment.start(__file__, params) as run:`, so that a failed or --smoke run "
        "never changes result/ (experiments/README.md)"
    )
    return script, None


def _dirs(cfg) -> dict[str, Path]:
    """Where a study publishes (defaults for configs that name only some directories)."""
    study_root = Path(cfg.STUDY_ROOT)
    return {
        "figures": Path(getattr(cfg, "FIGURE_DIR", study_root / "result" / "figures")),
        "tables": Path(getattr(cfg, "TABLE_DIR", study_root / "result" / "tables")),
        "processed": Path(getattr(cfg, "PROCESSED_DATA_DIR", study_root / "data" / "processed")),
    }


def _check_kind(directory: Path, name: str, kind: str) -> None:
    """Refuse to replace an artifact of another kind (a table by values, ...)."""
    previous = (_read_json(Path(directory) / f"{name}{SIDECAR_SUFFIX}") or {}).get("kind")
    assert previous in (None, kind), (
        f"{name!r} in {directory} already holds a {previous}; choose another name for the "
        f"{kind} (or delete the old {name}.* files first)"
    )


def _check_prefix(name: str, study: str) -> None:
    assert name.startswith(f"{study}-"), (
        f"{name!r}: names in result/ start with '{study}-' (one namespace for the whole "
        "thesis; make check W16)"
    )


def _check_template(name: str, smoke: bool) -> None:
    assert smoke or EXPERIMENT_NAME_RE.match(name), (
        f"{name} is a template and publishes nothing: create an experiment with make experiment"
    )


def _twice(name: str) -> str:
    return f"{name} is written twice in this run: give each artifact its own name"


def artifact_dir(cfg, area: str, name: str, kind: str) -> Path:
    """The directory a helper writes ``name`` into, after the checks at the call.

    Outside a run: ``FIGURE_DIR`` / ``TABLE_DIR``. Inside a run (full or ``--smoke``):
    the run's ``out/staged/<area>/``, once the name starts with ``<study>-``, is not
    written twice in this run, has the kind ``result/`` holds under that name, and the
    run is not a template's full run.
    """
    assert area in AREAS, f"area must be one of {AREAS}, got {area!r}"
    final = _dirs(cfg)[area]
    record = active_run(cfg)
    if record is None:
        _check_kind(final, name, kind)
        return final
    _check_template(record.get("experiment") or "", bool(record.get("smoke")))
    _check_prefix(name, Path(cfg.STUDY_ROOT).name)
    record_path = os.environ[RUN_ENV]
    staged = Path(record_path).parent / STAGED / area
    live = _LIVE.get(record_path)
    assert not (staged / f"{name}{SIDECAR_SUFFIX}").exists(), _twice(name)
    assert not (area == "tables" and live is not None and name in live._tables), _twice(name)
    _check_kind(final, name, kind)
    staged.mkdir(parents=True, exist_ok=True)
    return staged


# --- The run ------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write(path: Path, record: dict) -> None:
    # Through a temporary file, so that a kill mid-write never leaves a truncated record.
    part = path.with_name(path.name + ".part")
    text = json.dumps(record, indent=2, ensure_ascii=False, default=str) + "\n"
    part.write_text(text, encoding="utf-8")
    os.replace(part, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_entries(sources, repo_root: Path) -> list[dict]:
    """``sources=``: the files an output was made from, as ``{"path", "sha256"}`` entries.

    The helpers' contract (figures/tables ``sources=``): a path (``str`` or ``Path``)
    names an existing file, recorded repo-relative when it lies in the repository, with
    its sha256 now; a mapping is a complete entry (``src.utils.provenance.source_entry``).
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
            entries.append({"path": _display(path, repo_root), "sha256": _sha256(path)})
            continue
        assert isinstance(item, Mapping) and isinstance(item.get("path"), str), (
            "each source must be {'path': <repo-relative str>, 'sha256': <hex>}, got: " + repr(item)
        )
        assert isinstance(item.get("sha256"), str) and _SHA256_RE.match(item["sha256"]), (
            f"source {item['path']!r} needs a lowercase 64-hex 'sha256' "
            "(src.utils.provenance.source_entry computes both)"
        )
        entries.append(dict(item))
    try:
        json.dumps(entries)
    except TypeError as exc:
        raise AssertionError(f"sources must be JSON-serialisable (use str paths): {exc}") from None
    return entries


def params_sha256(seed, values: dict) -> str:
    """Hash of the seed and the effective parameters (in the run record and every sidecar)."""
    text = json.dumps(
        {"seed": seed, "params": values},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_params(params: ModuleType, smoke: bool) -> tuple[int, dict]:
    seed = getattr(params, "SEED", None)
    assert isinstance(seed, int) and not isinstance(seed, bool), (
        f"params.py must pin SEED = <int> (e.g. SEED = 42), got {seed!r}"
    )
    assert isinstance(getattr(params, "PARAMS", None), dict), (
        "params.py must define PARAMS = {...}: every value that can change the result (may be {})"
    )
    values = dict(params.PARAMS)
    small: dict = {}
    if smoke:
        small = getattr(params, "SMOKE", None)
        assert isinstance(small, dict), (
            "--smoke needs params.SMOKE (the small values for a smoke run; {} keeps PARAMS)"
        )
        unknown = sorted((key for key in small if key not in values), key=str)
        assert not unknown, f"params.SMOKE keys missing from params.PARAMS: {unknown}"
        values.update(small)
    _check_recordable(seed, values, small)
    return seed, values


def _check_recordable(seed, values: dict, small: dict) -> None:
    """Refuse parameters the run record cannot hold (checked before anything is cleared)."""
    try:
        params_sha256(seed, values)  # the strictest dump: the record's, with sorted keys
    except (TypeError, ValueError) as exc:
        culprits = []
        for key, value in values.items():
            try:
                params_sha256(seed, {key: value})
            except (TypeError, ValueError):
                culprits.append(f"{'SMOKE' if key in small else 'PARAMS'}[{key!r}]")
        where = ", ".join(culprits) or "the keys of PARAMS"
        raise AssertionError(
            f"params.py: {where} cannot be recorded in {RECORD} ({exc}): dict keys must be "
            "strings or numbers of one kind (no tuples, no str mixed with int), e.g. "
            '{"0-10": "low"}'
        ) from None


def _remove(path: Path) -> None:
    """Delete a file, a symlink or a directory tree (symlinks are never followed)."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


@contextlib.contextmanager
def _publication_lock(cfg) -> Iterator[None]:
    """One publication per study at a time (it takes a moment, so wait for it)."""
    directory = Path(cfg.STUDY_ROOT) / "result"
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _undo(entries, processed, *, keep_source: bool) -> list[tuple[str, Path]]:
    """Put back what a publication changed; ``entries`` are ``(target, backup)`` pairs.

    A backup that exists holds the old target; a write without a backup created its
    target. Safe to repeat: whatever was already put back is skipped.
    """
    done: list[tuple[str, Path]] = []
    for target, backup in reversed(entries):
        if backup is not None:
            if _exists(backup):
                os.replace(backup, target)
                done.append(("restored", target))
        elif _exists(target):
            target.unlink()
            done.append(("removed", target))
    if processed is not None:
        target, backup, source = processed
        if backup is None or _exists(backup):
            if _exists(target):  # the new directory is in place
                if keep_source and not _exists(source):
                    os.replace(target, source)
                else:
                    _remove(target)
                done.append(("removed", target))
            if backup is not None:
                os.replace(backup, target)
                done.append(("restored", target))
    return done


def _recover_locked(cfg) -> list[str]:
    """Undo a publication killed midway; the caller holds the publication lock."""
    repo_root = Path(cfg.REPO_ROOT)
    result_dir = Path(cfg.STUDY_ROOT) / "result"
    journal_path = result_dir / JOURNAL
    dirs = _dirs(cfg)
    notes: list[str] = []

    def path(text: str | None) -> Path | None:
        return None if text is None else repo_root / text

    if _exists(journal_path):
        journal = _read_json(journal_path) or {}
        try:
            entries = [(path(e["target"]), path(e["backup"])) for e in journal["entries"]]
            processed = journal["processed"]
            if processed is not None:
                processed = tuple(path(processed[key]) for key in ("target", "backup", "source"))
        except (KeyError, TypeError):
            raise AssertionError(
                f"{_display(journal_path, repo_root)} is unreadable: a publication was killed "
                "midway; restore result/ from git (git status shows what changed), then "
                "delete it"
            ) from None
        for action, target in _undo(entries, processed, keep_source=False):
            notes.append(f"{action} {_display(target, repo_root)} (publication killed)")
        pid = str(journal.get("pid"))
        for directory in dirs.values():
            if directory.is_dir():
                for leftover in sorted(directory.iterdir()):
                    match = _TEMP_RE.match(leftover.name)
                    if match and match["kind"] == "part" and match["pid"] == pid:
                        _remove(leftover)
                        notes.append(
                            f"removed {_display(leftover, repo_root)} (publication killed)"
                        )
        journal_path.unlink()
    # Without a journal, no publication is in flight (we hold the lock): every temporary
    # is from one killed before its journal was written or after its commit point.
    for directory in [*dirs.values(), result_dir]:
        if not directory.is_dir():
            continue
        for leftover in sorted(directory.iterdir()):
            match = _TEMP_RE.match(leftover.name)
            if match is None or (directory == result_dir and match["name"] != JOURNAL[1:]):
                continue
            _remove(leftover)
            notes.append(f"removed {_display(leftover, repo_root)} (publication killed)")
    return notes


def recover_interrupted_publication(cfg) -> list[str]:
    """Roll back a publication killed midway in this study (and clear its temporaries).

    Called at the start of every full run. Returns the notes it printed.
    """
    with _publication_lock(cfg):
        notes = _recover_locked(cfg)
    for note in notes:
        print(f"note: {note}", flush=True)
    return notes


def _staged_sets(staged: Path, *, strict: bool) -> list[dict]:
    """The staged artifacts: one per sidecar, with the files its ``files`` map lists."""
    sets = []
    for area in AREAS:
        directory = staged / area
        if not directory.is_dir():
            continue
        entries = {path.name: path for path in directory.iterdir()}
        listed: set[str] = set()
        for name in sorted(entries):
            if not name.endswith(SIDECAR_SUFFIX):
                continue
            sidecar = _read_json(entries[name])
            files = sidecar.get("files") if sidecar is not None else None
            files = sorted(files) if isinstance(files, dict) else []
            if strict:
                missing = [f for f in files if f not in entries or not entries[f].is_file()]
                assert sidecar is not None and not missing, (
                    f"out/{STAGED}/{area}/{name} lists {missing or 'no files'}, which are not "
                    "staged: only the helpers and run.promote() write there"
                )
            listed |= {name, *files}
            sets.append(
                {
                    "area": area,
                    "name": name[: -len(SIDECAR_SUFFIX)],
                    "kind": (sidecar or {}).get("kind"),
                    "files": [*files, name],
                }
            )
        orphans = sorted(
            name for name, path in entries.items() if name not in listed or not path.is_file()
        )
        assert not (strict and orphans), (
            f"out/{STAGED}/{area}/ holds {orphans}, which no sidecar lists: only the helpers "
            "and run.promote() write there"
        )
    return sets


def _belongs(file_name: str, name: str, old_files: set[str]) -> bool:
    """True when ``file_name`` is part of the artifact ``name`` (``<name>.<ext>``)."""
    if file_name in old_files:
        return True
    head, dot, ext = file_name.partition(".")
    return head == name and bool(dot) and _EXTENSION_RE.fullmatch(ext) is not None


class Run:
    """What run.py gets from ``with experiment.start(__file__, params) as run:``."""

    def __init__(self, cfg, exp_dir: Path, out_dir: Path, smoke: bool, seed: int, params: dict,
                 record: dict, record_path: Path) -> None:  # fmt: skip
        self.name, self.study = exp_dir.name, Path(cfg.STUDY_ROOT).name
        self.out_dir, self.smoke, self.seed, self.params = out_dir, smoke, seed, params
        self.record = record
        self._cfg, self._record_path = cfg, record_path
        self._repo_root = Path(cfg.REPO_ROOT)
        # run.promote() entries: result/tables/ artifact -> (source, file name, sources),
        # and data/processed/NNN_<slug>/ relative path -> source.
        self._tables: dict[str, tuple[Path, str, list[dict]]] = {}
        self._processed: dict[str, Path] = {}
        # While publication commits: the handlers a stop signal replaced, and the signals
        # that arrived meanwhile (see _hold).
        self._held: tuple[dict, list[int]] | None = None
        self._start = time.perf_counter()

    def _rel(self, path: Path) -> str:
        return _display(path, self._repo_root)

    def elapsed(self) -> float:
        """Seconds since the run started (after the checks and the clearing)."""
        return time.perf_counter() - self._start

    def stage(self, title: str) -> None:
        """Start a stage: printed at once, and written into the record with its start time."""
        stages = self.record["stages"]
        stages.append({"title": title, "start_s": round(self.elapsed(), 3)})
        _write(self._record_path, self.record)
        print(f"[{self.name}] {len(stages)}. {title} (t = {self.elapsed():.1f} s)", flush=True)

    def log(self, text: str) -> None:
        """Print a progress line with the elapsed time (not recorded)."""
        print(f"    {text} ({self.elapsed():.1f} s)", flush=True)

    def _inside(self, name: str) -> Path:
        path, root = (self.out_dir / name).resolve(), self.out_dir.resolve()
        assert path != root and path.is_relative_to(root), (
            f"{name!r} is not a file under {self._rel(root)}"
        )
        first = path.relative_to(root).parts[0]
        reserved = {STAGED, RECORD, RECORD + ".part", LOCK} | (set() if self.smoke else {SMOKE_DIR})
        assert first not in reserved, f"{name!r}: out/{first} belongs to the harness"
        return path

    def out(self, name: str) -> Path:
        """Path for a working output under out/ (out/smoke/ with --smoke), parents created.

        A name that leaves the directory, or one the harness owns (staged/, the record,
        the lock, and smoke/ in a full run), is refused.
        """
        path = self._inside(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def promote(self, name: str, dest_dir=None, *, sources=None) -> Path:
        """Publish a ``run.out()`` file when the run completes; checked now.

        ``dest_dir`` is ``config.TABLE_DIR`` (the default: a ``<study>-<what>.<ext>`` file
        with a kind ``"file"`` sidecar, e.g. the CSV a figure is drawn from) or
        ``config.PROCESSED_DATA_DIR / run.name`` (large data; that directory is replaced
        as a whole). The file is read when the run completes, and nothing is copied if
        the run fails or runs with --smoke. Returns the destination.

        ``sources`` names the files the output was made from that another run wrote
        (another experiment's ``result/tables/*.csv`` or ``data/processed/NNN_<slug>/``),
        as for the helpers: hashed now and recorded in the sidecar, so ``make check`` W14
        and ``--list-generators`` follow the output back to that experiment. Only a
        ``result/tables/`` file has a sidecar to hold them.
        """
        _check_template(self.name, self.smoke)
        source = self._inside(name)
        assert source.is_file(), (
            f"{self._rel(source)} does not exist: write it through run.out() first"
        )
        entries = _source_entries(sources, self._repo_root)
        dirs = _dirs(self._cfg)
        table_dir = dirs["tables"].resolve()
        mine = (dirs["processed"] / self.name).resolve()
        dest = Path(dirs["tables"] if dest_dir is None else dest_dir).resolve()
        base = Path(name).name
        if dest == table_dir:
            pattern = re.escape(self.study) + r"-[^./\\]+\.[A-Za-z0-9]+"
            assert re.fullmatch(pattern, base), (
                f"{base!r}: promote a <study>-<what>.<ext> name with no other dot (its sidecar "
                "is <study>-<what>.provenance.json)"
            )
            artifact = base.partition(".")[0]
            _check_kind(dirs["tables"], artifact, "file")
            staged = self.out_dir / STAGED / "tables" / f"{artifact}{SIDECAR_SUFFIX}"
            assert artifact not in self._tables and not staged.exists(), _twice(artifact)
            self._warn_large(source, base)
            self._tables[artifact] = (source, base, entries)
            return table_dir / base
        assert dest == mine or dest.is_relative_to(mine), (
            f"{self._rel(dest)}: run.promote() writes to result/tables/ (the default) or "
            "config.PROCESSED_DATA_DIR / run.name; figures go through figures.save_figure "
            "or figures.import_figure"
        )
        relative = (dest / base).relative_to(mine).as_posix()
        assert not entries, (
            f"{self._rel(dest / base)}: sources= is recorded in the sidecar of a result/tables/ "
            "file; data/processed/ has no sidecar, so pass sources= to what this run "
            "publishes in result/ (run.promote() into result/tables/, the helpers)"
        )
        assert relative not in self._processed, _twice(self._rel(dest / base))
        self._processed[relative] = source
        return dest / base

    def _warn_large(self, path: Path, base: str) -> None:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            print(
                f"warning: {base} is {size:,} bytes (> 1 MB): make security would refuse it in "
                "result/tables/; promote large outputs to config.PROCESSED_DATA_DIR / run.name",
                file=sys.stderr,
                flush=True,
            )

    def _staged_listing(self) -> list[str]:
        names: dict[str, set[str]] = {area: set() for area in AREAS}
        for item in _staged_sets(self.out_dir / STAGED, strict=False):
            names[item["area"]].add(item["name"])
        names["tables"] |= set(self._tables)
        listing = [f"{area}/{name}" for area in AREAS for name in sorted(names[area])]
        return listing + [f"processed/{relative}" for relative in sorted(self._processed)]

    def _materialise(self, staged: Path) -> None:
        """Copy the run.promote() files into out/staged/ (P1), checked against git now."""
        tables = staged / "tables"
        for artifact, (source, base, sources) in sorted(self._tables.items()):
            sidecar_path = tables / f"{artifact}{SIDECAR_SUFFIX}"
            assert not sidecar_path.exists(), _twice(artifact)
            tables.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, tables / base)
            self._warn_large(tables / base, base)
            sidecar = {
                "artifact": artifact,
                "kind": "file",
                "study": self.study,
                "script": self.record["script"],
                "experiment": self.name,
                "created": _now(),
                **artifact_git_state(self._cfg),
                "run": {key: self.record[key] for key in ("started", "seed", "params_sha256")},
                "files": {base: _sha256(tables / base)},
                **({"sources": sources} if sources else {}),
            }
            text = json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n"
            sidecar_path.write_text(text, encoding="utf-8")
        for relative, source in sorted(self._processed.items()):
            target = staged / "processed" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def _publish(self) -> None:
        """Put every staged artifact in place, all or none (a full run whose body completed)."""
        cfg, staged = self._cfg, self.out_dir / STAGED
        self._materialise(staged)
        sets = _staged_sets(staged, strict=True)
        dirs = _dirs(cfg)
        target_processed = dirs["processed"] / self.name
        new_processed = staged / "processed" if self._processed else None
        if new_processed is None and _exists(target_processed):
            self.log(
                f"note: {self._rel(target_processed)} is from an earlier run; this run "
                "promoted nothing there (delete it if nothing reads it)"
            )
        if not sets and new_processed is None:
            return
        _check_template(self.name, False)
        for item in sets:
            _check_prefix(item["name"], self.study)
        with _publication_lock(cfg):
            for note in _recover_locked(cfg):
                print(f"note: {note}", flush=True)
            writes, removals = self._plan(sets, staged, dirs)
            self._swap(writes, removals, new_processed, target_processed)
        promoted = sorted(
            self._rel(target) for _, target in writes if not target.name.endswith(SIDECAR_SUFFIX)
        )
        if new_processed is not None:
            promoted.append(self._rel(target_processed) + "/")
        removed = sorted(
            (self._rel(path), reason)
            for path, reason in removals.items()
            if not path.name.endswith(SIDECAR_SUFFIX)
        )
        self.record["promoted"] = promoted
        self.record["removed"] = [path for path, _ in removed]
        for path in promoted:
            self.log(f"published -> {path}")
        for path, reason in removed:
            self.log(f"removed {path} ({reason})")

    def _plan(self, sets: list[dict], staged: Path, dirs: dict) -> tuple[list, dict]:
        """P4: what is written where, and what goes (same-stem and stale artifacts)."""
        writes: list[tuple[Path, Path]] = []
        removals: dict[Path, str] = {}
        published = {(item["area"], item["name"]) for item in sets}
        for item in sets:
            target_dir = dirs[item["area"]]
            _check_kind(target_dir, item["name"], item["kind"])
            writes += [(staged / item["area"] / f, target_dir / f) for f in item["files"]]
            if not target_dir.is_dir():
                continue
            old = _read_json(target_dir / f"{item['name']}{SIDECAR_SUFFIX}") or {}
            old_files = set(old.get("files") or {}) if isinstance(old.get("files"), dict) else set()
            for path in sorted(target_dir.iterdir()):
                if (
                    path.name not in item["files"]
                    and path.is_file()
                    and _belongs(path.name, item["name"], old_files)
                ):
                    removals[path] = "replaced by another format"
        # What this experiment published before and this run no longer publishes.
        for area in AREAS:
            target_dir = dirs[area]
            if not target_dir.is_dir():
                continue
            for sidecar_path in sorted(target_dir.iterdir()):
                name = sidecar_path.name[: -len(SIDECAR_SUFFIX)]
                if (
                    not sidecar_path.name.endswith(SIDECAR_SUFFIX)
                    or sidecar_path.name.startswith(".")
                    or (area, name) in published
                ):
                    continue
                old = _read_json(sidecar_path)
                if old is None or (old.get("study"), old.get("experiment")) != (
                    self.study,
                    self.name,
                ):
                    continue
                reason = "this experiment no longer publishes it"
                removals[sidecar_path] = reason
                files = old.get("files") if isinstance(old.get("files"), dict) else {}
                for file_name in files:
                    path = target_dir / file_name
                    if "/" not in file_name and path.is_file():
                        removals.setdefault(path, reason)
        for _, target in writes:
            removals.pop(target, None)
        return writes, removals

    def _swap(self, writes, removals: dict, new_processed: Path | None, target: Path) -> None:
        """P5-P8: parts, journal, swap, commit; on any exception, roll back and re-raise.

        The caller holds the publication lock. Until the journal is unlinked (the commit
        point), a kill is rolled back by the next full run in the study. From the swap
        on, a stop signal waits until the run is recorded (``_hold``).
        """
        pid = os.getpid()
        journal_path = Path(self._cfg.STUDY_ROOT) / "result" / JOURNAL
        journal_part = journal_path.with_name(f"{JOURNAL}.{pid}.part")
        moves = [
            (path, path.with_name(f".{path.name}.{pid}.previous")) for path in sorted(removals)
        ]
        entries: list[tuple[Path, Path | None]] = list(moves)
        copies: list[tuple[Path, Path, Path | None]] = []  # (part, destination, backup)
        processed: tuple[Path, Path | None, Path] | None = None
        part_dir: Path | None = None
        try:
            # P5: every new file beside its destination, under a name of this process.
            for source, dest in writes:
                dest.parent.mkdir(parents=True, exist_ok=True)
                part = dest.with_name(f".{dest.name}.{pid}.part")
                backup = dest.with_name(f".{dest.name}.{pid}.previous") if _exists(dest) else None
                copies.append((part, dest, backup))
                entries.append((dest, backup))
                shutil.copyfile(source, part)
            if new_processed is not None:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = new_processed
                if os.stat(new_processed).st_dev != os.stat(target.parent).st_dev:
                    part_dir = target.with_name(f".{target.name}.{pid}.part")
                    shutil.copytree(new_processed, part_dir)
                    source = part_dir
                backup = target.with_name(f".{target.name}.{pid}.previous")
                processed = (target, backup if _exists(target) else None, source)
            # P6: the journal, written whole before anything in place changes.
            journal = {
                "pid": pid,
                "experiment": self.name,
                "entries": [
                    {"target": self._rel(t), "backup": None if b is None else self._rel(b)}
                    for t, b in entries
                ],
                "processed": None
                if processed is None
                else {
                    "target": self._rel(processed[0]),
                    "backup": None if processed[1] is None else self._rel(processed[1]),
                    "source": self._rel(processed[2]),
                },
            }
            journal_part.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
            os.replace(journal_part, journal_path)
            self._hold()  # from here a stop waits until the run is recorded
            # P7: the swap.
            for path, backup in moves:
                os.replace(path, backup)
            for part, dest, backup in copies:
                if backup is not None:
                    os.replace(dest, backup)
                os.replace(part, dest)
            if processed is not None:
                if processed[1] is not None:
                    os.replace(target, processed[1])
                os.replace(processed[2], target)
        except BaseException:
            _undo(entries, processed, keep_source=True)
            for part, _, _ in copies:
                part.unlink(missing_ok=True)
            if part_dir is not None and _exists(part_dir):
                _remove(part_dir)
            journal_part.unlink(missing_ok=True)
            journal_path.unlink(missing_ok=True)
            raise
        # P8: the commit point, then the old files go.
        os.unlink(journal_path)
        for _, backup in entries:
            if backup is not None:
                backup.unlink(missing_ok=True)
        if processed is not None and processed[1] is not None:
            _remove(processed[1])

    def _hold(self) -> None:
        """Make SIGINT, SIGTERM and SIGHUP wait from the swap until the run is recorded.

        A stop after the commit point would record a failed run whose files are already
        published. The handlers are replaced rather than the signals blocked, because a
        signal that another thread (a BLAS pool) receives still runs the main thread's
        handler. ``_release`` lets a signal that arrived meanwhile act.
        """
        if self._held is not None or threading.current_thread() is not threading.main_thread():
            return
        handlers: dict = {}
        pending: list[int] = []

        def wait(signum, frame) -> None:
            if not pending:
                note = f"\n[{self.name}] publishing: the stop waits until the run is recorded\n"
                with contextlib.suppress(OSError):
                    os.write(2, note.encode())
            pending.append(signum)

        self._held = (handlers, pending)
        for signum in _STOP_SIGNALS:
            handlers[signum] = signal.signal(signum, wait)

    def _release(self) -> None:
        """Restore the handlers ``_hold`` replaced, then deliver what arrived meanwhile."""
        if self._held is None:
            return
        handlers, pending = self._held
        self._held = None
        for signum, handler in handlers.items():
            signal.signal(signum, signal.SIG_DFL if handler is None else handler)
        for signum in dict.fromkeys(pending):
            signal.raise_signal(signum)


def _study_config(cfg, run_file):
    """The study config (run.py's ``config`` unless given), checked against ``run_file``."""
    if cfg is None:
        cfg = sys.modules.get("config")  # run.py imported its study's config.py as `config`
    assert cfg is not None and all(hasattr(cfg, key) for key in ("REPO_ROOT", "STUDY_ROOT")), (
        "experiment.start() needs this study's config: keep `import config` at the top of "
        "run.py (or pass cfg=config)"
    )
    repo_root, study_root = Path(cfg.REPO_ROOT).resolve(), Path(cfg.STUDY_ROOT).resolve()
    assert study_root.is_relative_to(repo_root), (
        f"the study {study_root} is outside the repository {repo_root}: experiment.start() "
        "needs this study's config"
    )
    if Path(run_file).resolve().parent.parent != (study_root / EXPERIMENTS).resolve():
        raise AssertionError(
            f"{_display(run_file, repo_root)} is not in projects/{study_root.name}/"
            f"{EXPERIMENTS}/<name>/: run projects/<study>/experiments/NNN_<slug>/run.py with "
            "this study's config"
        )
    return cfg


# Runs alive in this process, by record path (for checks that span helpers and promote()).
_LIVE: dict[str, Run] = {}


@contextlib.contextmanager
def start(
    run_file, params: ModuleType, argv: list[str] | None = None, *, cfg=None
) -> Iterator[Run]:
    """Run an experiment: ``with experiment.start(__file__, params) as run:``.

    Parses the flags, holds the output directory's lock, keeps out/params_used.json up
    to date, and publishes what the run staged when a full run completes. ``cfg``
    defaults to the study config run.py imported as ``config``.
    """
    parser = argparse.ArgumentParser(description="Run this experiment (experiments/README.md).")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="apply params.SMOKE, write to out/smoke/, publish nothing",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="replace a completed run; out/ is cleared first"
    )
    args = parser.parse_args(argv)
    cfg = _study_config(cfg, run_file)
    assert not os.environ.get(RUN_ENV), (
        f"an experiment is already running here ({os.environ.get(RUN_ENV)}): runs do not nest"
    )
    exp_dir = Path(run_file).resolve().parent
    out_dir = exp_dir / "out" / SMOKE_DIR if args.smoke else exp_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    # One run at a time per output directory. The kernel releases the lock when the
    # process ends, however it ends, so a free lock means no run is alive here.
    with open(out_dir / LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AssertionError(
                f"Another run is using {_display(out_dir, cfg.REPO_ROOT)}: wait for it to finish"
            ) from None
        yield from _run(args, argv, cfg, Path(run_file), exp_dir, out_dir, params)


def _run(args, argv, cfg, run_file: Path, exp_dir: Path, out_dir: Path, params) -> Iterator[Run]:
    repo_root, study_root = Path(cfg.REPO_ROOT).resolve(), Path(cfg.STUDY_ROOT).resolve()

    def rel(path: Path) -> str:
        return _display(path, repo_root)

    name = exp_dir.name
    record_path = out_dir / RECORD
    previous: dict = {}
    if record_path.is_file():
        loaded = _read_json(record_path)
        if not loaded:  # not JSON, not UTF-8, not an object, or {}
            assert args.overwrite, (
                f"{rel(record_path)} is unreadable: if its run died, pass --overwrite"
            )
            loaded = {"status": "unreadable"}
        previous = loaded
    # What an earlier run left here. A full run leaves out/smoke/ to the smoke runs.
    keep = {".gitkeep", LOCK} if args.smoke else {".gitkeep", LOCK, SMOKE_DIR}
    leftovers = sorted(path for path in out_dir.iterdir() if path.name not in keep)
    if not (args.smoke or args.overwrite):
        assert previous.get("status") != "completed", (
            f"{rel(out_dir)} holds a completed run from {previous.get('started')}: pass "
            "--overwrite to replace it, or start a new experiment to keep it"
        )
        assert previous or not leftovers, (
            f"{rel(out_dir)} holds files that no recorded run wrote: "
            f"{[path.name for path in leftovers]}; pass --overwrite to replace them"
        )
    seed, values = _read_params(params, args.smoke)  # before anything is deleted
    if not args.smoke:
        recover_interrupted_publication(cfg)
    if previous.get("status") == "running":
        # We hold the lock, so that run is not alive.
        print(
            f"[{name}] note: the run started {previous.get('started')} died without recording "
            "its end (killed, out of memory, container recreated); its outputs are cleared",
            flush=True,
        )
    # Clear the earlier run, so that no stale output sits beside the new ones.
    for path in leftovers:
        _remove(path)
    if leftovers:
        print(
            f"[{name}] cleared {len(leftovers)} entries left in {rel(out_dir)} by the earlier run",
            flush=True,
        )

    state = git_state(repo_root, study_root)
    git = (
        {"commit": None, "short": None, "dirty": ["(git cannot tell: no work tree or commit)"]}
        if state is None
        else {"commit": state["commit"], "short": state["short"], "dirty": list(state["dirty"])}
    )
    uv_lock = repo_root / "uv.lock"
    record = {
        "experiment": name,
        "study": study_root.name,
        "status": "running",
        "smoke": args.smoke,
        "argv": sys.argv[1:] if argv is None else list(argv),
        "script": rel(run_file),
        "pid": os.getpid(),
        "started": _now(),
        "seed": seed,
        "params": values,
        "params_sha256": params_sha256(seed, values),
        "git": {**git, "code_paths": code_pathspec(repo_root, study_root)},
        "python": platform.python_version(),
        "uv_lock_sha256": _sha256(uv_lock) if uv_lock.is_file() else None,
        "stages": [],
        "staged": [],
        "promoted": [],
        "removed": [],
    }
    _write(record_path, record)
    run = Run(cfg, exp_dir, out_dir, args.smoke, seed, values, record, record_path)
    print(f"[{name}] {'smoke' if args.smoke else 'full'} run -> {rel(out_dir)}", flush=True)
    if git["dirty"]:
        print(
            "warning: the code is not committed, so what this run writes is recorded as "
            f"uncommitted code (make check W15): {git['dirty']}",
            file=sys.stderr,
            flush=True,
        )
    handlers = {}
    try:
        os.environ[RUN_ENV] = str(record_path)
        _LIVE[str(record_path)] = run
        # Turn SIGTERM and SIGHUP into SystemExit, so that a stopped run is recorded as failed.
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGTERM, signal.SIGHUP):
                handlers[signum] = signal.signal(
                    signum, lambda number, frame: sys.exit(128 + number)
                )
        yield run
        if not args.smoke:
            run._publish()
    except BaseException:
        record["status"], record["error"] = "failed", traceback.format_exc()
        raise
    else:
        record["status"] = "completed"
    finally:
        try:
            os.environ.pop(RUN_ENV, None)
            _LIVE.pop(str(record_path), None)
            record["staged"] = run._staged_listing()
            end = git_state(repo_root, study_root, quiet=True)
            if git["commit"] is None or end is None:
                record["code_state"] = "unknown"
            elif git["dirty"]:
                record["code_state"] = "uncommitted"
            elif _changed(repo_root, study_root, git, end):
                record["code_state"] = "changed_during_run"
            else:
                record["code_state"] = "clean"
            record["finished"], record["elapsed_s"] = _now(), round(run.elapsed(), 3)
            _write(record_path, record)
            print(f"[{name}] {record['status']} in {record['elapsed_s']:.1f} s", flush=True)
        finally:
            try:
                run._release()  # a stop that waited for the record acts now
            finally:
                for signum, handler in handlers.items():
                    signal.signal(signum, handler)


# run.py imports this file as src.utils.experiment; the helpers load it by path under
# UTILS_KEY. Both names end up with one module (one _START, one set of live runs),
# whichever is imported first.
if sys.modules.get(__name__) is not None:
    sys.modules[__name__] = sys.modules.setdefault(UTILS_KEY, sys.modules[__name__])
