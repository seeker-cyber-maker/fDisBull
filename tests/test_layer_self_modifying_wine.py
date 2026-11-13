"""Real Wine/QEMU SMC acceptance; no mocked execution or external game inputs.

Run under memory-run for the 4 GiB VM. Runtime, target, evidence and temporary
files must be explicitly selected outside Git; missing native inputs skip by
default and fail when FDISBULL_REQUIRE_SMC_WINE=1.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project


def _inputs():
    names = ('FDISBULL_SMC_WINE_QEMU', 'FDISBULL_SMC_WINE_KERNEL',
             'FDISBULL_SMC_WINE_RUNTIME', 'FDISBULL_SMC_WINE_FIXTURE', 'FDISBULL_SMC_WINE_EVIDENCE')
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        message = 'Missing real Wine SMC inputs: ' + ', '.join(missing)
        if os.environ.get('FDISBULL_REQUIRE_SMC_WINE') == '1':
            pytest.fail(message)
        pytest.skip(message)
    return [Path(os.environ[name]).resolve(strict=True) for name in names]


def _artifact(project, identifier):
    row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
    raw = bytes(row[0])
    assert hashlib.sha256(raw).hexdigest() == row[1]
    return json.loads(raw)


def test_real_wine_smc_layers_relocated_writes_and_checkpoint_restore():
    qemu, kernel, runtime, source, evidence = _inputs()
    import lief
    from iced_x86 import Decoder
    image_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    pe = lief.PE.parse(str(source))
    base = pe.optional_header.imagebase
    exports = {s.name: base + s.address for s in pe.get_export().entries}
    victim, writer = exports['smc_target'], exports['smc_writer']
    assert victim // 4096 != writer // 4096
    assert bytes(pe.get_content_from_virtual_address(victim, 6)).hex() == 'b801000000c3'
    assert bytes(pe.get_content_from_virtual_address(exports['smc_self_writer'], 8)).hex() == 'c605ffffffff01c3'
    assert all((exports[name] - exports['smc_writer_immediate']) not in range(-15, 16)
               for name in ('smc_begin', 'smc_before_write', 'smc_after_write', 'smc_done'))
    path = evidence / 'wine-smc.fdb'
    if path.exists():
        pytest.fail('Use a fresh evidence directory; preserve earlier Wine SMC evidence')
    report = {'format': 'fdisbull-native-wine-smc-1', 'source_sha256': image_hash,
              'scope': 'Authored PE64 on real Wine/QEMU; Microsoft Windows unqualified', 'cases': []}

    def save():
        (evidence / 'WINE-SMC.json').write_text(json.dumps(report, indent=2) + '\n')

    with Project.create(path, source) as project:
        project.analyze(max_instructions=4096)
        static = project.disassembly(address=victim, lines=2)['instructions']
        versions = project.db.execute('SELECT count(*) FROM versions').fetchone()[0]
        with project.debugger(str(qemu), str(source.parent), kernel=str(kernel), initramfs=str(runtime),
                              files=[source.name], version=1, memory_mib=4096) as debug:
            report['runtime'] = debug.metadata
            start = debug.breakpoint(exports['smc_begin'])
            assert debug.run(timeout_ms=60000)['outcome'] == 'breakpoint'
            initial_regs = debug.registers()
            original_capture = debug.capture_code(victim, length=6, view='ram')
            original_data = _artifact(project, original_capture['artifact'])
            anchor = debug.save_state('smc-before-mutation.sav')
            report['checkpoint'] = {'artifact': anchor['artifact'], 'sha256': anchor['sha256'],
                                    'native_size': anchor['native_size']}
            report['original_capture'] = original_capture
            save()

            def memory(address, length=1):
                return debug.memory(address, length=length)['hex']

            def value(name):
                return int.from_bytes(bytes.fromhex(memory(exports[name], 4)), 'little')

            def stop_at(identifier):
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'breakpoint', result
                assert debug.registers()['project_address'] == hex(exports[identifier]), result
                return result

            def redirect(address):
                regs = debug.registers()
                debug.write_registers({'rip': {'expected': regs['rip'], 'value': hex(address + debug.delta)}})

            modes = ('baseline', 'execute_target', 'ram_target', 'execute_writer', 'same_value_write')
            for index, mode in enumerate(modes):
                case = {'mode': mode, 'status': 'running'}
                report['cases'].append(case)
                save()
                if index:
                    restored = debug.load_state(anchor['artifact'])
                    regs = debug.registers()
                    assert all(regs[k] == initial_regs[k] for k in ('rip', 'rflags', 'general', 'thread'))
                    assert debug.layers()['active'] == []
                    case['restored'] = restored
                assert memory(victim, 6) == 'b801000000c3'
                assert value('first_value') == value('second_value') == value('data_read') == 0
                before = debug.breakpoint(exports['smc_before_write'])
                after = debug.breakpoint(exports['smc_after_write'])
                done = debug.breakpoint(exports['smc_done'])
                if mode in ('execute_target', 'same_value_write'):
                    layer = debug.layer_patch(mode, victim + 1, expected_hex='01000000',
                                              data_hex='03000000', kind='execute')
                    case['layer'] = layer
                elif mode == 'ram_target':
                    case['layer'] = debug.layer_patch(mode, victim + 1, expected_hex='01000000',
                                                     data_hex='03000000', kind='ram')
                elif mode == 'execute_writer':
                    case['layer'] = debug.layer_patch(mode, exports['smc_writer_immediate'],
                                                     expected_hex='02', data_hex='04', kind='execute')
                if mode == 'same_value_write':
                    case['writer_layer'] = debug.layer_patch('same-value writer', exports['smc_writer_immediate'],
                                                            expected_hex='02', data_hex='01', kind='ram')
                stop_at('smc_before_write')
                assert value('first_value') == (3 if mode in ('execute_target', 'ram_target', 'same_value_write') else 1)
                assert value('data_read') == (3 if mode == 'ram_target' else 1)
                old = 3 if mode == 'ram_target' else 1
                assert memory(victim + 1) == f'{old:02x}'
                new = 4 if mode == 'execute_writer' else 1 if mode == 'same_value_write' else 2
                if mode == 'baseline':
                    # No guard/watch on the victim page: independently exercise
                    # a warmed instruction, guest write and guest cache flush.
                    case['unwatched_write_control'] = True
                else:
                    watch = debug.breakpoint(victim + 1, access='w', length=1)
                    stopped = debug.run(timeout_ms=60000)
                    assert stopped['outcome'] == 'watchpoint', stopped
                    assert memory(victim + 1) == f'{old:02x}'  # Wine watch is before the write.
                    case['before_write_watch'] = stopped
                    debug.delete_breakpoint(watch['breakpoint_id'])
                    trace = debug.trace(mode + '-guest-write.json', count=1, timeout_ms=60000)
                    document = _artifact(project, trace['artifact'])
                    assert document['complete'] and len(document['events']) == 1, document
                    event = document['events'][0]
                    assert event['project_address'] == hex(writer)
                    assert event['execution_bytes'].endswith(f'{new:02x}')
                    assert memory(victim + 1) == f'{new:02x}'
                    if mode == 'execute_writer':
                        assert event['ram_bytes'].endswith('02') and event['native_address']
                        moved = Decoder(64, bytes.fromhex(event['native_bytes']), ip=int(event['native_address'], 16)).decode()
                        assert moved.ip_rel_memory_address == victim + debug.delta + 1
                    case['completed_write_trace'] = trace
                stop_at('smc_after_write')
                assert memory(victim + 1) == f'{new:02x}'
                assert value('second_value') == 0
                if mode == 'execute_target':
                    with pytest.raises(DebuggerError, match='RAM guard changed before execution') as error:
                        debug.run(timeout_ms=60000)
                    case['stale_guard'] = str(error.value)
                    assert not debug.closed and value('second_value') == 0
                    assert debug.registers()['project_address'] == hex(victim)
                    debug.layers([])
                elif mode == 'ram_target':
                    with pytest.raises(ValueError, match='conflicts with changed memory'):
                        debug.layers([])
                    case['preserved'] = debug.layers([], conflict='keep_changed')
                    assert case['preserved']['preserved_changed_bytes']
                stop_at('smc_done')
                assert value('second_value') == (3 if mode == 'same_value_write' else new)
                case.update(first=value('first_value'), second=value('second_value'),
                            guest_data_read=value('data_read'), physical_code=memory(victim, 6))
                debug.layers([])
                if mode == 'execute_target':
                    rebased = debug.layer_patch('rebase after SMC', victim + 1, expected_hex='02000000',
                                                data_hex='04000000', kind='execute')
                    redirect(victim)
                    step = debug.trace('rebased-smc.json', count=1, timeout_ms=60000)
                    assert int(debug.registers()['general']['rax'], 16) == 4
                    assert memory(victim, 6) == 'b802000000c3'
                    case['rebase'] = {'layer': rebased, 'trace': step}
                    debug.layers([])
                if mode == 'execute_writer':
                    self_writer = exports['smc_self_writer']
                    own = debug.layer_patch('modify own original immediate', exports['smc_self_writer_immediate'],
                                            expected_hex='01', data_hex='02', kind='execute')
                    redirect(self_writer)
                    step = debug.trace('own-guard-write.json', count=1, timeout_ms=60000)
                    own_document = _artifact(project, step['artifact'])
                    own_event = own_document['events'][0]
                    assert own_event['ram_bytes'] == 'c605ffffffff01'
                    assert own_event['execution_bytes'] == 'c605ffffffff02'
                    moved = Decoder(64, bytes.fromhex(own_event['native_bytes']), ip=int(own_event['native_address'], 16)).decode()
                    assert moved.ip_rel_memory_address == self_writer + debug.delta + 6
                    assert memory(self_writer, 8) == 'c605ffffffff02c3'
                    redirect(self_writer)
                    with pytest.raises(DebuggerError, match='RAM guard changed before execution'):
                        debug.run(timeout_ms=60000)
                    case['self_write'] = {'layer': own, 'trace': step, 'original_ram': memory(self_writer, 8)}
                    debug.layers([])
                assert _artifact(project, original_capture['artifact']) == original_data
                assert project.disassembly(address=victim, lines=2)['instructions'] == static
                assert project.db.execute('SELECT count(*) FROM versions').fetchone()[0] == versions
                case['status'] = 'passed'
                save()
            debug.load_state(anchor['artifact'])
            assert memory(victim, 6) == 'b801000000c3'
            assert memory(exports['smc_self_writer'], 8) == 'c605ffffffff01c3'
            assert debug.layers()['active'] == []
            report['final_checkpoint_restored'] = True
            report['source_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == image_hash
            assert report['source_unchanged']
            report['status'] = 'passed'
            save()
    with Project(path) as reopened:
        assert _artifact(reopened, original_capture['artifact']) == original_data
        assert reopened.disassembly(address=victim, lines=2)['instructions'] == static
