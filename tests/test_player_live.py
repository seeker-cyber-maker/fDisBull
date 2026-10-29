import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_text_player import adventure_package, package
from fdisbull_player import LocalRuntime, LiveSession, Player, self_play

ROOT = Path(__file__).resolve().parents[1]


def test_restore_positions_state_events_and_invalidates_token(tmp_path):
    p = adventure_package()
    p['scheduled'] = [{'tick': 2, 'effects': [{'op': 'event', 'name': 'bell'}]}]
    r = LocalRuntime(p, tmp_path); old_token = r.observe()['context']['token']
    result = LiveSession(r).run_turn(['take key', 'use key on gate', 'go east'])
    assert result['checkpoint']['status'] == 'saved'
    restored = LocalRuntime(p, tmp_path); session = LiveSession(restored)
    result = session.run_turn(['inventory'])
    assert result['restore']['status'] == 'restored'
    assert result['outcomes'][0]['outcome'] == 'Carrying: brass key.'
    assert restored.context_id == 'hall' and restored.state['unlocked'] and restored.tick == 3
    assert restored.events == [{'tick': 2, 'name': 'bell'}]
    assert restored.observe()['context']['token'] != old_token
    assert restored.act({'context_token': old_token, 'verb': 'go', 'target': 'west', 'item': None})['status'] == 'rejected'


def test_corrupt_or_wrong_package_never_mutates_or_starts_fresh(tmp_path):
    p = adventure_package(); r = LocalRuntime(p, tmp_path)
    assert r.save()['status'] == 'saved'
    path = tmp_path / 'live.json'; saved = json.loads(path.read_text())
    for alter in (lambda x: x.update(package_hash='wrong'), lambda x: x['positions']['yard'].append('key'),
                  lambda x: x.update(tick=-1), lambda x: x.update(context='unknown'),
                  lambda x: x['events'].append({'tick': 100, 'name': 'bad'})):
        value = json.loads(json.dumps(saved)); alter(value); path.write_text(json.dumps(value))
        candidate = LocalRuntime(p, tmp_path); before = candidate.observe()
        result = LiveSession(candidate).run_turn(['take key'])
        assert result['restore']['status'] == 'incomplete' and not result['outcomes']
        assert candidate.observe() == before and candidate.tick == 0
    path.write_text('{')
    assert LocalRuntime(p, tmp_path).load()['status'] == 'incomplete'


def test_partial_effects_are_saved_and_failed_save_is_explicit(tmp_path):
    p = package(); p['actions'][0]['steps'][1]['effects'].append({'op': 'stop'})
    r = LocalRuntime(p, tmp_path); result = LiveSession(r).run_turn(['go east'])
    assert result['outcomes'][0]['outcome'].startswith('Incomplete')
    restored = LocalRuntime(p, tmp_path); assert restored.load()['status'] == 'restored'
    assert (restored.tick, restored.state['position']) == (1, 2)
    r.save = lambda slot: {'status': 'saved', 'complete': False, 'checkpoint': 'live'}
    session = LiveSession(r); result = session.run_turn(['look'])
    assert result['checkpoint']['status'] == 'incomplete' and session.blocked


def test_new_process_resume_cli(tmp_path):
    path = tmp_path / 'game.json'; path.write_text(json.dumps(adventure_package()))
    args = [sys.executable, '-m', 'fdisbull_player', '--package', str(path), '--live', '--save-dir', str(tmp_path / 'saves')]
    first = subprocess.run(args, input=json.dumps({'commands':['take key', 'use key on gate']})+'\n', text=True, capture_output=True, cwd=ROOT/'player')
    second = subprocess.run(args, input=json.dumps({'commands':['go east', 'inventory']})+'\n', text=True, capture_output=True, cwd=ROOT/'player')
    assert first.returncode == second.returncode == 0, (first.stderr, second.stderr)
    result = json.loads(second.stdout)
    assert result['restore']['status'] == 'restored' and result['checkpoint']['status'] == 'saved'
    assert result['outcomes'][0]['outcome'] == 'Success: You enter the hall.'
    assert result['outcomes'][1]['outcome'] == 'Carrying: brass key.'


def test_external_agent_choices_and_narration(tmp_path):
    script = tmp_path / 'agent.py'
    script.write_text('''import json, sys\nfor line in sys.stdin:\n r=json.loads(line); i=r["turn"]; commands=[["take key"],["use key on gate"],["go east"]][i]\n print(json.dumps({"commands":commands,"narration":"Chapter "+str(i),"done":i==2}), flush=True)\n''')
    runtime = LocalRuntime(adventure_package(), tmp_path / 'saves'); output=[]
    transcript = self_play(LiveSession(runtime), [sys.executable, str(script)], emit=output.append)
    assert transcript['status'] == 'agent_done'
    assert [t['outcomes'][0]['command'] for t in transcript['turns']] == ['take key', 'use key on gate', 'go east']
    assert any('Chapter 0' in line for line in output) and any('You enter the hall' in line for line in output)
    assert runtime.context_id == 'hall'


def test_external_agent_timeout(tmp_path):
    script = tmp_path / 'slow.py'; script.write_text('import time\ntime.sleep(10)\n')
    result = self_play(LiveSession(LocalRuntime(adventure_package(), tmp_path)), [sys.executable, str(script)], agent_timeout=.1, wall_seconds=1, emit=lambda _:None)
    assert result['status'] == 'agent_or_backend_error' and 'timed out' in result['error']


def test_pending_clarification_cleared_on_restore(tmp_path):
    p = package(); runtime = LocalRuntime(p, tmp_path)
    assert runtime.save()['status'] == 'saved'
    session = LiveSession(runtime)
    assert session.player.execute('take key').startswith('Which one?')
    assert session.player.pending is not None
    assert session.start()['status'] == 'restored'
    assert session.player.pending is None
    assert 'no action sent' in session.run_turn(['1'])['outcomes'][0]['outcome']


def test_json_backend_checkpoint_wire_protocol():
    from io import StringIO
    from fdisbull_player import JsonLineBackend
    reader = StringIO('{"status":"saved","complete":true,"checkpoint":"opaque"}\n'
                      '{"status":"restored","complete":true,"checkpoint":"opaque"}\n')
    writer = StringIO(); backend = JsonLineBackend(reader, writer)
    assert backend.save()['checkpoint'] == 'opaque'
    assert backend.load('opaque')['status'] == 'restored'
    assert [json.loads(line) for line in writer.getvalue().splitlines()] == [
        {'op':'save', 'slot':'live'}, {'op':'load', 'checkpoint':'opaque'}]


def test_cli_self_play_and_private_transcript(tmp_path):
    game = tmp_path / 'game.json'; game.write_text(json.dumps(adventure_package()))
    agent = tmp_path / 'agent.py'
    agent.write_text('''import json,sys\nfor line in sys.stdin:\n r=json.loads(line); i=r["turn"]; print(json.dumps({"commands":[["take key"],["use key on gate"],["go east"]][i],"narration":"Journey "+str(i),"done":i==2}),flush=True)\n''')
    transcript = tmp_path / 'transcript.json'
    import shlex
    result = subprocess.run([sys.executable, '-m', 'fdisbull_player', '--package', str(game), '--live',
                             '--save-dir', str(tmp_path/'saves'), '--agent-command', shlex.join([sys.executable, str(agent)]),
                             '--transcript', str(transcript)], text=True, capture_output=True, cwd=ROOT/'player')
    assert result.returncode == 0, result.stderr
    assert 'Journey 0' in result.stdout and '> go east' in result.stdout and 'You enter the hall' in result.stdout
    assert json.loads(transcript.read_text())['status'] == 'agent_done'
    assert os.stat(transcript).st_mode & 0o077 == 0


def test_incomplete_action_stops_turn_and_self_play_but_saves_partial_effects(tmp_path):
    p = package(); p['actions'][0]['steps'][1]['effects'].append({'op': 'stop'})
    runtime = LocalRuntime(p, tmp_path / 'saves')
    result = LiveSession(runtime).run_turn(['go east', 'go east'])
    assert result['status'] == 'incomplete' and len(result['outcomes']) == 1
    assert result['outcomes'][0]['status'] == 'incomplete'
    assert (runtime.tick, runtime.state['position']) == (1, 2)
    restored = LocalRuntime(p, tmp_path / 'saves')
    assert restored.load()['status'] == 'restored'
    assert (restored.tick, restored.state['position']) == (1, 2)

    agent = tmp_path / 'agent.py'
    agent.write_text('''import json, sys\nfor line in sys.stdin:\n print(json.dumps({"commands":["go east", "go east"], "narration":"Move", "done":False}), flush=True)\n''')
    other = LocalRuntime(p, tmp_path / 'other')
    transcript = self_play(LiveSession(other), [sys.executable, str(agent)], emit=lambda _: None)
    assert transcript['status'] == 'checkpoint_or_turn_failure'
    assert len(transcript['turns']) == 1 and other.tick == 1


def test_rejection_and_clarification_allow_following_commands(tmp_path):
    runtime = LocalRuntime(adventure_package(), tmp_path)
    result = LiveSession(runtime).run_turn(['go east', 'take key'])
    assert result['status'] == 'complete'
    assert [x['status'] for x in result['outcomes']] == ['rejected', 'success']
    assert len(runtime.inventory) == 1
    p = adventure_package()
    duplicate = dict(p['contexts']['yard']['objects'][0], id='key2', label='iron key')
    p['contexts']['yard']['objects'].append(duplicate)
    runtime = LocalRuntime(p, tmp_path / 'clarify')
    result = LiveSession(runtime).run_turn(['take key', '1'])
    assert len(result['outcomes']) == 2
    assert result['outcomes'][0]['outcome'].startswith('Which one?')
    assert result['outcomes'][1]['outcome'] == 'Success: Taken.'


def test_wall_limit_rechecked_after_slow_observation(tmp_path):
    import time
    class SlowObserve(LocalRuntime):
        def observe(self):
            time.sleep(.12)
            return super().observe()
    agent = tmp_path / 'agent.py'
    agent.write_text('''import json, sys\nfor line in sys.stdin:\n print(json.dumps({"commands":["take key"],"narration":"Take it","done":True}),flush=True)\n''')
    runtime = SlowObserve(adventure_package(), tmp_path / 'saves')
    transcript = self_play(LiveSession(runtime), [sys.executable, str(agent)], wall_seconds=.05, emit=lambda _: None)
    assert transcript['status'] == 'wall_limit' and transcript['turns'] == []
    assert runtime.tick == 0 and not runtime.inventory


def test_wall_limit_rechecked_after_agent_response(tmp_path, monkeypatch):
    import time
    from fdisbull_player.live import AgentProcess
    def slow_response(self, payload, timeout):
        time.sleep(.08)
        return {'commands': ['take key'], 'narration': 'Take it', 'done': True}
    monkeypatch.setattr(AgentProcess, 'request', slow_response)
    agent = tmp_path / 'agent.py'; agent.write_text('import time\ntime.sleep(10)\n')
    runtime = LocalRuntime(adventure_package(), tmp_path / 'saves')
    transcript = self_play(LiveSession(runtime), [sys.executable, str(agent)], wall_seconds=.05, emit=lambda _: None)
    assert transcript['status'] == 'wall_limit' and transcript['turns'] == []
    assert runtime.tick == 0 and not runtime.inventory
