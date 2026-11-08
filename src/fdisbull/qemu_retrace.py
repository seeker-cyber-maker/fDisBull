"""Passive observations of one explicitly selected QEMU VGA timing model.

Retrace phase is independent of renderer publication and guest drawing. These
reads neither wait for an edge nor update pixels, read the guest status port,
advance execution, or synchronize the machine with host time.
"""
from __future__ import annotations

from copy import deepcopy
import json
import time

from .dosbox_rpc import DebuggerError


RETRACE_COMMANDS = frozenset({'x-fdisbull-query-retrace'})
RETRACE_MODEL = 'qemu-vga-precise-fdisbull-v1'
_MAX_NS = (1 << 63) - 1
_MAX_UINT64 = (1 << 64) - 1
_RAW_FIELDS = frozenset(('msr', 'sr1', 'cr00', 'cr04', 'cr05', 'cr06',
                         'cr07', 'cr10', 'cr11', 'vbe-enable'))
_TIMING_FIELDS = frozenset(('ticks-per-char', 'total-chars', 'htotal', 'hstart',
                            'hend', 'vstart', 'vend', 'freq'))
_PHASE_INTS = frozenset(('period-ns', 'phase-ns', 'character', 'line', 'line-character'))
_PHASE_BOOLS = frozenset(('vertical-retrace', 'horizontal-retrace'))
_NATIVE_FIELDS = frozenset(('api-version', 'model', 'epoch', 'virtual-ns', 'device',
                            'device-type', 'console', 'head', 'timing-generation',
                            'phase-supported', 'raw', 'timing'))


def machine_retrace_configuration(profile, clock_profile):
    """Return the immutable selection; ordinary machines keep their defaults."""
    if type(profile) is not str or profile not in ('standard', 'precise'):
        raise ValueError('QEMU retrace profile must be standard or precise')
    if profile == 'precise' and clock_profile != 'virtual':
        raise ValueError('Precise retrace observation requires the explicit QEMU virtual clock profile')
    precise = profile == 'precise'
    return dict(profile=profile, adapter='std' if precise else None,
                retrace='precise' if precise else None,
                model=RETRACE_MODEL if precise else None,
                observation_only=True, host_synchronization=False)


def machine_retrace_arguments(profile):
    machine_retrace_configuration(profile, 'virtual')
    return (['-vga', 'std,retrace=precise', '-global', 'VGA.x-fdisbull-retrace=on']
            if profile == 'precise' else [])


def _invalid(vm, message):
    vm.close()
    raise DebuggerError(message)


def _integer(value, minimum=0, maximum=_MAX_NS):
    return type(value) is int and minimum <= value <= maximum


def _device(value):
    if (type(value) is not str or not value.startswith('/') or value == '/'
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        return False
    try:
        return len(value.encode('utf-8', errors='strict')) <= 512
    except UnicodeError:
        return False


def _model_timing(raw):
    """The declared model's integer arithmetic, not a hardware correction.

    In particular, QEMU selects character dots from MSR bit zero, rounds the
    character frequency before its nanosecond reciprocal, and uses inclusive
    sync endpoints. Preserve all three choices when checking its receipt.
    """
    dots = 8 if raw['msr'] & 1 else 9
    hz = (25_175_000, 28_322_000, 25_175_000, 25_175_000)[(raw['msr'] >> 2) & 3]
    ticks = 1_000_000_000 // (hz // dots)
    horizontal = (raw['cr00'] + 5) << ((raw['sr1'] >> 3) & 1)
    vertical = (raw['cr06'] | (((raw['cr07'] & 1) | ((raw['cr07'] >> 4) & 2)) << 8)) + 2
    hstart = raw['cr04'] + ((raw['cr05'] >> 5) & 3)
    vstart = raw['cr10'] | ((((raw['cr07'] >> 2) & 1) | ((raw['cr07'] >> 6) & 2)) << 8)
    return {'ticks-per-char': ticks, 'total-chars': horizontal * vertical,
            'htotal': horizontal, 'hstart': hstart, 'hend': hstart + (raw['cr05'] & 31) + 1,
            'vstart': vstart, 'vend': vstart + (raw['cr11'] & 15) + 1, 'freq': 0}


def _unsupported(raw, timing):
    if all(value == 0 for value in timing.values()):
        return 'uninitialized'
    if raw['vbe-enable'] & 1:
        return 'vbe-enabled'
    ticks, total, horizontal = (timing[key] for key in ('ticks-per-char', 'total-chars', 'htotal'))
    if (timing['freq'] != 0 or min(ticks, total, horizontal) <= 0
            or total % horizontal or ticks * total > _MAX_NS
            or not 0 <= timing['hstart'] <= timing['hend'] < horizontal
            or not 0 <= timing['vstart'] <= timing['vend'] < total // horizontal):
        return 'invalid-timing'
    return None


def _native_retrace(vm, value, clock):
    """Validate one native receipt without inferring a renderer/frame event."""
    if (type(value) is not dict or not _NATIVE_FIELDS <= value.keys()
            or type(value.get('phase-supported')) is not bool):
        _invalid(vm, 'Invalid native retrace receipt fields')
    fields = _NATIVE_FIELDS | ({'phase'} if value['phase-supported'] else {'unsupported-reason'})
    if (set(value) != fields or type(value['api-version']) is not int or value['api-version'] != 1
            or value['model'] != RETRACE_MODEL or value['device-type'] != 'VGA'
            or not _integer(value['epoch'], 1, _MAX_UINT64)
            or value['epoch'] != clock['virtual_clock']['native']['epoch']
            or not _integer(value['virtual-ns']) or value['virtual-ns'] != clock['virtual_ns']
            or not _device(value['device']) or type(value['console']) is not int or value['console'] != 0
            or type(value['head']) is not int or value['head'] != 0
            or not _integer(value['timing-generation'], 1, _MAX_UINT64)):
        _invalid(vm, 'Invalid native retrace model, clock or device identity')
    raw, timing = value['raw'], value['timing']
    if (type(raw) is not dict or set(raw) != _RAW_FIELDS
            or any(not _integer(item, 0, 65535 if key == 'vbe-enable' else 255)
                   for key, item in raw.items())
            or type(timing) is not dict or set(timing) != _TIMING_FIELDS
            or any(not _integer(item, -_MAX_NS - 1) for item in timing.values())):
        _invalid(vm, 'Invalid native retrace raw or cached timing fields')
    if any(timing.values()) and timing != _model_timing(raw):
        _invalid(vm, 'Native retrace cached timing contradicts the declared raw model')
    unsupported = _unsupported(raw, timing)
    if value['phase-supported'] != (unsupported is None):
        _invalid(vm, 'Native retrace phase eligibility contradicts its timing model')
    if unsupported is not None:
        if value['unsupported-reason'] != unsupported:
            _invalid(vm, 'Native retrace unsupported reason contradicts its timing model')
    else:
        phase = value['phase']
        if (type(phase) is not dict or set(phase) != _PHASE_INTS | _PHASE_BOOLS | {'status1-timing-bits'}
                or any(not _integer(phase[key]) for key in _PHASE_INTS)
                or any(type(phase[key]) is not bool for key in _PHASE_BOOLS)
                or not _integer(phase['status1-timing-bits'], 0, 255)):
            _invalid(vm, 'Invalid native retrace phase fields')
        period = timing['ticks-per-char'] * timing['total-chars']
        phase_ns = value['virtual-ns'] % period
        character = phase_ns // timing['ticks-per-char']
        line, line_character = divmod(character, timing['htotal'])
        vertical = timing['vstart'] <= line <= timing['vend']
        horizontal = timing['hstart'] <= line_character <= timing['hend']
        expected = {'period-ns': period, 'phase-ns': phase_ns, 'character': character,
                    'line': line, 'line-character': line_character,
                    'vertical-retrace': vertical, 'horizontal-retrace': horizontal,
                    'status1-timing-bits': (8 if vertical else 0) | (1 if vertical or horizontal else 0)}
        if phase != expected:
            _invalid(vm, 'Native retrace phase contradicts its observed clock and timing model')
    previous = getattr(vm, '_retrace_last', None)
    if previous is not None:
        if any(value[key] != previous[key] for key in ('epoch', 'model', 'device', 'device-type', 'console', 'head')):
            _invalid(vm, 'Native retrace device or ownership epoch changed')
        if (value['timing-generation'] < previous['timing-generation']
                or value['virtual-ns'] < previous['virtual-ns']):
            _invalid(vm, 'Native retrace timing generation or clock regressed')
        if value['timing-generation'] == previous['timing-generation'] and any(
                value.get(key) != previous.get(key) for key in
                ('raw', 'timing', 'phase-supported', 'unsupported-reason')):
            _invalid(vm, 'Native retrace timing changed without a new generation')
    vm._retrace_last = deepcopy(value)
    return deepcopy(value)


def _configuration(vm):
    configuration = getattr(vm, 'machine_configuration', {})
    if type(configuration) is not dict:
        _invalid(vm, 'Owned-machine precise retrace configuration is malformed')
    profile = configuration.get('retrace_profile')
    if type(profile) is not dict or profile.get('profile') != 'precise':
        if getattr(vm, 'native_retrace_admission', None) is not None:
            _invalid(vm, 'Owned-machine precise retrace profile changed')
        raise ValueError('Retrace observation requires the explicit QEMU precise retrace profile')
    expected = machine_retrace_configuration('precise', 'virtual')
    try:
        exact = json.dumps(profile, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True)
    except (TypeError, ValueError):
        exact = False
    clock_profile = configuration.get('clock_profile')
    if (not exact or type(configuration.get('cpus')) is not int or configuration['cpus'] != 1
            or type(clock_profile) is not dict or clock_profile.get('profile') != 'virtual'):
        _invalid(vm, 'Owned-machine precise retrace configuration changed')
    if not RETRACE_COMMANDS <= getattr(vm, 'qmp_commands', frozenset()):
        raise ValueError('Precise retrace observation requires native retrace extension API 1')


def admit_retrace(vm):
    """Admit the native model even before firmware establishes valid timing."""
    _configuration(vm)
    native_clock = getattr(vm, 'native_clock_admission', None)
    if type(native_clock) is not dict:
        raise ValueError('Precise retrace requires the admitted native virtual clock')
    clock = dict(virtual_ns=native_clock['virtual-ns'], virtual_clock=dict(native=native_clock))
    try:
        value = _native_retrace(vm, vm.qmp.call('x-fdisbull-query-retrace'), clock)
    except BaseException:
        vm.close()
        raise
    vm.native_retrace_admission = deepcopy(value)
    return value


def _remaining(owner):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None:
        raise ValueError('Retrace observation requires a bounded owned operation')
    if time.monotonic() >= deadline:
        raise TimeoutError('Retrace observation host deadline expired')


class QemuRetraceMixin:
    def retrace_observe(self, *, timeout_ms=1000):
        """Return one stable stopped phase receipt; never wait for an edge."""
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('Retrace observation requires a project outside a caller-owned transaction')
        _configuration(self.vm)
        if not isinstance(getattr(self.vm, 'native_retrace_admission', None), dict):
            _invalid(self.vm, 'Owned-machine native retrace admission is missing')
        _remaining(self)
        try:
            before = self._clock_snapshot()
            native = _native_retrace(self.vm, self.vm.qmp.call('x-fdisbull-query-retrace'), before)
            after = self._clock_snapshot()
            if (any(before[key] != after[key] for key in ('run', 'epoch', 'virtual_ns', 'counter'))
                    or before['virtual_clock']['native']['epoch'] != after['virtual_clock']['native']['epoch']
                    or before['sequence'] >= after['sequence']):
                _invalid(self.vm, 'Machine clock changed across the stopped retrace observation')
        except BaseException:
            self.vm.close()
            raise
        result = dict(format='fdisbull-retrace-observation-1', context='machine', run=self.run_id,
            epoch=before['epoch'], native_epoch=native['epoch'], clock_domain='QEMU_CLOCK_VIRTUAL',
            observed_ns=native['virtual-ns'], model=native['model'], device=native['device'],
            device_type=native['device-type'], console=native['console'], head=native['head'],
            timing_generation=native['timing-generation'], phase_supported=native['phase-supported'],
            unsupported_reason=native.get('unsupported-reason'), raw=deepcopy(native['raw']),
            timing=deepcopy(native['timing']), phase=deepcopy(native.get('phase')),
            clocks=dict(before=before, after=after), native=native,
            completed_renderer_update=None, completed_guest_frame=None, guest_frame_id=None,
            scope=('Current phase of the explicitly selected QEMU VGA integer timing model. '
                   'No guest status-port read, renderer publication, historical scanout, '
                   'completed guest drawing, input consumption or host-time synchronization is established.'))
        try:
            _remaining(self)
            self._event('machine-retrace-observe', result)
            _remaining(self)
        except BaseException as error:
            if getattr(error, 'result', None) is None:
                error.result = result
            raise
        return result
