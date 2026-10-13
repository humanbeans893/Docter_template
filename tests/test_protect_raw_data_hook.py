"""The raw-data hook blocks writes into projects/<study>/data/raw/ and lets reads through.

The hook is driven the way Claude Code runs it: a JSON payload on stdin, exit code 2 = blocked.
Raw data is git-ignored, so a false "allowed" here can mean an unrecoverable loss.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "protect_raw_data.py"
R = "projects/study1/data/raw"

BLOCKED = [
    # Redirections
    f"echo x > {R}/a.csv",
    f"echo x >> {R}/a.csv",
    f"echo x >| {R}/a.csv",
    f"ls &> {R}/ls.txt",
    f"ls 2> {R}/err.txt",
    f"exec 3> {R}/fd.txt",
    f"{{ echo a; echo b; }} > {R}/x.txt",
    f"cat <<'EOF' > {R}/notes.txt\nhello\nEOF",
    f"tee >(gzip > {R}/a.gz) < a.csv",
    # Copy destinations (the source may be anywhere)
    f"cp results/a.csv {R}/",
    f"cp a.csv {R}",
    f"cp -a /mnt/old/run {R}/legacy/run",
    f"cp -t {R}/legacy a.csv b.csv",
    "cp -r backup/raw projects/study1/data/",
    f"rsync -a --exclude .git /mnt/old/ {R}/legacy/old/",
    f"rsync -a /mnt/old/ {R}/legacy/old/ --exclude .git",
    f"rsync -a --remove-source-files {R}/a.csv backup/",
    "rsync -a --delete empty/ projects/study1/",
    f"ln -s /mnt/data {R}/link",
    f"install -m 644 a.csv {R}/a.csv",
    f"install -d {R}/legacy",
    # Moving, removing and changing files
    f"mv {R}/a.csv elsewhere/a.csv",
    f"mv a.csv {R}/",
    "mv projects/study1 projects/study2",
    f"rm -f {R}/a.csv",
    f"/bin/rm {R}/a.csv",
    f"\\rm {R}/a.csv",
    "rm -rf projects/study1/data",
    "rm -rf projects/study1",
    "rm -rf projects/*/data/raw/*",
    "rm -r projects/study1/data/*",
    "rm -rf .",
    "rm -rf ./*",
    f"rmdir {R}/legacy",
    f"mkdir -p {R}/legacy/x",
    f"touch {R}/a.csv",
    "touch projects/_template/data/raw/x",
    "touch {root}/projects/study1/data/raw/a.csv",
    f"truncate -s 0 {R}/a.csv",
    f"chmod -R u+w {R}",
    f"chown -R me {R}",
    f"ls | tee {R}/list.txt",
    f"sed -i 's/a/b/' {R}/a.csv",
    f"sed --in-place=.bak 's/a/b/' {R}/a.csv",
    f"perl -pi -e 's/a/b/' {R}/a.csv",
    f"dd if=/dev/zero of={R}/a.bin bs=1 count=1",
    f"sort -o {R}/a.csv a.csv",
    f"gzip {R}/a.csv",
    f"xz -k {R}/a.csv",
    # In-place rewriters (encoding, line endings), renamers and tools that write an output file
    f"shred -u {R}/a.csv",
    f"sed -I '' 's/a/b/' {R}/a.csv",
    f"sed -ni 's/a/b/p' {R}/a.csv",
    f"perl -CSD -0777 -pi.bak -e 's/a/b/' {R}/a.csv",
    f"dos2unix {R}/legacy/src/metrics.csv",
    f"unix2dos -q {R}/a.csv",
    f"mac2unix -k {R}/a.csv",
    f"dos2unix -n a.csv {R}/b.csv",
    f"dos2unix -n {R}/a.csv b.csv -o {R}/c.csv",
    f"cd {R} && dos2unix a.csv",
    f"nkf -w --overwrite {R}/legacy/src/metrics.csv",
    f"nkf --in-place=.bak -w {R}/a.csv",
    f"nkf -w -O a.csv {R}/b.csv",
    f"iconv -f CP932 -t UTF-8 {R}/a.csv -o {R}/a.csv",
    f"iconv -c --output={R}/b.csv -f CP932 a.csv",
    f"iconv -f CP932 -t UTF-8 {R}/a.csv | sponge {R}/a.csv",
    f"awk -i inplace '{{print}}' {R}/a.csv",
    f"gawk -iinplace -F, -f fix.awk {R}/a.csv",
    f"gawk --include=inplace -v OFS=, '{{$1=$1}} 1' {R}/a.csv",
    f"gawk '@include \"inplace\"; {{print}}' {R}/a.csv",
    f"patch {R}/a.csv < fix.diff",
    f"patch -i fix.diff {R}/a.csv",
    f"patch -p1 -o {R}/b.csv a.csv fix.diff",
    f"patch -d {R}/legacy/src -p1 < fix.diff",
    f"cd {R}/legacy/src && patch -p1 < /tmp/fix.diff",
    f"patch -p1 <<'EOF'\n--- a/{R}/a.csv\n+++ b/{R}/a.csv\n@@ -1 +1 @@\n-x\n+y\nEOF",
    f"git apply <<'EOF'\ndiff --git a/{R}/a.csv b/{R}/a.csv\n--- a/{R}/a.csv\n+++ b/{R}/a.csv\n"
    "@@ -1 +1 @@\n-x\n+y\nEOF",
    f"cd {R} && git apply /tmp/fix.diff",
    f"rename 's/ /_/g' {R}/legacy/src/*",
    f"perl-rename -v 's/\\.CSV$/.csv/' {R}/*.CSV",
    f"rename .CSV .csv {R}/legacy/src/*.CSV",
    f"split -l 1000 {R}/big.csv {R}/part_",
    f"cd {R} && split -l 1000 big.csv",
    f"csplit -f {R}/part {R}/big.csv '/^#/' '{{*}}'",
    f"uniq {R}/a.csv {R}/b.csv",
    # Archives and downloads
    f"tar -xzf old.tar.gz -C {R}/legacy/old",
    f"tar xf old.tar --directory={R}/legacy/old",
    f"git -C ../old-repo archive abc123 | tar -x -C {R}/legacy/old/code/",
    f"cd {R}/legacy && tar -xf ../../../../../old.tar",
    f"tar -czf {R}/backup.tgz src",
    f"unzip old.zip -d {R}/legacy/old",
    f"curl -sSLo {R}/a.csv https://example.org/a.csv",
    f"wget -P {R} https://example.org/a.csv",
    # find with actions over raw, and commands run by find -exec
    f"find {R} -name '*.tmp' -delete",
    f"find {R} -type f -exec rm {{}} +",
    f"find {R} -execdir chmod 644 {{}} \\;",
    f"find out -name '*.png' -exec cp {{}} {R}/ \\;",
    # find from a directory that holds raw data, like rm -r of that directory
    "find projects/study1 -delete",
    "find projects/study1/data -mindepth 1 -delete",
    "find . -name '*.csv' -delete",
    "find {root} -name '*.nc' -delete",
    "find . -name '*.nc' -exec rm {} +",
    "find projects/study1 -name '*.csv' -exec rm -f {} \\;",
    "find . -name '*.tmp' -execdir rm {} +",
    "find projects -name '*.tmp' -ok rm {} \\;",
    "find projects/study1/data -okdir rm {} \\;",
    "find projects -type f -exec sed -i 's/a/b/' {} +",
    "find projects/study1 -name '*.csv' -exec dos2unix {} +",
    "find . -name '*.csv' -exec nkf -w --overwrite {} \\;",
    "find projects -name '*.csv' -exec iconv -f CP932 -t UTF-8 {} -o {}.utf8 \\;",
    "find projects -name '*.csv' -exec gawk -i inplace '{print}' {} +",
    "find projects -name '* *' -exec rename 's/ /_/g' {} +",
    "find projects -name '*.csv' | xargs dos2unix",
    f"find {R} -name '*.csv' -exec dos2unix {{}} +",
    "find . -type f -exec sh -c 'rm \"$1\"' _ {} \\;",
    "find projects -type f -name '*.csv' | xargs rm -f",
    "find . -name '*.csv' -print0 | xargs -0 rm",
    'find projects -name "*.csv" | while read -r f; do rm "$f"; done',
    # Compound commands, working directory, variables, loops and pipes
    f"ls && cp a.csv {R}/",
    f"true || rm {R}/a.csv",
    f"echo ok; rm {R}/a.csv",
    f"echo start\nrm {R}/a.csv",
    f"cd {R} && touch new.csv",
    "cd projects/study1/data && rm -rf raw",
    f"pushd {R} && rm a.csv",
    f"(cd {R} && sha256sum * > SHA256SUMS)",
    f'RAW={R}; cp a.csv "$RAW/"',
    f'export RAW={R}\nrm -rf "${{RAW}}/legacy"',
    f'for f in {R}/*.csv; do rm "$f"; done',
    f"find {R} -name '*.csv' -print0 | xargs -0 rm",
    f'find {R} -type f | while read -r f; do rm "$f"; done',
    f"ls {R}/ | xargs -I{{}} rm {R}/{{}}",
    # Nested shells, substitutions and wrappers
    f"bash -c 'rm {R}/a.csv'",
    f'sh -c "cd {R} && rm a.csv"',
    f'eval "rm {R}/a.csv"',
    f"echo $(rm {R}/a.csv)",
    f'echo "`rm {R}/a.csv`"',
    # An apostrophe in a here-document inside $(...) is text, not a quote
    f"git commit -qm \"$(cat <<'EOF'\nit's done\nEOF\n)\"; rm -rf {R}",
    f'echo "$(cat <<EOF\nthe user\'s )\nEOF\n)"; rm -rf {R}',
    f"sudo rm {R}/a.csv",
    f"env LC_ALL=C rm {R}/a.csv",
    f"timeout 10 cp a.csv {R}/",
    f"time -p rm {R}/a.csv",
    # Git commands that delete or move git-ignored files (raw data is git-ignored)
    "git clean -fdx",
    "git clean -X -f",
    "git stash --all",
]

ALLOWED = [
    # Reading raw data
    f"ls -la {R}",
    f"cat {R}/README.md",
    f"sha256sum {R}/legacy/old/*",
    f"find {R} -type f -name '*.csv'",
    f"find {R} -type f | wc -l",
    f"find {R} -name '*.csv' -print0 | xargs -0 sha256sum",
    "du -sh projects/*/data/raw",
    f"wc -l < {R}/a.csv",
    f"diff {R}/a.csv projects/study1/data/processed/a.csv",
    f"git status --short {R}",
    f"git check-ignore -v {R}/a.csv",
    f"ls {R} 2>/dev/null || echo missing",
    f"ls {R}/ > /dev/null",
    f"grep -c '>' {R}/a.fasta",
    # find from the repository without a destructive action, or started below data/raw's parents
    "find . -name '*.py' -exec grep -l raw {} +",
    "find projects -name '*.csv' -exec wc -l {} +",
    "find projects -name '*.csv' | xargs sha256sum",
    "find projects/study1/experiments -name '*.nc' -delete",
    "find projects/study1/data/interim -mindepth 1 -delete",
    "find draft -type f -name '*.aux' -exec rm -f -- {} +",
    "find /var/tmp/other -name '*.nc' -delete",
    # The manifest command of docs/importing-past-results.md: reads raw, writes elsewhere
    f"(cd {R}/legacy/old && find . -type f ! -name .gitkeep -print0 | LC_ALL=C sort -z"
    " | xargs -0 sha256sum) > projects/study1/experiments/001_old/inputs.sha256",
    f"sha256sum {R}/legacy/old/a.csv | tee projects/study1/experiments/001_old/inputs.sha256",
    # Copying or unpacking FROM raw
    f"cp {R}/a.csv projects/study1/data/interim/a.csv",
    f"cp -a {R}/legacy/old/fig.png /tmp/fig.png",
    f"rsync -a {R}/ backup/raw-copy/",
    f"ln -s {R}/a.csv link.csv",
    f"tar -tzf {R}/old.tar.gz",
    f"tar -xzf {R}/old.tar.gz -C projects/study1/data/interim/old",
    f"tar -xzf {R}/old.tgz -O | head",
    f"tar -czf backup.tgz {R}",
    f"unzip -l {R}/old.zip",
    f"gzip -c {R}/a.csv > /tmp/a.csv.gz",
    f"zstd -d {R}/a.zst -o projects/study1/data/interim/a",
    f"grep -rn depth {R} > projects/study1/data/interim/hits.txt",
    # Converting or splitting raw files into files outside raw, and read-only modes
    f"nkf --guess {R}/a.csv",
    f"nkf -w {R}/a.csv > projects/study1/data/interim/a.csv",
    f"iconv -f CP932 -t UTF-8 {R}/a.csv -o projects/study1/data/interim/a.csv",
    f"iconv -f CP932 -t UTF-8 {R}/a.csv | sponge projects/study1/data/interim/a.csv",
    f"dos2unix -n {R}/a.csv projects/study1/data/interim/a.csv",
    f"dos2unix -ic {R}/*.csv",
    f"dos2unix -O {R}/a.csv > projects/study1/data/interim/a.csv",
    f"awk -F, '{{print $1}}' {R}/a.csv",
    f"awk -v n=1 -f prog.awk {R}/a.csv",
    "gawk -i inplace '{print}' projects/study1/data/interim/a.csv",
    f"perl -MList::Util=sum -lane 'print sum @F' {R}/a.csv",
    f"perl -Ilib -ne 'print if /id/' {R}/a.csv",
    f"perl -CSDi -ne 'print' {R}/a.csv",
    f"sed -n '1p' {R}/a.csv",
    f"rename -n 's/ /_/g' {R}/legacy/src/*",
    "rename 's/ /_/g' projects/study1/experiments/001_x/out/*",
    f"split -l 1000 {R}/big.csv projects/study1/data/interim/part_",
    f"csplit -f projects/study1/data/interim/part {R}/big.csv '/^#/' '{{*}}'",
    f"uniq -c {R}/a.csv",
    f"sort {R}/a.csv | uniq > projects/study1/data/interim/u.csv",
    f"patch -o /tmp/a.csv {R}/a.csv < fix.diff",
    f"cd {R} && patch --dry-run -p1 < /tmp/fix.diff",
    "patch -p1 < fix.diff",
    "patch -p1 <<'EOF'\n--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1 @@\n-a\n+b\nEOF",
    "git apply fix.patch",
    "git apply --check fix.patch",
    f"cat <<'EOF' > /tmp/fix.diff\n--- a/{R}/a.csv\n+++ b/{R}/a.csv\nEOF",
    "find projects -name '*.csv' -exec iconv -f CP932 -t UTF-8 {} \\;",
    "find . -name '*.csv' -exec awk 'NR==1' {} \\;",
    "find projects -name '*.csv' | xargs dos2unix -i",
    "find projects -name '*.csv' | xargs nkf --guess",
    "find projects/study1/experiments -name '*.csv' -exec dos2unix {} +",
    # Writing next to raw, but not into it
    "mkdir -p projects/study1/data/interim/acquired/x",
    "rm -rf projects/study1/data/interim/tmp",
    "rm -f projects/study1/result/figures/old.png",
    "rm -rf build draft/build",
    f"cd {R} && ls && cd ../../experiments && touch notes.md",
    "git clean -fd",
    # Ancestor protection applies to this repository only (scratch copies elsewhere)
    "rm -rf /var/tmp/other/projects/demo",
    # Text that only mentions raw paths
    f"echo 'rm {R}/a.csv'",
    f'echo "a; rm {R}/x"',
    f"printf '%s\\n' \"rsync -a /mnt/old/ {R}/legacy/old/\"",
    f"cat <<'EOF'\nrsync -a /mnt/old/ {R}/legacy/old/\nrm -rf {R}\nEOF",
    "git commit -m \"$(cat <<'EOF'\nFix the user's bug\nEOF\n)\"",
    f"git commit -m \"$(cat <<'EOF'\nThe user's step:\n  mkdir -p {R}/legacy/old\nEOF\n)\"",
    f"gh pr create --body \"$(cat <<'EOF'\nIt doesn't touch raw. User runs:\n"
    f'rsync -a /mnt/old/ {R}/legacy/old/\nEOF\n)"',
    "x=$(cat <<-EOF\n\tdon't\n\tEOF\n)",
    # Ordinary repository commands
    "docker compose exec -T research-template uv run python "
    "projects/study1/experiments/001_x/run.py --smoke",
    "python3 tools/thesis_check.py --all",
    "make check",
    "echo done 2>&1",
]


def run_hook(payload, root: Path) -> subprocess.CompletedProcess[str]:
    """Run the hook as Claude Code does, with `root` as the project directory."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=stdin,
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
        cwd=root,
        timeout=30,
        check=False,
    )


def run_bash(command: str, root: Path, cwd: Path | None = None) -> subprocess.CompletedProcess:
    command = command.replace("{root}", str(root))
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd or root)}
    return run_hook(payload, root)


@pytest.mark.parametrize("command", BLOCKED)
def test_blocks_bash_writes_into_raw(command, tmp_path):
    result = run_bash(command, tmp_path)
    assert result.returncode == 2, f"not blocked: {command!r}\n{result.stderr}"
    assert "data/raw/" in result.stderr


@pytest.mark.parametrize("command", ALLOWED)
def test_allows_reads_and_writes_elsewhere(command, tmp_path):
    result = run_bash(command, tmp_path)
    assert result.returncode == 0, f"blocked: {command!r}\n{result.stderr}"


def test_message_names_the_target_and_the_users_step(tmp_path):
    result = run_bash(f"rsync -a /mnt/old/ {R}/legacy/old/", tmp_path)
    assert result.returncode == 2
    assert f"rsync destination: {R}/legacy/old/" in result.stderr
    assert "user's step" in result.stderr
    assert "docs/importing-past-results.md" in result.stderr


def test_working_directory_inside_raw(tmp_path):
    raw = tmp_path / R
    raw.mkdir(parents=True)
    assert run_bash("touch new.csv", tmp_path, cwd=raw).returncode == 2
    assert run_bash("sha256sum * > /tmp/inputs.sha256", tmp_path, cwd=raw).returncode == 0


def test_patch_and_git_apply_check_the_files_a_diff_file_names(tmp_path):
    hunk = "@@ -1 +1 @@\n-x\n+y\n"
    (tmp_path / "raw.diff").write_text(f"--- a/{R}/a.csv\t2024-01-01\n+++ b/{R}/a.csv\n{hunk}")
    (tmp_path / "ok.diff").write_text(f"--- a/src/x.py\n+++ b/src/x.py\n{hunk}")
    for command in (
        "patch -p1 < raw.diff",
        "patch -p1 -i raw.diff",
        "patch --input=raw.diff",
        "git apply raw.diff",
        "git apply --index -p1 - < raw.diff",
    ):
        assert run_bash(command, tmp_path).returncode == 2, command
    for command in (
        "patch -p1 < ok.diff",
        "git apply ok.diff",
        "patch --dry-run -p1 < raw.diff",
        "git apply --check raw.diff",
        "git apply --cached raw.diff",
    ):
        assert run_bash(command, tmp_path).returncode == 0, command


def test_symlink_into_raw_is_resolved(tmp_path):
    raw = tmp_path / R
    raw.mkdir(parents=True)
    (tmp_path / "rawlink").symlink_to(raw, target_is_directory=True)
    assert run_bash("touch rawlink/a.csv", tmp_path).returncode == 2
    write = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "rawlink/a.csv")}}
    assert run_hook(write, tmp_path).returncode == 2


@pytest.mark.parametrize(
    ("tool", "field", "relative", "expected"),
    [
        ("Write", "file_path", f"{R}/a.csv", 2),
        ("Edit", "file_path", "projects/_template/data/raw/README.md", 2),
        ("NotebookEdit", "notebook_path", f"{R}/notes.ipynb", 2),
        ("Write", "file_path", "projects/study1/data/interim/a.csv", 0),
        ("Edit", "file_path", "projects/study1/data/README.md", 0),
        ("Write", "file_path", "projects/study1/experiments/001_old/inputs.sha256", 0),
    ],
)
def test_file_tools(tool, field, relative, expected, tmp_path):
    payload = {"tool_name": tool, "tool_input": {field: str(tmp_path / relative)}}
    result = run_hook(payload, tmp_path)
    assert result.returncode == expected, result.stderr


@pytest.mark.parametrize(
    "payload",
    ["", "not json", "[1, 2]", '{"tool_input": "x"}', '{"tool_name": "Bash", "tool_input": {}}'],
)
def test_malformed_input_never_blocks(payload, tmp_path):
    assert run_hook(payload, tmp_path).returncode == 0


def test_unparsable_command_that_writes_raw_is_still_blocked(tmp_path):
    # bash would reject the unterminated quote; the whitespace fallback still sees the target.
    assert run_bash(f'rm {R}/a.csv "unterminated', tmp_path).returncode == 2
    assert run_bash('echo "unterminated', tmp_path).returncode == 0


# --- The hook never fails open (any exit status other than 2 lets the tool call through) ------
SETTINGS = HOOK.parents[1] / "settings.json"
REPO = HOOK.parents[2]
RAW_WRITE = {"tool_name": "Bash", "tool_input": {"command": f"touch {R}/a.csv"}, "cwd": "/"}


def run_python(code: str, payload, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
        cwd=root,
        timeout=30,
        check=False,
    )


def test_too_old_interpreter_blocks_with_a_message(tmp_path):
    code = (
        "import runpy, sys\n"
        "sys.version_info = (3, 8, 10, 'final', 0)\n"
        "runpy.run_path(sys.argv[1], run_name='__main__')\n"
    )
    harmless = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(tmp_path)}
    result = run_python(code, harmless, tmp_path)
    assert result.returncode == 2, result.stderr
    assert "Python 3.8" in result.stderr
    assert "3.10 or newer" in result.stderr


def test_error_inside_the_hook_blocks(tmp_path):
    code = (
        "import json, runpy, sys\n"
        "def broken(*args, **kwargs):\n"
        "    raise RuntimeError('boom')\n"
        "json.load = broken\n"
        "runpy.run_path(sys.argv[1], run_name='__main__')\n"
    )
    result = run_python(code, {"tool_name": "Bash", "tool_input": {"command": "ls"}}, tmp_path)
    assert result.returncode == 2, result.stderr
    assert "BLOCKED" in result.stderr
    assert "RuntimeError: boom" in result.stderr


def settings_hook_command() -> str:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    (entry,) = settings["hooks"]["PreToolUse"]
    assert {"Write", "Edit", "NotebookEdit", "Bash"} <= set(entry["matcher"].split("|"))
    (hook,) = entry["hooks"]
    return hook["command"]


def run_settings_command(payload, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run the hook command of .claude/settings.json through sh, as Claude Code does."""
    return subprocess.run(
        ["/bin/sh", "-c", settings_hook_command()],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": str(bin_dir), "CLAUDE_PROJECT_DIR": str(REPO)},
        cwd=REPO,
        timeout=30,
        check=False,
    )


def test_settings_command_runs_the_hook(tmp_path):
    (tmp_path / "python3").symlink_to(sys.executable)
    blocked = run_settings_command({**RAW_WRITE, "cwd": str(REPO)}, tmp_path)
    assert blocked.returncode == 2, blocked.stderr
    assert "touch: projects/study1/data/raw/a.csv" in blocked.stderr
    harmless = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(REPO)}
    assert run_settings_command(harmless, tmp_path).returncode == 0


@pytest.mark.parametrize("python3", ["missing", "crashes"])
def test_settings_command_blocks_when_the_hook_cannot_run(python3, tmp_path):
    if python3 == "crashes":  # e.g. a SyntaxError on an interpreter too old to parse the hook
        fake = tmp_path / "python3"
        fake.write_text("#!/bin/sh\necho 'SyntaxError: invalid syntax' >&2\nexit 1\n")
        fake.chmod(0o755)
    result = run_settings_command(RAW_WRITE, tmp_path)
    assert result.returncode == 2, result.stderr
    assert "BLOCKED: the raw-data hook" in result.stderr
    assert "3.10 or newer" in result.stderr
