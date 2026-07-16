#!/usr/bin/env python3
"""Fail when tracked content is unsafe for a public repository."""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_TRACKED_BYTES = 1_000_000

FORBIDDEN_SUFFIXES = {".pem", ".p12", ".pfx", ".kdbx", ".sqlite"}
FORBIDDEN_NAMES = {".env", "credentials", "credentials.json", "zotero.sqlite"}
ALLOWED_ENV_FILES = {".env.example"}

SECRET_PATTERNS = {
    "GitHub token": re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    "GitHub fine-grained token": re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "OpenAI-style secret": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE " r"KEY-----"),
}

USE_ACTION = re.compile(r"^\s*-?\s*uses:\s*[^#\s]+@([^#\s]+)", re.MULTILINE)
PINNED_ACTION = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Finding:
    path: str
    message: str


def tracked_files(root: Path = REPO_ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [root / os.fsdecode(item) for item in result.stdout.split(b"\0") if item]


def forbidden_path_reason(path: Path, root: Path) -> str | None:
    relative = path.relative_to(root)
    posix = relative.as_posix()
    if path.name in FORBIDDEN_NAMES and path.name not in ALLOWED_ENV_FILES:
        return "application state or credentials must not be tracked"
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f"{path.suffix} application/credential file must not be tracked"
    if posix.startswith("references/attachments/") or posix.startswith("references/library/"):
        return "literature attachments must remain outside Git"
    if re.match(r"^projects/[^/]+/data/raw/.+", posix) and path.name != ".gitkeep":
        return "raw research data must not be tracked"
    return None


def scan_files(paths: list[Path], root: Path = REPO_ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        reason = forbidden_path_reason(path, root)
        if reason:
            findings.append(Finding(relative, reason))

        if path.is_symlink():
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                findings.append(Finding(relative, "tracked symlink points outside the repository"))
            continue
        if not path.is_file():
            continue
        if path.stat().st_size > MAX_TRACKED_BYTES:
            findings.append(
                Finding(relative, f"tracked file exceeds {MAX_TRACKED_BYTES // 1_000_000} MB")
            )

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(Finding(relative, f"possible {label}"))

        if relative.startswith(".github/workflows/") and path.suffix in {".yml", ".yaml"}:
            for match in USE_ACTION.finditer(text):
                ref = match.group(1)
                if not PINNED_ACTION.fullmatch(ref):
                    findings.append(
                        Finding(relative, f"GitHub Action is not pinned to a full SHA: @{ref}")
                    )
    return findings


def history_emails(root: Path = REPO_ROOT) -> list[Finding]:
    result = subprocess.run(
        ["git", "log", "--all", "--format=%H%x00%ae"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    findings: list[Finding] = []
    for raw in result.stdout.splitlines():
        commit, _, email = raw.partition("\0")
        if email and not email.endswith("@users.noreply.github.com"):
            findings.append(Finding(commit[:12], f"commit author email is public: {email}"))
    return findings


def print_findings(findings: list[Finding]) -> int:
    if not findings:
        print("Public repository check: OK")
        return 0
    print("Public repository check: FAILED", file=sys.stderr)
    for finding in findings:
        print(f"- {finding.path}: {finding.message}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        action="store_true",
        help="also fail on commit author emails that are not GitHub noreply addresses",
    )
    args = parser.parse_args(argv)

    findings = scan_files(tracked_files())
    if args.history:
        findings.extend(history_emails())
    return print_findings(findings)


if __name__ == "__main__":
    raise SystemExit(main())
