"""Private LE source companions to immutable owned-machine checkpoints.

A companion qualifies one stopped source relation. It neither restores a
saved handle nor establishes a DOS allocation, task or code lifetime.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from .qemu_cpu_undo_guard import full_load
from . import qemu_owned_checkpoint as owned

FORMAT = 'fdisbull-qemu-dos-le-checkpoint-1'
KIND = 'le-source-state'
MAX_DESCRIPTOR = 8 * 1024 * 1024
MAX_STATE = owned.MAX_STATE
SCOPE = 'saved stopped LE relation revalidated after full owned-machine restore'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _producer():
    root = Path(__file__).parent
    return {name: _sha((root/name).read_bytes()) for name in
            ('qemu_dos_le_checkpoint.py', 'qemu_owned_checkpoint.py', 'qemu_long_mode_fence.py',
             'qemu_dos_le_binding.py', 'qemu_dos_le_identity.py',
             'qemu_dos_source_admission.py', 'qemu_dos_le_match.py', 'le.py', 'qemu_machine.py', 'qemu_ram.py')}


# Exact c3857f1c companion producer; no mixed or partially matching manifests.
_BASELINE_PRODUCER = {
    'qemu_dos_le_checkpoint.py': '656d2278e07f21fe5c5e1fb297ca4d9b3339c0a5690c4187e2bdbeac3e7c7ae7',
    'qemu_owned_checkpoint.py': '5d916479343f96a48e0f6352ffa3a347c9eefc582d66d80fb0b4a18cb4f1b81c',
    'qemu_dos_le_binding.py': '9934f5b537b1bc52aaedf732f5f838b8b53a6526886e9d8d9014bb7f6b153f00',
    'qemu_dos_le_identity.py': '44cd61c9921eca81a6d79afc252818d87e68336ff5cce86f41f4d83663599ab0',
    'qemu_dos_source_admission.py': '1008a2933daead5469e92b6dd9af0dd40c68b00ab281e8c18d9817c1a8c1594c',
    'qemu_dos_le_match.py': 'fffeb298ab43572c5320886e8ee25045fcb1c8d621f4a6a06ac659b4a5fa4d43',
    'le.py': 'b97ea8142b88a0aecc968880ad5308a748ad73cf695bb4f6a1e4872752c53298',
    'qemu_machine.py': '3f2e9c669a60427a57564cb407de3b12adb55d7dde4ca67846078c3793b6aaa8',
    'qemu_ram.py': '19cb041cbbd8f2c46573c7c8396b44aaa40f8f9f22a6ecf0f93aff6005578103',
}

_ATOMIC_BATCH_PRODUCER = dict(_BASELINE_PRODUCER, **{
    'qemu_dos_le_checkpoint.py': '2bfad50a1bbab85af69faceebf3f3b72ab6f7feff30a9346a4013e30355c4174',
    'qemu_owned_checkpoint.py': 'cf8db2d53401c367fd253d2c76b188ef935fccea19175fd3206e01110dce7623',
})

_CMPXCHG16B_PRODUCER = dict(_BASELINE_PRODUCER, **{
    'qemu_dos_le_checkpoint.py': '9f4953ddb60fdecd257297cb5a6917a210c665c9e0323705f161e9ebf8aa90de',
    'qemu_owned_checkpoint.py': '3d615c980d600ff0740ca0bd2c78573db2f04ea41dcb848d2e7ed4db2ff187a8',
    'qemu_long_mode_fence.py': '023637781b36e41b4a2fd92313eca9feba4b3e9408f32fc067715941bf170348',
})


def _compatible_producer(recorded, current):
    return recorded == current or recorded in (
        _BASELINE_PRODUCER, _ATOMIC_BATCH_PRODUCER, _CMPXCHG16B_PRODUCER)


def _reference(project, reference, kind, version, *, maximum=None):
    _require(isinstance(reference, dict) and set(reference) == {'artifact', 'sha256', 'size'}
             and isinstance(reference['artifact'], str) and bool(reference['artifact'])
             and type(reference['size']) is int and reference['size'] > 0,
             'Invalid LE checkpoint artifact reference')
    row = project.db.execute(
        'SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
        (reference['artifact'],)).fetchone()
    _require(row is not None and row['kind'] == kind and row['version'] == version,
             'LE checkpoint reference kind or version differs')
    data = bytes(row['data'])
    _require(len(data) == reference['size'] and _sha(data) == row['sha256'] == reference['sha256']
             and (maximum is None or len(data) <= maximum), 'LE checkpoint referenced bytes differ')
    return row, data, json.loads(row['metadata'])


def _ref(receipt):
    return {key: receipt[key] for key in ('artifact', 'sha256', 'size')}


def _observe(session):
    state = getattr(session, '_le_source', None)
    _require(state is not None and state['state'] != 'retired',
             'LE checkpoint capture requires an installed current source binding')
    raw, stopped = session._le_source_observe(state, state['observations']+1)
    _require(state is session._le_source and session._le_source_owner_valid(state)
             and raw['source_qualification']['qualified'] is True and state['state'] == 'qualified-stopped',
             'LE checkpoint requires a fully qualified current source instruction')
    return dict(recipe=deepcopy(state['recipe']), gdt_hex=state['material']['gdt_hex'],
                binding=_ref(state['binding_artifact']), boundary=raw,
                registers=deepcopy(stopped['registers']))


def admit_le_source_capture(session, *, timeout_ms=60000):
    """Freshly admit an installed relation before a checkpoint/history intent.

    Ordinary source admission/binding artifacts are retained. No machine
    checkpoint, history intent, guest execution or memory write is performed.
    """
    with owned._operation(session, timeout_ms) as (_, deadline):
        owned._preflight(session)
        _observe(session)
        return session.dos_source_bind(expected_source_sha256=session.metadata['source_sha256'],
                                       timeout_ms=owned._remaining(deadline))


def _canonical(proof):
    qualification = proof['boundary']['source_qualification']
    return dict(source_location=qualification['source_location'],
                instruction_sha256=qualification['source_instruction_sha256'],
                context=qualification['context'], execution_bytes=qualification['execution_bytes'])


def _validate_source(session, document):
    """Validate stored proofs from retained source only; no live VM required."""
    from .le import load_runtime_le_carrier
    from .qemu_dos_source_admission import _source, _context, _producer as admission_producer
    from .qemu_dos_le_binding import _producer as binding_producer
    from .qemu_dos_le_identity import validate_recipe, qualify_instruction, BINDING_FORMAT
    _require(document.get('format') == FORMAT and document.get('source_view') == 'embedded-le'
             and document.get('source_scope') == SCOPE
             and document.get('lifetime_qualified') is False and document.get('source_binding_restored') is False
             and _compatible_producer(document.get('producer'), _producer()), 'LE checkpoint scope or producer identity differs')
    raw, identity = _source(session, document.get('source_sha256'))
    _require(type(document.get('version')) is int
             and all(document.get(k) == value for k, value in identity.items()),
             'LE checkpoint source/version identity differs')
    image = load_runtime_le_carrier(raw)
    recipe = validate_recipe(image, document['recipe'])
    _require(all(recipe[k] == value for k, value in identity.items())
             and recipe['run'] == document['run'] and recipe['capture_epoch'] == document['capture_epoch'],
             'LE checkpoint recipe owner identity differs')
    binding_row, binding_bytes, binding_metadata = _reference(session.project, document['binding'],
        'dos-source-binding', session.version['id'], maximum=4*1024*1024)
    binding = json.loads(binding_bytes)
    _require(binding.get('format') == BINDING_FORMAT and binding.get('recipe') == recipe
             and binding.get('gdt_hex') == document['gdt_hex'] and binding.get('producer') == binding_producer()
             and binding_row['run'] == recipe['run']
             and binding_metadata.get('binding_id') == recipe['binding_id']
             and binding_metadata.get('capture_epoch') == recipe['capture_epoch'],
             'LE checkpoint binding artifact differs')
    admission_row, admission_bytes, _ = _reference(session.project, binding['admission'],
        'dos-source-admission', session.version['id'], maximum=4*1024*1024)
    admission = json.loads(admission_bytes)
    _require(admission == recipe['initial_admission'] and admission_row['run'] == recipe['run']
             and admission.get('producer') == admission_producer(),
             'LE checkpoint source admission differs')
    from .event_search import _capture_sequence, _operation_receipt
    admission_created = _capture_sequence(session.project, dict(admission_row, size=len(admission_bytes)))
    admission_done = _operation_receipt(session.project, recipe['run'], 'dos-source-admission',
        admission_row['id'], dict(sha256=admission_row['sha256'], status='admitted'))
    binding_created = _capture_sequence(session.project, dict(binding_row, size=len(binding_bytes)))
    binding_done = _operation_receipt(session.project, recipe['run'], 'dos-source-bind', binding_row['id'],
        dict(sha256=binding_row['sha256'], binding_id=recipe['binding_id'],
             capture_epoch=recipe['capture_epoch'], admission=binding['admission']))
    _require(admission_created < admission_done < binding_created < binding_done,
             'LE checkpoint source receipt ordering differs')
    registers = document['registers']; boundary = document['boundary']
    cpu = _context(registers); table = recipe['initial_admission']['gdt']
    cpu.update(gdtr_base=table['base'], gdtr_limit=table['limit'])
    gdt = bytes.fromhex(document['gdt_hex'])
    _require(len(gdt) == table['limit']+1 and _sha(gdt) == table['sha256'],
             'LE checkpoint GDT material differs')
    witness = boundary['le_source_witness']
    _require(witness['cpu'] == cpu and witness['gdt_sha256'] == _sha(gdt),
             'LE checkpoint CPU/GDT witness differs')
    reads = {}
    for row in witness['readback']:
        address, length = row['address'], row['length']
        _require(type(address) is type(length) is int and 0 <= address < address+length <= 2**32
                 and 1 <= length <= 65536 and (address, length) not in reads,
                 'Invalid LE checkpoint source readback extent')
        value = bytes.fromhex(row['hex'])
        _require(len(value) == length, 'LE checkpoint source readback length differs')
        reads[address, length] = value
    _require(sum(length for _, length in reads) <= 524288, 'LE checkpoint readback budget exceeded')
    def read(address, length):
        _require((address, length) in reads, 'LE checkpoint source witness is incomplete')
        return reads[address, length]
    qualification = qualify_instruction(image, recipe, cpu, gdt, read)
    _require(qualification['qualified'] is True and boundary['source_qualification'].get('qualified') is True
             and qualification == boundary['source_qualification']
             and boundary['identity']['source_version'] == session.version['id']
             and boundary['identity']['source_location'] == qualification['source_location']
             and boundary['identity']['source_instruction_sha256'] == qualification['source_instruction_sha256']
             and boundary['identity']['context'] == qualification['context']
             and boundary['mapping_id'] == recipe['binding_id']
             and boundary['project_address'] is None and boundary['task_id'] is None
             and boundary['registers'] == registers['registers']
             and boundary['address'] == registers['linear_pc']
             and boundary['execution_bytes'] == qualification['execution_bytes'],
             'LE checkpoint stopped instruction proof differs')
    return dict(image=image, source_receipt_sequence=binding_done)


def _descriptor(session, proof, machine, producer):
    return dict(format=FORMAT, source_view='embedded-le', lifetime_qualified=False,
        source_binding_restored=False, source_scope=SCOPE, machine=machine,
        source_sha256=session.metadata['source_sha256'], version=session.version['id'],
        version_sha256=session.metadata['version_sha256'], run=session.run_id,
        capture_epoch=session._runtime_epoch, producer=producer, **proof)


def save_le_source_state(session, name='dos-le-source.json', max_bytes=None, timeout_ms=60000):
    from .external_files import _file_name
    _file_name(name)
    limit = MAX_STATE if max_bytes is None else max_bytes
    _require(type(limit) is int and MAX_DESCRIPTOR < limit <= MAX_STATE,
             'LE checkpoint charged byte budget must exceed 8 MiB and be at most 128 MiB')
    with owned._operation(session, timeout_ms) as (_, deadline):
        admit_le_source_capture(session, timeout_ms=owned._remaining(deadline))
        producer = _producer()
        before = _observe(session)
        captured = owned.capture_owned_machine_state(session, name='le-owned-machine.qcow2',
                                                      max_bytes=limit-MAX_DESCRIPTOR)
        try:
            after = _observe(session)
            _require(all(before[k] == after[k] for k in ('recipe', 'gdt_hex', 'binding', 'registers'))
                     and _canonical(before) == _canonical(after)
                     and before['boundary']['le_source_witness'] == after['boundary']['le_source_witness']
                     and producer == _producer(), 'LE source relation changed across machine capture')
            _, bundle = owned._unarchive(captured['data'])
            _require(bundle['registers'] == before['registers'], 'LE source and machine capture CPU differ')
            _validate_source(session, _descriptor(session, before,
                dict(artifact='pending', sha256=captured['sha256'], size=captured['size']), producer))
            owned._remaining(deadline)
            with session.project.transaction(True):
                from .qemu_dos_source_admission import _source
                _require(_source(session, session.metadata['source_sha256'], internal_transaction=True)[1]
                         == {k: before['recipe'][k] for k in ('source_sha256', 'version', 'version_sha256')}
                         and producer == _producer()
                         and session._le_source_owner_valid(session._le_source)
                         and session._le_source['recipe'] == before['recipe']
                         and session.registers() == before['registers'],
                         'LE source identity changed before companion publication')
                machine = session._artifact(captured['name'], captured['kind'], captured['data'], captured['metadata'])
                document = _descriptor(session, before, _ref(machine), producer)
                data = _json(document)
                charged = len(data)+machine['size']
                _require(len(data) <= MAX_DESCRIPTOR and charged <= limit,
                         'LE checkpoint descriptor or charged byte budget exceeded')
                receipt = session._artifact(name, KIND, data, dict(format=FORMAT, source_view='embedded-le',
                    source_sha256=document['source_sha256'], version_sha256=document['version_sha256'],
                    capture_epoch=document['capture_epoch'], machine=_ref(machine), charged_size=charged,
                    lifetime_qualified=False, source_binding_restored=False, host_files_restored=False))
                session._event('save-le-source-state', dict(artifact=receipt['artifact'], sha256=receipt['sha256'],
                    machine=_ref(machine), binding_id=before['recipe']['binding_id'], charged_size=charged))
                owned._remaining(deadline)
            return dict(receipt, machine=_ref(machine), charged_size=charged)
        except BaseException as error:
            owned._close_uncertain(session, error)
            raise


def read_le_source_state(session, artifact, *, full_machine=True):
    try:
        return _read_le_source_state(session, artifact, full_machine=full_machine)
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError('Malformed LE source checkpoint') from error


def _read_le_source_state(session, artifact, *, full_machine=True):
    _require(type(full_machine) is bool, 'full_machine must be Boolean')
    _require(isinstance(artifact, str) and bool(artifact), 'LE source checkpoint identifier must be nonempty')
    row = session.project.db.execute(
        'SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
        (artifact,)).fetchone()
    _require(row is not None and row['kind'] == KIND and row['version'] == session.version['id'],
             'LE source checkpoint must belong to the selected project version')
    data = bytes(row['data'])
    _require(0 < len(data) <= MAX_DESCRIPTOR and _sha(data) == row['sha256'],
             'LE source checkpoint bytes differ')
    document = json.loads(data); metadata = json.loads(row['metadata'])
    reader_producer = _producer()
    source = _validate_source(session, document)
    _require(reader_producer == _producer(), 'LE checkpoint producer changed during read')
    _require(row['run'] == document['run'], 'LE checkpoint capture run differs')
    machine_row, machine_bytes, machine_metadata = _reference(session.project, document['machine'],
        owned.KIND, session.version['id'], maximum=MAX_STATE)
    charged = len(data)+len(machine_bytes)
    _require(machine_row['run'] == document['run']
             and all(machine_metadata.get(k) == value for k, value in dict(format=owned.FORMAT,
                 source_sha256=document['source_sha256'], version_sha256=document['version_sha256'],
                 source_binding_restored=False, host_files_restored=False).items())
             and all(metadata.get(k) == value for k, value in dict(format=FORMAT, source_view='embedded-le',
                 source_sha256=document['source_sha256'], version_sha256=document['version_sha256'],
                 capture_epoch=document['capture_epoch'], machine=document['machine'], charged_size=charged,
                 lifetime_qualified=False, source_binding_restored=False, host_files_restored=False).items())
             and charged <= MAX_STATE, 'LE checkpoint machine or companion metadata join differs')
    _require(all(metadata.get(k) is False for k in
                 ('lifetime_qualified', 'source_binding_restored', 'host_files_restored'))
             and machine_metadata.get('source_binding_restored') is False
             and machine_metadata.get('host_files_restored') is False,
             'LE checkpoint authority flags differ')
    from .event_search import _capture_sequence, _operation_receipt
    machine_created = _capture_sequence(session.project, dict(machine_row, size=len(machine_bytes)))
    companion_created = _capture_sequence(session.project, dict(row, size=len(data)))
    completed = _operation_receipt(session.project, document['run'], 'save-le-source-state', artifact,
        dict(sha256=row['sha256'], machine=document['machine'],
             binding_id=document['recipe']['binding_id'], charged_size=charged))
    _require(source['source_receipt_sequence'] < machine_created < companion_created < completed,
             'LE checkpoint capture completion ordering differs')
    result = dict(artifact=artifact, sha256=row['sha256'], size=len(data), charged_size=charged,
                  machine=deepcopy(document['machine']), document=document, metadata=metadata,
                  reader_producer=reader_producer)
    if full_machine:
        _, _, _, bundle = owned._read_artifact(session.project, document['machine']['artifact'], session.version['id'])
        _require(bundle['registers'] == document['registers']
                 and bundle['process_provenance']['capture_epoch'] == document['capture_epoch'],
                 'LE source boundary and machine checkpoint identity differ')
        result['machine_document'] = bundle
    return result


def inspect_le_source_state(project, artifact):
    row = project.db.execute('SELECT r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                             (artifact,)).fetchone()
    _require(row is not None, 'LE source checkpoint is missing')
    version = project.version(row['version'])
    session = SimpleNamespace(project=project, version=version, metadata=dict(
        source_sha256=project.meta['source_sha256'], version_sha256=version['sha256']))
    prepared = read_le_source_state(session, artifact)
    doc = prepared['document']
    return {**{k: deepcopy(prepared[k]) for k in ('artifact', 'sha256', 'size', 'charged_size', 'machine')},
        'kind':KIND, 'format':FORMAT, 'source_view':'embedded-le', 'lifetime_qualified':False,
        'source_scope':SCOPE,
        'source_binding_restored':False, 'source_sha256':doc['source_sha256'],
        'version':doc['version'], 'version_sha256':doc['version_sha256'],
        'run':doc['run'], 'capture_epoch':doc['capture_epoch'],
        'source_location':deepcopy(_canonical(doc)['source_location']),
        'instruction_sha256':_canonical(doc)['instruction_sha256'],
        'placements':deepcopy(doc['recipe']['placements']),
        'metadata':deepcopy(prepared['metadata']),
        'components':[dict(name='le-source-companion.json', size=prepared['size']),
                      dict(name='machine-state', size=doc['machine']['size'])]}


def complete_le_restore(session, prepared, protected_binding):
    """Trusted pre-attestation proof check; never accepts a saved live handle."""
    _require(isinstance(protected_binding, dict) and protected_binding.get('live') is True,
             'LE source checkpoint restore requires fresh source admission')
    saved = prepared['document']
    current = _producer()
    _require(prepared.get('reader_producer') == current and _compatible_producer(saved['producer'], current),
             'LE checkpoint producer changed before restore completion')
    fresh = _observe(session)
    _require(fresh['recipe']['binding_id'] != saved['recipe']['binding_id']
             and fresh['recipe']['capture_epoch'] == session._runtime_epoch != saved['capture_epoch']
             and fresh['recipe']['placements'] == saved['recipe']['placements']
             and fresh['gdt_hex'] == saved['gdt_hex']
             and fresh['registers'] == saved['registers']
             and _canonical(fresh) == _canonical(saved)
             and getattr(session, '_owned_machine_restored', False) is True
             and session._process['source_mapping'].get('live') is False
             and session._process['source_mapping'].get('live_ranges') == [],
             'Fresh LE source relation differs from the selected checkpoint')
    owned._remaining(session._deadline)
    return dict(le_source_checkpoint_restored=True,
        le_source_checkpoint={k: deepcopy(prepared[k]) for k in ('artifact', 'sha256', 'size', 'charged_size', 'machine')},
        protected_source_binding=session._le_source_summary(), lifetime_qualified=False,
        source_revalidation_scope=SCOPE)


@full_load
def load_le_source_state(session, artifact, timeout_ms=60000):
    with owned._operation(session, timeout_ms) as (_, deadline):
        prepared = read_le_source_state(session, artifact)
        return owned._load_owned_machine_state(session, prepared['machine']['artifact'],
            timeout_ms=owned._remaining(deadline), rebind_protected_source=True, _le_checkpoint=prepared)
