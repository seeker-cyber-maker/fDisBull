"""Real Wine PE entry, imported effects, in-flight code mutation and exit."""
import base64
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.project import Project
from fdisbull.pe_module_recovery import expand_pe_module_contraction
from fdisbull.runtime_module_analysis import _module_path
from test_smc_function_wine import _inputs, _document
from test_pe_module_recovery import _program, verify_source_spec


def _route(code, start, symbols):
    """Source-bound budgets for the two declared branch inputs and internal calls."""
    from iced_x86 import Decoder, FlowControl, Mnemonic
    pc, returns, sites, arguments = start, [], [], iter((3, 11))
    x = None
    for _ in range(192):
        ins = Decoder(64, code[pc - start:], ip=pc).decode()
        assert not ins.is_invalid
        sites.append(pc)
        if pc == symbols['smc_exit_process_call']:
            return sites
        if pc in (symbols['smc_set_last_error_call'], symbols['smc_get_last_error_call']):
            pc = ins.next_ip
        elif ins.flow_control == FlowControl.CALL:
            if ins.near_branch_target == symbols['smc_function']:
                x = next(arguments)
            returns.append(ins.next_ip); pc = ins.near_branch_target
        elif ins.flow_control == FlowControl.RETURN:
            pc = returns.pop()
        elif ins.flow_control == FlowControl.CONDITIONAL_BRANCH:
            assert ins.mnemonic == Mnemonic.JA
            pc = ins.near_branch_target if x > 10 else ins.next_ip
        elif ins.flow_control == FlowControl.UNCONDITIONAL_BRANCH:
            pc = ins.near_branch_target
        else:
            assert ins.flow_control == FlowControl.NEXT
            pc = ins.next_ip
    raise AssertionError('Authored module exceeded its route budget')


def test_real_wine_module_initialization_imported_calls_and_process_exit():
    qemu, kernel, runtime, source, evidence = _inputs()
    import lief
    pe = lief.PE.parse(str(source)); base = pe.optional_header.imagebase
    symbols = {e.name: base + e.address for e in pe.get_export().entries}
    iat = {e.name: base + e.iat_address for imp in pe.imports for e in imp.entries}
    entry, end = symbols['smc_module_entry'], symbols['smc_module_end']
    code = bytes(pe.get_content_from_virtual_address(entry, end - entry))
    manual, labels, defaults = _program(base=entry, data_address=symbols['smc_data_start'], import_iat=iat)
    assert code == manual and len(code) == 261
    assert all(symbols[n] == a for n, a in labels.items() if n in symbols)
    assert bytes(pe.get_content_from_virtual_address(symbols['smc_data_start'], 64)) == defaults
    assert not pe.has_tls and not pe.data_directories[14].rva
    fdb = evidence / 'wine-smc-module.fdb'
    assert not fdb.exists(), 'Keep earlier evidence; select a fresh directory'
    report = {'format': 'fdisbull-native-module-acceptance-1', 'status': 'running',
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'symbols': symbols,
        'iat': iat, 'runs': {}, 'assistance': 'Natural PE entry and actual imported calls/exit; '
        'exit-control changes only one immediate while paused before first authored instruction; '
        'no stack/register/data resets, no checkpoint or OS rollback claim'}
    artifacts = {}
    def save():
        (evidence / 'WINE-SMC-MODULE.json').write_text(json.dumps(report, indent=2) + '\n')
    def remember(project, receipt):
        doc, raw = _document(project, receipt['artifact']); artifacts[receipt['artifact']] = raw
        return doc
    with Project.create(fdb, source) as project:
        project.analyze(max_instructions=4096)
        static = project.disassembly(entry, version=1, lines=160)['instructions']
        for name, exit_code in (('baseline', 7), ('repeat', 7), ('exit-control', 9)):
            row = {'exit_code': exit_code, 'segments': [], 'code_captures': [], 'external_calls': []}
            report['runs'][name] = row; save()
            with project.debugger(str(qemu), str(source.parent), kernel=str(kernel), initramfs=str(runtime),
                                  files=[source.name], version=1, memory_mib=4096) as debug:
                row['runtime'] = debug.metadata
                registers = debug.registers()
                assert registers['project_address'] == hex(entry)
                delta, stack = debug.delta, int(registers['general']['rsp'], 16)
                runtime_symbols = {n: a + delta for n, a in symbols.items()}
                runtime_iat = {n: a + delta for n, a in iat.items()}
                row.update(runtime_symbols=runtime_symbols, runtime_iat=runtime_iat)
                ranges = [{'address': hex(symbols['smc_data_start'] + delta), 'length': 64},
                          {'address': hex(min(iat.values()) + delta), 'length': 24},
                          {'address': hex(stack - 96), 'length': 104}]
                code_ranges = [{'address': hex(entry + delta), 'length': len(code)}]
                row['initialization'] = debug.capture_module_entry(
                    data_ranges=[ranges[0]], name=name + '-entry.json')
                initialized = remember(project, row['initialization'])
                assert initialized['initialization']['memory'][0]['hex'] == defaults.hex()
                row['contract'] = {'entry_registers': {'rsp': hex(stack)},
                    'memory_model': 'private_ordinary_ram', 'memory_observation': 'ordered',
                    'memory_ranges': ranges, 'entry_memory': initialized['initialization']['memory'],
                    'external_stack_ranges': [{'address': hex(stack - 96), 'length': 48},
                                              {'address': hex(stack - 40), 'length': 32}]}
                def ram():
                    result = []
                    for item in ranges:
                        raw = base64.b64decode(debug.call('read', {'address': int(item['address'], 16), 'length': item['length']})['data_base64'], validate=True)
                        assert len(raw) == item['length'];result.append({'address': item['address'], 'hex': raw.hex()})
                    return result
                original = debug.capture_code(entry, length=len(code), view='ram', name=name + '-original-code.json')
                assert remember(project, original)['hex'] == code.hex()
                row['original_capture'] = original
                initial_capture = original
                candidate = bytearray(code)
                if exit_code != 7:
                    # MOV ECX,7 immediately precedes the pre-exit NOP. Keep
                    # original and modified entry images as separate evidence.
                    offset = symbols['smc_module_before_exit'] - entry - 4
                    assert candidate[offset - 1:offset + 4] == bytes.fromhex('b907000000')
                    candidate[offset:offset + 4] = exit_code.to_bytes(4, 'little')
                    address = entry + delta + offset
                    before = debug.memory(entry + offset, length=4)['hex']
                    debug.call('write', {'address': address, 'data_hex': exit_code.to_bytes(4, 'little').hex()})
                    after = debug.memory(entry + offset, length=4)['hex']
                    assert before == '07000000' and after == '09000000'
                    row['entry_control'] = {'address': hex(address), 'expected_hex': before,
                        'data_hex': after, 'readback_verified': True}
                    initial_capture = debug.capture_code(entry, length=len(code), view='ram', name=name + '-controlled-entry-code.json')
                    assert remember(project, initial_capture)['hex'] == candidate.hex()
                row['memory'] = {'entry': ram()}
                row['code_captures'].append({'after_event': 0, 'capture': initial_capture})
                route = _route(bytes(candidate), entry, symbols)
                assert len(route) == 68
                cuts = [route.index(symbols['smc_writer']) + 1,
                        route.index(symbols['smc_set_last_error_call'])]
                active = initial_capture['artifact']; index = 0
                for cut in cuts:
                    trace = debug.trace(name + '-body-' + str(index) + '.json', count=cut - index, timeout_ms=60000)
                    doc = remember(project, trace)
                    assert doc['complete'] and len(doc['events']) == cut - index
                    assert [e['project_address'] for e in doc['events']] == [hex(a) for a in route[index:cut]]
                    row['segments'].append({'trace': trace['artifact'], 'capture': active})
                    index = cut
                    if cut == cuts[0]:
                        capture = debug.capture_code(entry, length=len(code), view='ram', name=name + '-after-store.json')
                        observed = remember(project, capture)
                        expected = bytearray(candidate); expected[symbols['smc_constant_immediate'] - entry] = 2
                        assert observed['hex'] == expected.hex()
                        row['code_captures'].append({'after_event': index, 'capture': capture});active = capture['artifact']
                for api in ('SetLastError', 'GetLastError', 'ExitProcess'):
                    callsite = symbols[{'SetLastError': 'smc_set_last_error_call', 'GetLastError': 'smc_get_last_error_call', 'ExitProcess': 'smc_exit_process_call'}[api]]
                    cut = route.index(callsite)
                    if index < cut:
                        trace = debug.trace(name + '-between-' + str(index) + '.json', count=cut - index, timeout_ms=60000)
                        doc = remember(project, trace);assert doc['complete']
                        assert [e['project_address'] for e in doc['events']] == [hex(a) for a in route[index:cut]]
                        row['segments'].append({'trace': trace['artifact'], 'capture': active});index = cut
                    assert debug.registers()['project_address'] == hex(callsite)
                    observed = debug.import_call(name=name + '-' + api + '.json', memory_ranges=ranges,
                                                 code_ranges=code_ranges, timeout_ms=60000)
                    api_doc = remember(project, observed)
                    assert api_doc['status'] == 'complete', api_doc
                    remember(project, api_doc['trace'])
                    row['segments'].append({'trace': api_doc['trace']['artifact'], 'capture': active})
                    row['external_calls'].append({'event_index': index, 'artifact': observed['artifact']})
                    index += 1
                    if api == 'GetLastError':
                        assert int(api_doc['contexts']['return']['general']['rax'], 16) & 0xffffffff == 0x1234
                    if api == 'ExitProcess':
                        assert api_doc['terminal']['exit_code'] == exit_code
                        row['memory']['exit'] = api_doc['memory']['entry']
                        row['terminal'] = api_doc['terminal']
                assert index == len(route)
                data = bytes.fromhex(row['memory']['exit'][0]['hex'])
                assert [int.from_bytes(data[k:k + 8], 'little') for k in range(0, 64, 8)] == [
                    3, 4, 5, 0x8877665544332211, 0x1122334455667788, 5, (1 << 64) - 1, 0x1234]
                save()
        promoted = {}
        for identifier in artifacts:
            if project.db.execute('SELECT kind FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()[0] == 'code-snapshot':
                promoted[identifier] = project.debug_promote_code(identifier, label='preserved module code image', max_instructions=512)
        report['versions'] = promoted;save()
    with Project(fdb) as project:
        def path(name):
            row = report['runs'][name]
            return {'segments': [{'trace': s['trace'], 'version': promoted[s['capture']]['version']} for s in row['segments']],
                'code_versions': [{'after_event': c['after_event'], 'version': promoted[c['capture']['artifact']]['version']} for c in row['code_captures']],
                'memory': row['memory'], 'initialization': row['initialization']['artifact'], 'external_calls': row['external_calls']}
        def compare(left, right):
            a, b = path(left), path(right)
            return project.debug_compare_runtime_modules(a['segments'][0]['version'], b['segments'][0]['version'],
                [a], [b], contract=report['runs'][left]['contract'], timeout_ms=10000)
        report['whole_module'] = compare('baseline', 'repeat');save()
        proof = report['whole_module']['module'];assert proof['status'] == 'equivalent_under_contract', proof
        report['source_specs'] = {name: verify_source_spec(proof[field], report['runs'][name]['contract'],
            report['runs'][name]['runtime_symbols'], import_iat=report['runs'][name]['runtime_iat'])
            for name, field in (('baseline', 'baseline_recovery'), ('repeat', 'layer_recovery'))}
        report['changed_exit'] = compare('baseline', 'exit-control');save()
        changed = report['changed_exit']['module'];assert changed['status'] == 'different', changed
        assert changed['counterexample']['exit_code'] == {'baseline': '0x7', 'layer': '0x9'}
        report['source_specs']['exit-control'] = verify_source_spec(changed['layer_recovery'],
            report['runs']['exit-control']['contract'], report['runs']['exit-control']['runtime_symbols'],
            exit_code=9, import_iat=report['runs']['exit-control']['runtime_iat'])
        a, b = path('baseline'), path('repeat')
        aa, bb = _module_path(project, a['segments'][0]['version'], a)[0], _module_path(project, b['segments'][0]['version'], b)[0]
        assert expand_pe_module_contraction(proof['contraction'], [aa], [bb]) == {'baseline': [aa], 'layer': [bb]}
        bad = deepcopy(a);bad['initialization'] = b['initialization']
        with pytest.raises(ValueError, match='identity differ'):
            _module_path(project, a['segments'][0]['version'], bad)
        bad = deepcopy(a);bad['external_calls'][0]['artifact'] = bad['external_calls'][1]['artifact']
        with pytest.raises(ValueError, match='owning native trace'):
            _module_path(project, a['segments'][0]['version'], bad)
        for identifier, raw in artifacts.items(): assert _document(project, identifier)[1] == raw
        assert project.disassembly(entry, version=1, lines=160)['instructions'] == static
        assert hashlib.sha256(source.read_bytes()).hexdigest() == report['source_sha256']
        report.update(status='passed', source_preserved=True, artifacts_preserved=True, static_preserved=True,
                      reopened=True, contraction_reexpanded=True, negative_bindings_rejected=True);save()
