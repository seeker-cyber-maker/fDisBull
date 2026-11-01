"""Authored collector failures and timing policy, without native execution."""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import time

import pytest

import examples.agi.verify_bridge_clip as module
from examples.agi.verify_goat import GoatRun


def test_probe_keeps_foreign_stop_primary_when_final_receipt_write_fails(tmp_path, monkeypatch):
    """An observer failure must survive a later persistence failure."""
    run = object.__new__(module.ClipRun)
    run.cs, run.ds, run.guest_elapsed = 0x1000, 0x20000, 0
    run.journal, run.predicate_proof, run.root = [], None, tmp_path
    run.report = {}
    position = {'room': 39, 'ego': {'x': 72, 'y': 88}}
    run.safe_state = lambda: deepcopy(position)
    run._idle = lambda: True
    run.remaining_limits = lambda *args: (100, 5000)
    # Only the collector's explicit source-condition precheck is exercised.
    # The fake stop occurs before any original instruction/source lookup.
    code = bytearray(0x416)
    code[0x410:0x416] = bytes((11, 0, 72, 84, 72, 87))
    run.resources = {39: SimpleNamespace(code=bytes(code), resource_sha256='authored-source')}
    calls = []

    def call(method, params=None):
        calls.append((method, params))
        if method == 'breakpoints.create':
            return {'breakpoint_id': 'owned-posn-entry'}
        assert method == 'breakpoints.delete'
        return {}

    run.d = SimpleNamespace(
        call=call,
        run=lambda **kwargs: {'outcome': 'pause', 'guest_elapsed_ms': 1,
                              'session': {'stop_reason': {'kind': 'pause'}}},
    )

    def read(session, address, length):
        assert session is run.d and address == run.ds + 0x921 and length == 4
        return bytes((0xc6, 0x08, 5, 0))

    monkeypatch.setattr(module, 'read', read)
    original_write = Path.write_text
    attempts = []

    def write(path, content, *args, **kwargs):
        if path.name == 'corner-predicate.private.json':
            attempts.append(content)
            if len(attempts) > 1:
                raise OSError('authored predicate receipt failure')
        return original_write(path, content, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', write)
    observed = None
    try:
        run.observe_corner_predicate()
    except BaseException as exc:
        observed = exc

    assert [params['breakpoint_id'] for method, params in calls
            if method == 'breakpoints.delete'] == ['owned-posn-entry']
    assert len(attempts) >= 2
    assert isinstance(observed, RuntimeError)
    assert 'Foreign predicate search stop preserved' in str(observed)
    assert run.predicate_proof['complete'] is False
    assert run.predicate_proof['error'] == 'Foreign predicate search stop preserved'


@pytest.mark.parametrize('context_cleanup_fails', [False, True])
def test_main_retains_remaining_evidence_after_journal_failure_and_reraises_route_primary(
        tmp_path, monkeypatch, context_cleanup_fails):
    """A failure in one artifact must not skip the other evidence or hashes."""
    source, root = tmp_path / 'owner-source', tmp_path / 'private-run'
    source.mkdir()
    primary = RuntimeError('authored route primary')
    original_manifest = {'authored-original': 'authored-hash'}
    report = {'source_manifest': original_manifest}
    calls, manifest_calls, writes = [], [], []

    @contextmanager
    def native_game(game_name, owner, output, backend, *, fair_play):
        assert game_name == 'kq1' and owner == source and output == root and fair_play
        root.mkdir()
        (root / 'game').mkdir()
        original_write(root / 'result.json', json.dumps(report))
        debugger = SimpleNamespace(call=lambda *args: calls.append(args))
        try:
            yield object(), debugger, {}, None, lambda name: calls.append(('frame', name)), report, root / 'game'
        finally:
            if context_cleanup_fails:
                raise OSError('authored native-context cleanup failure')

    class AuthoredRun:
        def __init__(self, project, debugger, live_report, frame, owner, output):
            self.report, self.root, self.d = live_report, output, debugger
            self.bp = None
            self.journal = [{'kind': 'authored-route-attempt'}]
            self.predicate_proof = {'format': 'authored-predicate', 'complete': False}

        def route(self, *, adjacent_control=False):
            assert adjacent_control is False
            raise primary

        def state(self):
            return {'room': 39, 'score': 0}

        def capture(self):
            return {'format': 'authored-partial-capture', 'actions': []}

    def manifest(path):
        manifest_calls.append(Path(path))
        return dict(original_manifest)

    original_write = Path.write_text

    def write(path, content, *args, **kwargs):
        writes.append(path.name)
        if path.name == 'journal.private.json':
            raise OSError('authored journal persistence failure')
        return original_write(path, content, *args, **kwargs)

    monkeypatch.setattr(module, 'native_game', native_game)
    monkeypatch.setattr(module, 'ClipRun', AuthoredRun)
    monkeypatch.setattr(module, 'manifest', manifest)
    monkeypatch.setattr(Path, 'write_text', write)
    monkeypatch.setattr('sys.argv', ['verify_bridge_clip.py', '--source', str(source),
                                   '--backend', str(tmp_path / 'unused-backend'),
                                   '--output', str(root)])
    observed = None
    try:
        module.main()
    except BaseException as exc:
        observed = exc

    assert observed is primary
    assert {'journal.private.json', 'partial-capture.private.json',
            'partial-predicate.private.json', 'result.json'} <= set(writes)
    assert source in manifest_calls and root / 'game' in manifest_calls
    assert json.loads((root / 'partial-capture.private.json').read_text()) == {
        'format': 'authored-partial-capture', 'actions': []}
    assert json.loads((root / 'partial-predicate.private.json').read_text()) == {
        'format': 'authored-predicate', 'complete': False}
    retained = json.loads((root / 'result.json').read_text())
    assert retained['post_teardown_source_unchanged'] is True
    assert retained['post_teardown_copy_unchanged'] is True
    assert retained['persistence_errors']
    assert any('journal' in item['operation'] and 'journal' in item['error']
               for item in retained['persistence_errors'])
    if context_cleanup_fails:
        assert any(item['operation'] == 'native context cleanup'
                   and 'authored native-context cleanup failure' in item['error']
                   for item in retained['persistence_errors'])


@pytest.mark.parametrize('previous', [True, False])
@pytest.mark.parametrize('fails', [False, True])
def test_precise_restores_the_previous_fast_forward_policy(previous, fails):
    run = object.__new__(module.ClipRun)
    run.fast_forward = previous
    result = object()
    primary = RuntimeError('authored waypoint failure')
    seen = []

    def precise(**kwargs):
        seen.append((run.fast_forward, kwargs))
        if fails:
            raise primary
        return result

    run._precise = precise
    if fails:
        with pytest.raises(RuntimeError) as observed:
            run.precise(x=72, y=88)
        assert observed.value is primary
    else:
        assert run.precise(x=72, y=88) is result

    assert seen == [(False, {'x': 72, 'y': 88})]
    assert run.fast_forward is previous


def test_goat_run_keeps_its_backward_compatible_fast_forward_default():
    assert GoatRun.fast_forward is True
    assert object.__new__(GoatRun).fast_forward is True


@pytest.mark.parametrize('policy', [True, False])
def test_advance_consumes_the_selected_fast_forward_policy(policy):
    run = object.__new__(GoatRun)
    run.guest_elapsed, run.deadline, run.journal = 0, time.monotonic() + 5, []
    run.fast_forward = policy
    run.state = lambda: {'authored-state': True}
    calls = []

    def advance(**kwargs):
        calls.append(kwargs)
        return {'outcome': 'guest_time', 'guest_elapsed_ms': 10}

    run.d = SimpleNamespace(run=advance)

    assert run.advance(10) == {'authored-state': True}
    assert len(calls) == 1 and calls[0]['fast_forward'] is policy
    assert run.guest_elapsed == 10
