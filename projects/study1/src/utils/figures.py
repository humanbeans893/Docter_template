"""Save matplotlib figures into FIGURE_DIR with shared style and provenance.

Helpers are config-agnostic: pass the study's ``config`` module (or any object
exposing ``VISUALIZATION`` / ``FIGURE_DIR`` / ``STUDY_ROOT`` / ``REPO_ROOT``),
so the module works unchanged in every study copied from the template.

Typical use in a script::

    import sys
    from pathlib import Path

    STUDY_ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(STUDY_ROOT))

    import config as cfg
    from src.utils.figures import apply_visualization_defaults, save_figure

    apply_visualization_defaults(cfg)
    fig, ax = plt.subplots()
    ...
    save_figure(fig, "<study>-overview", cfg)

Figure names must be bare stems prefixed with the study name (see
``draft/README.md``): the thesis resolves figures through a flat
``\\graphicspath`` namespace shared by all studies.

This module is deliberately self-contained (no sibling imports) so tests can
load it by file path without package machinery.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


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


def _git_state(repo_root: Path) -> dict:
    """Best-effort git commit/dirty state for provenance.

    Provenance is metadata, not data: a missing git repo degrades to
    ``"unknown"`` with a warning instead of failing the figure save
    (deliberate exception to the fail-explicit rule).
    """
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return {"git_commit": commit, "git_dirty": bool(dirty)}
    except (OSError, subprocess.CalledProcessError):
        print(f"warning: could not read git state under {repo_root}", file=sys.stderr)
        return {"git_commit": "unknown", "git_dirty": "unknown"}


def save_figure(
    fig, name: str, cfg, *, formats=None, close: bool = True, **savefig_kwargs
) -> list[Path]:
    """Save ``fig`` as ``FIGURE_DIR/<name>.<format>`` plus a provenance sidecar.

    ``name`` must be a bare stem (no directory, no extension); the extension
    comes from ``cfg.VISUALIZATION["format"]`` unless ``formats`` overrides it.
    A ``<name>.provenance.json`` sidecar records which script and git commit
    produced the figure. Returns the written figure paths (sidecar excluded).
    """
    assert name and "/" not in name and "\\" not in name, (
        f"name must be a bare file stem without directories, got: {name!r}"
    )
    assert "." not in name, (
        f"name must not contain an extension (format comes from config), got: {name!r}"
    )

    viz = cfg.VISUALIZATION
    fmts = list(formats) if formats is not None else [viz["format"]]
    figure_dir = Path(cfg.FIGURE_DIR)
    figure_dir.mkdir(parents=True, exist_ok=True)

    script = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else "unknown"
    provenance = {
        "figure": name,
        "study": Path(cfg.STUDY_ROOT).name,
        "script": str(script),
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        **_git_state(Path(cfg.REPO_ROOT)),
    }

    written: list[Path] = []
    for fmt in fmts:
        out = figure_dir / f"{name}.{fmt}"
        kwargs = {"dpi": viz["dpi"], "bbox_inches": "tight", **savefig_kwargs}
        if fmt == "png":
            # PNG text chunks carry a short summary inside the file itself.
            kwargs.setdefault(
                "metadata",
                {
                    "Software": f"{provenance['study']}: {provenance['script']}",
                    "Comment": f"commit {provenance['git_commit']} at {provenance['created']}",
                },
            )
        fig.savefig(out, **kwargs)
        written.append(out)

    sidecar = figure_dir / f"{name}.provenance.json"
    sidecar.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n")

    if close:
        import matplotlib.pyplot as plt

        plt.close(fig)
    return written
