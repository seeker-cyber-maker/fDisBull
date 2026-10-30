"""Recovery receipts and repeated-failure isolation; native acceptance is separate."""
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge


def read_receipt(work):
    return json.loads((work / 'z-session.json').read_text())


def pending(command, *, confirmed):
    return {'command': command, 'messages': [], 'events': [
        {'phase': 'food_purchase_committed', 'result': {'price': 500, 'quantity': 20}}
    ] if confirmed else []}


@pytest.mark.parametrize('confirmed', [False, True])
def test_unresolved_eof_keeps_failure_incomplete_while_owned_cleanup_finishes(
        tmp_path, monkeypatch, confirmed):
    """Exercise the actual entry point, with the native runner as the boundary."""
    source = tmp_path / 'source'; source.mkdir()
    work = tmp_path / 'service'
    writer = io.StringIO()
    monkeypatch.setattr(bridge.sys, 'stdin', io.StringIO())
    monkeypatch.setattr(bridge.sys, 'stdout', writer)
    monkeypatch.setattr(bridge, 'build_game', lambda source, work: source)

    class OwnedProcess:
        pid = 123
        returncode = None
        terminated = False

        def poll(self): return self.returncode
        def terminate(self): self.terminated = True; self.returncode = 0
        def wait(self, timeout): return self.returncode

    process = OwnedProcess()
    before_close = {}

    def run_native_boundary(argv, *, command_reader, on_ready, on_spawn,
                            on_action_error, recovery_required, **callbacks):
        on_spawn(process)
        text = SimpleNamespace(debug=SimpleNamespace(call=lambda op: {'state': 'stopped'}))
        on_ready(text)
        service = command_reader.__self__
        service.pending = pending('buy 20 small feeders', confirmed=confirmed)
        assert on_action_error(RuntimeError('declared unresolved provider failure'))
        before_close['diagnostic'] = (work / 'z-failure.json').read_bytes()
        before_close['receipt'] = read_receipt(work)
        assert recovery_required()
        with pytest.raises(EOFError): command_reader()
        return None

    monkeypatch.setattr(scenes, 'run_session', run_native_boundary)
    result = bridge.main(['--game-dir', str(source), '--backend', str(tmp_path / 'backend'),
                          '--work-dir', str(work)])
    receipt = read_receipt(work)
    assert result == 1 and process.terminated
    assert receipt['status'] == 'recovery-required' and receipt['complete'] is False
    assert receipt['cleanup_complete'] is True
    assert receipt['processes'] == [{'pid': process.pid, 'returncode': 0}]
    assert receipt['recovery_required'] is True
    assert receipt['action_failures'] == before_close['receipt']['action_failures']
    assert receipt['action_failures'][0]['restored_by'] is None
    assert (work / 'z-failure.json').read_bytes() == before_close['diagnostic']
    replies = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len(replies) == 1 and replies[0]['complete'] is False
    assert replies[0]['effects'] == ('applied-confirmed' if confirmed else 'unknown')
    assert receipt['action_failures'][0]['effects'] == replies[0]['effects']
    assert not (work / 'z-service-error.log').exists()  # EOF is not a second failure.


@pytest.mark.parametrize('second_confirmed', [False, True])
def test_repeated_failures_keep_diagnostics_effects_and_restore_links_separate(
        tmp_path, monkeypatch, second_confirmed):
    writer = io.StringIO()
    service = bridge.ZService(tmp_path, io.StringIO(), writer)
    values = {name: '00' * size for name, _, _, size in scenes.SAVE_RANGES}

    class NativeBoundary:
        framed = True

        def call(self, op):
            assert op == 'session.status'
            return {'state': 'stopped'}

        def save_state(self, name): return {'artifact': 'existing-native-state'}
        def load_state(self, artifact):
            assert artifact == 'existing-native-state'
            self.framed = False

    native = NativeBoundary()
    text = SimpleNamespace(**dict.fromkeys(bridge.SNAPSHOT_FIELDS))
    text.debug = native
    service.ready(text)
    service.observe = lambda **kw: {'complete': native.framed, 'context': {'id': 'dino_diner'}}
    monkeypatch.setattr(scenes, 'live_saved_fields', lambda debug: dict(values))

    def prepare(debug, milliseconds):
        assert milliseconds == 100
        debug.framed = True

    monkeypatch.setattr(scenes, 'run_guest', prepare)
    assert service.checkpoint({'op': 'save', 'slot': 'before'})['status'] == 'saved'

    service.pending = pending('buy 20 small feeders', confirmed=True)
    assert service.action_error(RuntimeError('first postcommit failure'))
    first = (tmp_path / 'z-failure.json').read_bytes()
    assert service.checkpoint({'op': 'load', 'checkpoint': 'before'})['status'] == 'restored'
    first_summary = dict(service.failures[0])

    command = 'buy 20 small feeders' if second_confirmed else 'go office'
    service.pending = pending(command, confirmed=second_confirmed)
    assert service.action_error(ValueError('second distinct provider failure'))
    second = json.loads((tmp_path / 'z-failure-002.json').read_text())
    receipt = read_receipt(tmp_path)
    assert (tmp_path / 'z-failure.json').read_bytes() == first
    assert second['error'] == 'second distinct provider failure'
    assert bool(second['confirmed_effects']) is second_confirmed
    assert len(receipt['action_failures']) == 2 and receipt['recovery_required'] is True
    assert receipt['action_failures'][0] == first_summary
    assert receipt['action_failures'][1]['restored_by'] is None
    replies = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len(replies) == 2
    assert [r['effects'] for r in replies] == [
        'applied-confirmed', 'applied-confirmed' if second_confirmed else 'unknown']

    assert service.checkpoint({'op': 'load', 'checkpoint': 'before'})['status'] == 'restored'
    assert service.recovery_required is False and service.checkpoint_failed is False
    assert service.failures[0] == first_summary
    assert service.failures[1]['restored_by'] == 'before'
    service.receipt('completed', complete=True)
    final = read_receipt(tmp_path)
    assert final['complete'] is True and final['recovery_required'] is False
    assert final['action_failures'] == service.failures
    assert (tmp_path / 'z-failure.json').read_bytes() == first
    assert not (tmp_path / 'z-failure-003.json').exists()
