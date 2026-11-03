"""Public DOS RAM and whole-machine restore in an actual paged PM guest."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_protected_mode_native import assemble_fixture


def test_real_paged_runtime_live_ram_edit_and_full_checkpoint(tmp_path):
    backend = os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        pytest.skip('Set FDISBULL_DOSBOX for native protected-mode acceptance')
    game = tmp_path / 'game'
    game.mkdir()
    binary = assemble_fixture(game)
    original = hashlib.sha256(binary.read_bytes()).hexdigest()
    report = {'fixture_sha256': original, 'backend_sha256':
              hashlib.sha256(Path(backend).read_bytes()).hexdigest(), 'stages': []}
    try:
        with Project.create(tmp_path / 'runtime.fdb', binary, image='com') as project:
            project.analyze(start='1000:0500', max_instructions=1)
            with project.debugger(backend, game) as debug:
                entry = debug.registers()
                base = int(entry['segments']['cs'], 16) * 16
                return_stop = debug.breakpoint('1000:0500')
                debug.run(guest_ms=150, timeout_ms=5000)
                registers = debug.registers()
                assert registers['cpu_mode'] == 'protected'
                assert registers['address_context']['paging_enabled'] is True
                assert registers['project_address'] is None
                report['stages'].append({'paged_context': registers['address_context']})
                for operation in (lambda: debug.memory('1000:0600', length=1),
                                  lambda: debug.breakpoint('1000:0500')):
                    with pytest.raises(ValueError, match='real mode'):
                        operation()
                trace = debug.trace('protected-fetches.json', count=8)
                row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                         (trace['artifact'],)).fetchone()
                events = json.loads(bytes(row[0]))['events']
                assert len(events) == 8
                assert all(event['cpu_mode'] == 'protected' and event['code_bits'] == 32
                           and event['project_address'] is None
                           and event['identity']['context'] is None for event in events)
                registers = debug.registers()
                report['stages'].append({'protected_trace_records': len(events),
                                         'DOS_source_projection': None})
                with pytest.raises(ValueError, match='Paged linear'):
                    debug.bind_runtime_memory('linear', base + 0x600, length=16,
                        expected_hex='01', provenance='authored stage counter')
                binding = debug.bind_runtime_memory('stage', base + 0x600,
                    space='physical', length=16, expected_hex='01',
                    provenance='authored COM stage/control/scratch layout')
                assert debug.runtime_memory('stage', offset=8, length=1)['hex'] == '00'
                state = debug.save_state('protected-paged.sav')
                state_info = project.debug_state_info(state['artifact'])
                assert {'CPU', 'Memory'} <= {part['name'] for part in state_info['components']}
                changed = debug.write_runtime_memory('stage', '5a', offset=8, expected_hex='00')
                assert changed['verified'] and changed['state_restore_used'] is False
                assert changed['kind'] == 'live-runtime-ram-edit'
                assert debug.runtime_memory('stage', offset=8, length=1)['hex'] == '5a'
                restored = debug.load_state(state['artifact'])
                assert restored['registers']['address_context'] == registers['address_context']
                for key in ('general', 'segments', 'instruction_pointer', 'flags', 'cpu_mode'):
                    assert restored['registers'][key] == registers[key]
                assert restored['intervention']['kind'] == 'full-native-checkpoint-restore'
                assert restored['intervention']['live_session_ram_edit'] is False
                assert restored['intervention']['edited_fork'] is False
                with pytest.raises(ValueError, match='invalidated'):
                    debug.runtime_memory(binding['id'], length=1)
                debug.bind_runtime_memory('fresh', base + 0x600, space='physical',
                    length=16, expected_hex='01', provenance='reobserved after full restore')
                assert debug.runtime_memory('fresh', offset=8, length=1)['hex'] == '00'
                report['stages'].append({'live_edit': changed,
                    'full_restore': restored['intervention'],
                    'checkpoint_sha256': state['sha256'],
                    'restored_cpu_and_context_verified': True,
                    'old_binding_invalidated': True, 'scratch_restored_hex': '00'})
                # A second continuation proves the native CPU/descriptor/paging
                # snapshot can execute again, beyond merely matching register text.
                debug.run(guest_ms=20, timeout_ms=5000)
                assert debug.registers()['cpu_mode'] == 'protected'
                assert debug.runtime_memory('fresh', length=1)['hex'] == '01'
                report['stages'].append({'resumed_paged_program': True})
                debug.write_runtime_memory('fresh', '01', offset=1, expected_hex='00')
                resumed = debug.run(timeout_ms=5000)
                assert resumed['outcome'] == 'breakpoint'
                assert resumed['session']['stop_reason']['breakpoint_id'] == return_stop['breakpoint_id']
                assert debug.registers()['cpu_mode'] == 'real'
                assert debug.registers()['ip'] == '0x00000500'
                # The old stage witness changes when the program itself updates
                # it: requalification is required after this real execution.
                with pytest.raises(ValueError, match='witness mismatch'):
                    debug.runtime_memory('fresh', length=1)
                debug.bind_runtime_memory('returned', base + 0x600, space='physical',
                    length=16, expected_hex='02', provenance='observed real-mode program return')
                report['stages'].append({'restored_program_returned_to_real_mode': True,
                                         'stage_hex': debug.runtime_memory('returned', length=1)['hex']})
            assert debug.closed and debug.rpc.process.poll() is not None
        assert hashlib.sha256(binary.read_bytes()).hexdigest() == original
        report['success'] = True
    finally:
        (tmp_path / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
