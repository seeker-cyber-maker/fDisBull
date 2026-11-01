"""Synthetic shield protocol checks; no original game files or native execution."""
from copy import deepcopy
from hashlib import sha256
import json
import time
from types import SimpleNamespace

import pytest

import examples.agi.verify_leprechaun as module
from test_agi_mushroom_route import AuthoredSession, memory_read, word


def shield_run(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'read', memory_read)
    run = object.__new__(module.CaveRun)
    run.root, run.d, run.report = tmp_path, AuthoredSession(), {}
    run.cs, run.ds = 0x1000, 0x20000
    run.guest_elapsed, run.deadline = 0, time.monotonic() + 30
    run.journal, run.messages, run.inputs = [], [], []
    run.fast_forward = False
    run.watch, run.watch_kind, run.bp = 'shield-watch', 'shield-item', 'print-watch'
    run.trace_active, run.trace_receipt = False, None
    run.inventory = {'base': 0x1000}
    code = bytearray(0x400)
    code[0x3dd:0x3e2] = bytes.fromhex('5c15050308')
    run.resources = {77: SimpleNamespace(code=bytes(code), resource_sha256=sha256(code).hexdigest())}
    word(run.d, run.ds + 0x979, 0x3000)
    run.d.memory[run.ds + 0x3002] = 77
    word(run.d, run.ds + 0x3004, 0x4000)
    run.d.memory[run.ds + 0x4000:run.ds + 0x4400] = code
    run.predicate_proof = {'complete': False, 'status': 'incomplete', 'native_execution': False}
    run.state = lambda: {'score': run.d.memory[run.ds + 12],
                         'inventory_locations': {'21': run.d.memory[run.ds + 0x1041]}}
    set_phase(run, 'item')
    return run


def set_phase(run, phase):
    run.watch_kind = 'shield-' + phase
    run.d.memory[run.ds + 12] = 11 if phase == 'score' else 3
    run.d.memory[run.ds + 0x1041] = 255
    run.d.register_state = {
        'segments': {'cs': '0x1000', 'ds': '0x2000', 'ss': '0x4000'},
        'instruction_pointer': hex({'item': 0x7486, 'return': 0x2fa, 'score': 0x72de}[phase]),
        'general': {'ebx': '0x3', 'eax': hex(0x43df if phase == 'return' else 8),
                    'esi': '0x43e2', 'edi': '0x103f', 'ebp': '0x100',
                    'esp': hex(0x108 if phase == 'return' else 0x100)},
    }
    word(run.d, 0x40106, 0x2fa)
    word(run.d, 0x40108, 0x43df)


def stop(run):
    reason = {'breakpoint_id': run.watch}
    if run.watch_kind != 'shield-return':
        reason['data_access'] = {'access': 'w', 'instruction': {
            'space': 'segmented', 'segment': '0x1000',
            'offset': hex(0x7482 if run.watch_kind == 'shield-item' else 0x72da)}}
    return {'outcome': 'breakpoint', 'guest_elapsed_ms': 10, 'session': {'stop_reason': reason}}


def test_authored_shield_sequence_records_effects_only_after_qualified_stops(tmp_path, monkeypatch):
    run = shield_run(tmp_path, monkeypatch)
    for phase in ('item', 'return', 'score'):
        set_phase(run, phase)
        run.handle_stop(stop(run))
        if phase != 'score':
            assert run.predicate_proof['complete'] is False
            assert run.predicate_proof['known_effects'] == {'score': 3, 'item_location': 255}
    proof = json.loads((tmp_path / 'shield-pickup.private.json').read_text())
    assert proof['complete'] is True and proof['after'] == {'score': 11, 'item_location': 255}
    assert proof['handler_return']['stack_verified'] is True
    trace = tmp_path / proof['trace']['path']
    assert sha256(trace.read_bytes()).hexdigest() == proof['trace']['sha256']
    assert json.loads(trace.read_text())['complete'] is True
    assert run.watch is None and not run.trace_active and run.d.runs == []
    creates = [p for m, p in run.d.calls if m == 'breakpoints.create']
    assert [p['kind'] for p in creates] == ['execution', 'w']


@pytest.mark.parametrize('phase', ['item', 'return', 'score'])
@pytest.mark.parametrize('fault', ['foreign', 'cs', 'ds', 'source', 'source-operation'])
def test_unbound_stop_is_preserved_without_resume(tmp_path, monkeypatch, phase, fault):
    run = shield_run(tmp_path, monkeypatch)
    set_phase(run, phase)
    run.item_frame = (0x4000, 0x100, 0x4000)
    out = stop(run)
    if fault == 'foreign': out['session']['stop_reason']['breakpoint_id'] = 'foreign'
    if fault in ('cs', 'ds'): run.d.register_state['segments'][fault] = '0x1001'
    if fault == 'source': run.d.memory[run.ds + 0x4000] ^= 1
    if fault == 'source-operation':
        changed = bytearray(run.resources[77].code); changed[0x3de] = 20
        run.resources[77].code = bytes(changed)
        run.d.memory[run.ds + 0x4000:run.ds + 0x4400] = changed
    with pytest.raises(RuntimeError): run.handle_stop(out)
    assert run.d.calls == [] and run.d.runs == [] and not run.predicate_proof['complete']


@pytest.mark.parametrize('fault', ['read', 'writer', 'ip', 'record', 'sp', 'return-site', 'cursor', 'item', 'score'])
def test_item_write_requires_original_writer_and_call_frame(tmp_path, monkeypatch, fault):
    run = shield_run(tmp_path, monkeypatch); out = stop(run)
    regs = run.d.register_state
    if fault == 'read': out['session']['stop_reason']['data_access']['access'] = 'r'
    if fault == 'writer': out['session']['stop_reason']['data_access']['instruction']['offset'] = '0x7483'
    if fault == 'ip': regs['instruction_pointer'] = '0x7482'
    if fault == 'record': regs['general']['edi'] = '0x1042'
    if fault == 'sp': regs['general']['esp'] = '0x102'
    if fault == 'return-site': word(run.d, 0x40106, 0x2fb)
    if fault == 'cursor': word(run.d, 0x40108, 0x43de)
    if fault == 'item': run.d.memory[run.ds + 0x1041] = 0
    if fault == 'score': run.d.memory[run.ds + 12] = 11
    with pytest.raises(RuntimeError): run.handle_stop(out)
    assert run.d.calls == [] and run.d.runs == [] and 'item_writer' not in run.predicate_proof


@pytest.mark.parametrize('fault', ['data', 'ip', 'ss', 'sp', 'ax', 'stack'])
def test_return_stop_is_not_interchangeable_with_data_stop(tmp_path, monkeypatch, fault):
    run = shield_run(tmp_path, monkeypatch); set_phase(run, 'return')
    run.item_frame = (0x4000, 0x100, 0x4000); out = stop(run)
    regs = run.d.register_state
    if fault == 'data': out['session']['stop_reason']['data_access'] = {'access': 'w'}
    if fault == 'ip': regs['instruction_pointer'] = '0x2fb'
    if fault == 'ss': regs['segments']['ss'] = '0x4001'
    if fault == 'sp': regs['general']['esp'] = '0x106'
    if fault == 'ax': regs['general']['eax'] = '0x43de'
    if fault == 'stack': word(run.d, 0x40108, 0x43de)
    with pytest.raises(RuntimeError): run.handle_stop(out)
    assert run.d.calls == [] and run.d.runs == [] and 'handler_return' not in run.predicate_proof


@pytest.mark.parametrize('fault', ['read', 'stop', 'empty', 'budget', 'cursor'])
def test_known_effects_survive_incomplete_trace(tmp_path, monkeypatch, fault):
    run = shield_run(tmp_path, monkeypatch)
    for phase in ('item', 'return'):
        set_phase(run, phase); run.handle_stop(stop(run))
    original = run.d.call
    def trace_fault(method, params=None):
        if method == 'trace.read':
            if fault == 'read': raise OSError('lost trace read')
            if fault == 'empty': return {'events': [], 'next_cursor': None}
            if fault == 'budget': return {'events': [{}] * 128, 'next_cursor': None}
            if fault == 'cursor': return {'events': [{}], 'next_cursor': 'more'}
        if method == 'trace.stop' and fault == 'stop': raise OSError('lost trace stop')
        return original(method, params)
    run.d.call = trace_fault
    set_phase(run, 'score')
    with pytest.raises((OSError, RuntimeError)): run.handle_stop(stop(run))
    proof = json.loads((tmp_path / 'shield-pickup.private.json').read_text())
    assert proof['known_effects'] == {'score': 11, 'item_location': 255}
    assert proof['complete'] is False and proof['native_execution'] is False
    assert run.d.runs == []


def test_lost_execution_response_is_never_replayed(tmp_path, monkeypatch):
    run = shield_run(tmp_path, monkeypatch)
    error = TimeoutError('lost execution response')
    def lost(**kwargs):
        run.d.runs.append(kwargs)
        run.d.memory[run.ds + 0x1041] = 255
        raise error
    run.d.run = lost
    with pytest.raises(TimeoutError) as raised: run.advance(20)
    assert raised.value is error and len(run.d.runs) == 1
    assert run.journal == [{'kind': 'run', 'attempted': True, 'result': None}]
    assert not run.predicate_proof['complete']


@pytest.mark.parametrize('fault', ['read', 'writer', 'ip', 'variable', 'addend', 'cursor', 'score', 'item'])
def test_score_write_requires_original_operands_and_effects(tmp_path, monkeypatch, fault):
    run = shield_run(tmp_path, monkeypatch); set_phase(run, 'score'); out = stop(run)
    regs = run.d.register_state
    if fault == 'read': out['session']['stop_reason']['data_access']['access'] = 'r'
    if fault == 'writer': out['session']['stop_reason']['data_access']['instruction']['offset'] = '0x72db'
    if fault == 'ip': regs['instruction_pointer'] = '0x72da'
    if fault == 'variable': regs['general']['ebx'] = '0x4'
    if fault == 'addend': regs['general']['eax'] = '0x7'
    if fault == 'cursor': regs['general']['esi'] = '0x43e1'
    if fault == 'score': run.d.memory[run.ds + 12] = 3
    if fault == 'item': run.d.memory[run.ds + 0x1041] = 0
    with pytest.raises(RuntimeError): run.handle_stop(out)
    assert run.d.calls == [] and run.d.runs == [] and 'score_writer' not in run.predicate_proof


@pytest.mark.parametrize('fault', [None, 'source', 'record', 'name'])
def test_inventory_binds_source_to_live_records_and_names(tmp_path, monkeypatch, fault):
    run = shield_run(tmp_path, monkeypatch); run.source = tmp_path
    decoded = bytearray(200); decoded[:2] = (81).to_bytes(2, 'little')
    for item in (8, 15, 16, 21, 24):
        offset = 90 + item * 3
        decoded[3 + item * 3:5 + item * 3] = offset.to_bytes(2, 'little')
        decoded[3 + offset:3 + offset + 3] = b'x!\0'
        word(run.d, run.ds + 0x1000 + item * 3, offset)
        run.d.memory[run.ds + 0x1000 + offset:run.ds + 0x1000 + offset + 3] = b'x!\0'
    key = b'Avis Durgan'
    raw = bytes(b ^ key[i % len(key)] for i, b in enumerate(decoded))
    (tmp_path / 'OBJECT').write_bytes(raw)
    monkeypatch.setattr(module, 'OBJECT_SHA256', sha256(raw).hexdigest())
    if fault == 'source': (tmp_path / 'OBJECT').write_bytes(raw + b'x')
    if fault == 'record': word(run.d, run.ds + 0x1000 + 21 * 3, 0)
    if fault == 'name': run.d.memory[run.ds + 0x1000 + 90 + 21 * 3] ^= 1
    if fault:
        with pytest.raises(RuntimeError): run.bind_inventory()
        assert 'cave_inventory_binding' not in run.report
    else:
        run.bind_inventory()
        record = run.report['cave_inventory_binding']['records']['21']
        assert record['record_offset'] == 63 and record['location_offset'] == 65
        assert record['name_sha256'] == sha256(b'x!\0').hexdigest()
    assert run.d.calls == [] and run.d.runs == []


@pytest.mark.parametrize('fault', [None, 'room', 'small', 'width', 'view', 'blocks', 'timer', 'step'])
def test_small_walking_is_limited_to_original_exit_state(tmp_path, monkeypatch, fault):
    run = shield_run(tmp_path, monkeypatch); run.samples = []; run.allow_small_walk = True
    state = {'dead': False, 'in_water': False, 'swimming': False, 'room': 78, 'small': True,
             'ego_width': 4, 'ego_view': 60, 'ignore_blocks': True, 'small_timer': 2, 'step_size': 1}
    changes = {'room': ('room', 77), 'small': ('small', False), 'width': ('ego_width', 6),
               'view': ('ego_view', 0), 'blocks': ('ignore_blocks', False),
               'timer': ('small_timer', 1), 'step': ('step_size', 2)}
    if fault:
        key, value = changes[fault]; state[key] = value
    run.state = lambda: deepcopy(state)
    if fault:
        with pytest.raises(RuntimeError): run.safe_state()
    else:
        assert run.safe_state() == state
    assert run.d.calls == [] and run.d.runs == []


def test_lost_execution_response_blocks_later_resume(tmp_path, monkeypatch):
    run = shield_run(tmp_path, monkeypatch)
    def lost(**kwargs):
        run.d.runs.append(kwargs)
        raise TimeoutError('unknown native outcome')
    run.d.run = lost
    with pytest.raises(TimeoutError): run.advance(20)
    with pytest.raises(RuntimeError): run.advance(20)
    assert len(run.d.runs) == 1


def test_saturated_trace_survives_failed_cleanup_readback(tmp_path, monkeypatch):
    run = shield_run(tmp_path, monkeypatch)
    for phase in ('item', 'return'):
        set_phase(run, phase)
        run.handle_stop(stop(run))
    events = [{'kind': 'authored-fetch', 'index': n} for n in range(128)]
    observed_run = {'outcome': 'breakpoint', 'guest_elapsed_ms': 10}
    run.journal.append({'kind': 'run', 'attempted': True, 'result': observed_run})
    original = run.d.call
    reads = 0
    def saturated_then_lost(method, params=None):
        nonlocal reads
        if method == 'trace.read':
            reads += 1
            if reads == 1:
                return {'events': deepcopy(events), 'next_cursor': None}
            raise OSError('lost cleanup trace readback')
        return original(method, params)
    run.d.call = saturated_then_lost
    set_phase(run, 'score')
    with pytest.raises(RuntimeError, match='trace.*incomplete'):
        run.handle_stop(stop(run))
    assert run.trace_active
    with pytest.raises(OSError, match='lost cleanup'):
        run.retain_trace_readback()
    # Match the independent cleanup actions in main: readback failure must not
    # prevent stopping the trace or retaining the already observed evidence.
    run.stop_trace()
    path = tmp_path / 'partial-shield-trace.private.json'
    path.write_text(json.dumps(run.trace_receipt, indent=2) + '\n')
    retained = json.loads(path.read_text())
    proof = json.loads((tmp_path / 'shield-pickup.private.json').read_text())
    assert retained['events'] == events and retained['runs'] == [observed_run]
    assert retained['complete'] is False
    assert proof['known_effects'] == {'score': 11, 'item_location': 255}
    assert proof['complete'] is False and proof['native_execution'] is False
    assert ('trace.stop', None) in run.d.calls and not run.trace_active
    assert reads == 2 and run.d.runs == []
