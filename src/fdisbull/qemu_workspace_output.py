"""Caller-attested output capture for one qualified minimal FreeDOS runtime.

SFT/buffer observations are conservative guards, not create/close/flush proofs.
The qualified image identifies initial boot bytes, not adversarial kernel RAM.
"""
from copy import deepcopy
import hashlib
import os

from .freedos_runtime import FORMAT as RUNTIME_FORMAT, VERSION, LOCK
from .dos_workspace_guest import observe_guest_files
from .qemu_workspace import _dos_path, _runtime_component, _json, _sha, _generation_receipt, _seal_workspace

FORMAT = 'fdisbull-qemu-workspace-output-1'
KIND = 'workspace-output-receipt'
# Exact component-04 image independently booted in the local workspace campaigns.
# Rebuilt images need their own layout/runtime qualification before admission.
QUALIFIED_IMAGE_SHA256 = 'badc71221f90a0ae823b23ee45b9372d8f6e4b819fecd301fed0ee4b7d0dadf2'


def qualified_runtime(runtime):
    if (not isinstance(runtime, dict) or runtime.get('format') != RUNTIME_FORMAT
            or runtime.get('version') != VERSION or not isinstance(runtime.get('files'), dict)):
        return False
    expected = {'system.img': QUALIFIED_IMAGE_SHA256,
                'source/kernel.zip': LOCK['kernel'], 'source/freecom.zip': LOCK['freecom']}
    return all(isinstance(runtime['files'].get(k), dict)
               and runtime['files'][k].get('sha256') == v for k, v in expected.items())


def _admit_runtime(session):
    state = getattr(session, '_dos_workspace', None)
    if (not isinstance(state, dict) or state.get('mode') != 'checkpointed'
            or state.get('version') != session.version['id']
            or state.get('source_sha256') != session.metadata.get('source_sha256')):
        raise ValueError('Output capture requires the current checkpointed source workspace')
    runtime = _runtime_component(session)
    if (runtime != state.get('runtime_descriptor')
            or _sha(_json(runtime)) != state.get('runtime_component_sha256')):
        raise ValueError('Output capture requires the qualified minimal FreeDOS runtime')
    if not qualified_runtime(runtime):
        raise ValueError('Output capture runtime image has not been qualified')
    return state


def _read_physical(session, address, length):
    if (type(address) is not int or type(length) is not int or length <= 0
            or address < 0 or address + length > 0xa0000):
        raise ValueError('Output file observation requires unwrapped conventional physical RAM')
    result = session.vm.debugger().memory(address, length, space='physical',
                                        timeout_ms=session._history_remaining_ms())
    if not isinstance(result, bytes) or len(result) != length:
        raise ValueError('Output file observation returned incomplete physical RAM')
    return result


def _context(session):
    state = _admit_runtime(session)
    from .qemu_input import require_released_machine_input
    require_released_machine_input(session.vm)
    if (getattr(session.vm, '_active_clock_budget', None) is not None
            or getattr(session.vm, '_frame_key_owner', None) is not None
            or session._input_schedule_bound()):
        raise ValueError('Resolve scheduled input, owned frame keys and clock budgets before output capture')
    if (session.project.db.in_transaction or session.closed
            or getattr(session, '_process', {}).get('state') != 'active'):
        raise ValueError('Output capture requires an active owned process outside a transaction')
    if (getattr(session, '_dos_task_binding', None) is not None
            or getattr(session, '_dos_task_views', None)
            or session.layers().get('active')
            or getattr(session.vm, '_clock_sync', None) is not None):
        raise ValueError('Output capture requires no active layers, task views or clock sync')
    session._stopped()
    registers = session.registers()
    address = registers.get('address_state', {})
    control = address.get('control', {})
    cr0 = control.get('CR0', control.get('cr0'))
    try:
        cr0 = int(cr0, 0) if isinstance(cr0, str) else cr0
    except ValueError:
        cr0 = None
    if (registers.get('cpu_mode') != 'real' or address.get('paging') is not False
            or address.get('register_context_match') is not True
            or address.get('machine_vcpus') != 1 or address.get('code_bits') != 16
            or type(address.get('a20')) is not bool or type(cr0) is not int or cr0 & 1):
        raise ValueError('Output capture requires a verified real-mode unpaged single CPU')
    ready = session._ready
    pointers = {k: ready.get(k) for k in
                ('list_of_lists_segment', 'list_of_lists_offset', 'child_psp')}
    if any(type(v) is not int for v in pointers.values()):
        raise ValueError('Output capture requires the owned DOS process pointers')
    nonce = getattr(session, '_nonce', None)
    if not isinstance(nonce, bytes) or len(nonce) != 16:
        raise ValueError('Output capture process nonce is unavailable')
    epoch = getattr(session, '_runtime_epoch', None)
    if not isinstance(epoch, str) or not epoch:
        raise ValueError('Output capture runtime epoch is unavailable')
    return dict(run=session.run_id, epoch=epoch,
                source_sha256=state['source_sha256'], version=session.version['id'],
                version_sha256=session.metadata.get('version_sha256'),
                runtime_component_sha256=state['runtime_component_sha256'],
                process_nonce_sha256=hashlib.sha256(nonce).hexdigest(),
                process=pointers, cpu={k: deepcopy(registers.get(k)) for k in
                                      ('registers', 'instruction_pointer', 'linear_pc',
                                       'cpu_mode', 'address_state')})


def _boundary(session):
    before = _context(session)
    p = before['process']
    files = observe_guest_files(lambda a, n: _read_physical(session, a, n),
                               p['list_of_lists_segment'], p['list_of_lists_offset'], p['child_psp'])
    if before != _context(session):
        raise ValueError('Output capture CPU/process context changed during observation')
    if files['ordinary_open_count'] or files['dirty_buffer_count']:
        raise ValueError('Output capture requires no ordinary open files or dirty DOS buffers')
    return dict(context=before, files=files)


def _select_output(store, generation, path):
    loaded = store.load(generation)
    manifest = loaded['manifest']
    entry = next((item for item in loaded['entries'] if item['dos_path'] == path), None)
    if path in manifest['protected_dos_paths'] or (entry and
            entry['path'].casefold() in manifest['protected_paths']):
        raise ValueError('Output capture cannot select an original or protected host path')
    if entry is None or entry['type'] != 'file':
        raise ValueError('Output capture requires a file in the sealed guest generation')
    return entry


def save_output(session, path, new_destination, *, closed_and_flushed=False):
    if closed_and_flushed is not True:
        raise ValueError('Output capture requires explicit closed_and_flushed=True caller attestation')
    path = _dos_path(path)
    try:
        destination = os.fspath(new_destination)
    except TypeError:
        raise ValueError('Output capture requires an absolute new host destination') from None
    if (not isinstance(destination, str) or not destination or '\0' in destination
            or not os.path.isabs(destination)):
        raise ValueError('Output capture requires an absolute new host destination')
    store = session._workspace_store()
    state = _admit_runtime(session)
    current = store.load(state['generation']['artifact'])['manifest']
    if path in current['protected_dos_paths']:
        raise ValueError('Output capture cannot select an original or protected host path')
    before = _boundary(session)
    # The ordinary full-checkpoint path owns uncertain native-effect handling.
    session._history_remaining_ms()
    sealed = _seal_workspace(session)
    capture_effects = dict(format=FORMAT, checkpoint=sealed['checkpoint'],
                           generation=deepcopy(sealed['workspace']['generation']),
                           export_published=False, receipt_persisted=False)
    try:
        after = _boundary(session)
    except BaseException as error:
        error.result = capture_effects
        session.close()
        raise
    if after != before:
        session.close()
        error = ValueError('Output file state or CPU/process identity changed during checkpoint capture')
        error.result = capture_effects
        raise error
    generation = sealed['workspace']['generation']['artifact']
    try:
        entry = _select_output(store, generation, path)
        checkpoint = session.project.db.execute('SELECT sha256 FROM debug_artifacts WHERE id=?',
                                               (sealed['checkpoint'],)).fetchone()
        if checkpoint is None:
            raise ValueError('Output checkpoint receipt is missing')
        result = dict(format=FORMAT, provenance='caller-attested', closed_and_flushed_attested=True,
                      guest_create_provenance=False, path=path, source_origin=entry['origin'],
                      size=entry['size'], sha256=entry['sha256'],
                      checkpoint=dict(artifact=sealed['checkpoint'], sha256=checkpoint['sha256']),
                      generation=_generation_receipt(store, generation),
                      context=before['context'], file_state_before=before['files'],
                      file_state_after=after['files'],
                      scope='Trusted qualified initial runtime; stopped file/buffer guards plus caller attestation. '
                            'No guest-create, automatic flush, sharing, locks or general coherence proof. '
                            'The physical copy is independent of the guest rewind cursor.')
    except BaseException as error:
        error.result = capture_effects
        raise
    try:
        session._history_remaining_ms()
        result['export'] = store.export_file(generation, path, destination)
        session._history_remaining_ms()
        encoded = _json(result)
        artifact = session._artifact('workspace-output.json', KIND, encoded,
                                     dict(format=FORMAT, generation=generation, sha256=_sha(encoded)))
        if artifact.get('sha256') != _sha(encoded):
            raise ValueError('Output capture receipt readback differs')
        result['artifact'] = artifact['artifact']
        return result
    except BaseException as error:
        partial_export = getattr(error, 'result', None)
        if 'export' not in result and partial_export is not None:
            result['export'] = deepcopy(partial_export)
        error.result = dict(**result, receipt_persisted=False, publication='do not replay')
        if 'export' in result:
            session.close()
        raise
