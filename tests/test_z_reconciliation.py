"""Readback repair uses durable replies and read-only, session-bound witnesses."""
import json
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from fixtures_z_scenes import scene_definition
from fdisbull.il_scenes import ILSceneBackend
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import BatchSession, Player


PLAN = [{'id': 'take', 'command': 'take key', 'expect_context': 'courtyard'},
        {'id': 'unlock', 'command': 'use key on gate'}]


class ReadbackBackend(ILSceneBackend):
    def __init__(self):
        super().__init__(scene_definition())
        self.operations = []
        self.fail_read = self.after_action = self.after_load = self.lose_reply = False
        self.rewrite = None

    def observe(self):
        self.operations.append('observe')
        if self.fail_read:
            self.fail_read = False
            raise ValueError('declared following-readback error')
        return super().observe()

    def act(self, request):
        self.operations.append('act')
        result = super().act(request)
        if self.lose_reply:
            raise EOFError('declared lost action reply')
        if self.rewrite:
            result.update(deepcopy(self.rewrite))
        self.fail_read = self.after_action
        return result

    def save(self, slot='live'):
        self.operations.append('save')
        return super().save(slot)

    def load(self, checkpoint='live'):
        self.operations.append('load')
        result = super().load(checkpoint)
        if self.rewrite:
            result.update(deepcopy(self.rewrite))
        self.fail_read = self.after_load
        return result

    def mutations(self):
        return [op for op in self.operations if op != 'observe']


def batch(tmp_path, backend):
    return BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)


def test_confirmed_action_readback_can_reconcile_without_dispatching_or_running_next_step(tmp_path):
    backend = ReadbackBackend(); original = batch(tmp_path, backend)
    backend.after_action = True
    assert original.run()['status'] == 'unknown'
    saved = json.loads(original.path.read_text())['steps'][0]['attempts'][0]
    assert saved['result']['effects'] == 'applied-confirmed'
    reopened = batch(tmp_path, backend)
    before = backend.mutations()
    result = reopened.reconcile()
    assert result['status'] == 'pending' and result['next_step'] == 'unlock'
    assert result['reconciliation']['status'] == 'reconciled'
    assert result['steps'][0]['state'] == 'completed'
    assert result['steps'][0]['attempts'][0]['result'] == saved['result']
    assert result['steps'][0]['attempts'][0]['error_type'] == saved['error_type']
    assert backend.mutations() == before == ['act']
    reopened.reconcile()
    assert backend.mutations() == before and backend.state['$key'] is True


@pytest.mark.parametrize('wrong_identity', [False, True])
def test_provider_navigation_receipt_reconciles_only_the_bound_attempt(tmp_path, wrong_identity):
    class HeldProvider(ReadbackBackend):
        held = False
        def observe(self):
            if self.held:
                return {'complete':False,'session_token':self.receipt['witness']['session_token'],
                        'reconciliation_available':True,
                        'recovery_id':'different' if wrong_identity else 'original-attempt'}
            return super().observe()
        def act(self, request):
            self.receipt = super().act(request)
            self.action = {k:request[k] for k in ('verb','target','item')}
            self.held = True
            return {'complete':False,'status':'incomplete','effects':'unknown',
                    'recovery_required':True,'recovery_id':'original-attempt'}
        def reconcile(self, recovery_id=None):
            assert recovery_id == 'original-attempt'
            self.operations.append('provider-read-only-reconcile')
            self.held = False
            return {**self.receipt,'read_only':True,'recovery_id':recovery_id,
                    'effects':'applied-confirmed','action':self.action}
    backend = HeldProvider(); session = batch(tmp_path, backend)
    assert session.run()['status'] == 'unknown'
    original = json.loads(session.path.read_text())['steps'][0]['attempts'][0]['result']
    result = session.reconcile()
    if wrong_identity:
        assert result['reconciliation']['status'] == 'unresolved' and backend.held
        assert 'provider-read-only-reconcile' not in backend.operations
    else:
        assert result['steps'][0]['state'] == 'completed' and result['next_step'] == 'unlock'
        attempt = result['steps'][0]['attempts'][0]
        assert attempt['result_before_reconciliation'] == original
        assert attempt['result']['read_only'] is True
    assert backend.operations.count('act') == 1


@pytest.mark.parametrize('following_read', ['error', 'unqualified'])
def test_consumed_provider_reconciliation_survives_failed_read_and_journal_reopen(tmp_path, following_read):
    class HeldProvider(ReadbackBackend):
        held = False
        fail_after_reconcile = False

        def observe(self):
            if self.fail_after_reconcile:
                self.fail_after_reconcile = False
                self.operations.append('observe')
                if following_read == 'error':
                    raise ValueError('declared reconciliation readback error')
                return {'complete':False,'session_token':self.receipt['witness']['session_token']}
            if self.held:
                self.operations.append('observe')
                return {'complete':False,'session_token':self.receipt['witness']['session_token'],
                        'reconciliation_available':True,'recovery_id':'original-attempt'}
            return super().observe()

        def act(self, request):
            self.receipt = super().act(request)
            self.action = {k:request[k] for k in ('verb','target','item')}
            self.held = True
            return {'complete':False,'status':'incomplete','effects':'unknown',
                    'recovery_required':True,'recovery_id':'original-attempt'}

        def reconcile(self, recovery_id=None):
            assert self.held, 'The consumed provider reconciliation must not be repeated'
            assert recovery_id == 'original-attempt'
            self.operations.append('provider-read-only-reconcile')
            self.held = False
            self.fail_after_reconcile = True
            self.certificate = {**self.receipt,'read_only':True,'recovery_id':recovery_id,
                                'effects':'applied-confirmed','action':self.action}
            return deepcopy(self.certificate)

    backend = HeldProvider(); session = batch(tmp_path, backend)
    assert session.run()['status'] == 'unknown'
    original = json.loads(session.path.read_text())['steps'][0]['attempts'][0]['result']
    result = session.reconcile()
    assert result['status'] == 'unknown' and result['reconciliation']['status'] == 'unresolved'
    assert result['reconciliation']['reason'] == (
        'observation-failed' if following_read == 'error' else 'unqualified-observation')
    assert not backend.held
    saved = json.loads(session.path.read_text())['steps'][0]
    assert saved['state'] == 'unknown'
    assert saved['attempts'][0]['result_before_reconciliation'] == original
    assert saved['attempts'][0]['result'] == backend.certificate
    before = backend.mutations()
    assert before == ['act', 'provider-read-only-reconcile']

    reopened = batch(tmp_path, backend)
    result = reopened.reconcile()
    assert result['reconciliation']['status'] == 'reconciled'
    assert result['steps'][0]['state'] == 'completed'
    assert result['status'] == 'pending' and result['next_step'] == 'unlock'
    assert result['steps'][1]['state'] == 'pending' and result['steps'][1]['attempts'] == []
    attempt = result['steps'][0]['attempts'][0]
    assert attempt['result_before_reconciliation'] == original
    assert attempt['result'] == backend.certificate
    assert backend.state['$key'] is True
    assert backend.mutations() == before
    assert reopened.reconcile()['reconciliation']['status'] == 'not-needed'
    assert backend.mutations() == before


def test_restore_reply_is_durable_before_following_read_and_reconciliation_rewinds_only_journal(tmp_path):
    backend = ReadbackBackend(); original = batch(tmp_path, backend)
    original.checkpoint('before'); original.run(max_steps=1)
    backend.after_load = True
    with pytest.raises(ValueError, match='readback'):
        original.recover('before')
    document = json.loads(original.path.read_text())
    assert document['recovery']['result']['status'] == 'restored'
    assert document['recovery']['result']['witness']['session_token'] == document['session_token']
    reopened = batch(tmp_path, backend)
    before = backend.mutations()
    result = reopened.reconcile()
    assert result['status'] == 'pending' and result['next_step'] == 'take'
    assert result['reconciliation']['status'] == 'reconciled'
    assert backend.mutations() == before == ['save', 'act', 'load']
    inspection = reopened.inspect(include_history=True)
    assert inspection['recovery'] is None and len(inspection['history']) == 1
    assert inspection['history'][0]['superseded'][0]['state'] == 'completed'
    assert inspection['history'][0]['receipt'] == document['recovery']['result']
    assert reopened.reconcile()['reconciliation']['status'] == 'verified'
    assert len(reopened.inspect(include_history=True)['history']) == 1
    assert backend.mutations() == before


@pytest.mark.parametrize('reply', [None, {'complete': False}, {'effects': 'unknown'},
                                  {'witness': None}, {'witness': {'session_token': 'foreign'}}])
def test_lost_incomplete_unknown_or_unbound_action_reply_cannot_be_reconciled(tmp_path, reply):
    backend = ReadbackBackend(); original = batch(tmp_path, backend)
    backend.after_action = True
    if reply is None: backend.lose_reply = True
    else: backend.rewrite = reply
    assert original.run()['status'] == 'unknown'
    before = backend.mutations()
    result = original.reconcile()
    assert result['status'] == 'unknown' and result['reconciliation']['status'] == 'unresolved'
    assert backend.mutations() == before == ['act']


@pytest.mark.parametrize('rewrite', [{'replay_safe': False}, {'checkpoint': 'different'},
                                    {'witness': None}, {'complete': False}])
def test_uncertified_restore_stays_latched_even_at_matching_destination(tmp_path, rewrite):
    backend = ReadbackBackend(); original = batch(tmp_path, backend)
    original.checkpoint('before'); original.run(max_steps=1)
    backend.after_load = True; backend.rewrite = rewrite
    with pytest.raises(ValueError, match='readback'): original.recover('before')
    before = backend.mutations()
    result = original.reconcile()
    assert result['status'] == 'recovery-incomplete'
    assert result['reconciliation']['status'] == 'unresolved'
    with pytest.raises(ValueError, match='recovery was interrupted'): original.run()
    assert backend.mutations() == before


@pytest.mark.parametrize('restore', [False, True])
def test_intervening_action_invalidates_witness_even_in_same_scene(tmp_path, restore):
    backend = ReadbackBackend(); original = batch(tmp_path, backend)
    if restore:
        original.checkpoint('before'); original.run(max_steps=1); backend.after_load = True
        with pytest.raises(ValueError): original.recover('before')
    else:
        backend.after_action = True; original.run()
    # Use the supported provider interface to change its revision at the same context.
    backend.after_action = backend.after_load = False
    command = 'take key' if restore else 'use key on gate'
    assert Player(backend).execute_result(command)['status'] == 'success'
    before = backend.mutations()
    result = original.reconcile()
    assert result['reconciliation']['status'] == 'unresolved'
    assert backend.mutations() == before


def test_history_opt_in_is_read_only_and_detached_and_completed_restore_can_be_verified(tmp_path):
    backend = ReadbackBackend(); original = batch(tmp_path, backend)
    original.checkpoint('before'); original.run(max_steps=1)
    assert original.recover('before')['status'] == 'restored'
    before = list(backend.operations)
    assert 'history' not in original.inspect()
    expanded = original.inspect(include_history=True)
    assert len(expanded['history']) == 1
    expanded['history'].clear()
    assert len(original.inspect(include_history=True)['history']) == 1
    assert backend.operations == before
    assert original.reconcile()['reconciliation']['status'] == 'verified'
    assert backend.mutations() == ['save', 'act', 'load']
    with pytest.raises(ValueError): original.inspect(include_history='yes')


def test_partial_original_effect_stays_unconfirmed_after_reconciling_a_continuation(tmp_path):
    class PartialOriginal(ReadbackBackend):
        def act(self, request):
            self.rewrite = ({'status': 'accepted', 'effects': 'partial',
                             'continuation': {'context': 'courtyard', 'command': 'use key on gate'}}
                            if request['verb'] == 'take' else None)
            return super().act(request)
    backend = PartialOriginal(); backend.after_action = True
    plan = [{'id': 'take', 'command': 'take key', 'expect_context': 'courtyard',
             'continuations': {'courtyard': 'use key on gate'}}]
    original = BatchSession(Player(backend), tmp_path / 'partial.json', plan)
    assert original.run()['status'] == 'unknown'
    assert original.reconcile()['status'] == 'paused'
    assert original.resume()['status'] == 'unknown'
    result = original.reconcile()
    assert result['status'] == 'paused' and result['reason'] == 'original-intent-unconfirmed'
    assert backend.mutations() == ['act', 'act']
    assert result['steps'][0]['attempts'][0]['result']['effects'] == 'partial'


def test_readback_failure_during_reconciliation_and_foreign_session_do_not_change_journal(tmp_path):
    backend = ReadbackBackend(); original = batch(tmp_path, backend)
    backend.after_action = True; original.run()
    before = original.path.read_bytes()
    backend.fail_read = True
    assert original.reconcile()['reconciliation']['reason'] == 'observation-failed'
    assert original.path.read_bytes() == before
    backend.epoch = 'different-native-session'
    assert original.reconcile()['reconciliation']['status'] == 'unresolved'
    assert original.path.read_bytes() == before
    assert backend.mutations() == ['act']


def test_reconciliation_and_history_have_public_batch_cli_operations(tmp_path):
    import os
    import shlex
    import subprocess
    from fixtures_z_scenes import write_scene
    root = Path(__file__).resolve().parents[1]
    plan = tmp_path / 'plan.json'; plan.write_text(json.dumps(PLAN))
    env = dict(os.environ, PYTHONPATH=str(root / 'src') + os.pathsep + str(root / 'player'))
    command = shlex.join([sys.executable, '-m', 'fdisbull.il_scenes', str(write_scene(tmp_path / 'scene.json'))])
    operations = [{'op': 'checkpoint', 'name': 'start'}, {'op': 'run', 'max_steps': 1},
                  {'op': 'recover', 'name': 'start'}, {'op': 'inspect', 'include_history': True},
                  {'op': 'reconcile'}, {'op': 'inspect'}]
    result = subprocess.run([sys.executable, '-m', 'fdisbull_player', '--backend-command', command,
                             '--batch-plan', str(plan), '--batch-journal', str(tmp_path / 'batch.json')],
                            input=''.join(json.dumps(x) + '\n' for x in operations),
                            capture_output=True, text=True, env=env, timeout=10)
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(replies[3]['history']) == 1 and replies[3]['recovery'] is None
    assert replies[4]['reconciliation']['status'] == 'verified'
    assert 'history' not in replies[5] and 'steps' not in replies[5]


def test_cli_keeps_batch_available_after_restore_readback_error(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    from fdisbull_player import __main__ as cli
    backend = ReadbackBackend(); backend.after_load = True
    plan = tmp_path / 'plan.json'; plan.write_text(json.dumps(PLAN))
    operations = [{'op': 'checkpoint', 'name': 'start'}, {'op': 'run', 'max_steps': 1},
                  {'op': 'recover', 'name': 'start'}, {'op': 'run'}, {'op': 'resume'},
                  {'op': 'checkpoint', 'name': 'unsafe'}, {'op': 'reconcile'},
                  {'op': 'inspect', 'include_history': True}]
    writer = io.StringIO()
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(''.join(json.dumps(x) + '\n' for x in operations)))
    monkeypatch.setattr(cli.sys, 'stdout', writer)
    assert cli.run_mode(backend, SimpleNamespace(batch_plan=str(plan),
                        batch_journal=str(tmp_path / 'cli-batch.json'))) == 0
    replies = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert replies[2]['status'] == 'recovery-incomplete' and replies[2]['complete'] is False
    assert all(r['status'] == 'recovery-incomplete' and r['complete'] is False for r in replies[3:6])
    assert replies[6]['reconciliation']['status'] == 'reconciled'
    assert len(replies[7]['history']) == 1 and replies[7]['recovery'] is None
    assert backend.mutations() == ['save', 'act', 'load']
