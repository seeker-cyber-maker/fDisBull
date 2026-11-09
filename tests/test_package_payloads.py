"""The release gate must detect omissions without a hand-maintained file list."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import subprocess
import zipfile

import pytest

spec = spec_from_file_location("check_package_payloads", Path(__file__).parents[1] / "scripts/check_package_payloads.py")
gate = module_from_spec(spec)
spec.loader.exec_module(gate)


def test_tracks_new_resource_and_checks_all_four_artifacts(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    source = {
        "src/fdisbull/__init__.py": b"core",
        "src/fdisbull/data/new-resource.swift": b"helper",
        "player/fdisbull_player/__init__.py": b"player",
        "tests/new-support.mjs": b"test",
        "scripts/new-support.c": b"support",
        "native/qemu-input-retrace/private-api.patch": b"retrace input extension",
    }
    for name, data in source.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    assert gate.tracked_payload(tmp_path) == source
    artifacts = {
        "core": {"fdisbull/" + n[len(gate.CORE):]: b for n, b in source.items() if n.startswith(gate.CORE)},
        "player": {"fdisbull_player/" + n[len(gate.PLAYER):]: b for n, b in source.items() if n.startswith(gate.PLAYER)},
        "sdist": {"fdisbull-1/" + n: b for n, b in source.items()},
        "tool": {"fdisbull-1/" + n: b for n, b in source.items()},
    }
    for kind, contents in artifacts.items():
        gate.check_payload(source, contents, kind)
        victim = next(n for n in contents if "new-resource.swift" in n) if kind != "player" else next(iter(contents))
        damaged = dict(contents)
        del damaged[victim]
        with pytest.raises(ValueError, match="missing="):
            gate.check_payload(source, damaged, kind)
        damaged = dict(contents)
        damaged[victim] = b"modified"
        with pytest.raises(ValueError, match="changed="):
            gate.check_payload(source, damaged, kind)


def test_rejects_duplicate_archive_entries(tmp_path):
    path = tmp_path / "test.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("fdisbull/file", b"one")
        with pytest.warns(UserWarning, match="Duplicate"):
            archive.writestr("fdisbull/file", b"two")
    with pytest.raises(ValueError, match="duplicate"):
        gate.archive_payload(path)


def test_source_support_omission_and_unexpected_file_fail():
    source = {"src/fdisbull/__init__.py": b"core", "player/fdisbull_player/__init__.py": b"player",
              "tests/new-check.mjs": b"test"}
    contents = {"fdisbull-1/" + name: data for name, data in source.items()}
    del contents["fdisbull-1/tests/new-check.mjs"]
    with pytest.raises(ValueError, match="new-check.mjs"):
        gate.check_payload(source, contents, "tool")
    contents["fdisbull-1/tests/new-check.mjs"] = b"test"
    contents["fdisbull-1/src/fdisbull/untracked.py"] = b"unexpected"
    with pytest.raises(ValueError, match="unexpected=.*untracked.py"):
        gate.check_payload(source, contents, "tool")


def test_rejects_archive_symlinks(tmp_path):
    path = tmp_path / "links.zip"
    link = zipfile.ZipInfo("fdisbull/link")
    link.create_system = 3
    link.external_attr = 0o120777 << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(link, "target")
    with pytest.raises(ValueError, match="symlink"):
        gate.archive_payload(path)


def test_receipt_binds_commit_and_artifact_bytes(tmp_path):
    import hashlib
    import json
    import sys
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    files = {"src/fdisbull/__init__.py": b"core", "player/fdisbull_player/__init__.py": b"player"}
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
    artifacts = {
        "core": {"fdisbull/__init__.py": b"core"},
        "player": {"fdisbull_player/__init__.py": b"player"},
        "sdist": {"fdisbull-1/" + n: b for n, b in files.items()},
        "tool": {"fdisbull-1/" + n: b for n, b in files.items()},
    }
    args = []
    for kind, contents in artifacts.items():
        path = tmp_path / (kind + ".zip")
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in contents.items():
                archive.writestr(name, data)
        args += ["--" + kind, str(path)]
    output = tmp_path / "receipt.json"
    subprocess.run([sys.executable, str(Path(gate.__file__)), "--source-root", str(repo), "--output", str(output), *args], check=True)
    receipt = json.loads(output.read_text())
    assert receipt["source_commit"] == subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert receipt["tracked_worktree_dirty"] is False
    assert receipt["inventory_counts"] == {"core": 1, "player": 1, "source_total": 2}
    assert receipt["artifacts"]["core"]["sha256"] == hashlib.sha256((tmp_path / "core.zip").read_bytes()).hexdigest()
    (repo / "src/fdisbull/__init__.py").write_bytes(b"changed")
    output.unlink()
    result = subprocess.run([sys.executable, str(Path(gate.__file__)), "--source-root", str(repo), "--output", str(output), *args], capture_output=True)
    assert result.returncode != 0
    assert not output.exists()
