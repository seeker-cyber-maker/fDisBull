"""Finite saved-script checkpoints on an independently authored DOS COM.

Two cases admit at most four VM lifetimes: an initial owner and one verified
replacement per case. Every instruction and checkpoint is dispatched by the
saved script. This source is an acceptance requirement, not an execution claim.
The caller supplies QEMU, qemu-img, firmware, mcopy and a full FreeDOS boot image.
"""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline
from test_qemu_dos_checkpoint_native import _inputs
from test_qemu_dos_checkpoint_sessions_native import _fixture


CASE_SECONDS = 90
SCRIPT_MS = 30000
MAX_STATE_BYTES = 64 * 1024 * 1024
PROCESS_FORMAT = 'fdisbull-qemu-dos-process-qcow2-v2'


def _remaining(deadline, ceiling):
    remaining = int((deadline - time.monotonic()) * 1000)
    if remaining < 1:
        raise TimeoutError('Native checkpoint-script case deadline expired')
    return min(remaining, ceiling)


@contextmanager
def _body_deadline(debug, deadline):
    previous = getattr(debug, '_rpc_deadline', None)
    debug._rpc_deadline = min(previous, deadline) if previous is not None else deadline
    try:
        yield
    finally:
        debug._rpc_deadline = previous


def _route(case, address):
    save, load = (('save-state', 'load-anchor-stone') if case == 'state_anchor'
                  else ('save-anchor-stone', 'load-state'))
    restore = dict(op=load, artifact='$saved.artifact', **{'as': 'restored'})
    if load == 'load-state':
        restore['timeout_ms'] = 30000
    return dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        dict(op='step', count=3, timeout_ms=5000, **{'as': 'prepared'}),
        dict(op='registers', **{'as': 'before_cpu'}),
        dict(op='memory', address=hex(address), length=2, space='physical',
             **{'as': 'before_data'}),
        dict(op='assert', value='$before_data.hex', equals='1111'),
        dict(op=save, name=case + '.qcow2', max_bytes=MAX_STATE_BYTES,
             **{'as': 'saved'}),
        dict(op='step', count=1, timeout_ms=5000, **{'as': 'changed'}),
        dict(op='registers', **{'as': 'changed_cpu'}),
        dict(op='memory', address=hex(address), length=2, space='physical',
             **{'as': 'changed_data'}),
        dict(op='assert', value='$changed_data.hex', equals='1211'),
        restore,
        dict(op='registers', **{'as': 'restored_cpu'}),
        dict(op='memory', address=hex(address), length=2, space='physical',
             **{'as': 'restored_data'}),
        dict(op='assert', value='$restored_cpu', equals='$before_cpu'),
        dict(op='assert', value='$restored_data', equals='$before_data'),
        dict(op='step', count=1, timeout_ms=5000, **{'as': 'canary'}),
        dict(op='registers', **{'as': 'canary_cpu'}),
        dict(op='memory', address=hex(address), length=2, space='physical',
             **{'as': 'canary_data'}),
        dict(op='assert', value='$canary_cpu', equals='$changed_cpu'),
        dict(op='assert', value='$canary_data', equals='$changed_data'),
    ])


def _results(route, report):
    assert report['ok'] and report['error'] is None, report
    assert report['completed_steps'] == report['requested_steps'] == len(route['steps'])
    assert len(report['steps']) == len(route['steps'])
    result = {}
    for index, (step, observed) in enumerate(zip(route['steps'], report['steps'], strict=True)):
        assert observed['index'] == index and observed['op'] == step['op']
        assert observed['ok'] is True
        if 'as' in step:
            result[step['as']] = observed['result']
    return result


def _local_state(debug, project):
    """Observe export effects without a guest operation or a refreshed receipt."""
    return (debug.vm, debug.rpc, deepcopy(debug._process), debug._runtime_epoch,
            debug._checkpoint_epoch,
            [tuple(row) for row in project.db.execute(
                'SELECT id,sha256 FROM debug_artifacts WHERE run=? ORDER BY rowid',
                (debug.run_id,))],
            tuple(project.db.execute(
                'SELECT COUNT(*),MAX(sequence) FROM debug_events WHERE run=?',
                (debug.run_id,)).fetchone()))


def _json_script(debug, project, saved_route, route, directory):
    observed = []
    original = debug.script

    @wraps(original)
    def capture(*args, **kwargs):
        result = original(*args, **kwargs)
        observed.append(deepcopy(result))
        return result

    debug.script = capture
    workspace = DebugWorkspace()
    workspace.sessions[debug.run_id] = debug
    try:
        with output_policy_context(OutputPolicy(max_inline_bytes=4096,
                artifact_dir=directory / 'bounded-outputs')):
            reply = respond(dict(id='anchor_state', method='debug-script', params=dict(
                project=str(project.path), run=debug.run_id, context='machine',
                script_id=saved_route['script_id'], timeout_ms=SCRIPT_MS)), debugger=workspace)
            assert reply['ok'], reply
            assert len(observed) == 1
            canonical = observed[0]
            (directory / 'canonical-script-result.json').write_text(
                json.dumps(canonical, sort_keys=True, indent=2, allow_nan=False) + '\n')
            marker = reply['result']
            assert marker['format'] == 'fdisbull-output-ref-1'
            assert marker['complete'] is False and marker['retry_safe'] is False
            assert marker['execution']['returned'] is True and marker['execution']['ok'] is True
            # Script results have their own ok/completed_steps contract, not a
            # scene-wait complete flag. Delivery incompleteness is not a retry.
            assert marker['execution']['complete'] is None
            before = _local_state(debug, project)
            output = directory / 'checkpoint-script-export.json'
            exported = respond(dict(method='output-export', params=dict(
                artifact=marker['artifact']['id'], output=str(output))))
            assert exported['ok'], exported
            raw = output.read_bytes()
            assert len(raw) == marker['artifact']['bytes']
            assert hashlib.sha256(raw).hexdigest() == marker['artifact']['sha256']
            document = json.loads(raw)
            assert document == dict(id='anchor_state', ok=True, result=public_addresses(canonical))
            assert _local_state(debug, project) == before and len(observed) == 1
            native = _results(route, canonical)['restored']['process']
            public = _results(route, document['result'])['restored']['process']
            for field in ('start', 'end'):
                assert type(native['allocation'][field]) is int
                assert public['allocation'][field] == hex(native['allocation'][field])
            assert native['drivers']['headers']
            for header, projected in zip(native['drivers']['headers'],
                                         public['drivers']['headers'], strict=True):
                assert type(header['address']) is int
                assert projected['address'] == hex(header['address'])
            return canonical, dict(path=output.name, bytes=len(raw),
                                   sha256=hashlib.sha256(raw).hexdigest())
    finally:
        workspace.sessions.clear()
        debug.script = original


def _artifact(project, identifier):
    row = project.db.execute('SELECT * FROM debug_artifacts WHERE id=?',
                             (identifier,)).fetchone()
    assert row is not None
    value = dict(row)
    value['data'] = bytes(value['data'])
    assert hashlib.sha256(value['data']).hexdigest() == value['sha256']
    value['metadata'] = json.loads(value['metadata'])
    return value


def _persistence(project, saved_route, route, report, results):
    encoded = json.dumps(route, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    row = project.db.execute('SELECT * FROM debug_scripts WHERE id=?',
                             (saved_route['script_id'],)).fetchone()
    assert row is not None
    script = dict(row)
    assert script['script'].encode() == encoded
    assert script['sha256'] == saved_route['sha256'] == hashlib.sha256(encoded).hexdigest()
    assert script['version'] == saved_route['version']
    source = _artifact(project, report['script_artifact'])
    assert source['kind'] == 'script' and source['data'] == encoded
    assert source['sha256'] == report['script_sha256'] == saved_route['sha256']
    evidence = _artifact(project, report['artifact'])
    assert evidence['kind'] == 'script-result'
    assert json.loads(evidence['data']) == {key: value for key, value in report.items()
                                           if key != 'artifact'}
    saved = results['saved']
    state = _artifact(project, saved['artifact'])
    assert state['kind'] == 'state' and state['sha256'] == saved['sha256']
    assert state['metadata'] == saved['metadata']
    assert len(state['data']) == saved['size'] <= MAX_STATE_BYTES
    assert state['metadata']['format'] == PROCESS_FORMAT
    assert all(item['run'] == report['run'] for item in (source, evidence, state))
    for kind in ('script', 'script-result', 'state'):
        assert project.db.execute('SELECT COUNT(*) FROM debug_artifacts WHERE run=? AND kind=?',
                                   (report['run'], kind)).fetchone()[0] == 1
    events = [json.loads(row['evidence']) for row in project.db.execute(
        "SELECT evidence FROM debug_events WHERE run=? AND operation='load-state' ORDER BY sequence",
        (report['run'],))]
    assert events == [results['restored']]
    info = project.debug_state_info(saved['artifact'])
    assert info == project.debug_anchor_stone_info(saved['artifact'])
    assert info['sha256'] == saved['sha256'] and info['metadata']['format'] == PROCESS_FORMAT
    assert info['version'] == saved_route['version']
    with zipfile.ZipFile(io.BytesIO(state['data'])) as archive:
        assert archive.namelist() == ['machine.qcow2', 'process.json']
        sidecar = archive.read('process.json')
        assert hashlib.sha256(sidecar).hexdigest() == state['metadata']['sidecar_sha256']
        bundle = json.loads(sidecar)
    assert bundle['format'] == PROCESS_FORMAT and bundle['registers'] == results['before_cpu']
    assert bundle['version'] == saved_route['version']
    assert bundle['source_sha256'] == state['metadata']['source_sha256']
    assert bundle['version_sha256'] == state['metadata']['version_sha256']
    assert bundle['process']['capture_epoch'] != results['restored']['capture_epoch']
    expected_process = dict(bundle['process'], capture_epoch=results['restored']['capture_epoch'])
    assert results['restored']['process'] == expected_process
    return dict(script=script, source=source, evidence=evidence, state=state, info=info)


@pytest.mark.parametrize('case', ['state_anchor', 'anchor_state'])
def test_native_saved_process_checkpoint_script(tmp_path, case):
    deadline = time.monotonic() + CASE_SECONDS
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img',
                                runtime['FDISBULL_QEMU_DOS_MCOPY'])
    source_bytes, fixture = _fixture('com')
    binary = tmp_path / fixture['filename']
    binary.write_bytes(source_bytes)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    database = tmp_path / 'checkpoint.fdb'
    public_export = None
    with Project.create(database, binary, image='com') as project:
        with project.debugger(runtime['FDISBULL_QEMU_DOS'], tmp_path, backend='qemu-dos',
                dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
                dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
                qemu_clock='standard', qemu_audio='off', qemu_retrace='standard',
                qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
                qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'],
                boot_timeout_ms=_remaining(deadline, 15000)) as debug:
            initial_vm, original_lock = debug.vm, debug.vm.lock
            initial_process = deepcopy(debug.dos_process_info())
            initial_epoch, initial_checkpoint = debug._runtime_epoch, debug._checkpoint_epoch
            selected_version, selected_run = debug.version['id'], debug.run_id
            assert 'x-fdisbull-dos-checkpoint-status' in debug.vm.qmp_commands
            assert debug.capabilities['save_states'] is True
            assert initial_process['state'] == 'active'
            base = initial_process['source_mapping']['runtime_base']
            base = int(base, 0) if isinstance(base, str) else base
            data_address = base + fixture['data_offset']
            route = _route(case, data_address)
            saved_route = project.debug_save_script(case + '.json', route)
            with _body_deadline(debug, deadline):
                if case == 'state_anchor':
                    canonical = debug.script(script_id=saved_route['script_id'], timeout_ms=SCRIPT_MS)
                    (tmp_path / 'canonical-script-result.json').write_text(
                        json.dumps(canonical, sort_keys=True, indent=2, allow_nan=False) + '\n')
                else:
                    canonical, public_export = _json_script(debug, project, saved_route, route, tmp_path)
                results = _results(route, canonical)
                assert results['prepared']['complete'] is True
                assert results['prepared']['requested_count'] == results['prepared']['completed_count'] == 3
                assert all(results[name]['outcome'] == 'step' for name in ('prepared', 'changed', 'canary'))
                assert [results[name]['hex'] for name in (
                    'before_data', 'changed_data', 'restored_data', 'canary_data')] == [
                        '1111', '1211', '1111', '1211']
                assert results['before_cpu'] == results['restored_cpu']
                assert results['changed_cpu'] == results['canary_cpu']
                assert results['before_cpu'] != results['changed_cpu']
                for name, offset in (('before_cpu', 9), ('restored_cpu', 9),
                                     ('changed_cpu', 13), ('canary_cpu', 13)):
                    pc = results[name]['linear_pc']
                    assert (int(pc, 0) if isinstance(pc, str) else pc) == base + offset
                restored = results['restored']
                assert restored['artifact'] == results['saved']['artifact']
                assert restored['sha256'] == results['saved']['sha256']
                assert results['saved']['metadata']['source_sha256'] == source_hash
                assert results['saved']['metadata']['version_sha256'] == debug.version['sha256']
                assert restored['origin_run'] == selected_run
                assert restored['source_binding_restored'] is True
                assert restored['host_files_restored'] is False
                assert restored['checkpoint_epoch'] == debug._checkpoint_epoch == initial_checkpoint + 1
                assert restored['capture_epoch'] == debug._runtime_epoch != initial_epoch
                assert restored['process'] == debug._process
                assert debug.version['id'] == selected_version and debug.run_id == selected_run
                assert debug.metadata['source_sha256'] == source_hash
                assert canonical['run'] == selected_run and saved_route['version'] == selected_version
                replacement_vm = debug.vm
                assert replacement_vm is not initial_vm and debug.rpc is replacement_vm
                assert replacement_vm.lock is original_lock
                assert initial_vm.process.poll() == 0
                assert initial_vm.qmp is None and initial_vm.gdb is None
                assert initial_vm.temporary is None and initial_vm._qemu_image_proof is None
                assert not debug.closed and replacement_vm.process.poll() is None
                retained = _persistence(project, saved_route, route, canonical, results)
                witness = dict(format='fdisbull-native-checkpoint-script-witness-1', case=case,
                    route='python-saved-id' if case == 'state_anchor' else 'json-saved-id',
                    run=selected_run, version=selected_version, data_address=hex(data_address),
                    source_sha256=source_hash, boot_sha256=boot_hash,
                    baseline_sha256=disk['prepared_sha256'], script=saved_route,
                    canonical_result='canonical-script-result.json', public_export=public_export,
                    checkpoint=results['saved'], restore=restored,
                    owner_before=dict(pid=initial_vm.process.pid, reaped=True,
                                      returncode=initial_vm.process.poll(), capture_epoch=initial_epoch),
                    owner_after=dict(pid=replacement_vm.process.pid,
                                     capture_epoch=debug._runtime_epoch), stable_lock=True,
                    completed_steps=canonical['completed_steps'],
                    memory_hex=[results[name]['hex'] for name in (
                        'before_data', 'changed_data', 'restored_data', 'canary_data')])
        assert replacement_vm.process.poll() is not None
        witness['owner_after'].update(reaped=True, returncode=replacement_vm.process.poll())
    with Project(database) as reopened:
        assert _persistence(reopened, saved_route, route, canonical, results) == retained
    assert binary.read_bytes() == source_bytes
    assert digest(boot) == boot_hash and digest(disk['image']) == disk['prepared_sha256']
    _remaining(deadline, 1)
    witness['offline_reopen_verified'] = True
    (tmp_path / 'checkpoint-script-witness.json').write_text(
        json.dumps(witness, sort_keys=True, indent=2, allow_nan=False) + '\n')
