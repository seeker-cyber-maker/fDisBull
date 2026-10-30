"""Bounded reply delivery is independent of original-action completion."""
import base64
import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull.dinopark_z import LIMIT, ZService


class NativeBoundary:
    run_id = 'native-run'

    def __init__(self):
        self.calls = []
        self.revision = 7
        self.stop = {'kind': 'pause'}

    def call(self, method):
        self.calls.append(method)
        assert method == 'session.status', 'reply recovery attempted guest execution/input'
        return {'session_id': 'native-session', 'state': 'stopped',
                'state_revision': self.revision, 'last_stop': dict(self.stop)}


def service(tmp_path, writer=None):
    native = NativeBoundary()
    backend = ZService(tmp_path, io.StringIO(), writer or io.StringIO())
    backend.text = SimpleNamespace(debug=native)
    return backend, native


def large_result():
    return {'complete': True, 'status': 'native-control-complete',
            'run': {'outcome': 'guest_time', 'observer_hits': [{'event': 'read', 'detail': 'x' * 100} for _ in range(415)]},
            'frame': {'sha256': 'a' * 64}, 'scope': 'input interval only; original quit not certified'}


def test_oversized_terminal_result_is_retained_instead_of_discarded(tmp_path):
    backend, _ = service(tmp_path)
    expected = large_result()
    backend.send(expected)
    wire = backend.writer.getvalue().encode()
    assert len(wire) <= LIMIT
    marker = json.loads(wire)
    assert marker['status'] == 'reply-retained'
    assert marker['complete'] is False and marker['retry_safe'] is False
    assert marker['execution'] == {'returned': True, 'complete': True, 'status': 'native-control-complete'}


def request(backend, value):
    before = len(backend.writer.getvalue())
    backend.reader = io.StringIO(json.dumps(value) + '\n')
    with pytest.raises(EOFError):
        backend.command()
    raw = backend.writer.getvalue()[before:]
    assert len(raw.encode()) <= LIMIT
    return json.loads(raw)


def retained(backend, result=None):
    backend.send(large_result() if result is None else result)
    return json.loads(backend.writer.getvalue().splitlines()[-1])['reply']


def test_paged_read_and_selection_are_exact_and_do_not_touch_guest(tmp_path):
    backend, native = service(tmp_path)
    result = large_result()
    ref = retained(backend, result)
    calls = list(native.calls)
    chunks = []
    offset = 0
    while True:
        reply = request(backend, {'op': 'read_reply', 'reply_id': ref['id'], 'offset': offset})
        chunks.append(base64.b64decode(reply['data_base64']))
        offset = reply['next_offset']
        if reply['eof']: break
    data = b''.join(chunks)
    assert json.loads(data) == result
    assert hashlib.sha256(data).hexdigest() == ref['sha256']
    assert len(data) == ref['bytes']
    assert request(backend, {'op': 'select_reply', 'reply_id': ref['id'], 'pointer': '/run/outcome'})['value'] == 'guest_time'
    assert request(backend, {'op': 'reply_status'})['reply'] == ref
    assert native.calls == calls
    assert backend.reply_pending


def test_actions_checkpoints_and_observation_are_held_until_delivery_accepted(tmp_path):
    backend, native = service(tmp_path)
    ref = retained(backend)
    calls = list(native.calls)
    for value in ({'op': 'act', 'action': {}}, {'op': 'save'}, {'op': 'load', 'checkpoint': 'old'}, {'op': 'observe'}):
        assert request(backend, value)['status'] == 'reply-retained'
    assert native.calls == calls
    backend.recovery_required = backend.checkpoint_failed = True
    value = {'op': 'accept_reply', 'reply_id': ref['id'], 'sha256': ref['sha256']}
    assert request(backend, value)['status'] == 'reply-accepted'
    assert request(backend, value)['status'] == 'reply-already-accepted'
    assert not backend.reply_pending
    assert backend.recovery_required and backend.checkpoint_failed
    assert all(call == 'session.status' for call in native.calls)


@pytest.mark.parametrize('change', ['revision', 'session', 'digest', 'missing-witness', 'stop', 'missing-stop', 'invalid-revision'])
def test_stale_foreign_or_unverifiable_receipt_cannot_release_hold(tmp_path, change):
    backend, native = service(tmp_path)
    ref = retained(backend)
    if change == 'revision': native.revision += 1
    elif change == 'session': backend.session_token = 'new-session'
    elif change == 'digest': ref['sha256'] = '0' * 64
    elif change == 'stop': native.stop = {'kind': 'breakpoint'}
    elif change == 'missing-stop': native.stop = {}
    elif change == 'invalid-revision': native.revision = -1
    else: backend.text = None
    reply = request(backend, {'op': 'accept_reply', 'reply_id': ref['id'], 'sha256': ref['sha256']})
    assert reply['status'] == 'unresolved'
    assert backend.reply_pending


def test_lost_reference_survives_journal_reopen_without_reexecuting(tmp_path):
    from fdisbull.z_replies import ZReplyJournal

    class BrokenWriter:
        def write(self, value): raise BrokenPipeError('lost after commit')
        def flush(self): pass

    backend, native = service(tmp_path, BrokenWriter())
    with pytest.raises(BrokenPipeError): backend.send(large_result())
    journal = ZReplyJournal(tmp_path)
    status = journal.status()
    assert status['status'] == 'reply-retained'
    ref = status['reply']
    assert journal.read(ref['id'])['range_complete']
    other, _ = service(tmp_path)
    assert other.reply_pending
    assert request(other, {'op': 'accept_reply', 'reply_id': ref['id'], 'sha256': ref['sha256']})['status'] == 'unresolved'
    assert len(native.calls) == 1


def test_corrupt_retained_bytes_are_never_accepted(tmp_path):
    backend, _ = service(tmp_path)
    ref = retained(backend)
    artifact = backend.replies.root / 'artifacts' / ref['artifact_id']
    artifact.write_bytes(b'{"changed":true}')
    for value in ({'op': 'read_reply', 'reply_id': ref['id']},
                  {'op': 'accept_reply', 'reply_id': ref['id'], 'sha256': ref['sha256']}):
        assert request(backend, value)['status'] == 'unresolved'
    assert backend.reply_pending


def test_retention_failure_preserves_unknown_and_blocks_input(tmp_path, monkeypatch):
    from fdisbull.output_artifacts import ArtifactError
    from fdisbull.z_replies import ZReplyJournal

    backend, _ = service(tmp_path)
    from fdisbull.output_artifacts import OutputArtifactStore
    calls = []
    def unavailable(store, chunks):
        calls.append(True)
        raise ArtifactError('quota_exceeded')
    monkeypatch.setattr(OutputArtifactStore, 'put_stream', unavailable)
    backend.send(large_result())
    assert json.loads(backend.writer.getvalue())['status'] == 'reply-unavailable'
    assert calls == [True]
    assert backend.reply_pending and ZReplyJournal(tmp_path).blocked
    assert request(backend, {'op': 'act', 'action': {}})['status'] == 'reply-unavailable'


def test_bad_read_parameters_do_not_create_a_hold_or_contact_native(tmp_path):
    backend, native = service(tmp_path)
    assert request(backend, {'op': 'read_reply', 'reply_id': 'reply-' + 'a' * 32})['status'] == 'unresolved'
    assert not backend.reply_pending and not native.calls
    ref = retained(backend)
    for value in ({'op': 'read_reply', 'reply_id': '../escape'},
                  {'op': 'read_reply', 'reply_id': ref['id'], 'length': 8193},
                  {'op': 'read_reply', 'reply_id': ref['id'], 'offset': True},
                  {'op': 'select_reply', 'reply_id': ref['id'], 'pointer': '/does-not-exist'}):
        assert request(backend, value)['status'] == 'unresolved'
    assert backend.reply_pending


def test_utf8_budget_and_unknown_execution_are_preserved(tmp_path):
    backend, _ = service(tmp_path)
    result = {'complete': False, 'status': 'incomplete', 'effects': 'unknown', 'text': '🦖' * 9000}
    ref = retained(backend, result)
    assert ref['bytes'] == len(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode())
    assert request(backend, {'op': 'select_reply', 'reply_id': ref['id'], 'pointer': '/effects'})['value'] == 'unknown'
    assert request(backend, {'op': 'select_reply', 'reply_id': ref['id'], 'pointer': ''})['complete'] is False
    marker = json.loads(backend.writer.getvalue().splitlines()[0])
    assert marker['execution']['complete'] is False


def test_repeated_old_ack_cannot_clear_a_new_hold(tmp_path):
    backend, _ = service(tmp_path)
    ref = retained(backend)
    accept = {'op': 'accept_reply', 'reply_id': ref['id'], 'sha256': ref['sha256']}
    assert request(backend, accept)['status'] == 'reply-accepted'
    second = retained(backend, {**large_result(), 'second': True})
    assert second['id'] != ref['id']
    assert request(backend, accept)['status'] == 'unresolved'
    assert backend.reply_pending


@pytest.mark.parametrize('invalid', [[], {}, {'pending': True}, {'unavailable': 'false'}])
def test_corrupt_journal_state_fails_closed_without_crashing(tmp_path, invalid):
    backend, _ = service(tmp_path)
    retained(backend)
    (backend.replies.root / 'state.json').write_text(json.dumps(invalid))
    assert backend.reply_pending
    assert request(backend, {'op': 'reply_status'})['status'] in ('unresolved', 'reply-unavailable')
    assert request(backend, {'op': 'act', 'action': {}})['status'] == 'reply-unavailable'


@pytest.mark.parametrize('invalid', [[], {}, {'artifact': []}])
def test_corrupt_receipt_fails_closed_without_crashing(tmp_path, invalid):
    backend, _ = service(tmp_path)
    ref = retained(backend)
    (backend.replies.root / (ref['id'] + '.json')).write_text(json.dumps(invalid))
    assert request(backend, {'op': 'read_reply', 'reply_id': ref['id']})['status'] == 'unresolved'
    assert backend.reply_pending
    assert request(backend, {'op': 'act', 'action': {}})['status'] == 'reply-unavailable'


def test_inline_boundary_is_unchanged_and_overflow_is_measured_in_bytes(tmp_path):
    backend, native = service(tmp_path)
    payload = {'text': 'x' * (LIMIT - len(b'{"text":""}\n'))}
    backend.send(payload)
    assert len(backend.writer.getvalue().encode()) == LIMIT
    assert json.loads(backend.writer.getvalue()) == payload
    assert not backend.reply_pending and not native.calls
    assert not backend.replies.root.exists()
    payload['text'] += 'x'
    assert retained(backend, payload)['bytes'] == LIMIT
    assert backend.reply_pending


def test_pending_delivery_cannot_be_recorded_as_clean_completion(tmp_path):
    backend, _ = service(tmp_path)
    retained(backend)
    backend.receipt('recovery-required', complete=True)
    receipt = json.loads((tmp_path / 'z-session.json').read_text())
    assert receipt['complete'] is False and receipt['reply_delivery_pending'] is True
    assert receipt['cleanup_complete'] is True  # host cleanup is independent
