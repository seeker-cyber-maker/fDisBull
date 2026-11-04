"""Compile and execute the authored C++ control core, not a ScummVM runtime."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).parents[1]
CASES = ["canonical-bytes", "before-after", "no-owner-resume", "breakpoint",
         "stale-generation", "live-word-guard", "long-operand", "nested-completion",
         "syscall-break", "pause-yield", "host-budget-yield", "trace-drop-count",
         "active-resource-and-stack", "bounds-and-invalid-decode"]


@pytest.fixture(scope="module")
def control_executable(tmp_path_factory):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        pytest.skip("C++ compiler unavailable; native control-kernel tests not run")
    work = tmp_path_factory.mktemp("kyra-native-core")
    executable = work / "control-core"
    built = subprocess.run([compiler, "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-fno-sanitize-recover=all", "-I", str(ROOT),
                            str(ROOT / "tests/fixtures/kyra_debug_core.cpp"), "-o", str(executable)],
                           capture_output=True, text=True, timeout=60)
    assert built.returncode == 0, built.stdout + built.stderr
    return executable


@pytest.mark.parametrize("case", CASES)
def test_native_control_kernel(control_executable, case):
    result = subprocess.run([str(control_executable), case], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "(control kernel only)" in result.stdout
