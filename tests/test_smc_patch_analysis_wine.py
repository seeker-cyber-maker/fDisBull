"""Real Wine self-modification -> temporal versions -> bounded patch analysis.

Run with the explicit native inputs used by test_layer_self_modifying_wine,
a fresh external evidence directory, and the heavy-job guard for the 4 GiB VM.
Original evidence is never opened or rewritten by this acceptance.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.pe_region_equivalence import expand_pe_contraction
from fdisbull.project import Project


def _inputs():
    names = ('FDISBULL_SMC_WINE_QEMU', 'FDISBULL_SMC_WINE_KERNEL',
             'FDISBULL_SMC_WINE_RUNTIME', 'FDISBULL_SMC_WINE_FIXTURE',
             'FDISBULL_SMC_WINE_EVIDENCE')
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        message = 'Missing real Wine SMC patch-analysis inputs: ' + ', '.join(missing)
        if os.environ.get('FDISBULL_REQUIRE_SMC_WINE') == '1':
            pytest.fail(message)
        pytest.skip(message)
    return [Path(os.environ[name]).resolve(strict=True) for name in names]


def _document(project, artifact):
    row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',
                             (artifact,)).fetchone()
    raw = bytes(row[0])
    assert hashlib.sha256(raw).hexdigest() == row[1]
    return json.loads(raw), raw


def _boundaries(left, right):
    fields = ('source_version', 'context', 'project_address')
    return [{
        'baseline': {key: left['events'][index]['identity'][key] for key in fields},
        'layer': {key: right['events'][index]['identity'][key] for key in fields},
        'evidence': 'Authored SMC target: captured MOV entry and native RET boundary; '
                    'exact stored captures and completed traces retained',
    } for index in (0, -1)]


def _replay_witness(left, right, witness):
    """Replay exact solver inputs on a separate CPU, not a new Wine observation."""
    import unicorn
    from unicorn import x86_const as reg
    outputs = []
    for trace in (left, right):
        cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        code = bytes.fromhex(trace['events'][0]['execution_bytes'])
        cpu.mem_map(0x1000, 4096)
        cpu.mem_write(0x1000, code)
        for name, value in witness['entry_general'].items():
            cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), int(value, 16))
        cpu.reg_write(reg.UC_X86_REG_EFLAGS, int(witness['entry_flags'], 16))
        cpu.emu_start(0x1000, 0x1000 + len(code), count=1)
        general = {name: hex(cpu.reg_read(getattr(reg, 'UC_X86_REG_' + name.upper())))
                   for name in witness['entry_general']}
        assert all(general[name] == value for name, value in witness['entry_general'].items()
                   if name != 'rax')
        assert cpu.reg_read(reg.UC_X86_REG_EFLAGS) == int(witness['entry_flags'], 16)
        outputs.append(general['rax'])
    assert outputs == [witness['differing_live_registers']['rax'][side]
                       for side in ('baseline', 'layer')]
    return {'provider': 'independent Unicorn CPU replay of captured MOV bytes',
            'exact_counterexample_inputs': True, 'outputs': outputs, 'status': 'passed'}


def test_real_wine_modified_code_recovers_changed_and_equivalent_behavior():
    qemu, kernel, runtime, source, evidence = _inputs()
    import lief
    pe = lief.PE.parse(str(source))
    base = pe.optional_header.imagebase
    exports = {entry.name: base + entry.address for entry in pe.get_export().entries}
    victim = exports['smc_target']
    assert bytes(pe.get_content_from_virtual_address(victim, 6)).hex() == 'b801000000c3'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    path = evidence / 'wine-smc-patch.fdb'
    if path.exists():
        pytest.fail('Use a fresh evidence directory; preserve earlier SMC patch evidence')
    report = {'format': 'fdisbull-native-smc-patch-acceptance-1', 'status': 'running',
              'source_sha256': source_hash, 'native': {}, 'versions': {},
              'scope': 'Real authored PE64 Wine/QEMU capture and completed MOV region; '
                       'debugger-directed probes and register seeds are explicit'}

    def save():
        (evidence / 'WINE-SMC-PATCH.json').write_text(json.dumps(report, indent=2) + '\n')

    original_artifacts = {}
    with Project.create(path, source) as project:
        project.analyze(max_instructions=4096)
        static = project.disassembly(victim, version=1, lines=2)['instructions']
        with project.debugger(str(qemu), str(source.parent), kernel=str(kernel),
                              initramfs=str(runtime), files=[source.name],
                              version=1, memory_mib=4096) as debug:
            report['runtime'] = debug.metadata
            before = debug.breakpoint(exports['smc_before_write'])
            after = debug.breakpoint(exports['smc_after_write'])
            done = debug.breakpoint(exports['smc_done'])
            first_call = debug.breakpoint(victim)

            def stop_at(address):
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'breakpoint', result
                assert debug.registers()['project_address'] == hex(address), result
                return result

            def memory(address, length):
                return debug.memory(address, length=length)['hex']

            def value(name):
                return int.from_bytes(bytes.fromhex(memory(exports[name], 4)), 'little')

            def redirect(address):
                registers = debug.registers()
                return debug.write_registers({'rip': {
                    'expected': registers['rip'], 'value': hex(address + debug.delta)}})

            def capture_and_trace(name, *, length, view, expected, result, directed=False):
                assert debug.registers()['project_address'] == hex(victim)
                registers = debug.registers()
                seed = '0xfedcba9876543210'
                edit = debug.write_registers({'rax': {
                    'expected': registers['general']['rax'], 'value': seed}})
                capture = debug.capture_code(victim, length=length, view=view,
                                             name=name + '-code.json')
                captured, captured_raw = _document(project, capture['artifact'])
                assert captured['hex'] == expected and captured['execution_proven'] is False
                trace = debug.trace(name + '-steps.json', count=2, timeout_ms=60000)
                document, trace_raw = _document(project, trace['artifact'])
                report['native'][name] = {'capture': capture, 'trace': trace,
                    'debugger_directed_probe': directed, 'incoming_rax_seed': seed,
                    'register_edit': edit, 'observed_result': debug.registers()['general']['rax']}
                save()
                assert document['complete'] and len(document['events']) == 2, document
                first, boundary = document['events']
                assert first['execution_bytes'] == expected[:-2]
                assert boundary['execution_bytes'] == 'c3'
                assert first['project_address'] == hex(victim)
                assert boundary['project_address'] == hex(victim + length - 1)
                assert all(event['observation']['instruction_completed'] is True
                           for event in document['events'])
                pre, post = first['registers'], boundary['registers']
                assert int(pre['general']['rax'], 16) == int(seed, 16)
                assert int(post['general']['rax'], 16) == result
                assert int(debug.registers()['general']['rax'], 16) == result
                assert pre['thread'] == post['thread']
                assert pre['rflags'] == post['rflags']
                assert {key: val for key, val in pre['general'].items() if key != 'rax'} == {
                    key: val for key, val in post['general'].items() if key != 'rax'}
                original_artifacts[capture['artifact']] = captured_raw
                original_artifacts[trace['artifact']] = trace_raw
                return capture, trace, document

            stop_at(victim)
            debug.delete_breakpoint(first_call['breakpoint_id'])
            original = capture_and_trace('original', length=6, view='ram',
                                         expected='b801000000c3', result=1)
            stop_at(exports['smc_before_write'])
            assert value('first_value') == 1 and value('data_read') == 1
            assert memory(victim, 6) == 'b801000000c3'
            stop_at(exports['smc_after_write'])
            assert memory(victim, 6) == 'b802000000c3'
            assert value('second_value') == 0
            # The marker has a real pending call return. This extra directed
            # probe returns to main, which then makes its ordinary second call.
            report['modified_probe_redirect'] = redirect(victim)
            modified = capture_and_trace('self-modified', length=6, view='ram',
                                         expected='b802000000c3', result=2, directed=True)
            stop_at(exports['smc_done'])
            assert value('first_value') == 1 and value('second_value') == 2
            report['natural_main_results'] = {'data_read': value('data_read'),
                'first_value': value('first_value'), 'second_value': value('second_value')}

            # A wider, equivalent MOV needs a later RET boundary. Put the RET
            # into unused physical padding: execution-layer RETs are outside
            # this backend's supported relocation profile. Original RET+5 stays.
            padding = memory(victim + 7, 1)
            return_layer = debug.layer_patch('explicit wider-probe return boundary',
                victim + 7, expected_hex=padding, data_hex='c3', kind='ram')
            wide_layer = debug.layer_patch('same constant with full-width MOV', victim,
                expected_hex=memory(victim, 7), data_hex='48c7c002000000', kind='execute')
            report['equivalent_probe_layers'] = [return_layer, wide_layer]
            report['equivalent_probe_redirect'] = redirect(victim)
            equivalent = capture_and_trace('equivalent-wide-mov', length=8, view='execute',
                expected='48c7c002000000c3', result=2, directed=True)
            assert memory(victim, 6) == 'b802000000c3'
            debug.layers([])
            assert memory(victim + 7, 1) == padding
            assert project.disassembly(victim, version=1, lines=2)['instructions'] == static
            assert len(project.versions()) == 1

        # Promotion is explicit and happens only after the native controller
        # closes; its new default version must not affect a live source session.
        for name, (capture, trace, _) in zip(('original', 'self-modified', 'equivalent-wide-mov'),
                                           (original, modified, equivalent), strict=True):
            promoted = project.debug_promote_code(capture['artifact'], label=name,
                                                  max_instructions=16)
            assert promoted['temporal']['execution_proven'] is False
            report['versions'][name] = promoted
        save()

    with Project(path) as project:
        def compare(left_name, right_name, left, right):
            return project.debug_compare_runtime_code(
                report['versions'][left_name]['version'], report['versions'][right_name]['version'],
                left[1]['artifact'], right[1]['artifact'], contract={},
                correspondence=_boundaries(left[2], right[2]))

        changed = compare('original', 'self-modified', original, modified)
        report['changed_behavior'] = changed
        save()
        assert changed['format'] == 'fdisbull-runtime-patch-analysis-1'
        assert changed['regional']['status'] == 'different', changed
        witness = changed['regional']['counterexample']
        assert witness['differing_live_registers'] == {
            'rax': {'baseline': '0x1', 'layer': '0x2'}}
        assert witness['differing_memory_bytes'] == {}
        assert witness['masked_flags']['baseline'] == witness['masked_flags']['layer']
        report['difference_witness_replay'] = _replay_witness(original[2], modified[2], witness)
        equal = compare('self-modified', 'equivalent-wide-mov', modified, equivalent)
        report['equivalent_behavior'] = equal
        save()
        assert equal['regional']['status'] == 'equivalent_under_contract', equal
        contraction = equal['regional']['contraction']
        expanded = expand_pe_contraction(contraction, modified[2], equivalent[2])
        assert expanded == {'baseline': modified[2], 'layer': equivalent[2]}
        report['contraction_reexpanded'] = True
        assert equal['regional']['contract']['live_flags'] == 0xffffffff
        for artifact, original_raw in original_artifacts.items():
            assert _document(project, artifact)[1] == original_raw
        assert project.disassembly(victim, version=1, lines=2)['instructions'] == static
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report.update(status='passed', original_artifacts_preserved=True,
                      original_static_version_preserved=True, original_source_preserved=True,
                      reopened_comparisons=True)
        save()
