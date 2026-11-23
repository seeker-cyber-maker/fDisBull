"""Opt-in screenshot-coordinate routes for the pinned QEMU DOS mouse driver."""
import time

from .dosbox_rpc import DebuggerError
from .external_files import _file_name
from .qemu_int33_click import _DEFAULT_BUDGET_NS, _advance_observed
from .qemu_int33_mouse_control import _calibrated_counts, _stopped_target
from .qemu_save_stop import safe_stop_enabled
from .qemu_video_frame import validate_video_frame_parameters
from .qemu_video_frame_state import _refuse
from .screenshot_grid import validate_step


FORMAT = 'fdisbull-qemu-coordinate-click-1'
_MOTION_FIELDS = ('minimum', 'maximum', 'buttons', 'button_edges',
                  'mickeys_per_eight_units', 'sensitivity_coefficients', 'position_remainders')


def validate_coordinate_click(x, y, *, delivery=None, button='left', hold_ms=80,
                              mode_id=None, frame_id=None, session_id=None, timeout_ms=3000,
                              capture=False):
    if delivery != 'observed-int33':
        raise ValueError('QEMU coordinate click requires explicit delivery=observed-int33 to execute guest phases')
    if type(x) is not int or type(y) is not int or not 0 <= x < 320 or not 0 <= y < 200:
        raise ValueError('QEMU coordinate click target must be within the 320x200 source raster')
    if type(button) is not str or button not in ('left', 'right'):
        raise ValueError('QEMU coordinate click supports left and right buttons')
    if type(hold_ms) is not int or not 1 <= hold_ms <= 1000:
        raise ValueError('hold_ms must be an integer in 1..1000')
    if (not capture or mode_id is not None) and (type(mode_id) is not int or not 1 <= mode_id < 1 << 53):
        raise ValueError('QEMU coordinate click requires the retained positive mode_id')
    if (not capture or frame_id is not None) and (type(frame_id) is not int or not 1 <= frame_id < 1 << 64):
        raise ValueError('QEMU coordinate click requires the exact retained frame_id')
    needs_session = not capture or mode_id is not None or frame_id is not None or session_id is not None
    if needs_session and (type(session_id) is not str or len(session_id) != 32
                          or any(char not in '0123456789abcdef' for char in session_id)):
        raise ValueError('QEMU coordinate click requires the retained raster session_id')
    validate_video_frame_parameters(timeout_ms=timeout_ms)


def validate_coordinate_click_frame(x, y, *, name='click-frame.png', grid_step=8,
                                    delivery=None, button='left', hold_ms=80,
                                    mode_id=None, frame_id=None, session_id=None, timeout_ms=3000):
    validate_coordinate_click(x, y, delivery=delivery, button=button, hold_ms=hold_ms,
                              mode_id=mode_id, frame_id=frame_id, session_id=session_id, timeout_ms=timeout_ms,
                              capture=True)
    _file_name(name)
    validate_step(grid_step)


def _preflight(owner, x, y, mode_id, frame_id, session_id, timeout_ms):
    if safe_stop_enabled(owner):
        raise ValueError('QEMU coordinate click requires the automatic DOS save-stop owner to be inactive')
    stopped, target = _stopped_target(owner, x, y, None, None, timeout_ms)
    raster = stopped['raster']
    if session_id is not None and session_id != raster['session_id']:
        _refuse('stale_session', 'STALE_SESSION: Requested QEMU click belongs to another raster session')
    if mode_id is not None and mode_id != raster['mode_id']:
        _refuse('stale_mode', 'STALE_MODE: Requested QEMU click mode is no longer retained')
    if frame_id is not None and frame_id != raster['frame_id']:
        _refuse('stale_frame', 'STALE_FRAME: Requested QEMU click frame is no longer retained')
    return stopped, target, _calibrated_counts(stopped, target)


def _public_observation(observed):
    return None if observed is None else {key: observed[key] for key in (
        'driver', 'raster', 'clock', 'position', 'buttons', 'minimum', 'maximum',
        'button_edges', 'driver_mickeys')}


def _public_phase(phase):
    if phase is None:
        return None
    value = dict(phase, observed=_public_observation(phase['observed']))
    execution = phase['execution']
    if execution is not None:
        value['execution'] = {key: execution[key] for key in (
            'outcome', 'timed_out', 'session', 'stop', 'clock_budget', 'input_delivery',
            'hook_hits', 'layer_conflict', 'save_boundary_conflict', 'native_machine_stop',
            'process') if key in execution}
    return value


def _public_result(result):
    result['target_landing'] = _public_observation(result['target_landing'])
    result['motion'] = _public_phase(result['motion'])
    frame = result['frame']
    if frame is not None:
        # Complete scanline, clock and producer metadata remain with the stored artifact.
        result['frame'] = dict(frame, metadata={key: frame['metadata'][key] for key in (
            'source', 'sha256', 'width', 'height', 'mode_id', 'frame_id', 'session_id',
            'frame_identity', 'coordinate_grid')})
    click = result['click']
    if click is not None:
        result['click'] = dict(click, before=_public_observation(click['before']),
                               press=_public_phase(click['press']), hold=_public_phase(click['hold']),
                               release=_public_phase(click['release']))
    return result


def _packets(counts):
    # The source and clip rectangles bound the delta before this split.
    dx, dy = counts
    packets = []
    while dx or dy:
        step_x = max(-4, min(4, dx))
        step_y = max(-4, min(4, dy))
        packets.append((step_x, step_y))
        dx -= step_x
        dy -= step_y
    return packets


def _motion_next_action(vm, result):
    state = getattr(vm, '_physical_input', None)
    if state and not state['valid']:
        return 'delivery_unknown'
    if state and state['pending']:
        queued = (result['motion'] or {}).get('queued') or {}
        if (not state['leases'] and
                [event['sequence'] for event in state['pending']] == queued.get('sequences')):
            return 'cancel_unsent_input'
        return 'inspect_owned_input'
    return None


def _move(owner, vm, result, stopped, packets, timeout_ms):
    current = stopped
    progress = result['motion_progress']
    for index, packet in enumerate(packets, start=1):
        if time.monotonic() >= vm.operation_deadline:
            return current, 'deadline_exhausted'
        raw_x, raw_y = current['raw_position']
        expected = [raw_x + packet[0], raw_y + packet[1] // 2]
        progress['attempted'] = index
        progress['attempted_counts'] = list(packet)
        result.update(stage='motion', motion=None)
        queued = owner.mouse_move_relative(*packet)
        outcome = _advance_observed(owner, vm, result, 'motion', queued, current,
                                    _DEFAULT_BUDGET_NS, timeout_ms)
        motion = result['motion']
        motion['counts'] = list(packet)
        if outcome is not None:
            return current, outcome
        observed = motion['observed']
        raster = observed['raster']
        if (observed['raw_position'] != expected
                or observed['position'] != [expected[0] & ~1, expected[1]]
                or any(observed[key] != stopped[key] for key in _MOTION_FIELDS)
                or raster['session_id'] != stopped['raster']['session_id']
                or raster['mode_id'] != stopped['raster']['mode_id']):
            return current, 'target_landing_unconfirmed'
        progress['verified'].append(dict(counts=list(packet), raw_position=expected,
            position=observed['position'], frame_id=raster['frame_id'],
            virtual_ns=observed['clock']['virtual_ns'], driver_mickeys=observed['driver_mickeys']))
        current = observed
    return current, None


def _execute(owner, x, y, button, hold_ms, timeout_ms, stopped, target, counts, frame=None):
    vm = owner.vm
    packets = _packets(counts)
    result = dict(format=FORMAT, run=owner.run_id, complete=False, outcome='unconfirmed', stage='preflight',
                  x=x, y=y, target=target, delivery='observed-int33', effect='unconfirmed',
                  mode_id=stopped['raster']['mode_id'], frame_id=stopped['raster']['frame_id'],
                  source=stopped['raster'], target_landing=None, motion=None, click=None,
                  motion_progress=dict(total_counts=list(counts), planned=len(packets),
                                       attempted=0, attempted_counts=None, verified=[]),
                  frame=frame, frame_phase='before_observed_input' if frame is not None else None,
                  next_action=None)
    try:
        landed, motion_outcome = _move(owner, vm, result, stopped, packets, timeout_ms)
        if motion_outcome is not None:
            result.update(outcome=motion_outcome, next_action=_motion_next_action(vm, result))
            return _public_result(result)
        if landed['position'] != target:
            result['outcome'] = 'target_landing_unconfirmed'
            return _public_result(result)
        result['target_landing'] = landed
        result['stage'] = 'click'
        raster = landed['raster']
        click = result['click'] = owner.mouse_click_int33(x, y, stream=raster['stream'],
            frame_id=raster['frame_id'], button=button, minimum_hold_ms=hold_ms,
            timeout_ms=timeout_ms)
        result.update(outcome=click['outcome'], complete=click['complete'], effect=click['effect'],
                      next_action=click['next_action'])
        return _public_result(result)
    except Exception as error:
        result.update(outcome='failed', click=getattr(error, 'int33_click', None))
        if result['click'] is not None:
            result.update(effect=result['click']['effect'], next_action=result['click']['next_action'])
        elif result['stage'] == 'motion':
            result['next_action'] = _motion_next_action(vm, result)
        error.coordinate_click = _public_result(result)
        raise


def _before_input_error(error, stage):
    error.coordinate_click = dict(format=FORMAT, stage=stage, complete=False,
                                  outcome='failed', effect='no_input_queued')


def click(self, x, y, *, delivery=None, button='left', hold_ms=80, mode_id=None,
          frame_id=None, session_id=None, timeout_ms=3000):
    """Reach and verify one coordinate click against an exact retained raster."""
    try:
        selection = _preflight(self, x, y, mode_id, frame_id, session_id, timeout_ms)
    except DebuggerError as error:
        _before_input_error(error, 'preflight')
        raise
    return _execute(self, x, y, button, hold_ms, timeout_ms, *selection)


def click_frame(self, x, y, *, name='click-frame.png', grid_step=8, delivery=None,
                button='left', hold_ms=80, mode_id=None, frame_id=None, session_id=None, timeout_ms=3000):
    """Capture a marked copy of the exact retained raster before observed input."""
    try:
        selection = _preflight(self, x, y, mode_id, frame_id, session_id, timeout_ms)
        raster = selection[0]['raster']
        capture = self.capture_video_frame(name[:248] + '.raw.png', stream=raster['stream'],
                                          frame_id=raster['frame_id'], timeout_ms=timeout_ms)
        frame = self.project.debug_grid(capture['artifact'], name=name, step=grid_step, target=[x, y])
    except DebuggerError as error:
        _before_input_error(error, 'preflight_or_capture')
        raise
    return _execute(self, x, y, button, hold_ms, timeout_ms, *selection, frame=frame)
