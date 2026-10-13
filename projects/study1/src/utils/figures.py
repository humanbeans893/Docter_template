"""Save matplotlib figures, or import past images, into FIGURE_DIR with provenance.

Helpers are config-agnostic: pass the study's ``config`` module (or any object
exposing ``VISUALIZATION`` / ``FIGURE_DIR`` / ``STUDY_ROOT`` / ``REPO_ROOT``),
so the module works unchanged in every study copied from the template.

Typical use in a script::

    import sys
    from pathlib import Path

    STUDY_ROOT = Path(__file__).resolve().parents[1]  # parents[2] in experiments/NNN_<slug>/
    sys.path.insert(0, str(STUDY_ROOT))

    import config as cfg
    from src.utils.figures import apply_visualization_defaults, save_figure

    apply_visualization_defaults(cfg)
    fig, ax = plt.subplots()
    ...
    save_figure(fig, "<study>-overview", cfg)

Inside ``experiment.start()`` the files go to the run's ``out/staged/`` and
reach ``result/`` when a full run completes (see experiment.py); outside a run
(a ``scripts/`` promotion script) they are written to ``result/`` at once.

Every figure gets a ``<name>.provenance.json`` sidecar (script, experiment,
time, git commit, the run inside an experiment, sha256 of each written file,
optional keys such as ``reproducibility`` and ``sources``);
``tools/thesis_check.py`` reads it. A script that draws from files another run
wrote (``result/tables/*.csv``, ``data/processed/NNN_<slug>/``) names them
with ``sources=[...]`` so the checker can follow them back to that experiment.
A past image that cannot be regenerated is brought in with ``import_figure``
(R3, see ``docs/importing-past-results.md``).

The figure files themselves carry no time and no commit, so regenerating
from the same code gives the same bytes; only the sidecar changes.

The commit a figure is credited to is the one the run started from (the run
record inside an experiment; outside a run, the git state when this module is
imported, so import it at the top of the script). If the code changes during
the run (a commit, or an uncommitted edit), the sidecar records the start
commit as uncommitted code and a warning says so. Only code counts (this
study's ``src/``, ``scripts/``, ``config.py`` and ``experiments/**/*.py``, and
the repository's ``config.py``, ``pyproject.toml`` and ``uv.lock``); prose and
every study's ``result/`` never do.

Figure names must be bare stems prefixed with the study name (see
``draft/README.md``): the thesis resolves figures through a flat
``\\graphicspath`` namespace shared by all studies.

This module loads only ``experiment.py`` beside it, by file path, so tests can
still load it by path.
"""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path


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

# Extensions graphicx tries for an extension-less \includegraphics, in its order.
# A stale sibling (an old .pdf next to a new .png) would silently win, so every
# save/import removes the siblings it did not write (publication does the same).
GRAPHICS_EXTENSIONS = _experiment.GRAPHICS_EXTENSIONS
# The repository rejects tracked files over 1 MB (tools/public_repo_check.py).
MAX_FILE_BYTES = _experiment.MAX_FILE_BYTES

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

_IMPORT_AS_IS = (".png", ".pdf", ".jpg", ".jpeg")
_IMPORT_CONVERTIBLE = (".tif", ".tiff", ".gif", ".bmp", ".webp")
# Pillow modes that PNG stores without loss; colour spaces below are converted to RGB.
_PNG_MODES = {"1", "L", "LA", "P", "PA", "RGB", "RGBA", "I;16"}
_RGB_CONVERTIBLE_MODES = {"CMYK", "YCbCr", "LAB", "HSV"}
_FORMAT_RE = re.compile(r"^[a-z0-9]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def apply_visualization_defaults(cfg) -> None:
    """Apply the shared ``VISUALIZATION`` constants to matplotlib rcParams."""
    import matplotlib

    viz = cfg.VISUALIZATION
    matplotlib.rcParams.update(
        {
            "savefig.dpi": viz["dpi"],
            "font.family": viz["font"]["family"],
            "font.size": viz["font"]["size"],
        }
    )


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
    assert "." not in name, (
        f"name must not contain an extension (the format is chosen separately), got: {name!r}"
    )


def _check_extra(extra, reserved=()) -> dict:
    """Validate the optional provenance mapping before anything is written."""
    if extra is None:
        return {}
    assert isinstance(extra, Mapping), f"provenance must be a mapping, got: {type(extra)!r}"
    extra = dict(extra)
    clashes = sorted(set(extra) & (set(CORE_KEYS) | set(reserved)))
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


@contextlib.contextmanager
def _reproducible_output(fmt: str, name: str):
    """Fix what matplotlib would vary between runs: the PS/EPS date and the SVG ids."""
    import matplotlib

    rc = {}
    if fmt == "svg" and matplotlib.rcParams["svg.hashsalt"] is None:
        rc["svg.hashsalt"] = name
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
    try:
        with matplotlib.rc_context(rc):
            yield
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)


def _remove_stale_siblings(figure_dir: Path, name: str, written: list[Path]) -> None:
    keep = {path.name for path in written}
    for path in sorted(figure_dir.iterdir()):
        if (
            path.stem == name
            and path.suffix.lower() in GRAPHICS_EXTENSIONS
            and path.name not in keep
            and path.is_file()
        ):
            path.unlink()
            print(f"removed stale {path.name}", file=sys.stderr)


def _write_sidecar(
    figure_dir: Path, name: str, written: list[Path], core: dict, extra: dict
) -> Path:
    sidecar = {
        **core,
        "files": {path.name: _sha256(path) for path in written},
        **extra,
    }
    path = figure_dir / f"{name}.provenance.json"
    path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _core_provenance(name: str, cfg) -> dict:
    script, experiment = _running_script(cfg)
    return {
        "artifact": name,
        "kind": "figure",
        "study": Path(cfg.STUDY_ROOT).name,
        "script": script,
        "experiment": experiment,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        **_git_state(cfg),
        **_run_key(cfg),
    }


def save_figure(
    fig,
    name: str,
    cfg,
    *,
    formats=None,
    close: bool = True,
    sources=None,
    provenance=None,
    **savefig_kwargs,
) -> list[Path]:
    """Save ``fig`` as ``FIGURE_DIR/<name>.<format>`` plus a provenance sidecar.

    ``name`` must be a bare stem (no directory, no extension); the extension
    comes from ``cfg.VISUALIZATION["format"]`` unless ``formats`` overrides it.
    ``sources`` lists the files the figure is drawn from (paths, hashed here):
    a promotion script in ``scripts/`` names the ``result/tables/*.csv`` or
    ``data/processed/NNN_<slug>/`` files it read, so ``make check`` can follow
    them to the experiment that made them. ``provenance`` adds optional
    sidecar keys (``reproducibility``, ``sources`` entries, ``note``, ...); a
    key that collides with a core key is refused. Files of the same name in
    another graphics format are removed so LaTeX cannot pick a stale one. The
    files carry no time and no commit (those are in the sidecar), so the same
    code and data give the same bytes. Inside a run the name must start with
    ``<study>-`` and is written once per run. Returns the written figure paths
    (sidecar excluded; the staged paths inside a run).
    """
    _check_name(name)
    extra = _with_sources(_check_extra(provenance), _source_entries(sources, cfg))

    viz = cfg.VISUALIZATION
    fmts = list(dict.fromkeys(formats)) if formats is not None else [viz["format"]]
    assert fmts, "formats must name at least one format, e.g. ['pdf']"
    for fmt in fmts:
        assert isinstance(fmt, str) and _FORMAT_RE.match(fmt), (
            f"formats must be lowercase extensions without a dot (e.g. 'png'), got: {fmt!r}"
        )
    core = _core_provenance(name, cfg)  # first: it refuses a run.py outside start()
    figure_dir = _experiment.artifact_dir(cfg, "figures", name, "figure")
    figure_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for fmt in fmts:
        out = figure_dir / f"{name}.{fmt}"
        kwargs = {"dpi": viz["dpi"], "bbox_inches": "tight", **savefig_kwargs}
        # No time or commit inside the file: matplotlib would stamp the time into
        # PDF/SVG, and the sidecar holds both.
        fixed = {
            "png": {"Software": f"{core['study']}: {core['script']}"},
            "pdf": {"CreationDate": None},
            "svg": {"Date": None},
        }.get(fmt)
        if fixed is not None:
            kwargs["metadata"] = {**fixed, **(savefig_kwargs.get("metadata") or {})}
        with _reproducible_output(fmt, name):
            fig.savefig(out, **kwargs)
        written.append(out)
        size = out.stat().st_size
        if size > MAX_FILE_BYTES:
            print(
                f"warning: {out.name} is {size:,} bytes (> 1 MB, the repository refuses it); "
                "lower dpi, rasterize dense artists, or save as vector PDF",
                file=sys.stderr,
            )

    if _experiment.active_run(cfg) is None:  # inside a run, publication does it
        _remove_stale_siblings(figure_dir, name, written)
    _write_sidecar(figure_dir, name, written, core, extra)

    if close:
        import matplotlib.pyplot as plt

        plt.close(fig)
    return written


def import_figure(
    source,
    name: str,
    cfg,
    *,
    note: str,
    license: str,
    convert_to_png: bool = False,
    sources=None,
    provenance=None,
) -> Path:
    """Copy a past image that cannot be regenerated into FIGURE_DIR as R3.

    For figures that survive only as images (``docs/importing-past-results.md``).
    ``.png`` / ``.pdf`` / ``.jpg`` / ``.jpeg`` are copied unchanged; with
    ``convert_to_png=True`` also ``.tif`` / ``.tiff`` / ``.gif`` / ``.bmp`` /
    ``.webp`` are converted to PNG (first frame). ``note`` says why the figure
    is included as-is and ``license`` who may reuse it (both required). The
    sidecar records ``reproducibility: "R3"`` and, as ``sources``, the copied
    file with its sha256. When ``source`` is a copy made under ``out/`` (a
    resized image, one frame of an animation), name the verified original with
    ``sources=[source_entry(original, cfg, sha256=verified[name])]`` (or
    ``provenance={"sources": [...]}``): the sidecar then records the original
    as the source and the file actually copied as ``copied``.
    Returns the path of the copied figure (the staged path inside a run).
    """
    source = Path(source)
    assert source.exists(), f"source image does not exist: {source}"
    assert source.is_file(), f"source must be a file, got: {source}"
    _check_name(name)
    assert isinstance(note, str) and note.strip(), (
        "note must say why this figure is included as-is (R3), e.g. "
        "'instrument output; raw data lost'"
    )
    assert isinstance(license, str) and license.strip(), (
        "license must state the reuse terms, e.g. 'own work' or 'CC BY 4.0, Smith et al. 2024'"
    )
    reserved = ("reproducibility", "note", "license", "converted_from", "copied")
    extra = _with_sources(
        _check_extra(provenance, reserved=reserved), _source_entries(sources, cfg)
    )
    originals = extra.pop("sources", None)

    suffix = source.suffix.lower()
    if suffix in _IMPORT_AS_IS:
        target_suffix = suffix
        payload = None
        size = source.stat().st_size
    else:
        assert suffix in _IMPORT_CONVERTIBLE, (
            f"unsupported image type {source.suffix!r}: use one of {_IMPORT_AS_IS}"
            f" (or {_IMPORT_CONVERTIBLE} with convert_to_png=True)"
        )
        assert convert_to_png, (
            f"{source.name}: {source.suffix!r} is not a LaTeX graphics format; "
            "pass convert_to_png=True to store it as PNG"
        )
        target_suffix = ".png"
        payload = _convert_to_png(source)
        size = len(payload)
    assert size <= MAX_FILE_BYTES, (
        f"{source.name} would be {size:,} bytes in result/figures (> 1 MB, the repository "
        "refuses it): convert or compress it in code first, and prefer vector PDF"
    )

    core = _core_provenance(name, cfg)  # first: it refuses a run.py outside start()
    figure_dir = _experiment.artifact_dir(cfg, "figures", name, "figure")
    figure_dir.mkdir(parents=True, exist_ok=True)
    target = figure_dir / f"{name}{target_suffix}"
    if payload is None:
        shutil.copyfile(source, target)
    else:
        target.write_bytes(payload)

    copied = {"path": _display_path(source, Path(cfg.REPO_ROOT)), "sha256": _sha256(source)}
    details = {
        "reproducibility": "R3",
        "sources": originals or [copied],
        "note": note.strip(),
        "license": license.strip(),
    }
    if originals:
        details["copied"] = copied
    if payload is not None:
        details["converted_from"] = suffix
    if _experiment.active_run(cfg) is None:  # inside a run, publication does it
        _remove_stale_siblings(figure_dir, name, [target])
    _write_sidecar(figure_dir, name, [target], core, {**details, **extra})
    return target


def _convert_to_png(source: Path) -> bytes:
    """Return the first frame of ``source`` encoded as PNG bytes."""
    from PIL import Image

    with Image.open(source) as image:
        image.seek(0)
        frame = image.copy()
    if frame.mode not in _PNG_MODES:
        assert frame.mode in _RGB_CONVERTIBLE_MODES, (
            f"{source.name}: image mode {frame.mode!r} has no faithful PNG form; if it holds "
            "measurements, plot them with save_figure instead (R2)"
        )
        frame = frame.convert("RGB")
    buffer = io.BytesIO()
    frame.save(buffer, format="PNG")
    return buffer.getvalue()
