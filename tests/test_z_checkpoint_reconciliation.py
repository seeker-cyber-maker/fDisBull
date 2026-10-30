"""Checkpoint save readback repair never repeats provider mutation."""
import io
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_z_reconciliation import ReadbackBackend, PLAN, batch
from fdisbull_player import BatchSession, Player


class SaveReadbackBackend(ReadbackBackend):
    def __init__(self):
        super().__init__()
        self.after_save = self.lose_save = False
        self.save_rewrite = None

    def save(self, slot='live'):
        result = super().save(slot)
        if self.lose_save:
            raise EOFError('declared lost save reply')
        if self.save_rewrite:
            result.update(deepcopy(self.save_rewrite))
        self.fail_read = self.after_save
        return result


def test_save_reply_survives_following_read_and_reconcile_retains_exact_checkpoint(tmp_path):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend)
    backend.after_save = True
    with pytest.raises(ValueError, match='readback'):
        original.checkpoint('before')
    held = json.loads(original.path.read_text())['recovery']
    assert held['operation'] == 'save' and held['result']['status'] == 'saved'
    assert held['result']['witness']['session_token'] == original.doc['session_token']
    reopened = batch(tmp_path, backend)
    before = list(backend.operations)
    result = reopened.reconcile()
    assert backend.operations[len(before):] == ['observe']
    assert result['reconciliation'] == {'status': 'reconciled', 'reason': 'durable-save-reply',
                                      'operation': 'save', 'checkpoint': 'before'}
    assert result['status'] == 'pending' and result['steps'][0]['attempts'] == []
    inspection = reopened.inspect(include_history=True)
    saved = inspection['checkpoint_details']['before']
    assert saved['handle'] == held['result']['checkpoint'] and saved['cursor'] == 0
    assert saved['receipt'] == held['result'] and saved['reconciled'] is True
    assert inspection['recovery'] is None and inspection['history'] == []
    inspection['checkpoint_details'].clear()
    assert 'before' in reopened.inspect(include_history=True)['checkpoint_details']
    assert 'checkpoint_details' not in reopened.inspect()
    assert reopened.reconcile()['reconciliation']['status'] == 'verified'
    assert backend.mutations() == ['save']
    backend.after_save = False
    assert reopened.run(max_steps=1)['steps'][0]['state'] == 'completed'
    assert backend.state['$key'] is True
    assert reopened.recover('before')['complete'] is True
    assert backend.state['$key'] is False and backend.mutations() == ['save', 'act', 'load']


def test_completed_save_can_be_verified_without_replacing_handle_or_adding_history(tmp_path):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend)
    assert original.checkpoint('before')['status'] == 'saved'
    saved = original.path.read_bytes(); before = list(backend.operations)
    assert original.reconcile()['reconciliation']['status'] == 'verified'
    assert backend.operations[len(before):] == ['observe'] and original.path.read_bytes() == saved


def test_cli_stays_available_during_save_hold_and_reconcile_never_resends_save(tmp_path, monkeypatch):
    from fdisbull_player import __main__ as cli
    backend = SaveReadbackBackend(); backend.after_save = True
    plan = tmp_path / 'plan.json'; plan.write_text(json.dumps(PLAN))
    operations = [{'op':'checkpoint','name':'start'}, {'op':'run'}, {'op':'resume'},
                  {'op':'recover','name':'start'}, {'op':'checkpoint','name':'unsafe'},
                  {'op':'inspect','include_history':True}, {'op':'reconcile'}, {'op':'reconcile'}]
    writer = io.StringIO()
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(''.join(json.dumps(x)+'\n' for x in operations)))
    monkeypatch.setattr(cli.sys, 'stdout', writer)
    assert cli.run_mode(backend, SimpleNamespace(batch_plan=str(plan), batch_journal=str(tmp_path/'cli.json'))) == 0
    replies = [json.loads(x) for x in writer.getvalue().splitlines()]
    assert all(x['status'] == 'recovery-incomplete' and not x['complete'] for x in replies[:5])
    assert replies[5]['recovery']['result']['status'] == 'saved'
    assert replies[6]['reconciliation']['status'] == 'reconciled'
    assert replies[7]['reconciliation']['status'] == 'verified'
    assert backend.mutations() == ['save']


@pytest.mark.parametrize('rewrite', [None, {'complete': False}, {'replay_safe': False},
    {'status': 'incomplete'}, {'checkpoint': None}, {'checkpoint': ''}, {'checkpoint': {}},
    {'witness': None}, {'witness': {'session_token': 'foreign'}},
    {'witness': {'session_token':'foreign','context_id':'courtyard','context_token':'stale'}}])
def test_uncertified_or_lost_save_stays_held_without_repeating_any_provider_mutation(tmp_path, rewrite):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend)
    backend.after_save = True
    if rewrite is None: backend.lose_save = True
    else: backend.save_rewrite = rewrite
    with pytest.raises((ValueError, EOFError)):
        original.checkpoint('before')
    reopened = batch(tmp_path, backend); held = reopened.path.read_bytes()
    before = list(backend.operations)
    result = reopened.reconcile()
    assert result['status'] == 'recovery-incomplete'
    assert result['reconciliation']['status'] == 'unresolved'
    assert result['reconciliation']['operation'] == 'save'
    assert backend.operations[len(before):] == ['observe'] and reopened.path.read_bytes() == held
    assert reopened.inspect()['checkpoints'] == []
    for method, args in [(reopened.run, ()), (reopened.resume, ()),
                         (reopened.checkpoint, ('other',)), (reopened.recover, ('before',))]:
        with pytest.raises(ValueError, match='recovery was interrupted'): method(*args)
    assert backend.mutations() == ['save']


def test_rejected_save_certificate_latches_even_without_an_injected_read_failure(tmp_path):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend)
    backend.save_rewrite = {'replay_safe': False}
    with pytest.raises(ValueError, match='certify'): original.checkpoint('before')
    assert original.inspect()['status'] == 'recovery-incomplete'
    assert original.inspect(include_history=True)['recovery']['result']['replay_safe'] is False
    assert original.reconcile()['reconciliation']['status'] == 'unresolved'
    assert backend.mutations() == ['save']


@pytest.mark.parametrize('foreign', [False, True])
def test_stale_same_scene_or_foreign_session_save_receipt_cannot_reconcile(tmp_path, foreign):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend)
    backend.after_save = True
    with pytest.raises(ValueError, match='readback'): original.checkpoint('before')
    if foreign: backend.epoch = 'different-session'
    else: assert Player(backend).execute_result('take key')['status'] == 'success'
    held = original.path.read_bytes(); before = list(backend.operations)
    assert original.reconcile()['reconciliation']['status'] == 'unresolved'
    assert original.path.read_bytes() == held and backend.operations[len(before):] == ['observe']


@pytest.mark.parametrize('fail_read', [False, True])
def test_legacy_provider_without_save_witness_works_normally_but_cannot_reconcile(tmp_path, fail_read):
    class LegacySave(SaveReadbackBackend):
        def save(self, slot='live'):
            result = super().save(slot); result.pop('witness', None); return result
    backend = LegacySave(); original = batch(tmp_path, backend); backend.after_save = fail_read
    if fail_read:
        with pytest.raises(ValueError, match='readback'): original.checkpoint('before')
        assert original.reconcile()['reconciliation']['status'] == 'unresolved'
    else:
        assert original.checkpoint('before')['status'] == 'saved'
        assert original.reconcile()['reconciliation']['status'] == 'not-needed'
    assert backend.mutations() == ['save']


def test_opaque_provider_handle_is_retained_instead_of_reconstructed_from_slot(tmp_path):
    class OpaqueSave(SaveReadbackBackend):
        def save(self, slot='live'):
            result = super().save(slot)
            opaque = 'opaque-provider-handle'
            self.checkpoints[opaque] = self.checkpoints.pop(slot)
            result['checkpoint'] = opaque
            return result
    backend = OpaqueSave(); original = batch(tmp_path, backend); backend.after_save = True
    with pytest.raises(ValueError, match='readback'): original.checkpoint('before')
    held = original.inspect(include_history=True)['recovery']
    assert held['slot'] != held['result']['checkpoint']
    assert original.reconcile()['reconciliation']['status'] == 'reconciled'
    assert original.inspect(include_history=True)['checkpoint_details']['before']['handle'] == 'opaque-provider-handle'
    assert original.recover('before')['status'] == 'restored'
    assert backend.mutations() == ['save', 'load']


def test_save_reconciliation_retains_completed_prefix_and_saved_cursor(tmp_path):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend)
    original.run(max_steps=1); backend.after_save = True
    with pytest.raises(ValueError, match='readback'): original.checkpoint('after-key')
    assert original.reconcile()['reconciliation']['status'] == 'reconciled'
    assert original.inspect(include_history=True)['checkpoint_details']['after-key']['cursor'] == 1
    original.run(); original.recover('after-key')
    status = original.inspect()
    assert status['steps'][0]['state'] == 'completed' and status['steps'][1]['state'] == 'pending'
    assert backend.state['$key'] is True


@pytest.mark.parametrize('change', [{'cursor': True}, {'cursor': 1}, {'session_token': 'foreign'},
                                   {'context': 'wrong'}, {'slot': None}, {'operation': 'unsupported'}])
def test_inconsistent_saved_boundary_metadata_never_installs_checkpoint(tmp_path, change):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend); backend.after_save = True
    with pytest.raises(ValueError): original.checkpoint('before')
    doc = json.loads(original.path.read_text()); doc['recovery'].update(change)
    original.path.write_text(json.dumps(doc)); before = original.path.read_bytes()
    assert batch(tmp_path, backend).reconcile()['reconciliation']['status'] == 'unresolved'
    assert original.path.read_bytes() == before and backend.mutations() == ['save']


def test_old_pending_save_without_durable_metadata_remains_unsupported(tmp_path):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend)
    doc = json.loads(original.path.read_text()); doc['recovery'] = {'operation':'save','name':'old'}
    original.path.write_text(json.dumps(doc)); before = original.path.read_bytes()
    assert batch(tmp_path, backend).reconcile()['reconciliation']['status'] == 'unresolved'
    assert original.path.read_bytes() == before and backend.mutations() == []


def test_read_failure_during_save_reconciliation_changes_neither_latch_nor_guest(tmp_path):
    backend = SaveReadbackBackend(); original = batch(tmp_path, backend); backend.after_save = True
    with pytest.raises(ValueError): original.checkpoint('before')
    backend.fail_read = True; held = original.path.read_bytes()
    result = original.reconcile()
    assert result['reconciliation']['operation'] == 'save'
    assert result['reconciliation']['reason'] == 'observation-failed'
    assert original.path.read_bytes() == held and backend.mutations() == ['save']


def test_unqualified_following_read_can_reconcile_from_durable_save_reply(tmp_path):
    class UnqualifiedRead(SaveReadbackBackend):
        def observe(self):
            result = super().observe()
            if getattr(self, 'unqualify_once', False):
                self.unqualify_once = False
                return {'complete': False, 'session_token': self.epoch}
            return result
        def save(self, slot='live'):
            result = super().save(slot); self.unqualify_once = True; return result
    backend = UnqualifiedRead(); original = batch(tmp_path, backend)
    with pytest.raises(ValueError, match='certify'): original.checkpoint('before')
    before = list(backend.operations)
    assert original.reconcile()['reconciliation']['status'] == 'reconciled'
    assert backend.operations[len(before):] == ['observe'] and backend.mutations() == ['save']
