"""Positioned mouse input for the stopped, source-bound Mode 13h witness."""
from .qemu_video_frame import validate_video_frame_parameters


_FORMAT = 'fdisbull-qemu-int33-input-1'
_BUTTONS = ('left', 'right')


def validate_int33_input(x, y, *, stream, frame_id, timeout_ms=1000, button='left'):
    validate_video_frame_parameters(stream=stream, frame_id=frame_id, timeout_ms=timeout_ms)
    if stream is None:
        raise ValueError('Positioned INT33 input requires the exact retained source raster')
    if type(x) is not int or type(y) is not int or not 0 <= x < 320 or not 0 <= y < 200:
        raise ValueError('Positioned INT33 target must be within the 320x200 source raster')
    if type(button) is not str or button not in _BUTTONS:
        raise ValueError('Positioned INT33 input supports left and right buttons')


def _stopped_target(owner, x, y, stream, frame_id, timeout_ms):
    state = owner.input_state()
    if (not state['valid'] or state['pending_edges'] or state['leases']
            or owner._input_schedule_bound() or getattr(owner.vm, '_frame_key_owner', None) is not None):
        raise ValueError('Positioned INT33 input requires a neutral owned input queue and no frame-key owner')
    cursor = owner.observe_int33_mouse(stream=stream, frame_id=frame_id, timeout_ms=timeout_ms)
    if cursor['buttons'] != 0:
        raise ValueError('Positioned INT33 input requires the driver to report all buttons released')
    # The admitted driver reports two horizontal coordinate units per VGA
    # pixel in this mode. Vertical coordinates are already in source rows.
    target = [2 * x, y]
    if any(not low <= value <= high for low, value, high in
           zip(cursor['minimum'], target, cursor['maximum'], strict=True)):
        raise ValueError('Positioned INT33 target lies outside the observed guest clip range')
    return cursor, target


def _positioned_counts(cursor, target):
    if cursor['position'] == target:
        return (0, 0)
    if (cursor['mickeys_per_eight_units'] != [8, 16]
            or cursor['sensitivity_coefficients'] != [256, 256]
            or cursor['position_remainders'] != [0, 0]):
        raise ValueError('Positioned INT33 motion requires the qualified driver ratio, sensitivity and rounding state')
    current_x, current_y = cursor['raw_position']
    dx = 0 if cursor['position'][0] == target[0] else target[0] - current_x
    dy = 2 * (target[1] - current_y)
    if abs(dx) > 4 or abs(dy) > 4:
        raise ValueError('Positioned INT33 motion requires at most four physical counts on each axis')
    return dx, dy


def mouse_move_int33(self, x, y, *, stream, frame_id, timeout_ms=1000):
    """Queue at most one calibrated physical motion packet.

    Run separately, then observe actual driver landing at a stopped boundary.
    """
    cursor, target = _stopped_target(self, x, y, stream, frame_id, timeout_ms)
    result = dict(format=_FORMAT, operation='motion', source_target=[x, y], target=target,
                  observed=cursor, counts=None, input=None, guest_consumed=None)
    if cursor['position'] == target:
        return dict(result, delivery='already_at_target')
    dx, dy = _positioned_counts(cursor, target)
    queued = self.mouse_move_relative(dx, dy)
    return dict(result, delivery=queued['delivery'], counts=[dx, dy], input=queued)


def mouse_button_down_int33(self, x, y, *, stream, frame_id, button='left', timeout_ms=1000):
    """Queue one physical press only after an exact stopped landing readback.

    Run separately and observe the driver. Release with mouse_button_up using
    the returned lease and observe the final driver state after execution.
    """
    cursor, target = _stopped_target(self, x, y, stream, frame_id, timeout_ms)
    if cursor['position'] != target:
        raise ValueError('Positioned INT33 target has no observed landing; no press was queued')
    queued = self.mouse_button_down(button)
    return dict(format=_FORMAT, operation='button-down', source_target=[x, y], target=target,
                observed=cursor, input=queued, delivery=queued['delivery'],
                lease=queued['lease'], guest_consumed=None)
