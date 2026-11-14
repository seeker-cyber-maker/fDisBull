"""Declared image displacement, bound to a retained VGA publication.

The scale converts pixels to QEMU REL event units. It is caller supplied, not
an observed guest-driver calibration. A native callback rechecks publication
and configuration identity before any motion event; it establishes neither
device queue acceptance nor actual pointer movement or current raster contents.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import time
import uuid

from .dosbox_rpc import DebuggerError
from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
from .qemu_display import DISPLAY_COMMANDS, _native_display
from .qemu_retrace import RETRACE_COMMANDS, _configuration as precise_configuration
from .qemu_vga_configuration import (VGA_CONFIGURATION_COMMANDS, _DISPLAY_FIELDS,
                                      validate_vga_configuration_snapshot)


MAPPED_MOUSE_COMMANDS = frozenset({'x-fdisbull-arm-display-motion'})
FORMAT = 'fdisbull-mapped-mouse-motion-1'
_DELAY_NS = 2_000_000
_MAX_NS = (1 << 63) - 1
_CANCELLATIONS = frozenset({'display-motion-configuration-changed',
                           'display-motion-publication-changed'})


def validate_mapped_mouse_parameters(dx_pixels, dy_pixels, *, counts_per_pixel,
                                    window, update_id, configuration_generation,
                                    timeout_ms=1000, allow_references=False):
    """Check every known axis independently, before locking or script effects."""
    def reference(value):
        return allow_references and isinstance(value, str) and value.startswith('$')

    def integer(value, label, minimum, maximum):
        if not reference(value) and (type(value) is not int or not minimum <= value <= maximum):
            raise ValueError(f'{label} must be an integer in {minimum}..{maximum}')

    pixels = {'x': dx_pixels, 'y': dy_pixels}
    for axis, value in pixels.items():
        integer(value, 'd' + axis + '_pixels', -8191, 8191)
    if dx_pixels == 0 and dy_pixels == 0:
        raise ValueError('Mapped mouse motion requires a nonzero pixel displacement')
    deltas = {}
    if not reference(counts_per_pixel):
        if type(counts_per_pixel) is not dict or set(counts_per_pixel) != {'x', 'y'}:
            raise ValueError('counts_per_pixel must contain exactly x and y rational scales')
        for axis, ratio in counts_per_pixel.items():
            if reference(ratio):
                continue
            if type(ratio) is not list or len(ratio) != 2:
                raise ValueError('Each counts_per_pixel axis must be [numerator, denominator]')
            numerator, denominator = ratio
            integer(numerator, axis + ' numerator', -32767, 32767)
            if not reference(numerator) and numerator == 0:
                raise ValueError('counts_per_pixel numerators must be nonzero')
            integer(denominator, axis + ' denominator', 1, 32767)
            if not any(reference(value) for value in (pixels[axis], numerator, denominator)):
                product = pixels[axis] * numerator
                if product % denominator:
                    raise ValueError('Mapped mouse motion requires exact integer REL units; no rounding')
                delta = product // denominator
                integer(delta, axis + ' derived REL units', -127, 127)
                deltas[axis] = delta
    if len(deltas) == 2 and not any(deltas.values()):
        raise ValueError('Mapped mouse motion requires a nonzero relative displacement')
    if not reference(window):
        if type(window) is not str or not 1 <= len(window) <= 128 or '\0' in window:
            raise ValueError('Mapped mouse window must be a nonempty token of at most 128 characters')
        try:
            window.encode('utf-8')
        except UnicodeEncodeError as error:
            raise ValueError('Mapped mouse window must be valid UTF-8') from error
    integer(update_id, 'update_id', 1, (1 << 64) - 1)
    integer(configuration_generation, 'configuration_generation', 1, (1 << 64) - 1)
    integer(timeout_ms, 'timeout_ms', 1, 600000)
    return deltas


def _observation(value, *, epoch, virtual_ns, previous=None):
    """Validate frozen callback evidence without moving live observation caches."""
    if (type(value) is not dict or not {'display', 'current'} <= value.keys()
            or set(value) - {'display', 'current', 'published'}
            or type(value['display']) is not dict or set(value['display']) - _DISPLAY_FIELDS):
        raise ValueError('Invalid native mapped-motion VGA observation fields')
    # Reuse the renderer shape contract with a private frontier. A callback can
    # be historical by the time the owning execution stops and queries it. A
    # changed observer state is cancellation evidence, not a new live reading.
    view = SimpleNamespace(close=lambda: None)
    clock = {'virtual_ns': virtual_ns, 'virtual_clock': {'native': {'epoch': epoch}}}
    try:
        display = _native_display(view, value['display'], clock,
                                  token=value['display'].get('token'))
    except DebuggerError as error:
        raise ValueError(str(error)) from error
    if previous is not None:
        prior_display = previous['display']
        if display.get('token') == prior_display.get('token'):
            if (display['updates'] < prior_display['updates']
                    or any(display.get(key) != prior_display.get(key) for key in ('start-ns', 'period-ns'))
                    or display['updates'] and display['published-ns'] < prior_display['published-ns']
                    or display['state'] == prior_display['state'] == 'stopped'
                        and display['stop-ns'] != prior_display['stop-ns']):
                raise ValueError('Native mapped-motion renderer window regressed or changed identity')
            if (display['updates'] == prior_display['updates'] and
                    any(display.get(key) != prior_display.get(key)
                        for key in ('update-id', 'published-ns', 'width', 'height'))):
                raise ValueError('Native mapped-motion publication metadata changed under one identity')
        elif display['state'] != 'idle' and display['start-ns'] < previous['current']['virtual-ns']:
            raise ValueError('Native mapped-motion replacement window predates its arm')
    current = validate_vga_configuration_snapshot(value['current'], epoch=epoch,
        virtual_ns=virtual_ns, device=previous['current'] if previous else value['current'],
        previous=previous['current'] if previous else None)
    if bool(display['updates']) != ('published' in value):
        raise ValueError('Native mapped-motion publication stamp is missing or invented')
    if display['updates']:
        published = validate_vga_configuration_snapshot(value['published'], epoch=epoch,
            virtual_ns=display['published-ns'], device=current,
            previous=previous.get('published') if previous else None)
        generation = published['configuration-generation']
        if (generation > current['configuration-generation']
                or generation == current['configuration-generation'] and published['raw'] != current['raw']):
            raise ValueError('Native mapped-motion publication contradicts current configuration')
        if previous is not None:
            older = previous['current']
            difference = generation - older['configuration-generation']
            if (difference == 0 and published['raw'] != older['raw']
                    or difference * (published['virtual-ns'] - older['virtual-ns']) < 0):
                raise ValueError('Native mapped-motion publication contradicts configuration history')
            identity = (display.get('token'), display.get('update-id'))
            prior_display = previous['display']
            if (identity == (prior_display.get('token'), prior_display.get('update-id'))
                    and published != previous.get('published')):
                raise ValueError('Native mapped-motion stamp changed under one publication')
    return deepcopy(value)


def _binding_change(armed, checked):
    if (checked['current']['configuration-generation'] >
            armed['current']['configuration-generation']):
        return 'display-motion-configuration-changed'
    frozen = lambda item: {key: value for key, value in item.items() if key != 'virtual-ns'}
    if (frozen(checked['display']) != frozen(armed['display'])
            or checked.get('published') != armed['published']):
        return 'display-motion-publication-changed'
    return None


def _known_observation_history(vm, armed, checked):
    """Cross-check first callback evidence without treating history as current.

    Strict virtual time orders configuration observations. Equal virtual time
    does not order paused QOM mutations, so a later live read at the callback's
    timestamp cannot retroactively invalidate its earlier configuration. Equal
    generations and equal publication identities are immutable at every time.
    """
    current = getattr(vm, '_vga_configuration_last', None)
    publication = getattr(vm, '_vga_publication_last', None)
    for sample in (checked['current'], checked.get('published')):
        if sample is None:
            continue
        for known in (current, publication['snapshot'] if publication else None):
            if known is None:
                continue
            identity = ('api-version', 'model', 'epoch', 'device', 'device-type', 'console', 'head')
            delta_time = sample['virtual-ns'] - known['virtual-ns']
            delta_generation = sample['configuration-generation'] - known['configuration-generation']
            if (any(sample[key] != known[key] for key in identity)
                    or delta_time * delta_generation < 0
                    or delta_generation == 0 and sample['raw'] != known['raw']):
                raise ValueError('Native mapped-motion callback contradicts observed VGA history')
    display = checked['display']
    if (publication is not None and
            (display.get('token'), display.get('update-id')) == publication['identity']
            and checked.get('published') != publication['snapshot']):
        raise ValueError('Native mapped-motion callback contradicts an observed publication stamp')
    known = getattr(vm, '_display_last', None)
    if known is None:
        return
    same_window = display.get('token') == known.get('token')
    if (same_window and display.get('update-id') == known.get('update-id')
            and any(display.get(key) != known.get(key)
                    for key in ('published-ns', 'width', 'height'))):
        raise ValueError('Native mapped-motion callback changed observed publication metadata')
    if known['virtual-ns'] >= checked['current']['virtual-ns']:
        return
    # This stopped public observation strictly predates the callback. A new
    # owned window cannot be replaced by the already consumed original token.
    if not same_window:
        if (display.get('token') == armed['display']['token']
                or display['state'] != 'idle' and display['start-ns'] < known['virtual-ns']):
            raise ValueError('Native mapped-motion callback reverted an observed renderer window')
    elif (display['updates'] < known['updates']
            or any(display.get(key) != known.get(key) for key in ('start-ns', 'period-ns'))
            or known['updates'] and display['published-ns'] < known['published-ns']
            or display['state'] == known['state'] == 'stopped' and display['stop-ns'] != known['stop-ns']):
        raise ValueError('Native mapped-motion callback regressed observed renderer history')


def validate_native_motion(value, expected, *, vm=None):
    """Require the original binding and a justified terminal callback decision."""
    planned = expected.get('motion') if expected is not None else None
    if planned is None:
        if 'motion' in value or value.get('reason') in _CANCELLATIONS:
            raise ValueError('Other native input invented mapped-motion evidence')
        return False
    descriptor = value.get('motion')
    fields = {'dx', 'dy', 'delay-ns', 'armed'}
    if (type(descriptor) is not dict or not fields <= descriptor.keys()
            or set(descriptor) - fields - {'checked'}
            or any(type(descriptor[key]) is not int or descriptor[key] != planned[key]
                   for key in ('dx', 'dy'))
            or type(descriptor['delay-ns']) is not int or descriptor['delay-ns'] != _DELAY_NS
            or value['deadline-ns'] != value['start-ns'] + _DELAY_NS):
        raise ValueError('Native mapped-motion descriptor differs from its declared plan')
    armed = _observation(descriptor['armed'], epoch=value['epoch'], virtual_ns=value['start-ns'])
    if armed != planned['before']['native']:
        raise ValueError('Native mapped-motion arm differs from the exact stopped observation')
    if (armed['display']['state'] != 'stopped' or not armed['display']['updates']
            or armed['published']['configuration-generation'] != armed['current']['configuration-generation']):
        raise ValueError('Native mapped-motion arm lacks a stopped matching publication')
    semantic_cancel = value['state'] == 'cancelled' and value.get('reason') in _CANCELLATIONS
    if value.get('reason') in _CANCELLATIONS and not semantic_cancel:
        raise ValueError('Native mapped-motion cancellation reason contradicts its state')
    needs_check = value['state'] == 'dispatched' or semantic_cancel
    if value['state'] != 'failed' and ('checked' in descriptor) != needs_check:
        raise ValueError('Native mapped-motion callback snapshot presence is invalid')
    if 'checked' in descriptor:
        checked = _observation(descriptor['checked'], epoch=value['epoch'],
                               virtual_ns=value['terminal-ns'], previous=armed)
        if checked['current']['virtual-ns'] < value['deadline-ns']:
            raise ValueError('Native mapped-motion callback preceded its deadline')
        if vm is not None and expected.get('native', {}).get('state') == 'armed':
            _known_observation_history(vm, armed, checked)
        change = _binding_change(armed, checked)
        if value['state'] == 'dispatched' and change is not None:
            raise ValueError('Native mapped-motion dispatch lost its publication/configuration binding')
        if semantic_cancel and change != value['reason']:
            raise ValueError('Native mapped-motion cancellation lacks its declared binding change')
    prior = expected.get('native', {}).get('motion')
    if prior is not None and (descriptor['armed'] != prior['armed']
            or 'checked' in prior and descriptor.get('checked') != prior['checked']):
        raise ValueError('Native mapped-motion changed frozen observation evidence')
    return semantic_cancel


def motion_receipt(native, schedule):
    planned = schedule['motion']
    descriptor = native['motion']
    return dict(format=FORMAT, dx_pixels=planned['dx_pixels'], dy_pixels=planned['dy_pixels'],
        counts_per_pixel=deepcopy(planned['counts_per_pixel']), dx=planned['dx'], dy=planned['dy'],
        coordinate_domain='retained_renderer_pixels', relative_unit='QEMU_REL_input_event',
        delay_ns=_DELAY_NS, before=deepcopy(planned['before']),
        native_arm=deepcopy(descriptor['armed']), native_check=deepcopy(descriptor.get('checked')),
        binding_verified=native['state'] == 'dispatched', guest_pixel_displacement=None,
        guest_pointer_position=None, mapping_verified=None, raster_coherence=None, target_reached=None,
        claim=('Caller-declared pixel displacement converted exactly to relative input units, with '
               'publication/configuration binding checked before callbacks. No button events are '
               'requested. Actual pixel travel, pointer position, driver scale, current raster, '
               'pre-existing button state, device acceptance and guest consumption remain unknown.'))


def _remaining(owner):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None or time.monotonic() >= deadline:
        raise TimeoutError('Mapped mouse motion host deadline expired')


def mouse_move_mapped(owner, dx_pixels, dy_pixels, *, counts_per_pixel, window,
                      update_id, configuration_generation, timeout_ms=1000):
    """Passively arm one exact relative batch against an owned publication."""
    from .qemu_input_schedule import INPUT_SCHEDULE_COMMANDS, _invalid, _native_schedule
    # Freeze the caller's nested declaration before deriving counts or making
    # native calls. The accepted receipt must describe those same input units.
    counts_per_pixel = deepcopy(counts_per_pixel)
    deltas = validate_mapped_mouse_parameters(dx_pixels, dy_pixels,
        counts_per_pixel=counts_per_pixel, window=window, update_id=update_id,
        configuration_generation=configuration_generation, timeout_ms=timeout_ms)
    if owner.project is None or owner.project.db.in_transaction:
        raise ValueError('Mapped mouse motion requires a project outside a caller-owned transaction')
    commands = (MAPPED_MOUSE_COMMANDS | INPUT_SCHEDULE_COMMANDS | VIRTUAL_CLOCK_COMMANDS |
                DISPLAY_COMMANDS | RETRACE_COMMANDS | VGA_CONFIGURATION_COMMANDS | {'input-send-event'})
    if not commands <= getattr(owner.vm, 'qmp_commands', frozenset()):
        raise ValueError('Mapped mouse motion requires native input/display/VGA extensions and virtual/precise profiles')
    precise_configuration(owner.vm)
    state = owner._input_storage()
    if state['pending'] or state['leases'] or owner._input_schedule_bound():
        raise ValueError('Mapped mouse motion requires an empty input queue and no owned held leases')
    _remaining(owner)
    clock = owner._input_schedule_context()
    prior = owner._input_schedule_read(clock)
    if prior['state'] == 'armed':
        raise ValueError('Cancel the current native input schedule before mapped mouse motion')
    before = owner.vga_configuration_observe(timeout_ms=timeout_ms)
    display = before['display']
    try:
        if display['state'] != 'stopped' or not display['updates']:
            raise ValueError('Mapped mouse motion requires an explicitly stopped nonempty renderer window')
        if (display['window'] != window or display['update_id'] != update_id
                or before['current']['configuration_generation'] != configuration_generation
                or before['configuration_matches'] is not True):
            raise ValueError('Mapped mouse motion expected a different publication or VGA configuration')
        if abs(dx_pixels) >= display['width'] or abs(dy_pixels) >= display['height']:
            raise ValueError('Mapped mouse displacement exceeds the retained publication dimensions')
        clock = before['clocks']['after']
        if clock['virtual_ns'] > _MAX_NS - _DELAY_NS:
            raise ValueError('Mapped mouse motion deadline overflows signed nanoseconds')
        _remaining(owner)
    except BaseException as error:
        if getattr(error, 'result', None) is None:
            error.result = dict(operation='mouse_move_mapped', before=deepcopy(before), armed=False)
        raise
    planned = dict(dx_pixels=dx_pixels, dy_pixels=dy_pixels,
        counts_per_pixel=deepcopy(counts_per_pixel), dx=deltas['x'], dy=deltas['y'], before=deepcopy(before))
    records = []
    for axis in ('x', 'y'):
        if deltas[axis]:
            records.append(dict(sequence=state['sequence'] + len(records) + 1, lease=None,
                event=dict(type='rel', data=dict(axis=axis, value=deltas[axis]))))
    schedule = dict(token=uuid.uuid4().hex, start_ns=clock['virtual_ns'],
        deadline_ns=clock['virtual_ns'] + _DELAY_NS, records=records, bound=True, motion=planned)
    expected = {'epoch': before['native_epoch'], 'virtual-ns': clock['virtual_ns'],
        'device': before['current']['device'], 'model': before['current']['model'],
        'configuration-generation': configuration_generation, 'window': window,
        'update-id': update_id, 'published-ns': display['published_ns'],
        'width': display['width'], 'height': display['height']}
    received = result = None
    try:
        _remaining(owner)
        received = owner.vm.qmp.call('x-fdisbull-arm-display-motion', {
            'token': schedule['token'], 'dx': deltas['x'], 'dy': deltas['y'], 'expected': expected})
        native = _native_schedule(owner, received, clock, schedule)
        if native['state'] != 'armed':
            _invalid(owner, 'Native mapped-motion arm did not leave a passive undelivered batch')
        _remaining(owner)
        state['pending'] = deepcopy(records)
        state['sequence'] += len(records)
        state['schedule'] = schedule
        result = owner._input_schedule_accept(native, clock)
        owner._input_persist('input.schedule-arm', result)
        _remaining(owner)
        copied = deepcopy(result)
        _remaining(owner)
        return copied
    except BaseException as error:
        if getattr(error, 'result', None) is None:
            error.result = (deepcopy(result) if result is not None else dict(
                operation='mouse_move_mapped', motion_plan=deepcopy(planned),
                native=deepcopy(received), validation_failed=True))
        owner._input_invalidate('Native mapped-motion arm outcome is uncertain; batch must not be replayed')
        owner.vm.close()
        raise
