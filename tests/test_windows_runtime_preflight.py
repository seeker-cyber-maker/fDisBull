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


def test_pe32_only_compiler_gate_does_not_require_win16_or_pe64(monkeypatch, tmp_path):
    fake_tool(tmp_path / "i686-w64-mingw32-gcc", "fixture")
    monkeypatch.setenv("PATH", str(tmp_path))
    selected = preflight.inspect("compilers", target="pe32")
    assert selected["ready_to_attempt"] is True
    assert selected["checks"]["selected_target"] == "pe32"
    assert selected["checks"]["target_toolchains_present"] == {
        "win16_ne": False, "win32_pe32": True, "win64_pe32_plus": False,
    }
    assert preflight.inspect("compilers", target="all")["ready_to_attempt"] is False
    assert preflight.inspect("compilers", target="win16")["ready_to_attempt"] is False


def test_macos_native_preflight_is_local_and_independent_of_wine(monkeypatch, tmp_path):
    for tool in ("clang", "lldb", "xcrun"):
        fake_tool(tmp_path / tool, "fixture")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(preflight.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(preflight.platform, "machine", lambda: "arm64")
    result = preflight.inspect("macos-native")
    assert result["ready_to_attempt"] is True
    assert result["checks"]["supported_macos_host"] is True
    assert result["checks"]["debug_permission_verified"] is False
    assert "wine" not in result["tools"] and "qemu" not in result["tools"]
    assert "macOS native LLDB entitlement and original target observation" in result["not_verified"]
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    assert preflight.inspect("macos-native")["ready_to_attempt"] is False
    monkeypatch.setattr(preflight.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(preflight.platform, "machine", lambda: "unknown")
    assert preflight.inspect("macos-native")["ready_to_attempt"] is False


def test_target_selector_is_rejected_outside_compiler_mode():
    with pytest.raises(ValueError, match="applies only"):
        preflight.inspect("macos-native", target="pe32")
    with pytest.raises(ValueError, match="applies only"):
        preflight.inspect("qemu-host", target="win16")


def test_pe32_cli_strict_succeeds_without_win16_toolchain(tmp_path):
    fake_tool(tmp_path / "i686-w64-mingw32-gcc", "fixture")
    env = {**os.environ, "PATH": str(tmp_path)}
    run = subprocess.run([sys.executable, str(FILE), "--mode", "compilers",
                          "--target", "pe32", "--strict"], capture_output=True,
                         text=True, env=env)
    assert run.returncode == 0, run.stderr
    record = json.loads(run.stdout)
    assert record["checks"]["selected_target"] == "pe32"
    assert record["ready_to_attempt"] is True
