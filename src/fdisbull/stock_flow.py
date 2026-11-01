"""Address-free word stock maintenance with explicit realization layouts.

The arithmetic contract contains no executable identity, register or address.
The native layout is caller-supplied evidence, not an automatic source lift.
"""
from __future__ import annotations


PORTS = {'stock': 'i16', 'produced': 'i16', 'population': 'i8',
         'supported': 'i16', 'support_cost': 'i16'}


def maintenance_contract():
    """Stock += produced - 2*population - supported*cost, modulo 2**16.

    Cost is restricted to 1..2. Signed byte population is widened before
    doubling; no assumption about ordinary-game reachability is implied.
    """
    def ref(name):
        return {'var': '$' + name}

    variables = {('$' + k): {'type': v, 'initial': 0} for k, v in
                 {**PORTS, 'new_stock': 'i16', 'consumption': 'i16',
                  'support': 'i16'}.items()}
    program = {'format': 'fdisbull-il-1', 'role': 'uil',
               'variables': variables, 'resources': {}, 'body': [
        {'id': 'widen-population', 'op': 'set', 'var': '$consumption', 'value': ref('population')},
        {'id': 'resident-consumption', 'op': 'add', 'var': '$consumption', 'value': ref('population')},
        {'id': 'support-base', 'op': 'set', 'var': '$support', 'value': ref('supported')},
        {'id': 'support-rate', 'op': 'if',
         'condition': {'op': 'eq', 'left': ref('support_cost'), 'right': 2},
         'then': [{'id': 'double-support', 'op': 'add', 'var': '$support', 'value': ref('supported')}],
         'else': []},
        {'id': 'stock-base', 'op': 'set', 'var': '$new_stock', 'value': ref('stock')},
        {'id': 'production', 'op': 'add', 'var': '$new_stock', 'value': ref('produced')},
        {'id': 'residents', 'op': 'subtract', 'var': '$new_stock', 'value': ref('consumption')},
        {'id': 'support', 'op': 'subtract', 'var': '$new_stock', 'value': ref('support')},
    ]}
    return {'format': 'fdisbull-block-contract-1', 'name': 'stock.maintenance.word16',
            'inputs': dict(PORTS), 'outputs': {'new_stock': 'i16'},
            'domain': {'support_cost': {'min': 1, 'max': 2}},
            'behavior': {'kind': 'uil', 'program': program}}


def maintenance_module(contract_id):
    """One identical invoking UIL over every selected implementation."""
    return {'format': 'fdisbull-module-uil-1', 'role': 'uil',
            'variables': {('$' + k): {'type': v, 'initial': 0}
                          for k, v in {**PORTS, 'new_stock': 'i16'}.items()},
            'resources': {}, 'body': [
                {'id': 'maintain-stock', 'op': 'invoke', 'binding': 'food',
                 'contract': contract_id,
                 'inputs': {k: {'var': '$' + k} for k in PORTS},
                 'outputs': {'new_stock': '$new_stock'}}]}


def native16_adapter(layout, *, record=0, frame=0x9000):
    """Realize the scalar ports in an explicit indexed-record/frame layout.

    record is realization context, not a semantic input. DS and SS occupy
    separate isolated arenas; the native provider guards every read and write.
    """
    fields = {'records', 'stride', 'population_field', 'stock_field', 'produced',
              'supported', 'cost_frame_offset', 'record_frame_offset', 'record_count'}
    if not isinstance(layout, dict) or set(layout) != fields:
        raise ValueError('maintenance layout needs every explicit field')
    if any(type(v) is not int for v in layout.values()) or type(record) is not int or type(frame) is not int:
        raise ValueError('maintenance layout and context must be integers')
    if not 1 <= layout['record_count'] <= 32768 or not 0 <= record < layout['record_count']:
        raise ValueError('record is outside the declared layout')
    if (layout['stride'] < 1 or not 0 <= layout['population_field'] < layout['stride']
            or not 0 <= layout['stock_field'] <= layout['stride'] - 2):
        raise ValueError('record fields must fit the declared stride')
    base = layout['records'] + record * layout['stride']
    locations = {'population': (base + layout['population_field'], 1),
                 'stock': (base + layout['stock_field'], 2),
                 'produced': (layout['produced'], 2), 'supported': (layout['supported'], 2)}
    for address, size in locations.values():
        if not 0 <= address <= 65536 - size:
            raise ValueError('maintenance data port crosses its segment')
    spans = sorted((a, a + n) for a, n in locations.values())
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ValueError('maintenance input ports overlap')
    cost, argument = frame + layout['cost_frame_offset'], frame + layout['record_frame_offset']
    if not 0 <= frame <= 65535 or any(not 0 <= x <= 65534 for x in (cost, argument)):
        raise ValueError('maintenance frame port crosses its segment')
    if abs(cost - argument) < 2:
        raise ValueError('maintenance frame argument overlaps the cost')
    return {'segments': {'cs': 'code', 'ds': 'data', 'es': 'data', 'ss': 'frame'},
            'registers': {'bp': frame},
            'inputs': {**{k: {'segment': 'ds', 'offset': a}
                         for k, (a, _) in locations.items()},
                       'support_cost': {'segment': 'ss', 'base': 'bp',
                                        'displacement': layout['cost_frame_offset']}},
            'outputs': {'new_stock': {'segment': 'ds', 'offset': locations['stock'][0]}},
            'initializers': [{'segment': 'ss', 'offset': argument,
                              'bytes_hex': record.to_bytes(2, 'little').hex()}]}


def decode_state(layout, data, frame_data, *, record=0, frame=0x9000):
    """Read a declared host representation into address-free typed inputs."""
    adapter = native16_adapter(layout, record=record, frame=frame)
    argument = adapter['initializers'][0]['offset']
    if frame_data[argument:argument + 2] != record.to_bytes(2, 'little'):
        raise ValueError('host frame record argument differs from selected record')
    arenas = {'ds': data, 'ss': frame_data}
    result = {}
    for port, typ in PORTS.items():
        binding = adapter['inputs'][port]
        offset = binding.get('offset', frame + binding.get('displacement', 0))
        size = 1 if typ == 'i8' else 2
        raw = arenas[binding['segment']][offset:offset + size]
        if len(raw) != size:
            raise ValueError('incomplete host-state port')
        result[port] = int.from_bytes(raw, 'little', signed=True)
    return result


def commit_state(layout, data, new_stock, *, record=0):
    """Commit only the selected stock word, retaining every other host byte."""
    adapter = native16_adapter(layout, record=record)
    if type(new_stock) is not int or not -32768 <= new_stock <= 32767:
        raise ValueError('new stock must be signed word16')
    offset = adapter['outputs']['new_stock']['offset']
    if len(data) < offset + 2:
        raise ValueError('incomplete host-state output')
    result = bytearray(data)
    result[offset:offset + 2] = new_stock.to_bytes(2, 'little', signed=True)
    return bytes(result)
