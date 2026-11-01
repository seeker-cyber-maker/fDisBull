"""Authored source/capture fixtures; original games and native states are absent."""
from copy import deepcopy
from hashlib import sha256

import pytest

from examples.agi import build_bottom_scene as exporter
from fdisbull.il_scenes import ILSceneBackend
from tests.test_agi_clip_scene import fixture as clip_fixture
from fdisbull_player import Player


def fixture(tmp_path):
    source, old, proof, trace, load, artifacts = clip_fixture(tmp_path)
    # A synthetic priority-3 stripe in the inward row, with a dry outer row.
    pic = bytes((0xf2, 3, 0xf6, 5, 166, 91, 166, 0xff))
    volume = (source/'VOL.0').read_bytes()
    directory = bytearray((source/'PICDIR').read_bytes())
    directory[39*3:39*3+3] = len(volume).to_bytes(3, 'big')
    (source/'VOL.0').write_bytes(volume+b'\x12\x34\0'+len(pic).to_bytes(2, 'little')+pic)
    (source/'PICDIR').write_bytes(directory)
    observations = []
    for index, (name, room, x, y) in enumerate((
            ('bridge-entry', 39, 113, 45), ('east-bank', 39, 110, 166),
            ('row-start', 39, 110, 167), ('over-water', 39, 79, 167), ('west-exit', 40, 151, 167))):
        s = deepcopy(old['observations']['o0']['state']);s.update(room=room, ignore_blocks=True,
                initializing=False, edge=0, control_direction=7 if index == 3 else 0, window=0)
        s['ego'].update(x=x, y=y, direction=7 if index == 3 else 0)
        raw = ('authored frame '+name).encode();path = name+'.png';artifacts[path] = raw
        observations.append({'id': name, 'state': s, 'guest_ms': 100+100*index,
                             'input_count': (0, 0, 1, 2, 3)[index], 'message_count': 1 if index == 4 else 0,
                             'frame': {'path': path, 'sha256': sha256(raw).hexdigest(),
                                       'metadata': {'source': 'last_completed_guest_frame', 'width': 320,
                                                    'height': 200, 'mode_id': 5, 'frame_id': index+1}}})
    inputs = [{'kind': 'keyboard', 'key': 'press:'+key, 'complete': True, 'delivered': True,
               'delivery': {'accepted': True}} for key in ('down', 'left', 'left')]
    capture = {'format': 'fdisbull-agi-bridge-bottom-capture-1', 'source': old['source'], 'runtime': old['runtime'],
               'picture': {'room': 39, 'sha256': sha256(pic).hexdigest()}, 'bottom_observations': observations,
               'inputs': inputs, 'messages': deepcopy(old['actions'][-1]['messages'])}
    report = {'boundary_case_complete': True, 'boundary_result': {'complete': True,
              'result': 'bottom-row-west-exit', 'final': deepcopy(observations[-1])},
              'post_teardown_source_unchanged': True, 'post_teardown_copy_unchanged': True}
    return source, capture, report, lambda name: artifacts[name]


def test_observed_route_and_checkpoint(tmp_path):
    scene, evidence = exporter.build(*fixture(tmp_path))
    b = ILSceneBackend(scene);player = Player(b)
    assert 'no action sent' in player.execute('use crossing').lower()
    assert player.execute('use edge').startswith('Success:') and b.state['$y'] == 167
    token = b.observe()['context']['token']
    assert b.save('edge')['status'] == 'saved'
    assert player.execute('use crossing').startswith('Success:')
    assert (b.state['$room'], b.state['$x'], b.state['$y'], b.state['$score']) == (40, 151, 167, 0)
    assert b.load('edge')['status'] == 'restored'
    assert b.state['$phase'] == 1 and b.state['$room'] == 39
    assert b.act({'verb': 'use', 'target': 'crossing', 'item': None, 'context_token': token})['status'] == 'rejected'
    assert player.execute('use crossing').startswith('Success:')
    assert evidence['observations'][3]['state']['x'] == 79


@pytest.mark.parametrize('fault', ['source', 'picture', 'incomplete', 'missing-frame', 'missing-dialogue',
                                  'input', 'order', 'count', 'final', 'water', 'initializing', 'wrong-row'])
def test_material_missing_or_conflicting_evidence_refuses(tmp_path, fault):
    source, c, report, loader = fixture(tmp_path)
    if fault == 'source': c['source']['agi_sha256'] = '0'*64
    if fault == 'picture': c['picture']['sha256'] = '0'*64
    if fault == 'incomplete': report['boundary_case_complete'] = False
    if fault == 'missing-frame': c['bottom_observations'][2]['frame']['sha256'] = '0'*64
    if fault == 'missing-dialogue': c['messages'] = []
    if fault == 'input': c['inputs'][1]['complete'] = False
    if fault == 'order': c['bottom_observations'][2]['guest_ms'] = 1
    if fault == 'count': c['bottom_observations'][2]['input_count'] = 99
    if fault == 'final': report['boundary_result']['final']['state']['ego']['x'] = 152
    if fault == 'water': c['bottom_observations'][3]['state']['in_water'] = True
    if fault == 'initializing': c['bottom_observations'][4]['state']['initializing'] = True
    if fault == 'wrong-row': c['bottom_observations'][3]['state']['ego']['y'] = 166
    with pytest.raises(ValueError): exporter.build(source, c, report, loader)
