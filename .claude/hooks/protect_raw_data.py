#!/usr/bin/env python3
"""PreToolUse hook: block writes into projects/<study>/data/raw/.

Raw data is immutable and git-ignored, so a raw file that is overwritten or deleted cannot be
restored from Git (AGENTS.md). Exit code 2 blocks the tool call and feeds stderr back to the
agent; malformed input never blocks.

- Write / Edit / NotebookEdit: the target file.
- Bash: the write targets of every command in the line. The line is split on ;, &&, ||, |, &
  and newlines with quoting respected, and subshells, cd/pushd, simple variables, for loops,
  here-documents, $(...), bash -c, eval and wrappers (sudo, env, timeout, xargs, ...) are
  followed. A write target is: the destination of cp/rsync/install/ln/scp; any path argument of
  mv/rm/rmdir/touch/mkdir/truncate/chmod/chown/chgrp/tee/shred/unlink and of sed -i/perl -i;
  dd of=; sort -o; the -C/--directory (or working) directory of tar -x and the archive of
  tar -c/-r/-u; unzip -d; output files of curl/wget; a raw file given to gzip/xz/zstd/bzip2
  without -c; find over raw with -delete/-exec/-execdir/-ok/-okdir; an output redirection
  (>, >>, &>, ...). Inside this repository, recursive rm or mv of a directory that holds raw
  data (projects/, projects/<s>/, projects/<s>/data/, the repository itself), find over one
  with -delete or with -exec/-ok of a destructive command, and rsync --delete into one are
  blocked as well, and so are git clean -x/-X and git stash --all, which remove git-ignored
  files, and xargs running a destructive command on input that names raw paths or comes from
  such a find. Reading raw data (ls, cat, sha256sum, find without destructive actions, copying
  FROM raw, redirecting elsewhere) is allowed.

This is a safety net, not a sandbox: writes made by programs (python, make recipes) and paths
computed at run time are invisible here. The read-only raw mounts in docker-compose.yml and the
deny rules in .claude/settings.json are the other layers.

The hook never fails open: an interpreter that is too old, or an error inside the hook, blocks
the tool call with a message (exit 2) instead of letting it through. It runs on Python 3.9 and
newer; the host tools need 3.10 (README.md). The command in .claude/settings.json also turns
any other exit status (python3 missing, a syntax error on an old interpreter) into a block.
"""

from __future__ import annotations

import fnmatch
import json
import os
import posixpath
import re
import sys

# The host's python3 runs this file, not the project's Python: check before anything else runs.
if sys.version_info < (3, 9):  # noqa: UP036
    print(
        "BLOCKED: the raw-data hook (.claude/hooks/protect_raw_data.py) cannot run on Python "
        f"{sys.version_info[0]}.{sys.version_info[1]}. Install python3 3.10 or newer on the host "
        "(README.md); until then every tool call is blocked.",
        file=sys.stderr,
    )
    sys.exit(2)

RAW_PATTERN = re.compile(r"(^|/)projects/[^/]+/data/raw(/|$)")
NONE, ANCESTOR, RAW = 0, 1, 2
EXPAND = "\x00"  # a `$` the shell would expand (unquoted or inside double quotes)
SUBST = "\x01"  # the output of a command or process substitution
MAX_DEPTH = 4
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
EXPANSION = re.compile(EXPAND + r"(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
FD_WORD = re.compile(r"\d+|\{[A-Za-z_][A-Za-z0-9_]*\}")
HEREDOC_WORD = re.compile(r"[ \t]*((?:'[^']*'|\"[^\"]*\"|\\.|[^\s;&|()<>'\"])+)")

EMPTY: frozenset[str] = frozenset()
# Longest first: the lexer takes the first operator that matches.
OPERATORS = tuple("&>> <<< && || ;; |& >> >| &> >& <& << <> ; & | ( ) < >".split())
OPERATOR_CHARS = set(";&|()<>")
WRITE_REDIRECTS = {">", ">>", ">|", "&>", "&>>", "<>", ">&"}
READ_REDIRECTS = {"<", "<&", "<<<", "<<", "<<-"}
LIST_SEPARATORS = {";", "&", "&&", "||", ";;", "\n"}
KEYWORDS = frozenset("{ } ! if then else elif fi do done while until esac".split())

SHELLS = frozenset({"bash", "sh", "dash", "zsh", "ksh"})
FIND_OPERATORS = frozenset({"(", ")", "!", ","})
ANY_PATH = frozenset(
    (
        "rmdir touch mkdir truncate chmod chown chgrp tee shred unlink mkfifo mknod chattr setfacl"
    ).split()
)
DESTRUCTIVE = ANY_PATH | {"rm", "mv"}
COMPRESSORS = frozenset(
    "gzip gunzip pigz unpigz bzip2 bunzip2 xz unxz lzma unlzma zstd unzstd".split()
)
RSYNC_LONG_VALUES = frozenset(
    (
        "--exclude --include --exclude-from --include-from --filter --files-from --rsh"
        " --rsync-path --temp-dir --partial-dir --backup-dir --suffix --compare-dest --copy-dest"
        " --link-dest --chmod --chown --usermap --groupmap --log-file --log-file-format"
        " --out-format --password-file --bwlimit --max-size --min-size --max-delete --timeout"
        " --contimeout --port --sockopts --block-size --modify-window --remote-option --iconv"
        " --checksum-choice --compress-choice --compress-level --skip-compress --info --debug"
        " --write-batch --only-write-batch --read-batch --address"
    ).split()
)
TARGET_LONG = frozenset({"--target-directory", "--suffix"})
COPY_SPECS = {  # command -> (short options taking a value, long options taking a value)
    "cp": ("tS", TARGET_LONG),
    "ln": ("tS", TARGET_LONG),
    "install": ("gmoSt", TARGET_LONG | {"--group", "--mode", "--owner", "--strip-program"}),
    "rsync": ("eTfMB@", RSYNC_LONG_VALUES),
    "scp": ("cFiJloPSDX", EMPTY),
}
RSYNC_WRITE_OPTIONS = tuple(
    "-T --temp-dir --partial-dir --backup-dir --log-file --write-batch --only-write-batch".split()
)
TAR_SHORT_VALUES = set("fCbHKLNTVXgFI")
TAR_LONG_VALUES = frozenset(
    (
        "--file --directory --exclude --exclude-from --files-from --transform --xform --owner"
        " --group --mode --mtime --newer --after-date --newer-mtime --label --format"
        " --use-compress-program --blocking-factor --record-size --tape-length --info-script"
        " --new-volume-script --listed-incremental --starting-file --strip-components --suffix"
        " --to-command --rsh-command --volno-file"
    ).split()
)
CURL_SHORT_VALUES = "AbcCdDeEFHKmoPQrTtuUwxXYyz"
CURL_LONG_VALUES = frozenset(
    (
        "--output --output-dir --dump-header --cookie-jar --cookie --data --data-raw"
        " --data-binary --data-urlencode --header --request --user --user-agent --referer --form"
        " --max-time --connect-timeout --retry --proxy --range --upload-file --write-out --config"
        " --url --cacert --cert --key --resolve --limit-rate --continue-at"
    ).split()
)
WGET_SHORT_VALUES = "oaeiBtOTwQPlADRIXUn"
WGET_LONG_VALUES = frozenset(
    "--output-document --directory-prefix --output-file --append-output --input-file".split()
)
XARGS_LONG_VALUES = frozenset(
    "--arg-file --delimiter --max-args --max-procs --max-chars --process-slot-var".split()
)
SORT_LONG_VALUES = frozenset(
    (
        "--output --key --field-separator --buffer-size --temporary-directory --files0-from"
        " --batch-size --compress-program --parallel --random-source --sort"
    ).split()
)
# command -> (short options taking a value, long options taking a value, operands to skip)
WRAPPERS = {
    "sudo": (
        "ughpCUrtDRT",
        frozenset("--user --group --host --prompt --close-from --role --type --chdir".split()),
        0,
    ),
    "doas": ("uC", EMPTY, 0),
    "env": ("uCS", frozenset({"--unset", "--chdir", "--split-string"}), 0),
    "nice": ("n", frozenset({"--adjustment"}), 0),
    "nohup": ("", EMPTY, 0),
    "builtin": ("", EMPTY, 0),
    "exec": ("a", EMPTY, 0),
    "command": ("", EMPTY, 0),
    "time": ("fo", frozenset({"--format", "--output"}), 0),
    "timeout": ("sk", frozenset({"--signal", "--kill-after"}), 1),  # the duration comes first
    "stdbuf": ("ioe", frozenset({"--input", "--output", "--error"}), 0),
    "ionice": ("cn", frozenset({"--class", "--classdata"}), 0),
    "chronic": ("", EMPTY, 0),
    "unbuffer": ("", EMPTY, 0),
}

PIPED_RAW = "projects/<piped>/data/raw/<line>"  # what `read` gets from a pipe that lists raw
RAW_STEP = (
    "Raw data is immutable and git-ignored, so a lost raw file cannot be restored from Git (see "
    "AGENTS.md). Write derived files to data/interim/ or data/processed/ from code. Copying "
    "past results into data/raw/ is the user's step: show them the command to run in their own "
    "terminal instead of running it (docs/importing-past-results.md)."
)


class LexError(ValueError):
    """The command could not be tokenized (unbalanced quotes or substitutions)."""


class Lexer:
    """Split a shell line into ("word", text) and ("op", text) tokens with quotes removed.

    The bodies of $(...), `...`, <(...) and >(...) are collected in `subs` so they are checked as
    commands of their own; here-document bodies are skipped because they are data.
    """

    def __init__(self, text: str):
        self.text, self.n = text, len(text)
        self.tokens: list[tuple[str, str]] = []
        self.subs: list[str] = []
        self.heredocs: list[tuple[str, bool]] = []
        self.heredoc_op: str | None = None
        self.buf: list[str] = []
        self.in_word = False
        self.quoted = False

    def add(self, chunk: str, *, quoted: bool = False) -> None:
        self.buf.append(chunk)
        self.in_word = True
        self.quoted = self.quoted or quoted

    def end_word(self) -> None:
        if self.in_word:
            word = "".join(self.buf)
            if self.heredoc_op:
                self.heredocs.append((word.replace(EXPAND, "$"), self.heredoc_op == "<<-"))
                self.heredoc_op = None
            self.tokens.append(("word", word))
        self.buf, self.in_word, self.quoted = [], False, False

    def run(self) -> tuple[list[tuple[str, str]], list[str]]:
        t, i = self.text, 0
        while i < self.n:
            c = t[i]
            if c in " \t\r":
                self.end_word()
                i += 1
            elif c == "\n":
                self.end_word()
                self.tokens.append(("op", "\n"))
                i = self.skip_heredocs(i + 1)
            elif c == "#" and not self.in_word:
                j = t.find("\n", i)
                i = self.n if j < 0 else j
            elif c == "\\":
                if t.startswith("\\\n", i):
                    i += 2
                else:
                    self.add(t[i + 1 : i + 2] or "\\", quoted=True)
                    i += 2
            elif c == "'":
                j = t.find("'", i + 1)
                if j < 0:
                    raise LexError("unterminated single quote")
                self.add(t[i + 1 : j], quoted=True)
                i = j + 1
            elif c == '"':
                i = self.double_quoted(i + 1)
            elif c == "`":
                j = self.backtick_end(i + 1)
                self.subs.append(t[i + 1 : j].replace("\\`", "`"))
                self.add(SUBST)
                i = j + 1
            elif c == "$":
                i = self.dollar(i, in_double=False)
            elif c in "<>" and t.startswith("(", i + 1):
                self.end_word()
                j = self.paren_end(i + 2)
                self.subs.append(t[i + 2 : j])
                self.add(SUBST)
                self.end_word()
                i = j + 1
            elif c in OPERATOR_CHARS:
                i = self.operator(i)
            else:
                self.add(c)
                i += 1
        self.end_word()
        return self.tokens, self.subs

    def operator(self, i: int) -> int:
        t = self.text
        fd_number = self.in_word and not self.quoted and FD_WORD.fullmatch("".join(self.buf))
        if t[i] in "<>" and fd_number:
            self.buf, self.in_word = [], False  # `2>file`: the digits name a file descriptor
        else:
            self.end_word()
        op = next(o for o in OPERATORS if t.startswith(o, i))
        if op == "<<" and t.startswith("-", i + 2):
            op = "<<-"
        self.tokens.append(("op", op))
        if op in ("<<", "<<-"):
            self.heredoc_op = op
        return i + len(op)

    def dollar(self, i: int, *, in_double: bool) -> int:
        """Handle the `$` at i (expansion, $'...', $"...", $(...), $((...)))."""
        t = self.text
        nxt = t[i + 1 : i + 2]
        if nxt == "'" and not in_double:  # $'...' (ANSI-C quoting)
            j = i + 2
            while j < self.n and t[j] != "'":
                j += 2 if t[j] == "\\" else 1
            if j >= self.n:
                raise LexError("unterminated $'...'")
            self.add(t[i + 2 : j], quoted=True)
            return j + 1
        if nxt == '"' and not in_double:  # $"..." (locale string)
            return self.double_quoted(i + 2)
        if nxt == "(":
            j = self.paren_end(i + 2)
            if t.startswith("((", i + 1):  # $(( arithmetic ))
                self.add("0")
            else:
                self.subs.append(t[i + 2 : j])
                self.add(SUBST)
            return j + 1
        if nxt == "{":
            j = t.find("}", i + 2)
            if j < 0:
                raise LexError("unterminated ${")
            self.add(EXPAND + t[i + 1 : j + 1])
            return j + 1
        self.add(EXPAND)
        return i + 1

    def double_quoted(self, i: int) -> int:
        t = self.text
        self.add("", quoted=True)
        while i < self.n:
            c = t[i]
            if c == '"':
                return i + 1
            if c == "\\" and i + 1 < self.n:
                if t[i + 1] == "\n":
                    i += 2
                elif t[i + 1] in '"\\$`':
                    self.add(t[i + 1])
                    i += 2
                else:
                    self.add(c)
                    i += 1
            elif c == "$":
                i = self.dollar(i, in_double=True)
            elif c == "`":
                j = self.backtick_end(i + 1)
                self.subs.append(t[i + 1 : j].replace("\\`", "`"))
                self.add(SUBST)
                i = j + 1
            else:
                self.add(c)
                i += 1
        raise LexError("unterminated double quote")

    def backtick_end(self, i: int) -> int:
        t = self.text
        while i < self.n:
            if t[i] == "\\":
                i += 2
            elif t[i] == "`":
                return i
            else:
                i += 1
        raise LexError("unterminated backquote")

    def paren_end(self, i: int) -> int:
        """Index of the `)` closing the `(` just before i (quotes, nesting, here-documents)."""
        t, depth = self.text, 1
        pending: list[tuple[str, bool]] = []  # here-documents opened on the current line
        while i < self.n:
            c = t[i]
            if c == "\\":
                i += 2
                continue
            if c == "\n" and pending:  # a here-document body is data (`it's` is no quote)
                saved, self.heredocs = self.heredocs, pending
                i = self.skip_heredocs(i + 1)
                self.heredocs, pending = saved, []
                continue
            if t.startswith("<<", i) and not t.startswith("<<<", i):
                strip = t.startswith("<<-", i)
                m = HEREDOC_WORD.match(t, i + (3 if strip else 2))
                if m:
                    pending.append((re.sub(r"[\\'\"]", "", m.group(1)), strip))
                    i = m.end()
                    continue
            if c in "'\"":
                j = i + 1
                while j < self.n and t[j] != c:
                    j += 2 if (c == '"' and t[j] == "\\") else 1
                if j >= self.n:
                    raise LexError("unterminated quote in substitution")
                i = j + 1
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise LexError("unterminated substitution")

    def skip_heredocs(self, i: int) -> int:
        t = self.text
        for delim, strip_tabs in self.heredocs:
            while i < self.n:
                j = t.find("\n", i)
                line = t[i:] if j < 0 else t[i:j]
                i = self.n if j < 0 else j + 1
                if (line.lstrip("\t") if strip_tabs else line).rstrip("\r") == delim:
                    break
        self.heredocs.clear()
        return i


def fallback_tokens(text: str) -> list[tuple[str, str]]:
    """Whitespace tokens for a line the lexer rejects (bash would reject it too)."""
    tokens: list[tuple[str, str]] = []
    for line in text.splitlines():
        for word in line.split():
            tokens.append(("op", word) if word in OPERATORS else ("word", word.strip("'\"")))
        tokens.append(("op", "\n"))
    return tokens


def could_be(name: str, pattern: str) -> bool:
    """True when the path component `pattern` (literal or glob) can name `name`."""
    return fnmatch.fnmatchcase(name, pattern)


def path_level(path: str, root: str | None) -> int:
    """RAW inside a raw directory; ANCESTOR for a directory of `root` that holds raw data."""
    if RAW_PATTERN.search(path):
        return RAW
    parts = [p for p in path.split("/") if p and p != "."]
    for i, part in enumerate(parts[:-3]):
        if part == "projects" and could_be("data", parts[i + 2]) and could_be("raw", parts[i + 3]):
            return RAW
    if not root or not path.startswith("/"):
        return NONE
    root_parts = [p for p in root.split("/") if p]
    # zip() without strict= (Python 3.10+): it stops at the shorter list, which is intended here.
    if not all(could_be(r, p) for r, p in zip(root_parts, parts)):  # noqa: B905
        return NONE
    if len(parts) <= len(root_parts):
        return ANCESTOR  # the repository itself or a directory above it
    rel = parts[len(root_parts) :]
    if not could_be("projects", rel[0]):
        return NONE
    if len(rel) <= 2 or (len(rel) == 3 and could_be("data", rel[2])):
        return ANCESTOR
    if could_be("data", rel[2]) and could_be("raw", rel[3]):
        return RAW
    return NONE


def split_args(args, short_values="", long_values=EMPTY):
    """GNU-style option parsing: (operands, {option: [values]})."""
    operands: list[str] = []
    options: dict[str, list[str]] = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            operands.extend(args[i + 1 :])
            break
        if a.startswith("--"):
            name, eq, value = a.partition("=")
            if not eq and name in long_values and i + 1 < len(args):
                value = args[i + 1]
                i += 1
            options.setdefault(name, []).append(value)
        elif a.startswith("-") and len(a) > 1:
            for k, ch in enumerate(a[1:], 1):
                if ch in short_values:
                    value = a[k + 1 :]
                    if not value and i + 1 < len(args):
                        value = args[i + 1]
                        i += 1
                    options.setdefault("-" + ch, []).append(value)
                    break
                options.setdefault("-" + ch, []).append("")
        else:
            operands.append(a)
        i += 1
    return operands, options


def first_operand(args, short_values="", long_values=EMPTY) -> int:
    """Index of the first non-option argument (where a wrapped command starts)."""
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            return i + 1
        if a.startswith("--"):
            name, eq, _ = a.partition("=")
            i += 2 if (not eq and name in long_values) else 1
        elif a.startswith("-") and len(a) > 1:
            k = next((k for k, ch in enumerate(a[1:], 1) if ch in short_values), None)
            i += 2 if (k is not None and k == len(a) - 1) else 1
        else:
            return i
    return i


def in_place(name: str, args) -> bool:
    """sed -i / perl -i (with or without a backup suffix) edit their files in place."""
    for a in args:
        if a == "--" or not a.startswith("-"):
            continue
        if a.startswith("--"):
            if name == "sed" and a.startswith("--in-place"):
                return True
            continue
        stop = "efl" if name == "sed" else "eE"
        for ch in a[1:]:
            if ch in stop:
                break
            if ch == "i":
                return True
    return False


def compressor_writes(args) -> bool:
    """gzip-style tools replace or add files next to their input unless -c/-t/-l is given."""
    for a in args:
        if a in ("--stdout", "--to-stdout", "--test", "--list", "--help", "--version"):
            return False
        if a.startswith("-") and not a.startswith("--") and set(a[1:]) & set("ctlhV"):
            return False
    return True


class Shell:
    """Walks the tokens of one command line and records the raw write targets it finds."""

    def __init__(self, cwd: str, root: str | None, depth: int = 0, variables=None):
        self.cwd_stack = [cwd]
        self.dirstack: list[str] = []
        self.root = root
        self.real_root = os.path.realpath(root) if root else None
        self.depth = depth
        self.vars: dict[str, str] = dict(variables or {})
        self.reasons: list[str] = []
        self.pipe_raw = False

    @property
    def cwd(self) -> str:
        return self.cwd_stack[-1]

    # --- entry points ------------------------------------------------------------------------
    def run(self, text: str) -> list[str]:
        try:
            tokens, subs = Lexer(text).run()
        except LexError:
            tokens, subs = fallback_tokens(text), []
        for sub in subs:
            self.recurse(sub)
        self.walk(tokens)
        return self.reasons

    def recurse(self, text: str) -> None:
        if self.depth < MAX_DEPTH:
            inner = Shell(self.cwd, self.root, self.depth + 1, self.vars)
            self.reasons.extend(inner.run(text))

    def walk(self, tokens) -> None:
        words: list[str] = []
        redirects: list[tuple[str, str]] = []
        pending = None
        for kind, text in tokens:
            if kind == "word":
                if pending:
                    redirects.append((pending, text))
                    pending = None
                else:
                    words.append(text)
                continue
            if text in WRITE_REDIRECTS or text in READ_REDIRECTS:
                pending = text
                continue
            self.finish(words, redirects)
            words, redirects, pending = [], [], None
            if text == "(":
                self.cwd_stack.append(self.cwd)
            elif text == ")" and len(self.cwd_stack) > 1:
                self.cwd_stack.pop()
            if text in LIST_SEPARATORS:
                self.pipe_raw = False
        self.finish(words, redirects)

    def finish(self, words, redirects) -> None:
        for op, target in redirects:
            target = self.expand(target)
            if op in WRITE_REDIRECTS:
                if not (op == ">&" and (target.isdigit() or target == "-")):
                    self.target(target, f"redirection {op}")
            elif op in ("<", "<&") and self.level(target) == RAW:
                self.pipe_raw = True
        if words:
            self.command([self.expand(w) for w in words])

    # --- paths -------------------------------------------------------------------------------
    def expand(self, word: str) -> str:
        if EXPAND not in word:
            return word

        def value(match: re.Match) -> str:
            name = match.group(1) or match.group(2)
            if name in self.vars:
                return self.vars[name]
            if name == "PWD" and self.cwd:
                return self.cwd
            if name in ("HOME", "CLAUDE_PROJECT_DIR") and os.environ.get(name):
                return os.environ[name]
            return "$" + name

        return EXPANSION.sub(value, word).replace(EXPAND, "$")

    def resolve(self, word: str) -> str:
        word = word.replace("\\", "/")
        if not word.startswith("/") and self.cwd:
            word = posixpath.join(self.cwd, word)
        return posixpath.normpath(word)

    def level(self, word: str) -> int:
        if not word or word == "-":
            return NONE
        path = self.resolve(word)
        level = path_level(path, self.root)
        if level < RAW and path.startswith("/") and not set(path) & set("*?[" + SUBST):
            level = max(level, path_level(os.path.realpath(path), self.real_root))
        return level

    def target(self, word: str, what: str, *, ancestors: bool = False) -> None:
        level = self.level(word)
        if level == RAW or (ancestors and level == ANCESTOR):
            shown = word.replace(SUBST, "$(...)")
            note = "" if level == RAW else " (a directory that holds raw data)"
            self.reasons.append(f"{what}: {shown}{note}")

    def landing(self, dest: str, sources, what: str, *, contents: bool = False) -> None:
        """`cp -r x/raw projects/s/data/` writes into raw although the destination is not raw."""
        if self.level(dest) == RAW:
            return  # already reported for the destination itself
        for source in sources:
            base = posixpath.basename(source.rstrip("/"))
            if base and base not in (".", "..") and not (contents and source.endswith("/")):
                self.target(posixpath.join(dest, base), what)

    def mentions_raw(self, args) -> bool:
        return self.level(".") == RAW or any(
            self.level(a) == RAW for a in args if not a.startswith("-")
        )

    # --- commands ----------------------------------------------------------------------------
    def command(self, words) -> None:
        i = 0
        while i < len(words) and ASSIGNMENT.match(words[i]):
            i += 1
        if i == len(words):
            self.assign(words)
            return
        words = words[i:]
        while words and words[0] in KEYWORDS:
            words = words[1:]
        if not words:
            return
        if words[0] in ("for", "select"):
            self.loop_variable(words[1:])
            return
        unwrapped = self.unwrap(posixpath.basename(words[0]), words[1:])
        if unwrapped is None:
            return
        name, args = unwrapped
        handler = HANDLERS.get(name)
        if handler:
            handler(self, name, args)
        elif name in ANY_PATH:
            for operand in split_args(args)[0]:
                self.target(operand, name)
        if self.mentions_raw(args):
            self.pipe_raw = True

    def unwrap(self, name: str, args):
        """Strip sudo/env/timeout/... and leading NAME=value words: (command, args) or None."""
        while name in WRAPPERS:
            short, long_, extra = WRAPPERS[name]
            if name == "command" and any(a in ("-v", "-V") for a in args[:1]):
                return None
            start = first_operand(args, short, long_)
            if name == "env":
                while start < len(args) and (args[start] == "-" or ASSIGNMENT.match(args[start])):
                    start += 1
            start += extra
            if start >= len(args):
                return None
            name, args = posixpath.basename(args[start]), args[start + 1 :]
        return name, args

    def assign(self, words) -> None:
        for word in words:
            if ASSIGNMENT.match(word):
                name, _, value = word.partition("=")
                self.vars[name] = value

    def loop_variable(self, args) -> None:
        if len(args) >= 2 and args[1] == "in" and args[2:]:
            items = args[2:]
            self.vars[args[0]] = next((w for w in items if self.level(w) == RAW), items[0])

    def h_assign(self, name, args) -> None:
        self.assign(args)

    def h_read(self, name, args) -> None:
        if self.pipe_raw:
            for var in split_args(args, "adnNpstu")[0]:
                self.vars[var] = PIPED_RAW

    def h_shell(self, name, args) -> None:
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
                i += 2
            elif a.startswith(("-", "+")) and a != "--":
                if not a.startswith("--") and "c" in a[1:]:
                    if i + 1 < len(args):
                        self.recurse(args[i + 1])
                    return
                i += 1
            else:
                return  # a script file: not inspected

    def h_eval(self, name, args) -> None:
        self.recurse(" ".join(args))

    def h_cd(self, name, args) -> None:
        if name == "popd":
            self.cwd_stack[-1] = self.dirstack.pop() if self.dirstack else ""
            return
        if name == "pushd":
            self.dirstack.append(self.cwd)
        operands = [a for a in args if a == "-" or not a.startswith("-")]
        if not operands:
            self.cwd_stack[-1] = os.environ.get("HOME", "")
        elif operands[-1] == "-":
            self.cwd_stack[-1] = ""
        else:
            self.cwd_stack[-1] = self.resolve(operands[-1])

    def h_copy(self, name, args) -> None:
        short, long_ = COPY_SPECS[name]
        operands, opts = split_args(args, short, long_)
        if name == "install" and ("-d" in opts or "--directory" in opts):
            for operand in operands:
                self.target(operand, "install -d")
            return
        if name == "rsync":
            for opt in RSYNC_WRITE_OPTIONS:
                for value in opts.get(opt, []):
                    self.target(value, f"rsync {opt}")
        dests = opts.get("-t", []) + opts.get("--target-directory", [])
        sources = operands
        if not dests:
            if len(operands) >= 2:
                dests, sources = [operands[-1]], operands[:-1]
            elif name == "ln" and operands:
                dests = ["."]
            else:
                return
        for dest in dests:
            if name in ("rsync", "scp") and re.match(r"^[^/]*:", dest):
                continue  # remote destination
            self.target(dest, f"{name} destination")
            self.landing(dest, sources, f"{name} destination", contents=name == "rsync")
            if name == "rsync" and any(o.startswith("--del") for o in opts):
                self.target(dest, "rsync --delete", ancestors=True)
        if name == "rsync" and "--remove-source-files" in opts:
            for source in sources:
                self.target(source, "rsync --remove-source-files")

    def h_mv(self, name, args) -> None:
        operands, opts = split_args(args, "tS", {"--target-directory", "--suffix"})
        dests = opts.get("-t", []) + opts.get("--target-directory", [])
        for path in operands + dests:
            self.target(path, "mv", ancestors=True)
        if not dests and len(operands) >= 2:
            dests, operands = [operands[-1]], operands[:-1]
        for dest in dests:
            self.landing(dest, operands, "mv destination")

    def h_rm(self, name, args) -> None:
        operands, opts = split_args(args)
        recursive = any(o in opts for o in ("-r", "-R", "--recursive"))
        for operand in operands:
            self.target(operand, "rm", ancestors=recursive)

    def h_in_place(self, name, args) -> None:
        if in_place(name, args):
            for a in args:
                if not a.startswith("-"):
                    self.target(a, f"{name} -i")

    def h_dd(self, name, args) -> None:
        for a in args:
            if a.startswith("of="):
                self.target(a[3:], "dd of=")

    def h_sort(self, name, args) -> None:
        _, opts = split_args(args, "koStT", SORT_LONG_VALUES)
        for opt in ("-o", "--output", "-T", "--temporary-directory"):
            for value in opts.get(opt, []):
                self.target(value, f"sort {opt}")

    def h_tar(self, name, args) -> None:
        modes: set[str] = set()
        archives: list[str] = []
        dirs: list[str] = []

        def record(opt: str, value: str = "") -> None:
            if opt in ("x", "--extract", "--get"):
                modes.add("x")
            elif opt in ("c", "r", "u", "A", "--create", "--append", "--update", "--catenate",
                         "--concatenate", "--delete"):  # fmt: skip
                modes.add("write-archive")
            elif opt in ("O", "--to-stdout", "--to-command"):
                modes.add("stdout")
            elif opt in ("f", "--file"):
                archives.append(value)
            elif opt in ("C", "--directory"):
                dirs.append(value)

        args = list(args)
        if args and re.fullmatch(r"[A-Za-z]+", args[0]):  # old style: tar xzf a.tar
            bundle, rest, taken = args[0], args[1:], 0
            for ch in bundle:
                if ch in TAR_SHORT_VALUES:
                    record(ch, rest[taken] if taken < len(rest) else "")
                    taken += 1
                else:
                    record(ch)
            args = rest[taken:]
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--":
                break
            if a.startswith("--"):
                opt, eq, value = a.partition("=")
                if not eq and opt in TAR_LONG_VALUES and i + 1 < len(args):
                    value = args[i + 1]
                    i += 1
                record(opt, value)
            elif a.startswith("-") and len(a) > 1:
                for k, ch in enumerate(a[1:], 1):
                    if ch in TAR_SHORT_VALUES:
                        value = a[k + 1 :]
                        if not value and i + 1 < len(args):
                            value = args[i + 1]
                            i += 1
                        record(ch, value)
                        break
                    record(ch)
            i += 1
        if "x" in modes and "stdout" not in modes:
            for directory in dirs or ["."]:
                self.target(directory, "tar -x into")
        if "write-archive" in modes:
            for archive in archives:
                if archive != "-":
                    self.target(archive, "tar archive")

    def h_unzip(self, name, args) -> None:
        dest, listing, i = ".", False, 0
        while i < len(args):
            a = args[i]
            if a.startswith("-") and len(a) > 1:
                for k, ch in enumerate(a[1:], 1):
                    if ch in "ltpvczZ":
                        listing = True
                    if ch in "dP":
                        value = a[k + 1 :]
                        if not value and i + 1 < len(args):
                            value = args[i + 1]
                            i += 1
                        if ch == "d":
                            dest = value
                        break
            i += 1
        if not listing:
            self.target(dest, "unzip into")

    def h_compress(self, name, args) -> None:
        operands, opts = split_args(args, "oS" if name in ("zstd", "unzstd") else "S")
        if opts.get("-o"):
            for value in opts["-o"]:
                self.target(value, f"{name} -o")
        elif compressor_writes(args):
            for operand in operands:
                self.target(operand, f"{name} (rewrites its input)")

    def h_curl(self, name, args) -> None:
        _, opts = split_args(args, CURL_SHORT_VALUES, CURL_LONG_VALUES)
        out_dir = (opts.get("--output-dir") or [""])[-1]
        for opt in ("-o", "--output", "-D", "--dump-header", "-c", "--cookie-jar"):
            for value in opts.get(opt, []):
                if value != "-":
                    self.target(posixpath.join(out_dir, value), f"curl {opt}")
        if any(o in opts for o in ("-O", "--remote-name", "--remote-name-all", "--output-dir")):
            self.target(out_dir or ".", "curl download directory")

    def h_wget(self, name, args) -> None:
        operands, opts = split_args(args, WGET_SHORT_VALUES, WGET_LONG_VALUES)
        documents = opts.get("-O", []) + opts.get("--output-document", [])
        for value in documents:
            if value != "-":
                self.target(value, "wget -O")
        for opt in ("-o", "--output-file", "-a", "--append-output"):
            for value in opts.get(opt, []):
                self.target(value, f"wget {opt}")
        if not documents and (operands or "-i" in opts or "--input-file" in opts):
            prefix = (opts.get("-P", []) + opts.get("--directory-prefix", []) or ["."])[-1]
            self.target(prefix, "wget download directory")

    def h_git(self, name, args) -> None:
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") else 1
        if i >= len(args):
            return
        sub, rest = args[i], args[i + 1 :]
        if sub == "clean":
            for a in rest:
                if a == "--":
                    break
                flags = set(a[1:].split("e")[0]) if a.startswith("-") and a[1:2] != "-" else set()
                if flags & {"x", "X"}:
                    self.reasons.append(f"git clean {a}: removes git-ignored files, raw data too")
        elif sub == "stash" and any(a in ("-a", "--all") for a in rest):
            self.reasons.append("git stash --all: moves git-ignored files (raw data) away")

    def h_find(self, name, args) -> None:
        i = 0
        while i < len(args) and (args[i] in ("-H", "-L", "-P", "-D") or args[i].startswith("-O")):
            i += 2 if args[i] == "-D" else 1
        starts = []
        while i < len(args) and not args[i].startswith("-") and args[i] not in FIND_OPERATORS:
            starts.append(args[i])
            i += 1
        expr, acting, destroys, j = args[i:], False, False, 0
        while j < len(expr):
            a = expr[j]
            if a == "-delete":
                acting = destroys = True
            elif a in ("-exec", "-execdir", "-ok", "-okdir"):
                acting = True
                k = j + 1
                while k < len(expr) and expr[k] not in (";", "+"):
                    k += 1
                if k > j + 1:
                    destroys = destroys or destructive(self, expr[j + 1 : k], shells=True)
                    self.command(expr[j + 1 : k])
                j = k
            elif a in ("-fprint", "-fprint0", "-fprintf", "-fls") and j + 1 < len(expr):
                self.target(expr[j + 1], f"find {a}")
                j += 1
            j += 1
        for start in starts or ["."]:
            level = self.level(start)
            if level == RAW and acting:
                self.reasons.append(f"find {start} with -delete/-exec")
            elif level == ANCESTOR:  # like rm -r of it: the walk reaches data/raw/
                if destroys:
                    self.reasons.append(
                        f"find {start} with -delete/-exec (a directory that holds raw data;"
                        " start find below it, e.g. projects/<study>/experiments/)"
                    )
                self.pipe_raw = True  # what it prints can name raw files (| xargs rm)

    def h_xargs(self, name, args) -> None:
        arg_files: list[str] = []
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--":
                i += 1
                break
            if not a.startswith("-") or a == "-":
                break
            if a.startswith("--"):
                opt, eq, value = a.partition("=")
                if not eq and opt in XARGS_LONG_VALUES and i + 1 < len(args):
                    value = args[i + 1]
                    i += 1
                if opt == "--arg-file":
                    arg_files.append(value)
            else:
                for k, ch in enumerate(a[1:], 1):
                    if ch in "adEILnPs":
                        value = a[k + 1 :]
                        if not value and i + 1 < len(args):
                            value = args[i + 1]
                            i += 1
                        if ch == "a":
                            arg_files.append(value)
                        break
                    if ch in "eil":
                        break  # optional value attached to the option
            i += 1
        sub = args[i:] or ["echo"]
        input_raw = self.pipe_raw or any(self.level(f) == RAW for f in arg_files)
        if input_raw and destructive(self, sub):
            self.reasons.append(f"xargs {sub[0]} on input that lists raw files")
        self.command(sub)


def destructive(shell: Shell, words, *, shells: bool = False) -> bool:
    """True when `words` (run by xargs or find -exec on each file) removes or rewrites files.

    With shells=True a shell, eval or xargs counts too: what it runs on each file is not known.
    """
    unwrapped = shell.unwrap(posixpath.basename(words[0]), words[1:]) if words else None
    if not unwrapped:
        return False
    cmd, args = unwrapped
    return (
        cmd in DESTRUCTIVE
        or (shells and cmd in SHELLS | {"eval", "xargs"})
        or (cmd in ("sed", "perl") and in_place(cmd, args))
        or (cmd in COMPRESSORS and compressor_writes(args))
    )


HANDLERS = {
    **dict.fromkeys(SHELLS, Shell.h_shell),
    **dict.fromkeys(COPY_SPECS, Shell.h_copy),
    **dict.fromkeys(COMPRESSORS, Shell.h_compress),
    **dict.fromkeys(("export", "declare", "typeset", "local", "readonly"), Shell.h_assign),
    "eval": Shell.h_eval,
    "cd": Shell.h_cd,
    "pushd": Shell.h_cd,
    "popd": Shell.h_cd,
    "read": Shell.h_read,
    "mv": Shell.h_mv,
    "rm": Shell.h_rm,
    "sed": Shell.h_in_place,
    "perl": Shell.h_in_place,
    "dd": Shell.h_dd,
    "sort": Shell.h_sort,
    "tar": Shell.h_tar,
    "unzip": Shell.h_unzip,
    "curl": Shell.h_curl,
    "wget": Shell.h_wget,
    "git": Shell.h_git,
    "find": Shell.h_find,
    "xargs": Shell.h_xargs,
}


def raw_file_target(path: str, cwd: str) -> bool:
    """Write/Edit target check (the lexical path, and the path with symlinks resolved)."""
    path = path.replace("\\", "/")
    if RAW_PATTERN.search(path):
        return True
    absolute = os.path.realpath(os.path.join(cwd, path))
    return bool(RAW_PATTERN.search(absolute.replace("\\", "/")))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0  # malformed input: never block unrelated tool calls
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        return 0
    tool_input = payload["tool_input"]
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd.startswith("/"):
        cwd = os.getcwd()
    root = os.environ.get("CLAUDE_PROJECT_DIR") or None
    root = posixpath.normpath(root) if root and root.startswith("/") else None

    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if isinstance(path, str) and path and raw_file_target(path, cwd):
        print(f"BLOCKED: '{path}' is inside a data/raw/ directory. {RAW_STEP}", file=sys.stderr)
        return 2

    command = tool_input.get("command")
    if payload.get("tool_name", "Bash") == "Bash" and isinstance(command, str):
        reasons = list(dict.fromkeys(Shell(posixpath.normpath(cwd), root).run(command)))
        if reasons:
            listed = "\n".join(f"  - {reason}" for reason in reasons[:10])
            print(
                f"BLOCKED: this command writes into a data/raw/ directory:\n{listed}\n{RAW_STEP}",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    try:
        status = main()
    except Exception as error:  # a crash would let the command through (any exit other than 2)
        print(
            f"BLOCKED: the raw-data hook failed ({type(error).__name__}: {error}), so this tool "
            "call could not be checked. Report it; on an old host python3, install 3.10 or newer "
            "(README.md).",
            file=sys.stderr,
        )
        status = 2
    sys.exit(status)
