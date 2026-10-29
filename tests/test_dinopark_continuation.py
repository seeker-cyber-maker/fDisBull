"""Continuation contracts; native correspondence is checked against the game."""
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge


def native_save(title):
    data = bytearray(4153)
    data[:6] = b'DINOSG'
    data[6:6 + len(title)] = title
    return bytes(data)


def test_native_title_survives_filename_renumbering_without_collision(tmp_path):
    # The original loader copies a previous slot to 000; its title stays 001.
    (tmp_path / 'DINOSG.000').write_bytes(native_save(b'agent001'))
    (tmp_path / 'DINOSG.002').write_bytes(native_save(b'AGENT002'))
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    label = scenes.native_save_label(tmp_path, 1)
    assert label == 'agent003'
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


@pytest.mark.parametrize('omit', [(), ('operating',), ('street', 'operating')])
def test_original_native_bundles_remain_loadable_with_new_recognition(tmp_path, omit):
    data = native_save(b'previous')
    (tmp_path / 'DINOSG.000').write_bytes(data)
    payload = {'resources': {}, 'patterns': {k: v for k, v in scenes.pattern_hashes().items() if k not in omit},
               'qualifications': dict.fromkeys(scenes.QUALIFICATIONS, True),
               'native_sha256': scenes.digest(tmp_path / 'DINOSG.000'),
               'saved_fields': scenes.native_fields(data)}
    envelope = {'format': 'dinopark-native-save-1', 'payload': payload,
                'sha256': scenes.document_hash(payload)}
    (tmp_path / 'save.json').write_text(json.dumps(envelope))
    assert scenes.read_save_bundle(tmp_path, {})[0] == payload
    payload['patterns']['main'] = 'wrong-original-profile'
    envelope['sha256'] = scenes.document_hash(payload)
    (tmp_path / 'save.json').write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match='qualification is incompatible'):
        scenes.read_save_bundle(tmp_path, {})


@pytest.mark.parametrize('notice,context,run_outcome,expected', [
    (['quarter_popup'], 'park.quarter-notice', 'guest_time', 'accepted'),
    (['parking_hint'], 'park.quarter-notice', 'guest_time', 'incomplete'),
    (['quarter_popup', 'parking_hint'], 'park.quarter-notice', 'guest_time', 'incomplete'),
    (['quarter_popup'], 'park', 'guest_time', 'incomplete'),
    (['quarter_popup'], 'park.quarter-notice', 'breakpoint', 'incomplete'),
])
def test_verified_quarter_pause_is_continuable_without_claiming_full_completion(
        tmp_path, notice, context, run_outcome, expected):
    writer = io.StringIO()
    service = bridge.ZService(tmp_path, io.StringIO(), writer)
    service.text = SimpleNamespace(current='park')
    service.observe = lambda: {'complete': True, 'context': {'id': context}}
    service.pending = {'command': 'advance time', 'messages': ['A recognized notice interrupted the advance.'],
                       'events': [{'phase': 'interrupted', 'command': 'advance time',
                                   'notices': notice, 'run': {'outcome': run_outcome}}]}
    service.finish()
    result = json.loads(writer.getvalue())
    assert result['status'] == expected
    assert result['complete'] is (expected == 'accepted')
    assert result['effects'] == ('partial' if expected == 'accepted' else 'unknown')


def test_z_native_backups_are_new_revisions_and_named_loads_are_visible(tmp_path):
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    library = tmp_path / 'saves'
    service.text = SimpleNamespace(current='office', save_library=library)
    _, bindings = service.objects()
    assert bindings['save', 'route-park'] == 'save park zpark'
    (library / 'zpark').mkdir(parents=True)
    (library / 'zpark/save.json').write_text('{}')  # Index only; loader still validates bytes.
    service.event({'phase': 'result', 'command': 'save park zpark'})
    objects, bindings = service.objects()
    assert bindings['save', 'route-park'] == 'save park zpark-002'
    assert bindings['load', 'route-park'] == 'load park zpark'
    assert bindings['load', 'save-zpark'] == 'load park zpark'
    assert next(o for o in objects if o['id'] == 'save-zpark')['aliases'] == ['zpark']
    assert (library / 'zpark/save.json').read_text() == '{}'


def test_revision_names_fit_native_contract_and_capacity_keeps_navigation(tmp_path):
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO(), slot='x' * 32)
    library = tmp_path / 'saves'
    service.text = SimpleNamespace(current='office', save_library=library)
    (library / service.slot).mkdir(parents=True)
    assert len(service.next_native_save_name()) == 32
    for i in range(64):
        p = library / f'park{i}'
        p.mkdir()
        (p / 'save.json').write_text('{}')
    _, bindings = service.objects()
    assert ('save', 'route-park') not in bindings
    assert bindings['go', 'route-park'] == 'go park'


def test_park_entry_quarter_pause_requires_its_own_verified_context(tmp_path):
    writer = io.StringIO()
    service = bridge.ZService(tmp_path, io.StringIO(), writer)
    service.text = SimpleNamespace(current='street')
    service.observe = lambda: {'complete': True, 'context': {'id': 'park-entry.quarter-notice'}}
    service.pending = {'command': 'go park', 'messages': ['Quarter notice interrupted entry.'],
                       'events': [{'phase': 'interrupted', 'command': 'go park',
                                   'notices': ['quarter_popup'], 'run': {'outcome': 'guest_time'}}]}
    service.finish()
    result = json.loads(writer.getvalue())
    assert result['status'] == 'accepted' and result['effects'] == 'partial'


@pytest.mark.parametrize('species,price', [(19, 25000), (4, 1500)])
def test_unqualified_species_or_price_never_sends_the_purchase_press(tmp_path, monkeypatch, species, price):
    def memory(address, length):
        values = {'4020:5c3a': 4500, '4020:bfbb': 5000, '4020:bad4': 4500,
                  '4020:68a5': species, '4020:45b8': price}
        return {'hex': values[address].to_bytes(length, 'little').hex()}
    text = scenes.TextScene(SimpleNamespace(memory=memory, scene_assert=lambda *a, **k: None),
                            None, None, event=lambda e: None)
    text.current, text.land_bought, text.mart = 'dinomart', True, 'first-page'
    actions = []
    text.shop_click = lambda p, ms, name: actions.append(name)
    text.shop_observe = lambda *a: None
    monkeypatch.setattr(scenes, 'prepare_mart_first_page', lambda t: None)
    with pytest.raises(RuntimeError, match='BUY withheld'):
        text.buy_dinosaur()
    assert actions == ['select dinosaur', 'select price']


def test_native_save_response_teaches_the_public_z_load_command(tmp_path):
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    native = ('Park saved as zpark-002. Resume folder: /Users/operator/private/saves/zpark-002\n'
              'Use load park zpark-002, or --load-save with that folder in a later session.')
    public = service.public_message(native)
    assert public == ('Park saved as zpark-002.\n'
                      'Use load zpark-002 to restore this backup, or load park for the latest backup.')


def test_commit_hook_journals_proof_without_nested_native_witness_queries(tmp_path):
    writer = io.StringIO()
    service = bridge.ZService(tmp_path, io.StringIO(), writer)
    service.pending = {'command': 'buy vegasaurus', 'messages': ['Order confirmed.'], 'events': []}
    witnessed = []
    service.oracle = witnessed.append
    service.event({'phase': 'vegasaurus_purchase_confirmed', 'proof': {'reservation_released': 25000}})
    assert witnessed == []
    receipt = json.loads((tmp_path / 'z-session.json').read_text())
    assert receipt['pending_effects'] == 'applied-confirmed' and receipt['complete'] is False
    service.finish()
    assert witnessed == ['command-complete']
    assert json.loads(writer.getvalue())['effects'] == 'applied-confirmed'
