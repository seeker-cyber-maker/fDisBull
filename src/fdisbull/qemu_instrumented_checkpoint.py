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
from .qemu_retrace import (VBE101_DISPLAY_START_FIELD, VBE101_PANNING_FIELD, VBE101_TIMING_FIELD,
                           validate_retrace_snapshot)
from .qemu_video_checkpoint import (FORMAT as VIDEO_FRAME_FORMAT, LATCH_MODEL, MODEL, MODE13_MODEL,
    OVERLAP_MODEL, VGA480_FLIP_MODEL, VGA480_FLIP_PROFILE, VGA480_FRAME_SIZE, VGA480_MODEL,
    VGA480_PALETTE_MODEL, VGA480_PALETTE_PROFILE,
    VGA480_PAN_MODEL, VGA480_PAN_PROFILE, VGA480_SYNC_MODEL, VGA480_SYNC_PROFILE, VGA480_XY_MODEL,
    VGA480_XY_PROFILE, VBE101_ORIGIN_FIELD, VBE101_PEL_FIELD, VBE101_PITCH_FIELD,
    clear_video_checkpoint_caches, logical_video_checkpoint,
    restored_video_info, validate_video_checkpoint, vbe101_frame_fields, video_model)

FORMAT = 'fdisbull-instrumented-qemu-state-1'
FRAME_KEYS_FORMAT = 'fdisbull-instrumented-qemu-state-2'
FRAME_KEY_REPEAT_FORMAT = 'fdisbull-instrumented-qemu-state-4'
VIDEO_PHASE_FORMAT = 'fdisbull-instrumented-qemu-state-5'
VIDEO_LATCH_FORMAT = 'fdisbull-instrumented-qemu-state-6'
VIDEO_OVERLAP_FORMAT = 'fdisbull-instrumented-qemu-state-7'
VIDEO_VGA480_FORMAT = 'fdisbull-instrumented-qemu-state-8'
VIDEO_VGA480_SYNC_FORMAT = 'fdisbull-instrumented-qemu-state-9'
VIDEO_VGA480_FLIP_FORMAT = 'fdisbull-instrumented-qemu-state-10'
VIDEO_VGA480_PAN_FORMAT = 'fdisbull-instrumented-qemu-state-11'
VIDEO_VGA480_XY_FORMAT = 'fdisbull-instrumented-qemu-state-12'
VIDEO_VGA480_PALETTE_FORMAT = 'fdisbull-instrumented-qemu-state-13'
_VIDEO_MODEL = {
    VIDEO_FRAME_FORMAT: MODEL, FRAME_KEY_REPEAT_FORMAT: MODEL,
    VIDEO_PHASE_FORMAT: MODE13_MODEL, VIDEO_LATCH_FORMAT: LATCH_MODEL, VIDEO_OVERLAP_FORMAT: OVERLAP_MODEL,
    VIDEO_VGA480_FORMAT: VGA480_MODEL, VIDEO_VGA480_SYNC_FORMAT: VGA480_SYNC_MODEL,
    VIDEO_VGA480_FLIP_FORMAT: VGA480_FLIP_MODEL,
    VIDEO_VGA480_PAN_FORMAT: VGA480_PAN_MODEL,
    VIDEO_VGA480_XY_FORMAT: VGA480_XY_MODEL,
    VIDEO_VGA480_PALETTE_FORMAT: VGA480_PALETTE_MODEL,
}
_VBE101_RETRACE_PROFILES = {VIDEO_VGA480_SYNC_FORMAT: VGA480_SYNC_PROFILE,
                            VIDEO_VGA480_FLIP_FORMAT: VGA480_FLIP_PROFILE,
                            VIDEO_VGA480_PAN_FORMAT: VGA480_PAN_PROFILE,
                            VIDEO_VGA480_XY_FORMAT: VGA480_XY_PROFILE,
                            VIDEO_VGA480_PALETTE_FORMAT: VGA480_PALETTE_PROFILE}
_VIDEO_FORMATS = frozenset(_VIDEO_MODEL)
_REPEAT_FORMATS = _VIDEO_FORMATS - {VIDEO_FRAME_FORMAT}
RESTORE_RECEIPT_FORMATS = _VIDEO_FORMATS | {FORMAT}
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
    from .qemu_video_control import require_no_video_frame_fence
    require_no_video_frame_fence(session.vm, 'instrumented checkpointing')
    from .qemu_step_over import require_no_step_over
    require_no_step_over(session.vm, 'instrumented checkpointing')
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


def _validate_vga_census(state, video):
    info = video['info']
    if not {'page-latch-offset-ns', 'scanout-layout'}.intersection(info):
        return
    census = state['retrace'].get('configuration')
    generation = census.get('configuration-generation') if type(census) is dict else None
    selected = info.get('pending-page-latch') or info.get('frame', {}).get('page-latch')
    latest = selected['configuration-generation'] if selected else video['configuration-generation']
    if type(generation) is not int or not latest <= generation < 1 << 64:
        raise ValueError('Source video configuration is ahead of the saved VGA census')


def _validate_vbe101_display_census(state, retrace):
    from .qemu_vga_configuration import validate_vga_configuration_snapshot
    raw = validate_vga_configuration_snapshot(state['retrace'].get('configuration'),
        epoch=state['source-epoch'], virtual_ns=state['virtual-ns'], device=retrace)['raw']
    starts = retrace[VBE101_DISPLAY_START_FIELD]
    panning = retrace.get(VBE101_PANNING_FIELD)
    width, height = VGA480_FRAME_SIZE
    pitch = panning['pitch-bytes'] if panning is not None else width
    x, y = raw['vbe'][8:10]
    palette = state['format'] == VIDEO_VGA480_PALETTE_FORMAT
    x_fits = x == 0 if palette and pitch < width else x + width <= pitch
    pel = panning['programmed-pel'] if panning is not None else 0
    programmed = starts['programmed-origin-bytes']
    if (raw['vbe'][1:5] != [width, height, 8, retrace['raw']['vbe-enable']]
            or raw['vbe'][6] != pitch or raw['vbe-line-offset'] != pitch
            or not x_fits):
        raise ValueError('VBE 101h display layout differs from the saved VGA census')
    if raw['vbe-start-address'] * 4 != programmed or y * pitch + x != programmed + pel:
        raise ValueError('VBE 101h programmed display start differs from the saved VGA census')
    limit = min(raw['vram-size'], raw['vbe-size'])
    if (state['format'] in (VIDEO_VGA480_XY_FORMAT, VIDEO_VGA480_PALETTE_FORMAT)
            and programmed + pel + (height - 1) * pitch + max(pitch, width) > limit):
        raise ValueError('VBE 101h programmed display start exceeds the saved backing span')
    origins = [programmed + pel,
               starts['active-origin-bytes'] + (panning['active-pel'] if panning is not None else 0)]
    video = state['video-frame']
    info = video['info']
    if palette and (raw['dac-8bit'] != bool(raw['vbe'][4] & 0x20)
            or (info.get('scanout-layout') == 'vbe-banked-101'
                and video['dac-8bit'] != raw['dac-8bit'])):
        raise ValueError('VBE 101h DAC width differs from the saved VGA census')
    frame = info.get('frame', {})
    if VBE101_ORIGIN_FIELD in frame:
        if VBE101_PITCH_FIELD in frame and frame[VBE101_PITCH_FIELD] != pitch:
            raise ValueError('VBE 101h retained raster pitch differs from the saved VGA census')
        origins.append(frame[VBE101_ORIGIN_FIELD] + frame.get(VBE101_PEL_FIELD, 0))
    if max(origins) + (height - 1) * pitch + width > limit:
        raise ValueError('VBE 101h display start exceeds the saved VGA memory window')
    if vbe101_frame_fields(info['model'], info.get('scanout-layout')):
        timing = retrace[VBE101_TIMING_FIELD]
        line = timing['line-period-ns']
        if video['line-period-ns'] != line or video['period-ns'] != line * timing['lines-per-frame']:
            raise ValueError('VBE 101h scanout differs from the saved retrace cadence')


def _decode(record):
    if (not isinstance(record, dict) or not isinstance(record.get('state'), str)
            or len(record['state'].encode()) > MAX_BYTES
            or hashlib.sha256(record['state'].encode()).hexdigest() != record.get('sha256')
            or type(record.get('icount')) is not int or not 0 <= record['icount'] < 1 << 64):
        raise ValueError('Invalid instrumented checkpoint state or hash')
    state = json.loads(record['state'])
    if (not isinstance(state, dict) or type(state.get('format')) is not str
            or state['format'] not in _VIDEO_FORMATS | {FORMAT, FRAME_KEYS_FORMAT}
            or type(state.get('virtual-ns')) is not int or not 0 <= state['virtual-ns'] < 1 << 63
            or type(state.get('source-epoch')) is not int or not 0 < state['source-epoch'] < 1 << 64
            or any(not isinstance(state.get(key), dict) for key in ('clock', 'audio', 'display', 'retrace'))):
        raise ValueError('Invalid instrumented checkpoint envelope')
    if state['format'] in _VIDEO_FORMATS | {FRAME_KEYS_FORMAT}:
        from .qemu_frame_keys import validate_frame_key_checkpoint
        validate_frame_key_checkpoint(state.get('frame-keys'), epoch=state['source-epoch'])
    elif 'frame-keys' in state:
        raise ValueError('Frame key checkpoint requires instrumented format 2')
    if state['format'] in _VIDEO_FORMATS:
        fields = {'format', 'virtual-ns', 'source-epoch', 'clock', 'audio',
                  'display', 'retrace', 'frame-keys', 'video-frame'}
        if state['format'] in _REPEAT_FORMATS:
            fields.add('frame-key-repeat')
        if set(state) != fields:
            raise ValueError('Invalid instrumented source checkpoint envelope fields')
        video = validate_video_checkpoint(state['video-frame'], epoch=state['source-epoch'],
                                          virtual_ns=state['virtual-ns'])
        if video['info']['model'] != _VIDEO_MODEL[state['format']]:
            raise ValueError('Source video model differs from its checkpoint format')
        if state['format'] in (*_VBE101_RETRACE_PROFILES, VIDEO_LATCH_FORMAT, VIDEO_VGA480_FORMAT):
            _validate_vga_census(state, video)
    elif 'video-frame' in state or 'frame-key-repeat' in state:
        raise ValueError('Source video and key repeat require their instrumented checkpoint formats')
    retrace = state['retrace'].get('info')
    fields = {VBE101_TIMING_FIELD, VBE101_DISPLAY_START_FIELD, VBE101_PANNING_FIELD}
    if isinstance(retrace, dict) and fields.intersection(retrace):
        profile = _VBE101_RETRACE_PROFILES.get(state['format'])
        if profile is None:
            raise ValueError('VBE 101h retrace timing requires instrumented checkpoint format 9 through 13')
        validate_retrace_snapshot(retrace, epoch=state['source-epoch'],
                                  virtual_ns=state['virtual-ns'], source_profile=profile)
        if VBE101_DISPLAY_START_FIELD in retrace:
            _validate_vbe101_display_census(state, retrace)
    if state['format'] in (VIDEO_VGA480_FLIP_FORMAT, VIDEO_VGA480_PAN_FORMAT,
                           VIDEO_VGA480_XY_FORMAT, VIDEO_VGA480_PALETTE_FORMAT):
        info = video['info']
        if (info['state'] == 'observing' and vbe101_frame_fields(info['model'], info.get('scanout-layout'))
                and (not isinstance(retrace, dict) or VBE101_DISPLAY_START_FIELD not in retrace)):
            raise ValueError('Banked VBE 101h scanout lacks its checkpoint display starts')
    if state['format'] in _REPEAT_FORMATS:
        from .qemu_frame_keys import validate_frame_key_repeat
        try:
            validate_frame_key_repeat(state['frame-key-repeat'], held=state['frame-keys']['held'])
        except DebuggerError as error:
            raise ValueError('Invalid checkpoint frame key repeat proof') from error
    return state


def validate(vm, record):
    if not enabled(vm):
        if record is not None:
            raise ValueError('Standard checkpoint unexpectedly carries instrumented state')
        return None
    require_commands(vm)
    state = _decode(record)
    if state['format'] in _VIDEO_FORMATS and not {
            'x-fdisbull-query-video-frame', 'x-fdisbull-query-frame-keys'} <= vm.qmp_commands:
        raise ValueError('Source video checkpoint requires native video and key ownership queries')
    _validate_launch_format(vm, state)
    if vm.machine_configuration.get('audio_profile', {}).get('profile') in ('pc-speaker', 'sb16', 'sb16-opl'):
        from .qemu_audio import audio_capture_format, require_audio_capture_format
        require_audio_capture_format(vm, audio_capture_format(state['audio'].get('info')))
    return state


def _validate_launch_format(vm, state):
    from .qemu_frame_keys import REPEAT_QUERY
    if (state['format'] in _REPEAT_FORMATS) != (REPEAT_QUERY in vm.qmp_commands):
        raise ValueError('Checkpoint format differs from the native frame key repeat capability')
    if (state['format'] in _REPEAT_FORMATS and state['frame-key-repeat'].get('profile')
            != vm.machine_configuration.get('frame_key_repeat_profile')):
        raise ValueError('Checkpoint frame key repeat profile differs from launch')
    if _VIDEO_MODEL.get(state['format'], MODEL) != video_model(vm.machine_configuration):
        raise ValueError('Checkpoint source video timing profile differs from launch')


def _close_capture_failure(session, error):
    session.vm._fdisbull_control_quarantine = 'uncertain instrumented checkpoint capture'
    try:
        session.close()
    except BaseException as cleanup_error:
        error.machine_cleanup_error = type(cleanup_error).__name__


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
        _close_capture_failure(session, error)
        raise
    except BaseException as error:
        _close_capture_failure(session, error)
        raise
    try:
        if (not isinstance(value, dict) or not isinstance(value.get('token'), str)
                or not 1 <= len(value['token']) <= 128):
            raise DebuggerError('Invalid native instrumented checkpoint export token')
        record = {key: value.get(key) for key in ('state', 'sha256')}
        record['icount'] = before['counter']['value']
        state = _decode(record)
        _validate_launch_format(session.vm, state)
        if (state['virtual-ns'] != before['virtual_ns']
                or state['source-epoch'] != before['virtual_clock']['native']['epoch']):
            raise DebuggerError('Native instrumentation changed during checkpoint capture')
        if state['format'] in _REPEAT_FORMATS:
            _verify_key_repeat(session.vm, state)
        return record, value['token']
    except BaseException as error:
        _close_capture_failure(session, error)
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
    if isinstance(value.get('frame-keys'), dict):
        value['frame-keys'].pop('source-epoch', None)
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
    if 'video-frame' in value:
        value['video-frame'] = logical_video_checkpoint(value['video-frame'])
    return value


def _empty_key_owner(state):
    return (isinstance(state, dict) and state.get('active') is False
            and state.get('generation') == 0 and state.get('accepted-edges') == 0
            and state.get('held') == [] and state.get('modifier-mask') == 0)


def _readback_view(saved, current, *, empty_native_key_owner):
    """Project only validated neutral extensions onto an older saved format."""
    if current['format'] == saved['format']:
        return current
    value = deepcopy(current)
    if saved['format'] in (FORMAT, FRAME_KEYS_FORMAT) and value['format'] == VIDEO_FRAME_FORMAT:
        if value['video-frame']['info']['state'] != 'idle':
            raise DebuggerError('Legacy instrumentation unexpectedly restored a source video owner')
        del value['video-frame']
        value['format'] = FRAME_KEYS_FORMAT
    if saved['format'] == FORMAT and value['format'] == FRAME_KEYS_FORMAT:
        if not _empty_key_owner(value['frame-keys']):
            raise DebuggerError('Legacy instrumentation unexpectedly restored a frame key owner')
        if empty_native_key_owner is not True:
            raise DebuggerError('Legacy instrumentation lacks independent empty frame key owner proof')
        del value['frame-keys']
        value['format'] = FORMAT
    if value['format'] != saved['format']:
        raise DebuggerError('Restored instrumentation readback format differs')
    return value


def restore(vm, record):
    saved = validate(vm, record)
    if saved is None:
        return None
    # A destination's startup source history cannot qualify restored history.
    # Keep pre-dispatch validation outside the uncertain-import cleanup path.
    clear_video_checkpoint_caches(vm)
    try:
        return _restore(vm, record, saved)
    except BaseException as error:
        clear_video_checkpoint_caches(vm)
        vm._fdisbull_control_quarantine = 'uncertain instrumented checkpoint restore'
        try:
            vm.close()
        except BaseException as cleanup_error:
            error.machine_cleanup_error = type(cleanup_error).__name__
        clear_video_checkpoint_caches(vm)
        raise


def _verify_key_repeat(vm, state):
    from .qemu_frame_keys import REPEAT_QUERY, validate_frame_key_repeat
    actual = validate_frame_key_repeat(vm.qmp.call(REPEAT_QUERY), held=state['frame-keys']['held'])
    if (actual != state['frame-key-repeat']
            or actual.get('profile') != vm.machine_configuration.get('frame_key_repeat_profile')):
        raise DebuggerError('Native frame key repeat readback differs from its checkpoint or launch profile')


def _validate_restore_receipt(result, saved):
    """Validate each native reply before comparing independent ownership."""
    epoch = result.get('new-epoch') if isinstance(result, dict) else None
    if (type(epoch) is not int or not 0 < epoch < 1 << 64
            or epoch == saved['source-epoch'] or result.get('virtual-ns') != saved['virtual-ns']):
        raise DebuggerError('Invalid restored native instrumentation ownership')
    source = saved.get('video-frame')
    if source is not None:
        fields = {'format', 'virtual-ns', 'new-epoch', 'frame-key-generation',
                  'video-frame-generation'}
        optional = {'audio-token', 'display-token', 'retrace-device',
                    'frame-key-token', 'video-frame-token'}
        if (not fields <= result.keys() or result.keys() - fields - optional
                or result['format'] != saved['format']
                or type(result['virtual-ns']) is not int
                or type(result['frame-key-generation']) is not int
                or result['frame-key-generation'] != saved['frame-keys']['generation']
                or type(result['video-frame-generation']) is not int
                or result['video-frame-generation'] != source['info']['stream-generation']
                or ('frame-key-token' in result) != saved['frame-keys']['active']
                or ('video-frame-token' in result) != (source['info']['state'] != 'idle')
                or any(type(result[key]) is not str for key in optional & result.keys())):
            raise DebuggerError('Invalid restored source video ownership receipt')
    return epoch


def _restore(vm, record, saved):
    result = vm.qmp.call(PREFIX + 'checkpoint-import', {'state': record['state']})
    epoch = _validate_restore_receipt(result, saved)
    status = vm.qmp.call(PREFIX + 'checkpoint-status')
    _validate_restore_receipt(status, saved)
    if status != result:
        raise DebuggerError('Restored instrumentation ownership changed')
    source = saved.get('video-frame')

    # Startup admissions describe the fresh, pre-load process. None of their
    # monotone frontiers can qualify the restored machine's earlier history.
    for key in ('_native_clock_epoch', '_native_clock_last_ns', '_clock_observation_state',
                '_active_clock_budget', '_clock_sync', '_audio_last', '_audio_export', '_audio_capture_format',
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
    key_state = saved.get('frame-keys')
    empty_native_key_owner = False
    if key_state is not None or 'x-fdisbull-query-frame-keys' in vm.qmp_commands:
        from .qemu_frame_keys import validate_frame_key_state, adopt_frame_keys
        current_keys = validate_frame_key_state(vm.qmp.call('x-fdisbull-query-frame-keys'), epoch=epoch)
        if current_keys['repeat-supported'] != (saved['format'] in _REPEAT_FORMATS):
            raise DebuggerError('Restored frame key repeat capability differs from its checkpoint')
        if key_state is None:
            if (not _empty_key_owner(current_keys) or current_keys['foreign-held']
                    or 'token' in current_keys):
                raise DebuggerError('Legacy instrumentation unexpectedly restored a frame key owner')
            empty_native_key_owner = True
        elif (current_keys['active'] != key_state['active']
                or current_keys['generation'] != key_state['generation']
                or current_keys['accepted-edges'] != key_state['accepted-edges']
                or current_keys['held'] != key_state['held']
                or key_state['active'] and (result.get('frame-key-token') != current_keys.get('token')
                    or result.get('frame-key-generation') != current_keys['generation'])):
            raise DebuggerError('Restored frame key ownership differs from its checkpoint')
        if saved['format'] in _REPEAT_FORMATS:
            _verify_key_repeat(vm, saved)
        adopt_frame_keys(vm, current_keys, expected_held=[] if key_state is None else key_state['held'])
    windows = {}
    if vm.machine_configuration.get('audio_profile', {}).get('profile') in ('pc-speaker', 'sb16', 'sb16-opl'):
        from .qemu_audio import _native_audio, audio_capture_format
        vm._audio_token = result.get('audio-token') or None
        vm._audio_capture_format = audio_capture_format(saved['audio']['info'])
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

    source_info = None
    if source is not None and source['info']['state'] != 'idle':
        source_info = restored_video_info(source, vm.qmp.call('x-fdisbull-query-video-frame'),
            epoch=epoch, token=result.get('video-frame-token'))

    # Read back the retained bytes, native timer phase, configuration and
    # callback frontiers through the same bounded native serializer.
    current = vm.qmp.call(PREFIX + 'checkpoint-export', max_reply_bytes=64 * 1024 * 1024)
    if not isinstance(current, dict):
        raise DebuggerError('Invalid restored instrumentation export')
    current = _decode(dict(state=current.get('state'), sha256=current.get('sha256'), icount=record['icount']))
    if (current['source-epoch'] != epoch or current['virtual-ns'] != saved['virtual-ns']
            or source is not None and current['format'] != saved['format']
            or source_info is not None and current.get('video-frame', {}).get('info') != source_info):
        raise DebuggerError('Restored instrumentation readback owner differs')
    if source is not None and source_info is None:
        # The public source query requires precise VGA even when idle. A
        # canonical idle sidecar also serves off-profile machines; verify its
        # exact new epoch/time through this full export without adopting it.
        restored_video_info(source, current['video-frame']['info'], epoch=epoch,
                            token=result.get('video-frame-token'))
    if _logical(_readback_view(saved, current,
            empty_native_key_owner=empty_native_key_owner)) != _logical(saved):
        raise DebuggerError('Restored native instrumentation data differs from its checkpoint')
    if source_info is not None:
        vm._video_frame_token = source_info['token']
        windows['video_frame'] = dict(old=source['info']['token'], new=source_info['token'])
        vm._video_frame_last = deepcopy(source_info)
    return dict(format=saved['format'] if source is not None else FORMAT,
                source_epoch=saved['source-epoch'], native_epoch=epoch,
                virtual_ns=saved['virtual-ns'], windows=windows,
                host_clock_sync_restored=False)
