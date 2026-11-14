"""Compile the shipped cleanup guard against controlled DOS errors, without a guest."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('profile', ['', 'layers/'])
def test_native_cleanup_only_contains_expected_agent_memory_error(tmp_path, profile):
    compiler = shutil.which('c++')
    if compiler is None:
        pytest.skip('C++ compiler required for native cleanup boundary')
    patch = (ROOT / 'experimental/dosbox-x' / profile / 'headless-agent.patch').read_text()
    lines = patch.splitlines()
    start = lines.index('+static bool SHELL_FreeMemoryForExit(uint16_t segment)')
    end = lines.index('+}', start) + 1
    guard = '\n'.join(line[1:] for line in lines[start:end])
    assert '+        const bool memory_released = SHELL_FreeMemoryForExit(psp->GetSegment());' in lines
    assert '+        if (memory_released) {' in lines
    assert any(line.lstrip('+ ').startswith('*error = "DOS target cleanup interrupted') for line in lines)
    code = r'''
#include <cassert>
#include <cstdint>
#include <string>
#define C_DOSBOX_AGENT 1
struct Control { std::string opt_agent_config; } instance, *control = &instance;
int error_code = 0, attempts = 0, logs = 0;
void DOS_FreeProcessMemory(uint16_t segment) {
    assert(segment == 0x701); ++attempts;
    if (error_code) throw error_code;
}
#define LOG_MSG(...) (++logs)
''' + guard + r'''
int main() {
    instance.opt_agent_config = "owned-agent";
    assert(SHELL_FreeMemoryForExit(0x701));
    error_code = 7;
    assert(!SHELL_FreeMemoryForExit(0x701));
    assert(attempts == 2 && logs == 1);
    error_code = 6;
    try { SHELL_FreeMemoryForExit(0x701); assert(false); }
    catch (int value) { assert(value == 6); }
    error_code = 7;
    instance.opt_agent_config.clear();
    try { SHELL_FreeMemoryForExit(0x701); assert(false); }
    catch (int value) { assert(value == 7); }
    control = nullptr;
    try { SHELL_FreeMemoryForExit(0x701); assert(false); }
    catch (int value) { assert(value == 7); }
    assert(logs == 1 && attempts == 5);
}
'''
    source = tmp_path / 'cleanup.cpp'
    source.write_text(code)
    executable = tmp_path / 'cleanup'
    subprocess.run([compiler, '-std=c++14', '-Wall', '-Wextra', '-Werror',
                    str(source), '-o', str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
