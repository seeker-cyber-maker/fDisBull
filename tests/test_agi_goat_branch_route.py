"""Authored branch boundary guards; no original game or native execution."""
from copy import deepcopy
from hashlib import sha256
import json
import time
from types import SimpleNamespace

import pytest

import examples.agi.verify_goat_branches as module
import examples.agi.verify_goat as goat_module


class AuthoredSession:
    def __init__(self):
        self.memory = bytearray(0x50000)
        self.calls = []
        self.runs = []
        self.register_state = {}

    def registers(self):
        return deepcopy(self.register_state)

    def call(self, method, *args, **kwargs):
        self.calls.append(method)
        raise AssertionError('Rejected effect must not change native control state')

    def run(self, **kwargs):
        self.runs.append(kwargs)
        raise AssertionError('Rejected effect must not resume the guest')


def branch_fixture(monkeypatch, branch='water-refusal', before_motion=2):
    run = object.__new__(module.GoatBranchesRun)
    run.d = AuthoredSession()
    run.cs, run.ds = 0x1000, 0x20000
    run.bp, run.watch, run.effects = 'print-watch', 'effect-watch', []
    run.guest_elapsed, run.journal = 0, []
    run.deadline = time.monotonic() + 10
    files = {}

    class MemoryPath:
        def __init__(self, name=''):
            self.name = name

        def __truediv__(self, name):
            return MemoryPath(name)

        def write_text(self, text):
            files[self.name] = text.encode()

        def read_bytes(self):
            return files[self.name]

    run.root = MemoryPath()

    def read(session, address, size):
        data = bytes(session.memory[address:address+size])
        assert len(data) == size
        return data

    def word(address, value):
        run.d.memory[address:address+2] = value.to_bytes(2, 'little')

    monkeypatch.setattr(module, 'read', read)
    logic, offset, opcode, argument, writer, resume = ((103, 381, 84, 13, 0x6dcb, 0x6dcf)
        if branch == 'water-refusal' else (8, 478, 13, 75, 0x7432, 0x7434))
    code = bytearray(500); code[offset:offset+2] = bytes([opcode, argument])
    resource = SimpleNamespace(logic=logic, code=bytes(code), resource_sha256='authored-logic-' + str(logic))
    run.resources = {logic: resource}
    word(run.ds+0x979, 0x3000)
    run.d.memory[run.ds+0x3002] = logic
    word(run.ds+0x3004, 0x4000)
    run.d.memory[run.ds+0x4000:run.ds+0x4000+len(code)] = code
    word(run.ds+0x963, 0x5000)
    run.expected_effect = {'branch': branch, 'logic': logic, 'offset': offset, 'opcode': opcode,
        'argument': argument, 'address': run.ds+0x5000+43*13+34 if logic == 103 else run.ds+0x112,
        'writer': writer, 'resume': resume, 'before': {'goat_motion': before_motion, 'following': True}}
    state = {'goat_motion': 1, 'water_refused': True, 'following': logic == 103}
    run.state = lambda: deepcopy(state)
    run.d.register_state = {'segments': {'cs': '0x1000', 'ds': '0x2000'},
        'instruction_pointer': hex(resume), 'general': {'esi': hex(0x4000+offset+2),
        'edi': hex(0x5000+43*13), 'ebx': '0x112', 'eax': '0xef'}}
    stop = {'outcome': 'breakpoint', 'guest_elapsed_ms': 0, 'session': {'stop_reason': {
        'breakpoint_id': 'effect-watch', 'data_access': {'access': 'w', 'instruction': {
            'space': 'segmented', 'segment': '0x1000', 'offset': hex(writer)}}}}}
    return run, stop, state, files


@pytest.mark.parametrize('fault', ['foreign-watch', 'read-access', 'linear-writer', 'writer-segment',
    'writer-offset', 'resume-cs', 'resume-ds', 'resume-ip', 'wrong-logic', 'source-crosses-segment',
    'source-byte', 'source-cursor', 'actor', 'before-motion', 'after-motion', 'refusal-flag', 'following'])
def test_refusal_stop_guards_reject_before_trace_or_continuation(monkeypatch, fault):
    run, stop, state, files = branch_fixture(monkeypatch)
    reason = stop['session']['stop_reason']; access = reason['data_access']; regs = run.d.register_state
    if fault == 'foreign-watch': reason['breakpoint_id'] = 'foreign'
    elif fault == 'read-access': access['access'] = 'r'
    elif fault == 'linear-writer': access['instruction']['space'] = 'linear'
    elif fault == 'writer-segment': access['instruction']['segment'] = '0x1001'
    elif fault == 'writer-offset': access['instruction']['offset'] = '0x6dcc'
    elif fault == 'resume-cs': regs['segments']['cs'] = '0x1001'
    elif fault == 'resume-ds': regs['segments']['ds'] = '0x2001'
    elif fault == 'resume-ip': regs['instruction_pointer'] = '0x6dcb'
    elif fault == 'wrong-logic': run.d.memory[run.ds+0x3002] = 8
    elif fault == 'source-crosses-segment': run.d.memory[run.ds+0x3004:run.ds+0x3006] = b'\x00\xff'
    elif fault == 'source-byte': run.d.memory[run.ds+0x4000] ^= 1
    elif fault == 'source-cursor': regs['general']['esi'] = hex(0x4000+381)
    elif fault == 'actor': regs['general']['edi'] = hex(0x5000+43*12)
    elif fault == 'before-motion': run.expected_effect['before']['goat_motion'] = 1
    elif fault == 'after-motion': state['goat_motion'] = 2
    elif fault == 'refusal-flag': state['water_refused'] = False
    elif fault == 'following': state['following'] = False
    with pytest.raises(RuntimeError): run.handle_stop(stop)
    assert run.d.calls == run.d.runs == run.effects == []
    assert files == {} and run.watch == 'effect-watch'


@pytest.mark.parametrize('fault', ['before-following', 'after-following', 'flag-address', 'flag-mask'])
def test_departure_requires_the_observed_following_flag_reset(monkeypatch, fault):
    run, stop, state, files = branch_fixture(monkeypatch, 'water-departure')
    if fault == 'before-following': run.expected_effect['before']['following'] = False
    if fault == 'after-following': state['following'] = True
    if fault == 'flag-address': run.d.register_state['general']['ebx'] = '0x113'
    if fault == 'flag-mask': run.d.register_state['general']['eax'] = '0xdf'
    with pytest.raises(RuntimeError, match='flag write differs'): run.handle_stop(stop)
    assert run.d.calls == run.d.runs == run.effects == [] and files == {}


@pytest.mark.parametrize('before_motion', [0, 2])
def test_refusal_accepts_stopped_or_follow_motion_before_original_wander(monkeypatch, before_motion):
    run, stop, state, files = branch_fixture(monkeypatch, before_motion=before_motion)
    run.d.call = lambda method, *a, **k: run.d.calls.append(method) or {}
    run.trace_effect = lambda branch: {'path': 'authored.trace', 'sha256': 'd' * 64, 'count': 32}
    run.handle_stop(stop)
    proof = json.loads(files['water-refusal-effect.private.json'])
    assert proof['status'] == 'verified' and proof['complete'] is True
    assert proof['before']['goat_motion'] == before_motion and proof['after_access']['goat_motion'] == 1
    assert proof['after_access']['following'] is True
    assert run.d.calls == ['breakpoints.delete'] and run.d.runs == []


@pytest.mark.parametrize('branch', ['water-refusal', 'water-departure'])
def test_lost_effect_trace_preserves_observed_write_without_verifying_continuation(monkeypatch, branch):
    run, stop, state, files = branch_fixture(monkeypatch, branch)
    def call(method, *args, **kwargs):
        run.d.calls.append(method)
        assert method in ('breakpoints.delete', 'trace.start', 'trace.stop')
        return {}
    def lost(**kwargs):
        run.d.runs.append(kwargs)
        raise TimeoutError('trace response lost after dispatch')
    run.d.call, run.d.run = call, lost
    with pytest.raises(TimeoutError, match='trace response lost'): run.handle_stop(stop)
    proof = json.loads(files[branch+'-effect.private.json'])
    trace = json.loads(files[branch+'-trace.private.json'])
    assert proof['native_execution'] is True and proof['status'] == 'incomplete' and proof['complete'] is False
    assert proof['source_logic'] == run.expected_effect['logic']
    assert proof['source_offset'] == run.expected_effect['offset']
    assert proof['writer'] == {'offset': run.expected_effect['writer'], 'resume_offset': run.expected_effect['resume']}
    assert proof['source_binding']['code_offset'] == 0x4000
    assert 'trace response lost' in proof['error']
    assert trace['run'] is None and trace['complete'] is False
    assert run.journal == [{'kind': 'effect-trace', 'attempted': True, 'branch': branch, 'result': None}]
    assert run.d.calls == ['breakpoints.delete', 'trace.start', 'trace.stop'] and len(run.d.runs) == 1
    with pytest.raises(RuntimeError, match='Missing qualified'): run.effect_reference(branch)
    assert len(run.d.runs) == 1


@pytest.mark.parametrize('site, armed', [((103, 375, 1), True), ((103, 413, 2), False),
    ((103, 375, 2), False), ((8, 375, 1), False), ((103, 374, 1), False)])
def test_message_hook_arms_only_the_regular_water_refusal(site, armed, monkeypatch):
    run, stop, state, files = branch_fixture(monkeypatch)
    run.watch = None; calls = []
    run.arm_effect = lambda *args: calls.append(args)
    run.message_observed(dict(zip(('logic', 'source_offset', 'message_id'), site)))
    expected = ('water-refusal', 103, 381, 84, 13, run.ds+0x5000+43*13+34, 0x6dcb, 0x6dcf)
    assert calls == ([expected] if armed else [])
    assert run.d.calls == run.d.runs == []


@pytest.mark.parametrize('prior', ['active-watch', 'prior-effect'])
def test_regular_message_cannot_arm_duplicate_refusal(prior, monkeypatch):
    run, stop, state, files = branch_fixture(monkeypatch)
    if prior == 'prior-effect':
        run.watch = None; run.effects = [{'branch': 'water-refusal', 'complete': True}]
    run.arm_effect = lambda *args: pytest.fail('Duplicate refusal must not arm another watch')
    with pytest.raises(RuntimeError, match='Duplicate refusal'):
        run.message_observed({'logic': 103, 'source_offset': 375, 'message_id': 1})
    assert run.d.calls == run.d.runs == []


@pytest.mark.parametrize('fault', ['engine', 'source-operation'])
def test_effect_watch_requires_original_engine_and_source_operation(fault, monkeypatch):
    run, stop, state, files = branch_fixture(monkeypatch)
    run.watch = None
    monkeypatch.setattr(module, '_ENGINE_LENGTH', 1)
    monkeypatch.setattr(module, '_ENGINE_SHA256', sha256(b'X').hexdigest())
    run.d.memory[run.cs*16] = ord('Y') if fault == 'engine' else ord('X')
    if fault == 'source-operation':
        resource = run.resources[103]; code = bytearray(resource.code); code[382] = 12
        resource.code = bytes(code)
    with pytest.raises(RuntimeError):
        run.arm_effect('water-refusal', 103, 381, 84, 13, run.ds+0x5000+43*13+34, 0x6dcb, 0x6dcf)
    assert run.watch is None and run.d.calls == run.d.runs == []


def test_incomplete_print_observation_does_not_dispatch_branch_hook(monkeypatch):
    run, stop, state, files = branch_fixture(monkeypatch)
    hooks = []; run.messages = []
    run.message_observed = hooks.append
    run.d.call = lambda *args, **kwargs: {}
    run.d.run = lambda **kwargs: {'outcome': 'breakpoint', 'guest_elapsed_ms': 0,
        'session': {'stop_reason': {'breakpoint_id': 'print-watch'}}}
    class IncompleteObserver:
        def __init__(self, *args, **kwargs): pass
        def finish(self, **kwargs): return {'status': 'incomplete', 'error': 'print return unknown', 'stops': []}
        def readback(self): return self.finish()
    monkeypatch.setattr(goat_module, 'AGIDOSPrintObserver', IncompleteObserver)
    with pytest.raises(RuntimeError, match='Original message did not complete'):
        run.advance(1)
    assert hooks == [] and run.effects == []
