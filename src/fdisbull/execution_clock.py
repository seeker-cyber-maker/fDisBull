"""Pure validation of qualified source-bound virtual-clock observations.

Clock identity and an unchanged stopped bracket establish an observation time.
They do not establish instruction retirement, natural execution timing, guest
input consumption, or causation. Instruction counts remain a separate domain.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re


FORMAT = 'fdisbull-source-clock-1'
DOMAIN = 'QEMU_CLOCK_VIRTUAL'
MAX_NS = (1 << 63) - 1
MAX_COUNTER = (1 << 64) - 1
_IDENTITY = ('run', 'epoch', 'native_epoch')
_CLOCK_FIELDS = frozenset(('format', 'domain', *_IDENTITY, 'virtual_ns',
                           'icount', 'before', 'after'))
_SAMPLE_FIELDS = frozenset(('sequence', 'virtual_ns', 'icount', 'native_epoch'))


def _integer(value, name, minimum=0, maximum=MAX_NS):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer in {minimum}..{maximum}')
    return value


def _run(value):
    if (type(value) is not str or not value.strip() or len(value) > 128
            or any(ord(character) < 32 for character in value)):
        raise ValueError('Source clock run must be a nonempty bounded identifier')
    return value


def _epoch(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{32}', value) is None:
        raise ValueError('Source clock epoch must be 32 lowercase hexadecimal characters')
    return value


def validate_clock(value, *, run=None):
    """Copy an exact, typed, unchanged stopped clock bracket."""
    if (type(value) is not dict or set(value) != _CLOCK_FIELDS
            or value['format'] != FORMAT or value['domain'] != DOMAIN):
        raise ValueError('Invalid source clock format, domain or fields')
    _run(value['run']); _epoch(value['epoch'])
    if run is not None and value['run'] != run:
        raise ValueError('Source clock run differs from its owning trace or witness')
    _integer(value['native_epoch'], 'Source clock native epoch', 1, MAX_COUNTER)
    _integer(value['virtual_ns'], 'Source clock virtual nanoseconds')
    _integer(value['icount'], 'Source clock instruction counter', 0, MAX_COUNTER)
    for name in ('before', 'after'):
        sample = value[name]
        if type(sample) is not dict or set(sample) != _SAMPLE_FIELDS:
            raise ValueError('Source clock bracket requires exact before/after sample fields')
        _integer(sample['sequence'], 'Source clock observation sequence', 1)
        _integer(sample['virtual_ns'], 'Source clock sample virtual nanoseconds')
        _integer(sample['icount'], 'Source clock sample instruction counter', 0, MAX_COUNTER)
        _integer(sample['native_epoch'], 'Source clock sample native epoch', 1, MAX_COUNTER)
        if any(sample[field] != value[field] for field in ('virtual_ns', 'icount', 'native_epoch')):
            raise ValueError('Source clock changed within its stopped observation bracket')
    if value['before']['sequence'] >= value['after']['sequence']:
        raise ValueError('Source clock bracket observation sequence must increase')
    return deepcopy(value)


def validate_clock_order(previous, current, *, allow_same=False):
    """Require one clock identity and ordered, nonregressing observations."""
    before = validate_clock(previous)
    after = validate_clock(current)
    if allow_same and before == after:
        return after
    if any(before[field] != after[field] for field in _IDENTITY):
        raise ValueError('Source clock identity changed within the trace')
    if (after['virtual_ns'] < before['virtual_ns']
            or after['icount'] < before['icount']):
        raise ValueError('Source clock time or instruction counter regressed')
    if after['before']['sequence'] <= before['after']['sequence']:
        raise ValueError('Source clock observation brackets overlap or move backwards')
    return after


def validate_clock_predicate(value):
    """Validate a half-open virtual-time range bound to one owned clock."""
    fields = {'kind', *_IDENTITY, 'start_ns', 'end_ns'}
    if type(value) is not dict or set(value) != fields or value['kind'] != 'virtual-time-range':
        raise ValueError('Virtual-time range requires exact clock identity and interval fields')
    _run(value['run']); _epoch(value['epoch'])
    _integer(value['native_epoch'], 'Virtual-time range native epoch', 1, MAX_COUNTER)
    _integer(value['start_ns'], 'Virtual-time range start')
    _integer(value['end_ns'], 'Virtual-time range end', 0, MAX_NS + 1)
    if value['start_ns'] >= value['end_ns']:
        raise ValueError('Virtual-time interval must be nonempty and half-open')
    return deepcopy(value)


def clock_predicates(predicate):
    """Return validated clock leaves for live or saved-script admission.

    The shared validator bounds depth/node count and rejects malformed Boolean
    trees before this traversal. Import locally to keep this module reusable by
    that validator without an import cycle.
    """
    if predicate is None:
        return []
    from .execution_events import validate_predicate

    checked = validate_predicate(predicate)
    leaves = []

    def visit(value):
        for operator in ('all', 'any'):
            if operator in value:
                for child in value[operator]:
                    visit(child)
                return
        if value.get('kind') == 'virtual-time-range':
            leaves.append(value)

    visit(checked)
    return leaves


def validate_clock_admission(mapping, *, backend, native_epoch):
    """Bind timed rows to the explicit single-CPU virtual launch admission."""
    from .qemu_clock import machine_clock_configuration

    _integer(native_epoch, 'Source clock native epoch', 1, MAX_COUNTER)
    configuration = mapping.get('machine_configuration') if type(mapping) is dict else None
    if (backend != 'qemu-dos' or type(configuration) is not dict
            or type(configuration.get('cpus')) is not int or configuration['cpus'] != 1):
        raise ValueError('Source clocks require the native DOS single-CPU virtual profile')
    profile = configuration.get('clock_profile')
    expected = machine_clock_configuration('virtual', 1)
    try:
        exact = (type(profile) is dict and json.dumps(profile, sort_keys=True, allow_nan=False)
                 == json.dumps(expected, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError):
        exact = False
    if not exact:
        raise ValueError('Source clocks require the exact admitted virtual clock profile')
    admission = configuration.get('native_clock_admission')
    if type(admission) is not dict:
        raise ValueError('Source clock lacks its retained native admission')
    _integer(admission.get('epoch'), 'Admitted native clock epoch', 1, MAX_COUNTER)
    if admission['epoch'] != native_epoch:
        raise ValueError('Source clock native epoch differs from launch admission')


def validate_trace_clocks(document, *, run, backend, mapping=None):
    """Copy homogeneous event clocks and an optional retained final endpoint.

    ``mapping`` is required when admitting a raw trace. Already normalized
    searches can validate the same clock ordering without retaining a second
    copy of the immutable launch configuration.
    """
    clocks, previous, timed = [], None, None
    for event in document['events']:
        if type(event) is not dict:
            raise ValueError('Trace event must be an object')
        present = 'clock' in event
        if timed is not None and present != timed:
            raise ValueError('Trace cannot mix timed and clockless event rows')
        timed = present
        clock = validate_clock(event['clock'], run=run) if present else None
        if clock is not None:
            if previous is not None:
                validate_clock_order(previous, clock)
            previous = clock
        clocks.append(clock)
    collector = document.get('collector')
    stop = collector.get('current_stop') if type(collector) is dict else None
    endpoint = validate_clock(stop['clock'], run=run) if type(stop) is dict and 'clock' in stop else None
    if endpoint is not None:
        if timed is False:
            raise ValueError('A timed trace endpoint cannot follow clockless event rows')
        if previous is not None:
            validate_clock_order(previous, endpoint, allow_same=True)
    admitted = previous if previous is not None else endpoint
    if admitted is not None:
        if backend != 'qemu-dos':
            raise ValueError('Source clocks require the native DOS virtual profile')
        if mapping is not None:
            validate_clock_admission(mapping, backend=backend, native_epoch=admitted['native_epoch'])
    return clocks, endpoint
