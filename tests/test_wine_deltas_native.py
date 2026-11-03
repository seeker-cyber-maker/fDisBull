"""Opt-in real PE delta undo, cached-machine refusal and native recovery."""
import hashlib
import json
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_wine_advanced import native_inputs


def projection(debug, address):
    registers = debug.registers()
    return ({key: registers[key] for key in ('general', 'rip', 'rflags', 'thread')},
            debug.memory(address, length=4)['hex'])


def test_real_pe_delta_undo_freezes_both_contexts_and_recovers_full_anchor(tmp_path):
    import lief
    from PIL import Image
    qemu, kernel, runtime, fixture = native_inputs()
    source = Path(fixture)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    binary = lief.PE.parse(str(source))
    base = binary.optional_header.imagebase
    exports = {item.name: base + item.address for item in binary.get_export().entries}
    path = tmp_path / 'deltas.fdb'
    with Project.create(path, source) as project:
        project.analyze(start=exports['checkpoint'], max_instructions=64)
        project.analyze(start=exports['write_only'], max_instructions=16)
        original_code = project.disassembly(address=exports['write_only'], version=1)['instructions']
        child = project.patch(exports['write_only'], '90')['version']
        with project.debugger(qemu, source.parent, kernel=kernel, initramfs=runtime,
                              files=[source.name], version=1) as debug:
            bp = debug.breakpoint(exports['checkpoint'])
            assert debug.run(timeout_ms=60000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(bp['breakpoint_id'])
            # Declared diagnostic setup, using the authored native oracle only.
            before = debug.registers()
            debug.write_registers({'rip': {'expected': before['rip'],
                'value': debug.runtime_base + exports['write_only'] - base}})
            initial = projection(debug, exports['counter'])
            assert initial[1] == '07000000'
            frame = debug.screenshot('before-delta.png')
            machine = debug.machine  # Retain the handle before partial rewind.
            started = debug.cpu_delta_start([{'address': exports['counter'], 'length': 4}], max_steps=3)
            info = project.debug_anchor_stone_info(started['anchor']['artifact'])
            assert started['anchor_bytes_used'] == info['size'] + info['native_size']
            states = []
            for _ in range(3):
                states.append(projection(debug, exports['counter']))
                debug.cpu_delta_record()
            assert projection(debug, exports['counter'])[1] == '11000000'
            history = debug.cpu_delta_status()
            assert debug.capture_code(exports['write_only'], length=8)['artifact']
            assert debug.cpu_delta_status() == history
            result = debug.cpu_delta_rewind()
            assert result['partial_restored'] and not result['full_machine_restored']
            assert projection(debug, exports['counter']) == states[2]
            frozen = projection(debug, exports['counter'])
            for operation in (
                lambda: debug.run(guest_ms=None), lambda: debug.trace(count=1),
                lambda: debug.screenshot(), lambda: debug.save_anchor_stone(),
                lambda: debug.capture_code(exports['write_only'], length=8),
                lambda: debug.layers([]),
                lambda: debug.write_registers({'rax': {'expected': frozen[0]['general']['rax'], 'value': 42}}),
                lambda: debug.cpu_delta_record(), lambda: machine.resume(),
                lambda: machine.step(), lambda: machine.write_memory(0, '01', expected_hex='00')):
                with pytest.raises(ValueError, match='frozen'):
                    operation()
                assert projection(debug, exports['counter']) == frozen
            debug.cpu_delta_rewind(count=2)
            assert projection(debug, exports['counter']) == initial
            old_process = debug.rpc.process
            debug.cpu_delta_recover()
            assert not debug.cpu_delta_status()['frozen']
            assert projection(debug, exports['counter']) == initial
            assert old_process.poll() is not None and debug.rpc.process.pid != old_process.pid
            assert debug.capture_code(exports['write_only'], length=8)['artifact']
            scripted = debug.script({'format': 'fdisbull-script-1', 'steps': [
                {'op': 'delta-start', 'ranges': [{'address': exports['counter'], 'length': 4}]},
                {'op': 'delta-record'},
                # The authored counter is a stand-in for an agent-declared RNG group.
                {'op': 'delta-rewind', 'policy': {'name': 'preserve-counter',
                    'preserve_memory': [{'address': exports['counter'], 'length': 4}],
                    'allow_partial_resume': True}},
                {'op': 'memory', 'address': exports['counter'], 'length': 4},
                {'op': 'delta-status'},
                {'op': 'save-anchor-stone', 'as': 'derived'},
                {'op': 'capture-code', 'address': exports['write_only'], 'length': 8},
                {'op': 'trace', 'count': 1},
                {'op': 'load-anchor-stone', 'artifact': '$derived.artifact'},
                {'op': 'delta-status'},
                {'op': 'delta-recover'}]}, timeout_ms=240000)
            assert scripted['ok'], scripted
            assert scripted['steps'][3]['result']['hex'] == '11000000'
            branch = scripted['steps'][4]['result']
            assert branch['execution_allowed'] and not branch['resume_safe'] and not branch['valid']
            derived = scripted['steps'][5]['result']
            captured = scripted['steps'][6]['result']
            doc = json.loads(bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                (captured['artifact'],)).fetchone()['data']))
            assert doc['identity']['delta_experiment']['policy']['name'] == 'preserve-counter'
            assert scripted['steps'][9]['result']['experiment'] == branch['experiment']
            assert debug.cpu_delta_status()['experiment'] is None
            assert projection(debug, exports['counter']) == initial
            debug.trace(count=1)
            assert projection(debug, exports['counter'])[1] == '11000000'
        assert project.disassembly(address=exports['write_only'], version=1)['instructions'] == original_code
        def code_byte(version):
            region = next(r for r in project.regions(version)
                          if r.start <= exports['write_only'] < r.start + len(r.data))
            return region.data[exports['write_only'] - region.start]
        assert code_byte(1) == 0xc7 and code_byte(child) == 0x90
    with Project(path) as reopened:
        assert reopened.debug_anchor_stone_info(started['anchor']['artifact'])['sha256'] == started['anchor']['sha256']
        exported = reopened.debug_export(frame['artifact'], tmp_path / 'stored-before.png')
        with Image.open(exported['output']) as image:
            assert image.size == (320, 200)
            image.verify()
        assert reopened.debug_anchor_stone_info(derived['artifact'])['metadata']['delta_experiment'] == branch['experiment']
        with reopened.debugger(qemu, source.parent, kernel=kernel, initramfs=runtime,
                               files=[source.name], version=1, state=derived['artifact']) as restored:
            status = restored.cpu_delta_status()
            assert status['experiment'] == branch['experiment']
            assert status['execution_allowed'] and not status['resume_safe']
            assert projection(restored, exports['counter'])[1] == '11000000'
            restored.trace(count=1)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
