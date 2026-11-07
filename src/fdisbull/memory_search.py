"""Bounded scalar searches over explicitly identified memory snapshots.

This module neither captures memory nor writes into a target. The caller owns
the bytes, observation context and private artifact storage. Capture identifiers
distinguish observations; the complete context distinguishes source, run, task,
mapping and region. Matching caller-supplied labels is not proof that a backend
observed those identities. In particular, an address alone is never a context.

Returned dictionaries contain metadata, candidate intervals and bounded value
rows, not the snapshot payload. Store payloads separately in the private object
store. SHA-256 fields bind those objects and detect accidental changes; they are
not authentication of arbitrarily reconstructed JSON. A live adapter must load
its own retained artifacts and revalidate context, expected bytes and readback.
"""
from __future__ import annotations

import hashlib
import json


MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_CANDIDATES = 1_048_576
MAX_INTERVALS = 65_536
MAX_RESULT_ROWS = 4096
_MAX_ADDRESS = (1 << 64) - 1
_MAX_DISPLAY_VALUE = (1 << 65) - 1
_MAX_GENERATION = 65_535
_CONTEXT_KEYS = frozenset(('source_sha256', 'run_id', 'address_space', 'region',
                           'task_id', 'mapping_id', 'version_id'))
_SNAPSHOT_KEYS = frozenset(('format', 'context', 'context_sha256', 'capture_id',
                            'captured_at', 'length', 'data_sha256', 'snapshot_sha256'))
_SPEC_KEYS = frozenset(('width', 'signed', 'byteorder', 'stride', 'bias'))
_STATE_KEYS = frozenset(('format', 'spec', 'snapshot_sha256', 'context_sha256',
                         'data_sha256', 'capture_id', 'generation', 'parent_sha256',
                         'previous_snapshot_sha256', 'query', 'total_positions',
                         'candidate_count', 'candidate_ranges', 'candidate_limit',
                         'complete', 'state_sha256'))
_INITIAL_MODES = frozenset(('unknown', 'equal', 'range'))
_REFINE_MODES = frozenset(('equal', 'not_equal', 'changed', 'unchanged',
                           'increased', 'decreased', 'delta'))
_EDIT_CONDITIONS = frozenset(('equal', 'not_equal', 'greater', 'greater_equal',
                              'less', 'less_equal', 'always'))


def _integer(value, name, low=0, high=_MAX_ADDRESS):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _text(value, name, maximum=256):
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f'{name} must be a nonempty string of at most {maximum} characters')
    return value


def _digest(value, name):
    if (type(value) is not str or len(value) != 64
            or any(character not in '0123456789abcdef' for character in value)):
        raise ValueError(f'{name} must be a lowercase SHA-256 digest')
    return value


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _seal(value, field):
    return dict(value, **{field: _sha(_json_bytes(value))})


def _plain_context(value):
    """Reject objects, cycles, huge integers and unbounded metadata before JSON."""
    nodes, characters = 0, 0

    def check(item, depth=0):
        nonlocal nodes, characters
        nodes += 1
        if nodes > 4096 or depth > 12:
            raise ValueError('snapshot context exceeds its metadata budget')
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            _integer(item, 'context integer', -_MAX_ADDRESS, _MAX_ADDRESS)
            return
        if type(item) is str:
            characters += len(item)
            if len(item) > 4096 or characters > 65_536:
                raise ValueError('snapshot context string exceeds its metadata budget')
            return
        if type(item) is list:
            for child in item:
                check(child, depth + 1)
            return
        if type(item) is dict:
            for key, child in item.items():
                _text(key, 'context key', 128)
                characters += len(key)
                if characters > 65_536:
                    raise ValueError('snapshot context keys exceed their metadata budget')
                check(child, depth + 1)
            return
        raise ValueError('snapshot context must contain only bounded JSON values, without floats')

    check(value)
    encoded = _json_bytes(value)
    if len(encoded) > 65_536:
        raise ValueError('snapshot context exceeds 64 KiB of metadata')
    return json.loads(encoded)


def _context(value, length):
    if type(value) is not dict or not _CONTEXT_KEYS <= value.keys():
        raise ValueError('snapshot context requires source/run/address-space/region/task/mapping/version identity')
    result = _plain_context(value)
    _digest(result['source_sha256'], 'context source_sha256')
    for name in ('run_id', 'version_id'):
        if type(result[name]) is int:
            _integer(result[name], 'context ' + name, 1)
        else:
            _text(result[name], 'context ' + name)
    for name in ('address_space', 'task_id', 'mapping_id'):
        _text(result[name], 'context ' + name)
    region = result['region']
    if type(region) is not dict or not {'start', 'length'} <= region.keys():
        raise ValueError('snapshot context region requires numeric start and length')
    start = _integer(region['start'], 'context region.start')
    size = _integer(region['length'], 'context region.length', 1, MAX_SNAPSHOT_BYTES)
    if size != length or start + size > _MAX_ADDRESS + 1:
        raise ValueError('snapshot context region must match the bytes without address overflow')
    return result


def _bytes(data):
    if type(data) is not bytes or not 1 <= len(data) <= MAX_SNAPSHOT_BYTES:
        raise ValueError(f'snapshot must contain immutable bytes, from 1 to {MAX_SNAPSHOT_BYTES} bytes')
    return data


def snapshot_metadata(data, *, context, capture_id, captured_at=None):
    """Describe caller-owned immutable bytes and a fully supplied identity.

    ``context.region.start`` is an integer in the declared address space and
    ``context.region.length`` must equal the supplied byte length. Additional
    context fields participate in identity, including any evidence qualifiers.
    Capture ID and time belong outside context so they can change on each stop.
    No backend observation or allocation-lifetime evidence is invented here.
    """
    _bytes(data)
    identity = _context(context, len(data))
    _text(capture_id, 'capture_id')
    if captured_at is not None:
        _text(captured_at, 'captured_at', 128)
    return _seal(dict(format='fdisbull-memory-snapshot-1', context=identity,
                      context_sha256=_sha(_json_bytes(identity)), capture_id=capture_id,
                      captured_at=captured_at, length=len(data), data_sha256=_sha(data)),
                 'snapshot_sha256')


def validate_snapshot(data, snapshot):
    """Return detached metadata only after verifying all fields against bytes."""
    if type(snapshot) is not dict or snapshot.keys() != _SNAPSHOT_KEYS:
        raise ValueError('snapshot metadata has an unsupported shape')
    if snapshot['format'] != 'fdisbull-memory-snapshot-1':
        raise ValueError('snapshot metadata has an unsupported format')
    _integer(snapshot['length'], 'snapshot length', 1, MAX_SNAPSHOT_BYTES)
    for name in ('context_sha256', 'data_sha256', 'snapshot_sha256'):
        _digest(snapshot[name], 'snapshot ' + name)
    expected = snapshot_metadata(data, context=snapshot['context'],
                                 capture_id=snapshot['capture_id'], captured_at=snapshot['captured_at'])
    if snapshot != expected:
        raise ValueError('snapshot metadata or payload differs from its recorded identity')
    return expected


def _spec(width, signed, byteorder, stride, bias):
    if type(width) is not int or width not in (1, 2, 4, 8):
        raise ValueError('scalar width must be 1, 2, 4 or 8 bytes')
    if type(signed) is not bool:
        raise ValueError('scalar signed must be boolean')
    if type(byteorder) is not str or byteorder not in ('little', 'big'):
        raise ValueError('scalar byteorder must be little or big')
    _integer(stride, 'scalar stride', 1, MAX_SNAPSHOT_BYTES)
    _integer(bias, 'scalar bias', -_MAX_ADDRESS, _MAX_ADDRESS)
    return dict(width=width, signed=signed, byteorder=byteorder, stride=stride, bias=bias)


def _scalar_limits(spec):
    bits = spec['width'] * 8
    return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if spec['signed'] else (0, (1 << bits) - 1)


def _stored_value(value, spec, name):
    """The explicit convention is stored_value = displayed_value + bias."""
    # A displayed value can lie just outside the scalar's storage range. For
    # example, bias=-1 can represent displayed 2**64 using stored 2**64-1.
    _integer(value, name, -_MAX_DISPLAY_VALUE, _MAX_DISPLAY_VALUE)
    stored = value + spec['bias']
    low, high = _scalar_limits(spec)
    if not low <= stored <= high:
        raise ValueError(f'{name} plus bias does not fit the selected scalar; wrapping is not allowed')
    return stored


def _query(mode, spec, *, initial, value=None, minimum=None, maximum=None, delta=None):
    allowed = _INITIAL_MODES if initial else _REFINE_MODES
    if type(mode) is not str or mode not in allowed:
        raise ValueError('unsupported initial search mode' if initial else 'unsupported refinement mode')
    result = dict(mode=mode)
    if mode in ('equal', 'not_equal'):
        if minimum is not None or maximum is not None or delta is not None:
            raise ValueError('value comparison accepts only value')
        result.update(value=value, stored_value=_stored_value(value, spec, 'comparison value'))
    elif mode == 'range':
        if value is not None or delta is not None:
            raise ValueError('range comparison accepts only minimum and maximum')
        low = _stored_value(minimum, spec, 'minimum')
        high = _stored_value(maximum, spec, 'maximum')
        if low > high:
            raise ValueError('range minimum must not exceed maximum')
        result.update(minimum=minimum, maximum=maximum, stored_minimum=low, stored_maximum=high)
    elif mode == 'delta':
        if value is not None or minimum is not None or maximum is not None:
            raise ValueError('delta comparison accepts only delta')
        _integer(delta, 'delta', -_MAX_ADDRESS, _MAX_ADDRESS)
        result['delta'] = delta
    elif any(item is not None for item in (value, minimum, maximum, delta)):
        raise ValueError('this comparison mode does not accept value parameters')
    return result


def _positions(length, spec):
    return max(0, (length - spec['width']) // spec['stride'] + 1)


def _value(data, index, spec):
    start = index * spec['stride']
    return int.from_bytes(data[start:start + spec['width']], spec['byteorder'], signed=spec['signed'])


def _matches(query, current, previous=None):
    mode = query['mode']
    if mode == 'unknown':
        return True
    if mode == 'equal':
        return current == query['stored_value']
    if mode == 'not_equal':
        return current != query['stored_value']
    if mode == 'range':
        return query['stored_minimum'] <= current <= query['stored_maximum']
    if mode == 'changed':
        return current != previous
    if mode == 'unchanged':
        return current == previous
    if mode == 'increased':
        return current > previous
    if mode == 'decreased':
        return current < previous
    # Arithmetic is on decoded Python integers, never modular CPU arithmetic.
    return current - previous == query['delta']


def _indices(ranges):
    for first, stop in ranges:
        yield from range(first, stop)


def _collect(indices, predicate, limit):
    ranges, count = [], 0
    for index in indices:
        if not predicate(index):
            continue
        count += 1
        if count > limit:
            raise ValueError('search candidate limit exceeded; narrow the region or predicate before retrying')
        if ranges and ranges[-1][1] == index:
            ranges[-1][1] = index + 1
        else:
            if len(ranges) >= MAX_INTERVALS:
                raise ValueError('search candidate interval budget exceeded; narrow the region before retrying')
            ranges.append([index, index + 1])
    return ranges, count


def _state(snapshot, spec, query, ranges, count, limit, *, parent=None):
    return _seal(dict(format='fdisbull-memory-search-1', spec=spec, query=query,
                      snapshot_sha256=snapshot['snapshot_sha256'],
                      context_sha256=snapshot['context_sha256'], data_sha256=snapshot['data_sha256'],
                      capture_id=snapshot['capture_id'], total_positions=_positions(snapshot['length'], spec),
                      candidate_count=count, candidate_ranges=ranges, candidate_limit=limit, complete=True,
                      generation=0 if parent is None else parent['generation'] + 1,
                      parent_sha256=None if parent is None else parent['state_sha256'],
                      previous_snapshot_sha256=None if parent is None else parent['snapshot_sha256']),
                 'state_sha256')


def start_search(data, snapshot, *, width=1, signed=False, byteorder='little', stride=1,
                 mode='unknown', value=None, minimum=None, maximum=None, bias=0,
                 max_candidates=MAX_CANDIDATES):
    """Start an exhaustive bounded search; no partial reusable state is returned.

    Index ``i`` denotes byte offset ``i * stride``. Adjacent surviving indices
    are represented as half-open intervals, so a dense unknown-value search
    needs one interval. Every returned state contains *all* surviving candidates;
    candidate or interval-budget overflow raises ValueError instead of silently
    dropping addresses. Result-row pagination is a separate operation.
    """
    metadata = validate_snapshot(data, snapshot)
    spec = _spec(width, signed, byteorder, stride, bias)
    query = _query(mode, spec, initial=True, value=value, minimum=minimum, maximum=maximum)
    limit = _integer(max_candidates, 'max_candidates', 1, MAX_CANDIDATES)
    positions = _positions(len(data), spec)
    if mode == 'unknown':
        if positions > limit:
            raise ValueError('search candidate limit exceeded; narrow the region or choose a value predicate')
        ranges, count = ([[0, positions]] if positions else []), positions
    else:
        ranges, count = _collect(range(positions), lambda index: _matches(query, _value(data, index, spec)), limit)
    return _state(metadata, spec, query, ranges, count, limit)


def validate_search(state, data, snapshot):
    """Verify shape, bounds, checksum and exact current-snapshot binding.

    This validates a retained artifact, not the authorship of arbitrary JSON.
    The parent digest is provenance; the live adapter owns the artifact chain.
    A caller must not replace that chain with a self-declared candidate list.
    """
    metadata = validate_snapshot(data, snapshot)
    if (type(state) is not dict or state.keys() != _STATE_KEYS
            or state['format'] != 'fdisbull-memory-search-1' or state['complete'] is not True):
        raise ValueError('search state has an unsupported or incomplete shape')
    if type(state['spec']) is not dict or state['spec'].keys() != _SPEC_KEYS:
        raise ValueError('search state has an unsupported scalar specification')
    spec = _spec(**state['spec'])
    for name in ('snapshot_sha256', 'context_sha256', 'data_sha256', 'capture_id'):
        if state[name] != metadata[name]:
            raise ValueError('search state belongs to a different snapshot or context')
    generation = _integer(state['generation'], 'search generation', 0, _MAX_GENERATION)
    if generation == 0:
        if state['parent_sha256'] is not None or state['previous_snapshot_sha256'] is not None:
            raise ValueError('initial search state cannot claim a previous state or snapshot')
    else:
        _digest(state['parent_sha256'], 'parent state digest')
        _digest(state['previous_snapshot_sha256'], 'previous snapshot digest')
        if state['previous_snapshot_sha256'] == state['snapshot_sha256']:
            raise ValueError('refined search state requires a different previous snapshot')
    query = state['query']
    if type(query) is not dict or 'mode' not in query or len(query) > 5:
        raise ValueError('search query has an unsupported shape')
    expected_query = _query(query['mode'], spec, initial=generation == 0,
                            value=query.get('value'), minimum=query.get('minimum'),
                            maximum=query.get('maximum'), delta=query.get('delta'))
    if (query.keys() != expected_query.keys()
            or any(type(query[key]) is not type(value) or query[key] != value
                   for key, value in expected_query.items())):
        raise ValueError('search query has altered or unsupported fields')
    positions = _positions(len(data), spec)
    if type(state['total_positions']) is not int or state['total_positions'] != positions:
        raise ValueError('search position bounds differ from the snapshot')
    limit = _integer(state['candidate_limit'], 'candidate_limit', 1, MAX_CANDIDATES)
    count = _integer(state['candidate_count'], 'candidate_count', 0, limit)
    ranges = state['candidate_ranges']
    if type(ranges) is not list or len(ranges) > MAX_INTERVALS:
        raise ValueError('search candidate intervals exceed their shape or interval budget')
    previous_stop, actual_count = -1, 0
    for item in ranges:
        if type(item) is not list or len(item) != 2:
            raise ValueError('each candidate interval requires exactly two integer indices')
        first = _integer(item[0], 'candidate interval start', 0, positions)
        stop = _integer(item[1], 'candidate interval stop', 0, positions)
        if first >= stop or first <= previous_stop:
            raise ValueError('candidate intervals must be ordered, nonoverlapping and maximally joined')
        actual_count += stop - first
        previous_stop = stop
    if actual_count != count:
        raise ValueError('candidate interval count differs from recorded candidate_count')
    if generation == 0 and query['mode'] == 'unknown' and count != positions:
        raise ValueError('unknown initial search must retain every complete scalar position')
    _digest(state['state_sha256'], 'search state digest')
    if _sha(_json_bytes({key: value for key, value in state.items() if key != 'state_sha256'})) != state['state_sha256']:
        raise ValueError('search state checksum differs from its recorded contents')
    # All variable-size objects have already been bounded and type-checked.
    return json.loads(_json_bytes(state))


def refine_search(state, before_data, before_snapshot, after_data, after_snapshot, *,
                  mode, value=None, delta=None, max_candidates=MAX_CANDIDATES):
    """Narrow only previous survivors using a distinct, compatible observation.

    ``delta`` means new minus old in mathematical integers. An unsigned byte
    changing from 255 to 0 therefore has delta -255, not +1. Exact comparisons
    use the initial search's explicit bias; changed/order comparisons operate
    on stored scalar values. Source/run/task/mapping/region changes refuse.
    """
    previous = validate_search(state, before_data, before_snapshot)
    current = validate_snapshot(after_data, after_snapshot)
    if current['context_sha256'] != previous['context_sha256']:
        raise ValueError('memory search context changed; start a separate search for the new identity')
    if current['capture_id'] == previous['capture_id']:
        raise ValueError('refinement requires a new capture_id, not a replayed observation')
    if previous['generation'] >= _MAX_GENERATION:
        raise ValueError('search generation budget exhausted')
    spec = previous['spec']
    query = _query(mode, spec, initial=False, value=value, delta=delta)
    limit = _integer(max_candidates, 'max_candidates', 1, MAX_CANDIDATES)
    ranges, count = _collect(_indices(previous['candidate_ranges']),
                             lambda index: _matches(query, _value(after_data, index, spec),
                                                    _value(before_data, index, spec)), limit)
    return _state(current, spec, query, ranges, count, limit, parent=previous)


def search_results(state, data, snapshot, *, before_data=None, before_snapshot=None,
                   offset=0, limit=64):
    """Return a bounded page without truncating the retained candidate set.

    ``offset`` is a candidate ordinal for pagination, not a byte address. Rows
    report byte offsets and addresses in the supplied address space. Previous
    values are returned only when the exact preceding observation is supplied.
    """
    snapshot = validate_snapshot(data, snapshot)
    checked = validate_search(state, data, snapshot)
    rank = _integer(offset, 'result offset', 0, checked['candidate_count'])
    limit = _integer(limit, 'result limit', 1, MAX_RESULT_ROWS)
    if (before_data is None) != (before_snapshot is None):
        raise ValueError('previous values require both before_data and before_snapshot')
    if before_data is not None:
        previous = validate_snapshot(before_data, before_snapshot)
        if (previous['snapshot_sha256'] != checked['previous_snapshot_sha256']
                or previous['context_sha256'] != checked['context_sha256']):
            raise ValueError('previous values require the exact previous compatible snapshot')
    spec, rows, skip = checked['spec'], [], rank
    for first, stop in checked['candidate_ranges']:
        if skip >= stop - first:
            skip -= stop - first
            continue
        begin = first + skip
        skip = 0
        for index in range(begin, min(stop, begin + limit - len(rows))):
            byte_offset = index * spec['stride']
            current_value = _value(data, index, spec)
            previous_value = _value(before_data, index, spec) if before_data is not None else None
            rows.append(dict(offset=byte_offset,
                             address=hex(snapshot['context']['region']['start'] + byte_offset),
                             value=current_value, displayed_value=current_value - spec['bias'],
                             previous_value=previous_value,
                             previous_displayed_value=None if previous_value is None else previous_value - spec['bias']))
        if len(rows) == limit:
            break
    end = rank + len(rows)
    more = end < checked['candidate_count']
    return dict(format='fdisbull-memory-search-results-1', state_sha256=checked['state_sha256'],
                snapshot_sha256=checked['snapshot_sha256'], candidate_count=checked['candidate_count'],
                search_complete=True, offset=rank, returned=len(rows), rows=rows,
                previous_values_observed=before_data is not None, truncated=more,
                next_offset=end if more else None)


def plan_edit(state, data, snapshot, *, offset, value, condition='equal', compare_value=None):
    """Plan one guarded candidate edit without applying it or running a timer.

    ``value`` and ``compare_value`` use the search's displayed-value convention.
    With the default equality condition and no compare_value, compare against
    the captured scalar itself. A false condition yields an ineligible plan;
    no write is performed in either case. A live consumer must revalidate the
    current task/mapping/context, compare expected bytes, write under an owned
    stopped-target lock, and verify readback. The plan is not a permission grant.
    """
    snapshot = validate_snapshot(data, snapshot)
    checked = validate_search(state, data, snapshot)
    spec = checked['spec']
    byte_offset = _integer(offset, 'edit offset', 0, len(data) - spec['width'])
    index, remainder = divmod(byte_offset, spec['stride'])
    if remainder or not any(first <= index < stop for first, stop in checked['candidate_ranges']):
        raise ValueError('edit offset must identify a surviving complete candidate')
    replacement = _stored_value(value, spec, 'replacement value')
    if type(condition) is not str or condition not in _EDIT_CONDITIONS:
        raise ValueError('unsupported edit condition')
    observed = _value(data, index, spec)
    if condition == 'always':
        if compare_value is not None:
            raise ValueError('always condition does not accept compare_value')
        comparison, matched = None, True
    else:
        if condition == 'equal' and compare_value is None:
            compare_value = observed - spec['bias']
        comparison = _stored_value(compare_value, spec, 'condition compare_value')
        matched = {'equal': observed == comparison, 'not_equal': observed != comparison,
                   'greater': observed > comparison, 'greater_equal': observed >= comparison,
                   'less': observed < comparison, 'less_equal': observed <= comparison}[condition]
    return _seal(dict(format='fdisbull-memory-edit-plan-1', state_sha256=checked['state_sha256'],
                      snapshot_sha256=checked['snapshot_sha256'], context_sha256=checked['context_sha256'],
                      capture_id=checked['capture_id'], context=_plain_context(snapshot['context']), spec=dict(spec),
                      address=hex(snapshot['context']['region']['start'] + byte_offset), offset=byte_offset,
                      length=spec['width'], expected_hex=data[byte_offset:byte_offset + spec['width']].hex(),
                      replacement_hex=replacement.to_bytes(spec['width'], spec['byteorder'], signed=spec['signed']).hex(),
                      requested_displayed_value=value, replacement_value=replacement,
                      condition=dict(mode=condition, compare_value=compare_value,
                                     stored_comparison_value=comparison, observed_value=observed, matched=matched),
                      eligible=matched, status='planned' if matched else 'condition-not-met', write_performed=False,
                      guard_scope='Caller must revalidate live context, expected bytes and readback at an owned stop'),
                 'plan_sha256')
