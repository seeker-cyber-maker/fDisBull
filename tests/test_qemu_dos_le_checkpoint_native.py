"""Authored LE source checkpoints and capture-only histories across owners.

The real DOS bootstrap, protected code and relocation witnesses come from the
existing MZ/BW/MZ/LE fixture. Guest instructions produce every counter change;
no debugger memory/register writes manufacture source admission or placement.
QEMU, firmware, qemu-img, NASM, mcopy and FreeDOS remain separate native inputs.
"""
from copy import deepcopy
import filecmp
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from support.qemu_dos_le_fixture import build_fixture
from test_qemu_dos_process_native import launch_options, process_record, process_runtime


CHECKPOINT_FORMAT = 'fdisbull-qemu-dos-le-checkpoint-1'
HISTORY_FORMAT = 'fdisbull-qemu-dos-le-history-1'
HISTORY_BUDGET = 256 * 1024 * 1024


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _checkpoint_tool():
    selected = os.environ.get('FDISBULL_QEMU_IMG')
    if not selected:
        required = ('FDISBULL_REQUIRE_QEMU_DOS', 'FDISBULL_REQUIRE_QEMU_DOS_OS',
                    'FDISBULL_REQUIRE_QEMU_LAYERS')
        if any(os.environ.get(name) == '1' for name in required):
            pytest.fail('FDISBULL_QEMU_IMG is required for native LE checkpoints/history')
        pytest.skip('Supply FDISBULL_QEMU_IMG for native LE checkpoints/history')
    tool = Path(selected).expanduser().resolve(strict=True)
    assert tool.is_file() and os.access(tool, os.X_OK)
    return tool


def _counter(debug, fixture):
    return int.from_bytes(bytes.fromhex(debug.memory(
        fixture['counter_address'], length=4, space='physical')['hex']), 'little')


def _state(debug, fixture):
    binding = debug.dos_source_binding()
    assert binding['live'] and binding['state'] == 'qualified-stopped'
    assert binding['last_observation']['qualified'] is True
    return dict(cpu=deepcopy(debug.registers()), counter=_counter(debug, fixture),
                binding=deepcopy(binding), site=deepcopy(binding['last_observation']))


def _assert_restore(debug, restored, previous_owner, previous_binding, expected, fixture):
    assert previous_owner.poll() is not None and debug.vm.process is not previous_owner
    assert debug.vm.process.poll() is None and not debug.closed
    assert restored['machine_state_restored'] is True
    assert restored['source_binding_restored'] is False
    assert restored['protected_source_rebound'] is True
    assert restored['le_source_checkpoint_restored'] is True
    companion = restored['le_source_checkpoint']
    assert restored['artifact'] == companion['machine']['artifact']
    assert companion['charged_size'] == companion['size'] + companion['machine']['size']
    binding = debug.dos_source_binding()
    assert binding == restored['protected_source_binding']
    assert binding['live'] and binding['state'] == 'qualified-stopped'
    assert binding['binding_id'] not in (previous_binding.get('binding_id'),
                                      expected['binding']['binding_id'])
    assert binding['capture_epoch'] == restored['capture_epoch']
    assert binding['capture_epoch'] not in (previous_binding.get('capture_epoch'),
                                         expected['binding']['capture_epoch'])
    assert binding['last_observation']['qualified'] is True
    for field in ('source_location', 'instruction_sha256', 'linear_pc'):
        assert binding['last_observation'][field] == expected['site'][field]
    actual = debug.registers()
    for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
        assert actual[field] == expected['cpu'][field], field
    assert _counter(debug, fixture) == expected['counter']
    mapping = debug.dos_process_info()['source_mapping']
    assert mapping['live'] is False and mapping['live_ranges'] == []
    with pytest.raises(ValueError, match='retired the DOS source binding'):
        debug.save_state('le-does-not-restore-mz-authority.qcow2')
    assert debug.dos_source_binding()['binding_id'] == binding['binding_id']
    return binding


def _trace_one(project, debug, name, directory, mnemonic):
    receipt = debug.trace(name + '.json', count=1, bits=32, timeout_ms=10000)
    assert receipt['metadata']['complete']
    destination = directory / (name + '-warm.json')
    project.debug_export(receipt['artifact'], destination)
    document = json.loads(destination.read_bytes())
    assert len(document['events']) == 1 and document['window']['closed']
    event = document['events'][0]
    assert event['project_address'] is None
    identity = event['identity']
    assert identity['source_location']['source_view'] == 'embedded-le'
    canonical = dict(location=identity['source_location'],
        instruction_sha256=identity['source_instruction_sha256'],
        context=identity['context'], execution_bytes=event['execution_bytes'])
    query = project.event_trace_query(receipt['artifact'],
                                     predicate=dict(kind='mnemonic', equals=mnemonic))
    assert query['matched_count'] == 1
    return dict(artifact=receipt['artifact'], path=destination,
                canonical=canonical, query=query, mnemonic=mnemonic)


def _assert_companion(project, receipt):
    row = project.db.execute('SELECT kind,data,sha256 FROM debug_artifacts WHERE id=?',
                             (receipt['artifact'],)).fetchone()
    assert row['kind'] == 'le-source-state'
    data = bytes(row['data'])
    assert len(data) == receipt['size']
    assert hashlib.sha256(data).hexdigest() == row['sha256'] == receipt['sha256']
    assert json.loads(data)['format'] == CHECKPOINT_FORMAT
    machine = receipt['machine']
    native = project.db.execute('SELECT kind,sha256,fdb_length(data) AS size FROM debug_artifacts WHERE id=?',
                                (machine['artifact'],)).fetchone()
    assert native['kind'] == 'machine-state'
    assert native['sha256'] == machine['sha256'] and native['size'] == machine['size']
    assert receipt['charged_size'] == receipt['size'] + machine['size']
    info = project.debug_state_info(receipt['artifact'])
    assert info['metadata']['format'] == CHECKPOINT_FORMAT
    assert info['sha256'] == receipt['sha256']


@pytest.mark.parametrize('profile', ['standard', 'virtual'])
def test_native_le_checkpoint_capture_history_branch_and_cold_restore(tmp_path, process_runtime, profile):
    runtime = process_runtime
    tool = _checkpoint_tool()
    fixture = build_fixture(tmp_path, runtime['nasm'])
    original_paths = (fixture['path'], runtime['executable'], runtime['boot_image'], tool)
    originals = {str(path): _digest(path) for path in original_paths}
    disk = prepare_dos_baseline(runtime['boot_image'], tmp_path / 'le-checkpoint-baseline.img',
        runtime['mcopy'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    options = launch_options(runtime, disk, qemu_checkpoint_tool=str(tool), qemu_clock=profile)
    database = tmp_path / 'le-checkpoint-history.fdb'
    traces = []; stored_exports = {}; companions = {}

    with Project.create(database, fixture['path']) as project:
        with project.debugger(runtime['executable'], tmp_path, **options) as debug:
            process_record(debug)
            point = debug.breakpoint(fixture['code_base'])
            arrived = debug.run(timeout_ms=10000)
            assert arrived['outcome'] == 'breakpoint', arrived
            debug.delete_breakpoint(point['breakpoint_id'])
            initial = debug.dos_source_bind(expected_source_sha256=fixture['sha256'])
            explicit_a = debug.save_le_source_state('explicit-le-A.json', timeout_ms=60000)
            _assert_companion(project, explicit_a)
            a = _state(debug, fixture)
            assert a['binding']['binding_id'] != initial['binding_id']
            assert a['counter'] == 0 and int(a['cpu']['linear_pc'], 0) == fixture['code_base']
            companions[explicit_a['artifact']] = explicit_a

            started = debug.le_rewind_start(max_steps=3, max_bytes=HISTORY_BUDGET, timeout_ms=60000)
            node_a = started['cursor']
            # Saves refresh source admission. Compare source sites and CPU,
            # rather than pretending the first live handle was persisted.
            root_a = _state(debug, fixture)
            assert root_a['site']['source_location'] == a['site']['source_location']
            progressed = debug.trace_until(dict(kind='register', register='eax', equals=3),
                max_steps=100, timeout_ms=15000, name='le-progress-to-B.json')
            assert progressed['matched'] and progressed['exact_stop'] and progressed['source_window_closed']
            assert int(debug.registers()['linear_pc'], 0) == fixture['code_base'] + fixture['store_offset']
            assert _counter(debug, fixture) == 2
            captured_b = debug.le_rewind_record(advance='capture', count=1, timeout_ms=60000)
            node_b = captured_b['cursor']; history = captured_b['history']
            b = _state(debug, fixture)
            assert b['counter'] == 2

            previous = debug.dos_source_binding(); owner = debug.vm.process
            restored = debug.load_le_source_state(explicit_a['artifact'], timeout_ms=60000)
            _assert_restore(debug, restored, owner, previous, a, fixture)
            traces.append(_trace_one(project, debug, 'le-A-after-explicit-restore', tmp_path, 'mov'))
            assert traces[-1]['canonical']['location'] == a['site']['source_location']

            previous = debug.dos_source_binding(); owner = debug.vm.process
            restored = debug.le_rewind(history=history, node=node_b, timeout_ms=60000)
            _assert_restore(debug, restored['restore'], owner, previous, b, fixture)
            traces.append(_trace_one(project, debug, 'le-B-after-history-restore', tmp_path, 'mov'))
            assert traces[-1]['canonical']['location'] == b['site']['source_location']
            assert _counter(debug, fixture) == 3  # The actual restored offset32 store executed.

            previous = debug.dos_source_binding(); owner = debug.vm.process
            restored = debug.le_rewind(history=history, node=node_a, timeout_ms=60000)
            _assert_restore(debug, restored['restore'], owner, previous, root_a, fixture)
            stepped = debug.step(timeout_ms=10000)
            assert stepped['outcome'] == 'step' and stepped['timed_out'] is False
            assert int(debug.registers()['linear_pc'], 0) == fixture['code_base'] + 5
            assert _counter(debug, fixture) == 0
            branch = debug.le_rewind_record(advance='capture', count=1, timeout_ms=60000)
            node_c = branch['cursor']; history = branch['history']
            assert len({node_a, node_b, node_c}) == 3
            c = _state(debug, fixture)
            status = debug.le_rewind_status(history=history)
            assert status['cursor'] == node_c and status['captures_used'] == 3
            assert set(status['node_ids']) == {node_a, node_b, node_c}
            row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (history,)).fetchone()
            manifest = json.loads(bytes(row['data']))
            assert manifest['format'] == HISTORY_FORMAT
            nodes = {node['id']: node for node in manifest['nodes']}
            assert nodes[node_a]['parent'] is None
            assert nodes[node_b]['parent'] == nodes[node_c]['parent'] == node_a
            assert status['state_bytes_used'] == sum(node['checkpoint']['size'] for node in nodes.values())
            assert status['state_bytes_used'] <= HISTORY_BUDGET
            for node in nodes.values():
                checkpoint = node['checkpoint']
                assert checkpoint['size'] == checkpoint['manifest_size'] + checkpoint['machine']['size']
                receipt = dict(artifact=checkpoint['artifact'], sha256=checkpoint['sha256'],
                    size=checkpoint['manifest_size'], charged_size=checkpoint['size'], machine=checkpoint['machine'])
                _assert_companion(project, receipt)
                companions[receipt['artifact']] = receipt
            for receipt in companions.values():
                for reference in (receipt, receipt['machine']):
                    artifact = reference['artifact']
                    if artifact not in stored_exports:
                        path = tmp_path / ('warm-' + artifact + '.bin')
                        project.debug_export(artifact, path)
                        assert _digest(path) == reference['sha256']
                        stored_exports[artifact] = path
            history_path = tmp_path / 'warm-le-history.json'
            project.debug_export(history, history_path); stored_exports[history] = history_path
            traces.append(_trace_one(project, debug, 'le-C-after-branch-capture', tmp_path, 'nop'))
            assert traces[-1]['canonical']['location'] == c['site']['source_location']
            final_owner = debug.vm.process
        assert final_owner.poll() is not None

    with Project(database) as project:
        # These readers and exports run with no live debugger at all.
        for receipt in companions.values():
            _assert_companion(project, receipt)
        for artifact, warm in stored_exports.items():
            cold = tmp_path / ('cold-' + artifact + '.bin')
            project.debug_export(artifact, cold)
            assert filecmp.cmp(warm, cold, shallow=False)
        for trace in traces:
            cold = tmp_path / ('cold-' + trace['artifact'] + '.json')
            project.debug_export(trace['artifact'], cold)
            assert filecmp.cmp(trace['path'], cold, shallow=False)
            assert project.event_trace_query(trace['artifact'],
                predicate=dict(kind='mnemonic', equals=trace['mnemonic'])) == trace['query']
        with project.debugger(runtime['executable'], tmp_path, **options) as debug:
            attached = debug.le_rewind_start(history=history, timeout_ms=60000)
            assert attached['valid'] is False and attached['cursor'] is None
            for node, expected, reference in ((node_b, b, traces[1]), (node_a, root_a, traces[0])):
                previous = debug.dos_source_binding(); owner = debug.vm.process
                restored = debug.le_rewind(history=history, node=node, timeout_ms=60000)
                _assert_restore(debug, restored['restore'], owner, previous, expected, fixture)
                fresh_trace = _trace_one(project, debug, 'cold-selected-' + node, tmp_path,
                                         reference['mnemonic'])
                assert fresh_trace['canonical'] == reference['canonical']
            previous = debug.dos_source_binding(); owner = debug.vm.process
            restored = debug.load_le_source_state(explicit_a['artifact'], timeout_ms=60000)
            _assert_restore(debug, restored, owner, previous, a, fixture)
            final_owner = debug.vm.process
        assert final_owner.poll() is not None

    assert {path: _digest(path) for path in originals} == originals
    assert _digest(disk['image']) == disk['prepared_sha256']
