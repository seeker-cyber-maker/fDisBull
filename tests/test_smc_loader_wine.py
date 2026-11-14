"""Opt-in real Wine loader, DLL self-modification and implementation checks.

The selected fixture directory must contain the homegrown smc-init.exe and
SMCINIT.dll. All guest observations stay in the private external evidence FDB.
Callback replay checks the observed inputs; it is not a proof of Wine's loader.
"""
import base64
import hashlib
import json
import time

from fdisbull.debug_semantics import normalize_trace, PE_TRACE_SEMANTICS
from fdisbull.project import Project
from test_smc_function_wine import _inputs, _document
from test_wine_loader_initialization import (
    inspect_loader_fixtures, verify_loader_observations, verify_executable_observations,
)


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

                milestone('before-tls')
                tls_bp, main_bp = bp(ds['dll_tls_callback']), bp(ds['dll_entry'])
                debug.loader_control(stop_on_load=False)
                gap_before = snapshot('before-loader-to-tls')
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'breakpoint'
                assert int(debug.call('registers')['rip'], 16) == ds['dll_tls_callback']
                delete(tls_bp)
                gap_after = snapshot('tls-attach-entry')
                transition('loader-to-tls-attach', 'loader.run', gap_before, gap_after, result)
                assert int(debug.call('registers')['general']['rdx'], 16) == 1
                callback('tls-attach'); milestone('tls-attached')
                gap_before = snapshot('tls-attach-return')
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'breakpoint'
                assert int(debug.call('registers')['rip'], 16) == ds['dll_entry']
                delete(main_bp)
                gap_after = snapshot('dll-attach-entry')
                transition('tls-return-to-dll-attach', 'loader.run', gap_before, gap_after, result)
                assert int(debug.call('registers')['general']['rdx'], 16) == 1
                callback('dll-attach'); milestone('dll-attached')
                gap_before = snapshot('dll-attach-return')
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
                detach_bps = {bp(ds[n]): ds[n] for n in ('dll_tls_callback', 'dll_entry')}
                exit_before = snapshot('exit-call-before')
                exit_modules = debug.call('modules')
                exit_resolution = resolve_loaded_export(exit_modules, 'kernel32.dll', 'ExitProcess', read)
                exit_iat = read(runtime_iat['ExitProcess'], 8)
                assert int.from_bytes(exit_iat, 'little') == int(exit_resolution['target'], 16)
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
                gap_before = exit_entry
                for index in range(2):
                    result = debug.run(timeout_ms=60000)
                    assert result['outcome'] == 'breakpoint', result
                    registers = debug.call('registers'); ip = int(registers['rip'], 16)
                    identifier = next(k for k, a in detach_bps.items() if a == ip)
                    delete(identifier); del detach_bps[identifier]
                    gap_after = snapshot('detach-' + str(index) + '-entry')
                    transition('exit-to-detach-' + str(index), 'ExitProcess/loader.run', gap_before, gap_after, result)
                    assert int(registers['general']['rdx'], 16) == 0
                    callback('detach-' + str(index)); milestone('detached')
                    gap_before = snapshot('detach-' + str(index) + '-return')
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
        from fdisbull.pe_loader_module_recovery import ENVIRONMENT, expand_loader_module_contraction
        from test_pe_loader_source_spec import verify_loader_module_source_spec
        with Project(evidence / 'wine-smc-dll.fdb') as subject:
            report['whole_module'] = {}
            for name, row in report['runs'].items():
                proof = project.debug_recover_loader_module(subject, row,
                    environment_contract=ENVIRONMENT, timeout_ms=60000)
                report['whole_module'][name] = proof
                save()
                assert proof['status'] == 'recovered_under_environment_contract', proof.get('reason')
                source_proof = verify_loader_module_source_spec(proof, symbols=row['runtime_symbols'])
                assert expand_loader_module_contraction(proof['contraction'], row) == row
                report.setdefault('whole_module_source_specs', {})[name] = source_proof
            assert report['whole_module']['baseline']['whole_module_recovery']['main']['exe_memory'] == \
                   report['whole_module']['repeat']['whole_module_recovery']['main']['exe_memory']
            assert report['whole_module']['baseline']['whole_module_recovery']['final_dll_memory'] == \
                   report['whole_module']['repeat']['whole_module_recovery']['final_dll_memory']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == report['source_sha256']
    assert hashlib.sha256(library.read_bytes()).hexdigest() == dll_hash
    report.update(status='passed', reopened=True, all_artifacts_preserved=True,
                  source_files_preserved=True, owned_guests_reaped=True)
    save()
