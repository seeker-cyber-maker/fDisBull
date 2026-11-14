"""Immutable, project-owned searches over qualified execution observations.

This adapter never executes a guest or infers a function. Search candidates are
reconstructed from their retained trace lineage before use. Artifact digests
detect changed records; they are not authentication for caller-supplied JSON.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from . import execution_events as kernel


MAX_BYTES = 16 * 1024 * 1024
MAX_HISTORY = 128
MAX_CAPTURE_RECEIPTS = 4096
FORMAT = 'fdisbull-event-search-artifact-1'
_BACKENDS = frozenset(('dosbox', 'dosbox-qemu', 'qemu-dos', 'wine-qemu', 'ida-wine-qemu'))
_MUTABLE_MAPPING = frozenset(('execution_origin', 'checkpoint_intervention',
    'delta_experiment', 'timeline_experiment', 'qemu_pid', 'restored_from',
    'capabilities', 'window_requested', 'dot_mode'))
_STATE_FIELDS = frozenset(('format', 'registers', 'native_sha256', 'native_size',
    'storage', 'capture', 'target_paused', 'host_files_restored', 'derivation'))
_ENVELOPE_KEYS = frozenset(('format', 'owner', 'generation', 'parent', 'trace',
                            'regions', 'operation', 'state'))
_IDENTITY_KEYS = frozenset(('source_sha256', 'version_sha256', 'version', 'backend'))


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer in {minimum}..{maximum}')
    return value


def _identifier(value):
    if (type(value) is not str or not 1 <= len(value) <= 128
            or any(ord(character) < 32 for character in value)):
        raise ValueError('An owned artifact identifier is required')
    return value


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Invalid stored SHA-256 identity')
    return value


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Duplicate JSON field in retained event evidence')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON value in retained event evidence: ' + value)


def _document(data):
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError('Invalid JSON in retained event evidence') from error
    if type(value) is not dict:
        raise ValueError('Retained event evidence must be a JSON object')
    return value


def _artifact(project, identifier, kind):
    """Check the size before materializing a possibly external artifact blob."""
    _identifier(identifier)
    row = project.db.execute('''SELECT a.id,a.run,a.name,a.kind,a.sha256,a.metadata,
        fdb_length(a.data) AS size,r.version,r.metadata AS run_metadata,
        v.sha256 AS version_sha256 FROM debug_artifacts a
        JOIN debug_runs r ON r.id=a.run JOIN versions v ON v.id=r.version
        WHERE a.id=?''', (identifier,)).fetchone()
    if row is None or row['kind'] != kind:
        raise ValueError('Unknown owned ' + kind + ' artifact')
    if type(row['size']) is not int or not 0 < row['size'] <= MAX_BYTES:
        raise ValueError('Retained event artifact exceeds its 16 MiB budget')
    _digest(row['sha256'])
    data = bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                    (identifier,)).fetchone()[0])
    if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
        raise ValueError('Retained event artifact failed its size or hash check')
    return dict(row), _document(data)


def _backend(project, metadata):
    value = metadata.get('backend')
    if value is None and project.meta['format'] in ('MZ', 'COM', 'SYS'):
        value = 'dosbox'
    if type(value) is not str or value not in _BACKENDS:
        raise ValueError('Event searches require a qualified DOS or PE trace backend')
    return value


def _mapping_identity(project, metadata):
    if type(metadata) is not dict:
        raise ValueError('Trace requires retained launch mapping metadata')
    backend = _backend(project, metadata)
    required = ('static_load_segment', 'runtime_load_segment') if backend.startswith('dosbox') else (
        'static_image_base', 'runtime_image_base')
    if any(key not in metadata for key in required):
        raise ValueError('Trace requires explicit static and runtime image mapping bases')
    result = {key: value for key, value in metadata.items()
            if key not in _MUTABLE_MAPPING and key != 'backend'} | {
                'backend': backend}
    maximum = 0xffff if backend.startswith('dosbox') else (1 << 64) - 1
    for key in required:
        value = result[key]
        if type(value) is str and re.fullmatch(r'0[xX][0-9a-fA-F]{1,17}', value):
            value = int(value, 16)
        result[key] = _integer(value, key + ' mapping base', 0, maximum)
    if 'runtime_inputs' in result:
        inputs = result['runtime_inputs']
        if type(inputs) is not dict or len(inputs) > 32:
            raise ValueError('Invalid retained backend input identities')
        normalized = {}
        for name, item in inputs.items():
            if type(item) is not dict or 'sha256' not in item:
                raise ValueError('Retained backend input lacks a content identity')
            normalized[name] = dict(sha256=_digest(item['sha256']))
        result['runtime_inputs'] = normalized
    return result


def _capture_sequence(project, row):
    """Bind historical mapping to its bounded, decoded creation receipt.

    Artifact events can be external objects. SQLite sees their storage envelope,
    not the artifact ID in the decoded document, so JSON extraction in SQL cannot
    identify this receipt. Validate count and total size before reading them.
    """
    sizes = project.db.execute('''SELECT sequence,fdb_length(evidence) AS size
        FROM debug_events WHERE run=? AND operation='artifact'
        ORDER BY sequence LIMIT ?''', (row['run'], MAX_CAPTURE_RECEIPTS + 1)).fetchall()
    if (len(sizes) > MAX_CAPTURE_RECEIPTS
            or any(type(item['size']) is not int or not 0 < item['size'] <= MAX_BYTES for item in sizes)
            or sum(item['size'] for item in sizes) > MAX_BYTES):
        raise ValueError('Historical trace creation receipts exceed the count or size budget')
    matches = []
    for item in project.db.execute('''SELECT sequence,evidence FROM debug_events
            WHERE run=? AND operation='artifact' ORDER BY sequence LIMIT ?''',
            (row['run'], MAX_CAPTURE_RECEIPTS)):
        receipt = _document(item['evidence'])
        if receipt.get('artifact') == row['id']:
            matches.append((item['sequence'], receipt))
            if len(matches) > 1:
                break
    if len(matches) != 1:
        raise ValueError('Historical trace requires its unique artifact creation receipt')
    sequence, receipt = matches[0]
    expected = dict(artifact=row['id'], run=row['run'], version=row['version'],
                    kind=row['kind'], sha256=row['sha256'], size=row['size'])
    if _json({key: receipt.get(key) for key in expected}) != _json(expected):
        raise ValueError('Historical trace differs from its artifact creation receipt')
    return sequence


def _historical_pe_mapping(project, row, captured, current, metadata):
    """An ordered successful restore can explain a changed PE process mapping.

    Offline trace comparison needs only the retained state manifest and success
    receipt; it never loads a native checkpoint or requires its machine payload.
    Every event is still checked against the immutable captured mapping below.
    """
    if current['backend'] not in ('wine-qemu', 'ida-wine-qemu'):
        return False
    changed_by_restore = {'runtime_image_base', 'target_pid'}
    if (_json({key: value for key, value in captured.items() if key not in changed_by_restore})
            != _json({key: value for key, value in current.items() if key not in changed_by_restore})):
        return False
    restored = metadata.get('restored_from')
    if type(restored) is not str or not restored:
        return False
    sequence = _capture_sequence(project, row)
    latest = project.db.execute('''SELECT sequence,fdb_length(evidence) AS size FROM debug_events
        WHERE run=? AND operation='load-state' ORDER BY sequence DESC LIMIT 1''', (row['run'],)).fetchone()
    if latest is None or latest['sequence'] <= sequence:
        return False
    if type(latest['size']) is not int or not 0 < latest['size'] <= MAX_BYTES:
        raise ValueError('Historical restore receipt exceeds its size budget')
    receipt = _document(project.db.execute('SELECT evidence FROM debug_events WHERE sequence=?',
                                          (latest['sequence'],)).fetchone()[0])
    if (receipt.get('artifact') != restored or receipt.get('state') != 'stopped'
            or receipt.get('error') is not None or receipt.get('ok') is False):
        return False
    state_row, state = _artifact(project, restored, 'state')
    if (state_row['version'] != row['version'] or receipt.get('sha256') != state_row['sha256']
            or state.get('format') != 'fdisbull-qemu-native-1'
            or type(state.get('metadata')) is not dict):
        return False
    state_mapping = {key: value for key, value in state['metadata'].items() if key not in _STATE_FIELDS}
    return _json(_mapping_identity(project, state_mapping)) == _json(current)


def _native_step_policy(policy):
    """Validate the retained meanings of an observed QEMU stepping mask."""
    if (type(policy) is not dict or policy.get('format') != 'fdisbull-qemu-step-policy-1'
            or policy.get('status') != 'observed' or policy.get('changed') is not False):
        raise ValueError('Native DOS trace lacks its observed read-only step policy')
    bits, mask = policy.get('bits'), policy.get('mask')
    if type(bits) is not dict or not 3 <= len(bits) <= 8:
        raise ValueError('Native DOS trace step-control bits are malformed')
    _integer(mask, 'native step-control mask', 0, 0xffffffff)
    occupied = 0
    for name, value in bits.items():
        if type(name) is not str or re.fullmatch('[A-Z][A-Z0-9_]{0,31}', name) is None:
            raise ValueError('Native DOS trace step-control name is malformed')
        _integer(value, 'native step-control bit', 1, 0xffffffff)
        if value & (value - 1) or occupied & value:
            raise ValueError('Native DOS trace step-control bits overlap')
        occupied |= value
    if not {'ENABLE', 'NOIRQ', 'NOTIMER'} <= bits.keys():
        raise ValueError('Native DOS trace step-control meanings are incomplete')
    known = bits['ENABLE'] | bits['NOIRQ'] | bits['NOTIMER']
    if (mask & ~known or policy.get('unknown_mask') != 0
            or policy.get('enabled') is not True or not mask & bits['ENABLE']):
        raise ValueError('Native DOS trace requires a known enabled step-control mask')
    for name, field in (('NOIRQ', 'interrupts_masked'), ('NOTIMER', 'timers_masked')):
        if type(policy.get(field)) is not bool or policy[field] != bool(mask & bits[name]):
            raise ValueError('Native DOS trace step-control observation contradicts its mask')


def _native_binding(project, row, document, metadata):
    """Bind immutable capture identity to the original, ordered entry receipt.

    The live run can have exited, become resident, or closed since capture.
    Its immutable initial entry and load must still match, while later epochs,
    live ranges, status and termination metadata are expected to change.
    """
    from .qemu_trace_identity import CAPTURE_FORMAT, SOURCE_SCOPE, load_trace_binding

    captured = load_trace_binding(project, row['version'], document['mapping'])
    captured_process = document['mapping']['process']
    if (captured_process.get('state') != 'active' or captured_process.get('machine_closed')
            or captured_process['source_mapping'].get('live') is not True
            or captured_process['source_mapping'].get('status') != 'initial-load-verified'):
        raise ValueError('Native DOS trace must capture an active verified initial process')
    current = load_trace_binding(project, row['version'], metadata)
    if _json(captured['identity']) != _json(current['identity']):
        raise ValueError('Native DOS trace differs from the immutable run launch identity')
    entries = project.db.execute('''SELECT sequence,fdb_length(evidence) AS size
        FROM debug_events WHERE run=? AND operation='dos-process-entry'
        ORDER BY sequence LIMIT 2''', (row['run'],)).fetchall()
    if len(entries) != 1:
        raise ValueError('Native DOS trace requires its unique original process-entry receipt')
    entry = entries[0]
    if type(entry['size']) is not int or not 0 < entry['size'] <= MAX_BYTES:
        raise ValueError('Native DOS process-entry receipt exceeds its size budget')
    if entry['sequence'] >= _capture_sequence(project, row):
        raise ValueError('Native DOS process-entry receipt must precede trace capture')
    receipt = _document(project.db.execute('SELECT evidence FROM debug_events WHERE sequence=?',
                                          (entry['sequence'],)).fetchone()[0])
    process = receipt.get('process')
    if (type(process) is not dict or process.get('state') != 'active'
            or type(process.get('source_mapping')) is not dict
            or process['source_mapping'].get('status') != 'initial-load-verified'
            or process['source_mapping'].get('live') is not True):
        raise ValueError('Native DOS process-entry receipt is not a verified active initial load')
    original_metadata = dict(metadata, process=process)
    original = load_trace_binding(project, row['version'], original_metadata)
    if _json(original['identity']) != _json(captured['identity']):
        raise ValueError('Native DOS trace mapping differs from its original process-entry receipt')
    epoch = original['capture_epoch']
    if (epoch != row['run'] + ':process:1' or captured['capture_epoch'] != epoch
            or document.get('capture_epoch') != epoch):
        raise ValueError('Native DOS trace capture epoch differs from its original process entry')
    capture = document.get('native_process_capture')
    if (type(capture) is not dict or capture.get('format') != CAPTURE_FORMAT
            or capture.get('source_scope') != SOURCE_SCOPE
            or capture.get('capture_epoch', epoch) != epoch):
        raise ValueError('Native DOS trace requires a source-bound process capture')
    _native_step_policy(capture.get('step_policy'))
    return captured


def _native_events(document, compiled, binding):
    """Reconstruct every claimed source instruction; never trust a flag/hash."""
    from .qemu_trace_identity import qualify_instruction

    for index, (raw, event) in enumerate(zip(document['events'], compiled['events'])):
        identity = raw.get('identity')
        if (type(identity) is not dict or identity.get('source_version') != compiled['identity']['version']
                or identity.get('runtime_address') is None or type(raw.get('registers')) is not dict
                or type(raw.get('task_id')) is not int
                or raw['task_id'] != binding['identity']['psp_segment']
                or raw.get('mapping_id') != binding['capture_epoch']):
            raise ValueError('Native DOS observation differs from its captured process/epoch identity')
        completed = event['observation'].get('instruction_completed')
        if completed is not None and completed is not False:
            raise ValueError('Native DOS step evidence cannot certify instruction retirement')
        claimed = raw.get('project_address')
        digest = identity.get('source_instruction_sha256')
        if claimed is None:
            if identity.get('project_address') is not None or digest is not None or identity.get('context') is not None:
                raise ValueError('Unqualified native DOS observation claims a source instruction')
            if event['site'] is not None or compiled['window']['closed']:
                raise ValueError('A native source boundary cannot close a source search window')
            if index != len(compiled['events']) - 1:
                raise ValueError('Native DOS capture continued beyond an unqualified source boundary')
            continue
        if (raw.get('cpu_mode') != 'real' or raw.get('code_bits') != 16
                or event['observation'].get('registers_stage') != 'before-instruction'
                or event['observation'].get('flags_materialized') is not True):
            raise ValueError('Native DOS source claim requires stopped 16-bit real-mode registers')
        context = event['execution_context']['address_context']
        if (type(context) is not dict or context.get('cpu_mode') != 'real'
                or context.get('code_bits') != 16 or context.get('paging_enabled') is not False
                or type(context.get('cr0')) is not int or context['cr0'] & 0x80000001):
            raise ValueError('Native DOS source claim requires observed unpaged real-mode control state')
        cs = context.get('cs')
        if (type(cs) is not dict or cs.get('selector') != event['pc']['segment']
                or cs.get('base') != event['pc']['segment'] * 16
                or type(cs.get('attributes')) is not int or cs['attributes'] & 0x600000
                or type(cs.get('limit')) is not int
                or cs['limit'] < event['pc']['offset'] + (event['size'] or 1) - 1):
            raise ValueError('Native DOS source claim differs from its observed CS descriptor cache')
        code = bytes.fromhex(raw.get('execution_bytes', raw.get('bytes', '')))
        qualification = qualify_instruction(binding, event['pc']['linear'], code,
            segment=event['pc']['segment'], offset=event['pc']['offset'])
        if not qualification['qualified']:
            raise ValueError('Native DOS source instruction failed byte qualification: ' + qualification['reason'])
        if (event['pc']['project'] != qualification['project_address']
                or identity.get('context') != qualification['context']
                or digest != qualification['source_instruction_sha256']
                or event['site'] is None
                or event['site']['instruction_sha256'] != qualification['source_instruction_sha256']):
            raise ValueError('Native DOS claimed source instruction differs from original project bytes')
        if 'bytes' in raw and 'execution_bytes' in raw and raw['bytes'] != raw['execution_bytes']:
            raise ValueError('Native DOS observed instruction byte fields disagree')


def _operation_receipt(project, run, operation, artifact, expected):
    """Find one bounded operation receipt, decoding external evidence safely."""
    rows = project.db.execute("""SELECT sequence,fdb_length(evidence) AS size
        FROM debug_events WHERE run=? AND operation=? ORDER BY sequence LIMIT ?""",
        (run, operation, MAX_CAPTURE_RECEIPTS + 1)).fetchall()
    if (len(rows) > MAX_CAPTURE_RECEIPTS or
            any(type(r['size']) is not int or not 0 < r['size'] <= MAX_BYTES for r in rows)
            or sum(r['size'] for r in rows) > MAX_BYTES):
        raise ValueError('LE operation receipts exceed their bounded evidence budget')
    matches = []
    for row in rows:
        value = _document(project.db.execute('SELECT evidence FROM debug_events WHERE sequence=?',
                                            (row['sequence'],)).fetchone()[0])
        if value.get('artifact') == artifact:
            if any(value.get(key) != item for key, item in expected.items()):
                raise ValueError('LE operation receipt differs from its artifact identity')
            matches.append(row['sequence'])
    if len(matches) != 1:
        raise ValueError('LE capture requires its unique ' + operation + ' receipt')
    return matches[0]


def _le_launch_binding(project, row, document, metadata):
    """Reconstruct the immutable launch while permitting a fresh restore epoch."""
    from .qemu_trace_identity import load_trace_binding
    extra = _MUTABLE_MAPPING | {'protected_source_binding', 'protected_source_binding_artifact',
             'protected_source_binding_material', 'checkpoint_restore'}
    captured_metadata = {key: value for key, value in document['mapping'].items() if key not in extra}
    current_metadata = {key: value for key, value in metadata.items() if key not in extra}
    captured = load_trace_binding(project, row['version'], captured_metadata)
    current = load_trace_binding(project, row['version'], current_metadata)
    process = captured_metadata['process']
    if process.get('state') != 'active' or process.get('machine_closed'):
        raise ValueError('LE trace must capture an active owned DOS process')
    entries = project.db.execute("""SELECT sequence,fdb_length(evidence) AS size
        FROM debug_events WHERE run=? AND operation='dos-process-entry'
        ORDER BY sequence LIMIT 2""", (row['run'],)).fetchall()
    if (len(entries) != 1 or type(entries[0]['size']) is not int
            or not 0 < entries[0]['size'] <= MAX_BYTES):
        raise ValueError('LE trace requires its unique bounded original process-entry receipt')
    entry = entries[0]
    receipt = _document(project.db.execute('SELECT evidence FROM debug_events WHERE sequence=?',
                                          (entry['sequence'],)).fetchone()[0])
    original_process = receipt.get('process')
    if (type(original_process) is not dict or original_process.get('state') != 'active'
            or original_process.get('source_mapping', {}).get('status') != 'initial-load-verified'
            or original_process['source_mapping'].get('live') is not True):
        raise ValueError('LE trace original process entry is not verified')
    original = load_trace_binding(project, row['version'], dict(current_metadata, process=original_process))
    if not (_json(original['identity']) == _json(current['identity']) == _json(captured['identity'])):
        raise ValueError('LE trace differs from its immutable DOS launch identity')
    return entry['sequence']


def _le_native_binding(project, row, document, metadata):
    from .le import load_runtime_le_carrier
    from .qemu_dos_le_identity import BINDING_FORMAT, CAPTURE_FORMAT, SOURCE_SCOPE, validate_recipe

    mapping = document['mapping']; recipe = mapping.get('protected_source_binding')
    capture = document.get('native_process_capture')
    if (type(recipe) is not dict or type(capture) is not dict
            or capture.get('format') != CAPTURE_FORMAT or capture.get('source_scope') != SOURCE_SCOPE
            or capture.get('binding_id') != recipe.get('binding_id')
            or capture.get('capture_epoch') != recipe.get('capture_epoch')
            or document.get('capture_epoch') != recipe.get('capture_epoch')
            or mapping.get('process', {}).get('capture_epoch') != recipe.get('capture_epoch')):
        raise ValueError('LE capture differs from its bound process epoch')
    _native_step_policy(capture.get('step_policy'))
    entry_sequence = _le_launch_binding(project, row, document, metadata)
    reference = mapping.get('protected_source_binding_artifact')
    if type(reference) is not dict:
        raise ValueError('LE capture lacks its owned source-binding artifact')
    binding_row, binding_document = _artifact(project, reference.get('artifact'), 'dos-source-binding')
    if (binding_row['run'] != row['run'] or binding_row['version'] != row['version']
            or reference.get('sha256') != binding_row['sha256'] or reference.get('size') != binding_row['size']
            or binding_document.get('format') != BINDING_FORMAT or binding_document.get('recipe') != recipe):
        raise ValueError('LE capture source binding differs from retained evidence')
    admission_reference = binding_document.get('admission')
    if type(admission_reference) is not dict:
        raise ValueError('LE source binding lacks its initial admission artifact')
    admission_row, admission = _artifact(project, admission_reference.get('artifact'), 'dos-source-admission')
    if (admission_row['run'] != row['run'] or admission_row['version'] != row['version']
            or admission_reference.get('sha256') != admission_row['sha256']
            or admission_reference.get('size') != admission_row['size']
            or admission != recipe.get('initial_admission')):
        raise ValueError('LE binding initial admission differs from retained evidence')
    identity = dict(run=row['run'], capture_epoch=recipe.get('capture_epoch'),
        source_sha256=metadata['source_sha256'], version=row['version'], version_sha256=row['version_sha256'])
    if any(recipe.get(key) != value or admission.get(key) != value for key, value in identity.items()):
        raise ValueError('LE admission/binding identity differs from its owning trace')
    admission_created = _capture_sequence(project, admission_row)
    admission_event = _operation_receipt(project, row['run'], 'dos-source-admission', admission_row['id'],
        dict(sha256=admission_row['sha256'], status='admitted'))
    binding_created = _capture_sequence(project, binding_row)
    binding_event = _operation_receipt(project, row['run'], 'dos-source-bind', binding_row['id'],
        dict(sha256=binding_row['sha256'], binding_id=recipe.get('binding_id'),
             capture_epoch=recipe.get('capture_epoch'), admission=admission_reference))
    trace_created = _capture_sequence(project, row)
    if not entry_sequence < admission_created < admission_event < binding_created < binding_event < trace_created:
        raise ValueError('LE capture admission/binding/trace evidence is out of order')
    source_size = project.db.execute('SELECT fdb_length(source_bytes) FROM binary_info WHERE version=?',
                                     (row['version'],)).fetchone()
    if source_size is None or type(source_size[0]) is not int or not 0 < source_size[0] <= 64*1024*1024:
        raise ValueError('LE trace retained original source exceeds its bounded extent')
    source = bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',
                                      (row['version'],)).fetchone()[0])
    if len(source) != source_size[0] or hashlib.sha256(source).hexdigest() != metadata['source_sha256']:
        raise ValueError('LE trace retained source identity differs')
    image = load_runtime_le_carrier(source)
    validate_recipe(image, recipe)
    configuration = mapping.get('machine_configuration')
    if (type(configuration) is not dict or configuration.get('cpus') != 1
            or type(configuration.get('memory_mib')) is not int or not 1 <= configuration['memory_mib'] <= 0xffffffff):
        raise ValueError('LE trace requires its one-CPU bounded RAM configuration')
    material = mapping.get('protected_source_binding_material')
    gdt_hex = binding_document.get('gdt_hex')
    if (type(material) is not dict or material.get('gdt_hex') != gdt_hex
            or type(gdt_hex) is not str or len(gdt_hex) > 2*65536
            or not re.fullmatch('[0-9a-f]*', gdt_hex) or len(gdt_hex) % 2):
        raise ValueError('LE trace GDT material differs from its source binding')
    gdt = bytes.fromhex(gdt_hex)
    if (len(gdt) != admission['gdt']['limit'] + 1
            or hashlib.sha256(gdt).hexdigest() != admission['gdt']['sha256']):
        raise ValueError('LE trace GDT differs from its initial admission')
    return dict(image=image, recipe=recipe, gdt=gdt, ram_end=min(configuration['memory_mib'] << 20, 0xc0000000))


def _le_native_events(document, compiled, binding):
    """Re-run complete instruction relocation proof from retained readback bytes."""
    from .qemu_dos_le_identity import qualify_instruction
    recipe, gdt = binding['recipe'], binding['gdt']
    for index, (raw, event) in enumerate(zip(document['events'], compiled['events'])):
        identity = raw.get('identity')
        if (type(identity) is not dict or identity.get('source_version') != compiled['identity']['version']
                or raw.get('mapping_id') != recipe['binding_id'] or raw.get('task_id') is not None
                or raw.get('project_address') is not None or event['pc']['project'] is not None
                or event['observation'].get('instruction_completed') not in (None, False)):
            raise ValueError('LE observation differs from its bound source/epoch identity')
        if identity.get('source_location') is None:
            if event['site'] is not None or compiled['window']['closed'] or index != len(compiled['events'])-1:
                raise ValueError('LE trace continued beyond an unqualified source boundary')
            continue
        witness = raw.get('le_source_witness')
        if type(witness) is not dict or set(witness) != {'cpu', 'gdt_sha256', 'readback'}:
            raise ValueError('LE source event lacks its stopped readback witness')
        cpu = witness['cpu']
        initial = recipe['initial_admission']['gdt']
        if (type(cpu) is not dict or witness['gdt_sha256'] != hashlib.sha256(gdt).hexdigest()
                or cpu.get('gdtr_base') != initial['base'] or cpu.get('gdtr_limit') != initial['limit']):
            raise ValueError('LE source witness differs from its admitted GDT')
        reads = witness['readback']
        if type(reads) is not list or not 1 <= len(reads) <= 64:
            raise ValueError('LE source readback exceeds its extent budget')
        memory = {}
        for extent in reads:
            if type(extent) is not dict or set(extent) != {'address', 'length', 'hex'}:
                raise ValueError('Invalid LE source readback extent')
            address = _integer(extent['address'], 'LE readback address', 0, 0xffffffff)
            length = _integer(extent['length'], 'LE readback length', 1, 524288)
            value = extent['hex']
            if (not (0 <= address < address+length <= 0xa0000
                         or 0x100000 <= address < address+length <= binding['ram_end'])
                    or type(value) is not str or len(value) != length*2
                    or re.fullmatch('[0-9a-f]*', value) is None):
                raise ValueError('Invalid LE source readback bytes')
            key = (address, length); data = bytes.fromhex(value)
            for (prior_address, prior_length), prior in memory.items():
                low, high = max(address, prior_address), min(address+length, prior_address+prior_length)
                if low < high and data[low-address:high-address] != prior[low-prior_address:high-prior_address]:
                    raise ValueError('Contradictory overlapping LE source readback extents')
            memory[key] = data
        def read(address, length):
            if (address, length) not in memory:
                raise ValueError('LE source witness lacks required read coverage')
            return memory[address, length]
        qualification = qualify_instruction(binding['image'], recipe, cpu, gdt, read)
        # Exact public identity and the runtime bytes are checked below; no
        # stored mask, source flag or digest authorizes a source claim itself.
        if not qualification.get('qualified'):
            raise ValueError('Retained LE source instruction no longer qualifies')
        if (identity.get('source_location') != qualification.get('source_location')
                or identity.get('context') != qualification.get('context')
                or identity.get('source_instruction_sha256') != qualification.get('source_instruction_sha256')):
            raise ValueError('LE event source identity differs from reconstructed original instruction')
        if (raw.get('cpu_mode') != 'protected' or raw.get('code_bits') != 32
                or event['observation'].get('registers_stage') != 'before-instruction'
                or event['observation'].get('flags_materialized') is not True):
            raise ValueError('LE source event lacks observed stopped protected32 registers')
        context = event['execution_context']['address_context']
        cs = context.get('cs', {}) if type(context) is dict else {}
        if (type(context) is not dict or context.get('cpu_mode') != 'protected' or context.get('code_bits') != 32
                or context.get('paging_enabled') is not False or context.get('a20') is not True
                or type(context.get('cr0')) is not int
                or context['cr0'] & 0x80000001 != 1
                or cs.get('selector') != cpu.get('cs') or cs.get('base') != cpu.get('cs_base')
                or cs.get('limit') != cpu.get('cs_limit') or cs.get('attributes') != cpu.get('cs_attributes')
                or event['pc']['offset'] != cpu.get('ip') or event['pc']['segment'] != cpu.get('cs')):
            raise ValueError('LE source witness differs from observed PC or address context')
        code = bytes.fromhex(raw.get('execution_bytes', raw.get('bytes', '')))
        if 'bytes' in raw and 'execution_bytes' in raw and raw['bytes'] != raw['execution_bytes']:
            raise ValueError('LE observed instruction byte fields disagree')
        if (code.hex() != qualification.get('execution_bytes')
                or len(code) != qualification.get('instruction_size')):
            raise ValueError('LE trace instruction bytes differ from reconstructed source witness')
        claimed = raw.get('source_qualification')
        expected = {key: value for key, value in qualification.items() if key != 'execution_bytes'}
        if (type(claimed) is not dict or
                {key: value for key, value in claimed.items() if key != 'execution_bytes'} != expected
                or ('execution_bytes' in claimed and claimed['execution_bytes'] != code.hex())):
            raise ValueError('LE source qualification differs from reconstructed instruction')


def _regions(mapped, supplied):
    if supplied is None:
        supplied = []
        for index, (start, end, name) in enumerate(mapped):
            identifier = f'project:{index}:{start:x}:{end:x}'
            if type(name) is not str or not name.strip() or len(name) > 256:
                name = identifier
            supplied.append(dict(id=identifier, name=name, space='project', start=start, end=end))
    return kernel.validate_regions(supplied)


def _qualify_image(compiled, mapped):
    """Caller region labels cannot establish original-image membership.

    A changed instruction can still be compared by its observed byte hash, but
    a site outside the selected image is not a cross-run source identity. A PC
    inside the image remains a valid PC even when its decoded instruction spans
    beyond the mapped bytes; only that instruction's site becomes unqualified.
    """
    for event in compiled['events']:
        address = event['pc']['project']
        if address is None:
            continue
        containing = next(((start, end) for start, end, _ in mapped if start <= address < end), None)
        if containing is None:
            event['pc']['project'] = None
            event['site'] = None
            event['source_qualification'] = 'PC is outside the selected source image'
            linear = event['pc']['linear']
            event['region'] = next((region for region in compiled['regions']
                if region['space'] == 'linear' and linear is not None
                and region['start'] <= linear < region['end']), None)
        elif event['site'] is not None and address + event['size'] > containing[1]:
            event['site'] = None
            event['source_qualification'] = 'Instruction extends beyond its mapped source region'
    compiled['unqualified_events'] = sum(event['site'] is None for event in compiled['events'])


def _trace_reference(row):
    return dict(artifact=row['id'], sha256=row['sha256'], run=row['run'], version=row['version'])


def _trace(project, identifier, *, regions=None):
    row, document = _artifact(project, identifier, 'trace')
    metadata = _document(row['run_metadata'])
    mapping = document.get('mapping')
    if type(mapping) is not dict:
        raise ValueError('Stored trace lacks its launch mapping identity')
    if (type(document.get('version')) is not int or document['version'] != row['version']
            or metadata.get('source_sha256') != project.meta['source_sha256']
            or metadata.get('version_sha256') != row['version_sha256']
            or mapping.get('source_sha256') != metadata['source_sha256']
            or mapping.get('version_sha256') != metadata['version_sha256']):
        raise ValueError('Trace source or version differs from its owning project run')
    _digest(metadata['source_sha256'])
    _digest(metadata['version_sha256'])
    native_binding = None
    le_binding = None
    if _backend(project, metadata) == 'qemu-dos':
        capture = document.get('native_process_capture')
        if type(capture) is dict and capture.get('format') == 'fdisbull-qemu-dos-le-capture-1':
            le_binding = _le_native_binding(project, row, document, metadata)
        else:
            native_binding = _native_binding(project, row, document, metadata)
    else:
        captured_mapping = _mapping_identity(project, mapping)
        current_mapping = _mapping_identity(project, metadata)
        if (_json(captured_mapping) != _json(current_mapping)
                and not _historical_pe_mapping(project, row, captured_mapping, current_mapping, metadata)):
            raise ValueError('Trace mapping differs from the retained run launch identity')
    mapped = [(region.start, region.start + len(region.data), region.name)
              for region in project.regions(row['version']) if region.data]
    compiled = kernel.normalize_trace(document, regions=_regions([] if le_binding is not None else mapped, regions))
    expected = dict(source_sha256=metadata['source_sha256'], version_sha256=row['version_sha256'],
                    version=row['version'], backend=_backend(project, metadata))
    if (_json(compiled['identity']) != _json(expected) or compiled['run'] != row['run']):
        raise ValueError('Normalized trace identity differs from its owning run')
    clock = next((event['clock'] for event in compiled['events'] if 'clock' in event),
                 compiled.get('collector', {}).get('current_stop', {}).get('clock'))
    if clock is not None:
        from .execution_clock import validate_clock_admission

        validate_clock_admission(metadata, backend=expected['backend'], native_epoch=clock['native_epoch'])
        fields = ('cpus', 'clock_profile', 'native_clock_admission')
        captured = mapping['machine_configuration']
        owned = metadata['machine_configuration']
        if _json({key: captured[key] for key in fields}) != _json({key: owned[key] for key in fields}):
            raise ValueError('Trace clock admission differs from its owning run')
    if native_binding is not None:
        _native_events(document, compiled, native_binding)
    if le_binding is not None:
        _le_native_events(document, compiled, le_binding)
    else:
        _qualify_image(compiled, mapped)
    compiled['artifact'] = dict(id=row['id'], sha256=row['sha256'])
    return row, compiled


def _search_document(project, identifier):
    row, envelope = _artifact(project, identifier, 'event-search')
    if envelope.keys() != _ENVELOPE_KEYS or envelope['format'] != FORMAT:
        raise ValueError('Invalid event search envelope')
    _integer(envelope['generation'], 'search generation', 0, MAX_HISTORY - 1)
    owner = envelope['owner']
    if (type(owner) is not dict or owner.keys() != _IDENTITY_KEYS | {'run'}
            or owner['run'] != row['run'] or type(owner['version']) is not int
            or owner['version'] != row['version']
            or owner['version_sha256'] != row['version_sha256']
            or owner['source_sha256'] != project.meta['source_sha256']):
        raise ValueError('Event search differs from its owning source or run')
    _digest(owner['source_sha256'])
    _digest(owner['version_sha256'])
    _identifier(owner['run'])
    if type(owner['backend']) is not str or owner['backend'] not in _BACKENDS:
        raise ValueError('Unsupported retained event search backend')
    parent = envelope['parent']
    if parent is not None:
        if type(parent) is not dict or parent.keys() != {'artifact', 'sha256'}:
            raise ValueError('Invalid event search parent reference')
        _identifier(parent['artifact'])
        _digest(parent['sha256'])
    reference = envelope['trace']
    if type(reference) is not dict or reference.keys() != {'artifact', 'sha256', 'run', 'version'}:
        raise ValueError('Invalid event search trace reference')
    _identifier(reference['artifact'])
    _identifier(reference['run'])
    _digest(reference['sha256'])
    _integer(reference['version'], 'trace reference version', 1, (1 << 63) - 1)
    operation = envelope['operation']
    if type(operation) is not dict:
        raise ValueError('Invalid retained search operation')
    keys = {'mode', 'predicate', 'label'}
    if parent is None:
        keys |= {'feature', 'registers'}
    if (operation.keys() != keys or type(operation['mode']) is not str or operation['mode'] not in
            (('start',) if parent is None else ('retain', 'exclude'))):
        raise ValueError('Invalid retained search operation')
    normalized = kernel.validate_regions(envelope['regions'])
    if _json(normalized) != _json(envelope['regions']):
        raise ValueError('Retained search regions are not canonical')
    return row, envelope


def _operation(state, mode):
    history = state['history'][-1]
    result = dict(mode=mode, predicate=deepcopy(history['predicate']), label=history['label'])
    if mode == 'start':
        result.update(feature=state['feature'],
                      registers=deepcopy(state['registers']) if state['feature'] == 'register-value' else None)
    return result


def _load_search(project, identifier):
    """Replay a bounded lineage without retaining every large intermediate state."""
    _identifier(identifier)
    chain, visited = [], set()
    current, expected_sha = identifier, None
    while True:
        if current in visited or len(chain) >= MAX_HISTORY:
            raise ValueError('Event search lineage is cyclic or exceeds 128 trials')
        visited.add(current)
        row, envelope = _search_document(project, current)
        if expected_sha is not None and expected_sha != row['sha256']:
            raise ValueError('Event search parent artifact changed')
        chain.append(dict(artifact=current, sha256=row['sha256']))
        if envelope['parent'] is None:
            break
        current, expected_sha = envelope['parent']['artifact'], envelope['parent']['sha256']
    state, owner, regions, previous, references = None, None, None, None, []
    for generation, reference in enumerate(reversed(chain)):
        row, envelope = _search_document(project, reference['artifact'])
        if row['sha256'] != reference['sha256']:
            raise ValueError('Event search changed during lineage verification')
        if envelope['generation'] != generation or envelope['parent'] != previous:
            raise ValueError('Event search generation or parent lineage differs')
        if generation == 0:
            owner, regions = envelope['owner'], envelope['regions']
        elif _json(envelope['owner']) != _json(owner) or _json(envelope['regions']) != _json(regions):
            raise ValueError('Event search lineage changes source, owner or region identity')
        trace_row, compiled = _trace(project, envelope['trace']['artifact'], regions=regions)
        if (_trace_reference(trace_row) != envelope['trace']
                or _json(compiled['identity']) != _json({key: owner[key] for key in _IDENTITY_KEYS})):
            raise ValueError('Referenced trace changed or differs from the search identity')
        operation = envelope['operation']
        if generation == 0:
            if trace_row['run'] != owner['run']:
                raise ValueError('Initial trace and event search have different owning runs')
            state = kernel.start_search(compiled, **{key: operation[key]
                for key in ('feature', 'registers', 'predicate', 'label')})
        else:
            state = kernel.refine_search(state, compiled, **operation)
        kernel.validate_search(envelope['state'])
        if (_json(state) != _json(envelope['state'])
                or _json(_operation(state, operation['mode'])) != _json(operation)):
            raise ValueError('Retained search state differs from its verified trace lineage')
        references.append(envelope['trace'])
        previous = reference
    return row, envelope, state, references


def _save(project, envelope):
    raw = _json(envelope)
    if len(raw) > MAX_BYTES:
        raise ValueError('Event search exceeds its 16 MiB artifact budget')
    preview = kernel.search_results(envelope['state'], limit=16)
    artifact = project._debug_artifact(envelope['owner']['run'], 'event-search.json', 'event-search', raw,
        dict(format=FORMAT, generation=envelope['generation'], trace_artifact=envelope['trace']['artifact'],
             parent_search_artifact=(envelope['parent'] or {}).get('artifact')))
    return {key: value for key, value in artifact.items() if key != 'metadata'} | {
        'trace_artifact': envelope['trace']['artifact'], 'generation': envelope['generation'],
        'results': preview}


class EventSearchProjectMixin:
    """Persistent event-set narrowing; all operations work without a live guest."""

    def event_search_start(self, trace, *, feature='site', registers=None, predicate=None,
                           label='trial', regions=None):
        with self.transaction(True):
            row, compiled = _trace(self, trace, regions=regions)
            state = kernel.start_search(compiled, feature=feature, registers=registers,
                                        predicate=predicate, label=label)
            envelope = dict(format=FORMAT, owner=dict(compiled['identity'], run=row['run']), generation=0,
                parent=None, trace=_trace_reference(row), regions=compiled['regions'],
                operation=_operation(state, 'start'), state=state)
            return _save(self, envelope)

    def event_search_refine(self, search, trace, *, mode='retain', predicate=None, label='trial'):
        with self.transaction(True):
            row, previous, state, _ = _load_search(self, search)
            if previous['generation'] + 1 >= MAX_HISTORY:
                raise ValueError('Event search lineage exceeds 128 trials')
            trace_row, compiled = _trace(self, trace, regions=previous['regions'])
            if _json(compiled['identity']) != _json(state['identity']):
                raise ValueError('Cannot refine an event search across source, version or backend identities')
            state = kernel.refine_search(state, compiled, mode=mode, predicate=predicate, label=label)
            envelope = dict(format=FORMAT, owner=previous['owner'], generation=previous['generation'] + 1,
                parent=dict(artifact=search, sha256=row['sha256']), trace=_trace_reference(trace_row),
                regions=previous['regions'], operation=_operation(state, mode), state=state)
            return _save(self, envelope)

    def event_search_results(self, search, *, offset=0, limit=64):
        with self.transaction():
            _, envelope, state, references = _load_search(self, search)
            return dict(search_artifact=search, trace_artifact=envelope['trace']['artifact'],
                        owner=deepcopy(envelope['owner']), trace_references=references,
                        **kernel.search_results(state, offset=offset, limit=limit))

    def event_trace_query(self, trace, *, predicate, regions=None, offset=0, limit=64):
        _integer(offset, 'offset', 0, (1 << 63) - 1)
        _integer(limit, 'limit', 1, 256)
        checked = kernel.validate_predicate(predicate)
        with self.transaction():
            row, compiled = _trace(self, trace, regions=regions)
            matches = unknown = 0
            rows, unknown_examples = [], []
            events = compiled['events']
            initial = events[0] if events else None
            for index, event in enumerate(events):
                evaluation = kernel.evaluate_predicate(checked, event, initial=initial,
                    previous=events[index - 1] if index else None)
                if evaluation['matched'] is None:
                    unknown += 1
                    if len(unknown_examples) < 8:
                        unknown_examples.append(dict(index=event['index'], unknown=evaluation['unknown']))
                elif evaluation['matched'] is True:
                    if offset <= matches < offset + limit:
                        rows.append(dict(deepcopy(event), trace_artifact=trace,
                                         evaluation=evaluation))
                    matches += 1
            result = dict(trace_artifact=trace, trace_sha256=row['sha256'], run=row['run'],
                identity=compiled['identity'], predicate=checked, regions=compiled['regions'],
                window=compiled['window'], complete=compiled['window']['closed'],
                scanned_events=len(compiled['events']), matched_count=matches,
                unknown_count=unknown, unmatched_count=len(compiled['events']) - matches - unknown,
                unknown_examples=unknown_examples, offset=offset, limit=limit, rows=rows,
                next_offset=offset + len(rows) if offset + len(rows) < matches else None,
                scope='Retrospective observations only; no claim the live target stopped at a returned match')
            endpoint = compiled.get('collector', {}).get('current_stop', {}).get('clock')
            if endpoint is not None:
                result['endpoint_clock'] = deepcopy(endpoint)
            return result
