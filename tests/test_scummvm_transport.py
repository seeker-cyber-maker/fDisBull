"""Concurrent, fail-closed transport checks for the ScummVM JSON-lines bridge."""
from concurrent.futures import ThreadPoolExecutor
import os
import textwrap
import threading
import time

import pytest

from fdisbull.scummvm_rpc import ScummVMError, ScummVMRPC


def _bridge(tmp_path, scenario):
    tmp_path.mkdir(parents=True, exist_ok=True)
    script = tmp_path / 'bridge.py'
    script.write_text(textwrap.dedent('''\
        #!/usr/bin/env python3
        import json, os, pathlib, socket, sys, time

        scenario = SCENARIO
        sock = socket.socket(fileno=int(os.environ['FDISBULL_SCUMMVM_FD']))
        stream = sock.makefile('rwb', buffering=0)
        def send(value, fragmented=False):
            data = (json.dumps(value, separators=(',', ':')) + '\\n').encode()
            if fragmented:
                for start in range(0, len(data), 3):
                    sock.sendall(data[start:start + 3])
            else:
                sock.sendall(data)

        run_id = None
        for line in stream:
            request = json.loads(line)
            request_id = request['id']
            op = request['op']
            if op == 'hello':
                send({'id':request_id, 'ok':True, 'engine':'agi',
                      'capabilities':['run', 'pause'], 'virtual_clock':True})
            elif scenario == 'no_pause' and op == 'pause':
                send({'id':request_id, 'ok':False,
                      'error':'unsupported', 'message':'No pause operation'})
            elif op == 'pause' and run_id is None:
                send({'id':request_id, 'ok':True})
            elif scenario in ('pause', 'bad_concurrent') and op == 'run':
                run_id = request_id
                pathlib.Path.cwd().joinpath('run-received').write_text('ready')
            elif scenario == 'pause' and op == 'pause':
                send({'id':request_id, 'ok':True}, fragmented=True)
                send({'id':run_id, 'ok':True,
                      'stop':{'reason':'pause','instructions':1,'guest_ms':20}},
                     fragmented=True)
            elif scenario == 'bad_concurrent' and op == 'pause':
                send({'id':request_id + 17, 'ok':True})
            elif scenario == 'unknown':
                send({'id':request_id + 17, 'ok':True})
            elif scenario == 'duplicate':
                response = (json.dumps({'id':request_id, 'ok':True}) + '\\n').encode()
                sock.sendall(response + response)
            elif scenario == 'eof':
                break
            elif scenario == 'timeout':
                time.sleep(5)
            elif scenario == 'refusal' and op == 'state.get':
                send({'id':request_id, 'ok':False, 'error':'refused', 'message':'No state'})
            elif scenario == 'refusal':
                send({'id':request_id, 'ok':True, 'value':42})
            elif scenario == 'no_pause':
                send({'id':request_id, 'ok':True, 'value':42})
            elif scenario == 'backpressure':
                send({'id':request_id, 'ok':True, 'length':len(request['payload'])})
            elif op == 'quit':
                send({'id':request_id, 'ok':True})
                break
    '''.replace('SCENARIO', repr(scenario))))
    script.chmod(0o700)
    game = tmp_path / 'game'
    game.mkdir()
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    return script, game, runtime


def _start(tmp_path, scenario):
    executable, game, runtime = _bridge(tmp_path, scenario)
    return ScummVMRPC(executable, game, game_id='kq1', runtime_parent=runtime)


def test_pause_reply_can_arrive_before_outstanding_run_reply(tmp_path):
    rpc = _start(tmp_path, 'pause')
    try:
        assert 'pause' in rpc.capabilities['features']
        sent = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(rpc.call, 'run', {'max_instructions':100000},
                                  timeout_ms=4000, on_sent=sent.set)
            assert sent.wait(2), 'run request was not completely sent'
            marker = rpc.root / 'run-received'
            deadline = time.monotonic() + 2
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.exists(), 'backend did not receive the run request'
            assert rpc.call('pause', timeout_ms=2000) == {}
            assert running.result(timeout=2)['stop']['reason'] == 'pause'
        assert rpc.sequence == 4
    finally:
        rpc.close()


def test_invalid_concurrent_reply_fails_both_pending_calls(tmp_path):
    rpc = _start(tmp_path, 'bad_concurrent')
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(rpc.call, 'run', {'max_instructions':100000}, timeout_ms=3000)
            marker = rpc.root / 'run-received'
            deadline = time.monotonic() + 2
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.exists()
            with pytest.raises(ScummVMError, match='unknown'):
                rpc.call('pause', timeout_ms=2000)
            with pytest.raises(ScummVMError, match='unknown'):
                running.result(timeout=2)
        assert rpc.process.poll() is not None
    finally:
        rpc.close()


def test_malformed_response_identity_and_duplicates_close_channel(tmp_path):
    for scenario in ('unknown', 'duplicate'):
        rpc = _start(tmp_path / scenario, scenario)
        try:
            with pytest.raises(ScummVMError):
                rpc.call('state.get', timeout_ms=1000)
            assert rpc.process.poll() is not None
            with pytest.raises(ScummVMError, match='closed|Invalid|unknown|duplicate'):
                rpc.call('state.get', timeout_ms=1000)
        finally:
            rpc.close()


@pytest.mark.parametrize('scenario', ['eof', 'timeout'])
def test_eof_or_timeout_reaps_owner_without_replaying_request(tmp_path, scenario):
    rpc = _start(tmp_path, scenario)
    try:
        with pytest.raises(ScummVMError):
            rpc.call('state.get', timeout_ms=250)
        assert rpc.process.poll() is not None
        assert rpc.sequence == 3
    finally:
        rpc.close()


def test_backend_refusal_keeps_a_valid_channel_and_large_send_drains(tmp_path):
    rpc = _start(tmp_path / 'refusal', 'refusal')
    try:
        with pytest.raises(ScummVMError, match='No state'):
            rpc.call('state.get')
        assert rpc.call('status')['value'] == 42
    finally:
        rpc.close()
    rpc = _start(tmp_path / 'no_pause', 'no_pause')
    try:
        assert 'pause' not in rpc.capabilities['features']
        assert rpc.call('status')['value'] == 42
    finally:
        rpc.close()
    rpc = _start(tmp_path / 'backpressure', 'backpressure')
    try:
        assert rpc.call('echo', {'payload':'x' * (2 * 1024 * 1024)}, timeout_ms=5000)['length'] == 2 * 1024 * 1024
    finally:
        rpc.close()


@pytest.mark.skipif(not (os.environ.get('FDISBULL_SCUMMVM_NATIVE') and
                         os.environ.get('FDISBULL_AGI_KQ1_DIR')),
                    reason='set patched backend and private KQ1 directory for native qualification')
def test_native_running_kq1_accepts_concurrent_pause(tmp_path):
    rpc = ScummVMRPC(os.environ['FDISBULL_SCUMMVM_NATIVE'],
                     os.environ['FDISBULL_AGI_KQ1_DIR'], game_id='kq1',
                     runtime_parent=tmp_path)
    try:
        assert 'pause' in rpc.capabilities['features']
        sent = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(rpc.call, 'run',
                                  {'max_instructions':10000000, 'max_ms':10000},
                                  timeout_ms=12000, on_sent=sent.set)
            assert sent.wait(3)
            assert rpc.call('pause', timeout_ms=3000) == {}
            assert running.result(timeout=3)['stop']['reason'] == 'pause'
    finally:
        rpc.close()
