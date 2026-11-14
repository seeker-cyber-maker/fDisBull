"""Observations and explicit waits for one selected QEMU VGA timing model.

Retrace phase is independent of renderer publication and guest drawing. These
passive reads do not update pixels, read the guest status port or advance
execution. An explicit wait composes a single native clock budget with two
stopped observations; neither operation synchronizes the machine with host time.
"""
from __future__ import annotations

from copy import deepcopy
import json
import time

from .dosbox_rpc import DebuggerError
from .qemu_clock import clock_timer_stop_is_ordinary, validate_clock_budget


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


def validate_retrace_snapshot(value, *, epoch, virtual_ns, previous=None):
    """Validate a native snapshot against explicit historical clock evidence.

    Callback receipts can precede the latest live observation. This pure
    validator never reads or updates an owned VM's live retrace frontier.
    """
    def invalid(message):
        raise ValueError(message)

    if not _integer(epoch, 1, _MAX_UINT64) or not _integer(virtual_ns):
        invalid('Invalid explicit native retrace snapshot clock')
    if (type(value) is not dict or not _NATIVE_FIELDS <= value.keys()
            or type(value.get('phase-supported')) is not bool):
        invalid('Invalid native retrace receipt fields')
    fields = _NATIVE_FIELDS | ({'phase'} if value['phase-supported'] else {'unsupported-reason'})
    if (set(value) != fields or type(value['api-version']) is not int or value['api-version'] != 1
            or value['model'] != RETRACE_MODEL or value['device-type'] != 'VGA'
            or not _integer(value['epoch'], 1, _MAX_UINT64)
            or value['epoch'] != epoch
            or not _integer(value['virtual-ns']) or value['virtual-ns'] != virtual_ns
            or not _device(value['device']) or type(value['console']) is not int or value['console'] != 0
            or type(value['head']) is not int or value['head'] != 0
            or not _integer(value['timing-generation'], 1, _MAX_UINT64)):
        invalid('Invalid native retrace model, clock or device identity')
    raw, timing = value['raw'], value['timing']
    if (type(raw) is not dict or set(raw) != _RAW_FIELDS
            or any(not _integer(item, 0, 65535 if key == 'vbe-enable' else 255)
                   for key, item in raw.items())
            or type(timing) is not dict or set(timing) != _TIMING_FIELDS
            or any(not _integer(item, -_MAX_NS - 1) for item in timing.values())):
        invalid('Invalid native retrace raw or cached timing fields')
    if any(timing.values()) and timing != _model_timing(raw):
        invalid('Native retrace cached timing contradicts the declared raw model')
    unsupported = _unsupported(raw, timing)
    if value['phase-supported'] != (unsupported is None):
        invalid('Native retrace phase eligibility contradicts its timing model')
    if unsupported is not None:
        if value['unsupported-reason'] != unsupported:
            invalid('Native retrace unsupported reason contradicts its timing model')
    else:
        phase = value['phase']
        if (type(phase) is not dict or set(phase) != _PHASE_INTS | _PHASE_BOOLS | {'status1-timing-bits'}
                or any(not _integer(phase[key]) for key in _PHASE_INTS)
                or any(type(phase[key]) is not bool for key in _PHASE_BOOLS)
                or not _integer(phase['status1-timing-bits'], 0, 255)):
            invalid('Invalid native retrace phase fields')
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
            invalid('Native retrace phase contradicts its observed clock and timing model')
    if previous is not None:
        if type(previous) is not dict:
            invalid('Invalid previous native retrace snapshot')
        previous = validate_retrace_snapshot(previous, epoch=epoch,
                                            virtual_ns=previous.get('virtual-ns'))
        if any(value[key] != previous[key] for key in ('epoch', 'model', 'device', 'device-type', 'console', 'head')):
            invalid('Native retrace device or ownership epoch changed')
        if (value['timing-generation'] < previous['timing-generation']
                or value['virtual-ns'] < previous['virtual-ns']):
            invalid('Native retrace timing generation or clock regressed')
        if value['timing-generation'] == previous['timing-generation'] and any(
                value.get(key) != previous.get(key) for key in
                ('raw', 'timing', 'phase-supported', 'unsupported-reason')):
            invalid('Native retrace timing changed without a new generation')
    return deepcopy(value)


def _native_retrace(vm, value, clock):
    """Validate a current observation and advance only its live VM frontier."""
    try:
        checked = validate_retrace_snapshot(value,
            epoch=clock['virtual_clock']['native']['epoch'], virtual_ns=clock['virtual_ns'],
            previous=getattr(vm, '_retrace_last', None))
    except ValueError as error:
        _invalid(vm, str(error))
    vm._retrace_last = deepcopy(checked)
    return checked


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


def validate_retrace_wait_parameters(*, edge='enter', timeout_ms=1000):
    """Validate literals without observing or changing an owned machine."""
    if type(edge) is not str or edge not in ('enter', 'exit'):
        raise ValueError('Retrace edge must be enter or exit')
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Retrace wait host timeout must be 1..600000 ms')


def _remaining(owner, *, label='Retrace observation'):
    deadline = getattr(owner.vm, 'operation_deadline', None)
    if deadline is None:
        raise ValueError(label + ' requires a bounded owned operation')
    if time.monotonic() >= deadline:
        raise TimeoutError(label + ' host deadline expired')


class QemuRetraceMixin:
    def retrace_wait(self, *, edge='enter', timeout_ms=1000):
        """Continue once toward the strictly next modeled vertical edge.

        The public context owns one lock and absolute host deadline across
        both stopped observations and the native clock budget. A generation
        change invalidates the planned occurrence even when the final register
        tuple has returned to its original value. No stop causes a retry.
        """
        validate_retrace_wait_parameters(edge=edge, timeout_ms=timeout_ms)
        if self.project is None or self.project.db.in_transaction:
            raise ValueError('Retrace wait requires a project outside a caller-owned transaction')
        _configuration(self.vm)
        _remaining(self, label='Retrace wait')
        result = dict(format='fdisbull-retrace-wait-1', context='machine', run=self.run_id,
            edge=edge, outcome='error', synchronized=False, unsupported_reason=None,
            clock_domain='QEMU_CLOCK_VIRTUAL', target_ns=None, window_end_ns=None,
            before=None, after=None, execution=None,
            completed_renderer_update=None, completed_guest_frame=None, guest_frame_id=None,
            scope=('One native clock budget toward the strictly next vertical retrace '
                   'transition of the admitted QEMU VGA integer timing model. Success '
                   'requires an unchanged timing generation and an ordinary timer stop '
                   'inside that absolute occurrence. Renderer completion, completed guest '
                   'drawing, physical scanout and host-time synchronization remain unknown.'))
        stage = 'before'
        try:
            before = self.retrace_observe(timeout_ms=timeout_ms)
            result['before'] = before
            _remaining(self, label='Retrace wait')
            if not before['phase_supported']:
                result.update(outcome='unsupported', unsupported_reason=before['unsupported_reason'])
            else:
                timing = before['timing']
                tick, horizontal = timing['ticks-per-char'], timing['htotal']
                period = tick * timing['total-chars']
                entry = tick * horizontal * timing['vstart']
                exit_ = tick * horizontal * (timing['vend'] + 1)
                width = exit_ - entry
                if entry == 0 and exit_ == period:
                    result.update(outcome='unsupported', unsupported_reason='no-transition')
                else:
                    now = before['observed_ns']
                    phase = entry if edge == 'enter' else exit_ % period
                    delta = (phase - now) % period or period
                    window = width if edge == 'enter' else period - width
                    validate_clock_budget(delta, timeout_ms)
                    if now > _MAX_NS - delta:
                        raise ValueError('Retrace target would overflow signed nanoseconds')
                    target = result['target_ns'] = now + delta
                    if target > _MAX_NS - window:
                        raise ValueError('Retrace window would overflow signed nanoseconds')
                    result['window_end_ns'] = target + window
                    stage = 'execution'
                    execution = self.clock_advance(delta, timeout_ms=timeout_ms)
                    result['execution'] = execution
                    _remaining(self, label='Retrace wait')
                    stage = 'after'
                    after = self.retrace_observe(timeout_ms=timeout_ms)
                    result['after'] = after
                    budget = execution['clock_budget']
                    identity = ('run', 'epoch', 'native_epoch', 'model', 'device',
                                'device_type', 'console', 'head')
                    if (any(before[key] != after[key] for key in identity)
                            or budget['epoch'] != before['epoch']
                            or budget['native_arm']['epoch'] != before['native_epoch']
                            or budget['native']['epoch'] != before['native_epoch']
                            or budget['start_ns'] != now
                            or budget['requested_delta_ns'] != delta
                            or budget['deadline_ns'] != target
                            or budget['stopped_ns'] != after['observed_ns']):
                        _invalid(self.vm, 'Retrace wait lost its owned clock or device identity')
                    if before['timing_generation'] != after['timing_generation']:
                        result['outcome'] = 'timing-changed'
                    elif not clock_timer_stop_is_ordinary(execution):
                        result['outcome'] = 'interrupted'
                    elif not target <= after['observed_ns'] < result['window_end_ns']:
                        result['outcome'] = 'missed-edge'
                    else:
                        result.update(outcome='synchronized', synchronized=True)
            stage = 'journal'
            _remaining(self, label='Retrace wait')
            self._event('machine-retrace-wait', result)
            _remaining(self, label='Retrace wait')
        except BaseException as error:
            # A child may have observed a real native stop or complete phase
            # receipt before its cleanup/journal failed. Keep that evidence
            # inside the composed result rather than replacing it with a plan.
            known = getattr(error, 'result', None)
            if known is not None and known is not result:
                if (stage in ('before', 'after') and isinstance(known, dict)
                        and known.get('format') == 'fdisbull-retrace-observation-1'):
                    result[stage] = known
                elif (result['execution'] is None and isinstance(known, dict)
                        and (isinstance(known.get('session'), dict)
                             and isinstance(known['session'].get('stop_reason'), dict)
                             or 'native_machine_stop' in known)):
                    result['execution'] = known
                elif known is not result['execution']:
                    result['failure_evidence'] = known
            result.update(outcome='error', synchronized=False, failure_stage=stage)
            error.result = result
            raise
        return result

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
