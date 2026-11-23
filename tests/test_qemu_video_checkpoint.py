"""Authored host sidecars and QMP replies, not native save/restore evidence.

Clock/display/key validators are real; the existing precise-device admission
is stubbed at its public helper. No subprocess or emulator is launched.
"""
from base64 import b64encode, b64decode
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull import qemu_instrumented_checkpoint as checkpoint
from fdisbull.qemu_video_checkpoint import (
    FORMAT, EMPTY_SHA256, I64_MAX, MODE13_MODEL, MODE13_PROFILE,
    validate_video_checkpoint, logical_video_checkpoint, restored_video_info)


def envelope(state):
    text = json.dumps(state, sort_keys=True, separators=(',', ':'))
    return dict(state=text, sha256=hashlib.sha256(text.encode()).hexdigest(), icount=101)


def source_record(state='observing', *, rows=3, complete=True, virtual_ns=None):
    # Independent declared cadence: H=8, P=3200, first raster B=3200.
    # Complete pixels and the subsequent prefix deliberately have different RGB.
    if state != 'observing':
        rows = 0
    if state in ('idle', 'invalidated'):
        complete = False
    start = 6400 if complete else 3200
    prefix = [dict(row=r, **{'intended-ns': start + 2 + 16*r,
                            'actual-ns': start + 3 + 16*r}) for r in range(rows)]
    now = max(6400 if complete else 3100, prefix[-1]['actual-ns'] if prefix else 0)
    if state != 'observing':
        now = 7000
    if virtual_ns is not None:
        now = virtual_ns
    info = {'api-version': 1, 'model': 'qemu-vga-chain4-scanline-v1', 'state': state,
        'epoch': 1, 'virtual-ns': now, 'stream-generation': 0 if state == 'idle' else 4,
        'frame-sequence': 0 if state == 'idle' else 23 if complete else 22,
        'aborted-frames': 0 if state == 'idle' else 3,
        'in-progress': bool(rows), 'rows-sampled': rows}
    if state != 'idle':
        info.update(token='saved-source-owner', device='/machine/vga', **{'start-ns': 10})
    if state == 'observing':
        info['next-deadline-ns'] = start + 2 + 16*rows
    elif state == 'stopped':
        info['stop-ns'] = 6500
    elif state == 'invalidated':
        info['reason'] = 'source-or-generation-changed'
    rgb = b'\x04\x55\xaa' * (320*200) if complete else b''
    partial = b'\x0b\x16\x21' * (320*rows)
    if complete:
        info['frame'] = {'frame-id': 23, 'stream-generation': 4, 'epoch': 1,
            'configuration-generation': 7, 'timing-generation': 9,
            'width': 320, 'height': 200, 'stride': 960, 'pixel-format': 'RGB888',
            'dac-conversion': 'replicate-6-to-8-v1', 'dac-8bit': False,
            'frame-start-ns': 3200, 'period-ns': 3200, 'line-period-ns': 8,
            'first-sample-ns': 3203, 'last-sample-ns': 6387, 'completed-ns': 6387,
            'pixel-sha256': hashlib.sha256(rgb).hexdigest(),
            'rows': [dict(row=r, **{'intended-ns': 3202 + 16*r,
                                   'actual-ns': 3203 + 16*r}) for r in range(200)]}
    live_descriptor = state in ('observing', 'stopped')
    return {'info': info, 'device-path': '' if state == 'idle' else '/machine/vga',
        'console-index': 0, 'configuration-generation': 7 if live_descriptor else 0,
        'timing-generation': 9 if live_descriptor else 0, 'period-ns': 3200 if live_descriptor else 0,
        'line-period-ns': 8 if live_descriptor else 0, 'dac-8bit': False,
        'frame-start-ns': start if state == 'observing' else 0,
        'timer-pending': state == 'observing',
        'timer-expire-ns': info.get('next-deadline-ns', -1),
        'partial-rows': prefix, 'partial-rgb-base64': b64encode(partial).decode(),
        'partial-sha256': hashlib.sha256(partial).hexdigest(),
        'rgb-base64': b64encode(rgb).decode()}


def key_record(epoch=1):
    return {'active': False, 'source-epoch': epoch, 'generation': 0, 'accepted-edges': 0,
        'held': [], 'device-path': '/machine/kbd', 'device-type': 'ps2-kbd',
        'scan-enabled': True, 'scancode-set': 2, 'translated': True, 'modifier-mask': 0,
        'fifo-count': 0, 'fifo-sha256': hashlib.sha256(b'').hexdigest(),
        'controller-status': 0, 'controller-mode': 0, 'controller-pending': 0,
        'controller-obsrc': 0, 'controller-obdata': 0, 'throttle-deadline-ns': -1,
        'fifo-read-pointer': 0, 'fifo-write-pointer': 0, 'fifo-command-pointer': -1,
        'write-command': -1}


def make_state(source=None, *, version=FORMAT):
    source = source_record() if source is None else source
    now = source['info']['virtual-ns']
    value = {'format': version, 'source-epoch': 1, 'virtual-ns': now,
        'clock': {'api-version': 1, 'epoch': 1, 'virtual-ns': now, 'running': False,
            'status': 'paused', 'pending-stop': False, 'budget-supported': True, 'budget-state': 'idle'},
        'audio': {'profile': 'off', 'active': False, 'info': {'epoch': 1},
                  'pcm-base64': '', 'core-base64': ''},
        'display': {'profile': 'off', 'active': False,
            'info': {'api-version': 1, 'epoch': 1, 'state': 'idle', 'virtual-ns': now,
                     'period-ns': 0, 'updates': 0}},
        'retrace': {'profile': 'precise', 'admitted': True, 'device-path': '/machine/vga',
                    'info': {'epoch': 1}, 'configuration': {'epoch': 1}}}
    if version in (checkpoint.FRAME_KEYS_FORMAT, FORMAT):
        value['frame-keys'] = key_record()
    if version == FORMAT:
        value['video-frame'] = deepcopy(source)
    return value


def rebind(state, epoch=2):
    state['source-epoch'] = state['clock']['epoch'] = epoch
    for channel in ('audio', 'display', 'retrace'):
        state[channel]['info']['epoch'] = epoch
    state['retrace']['configuration']['epoch'] = epoch
    if 'frame-keys' in state:
        state['frame-keys']['source-epoch'] = epoch
    if 'video-frame' in state:
        info = state['video-frame']['info']
        info['epoch'] = epoch
        if 'token' in info:
            info['token'] = 'fresh-source-owner'
        if 'frame' in info:
            info['frame']['epoch'] = epoch


class CheckpointPeer:
    def __init__(self, state, *, readback_format=None):
        self.saved = deepcopy(state)
        self.record = envelope(self.saved)
        self.current = deepcopy(state)
        self.current['format'] = readback_format or state['format']
        if self.current['format'] != checkpoint.FORMAT:
            self.current.setdefault('frame-keys', key_record())
        if self.current['format'] == FORMAT:
            self.current.setdefault('video-frame', source_record('idle', virtual_ns=state['virtual-ns']))
        rebind(self.current)
        self.receipt = {'format': FORMAT if state['format'] == FORMAT else
                        checkpoint.FORMAT if self.current['format'] == checkpoint.FORMAT else checkpoint.FRAME_KEYS_FORMAT,
            'new-epoch': 2, 'virtual-ns': state['virtual-ns'], 'retrace-device': '/machine/vga'}
        if 'frame-keys' in self.current:
            self.receipt['frame-key-generation'] = self.current['frame-keys']['generation']
            if self.current['frame-keys']['active']:
                self.receipt['frame-key-token'] = 'fresh-key-owner'
        if state['format'] == FORMAT:
            info = self.current['video-frame']['info']
            self.receipt['video-frame-generation'] = info['stream-generation']
            if info['state'] != 'idle':
                self.receipt['video-frame-token'] = info['token']
        self.qmp = self
        self.qmp_commands = set(checkpoint.COMMANDS) | {'x-fdisbull-query-video-frame'}
        if 'frame-keys' in self.current:
            self.qmp_commands.add('x-fdisbull-query-frame-keys')
        self.machine_configuration = {'clock_profile': {'profile': 'virtual'},
            'audio_profile': {'profile': 'off'}, 'retrace_profile': {'profile': 'precise'}}
        self.calls = []
        self.close_calls = 0
        self.closed = False
        self.before_call = lambda command: None

    def call(self, command, arguments=None, **options):
        self.calls.append((command, deepcopy(arguments), options))
        self.before_call(command)
        if command == checkpoint.PREFIX + 'checkpoint-import':
            assert arguments == {'state': self.record['state']}
            return deepcopy(self.receipt)
        if command == checkpoint.PREFIX + 'checkpoint-status':
            return deepcopy(self.receipt)
        if command == 'x-fdisbull-query-clock':
            return deepcopy(self.current['clock'])
        if command == 'query-replay':
            return dict(mode='none', icount=self.record['icount'])
        if command == 'x-fdisbull-query-frame-keys':
            state = deepcopy(self.current['frame-keys'])
            state['epoch'] = state.pop('source-epoch')
            state.update({'api-version': 1, 'valid': True, 'edge-capacity': 32,
                          'repeat-supported': False, 'foreign-held': []})
            if state['active']:
                state['token'] = 'fresh-key-owner'
            return state
        if command == 'x-fdisbull-query-display':
            return deepcopy(self.current['display']['info'])
        if command == 'x-fdisbull-query-video-frame':
            return deepcopy(self.current['video-frame']['info'])
        if command == checkpoint.PREFIX + 'checkpoint-export':
            assert options == {'max_reply_bytes': 64*1024*1024}
            return dict(envelope(self.current), token='fresh-export-token')
        raise AssertionError(command)

    def close(self):
        self.close_calls += 1
        self.closed = True


@pytest.fixture
def source_peer(monkeypatch):
    monkeypatch.setattr('fdisbull.qemu_retrace.admit_retrace', lambda vm: {'device': '/machine/vga'})
    return CheckpointPeer


@pytest.mark.parametrize('state,rows,complete', [
    ('idle', 0, False), ('observing', 0, False), ('observing', 1, False),
    ('observing', 199, False), ('observing', 0, True), ('observing', 3, True),
    ('observing', 199, True), ('stopped', 0, False), ('stopped', 0, True),
    ('invalidated', 0, False)])
def test_valid_source_shapes_preserve_independent_bounded_images(state, rows, complete):
    value = source_record(state, rows=rows, complete=complete)
    result = validate_video_checkpoint(value, epoch=1, virtual_ns=value['info']['virtual-ns'])
    assert result == value and result is not value and result['info'] is not value['info']
    assert len(b64decode(result['partial-rgb-base64'])) == rows*960
    assert len(b64decode(result['rgb-base64'])) == (192000 if complete else 0)
    if rows and complete:
        assert b64decode(result['partial-rgb-base64'])[:3] == b'\x0b\x16\x21'
        assert b64decode(result['rgb-base64'])[:3] == b'\x04\x55\xaa'
    if not rows:
        assert result['partial-sha256'] == EMPTY_SHA256


def set_path(value, path, item):
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = item


@pytest.mark.parametrize('path,item', [
    (('extra',), 1), (('info', 'extra'), 1), (('info', 'api-version'), True),
    (('info', 'model'), 'renderer'), (('info', 'state'), 'unknown'),
    (('info', 'epoch'), True), (('info', 'epoch'), 2), (('info', 'virtual-ns'), -1),
    (('info', 'stream-generation'), 0), (('info', 'frame-sequence'), -1),
    (('info', 'aborted-frames'), 1 << 64), (('info', 'rows-sampled'), 200),
    (('info', 'in-progress'), False), (('info', 'token'), ''),
    (('info', 'token'), 'x\0y'), (('info', 'token'), '\u00e9'*65),
    (('device-path',), '/foreign/vga'), (('console-index',), False),
    (('configuration-generation',), 8), (('period-ns',), 0), (('line-period-ns',), 3),
    (('dac-8bit',), 0), (('timer-pending',), False), (('timer-expire-ns',), -2),
    (('frame-start-ns',), 6401), (('partial-sha256',), '0'*64),
    (('partial-rgb-base64',), ''), (('rgb-base64',), ''),
    (('partial-rows', 0, 'row'), 1), (('partial-rows', 0, 'actual-ns'), 6401),
    (('partial-rows', 0, 'actual-ns'), 6410),
    (('info', 'frame', 'width'), 319), (('info', 'frame', 'frame-id'), 22),
    (('info', 'frame', 'epoch'), 2), (('info', 'frame', 'dac-conversion'), 'qemu-renderer'),
    (('info', 'frame', 'completed-ns'), 6388),
    (('info', 'frame', 'rows', 0, 'extra'), 0),
    (('info', 'frame', 'rows', 0, 'intended-ns'), 3203),
    (('info', 'frame', 'pixel-sha256'), 'f'*64),
    (('info', 'session_id'), 'historical-host-session'),
])
def test_malformed_source_data_refuses_before_any_native_call(path, item):
    state = make_state()
    set_path(state['video-frame'], path, item)
    vm = CheckpointPeer(state)
    with pytest.raises(ValueError):
        checkpoint.restore(vm, vm.record)
    assert vm.calls == [] and vm.close_calls == 0


@pytest.mark.parametrize('field', ['info', 'timer-expire-ns', 'partial-rows', 'partial-sha256', 'rgb-base64'])
def test_missing_source_field_refuses(field):
    value = source_record()
    del value[field]
    with pytest.raises(ValueError):
        validate_video_checkpoint(value, epoch=1, virtual_ns=6435)


@pytest.mark.parametrize('change', ['invalid-character', 'whitespace', 'suffix', 'extra-row', 'uppercase-hash'])
def test_pixel_encodings_and_extents_are_exact(change):
    value = source_record()
    encoded = value['partial-rgb-base64']
    if change == 'invalid-character': value['partial-rgb-base64'] = '!' + encoded[1:]
    elif change == 'whitespace': value['partial-rgb-base64'] = '\n' + encoded[1:]
    elif change == 'suffix': value['partial-rgb-base64'] += '===='
    elif change == 'extra-row': value['partial-rgb-base64'] = b64encode(b'\0'*3840).decode()
    else: value['partial-sha256'] = value['partial-sha256'].upper()
    with pytest.raises(ValueError):
        validate_video_checkpoint(value, epoch=1, virtual_ns=value['info']['virtual-ns'])


@pytest.mark.parametrize('state', ['idle', 'stopped', 'invalidated'])
@pytest.mark.parametrize('field,item', [('timer-pending', True), ('frame-start-ns', 3200),
                                     ('partial-sha256', '0'*64)])
def test_inactive_progress_and_empty_prefix_are_canonical(state, field, item):
    value = source_record(state)
    value[field] = item
    with pytest.raises(ValueError):
        validate_video_checkpoint(value, epoch=1, virtual_ns=value['info']['virtual-ns'])


def test_completed_rows_may_not_follow_saved_stop_even_before_outer_time():
    value = source_record('stopped')
    value['info']['stop-ns'] = 6386
    assert value['info']['frame']['completed-ns'] == 6387 < value['info']['virtual-ns']
    with pytest.raises(ValueError, match='stop boundary'):
        validate_video_checkpoint(value, epoch=1, virtual_ns=7000)


@pytest.mark.parametrize('phase', ['future', 'due', 'deferred', 'retained-due', 'retained-past'])
def test_intended_and_actual_timer_phase_remain_distinct(phase):
    value = source_record()
    intended = value['info']['next-deadline-ns']
    if phase != 'future':
        value['info']['virtual-ns'] = intended + (0 if phase == 'due' else 3)
    if phase == 'deferred':
        value['timer-expire-ns'] = value['info']['virtual-ns'] + 1
    elif phase == 'retained-due':
        value['timer-expire-ns'] = value['info']['virtual-ns']
    elif phase == 'retained-past':
        value['timer-expire-ns'] = intended + 1
    result = validate_video_checkpoint(value, epoch=1, virtual_ns=value['info']['virtual-ns'])
    assert result['info']['next-deadline-ns'] == intended
    assert result['timer-expire-ns'] == value['timer-expire-ns']


def test_arbitrary_timer_rebase_is_refused():
    value = source_record()
    value['timer-expire-ns'] += 1
    with pytest.raises(ValueError, match='timer phase'):
        validate_video_checkpoint(value, epoch=1, virtual_ns=value['info']['virtual-ns'])


@pytest.mark.parametrize('phase', ['before-intended', 'future-deferral', 'overflow', 'boolean'])
def test_impossible_actual_timer_phase_refuses(phase):
    value = source_record()
    intended = value['info']['next-deadline-ns']
    value['info']['virtual-ns'] = intended + 5
    value['timer-expire-ns'] = {'before-intended': intended - 1,
        'future-deferral': intended + 7, 'overflow': I64_MAX + 1, 'boolean': True}[phase]
    with pytest.raises(ValueError):
        validate_video_checkpoint(value, epoch=1, virtual_ns=value['info']['virtual-ns'])


@pytest.mark.parametrize('expiry', [I64_MAX, I64_MAX-1])
def test_prior_deferral_at_signed_clock_boundary_does_not_overflow(expiry):
    value = source_record(virtual_ns=I64_MAX)
    value['timer-expire-ns'] = expiry
    assert validate_video_checkpoint(value, epoch=1, virtual_ns=I64_MAX) == value


@pytest.mark.parametrize('field', ['configuration-generation', 'timing-generation', 'period-ns', 'line-period-ns'])
def test_descriptor_integer_bounds_refuse(field):
    value = source_record()
    value[field] = 1 << (64 if field.endswith('generation') else 63)
    with pytest.raises(ValueError):
        validate_video_checkpoint(value, epoch=1, virtual_ns=value['info']['virtual-ns'])


def test_row_deadline_overflow_refuses_before_pixel_admission():
    value = source_record(rows=199, complete=False, virtual_ns=I64_MAX)
    value['frame-start-ns'] = I64_MAX - I64_MAX % 3200
    value['info']['next-deadline-ns'] = value['frame-start-ns'] + 2 + 199*16
    value['timer-expire-ns'] = value['info']['next-deadline-ns']
    with pytest.raises(ValueError):
        validate_video_checkpoint(value, epoch=1, virtual_ns=I64_MAX)


def test_logical_comparison_removes_only_source_owner_identities():
    before = source_record()
    after = deepcopy(before)
    after['info']['epoch'] = after['info']['frame']['epoch'] = 2
    after['info']['token'] = 'new-owner'
    assert logical_video_checkpoint(before) == logical_video_checkpoint(after)
    after['timer-expire-ns'] += 1
    assert logical_video_checkpoint(before) != logical_video_checkpoint(after)
    assert before['info']['token'] == 'saved-source-owner'


@pytest.mark.parametrize('state', ['idle', 'observing', 'stopped', 'invalidated'])
def test_restore_adopts_source_only_after_exact_readback_and_clears_startup_caches(source_peer, state):
    vm = source_peer(make_state(source_record(state)))
    archived = deepcopy(vm.record)
    prior = {'_video_frame_token': 'startup-owner', '_video_frame_last': {'frame-sequence': 99999},
             '_video_frame_probe_samples': {(0, 0): [255, 255, 255]}, '_video_frame_owned_rgb': b'old'}
    vm.__dict__.update(prior)
    checked = []
    def verify_unpublished(command):
        if command in (checkpoint.PREFIX+'checkpoint-import', checkpoint.PREFIX+'checkpoint-export'):
            assert not any(name in vm.__dict__ for name in prior)
            checked.append(command)
    vm.before_call = verify_unpublished
    result = checkpoint.restore(vm, vm.record)
    assert checked == [checkpoint.PREFIX+'checkpoint-import', checkpoint.PREFIX+'checkpoint-export']
    assert vm.record == archived and not vm.closed
    assert result['format'] == FORMAT and result['native_epoch'] == 2
    assert '_video_frame_probe_samples' not in vm.__dict__ and '_video_frame_owned_rgb' not in vm.__dict__
    if state == 'idle':
        assert '_video_frame_token' not in vm.__dict__ and result['windows'] == {}
        assert '_video_frame_last' not in vm.__dict__
    else:
        assert vm._video_frame_token == 'fresh-source-owner'
        assert vm._video_frame_last == vm.current['video-frame']['info']
        assert result['windows']['video_frame'] == {'old': 'saved-source-owner', 'new': 'fresh-source-owner'}


@pytest.mark.parametrize('saved,current', [(checkpoint.FORMAT, checkpoint.FORMAT),
    (checkpoint.FORMAT, checkpoint.FRAME_KEYS_FORMAT), (checkpoint.FORMAT, FORMAT),
    (checkpoint.FRAME_KEYS_FORMAT, checkpoint.FRAME_KEYS_FORMAT), (checkpoint.FRAME_KEYS_FORMAT, FORMAT)])
def test_legacy_neutral_upgrades_preserve_archived_record_and_summary(source_peer, saved, current):
    vm = source_peer(make_state(source_record('idle'), version=saved), readback_format=current)
    archived, native_receipt = deepcopy(vm.record), deepcopy(vm.receipt)
    result = checkpoint.restore(vm, vm.record)
    assert vm.record == archived and vm.receipt == native_receipt and not vm.closed
    assert result == dict(format=checkpoint.FORMAT, source_epoch=1, native_epoch=2,
        virtual_ns=7000, windows={}, host_clock_sync_restored=False)
    assert '_video_frame_token' not in vm.__dict__ and '_video_frame_last' not in vm.__dict__


@pytest.mark.parametrize('extra', ['source', 'key-owner', 'key-device-proof'])
def test_legacy_projection_cannot_hide_non_neutral_or_changed_state(source_peer, extra):
    saved = checkpoint.FRAME_KEYS_FORMAT if extra == 'key-device-proof' else checkpoint.FORMAT
    vm = source_peer(make_state(source_record('idle'), version=saved), readback_format=FORMAT)
    if extra == 'source':
        vm.current['video-frame'] = source_record(virtual_ns=7000)
        rebind(vm.current)
    elif extra == 'key-owner':
        vm.current['frame-keys']['generation'] = 1
    else:
        vm.current['frame-keys']['fifo-count'] = 1
    with pytest.raises(DebuggerError):
        checkpoint.restore(vm, vm.record)
    assert vm.closed and '_video_frame_token' not in vm.__dict__


def test_restore_keeps_a_fresh_host_revision_and_mode_lifetime(source_peer):
    from fdisbull.qemu_session_revision import SessionRevision
    old, fresh = SessionRevision(), SessionRevision()
    old.effect(); old.mode(('saved-mode',))
    vm = source_peer(make_state())
    vm.session_revision = fresh
    before = fresh.snapshot()
    checkpoint.restore(vm, vm.record)
    assert vm.session_revision is fresh and fresh.snapshot() == before
    assert fresh.session_id != old.session_id and fresh._mode_id == 0 and fresh._mode_key is None


@pytest.mark.parametrize('change', ['missing-token', 'reused-token', 'extra-token-idle',
    'missing-generation', 'wrong-generation', 'boolean-generation', 'missing-key-generation',
    'wrong-format', 'extra-field', 'same-epoch', 'boolean-epoch', 'boolean-time'])
def test_import_receipt_requires_exact_new_owner_before_source_adoption(source_peer, change):
    source = (source_record('idle', virtual_ns=1) if change == 'boolean-time' else
              source_record('idle') if change == 'extra-token-idle' else source_record())
    state = make_state(source)
    vm = source_peer(state)
    if change == 'missing-token': del vm.receipt['video-frame-token']
    elif change == 'reused-token': vm.receipt['video-frame-token'] = 'saved-source-owner'
    elif change == 'extra-token-idle': vm.receipt['video-frame-token'] = 'unexpected'
    elif change == 'missing-generation': del vm.receipt['video-frame-generation']
    elif change == 'wrong-generation': vm.receipt['video-frame-generation'] += 1
    elif change == 'boolean-generation': vm.receipt['video-frame-generation'] = True
    elif change == 'missing-key-generation': del vm.receipt['frame-key-generation']
    elif change == 'wrong-format': vm.receipt['format'] = checkpoint.FRAME_KEYS_FORMAT
    elif change == 'extra-field': vm.receipt['host-session'] = 'old'
    elif change == 'same-epoch': vm.receipt['new-epoch'] = 1
    elif change == 'boolean-epoch': vm.receipt['new-epoch'] = True
    else: vm.receipt['virtual-ns'] = True
    with pytest.raises(DebuggerError):
        checkpoint.restore(vm, vm.record)
    assert vm.closed and vm.close_calls == 1 and '_video_frame_token' not in vm.__dict__
    assert checkpoint.PREFIX+'checkpoint-export' not in [c[0] for c in vm.calls]


def test_status_is_an_independent_ownership_check(source_peer):
    vm = source_peer(make_state())
    def change_receipt(command):
        if command == checkpoint.PREFIX+'checkpoint-status':
            vm.receipt['video-frame-token'] = 'changed-between-import-and-status'
    vm.before_call = change_receipt
    with pytest.raises(DebuggerError, match='ownership changed'):
        checkpoint.restore(vm, vm.record)
    assert vm.closed and [c[0] for c in vm.calls] == [
        checkpoint.PREFIX+'checkpoint-import', checkpoint.PREFIX+'checkpoint-status']


@pytest.mark.parametrize('field', ['new-epoch', 'virtual-ns', 'frame-key-generation',
                                 'video-frame-generation'])
@pytest.mark.parametrize('scalar', ['bool', 'float'])
def test_status_equal_valued_numeric_types_refuse_before_any_owner_adoption(source_peer, field, scalar):
    state = make_state(source_record('idle', virtual_ns=0))
    rebind(state, epoch=3)
    vm = source_peer(state)
    rebind(vm.current, epoch=1)
    vm.receipt['new-epoch'] = 1
    original_receipt = deepcopy(vm.receipt)
    original_record, original_current = deepcopy(vm.record), deepcopy(vm.current)
    prior = {'_video_frame_token': 'startup-owner', '_video_frame_last': {'frame-sequence': 99999},
             '_video_frame_probe_samples': {(0, 0): [255, 255, 255]}, '_video_frame_owned_rgb': b'old'}
    vm.__dict__.update(prior)
    malformed = bool(original_receipt[field]) if scalar == 'bool' else float(original_receipt[field])
    assert malformed == original_receipt[field] and type(malformed) is not int
    native_call = vm.call
    def independent_status(command, arguments=None, **options):
        reply = native_call(command, arguments, **options)
        if command == checkpoint.PREFIX+'checkpoint-status':
            reply[field] = malformed
        return reply
    vm.call = independent_status
    with pytest.raises(DebuggerError):
        checkpoint.restore(vm, vm.record)
    assert vm.receipt == original_receipt and vm.record == original_record
    assert vm.current == original_current
    assert [call[0] for call in vm.calls] == [
        checkpoint.PREFIX+'checkpoint-import', checkpoint.PREFIX+'checkpoint-status']
    assert vm.closed and vm.close_calls == 1
    assert not any(name in vm.__dict__ for name in prior)
    assert '_frame_key_owner' not in vm.__dict__


def test_status_exact_integer_receipts_allow_zero_fields_and_fresh_epoch_one(source_peer):
    state = make_state(source_record('idle', virtual_ns=0))
    rebind(state, epoch=3)
    vm = source_peer(state)
    rebind(vm.current, epoch=1)
    vm.receipt['new-epoch'] = 1
    expected = deepcopy(vm.receipt)
    for field in ('new-epoch', 'virtual-ns', 'frame-key-generation', 'video-frame-generation'):
        assert type(expected[field]) is int
    result = checkpoint.restore(vm, vm.record)
    assert result['source_epoch'] == 3 and result['native_epoch'] == 1
    assert result['virtual_ns'] == 0 and result['windows'] == {}
    assert vm.receipt == expected and vm.close_calls == 0 and not vm.closed
    assert '_video_frame_token' not in vm.__dict__ and '_video_frame_last' not in vm.__dict__
    assert vm.calls[-1][0] == checkpoint.PREFIX+'checkpoint-export'


@pytest.mark.parametrize('change', ['sequence', 'reason', 'stop', 'query-token', 'query-frame-epoch'])
def test_independent_source_query_must_match_saved_logical_metadata(source_peer, change):
    state = 'invalidated' if change == 'reason' else 'stopped' if change == 'stop' else 'observing'
    vm = source_peer(make_state(source_record(state)))
    info = vm.current['video-frame']['info']
    if change == 'sequence':
        info['frame-sequence'] += 1
        info['frame']['frame-id'] += 1
    elif change == 'reason': info['reason'] = 'another-reason'
    elif change == 'stop': info['stop-ns'] += 1
    elif change == 'query-token': info['token'] = 'unreceipted-token'
    else: info['frame']['epoch'] = 3
    with pytest.raises((ValueError, DebuggerError)):
        checkpoint.restore(vm, vm.record)
    assert vm.closed and '_video_frame_token' not in vm.__dict__
    assert checkpoint.PREFIX+'checkpoint-export' not in [c[0] for c in vm.calls]


@pytest.mark.parametrize('change', ['partial-pixels', 'complete-pixels', 'swap-images',
    'partial-time', 'timer-valid-to-valid', 'export-epoch', 'export-token'])
def test_full_readback_detects_changed_bytes_times_and_owners(source_peer, change):
    saved = source_record(virtual_ns=6460)
    saved['timer-expire-ns'] = 6451  # D=6450; prior deferral at 6450.
    vm = source_peer(make_state(saved))
    archived = deepcopy(vm.record)
    def alter_only_export(command):
        if command != checkpoint.PREFIX+'checkpoint-export':
            return
        current = vm.current['video-frame']
        if change == 'partial-pixels':
            data = bytes([99])*2880
            current['partial-rgb-base64'] = b64encode(data).decode()
            current['partial-sha256'] = hashlib.sha256(data).hexdigest()
        elif change == 'complete-pixels':
            data = bytes([99])*192000
            current['rgb-base64'] = b64encode(data).decode()
            current['info']['frame']['pixel-sha256'] = hashlib.sha256(data).hexdigest()
        elif change == 'swap-images':
            current['partial-rgb-base64'], current['rgb-base64'] = (
                current['rgb-base64'], current['partial-rgb-base64'])
        elif change == 'partial-time': current['partial-rows'][0]['actual-ns'] += 1
        elif change == 'timer-valid-to-valid':
            current['timer-expire-ns'] = 6452  # Both phases are structurally valid.
            assert validate_video_checkpoint(current, epoch=2, virtual_ns=6460) == current
        elif change == 'export-epoch': rebind(vm.current, epoch=3)
        else: current['info']['token'] = 'changed-at-export'
    vm.before_call = alter_only_export
    with pytest.raises((ValueError, DebuggerError)):
        checkpoint.restore(vm, vm.record)
    assert vm.record == archived and vm.closed and vm.close_calls == 1
    assert '_video_frame_token' not in vm.__dict__ and '_video_frame_last' not in vm.__dict__
    assert vm.calls[-1][0] == checkpoint.PREFIX+'checkpoint-export'


@pytest.mark.parametrize('state', ['idle', 'invalidated'])
@pytest.mark.parametrize('extra', ['frame', 'pixels', 'descriptor', 'start'])
def test_inactive_source_cannot_smuggle_usable_image_or_descriptor(state, extra):
    value = source_record(state)
    if extra == 'frame': value['info']['frame'] = source_record()['info']['frame']
    elif extra == 'pixels': value['rgb-base64'] = source_record()['rgb-base64']
    elif extra == 'descriptor': value['configuration-generation'] = 1
    elif state == 'idle': value['info']['start-ns'] = 10
    else: value['info']['next-deadline-ns'] = 7001
    with pytest.raises(ValueError):
        validate_video_checkpoint(value, epoch=1, virtual_ns=7000)


def test_capture_format3_preserves_exact_sidecar_without_adopting_a_source_owner(source_peer):
    from types import SimpleNamespace
    vm = source_peer(make_state())
    vm.current = deepcopy(vm.saved)
    session = SimpleNamespace(vm=vm, close=vm.close,
        _clock_snapshot=lambda: {'counter': {'value': 101},
            'virtual_ns': vm.saved['virtual-ns'], 'virtual_clock': {'native': {'epoch': 1}}})
    record, token = checkpoint.capture(session)
    assert record == vm.record and token == 'fresh-export-token'
    checkpoint.verify_saved(session, record)
    assert [c[0] for c in vm.calls] == [checkpoint.PREFIX+'checkpoint-export']*2
    assert not vm.closed and '_video_frame_token' not in vm.__dict__


@pytest.mark.parametrize('lying_idle', [False, True])
def test_idle_format3_off_profile_uses_exact_readback_without_source_query_or_cache(
        source_peer, lying_idle):
    vm = source_peer(make_state(source_record('idle')))
    vm.machine_configuration['retrace_profile']['profile'] = 'off'
    # The peer retains only the host envelope fields this test exercises. A
    # native off-profile sidecar has its separately validated retrace schema.
    for value in (vm.saved, vm.current):
        value['retrace'] = {'profile': 'off', 'admitted': False}
    vm.record = envelope(vm.saved)
    vm.receipt.pop('retrace-device')
    def guard_and_alter(command):
        assert command != 'x-fdisbull-query-video-frame', 'off-profile source query must not dispatch'
        if lying_idle and command == checkpoint.PREFIX+'checkpoint-export':
            vm.current['video-frame'] = source_record(virtual_ns=7000)
            info = vm.current['video-frame']['info']
            info['epoch'] = info['frame']['epoch'] = 2
            info['token'] = 'unexpected-source-owner'
    vm.before_call = guard_and_alter
    if lying_idle:
        with pytest.raises((ValueError, DebuggerError)):
            checkpoint.restore(vm, vm.record)
        assert vm.closed
    else:
        result = checkpoint.restore(vm, vm.record)
        assert result['windows'] == {} and not vm.closed
    assert '_video_frame_token' not in vm.__dict__ and '_video_frame_last' not in vm.__dict__
    assert vm.calls[-1][0] == checkpoint.PREFIX+'checkpoint-export'


def phased_record(*, complete):
    """An authored initial raster and a partial steady raster, eight ns apart per line."""
    record = source_record(rows=3, complete=complete)
    info = record['info']
    info.update(model=MODE13_MODEL, **{'mode-setup': {'committed-ns': 100,
        'configuration-generation': 7, 'timing-generation': 9}})
    if complete:
        info['frame']['source-phase'] = 0
        # H=8; the second raster samples one physical line later.
        info['next-deadline-ns'] = record['timer-expire-ns'] = 6458
        for r, row in enumerate(record['partial-rows']):
            row.update({'intended-ns': 6410 + 16*r, 'actual-ns': 6411 + 16*r})
        info['virtual-ns'] = 6443
    return record


@pytest.mark.parametrize('complete', [False, True], ids=['initial', 'steady'])
def test_mode_setup_phase_preserves_pending_row_across_owner_rebind(complete):
    record = phased_record(complete=complete)
    info = record['info']
    assert validate_video_checkpoint(record, epoch=1, virtual_ns=info['virtual-ns']) == record
    restored = deepcopy(info)
    restored.update(epoch=9, token='replacement')
    if complete:
        restored['frame']['epoch'] = 9
    assert restored_video_info(record, restored, epoch=9, token='replacement') == restored
    restored['next-deadline-ns'] += 8
    with pytest.raises(ValueError, match='pending raster phase'):
        restored_video_info(record, restored, epoch=9, token='replacement')


@pytest.mark.parametrize('fault', ['unknown-setup', 'stale-generation', 'foreign-phase',
    'boolean-phase', 'wrong-deadline', 'setup-after-first-frame', 'standard-with-phase'])
def test_mode_setup_phase_rejects_inconsistent_saved_raster(fault):
    record = phased_record(complete=True)
    info = record['info']
    if fault == 'unknown-setup':
        del info['mode-setup']
    elif fault == 'stale-generation':
        info['mode-setup']['configuration-generation'] += 1
    elif fault == 'wrong-deadline':
        info['next-deadline-ns'] -= 8
    elif fault == 'setup-after-first-frame':
        info['mode-setup']['committed-ns'] = 3200
    elif fault == 'standard-with-phase':
        info['model'] = 'qemu-vga-chain4-scanline-v1'
    else:
        info['frame']['source-phase'] = True if fault == 'boolean-phase' else 1
    with pytest.raises(ValueError):
        validate_video_checkpoint(record, epoch=1, virtual_ns=info['virtual-ns'])


def test_format5_admits_only_the_selected_checkpoint_profile():
    from fdisbull.qemu_frame_keys import REPEAT_QUERY
    source = phased_record(complete=True)
    state = make_state(source)
    state.update(format=checkpoint.VIDEO_PHASE_FORMAT,
                 **{'frame-key-repeat': {'parameter': 43, 'delay-ns': 500000000,
                     'interval-ns': 91666666, 'deadline-ns': -1}})
    machine = SimpleNamespace(
        qmp_commands=checkpoint.COMMANDS | {'x-fdisbull-query-video-frame', 'x-fdisbull-query-frame-keys',
                                           REPEAT_QUERY},
        machine_configuration={'clock_profile': {'profile': 'virtual'}})
    with pytest.raises(ValueError, match='profile differs'):
        checkpoint.validate(machine, envelope(state))
    machine.machine_configuration['video_source_profile'] = MODE13_PROFILE
    assert checkpoint.validate(machine, envelope(state)) == state
    state['format'] = checkpoint.FRAME_KEY_REPEAT_FORMAT
    with pytest.raises(ValueError, match='model differs'):
        checkpoint.validate(machine, envelope(state))
