"""The LaTeX build recovers from a failed or unfinished run (CI builds the real PDFs).

A lualatex run killed by THESIS_TEX_TIMEOUT (or a kill, or a closed terminal) leaves its .aux
cut off mid-line, and TeX reads it at \\begin{document} before rewriting it, so every later
build would fail until `make clean-tex`. compile.sh starts such a job from an empty build
directory. A stand-in for lualatex keeps these tests free of TeX (the container has none):
like TeX, it fails on a cut-off .aux and rewrites the .aux on every pass.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DRAFT = Path(__file__).resolve().parents[1] / "draft"
COMPILE = DRAFT / "compile.sh"

FAKE_LUALATEX = r"""#!/usr/bin/env bash
for arg in "$@"; do
  case "${arg}" in
    -output-directory=*) dir="${arg#*=}" ;;
    -jobname=*) name="${arg#*=}" ;;
  esac
done
aux="${dir}/${name}.aux"
log="${dir}/${name}.log"
if [ -f "${aux}" ] && grep -q 'CUT' "${aux}"; then
  echo "${name}.aux:1: File ended while scanning use of \BKM@entry." > "${log}"
  exit 1
fi
if [ -n "${FAKE_TEX_HANG:-}" ]; then
  printf '\\BKM@entry{id=1,CUT' > "${aux}"
  exec sleep 60
fi
printf '\\relax\n' > "${aux}"
: > "${log}"
printf '%%PDF-1.4\n' > "${dir}/${name}.pdf"
"""

needs_timeout = pytest.mark.skipif(shutil.which("timeout") is None, reason="needs timeout(1)")


def test_missing_value_marker_is_robust() -> None:
    # In a heading or caption the draft marker reaches the .toc/.lof. Expanded there, a key with
    # `_' (research ids may contain it) is read back as a subscript: "Missing $ inserted".
    text = (DRAFT / "values.tex").read_text(encoding="utf-8")
    draft_branch = text.split("\\ifThesisFinal", 1)[1].split("\\else", 1)[1].split("\\fi", 1)[0]
    assert re.search(r"^\s*\\DeclareRobustCommand\{\\ThesisMissingValue\}", draft_branch, re.M), (
        "draft/values.tex: define the draft and review \\ThesisMissingValue with "
        "\\DeclareRobustCommand"
    )


@pytest.fixture
def draft(tmp_path: Path) -> Path:
    draft = tmp_path / "draft"
    draft.mkdir()
    shutil.copy2(COMPILE, draft / "compile.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "lualatex").write_text(FAKE_LUALATEX, encoding="utf-8")
    (bin_dir / "lualatex").chmod(0o755)
    return draft


def compile_sh(draft: Path, *args: str, hang: bool = False) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{draft.parent / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    env["THESIS_TEX_TIMEOUT"] = "1"
    env.pop("FAKE_TEX_HANG", None)
    if hang:
        env["FAKE_TEX_HANG"] = "1"
    return subprocess.run(
        ["bash", str(draft / "compile.sh"), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=draft.parent,
        timeout=60,
        check=False,
    )


@needs_timeout
def test_build_after_a_timeout_starts_afresh(draft: Path) -> None:
    timed_out = compile_sh(draft, "main", hang=True)
    assert timed_out.returncode == 1
    assert "timed out" in timed_out.stderr
    assert "CUT" in (draft / "build" / "main" / "main.aux").read_text(encoding="utf-8")

    result = compile_sh(draft, "main")
    assert result.returncode == 0, result.stderr
    assert "Built draft/main.pdf" in result.stdout
    assert (draft / "build" / "main" / ".build-complete").is_file()


def test_build_after_a_kill_starts_afresh(draft: Path) -> None:
    # What a killed build leaves behind: a cut-off .aux and no .build-complete marker.
    job = draft / "build" / "main"
    job.mkdir(parents=True)
    (job / "main.aux").write_text("\\BKM@entry{id=1,CUT", encoding="utf-8")
    result = compile_sh(draft, "main")
    assert result.returncode == 0, result.stderr


def test_completed_build_directory_is_reused(draft: Path) -> None:
    assert compile_sh(draft, "main").returncode == 0
    kept = draft / "build" / "main" / "kept.txt"
    kept.write_text("x", encoding="utf-8")
    assert compile_sh(draft, "main").returncode == 0
    assert kept.is_file()
