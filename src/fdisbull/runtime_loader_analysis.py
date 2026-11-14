"""Bind native loader composition evidence without inferring loader semantics."""
from copy import deepcopy
import hashlib
import json

from .wine_arch import validate_context
from .wine_import_calls import resolve_loaded_export
from .debug_semantics import PE_TRACE_SEMANTICS


def _number(value):
    if type(value) is int:
        result = value
    elif isinstance(value, str) and value.startswith('0x'):
        result = int(value, 16)
    else:
        raise ValueError('Exact PE64 address required')
    if not 0 <= result < 1 << 64:
        raise ValueError('PE64 address wraps')
    return result


def _source(project):
    import lief
    version = project.version(1)
    row = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()
    if version['parent'] is not None or row is None or row[0] is None:
        raise ValueError('Original preserved PE source is required')
    raw = bytes(row[0])
    if hashlib.sha256(raw).hexdigest() != project.meta['source_sha256']:
        raise ValueError('Original source bytes do not match their recorded identity')
    pe = lief.PE.parse(list(raw))
    if (pe is None or int(pe.header.machine) != 0x8664 or int(pe.optional_header.magic) != 0x20b
            or pe.data_directories[14].rva):
        raise ValueError('Loader composition requires native AMD64 PE sources without CLR')
    return raw, pe


def _journal_artifacts(project, run):
    """Load bounded JSON objects and their unique matching native journal rows."""
    rows = list(project.db.execute('SELECT * FROM debug_artifacts WHERE run=?', (run,)))
    if not 1 <= len(rows) <= 512:
        raise ValueError('Loader composition artifact budget exceeded')
    journal = {}
    for event in project.db.execute("SELECT sequence,evidence FROM debug_events WHERE run=? AND operation='artifact' ORDER BY sequence", (run,)):
        receipt = json.loads(event['evidence'])
        identifier = receipt.get('artifact')
        if identifier in journal:
            raise ValueError('Duplicate artifact identity in native journal')
        journal[identifier] = (event['sequence'], receipt)
    documents, receipts, total = {}, {}, 0
    for row in rows:
        raw = bytes(row['data']); total += len(raw)
        if total > 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise ValueError('Loader artifact hash or total-byte budget differs')
        if row['id'] not in journal:
            raise ValueError('Artifact lacks its native journal identity')
        sequence, receipt = journal[row['id']]
        if (receipt.get('run') != run or receipt.get('version') != 1
                or receipt.get('sha256') != row['sha256'] or receipt.get('kind') != row['kind']
                or receipt.get('size') != len(raw)):
            raise ValueError('Artifact and native journal identities differ')
        document = json.loads(raw)
        if not isinstance(document, dict):
            raise ValueError('Loader artifacts require JSON object documents')
        documents[row['id']] = document
        receipts[row['id']] = {'sequence': sequence, 'sha256': row['sha256'], 'kind': row['kind'],
            'run': run, 'version': 1, 'size': len(raw)}
    return documents, receipts


def _reference(reference, documents, receipts, kind=None):
    if not isinstance(reference, dict) or not isinstance(reference.get('artifact'), str):
        raise ValueError('An exact stored artifact reference is required')
    identifier = reference['artifact']
    if identifier not in documents or (kind is not None and receipts[identifier]['kind'] != kind):
        raise ValueError('Artifact reference has the wrong owning run or kind')
    for key in ('sha256', 'kind', 'run', 'version', 'size'):
        if key in reference and reference[key] != receipts[identifier][key]:
            raise ValueError('Artifact reference contradicts its stored identity')
    return documents[identifier]


def _resolve(resolution, modules, module, name):
    rows, cursor = resolution['reads'], 0
    def read(address, length):
        nonlocal cursor
        if cursor >= len(rows):
            raise ValueError('Missing loaded-export memory observation')
        row = rows[cursor]; cursor += 1
        raw = bytes.fromhex(row['hex'])
        if (_number(row['address']) != address or len(raw) != length
                or hashlib.sha256(raw).hexdigest() != row['sha256']):
            raise ValueError('Loaded-export memory ledger differs')
        return raw
    actual = resolve_loaded_export(modules, module, name, read)
    if cursor != len(rows) or actual != resolution:
        raise ValueError('Loaded-export resolution differs from its complete ledger')


def _cells(rows, *, maximum=2048, range_limit=64):
    if not isinstance(rows, list) or len(rows) > range_limit:
        raise ValueError('Bounded snapshot ranges required')
    result = {}
    for row in rows:
        address, raw = _number(row['address']), bytes.fromhex(row['hex'])
        if not raw or address + len(raw) > 1 << 64:
            raise ValueError('Snapshot address range is empty or wraps')
        for k, byte in enumerate(raw):
            if address + k in result:
                raise ValueError('Snapshot ranges overlap')
            result[address + k] = byte
    if len(result) > maximum:
        raise ValueError('Snapshot byte budget exceeded')
    return result


def _native_exit(project, run, reported):
    exits = []
    for event in project.db.execute("SELECT sequence,evidence FROM debug_events WHERE run=? AND operation='run' ORDER BY sequence", (run,)):
        outcome = json.loads(event['evidence'])
        if outcome.get('outcome') == 'exited': exits.append((event['sequence'], outcome))
    if (len(exits) != 1 or exits[0][1] != reported or reported.get('run') != run
            or reported.get('session', {}).get('state') != 'exited'
            or type(reported['session'].get('exit_code')) is not int):
        raise ValueError('Terminal report differs from its actual native process-exit event')
    return exits[0][0]


def _require_protected_memory_join(rows, expected, cells, label):
    observed = _cells(rows, maximum=65536, range_limit=4096)
    if not cells <= observed.keys() or any(observed[a] != expected[a] for a in cells):
        raise ValueError('Dispatcher protected-memory boundary differs: ' + label)


def _bind_loader_capsules(report, *, run, exe_image, dll_image, documents, receipts, protected, terminal_sequence):
    """Bind both native dispatcher bodies to the exact journaled callbacks.

    This establishes provenance and joins only. Instruction semantics and the
    protected-memory frame are re-proved by the loader capsule verifier.
    """
    references = report.get('loader_capsules')
    if not isinstance(references, list) or len(references) != 2:
        raise ValueError('Verified loader composition requires both attach/detach capsules')
    selection = report.get('loader_selection', {})
    source = selection.get('source', {})
    digest = source.get('source_sha256')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Exact original Wine loader source identity is required')
    def doc(reference, kind=None):
        return _reference(reference, documents, receipts, kind)
    def sequence(reference):
        doc(reference)
        return receipts[reference['artifact']]['sequence']
    fields = ('name', 'base', 'size', 'bits', 'generation')
    def same_module(a, b):
        return all(a.get(k) == b.get(k) for k in fields)
    candidates = [reference for reference in selection.get('candidates', [])
                  if doc(reference, 'loader-dispatch-selection').get('selected') is True]
    if len(candidates) != 2 or sequence(candidates[0]) >= sequence(candidates[1]):
        raise ValueError('Both dispatcher capsules require their own ordered native selection')
    def protected_rows(rows):
        mapping = {}
        for row in rows:
            role, address, raw = row.get('role'), _number(row['address']), bytes.fromhex(row['hex'])
            if role in mapping or role not in protected or protected[role] != (address, len(raw)):
                raise ValueError('A capsule omits or rewrites a complete protected source range')
            mapping[role] = (address, len(raw))
        if mapping != protected:
            raise ValueError('A capsule must observe every protected image, global and IAT word')
        return _cells(rows)
    result = []
    outer_references = report.get('loader_outer_edges')
    if not isinstance(outer_references, list) or len(outer_references) != 2:
        raise ValueError('The complete outer loader/ExitProcess prefixes must remain explicit')
    for index, reference in enumerate(references):
        capsule = doc(reference, 'wine-loader-dispatch-capsule')
        phase, reason = ('attach', 1) if index == 0 else ('detach', 0)
        if (capsule.get('format') != 'fdisbull-wine-loader-dispatch-capsule-1'
                or capsule.get('status') != 'complete' or capsule.get('semantics') != PE_TRACE_SEMANTICS
                or capsule.get('run') != run or capsule.get('controller_source_sha256') != exe_image['sha256']
                or capsule.get('subject_source_sha256') != dll_image['sha256']
                or not same_module(capsule.get('subject_module', {}), dll_image['module'])
                or not same_module(capsule.get('loader_module', {}), selection.get('module', {}))
                or capsule['loader_module'].get('source_sha256') != digest
                or capsule.get('summaries') != []):
            raise ValueError('Dispatcher capsule source, owner, native run or completeness differs')
        ranges = {r['role']: (_number(r['address']), r['length']) for r in capsule['protected_ranges']}
        if len(ranges) != len(capsule['protected_ranges']) or ranges != protected:
            raise ValueError('Dispatcher protected ranges differ from complete source definitions')
        validate_context(capsule['entry'], 64); validate_context(capsule['exit'], 64)
        selected = doc(candidates[index])
        if (selected.get('run') != run or selected.get('source') != source
                or selected.get('registers') != capsule['entry']
                or not same_module(selected.get('module', {}), capsule['loader_module'])
                or _number(selected['registers']['rip']) != _number(selection['entry_address'])
                or _number(selected['modref']) != _number(capsule['selection']['modref'])
                or _number(selected['base_pointer_address']) != _number(selected['modref']) + 0x30
                or bytes.fromhex(selected['base_pointer_hex']) != _number(dll_image['base']).to_bytes(8, 'little')
                or _number(capsule['entry']['general']['rdx']) & 0xffffffff != reason
                or capsule['selection'].get('reason_low32') != reason
                or _number(capsule['selection']['dll_base']) != _number(dll_image['base'])):
            raise ValueError('Dispatcher source selection is detached from its actual invocation')
        for state in (capsule['modules_before'], capsule['modules_after']):
            for expected in (capsule['loader_module'], dll_image['module']):
                owners = [m for m in state['modules'] if _number(m['base']) == _number(expected['base'])]
                if len(owners) != 1 or not same_module(owners[0], expected):
                    raise ValueError('Dispatcher source module generation changes within its capsule')
        outer_reference = outer_references[index]
        outer = doc(outer_reference, 'loader-outer-edge')
        before = doc(outer['before'], 'loader-frame-snapshot')
        after = doc(outer['after'], 'loader-frame-snapshot')
        if (after['registers'] != capsule['entry']
                or not sequence(outer['before']) < sequence(candidates[index]) < sequence(outer['after']) < sequence(outer_reference)
                or sequence(outer_reference) >= sequence(reference)):
            raise ValueError('An outer loader prefix is detached from its actual dispatcher entry')
        if index == 0:
            if (outer['before']['artifact'] != report['recovery']['snapshots'][0]['artifact']
                    or outer['after']['artifact'] != doc(report['recovery']['transitions'][0])['before']['artifact']):
                raise ValueError('The pre-dispatch initialization interval was omitted or replaced')
        elif outer['before']['artifact'] != report['recovery']['calls'][-1]['entry']['artifact']:
            raise ValueError('The ExitProcess prefix does not start at its actual imported entry')
        framed = {a for role, (start, length) in protected.items()
                  if index or not role.startswith('iat-') for a in range(start, start + length)}
        a, b = _cells(before['memory']), _cells(after['memory'])
        if not framed <= a.keys() or not framed <= b.keys() or any(a[p] != b[p] for p in framed):
            raise ValueError('Observed outer dispatcher prefix violates its remaining source-memory frame')
        return_snapshots = [r for r in report['recovery']['snapshots'] if
            doc(r, 'loader-frame-snapshot').get('label') == phase + '-dispatcher-return']
        if len(return_snapshots) != 1 or doc(return_snapshots[0])['registers'] != capsule['exit']:
            raise ValueError('The dispatcher return needs its own actual outer-boundary snapshot')
        if sequence(reference) >= sequence(return_snapshots[0]):
            raise ValueError('Dispatcher return snapshot chronology differs')
        steps = capsule.get('steps')
        if not isinstance(steps, list) or not 1 <= len(steps) <= 2048:
            raise ValueError('Dispatcher native instruction budget differs')
        if steps[0]['event']['registers'] != capsule['entry'] or steps[-1]['after'] != capsule['exit']:
            raise ValueError('Dispatcher entry/exit does not match its complete native body')
        for step_index, step in enumerate(steps):
            event = step['event']; validate_context(event['registers'], 64); validate_context(step['after'], 64)
            identity, observation = event['identity'], event['observation']
            if (event.get('project_address') is not None or identity.get('project_address') is not None
                    or identity.get('source_version') != 1 or identity.get('context') != 'flat'
                    or identity.get('runtime_address') != event['address'] or event['address'] != event['registers']['rip']
                    or observation.get('registers_stage') != 'before-instruction'
                    or observation.get('instruction_completed') is not True
                    or event['registers']['thread'] != capsule['entry']['thread']
                    or step['after']['thread'] != capsule['entry']['thread']
                    or (step_index and event['registers'] != steps[step_index - 1]['after'])):
                raise ValueError('Dispatcher steps rewrite their actual foreign-module native identity')
            before, after = protected_rows(step['protected_before']), protected_rows(step['protected_after'])
            if step_index and before != protected_rows(steps[step_index - 1]['protected_after']):
                raise ValueError('Dispatcher protected-state prefix is discontinuous')
            read = step['code_read']; raw = bytes.fromhex(read['hex'])
            executed = bytes.fromhex(event.get('execution_bytes', event['bytes']))
            address = _number(event['address'])
            if (read['address'] != event['address'] or hashlib.sha256(raw).hexdigest() != read['sha256']
                    or not raw.startswith(executed)):
                raise ValueError('Dispatcher instruction differs from its exact hashed native read')
            owners = [m for m in capsule['modules_before']['modules'] if _number(m['base']) <= address
                      and address + len(executed) <= _number(m['base']) + m['size']]
            if len(owners) != 1 or not same_module(read['module'], owners[0]):
                raise ValueError('Dispatcher instruction lacks its exact loaded-module owner')
        owned_cells = {a for start, length in protected.values() for a in range(start, start + length)}
        initial_union = _cells(capsule['entry_memory'], maximum=65536, range_limit=4096)
        final_union = _cells(capsule['exit_memory'], maximum=65536, range_limit=4096)
        first_frame, last_frame = protected_rows(steps[0]['protected_before']), protected_rows(steps[-1]['protected_after'])
        if (not owned_cells <= initial_union.keys() or not owned_cells <= final_union.keys()
                or any(initial_union[a] != first_frame[a] or final_union[a] != last_frame[a] for a in owned_cells)):
            raise ValueError('Dispatcher source-memory entry/return joins disagree despite their contexts')
        _require_protected_memory_join(doc(outer['after'])['memory'], first_frame, owned_cells, 'entry snapshot')
        _require_protected_memory_join(doc(return_snapshots[0])['memory'], last_frame, owned_cells, 'return snapshot')
        callbacks = capsule.get('callbacks'); spans = capsule.get('callback_spans')
        indices = (0, 1) if index == 0 else (3, 4)
        if not isinstance(callbacks, list) or len(callbacks) != 2 or not isinstance(spans, list) or len(spans) != 2:
            raise ValueError('Both authored callback bodies must be part of each dispatcher capsule')
        callback_refs = [report['callbacks'][i] for i in indices]
        order = [sequence(candidates[index]), *[sequence(r) for r in callback_refs], sequence(reference)]
        if order != sorted(set(order)):
            raise ValueError('Dispatcher selection/body/callback chronology differs from its native journal')
        previous_last = -1
        for position, (view, span, callback_ref) in enumerate(zip(callbacks, spans, callback_refs, strict=True)):
            original = doc(callback_ref, 'dll-callback')
            if ({k: v for k, v in view.items() if k != 'independent_replay'} !=
                    {k: v for k, v in original.items() if k != 'independent_replay'}):
                raise ValueError('Dispatcher callback view differs from its actual journaled source body')
            first, last = span['first_step'], span['last_step']
            expected_role = ('tls-' if position == 0 else 'dll-') + phase
            if (type(first) is not int or type(last) is not int or not previous_last < first <= last < len(steps)
                    or span['role'] != expected_role or original['source_role'] != expected_role):
                raise ValueError('Dispatcher callback spans do not establish the source TLS/DllMain order')
            body = steps[first:last + 1]
            if (len(body) != len(original['steps']) or original['entry'] != body[0]['event']['registers']
                    or original['exit'] != body[-1]['after'] or any(a['event'] != b['event'] or a['after'] != b['after']
                       for a, b in zip(original['steps'], body, strict=True))):
                raise ValueError('Dispatcher callback span is detached from its exact native instructions')
            dll_cells = {a for role, (start, length) in protected.items() if role in ('dll-code', 'dll-data')
                         for a in range(start, start + length)}
            for native, capsule_step in zip(original['steps'], body, strict=True):
                for field, capsule_field in (('memory_before', 'protected_before'), ('memory_after', 'protected_after')):
                    a, b = _cells(native[field]), protected_rows(capsule_step[capsule_field])
                    if not dll_cells <= a.keys() or any(a[p] != b[p] for p in dll_cells):
                        raise ValueError('Dispatcher callback memory differs from its journaled source frame')
            previous_last = last
        edge = doc(report['recovery']['transitions'][1 if index == 0 else 4])
        before, after = doc(edge['before']), doc(edge['after'])
        left = protected_rows(steps[spans[0]['last_step']]['protected_after'])
        right = protected_rows(steps[spans[1]['first_step']]['protected_before'])
        _require_protected_memory_join(before['memory'], left, owned_cells, 'inner callback return')
        _require_protected_memory_join(after['memory'], right, owned_cells, 'inner next callback entry')
        result.append({'artifact': reference['artifact'], 'capsule': capsule, 'phase': phase,
            'callback_artifacts': [r['artifact'] for r in callback_refs], 'selection_artifact': candidates[index]['artifact'],
            'outer_prefix': deepcopy(outer_reference), 'entry_snapshot': deepcopy(outer['after']),
            'exit_snapshot': deepcopy(return_snapshots[0]), 'outer_prefix_frame_bytes': len(framed)})
    if sequence(references[0]) >= sequence(report['recovery']['entry']) or sequence(references[1]) >= terminal_sequence:
        raise ValueError('Dispatcher capsules do not precede their main-entry/terminal boundaries')
    return result


def load_loader_evidence(project, dll_project, run_report, *, require_loader_capsules=False):
    """Return hash-bound observations and source images for a semantic checker.

    Native equality at a loader gap is deliberately not a universal frame
    condition. The composition checker must expose that condition explicitly.
    """
    if not isinstance(run_report, dict) or 'recovery' not in run_report:
        raise ValueError('Fresh full-range loader composition evidence is required')
    report = deepcopy(run_report); recovery = report['recovery']
    if recovery.get('format') != 'fdisbull-native-loader-composition-evidence-1':
        raise ValueError('Unknown loader composition observation format')
    exe_raw, exe = _source(project); dll_raw, dll = _source(dll_project)
    if exe.has_tls or not dll.has_tls or not int(dll.header.characteristics) & 0x2000:
        raise ValueError('Expected native EXE plus authored TLS DLL')
    runtime = report['runtime']; module = report['loaded_module']
    if (runtime.get('backend') != 'wine-qemu' or runtime.get('bits') != 64
            or runtime.get('loader_mode') != 'process-create'
            or runtime.get('source_sha256') != project.meta['source_sha256']
            or runtime.get('version_sha256') != project.version(1)['sha256']):
        raise ValueError('Native loader controller source/profile identity differs')
    exe_base, dll_base = _number(runtime['runtime_image_base']), _number(module['base'])
    if (_number(runtime['static_image_base']) != exe.imagebase or module['bits'] != 64
            or module['size'] != dll.optional_header.sizeof_image or module['generation'] < 1
            or module['name'].casefold() != dll_project.meta['filename'].casefold()):
        raise ValueError('Observed DLL mapping differs from its original source')
    source_imports = {}
    for imported in exe.imports:
        for entry in imported.entries:
            if not entry.name or entry.name in source_imports:
                raise ValueError('Duplicate or unnamed source imports are outside this profile')
            source_imports[entry.name] = {'module': imported.name,
                'iat_address': hex(exe_base + entry.iat_address)}
    expected_imports = {'SetLastError': 'kernel32.dll', 'GetLastError': 'kernel32.dll',
        'ExitProcess': 'kernel32.dll', 'dll_report': module['name'].casefold()}
    if {n: r['module'].casefold() for n, r in source_imports.items()} != expected_imports or list(dll.imports):
        raise ValueError('Unexpected source import graph')
    def image(pe, base, prefix):
        symbols = {e.name: hex(base + e.address) for e in pe.get_export().entries}
        supplied = report['runtime_symbols'][prefix]
        if {n: _number(v) for n, v in supplied.items()} != {n: _number(v) for n, v in symbols.items()}:
            raise ValueError('Runtime exported symbols differ from source RVA identity')
        start = _number(symbols['smc_module_entry' if prefix == 'exe' else 'dll_code_start'])
        end = _number(symbols['smc_module_end' if prefix == 'exe' else 'dll_code_end'])
        data = _number(symbols['smc_data_start' if prefix == 'exe' else 'dll_data_start'])
        data_end = _number(symbols['smc_data_end' if prefix == 'exe' else 'dll_data_end'])
        if not 1 <= end - start <= 512 or not 1 <= data_end - data <= 128:
            raise ValueError('Authored source code/data budget exceeded')
        return {'base': hex(base), 'symbols': symbols,
            'code': {'address': hex(start), 'hex': bytes(pe.get_content_from_virtual_address(start - base + pe.imagebase, end - start)).hex()},
            'globals': {'address': hex(data), 'hex': bytes(pe.get_content_from_virtual_address(data - base + pe.imagebase, data_end - data)).hex()}}
    exe_image, dll_image = image(exe, exe_base, 'exe'), image(dll, dll_base, 'dll')
    exe_image.update(sha256=project.meta['source_sha256'], imports=source_imports)
    dll_image.update(sha256=dll_project.meta['source_sha256'], module=deepcopy(module))
    create_id = report['process_create']['artifact']
    owner = project.db.execute('SELECT run FROM debug_artifacts WHERE id=?', (create_id,)).fetchone()
    if owner is None:
        raise ValueError('Missing process-create artifact')
    run = owner['run']; native = project.db.execute('SELECT * FROM debug_runs WHERE id=?', (run,)).fetchone()
    if native is None or native['version'] != 1 or native['state'] != 'closed' or not native['ended']:
        raise ValueError('Loader composition requires one closed original-source native run')
    if json.loads(native['metadata']) != runtime:
        raise ValueError('Reported runtime differs from its owning native run')
    documents, receipts = _journal_artifacts(project, run)
    def doc(ref, kind=None):
        return _reference(ref, documents, receipts, kind)
    def sequence(ref):
        doc(ref); return receipts[ref['artifact']]['sequence']
    def check_references(value, depth=0):
        if depth > 32:
            raise ValueError('Loader report nesting exceeds its budget')
        if isinstance(value, dict):
            if 'artifact' in value: doc(value)
            for child in value.values(): check_references(child, depth + 1)
        elif isinstance(value, list):
            if len(value) > 2048: raise ValueError('Loader report list budget exceeded')
            for child in value: check_references(child, depth + 1)
    check_references(report)
    created = doc(report['process_create'], 'loader-stop')
    if created.get('stop_reason', {}).get('kind') != 'process-create' or created.get('loader', {}).get('entry_reached') is not False:
        raise ValueError('Actual process-create stop before loader entry is required')
    # The stored journal, not a report's list ordering, is the chronology anchor.
    listed = recovery['sequence']; previous = -1; seen = set()
    if not isinstance(listed, list) or not listed:
        raise ValueError('Explicit artifact sequence is required')
    for index, ref in enumerate(listed):
        actual = sequence(ref)
        if ref.get('index') != index or ref['artifact'] in seen or actual <= previous:
            raise ValueError('Reported artifact chronology contradicts the native journal')
        seen.add(ref['artifact']); previous = actual
    entry = doc(recovery['entry'], 'loader-frame-snapshot')
    protected = {
        'exe-data': (_number(exe_image['globals']['address']), len(bytes.fromhex(exe_image['globals']['hex']))),
        'dll-data': (_number(dll_image['globals']['address']), len(bytes.fromhex(dll_image['globals']['hex']))),
        'exe-code': (_number(exe_image['code']['address']), len(bytes.fromhex(exe_image['code']['hex']))),
        'dll-code': (_number(dll_image['code']['address']), len(bytes.fromhex(dll_image['code']['hex']))),
        **{'iat-' + n: (_number(row['iat_address']), 8) for n, row in source_imports.items()}}
    def range_map(rows):
        if not isinstance(rows, list) or len(rows) > 32:
            raise ValueError('Bounded role-labelled memory ranges required')
        result, cells = {}, set()
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'role', 'address', 'length'}
                    or not isinstance(row['role'], str) or row['role'] in result
                    or type(row['length']) is not int or not 1 <= row['length'] <= 512):
                raise ValueError('Invalid protected/environment role range')
            start = _number(row['address']); span = set(range(start, start + row['length']))
            if start + row['length'] > 1 << 64 or cells & span:
                raise ValueError('Protected/environment memory ranges overlap or wrap')
            cells |= span; result[row['role']] = (start, row['length'])
        return result, cells
    if range_map(recovery['protected_ranges'])[0] != protected:
        raise ValueError('Protected code/global/IAT ranges differ from their complete source definitions')
    main_stack = _number(entry['registers']['general']['rsp'])
    teb = _number(entry['thread_info']['teb'])
    environment = {'teb-self': (teb + 0x30, 8), 'last-error': (teb + 0x68, 4),
                   'main-stack': (main_stack - 48, 56)}
    if range_map(recovery['environment_ranges'])[0] != environment or _number(recovery['main_entry_stack']) != main_stack:
        raise ValueError('Environment frame ranges differ from their observed thread/main frame')
    def source_bytes(snapshot, image, field):
        expected = bytes.fromhex(image[field]['hex']); address = _number(image[field]['address'])
        cells = _cells(snapshot['memory'])
        if any(cells.get(address + k) != byte for k, byte in enumerate(expected)):
            raise ValueError('Observed initial code/globals differ from their original source image')
    source_bytes(entry, exe_image, 'code'); source_bytes(entry, exe_image, 'globals')
    if not recovery['snapshots']:
        raise ValueError('Missing pre-TLS source initialization snapshot')
    before_tls = doc(recovery['snapshots'][0], 'loader-frame-snapshot')
    source_bytes(before_tls, dll_image, 'code'); source_bytes(before_tls, dll_image, 'globals')
    for milestone in report['milestones']:
        if {k: v for k, v in milestone.items() if k != 'artifact'} != doc(milestone, 'loaded-code-snapshot'):
            raise ValueError('Inline milestone differs from its immutable stored observation')
    binding = doc(recovery['bindings'], 'loader-entry-bindings')
    if (binding.get('run') != run or binding.get('source_sha256') != exe_image['sha256']
            or binding.get('dll_source_sha256') != dll_image['sha256']
            or _number(binding['entry_address']) != _number(exe_image['symbols']['smc_module_entry'])
            or _number(binding['runtime_image_base']) != exe_base or _number(binding['dll_runtime_base']) != dll_base
            or binding['entry_snapshot']['artifact'] != recovery['entry']['artifact']):
        raise ValueError('Application-entry binding source or frame identity differs')
    if len(binding['headers']) != 2:
        raise ValueError('Both original source headers must be observed')
    exe_modules = [m for m in binding['modules']['modules'] if _number(m['base']) == exe_base]
    if len(exe_modules) != 1 or exe_modules[0]['bits'] != 64 or exe_modules[0]['size'] != exe.optional_header.sizeof_image:
        raise ValueError('Application source has no unique native loaded-module identity')
    for header, raw, pe, base in zip(binding['headers'], (exe_raw, dll_raw), (exe, dll), (exe_base, dll_base), strict=True):
        if _number(header['address']) != base or bytes.fromhex(header['hex']) != raw[:pe.optional_header.sizeof_headers]:
            raise ValueError('Loaded PE headers differ from original source headers')
    if len(binding['imports']) != 4 or {x['name'] for x in binding['imports']} != set(source_imports):
        raise ValueError('Entry import bindings are incomplete or duplicated')
    for imported in binding['imports']:
        source = source_imports[imported['name']]
        if (imported['module'].casefold() != source['module'].casefold()
                or imported['iat_address'] != source['iat_address']
                or int.from_bytes(bytes.fromhex(imported['iat_hex']), 'little') != _number(imported['target'])):
            raise ValueError('Entry IAT bytes differ from source import identity')
        _resolve(imported['resolution'], binding['modules'], imported['module'], imported['name'])
        if imported['resolution']['target'] != imported['target']:
            raise ValueError('Entry IAT does not point to its actual loaded named export')
        if imported['name'] == 'dll_report' and imported['target'] != dll_image['symbols']['dll_report']:
            raise ValueError('Authored DLL report import points outside its source export')
    tls = doc(report['tls_directory'], 'loaded-image-structure')
    if binding['tls_directory']['artifact'] != report['tls_directory']['artifact']:
        raise ValueError('Entry binding references another TLS observation')
    dll_delta = dll_base - dll.imagebase
    if (tls['source_sha256'] != dll_image['sha256'] or _number(tls['address']) != dll_base + dll.data_directories[9].rva
            or _number(tls['source_tls_rva']) != dll.data_directories[9].rva
            or _number(tls['callbacks_address']) != dll.tls.addressof_callbacks + dll_delta
            or bytes.fromhex(tls['callbacks_hex']) != (_number(dll_image['symbols']['dll_tls_callback']).to_bytes(8, 'little') + bytes(8))
            or dll.imagebase + dll.optional_header.addressof_entrypoint + dll_delta != _number(dll_image['symbols']['dll_entry'])):
        raise ValueError('Genuine source TLS/DllMain entry identity differs')
    native_tls = bytes.fromhex(tls['hex'])
    source_tls = bytearray(dll.get_content_from_virtual_address(dll.imagebase + dll.data_directories[9].rva, 40))
    for k in range(0, 32, 8):
        value = int.from_bytes(source_tls[k:k + 8], 'little')
        if value: source_tls[k:k + 8] = (value + dll_delta).to_bytes(8, 'little')
    if native_tls != source_tls:
        raise ValueError('Loaded TLS directory differs from its relocated source declarations')
    # Verify every raw step's controller identity and source ownership. The
    # semantic checker separately proves these bytes and their state effects.
    for ref in report['callbacks']:
        callback = doc(ref, 'dll-callback')
        if (callback.get('status') != 'complete' or callback.get('run') != run
                or callback.get('controller_source_sha256') != exe_image['sha256']
                or callback.get('subject_source_sha256') != dll_image['sha256']):
            raise ValueError('Callback source or owning native run differs')
        if any(callback['subject_module'].get(k) != module.get(k) for k in ('base', 'name', 'size', 'generation', 'bits')):
            raise ValueError('Callback DLL generation or mapping differs')
        role = callback['source_role']
        if role not in ('tls-attach', 'dll-attach', 'report', 'tls-detach', 'dll-detach'):
            raise ValueError('Unknown DLL source callback role')
        if role != 'report' and (_number(callback['entry']['general']['rdx']) & 0xffffffff) != (1 if role.endswith('attach') else 0):
            raise ValueError('Callback reason differs from its source phase')
        target = 'dll_report' if role == 'report' else 'dll_tls_callback' if role.startswith('tls-') else 'dll_entry'
        if callback['entry']['rip'] != dll_image['symbols'][target]:
            raise ValueError('Callback entry differs from its actual source export')
        for step in callback['steps']:
            event = step['event']; validate_context(event['registers'], 64); validate_context(step['after'], 64)
            if (event['identity'].get('source_version') != 1 or event.get('project_address') is not None
                    or event['identity'].get('project_address') is not None
                    or event['observation'].get('instruction_completed') is not True
                    or not _number(dll_image['code']['address']) <= _number(event['address']) < _number(dll_image['code']['address']) + len(bytes.fromhex(dll_image['code']['hex']))):
                raise ValueError('Foreign callback instruction lacks its exact native source identity')
    # All explicit snapshots and new source segments are independently owned.
    for ref in recovery['snapshots']:
        snapshot = doc(ref, 'loader-frame-snapshot')
        if (snapshot.get('format') != 'fdisbull-loader-frame-snapshot-1' or snapshot.get('run') != run
                or snapshot.get('controller_source_sha256') != exe_image['sha256']
                or snapshot.get('subject_source_sha256') != dll_image['sha256']):
            raise ValueError('Loader snapshot belongs to another source or run')
        validate_context(snapshot['registers'], 64)
        ranges, cells = range_map(snapshot['ranges'])
        if ({k: ranges.get(k) for k in protected} != protected
                or any(k not in protected and environment.get(k) != value for k, value in ranges.items())
                or set(_cells(snapshot['memory'])) != cells
                or _number(snapshot['thread_info']['teb']) != teb
                or snapshot['thread_info']['thread'] != snapshot['registers']['thread']):
            raise ValueError('Snapshot does not cover its exact source and environment ranges')
        if snapshot['registers']['thread'] != entry['registers']['thread']:
            raise ValueError('Loader composition changes its selected primary thread')
        for expected_module in (module, exe_modules[0]):
            observed_modules = [m for m in snapshot['modules']['modules'] if _number(m['base']) == _number(expected_module['base'])]
            if len(observed_modules) != 1 or any(observed_modules[0].get(k) != expected_module.get(k) for k in ('name', 'base', 'size', 'generation', 'bits')):
                raise ValueError('Loader frame reuses an absent or changed source module generation')
    for ref in recovery['main_segments']:
        segment = doc(ref, 'authored-module-segment')
        if segment.get('status') != 'complete' or segment.get('run') != run or segment.get('source_sha256') != exe_image['sha256']:
            raise ValueError('Authored EXE segment is not complete and source-bound')
        for step in segment['steps']:
            event = step['event']; address = _number(event['address'])
            if (event['identity'].get('source_version') != 1 or event.get('project_address') != hex(address - exe_base + exe.imagebase)
                    or not _number(exe_image['code']['address']) <= address < _number(exe_image['code']['address']) + len(bytes.fromhex(exe_image['code']['hex']))
                    or event['observation'].get('instruction_completed') is not True):
                raise ValueError('Authored EXE step has an inconsistent source address identity')
    for ref in recovery['transitions']:
        transition = doc(ref, 'loader-frame-transition')
        if transition.get('run') != run or transition.get('operation') not in ('loader.run', 'ExitProcess/loader.run', 'loader.dispatch-capsule'):
            raise ValueError('Unknown opaque-loader transition provenance')
        if sequence(transition['before']) >= sequence(ref) or (transition['after'] is not None and
                not sequence(transition['before']) < sequence(transition['after']) < sequence(ref)):
            raise ValueError('Opaque-loader frame observations are chronologically inconsistent')
    # These are stored native run outcomes, rather than a caller-authored exit
    # assertion. A terminal transition and the public report must identify the
    # same one actual process-exit event after the last source callback.
    exit_sequence = _native_exit(project, run, report['terminal'])
    terminal_transitions = [ref for ref in recovery['transitions'] if doc(ref)['after'] is None]
    if (len(terminal_transitions) != 1
            or doc(terminal_transitions[0])['outcome'] != report['terminal']
            or not sequence(doc(terminal_transitions[0])['before']) < exit_sequence < sequence(terminal_transitions[0])):
        raise ValueError('Terminal frame transition does not bracket the native exit event')
    for ref in report['apis']:
        api = doc(ref, 'import-call'); imported = api['import']
        if (api.get('status') != 'complete' or api['identity']['run'] != run
                or api['identity']['source_version'] != 1
                or api['identity']['source_sha256'] != exe_image['sha256']
                or api['identity']['version_sha256'] != project.version(1)['sha256']
                or imported['name'] not in ('SetLastError', 'GetLastError')
                or imported['runtime_iat_address'] != source_imports[imported['name']]['iat_address']
                or imported['module'].casefold() != source_imports[imported['name']]['module'].casefold()):
            raise ValueError('Verified API observation has a different source/run/import identity')
        _resolve(api['resolution'], api['modules_before'], imported['module'], imported['name'])
        call = doc(api['trace'], 'trace')
        if (call.get('complete') is not True or call.get('run') != run or call.get('version') != 1
                or len(call['events']) != 1 or call['events'][0]['registers'] != api['contexts']['before']
                or imported['target'] != api['resolution']['target']):
            raise ValueError('API implementation is not tied to its actual source CALL trace')
    # Legacy milestone/callback/API lists remain linked to actual journal order.
    callbacks, milestones = report['callbacks'], report['milestones']
    if (len(callbacks) != 5 or len(milestones) != 7 or len(report['apis']) != 8
            or [m['phase'] for m in milestones] != ['before-tls', 'tls-attached', 'dll-attached', 'exe-entry', 'reported', 'detached', 'detached']):
        raise ValueError('The complete observed source callback schedule is required')
    mark = lambda n: {'artifact': milestones[n]['artifact']}
    chronology = [report['process_create'], report['tls_directory'], mark(0),
        callbacks[0], mark(1), callbacks[1], mark(2), mark(3), callbacks[2], mark(4)]
    chronology += report['apis'] + [report['exit_call']]
    for callback, milestone in zip(report['callbacks'][3:], report['milestones'][5:], strict=True):
        chronology += [callback, {'artifact': milestone['artifact']}]
    order = [sequence(ref) for ref in chronology]
    if order != sorted(set(order)) or order[-1] >= exit_sequence:
        raise ValueError('Native callback/API/milestone schedule is not chronological')
    loader_documents = [documents[k] for k in sorted(receipts, key=lambda k: receipts[k]['sequence']) if receipts[k]['kind'] == 'loader-events']
    if any(row.get('lost_before') is not False for row in loader_documents) or [e for row in loader_documents for e in row['events']] != report['loader_events']:
        raise ValueError('Reported loader history differs from its complete native event artifacts')
    loader_capsules = _bind_loader_capsules(report, run=run, exe_image=exe_image, dll_image=dll_image,
        documents=documents, receipts=receipts, protected=protected, terminal_sequence=exit_sequence) if require_loader_capsules else []
    return {'format': 'fdisbull-runtime-loader-evidence-1', 'run': run, 'metadata': deepcopy(runtime),
        'exe': exe_image, 'dll': dll_image, 'documents': documents, 'receipts': receipts, 'report': report,
        'loader_capsules': loader_capsules,
        'subject_source_bytes': dll_raw if require_loader_capsules else None,
        'scope': 'Hash-bound native/source observations only; universal loader frame conditions require an explicit semantic contract'}
