"""Tests for the public repository safety gate."""

import pytest

# Built by concatenation so this file itself never contains a real-looking home path.
HOME = "/" + "home/"
USERS = "/" + "Users/"
WSL_USERS = "/mnt/c" + USERS
WINDOWS_USERS = "C:" + "\\" + "Users" + "\\"
DRIVE_USERS = "D:/" + "Users/"


@pytest.fixture(scope="module")
def checker(repo_root, load_module_by_path):
    return load_module_by_path(
        repo_root / "tools" / "public_repo_check.py", "public_repo_check_under_test"
    )


def test_detects_secret_and_large_file(tmp_path, checker):
    secret = tmp_path / "notes.txt"
    secret.write_text("token = " + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456")
    large = tmp_path / "large.bin"
    large.write_bytes(b"x" * (checker.MAX_TRACKED_BYTES + 1))

    findings = checker.scan_files([secret, large], root=tmp_path)

    messages = {finding.message for finding in findings}
    assert "possible GitHub token" in messages
    assert any("exceeds" in message for message in messages)


def test_requires_sha_pinned_actions(tmp_path, checker):
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = workflow_dir / "ci.yml"
    workflow.write_text(
        "steps:\n"
        "  - uses: actions/checkout@v4\n"
        "  - uses: owner/action@0123456789abcdef0123456789abcdef01234567\n"
    )

    findings = checker.scan_files([workflow], root=tmp_path)

    assert len(findings) == 1
    assert "@v4" in findings[0].message


def test_rejects_external_symlink(tmp_path, checker):
    external = tmp_path.parent / "external-literature"
    external.mkdir(exist_ok=True)
    link = tmp_path / "literature"
    link.symlink_to(external, target_is_directory=True)

    findings = checker.scan_files([link], root=tmp_path)

    assert any("outside" in finding.message for finding in findings)


@pytest.mark.parametrize("name", [".codex/config.toml", "sub/.codex/config.toml"])
def test_rejects_codex_project_settings(tmp_path, checker, name):
    path = tmp_path / name
    path.parent.mkdir(parents=True)
    path.write_text('model = "x"\n')

    findings = checker.scan_files([path], root=tmp_path)

    assert any("Codex" in finding.message for finding in findings)


def test_flags_local_home_paths(tmp_path, checker):
    notes = tmp_path / "notes.md"
    notes.write_text(
        f"data in {HOME}someone/thesis/raw\n"
        f'cfg = "{USERS}Alice/Library/x"\n'
        f"see file://{HOME}bob/a.txt\n",
        encoding="utf-8",
    )

    findings = checker.scan_files([notes], root=tmp_path)

    flagged = sorted(finding.message for finding in findings)
    assert len(flagged) == 3
    assert any("someone/" in message and "line 1" in message for message in flagged)
    assert any("Alice/" in message and "line 2" in message for message in flagged)
    assert any("bob/" in message and "line 3" in message for message in flagged)


def test_flags_windows_and_wsl_user_paths(tmp_path, checker):
    notes = tmp_path / "README.md"
    notes.write_text(
        f"元の場所: {WSL_USERS}taro/Documents/old-thesis/results/\n"
        f"or {WINDOWS_USERS}taro\\Documents\\old-thesis\n"
        f"or {DRIVE_USERS}hanako/old\n",
        encoding="utf-8",
    )
    sidecar = tmp_path / "fig1.provenance.json"
    escaped = WINDOWS_USERS.replace("\\", "\\\\")
    sidecar.write_text(f'{{"sources": ["{escaped}jiro\\\\old\\\\a.csv"]}}\n', encoding="utf-8")

    findings = checker.scan_files([notes, sidecar], root=tmp_path)

    flagged = sorted(f"{finding.path} {finding.message}" for finding in findings)
    assert len(flagged) == 4, flagged
    assert any("taro/" in message and "line 1" in message for message in flagged)
    assert any("taro\\" in message and "line 2" in message for message in flagged)
    assert any("hanako/" in message and "line 3" in message for message in flagged)
    assert any(
        message.startswith("fig1.provenance.json") and "jiro" in message for message in flagged
    )


def test_allows_container_home_urls_and_placeholders(tmp_path, checker):
    notes = tmp_path / "notes.md"
    notes.write_text(
        f"HOME: {HOME}app\nMPLCONFIGDIR: {HOME}app/.cache/matplotlib\n"
        f"https://example.org{HOME}someone/page\n"
        f"copy from {HOME}<user>/old-repo or <PATH>\n"
        f"~{HOME}x/ is relative\n"
        f"https://example.org/mnt/c{USERS}someone/page\n"
        f"{WSL_USERS}<user>/old-repo and {WINDOWS_USERS}<user>\\old-repo\n",
        encoding="utf-8",
    )

    assert checker.scan_files([notes], root=tmp_path) == []
