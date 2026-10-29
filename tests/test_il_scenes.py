"""Z consumes public scenes; original/reconstructed rules stay in shared IL."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from fdisbull.il_scenes import ILSceneBackend
from fdisbull.il_recovery import recover_v3_attributes, save_il
from fdisbull.project import Project

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'player'))
from fdisbull_player import Player, LiveSession

ROOT = Path(__file__).resolve().parents[1]


def definition():
    return json.loads((ROOT / 'examples/z/key-and-gate.json').read_text())


def test_z_uses_shared_il_for_guard_inventory_and_scene_changes():
    backend = ILSceneBackend(definition()); player = Player(backend)
    initial = deepcopy(backend.state)
    assert 'Courtyard' in player.execute('look')
    assert 'small brass key' in player.execute('x key')
    assert backend.state == initial
    assert player.execute('n') == 'Rejected: Action refused.'
    assert player.execute('take key') == 'Success: You take the brass key.'
    assert player.execute('inventory') == 'Carrying: brass key.'
    assert player.execute('use key on gate') == 'Success: You unlock the gate.'
    assert player.execute('north') == 'Success: You pass through the gate into the garden.'
    assert 'Garden' in player.execute('look')
    assert player.execute('s') == 'Success: You return to the courtyard.'
    assert backend.state == {'$key': True, '$unlocked': True, '$room': 0, '$moves': 2}
    assert backend.programs['north'] == definition()['programs']['north']


def test_stale_and_hidden_requests_cannot_dispatch_or_expose_rules():
    backend = ILSceneBackend(definition()); obs = backend.observe()
    request = {'verb': 'take', 'target': 'key', 'item': None, 'context_token': obs['context']['token']}
    assert backend.act(request)['status'] == 'success'
    state = deepcopy(backend.state)
    assert backend.act(request)['status'] == 'rejected'
    assert backend.state == state
    text = json.dumps(backend.observe())
    for hidden in ('programs', '$unlocked', 'evidence', 'require', 'sources', 'variables'):
        assert hidden not in text
    assert backend.act({**request, 'target': 'unseen', 'context_token': backend.observe()['context']['token']})['status'] == 'rejected'


def test_missing_host_capability_never_commits_or_narrates_success():
    doc = definition(); program = doc['programs']['take-key']
    program['body'].append({'id': 'host', 'op': 'click', 'target': 'original-private-button'})
    backend = ILSceneBackend(doc); before = deepcopy(backend.state)
    assert Player(backend).execute('take key') == 'Incomplete: Action unsupported or incomplete.'
    assert backend.state == before


def test_known_commit_survives_missing_followup_context():
    doc = definition()
    doc['programs']['north']['body'][1]['value'] = 99
    backend = ILSceneBackend(doc); player = Player(backend)
    player.execute('take key'); player.execute('use key on gate')
    assert player.execute('n').startswith('Success:')
    assert backend.state['$room'] == 99
    assert backend.observe() == {'complete': False}


def test_memory_checkpoints_support_bounded_model_turns_and_invalidate_tokens():
    backend = ILSceneBackend(definition()); session = LiveSession(backend)
    assert session.start()['status'] == 'missing'
    token = backend.observe()['context']['token']
    turn = session.run_turn(['take key', 'use key on gate', 'n'])
    assert turn['status'] == 'complete' and turn['checkpoint']['status'] == 'saved'
    assert backend.state['$room'] == 1
    assert backend.observe()['context']['token'] != token
    Player(backend).execute('s')
    assert backend.load('live')['status'] == 'restored'
    assert backend.state['$room'] == 1
    assert ILSceneBackend(definition()).load('live')['status'] == 'missing'


def test_source_checked_udl_revision_reopens_without_debugger(tmp_path):
    binary = tmp_path / 'test.com'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    source = tmp_path / 'story'; source.write_bytes(b'\x03' + bytes(63) + bytes.fromhex('4b860b4b8603'))
    program = recover_v3_attributes(source.read_bytes(), [64, 67], source_file='story',
                                   object_variable=134, bindings={11: '$opened', 3: '$seen'})
    doc = {'format': 'fdisbull-il-scene-1', 'programs': {}, 'partial': True,
           'contexts': [{'id': 'room', 'title': 'Room', 'description': 'A test container.',
                         'when': {'op': 'eq', 'left': True, 'right': True}}],
           'objects': [{'id': 'box', 'context': 'room', 'label': 'box', 'aliases': [],
                        'description': 'A source-bound test object.', 'bindings': [{'verb': 'open', 'program': 'open'}]}]}
    database = tmp_path / 'source.fdb'
    with Project.create(database, binary, image='com') as project:
        project.attach_file(source, name='story')
        revision = save_il(project, 'open', program)
    doc['programs']['open'] = {'revision': revision['id']}
    with Project(database) as project:
        backend = ILSceneBackend(doc, project=project)
    assert Player(backend).execute('open box') == 'Success: Action completed.'
    assert backend.state == {'$opened': True, '$seen': True}
    assert backend.sources['open']['sha256'] == revision['sha256']
    with Project(database) as project:
        project.db.execute('UPDATE external_files SET data=? WHERE name=?', (b'changed', 'story'))
        project.db.commit()
        with pytest.raises(ValueError, match='hash'):
            ILSceneBackend(doc, project=project)


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(execute_host=True),
    lambda d: d['programs']['north']['variables']['$room'].update(type=[]),
    lambda d: d['objects'][0]['bindings'][0].update(program='missing'),
    lambda d: d['contexts'][0].update(when={'op': 'call_native'}),
    lambda d: d['objects'][0].update(aliases='key'),
])
def test_bad_content_is_refused_before_execution(mutate):
    doc = definition(); mutate(doc)
    with pytest.raises(ValueError): ILSceneBackend(doc)


def test_text_amplification_is_bounded_before_action():
    doc = definition(); program = doc['programs']['take-key']
    program['resources']['message']['text'] = 'x' * 1000
    program['body'] = [{'id': str(i), 'op': 'text', 'resource': 'message'} for i in range(40)]
    with pytest.raises(ValueError, match='output budget'): ILSceneBackend(doc)
