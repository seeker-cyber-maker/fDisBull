"""Native known-source SMC function paths, stack effects and temporal analysis.

Select the new self_modifying_function_wine.S fixture through the existing
FDISBULL_SMC_WINE_* inputs, a fresh external evidence directory and the heavy
job guard. This test never opens the prior SMC evidence or launches a compiler.
"""
import base64
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from fdisbull.pe_function_recovery import expand_pe_function_contraction


MASK64 = (1 << 64) - 1
OUTPUT_SEED = 0x8877665544332211
SPILL_SEED = 0x0f1e2d3c4b5a6978
RBX_SEED = 0x76543210fedcba98
RAX_SEED = 0xfedcba9876543210
EDITABLE_FLAGS = 0xcd5


def _inputs():
    names = ('FDISBULL_SMC_WINE_QEMU', 'FDISBULL_SMC_WINE_KERNEL',
             'FDISBULL_SMC_WINE_RUNTIME', 'FDISBULL_SMC_WINE_FIXTURE',
             'FDISBULL_SMC_WINE_EVIDENCE')
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        message = 'Missing real Wine SMC function inputs: ' + ', '.join(missing)
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


def _route(code, start, function_end, caller_boundary, x):
    """Decode actual captured bytes and follow this authored unsigned guard.

    This supplies the native trace budget, not a substitute for the native
    trace or the symbolic path-domain/coverage analysis.
    """
    from iced_x86 import Decoder, FlowControl, Mnemonic
    raw = bytes.fromhex(code)
    address = start
    addresses = []
    for _ in range(64):
        instruction = Decoder(64, raw[address - start:address - start + 15],
                              ip=address).decode()
        assert not instruction.is_invalid
        addresses.append(address)
        if address == caller_boundary:
            assert instruction.mnemonic == Mnemonic.NOP
            return addresses
        assert start <= address < function_end
        if instruction.flow_control == FlowControl.CONDITIONAL_BRANCH:
            assert instruction.mnemonic == Mnemonic.JA
            address = instruction.near_branch_target if x > 10 else instruction.next_ip
        elif instruction.flow_control == FlowControl.UNCONDITIONAL_BRANCH:
            address = instruction.near_branch_target
        elif instruction.flow_control == FlowControl.RETURN:
            address = caller_boundary
        else:
            assert instruction.flow_control == FlowControl.NEXT
            address = instruction.next_ip
    raise AssertionError('Authored function path exceeded its bounded decode budget')


def _verify_source_spec(recovery, key, contract):
    """Check recovered expressions against the independently stated source rule."""
    import z3 as z
    registers = {n: z.BitVec('entry_' + n, 64) for n in recovery['cases'][0]['registers']}
    cells = {a + offset: z.BitVec(f'entry_ram_{a + offset:x}', 8)
             for row in contract['memory_ranges'] for a in [int(row['address'], 16)]
             for offset in range(row['length'])}
    declarations = {str(v): v for v in list(registers.values()) + list(cells.values())}
    declarations['entry_flags'] = z.BitVec('entry_flags', 32)
    assumptions = [registers[n] == int(v, 16) for n, v in contract['entry_registers'].items()]
    for row in contract['entry_memory']:
        a = int(row['address'], 16)
        assumptions += [cells[a + i] == b for i, b in enumerate(bytes.fromhex(row['hex']))]
    x, stack, out = registers['rcx'], int(contract['entry_registers']['rsp'], 16), int(contract['entry_registers']['rdx'], 16)
    target = int(recovery['call_frame']['return_target'], 16)
    accepted = z.ULE(x, 10)
    def parse(text, sort):
        result = z.Const('source_spec_result', sort)
        expression = z.parse_smt2_string('(assert (= source_spec_result ' + text + '))',
                                        decls=declarations | {'source_spec_result': result})[0]
        return expression.arg(1)
    for case in recovery['cases']:
        guard = parse(case['guard'], z.BoolSort())
        writes_output = len(case['ordered_accesses']) == 4
        assert len(case['ordered_accesses']) in (3, 4)
        deviations = [guard != (accepted if writes_output else z.Not(accepted))]
        expected_result = z.If(accepted, x + key, z.BitVecVal(MASK64, 64))
        for name, text in case['registers'].items():
            expected = expected_result if name == 'rax' else registers[name] + 8 if name == 'rsp' else registers[name]
            deviations.append(parse(text, z.BitVecSort(64)) != expected)
        for address, text in case['memory_bytes'].items():
            a = int(address, 16)
            expected = (z.If(accepted, z.Extract((a - out) * 8 + 7, (a - out) * 8, x + key), cells[a])
                        if out <= a < out + 8 else
                        z.Extract((a - stack + 8) * 8 + 7, (a - stack + 8) * 8, registers['rbx'])
                        if stack - 8 <= a < stack else cells[a])
            deviations.append(parse(text, z.BitVecSort(8)) != expected)
        accesses = [('write', stack - 8, registers['rbx'])]
        if writes_output:
            accesses.append(('write', out, x + key))
        accesses += [('read', stack - 8, registers['rbx']), ('read', stack, z.BitVecVal(target, 64))]
        for actual, (kind, address, value) in zip(case['ordered_accesses'], accesses, strict=True):
            assert actual['kind'] == kind and actual['width'] == 8
            deviations += [parse(actual['address'], z.BitVecSort(64)) != address,
                           parse(actual['value'], z.BitVecSort(64)) != value]
        # Guard equality is checked without assuming the guard. Effects are
        # checked on the entire source-defined branch domain, not sample x=3/11.
        solver = z.Solver()
        solver.add(*assumptions, deviations[0])
        assert solver.check() == z.unsat
        solver = z.Solver()
        solver.add(*assumptions, guard, z.Or(*deviations[1:]))
        assert solver.check() == z.unsat
    return {'status': 'proved_under_entry_contract', 'cases': len(recovery['cases']),
            'checked': ['unsigned branch domains', 'return value', 'all selected GPRs and stack advance',
                        'output/spill/return-slot final bytes', 'ordered memory addresses/values'],
            'flags': 'Checked against actual native steps and retained live in encoding-equivalence proof'}


def _replay_function_witness(report, witness):
    """Independent CPU replay through RET at the exact symbolic witness state."""
    import unicorn
    from unicorn import x86_const as reg
    results = []
    for name in ('original', 'self-modified'):
        epoch = report['epochs'][name]
        case = epoch['cases'][witness['baseline_path' if name == 'original' else 'layer_path']]
        start = int(case['decoded_path'][0], 16)
        caller = int(case['decoded_path'][-1], 16)
        code = bytes.fromhex(epoch['captured_code'])
        cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        pages = {address & ~4095 for address in range(start, start + len(code))}
        pages |= {int(address, 16) & ~4095 for address in witness['entry_memory']}
        for page in pages:
            cpu.mem_map(page, 4096)
        cpu.mem_write(start, code)
        for address, byte in witness['entry_memory'].items():
            cpu.mem_write(int(address, 16), bytes([int(byte, 16)]))
        for name_, value in witness['entry_general'].items():
            cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name_.upper()), int(value, 16))
        cpu.reg_write(reg.UC_X86_REG_EFLAGS, int(witness['entry_flags'], 16))
        completed = []
        def boundary(guest, address, size, _):
            completed.append(address)
            if address == caller:
                guest.emu_stop()
        cpu.hook_add(unicorn.UC_HOOK_CODE, boundary)
        cpu.emu_start(start, start + len(code), count=256)
        assert cpu.reg_read(reg.UC_X86_REG_RIP) == caller
        results.append({'general': {n: hex(cpu.reg_read(getattr(reg, 'UC_X86_REG_' + n.upper())))
                                    for n in witness['entry_general']},
                        'flags': hex(cpu.reg_read(reg.UC_X86_REG_EFLAGS) & 0xffffffff),
                        'memory': {a: hex(bytes(cpu.mem_read(int(a, 16), 1))[0]) for a in witness['entry_memory']},
                        'return_target': hex(caller), 'instructions': len(completed) - 1})
    a, b = results
    assert {n: {'baseline': a['general'][n], 'layer': b['general'][n]} for n in a['general']
            if a['general'][n] != b['general'][n]} == witness['differing_live_registers']
    assert {p: {'baseline': a['memory'][p], 'layer': b['memory'][p]} for p in a['memory']
            if a['memory'][p] != b['memory'][p]} == witness['differing_memory_bytes']
    assert {'baseline': a['flags'], 'layer': b['flags']} == witness['masked_flags']
    return {'status': 'passed', 'provider': 'independent Unicorn CPU',
            'exact_counterexample_inputs': True, 'results': results}


def test_real_wine_smc_function_paths_recover_guarded_return_and_memory_behavior():
    qemu, kernel, runtime, source, evidence = _inputs()
    import lief
    pe = lief.PE.parse(str(source))
    base = pe.optional_header.imagebase
    exports = {entry.name: base + entry.address for entry in pe.get_export().entries}
    function = exports['smc_function']
    function_end = exports['smc_function_end']
    gate, caller = exports['smc_gate'], exports['smc_gate_return']
    constant, immediate = exports['smc_constant'], exports['smc_constant_immediate']
    output = exports['smc_output']
    assert function < constant < function_end == gate < caller
    assert immediate == constant + 1
    span = caller + 1 - function
    assert 1 <= span <= 65536
    original_code = bytes(pe.get_content_from_virtual_address(function, span)).hex()
    slot_offset = constant - function
    assert original_code[slot_offset * 2:(slot_offset + 10) * 2] == 'b8010000009090909090'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    path = evidence / 'wine-smc-function.fdb'
    if path.exists():
        pytest.fail('Use a fresh evidence directory; preserve earlier function evidence')
    report = {'format': 'fdisbull-native-smc-function-acceptance-1', 'status': 'running',
        'source_sha256': source_hash, 'source_contract': {
            'arguments': 'unsigned x in RCX; valid private output pointer in RDX',
            'accepted': 'x <= 10: return and store x+epoch_constant',
            'rejected': 'x > 10: return UINT64_MAX and preserve output bytes',
            'stack': 'spill/restore RBX at entry_RSP-8; RET consumes actual caller return word'},
        'assistance': 'Explicit register seeds, marker/gate redirects and guarded resets of '
                      'declared RAM; no checkpoint or deterministic replay claim',
        'epochs': {}, 'versions': {}}

    def save():
        (evidence / 'WINE-SMC-FUNCTION.json').write_text(json.dumps(report, indent=2) + '\n')

    artifact_bytes = {}
    with Project.create(path, source) as project:
        project.analyze(max_instructions=4096)
        static = project.disassembly(function, version=1, lines=64)['instructions']
        with project.debugger(str(qemu), str(source.parent), kernel=str(kernel),
                              initramfs=str(runtime), files=[source.name],
                              version=1, memory_mib=4096) as debug:
            report['runtime'] = debug.metadata
            for marker in ('smc_before_write', 'smc_after_write', 'smc_done'):
                debug.breakpoint(exports[marker])
            common_general = None
            common_flags = None
            entry_rsp = None

            def stop_at(address):
                stopped = debug.run(timeout_ms=60000)
                assert stopped['outcome'] == 'breakpoint', stopped
                assert debug.registers()['project_address'] == hex(address), stopped
                return stopped

            def main_word(address):
                return int.from_bytes(bytes.fromhex(debug.memory(address, length=8)['hex']), 'little')

            def raw_word(address):
                result = debug.call('read', {'address': address, 'length': 8})
                raw = base64.b64decode(result['data_base64'], validate=True)
                assert len(raw) == 8
                return raw.hex()

            def guarded_reset(address, data_hex, purpose):
                # Test-only intervention at the three explicitly declared words.
                # The two stack words are outside main-image memory authority.
                expected = raw_word(address)
                if expected != data_hex:
                    debug.call('write', {'address': address, 'data_hex': data_hex})
                assert raw_word(address) == data_hex
                return {'address': hex(address), 'expected_hex': expected, 'data_hex': data_hex,
                        'readback_verified': True, 'purpose': purpose,
                        'mechanism': 'paused native RPC read/guarded-write/readback; authored test only'}

            def edit_context(target_general, target_rip, flags):
                current = debug.registers()
                changes = {name: {'expected': current['general'][name], 'value': value}
                           for name, value in target_general.items()
                           if int(current['general'][name], 16) != int(value, 16)}
                if int(current['rip'], 16) != target_rip:
                    changes['rip'] = {'expected': current['rip'], 'value': hex(target_rip)}
                adjusted = (int(current['rflags'], 16) & ~EDITABLE_FLAGS) | (flags & EDITABLE_FLAGS)
                if adjusted != int(current['rflags'], 16):
                    changes['rflags'] = {'expected': current['rflags'], 'value': hex(adjusted)}
                return debug.write_registers(changes) if changes else {'registers': [], 'memory': []}

            def snapshot(function_rsp):
                current_rsp = int(debug.registers()['general']['rsp'], 16)
                stack = debug.stack_memory(offset=function_rsp - 8 - current_rsp, length=16)
                assert int(stack['runtime_address'], 16) == function_rsp - 8
                assert len(bytes.fromhex(stack['hex'])) == 16
                return [
                    {'address': hex(output + debug.delta),
                     'hex': debug.memory(output, length=8)['hex']},
                    {'address': hex(function_rsp - 8), 'hex': stack['hex'][:16]},
                    {'address': hex(function_rsp), 'hex': stack['hex'][16:]},
                ]

            def collect_epoch(name, epoch_constant, *, view):
                nonlocal common_general, common_flags, entry_rsp
                marker = debug.registers()
                marker_rsp = int(marker['general']['rsp'], 16)
                function_rsp = marker_rsp - 8
                if entry_rsp is None:
                    entry_rsp = function_rsp
                    common_general = dict(marker['general'])
                    common_flags = int(marker['rflags'], 16)
                assert function_rsp == entry_rsp
                output_runtime = output + debug.delta
                original_ram = {address: raw_word(address) for address in
                                (output_runtime, function_rsp - 8, function_rsp)}
                row = {'constant': epoch_constant, 'view': view, 'marker_registers': marker,
                       'paths': [], 'cases': [], 'held_out_native': [], 'restoration': []}
                report['epochs'][name] = row
                save()

                def begin_probe(x):
                    resets = [
                        guarded_reset(output_runtime, OUTPUT_SEED.to_bytes(8, 'little').hex(),
                                      'set declared output sentinel'),
                        guarded_reset(function_rsp - 8, SPILL_SEED.to_bytes(8, 'little').hex(),
                                      'set declared local-spill observation'),
                        guarded_reset(function_rsp, original_ram[function_rsp],
                                      'restore pre-gate return-slot bytes; real CALL writes its return word'),
                    ]
                    general = {**common_general, 'rsp': hex(marker_rsp), 'rax': hex(RAX_SEED),
                               'rbx': hex(RBX_SEED), 'rcx': hex(x), 'rdx': hex(output_runtime)}
                    edits = edit_context(general, gate + debug.delta, common_flags)
                    call = debug.trace(name + '-gate-' + str(x) + '.json', count=1, timeout_ms=60000)
                    call_doc, call_raw = _document(project, call['artifact'])
                    artifact_bytes[call['artifact']] = call_raw
                    assert call_doc['complete'] and len(call_doc['events']) == 1
                    event = call_doc['events'][0]
                    assert event['project_address'] == hex(gate)
                    assert event['observation']['instruction_completed'] is True
                    registers = debug.registers()
                    assert registers['project_address'] == hex(function)
                    assert int(registers['general']['rsp'], 16) == function_rsp
                    entry = snapshot(function_rsp)
                    assert entry[-1]['hex'] == (caller + debug.delta).to_bytes(8, 'little').hex()
                    return {'input': hex(x), 'ram_resets': resets, 'register_edits': edits,
                            'gate_call': call, 'entry_registers': registers, 'memory': {'entry': entry}}

                for x, label in ((3, 'accepted'), (11, 'rejected')):
                    case = begin_probe(x)
                    if 'capture' not in row:
                        capture = debug.capture_code(function, length=span, view=view,
                                                      name=name + '-function-code.json')
                        captured, captured_raw = _document(project, capture['artifact'])
                        artifact_bytes[capture['artifact']] = captured_raw
                        assert captured['execution_proven'] is False
                        expected_slot = ('b8' + epoch_constant.to_bytes(4, 'little').hex() + '9090909090'
                                         if view == 'ram' else '48b80200000000000000')
                        assert captured['hex'][slot_offset * 2:(slot_offset + 10) * 2] == expected_slot
                        row['capture'] = capture
                        row['captured_code'] = captured['hex']
                    route = _route(row['captured_code'], function, function_end, caller, x)
                    expected_count = 10 if x > 10 else 13 if view == 'execute' else 18
                    assert len(route) == expected_count
                    trace = debug.trace(name + '-' + label + '.json', count=len(route), timeout_ms=60000)
                    document, raw = _document(project, trace['artifact'])
                    artifact_bytes[trace['artifact']] = raw
                    case.update(trace=trace, decoded_path=[hex(address) for address in route],
                                exit_registers=debug.registers())
                    case['memory']['exit'] = snapshot(function_rsp)
                    row['cases'].append(case)
                    row['paths'].append({'trace': trace['artifact'], 'memory': case['memory']})
                    save()
                    assert document['complete'] and len(document['events']) == len(route), document
                    assert [event['project_address'] for event in document['events']] == [hex(a) for a in route]
                    assert all(event['observation']['instruction_completed'] is True
                               for event in document['events'])
                    assert document['events'][-2]['instruction']['mnemonic'] == 'ret'
                    assert document['events'][-1]['project_address'] == hex(caller)
                    assert document['events'][-1]['execution_bytes'] == '90'
                    registers = case['exit_registers']
                    result = MASK64 if x > 10 else x + epoch_constant
                    assert int(registers['general']['rax'], 16) == result
                    assert int(registers['general']['rsp'], 16) == marker_rsp
                    assert int(registers['general']['rbx'], 16) == RBX_SEED
                    assert all(registers['general'][reg] == case['entry_registers']['general'][reg]
                               for reg in common_general if reg not in ('rax', 'rsp'))
                    exit_memory = {item['address']: item['hex'] for item in case['memory']['exit']}
                    expected_output = OUTPUT_SEED if x > 10 else result
                    assert exit_memory[hex(output_runtime)] == expected_output.to_bytes(8, 'little').hex()
                    assert exit_memory[hex(function_rsp - 8)] == RBX_SEED.to_bytes(8, 'little').hex()
                    assert exit_memory[hex(function_rsp)] == (caller + debug.delta).to_bytes(8, 'little').hex()

                # Additional boundary inputs are native observations, separate
                # from the two complete traces supplied to symbolic coverage.
                boundary = debug.breakpoint(caller)
                for x in (0, 10, MASK64):
                    case = begin_probe(x)
                    case['stop'] = stop_at(caller)
                    registers = debug.registers()
                    expected = MASK64 if x > 10 else x + epoch_constant
                    actual_output = main_word(output)
                    case.update(exit_registers=registers, result=registers['general']['rax'],
                                output=hex(actual_output))
                    row['held_out_native'].append(case)
                    save()
                    assert int(registers['general']['rax'], 16) == expected
                    assert int(registers['general']['rbx'], 16) == RBX_SEED
                    assert int(registers['general']['rsp'], 16) == marker_rsp
                    assert actual_output == (OUTPUT_SEED if x > 10 else expected)
                debug.delete_breakpoint(boundary['breakpoint_id'])
                for address, raw in original_ram.items():
                    row['restoration'].append(guarded_reset(address, raw, 'restore original marker RAM'))
                row['marker_context_restoration'] = edit_context(
                    marker['general'], int(marker['rip'], 16), int(marker['rflags'], 16))
                assert all(raw_word(address) == raw for address, raw in original_ram.items())
                assert debug.registers()['project_address'] == marker['project_address']
                save()

            stop_at(exports['smc_before_write'])
            assert main_word(exports['first_value']) == 4 and main_word(output) == 4
            collect_epoch('original', 1, view='ram')
            stop_at(exports['smc_after_write'])
            assert debug.memory(immediate, length=4)['hex'] == '02000000'
            assert main_word(exports['first_value']) == 4 and main_word(exports['second_value']) == 0
            collect_epoch('self-modified', 2, view='ram')
            layer = debug.layer_patch('equivalent full-width constant window', constant,
                expected_hex=debug.memory(constant, length=10)['hex'],
                data_hex='48b80200000000000000', kind='execute')
            report['equivalent_control_layer'] = layer
            collect_epoch('equivalent-wide-mov', 2, view='execute')
            debug.layers([])
            assert debug.memory(constant, length=10)['hex'] == 'b8020000009090909090'
            stop_at(exports['smc_done'])
            report['natural_main_results'] = {name: hex(main_word(exports[name])) for name in
                ('first_value', 'second_value', 'rejected_value', 'rejected_output')}
            assert report['natural_main_results'] == {'first_value': '0x4', 'second_value': '0x5',
                'rejected_value': hex(MASK64), 'rejected_output': hex(OUTPUT_SEED)}
            assert project.disassembly(function, version=1, lines=64)['instructions'] == static
            assert len(project.versions()) == 1
            report['contract'] = {'entry_registers': {'rsp': hex(entry_rsp), 'rdx': hex(output + debug.delta)},
                'entry_memory': [{'address': hex(entry_rsp),
                                  'hex': (caller + debug.delta).to_bytes(8, 'little').hex()}],
                'memory_model': 'private_ordinary_ram', 'memory_observation': 'ordered',
                'memory_ranges': [{'address': hex(address), 'length': 8} for address in
                                  (output + debug.delta, entry_rsp - 8, entry_rsp)]}
            save()

        # Offline promotion cannot alter the version selected by a live native
        # controller. Original artifacts and source version remain authoritative.
        for name, row in report['epochs'].items():
            promoted = project.debug_promote_code(row['capture']['artifact'], label=name + ' function',
                                                  max_instructions=128)
            assert promoted['temporal']['execution_proven'] is False
            report['versions'][name] = promoted
        save()

    with Project(path) as project:
        def compare(left, right):
            return project.debug_compare_runtime_functions(
                report['versions'][left]['version'], report['versions'][right]['version'],
                report['epochs'][left]['paths'], report['epochs'][right]['paths'],
                contract=report['contract'], timeout_ms=5000)

        report['changed_behavior'] = compare('original', 'self-modified')
        save()
        assert report['changed_behavior']['format'] == 'fdisbull-runtime-function-analysis-1'
        assert report['changed_behavior']['function']['status'] == 'different', report['changed_behavior']
        report['source_specification'] = {}
        changed_function = report['changed_behavior']['function']
        for name, key, field in (('original', 1, 'baseline_recovery'), ('self-modified', 2, 'layer_recovery')):
            report['source_specification'][name] = _verify_source_spec(changed_function[field], key, report['contract'])
        report['difference_witness_replay'] = _replay_function_witness(report, changed_function['counterexample'])
        report['equivalent_behavior'] = compare('self-modified', 'equivalent-wide-mov')
        save()
        assert report['equivalent_behavior']['function']['status'] == 'equivalent_under_contract', report['equivalent_behavior']
        equal_function = report['equivalent_behavior']['function']
        report['source_specification']['equivalent-wide-mov'] = _verify_source_spec(
            equal_function['layer_recovery'], 2, report['contract'])
        def documents(name):
            return [{'trace': _document(project, p['trace'])[0], 'memory': p['memory']}
                    for p in report['epochs'][name]['paths']]
        a, b = documents('self-modified'), documents('equivalent-wide-mov')
        assert expand_pe_function_contraction(equal_function['contraction'], a, b) == {'baseline': a, 'layer': b}
        report['function_contraction_reexpanded'] = True
        for artifact, raw in artifact_bytes.items():
            assert _document(project, artifact)[1] == raw
        assert project.disassembly(function, version=1, lines=64)['instructions'] == static
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report.update(status='passed', original_artifacts_preserved=True,
                      original_static_preserved=True, original_source_preserved=True,
                      reopened_function_comparisons=True)
        save()
