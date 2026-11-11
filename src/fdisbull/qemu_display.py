"""Retained completed QEMU renderer updates, never inferred guest frames.

The native observer runs at an explicitly selected virtual-time cadence. Each
publication follows the synchronous renderer and copies its pixels under BQL.
Reading or exporting that publication never refreshes the guest's display.
The period is an observation period, not a VGA refresh-rate or VBlank claim.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
from pathlib import Path
import time
import uuid

from .dosbox_rpc import DebuggerError


DISPLAY_COMMANDS = frozenset({
    'x-fdisbull-query-display', 'x-fdisbull-start-display',
    'x-fdisbull-stop-display', 'x-fdisbull-export-display',
})
DISPLAY_PROBE_COMMANDS = frozenset({'x-fdisbull-probe-display'})
MAX_DISPLAY_PROBE_POINTS = 256
MIN_DISPLAY_PERIOD_NS = 1_000_000
MAX_DISPLAY_PERIOD_NS = 1_000_000_000


def validate_display_period(period_ns):
    if type(period_ns) is not int or not MIN_DISPLAY_PERIOD_NS <= period_ns <= MAX_DISPLAY_PERIOD_NS:
        raise ValueError('Display period_ns must be an integer in 1000000..1000000000')


def validate_after_update(after_update):
    if after_update is not None and (type(after_update) is not int or not 0 <= after_update < 1 << 64):
        raise ValueError('after_update must be a nonnegative renderer update ID in this window')


def validate_display_probe_parameters(points, *, window=None, update_id=None,
                                      timeout_ms=1000, allow_references=False):
    """Validate every known value without acquiring ownership or doing I/O."""
    def reference(value):
        return allow_references and isinstance(value, str) and value.startswith('$')

    if not reference(points):
        if not isinstance(points, list) or len(points) > MAX_DISPLAY_PROBE_POINTS:
            raise ValueError('Renderer probe requires a list of at most 256 points')
        for point in points:
            if reference(point):
                continue
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError('Renderer probe points require exactly two coordinates')
            if isinstance(point, tuple) and any(reference(value) for value in point):
                raise ValueError('Script renderer probe references require list points')
            for coordinate in point:
                if not reference(coordinate) and (type(coordinate) is not int
                                                  or not 0 <= coordinate <= 8191):
                    raise ValueError('Renderer probe coordinates must be integers in 0..8191')
    if (window is None) != (update_id is None):
        raise ValueError('Renderer probe window and update_id must be supplied together')
    if window is not None and not reference(window):
        if type(window) is not str or not 1 <= len(window) <= 128 or '\0' in window:
            raise ValueError('Renderer probe window must be a nonempty token of at most 128 characters')
    if update_id is not None and not reference(update_id):
        if type(update_id) is not int or not 1 <= update_id < 1 << 64:
            raise ValueError('Renderer probe update_id must be a positive uint64 publication ID')
    if not reference(timeout_ms) and (type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000):
        raise ValueError('Renderer probe timeout_ms must be an integer in 1..600000')


def _invalid(vm, message):
    vm.close()
    raise DebuggerError(message)


def _native_display(vm, value, clock, *, token=None):
    def integer(item, maximum=(1 << 63) - 1):
        return type(item) is int and 0 <= item <= maximum

    required = {'api-version', 'epoch', 'state', 'virtual-ns', 'period-ns', 'updates'}
    if (not isinstance(value, dict) or not required <= value.keys()
            or type(value['api-version']) is not int or value['api-version'] != 1
            or not integer(value['epoch'], (1 << 64) - 1)
            or value['epoch'] != clock['virtual_clock']['native']['epoch']
            or not integer(value['virtual-ns']) or value['virtual-ns'] != clock['virtual_ns']
            or value['state'] not in ('idle', 'observing', 'stopped')
            or not integer(value['updates'], (1 << 64) - 1)
            or not integer(value['period-ns'], MAX_DISPLAY_PERIOD_NS)):
        _invalid(vm, 'Invalid native QEMU renderer receipt')
    latest = ('update-id', 'published-ns', 'width', 'height')
    if value['state'] == 'idle':
        if (any(key in value for key in ('token', 'start-ns', 'stop-ns', *latest))
                or value['updates'] or value['period-ns'] or token is not None):
            _invalid(vm, 'Idle native renderer unexpectedly retains an observation window')
    else:
        if (token is None or not isinstance(value.get('token'), str) or not 1 <= len(value['token']) <= 128
                or value['token'] != token
                or not integer(value.get('start-ns')) or value['start-ns'] > value['virtual-ns']
                or value['period-ns'] < MIN_DISPLAY_PERIOD_NS
                or 'stop-ns' in value and (not integer(value['stop-ns']) or
                    not value['start-ns'] <= value['stop-ns'] <= value['virtual-ns'])
                or (value['state'] == 'stopped') != ('stop-ns' in value)):
            _invalid(vm, 'Native renderer window identity or interval is invalid')
        if value['updates']:
            if (not all(key in value for key in latest)
                    or not integer(value['update-id'], (1 << 64) - 1)
                    or value['update-id'] != value['updates']
                    or not integer(value['published-ns'])
                    or not value['start-ns'] <= value['published-ns'] <= value.get('stop-ns', value['virtual-ns'])
                    or not integer(value['width'], 8192) or not integer(value['height'], 8192)
                    or min(value['width'], value['height']) < 1
                    or value['width'] * value['height'] * 3 > 16 * 1024 * 1024):
                _invalid(vm, 'Native completed renderer update has invalid identity or dimensions')
        elif any(key in value for key in latest):
            _invalid(vm, 'Native renderer invented a publication before completing an update')
    prior = getattr(vm, '_display_last', None)
    if prior is not None and prior.get('token') == value.get('token'):
        if (value['updates'] < prior['updates']
                or value.get('start-ns') != prior.get('start-ns')
                or value['period-ns'] != prior['period-ns']
                or 'stop-ns' in prior and value.get('stop-ns') != prior['stop-ns']
                or prior['updates'] and (value['published-ns'] < prior['published-ns']
                    or value['updates'] == prior['updates'] and
                    any(value[key] != prior[key] for key in latest))):
            _invalid(vm, 'Native renderer publication regressed or changed identity')
        if 'stop-ns' in prior and any(value.get(key) != item for key, item in prior.items() if key != 'virtual-ns'):
            _invalid(vm, 'Stopped native renderer changed after observation ended')
    vm._display_last = deepcopy(value)
    return deepcopy(value)


class QemuDisplayMixin:
    def _display_context(self):
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('Renderer observation requires a project outside a caller-owned transaction')
        if (self.vm.machine_configuration.get('clock_profile', {}).get('profile') != 'virtual'
                or not DISPLAY_COMMANDS <= getattr(self.vm, 'qmp_commands', frozenset())):
            raise ValueError('Renderer observation requires the virtual clock and native display extension API 1')
        self._stopped()
        return self.clock_observe()

    def _display_read(self, clock):
        return _native_display(self.vm, self.vm.qmp.call('x-fdisbull-query-display'), clock,
                               token=getattr(self.vm, '_display_token', None))

    def _display_receipt(self, native, clock):
        published = native.get('published-ns')
        return dict(format='fdisbull-renderer-window-1', context='machine', run=self.run_id,
                    epoch=clock['epoch'], window=native.get('token'), state=native['state'],
                    observed_ns=native['virtual-ns'], start_ns=native.get('start-ns'),
                    stop_ns=native.get('stop-ns'), clock_domain='QEMU_CLOCK_VIRTUAL',
                    observation_period_ns=native['period-ns'], updates=native['updates'],
                    update_id=native.get('update-id'), published_ns=published,
                    age_ns=native['virtual-ns'] - published if published is not None else None,
                    width=native.get('width'), height=native.get('height'),
                    completed_renderer_update=bool(native['updates']),
                    completed_guest_frame=None, guest_frame_id=None,
                    clock=deepcopy(clock), native=deepcopy(native),
                    scope=('Latest completed synchronous QEMU renderer update, copied into '
                           'owned pixels at publication. Observation cadence is not VGA '
                           'refresh timing; guest drawing, VBlank, readiness and input '
                           'consumption are not established.'))

    def display_observe(self):
        clock = self._display_context()
        result = self._display_receipt(self._display_read(clock), clock)
        self._event('machine-display-observe', result)
        return result

    def display_probe(self, points, *, window=None, update_id=None, timeout_ms=1000):
        """Read ordered RGB samples from one retained renderer publication.

        An optional window/update pair requires that exact publication. With
        neither supplied, the current retained publication is selected under
        the machine lock. No refresh, image export or guest execution occurs.
        """
        from .qemu_clock import VIRTUAL_CLOCK_COMMANDS

        validate_display_probe_parameters(points, window=window, update_id=update_id,
                                          timeout_ms=timeout_ms)
        points = [list(point) for point in points]
        commands = DISPLAY_COMMANDS | DISPLAY_PROBE_COMMANDS | VIRTUAL_CLOCK_COMMANDS
        if not commands <= getattr(self.vm, 'qmp_commands', frozenset()):
            raise ValueError('Renderer probe requires its native extension and virtual clock')
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('Renderer probe requires a project outside a caller-owned transaction')
        if self.vm.machine_configuration.get('clock_profile', {}).get('profile') != 'virtual':
            raise ValueError('Renderer probe requires the explicit virtual clock profile')
        self._stopped()
        before = prequery = None
        received_prequery = False
        try:
            before = self.clock_observe()
            prequery = self.vm.qmp.call('x-fdisbull-query-display')
            received_prequery = True
            prior = _native_display(self.vm, prequery, before,
                                    token=getattr(self.vm, '_display_token', None))
        except BaseException as error:
            # The first clock observation also journals evidence. Its storage
            # failure must have the same disposition as later probe persistence.
            self.vm.close()
            if getattr(error, 'result', None) is None and (before is not None or received_prequery):
                error.result = dict(format='fdisbull-renderer-probe-error-1', run=self.run_id,
                    stage='publication-query', requested_points=points, clock=before,
                    native=deepcopy(prequery), native_received=received_prequery)
            raise
        if not prior['updates']:
            raise ValueError('No completed renderer update is retained; advance the machine explicitly')
        if window is not None and (window != prior['token'] or update_id != prior['update-id']):
            raise ValueError('Renderer probe expected a different retained publication')
        if any(x >= prior['width'] or y >= prior['height'] for x, y in points):
            raise ValueError('Renderer probe point is outside the retained publication')

        def remaining():
            deadline = getattr(self.vm, 'operation_deadline', None)
            if deadline is None or time.monotonic() >= deadline:
                raise TimeoutError('Renderer pixel probe host deadline expired')

        raw = result = None
        received_probe = False
        try:
            remaining()
            raw = self.vm.qmp.call('x-fdisbull-probe-display', dict(
                token=prior['token'], **{'update-id': prior['update-id']},
                points=[dict(x=x, y=y) for x, y in points]))
            received_probe = True
            if not isinstance(raw, dict) or set(raw) != {'display', 'samples'}:
                _invalid(self.vm, 'Invalid native renderer probe response')
            native = _native_display(self.vm, raw['display'], before, token=prior['token'])
            if native != prior:
                _invalid(self.vm, 'Native renderer changed across its stopped probe')
            samples = raw['samples']
            if not isinstance(samples, list) or len(samples) != len(points):
                _invalid(self.vm, 'Native renderer probe returned an incomplete sample list')
            pixels, observed = [], {}
            identity = (prior['token'], prior['update-id'])
            previous = getattr(self.vm, '_display_probe_samples', None)
            known = previous['samples'] if previous is not None and previous['identity'] == identity else {}
            for point, sample in zip(points, samples, strict=True):
                if (not isinstance(sample, dict) or set(sample) != {'x', 'y', 'r', 'g', 'b'}
                        or any(type(sample[key]) is not int for key in sample)
                        or [sample['x'], sample['y']] != point
                        or any(not 0 <= sample[key] <= 255 for key in ('r', 'g', 'b'))):
                    _invalid(self.vm, 'Native renderer probe sample identity or RGB is invalid')
                rgb = [sample[key] for key in ('r', 'g', 'b')]
                coordinate = tuple(point)
                if (coordinate in observed and observed[coordinate] != rgb
                        or coordinate in known and known[coordinate] != rgb):
                    _invalid(self.vm, 'Native renderer probe pixels changed under one publication ID')
                observed[coordinate] = rgb
                pixels.append(dict(x=point[0], y=point[1], rgb=rgb))
            after = self.clock_observe()
            if (any(before[key] != after[key] for key in ('run', 'epoch', 'counter', 'virtual_ns'))
                    or before['virtual_clock']['native']['epoch'] != after['virtual_clock']['native']['epoch']
                    or before['sequence'] >= after['sequence']):
                _invalid(self.vm, 'Machine clock changed across the stopped renderer probe')
            result = self._display_receipt(native, before)
            result.update(format='fdisbull-renderer-probe-1', source='qemu_completed_renderer_update',
                          stopped=True, points=points, pixels=pixels, pixel_format='RGB24',
                          coordinate_domain='retained_renderer_pixels',
                          clocks=dict(before=before, after=after), native=deepcopy(raw))
            remaining()
            self._event('machine-display-probe', result)
            remaining()
            # One previous probe, at most 256 coordinates. This detects overlap
            # contradictions without accumulating an unbounded pixel history.
            self.vm._display_probe_samples = dict(identity=identity, samples=deepcopy(observed))
            return result
        except BaseException as error:
            self.vm.close()
            if getattr(error, 'result', None) is None and (received_probe or result is not None):
                error.result = deepcopy(result) if result is not None else dict(
                    format='fdisbull-renderer-probe-error-1', run=self.run_id,
                    stage='pixel-probe', requested_points=points, publication=prior,
                    native=deepcopy(raw), native_received=received_probe, clock=before)
            raise

    def display_start(self, *, period_ns=16_666_667):
        validate_display_period(period_ns)
        clock = self._display_context()
        prior = self._display_read(clock)
        if prior['state'] == 'observing':
            raise ValueError('Stop the current renderer observation window before starting another')
        token = uuid.uuid4().hex
        try:
            native = _native_display(self.vm, self.vm.qmp.call('x-fdisbull-start-display',
                {'token': token, 'period-ns': period_ns}), clock, token=token)
            if (native['state'] != 'observing' or native['updates'] != 0
                    or native['start-ns'] != clock['virtual_ns'] or native['period-ns'] != period_ns):
                _invalid(self.vm, 'Native renderer start differs from the requested window')
            self.vm._display_token = token
            result = self._display_receipt(native, clock)
            self._event('machine-display-start', result)
            return result
        except BaseException:
            self.vm.close()
            raise

    def display_stop(self):
        clock = self._display_context()
        prior = self._display_read(clock)
        if prior['state'] == 'idle':
            raise ValueError('No owned renderer observation window has been started')
        try:
            native = _native_display(self.vm, self.vm.qmp.call('x-fdisbull-stop-display',
                {'token': prior['token']}), clock, token=prior['token'])
            if (native['updates'] != prior['updates']
                    or native.get('stop-ns') != prior.get('stop-ns', clock['virtual_ns'])):
                _invalid(self.vm, 'Native renderer stop changed its completed publication')
            result = self._display_receipt(native, clock)
            self._event('machine-display-stop', result)
            return result
        except BaseException:
            self.vm.close()
            raise

    def capture_display(self, name='machine-display.png', *, after_update=None, max_bytes=None):
        """Save the retained publication; an optional ID requires a newer one.

        ``after_update`` is local to this observation window. Refusing a stale
        update does not run the VM or wait for another renderer callback.
        """
        from PIL import Image
        from .debugger import _file_name

        _file_name(name)
        if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= 16 * 1024**2):
            raise ValueError('Renderer PNG max_bytes must be an integer in 1..16777216')
        validate_after_update(after_update)
        clock = self._display_context()
        prior = self._display_read(clock)
        if not prior['updates']:
            raise ValueError('No completed renderer update is retained; advance the machine explicitly')
        if after_update is not None and prior['update-id'] <= after_update:
            raise ValueError('No newer renderer update is retained in this observation window')
        path = Path(self.vm.temporary.name) / ('display-' + uuid.uuid4().hex + '.ppm')
        try:
            native = _native_display(self.vm, self.vm.qmp.call('x-fdisbull-export-display',
                {'token': prior['token'], 'filename': str(path)}), clock, token=prior['token'])
            if native != prior:
                _invalid(self.vm, 'Native renderer changed across its stopped export')
            if not path.is_file() or not 0 < path.stat().st_size <= 16 * 1024 * 1024 + 128:
                _invalid(self.vm, 'Retained renderer pixels are missing or exceed the capture bound')
            raw = path.read_bytes()
            header = f"P6\n{native['width']} {native['height']}\n255\n".encode('ascii')
            if (not raw.startswith(header) or
                    len(raw) != len(header) + native['width'] * native['height'] * 3):
                _invalid(self.vm, 'Retained renderer pixels differ from the publication dimensions')
            pixels = raw[len(header):]
            pixel_hash = hashlib.sha256(pixels).hexdigest()
            previous = getattr(self.vm, '_display_export', None)
            identity = (native['token'], native['update-id'])
            if previous is not None and previous['identity'] == identity and previous['sha256'] != pixel_hash:
                _invalid(self.vm, 'Retained native pixels changed under the same renderer update ID')
            self.vm._display_export = dict(identity=identity, sha256=pixel_hash)
            output = io.BytesIO()
            with Image.frombytes('RGB', (native['width'], native['height']), pixels) as image:
                image.save(output, format='PNG')
            after = self.clock_observe()
            if (clock['epoch'] != after['epoch'] or clock['counter'] != after['counter']
                    or clock['virtual_ns'] != after['virtual_ns']):
                _invalid(self.vm, 'Machine clock changed across the stopped renderer export')
        except BaseException:
            self.vm.close()
            raise
        finally:
            path.unlink(missing_ok=True)
        data = output.getvalue()
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError('Renderer PNG exceeds its image byte budget before artifact publication')
        metadata = self._display_receipt(native, clock)
        metadata.update(source='qemu_completed_renderer_update', stopped=True,
                        pixel_sha256=hashlib.sha256(pixels).hexdigest(),
                        sha256=hashlib.sha256(data).hexdigest(),
                        clocks=dict(before=clock, after=after))
        artifact = self._artifact(name, 'screenshot', data, metadata)
        self._event('machine-capture-display', dict(artifact=artifact['artifact'],
                    window=native['token'], update_id=native['update-id'], sha256=metadata['sha256']))
        return artifact
