"""Recovery through real typed-IL actions; native correspondence is separate."""
import json
from pathlib import Path
import sys

import pytest
from fixtures_z_scenes import scene_definition
from fdisbull.il_scenes import ILSceneBackend

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import BatchSession, Player

PLAN = [{'id': 'take', 'command': 'take key'},
        {'id': 'unlock', 'command': 'use key on gate'},
        {'id': 'travel', 'command': 'n', 'expect_context': 'garden'}]


class CountedBackend(ILSceneBackend):
    def __init__(self):
        super().__init__(scene_definition())
        self.inputs = []
        self.lose_result = False

    def act(self, request):
        self.inputs.append(dict(request))
        result = super().act(request)
        if self.lose_result:
            self.lose_result = False
            raise EOFError('deliberately lost reply after commit')
        return result


def test_reopen_continues_pending_steps_without_replaying_completed_actions(tmp_path):
    backend = CountedBackend()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    assert batch.run(max_steps=1)['status'] == 'pending'
    assert len(backend.inputs) == 1 and backend.state['$key'] is True
    reopened = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    assert reopened.run()['complete'] is True
    assert [x['verb'] for x in backend.inputs] == ['take', 'use', 'go']
    assert backend.state['$moves'] == 1
    assert batch.inspect()['complete'] is True


def test_lost_reply_blocks_until_verified_rewind_then_preserves_superseded_evidence(tmp_path):
    backend = CountedBackend()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    batch.checkpoint('before-purchase')
    backend.lose_result = True
    assert batch.run()['status'] == 'unknown'
    assert backend.state['$key'] is True
    reopened = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    assert reopened.resume()['status'] == 'unknown'
    assert len(backend.inputs) == 1
    assert reopened.recover('before-purchase')['status'] == 'restored'
    assert backend.state['$key'] is False
    assert reopened.run()['complete'] is True
    data = json.loads((tmp_path / 'batch.json').read_text())
    assert data['history'][0]['superseded'][0]['state'] == 'unknown'
    assert data['history'][0]['superseded'][0]['attempts'][0]['error_type'] == 'EOFError'
    assert len(backend.inputs) == 4  # One discarded branch, three current-branch intents.


def test_declared_continuation_sends_a_new_action_once_and_never_repeats_original(tmp_path):
    class Interrupted(CountedBackend):
        def act(self, request):
            result = super().act(request)
            if request['verb'] == 'take':
                result.update(status='accepted', effects='partial',
                              continuation={'context':'courtyard','command':'use key on gate'})
            return result
    backend = Interrupted()
    plan = [{'id': 'setup', 'command': 'take key', 'expect_context': 'courtyard',
             'continuations': {'courtyard': 'use key on gate'}}, PLAN[2]]
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', plan)
    assert batch.run()['status'] == 'paused'
    assert batch.inspect()['reason'] == 'continuation-required'
    assert batch.run()['status'] == 'paused'
    assert len(backend.inputs) == 1
    resumed = batch.resume()
    assert resumed['status'] == 'paused' and resumed['reason'] == 'original-intent-unconfirmed'
    assert [x['verb'] for x in backend.inputs] == ['take', 'use']
    assert batch.inspect()['steps'][0]['attempts'][1]['kind'] == 'continuation'


def test_unknown_confirmed_effect_is_preserved_and_not_retried(tmp_path):
    class FollowupFailed(CountedBackend):
        def act(self, request):
            result = super().act(request)
            result.update(status='incomplete', complete=False, effects='applied-confirmed')
            return result
    backend = FollowupFailed()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    result = batch.run()
    assert result['status'] == 'unknown'
    assert result['steps'][0]['attempts'][0]['result']['effects'] == 'applied-confirmed'
    assert batch.resume()['status'] == 'unknown'
    assert len(backend.inputs) == 1


def test_crashed_dispatch_and_foreign_session_never_dispatch_on_reopen(tmp_path):
    backend = CountedBackend()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    doc = json.loads(batch.path.read_text())
    doc['steps'][0]['state'] = 'running'  # Durable pre-dispatch boundary left by a killed driver.
    batch.path.write_text(json.dumps(doc))
    assert BatchSession(Player(backend), batch.path, PLAN).run()['status'] == 'unknown'
    assert backend.inputs == []
    other = BatchSession(Player(CountedBackend()), batch.path, PLAN)
    with pytest.raises(ValueError, match='session changed'):
        other.run()


def test_plan_changes_and_recovery_without_provider_certificate_are_refused(tmp_path):
    backend = CountedBackend()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    with pytest.raises(ValueError, match='plan'):
        BatchSession(Player(backend), batch.path, list(reversed(PLAN)))
    backend.save = lambda slot: {'status': 'saved', 'complete': True, 'checkpoint': slot}
    with pytest.raises(ValueError, match='certify'):
        batch.checkpoint('unsafe')
    assert backend.inputs == []


def test_failed_restore_latches_batch_and_cannot_authorize_new_input(tmp_path):
    backend = CountedBackend()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', PLAN)
    batch.checkpoint('safe')
    batch.run(max_steps=1)
    backend.load = lambda name: {'complete': True, 'status': 'restored', 'replay_safe': False}
    assert batch.recover('safe')['status'] == 'recovery-incomplete'
    assert BatchSession(Player(backend), batch.path, PLAN).inspect()['status'] == 'recovery-incomplete'
    with pytest.raises(ValueError, match='recovery was interrupted'):
        batch.run()
    assert len(backend.inputs) == 1


def test_bad_command_is_a_rejection_and_never_skipped_as_a_successful_read(tmp_path):
    backend = CountedBackend()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', [{'id': 'bad', 'command': 'buy nonexistent'}])
    assert batch.run()['status'] == 'rejected'
    assert backend.inputs == []


def test_committed_effect_with_unmet_destination_has_distinct_pause_reason(tmp_path):
    backend = CountedBackend()
    batch = BatchSession(Player(backend), tmp_path / 'batch.json',
                         [{'id':'take','command':'take key','expect_context':'garden'}])
    result = batch.run()
    assert result['status'] == 'paused' and result['reason'] == 'destination-mismatch'
    assert result['steps'][0]['attempts'][0]['result']['effects'] == 'applied-confirmed'
    assert batch.resume()['reason'] == 'destination-mismatch'
    assert len(backend.inputs) == 1


def test_repeated_partial_continuation_and_invalid_resume_budget_send_no_extra_input(tmp_path):
    class StillInterrupted(CountedBackend):
        def act(self, request):
            result = super().act(request)
            result.update(status='accepted', effects='partial',
                          continuation={'context':'courtyard','command':'use key on gate'})
            return result
    backend = StillInterrupted()
    plan = [{'id': 'setup', 'command': 'take key',
             'continuations': {'courtyard': 'use key on gate'}}]
    batch = BatchSession(Player(backend), tmp_path / 'batch.json', plan)
    assert batch.run()['status'] == 'paused'
    with pytest.raises(ValueError): batch.resume(max_steps=0)
    assert len(backend.inputs) == 1
    assert batch.resume()['status'] == 'paused'
    assert batch.resume()['status'] == 'paused'
    assert len(backend.inputs) == 2


def test_batch_cli_uses_the_installed_public_operation_shape(tmp_path):
    import os, shlex, subprocess
    from fixtures_z_scenes import write_scene
    root = Path(__file__).resolve().parents[1]
    plan = tmp_path / 'plan.json'; plan.write_text(json.dumps(PLAN))
    env = dict(os.environ, PYTHONPATH=str(root / 'src') + os.pathsep + str(root / 'player'))
    backend = shlex.join([sys.executable, '-m', 'fdisbull.il_scenes', str(write_scene(tmp_path / 'scene.json'))])
    operations = [{'op':'checkpoint','name':'start'}, {'op':'run','max_steps':1},
                  {'op':'run'}, {'op':'recover','name':'start'}, {'op':'run'}, {'op':'inspect'}]
    result = subprocess.run([sys.executable, '-m', 'fdisbull_player', '--backend-command', backend,
                             '--batch-plan', str(plan), '--batch-journal', str(tmp_path / 'batch.json')],
                            input=''.join(json.dumps(x) + '\n' for x in operations),
                            capture_output=True, text=True, env=env, timeout=10)
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert [x['status'] for x in replies] == ['saved', 'pending', 'completed', 'restored', 'completed', 'completed']
    assert len(result.stdout) < 2048

@pytest.mark.parametrize('continuation', ['take key', 'take brass key'])
def test_partial_action_cannot_be_repeated_through_original_or_alias(tmp_path, continuation):
    class Partial(CountedBackend):
        def observe(self):
            result = super().observe()
            for obj in result.get('objects', []) + result.get('inventory', []):
                if obj['label'].casefold() == 'key':
                    obj['aliases'].append('brass key')
            return result
        def act(self, request):
            result = super().act(request)
            if request['verb'] == 'take':
                result.update(status='accepted', effects='partial',
                              continuation={'context':'courtyard','command':continuation})
            return result
    backend = Partial()
    plan = [{'id':'take', 'command':'take key', 'continuations':{'courtyard':continuation}}]
    batch = BatchSession(Player(backend), tmp_path/'batch.json', plan)
    assert batch.run()['status'] == 'paused'
    result = batch.resume()
    assert len(backend.inputs) == 1
    assert result['status'] == 'paused'
    assert result['steps'][0]['attempts'][0]['result']['effects'] == 'partial'


def test_passive_or_unrelated_continuation_does_not_certify_partial_intent(tmp_path):
    class Partial(CountedBackend):
        def act(self, request):
            result = super().act(request)
            if request['verb'] == 'take':
                result.update(status='accepted',effects='partial',
                              continuation={'context':'courtyard','command':'look'})
            return result
    backend=Partial()
    plan=[{'id':'take','command':'take key','continuations':{'courtyard':'look'}}]
    batch=BatchSession(Player(backend),tmp_path/'batch.json',plan)
    assert batch.run()['status']=='paused'
    result=batch.resume()
    assert result['status']=='paused' and not result['complete']
    assert result['steps'][0]['attempts'][0]['result']['effects']=='partial'
    assert len(backend.inputs)==1


def test_plan_alone_does_not_authorize_continuation(tmp_path):
    class Partial(CountedBackend):
        def act(self, request):
            result=super().act(request)
            if request['verb']=='take': result.update(status='accepted',effects='partial')
            return result
    backend=Partial()
    plan=[{'id':'take','command':'take key','continuations':{'courtyard':'use key on gate'}}]
    batch=BatchSession(Player(backend),tmp_path/'batch.json',plan)
    assert batch.run()['status']=='paused'
    assert batch.resume()['status']=='paused'
    assert len(backend.inputs)==1


def test_confirmed_effect_can_finish_after_authorized_destination_change(tmp_path):
    class Confirmed(CountedBackend):
        def act(self, request):
            result = super().act(request)
            if request['verb'] == 'take':
                result['continuation'] = {'context':'courtyard','command':'n'}
            return result
    backend = Confirmed()
    backend.state['$unlocked'] = True
    plan = [{'id':'take','command':'take key','expect_context':'garden',
             'continuations':{'courtyard':'n'}}]
    batch = BatchSession(Player(backend),tmp_path/'batch.json',plan)
    assert batch.run()['reason'] == 'destination-mismatch'
    result = batch.resume()
    assert result['complete'] and result['status'] == 'completed'
    assert result['steps'][0]['attempts'][0]['result']['effects'] == 'applied-confirmed'
    assert [item['verb'] for item in backend.inputs] == ['take','go']


def test_provider_authorization_must_match_current_context_and_command(tmp_path):
    class Partial(CountedBackend):
        def act(self, request):
            result = super().act(request)
            if request['verb'] == 'take':
                result.update(status='accepted',effects='partial',
                              continuation={'context':'elsewhere','command':'use key on gate'})
            return result
    backend = Partial()
    plan = [{'id':'take','command':'take key','continuations':{'courtyard':'use key on gate'}}]
    batch = BatchSession(Player(backend),tmp_path/'batch.json',plan)
    assert batch.run()['status'] == 'paused'
    assert batch.resume()['status'] == 'paused'
    assert len(backend.inputs) == 1
