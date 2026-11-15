"""Real DOS CPU writes, fetch-overlay guards and checkpoint-backed SMC rewind.

Select FDISBULL_DOSBOX to run; use an external pytest --basetemp and TMPDIR for
native evidence. No original game or supplied legacy executable is executed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import sys

import pytest

from fdisbull.project import Project
from native_fixture import prepare_native_fixture
from test_dos_loader import mz_file


# Authored 16-bit module, with unambiguous instruction boundaries:
# 0000 CLI; 0001 PUSH CS; 0002 POP DS;
# 0003 MOV byte [0021h],44h; 0008 JMP 0020h;
# 0020 MOV AX,1111h; 0023 JMP 0023h.
# The CPU changes the low byte of the immediate, so RAM becomes MOV AX,1144h.
MODULE = bytearray(512)
MODULE[:10] = bytes.fromhex('fa0e1fc606210044eb16')
MODULE[0x20:0x25] = bytes.fromhex('b81111ebfe')
MODULE = bytes(MODULE)
TARGET = '1000:0020'
IMMEDIATE = '1000:0021'
LOOP = '1000:0023'


def _bytes(project, artifact):
    row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
    assert row is not None
    data = bytes(row['data'])
    assert hashlib.sha256(data).hexdigest() == row['sha256']
    return data


def _capture(project, debug, name, *, view='ram'):
    captured = debug.capture_code(TARGET, length=3, view=view, name=name)
    raw = _bytes(project, captured['artifact'])
    return captured, json.loads(raw), raw


def _cpu(debug):
    registers = debug.registers()
    return {key: registers[key] for key in ('general', 'segments', 'instruction_pointer', 'flags')}


def _static(project):
    return [tuple(row) for row in project.db.execute('SELECT * FROM instructions WHERE version=1 ORDER BY address')]


def _write_receipt(name, document):
    parent = os.environ.get('FDISBULL_SMC_EVIDENCE_ROOT')
    if parent:
        root = Path(parent)
        assert root.is_absolute() and root.is_dir()
        (root / name).write_text(json.dumps(document, sort_keys=True, indent=2) + '\n')


@pytest.fixture
def dos_smc(tmp_path, monkeypatch):
    configured = os.environ.get('FDISBULL_DOSBOX')
    if not configured:
        pytest.skip('Set FDISBULL_DOSBOX for actual DOS self-modifying-code acceptance')
    backend = Path(configured).expanduser().resolve(strict=True)
    game = tmp_path / 'game'
    game.mkdir()
    target = game / 'SMC.EXE'
    target.write_bytes(mz_file(MODULE, ss=0, sp=0x200))
    original = target.read_bytes()
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path / 'objects'))
    project_path = tmp_path / 'self-modifying.fdb'
    with Project.create(project_path, target) as project:
        project.analyze(max_instructions=32)
        static = _static(project)
        assert project.disassembly(TARGET, lines=1)['instructions'][0]['bytes'] == 'b81111'
        with project.debugger(backend, game) as debug:
            assert debug.rpc.capabilities.get('code_layers') == 'normal_core_real_mode_guarded_fetch_v1'
            assert debug.rpc.capabilities.get('save_states') is True
            process = debug.rpc.process
            prepare_native_fixture(debug)
            identity = {
                'backend': str(backend), 'backend_sha256': hashlib.sha256(backend.read_bytes()).hexdigest(),
                'backend_protocol': debug.rpc.capabilities.get('protocol_version'),
                'code_layers': debug.rpc.capabilities['code_layers'], 'save_states': True,
                'host': {'system': platform.system(), 'machine': platform.machine(), 'python': sys.version},
                'fdisbull_version': debug.metadata['fdisbull_version'],
                'runtime_profile': debug.metadata['runtime_profile'],
                'source_sha256': hashlib.sha256(original).hexdigest(),
                'project': str(project_path), 'run': debug.run_id,
            }
            yield project, debug, identity
        assert process.poll() is not None, 'Owned DOS backend was not reaped'
        assert target.read_bytes() == original
        assert _static(project) == static
        assert len(project.versions()) == 1


def test_cpu_write_stales_overlay_then_disable_rebase_and_keep_changed_preserve_history(dos_smc):
    project, debug, identity = dos_smc
    entry = debug.save_state('smc-entry.sav')
    first, first_doc, first_raw = _capture(project, debug, 'smc-original-ram.json')
    assert first_doc['hex'] == 'b81111' and first_doc['execution_proven'] is False
    old = debug.layer_patch('original-immediate-theory', IMMEDIATE,
                            expected_hex='1111', data_hex='2222', kind='execute')['layer']
    overlay, overlay_doc, overlay_raw = _capture(project, debug, 'smc-original-overlay.json', view='execute')
    assert overlay_doc['hex'] == 'b82222'
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '1111'
    before_ax = int(debug.registers()['general']['eax'], 16)
    watch = debug.breakpoint(IMMEDIATE, access='w', length=1)
    write_stop = debug.run(timeout_ms=3000, fast_forward=True)
    assert write_stop['outcome'] == 'breakpoint', write_stop
    access = write_stop['session']['stop_reason']['data_access']
    assert access['project_instruction'] == '0x10003'
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '4411'
    assert int(debug.registers()['instruction_pointer'], 16) == 8
    for breakpoint in watch['breakpoints']:
        debug.delete_breakpoint(breakpoint['breakpoint_id'])
    conflict = debug.run(timeout_ms=3000, fast_forward=True)
    assert conflict['outcome'] == 'layer_conflict', conflict
    assert int(debug.registers()['general']['eax'], 16) == before_ax
    assert int(debug.registers()['instruction_pointer'], 16) == 0x20
    stale = debug.code(TARGET, length=3, view='execute')
    assert stale['overlay_valid'] is False
    assert debug.layers()['active'] == [old]
    debug.layers([])
    changed, changed_doc, changed_raw = _capture(project, debug, 'smc-changed-ram.json')
    assert changed_doc['hex'] == 'b84411'
    after_write = debug.save_state('smc-after-write.sav')
    debug.breakpoint(LOOP)
    resumed = debug.run(timeout_ms=3000, fast_forward=True)
    assert resumed['outcome'] == 'breakpoint'
    assert int(debug.registers()['general']['eax'], 16) == 0x1144

    debug.load_state(after_write['artifact'])
    rebased = debug.layer_patch('changed-immediate-theory', IMMEDIATE,
                                expected_hex='4411', data_hex='5555', kind='execute')['layer']
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '4411'
    assert debug.code(TARGET, length=3)['hex'] == 'b85555'
    trace = debug.trace('smc-rebased-execution.json', count=4, timeout_ms=3000, fast_forward=True)
    assert trace['metadata']['run']['outcome'] == 'breakpoint'
    assert int(debug.registers()['general']['eax'], 16) == 0x5555
    trace_doc = json.loads(_bytes(project, trace['artifact']))
    fetched = next(event for event in trace_doc['events'] if event['project_address'] == '0x10020')
    assert fetched['ram_bytes'].startswith('b84411')
    assert fetched['execution_bytes'].startswith('b85555')
    assert fetched['active_layers'] == [rebased]
    debug.layers([])

    # A visible RAM theory gets a real CPU write while active. Removal must not
    # overwrite the modified low byte; its unchanged high byte is restored.
    debug.load_state(entry['artifact'])
    ram = debug.layer_patch('ram-immediate-theory', IMMEDIATE,
                            expected_hex='1111', data_hex='3333', kind='ram')['layer']
    assert debug.run(timeout_ms=3000, fast_forward=True)['outcome'] == 'breakpoint'
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '4433'
    assert int(debug.registers()['general']['eax'], 16) == 0x3344
    with pytest.raises(ValueError, match='changed memory'):
        debug.layers([])
    assert debug.layers()['active'] == [ram]
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '4433'
    cleared = debug.layers([], conflict='keep_changed')
    assert cleared['preserved_changed_bytes'] == [{'address': '0x10021', 'layer_byte': 0x33, 'observed_byte': 0x44}]
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '4411'
    assert debug.layers()['active'] == []
    assert project.disassembly(TARGET, lines=1)['instructions'][0]['bytes'] == 'b81111'
    assert _bytes(project, first['artifact']) == first_raw
    assert _bytes(project, overlay['artifact']) == overlay_raw
    assert _bytes(project, changed['artifact']) == changed_raw
    events = project.debug_events(debug.run_id)['events']
    assert any(event['operation'] == 'layer-transition' and
               event['evidence'].get('preserved_changed_bytes') == cleared['preserved_changed_bytes'] for event in events)
    _write_receipt('dos-smc-layer-views.json', {
        'format': 'fdisbull-dos-smc-acceptance-1', 'status': 'passed', 'identity': identity,
        'cpu_write': {'instruction': access['project_instruction'], 'changed_immediate': '4411', 'stop': write_stop['outcome']},
        'stale_execution_layer': {'outcome': conflict['outcome'], 'ip': '0x20', 'alternate_instruction_not_executed': True},
        'resumed_ram_ax': '0x1144', 'rebased_execute_ax': '0x5555',
        'ram_layer_ax': '0x3344', 'keep_changed': cleared['preserved_changed_bytes'],
        'captures': [{'artifact': item['artifact'], 'sha256': item['sha256']} for item in (first, overlay, changed, trace)],
        'static_source_and_earlier_captures_unchanged': True,
        'scope': 'Actual authored DOS real-mode normal-core execution; code snapshots alone are not execution proof',
    })


def test_native_checkpoint_rewind_restores_cpu_written_instruction_and_prior_capture(dos_smc):
    project, debug, identity = dos_smc
    original, original_doc, original_raw = _capture(project, debug, 'rewind-original-code.json')
    assert original_doc['hex'] == 'b81111'
    debug.rewind_start(max_steps=8)
    debug.rewind_record(count=3)
    before = _cpu(debug)
    assert int(before['instruction_pointer'], 16) == 3
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '1111'
    record = debug.rewind_record(count=1)
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '4411'
    assert int(debug.registers()['instruction_pointer'], 16) == 8
    changed, changed_doc, changed_raw = _capture(project, debug, 'rewind-changed-code.json')
    assert changed_doc['hex'] == 'b84411'
    restored = debug.rewind(count=1)
    assert _cpu(debug) == before
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '1111'
    assert _bytes(project, original['artifact']) == original_raw
    assert _bytes(project, changed['artifact']) == changed_raw
    # A fresh future executes the CPU store again while the old artifacts remain.
    debug.rewind_record(count=1)
    assert debug.memory(IMMEDIATE, length=2)['hex'] == '4411'
    assert _bytes(project, changed['artifact']) == changed_raw
    status = debug.rewind_status()
    assert status['valid'] and status['cursor'] == 4
    assert status['disk_restore'] is False
    assert status['instruction_completion'] == 'unknown'
    _write_receipt('dos-smc-rewind.json', {
        'format': 'fdisbull-dos-smc-rewind-acceptance-1', 'status': 'passed', 'identity': identity,
        'before_store_ip': '0x3', 'after_store_ip': '0x8', 'changed_immediate': '4411',
        'rewound_immediate': '1111', 'cpu_registers_restored': True,
        'checkpoint': restored['target_checkpoint'], 'record_count': record['recorded_count'],
        'earlier_captures_unchanged': True, 'new_future_repeats_store': True,
        'scope': status,
    })
