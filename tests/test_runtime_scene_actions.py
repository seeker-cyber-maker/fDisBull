"""Stored action authority is explicit, immutable and separate from passive RAM."""
from copy import deepcopy
import hashlib

import pytest

from fdisbull.project import Project
from fdisbull.scenes import encoded
from test_qemu_io_public import raw_project


def definition():
    context = dict(state='authored RAM control', triggers=['physical keyboard'])
    return dict(format='fdisbull-scene-3',
        observation_profile=dict(kind='runtime-memory', version=1),
        action_profile=dict(kind='qemu-virtual-keyboard', version=1),
        context=context,
        match={'runtime_memory': dict(binding='control', offset=0, length=1, hex='01')},
        objects=[dict(name='advance', context=context,
            visible={'constant': True}, ready={'constant': True},
            enabled={'constant': True}, outcome={'constant': False},
            action=dict(kind='press', key='a'))])


def passive(doc):
    doc = deepcopy(doc)
    doc['format'] = 'fdisbull-scene-2'
    doc.pop('action_profile', None)
    for obj in doc['objects']:
        for key in ('action', 'guest_ms', 'timeout_ms', 'outcome_phase'):
            obj.pop(key, None)
    return doc


def test_action_manifest_round_trips_with_pinned_identity_and_defaults(raw_project):
    project = raw_project
    original = definition()
    saved = project.debug_save_scene('controls', original)
    assert original == definition(), 'saving must not mutate caller declarations'
    doc, obj = saved['definition'], saved['definition']['objects'][0]
    assert doc['format'] == 'fdisbull-scene-3'
    assert doc['action_profile'] == {'kind': 'qemu-virtual-keyboard', 'version': 1}
    assert obj['action'] == dict(kind='press', key='a', modifiers=[], hold_ms=40, gap_ms=40)
    assert (obj['guest_ms'], obj['timeout_ms'], obj['outcome_phase']) == (5000, 5000, 'state')
    assert doc['source_identity'] == dict(source_sha256=project.meta['source_sha256'],
        version=project.version()['id'], version_sha256=project.version()['sha256'])
    assert saved['sha256'] == hashlib.sha256(encoded(doc)).hexdigest()
    with Project(project.path) as reopened:
        assert reopened.debug_scene_info(saved['id']) == saved
        assert reopened.debug_scene_info('controls') == saved


def test_action_revision_keeps_object_identity_and_prior_plan(raw_project):
    first = raw_project.debug_save_scene('controls', definition())
    changed = deepcopy(first['definition'])
    changed['objects'][0]['name'] = 'next'
    changed['objects'][0]['action']['key'] = 'b'
    second = raw_project.debug_save_scene('controls', changed, parent=first['id'])
    assert first['id'] != second['id'] and first['sha256'] != second['sha256']
    assert second['definition']['objects'][0]['id'] == first['definition']['objects'][0]['id']
    assert second['definition']['objects'][0]['aliases'] == ['advance']
    assert raw_project.debug_scene_info(first['id']) == first
    with pytest.raises(ValueError, match='parent'):
        raw_project.debug_save_scene('controls', changed, parent=first['id'])


@pytest.mark.parametrize('path,value', [
    (('action_profile',), {'kind': 'native-keyboard', 'version': 1}),
    (('action_profile',), {'kind': 'qemu-virtual-keyboard', 'version': True}),
    (('action_profile',), {'kind': 'qemu-virtual-keyboard', 'version': 1, 'implicit': True}),
    (('objects', 0, 'action'), {'kind': 'click', 'button': 'left'}),
    (('objects', 0, 'action'), {'kind': 'type', 'text': 'a'}),
    (('objects', 0, 'action'), {'kind': 'press', 'key': '$prior.key'}),
    (('objects', 0, 'action'), {'kind': 'press', 'key': 'a', 'modifiers': ['ctrl', 'ctrl']}),
    (('objects', 0, 'action'), {'kind': 'press', 'key': 'a', 'modifiers': ('ctrl',)}),
    (('objects', 0, 'action'), {'kind': 'press', 'key': 'a', 'hold_ms': True}),
    (('objects', 0, 'action'), {'kind': 'press', 'key': 'a', 'gap_ms': 0}),
    (('objects', 0, 'action'), {'kind': 'press', 'key': 'a', 'hold_ms': 1001}),
    (('objects', 0, 'action'), {'kind': 'press', 'key': 'a', 'repeat': 2}),
    (('objects', 0, 'guest_ms'), True),
    (('objects', 0, 'guest_ms'), 120001),
    (('objects', 0, 'timeout_ms'), 60001),
    (('objects', 0, 'outcome_phase'), 'committed'),
    (('objects', 0, 'point'), [1, 2]),
    (('handlers',), []),
    (('objects', 0, 'outcome'), {'any': [{'constant': True}, {'pixel': {'x': 0, 'y': 0, 'rgb': [0, 0, 0]}}]}),
])
def test_invalid_action_authority_refuses_before_any_scene_row(raw_project, path, value):
    doc = definition()
    target = doc
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        raw_project.debug_save_scene('invalid', doc)
    assert raw_project.db.execute('SELECT count(*) FROM debug_scene_revisions').fetchone()[0] == 0


@pytest.mark.parametrize('missing', ['action_profile', 'action'])
def test_action_profile_and_each_action_are_required(raw_project, missing):
    doc = definition()
    if missing == 'action':
        del doc['objects'][0]['action']
    else:
        del doc[missing]
    with pytest.raises(ValueError):
        raw_project.debug_save_scene('missing', doc)


@pytest.mark.parametrize('direction', ['passive_to_action', 'action_to_passive'])
def test_revision_chain_cannot_gain_or_lose_action_authority(raw_project, direction):
    start, finish = (passive(definition()), definition()) if direction == 'passive_to_action' else (definition(), passive(definition()))
    first = raw_project.debug_save_scene('controls', start)
    with pytest.raises(ValueError, match='profile'):
        raw_project.debug_save_scene('controls', finish, parent=first['id'])
    assert raw_project.debug_scene_info('controls') == first


def test_passive_profile_still_refuses_action_fields(raw_project):
    doc = passive(definition())
    doc['objects'][0]['action'] = dict(kind='press', key='a')
    with pytest.raises(ValueError, match='passive|Passive'):
        raw_project.debug_save_scene('passive', doc)


def test_stored_noncanonical_action_is_rejected_even_with_matching_hash(raw_project):
    saved = raw_project.debug_save_scene('controls', definition())
    altered = deepcopy(saved['definition'])
    del altered['objects'][0]['action']['hold_ms']
    data = encoded(altered)
    with raw_project.transaction(True):
        raw_project.db.execute('UPDATE debug_scene_revisions SET document=?,sha256=? WHERE id=?',
            (data.decode(), hashlib.sha256(data).hexdigest(), saved['id']))
    with pytest.raises(ValueError, match='canonical'):
        raw_project.debug_scene_info(saved['id'])


def test_action_selection_requires_the_explicit_profile_and_an_object(raw_project):
    from fdisbull.runtime_scene_actions import select
    saved = raw_project.debug_save_scene('controls', definition())
    selected, obj = select(raw_project, 'controls', raw_project.version()['id'], 'advance')
    assert selected == saved and obj == saved['definition']['objects'][0]
    raw_project.debug_save_scene('passive', passive(definition()))
    with pytest.raises(ValueError, match='scene-3'):
        select(raw_project, 'passive', raw_project.version()['id'], 'advance')
    with pytest.raises(ValueError, match='object'):
        select(raw_project, 'controls', raw_project.version()['id'], None)
