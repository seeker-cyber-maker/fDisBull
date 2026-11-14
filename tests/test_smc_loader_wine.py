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
            report['runs'][name] = row; save()
            with project.debugger(str(qemu), str(source.parent), kernel=str(kernel), initramfs=str(runtime),
                    files=[source.name, library.name], version=1, memory_mib=4096,
                    loader_mode='process-create') as debug:
                row['runtime'] = debug.metadata
                owned, cursor = {}, 0

                def remember(receipt):
                    doc, raw = _document(project, receipt['artifact'])
                    artifacts[receipt['artifact']] = raw
                    return doc

                def artifact(label, kind, doc):
                    receipt = debug._artifact(name + '-' + label + '.json', kind,
                        json.dumps(doc, indent=2).encode(), {'status': doc.get('status', 'observed')})
                    remember(receipt)
                    return receipt

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
                code_start, code_length = ds['dll_code_start'], len(original_code)
                data_start = ds['dll_data_start']
                row['runtime_symbols'] = {'exe': es, 'dll': ds}
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
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'breakpoint'
                assert int(debug.call('registers')['rip'], 16) == ds['dll_tls_callback']
                delete(tls_bp)
                assert int(debug.call('registers')['general']['rdx'], 16) == 1
                callback('tls-attach'); milestone('tls-attached')
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'breakpoint'
                assert int(debug.call('registers')['rip'], 16) == ds['dll_entry']
                delete(main_bp)
                assert int(debug.call('registers')['general']['rdx'], 16) == 1
                callback('dll-attach'); milestone('dll-attached')
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'entry', result
                assert debug.registers()['project_address'] == hex(symbols['smc_module_entry'])
                history(); milestone('exe-entry')
                entry_data = read(es['smc_data_start'], 32)
                run_to(es['smc_dll_report_call'])
                row['report_call'] = debug.trace(name + '-report-call.json', count=1, timeout_ms=60000)
                remember(row['report_call'])
                assert int(debug.call('registers')['rip'], 16) == ds['dll_report']
                reported = callback('dll-report')
                report_return = int(reported['exit']['general']['rax'], 16)
                assert report_return == 3
                milestone('reported', result=report_return)
                for index, expected in enumerate((0, 1, 0xffffffff, 0x1234)):
                    for api, stem in (('SetLastError', 'smc_set_last_error_call_'),
                                      ('GetLastError', 'smc_get_last_error_call_')):
                        current = int(debug.call('registers')['rip'], 16)
                        target = es[stem + str(index)]
                        if current != target: run_to(target)
                        receipt = debug.import_call(name=name + '-' + api + '-' + str(index) + '.json',
                            memory_ranges=[{'address': hex(es['smc_data_start']), 'length': 32}],
                            trace_implementation=True, timeout_ms=60000)
                        doc = remember(receipt); row['apis'].append(receipt)
                        assert doc['status'] == 'complete', doc
                        assert doc['implementation_contract']['status'] == 'proved_for_observed_implementation', doc
                        if api == 'GetLastError':
                            assert int(doc['contexts']['return']['general']['rax'], 16) == expected
                        save()
                run_to(es['smc_exit_process_call'])
                final_data = read(es['smc_data_start'], 32)
                row['executable_data'] = {'entry': entry_data.hex(), 'final': final_data.hex()}
                detach_bps = {bp(ds[n]): ds[n] for n in ('dll_tls_callback', 'dll_entry')}
                row['exit_call'] = debug.trace(name + '-exit-call.json', count=1, timeout_ms=60000)
                remember(row['exit_call'])
                for index in range(2):
                    result = debug.run(timeout_ms=60000)
                    assert result['outcome'] == 'breakpoint', result
                    registers = debug.call('registers'); ip = int(registers['rip'], 16)
                    identifier = next(k for k, a in detach_bps.items() if a == ip)
                    delete(identifier); del detach_bps[identifier]
                    assert int(registers['general']['rdx'], 16) == 0
                    callback('detach-' + str(index)); milestone('detached')
                result = debug.run(timeout_ms=60000)
                assert result['outcome'] == 'exited' and result['session']['exit_code'] == 7, result
                row['terminal'] = result
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
    assert hashlib.sha256(source.read_bytes()).hexdigest() == report['source_sha256']
    assert hashlib.sha256(library.read_bytes()).hexdigest() == dll_hash
    report.update(status='passed', reopened=True, all_artifacts_preserved=True,
                  source_files_preserved=True, owned_guests_reaped=True)
    save()
