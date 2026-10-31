"""Native LLDB qualification uses only a fixture authored by this test."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

import pytest

from fdisbull.macos_lldb import _log_tail, _source_still_matches, observe_macos_arm64_launch


_FIXTURE = r'''
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
__attribute__((noinline)) int marker(int x) {
    volatile int y = x + 7;
    return y;
}
int main(int argc, char **argv) {
    if (getenv("FDISBULL_LLDB_OBSERVATION_CONFIG")) return 5;
    if (argc > 1) {
        FILE *file = fopen(argv[1], "w");
        if (!file) return 3;
        fprintf(file, "%d", getpid());
        fclose(file);
        for (;;) sleep(1);
    }
    return marker(35) == 42 ? 0 : 1;
}
'''


def test_post_launch_source_check_rejects_growth_and_mutation(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'original')
    sha256 = hashlib.sha256(b'original').hexdigest()
    assert _source_still_matches(source, size=8, sha256=sha256)
    source.write_bytes(b'original' + b'x' * 4096)
    assert not _source_still_matches(source, size=8, sha256=sha256)
    source.write_bytes(b'changed!')
    assert not _source_still_matches(source, size=8, sha256=sha256)


def test_lldb_diagnostic_reads_only_log_tail(tmp_path):
    log = tmp_path / 'lldb.stderr'
    log.write_bytes(b'prefix' * 1000 + b'final error')
    tail = _log_tail(log)
    assert len(tail) <= 2048 and tail.endswith('final error')


@pytest.fixture(scope='module')
def arm64_executable(tmp_path_factory):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        pytest.skip('native LLDB fixture requires an arm64 macOS host')
    if not Path('/usr/bin/clang').is_file() or not shutil.which('lldb'):
        pytest.skip('Apple clang and LLDB are required for the native fixture')
    root = tmp_path_factory.mktemp('fdisbull-lldb')
    source, binary = root / 'fixture.c', root / 'fixture'
    source.write_text(_FIXTURE, encoding='utf-8')
    subprocess.run(['/usr/bin/clang', '-arch', 'arm64', '-g', '-O0',
                    str(source), '-o', str(binary)], check=True, capture_output=True)
    return binary


def test_arm64_lldb_observation_binds_source_runtime_and_stop(arm64_executable):
    receipt = observe_macos_arm64_launch(arm64_executable, symbol='marker')
    assert receipt['status'] == 'ok', receipt.get('reason')
    source, runtime = receipt['source'], receipt['runtime']
    assert source['sha256'] == hashlib.sha256(arm64_executable.read_bytes()).hexdigest()
    assert source['architecture'] == 'arm64'
    assert runtime['source_identity_confirmed'] is True
    assert runtime['stop_reason']['kind'] == 'breakpoint'
    assert runtime['pc_runtime'] == int(runtime['registers']['pc'], 16)
    image = runtime['main_image']
    assert image['slide'] == image['load_base'] - image['file_base']
    assert runtime['pc_static_va'] == runtime['pc_runtime'] - image['slide']
    text_section = next(section for section in image['mapped_sections'] if section['name'] == '__TEXT')
    assert text_section['load_address'] <= runtime['pc_runtime'] < (
        text_section['load_address'] + text_section['size'])
    memory = runtime['memory']
    assert memory['status'] == 'ok'
    # The fixture's __TEXT segment has file offset zero. This is an actual
    # source-to-runtime byte comparison, not a mocked decoder assertion.
    offset = runtime['pc_static_va'] - text_section['file_address']
    expected = arm64_executable.read_bytes()[offset:offset + memory['size']]
    assert bytes.fromhex(memory['hex']) == expected
    assert runtime['disassembly']['status'] == 'ok'
    assert runtime['disassembly']['instructions'][0]['runtime_address'] == runtime['pc_runtime']


def test_unresolved_breakpoint_does_not_launch(arm64_executable):
    receipt = observe_macos_arm64_launch(arm64_executable, symbol='fdisbull_absent_symbol_9e17')
    assert receipt['status'] == 'unresolved_breakpoint'
    assert receipt['source']['sha256'] == hashlib.sha256(arm64_executable.read_bytes()).hexdigest()
    assert 'runtime' not in receipt


def test_timeout_terminates_only_its_authored_fixture(arm64_executable, tmp_path):
    pid_file = tmp_path / 'fixture.pid'
    receipt = observe_macos_arm64_launch(arm64_executable, symbol='marker',
                                         argv=[str(pid_file)], timeout_seconds=5)
    assert receipt['status'] == 'timeout', receipt.get('reason')
    assert pid_file.is_file(), 'fixture did not start before the timeout'
    pid = int(pid_file.read_text())
    for _ in range(10):
        observed = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
                                  text=True, capture_output=True)
        if observed.returncode != 0:
            break
        time.sleep(0.1)
    else:
        if str(arm64_executable) in observed.stdout:
            os.kill(pid, 9)  # clean up only this test's identified fixture
        pytest.fail('timed-out LLDB launch left its fixture process running')


def test_non_macho_is_explicitly_unsupported(tmp_path):
    binary = tmp_path / 'not-a-macho'
    binary.write_bytes(b'not a Mach-O executable')
    receipt = observe_macos_arm64_launch(binary, symbol='main')
    assert receipt['status'] == 'unsupported'
    assert receipt['source']['sha256'] == hashlib.sha256(binary.read_bytes()).hexdigest()


def test_lldb_permission_denial_is_explicit(arm64_executable, tmp_path):
    unavailable = tmp_path / 'not-executable-lldb'
    unavailable.write_bytes(b'')
    unavailable.chmod(0o644)
    receipt = observe_macos_arm64_launch(arm64_executable, symbol='marker',
                                         lldb_path=unavailable)
    assert receipt['status'] == 'permission_denied'
    assert 'runtime' not in receipt


def test_target_launch_permission_denial_is_explicit(arm64_executable, tmp_path):
    denied = tmp_path / 'fixture-without-execute-permission'
    shutil.copy2(arm64_executable, denied)
    denied.chmod(0o644)
    receipt = observe_macos_arm64_launch(denied, symbol='marker')
    assert receipt['status'] == 'permission_denied'
    assert receipt['source']['sha256'] == hashlib.sha256(denied.read_bytes()).hexdigest()
    assert 'runtime' not in receipt
