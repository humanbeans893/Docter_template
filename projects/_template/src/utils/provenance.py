"""Verify past results before they are used, and check numbers against references.

Past outputs are copied by the user into ``data/raw/legacy/<source>/`` and
described by a GNU ``sha256sum`` manifest committed next to the experiment
(``experiments/NNN_<slug>/inputs.sha256``). ``verify_inputs`` proves that the files
on disk are exactly the registered ones before any figure, table or value is
regenerated from them; ``crosscheck`` compares regenerated numbers with the
archived or published ones (see ``docs/importing-past-results.md``).

Typical use in ``experiments/NNN_<slug>/run.py``::

    from src.utils.provenance import crosscheck, source_entry, verify_inputs

    verified = verify_inputs(
        params.SOURCE_DIR,
        params.MANIFEST,
        cache=config.INTERIM_DATA_DIR / run.name / "inputs_verified.json",
    )
    metrics = params.SOURCE_DIR / "results" / "metrics.csv"
    sources = [source_entry(metrics, config, sha256=verified["results/metrics.csv"])]

This module is deliberately self-contained (no sibling imports) so tests can
load it by file path without package machinery.
"""

import hashlib
import json
import math
import numbers
import os
import re
import shlex
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REFERENCE_KEYS = {"value", "rtol", "atol", "source"}
# Excluded from manifests: placeholders that keep empty directories in git.
IGNORED_NAMES = {".gitkeep"}
# The service in docker-compose.yml; Python and the past files outside the
# repository (/external) are only reachable inside it.
COMPOSE_SERVICE = "research-template"
_NOT_UTF8 = (
    "a file name is not UTF-8 (Shift_JIS/CP932 names come from zips made on Japanese "
    "Windows). Rename the copied files on the host, e.g. `convmv -r -f cp932 -t utf8 "
    "--notest <dir>`, or extract the zip again with `unzip -O cp932`, then regenerate "
    "the manifest"
)


def sha256_file(path) -> str:
    """Return the hex sha256 of ``path``, read in chunks so large files fit in memory."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _in_repository(path) -> bool:
    """True when ``path`` lies under the working directory (the repository root)."""
    return Path(path).resolve().is_relative_to(Path.cwd().resolve())


def manifest_command(directory, manifest) -> str:
    """Return the shell command that writes the sha256 manifest of ``directory``.

    The command is run on the host from the repository root. It only reads
    ``directory`` (raw data stays untouched) and writes the manifest outside
    it. Paths are shown relative to the working directory (the repository
    root, both on the host and in Docker) when possible. A directory outside
    the repository (e.g. ``/external``, mounted by docker-compose.files.yml)
    exists only inside the container, so its command runs there through
    ``docker compose exec``.
    """

    def shown(path) -> str:
        path = Path(path)
        try:
            text = path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            text = str(path)
        return shlex.quote(text)

    command = (
        f"(cd {shown(directory)} && find . -type f ! -name .gitkeep -print0 "
        f"| LC_ALL=C sort -z | xargs -0 sha256sum) > {shown(manifest)}"
    )
    if _in_repository(directory):
        return command
    return f"docker compose exec -T {COMPOSE_SERVICE} bash -c {shlex.quote(command)}"


def _unescape(name: str, line_no: int, path: Path) -> str:
    """Undo GNU sha256sum's escaping of backslash, newline and carriage return."""
    out = []
    chars = iter(name)
    for ch in chars:
        if ch != "\\":
            out.append(ch)
            continue
        nxt = next(chars, "")
        replacement = {"\\": "\\", "n": "\n", "r": "\r"}.get(nxt)
        assert replacement is not None, f"{path}:{line_no}: bad escape '\\{nxt}' in file name"
        out.append(replacement)
    return "".join(out)


def read_sha256_manifest(path) -> dict[str, str]:
    """Parse a GNU ``sha256sum`` manifest into {relative name: lowercase hex}.

    Accepts the text (``<hex>  <name>``) and binary (``<hex> *<name>``) forms
    and the escaped form sha256sum writes for names with a backslash or a
    newline; a leading ``./`` (from ``find .``) is stripped.
    """
    path = Path(path)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        line_no = raw[: exc.start].count(b"\n") + 1
        raise AssertionError(f"{path}:{line_no}: {_NOT_UTF8}") from None
    entries: dict[str, str] = {}
    for line_no, line in enumerate(text.split("\n"), start=1):
        if not line:
            continue
        escaped = line.startswith("\\")
        if escaped:
            line = line[1:]
        digest, sep, rest = line[:64], line[64:66], line[66:]
        assert _HEX_RE.match(digest) and sep in ("  ", " *") and rest, (
            f"{path}:{line_no}: not a sha256sum line (expected '<64 hex>  <name>'): {line!r}"
        )
        assert rest != "-", (
            f"{path}:{line_no}: '-' is standard input: the directory had no files when the "
            "manifest was generated"
        )
        name = _unescape(rest, line_no, path) if escaped else rest
        if name.startswith("./"):
            name = name[2:]
        assert name not in entries, f"{path}:{line_no}: {name!r} is listed twice"
        entries[name] = digest.lower()
    return entries


def _files_under(directory: Path) -> dict[str, Path]:
    """Regular files below ``directory`` (like ``find -type f``: no symlinks, no .gitkeep)."""
    found: dict[str, Path] = {}
    for root, _dirs, files in os.walk(directory):
        for file_name in files:
            full = Path(root) / file_name
            if file_name in IGNORED_NAMES or full.is_symlink() or not full.is_file():
                continue
            name = full.relative_to(directory).as_posix()
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                raise AssertionError(f"{directory}: {name!r}: {_NOT_UTF8}") from None
            found[name] = full
    return found


def _cache_hit(cache: Path, directory: Path, manifest_sha: str, files: dict[str, Path], expected):
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached["directory"] != str(directory) or cached["manifest_sha256"] != manifest_sha:
            return False
        recorded = cached["files"]
        if set(recorded) != set(files):
            return False
        for name, full in files.items():
            stat = full.stat()
            entry = recorded[name]
            if (
                entry["sha256"] != expected[name]
                or entry["size"] != stat.st_size
                or entry["mtime_ns"] != stat.st_mtime_ns
            ):
                return False
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def verify_inputs(directory, manifest, *, recorded=None, cache=None) -> dict[str, str]:
    """Check that ``directory`` holds exactly the files of ``manifest``, unchanged.

    Fails (AssertionError) when the manifest is missing or empty, the directory
    is missing, a file is missing or unregistered, a file name is not UTF-8, a
    hash differs, or a hash the old tool recorded itself (``recorded``:
    manifest-relative name -> hex, only for files inside ``directory``)
    disagrees with the manifest. ``cache`` (e.g.
    ``config.INTERIM_DATA_DIR / run.name / "inputs_verified.json"``, which full and
    smoke runs share) skips re-hashing when the manifest and every file's size and
    mtime are unchanged since the last full verification; it is written whole
    (through a temporary file), with its directory created. Returns
    {relative name: sha256}.
    """
    directory = Path(directory).resolve()
    manifest = Path(manifest).resolve()
    command = manifest_command(directory, manifest)
    if _in_repository(directory):
        todo = (
            f"copy the past files to {directory} on the host, then generate the manifest "
            "with this command, run on the host from the repository root"
        )
    else:
        todo = (
            f"{directory} is outside the repository and exists only inside the container "
            "(/external is the folder EXTERNAL_FILES_DIR names on the host): put the past "
            "files there on the host, then generate the manifest with this command, run on "
            "the host from the repository root (it runs inside the container)"
        )
    assert manifest.is_file(), f"no input manifest {manifest}: {todo}:\n  {command}"
    expected = read_sha256_manifest(manifest)
    assert expected, f"input manifest {manifest} is empty: {todo}:\n  {command}"
    if _in_repository(directory):
        absent = "copy the past files there on the host (see the experiment README)"
    else:
        absent = (
            "outside the repository it is reached only through the read-only /external mount, "
            "which is missing or does not hold it. List docker-compose.files.yml in COMPOSE_FILE "
            "in .env, set EXTERNAL_FILES_DIR to the host folder of the past files, check that no "
            "job is running, then run make up"
        )
    assert directory.is_dir(), f"{directory} is not a directory: {absent}"
    for name in expected:
        pure = PurePosixPath(name)
        assert not pure.is_absolute() and ".." not in pure.parts, (
            f"manifest entry {name!r} points outside {directory}"
        )

    files = _files_under(directory)
    missing = sorted(set(expected) - set(files))
    unregistered = sorted(set(files) - set(expected))
    assert not missing and not unregistered, (
        f"{directory} does not match {manifest.name}: missing {missing}, unregistered "
        f"{unregistered}. Restore the missing files, or regenerate the manifest after a "
        f"deliberate change:\n  {command}"
    )

    manifest_sha = sha256_file(manifest)
    cache = Path(cache) if cache is not None else None
    if cache is None or not _cache_hit(cache, directory, manifest_sha, files, expected):
        actual = {name: sha256_file(full) for name, full in files.items()}
        changed = sorted(name for name in expected if actual[name] != expected[name])
        assert not changed, (
            f"sha256 differs from {manifest.name} for {changed}: the past files changed "
            "after registration (raw data must stay untouched)"
        )
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "directory": str(directory),
                "manifest": str(manifest),
                "manifest_sha256": manifest_sha,
                "files": {
                    name: {
                        "sha256": actual[name],
                        "size": full.stat().st_size,
                        "mtime_ns": full.stat().st_mtime_ns,
                    }
                    for name, full in sorted(files.items())
                },
                "verified_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            part = cache.with_name(f".{cache.name}.{os.getpid()}.part")
            part.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            os.replace(part, cache)

    problems = []
    for name, digest in sorted((recorded or {}).items()):
        name = name[2:] if name.startswith("./") else name
        if name not in expected:
            problems.append(
                f"{name}: recorded by the old tool but not in the manifest (RECORDED_SHA256 "
                "names only files inside the copied directory; check a hash of input data "
                "against the checksum in that dataset's data/README.md entry instead)"
            )
        elif expected[name] != str(digest).lower():
            problems.append(f"{name}: old record {digest} != manifest {expected[name]}")
    assert not problems, "recorded hashes disagree with the manifest:\n  " + "\n  ".join(problems)
    return expected


def source_entry(path, cfg, *, sha256: str | None = None) -> dict[str, str]:
    """Return ``{"path", "sha256"}`` for a provenance ``sources`` list.

    ``path`` is stored repo-relative when it lies in the repository; pass the
    hash ``verify_inputs`` already returned as ``sha256`` to avoid re-reading
    a large file.
    """
    path = Path(path)
    assert path.is_file(), f"source file does not exist: {path}"
    resolved = path.resolve()
    try:
        shown = resolved.relative_to(Path(cfg.REPO_ROOT).resolve()).as_posix()
    except ValueError:
        shown = str(resolved)
    digest = sha256_file(path) if sha256 is None else sha256.lower()
    assert _HEX_RE.match(digest), f"sha256 must be 64 hex characters, got: {sha256!r}"
    return {"path": shown, "sha256": digest}


def _real(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def crosscheck(actual: Mapping, reference: Mapping) -> list[dict]:
    """Compare regenerated numbers with reference numbers; fail listing every mismatch.

    ``reference[key] = {"value": float, "rtol": 0, "atol": 0, "source": str}``
    (``source``: where the reference number is written, e.g. a bib key and
    table). A row passes when ``|actual - reference| <= atol + rtol * |reference|``.
    Every row is computed before failing, so the message shows everything.
    Returns the rows ``{key, actual, reference, abs_diff, rtol, atol, source, ok}``.
    """
    assert isinstance(actual, Mapping), f"actual must be a mapping, got: {type(actual)!r}"
    assert isinstance(reference, Mapping) and reference, "reference must be a non-empty mapping"
    rows: list[dict] = []
    problems: list[str] = []
    for key in sorted(reference):
        spec = reference[key]
        assert isinstance(spec, Mapping), f"reference[{key!r}] must be a mapping, got: {spec!r}"
        unknown = sorted(set(spec) - _REFERENCE_KEYS)
        assert not unknown, f"reference[{key!r}] has unknown fields {unknown}"
        assert _real(spec.get("value")), f"reference[{key!r}]['value'] must be a number"
        source = spec.get("source")
        assert isinstance(source, str) and source.strip(), (
            f"reference[{key!r}] needs a 'source' (where the number is written)"
        )
        rtol, atol = spec.get("rtol", 0), spec.get("atol", 0)
        assert _real(rtol) and rtol >= 0 and _real(atol) and atol >= 0, (
            f"reference[{key!r}]: rtol and atol must be non-negative numbers"
        )
        if key not in actual:
            problems.append(f"{key}: no regenerated value (fill `actual`)")
            continue
        value = actual[key]
        assert _real(value), f"actual[{key!r}] must be a number, got: {value!r}"
        ref = float(spec["value"])
        diff = abs(float(value) - ref)
        ok = math.isfinite(diff) and diff <= float(atol) + float(rtol) * abs(ref)
        rows.append(
            {
                "key": key,
                "actual": float(value),
                "reference": ref,
                "abs_diff": diff,
                "rtol": float(rtol),
                "atol": float(atol),
                "source": source,
                "ok": ok,
            }
        )
        if not ok:
            problems.append(
                f"{key}: {float(value)!r} vs {ref!r} ({source}), |diff| {diff:.3g} > "
                f"atol {float(atol):g} + rtol {float(rtol):g} * |reference|"
            )
    assert not problems, "crosscheck failed:\n  " + "\n  ".join(problems)
    return rows
