"""Versioned owned-key sidecars are validated before any native restore."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.qemu_instrumented_checkpoint import _decode, _logical, FORMAT, FRAME_KEYS_FORMAT
from test_qemu_frame_keys import keys, frames, session, project
from test_qemu_video_checkpoint import (FORMAT as VIDEO_FORMAT, key_record,
    make_state, source_record, source_peer)


def state_record(keys):
    native = keys.key_state
    names = ('active','generation','accepted-edges','held','device-path','device-type',
        'scan-enabled','scancode-set','translated','modifier-mask','fifo-count','fifo-sha256',
        'controller-status','controller-mode','controller-pending','controller-obsrc',
        'controller-obdata','throttle-deadline-ns')
    names += ('fifo-read-pointer','fifo-write-pointer','fifo-command-pointer','write-command')
    return dict(format=FRAME_KEYS_FORMAT, **{'source-epoch':1,'virtual-ns':1000},
        clock={},audio={},display={},retrace={},
        **{'frame-keys':dict({name:deepcopy(native[name]) for name in names},**{'source-epoch':1})})


def envelope(state):
    data = json.dumps(state,sort_keys=True,separators=(',',':'))
    return dict(state=data,sha256=hashlib.sha256(data.encode()).hexdigest(),icount=10)


def test_owned_key_checkpoint_requires_its_new_format_and_complete_proof(keys):
    keys.frame_inputs([dict(key='a',pressed=True)])
    state = state_record(keys)
    assert _decode(envelope(state))['frame-keys']['held'] == ['a']
    state['format'] = FORMAT
    with pytest.raises(ValueError,match='format 2'):
        _decode(envelope(state))
    state['format'] = FRAME_KEYS_FORMAT
    del state['frame-keys']
    with pytest.raises(ValueError): _decode(envelope(state))


@pytest.mark.parametrize('field,value',[('held',['a','a']),('source-epoch',2),
    ('fifo-count',257),('throttle-deadline-ns',-2),('active',False)])
def test_corrupt_input_proof_is_refused_without_a_native_load(keys,field,value):
    keys.frame_inputs([dict(key='a',pressed=True)])
    state = state_record(keys)
    state['frame-keys'][field] = value
    with pytest.raises(ValueError): _decode(envelope(state))
    assert not keys.closed and keys.key_state['held'] == ['a']


def test_logical_restore_comparison_preserves_key_and_device_state(keys):
    keys.frame_inputs([dict(key='a',pressed=True)])
    before = state_record(keys)
    after = deepcopy(before)
    after['source-epoch'] = after['frame-keys']['source-epoch'] = 2
    assert _logical(before) == _logical(after)
    after['frame-keys']['modifier-mask'] ^= 1
    assert _logical(before) != _logical(after)


def test_legacy_sidecar_without_frame_keys_remains_readable(keys):
    state = state_record(keys)
    state['format'] = FORMAT
    del state['frame-keys']
    assert _decode(envelope(state))['format'] == FORMAT


@pytest.mark.parametrize('version,has_keys,has_video,accepted', [
    (FORMAT, False, False, True), (FORMAT, True, False, False),
    (FORMAT, False, True, False), (FRAME_KEYS_FORMAT, True, False, True),
    (FRAME_KEYS_FORMAT, False, False, False), (FRAME_KEYS_FORMAT, True, True, False),
    (VIDEO_FORMAT, True, True, True), (VIDEO_FORMAT, False, True, False),
    (VIDEO_FORMAT, True, False, False)])
def test_versioned_key_and_source_presence_matrix(version, has_keys, has_video, accepted):
    state = make_state(source_record('idle'), version=version)
    state.pop('frame-keys', None)
    state.pop('video-frame', None)
    if has_keys: state['frame-keys'] = key_record()
    if has_video: state['video-frame'] = source_record('idle')
    if accepted:
        assert _decode(envelope(state)) == state
    else:
        with pytest.raises(ValueError): _decode(envelope(state))


@pytest.mark.parametrize('field,value', [('source-epoch', 2), ('generation', True),
    ('held', ['a']), ('fifo-sha256', 'X'*64), ('write-command', -2)])
def test_format3_idle_source_still_requires_complete_valid_key_proof(field, value):
    state = make_state(source_record('idle'))
    state['frame-keys'][field] = value
    with pytest.raises(ValueError): _decode(envelope(state))


def test_legacy_empty_key_owner_allows_preserved_nonempty_guest_fifo(source_peer):
    from fdisbull.qemu_instrumented_checkpoint import restore
    vm = source_peer(make_state(source_record('idle'), version=FORMAT),
                     readback_format=VIDEO_FORMAT)
    native = vm.current['frame-keys']
    native.update({'fifo-count': 2, 'fifo-write-pointer': 2,
                   'fifo-sha256': hashlib.sha256(b'authored guest fifo').hexdigest(),
                   'controller-obdata': 37})
    original_record = deepcopy(vm.record)
    original_native = deepcopy(native)
    result = restore(vm, vm.record)
    assert result['format'] == FORMAT and result['windows'] == {}
    assert vm.record == original_record and vm.current['frame-keys'] == original_native
    assert vm._frame_key_owner is None and not vm.closed


@pytest.mark.parametrize('field,value', [('generation', 1), ('accepted-edges', 1),
                                       ('modifier-mask', 1)])
def test_legacy_upgrade_refuses_nonempty_native_key_owner(source_peer, field, value):
    from fdisbull.dosbox_rpc import DebuggerError
    from fdisbull.qemu_instrumented_checkpoint import restore
    vm = source_peer(make_state(source_record('idle'), version=FORMAT),
                     readback_format=VIDEO_FORMAT)
    vm.current['frame-keys'][field] = value
    with pytest.raises(DebuggerError, match='frame key owner'):
        restore(vm, vm.record)
    assert vm.closed and '_video_frame_token' not in vm.__dict__


@pytest.mark.parametrize('current', [FRAME_KEYS_FORMAT, VIDEO_FORMAT], ids=['format2', 'format3'])
def test_legacy_projection_requires_an_advertised_independent_key_query(source_peer, current):
    from fdisbull.dosbox_rpc import DebuggerError
    from fdisbull.qemu_instrumented_checkpoint import PREFIX, restore
    vm = source_peer(make_state(source_record('idle'), version=FORMAT), readback_format=current)
    vm.qmp_commands.remove('x-fdisbull-query-frame-keys')
    original_record, original_current = deepcopy(vm.record), deepcopy(vm.current)
    prior = {'_video_frame_token': 'startup-owner', '_video_frame_last': {'frame-sequence': 99999},
             '_video_frame_probe_samples': {(0, 0): [255, 255, 255]}, '_video_frame_owned_rgb': b'old'}
    vm.__dict__.update(prior)
    with pytest.raises(DebuggerError, match='independent empty frame key owner proof'):
        restore(vm, vm.record)
    assert vm.record == original_record and vm.current == original_current
    assert vm.closed and vm.close_calls == 1
    assert not any(name in vm.__dict__ for name in prior)
    assert '_frame_key_owner' not in vm.__dict__
    assert 'x-fdisbull-query-frame-keys' not in [call[0] for call in vm.calls]
    assert vm.calls[-1][0] == PREFIX+'checkpoint-export'


def test_genuine_format1_restore_preserves_no_key_query_compatibility(source_peer):
    from fdisbull.qemu_instrumented_checkpoint import PREFIX, restore
    vm = source_peer(make_state(source_record('idle'), version=FORMAT), readback_format=FORMAT)
    assert 'x-fdisbull-query-frame-keys' not in vm.qmp_commands
    original_record = deepcopy(vm.record)
    result = restore(vm, vm.record)
    assert vm.record == original_record and vm.close_calls == 0 and not vm.closed
    assert result == dict(format=FORMAT, source_epoch=1, native_epoch=2,
        virtual_ns=7000, windows={}, host_clock_sync_restored=False)
    assert 'x-fdisbull-query-frame-keys' not in [call[0] for call in vm.calls]
    assert '_frame_key_owner' not in vm.__dict__ and '_video_frame_token' not in vm.__dict__
    assert vm.calls[-1][0] == PREFIX+'checkpoint-export'


@pytest.mark.parametrize('current', [FRAME_KEYS_FORMAT, VIDEO_FORMAT], ids=['format2', 'format3'])
def test_legacy_projection_accepts_independently_verified_empty_native_keys(source_peer, current):
    from fdisbull.qemu_instrumented_checkpoint import PREFIX, restore
    vm = source_peer(make_state(source_record('idle'), version=FORMAT), readback_format=current)
    original_record, original_current = deepcopy(vm.record), deepcopy(vm.current)
    def require_query_before_export(command):
        if command == PREFIX+'checkpoint-export':
            assert [call[0] for call in vm.calls].count('x-fdisbull-query-frame-keys') == 1
    vm.before_call = require_query_before_export
    result = restore(vm, vm.record)
    assert vm.record == original_record and vm.current == original_current
    assert result['format'] == FORMAT and result['windows'] == {}
    assert vm._frame_key_owner is None and vm.close_calls == 0 and not vm.closed
    assert '_video_frame_token' not in vm.__dict__ and '_video_frame_last' not in vm.__dict__


@pytest.mark.parametrize('current', [FRAME_KEYS_FORMAT, VIDEO_FORMAT], ids=['format2', 'format3'])
@pytest.mark.parametrize('problem', ['foreign-held', 'inactive-token', 'null-token', 'active-owner'])
def test_legacy_projection_cannot_infer_native_key_ownership_from_serialized_state(
        source_peer, current, problem):
    from fdisbull.dosbox_rpc import DebuggerError
    from fdisbull.qemu_instrumented_checkpoint import PREFIX, restore
    vm = source_peer(make_state(source_record('idle'), version=FORMAT), readback_format=current)
    original_record, original_current = deepcopy(vm.record), deepcopy(vm.current)
    native_call = vm.call
    def independent_keys(command, arguments=None, **options):
        reply = native_call(command, arguments, **options)
        if command == 'x-fdisbull-query-frame-keys':
            if problem == 'foreign-held': reply['foreign-held'] = ['a']
            elif problem == 'inactive-token': reply['token'] = 'foreign-owner'
            elif problem == 'null-token': reply['token'] = None
            else: reply.update(active=True, generation=1, token='foreign-owner')
        return reply
    vm.call = independent_keys
    with pytest.raises(DebuggerError):
        restore(vm, vm.record)
    assert vm.record == original_record and vm.current == original_current
    assert vm.closed and vm.close_calls == 1
    assert vm.calls[-1][0] == 'x-fdisbull-query-frame-keys'
    assert PREFIX+'checkpoint-export' not in [call[0] for call in vm.calls]
    assert '_frame_key_owner' not in vm.__dict__
    assert '_video_frame_token' not in vm.__dict__ and '_video_frame_last' not in vm.__dict__
