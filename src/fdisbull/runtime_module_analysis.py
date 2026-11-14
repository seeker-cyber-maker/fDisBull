"""Bind module-entry, code-epoch and imported-call observations to recovery."""
from copy import deepcopy
import base64
import hashlib
import json

from .runtime_patch_analysis import _artifact, _bound_trace


def _resolution(resolution, modules, name):
    """Recompute the named export from its immutable native memory-read ledger."""
    from .wine_import_calls import resolve_loaded_export
    rows, offset = resolution['reads'], 0
    def read(address, length):
        nonlocal offset
        if offset >= len(rows):
            raise ValueError('Incomplete recorded import resolution')
        row = rows[offset]; offset += 1
        raw = bytes.fromhex(row['hex'])
        if (int(row['address'], 16) != address or len(raw) != length
                or hashlib.sha256(raw).hexdigest() != row['sha256']):
            raise ValueError('Recorded import-resolution read differs')
        return raw
    result = resolve_loaded_export(modules, 'KERNEL32.dll', name, read)
    if offset != len(rows) or result != resolution:
        raise ValueError('Recorded named-export resolution differs')


def _pe(project, version):
    import lief
    row = project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?', (version,)).fetchone()
    if row is None or row[0] is None:
        raise ValueError('Module initialization requires the preserved original PE bytes')
    raw = bytes(row[0])
    if hashlib.sha256(raw).hexdigest() != project.meta['source_sha256']:
        raise ValueError('Original module source identity differs')
    pe = lief.PE.parse(list(raw))
    if pe is None or pe.has_tls or pe.data_directories[14].rva:
        raise ValueError('This module profile requires a native PE without TLS/CLR')
    return pe


def _validate_initialization(project, source, document, identity):
    pe = _pe(project, source)
    delta = int(identity['runtime_image_base'], 16) - int(identity['static_image_base'], 16)
    if (document['source_sha256'] != project.meta['source_sha256']
            or int(document['image_base'], 16) != pe.optional_header.imagebase + delta
            or int(document['entry_address'], 16) != project.meta['entry'] + delta
            or document['stage'] != 'pe-entry-after-loader'
            or document['tls_callbacks'] != [] or document['clr'] is not False):
        raise ValueError('Initialization does not identify this original PE entry')
    expected = {e.name: pe.optional_header.imagebase + e.iat_address + delta
                for imp in pe.imports for e in imp.entries}
    bindings = {row['name']: int(row['iat_address'], 16) for row in document['imports']}
    if expected != bindings:
        raise ValueError('Initialization does not cover the original import table exactly')
    iat = {address + k for address in bindings.values() for k in range(8)}
    cells = {}
    for row in document['memory']:
        address = int(row['address'], 16)
        for offset, byte in enumerate(bytes.fromhex(row['hex'])):
            a = address + offset
            if a in cells:
                raise ValueError('Overlapping module initialization observations')
            cells[a] = byte
            if a in iat:
                continue
            region = next((r for r in project.regions(source)
                           if not r.executable and r.writable and r.start <= a - delta < r.start + len(r.data)), None)
            if region is None or region.data[a - delta - region.start] != byte:
                raise ValueError('Observed loader data differs from the original mapped PE data')
    if not iat <= cells.keys():
        raise ValueError('Missing initialized IAT bytes')


def observe_module_entry(session, *, data_ranges, name='module-entry.json'):
    """Capture the actual post-loader entry image, not a loader execution proof."""
    from .external_files import _file_name
    from .wine_import_calls import _ranges, resolve_loaded_export
    _file_name(name)
    ranges = _ranges(data_ranges, 128)
    if session.status().get('state') != 'stopped':
        raise ValueError('Module entry capture requires a stopped PE64 thread')
    registers = session.call('registers')
    if int(registers['rip'], 16) != session.project.meta['entry'] + session.delta:
        raise ValueError('Module initialization must be observed before the first entry instruction')
    pe = _pe(session.project, session.version['id'])
    def read(address, length):
        raw = base64.b64decode(session.call('read', {'address': address, 'length': length})['data_base64'], validate=True)
        if len(raw) != length:
            raise ValueError('Incomplete module-entry memory observation')
        return raw
    modules = session.call('modules')
    memory = [{'address': row['address'], 'hex': read(int(row['address'], 16), row['length']).hex()} for row in ranges]
    imports, resolutions = [], []
    for imported in pe.imports:
        for entry in imported.entries:
            if imported.name.casefold() != 'kernel32.dll' or entry.name not in ('SetLastError', 'GetLastError', 'ExitProcess'):
                raise ValueError('Unmodeled import in module entry')
            address = pe.optional_header.imagebase + entry.iat_address + session.delta
            raw = read(address, 8)
            resolution = resolve_loaded_export(modules, imported.name, entry.name, read)
            if int.from_bytes(raw, 'little') != int(resolution['target'], 16):
                raise ValueError('Initialized IAT target differs from its actual loaded export')
            imports.append({'name': entry.name, 'iat_address': hex(address), 'target': resolution['target']})
            resolutions.append({'name': entry.name, 'resolution': resolution})
            memory.append({'address': hex(address), 'hex': raw.hex()})
    initialization = {'stage': 'pe-entry-after-loader', 'source_sha256': session.project.meta['source_sha256'],
        'entry_address': registers['rip'], 'image_base': hex(session.runtime_base),
        'memory': memory, 'tls_callbacks': [], 'clr': False, 'imports': imports}
    _validate_initialization(session.project, session.version['id'], initialization, session.metadata)
    return session._artifact(name, 'module-initialization', json.dumps({
        'format': 'fdisbull-pe-module-entry-1', 'identity': {
            'run': session.run_id, 'source_version': session.version['id'],
            'source_sha256': session.project.meta['source_sha256'],
            'version_sha256': session.version['sha256'], 'mapping': session.metadata},
        'initialization': initialization, 'registers': registers, 'resolutions': resolutions,
        'modules_before': modules,
        'scope': 'Observed PE data and resolved IAT before authored entry; DLL/loader internals unproved'}, indent=2).encode(), {})


def _module_path(project, initial_version, path):
    if not isinstance(path, dict) or set(path) != {'segments', 'memory', 'code_versions', 'external_calls', 'initialization'}:
        raise ValueError('Stored module path requires segments, RAM, code versions, API artifacts and initialization')
    if not isinstance(path['segments'], list) or not 1 <= len(path['segments']) <= 32:
        raise ValueError('A module path requires 1..32 stored trace segments')
    events, references, boundaries = [], [], {}
    trace = None
    for segment in path['segments']:
        if not isinstance(segment, dict) or set(segment) != {'trace', 'version'}:
            raise ValueError('Each module segment requires an exact trace and captured version')
        part, receipt = _bound_trace(project, segment['version'], segment['trace'], allow_single=True)
        if receipt['view'] != 'ram' or any(e.get('execution_bytes', e.get('bytes')) != e.get('ram_bytes', e.get('bytes')) for e in part['events']):
            raise ValueError('Module recovery excludes execution overlays')
        if trace is None:
            trace = deepcopy(part)
        elif any(receipt[k] != references[0][k] for k in ('run', 'source_version', 'capture_address', 'capture_size')):
            raise ValueError('Module segments require one source, run and full code span')
        boundaries[len(events)] = receipt['version']
        events.extend(deepcopy(part['events']))
        references.append(receipt)
        if len(events) > 256:
            raise ValueError('Module path exceeds its bounded instruction budget')
    if references[0]['version'] != initial_version:
        raise ValueError('Module path requires the selected initial captured version')
    owner = references[0]
    init_row, entry = _artifact(project, path['initialization'], 'module-initialization')
    identity = entry['identity']
    if (entry.get('format') != 'fdisbull-pe-module-entry-1'
            or init_row['run'] != owner['run'] or identity['run'] != owner['run']
            or identity['source_version'] != owner['source_version']
            or identity['source_sha256'] != owner['source_sha256']
            or identity['version_sha256'] != owner['source_version_sha256']
            or entry['registers'] != events[0]['registers']):
        raise ValueError('Module-entry artifact and first native instruction identity differ')
    _validate_initialization(project, owner['source_version'], entry['initialization'], identity['mapping'])
    if (len(entry['resolutions']) != len(entry['initialization']['imports'])
            or {r['name'] for r in entry['resolutions']} != {r['name'] for r in entry['initialization']['imports']}):
        raise ValueError('Module entry lacks complete named-export resolution evidence')
    for row in entry['resolutions']:
        _resolution(row['resolution'], entry['modules_before'], row['name'])
        if row['resolution']['target'] != next(x['target'] for x in entry['initialization']['imports'] if x['name'] == row['name']):
            raise ValueError('Initialized import differs from its resolved named export')
    if not isinstance(path['code_versions'], list) or not 1 <= len(path['code_versions']) <= 33:
        raise ValueError('Module path requires its initial and every written code version')
    versions, previous = [], -1
    for row in path['code_versions']:
        if (set(row) != {'after_event', 'version'} or type(row['after_event']) is not int
                or not previous < row['after_event'] < len(events)
                or boundaries.get(row['after_event']) != row['version']):
            raise ValueError('Module code versions must name ordered native segment boundaries')
        previous = row['after_event']
        record = project._runtime_record(row['version'])
        _, capture = _artifact(project, record['artifact'], 'code-snapshot')
        versions.append({'after_event': previous, 'image': [{'address': capture['runtime_address'], 'hex': capture['hex']}]})
    if versions[0]['after_event'] != 0:
        raise ValueError('Missing module entry code image')
    for start, version in boundaries.items():
        active = [row['version'] for row in path['code_versions'] if row['after_event'] <= start][-1]
        if active != version:
            raise ValueError('A native module segment uses a stale code epoch')
    calls, api_receipts, terminal = [], [], None
    if not isinstance(path['external_calls'], list) or not 1 <= len(path['external_calls']) <= 32:
        raise ValueError('Module paths require bounded stored imported-call observations')
    prior = -1
    for row in path['external_calls']:
        if set(row) != {'event_index', 'artifact'} or type(row['event_index']) is not int or not prior < row['event_index'] < len(events):
            raise ValueError('External call records require strictly ordered native event indices')
        index = prior = row['event_index']
        stored, api = _artifact(project, row['artifact'], 'import-call')
        if (api.get('format') != 'fdisbull-wine-import-call-1' or api.get('status') != 'complete'
                or stored['run'] != owner['run'] or api['identity']['run'] != owner['run']
                or api['identity']['source_version'] != owner['source_version']
                or api['identity']['source_sha256'] != owner['source_sha256']
                or api['identity']['version_sha256'] != owner['source_version_sha256']
                or api['contexts']['before'] != events[index]['registers']
                or api['trace']['artifact'] not in [s['trace'] for s in path['segments']]):
            raise ValueError('Imported call artifact differs from its owning native trace/run')
        _, native_call = _artifact(project, api['trace']['artifact'], 'trace')
        if native_call['events'] != [events[index]] or api['import']['target'] != api['resolution']['target']:
            raise ValueError('Imported call instruction or observed export binding differs')
        _resolution(api['resolution'], api['modules_before'], api['import']['name'])
        observed = api['entry_instruction']
        read = observed['read']; raw = bytes.fromhex(read['hex'])
        from iced_x86 import Decoder
        instruction = Decoder(64, raw, ip=int(api['import']['target'], 16)).decode()
        fingerprint = api['resolution']['reads'][-1]
        if (hashlib.sha256(raw).hexdigest() != read['sha256'] or len(raw) != 15
                or read['address'] != api['import']['target'] or observed['address'] != read['address']
                or observed['project_address'] is not None or observed['identity']['project_address'] is not None
                or observed['identity']['runtime_address'] != read['address']
                or observed['identity']['source_version'] != owner['source_version']
                or observed['registers'] != api['contexts']['entry']
                or observed['observation']['instruction_completed'] is not False
                or instruction.is_invalid or observed['bytes'] != raw[:instruction.len].hex()
                or observed['execution_bytes'] != observed['bytes']
                or fingerprint['address'] != read['address'] or not bytes.fromhex(fingerprint['hex']).startswith(raw)):
            raise ValueError('Imported API entry instruction differs from its native memory observation')
        terminal_call = api['import']['name'] == 'ExitProcess'
        if terminal_call:
            if index != len(events) - 1 or api['outcome']['outcome'] != 'exited' or api['outcome']['session']['state'] != 'exited':
                raise ValueError('Module must end with actual ExitProcess evidence')
            events.append(deepcopy(api['entry_instruction']))
            terminal = {'name': 'ExitProcess', 'exit_code': hex(api['terminal']['exit_code']), 'process_exited': True}
        calls.append({'event_index': index, 'name': api['import']['name'],
            'iat_address': api['import']['runtime_iat_address'], 'target': api['import']['target'],
            'entry_registers': api['contexts']['entry'],
            'return_registers': None if terminal_call else api['contexts']['return'],
            'memory': {'entry': api['memory']['entry'], 'exit': None if terminal_call else api['memory']['return']},
            'code': {'entry': api['code']['entry'], 'exit': None if terminal_call else api['code']['return']}})
        api_receipts.append({'artifact': row['artifact'], 'sha256': stored['sha256']})
    if terminal is None:
        raise ValueError('Missing observed process termination')
    trace.update(events=events, requested_count=len(events), composition='Native module segments plus stored imported entry boundary')
    return {'trace': trace, 'memory': path['memory'], 'code': {'entry': versions[0]['image'],
        'exit': versions[-1]['image'], 'versions': versions}, 'external_calls': calls, 'terminal': terminal}, {
        'segments': references, 'initialization': path['initialization'], 'initialization_sha256': init_row['sha256'],
        'external_calls': api_receipts, 'execution_proven': False}, entry['initialization']


def compare_runtime_modules(project, baseline_version, layer_version, baseline_paths, layer_paths, *, contract, timeout_ms=10000):
    from .pe_module_recovery import compare_pe_modules
    documents, receipts, initializations = [], [], []
    for version, paths in ((baseline_version, baseline_paths), (layer_version, layer_paths)):
        if not isinstance(paths, list) or not 1 <= len(paths) <= 8:
            raise ValueError('Module comparison requires 1..8 observed paths per family')
        bound = [_module_path(project, version, path) for path in paths]
        documents.append([x[0] for x in bound]); receipts.append([x[1] for x in bound]); initializations.extend(x[2] for x in bound)
    if any(row != initializations[0] for row in initializations):
        raise ValueError('Compared module runs require identical observed loader data and import bindings')
    proof = compare_pe_modules(*documents, contract=contract, initialization=initializations[0], timeout_ms=timeout_ms)
    return {'format': 'fdisbull-runtime-module-analysis-1', 'baseline': receipts[0], 'layer': receipts[1],
            'module': proof, 'semantic_equivalence': None,
            'scope': 'Source-entry to observed process exit under declared imported-call contracts; DLL/loader/OS internals unproved'}
