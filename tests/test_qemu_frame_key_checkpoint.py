"""Versioned owned-key sidecars are validated before any native restore."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.qemu_instrumented_checkpoint import _decode, _logical, FORMAT, FRAME_KEYS_FORMAT
from test_qemu_frame_keys import keys, frames, session, project


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
