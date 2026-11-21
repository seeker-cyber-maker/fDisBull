"""Inventory must stay noninvasive and never promote labels to qualification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dotbox_runtime_probe_test", ROOT / "src/dotbox/runtime_probe.py")
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.fixture
def lightweight(monkeypatch):
    monkeypatch.setattr(probe, "_libraries", lambda: {"SDL2": {"lookup_match_found": False}})


def test_secret_environment_values_and_private_paths_are_not_emitted(monkeypatch, lightweight, tmp_path):
    secret = "private-token-and-server-path"
    for name in ("DISPLAY", "PULSE_SERVER", "SDL_VIDEODRIVER", "GH_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.setenv(name, secret)
    backend = tmp_path / "dosbox-x"
    backend.write_bytes(b"explicit backend fixture")
    result = probe.collect_runtime(backend=backend, context="dot-cloud", label="before-takeover")
    encoded = json.dumps(result)
    assert secret not in encoded
    assert str(tmp_path) not in encoded
    assert result["display"]["environment_presence"]["DISPLAY"] is True
    assert result["audio"]["environment_presence"]["PULSE_SERVER"] is True
    assert result["context"] == {"requested": "dot-cloud", "identity_verified": False, "evidence": "current_process_only"}
    assert result["qualification"]["dot_computer_verified"] is False
    assert result["takeover"]["owner"] == "unknown"
    assert result["takeover"]["source"] == "unavailable"


def test_backend_is_hashed_without_being_executed(monkeypatch, lightweight, tmp_path):
    marker = tmp_path / "launched"
    backend = tmp_path / "dosbox-x"
    content = f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n".encode()
    backend.write_bytes(content)
    backend.chmod(0o700)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("probe launched a subprocess"))
    result = probe.collect_runtime(backend=backend)["backend"]
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["bytes"] == len(content)
    assert result["executable_bit_set"] is True
    assert result["launched"] is False
    assert result["capabilities"] == "not_queried"
    assert not marker.exists()


def test_distribution_metadata_is_used_without_importing_runtime_packages(monkeypatch, lightweight):
    looked_up = []
    def version(name):
        looked_up.append(name)
        if name == "fdisbull":
            raise probe.metadata.PackageNotFoundError(name)
        return "1.2.3"
    monkeypatch.setattr(probe.metadata, "version", version)
    before = set(sys.modules)
    result = probe.collect_runtime()
    assert looked_up == list(probe.DISTRIBUTIONS)
    assert result["distributions"]["fdisbull"] == {"status": "not_found"}
    assert result["distributions"]["Pillow"] == {"status": "installed", "version": "1.2.3"}
    added = set(sys.modules) - before
    assert not any(name == "fdisbull" or name.startswith("fdisbull.") for name in added)


def test_missing_explicit_backend_is_an_inventory_result(lightweight, tmp_path):
    result = probe.collect_runtime(backend=tmp_path / "missing")["backend"]
    assert result == {"status": "unavailable", "error": "not_regular_file"}


@pytest.mark.parametrize("options", [{"context": "some-cloud"}, {"label": "bad label"}, {"label": "x" * 65}])
def test_invalid_context_and_receipt_labels_are_rejected(options, lightweight):
    with pytest.raises(ValueError):
        probe.collect_runtime(**options)


def test_receipt_is_private_and_overwrite_is_refused(tmp_path, lightweight, capsys):
    path = tmp_path / "receipt.json"
    assert probe.main(["--context", "local", "--output", str(path)]) == 0
    saved = path.read_bytes()
    assert json.loads(saved)["format"] == "dotbox-runtime-probe-1"
    if sys.platform != "win32":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(SystemExit) as error:
        probe.main(["--output", str(path)])
    assert error.value.code == 2
    assert path.read_bytes() == saved
    assert "existing files are preserved" in capsys.readouterr().err


def test_canonical_probe_runs_as_one_attached_file_without_checkout(tmp_path):
    attached = tmp_path / "dotbox_runtime_probe.py"
    shutil.copyfile(ROOT / "src/dotbox/runtime_probe.py", attached)
    result = subprocess.run([sys.executable, str(attached), "--context", "dot-cloud", "--label", "before-takeover"],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    receipt = json.loads(result.stdout)
    assert receipt["qualification"]["status"] == "inventory_only"
    assert receipt["takeover"]["supported_provider_observed"] is False
    assert receipt["context"]["identity_verified"] is False
    assert receipt["backend"]["status"] == "not_supplied"


def test_checkout_wrapper_runs_without_installing_dotbox(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "scripts/dotbox_runtime_probe.py"), "--context", "local"],
                            cwd=tmp_path, capture_output=True, text=True, check=True)
    receipt = json.loads(result.stdout)
    assert receipt["context"]["requested"] == "local"
    assert receipt["qualification"]["native_game_launch_verified"] is False
