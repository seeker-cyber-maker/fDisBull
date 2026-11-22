"""Stopped key-batch host contract at a controlled QMP boundary.

The peer is an authored protocol double. These tests do not qualify the native
encoder, device delivery, IRQ consumption or checkpoint compatibility.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_frame_key_batch import (
    APPLY_COMMAND, PLAN_COMMAND, BATCH_COMMANDS, INPUT_RECEIPT_RESERVE,
    InputReceiptBudgetError, VerifiedBatchRefusal, batch_digest, batch_payload,
    compact_receipt, reserve_receipt, state_digest, state_payload,
    strict_plan_request, validate_apply, validate_plan,
)
from fdisbull.qemu_session_revision import passive_dispatch
from test_qemu_dos_history import project, session
from test_qemu_dos_frames import frames, start
from test_qemu_frame_keys import keys


VECTORS = json.loads((Path(__file__).parent / 'fixtures' /
                     'qemu_frame_key_batch_vectors.json').read_text())['vectors']
CHORD = [dict(key=key, pressed=True) for key in ('ctrl', 'alt', 'a', 'up')]


def _reference_state_digest(proof):
    """Independent wire specimen encoder from the frozen protocol table."""
    chunks = [b'fdisbull-frame-key-batch-state-v1\0']
    boolean = {'active', 'valid', 'repeat-supported', 'scan-enabled', 'translated'}
    strings = {'device-path', 'device-type', 'fifo-sha256'}
    arrays = {'held', 'foreign-held'}
    signed = {'fifo-command-pointer', 'throttle-deadline-ns', 'write-command'}
    def string(value):
        raw = value.encode('utf-8')
        return struct.pack('<I', len(raw)) + raw
    fields = sorted(set(proof) | {'token'})
    for field in fields:
        value = proof.get(field)
        if field == 'token': chunks.append(b'\0' if value is None else b'\1' + string(value))
        elif field in boolean: chunks.append(bytes([int(value)]))
        elif field in strings: chunks.append(string(value))
        elif field in arrays:
            chunks.append(struct.pack('<I', len(value)))
            chunks.extend(string(key) for key in value)
        else: chunks.append(struct.pack('<q' if field in signed else '<Q', value))
    return hashlib.sha256(b''.join(chunks)).hexdigest()


def _reference_batch_digest(state, edges, encoded, modifiers):
    chunks = [b'fdisbull-frame-key-batch-request-v1\0', bytes.fromhex(state),
              struct.pack('<I', len(edges))]
    for edge in edges:
        key = edge['key'].encode()
        chunks.extend((struct.pack('<I', len(key)), key, bytes([edge['pressed']])))
    chunks.extend((struct.pack('<I', len(encoded)), bytes(encoded),
                   struct.pack('<Q', modifiers), b'\0'))
    return hashlib.sha256(b''.join(chunks)).hexdigest()


def _plan(before, edges):
    held = set(before['held'])
    encoded = []
    codes = {'ctrl': [0x14], 'alt': [0x11], 'shift': [0x12], 'a': [0x1c],
             'b': [0x32], 'up': [0xe0, 0x75], 'esc': [0x76]}
    for edge in edges:
        code = codes[edge['key']]
        if edge['pressed']:
            held.add(edge['key']); encoded.extend(code)
        else:
            held.remove(edge['key']); encoded.extend(code[:-1] + [0xf0, code[-1]])
    modifier = sum({'ctrl': 1, 'shift': 2, 'alt': 4}.get(key, 0) for key in held)
    digest = _reference_state_digest(before)
    return {'api-version': 1, 'outcome': 'ready', 'before': deepcopy(before),
            'edges': deepcopy(edges), 'state-sha256': digest,
            'batch-sha256': _reference_batch_digest(digest, edges, encoded, modifier),
            'encoded-bytes': encoded, 'encoded-byte-count': len(encoded),
            'available-bytes': 16 - before['fifo-count'], 'resulting-held': sorted(held),
            'resulting-modifier-mask': modifier, 'resulting-translation-prefix': False}


def _accepted(before, request, plan):
    after = deepcopy(before)
    count = plan['encoded-byte-count']
    after.update(active=True, token=request['token'], held=plan['resulting-held'],
                 generation=before['generation'] + 1)
    after.update({'accepted-edges': before['accepted-edges'] + len(request['edges']),
                  'modifier-mask': plan['resulting-modifier-mask'],
                  'fifo-count': before['fifo-count'] + count,
                  'fifo-write-pointer': (before['fifo-write-pointer'] + count) % 256})
    if count:
        after.update({'controller-status': (before['controller-status'] & ~0x21) | 1,
                      'controller-pending': before['controller-pending'] | 0x10,
                      'controller-obsrc': 1, 'edge-capacity': 0,
                      'fifo-sha256': hashlib.sha256(bytes(plan['encoded-bytes'])).hexdigest()})
    return dict(request, **{'api-version': 1, 'outcome': 'accepted',
                'before': deepcopy(before), 'after': after, 'encoded-byte-count': count,
                'accepted-edge-count': len(request['edges'])})


@pytest.fixture
def batch_keys(keys):
    keys.vm.qmp_commands |= BATCH_COMMANDS
    keys.key_state.update({'translated': False, 'throttle-deadline-ns': -1,
                           'controller-mode': 1})
    prior = keys.vm.qmp.call
    peer = SimpleNamespace(calls=[], plan_refusal=None, apply_refusal=None,
                           transform_plan=None, transform_apply=None)
    def call(name, args=None, **kwargs):
        peer.calls.append((name, deepcopy(args)))
        if name == PLAN_COMMAND:
            raw = _plan(keys.key_state, args['edges'])
            if peer.plan_refusal:
                raw = {'api-version': 1, 'outcome': 'refused',
                       'before': deepcopy(keys.key_state), 'edges': deepcopy(args['edges']),
                       'reason': peer.plan_refusal}
            return peer.transform_plan(raw) if peer.transform_plan else raw
        if name == APPLY_COMMAND:
            if peer.apply_refusal:
                raw = dict(args, **{'api-version': 1, 'outcome': 'refused',
                         'before': deepcopy(keys.key_state), 'after': deepcopy(keys.key_state),
                         'reason': peer.apply_refusal})
            else:
                raw = _accepted(keys.key_state, args, _plan(keys.key_state, args['edges']))
                keys.key_state.clear(); keys.key_state.update(deepcopy(raw['after']))
            return peer.transform_apply(raw) if peer.transform_apply else raw
        return prior(name, args, **kwargs)
    keys.vm.qmp.call = call
    keys.batch_peer = peer
    return keys


def _invoke(keys, entry, edges=None):
    edges = deepcopy(CHORD if edges is None else edges)
    if entry == 'direct': return keys.frame_inputs(edges)
    return keys.timeline_advance(inputs=[dict(frame=0, edges=edges)])


def _request(plan):
    return {'token': plan['before'].get('token', 'new-owner'),
            'expected-epoch': plan['before']['epoch'],
            'expected-generation': plan['before']['generation'],
            'expected-state-sha256': plan['state-sha256'],
            'expected-batch-sha256': plan['batch-sha256'], 'edges': deepcopy(plan['edges'])}


@pytest.mark.parametrize('vector', VECTORS, ids=lambda v: v['name'])
def test_frozen_independent_serializer_vectors(vector):
    before, edges, encoded = vector['before'], vector['edges'], vector['encoded_bytes']
    assert state_payload(before).hex() == vector['state_payload_hex']
    assert state_digest(before) == vector['state_sha256']
    args = (vector['state_sha256'], edges, encoded,
            vector['resulting_modifier_mask'], vector['resulting_translation_prefix'])
    assert batch_payload(*args).hex() == vector['batch_payload_hex']
    assert batch_digest(*args) == vector['batch_sha256']


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
def test_four_edge_chord_uses_one_batch_despite_legacy_capacity(batch_keys, entry):
    start(batch_keys)
    result = _invoke(batch_keys, entry)
    calls = [name for name, _ in batch_keys.batch_peer.calls]
    assert calls.count(PLAN_COMMAND) == calls.count(APPLY_COMMAND) == 1
    assert 'x-fdisbull-apply-frame-key-edges' not in calls
    assert batch_keys.key_state['held'] == ['a', 'alt', 'ctrl', 'up']
    assert batch_keys.key_state['accepted-edges'] == 4
    manifest = batch_keys._frame_manifest()
    receipt = manifest['input_journal'][0]
    assert receipt['guest_consumed'] is None and receipt['repeat_supported'] is False
    assert receipt['batch']['accepted_edges'] == 4 and receipt['batch']['encoded_bytes'] == 5
    assert receipt['native']['controller-pending'] == 0x10
    assert receipt['native']['controller-status'] == 1
    assert len(json.dumps(receipt, separators=(',', ':'), sort_keys=True).encode()) < INPUT_RECEIPT_RESERVE
    assert result.get('outcome', 'completed') == 'completed'


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
@pytest.mark.parametrize('capability', ['absent', 'partial'])
def test_capability_fallback_is_conservative(batch_keys, entry, capability):
    start(batch_keys)
    batch_keys.vm.qmp_commands -= BATCH_COMMANDS
    if capability == 'partial': batch_keys.vm.qmp_commands.add(PLAN_COMMAND)
    if entry == 'timeline' and capability == 'absent':
        assert _invoke(batch_keys, entry)['outcome'] == 'input_refused'
    else:
        with pytest.raises(ValueError, match='capacity|incomplete'): _invoke(batch_keys, entry)
    assert batch_keys.key_state['held'] == [] and not batch_keys.closed
    assert not any(name in BATCH_COMMANDS for name, _ in batch_keys.batch_peer.calls)


def test_empty_direct_request_is_read_only(batch_keys):
    root = start(batch_keys)
    receipt = batch_keys.frame_inputs([])
    assert receipt['edges'] == []
    assert batch_keys.timeline_status()['cursor'] == root['cursor']
    assert not batch_keys.key_state['active'] and not batch_keys.events
    assert not any(name in BATCH_COMMANDS for name, _ in batch_keys.batch_peer.calls)
    assert batch_keys._frame_manifest().get('input_journal', []) == []


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
@pytest.mark.parametrize('stage', ['plan', 'apply'])
def test_verified_refusal_preserves_existing_dirty_journal(batch_keys, entry, stage):
    start(batch_keys)
    batch_keys.frame_inputs([dict(key='a', pressed=True)])
    before = batch_keys._frame_manifest()
    batch_keys.batch_peer.calls.clear(); batch_keys.events.clear()
    setattr(batch_keys.batch_peer, stage + '_refusal', 'device-busy')
    if entry == 'direct':
        with pytest.raises(VerifiedBatchRefusal):
            _invoke(batch_keys, entry, [dict(key='a', pressed=False)])
    else:
        result = _invoke(batch_keys, entry, [dict(key='a', pressed=False)])
        assert result['outcome'] == 'input_refused' and result['completed_frames'] == 0
        assert result['pending_inputs'] == before['pending_inputs']
    after = batch_keys._frame_manifest()
    for name in ('cursor', 'nodes', 'head', 'input_journal', 'pending_inputs', 'input_dirty'):
        assert after[name] == before[name]
    assert after['pending'] is None and not batch_keys.closed
    assert not any(name == 'frame-inputs' for name, _ in batch_keys.events)
    if stage == 'plan':
        assert after['revision'] == before['revision']
        assert not batch_keys.events
        assert all(name != APPLY_COMMAND for name, _ in batch_keys.batch_peer.calls)
    else: assert after['revision'] == before['revision'] + 2
    assert 'x-fdisbull-arm-display-frame' not in [name for name, _ in batch_keys.batch_peer.calls]


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
@pytest.mark.parametrize('malformed', ['missing-before', 'changed-before', 'boolean-generation'])
def test_planning_refusal_requires_complete_typed_continuity(batch_keys, entry, malformed):
    start(batch_keys)
    batch_keys.batch_peer.plan_refusal = 'device-busy'
    def corrupt(raw):
        if malformed == 'missing-before': raw.pop('before')
        elif malformed == 'changed-before': raw['before']['fifo-sha256'] = 'f' * 64
        else: raw['before']['generation'] = False
        return raw
    batch_keys.batch_peer.transform_plan = corrupt
    with pytest.raises(DebuggerError): _invoke(batch_keys, entry)
    assert batch_keys.closed and batch_keys.key_state['held'] == []
    assert not any(name == APPLY_COMMAND for name, _ in batch_keys.batch_peer.calls)


@pytest.mark.parametrize('field,value', [
    ('api-version', True), ('encoded-byte-count', True), ('available-bytes', 16.0),
    ('resulting-modifier-mask', 5.0), ('resulting-translation-prefix', 0),
    ('state-sha256', 'f' * 64), ('batch-sha256', 'f' * 64),
])
def test_plan_rejects_equal_valued_wrong_types_and_unbound_digests(batch_keys, field, value):
    plan = _plan(batch_keys.key_state, CHORD)
    plan[field] = value
    with pytest.raises(DebuggerError): validate_plan(plan, batch_keys.key_state, CHORD, ['a','alt','ctrl','up'])


@pytest.mark.parametrize('field,value', [
    ('generation', True), ('fifo-count', 4), ('controller-status', 0),
    ('controller-pending', 0), ('controller-obsrc', 0), ('edge-capacity', 2),
    ('throttle-deadline-ns', 0), ('device-path', '/replacement'),
])
def test_apply_requires_real_post_irq_proof(batch_keys, field, value):
    plan = _plan(batch_keys.key_state, CHORD); request = _request(plan)
    raw = _accepted(batch_keys.key_state, request, plan)
    raw['after'][field] = value
    with pytest.raises(DebuggerError): validate_apply(raw, request, plan)


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
@pytest.mark.parametrize('failure', ['lost', 'malformed'])
def test_uncertain_acceptance_closes_without_replay_or_release(batch_keys, entry, failure):
    start(batch_keys)
    def corrupt(raw):
        if failure == 'lost': raise TimeoutError('lost accepted response')
        raw['after']['generation'] = True
        return raw
    batch_keys.batch_peer.transform_apply = corrupt
    with pytest.raises((TimeoutError, DebuggerError)): _invoke(batch_keys, entry)
    assert batch_keys.closed and batch_keys.key_state['held'] == ['a','alt','ctrl','up']
    calls = [name for name, _ in batch_keys.batch_peer.calls]
    assert calls.count(APPLY_COMMAND) == 1
    assert 'x-fdisbull-apply-frame-key-edges' not in calls
    assert 'x-fdisbull-detach-frame-keys' not in calls
    row = batch_keys.project.db.execute("SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid DESC LIMIT 1").fetchone()
    assert json.loads(bytes(row['data']))['pending'] is not None


@pytest.mark.parametrize('payload,expected', [
    ({'edges': CHORD}, True), ({'edges': []}, False), ({'edges': CHORD, 'extra': 1}, False),
    ({'edges': [dict(key='a',pressed=1)]}, False),
    ({'edges': [dict(key='a',pressed=True)] * 2}, False),
    ({'edges': [dict(key='ctrl_r',pressed=True)]}, True),
    ({'edges': [dict(key='escape',pressed=True)]}, False),
])
def test_only_exact_plan_schema_is_cooperatively_passive(payload, expected):
    assert strict_plan_request(payload) is expected
    admission = SimpleNamespace(protocol='qmp', operation=PLAN_COMMAND, arguments=payload)
    assert passive_dispatch(SimpleNamespace(), admission, []) is expected
    admission.operation = APPLY_COMMAND
    assert passive_dispatch(SimpleNamespace(), admission, []) is False


def test_receipt_reservation_bounds_actual_unicode_serialization(batch_keys):
    before = deepcopy(batch_keys.key_state)
    before['device-path'] = '\u0800' * 341
    before['device-type'] = '\u0800' * 42
    plan = _plan(before, CHORD); request = _request(plan)
    bound = reserve_receipt(plan, request['token'], CHORD)
    result = _accepted(before, request, plan)['after']
    payload = json.dumps(compact_receipt(result, CHORD, plan), sort_keys=True,
                         separators=(',', ':'), ensure_ascii=True).encode()
    assert len(payload) <= bound <= INPUT_RECEIPT_RESERVE - 2


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
def test_apply_refusal_resolution_failure_closes_original(batch_keys, entry):
    start(batch_keys)
    batch_keys.batch_peer.apply_refusal = 'device-busy'
    previous = batch_keys._history_new_revision
    def fail_resolution(manifest, **kwargs):
        if manifest.get('pending') is not None and kwargs.get('pending', 'absent') is None:
            raise OSError('cannot persist refusal resolution')
        return previous(manifest, **kwargs)
    batch_keys._history_new_revision = fail_resolution
    with pytest.raises(OSError, match='persist refusal'): _invoke(batch_keys, entry)
    assert batch_keys.closed and batch_keys.key_state['held'] == []


@pytest.mark.parametrize('entry', ['direct', 'timeline'])
def test_oversized_serialized_receipt_refuses_before_intent(batch_keys, entry):
    from fdisbull.qemu_frame_keys import adopt_frame_keys
    start(batch_keys)
    batch_keys.key_state.update({'active': True, 'token': '\x01' * 128, 'generation': 1,
                                'device-path': '\x01' * 1024,
                                'device-type': '\x01' * 128})
    adopt_frame_keys(batch_keys.vm, batch_keys.key_state)
    before = batch_keys._frame_manifest()
    if entry == 'direct':
        with pytest.raises(InputReceiptBudgetError): _invoke(batch_keys, entry)
    else: assert _invoke(batch_keys, entry)['outcome'] == 'input_refused'
    assert not batch_keys.closed and not batch_keys.events
    assert batch_keys._frame_manifest() == before
    assert all(name != APPLY_COMMAND for name, _ in batch_keys.batch_peer.calls)


def test_later_refusal_retains_completed_prefix_and_accepted_journal(batch_keys):
    root = start(batch_keys)
    prior = batch_keys.capture_display
    def capture(*args, **kwargs):
        result = prior(*args, **kwargs)
        batch_keys.batch_peer.plan_refusal = 'device-busy'
        return result
    batch_keys.capture_display = capture
    result = batch_keys.timeline_advance(frames=2, inputs=[
        dict(frame=0, edges=[dict(key='a', pressed=True)]),
        dict(frame=1, edges=[dict(key='a', pressed=False)]),
    ])
    assert result['outcome'] == 'input_refused' and result['completed_frames'] == 1
    assert result['cursor'] != root['cursor'] and result['valid']
    assert result['nodes'][-1]['frame']['keys'] == ['a']
    manifest = batch_keys._frame_manifest()
    assert len(manifest['input_journal']) == 1 and manifest['pending'] is None
    assert manifest['pending_inputs'] == [] and not manifest['input_dirty']
    names = [name for name, _ in batch_keys.batch_peer.calls]
    assert names.count(APPLY_COMMAND) == names.count('x-fdisbull-arm-display-frame') == 1
