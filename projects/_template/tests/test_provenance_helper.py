"""Tests for src/utils/provenance.py (manifest parsing, input verification, crosscheck)."""

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def write_tree(root, files):
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def write_manifest(path, root, names):
    """Write a manifest the way `find . -type f | sort | xargs sha256sum` does."""
    lines = [
        f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  ./{name}" for name in names
    ]
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture()
def legacy(tmp_path):
    root = tmp_path / "raw" / "legacy" / "old-run"
    write_tree(root, {"metrics.csv": b"a,b\n1,2\n", "figs/map.png": b"png", ".gitkeep": b""})
    manifest = tmp_path / "experiments" / "001_old_run" / "inputs.sha256"
    manifest.parent.mkdir(parents=True)
    write_manifest(manifest, root, ["figs/map.png", "metrics.csv"])
    return root, manifest


def test_sha256_file_known_value(provenance_mod, tmp_path):
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    abc = tmp_path / "abc"
    abc.write_bytes(b"abc")

    assert provenance_mod.sha256_file(empty) == EMPTY_SHA256
    assert provenance_mod.sha256_file(abc) == hashlib.sha256(b"abc").hexdigest()


def test_read_manifest_text_binary_and_escaped_forms(provenance_mod, tmp_path):
    a, b, c = "A" * 64, "b" * 64, "c" * 64
    manifest = tmp_path / "inputs.sha256"
    manifest.write_text(f"{a}  ./x/one.csv\n{b} *two.bin\n\\{c}  dir\\\\back\\nslash.txt\n\n")

    assert provenance_mod.read_sha256_manifest(manifest) == {
        "x/one.csv": a.lower(),
        "two.bin": b,
        "dir\\back\nslash.txt": c,
    }


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("abc  file.csv\n", "not a sha256sum line"),
        (f"{'a' * 64} file.csv\n", "not a sha256sum line"),
        (f"{'a' * 64}  a.csv\n{'b' * 64}  ./a.csv\n", "listed twice"),
        (f"{'a' * 64}  -\n", "standard input"),
    ],
)
def test_read_manifest_rejects_malformed_lines(provenance_mod, tmp_path, content, message):
    manifest = tmp_path / "inputs.sha256"
    manifest.write_text(content)
    with pytest.raises(AssertionError, match=message):
        provenance_mod.read_sha256_manifest(manifest)


def test_verify_inputs_accepts_a_nested_tree(provenance_mod, legacy):
    root, manifest = legacy

    verified = provenance_mod.verify_inputs(root, manifest)

    assert verified == {
        "metrics.csv": hashlib.sha256(b"a,b\n1,2\n").hexdigest(),
        "figs/map.png": hashlib.sha256(b"png").hexdigest(),
    }


def test_verify_inputs_requires_a_manifest(provenance_mod, legacy, tmp_path):
    root, manifest = legacy
    with pytest.raises(AssertionError, match="generate the manifest with") as missing:
        provenance_mod.verify_inputs(root, tmp_path / "none.sha256")
    assert "sha256sum" in str(missing.value)

    manifest.write_text("")
    with pytest.raises(AssertionError, match="is empty"):
        provenance_mod.verify_inputs(root, manifest)


def test_verify_inputs_requires_the_directory(provenance_mod, legacy, tmp_path, monkeypatch):
    _root, manifest = legacy
    monkeypatch.chdir(tmp_path)  # the repository root: the user copies the files on the host
    with pytest.raises(AssertionError, match="not a directory: copy the past files there"):
        provenance_mod.verify_inputs(tmp_path / "nowhere", manifest)

    # Outside the repository only the /external mount reaches it: say how to mount it.
    monkeypatch.chdir(tmp_path / "experiments")
    with pytest.raises(AssertionError, match="not a directory: outside the repository") as excinfo:
        provenance_mod.verify_inputs(tmp_path / "nowhere", manifest)
    assert "COMPOSE_FILE" in str(excinfo.value)
    assert "EXTERNAL_FILES_DIR" in str(excinfo.value)


def test_verify_inputs_reports_missing_and_unregistered_files(provenance_mod, legacy):
    root, manifest = legacy
    (root / "metrics.csv").unlink()
    (root / "figs" / "extra.png").write_bytes(b"new")

    with pytest.raises(AssertionError, match="missing") as excinfo:
        provenance_mod.verify_inputs(root, manifest)
    assert "metrics.csv" in str(excinfo.value) and "figs/extra.png" in str(excinfo.value)


def test_verify_inputs_detects_changed_content(provenance_mod, legacy):
    root, manifest = legacy
    (root / "metrics.csv").write_bytes(b"a,b\n1,3\n")

    with pytest.raises(AssertionError, match="sha256 differs"):
        provenance_mod.verify_inputs(root, manifest)


def test_verify_inputs_rejects_paths_outside_the_directory(provenance_mod, legacy):
    root, manifest = legacy
    manifest.write_text(f"{'a' * 64}  ../escape.csv\n")

    with pytest.raises(AssertionError, match="outside"):
        provenance_mod.verify_inputs(root, manifest)


def test_verify_inputs_checks_hashes_the_old_tool_recorded(provenance_mod, legacy):
    root, manifest = legacy
    good = hashlib.sha256(b"png").hexdigest()

    provenance_mod.verify_inputs(root, manifest, recorded={"./figs/map.png": good.upper()})
    with pytest.raises(AssertionError, match="old record"):
        provenance_mod.verify_inputs(root, manifest, recorded={"metrics.csv": "0" * 64})
    with pytest.raises(AssertionError, match="not in the manifest") as excinfo:
        provenance_mod.verify_inputs(root, manifest, recorded={"gone.csv": good})
    # A hash of input data (e.g. run_meta.json's ocean_data_sha256) belongs in the ledger.
    assert "data/README.md" in str(excinfo.value)


def test_verify_inputs_cache_skips_rehashing_until_files_change(
    provenance_mod, legacy, tmp_path, monkeypatch
):
    root, manifest = legacy
    cache = tmp_path / "out" / "inputs_verified.json"
    provenance_mod.verify_inputs(root, manifest, cache=cache)
    record = json.loads(cache.read_text())
    assert set(record) == {"directory", "manifest", "manifest_sha256", "files", "verified_at"}
    assert set(record["files"]["metrics.csv"]) == {"sha256", "size", "mtime_ns"}

    hashed = []
    real = provenance_mod.sha256_file
    monkeypatch.setattr(
        provenance_mod, "sha256_file", lambda path: hashed.append(path.name) or real(path)
    )
    provenance_mod.verify_inputs(root, manifest, cache=cache)
    assert hashed == ["inputs.sha256"]  # only the manifest itself

    changed = root / "metrics.csv"
    changed.write_bytes(b"a,b\n9,9\n")  # same size; move mtime past the clock granularity
    mtime_ns = record["files"]["metrics.csv"]["mtime_ns"] + 1_000_000_000
    os.utime(changed, ns=(mtime_ns, mtime_ns))
    with pytest.raises(AssertionError, match="sha256 differs"):
        provenance_mod.verify_inputs(root, manifest, cache=cache)


def test_the_verification_cache_is_written_whole(provenance_mod, legacy, tmp_path, monkeypatch):
    # The import template keeps the cache in data/interim/NNN_<slug>/, which full and smoke
    # runs share: it is created on first use and replaced in one step, never half-written.
    root, manifest = legacy
    cache = tmp_path / "data" / "interim" / "001_old_run" / "inputs_verified.json"

    provenance_mod.verify_inputs(root, manifest, cache=cache)
    assert json.loads(cache.read_text())["manifest_sha256"] == provenance_mod.sha256_file(manifest)
    assert sorted(p.name for p in cache.parent.iterdir()) == ["inputs_verified.json"]

    cache.write_text("{}")  # a stale cache is rewritten whole
    replaced = []
    real = provenance_mod.os.replace
    monkeypatch.setattr(
        provenance_mod.os,
        "replace",
        lambda src, dst: replaced.append(Path(src).name) or real(src, dst),
    )
    provenance_mod.verify_inputs(root, manifest, cache=cache)
    assert replaced == [f".inputs_verified.json.{os.getpid()}.part"]
    assert set(json.loads(cache.read_text())["files"]) == {"figs/map.png", "metrics.csv"}
    assert sorted(p.name for p in cache.parent.iterdir()) == ["inputs_verified.json"]


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="GNU coreutils not installed")
def test_printed_manifest_command_matches_the_reader(provenance_mod, legacy, tmp_path, monkeypatch):
    root, _manifest = legacy
    (root / "name with space.txt").write_bytes(b"x")
    generated = tmp_path / "experiments" / "generated.sha256"
    monkeypatch.chdir(tmp_path)  # the command shows paths relative to the repository root

    command = provenance_mod.manifest_command(root, generated)
    assert command.startswith("(cd raw/legacy/old-run && find . -type f ! -name .gitkeep")
    assert command.endswith("> experiments/generated.sha256")
    subprocess.run(["bash", "-c", command], check=True, cwd=tmp_path)

    assert provenance_mod.verify_inputs(root, generated) == {
        "figs/map.png": hashlib.sha256(b"png").hexdigest(),
        "metrics.csv": hashlib.sha256(b"a,b\n1,2\n").hexdigest(),
        "name with space.txt": hashlib.sha256(b"x").hexdigest(),
    }


def test_source_entry_is_repo_relative(provenance_mod, tmp_path):
    data = tmp_path / "projects" / "demo" / "data" / "raw" / "a.csv"
    data.parent.mkdir(parents=True)
    data.write_bytes(b"1")
    cfg = SimpleNamespace(REPO_ROOT=tmp_path)

    assert provenance_mod.source_entry(data, cfg) == {
        "path": "projects/demo/data/raw/a.csv",
        "sha256": hashlib.sha256(b"1").hexdigest(),
    }
    assert provenance_mod.source_entry(data, cfg, sha256="F" * 64)["sha256"] == "f" * 64


def test_crosscheck_returns_rows_within_tolerance(provenance_mod):
    reference = {
        "rmse": {"value": 0.42, "atol": 0.005, "source": "old README"},
        "n": {"value": 120, "source": "smith2024ocean, Table 2"},
        "bias": {"value": -1.0, "rtol": 0.01, "source": "archived metrics.csv"},
    }

    rows = provenance_mod.crosscheck({"rmse": 0.4231, "n": 120, "bias": -1.009}, reference)

    assert [row["key"] for row in rows] == ["bias", "n", "rmse"]
    assert all(row["ok"] for row in rows)
    assert set(rows[0]) == {
        "key",
        "actual",
        "reference",
        "abs_diff",
        "rtol",
        "atol",
        "source",
        "ok",
    }


def test_crosscheck_lists_every_failure(provenance_mod):
    reference = {
        "a": {"value": 1.0, "source": "s"},
        "b": {"value": 2.0, "atol": 0.1, "source": "s"},
        "c": {"value": 3.0, "source": "s"},
    }

    with pytest.raises(AssertionError) as excinfo:
        provenance_mod.crosscheck({"a": 1.0, "b": 2.5, "x": 0.0}, reference)

    message = str(excinfo.value)
    assert "b: 2.5 vs 2.0" in message and "c: no regenerated value" in message
    assert "a:" not in message


@pytest.mark.parametrize(
    "reference",
    [
        {},
        {"a": {"value": 1.0}},
        {"a": {"value": 1.0, "source": "s", "tol": 0.1}},
        {"a": {"value": "1.0", "source": "s"}},
        {"a": {"value": 1.0, "source": "s", "rtol": -1}},
    ],
)
def test_crosscheck_rejects_malformed_references(provenance_mod, reference):
    with pytest.raises(AssertionError):
        provenance_mod.crosscheck({"a": 1.0}, reference)


def test_a_manifest_with_non_utf8_names_says_how_to_fix_them(provenance_mod, tmp_path):
    # 'テスト.csv' in CP932, as unzipped from an archive made on Japanese Windows.
    manifest = tmp_path / "inputs.sha256"
    manifest.write_bytes(
        f"{'a' * 64}  ./ok.csv\n{'b' * 64}  ./".encode() + b"\x83e\x83X\x83g.csv\n"
    )

    with pytest.raises(AssertionError, match="not UTF-8") as excinfo:
        provenance_mod.read_sha256_manifest(manifest)
    assert f"{manifest}:2:" in str(excinfo.value) and "convmv" in str(excinfo.value)


@pytest.mark.skipif(os.name != "posix", reason="needs byte file names")
def test_verify_inputs_reports_non_utf8_file_names(provenance_mod, legacy):
    root, manifest = legacy
    try:
        with open(os.fsencode(root) + b"/\x83e\x83X\x83g.csv", "wb") as handle:
            handle.write(b"x")
    except OSError:
        pytest.skip("the file system refuses non-UTF-8 names")

    with pytest.raises(AssertionError, match="not UTF-8"):
        provenance_mod.verify_inputs(root, manifest)


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="GNU coreutils not installed")
def test_manifest_command_for_a_directory_outside_the_repository_runs_in_the_container(
    provenance_mod, legacy, tmp_path, monkeypatch
):
    # Past files under /external exist only inside the container, so the printed command
    # runs there through `docker compose exec`, from the repository root on the host.
    root, _manifest = legacy
    repo = tmp_path / "repo"
    generated = repo / "projects" / "demo" / "experiments" / "001_old_run" / "inputs.sha256"
    generated.parent.mkdir(parents=True)
    monkeypatch.chdir(repo)

    command = provenance_mod.manifest_command(root, generated)
    assert command.startswith("docker compose exec -T research-template bash -c ")
    assert f"(cd {root} && find . -type f" in command
    assert "> projects/demo/experiments/001_old_run/inputs.sha256" in command
    with pytest.raises(AssertionError, match="EXTERNAL_FILES_DIR") as excinfo:
        provenance_mod.verify_inputs(root, generated)
    assert command in str(excinfo.value)

    # A stand-in for `docker compose exec -T <service>` that runs the command here.
    fake = tmp_path / "bin" / "docker"
    fake.parent.mkdir()
    fake.write_text('#!/bin/sh\nshift 4\nexec "$@"\n')
    fake.chmod(0o755)
    path = f"{fake.parent}{os.pathsep}{os.environ.get('PATH', '')}"
    subprocess.run(["bash", "-c", command], check=True, cwd=repo, env={**os.environ, "PATH": path})
    assert provenance_mod.verify_inputs(root, generated) == {
        "figs/map.png": hashlib.sha256(b"png").hexdigest(),
        "metrics.csv": hashlib.sha256(b"a,b\n1,2\n").hexdigest(),
    }
