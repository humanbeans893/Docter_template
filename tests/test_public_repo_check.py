"""Tests for the public repository safety gate."""


def test_detects_secret_and_large_file(tmp_path, load_module_by_path, repo_root):
    checker = load_module_by_path(
        repo_root / "tools" / "public_repo_check.py", "public_repo_check_under_test"
    )
    secret = tmp_path / "notes.txt"
    secret.write_text("token = " + "ghp_" + "abcdefghijklmnopqrstuvwxyz123456")
    large = tmp_path / "large.bin"
    large.write_bytes(b"x" * (checker.MAX_TRACKED_BYTES + 1))

    findings = checker.scan_files([secret, large], root=tmp_path)

    messages = {finding.message for finding in findings}
    assert "possible GitHub token" in messages
    assert any("exceeds" in message for message in messages)


def test_requires_sha_pinned_actions(tmp_path, load_module_by_path, repo_root):
    checker = load_module_by_path(
        repo_root / "tools" / "public_repo_check.py", "public_repo_check_actions_test"
    )
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


def test_rejects_external_symlink(tmp_path, load_module_by_path, repo_root):
    checker = load_module_by_path(
        repo_root / "tools" / "public_repo_check.py", "public_repo_check_symlink_test"
    )
    external = tmp_path.parent / "external-literature"
    external.mkdir(exist_ok=True)
    link = tmp_path / "literature"
    link.symlink_to(external, target_is_directory=True)

    findings = checker.scan_files([link], root=tmp_path)

    assert any("outside" in finding.message for finding in findings)
