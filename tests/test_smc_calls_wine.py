"""Native internal CALL/RET and in-flight SMC recovery of the authored fixture.

Requires the existing matching Wine runtime, the separately built homegrown
target and a fresh private evidence directory. No compiler or VM is launched
by an ordinary unconfigured test run.
"""
import base64
from copy import deepcopy
import hashlib
import json

from fdisbull.project import Project
from fdisbull.pe_function_recovery import expand_pe_function_contraction
from test_smc_function_wine import _inputs, _document, MASK64, RBX_SEED, RAX_SEED, EDITABLE_FLAGS
from test_pe_function_execution import _program, verify_source_spec, SENTINELS, MODE


def _route(code, start, caller, x):
    """Budget/routes from the authored guard/calls, then verify native events."""
    from iced_x86 import Decoder, FlowControl, Mnemonic
    address, returns, result = start, [], []
    for _ in range(64):
        ins = Decoder(64, code[address - start:], ip=address).decode()
        assert not ins.is_invalid
        result.append(address)
        if address == caller:
            assert ins.mnemonic == Mnemonic.NOP
            return result
        if ins.flow_control == FlowControl.CALL:
            returns.append(ins.next_ip)
            address = ins.near_branch_target
        elif ins.flow_control == FlowControl.RETURN:
            address = returns.pop() if returns else caller
        elif ins.flow_control == FlowControl.CONDITIONAL_BRANCH:
            assert ins.mnemonic == Mnemonic.JA
            address = ins.near_branch_target if x > 10 else ins.next_ip
        elif ins.flow_control == FlowControl.UNCONDITIONAL_BRANCH:
            address = ins.near_branch_target
        else:
            assert ins.flow_control == FlowControl.NEXT
            address = ins.next_ip
    raise AssertionError('Authored call path exceeded its decode budget')


def _replay_witness(project, report, witness):
    """Replay exact symbolic inputs through the actual target bytes and RET."""
    import unicorn
    from unicorn import x86_const as reg
    results = []
    for family in ('baseline', 'writer-control'):
        case = report['families'][family]['cases'][0]
        capture, _ = _document(project, case['code_captures'][0]['capture']['artifact'])
        start, raw = int(capture['runtime_address'], 16), bytes.fromhex(capture['hex'])
        caller = start + report['symbols']['smc_gate_return'] - report['symbols']['smc_function']
        cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        pages = {a & ~4095 for a in range(start, start + len(raw))}
        pages |= {int(a, 16) & ~4095 for a in witness['entry_memory']}
        for page in pages:
            cpu.mem_map(page, 4096)
        cpu.mem_write(start, raw)
        for address, byte in witness['entry_memory'].items():
            cpu.mem_write(int(address, 16), bytes([int(byte, 16)]))
        for name, value in witness['entry_general'].items():
            cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), int(value, 16))
        cpu.reg_write(reg.UC_X86_REG_EFLAGS, int(witness['entry_flags'], 16))
        sites = []
        def before(guest, address, size, _):
            sites.append(address)
            if address == caller:
                guest.emu_stop()
        cpu.hook_add(unicorn.UC_HOOK_CODE, before)
        cpu.emu_start(start, start + len(raw), count=256)
        assert cpu.reg_read(reg.UC_X86_REG_RIP) == caller
        results.append({'general': {n: hex(cpu.reg_read(getattr(reg, 'UC_X86_REG_' + n.upper())))
                                    for n in witness['entry_general']},
            'flags': hex(cpu.reg_read(reg.UC_X86_REG_EFLAGS) & 0xffffffff),
            'memory': {a: hex(bytes(cpu.mem_read(int(a, 16), 1))[0]) for a in witness['entry_memory']},
            'code': {hex(start + i): hex(b) for i, b in enumerate(bytes(cpu.mem_read(start, len(raw))))},
            'caller_boundary': hex(caller), 'completed_instructions': len(sites) - 1})
    a, b = results
    for field, expected in (('general', 'differing_live_registers'), ('memory', 'differing_memory_bytes'),
                            ('code', 'differing_code_bytes')):
        differences = {key: {'baseline': a[field][key], 'layer': b[field][key]}
                       for key in a[field] if a[field][key] != b[field][key]}
        assert differences == witness[expected]
    assert {'baseline': a['flags'], 'layer': b['flags']} == witness['masked_flags']
    return {'status': 'passed', 'provider': 'independent Unicorn CPU',
            'exact_witness_inputs': True, 'actual_target_bytes': True, 'results': results}


def test_real_wine_internal_calls_and_execution_time_mutation():
    qemu, kernel, runtime, source, evidence = _inputs()
    import lief
    pe = lief.PE.parse(str(source))
    base = pe.optional_header.imagebase
    symbols = {e.name: base + e.address for e in pe.get_export().entries}
    start, caller, gate = (symbols[n] for n in ('smc_function', 'smc_gate_return', 'smc_gate'))
    span = caller + 1 - start
    original = bytes(pe.get_content_from_virtual_address(start, span))
    independent, _ = _program()
    assert original == independent[:span] and span == 93
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    fdb = evidence / 'wine-smc-calls.fdb'
    assert not fdb.exists(), 'Preserve previous evidence and use a fresh directory'
    report = {'format': 'fdisbull-native-smc-calls-acceptance-1', 'status': 'running',
              'source_sha256': source_sha, 'symbols': symbols, 'families': {},
              'assistance': 'Paused, guarded code/RAM/context resets and gate redirects are recorded; '
                            'native guest instructions perform the in-function mutation. No checkpoint claim.',
              'source_contract': 'unsigned x<=10: out[0]=x+1; nested prepare/writer changes '
                                 'value immediate1->2; out[1]=x+2; return x+2. '
                                 'Otherwise return UINT64_MAX and preserve output.'}
    artifacts = {}
    def save():
        (evidence / 'WINE-SMC-CALLS.json').write_text(json.dumps(report, indent=2) + '\n')
    def remember(project, receipt):
        doc, raw = _document(project, receipt['artifact'])
        artifacts[receipt['artifact']] = raw
        return doc

    with Project.create(fdb, source) as project:
        project.analyze(max_instructions=4096)
        static = project.disassembly(start, version=1, lines=96)['instructions']
        with project.debugger(str(qemu), str(source.parent), kernel=str(kernel),
                              initramfs=str(runtime), files=[source.name],
                              version=1, memory_mib=4096) as debug:
            report['runtime'] = debug.metadata
            marker = debug.breakpoint(symbols['smc_before_write'])
            stopped = debug.run(timeout_ms=60000)
            assert stopped['outcome'] == 'breakpoint'
            assert debug.registers()['project_address'] == hex(symbols['smc_before_write'])
            debug.delete_breakpoint(marker['breakpoint_id'])
            context = debug.registers()
            marker_rsp = int(context['general']['rsp'], 16)
            stack, out = marker_rsp - 8, symbols['smc_output'] + debug.delta
            native_symbols = {n: a + debug.delta for n, a in symbols.items()}
            def read(address, length):
                raw = base64.b64decode(debug.call('read', {'address': address, 'length': length})['data_base64'], validate=True)
                assert len(raw) == length
                return raw.hex()
            def reset(address, data, purpose):
                before = read(address, len(bytes.fromhex(data)))
                if before != data:
                    debug.call('write', {'address': address, 'data_hex': data})
                assert read(address, len(bytes.fromhex(data))) == data
                return {'address': hex(address), 'expected_hex': before, 'data_hex': data,
                        'readback_verified': True, 'purpose': purpose}
            def edit(general, rip, flags):
                current = debug.registers()
                changes = {n: {'expected': current['general'][n], 'value': value}
                           for n, value in general.items() if int(current['general'][n], 16) != int(value, 16)}
                if int(current['rip'], 16) != rip:
                    changes['rip'] = {'expected': current['rip'], 'value': hex(rip)}
                value = (int(current['rflags'], 16) & ~EDITABLE_FLAGS) | (flags & EDITABLE_FLAGS)
                if value != int(current['rflags'], 16):
                    changes['rflags'] = {'expected': current['rflags'], 'value': hex(value)}
                return debug.write_registers(changes) if changes else {}
            def ram():
                current = int(debug.registers()['general']['rsp'], 16)
                window = debug.stack_memory(offset=stack - 40 - current, length=48)
                assert int(window['runtime_address'], 16) == stack - 40
                return [{'address': hex(out), 'hex': debug.memory(symbols['smc_output'], length=16)['hex']},
                        {'address': hex(stack - 40), 'hex': window['hex']}]
            original_ram = {out: read(out, 16), stack - 40: read(stack - 40, 48)}
            report['marker_context'] = context
            report['contract'] = {'entry_registers': {'rsp': hex(stack), 'rdx': hex(out)},
                'entry_memory': [{'address': hex(stack), 'hex': (caller + debug.delta).to_bytes(8, 'little').hex()}],
                'memory_model': 'private_ordinary_ram', 'memory_observation': 'ordered',
                'memory_ranges': [{'address': hex(out), 'length': 16}, {'address': hex(stack - 40), 'length': 48}]}
            for name, mutation, inputs in (('baseline', 2, (3, 11, 0, 10, MASK64)),
                                            ('repeat', 2, (3, 11)), ('writer-control', 3, (3, 11))):
                family = {'mutation': mutation, 'cases': []}
                report['families'][name] = family
                seed = bytearray(original)
                seed[symbols['smc_after_store'] - start - 1] = mutation
                for x in inputs:
                    case = {'input': hex(x), 'segments': [], 'code_captures': [], 'resets': []}
                    family['cases'].append(case)
                    case['resets'].append(reset(start + debug.delta, seed.hex(), 'restore exact authored entry code; writer control explicitly labeled'))
                    for address, raw in original_ram.items():
                        case['resets'].append(reset(address, raw, 'restore declared private RAM before gate CALL'))
                    general = {**context['general'], 'rax': hex(RAX_SEED), 'rbx': hex(RBX_SEED),
                               'rcx': hex(x), 'rdx': hex(out)}
                    case['context_edit'] = edit(general, gate + debug.delta, int(context['rflags'], 16))
                    gate_trace = debug.trace(name + '-gate-' + str(x) + '.json', count=1, timeout_ms=60000)
                    remember(project, gate_trace)
                    case['gate_trace'] = gate_trace
                    assert debug.registers()['project_address'] == hex(start)
                    assert int(debug.registers()['general']['rsp'], 16) == stack
                    case['memory'] = {'entry': ram()}
                    route = _route(bytes(seed), start, caller, x)
                    cuts = [route.index(symbols['smc_writer']) + 1, len(route)] if x <= 10 else [len(route)]
                    prior = 0
                    for end in cuts:
                        capture = debug.capture_code(start, length=span, view='ram', name=f'{name}-{x}-code-{prior}.json')
                        captured = remember(project, capture)
                        case['code_captures'].append({'after_event': prior, 'capture': capture})
                        trace = debug.trace(f'{name}-{x}-steps-{prior}.json', count=end - prior, timeout_ms=60000)
                        document = remember(project, trace)
                        assert document['complete'] and len(document['events']) == end - prior
                        assert [e['project_address'] for e in document['events']] == [hex(a) for a in route[prior:end]]
                        assert all(e['observation']['instruction_completed'] is True for e in document['events'])
                        case['segments'].append({'trace': trace['artifact'], 'capture': capture['artifact']})
                        if prior == 0:
                            assert captured['hex'] == seed.hex()
                        else:
                            expected = bytearray(seed)
                            expected[symbols['smc_constant_immediate'] - start] = mutation
                            assert captured['hex'] == expected.hex()
                        prior = end
                    case['memory']['exit'] = ram()
                    case['exit_registers'] = debug.registers()
                    assert int(case['exit_registers']['general']['rax'], 16) == (x + mutation if x <= 10 else MASK64)
                    assert int(case['exit_registers']['general']['rsp'], 16) == stack + 8
                    assert int(case['exit_registers']['general']['rbx'], 16) == RBX_SEED
                    output = bytes.fromhex(case['memory']['exit'][0]['hex'])
                    assert [int.from_bytes(output[i:i + 8], 'little') for i in (0, 8)] == (
                        [x + 1, x + mutation] if x <= 10 else list(SENTINELS))
                    case['route'] = [hex(a) for a in route]
                    save()
            report['restoration'] = [reset(start + debug.delta, original.hex(), 'restore original code before natural main')]
            for address, raw in original_ram.items():
                report['restoration'].append(reset(address, raw, 'restore original marker RAM'))
            report['marker_restoration'] = edit(context['general'], int(context['rip'], 16), int(context['rflags'], 16))
            restored = debug.capture_code(start, length=span, view='ram', name='restored-before-main.json')
            assert remember(project, restored)['hex'] == original.hex()
            report['restored_capture'] = restored
            done = debug.breakpoint(symbols['smc_done'])
            assert debug.run(timeout_ms=60000)['outcome'] == 'breakpoint'
            assert debug.registers()['project_address'] == hex(symbols['smc_done'])
            debug.delete_breakpoint(done['breakpoint_id'])
            report['natural_main'] = {'first_value': read(native_symbols['first_value'], 8),
                'output': read(native_symbols['smc_output'], 16),
                'rejected_value': read(native_symbols['rejected_value'], 8),
                'rejected_output': read(native_symbols['rejected_output'], 16)}
            assert report['natural_main'] == {'first_value': (5).to_bytes(8, 'little').hex(),
                'output': (4).to_bytes(8, 'little').hex() + (5).to_bytes(8, 'little').hex(),
                'rejected_value': MASK64.to_bytes(8, 'little').hex(),
                'rejected_output': b''.join(v.to_bytes(8, 'little') for v in SENTINELS).hex()}
            final_capture = debug.capture_code(start, length=span, view='ram', name='natural-final-code.json')
            remember(project, final_capture)
            report['natural_final_capture'] = final_capture
            assert len(project.versions()) == 1
            save()
        versions = {}
        for identifier in list(artifacts):
            row = project.db.execute('SELECT kind FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
            if row['kind'] == 'code-snapshot':
                versions[identifier] = project.debug_promote_code(identifier, label='preserved call/SMC code epoch', max_instructions=128)
        report['versions'] = versions
        save()
    with Project(fdb) as project:
        def paths(name, only_accepted=False):
            result = []
            for case in report['families'][name]['cases'][:1 if only_accepted else 2]:
                result.append({'segments': [{'trace': s['trace'], 'version': versions[s['capture']]['version']} for s in case['segments']],
                    'code_versions': [{'after_event': c['after_event'], 'version': versions[c['capture']['artifact']]['version']} for c in case['code_captures']],
                    'memory': case['memory']})
            return result
        def compare(left, right, accepted=False):
            a, b = paths(left, accepted), paths(right, accepted)
            contract = deepcopy(report['contract'])
            if accepted:
                contract['entry_register_ranges'] = {'rcx': {'min': '0x0', 'max': '0xa'}}
            return project.debug_compare_runtime_functions(a[0]['segments'][0]['version'], b[0]['segments'][0]['version'],
                a, b, contract=contract, execution_mode=MODE, timeout_ms=10000)
        report['whole_function'] = compare('baseline', 'repeat')
        save()
        proof = report['whole_function']['function']
        assert proof['status'] == 'equivalent_under_contract', proof
        report['source_specifications'] = {side: verify_source_spec(proof[side + '_recovery'], report['contract'], native_symbols)
                                            for side in ('baseline', 'layer')}
        report['changed_writer'] = compare('baseline', 'writer-control', True)
        save()
        assert report['changed_writer']['function']['status'] == 'different'
        assert 'rax' in report['changed_writer']['function']['counterexample']['differing_live_registers']
        report['difference_witness_replay'] = _replay_witness(
            project, report, report['changed_writer']['function']['counterexample'])
        for identifier, raw in artifacts.items():
            assert _document(project, identifier)[1] == raw
        assert project.disassembly(start, version=1, lines=96)['instructions'] == static
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
        # Expansion is checked against the exact documents assembled by the
        # public runtime binder, without relabeling native versions/events.
        from fdisbull.runtime_patch_analysis import _execution_path
        docs = [[_execution_path(project, ps[0]['segments'][0]['version'], p)[0] for p in ps]
                for ps in (paths('baseline'), paths('repeat'))]
        assert expand_pe_function_contraction(proof['contraction'], *docs) == {'baseline': docs[0], 'layer': docs[1]}
        report.update(status='passed', artifacts_preserved=True, source_preserved=True,
                      static_version_preserved=True, reopened=True, contraction_reexpanded=True)
        save()
