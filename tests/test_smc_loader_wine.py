"""Opt-in real Wine loader, DLL self-modification and implementation checks.

The selected fixture directory must contain the homegrown smc-init.exe and
SMCINIT.dll. All guest observations stay in the private external evidence FDB.
Callback replay checks the observed inputs; it is not a proof of Wine's loader.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import time

import pytest

from fdisbull.debug_semantics import normalize_trace, PE_TRACE_SEMANTICS
from fdisbull.project import Project
from test_smc_function_wine import _inputs, _document
from test_wine_loader_initialization import (
    inspect_loader_fixtures, verify_loader_observations, verify_executable_observations,
)
from test_wine_loader_dispatch import capture_loader_capsule
from test_wine_loader_intervals import capture_loader_interval
from test_wine_process_attach import capture_process_attach, derive_attach_success_tail


def _replay_callback(document):
    """Replay exact source-bound instructions with an independent CPU engine.

    Compare every GPR, defined arithmetic flag, RIP, and the complete captured
    code/global/return-slot bytes after every instruction. Undefined arithmetic
    flags are excluded per instruction, rather than assumed deterministic.
    """
    import capstone
    import unicorn
    from unicorn import x86_const as reg
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    checked = 0
    for row in document['steps']:
        event, after = row['event'], row['after']
        cpu = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
        pages = set()
        for memory in row['memory_before']:
            a, raw = int(memory['address'], 16), bytes.fromhex(memory['hex'])
            pages.update(range(a & ~4095, (a + len(raw) + 4095) & ~4095, 4096))
        # RET's destination belongs to the loader; map a sentinel page so the
        # CPU may fetch there after the one completed RET, without executing it.
        pages.add(int(after['rip'], 16) & ~4095)
        for page in pages:
            cpu.mem_map(page, 4096)
        for memory in row['memory_before']:
            cpu.mem_write(int(memory['address'], 16), bytes.fromhex(memory['hex']))
        spans = [(int(m['address'], 16), len(bytes.fromhex(m['hex']))) for m in row['memory_before']]
        def memory_access(guest, kind, address, width, value, user):
            assert any(a <= address and address + width <= a + n for a, n in spans), (address, width)
        cpu.hook_add(unicorn.UC_HOOK_MEM_READ | unicorn.UC_HOOK_MEM_WRITE, memory_access)
        for name, value in event['registers']['general'].items():
            cpu.reg_write(getattr(reg, 'UC_X86_REG_' + name.upper()), int(value, 16))
        cpu.reg_write(reg.UC_X86_REG_EFLAGS, int(event['registers']['rflags'], 16))
        start = int(event['address'], 16)
        cpu.emu_start(start, 0, count=1)
        assert cpu.reg_read(reg.UC_X86_REG_RIP) == int(after['rip'], 16)
        for name, value in after['general'].items():
            assert cpu.reg_read(getattr(reg, 'UC_X86_REG_' + name.upper())) == int(value, 16), (name, event)
        ins = next(decoder.disasm(bytes.fromhex(event['bytes']), start))
        # Intel defines AF as undefined after logical TEST/OR. Other flags
        # checked here are defined by CMP/ADD or preserved by MOV/LEA/RET/Jcc.
        mask = 0xffffffff & ~(0x10 if ins.mnemonic in ('test', 'or') else 0)
        assert (cpu.reg_read(reg.UC_X86_REG_EFLAGS) ^ int(after['rflags'], 16)) & mask == 0
        for memory in row['memory_after']:
            raw = bytes.fromhex(memory['hex'])
            assert bytes(cpu.mem_read(int(memory['address'], 16), len(raw))) == raw
        checked += 1
    return {'status': 'native_source_callback_replayed', 'instructions': checked,
            'registers': 'all captured GPRs and RIP', 'flags': 'all captured defined FLAGS bits',
            'memory': 'all captured code, globals and caller return word',
            'scope': 'Exact observed inputs; independent CPU replay, not universal loader equivalence'}


def test_real_wine_loader_dll_versions_and_actual_api_implementations():
    qemu, kernel, runtime, source, evidence = _inputs()
    library = source.parent / 'SMCINIT.dll'
    inspect_loader_fixtures(source, library)
    import lief
    pe, dll = lief.PE.parse(str(source)), lief.PE.parse(str(library))
    loader_path = os.environ.get('FDISBULL_WINE_LOADER_SOURCE')
    if not loader_path:
        if os.environ.get('FDISBULL_REQUIRE_SMC_WINE') == '1':
            pytest.fail('The loader capsule requires FDISBULL_WINE_LOADER_SOURCE')
        pytest.skip('Select the frozen Wine ntdll.dll source for dispatcher capture')
    loader_path = Path(loader_path).resolve(strict=True)
    loader_pe = lief.PE.parse(str(loader_path))
    assert loader_pe is not None and loader_pe.header.machine == lief.PE.Header.MACHINE_TYPES.AMD64
    assert loader_pe.optional_header.magic == lief.PE.PE_TYPE.PE32_PLUS
    selected_symbols = [s for s in loader_pe.symbols if s.name == 'MODULE_InitDLL']
    assert len(selected_symbols) == 1
    selected_symbol = selected_symbols[0]
    module_init_rva = loader_pe.sections[selected_symbol.section_idx - 1].virtual_address + selected_symbol.value
    assert module_init_rva == 0x31600
    exception = loader_pe.data_directories[3]
    pdata = bytes(loader_pe.get_content_from_virtual_address(loader_pe.imagebase + exception.rva, exception.size))
    runtime_functions = [struct.unpack_from('<III', pdata, offset) for offset in range(0, len(pdata), 12)]
    declared = [item for item in runtime_functions if item[0] == module_init_rva]
    assert len(declared) == 1 and declared[0][0] < declared[0][1]
    detach_symbols = [s for s in loader_pe.symbols if s.name == 'process_detach']
    assert len(detach_symbols) == 1
    detach_symbol = detach_symbols[0]
    detach_rva = loader_pe.sections[detach_symbol.section_idx - 1].virtual_address + detach_symbol.value
    assert detach_rva == 0x31d10
    detach_function = [item for item in runtime_functions if item[0] == detach_rva]
    assert len(detach_function) == 1
    outer_symbols = {}
    for symbol_name, expected_rva in (('process_attach.part.0', 0x31a30), ('call_ldr_notifications', 0x2ca70)):
        candidates = [s for s in loader_pe.symbols if s.name == symbol_name]
        assert len(candidates) == 1
        symbol = candidates[0]
        rva = loader_pe.sections[symbol.section_idx - 1].virtual_address + symbol.value
        assert rva == expected_rva
        function = [item for item in runtime_functions if item[0] == rva]
        assert len(function) == 1
        outer_symbols[symbol_name] = {'begin_rva': hex(function[0][0]), 'end_rva': hex(function[0][1]),
                                      'unwind_rva': hex(function[0][2])}
    loader_source = {'filename': loader_path.name, 'source_sha256': hashlib.sha256(loader_path.read_bytes()).hexdigest(),
        'preferred_image_base': hex(loader_pe.imagebase), 'module_init_rva': hex(module_init_rva),
        'pdata_rva': hex(exception.rva), 'pdata_size': exception.size,
        'runtime_function': {'begin_rva': hex(declared[0][0]), 'end_rva': hex(declared[0][1]),
                             'unwind_rva': hex(declared[0][2])},
        'process_attach': outer_symbols,
        'intervals': {'attach_success_tail': {'start_rva': '0x31bf7', 'ret_rva': '0x31b2c'},
                      'detach_selection_prefix': {'start_rva': hex(detach_rva), 'call_rva': '0x31d56',
                          'end_rva': hex(module_init_rva), 'unwind_rva': hex(detach_function[0][2])}}}
    base, dll_base = pe.imagebase, dll.imagebase
    symbols = {e.name: base + e.address for e in pe.get_export().entries}
    dll_symbols = {e.name: dll_base + e.address for e in dll.get_export().entries}
    dll_hash = hashlib.sha256(library.read_bytes()).hexdigest()
    original_code = bytes(dll.get_content_from_virtual_address(dll_symbols['dll_code_start'],
                           dll_symbols['dll_code_end'] - dll_symbols['dll_code_start']))
    fdb = evidence / 'wine-smc-loader.fdb'
    assert not fdb.exists(), 'Preserve earlier observations; select a fresh evidence directory'
    report = {'format': 'fdisbull-native-loader-acceptance-1', 'status': 'running',
        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'dll_sha256': dll_hash, 'runs': {}, 'scope':
        'Real Wine loader milestones and exact Set/Get implementations. Other DLL initialization, '
        'concurrency, hidden OS state and complete ExitProcess implementation remain unproved.'}
    artifacts, code_images = {}, {}

    def save():
        (evidence / 'WINE-SMC-LOADER.json').write_text(json.dumps(report, indent=2) + '\n')

    with Project.create(fdb, source) as project:
        project.analyze(max_instructions=4096)
        for name in ('baseline', 'repeat'):
            row = {'milestones': [], 'callbacks': [], 'apis': [], 'loader_events': []}
            row['recovery'] = {'format': 'fdisbull-native-loader-composition-evidence-1',
                'protected_ranges': [], 'environment_ranges': [], 'snapshots': [],
                'main_segments': [], 'transitions': [], 'calls': [], 'sequence': []}
            row.update(loader_capsules=[], loader_selection={'source': loader_source, 'candidates': []}, loader_outer_edges=[])
            row.update(loader_intervals=[], loader_interval_boundaries={})
            report['runs'][name] = row; save()
            with project.debugger(str(qemu), str(source.parent), kernel=str(kernel), initramfs=str(runtime),
                    files=[source.name, library.name], version=1, memory_mib=4096,
                    loader_mode='process-create') as debug:
                row['runtime'] = debug.metadata
                owned, cursor = {}, 0

                def remember(receipt):
                    doc, raw = _document(project, receipt['artifact'])
                    artifacts[receipt['artifact']] = raw
                    sequence = row['recovery']['sequence']
                    if not any(item['artifact'] == receipt['artifact'] for item in sequence):
                        sequence.append({'index': len(sequence), 'kind': receipt['kind'],
                            'artifact': receipt['artifact'], 'sha256': receipt['sha256']})
                    return doc

                def artifact(label, kind, doc):
                    receipt = debug._artifact(name + '-' + label + '.json', kind,
                        json.dumps(doc, indent=2).encode(), {'status': doc.get('status', 'observed')})
                    remember(receipt)
                    return receipt

                def recovery_artifact(label, kind, doc):
                    return artifact(label, kind, doc)

                def read(address, length):
                    raw = base64.b64decode(debug.call('read', {'address': address, 'length': length})['data_base64'], validate=True)
                    assert len(raw) == length
                    return raw

                def history():
                    nonlocal cursor
                    doc = debug.loader_events(after=cursor)
                    assert not doc['lost_before']
                    row['loader_events'].extend(doc['events']); cursor = doc['next_after']
                    artifact('loader-' + str(cursor), 'loader-events', doc)

                def bp(address):
                    result = debug.call('bp', {'address': address})
                    owned[result['breakpoint_id']] = address
                    return result['breakpoint_id']

                def delete(identifier):
                    result = debug.call('del', {'id': int(identifier[3:])})
                    del owned[identifier]
                    return result

                def run_to(address):
                    identifier = bp(address)
                    outcome = debug.run(timeout_ms=60000)
                    assert outcome['outcome'] == 'breakpoint', outcome
                    assert int(debug.call('registers')['rip'], 16) == address, outcome
                    delete(identifier)
                    return outcome

                status = debug.call('status')
                assert status['stop_reason']['kind'] == 'process-create'
                # Keep the observed PC; its ownership is runtime evidence, not
                # an assumed property of every Windows/Wine loader version.
                row['initial_project_address'] = debug.registers()['project_address']
                row['process_create'] = artifact('process-create', 'loader-stop', status)
                history()
                loaded = None
                for _ in range(64):
                    outcome = debug.run(timeout_ms=60000)
                    history()
                    assert outcome['outcome'] == 'dll-load', outcome
                    modules = debug.call('modules')
                    matches = [m for m in modules['modules'] if m['name'].casefold() == library.name.casefold()]
                    if matches:
                        assert len(matches) == 1
                        loaded = matches[0]; break
                assert loaded is not None, 'Authored DLL was not observed before loader initialization'
                row['loaded_module'] = loaded
                db = int(loaded['base'], 16)
                ds = {n: db + a - dll_base for n, a in dll_symbols.items()}
                es = {n: a + debug.delta for n, a in symbols.items()}
                runtime_iat = {entry.name: base + entry.iat_address + debug.delta
                               for imported in pe.imports for entry in imported.entries}
                code_start, code_length = ds['dll_code_start'], len(original_code)
                data_start = ds['dll_data_start']
                row['runtime_symbols'] = {'exe': es, 'dll': ds}
                row['runtime_iat'] = runtime_iat
                from fdisbull.wine_import_calls import resolve_loaded_export
                row['dll_export'] = resolve_loaded_export(modules, library.name, 'dll_report', read)
                assert int(row['dll_export']['target'], 16) == ds['dll_report']
                # Observe genuine TLS directory and callback array before ContinueDebugEvent.
                tls_rva = dll.data_directories[9].rva
                tls = read(db + tls_rva, 40)
                callbacks = int.from_bytes(tls[24:32], 'little')
                assert callbacks == ds['dll_tls_callbacks']
                assert int.from_bytes(read(callbacks, 8), 'little') == ds['dll_tls_callback']
                assert read(callbacks + 8, 8) == bytes(8)
                row['tls_directory'] = artifact('tls-directory', 'loaded-image-structure', {
                    'module': loaded, 'address': hex(db + tls_rva), 'hex': tls.hex(),
                    'callbacks_address': hex(callbacks), 'callbacks_hex': read(callbacks, 16).hex(),
                    'source_sha256': dll_hash, 'source_tls_rva': hex(tls_rva)})

                recovery = row['recovery']
                recovery['protected_ranges'] = [
                    {'role': 'exe-data', 'address': hex(es['smc_data_start']), 'length': 32},
                    {'role': 'dll-data', 'address': hex(data_start), 'length': 64},
                    {'role': 'exe-code', 'address': hex(es['smc_module_entry']),
                     'length': es['smc_module_end'] - es['smc_module_entry']},
                    {'role': 'dll-code', 'address': hex(code_start), 'length': code_length},
                    *[{'role': 'iat-' + imported, 'address': hex(slot), 'length': 8}
                      for imported, slot in sorted(runtime_iat.items())]]
                thread_info = debug.thread_info()
                teb = int(thread_info['teb'], 16)
                recovery['environment_ranges'] = [
                    {'role': 'teb-self', 'address': hex(teb + 0x30), 'length': 8},
                    {'role': 'last-error', 'address': hex(teb + 0x68), 'length': 4}]
                recovery['main_entry_stack'] = None

                def all_ranges():
                    return recovery['protected_ranges'] + recovery['environment_ranges']

                def full_memory():
                    return [{'address': item['address'], 'hex': read(int(item['address'], 16), item['length']).hex()}
                            for item in all_ranges()]

                def snapshot(label):
                    doc = {'format': 'fdisbull-loader-frame-snapshot-1', 'run': debug.run_id,
                        'controller_source_sha256': project.meta['source_sha256'],
                        'subject_source_sha256': dll_hash, 'label': label,
                        'registers': debug.call('registers'), 'status': debug.call('status'),
                        'modules': debug.call('modules'), 'thread_info': debug.thread_info(),
                        'ranges': all_ranges(), 'memory': full_memory(),
                        'main_entry_stack': recovery['main_entry_stack']}
                    receipt = recovery_artifact(label, 'loader-frame-snapshot', doc)
                    recovery['snapshots'].append(receipt)
                    return receipt

                def transition(label, operation, before, after, outcome):
                    receipt = recovery_artifact(label, 'loader-frame-transition', {
                        'format': 'fdisbull-loader-frame-transition-1', 'label': label,
                        'run': debug.run_id, 'operation': operation, 'before': before, 'after': after,
                        'outcome': outcome,
                        'scope': 'Paired native observations across opaque loader/ExitProcess execution; '
                                 'registers, FLAGS, TEB and stack are observed, not assumed preserved'})
                    recovery['transitions'].append(receipt)
                    return receipt

                def main_segment(label, *, target=None, count=None):
                    """Observe every authored EXE instruction up to its next call boundary."""
                    assert (target is None) != (count is None)
                    before = debug.call('registers')
                    doc = {'format': 'fdisbull-native-authored-module-segment-1', 'status': 'partial',
                        'run': debug.run_id, 'source_sha256': project.meta['source_sha256'],
                        'entry': before, 'memory_entry': full_memory(), 'ranges': all_ranges(),
                        'target': hex(target) if target is not None else None,
                        'requested_count': count, 'steps': [], 'semantics': PE_TRACE_SEMANTICS}
                    try:
                        for _ in range(64):
                            regs = debug.call('registers')
                            ip = int(regs['rip'], 16)
                            if target is not None and ip == target:
                                break
                            assert es['smc_module_entry'] <= ip < es['smc_module_end']
                            pre = full_memory()
                            event, state = debug._step_instruction(time.monotonic() + 60)
                            assert event is not None and state['stop_reason']['kind'] == 'step', state
                            assert event['registers'] == regs
                            event['project_address'] = debug.project_address(ip)
                            normalize_trace('wine-qemu', [event], version=debug.version['id'], delta=debug.delta)
                            after, post = debug.call('registers'), full_memory()
                            doc['steps'].append({'event': event, 'after': after,
                                                 'memory_before': pre, 'memory_after': post})
                            if count is not None and len(doc['steps']) == count:
                                break
                        else:
                            raise AssertionError('Authored EXE segment exceeded its 64-instruction budget')
                        after = debug.call('registers')
                        if target is not None:
                            assert int(after['rip'], 16) == target
                        else:
                            assert len(doc['steps']) == count
                        doc.update(status='complete', exit=after, memory_exit=full_memory())
                    finally:
                        receipt = recovery_artifact(label, 'authored-module-segment', doc)
                        recovery['main_segments'].append(receipt)
                        save()
                    return doc, receipt

                def milestone(phase, *, result=None):
                    code = read(code_start, code_length)
                    constant = int.from_bytes(read(ds['dll_report_constant_immediate'], 4), 'little')
                    expected = bytearray(original_code)
                    expected[ds['dll_report_constant_immediate'] - code_start] = constant
                    assert code == expected and constant in (1, 2, 3)
                    code_images.setdefault(constant, code)
                    assert code_images[constant] == code
                    doc = {'format': 'fdisbull-loaded-code-observation-1', 'phase': phase,
                        'module': loaded, 'source_sha256': dll_hash,
                        'code': {'address': hex(code_start), 'rva': hex(code_start - db),
                            'hex': code.hex(), 'sha256': hashlib.sha256(code).hexdigest()},
                        'data': read(data_start, 64).hex(), 'constant': constant,
                        'registers': debug.call('registers'), 'loader_control': debug.call('status')['loader']}
                    if result is not None: doc['report_return'] = result
                    receipt = artifact(phase + '-' + str(len(row['milestones'])), 'loaded-code-snapshot', doc)
                    row['milestones'].append(dict(doc, artifact=receipt['artifact']))
                    save()

                def callback(label):
                    before = debug.call('registers')
                    start, stack = int(before['rip'], 16), int(before['general']['rsp'], 16)
                    ret = int.from_bytes(read(stack, 8), 'little')
                    assert code_start <= start < code_start + code_length
                    doc = {'format': 'fdisbull-native-dll-callback-1', 'status': 'partial',
                        'run': debug.run_id, 'controller_source_sha256': project.meta['source_sha256'],
                        'subject_module': loaded, 'subject_source_sha256': dll_hash,
                        'entry': before, 'return_address': hex(ret), 'steps': [], 'semantics': PE_TRACE_SEMANTICS}
                    reason = int(before['general']['rdx'], 16) & 0xffffffff
                    doc['source_role'] = ('report' if start == ds['dll_report'] else
                        ('tls-' if start == ds['dll_tls_callback'] else 'dll-') +
                        ('attach' if reason == 1 else 'detach' if reason == 0 else 'thread'))
                    ranges = ((code_start, code_length), (data_start, 64), (stack, 8))
                    def ram():
                        return [{'address': hex(a), 'hex': read(a, n).hex()} for a, n in ranges]
                    try:
                        for _ in range(64):
                            regs = debug.call('registers')
                            ip = int(regs['rip'], 16)
                            assert code_start <= ip < code_start + code_length
                            pre = ram()
                            event, state = debug._step_instruction(time.monotonic() + 60)
                            assert event is not None and state['stop_reason']['kind'] == 'step', state
                            assert event['registers'] == regs
                            event['project_address'] = None
                            normalize_trace('wine-qemu', [event], version=debug.version['id'])
                            observed = bytes.fromhex(pre[0]['hex'])
                            assert bytes.fromhex(event['bytes']) == observed[ip-code_start:ip-code_start+len(bytes.fromhex(event['bytes']))]
                            after, post = debug.call('registers'), ram()
                            doc['steps'].append({'event': event, 'after': after,
                                                 'memory_before': pre, 'memory_after': post})
                            if pre[0]['hex'] != post[0]['hex']:
                                code = bytes.fromhex(post[0]['hex'])
                                constant = int.from_bytes(code[ds['dll_report_constant_immediate']-code_start:
                                                               ds['dll_report_constant_immediate']-code_start+4], 'little')
                                code_images.setdefault(constant, code)
                                row.setdefault('mutation_receipts', []).append(artifact(
                                    label + '-mutation', 'loaded-code-mutation', {
                                        'module': loaded, 'source_sha256': dll_hash,
                                        'event_index': len(doc['steps'])-1, 'event': event,
                                        'before': pre[0], 'after': post[0], 'constant': constant}))
                            if int(after['rip'], 16) == ret:
                                assert event['bytes'] == 'c3'
                                assert int(after['general']['rsp'], 16) == stack + 8
                                doc.update(status='complete', exit=after)
                                break
                        assert doc['status'] == 'complete', 'Authored callback exceeded its bound'
                        doc['independent_replay'] = _replay_callback(doc)
                    finally:
                        row['callbacks'].append(artifact(label, 'dll-callback', doc))
                        save()
                    return doc

                loader_modules = [m for m in debug.call('modules')['modules'] if m['name'].casefold() == 'ntdll.dll']
                assert len(loader_modules) == 1 and loader_modules[0]['bits'] == 64
                loader_module = dict(loader_modules[0], source_sha256=loader_source['source_sha256'])
                dispatcher = int(loader_module['base'], 16) + module_init_rva
                source_prefix = bytes(loader_pe.get_content_from_virtual_address(loader_pe.imagebase + module_init_rva, 32))
                assert read(dispatcher, 32) == source_prefix
                row['loader_selection'].update(module=loader_module, entry_address=hex(dispatcher),
                    entry_prefix_hex=source_prefix.hex())
                process_attach_address = int(loader_module['base'], 16) + 0x31a30
                notification_address = int(loader_module['base'], 16) + 0x2ca70
                attach_prefix = bytes(loader_pe.get_content_from_virtual_address(loader_pe.imagebase + 0x31a30, 32))
                assert read(process_attach_address, 32) == attach_prefix
                row['loader_process_attach_selection'] = {'source': loader_source,
                    'entry_address': hex(process_attach_address), 'entry_prefix_hex': attach_prefix.hex(), 'candidates': []}

                def select_process_attach():
                    identifier = bp(process_attach_address)
                    for _ in range(256):
                        outcome = debug.run(timeout_ms=60000)
                        assert outcome['outcome'] == 'breakpoint', outcome
                        registers = debug.call('registers')
                        assert int(registers['rip'], 16) == process_attach_address
                        node = int(registers['general']['rcx'], 16)
                        module_link = int.from_bytes(read(node, 8), 'little')
                        assert module_link >= 0xa0
                        wm = module_link - 0xa0
                        raw = read(wm + 0x30, 8)
                        selected = int.from_bytes(raw, 'little') == db
                        receipt = recovery_artifact('process-attach-candidate-' +
                            str(len(row['loader_process_attach_selection']['candidates'])), 'loader-process-attach-selection', {
                                'format': 'fdisbull-wine-process-attach-selection-1', 'run': debug.run_id,
                                'module': loader_module, 'source': loader_source, 'registers': registers,
                                'node': hex(node), 'node_module_pointer': hex(module_link), 'modref': hex(wm),
                                'base_pointer_address': hex(wm + 0x30), 'base_pointer_hex': raw.hex(), 'selected': selected})
                        row['loader_process_attach_selection']['candidates'].append(receipt)
                        if selected:
                            delete(identifier)
                            return outcome
                    raise AssertionError('Selected process_attach exceeded its 256-invocation search budget')

                def record_dispatcher_selection(registers, reason):
                    assert int(registers['rip'], 16) == dispatcher
                    modref = int(registers['general']['rcx'], 16)
                    actual_base = int.from_bytes(read(modref + 0x30, 8), 'little')
                    actual_reason = int(registers['general']['rdx'], 16) & 0xffffffff
                    receipt = recovery_artifact('dispatcher-candidate-' + str(len(row['loader_selection']['candidates'])),
                        'loader-dispatch-selection', {'format': 'fdisbull-wine-loader-selection-1',
                            'run': debug.run_id, 'module': loader_module, 'source': loader_source,
                            'registers': registers, 'modref': hex(modref), 'base_pointer_address': hex(modref + 0x30),
                            'base_pointer_hex': read(modref + 0x30, 8).hex(),
                            'selected': actual_base == db and actual_reason == reason})
                    row['loader_selection']['candidates'].append(receipt)
                    return actual_base == db and actual_reason == reason

                def capsule(reason, initial_gap, *, whole_attach=False):
                    mode = 'attach' if reason == 1 else 'detach'
                    state = {'gap_before': initial_gap, 'callback_index': 0, 'last_return': None}
                    def boundary(kind, payload):
                        if kind == 'module_entry':
                            assert whole_attach and reason == 1
                            assert record_dispatcher_selection(payload['registers'], 1)
                            state['dispatcher_entry'] = snapshot('attach-dispatcher-entry')
                            state['gap_before'] = state['dispatcher_entry']
                            row['loader_outer_edges'].append(recovery_artifact('loader-to-attach-dispatcher', 'loader-outer-edge', {
                                'before': before_dispatch, 'after': state['dispatcher_entry'],
                                'scope': 'Opaque outer loader prefix; selected process_attach is retained separately'}))
                        elif kind == 'module_observed':
                            remember(payload['artifact'])
                            row['loader_capsules'].append(payload['artifact'])
                            state['capsule_document'] = payload['document']
                            state['capsule_return'] = snapshot(mode + '-dispatcher-return')
                        elif kind == 'callback_entry':
                            role = payload['source_role']
                            assert role in (('tls-attach', 'dll-attach') if reason == 1 else ('tls-detach', 'dll-detach'))
                            index = state['callback_index']
                            label = ('loader-to-tls-attach' if index == 0 else 'tls-return-to-dll-attach') if reason == 1 else 'exit-to-detach-' + str(index)
                            after = snapshot(role + '-entry')
                            transition(label, 'loader.dispatch-capsule', state['gap_before'], after,
                                       {'outcome': 'native-dispatch', 'role': role})
                        elif kind == 'callback_return':
                            role = payload['source_role']
                            payload['independent_replay'] = _replay_callback(payload)
                            row['callbacks'].append(artifact(mode + '-capsule-' + role, 'dll-callback', payload))
                            milestone('tls-attached' if role == 'tls-attach' else
                                      'dll-attached' if role == 'dll-attach' else 'detached')
                            state['gap_before'] = snapshot(role + '-return')
                            state['last_return'] = state['gap_before']
                            state['callback_index'] += 1
                    entry = debug.call('registers')
                    capsule_stack = int(entry['general']['rsp'], 16)
                    node = int(entry['general']['rcx'], 16) if whole_attach else None
                    modref = int.from_bytes(read(node, 8), 'little') - 0xa0 if whole_attach else int(entry['general']['rcx'], 16)
                    extra = [{'role': 'dispatcher-stack', 'address': hex(capsule_stack - 4032), 'length': 4096},
                             {'role': 'wine-modref', 'address': hex(modref), 'length': 256},
                             {'role': 'teb-prefix', 'address': hex(teb), 'length': 256},
                             {'role': 'subject-pe-headers', 'address': hex(db), 'length': 1024},
                             {'role': 'subject-tls-directory', 'address': hex(db + tls_rva), 'length': 40},
                             {'role': 'subject-tls-callbacks', 'address': hex(callbacks), 'length': 16}]
                    if whole_attach:
                        peb = int.from_bytes(read(teb + 0x60, 8), 'little')
                        ldr = int.from_bytes(read(peb + 0x18, 8), 'little')
                        old_tail = int.from_bytes(read(ldr + 0x38, 8), 'little')
                        head, previous = ldr + 0x30, ldr + 0x30
                        cursor_node = int.from_bytes(read(head, 8), 'little')
                        list_entries = []
                        for index in range(33):
                            if cursor_node == head:
                                assert previous == old_tail
                                break
                            assert index < 32 and cursor_node not in (int(item['address'], 16) for item in list_entries)
                            links = read(cursor_node, 16)
                            assert int.from_bytes(links[8:], 'little') == previous
                            list_entries.append({'role': 'initialization-list-node-' + str(index),
                                                 'address': hex(cursor_node), 'length': 16})
                            previous, cursor_node = cursor_node, int.from_bytes(links[:8], 'little')
                        else:
                            raise AssertionError('Existing initialization list exceeded its 32-node bound')
                        extra[0] = {'role': 'outer-caller-stack', 'address': hex(capsule_stack - 4096), 'length': 4160}
                        extra.extend([
                            {'role': 'ddag-node', 'address': hex(node), 'length': 128},
                            {'role': 'peb-prefix', 'address': hex(peb), 'length': 256},
                            {'role': 'loader-data', 'address': hex(ldr), 'length': 256},
                            {'role': 'prior-initialization-tail', 'address': hex(old_tail), 'length': 16},
                            {'role': 'process-detaching', 'address': hex(int(loader_module['base'], 16) + 0x95938), 'length': 4},
                            {'role': 'current-modref', 'address': hex(int(loader_module['base'], 16) + 0x958b8), 'length': 8},
                            {'role': 'notification-sentinel', 'address': hex(int(loader_module['base'], 16) + 0x6d4e0), 'length': 16},
                            {'role': 'module-debug-flags', 'address': hex(int(loader_module['base'], 16) + 0x6d5d0), 'length': 1},
                            {'role': 'loader-debug-flags', 'address': hex(int(loader_module['base'], 16) + 0x6d5c0), 'length': 1}])
                        extra.extend(list_entries)
                        captured = capture_process_attach(debug, name=name + '-process-attach.json',
                            entry_address=process_attach_address, module_entry_address=dispatcher,
                            notification_entry_address=notification_address, dll_base=db,
                            protected_ranges=recovery['protected_ranges'], extra_ranges=extra, module_extra_ranges=extra,
                            subject_symbols=ds, subject_source_sha256=dll_hash, subject_module=loaded,
                            loader_module=loader_module, on_boundary=boundary, max_steps=1024, timeout_ms=600000)
                        remember(captured['artifact'])
                        row['loader_process_attach'] = captured['artifact']
                        state['full_process_attach'] = captured
                        assert captured['document']['status'] == 'complete' and state['callback_index'] == 2
                        return state
                    captured = capture_loader_capsule(debug, name=name + '-' + mode + '-dispatcher.json',
                        dll_base=db, protected_ranges=recovery['protected_ranges'], extra_ranges=extra,
                        entry_address=dispatcher, max_steps=2048, timeout_ms=600000,
                        subject_symbols=ds, subject_source_sha256=dll_hash,
                        subject_module=loaded, loader_module=loader_module, on_boundary=boundary)
                    remember(captured['artifact'])
                    row['loader_capsules'].append(captured['artifact'])
                    assert captured['document']['status'] == 'complete' and state['callback_index'] == 2
                    state['capsule_return'] = snapshot(mode + '-dispatcher-return')
                    state['capsule_document'] = captured['document']
                    return state

                milestone('before-tls')
                debug.loader_control(stop_on_load=False)
                before_dispatch = snapshot('before-loader-to-module-dispatch')
                select_process_attach()
                process_entry = snapshot('selected-process-attach-entry')
                row['loader_process_attach_boundaries'] = {'entry_snapshot': process_entry}
                attach = capsule(1, process_entry, whole_attach=True)
                gap_before = attach['last_return']
                full_attach = attach['full_process_attach']
                tail_first = full_attach['document']['module_span']['last_step'] + 1
                tail_entry = full_attach['document']['steps'][tail_first]['event']['registers']
                tail_pc, tail_stack = int(tail_entry['rip'], 16), int(tail_entry['general']['rsp'], 16)
                assert tail_pc == int(loader_module['base'], 16) + 0x31bf7
                selected_modref = int(attach['capsule_document']['selection']['modref'], 16)
                tail = derive_attach_success_tail(debug, full_attach, name=name + '-attach-success-tail.json',
                    extra_ranges=[{'role': 'caller-frame', 'address': hex(tail_stack), 'length': 128},
                        {'role': 'selected-modref', 'address': hex(selected_modref), 'length': 256},
                        {'role': 'module-debug-flags', 'address': hex(int(loader_module['base'], 16) + 0x6d5d0), 'length': 1},
                        {'role': 'current-modref', 'address': hex(int(loader_module['base'], 16) + 0x958b8), 'length': 8}])
                remember(tail['artifact']); row['loader_intervals'].append(tail['artifact'])
                attach['process_return'] = snapshot('attach-caller-return')
                row['loader_process_attach_boundaries']['exit_snapshot'] = attach['process_return']
                row['loader_interval_boundaries']['attach_success_tail'] = {
                    'entry_snapshot': attach['capsule_return'], 'exit_snapshot': attach['process_return']}
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'entry', result
                assert debug.registers()['project_address'] == hex(symbols['smc_module_entry'])
                main_stack = int(debug.call('registers')['general']['rsp'], 16)
                recovery['main_entry_stack'] = hex(main_stack)
                recovery['environment_ranges'].append({'role': 'main-stack', 'address': hex(main_stack - 48), 'length': 56})
                recovery['entry'] = snapshot('exe-module-entry')
                transition('dll-return-to-exe-entry', 'loader.run', gap_before, recovery['entry'], result)
                history(); milestone('exe-entry')
                entry_data = read(es['smc_data_start'], 32)
                entry_modules = debug.call('modules')
                bindings = []
                for imported in pe.imports:
                    for item in imported.entries:
                        slot = runtime_iat[item.name]
                        raw = read(slot, 8)
                        resolution = resolve_loaded_export(entry_modules, imported.name, item.name, read)
                        assert int.from_bytes(raw, 'little') == int(resolution['target'], 16)
                        bindings.append({'name': item.name, 'module': imported.name,
                            'iat_address': hex(slot), 'iat_hex': raw.hex(), 'target': resolution['target'],
                            'resolution': resolution})
                recovery['bindings'] = recovery_artifact('entry-bindings', 'loader-entry-bindings', {
                    'format': 'fdisbull-loader-entry-bindings-1', 'run': debug.run_id,
                    'source_sha256': project.meta['source_sha256'], 'dll_source_sha256': dll_hash,
                    'entry_address': hex(es['smc_module_entry']), 'runtime_image_base': hex(debug.runtime_base),
                    'dll_runtime_base': hex(db), 'modules': entry_modules, 'imports': bindings,
                    'entry_snapshot': recovery['entry'], 'tls_directory': row['tls_directory'],
                    'headers': [{'module': source.name, 'address': hex(debug.runtime_base),
                        'hex': read(debug.runtime_base, pe.optional_header.sizeof_headers).hex()},
                        {'module': library.name, 'address': hex(db),
                         'hex': read(db, dll.optional_header.sizeof_headers).hex()}],
                    'scope': 'Observed application entry after the two authored DLL attach callbacks; '
                             'other DLL initialization and hidden loader state remain outside this evidence'})
                main_segment('entry-to-report', target=es['smc_dll_report_call'])
                report_before = snapshot('report-call-before')
                row['report_call'] = debug.trace(name + '-report-call.json', count=1, timeout_ms=60000)
                remember(row['report_call'])
                assert int(debug.call('registers')['rip'], 16) == ds['dll_report']
                report_entry = snapshot('report-call-entry')
                reported = callback('dll-report')
                report_return = int(reported['exit']['general']['rax'], 16)
                assert report_return == 3
                milestone('reported', result=report_return)
                report_after = snapshot('report-call-return')
                report_binding = next(b for b in bindings if b['name'] == 'dll_report')
                recovery['calls'].append({'name': 'dll_report', 'callsite': hex(es['smc_dll_report_call']),
                    'return_address': hex(es['smc_dll_report_return']),
                    'iat_address': report_binding['iat_address'], 'target': report_binding['target'],
                    'before': report_before, 'entry': report_entry, 'return': report_after,
                    'trace': row['report_call'], 'implementation': None, 'callback': row['callbacks'][-1]})
                for index, expected in enumerate((0, 1, 0xffffffff, 0x1234)):
                    for api, stem in (('SetLastError', 'smc_set_last_error_call_'),
                                      ('GetLastError', 'smc_get_last_error_call_')):
                        current = int(debug.call('registers')['rip'], 16)
                        target = es[stem + str(index)]
                        if current != target:
                            main_segment('main-to-' + api + '-' + str(index), target=target)
                        api_before = snapshot(api + '-' + str(index) + '-before')
                        ram_ranges = [{'address': r['address'], 'length': r['length']} for r in all_ranges()
                                      if r['role'] not in ('exe-code', 'dll-code')]
                        code_ranges = [{'address': r['address'], 'length': r['length']} for r in all_ranges()
                                       if r['role'] in ('exe-code', 'dll-code')]
                        receipt = debug.import_call(name=name + '-' + api + '-' + str(index) + '.json',
                            memory_ranges=ram_ranges, code_ranges=code_ranges,
                            trace_implementation=True, timeout_ms=60000)
                        doc = remember(receipt); row['apis'].append(receipt)
                        assert doc['status'] == 'complete', doc
                        assert doc['implementation_contract']['status'] == 'proved_for_observed_implementation', doc
                        if api == 'GetLastError':
                            assert int(doc['contexts']['return']['general']['rax'], 16) == expected
                        api_after = snapshot(api + '-' + str(index) + '-return')
                        recovery['calls'].append({'name': api, 'callsite': hex(target),
                            'return_address': hex(target + 6), 'iat_address': doc['import']['runtime_iat_address'],
                            'target': doc['import']['target'], 'before': api_before, 'entry': None,
                            'return': api_after, 'trace': None, 'implementation': receipt, 'callback': None})
                        save()
                main_segment('main-to-exit', target=es['smc_exit_process_call'])
                final_data = read(es['smc_data_start'], 32)
                row['executable_data'] = {'entry': entry_data.hex(), 'final': final_data.hex()}
                exit_before = snapshot('exit-call-before')
                exit_modules = debug.call('modules')
                exit_resolution = resolve_loaded_export(exit_modules, 'kernel32.dll', 'ExitProcess', read)
                exit_iat = read(runtime_iat['ExitProcess'], 8)
                assert int.from_bytes(exit_iat, 'little') == int(exit_resolution['target'], 16)
                detach_address = int(loader_module['base'], 16) + detach_rva
                assert read(detach_address, 32) == bytes(loader_pe.get_content_from_virtual_address(loader_pe.imagebase + detach_rva, 32))
                detach_entry_bp = bp(detach_address)
                row['exit_call'] = debug.trace(name + '-exit-call.json', count=1, timeout_ms=60000)
                remember(row['exit_call'])
                exit_entry = snapshot('exit-call-entry')
                exit_registers = debug.call('registers')
                assert int(exit_registers['rip'], 16) == int(exit_resolution['target'], 16)
                assert int(exit_registers['general']['rsp'], 16) == main_stack - 48
                assert int.from_bytes(read(main_stack - 48, 8), 'little') == es['smc_module_unreachable']
                recovery['exit_binding'] = recovery_artifact('exit-import-binding', 'loader-exit-binding', {
                    'format': 'fdisbull-loader-exit-binding-1', 'run': debug.run_id,
                    'modules': exit_modules, 'resolution': exit_resolution, 'iat_address': hex(runtime_iat['ExitProcess']),
                    'iat_hex': exit_iat.hex(), 'entry_registers': exit_registers,
                    'callsite': hex(es['smc_exit_process_call']), 'call_hex': read(es['smc_exit_process_call'], 6).hex(),
                    'return_address': hex(es['smc_module_unreachable']), 'call_trace': row['exit_call']})
                recovery['calls'].append({'name': 'ExitProcess', 'callsite': hex(es['smc_exit_process_call']),
                    'return_address': hex(es['smc_module_unreachable']), 'iat_address': hex(runtime_iat['ExitProcess']),
                    'target': exit_resolution['target'], 'before': exit_before, 'entry': exit_entry,
                    'return': None, 'trace': row['exit_call'], 'implementation': None, 'callback': None})
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'breakpoint' and int(debug.call('registers')['rip'], 16) == detach_address, result
                delete(detach_entry_bp)
                prefix_entry = snapshot('process-detach-entry')
                prefix_registers = debug.call('registers')
                prefix_stack = int(prefix_registers['general']['rsp'], 16)
                peb = int.from_bytes(read(teb + 0x60, 8), 'little')
                ldr = int.from_bytes(read(peb + 0x18, 8), 'little')
                prefix = capture_loader_interval(debug, name=name + '-detach-selection-prefix.json',
                    role='detach_selection_prefix', start_address=detach_address, stop_address=dispatcher,
                    boundary_kind='callee-entry', expected_stack_delta=-0x50,
                    protected_ranges=recovery['protected_ranges'],
                    extra_ranges=[{'role': 'selector-stack', 'address': hex(prefix_stack - 0x50), 'length': 88},
                        {'role': 'selected-modref', 'address': hex(selected_modref), 'length': 256},
                        {'role': 'teb-prefix', 'address': hex(teb), 'length': 256},
                        {'role': 'peb-prefix', 'address': hex(peb), 'length': 256},
                        {'role': 'loader-data', 'address': hex(ldr), 'length': 256},
                        {'role': 'process-detaching', 'address': hex(int(loader_module['base'], 16) + 0x95938), 'length': 4}],
                    loader_module=loader_module, subject_module=loaded, subject_source_sha256=dll_hash,
                    max_steps=64, timeout_ms=60000)
                remember(prefix['artifact']); row['loader_intervals'].append(prefix['artifact'])
                assert record_dispatcher_selection(debug.call('registers'), 0)
                dispatch_entry = snapshot('detach-dispatcher-entry')
                row['loader_interval_boundaries']['detach_selection_prefix'] = {
                    'entry_snapshot': prefix_entry, 'exit_snapshot': dispatch_entry}
                row['loader_outer_edges'].append(recovery_artifact('exit-to-detach-dispatcher', 'loader-outer-edge', {
                    'before': exit_entry, 'after': dispatch_entry,
                    'scope': 'Opaque ExitProcess/loader prefix outside the complete MODULE_InitDLL capsule'}))
                detached = capsule(0, exit_entry)
                gap_before = detached['last_return']
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'exited' and result['session']['exit_code'] == 7, result
                row['terminal'] = result
                transition('detach-return-to-process-exit', 'ExitProcess/loader.run', gap_before, None, result)
                history()
                assert not owned
                row['source_milestones'] = verify_loader_observations(row['milestones'], exit_code=7)
                row['source_executable'] = verify_executable_observations(entry_data, final_data, exit_code=7)
                save()
        assert set(code_images) == {1, 2, 3}
        # Create a separate source analysis of the DLL. Derived versions retain
        # native module/RVA correspondence; foreign instructions never acquire
        # a fabricated address in the controller EXE's source project.
        dll_fdb = evidence / 'wine-smc-dll.fdb'
        assert not dll_fdb.exists()
        with Project.create(dll_fdb, library) as subject:
            subject.analyze(max_instructions=4096)
            versions = {1: subject.version(1)}
            for constant in (2, 3):
                patched = subject.patch(dll_symbols['dll_code_start'], code_images[constant].hex(),
                    label='Observed DLL constant ' + str(constant), version=versions[constant-1]['id'],
                    origin='Derived from actual Wine loaded-code snapshots; source DLL SHA256 ' + dll_hash)
                versions[constant] = subject.version(patched['version'])
            report['derived_dll_versions'] = versions
            for constant, version in versions.items():
                region = next(r for r in subject.regions(version['id']) if r.start <= dll_symbols['dll_code_start'] < r.start + len(r.data))
                offset = dll_symbols['dll_code_start'] - region.start
                assert region.data[offset:offset+len(original_code)] == code_images[constant]
        for identifier, raw in artifacts.items():
            assert _document(project, identifier)[1] == raw
    with Project(fdb) as project:
        for identifier, raw in artifacts.items(): assert _document(project, identifier)[1] == raw
        closed = [json.loads(r[0]) for r in project.db.execute("SELECT evidence FROM debug_events WHERE operation='close'")]
        assert len(closed) == 2 and all(r['process_reaped'] is True for r in closed)
        from fdisbull.pe_loader_module_recovery import VERIFIED_PROCESS_ATTACH_ENVIRONMENT, expand_loader_module_contraction
        from test_pe_loader_source_spec import verify_loader_module_source_spec
        from test_pe_wine_loader_source_spec import verify_wine_loader_source_spec
        from test_pe_wine_loader_interval_source_spec import verify_wine_loader_interval_source_spec
        from test_pe_process_attach_source_spec import verify_process_attach_source_spec
        from test_wine_loader_dispatch_replay import replay_wine_loader_capsule
        from test_wine_loader_intervals import replay_wine_loader_interval
        from test_wine_process_attach import replay_process_attach
        from fdisbull.pe_wine_loader_contracts import expand_wine_loader_contract
        from fdisbull.pe_wine_loader_intervals import expand_wine_loader_interval
        from fdisbull.pe_wine_process_attach import expand_wine_process_attach
        with Project(evidence / 'wine-smc-dll.fdb') as subject:
            report['whole_module'] = {}
            caller_proofs = 0
            full_attach_proofs = 0
            for name, row in report['runs'].items():
                capsule_docs = {reference['artifact']: _document(project, reference['artifact'])[0]
                                for reference in row['loader_capsules']}
                interval_docs = {reference['artifact']: _document(project, reference['artifact'])[0]
                                 for reference in row['loader_intervals']}
                process_attach_doc = _document(project, row['loader_process_attach']['artifact'])[0]
                embedded_identifier = process_attach_doc['module_span']['artifact']['artifact']
                report.setdefault('loader_process_attach_replays', {})[name] = replay_process_attach(
                    process_attach_doc, module_capsule=capsule_docs[embedded_identifier])
                assert sorted(document['role'] for document in interval_docs.values()) == [
                    'attach_success_tail', 'detach_selection_prefix']
                report.setdefault('loader_capsule_replays', {})[name] = {
                    identifier: replay_wine_loader_capsule(document)
                    for identifier, document in capsule_docs.items()}
                report.setdefault('loader_interval_replays', {})[name] = {
                    identifier: replay_wine_loader_interval(document)
                    for identifier, document in interval_docs.items()}
                proof = project.debug_recover_loader_module(subject, row,
                    environment_contract=VERIFIED_PROCESS_ATTACH_ENVIRONMENT, loader_source=loader_path, timeout_ms=60000)
                report['whole_module'][name] = proof
                save()
                assert proof['status'] == 'recovered_under_environment_contract', proof.get('reason')
                dispatch_specs = []
                assert len(proof['loader_dispatch_contracts']) == 2
                for dispatch in proof['loader_dispatch_contracts']:
                    capsule_doc = capsule_docs[dispatch['artifact']]
                    contract, dispatch_proof = dispatch['contract'], dispatch['proof']
                    dispatch_specs.append(verify_wine_loader_source_spec(dispatch_proof,
                        contract=contract, capsule=capsule_doc))
                    assert expand_wine_loader_contract(dispatch_proof, capsule_doc, contract) == {
                        'capsule': capsule_doc, 'contract': contract}
                report.setdefault('loader_dispatch_source_specs', {})[name] = dispatch_specs
                interval_specs = []
                assert sorted(caller['role'] for caller in proof['loader_caller_contracts']) == [
                    'attach_success_tail', 'detach_selection_prefix']
                for caller in proof['loader_caller_contracts']:
                    interval_doc = interval_docs[caller['artifact']]
                    contract, interval_proof = caller['contract'], caller['proof']
                    interval_specs.append(verify_wine_loader_interval_source_spec(interval_proof,
                        contract=contract, interval=interval_doc))
                    assert expand_wine_loader_interval(interval_proof, interval_doc, contract) == {
                        'interval': interval_doc, 'contract': contract}
                    caller_proofs += 1
                report.setdefault('loader_interval_source_specs', {})[name] = interval_specs
                full_attach = proof['loader_process_attach_contract']
                assert full_attach['artifact'] == row['loader_process_attach']['artifact']
                assert full_attach['coverage']['dispatcher_artifact'] == embedded_identifier
                full_contract, full_proof = full_attach['contract'], full_attach['proof']
                attach_dispatch = next(p for p in proof['loader_dispatch_contracts'] if p['phase'] == 'attach')
                assert full_contract['module_contract'] == attach_dispatch['contract']
                assert full_proof['module_contract']['source'] == attach_dispatch['proof']['source']
                nested_source_spec = verify_wine_loader_source_spec(full_proof['module_contract'],
                    contract=full_contract['module_contract'], capsule=capsule_docs[embedded_identifier])
                report.setdefault('loader_process_attach_module_source_specs', {})[name] = nested_source_spec
                assert full_proof['checks']['instructions'] == len(process_attach_doc['steps'])
                assert full_proof['checks']['path_cover'] == 'complete'
                assert set(full_proof['transfer']['vectors']) == {'xmm0', 'xmm1'}
                assert len(full_proof['transfer']['protected_memory']) == 594
                assert full_proof['code_versions'] == process_attach_doc['code_versions']
                full_spec = verify_process_attach_source_spec(full_proof,
                    contract=full_contract, observation=process_attach_doc)
                assert full_spec['list_append']['new_node'] == int(full_contract['addresses']['modref'], 16) + 0x20
                assert full_spec['list_append']['old_tail'] == int(full_contract['addresses']['old_tail'], 16)
                assert expand_wine_process_attach(full_proof, process_attach_doc, full_contract,
                    capsule_docs[embedded_identifier]) == {'capsule': process_attach_doc,
                        'contract': full_contract, 'module_capsule': capsule_docs[embedded_identifier]}
                assert proof['contraction']['process_attach_contract'] == full_proof['sha256']
                report.setdefault('loader_process_attach_source_specs', {})[name] = full_spec
                full_attach_proofs += 1
                assert len(proof['remaining_loader_intervals']) == 4
                assert sum(edge.get('status') == 'proved_native_dispatch_interval'
                           for edge in proof['environment_edges']) == 2
                source_proof = verify_loader_module_source_spec(proof, symbols=row['runtime_symbols'])
                assert expand_loader_module_contraction(proof['contraction'], row) == row
                report.setdefault('whole_module_source_specs', {})[name] = source_proof
            assert caller_proofs == 4
            assert full_attach_proofs == 2
            assert report['whole_module']['baseline']['whole_module_recovery']['main']['exe_memory'] == \
                   report['whole_module']['repeat']['whole_module_recovery']['main']['exe_memory']
            assert report['whole_module']['baseline']['whole_module_recovery']['final_dll_memory'] == \
                   report['whole_module']['repeat']['whole_module_recovery']['final_dll_memory']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == report['source_sha256']
    assert hashlib.sha256(library.read_bytes()).hexdigest() == dll_hash
    report.update(status='passed', reopened=True, all_artifacts_preserved=True,
                  source_files_preserved=True, owned_guests_reaped=True)
    save()
