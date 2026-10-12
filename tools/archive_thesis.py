#!/usr/bin/env python3
"""Archive the submitted version of the thesis in dist/<TAG>/.

    git tag <TAG>                 # on the commit that was submitted
    make archive TAG=<TAG>        # runs make submission first, then this tool
    python3 tools/archive_thesis.py --tag <TAG>

Refuses unless the working tree is clean, TAG exists and points at HEAD, and
draft/submission.pdf and draft/supplementary.pdf exist. Writes the git-ignored
dist/<TAG>/ with:
  submission.pdf, supplementary.pdf   the built PDFs
  source.tar                          `git archive` of TAG (code, manuscript, manifests)
  data-manifest.tsv                   path, size and sha256 of every file under
                                      projects/*/data/raw/ (read only; raw is not in Git)
  generators.txt                      `thesis_check.py --list-generators`: the scripts
                                      that regenerate every figure, table and value
  SHA256SUMS                          sha256 of the files above (`sha256sum -c SHA256SUMS`)

An existing dist/<TAG>/ is never overwritten. Stdlib only, so it runs on the host
(python3 3.10 or newer).
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The host python3 runs this file; stop with one line instead of a TypeError on old ones.
if sys.version_info < (3, 10):  # noqa: UP036
    sys.exit(f"{Path(__file__).name}: needs python3 3.10 or newer, not {sys.version.split()[0]}")

REPO_ROOT = Path(__file__).resolve().parents[1]
THESIS_CHECK = Path(__file__).resolve().with_name("thesis_check.py")
PDFS = ("submission.pdf", "supplementary.pdf")


class ArchiveError(Exception):
    """A precondition failed; nothing has been written."""


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ArchiveError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_preconditions(root: Path, tag: str) -> Path:
    """Return the archive directory, or raise ArchiveError naming every problem."""
    problems: list[str] = []
    try:
        git(root, "check-ref-format", f"refs/tags/{tag}")
    except ArchiveError:
        raise ArchiveError(f"{tag!r} is not a valid tag name") from None
    status = git(root, "status", "--porcelain")
    if status.strip():
        changed = ", ".join(line[3:] for line in status.splitlines()[:5])
        problems.append(f"the working tree is not clean ({changed}): commit or stash first")
    try:
        tagged = git(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}")
    except ArchiveError:
        problems.append(f"tag {tag!r} does not exist: create it on the submitted commit first")
    else:
        head = git(root, "rev-parse", "HEAD")
        if tagged.strip() != head.strip():
            problems.append(f"tag {tag!r} does not point at HEAD: check out the tagged commit")
    for name in PDFS:
        if not (root / "draft" / name).is_file():
            problems.append(f"draft/{name} is missing: run make submission first")
    target = root / "dist" / tag
    if target.exists():
        problems.append(f"dist/{tag} already exists: archives are never overwritten")
    probe = f"dist/{tag}/SHA256SUMS"
    ignored = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", probe], capture_output=True, check=False
    )
    if ignored.returncode != 0:
        problems.append("dist/ is not git-ignored: add /dist/ to .gitignore")
    if problems:
        raise ArchiveError("\n".join(problems))
    return target


def data_manifest(root: Path) -> list[str]:
    """``path<TAB>size<TAB>sha256`` of every file under projects/*/data/raw/ (reads only)."""
    files: list[Path] = []
    for raw in (root / "projects").glob("*/data/raw"):
        for directory, _dirnames, filenames in os.walk(raw):
            files.extend(Path(directory) / name for name in filenames)
    rows = ["path\tsize\tsha256"]
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        if path.is_file():  # skips dangling symlinks
            relative = path.relative_to(root).as_posix()
            rows.append(f"{relative}\t{path.stat().st_size}\t{sha256_file(path)}")
    return rows


def generators(root: Path) -> str:
    command = [sys.executable, str(THESIS_CHECK), "--draft-dir", str(root / "draft")]
    result = subprocess.run(
        [*command, "--list-generators"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ArchiveError(f"thesis_check.py --list-generators failed: {result.stderr.strip()}")
    return result.stdout


def build(root: Path, tag: str, staging: Path) -> None:
    for name in PDFS:
        shutil.copy2(root / "draft" / name, staging / name)
    prefix = tag.replace("/", "-")
    source = staging / "source.tar"
    git(root, "archive", "--format=tar", f"--prefix={prefix}/", "-o", str(source), tag)
    manifest = "\n".join(data_manifest(root)) + "\n"
    (staging / "data-manifest.tsv").write_text(manifest, encoding="utf-8")
    (staging / "generators.txt").write_text(generators(root), encoding="utf-8")
    names = sorted(path.name for path in staging.iterdir() if path.is_file())
    sums = [f"{sha256_file(staging / name)}  {name}" for name in names]
    (staging / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")


def archive(root: Path, tag: str) -> Path:
    target = check_preconditions(root, tag)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".archive.", suffix=".tmp", dir=target.parent))
    try:
        build(root, tag, staging)
        os.replace(staging, target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tag", required=True, help="the tag of the submitted commit (at HEAD)")
    args = parser.parse_args(argv)
    try:
        target = archive(root, args.tag)
    except ArchiveError as exc:
        print("error: nothing was archived:", file=sys.stderr)
        for line in str(exc).splitlines():
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"Archived {args.tag} in {target.relative_to(root).as_posix()}/:")
    for name in sorted(path.name for path in target.iterdir()):
        print(f"  {name}")
    print("Keep a copy outside this machine (dist/ is not in Git). Verify later with:")
    print(f"  (cd {target.relative_to(root).as_posix()} && sha256sum -c SHA256SUMS)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
