"""Bounded QEMU DOS source capture and offline admission."""
from copy import deepcopy
from functools import partial
from .qemu_machine import machine_trace_operation


ADMISSION = 'original-real16-ordinary-ram-v1'
STABLE_MAPPING = ('static_base', 'runtime_base', 'delta', 'module_size', 'load_segment',
                  'source_sha256', 'expected_module_sha256', 'observed_module_sha256')
LE_ADMISSION = 'bound-le-protected32-ordinary-ram-v1'


def _le_extent(image, recipe, cpu, start, length, backing):
    """Derive one source-backed extent inside the admitted CS and code object."""
    if (type(start) is not int or type(length) is not int or not 1 <= length <= 65536
            or not 0 <= start < start + length <= 2**32):
        raise ValueError('Invalid LE capture extent')
    selector_offset = start - cpu['cs_base']
    if selector_offset < 0 or selector_offset + length - 1 > cpu['cs_limit']:
        raise ValueError('LE capture extent exceeds the current code selector')
    index = recipe['initial_admission']['observation']['identity_evidence']['code_object']
    obj = next(o for o in image.metadata['le']['objects'] if o['index'] == index)
    placements = [p for p in recipe['placements'] if p['object_index'] == index]
    if (len(placements) != 1 or placements[0]['bits'] != 32 or not obj['executable']
            or not placements[0]['runtime_base'] <= start
            or start + length > placements[0]['runtime_base'] + obj['virtual_size']):
        raise ValueError('LE capture must fit the admitted executable object')
    offset = start - placements[0]['runtime_base']
    cursor = offset
    for page in sorted((p for p in image.metadata['le']['pages'] if p['object'] == index),
                       key=lambda p: p['object_offset']):
        low, high = page['object_offset'], page['object_offset'] + page['file_size']
        if low <= cursor < high:
            cursor = min(offset + length, high)
        if cursor == offset + length:
            break
    if cursor != offset + length:
        raise ValueError('LE capture is not fully file-backed')
    cursor = start
    for span in backing:
        if int(span['physical_address'], 16) != cursor or type(span['length']) is not int or span['length'] <= 0:
            raise ValueError('LE capture backing differs')
        cursor += span['length']
    if cursor != start + length:
        raise ValueError('LE capture backing extent differs')
    location = dict(source_view='embedded-le', application_source_sha256=recipe['application_source_sha256'],
                    object_id='le:' + str(index), object_index=index, object_offset=offset,
                    preferred_address=obj['virtual_address'] + offset)
    return location, selector_offset


def qualify_qemu_le_capture(session, observed):
    """Capture a source-bound LE extent, independently of its byte contents.

    The current instruction and placement witnesses must remain qualified;
    captured bytes themselves may have changed. This is a stopped observation,
    not an execution or allocation-lifetime claim.
    """
    try:
        return _qualify_qemu_le_capture(session, observed)
    except (KeyError, TypeError, ValueError, AttributeError, IndexError, StopIteration):
        return None


@partial(machine_trace_operation, label='Protected LE code capture', default_timeout_ms=10000)
def _qualify_qemu_le_capture(session, observed):
    from .project import now
    from .qemu_dos_le_checkpoint import _observe, _producer

    if (observed.get('space') != 'linear' or observed.get('active_layers')
            or observed.get('view') not in ('ram', 'execute')
            or getattr(session, '_dos_task_monitor', None)
            or getattr(session, '_dos_task_binding', None)):
        return None
    binding = getattr(session, '_le_source', None)
    if binding is None or binding.get('state') == 'retired':
        return None
    first = _observe(session)
    recipe = first['recipe']
    start = int(observed['runtime_address'], 16)
    length = observed['length']
    raw = bytes.fromhex(observed['hex'])
    if type(length) is not int or not 1 <= length <= 65536 or len(raw) != length:
        raise ValueError('Invalid LE capture extent')
    import hashlib
    if hashlib.sha256(raw).hexdigest() != observed['sha256']:
        raise ValueError('LE capture byte hash differs')
    cpu = first['boundary']['le_source_witness']['cpu']
    location, selector_offset = _le_extent(binding['image'], recipe, cpu, start, length, observed['backing'])
    remote = session._stopped()
    if (remote.memory(start, length, space='physical', timeout_ms=session._remaining()) != raw
            or remote.memory(start, length, space='virtual', timeout_ms=session._remaining()) != raw):
        raise ValueError('LE capture changed during stopped readback')
    second = _observe(session)
    if (any(first[k] != second[k] for k in ('recipe', 'gdt_hex', 'binding', 'registers'))
            or first['boundary']['source_qualification'] != second['boundary']['source_qualification']
            or first['boundary']['le_source_witness'] != second['boundary']['le_source_witness']
            or binding is not session._le_source
            or not session._le_source_owner_valid(binding)):
        raise ValueError('LE source relation changed during capture')
    inputs = _qemu_input_hashes(session.metadata.get('runtime_inputs', {}))
    identity = dict(run=session.run_id, source_version=recipe['version'],
        source_version_sha256=recipe['version_sha256'], source_sha256=recipe['source_sha256'],
        arch=session.project.arch, bits=session.project.bits, cpu_mode='protected',
        captured_at=now(), backend='qemu-dos', backend_sha256=inputs.get('qemu_image'),
        runtime_inputs=inputs, layer_hashes={}, process_epoch=recipe['capture_epoch'])
    return {**observed, 'format': 'fdisbull-runtime-code-1', 'qemu_le_source_admission': LE_ADMISSION,
            'identity': identity, 'project_address': None,
            'capture_registers': first['registers'], 'execution_proven': False,
            'le_capture': dict(producer=_producer(), recipe=recipe, gdt_hex=first['gdt_hex'], boundary=first['boundary'],
                binding_artifact=first['binding'], source_location=location, selector_offset=selector_offset)}


def validate_qemu_le_capture(project, observation, run_metadata, *, run, version):
    """Replay a retained LE relation and validate its captured source extent offline."""
    from types import SimpleNamespace
    from .qemu_dos_le_checkpoint import FORMAT, SCOPE, _validate_source
    import hashlib
    try:
        identity = observation['identity']; proof = observation['le_capture']
        recipe = proof['recipe']; location = proof['source_location']
        selected = project.version(version)
        if (observation.get('format') != 'fdisbull-runtime-code-1'
                or observation.get('qemu_le_source_admission') != LE_ADMISSION
                or observation.get('space') != 'linear' or observation.get('view') not in ('ram', 'execute')
                or observation.get('active_layers') != [] or observation.get('execution_proven') is not False
                or identity['layer_hashes'] != {} or identity['run'] != run
                or identity['source_version'] != version or identity['source_version_sha256'] != selected['sha256']
                or identity['source_sha256'] != project.meta['source_sha256']
                or identity['arch'] != project.arch or identity['bits'] != project.bits
                or identity['backend'] != 'qemu-dos' or identity['cpu_mode'] != 'protected'
                or run_metadata['backend'] != 'qemu-dos'
                or run_metadata['source_sha256'] != identity['source_sha256']
                or run_metadata['version_sha256'] != identity['source_version_sha256']
                or identity['runtime_inputs'] != _qemu_input_hashes(run_metadata['runtime_inputs'])
                or identity['backend_sha256'] != identity['runtime_inputs']['qemu_image']
                or identity['process_epoch'] != recipe['capture_epoch'] or recipe['run'] != run):
            raise ValueError('LE capture source or producer identity differs')
        document = dict(format=FORMAT, source_view='embedded-le', source_scope=SCOPE,
            lifetime_qualified=False, source_binding_restored=False, producer=proof['producer'],
            source_sha256=identity['source_sha256'], version=version,
            version_sha256=identity['source_version_sha256'], run=run,
            capture_epoch=identity['process_epoch'], recipe=recipe, binding=proof['binding_artifact'],
            gdt_hex=proof['gdt_hex'], boundary=proof['boundary'], registers=observation['capture_registers'])
        session = SimpleNamespace(project=project, version=selected, metadata=run_metadata)
        validated = _validate_source(session, document)
        image = validated['image']
        cpu = proof['boundary']['le_source_witness']['cpu']
        raw = bytes.fromhex(observation['hex']); length = observation['length']
        start = int(observation['runtime_address'], 16)
        expected, selector_offset = _le_extent(image, recipe, cpu, start, length, observation['backing'])
        if (len(raw) != length or hashlib.sha256(raw).hexdigest() != observation['sha256']
                or location != expected or type(proof['selector_offset']) is not int
                or proof['selector_offset'] != selector_offset
                or observation['project_address'] is not None):
            raise ValueError('LE capture source extent differs')
        return dict(image=image, recipe=recipe, source_location=location, raw=raw,
                    cpu=cpu, gdt_hex=proof['gdt_hex'], selector_offset=selector_offset,
                    source_receipt_sequence=validated['source_receipt_sequence'])
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError, StopIteration) as error:
        raise ValueError('Malformed LE capture') from error


def qualify_qemu_source_capture(session, observed):
    """Admit only the original, unpaged DOS module and ordinary RAM backing."""
    try:
        return _qualify_qemu_source_capture(session, observed)
    except (KeyError, TypeError, ValueError, AttributeError):
        # A malformed or stale observation remains an ordinary opaque capture.
        return None


def _qemu_input_hashes(inputs):
    return {k: v['sha256'] for k, v in inputs.items()
            if isinstance(v, dict) and isinstance(v.get('sha256'), str)}


def validate_qemu_source_capture(observation, run_metadata):
    """Validate persisted source, producer, mapping and CPU facts without live state."""
    try:
        identity = observation['identity']
        mapping = identity['source_mapping']
        run_process = run_metadata['process']
        original = run_process['source_mapping']
        state = observation['capture_registers']['address_state']
        address = int(observation['project_address'], 16)
        runtime = int(observation['runtime_address'], 16)
        size = observation['length']
        delta = identity['delta']
        epoch = identity['process_epoch']
        prefix = identity['run'] + ':process:'
        if (observation.get('qemu_source_admission') != ADMISSION
                or observation['space'] != 'source' or identity['backend'] != 'qemu-dos'
                or run_metadata['backend'] != identity['backend']
                or run_metadata['runtime_profile'] != 'dos-exec-load-only-v1'
                or run_metadata['source_sha256'] != identity['source_sha256']
                or run_metadata['version_sha256'] != identity['source_version_sha256']
                or identity['runtime_inputs'] != _qemu_input_hashes(run_metadata['runtime_inputs'])
                or identity['backend_sha256'] != identity['runtime_inputs']['qemu_image']
                or identity['process_psp'] != run_process['psp_segment']
                or not isinstance(epoch, str) or not epoch.startswith(prefix)
                or not epoch[len(prefix):].isdigit() or int(epoch[len(prefix):]) < 1
                or any(mapping[k] != original[k] for k in STABLE_MAPPING)
                or mapping['expected_module_sha256'] != mapping['observed_module_sha256']
                or mapping['status'] != 'initial-load-verified' or mapping['live'] is not True
                or mapping['source_sha256'] != identity['source_sha256']):
            raise ValueError('QEMU capture source or producer identity mismatch')
        if (observation['capture_registers']['cpu_mode'] != 'real'
                or state['cpu_mode'] != 'real' or state['code_bits'] != 16
                or state['paging'] is not False or state['register_context_match'] is not True
                or state['machine_vcpus'] != 1):
            raise ValueError('QEMU capture stopped CPU mismatch')
        if (type(size) is not int or not 1 <= size <= 65536
                or len(bytes.fromhex(observation['hex'])) != size
                or type(delta) is not int or delta % 16
                or runtime-address != delta or mapping['runtime_base']-mapping['static_base'] != delta
                or int(identity['project_base'], 16) != mapping['static_base']
                or int(identity['runtime_base'], 16) != mapping['runtime_base']
                or not 0 <= runtime < runtime+size <= 0xa0000):
            raise ValueError('QEMU capture source range mismatch')
        extent, = mapping['live_ranges']
        if (extent['project_address'] != mapping['static_base'] or extent['runtime_address'] != mapping['runtime_base']
                or extent['length'] != mapping['module_size']
                or not extent['project_address'] <= address < address+size <= extent['project_address']+extent['length']):
            raise ValueError('QEMU capture source extent mismatch')
        cursor = runtime
        for span in observation['backing']:
            if int(span['physical_address'], 16) != cursor or type(span['length']) is not int or span['length'] <= 0:
                raise ValueError('QEMU capture backing mismatch')
            cursor += span['length']
        cs = int(observation['project_cs'], 16)
        rcs = int(observation['runtime_cs'], 16)
        ip = int(observation['instruction_pointer'], 16)
        if (cursor != runtime+size or cs != identity['project_cs'] or rcs != identity['runtime_cs']
                or not 0 <= cs <= 0xffff or not 0 <= rcs <= 0xffff
                or not 0 <= ip < ip+size <= 0x10000 or cs*16+ip != address
                or rcs*16+ip != runtime or (rcs-cs)*16 != delta):
            raise ValueError('QEMU capture selector or backing mismatch')
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError('Malformed QEMU source capture') from error


def _qualify_qemu_source_capture(session, observed):
    from .project import now
    process = getattr(session, '_process', None)
    if (observed.get('space') != 'source' or not isinstance(process, dict)
            or getattr(session, '_dos_task_monitor', None)
            or getattr(session, '_dos_task_binding', None)
            or session.project.meta.get('format') not in ('COM', 'MZ')):
        return None
    mapping = process.get('source_mapping', {})
    if (process.get('state') != 'active' or process.get('machine_closed')
            or not mapping.get('live') or mapping.get('status') != 'initial-load-verified'
            or mapping.get('source_sha256') != session.project.meta['source_sha256']
            or process.get('capture_epoch') != getattr(session, '_runtime_epoch', None)):
        return None
    from .qemu_dos_trace import _ownership
    _ownership(session, {'capture_epoch': process['capture_epoch']})
    registers = session.registers()
    delta = mapping['delta']
    runtime_cs = int(observed['runtime_cs'], 16)
    project_cs = int(observed['project_cs'], 16)
    inputs = session.metadata.get('runtime_inputs', {})
    identity = {'run': session.run_id, 'source_version': session.version['id'],
                'source_version_sha256': session.version['sha256'],
                'source_sha256': session.project.meta['source_sha256'],
                'arch': session.project.arch, 'bits': session.project.bits,
                'cpu_mode': 'real', 'captured_at': now(),
                'project_base': hex(mapping['static_base']), 'runtime_base': hex(mapping['runtime_base']),
                'delta': delta, 'runtime_cs': runtime_cs, 'project_cs': project_cs,
                'backend': session.metadata.get('backend', 'qemu-dos'),
                'backend_sha256': inputs.get('qemu_image', {}).get('sha256'),
                'runtime_inputs': _qemu_input_hashes(inputs),
                'layer_hashes': {i: session.project.debug_layer_info(i)['sha256'] for i in observed['active_layers']},
                'process_epoch': process['capture_epoch'],
                'source_mapping': {k: deepcopy(mapping[k])
                                   for k in (*STABLE_MAPPING, 'status', 'live', 'live_ranges')},
                'process_psp': process['psp_segment']}
    result = {**observed, 'format': 'fdisbull-runtime-code-1',
            'qemu_source_admission': ADMISSION,
            'identity': identity, 'capture_registers': registers, 'execution_proven': False}
    validate_qemu_source_capture(result, session.metadata)
    return result
