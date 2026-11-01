"""Authored pickup/control protocol checks; no original files or native execution."""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

import examples.agi.verify_mushroom as module


class AuthoredSession:
    def __init__(self):
        self.memory = bytearray(0x60000)
        self.calls, self.runs = [], []
        self.register_state = {}
        self.created = 0
        self.stop_fault = False

    def registers(self):
        return deepcopy(self.register_state)

    def call(self, method, params=None):
        self.calls.append((method, deepcopy(params)))
        if method == 'breakpoints.create':
            self.created += 1
            return {'breakpoint_id': f'owned-{self.created}'}
        if method == 'breakpoints.delete':
            return {}
        if method == 'trace.start':
            return {}
        if method == 'trace.read':
            return {'events': [{'kind': 'authored-fetch', 'index': n} for n in range(12)],
                    'next_cursor': None}
        if method == 'trace.stop':
            if self.stop_fault:
                raise OSError('authored trace stop failure')
            return {}
        raise AssertionError(f'Unexpected authored RPC: {method}')

    def run(self, **kwargs):
        self.runs.append(kwargs)
        raise AssertionError('Rejected pickup stop must not resume execution')


def memory_read(session, address, length):
    raw = bytes(session.memory[address:address + length])
    assert len(raw) == length
    return raw


def word(session, address, value):
    session.memory[address:address + 2] = value.to_bytes(2, 'little')


def pickup_run(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'read', memory_read)
    run = object.__new__(module.MushroomRun)
    run.root, run.d, run.report = tmp_path, AuthoredSession(), {}
    run.cs, run.ds = 0x1000, 0x20000
    run.guest_elapsed, run.deadline = 0, time.monotonic() + 30
    run.journal, run.messages, run.inputs = [], [], []
    run.watch, run.watch_kind, run.bp = 'score-watch', 'score', 'print-watch'
    run.trace_active, run.trace_receipt, run.pickup_active = False, None, True
    run.inventory = {'base': 0x1000, 'end': 0x1051, 'stride': 3, 'item': 24,
                     'location_linear': run.ds + 0x104a, 'carried_value': 255}
    code = bytearray(0x19b)
    code[0x195:0x19a] = bytes((5, 3, 1, 92, 24))
    run.resources = {47: SimpleNamespace(code=bytes(code), resource_sha256=sha256(code).hexdigest())}
    word(run.d, run.ds + 0x979, 0x3000)
    run.d.memory[run.ds + 0x3002] = 47
    word(run.d, run.ds + 0x3004, 0x4000)
    run.d.memory[run.ds + 0x4000:run.ds + 0x4000 + len(code)] = code
    run.predicate_proof = {
        'format': 'fdisbull-agi-mushroom-pickup-1', 'status': 'incomplete',
        'complete': False, 'native_execution': False, 'source_logic': 47,
        'source_logic_sha256': run.resources[47].resource_sha256,
        'score_source_offset': 0x195, 'item_source_offset': 0x198,
        'before': {'score': 0, 'item_location': 0}, 'inventory_binding': run.inventory,
    }
    run.state = lambda: {
        'room': 47, 'score': run.d.memory[run.ds + 12],
        'mushroom_carried': run.d.memory[run.inventory['location_linear']] == 255,
    }
    set_phase(run, 'score')
    return run


def set_phase(run, phase):
    run.watch_kind = phase
    run.d.memory[run.ds + 12] = 1
    run.d.memory[run.inventory['location_linear']] = 0 if phase == 'score' else 255
    run.d.register_state = {
        'segments': {'cs': '0x1000', 'ds': '0x2000', 'ss': '0x4000'},
        'instruction_pointer': hex({'score': 0x72de, 'item': 0x7486, 'return': 0x2fa}[phase]),
        'general': {'ebx': '0x3', 'eax': hex(0x419a if phase == 'return' else 1),
                    'esi': '0x4198', 'edi': '0x1048', 'ebp': '0x100',
                    'esp': hex(0x108 if phase == 'return' else 0x100)},
    }
    word(run.d, 0x40000 + 0x106, 0x2fa)
    word(run.d, 0x40000 + 0x108, 0x419a)


def pickup_stop(run):
    reason = {'breakpoint_id': run.watch}
    if run.watch_kind in ('score', 'item'):
        reason['data_access'] = {'access': 'w', 'instruction': {
            'space': 'segmented', 'segment': '0x1000',
            'offset': hex(0x72da if run.watch_kind == 'score' else 0x7482)}}
    return {'outcome': 'breakpoint', 'guest_elapsed_ms': 10,
            'session': {'stop_reason': reason}}


@pytest.mark.parametrize('phase', ['score', 'item', 'return'])
@pytest.mark.parametrize('fault', ['foreign', 'cs', 'ds', 'source', 'source-operation'])
def test_pickup_source_and_stop_guards_never_resume(tmp_path, monkeypatch, phase, fault):
    run = pickup_run(tmp_path, monkeypatch)
    set_phase(run, phase)
    if phase == 'return':
        run.item_frame = (0x4000, 0x100, 0x4000)
    out = pickup_stop(run)
    if fault == 'foreign':
        out['session']['stop_reason']['breakpoint_id'] = 'foreign-owner'
    elif fault in ('cs', 'ds'):
        run.d.register_state['segments'][fault] = '0x1001'
    elif fault == 'source':
        run.d.memory[run.ds + 0x4000] ^= 1
    elif fault == 'source-operation':
        changed = bytearray(run.resources[47].code)
        changed[0x199] = 23
        run.resources[47].code = bytes(changed)
        run.d.memory[run.ds + 0x4000:run.ds + 0x4000 + len(changed)] = changed
    with pytest.raises(RuntimeError):
        run.handle_stop(out)
    assert run.d.runs == [] and run.d.calls == []
    assert run.predicate_proof['complete'] is False


@pytest.mark.parametrize('fault', ['read-access', 'writer', 'resume', 'variable', 'addend',
                                  'cursor', 'score', 'already-carried'])
def test_score_writer_and_operands_must_bind_before_tracing(tmp_path, monkeypatch, fault):
    run = pickup_run(tmp_path, monkeypatch)
    out = pickup_stop(run)
    access = out['session']['stop_reason']['data_access']
    regs = run.d.register_state
    if fault == 'read-access': access['access'] = 'r'
    if fault == 'writer': access['instruction']['offset'] = '0x72db'
    if fault == 'resume': regs['instruction_pointer'] = '0x72da'
    if fault == 'variable': regs['general']['ebx'] = '0x4'
    if fault == 'addend': regs['general']['eax'] = '0x2'
    if fault == 'cursor': regs['general']['esi'] = '0x4195'
    if fault == 'score': run.d.memory[run.ds + 12] = 0
    if fault == 'already-carried': run.d.memory[run.inventory['location_linear']] = 255
    with pytest.raises(RuntimeError): run.handle_stop(out)
    assert run.d.calls == [] and run.d.runs == []
    assert 'score_writer' not in run.predicate_proof


@pytest.mark.parametrize('fault', ['writer', 'resume', 'actor', 'frame', 'return-site', 'cursor', 'item'])
def test_item_write_requires_named_inventory_record_and_original_call_frame(tmp_path, monkeypatch, fault):
    run = pickup_run(tmp_path, monkeypatch)
    set_phase(run, 'item')
    out = pickup_stop(run)
    regs = run.d.register_state
    if fault == 'writer': out['session']['stop_reason']['data_access']['instruction']['offset'] = '0x7483'
    if fault == 'resume': regs['instruction_pointer'] = '0x7482'
    if fault == 'actor': regs['general']['edi'] = '0x104b'
    if fault == 'frame': regs['general']['esp'] = '0x102'
    if fault == 'return-site': word(run.d, 0x40106, 0x2fb)
    if fault == 'cursor': word(run.d, 0x40108, 0x4199)
    if fault == 'item': run.d.memory[run.inventory['location_linear']] = 0
    with pytest.raises(RuntimeError): run.handle_stop(out)
    assert run.d.calls == [] and run.d.runs == []
    assert 'item_writer' not in run.predicate_proof


@pytest.mark.parametrize('fault', ['access', 'ip', 'ss', 'sp', 'ax', 'stack-cursor'])
def test_original_return_must_bind_before_trace_is_accepted(tmp_path, monkeypatch, fault):
    run = pickup_run(tmp_path, monkeypatch)
    set_phase(run, 'return')
    run.item_frame = (0x4000, 0x100, 0x4000)
    out = pickup_stop(run)
    regs = run.d.register_state
    if fault == 'access': out['session']['stop_reason']['data_access'] = {'access': 'w'}
    if fault == 'ip': regs['instruction_pointer'] = '0x2fb'
    if fault == 'ss': regs['segments']['ss'] = '0x4001'
    if fault == 'sp': regs['general']['esp'] = '0x106'
    if fault == 'ax': regs['general']['eax'] = '0x4199'
    if fault == 'stack-cursor': word(run.d, 0x40108, 0x4199)
    with pytest.raises(RuntimeError): run.handle_stop(out)
    assert run.d.calls == [] and run.d.runs == []
    assert 'handler_return' not in run.predicate_proof


def test_authored_score_item_and_return_sequence_only_confirms_after_all_stops(tmp_path, monkeypatch):
    run = pickup_run(tmp_path, monkeypatch)
    for phase in ('score', 'item', 'return'):
        set_phase(run, phase)
        run.handle_stop(pickup_stop(run))
        if phase != 'return': assert run.predicate_proof['complete'] is False
    proof = json.loads((tmp_path / 'mushroom-pickup.private.json').read_text())
    assert proof['status'] == 'verified' and proof['complete'] is True
    assert proof['score_writer']['bx'] == 3 and proof['score_writer']['al'] == 1
    assert proof['item_writer']['di_offset'] == 0x1048
    assert proof['handler_return'] == {'offset': 0x2fa, 'observed': True,
                                       'source_cursor_offset': 0x19a, 'stack_verified': True}
    trace = tmp_path / proof['trace']['path']
    assert sha256(trace.read_bytes()).hexdigest() == proof['trace']['sha256']
    assert json.loads(trace.read_text())['complete'] is True
    assert run.watch is None and run.trace_active is False and run.d.runs == []


def test_lost_route_slice_retains_unknown_attempt_without_resuming(tmp_path, monkeypatch):
    run = pickup_run(tmp_path, monkeypatch)
    primary = TimeoutError('authored lost execution response')
    def lost(**kwargs):
        run.d.runs.append(kwargs)
        run.d.memory[run.inventory['location_linear']] = 255
        raise primary
    run.d.run = lost
    with pytest.raises(TimeoutError) as observed:
        run.advance(20)
    assert observed.value is primary and len(run.d.runs) == 1
    assert run.journal == [{'kind': 'run', 'attempted': True, 'result': None,
                            'error': 'authored lost execution response'}]
    assert run.state()['mushroom_carried'] is True
    assert run.predicate_proof['complete'] is False


@pytest.mark.parametrize('budget', ['guest', 'wall'])
def test_exhausted_budget_never_dispatches_a_native_slice(tmp_path, monkeypatch, budget):
    run = pickup_run(tmp_path, monkeypatch)
    if budget == 'guest': run.guest_elapsed = run.guest_budget_ms
    else: run.deadline = time.monotonic() - 1
    with pytest.raises(RuntimeError, match='budget'): run.advance(10)
    assert run.d.runs == [] and run.journal == []


@pytest.mark.parametrize('fault', [None, 'source', 'handler', 'table', 'bounds', 'record', 'name'])
def test_inventory_binding_reads_live_named_record(tmp_path, monkeypatch, fault):
    session = AuthoredSession()
    cs, ds, base = 0x1000, 0x20000, 0x1000
    (tmp_path / 'OBJECT').write_bytes(b'authored inventory identity')
    monkeypatch.setattr(module, 'OBJECT_SHA256', sha256((tmp_path / 'OBJECT').read_bytes()).hexdigest())
    monkeypatch.setattr(module, 'read', memory_read)
    session.memory[cs * 16 + 0x7601:cs * 16 + 0x7603] = b'\x03\x00'
    session.memory[cs * 16 + 0x7471:cs * 16 + 0x7471 + len(module.GET_HANDLER)] = module.GET_HANDLER
    word(session, ds + 0x78d, 0x7471)
    word(session, ds + 0x969, base); word(session, ds + 0x96b, base + 81)
    word(session, ds + base + 72, 0x133)
    session.memory[ds + base + 0x133:ds + base + 0x13c] = b'mushroom\0'
    if fault == 'source': (tmp_path / 'OBJECT').write_bytes(b'changed authored identity')
    if fault == 'handler': session.memory[cs * 16 + 0x7471] ^= 1
    if fault == 'table': word(session, ds + 0x78d, 0x7472)
    if fault == 'bounds': word(session, ds + 0x96b, base + 80)
    if fault == 'record': word(session, ds + base + 72, 0x134)
    if fault == 'name': session.memory[ds + base + 0x133] = ord('M')
    if fault:
        with pytest.raises(RuntimeError): module.bind_mushroom(session, tmp_path, cs, ds)
    else:
        binding = module.bind_mushroom(session, tmp_path, cs, ds)
        assert binding['item'] == 24 and binding['location_linear'] == ds + base + 74
        assert binding['carried_value'] == 255 and binding['name_offset'] == 0x133
    assert session.calls == [] and session.runs == []


@pytest.mark.parametrize('flags, location', [(False, 0), (False, 255), (True, 0), (True, 255)])
def test_carried_state_uses_the_actual_inventory_byte(tmp_path, monkeypatch, flags, location):
    run = pickup_run(tmp_path, monkeypatch)
    monkeypatch.setattr(module.ClipRun, 'state', lambda self: {'room': 47})
    for flag in (121, 123):
        if flags:
            run.d.memory[run.ds + 0x109 + flag // 8] |= 0x80 >> (flag % 8)
    run.d.memory[run.inventory['location_linear']] = location
    state = module.MushroomRun.state(run)
    assert state['mushroom_carried'] is (location == 255)
    assert state['mushroom_taken'] is flags and state['mushroom_scored'] is flags


@pytest.mark.parametrize('fault', [None, 'room', 'x', 'direction', 'control', 'keyboard', 'moving'])
def test_adjacent_control_requires_bounded_stable_motion_context(tmp_path, monkeypatch, fault):
    run = pickup_run(tmp_path, monkeypatch)
    current = {'room': 1, 'score': 0, 'ego': {'x': 0, 'y': 0, 'direction': 0}, 'control_direction': 0}
    advances, observations = [], []
    run.state = lambda: deepcopy(current)
    def move(key, *, room=None, axis=None, target=None):
        if room is not None: current['room'] = room
        if axis is not None: current['ego'][axis] = target
    def precise(**targets):
        current['ego'].update(targets)
    def press(*args, **kwargs):
        current.update(room=34 if fault == 'room' else 33,
                       control_direction=0 if fault == 'control' else 1)
        current['ego'].update(x=152 if fault == 'x' else 153, y=85,
                              direction=0 if fault == 'direction' else 1)
    def advance(ms):
        advances.append(ms); run.guest_elapsed += ms
        if fault == 'moving': current['ego']['y'] -= 1
    def neutral():
        current['ego']['direction'] = current['control_direction'] = 0
    run.move, run.precise, run.press, run.advance, run.neutral = move, precise, press, advance, neutral
    run.static_path = lambda x, y: current['ego'].update(x=x, y=y)
    run.observe_clip = lambda name: observations.append(name)
    run.safe_state = run.state
    run._idle = lambda: fault != 'keyboard'
    run.capture = lambda: {'format': 'authored-control-capture'}
    if fault is None:
        assert run.route(adjacent_control=True) == {'format': 'authored-control-capture'}
        control = run.report['adjacent_control']
        assert control['complete'] is True
        assert control['result'] == 'bounded-north-request-without-advancement'
        assert control['stable_samples'] == 20 and len(control['samples']) == 21
        assert sum(advances) == 2000
        assert observations == ['control-before', 'control-stopped']
    else:
        with pytest.raises(RuntimeError, match='budget' if fault == 'moving' else 'unknown'):
            run.route(adjacent_control=True)
        assert 'adjacent_control' not in run.report
        assert sum(advances) == (6000 if fault == 'moving' else 0)
    assert run.d.runs == [] and run.d.calls == []


@pytest.mark.parametrize('events', [[], [{'index': 'replacement'}]])
def test_partial_trace_readback_cannot_replace_known_events(tmp_path, monkeypatch, events):
    run = pickup_run(tmp_path, monkeypatch)
    run.handle_stop(pickup_stop(run))
    known = [{'index': 'known'}]
    run.trace_receipt['events'] = deepcopy(known)
    def call(method, params=None):
        assert method == 'trace.read'
        return {'events': events, 'next_cursor': None}
    run.d.call = call
    with pytest.raises(RuntimeError, match='known events'):
        run.retain_trace_readback()
    assert run.trace_receipt['events'] == known
    assert run.predicate_proof['complete'] is False and run.d.runs == []


@pytest.mark.parametrize('fault', ['trace-stop', 'trace-write'])
def test_main_retains_partial_trace_and_known_writes_after_cleanup_or_storage_fault(
        tmp_path, monkeypatch, fault):
    """Storage/cleanup failure must not discard already-read fetch observations."""
    source, root = tmp_path / 'source', tmp_path / 'private-run'
    source.mkdir(); root.mkdir(); (root / 'game').mkdir()
    run = pickup_run(root, monkeypatch)
    report = run.report
    report['source_manifest'] = {'authored': 'identity'}
    original_write = Path.write_text
    failed_once = False
    def write(path, text, *args, **kwargs):
        nonlocal failed_once
        if fault == 'trace-write' and path.name == 'mushroom-trace.private.json' and not failed_once:
            failed_once = True
            raise OSError('authored trace persistence failure')
        return original_write(path, text, *args, **kwargs)
    monkeypatch.setattr(Path, 'write_text', write)
    run.capture = lambda: {'format': 'authored-partial-capture', 'actions': []}
    run.frame = lambda name: None
    def route(*, adjacent_control):
        assert adjacent_control is False
        for phase in ('score', 'item', 'return'):
            set_phase(run, phase)
            if phase == 'return' and fault == 'trace-stop': run.d.stop_fault = True
            run.handle_stop(pickup_stop(run))
        raise AssertionError('Faulted trace must not complete its route')
    run.route = route
    @contextmanager
    def context(*args, **kwargs):
        yield object(), run.d, {}, None, run.frame, report, root / 'game'
    monkeypatch.setattr(module, 'native_game', context)
    monkeypatch.setattr(module, 'MushroomRun', lambda *args: run)
    monkeypatch.setattr('examples.agi.verify_bridge_clip.manifest', lambda path: report['source_manifest'])
    monkeypatch.setattr('sys.argv', ['verify_mushroom.py', '--source', str(source), '--backend',
                                   str(tmp_path / 'unused-backend'), '--output', str(root)])
    with pytest.raises(OSError, match='authored trace'):
        module.main()
    assert run.predicate_proof['complete'] is False
    assert run.predicate_proof['score_writer']['al'] == 1
    assert run.predicate_proof['item_writer']['di_offset'] == 0x1048
    assert run.predicate_proof['handler_return']['observed'] is True
    assert any(method == 'trace.stop' for method, _ in run.d.calls)
    assert run.watch is None and run.d.runs == []
    retained = json.loads((root / 'result.json').read_text())
    assert 'authored trace' in retained['error']
    if fault == 'trace-stop':
        assert any('trace' in item['operation'] for item in retained['persistence_errors'])
    proof = json.loads((root / 'partial-predicate.private.json').read_text())
    assert proof['complete'] is False and proof['handler_return']['observed'] is True
    reference = proof['partial_trace']
    raw = (root / reference['path']).read_bytes()
    assert sha256(raw).hexdigest() == reference['sha256']
    trace = json.loads(raw)
    assert len(trace['events']) == reference['event_count'] == 12
    # A failed stop leaves trace completion unknown. A failed artifact write
    # preserves the already completed read/stop, while the pickup stays partial.
    assert trace['complete'] is (fault == 'trace-write')
