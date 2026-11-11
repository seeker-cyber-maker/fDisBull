"""Stopped native instrumentation sidecars for private DOS process checkpoints.

The machine snapshot carries guest device/CPU/RAM state. This record carries
the native observers' retained data and ownership. Restore creates new native
and host observation epochs; host monotonic synchronization is never replayed.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .dosbox_rpc import DebuggerError

FORMAT = 'fdisbull-instrumented-qemu-state-1'
PREFIX = 'x-fdisbull-instrumented-'
COMMANDS = frozenset(PREFIX + name for name in (
    'checkpoint-export', 'checkpoint-import', 'checkpoint-status',
    'snapshot-save', 'snapshot-load'))
MAX_BYTES = 48 * 1024 * 1024


def enabled(vm):
    return vm.machine_configuration.get('clock_profile', {}).get('profile') == 'virtual'


def require_commands(vm):
    if not COMMANDS <= vm.qmp_commands:
        raise ValueError('Instrumented checkpoints require the native instrumented checkpoint extension')


def preflight(session):
    if session._input_schedule_bound():
        raise ValueError('Resolve the native input schedule before checkpointing')
    sync = getattr(session.vm, '_clock_sync', None)
    if sync is not None and sync.get('state') != 'stopped':
        raise ValueError('Stop host clock synchronization before checkpointing')
    if enabled(session.vm):
        require_commands(session.vm)
        clock = session._clock_snapshot()
        if clock['virtual_clock']['native']['budget-state'] in ('armed', 'fired'):
            raise ValueError('Resolve the native clock budget before checkpointing')


def _decode(record):
    if (not isinstance(record, dict) or not isinstance(record.get('state'), str)
            or len(record['state'].encode()) > MAX_BYTES
            or hashlib.sha256(record['state'].encode()).hexdigest() != record.get('sha256')
            or type(record.get('icount')) is not int or not 0 <= record['icount'] < 1 << 64):
        raise ValueError('Invalid instrumented checkpoint state or hash')
    state = json.loads(record['state'])
    if (not isinstance(state, dict) or state.get('format') != FORMAT
            or type(state.get('virtual-ns')) is not int or not 0 <= state['virtual-ns'] < 1 << 63
            or type(state.get('source-epoch')) is not int or not 0 < state['source-epoch'] < 1 << 64
            or any(not isinstance(state.get(key), dict) for key in ('clock', 'audio', 'display', 'retrace'))):
        raise ValueError('Invalid instrumented checkpoint envelope')
    return state


def validate(vm, record):
    if not enabled(vm):
        if record is not None:
            raise ValueError('Standard checkpoint unexpectedly carries instrumented state')
        return None
    require_commands(vm)
    return _decode(record)


def capture(session):
    if not enabled(session.vm):
        return None, None
    before = session._clock_snapshot()
    try:
        value = session.vm.qmp.call(PREFIX + 'checkpoint-export', max_reply_bytes=64 * 1024 * 1024)
    except DebuggerError as error:
        # The native contract performs all eligibility checks before token
        # issuance. A complete explicit refusal leaves that stopped owner live.
        if str(error).startswith('QMP ' + PREFIX + 'checkpoint-export: '):
            raise ValueError('Native instrumented checkpoint refused: ' + str(error)) from error
        session.close()
        raise
    except BaseException:
        session.close()
        raise
    try:
        if (not isinstance(value, dict) or not isinstance(value.get('token'), str)
                or not 1 <= len(value['token']) <= 128):
            raise DebuggerError('Invalid native instrumented checkpoint export token')
        record = {key: value.get(key) for key in ('state', 'sha256')}
        record['icount'] = before['counter']['value']
        state = _decode(record)
        if (state['virtual-ns'] != before['virtual_ns']
                or state['source-epoch'] != before['virtual_clock']['native']['epoch']):
            raise DebuggerError('Native instrumentation changed during checkpoint capture')
        return record, value['token']
    except BaseException:
        session.close()
        raise


def verify_saved(session, record):
    if record is not None:
        after, _ = capture(session)
        if after != record:
            raise DebuggerError('Native instrumentation changed while saving the checkpoint')


def _logical(value):
    """Remove only the native owner identities deliberately rebound at import."""
    value = deepcopy(value)
    value.pop('source-epoch', None)
    value['clock'].pop('epoch', None)
    # A fresh local-load process can retain prelaunch/paused rather than the
    # source debugger stop class. Both are independently validated as stopped.
    value['clock'].pop('status', None)
    if isinstance(value['clock'].get('info'), dict):
        value['clock']['info'].pop('epoch', None)
    for channel in ('audio', 'display', 'retrace'):
        info = value[channel].get('info')
        if isinstance(info, dict):
            info.pop('epoch', None)
            if channel in ('audio', 'display'):
                info.pop('token', None)
    publication = value['display'].get('published-configuration')
    if isinstance(publication, dict):
        publication.pop('epoch', None)
    configuration = value['retrace'].get('configuration')
    if isinstance(configuration, dict):
        configuration.pop('epoch', None)
    return value


def restore(vm, record):
    saved = validate(vm, record)
    if saved is None:
        return None
    result = vm.qmp.call(PREFIX + 'checkpoint-import', {'state': record['state']})
    epoch = result.get('new-epoch') if isinstance(result, dict) else None
    if (type(epoch) is not int or not 0 < epoch < 1 << 64
            or epoch == saved['source-epoch'] or result.get('virtual-ns') != saved['virtual-ns']):
        raise DebuggerError('Invalid restored native instrumentation ownership')
    if vm.qmp.call(PREFIX + 'checkpoint-status') != result:
        raise DebuggerError('Restored instrumentation ownership changed')

    # Startup admissions describe the fresh, pre-load process. None of their
    # monotone frontiers can qualify the restored machine's earlier history.
    for key in ('_native_clock_epoch', '_native_clock_last_ns', '_clock_observation_state',
                '_active_clock_budget', '_clock_sync', '_audio_last', '_audio_export',
                '_display_last', '_display_probe_samples', '_display_export', '_retrace_last',
                '_vga_configuration_last', '_vga_publication_last'):
        vm.__dict__.pop(key, None)
    from .qemu_clock import _native_clock
    native = _native_clock(vm, vm.qmp.call('x-fdisbull-query-clock'))
    if (native['epoch'] != epoch or native['virtual-ns'] != saved['virtual-ns']
            or native['budget-state'] in ('armed', 'fired', 'invalidated')):
        raise DebuggerError('Restored native clock differs from its checkpoint')
    vm.native_clock_admission = native
    counter = vm.qmp.call('query-replay')
    if counter.get('mode') != 'none' or counter.get('icount') != record['icount']:
        raise DebuggerError('Restored native instruction counter differs from its checkpoint')
    clock = dict(virtual_ns=native['virtual-ns'], virtual_clock=dict(native=native))
    windows = {}
    if vm.machine_configuration.get('audio_profile', {}).get('profile') == 'pc-speaker':
        from .qemu_audio import _native_audio
        vm._audio_token = result.get('audio-token') or None
        actual = _native_audio(vm, vm.qmp.call('x-fdisbull-query-audio'), clock, token=vm._audio_token)
        if actual['state'] != 'idle':
            if vm._audio_token == saved['audio']['info']['token']:
                raise DebuggerError('Restored audio reused the former owner token')
            windows['audio'] = dict(old=saved['audio']['info']['token'], new=vm._audio_token)
    from .qemu_display import _native_display
    vm._display_token = result.get('display-token') or None
    actual = _native_display(vm, vm.qmp.call('x-fdisbull-query-display'), clock, token=vm._display_token)
    if actual['state'] != 'idle':
        if vm._display_token == saved['display']['info']['token']:
            raise DebuggerError('Restored display reused the former owner token')
        windows['display'] = dict(old=saved['display']['info']['token'], new=vm._display_token)
    if vm.machine_configuration.get('retrace_profile', {}).get('profile') == 'precise':
        from .qemu_retrace import admit_retrace
        retrace = admit_retrace(vm)
        if result.get('retrace-device') != retrace['device'] or retrace['device'] != saved['retrace']['device-path']:
            raise DebuggerError('Restored retrace device differs from its checkpoint')

    # Read back the retained bytes, native timer phase, configuration and
    # callback frontiers through the same bounded native serializer.
    current = vm.qmp.call(PREFIX + 'checkpoint-export', max_reply_bytes=64 * 1024 * 1024)
    current = dict(state=current.get('state'), sha256=current.get('sha256'), icount=record['icount'])
    if _logical(_decode(current)) != _logical(saved):
        raise DebuggerError('Restored native instrumentation data differs from its checkpoint')
    return dict(format=FORMAT, source_epoch=saved['source-epoch'], native_epoch=epoch,
                virtual_ns=saved['virtual-ns'], windows=windows,
                host_clock_sync_restored=False)
