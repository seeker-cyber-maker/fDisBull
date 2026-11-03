"""Synthetic host-adapter contract checks; not original-game parity evidence."""
import base64
from copy import deepcopy

import pytest

import fdisbull.agi_host as agi_host
import fdisbull.agi_dos as agi_dos
from fdisbull.agi_dos import (
    AGIDOSMonitor,
    DISPATCH,
    FETCH,
    FAST_FETCH,
    LOGIC_RETURN,
    _CALL_SIGNATURE,
    _ENGINE_LENGTH,
    _SIGNATURE,
    _TABLE,
    _TABLE_EXPECTED,
)
from test_agi_control import loaded, lift


CS = 0x1000
DS = 0x2000
SS = 0x2800
CODE = 0x3000
OBJECTS = 0x4000


def _u16(memory, address, value):
    memory[address:address + 2] = (value & 0xFFFF).to_bytes(2, 'little')


def _put_flag(memory, index, enabled):
    address = DS * 16 + 0x109 + index // 8
    mask = 0x80 >> (index & 7)
    memory[address] = (memory[address] | mask) if enabled else (memory[address] & ~mask)


def _put_object(memory, number, **fields):
    """Write only the deliberately modeled fields in an authored 43-byte row."""
    address = DS * 16 + OBJECTS + number * 43
    row = bytearray(43)
    offsets = {
        'x': (3, 2), 'y': (5, 2), 'prev_x': (0x16, 2), 'prev_y': (0x18, 2),
        'width': (0x1A, 2), 'height': (0x1C, 2), 'view': (7, 1), 'loop': (0x0A, 1),
        'loop_count': (0x0B, 1), 'cel': (0x0E, 1), 'cel_count': (0x0F, 1),
        'step_size': (0x1E, 1), 'direction': (0x21, 1), 'motion': (0x22, 1),
        'cycle': (0x23, 1), 'follow_step': (0x27, 1), 'follow_flag': (0x28, 1),
        'follow_count': (0x29, 1), 'view_ptr': (0x08, 2), 'loop_ptr': (0x0C, 2),
        'cel_ptr': (0x10, 2), 'previous_ptr': (0x12, 2),
    }
    flags = fields.pop('flags', 0)
    for name, value in fields.items():
        offset, size = offsets[name]
        row[offset:offset + size] = int(value & ((1 << (size * 8)) - 1)).to_bytes(size, 'little')
    row[0x25:0x27] = int(flags).to_bytes(2, 'little')
    memory[address:address + 43] = row


class SyntheticDOSSession:
    """Small authored instruction fixture behind the real monitor API boundary."""

    session_id = 'synthetic-agi-host-session'
    run_id = 'synthetic-run'
    runtime_load = 0
    _runtime_epoch = 'synthetic-epoch'
    closed = False

    def __init__(self, resource, *, initial=None, object_fields=None, fail_mode=None):
        self.memory = bytearray(0x50000)
        self.resource = resource
        self.fail_mode = fail_mode
        self.run_calls = 0
        self.print_calls = 0
        self.screenshot_calls = 0
        self.breakpoints = 0
        self.breakpoint_ids = []
        self.state_revision = 0
        self.frame_id = 1
        self.mode_id = 1
        self.memory[CS * 16:CS * 16 + _ENGINE_LENGTH] = bytes(_ENGINE_LENGTH)
        self.memory[CS * 16 + DISPATCH:CS * 16 + DISPATCH + len(_SIGNATURE)] = _SIGNATURE
        self.memory[CS * 16 + 0x02F5:CS * 16 + 0x02F5 + len(_CALL_SIGNATURE)] = _CALL_SIGNATURE
        for opcode, address in _TABLE_EXPECTED.items():
            _u16(self.memory, DS * 16 + _TABLE + opcode * 4, address)
        self.memory[DS * 16 + CODE:DS * 16 + CODE + len(resource.code)] = resource.code
        _u16(self.memory, DS * 16 + 0x963, OBJECTS)
        _u16(self.memory, DS * 16 + 0x12D, 36)
        _u16(self.memory, DS * 16 + 0x139, 1)
        _u16(self.memory, DS * 16 + 0x0FF2, 0)  # No loaded-view list in this fixture.
        _u16(self.memory, DS * 16 + 0x979, 0x5000)
        self.memory[DS*16+0x5002]=resource.logic
        _u16(self.memory, DS*16+0x5004, CODE)
        _u16(self.memory, DS*16+0x5006, CODE)
        _u16(self.memory, SS*16+0x0808, LOGIC_RETURN)
        _u16(self.memory, SS*16+0x080A, 0x5000)
        _put_object(self.memory, 0)
        _put_object(self.memory, 13, **(object_fields or {}))
        for name, value in (initial or {}).items():
            family, index = name[len('$agi_')], int(name[len('$agi_') + 1:])
            if family == 'v':
                self.memory[DS * 16 + 9 + index] = value
            else:
                _put_flag(self.memory, index, value)
        self.register_state = {
            'segments': {'cs': hex(CS), 'ds': hex(DS), 'ss': hex(SS)},
            'instruction_pointer': hex(FETCH),
            'general': {'esi': hex(CODE), 'eax': hex(resource.code[0]), 'esp': hex(0x0800)},
            'flags': '0x0000', 'session_id': self.session_id,
        }

    def registers(self):
        return deepcopy(self.register_state)

    def call(self, method, params=None):
        if method == 'session.status':
            return {'state': 'stopped', 'state_revision': self.state_revision,
                    'frame_id': self.frame_id, 'mode_id': self.mode_id}
        if method == 'memory.read':
            offset = int(params['address']['offset'], 16)
            data = bytes(self.memory[offset:offset + params['length']])
            return {'data_base64': base64.b64encode(data).decode('ascii')}
        if method == 'breakpoints.create':
            self.breakpoints += 1
            self.state_revision += 1
            ident = f'synthetic-bp-{self.breakpoints}'
            self.breakpoint_ids.append(ident)
            return {'breakpoint_id': ident}
        if method == 'breakpoints.delete':
            self.state_revision += 1
            return {}
        raise AssertionError(f'unexpected fake backend call: {method}')

    def _advance(self, offset, opcode):
        code = self.resource.code
        size = {0: 1, 3: 3, 12: 2, 13: 2, 101: 2}.get(opcode)
        if size is None:
            raise AssertionError(f'fixture opcode {opcode} is not implemented')
        if opcode == 3:
            target, value = code[offset + 1], code[offset + 2]
            self.memory[DS * 16 + 9 + target] = value
        elif opcode in (12, 13):
            _put_flag(self.memory, code[offset + 1], opcode == 12)
        elif opcode == 101:
            self.print_calls += 1
            # Authored blocking-print outcome used by the synthetic test only.
            _put_flag(self.memory, 15, False)
            self.memory[DS * 16 + 9 + 21] = 0
        return offset + size

    def run(self, **kwargs):
        self.run_calls += 1
        self.state_revision += 1
        pc = int(self.register_state['instruction_pointer'], 16)
        assert pc in (FETCH, FAST_FETCH)
        offset = int(self.register_state['general']['esi'], 16) - CODE
        opcode = self.resource.code[offset]
        next_offset = self._advance(offset, opcode)
        if opcode == 0:
            self.register_state['instruction_pointer'] = hex(LOGIC_RETURN)
            self.register_state['general']['esp'] = hex(0x080A)
        else:
            self.register_state['instruction_pointer'] = hex(FETCH)
            self.register_state['general']['esi'] = hex(CODE + next_offset)
            self.register_state['general']['eax'] = hex(self.resource.code[next_offset])
        owned = self.breakpoint_ids[:1] if opcode != 0 else self.breakpoint_ids[-1:]
        stop = {'outcome': 'breakpoint', 'session': {'stop_reason': {
            'kind': 'breakpoint', 'breakpoint_id': owned[0] if owned else None}}}
        if self.fail_mode == 'transport_after_action':
            raise TimeoutError('synthetic response lost after action')
        if self.fail_mode == 'partial_after_action':
            return {'outcome': 'guest_time', 'timed_out': False, 'guest_elapsed_ms': 1}
        stop['guest_elapsed_ms'] = 1
        return stop

    def screenshot(self, name, *, hooks):
        self.screenshot_calls += 1
        self.frame_id += 1
        if self.fail_mode == 'screenshot_error':
            raise OSError('synthetic screenshot transport failure')
        return {'artifact': f'synthetic-frame-{self.screenshot_calls}',
                'metadata': {'authored_fixture': True, 'name': name, 'hooks': hooks}}


def make_host(tmp_path, monkeypatch, code, initial=None, *, object_fields=None, fail_mode=None):
    program = loaded(tmp_path, {0: bytes(code)})
    projection = lift(program, initial or {}, control_flow='compact', effect_profile='agi-2.917')
    session = SyntheticDOSSession(program.root, initial=initial, object_fields=object_fields,
                                  fail_mode=fail_mode)
    from hashlib import sha256
    monkeypatch.setattr(agi_dos, '_ENGINE_SHA256',
                        sha256(session.memory[CS * 16:CS * 16 + _ENGINE_LENGTH]).hexdigest())
    monitor = AGIDOSMonitor(session, program.root, cs=CS, ds=DS, code_offset=CODE)
    monkeypatch.setattr(agi_host, 'logic_messages',
                        lambda resource: {resource.resource_sha256: {'1': 'Authored fixture text'}})
    host = agi_host.AGIDOSHostAdapter(monitor, projection, viewdir=tmp_path, volume_dir=tmp_path)
    return host, session, projection


def test_capture_state_decodes_high_bit_first_packed_flags_and_bytes():
    raw_bytes = bytearray(0x137)
    raw_bytes[7] = 0xA5
    raw_bytes[0x100] = 0x81
    raw_bytes[0x101] = 0x80
    raw = {'data_0009_013f_hex': raw_bytes.hex()}

    state = agi_host.capture_state(None, ['$agi_v7', '$agi_f0', '$agi_f6', '$agi_f7', '$agi_f8'], raw)

    assert state == {'$agi_v7': 0xA5, '$agi_f0': True, '$agi_f6': False,
                     '$agi_f7': True, '$agi_f8': True}
    for bad in ('$agi_v256', '$agi_f256', '$agi_f01', '$agi_x1'):
        with pytest.raises(ValueError, match='invalid native AGI scalar'):
            agi_host.capture_state(None, [bad], raw)
    with pytest.raises(ValueError,match='incomplete native AGI scalar capture'):
        agi_host.capture_state(None,['$agi_v0'],{'data_0009_013f_hex':'00'})


def test_changed_initial_snapshot_refuses_without_guest_execution(tmp_path,monkeypatch):
    host,session,_=make_host(tmp_path,monkeypatch,[3,1,42,0],{'$agi_v1':0})
    session.memory[DS*16+10]=7
    result=host.run()
    assert result['status']=='incomplete' and 'initial state changed' in result['error']
    assert result['native_execution'] is False and session.run_calls==0
    assert host.run()==result


def test_native_object_projection_maps_known_fields_and_reports_exclusions(tmp_path, monkeypatch):
    fields = dict(x=-2, y=60, prev_x=10, prev_y=20, width=8, height=9,
                  view=2, loop=1, loop_count=4, cel=3, cel_count=5,
                  step_size=7, direction=6, motion=1, cycle=2,
                  follow_step=8, follow_flag=9, follow_count=10,
                  flags=(1 << 0) | (1 << 5))
    host, session, _ = make_host(tmp_path, monkeypatch, [0])
    _put_object(session.memory,13,**fields)
    actor = host._object(session.memory[DS*16+OBJECTS+13*43:DS*16+OBJECTS+14*43].hex())
    host.context['objects']['13']=actor

    assert {k: actor[k] for k in ('x', 'y', 'prev_x', 'prev_y', 'width', 'height',
                                   'view', 'loop', 'loop_count', 'cel', 'cel_count',
                                   'step_size', 'direction', 'motion', 'cycle',
                                   'follow_step', 'follow_flag', 'follow_count')} == {
        'x': -2, 'y': 60, 'prev_x': 10, 'prev_y': 20, 'width': 8, 'height': 9,
        'view': 2, 'loop': 1, 'loop_count': 4, 'cel': 3, 'cel_count': 5,
        'step_size': 7, 'direction': 6, 'motion': 'wander', 'cycle': 'reverse_loop',
        'follow_step': 8, 'follow_flag': '$agi_f9', 'follow_count': 10,
    }
    assert actor['flags'] == ['drawn', 'cycling']

    model_context = deepcopy(host.context)
    actor_model = model_context['objects']['13']
    actor_model.update(view_replaced=True, prev_width=4, prev_height=3,
                       follow_step=99, follow_flag='$agi_f99', follow_count=88)
    model = {'state': {}, 'effect_context': model_context}
    differences, excluded = host._differences(model, {}, host.context, host.monitor.snapshot())

    assert differences == []
    assert set(excluded) >= {
        'objects.13.view_replaced', 'objects.13.prev_width', 'objects.13.prev_height',
        'objects.13.follow_step', 'objects.13.follow_flag', 'objects.13.follow_count',
    }


def test_unknown_native_motion_and_cycle_are_rejected_not_guessed(tmp_path, monkeypatch):
    program = loaded(tmp_path, {0: b'\0'})
    session = SyntheticDOSSession(program.root, object_fields={'motion': 3})
    from hashlib import sha256
    monkeypatch.setattr(agi_dos, '_ENGINE_SHA256',
                        sha256(session.memory[CS * 16:CS * 16 + _ENGINE_LENGTH]).hexdigest())
    monitor = AGIDOSMonitor(session, program.root, cs=CS, ds=DS, code_offset=CODE)
    projection = lift(program, {}, control_flow='compact', effect_profile='agi-2.917')
    monkeypatch.setattr(agi_host, 'logic_messages', lambda resource: {})

    with pytest.raises(ValueError, match='unsupported native motion/cycle'):
        agi_host.AGIDOSHostAdapter(monitor, projection, viewdir=tmp_path, volume_dir=tmp_path)


def test_object_count_mismatch_is_a_difference_not_verified():
    expected = {
        'contract': agi_host.CONTRACT, 'horizon': 36, 'player_control': True,
        'objects': {'0': {'x': 0}}, 'views': {}, 'loaded_views': [], 'messages': {},
    }
    actual = deepcopy(expected)
    actual['objects']['13'] = {'x': 0}
    model = {'state': {}, 'effect_context': expected}
    raw = {'object_0_hex': bytes(43).hex(), 'object_13_hex': bytes(43).hex()}

    differences, _ = agi_host.AGIDOSHostAdapter._differences(model, {}, actual, raw)

    assert differences, 'object-count/schema disagreement must block a verified result'


def test_native_loaded_view_and_object_pointer_binding_rejects_wrong_cel(tmp_path, monkeypatch):
    program = loaded(tmp_path, {0: b'\0'})
    payload = bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 3, 2, 0, 3, 0, 3, 0])
    viewdir = tmp_path / 'VIEWDIR'
    directory = bytearray(9)
    directory[6:9] = bytes(3)  # View 2, volume 0, offset 0.
    viewdir.write_bytes(directory)
    (tmp_path / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)

    session = SyntheticDOSSession(program.root)
    _u16(session.memory, DS * 16 + 0x0FF2, 0x6000)
    _u16(session.memory, DS * 16 + 0x6000, 0)
    session.memory[DS * 16 + 0x6002] = 2
    _u16(session.memory, DS * 16 + 0x6003, 0x6100)
    session.memory[DS * 16 + 0x6100:DS * 16 + 0x6100 + len(payload)] = payload
    _put_object(session.memory, 13, view=2, loop=0, cel=0, view_ptr=0x6100,
                 loop_ptr=0x6107, cel_ptr=0x610A, loop_count=1, cel_count=1,
                 width=3, height=2)
    from hashlib import sha256
    monkeypatch.setattr(agi_dos, '_ENGINE_SHA256',
                        sha256(session.memory[CS * 16:CS * 16 + _ENGINE_LENGTH]).hexdigest())
    monitor = AGIDOSMonitor(session, program.root, cs=CS, ds=DS, code_offset=CODE)
    projection = lift(program, {}, control_flow='compact', effect_profile='agi-2.917')
    monkeypatch.setattr(agi_host, 'logic_messages', lambda resource: {})
    host = agi_host.AGIDOSHostAdapter(monitor, projection, viewdir=viewdir, volume_dir=tmp_path)

    assert host.context['loaded_views'] == [2]
    assert host.context['views']['2']['loops'] == [[{'width': 3, 'height': 2}]]

    _u16(session.memory, DS * 16 + OBJECTS + 13 * 43 + 0x10, 0x610B)
    with pytest.raises(ValueError, match='cel pointer or geometry differs'):
        host._context(monitor.snapshot())


def test_projection_tampering_is_refused_before_any_guest_step(tmp_path, monkeypatch):
    program = loaded(tmp_path, {0: bytes.fromhex('03010700')})
    projection = lift(program, {'$agi_v1': 0}, control_flow='compact', effect_profile='agi-2.917')
    tampered = deepcopy(projection)
    source_id = next(iter(tampered['block_sources']))
    tampered['block_sources'][source_id]['offset'] += 1
    session = SyntheticDOSSession(program.root, initial={'$agi_v1': 0})
    from hashlib import sha256
    monkeypatch.setattr(agi_dos, '_ENGINE_SHA256',
                        sha256(session.memory[CS * 16:CS * 16 + _ENGINE_LENGTH]).hexdigest())
    monitor = AGIDOSMonitor(session, program.root, cs=CS, ds=DS, code_offset=CODE)
    monkeypatch.setattr(agi_host, 'logic_messages', lambda resource: {})

    with pytest.raises(ValueError, match='projection does not match'):
        agi_host.AGIDOSHostAdapter(monitor, tampered, viewdir=tmp_path, volume_dir=tmp_path)

    assert session.run_calls == 0
    assert session.breakpoints == 0


@pytest.mark.parametrize('failure', ['partial_after_action', 'transport_after_action'])
def test_readback_after_interrupted_host_action_never_replays(tmp_path, monkeypatch, failure):
    initial = {'$agi_f15': False, '$agi_v1': 0, '$agi_v21': 2}
    host, session, _ = make_host(tmp_path, monkeypatch, [101, 1, 3, 1, 42, 0], initial,
                                  fail_mode=failure)

    report = host.run()
    first = host.readback()
    second = host.run()

    assert report['status'] == 'incomplete' and report['recovery_required'] is True
    assert first == second == report
    assert session.print_calls == 1
    assert session.run_calls == 1
    assert report['host_completions'] == []
    assert report['attempts']
    assert report['native_execution'] is (True if failure=='partial_after_action' else None)


def test_screenshot_failure_keeps_completed_handler_and_pending_model_without_replay(tmp_path, monkeypatch):
    initial = {'$agi_f15': False, '$agi_v1': 0, '$agi_v21': 2}
    host, session, _ = make_host(tmp_path, monkeypatch, [101, 1, 3, 1, 42, 0], initial,
                                  fail_mode='screenshot_error')

    report = host.run()
    first = host.readback()
    second = host.run()

    assert report['status'] == 'incomplete' and report['recovery_required'] is True
    assert first == second == report
    assert len(report['host_completions']) == 1
    assert report['host_completions'][0]['frame_status'] == 'failed'
    assert report['model']['status'] == 'pending_host'
    assert session.print_calls == 1 and session.run_calls == 1


def test_successful_host_trial_uses_coherent_post_cleanup_snapshot(tmp_path, monkeypatch):
    host, session, _ = make_host(tmp_path, monkeypatch, [3, 1, 7, 0], {'$agi_v1': 0})

    report = host.run()

    assert report['status'] == 'verified' and report['complete'] is True
    assert report['observed_state']['$agi_v1'] == 7
    assert session.run_calls == 2
    assert session.state_revision > 0
