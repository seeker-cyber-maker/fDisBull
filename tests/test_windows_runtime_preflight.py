"""Read-only runtime preflight checks; no Wine, VM or original game is launched."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

FILE = Path(__file__).resolve().parents[1] / "scripts" / "windows_runtime_preflight.py"
spec = importlib.util.spec_from_file_location("windows_runtime_preflight", FILE)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def fake_tool(path: Path, text: str) -> str:
    path.write_text("#!/bin/sh\nprintf '%s\\n' '" + text + "'\n")
    path.chmod(0o755)
    return str(path)


@pytest.mark.parametrize("text,expected", [
    ("wine-11.0", (11, 0, 0)),
    ("wine-11.1 (Staging)", (11, 1, 0)),
    ("wine-10.0", (10, 0, 0)),
    ("not-a-wine-version", None),
])
def test_wine_version_parser(text, expected):
    assert preflight._version(text, "wine") == expected


def test_qemu_parser():
    assert preflight._version("QEMU emulator version 9.2.4", "qemu") == (9, 2, 4)
    assert preflight._version("QEMU emulator version 8.2", "qemu") == (8, 2, 0)
    assert preflight._version("unknown", "qemu") is None


def test_wine_guest_requires_wine11_display_and_non_win32_prefix(tmp_path):
    wine11 = fake_tool(tmp_path / "wine-11", "wine-11.0")
    wine10 = fake_tool(tmp_path / "wine-10", "wine-10.0")
    xvfb = fake_tool(tmp_path / "Xvfb", "unused")
    ok = preflight.inspect("wine-guest", wine=wine11, xvfb=xvfb, env={"WINEARCH": "wow64"})
    assert ok["ready_to_attempt"] is True
    assert ok["qualification"].startswith("preflight-only")
    assert ok["checks"]["prefix_architecture_verified"] is False
    assert preflight.inspect("wine-guest", wine=wine10, xvfb=xvfb, env={})["ready_to_attempt"] is False
    assert preflight.inspect("wine-guest", wine=wine11, xvfb=xvfb, env={"WINEARCH": "win32"})["ready_to_attempt"] is False
    assert preflight.inspect("wine-guest", wine=wine11, xvfb="/no/xvfb", env={})["ready_to_attempt"] is False
    assert preflight.inspect("wine-guest", wine=wine11, xvfb="/no/xvfb", env={"DISPLAY": ":9"})["ready_to_attempt"] is True


def test_qemu_host_needs_versioned_binary_kernel_and_runtime(tmp_path):
    qemu = fake_tool(tmp_path / "qemu", "QEMU emulator version 9.2.4")
    kernel, image = tmp_path / "kernel", tmp_path / "runtime.cpio.gz"
    kernel.write_bytes(b"test-kernel-placeholder")
    image.write_bytes(b"test-runtime-placeholder")
    result = preflight.inspect("qemu-host", qemu=qemu, kernel=str(kernel), initramfs=str(image))
    assert result["ready_to_attempt"]
    assert str(kernel) not in json.dumps(result)
    image.unlink()
    assert not preflight.inspect("qemu-host", qemu=qemu, kernel=str(kernel), initramfs=str(image))["ready_to_attempt"]
    qemu_old = fake_tool(tmp_path / "qemu-old", "QEMU emulator version 8.2.0")
    image.write_bytes(b"test-runtime-placeholder")
    assert not preflight.inspect("qemu-host", qemu=qemu_old, kernel=str(kernel), initramfs=str(image))["ready_to_attempt"]


def test_compiler_gate_reports_per_target_not_fake_execution(monkeypatch, tmp_path):
    for name in ("wcc", "wlink", "i686-w64-mingw32-gcc"):
        fake_tool(tmp_path / name, "fixture")
    monkeypatch.setenv("PATH", str(tmp_path))
    result = preflight.inspect("compilers")
    assert result["checks"]["target_toolchains_present"] == {
        "win16_ne": True, "win32_pe32": True, "win64_pe32_plus": False,
    }
    assert result["ready_to_attempt"] is False


def test_strict_cli_and_no_guest_launch(tmp_path):
    wine = fake_tool(tmp_path / "wine", "wine-11.0")
    missing = tmp_path / "not-xvfb"
    run = subprocess.run([sys.executable, str(FILE), "--mode", "wine-guest", "--wine", wine,
                          "--xvfb", str(missing), "--strict"], text=True, capture_output=True,
                         env={k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WINEARCH")})
    assert run.returncode == 2
    record = json.loads(run.stdout)
    assert record["ready_to_attempt"] is False
    assert "original Windows program execution" in record["not_verified"]
    assert not missing.exists()
