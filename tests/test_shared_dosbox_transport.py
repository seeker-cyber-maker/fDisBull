"""Both product transports obey the same wire contract with real private pipes.

The authored peer is not a native DOSBox build or GUI acceptance fixture.
"""
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=['fdisbull', 'dotbox'])
def transport(request, monkeypatch):
    if request.param == 'dotbox':
        source = ROOT / 'apps/dotbox/src'
        if not source.is_dir():
            pytest.skip('The standalone fDisBull source distribution omits the DotBox application')
        monkeypatch.syspath_prepend(str(source))
        module = importlib.import_module('dotbox.native_rpc')
    else:
        module = importlib.import_module('fdisbull.dosbox_rpc')
    return request.param, module


@pytest.fixture
def peer(tmp_path):
    executable = tmp_path / 'wire-peer'
    executable.write_text(f'''#!{sys.executable}
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
config = Path(args[args.index('--agent-config') + 1]).read_text()
endpoint = next(line.split('=', 1)[1] for line in config.splitlines() if line.startswith('endpoint='))
_, source, sink = endpoint.split(':')
with os.fdopen(int(source), 'r') as reader, os.fdopen(int(sink), 'w') as writer:
    for line in reader:
        request = json.loads(line)
        method = request['method']
        reply = {{'jsonrpc': '2.0', 'id': request['id']}}
        if method == 'agent.capabilities':
            reply['result'] = {{'video': {{'headless': True}}}}
        elif method == 'test.refusal':
            reply['error'] = {{'code': -1, 'message': 'authored refusal', 'data': {{'reason': 'REFUSED'}}}}
        elif method == 'test.bad-id':
            reply['id'] = 'unrelated-request'
            reply['result'] = {{}}
        elif method == 'test.scalar':
            reply['result'] = 7
        elif method == 'test.eof':
            print('authored native EOF marker', flush=True)
            break
        elif method == 'test.timeout':
            time.sleep(30)
            continue
        else:
            reply['result'] = {{'id': request['id'], 'method': method, 'params': request['params']}}
        writer.write(json.dumps(reply) + '\\n')
        writer.flush()
''')
    executable.chmod(0o700)
    return executable


def test_product_identity_and_recoverable_refusal(transport, peer, tmp_path):
    product, module = transport
    rpc = module.DOSBoxRPC(peer, tmp_path)
    try:
        assert rpc.call('test.echo', {'value': 3}) == {
            'id': product + '-2', 'method': 'test.echo', 'params': {'value': 3}}
        with pytest.raises(module.DebuggerError, match=r'authored refusal \(REFUSED\)'):
            rpc.call('test.refusal')
        assert rpc.reader is not None and rpc.writer is not None
        assert rpc.call('test.after-refusal')['id'] == product + '-4'
    finally:
        result = rpc.close()
    assert rpc.process.poll() is not None
    if product == 'dotbox':
        assert result['process_reaped'] is True
    else:
        assert result is None


def test_lock_admission_timeout_keeps_channel_and_request_sequence(transport, peer, tmp_path):
    product, module = transport
    rpc = module.DOSBoxRPC(peer, tmp_path)
    try:
        rpc.lock.acquire()
        try:
            with pytest.raises(module.DebuggerError, match='channel ownership'):
                rpc.call('test.must-not-send', timeout_ms=10)
        finally:
            rpc.lock.release()
        assert rpc.reader is not None and rpc.writer is not None
        assert rpc.call('test.after-lock')['id'] == product + '-2'
    finally:
        rpc.close()


@pytest.mark.parametrize('method, error, message', [
    ('test.bad-id', OSError, 'Invalid RPC response identity'),
    ('test.scalar', ValueError, 'RPC result must be an object'),
    ('test.timeout', TimeoutError, 'without replay'),
])
def test_admitted_failure_closes_channel_without_replay(transport, peer, tmp_path, method, error, message):
    _, module = transport
    rpc = module.DOSBoxRPC(peer, tmp_path)
    try:
        with pytest.raises(error, match=message):
            rpc.call(method, timeout_ms=50)
        assert rpc.reader is None and rpc.writer is None and rpc.sequence == 2
        with pytest.raises(module.DebuggerError, match='channel is closed'):
            rpc.call('test.must-not-replay')
        assert rpc.sequence == 2
    finally:
        rpc.close()
    assert rpc.process.poll() is not None


def test_request_budget_failure_is_terminal_after_admission(transport, peer, tmp_path):
    _, module = transport
    rpc = module.DOSBoxRPC(peer, tmp_path)
    try:
        rpc.limit = 128
        with pytest.raises(module.DebuggerError, match='request exceeds'):
            rpc.call('test.oversize', {'data': 'x' * 256})
        assert rpc.reader is None and rpc.writer is None and rpc.sequence == 2
    finally:
        rpc.close()


def test_eof_preserves_product_diagnostic_policy(transport, peer, tmp_path):
    product, module = transport
    rpc = module.DOSBoxRPC(peer, tmp_path)
    try:
        with pytest.raises(OSError, match='Emulator closed the RPC channel') as caught:
            rpc.call('test.eof')
        assert ('authored native EOF marker' in str(caught.value)) is (product == 'dotbox')
        assert rpc.reader is None and rpc.writer is None
    finally:
        rpc.close()


def test_staged_dos_guest_imports_and_exchanges_without_host_packages(peer, tmp_path, monkeypatch):
    from fdisbull.dos_runtime import resources

    staged = tmp_path / 'guest'
    mapping = resources()
    for name, source in mapping.items():
        target = staged / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # The guest has only the resources actually staged by dos_runtime; -I -S
    # prevents a host installation or inherited source path from hiding a miss.
    script = '''
import json, sys
sys.path.insert(0, sys.argv[1])
import dos_broker
from remote.dosbox_rpc import DOSBoxRPC
rpc = DOSBoxRPC(sys.argv[2], sys.argv[3])
try:
    assert rpc.call('test.guest')['id'] == 'fdisbull-2'
finally:
    rpc.close()
assert rpc.process.poll() is not None
print(json.dumps(sorted(dos_broker.RESOURCES)))
'''
    result = subprocess.run(
        [sys.executable, '-I', '-S', '-c', script,
         str(staged / 'opt/fdisbull'), str(peer), str(tmp_path)],
        cwd=staged, capture_output=True, text=True, check=True, timeout=10)
    assert set(json.loads(result.stdout)) == set(mapping)

    # Runtime preparation, in-guest identity and retained-input identity must
    # bind the same bytes. This is the legacy DOSBox-in-QEMU profile.
    monkeypatch.syspath_prepend(str(ROOT / 'scripts/ci'))
    spec = importlib.util.spec_from_file_location(
        'shared_transport_runtime_inputs', ROOT / 'scripts/ci/unified-runtime-inputs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.RESOURCES['dos']) == set(mapping)
    for guest_name, source_name in module.RESOURCES['dos'].items():
        assert (ROOT / source_name).read_bytes() == mapping[guest_name].read_bytes()
