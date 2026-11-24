"""Bounded QEMU DOS source capture and offline admission."""
from copy import deepcopy


ADMISSION = 'original-real16-ordinary-ram-v1'
STABLE_MAPPING = ('static_base', 'runtime_base', 'delta', 'module_size', 'load_segment',
                  'source_sha256', 'expected_module_sha256', 'observed_module_sha256')


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
