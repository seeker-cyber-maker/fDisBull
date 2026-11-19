"""Strict ordinary-pause observations on one explicitly selected DOSBox build.

This is opt-in native qualification. The extracted-loop source tests do not
establish this behavior, and a pass here does not close a different game's
previously retained counterexample. No settling read or clock tolerance is used.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC


BUSY_COM = bytes.fromhex('b83412bb78564043ebfc')
WAITS_MS = (25, 35, 45, 55, 65, 75, 85, 95)
PROFILE = ('dosbox machine=svga_s3', 'cpu core=normal', 'cpu cycles=fixed 157600',
           'render frameskip=0', 'render doublescan=false', 'render scaler=none',
           'video scanline render on demand=false', 'video vga palette update on full load=true',
           'video enable 8-bit dac=false')


def test_real_ordinary_pause_keeps_four_clock_status_register_brackets(tmp_path):
    executable = os.environ.get('FDISBULL_DOSBOX')
    if not executable:
        pytest.skip('Set FDISBULL_DOSBOX for native ordinary-pause qualification')
    executable = str(Path(executable).resolve(strict=True))
    game = tmp_path/'game'
    game.mkdir()
    fixture = game/'PVERIFY.COM'
    fixture.write_bytes(BUSY_COM)
    # Preserve the existing constructor flags and add one explicit profile in
    # a single exec. There is still exactly one native process lifetime.
    launcher = tmp_path/'dosbox-profile'
    launcher.write_text('#!'+sys.executable+'\nimport os, sys\n'
        + 'native='+repr(executable)+'\nsettings='+repr(PROFILE)+'\n'
        + "os.execv(native, [native, *sys.argv[1:], *[v for s in settings for v in ('-set', s)]])\n")
    launcher.chmod(0o700)
    report = dict(profile=list(PROFILE), effective_profile_verified=False,
                  fixture_sha256=hashlib.sha256(BUSY_COM).hexdigest(), episodes=[], calls=[])
    rpc = process = logfd = session = None
    end = time.monotonic()+75

    def save():
        encoded = json.dumps(report, indent=2, sort_keys=True).encode()
        assert len(encoded) <= 1048576
        (tmp_path/'pause-observations.json').write_bytes(encoded+b'\n')

    def spawned(value):
        nonlocal process, logfd
        assert process is None
        process = value
        report['native_pid'] = value.pid
        logfd = os.open(f'/proc/{value.pid}/fd/1', os.O_RDONLY) if sys.platform.startswith('linux') else None

    def call(method, params=None):
        remaining = int((end-time.monotonic())*1000)
        assert remaining > 0, 'Original native observation deadline exhausted'
        assert len(report['calls']) < 512
        params = dict(params or {})
        if session is not None:
            params['session_id'] = session
        row = dict(method=method, params=params)
        report['calls'].append(row)
        try:
            reply = rpc.call(method, params, timeout_ms=min(1000, remaining))
            row['reply'] = reply
        except BaseException as error:
            row['error'] = dict(type=type(error).__name__, message=str(error))
            raise
        finally:
            save()
        assert session is None or reply.get('session_id') == session
        return reply

    try:
        rpc = DOSBoxRPC(launcher, game, on_spawn=spawned)
        report['capabilities'] = rpc.capabilities
        assert rpc.capabilities.get('debugger') is True
        assert rpc.capabilities.get('timing', {}).get('guest_clock') == 'PIC_Ticks_milliseconds'
        assert rpc.capabilities.get('timing', {}).get('fast_forward') is True
        start = call('session.start', dict(target=dict(command='PVERIFY.COM', arguments=[]),
                     mounts=[dict(drive='C', host_path=str(game))], break_at='entry'))
        assert start['state'] == 'stopped' and start['stop_reason']['kind'] == 'startup'
        session = start['session_id']
        assert call('execution.timing', dict(fast_forward=False))['fast_forward'] is False
        work_end = end
        for wait_ms in WAITS_MS:
            end = min(work_end, time.monotonic()+5)
            episode = dict(wait_ms=wait_ms, blocks=[])
            report['episodes'].append(episode)
            running = episode['continue'] = call('execution.continue')
            assert running.get('state') == 'running' and running.get('stop_reason') is None
            waited = call('execution.wait', dict(operation_id=running['operation_id'], timeout_ms=wait_ms))
            assert waited.get('running') is True and waited.get('stop_reason') is None
            try:
                pause = episode['pause'] = call('execution.pause')
                operation = pause['operation_id']
            except ValueError as error:
                if not str(error).endswith('(TARGET_NOT_RUNNING)'):
                    raise
                episode['pause_race'] = str(error)
                operation = running['operation_id']
            stopped = episode['first_stop'] = call('execution.wait', dict(operation_id=operation, timeout_ms=500))
            assert stopped.get('running', False) is False
            assert stopped['state'] == 'stopped' and stopped['stop_reason']['kind'] == 'pause'
            for _ in range(4):
                block = {}
                episode['blocks'].append(block)
                block['timing_before'] = call('execution.timing')
                block['status'] = call('session.status')
                assert block['status']['state'] == 'stopped'
                block['registers'] = call('state.get_registers')
                block['timing_after'] = call('execution.timing')
            # Finish the declared four read-only blocks before asserting. Any
            # mismatch fails this test before the next loop can continue.
            first = episode['blocks'][0]
            for block in episode['blocks']:
                assert block['timing_before'] == first['timing_before'] == block['timing_after']
                assert block['timing_before']['fast_forward'] is False
                assert type(block['timing_before']['guest_ticks']) is int
                assert block['status'] == first['status']
                assert block['registers'] == first['registers']
                for field in ('timing_before', 'status', 'registers', 'timing_after'):
                    assert block[field]['state_revision'] == stopped['state_revision']
                assert block['status']['last_stop']['kind'] == 'pause'
    finally:
        try:
            if rpc is not None:
                rpc.close()
        finally:
            if process is not None:
                report['native_reaped'] = process.poll() is not None
                report['native_returncode'] = process.returncode
            if logfd is not None:
                try:
                    os.lseek(logfd, 0, os.SEEK_SET)
                    log = os.read(logfd, 262145)
                    (tmp_path/'emulator.log').write_bytes(log[:262144])
                    report['native_log_complete'] = len(log) == os.fstat(logfd).st_size <= 262144
                finally:
                    os.close(logfd)
            save()
        assert process is None or report['native_reaped']
        assert logfd is None or report['native_log_complete']
        assert fixture.read_bytes() == BUSY_COM
