"""Continuation contracts; native correspondence is checked against the game."""
import io
import json
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_scenes as scenes, dinopark_z as bridge


@pytest.mark.parametrize('mismatch', [False, True])
def test_checkpoint_reply_has_durable_native_witness_and_requires_requalification(tmp_path, monkeypatch, mismatch):
    """Orchestration at the native-debug boundary; original-game proof is separate."""
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    advances = []
    class NativeBoundary:
        loaded = False
        framed = True
        def save_state(self, name): return {'artifact':'owned-native-state'}
        def load_state(self, artifact):
            self.loaded, self.framed = True, False
    native = NativeBoundary()
    values = {name: '00' * length for name, _, _, length in scenes.SAVE_RANGES}
    def fields(debug):
        return {**values, 'cash':'01000000'} if mismatch and debug.loaded else dict(values)
    monkeypatch.setattr(scenes, 'live_saved_fields', fields)
    def advance(debug, ms):
        advances.append(ms); debug.framed = True
    monkeypatch.setattr(scenes, 'run_guest', advance)
    service.text = SimpleNamespace(**dict.fromkeys(bridge.SNAPSHOT_FIELDS))
    service.text.debug = native
    service.observe = lambda **kw: {'complete':native.framed, 'context':{'id':'office'}}
    assert service.checkpoint({'op':'save','slot':'before'})['status'] == 'saved'
    saved = json.loads((tmp_path/'z-session.json').read_text())
    assert saved['status'] == 'checkpoint-saved' and saved['complete'] is False
    result = service.checkpoint({'op':'load','checkpoint':'before'})
    receipt = json.loads((tmp_path/'z-session.json').read_text())
    if mismatch:
        assert result['complete'] is False and service.checkpoint_failed is True
        assert advances == [] and receipt['status'] == 'checkpoint-incomplete'
    else:
        assert result['status'] == 'restored' and result['replay_safe'] is True
        assert advances == [100] and service.checkpoint_failed is False
        witness = next(e for e in receipt['history'] if e['phase']=='checkpoint_restored')
        assert witness['field_count'] == 20 and witness['saved_fields'] == witness['restored_fields'] == values
        assert witness['context'] == 'office' and receipt['complete'] is False


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


@pytest.mark.parametrize('omit', [(), ('catalogue',), ('operating', 'catalogue'),
                                  ('street', 'operating', 'catalogue')])
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
    (['parking_hint'], 'park.parking-notice', 'guest_time', 'accepted'),
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


@pytest.mark.parametrize('notice,context', [('quarter_popup', 'park-entry.quarter-notice'),
                                        ('parking_hint', 'park-entry.parking-notice')])
def test_park_entry_notice_pause_requires_its_own_verified_context(tmp_path, notice, context):
    writer = io.StringIO()
    service = bridge.ZService(tmp_path, io.StringIO(), writer)
    service.text = SimpleNamespace(current='street')
    service.observe = lambda: {'complete': True, 'context': {'id': context}}
    service.pending = {'command': 'go park', 'messages': ['Quarter notice interrupted entry.'],
                       'events': [{'phase': 'interrupted', 'command': 'go park',
                                   'notices': [notice], 'run': {'outcome': 'guest_time'}}]}
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


@pytest.mark.parametrize('notice', ['quarter_popup', 'parking_hint'])
def test_entry_notice_can_return_to_street_without_replaying_entry(monkeypatch, notice):
    from types import SimpleNamespace
    from fdisbull import dinopark_scenes as scenes
    text = scenes.TextScene.__new__(scenes.TextScene)
    text.current, text.street = 'street', 'verified-street'
    text.park_opened, text.pending_park_entry = True, True
    text.notice_outcome_unknown = False
    text.patterns = {name: name for name in ('quarter_popup', 'parking_hint', 'park_view', 'shop_street')}
    events, inputs, assertions = [], [], []
    text.event, text.format_status = events.append, lambda value: 'status'
    text.project = object()
    text.debug = SimpleNamespace(
        keyboard_press=lambda key: (inputs.append(key) or {'accepted': True, 'delivery': 'queued'}),
        scene_assert=lambda scene, **kw: assertions.append((scene, kw)))
    frames = iter([notice, notice, 'shop_street'])
    monkeypatch.setattr(scenes, 'take_frame', lambda *args: ({'artifact': 'retained'}, next(frames)))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(scenes, 'run_guest', lambda *args: None)
    monkeypatch.setattr(scenes, 'park_snapshot', lambda debug: {})
    monkeypatch.setattr(scenes, 'parking_notice_input',
                        lambda text: (inputs.append('parking-thumb') or {'accepted': True, 'delivery': 'queued'}))
    result = text.acknowledge_notice()
    assert inputs == (['parking-thumb'] if notice == 'parking_hint' else ['enter'])
    assert text.current == 'street' and not text.pending_park_entry and not text.notice_outcome_unknown
    assert assertions == [('verified-street', {'object': 'street.office'})]
    assert events[-1]['park_entry_outcome'] == 'not_completed'
    assert 'Use go park' in result


@pytest.mark.parametrize('submitted,trigger,context,expected', [
    (False, 'guest_time', 'dino_diner.parking-notice', 'accepted'),
    (True, 'guest_time', 'dino_diner.parking-notice', 'incomplete'),
    (False, 'breakpoint', 'dino_diner.parking-notice', 'incomplete'),
    (False, 'guest_time', 'dino_diner', 'incomplete'),
])
def test_food_pause_requires_unsubmitted_order_and_verified_modal(tmp_path, submitted, trigger, context, expected):
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    service.observe = lambda: {'complete': True, 'context': {'id': context}}
    service.pending = {'command': 'buy 20 small feeders', 'messages': ['Parking advice interrupted the menu.'],
                       'events': [{'phase': 'interrupted', 'command': 'buy 20 small feeders',
                                   'notices': ['parking_hint'], 'food_order_submitted': submitted,
                                   'run': {'outcome': trigger}}]}
    service.finish()
    reply = json.loads(service.writer.getvalue())
    assert reply['status'] == expected
    assert reply['effects'] == ('partial' if expected == 'accepted' else 'unknown')


@pytest.mark.parametrize('visible,known', [({'parking_hint'}, True),
    ({'parking_hint', 'food_menu'}, False), ({'parking_hint', 'quarter_popup'}, False)])
def test_menu_interruption_is_unique_and_does_not_wait_or_send_input(monkeypatch, visible, known):
    from types import SimpleNamespace
    from fdisbull import dinopark_scenes as scenes
    text = scenes.TextScene.__new__(scenes.TextScene)
    text.project, text.debug = object(), SimpleNamespace()
    text.patterns = {n: n for n in ('food_menu', 'parking_hint', 'quarter_popup')}
    text.event = lambda event: None
    monkeypatch.setattr(scenes, 'take_frame', lambda *a: ({'artifact': 'actual-frame'}, visible))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: pattern in image)
    monkeypatch.setattr(scenes, 'balances', lambda debug: {'loan': 5000})
    error = scenes.KnownSceneNotice if known else RuntimeError
    with pytest.raises(error) as caught:
        text.shop_observe('food_menu', {'loan': 5000}, 'menu', interrupts=('parking_hint',))
    if known:
        assert caught.value.notice == 'parking_hint'
        assert caught.value.frame == {'artifact': 'actual-frame'}
    else:
        assert not isinstance(caught.value, scenes.KnownSceneNotice)


@pytest.mark.parametrize('after,qualified', [('food_menu', True), ('food_selected', False)])
def test_parking_acknowledgment_never_submits_or_replays_food_order(monkeypatch, after, qualified):
    from types import SimpleNamespace
    from fdisbull import dinopark_scenes as scenes
    text = scenes.TextScene.__new__(scenes.TextScene)
    text.current, text.pending_food_notice, text.notice_outcome_unknown = 'dino_diner', True, False
    text.locations, text.project = {'dino_diner': 'diner-revision'}, object()
    text.patterns = {n: n for n in ('parking_hint', 'quarter_popup', 'dino_diner',
                                  'food_menu', 'food_selected', 'shop_street')}
    inputs, assertions, events = [], [], []
    text.event = events.append
    text.debug = SimpleNamespace(
        keyboard_press=lambda key: (inputs.append(key) or {'accepted': True, 'delivery': 'queued'}),
        scene_assert=lambda scene, **kw: assertions.append((scene, kw)))
    from itertools import chain, repeat
    frames = chain(['parking_hint', 'parking_hint'], repeat(after))
    monkeypatch.setattr(scenes, 'take_frame', lambda *a: ({'artifact': 'retained'}, next(frames)))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(scenes, 'run_guest', lambda *a: None)
    monkeypatch.setattr(scenes, 'parking_notice_input',
                        lambda text: (inputs.append('parking-thumb') or {'accepted': True, 'delivery': 'queued'}))
    result = text.acknowledge_notice()
    assert inputs == ['parking-thumb']
    assert text.pending_food_notice is (not qualified)
    assert text.notice_outcome_unknown is (not qualified)
    if qualified:
        assert assertions == [('diner-revision', {'object': 'dino_diner.back'})]
        assert events[-1]['food_order_submitted'] is False
        assert 'submit a new order' in result
    else:
        assert assertions == [] and 'outcome unknown' in result


@pytest.mark.parametrize('ambiguous', [False, True])
def test_pending_parking_advice_exposes_only_its_verified_action(tmp_path, monkeypatch, ambiguous):
    from types import SimpleNamespace
    from fdisbull import dinopark_scenes as scenes
    service = bridge.ZService(tmp_path, io.StringIO(), io.StringIO())
    service.text = SimpleNamespace(current='dino_diner', pending_food_notice=True,
        notice_outcome_unknown=False, project=object(), patterns={'parking_hint': 'parking', 'quarter_popup': 'quarter'},
        describe=lambda: 'The background diner still matches.',
        debug=SimpleNamespace(registers=lambda: {'state_revision': 42}))
    service.objects = lambda: ([{'id': 'notice'}, {'id': 'food'}, {'id': 'route-street'}], {})
    visible = {'parking', 'quarter'} if ambiguous else {'parking'}
    monkeypatch.setattr(scenes, 'take_frame', lambda *a: ({}, visible))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: pattern in image)
    observed = service.observe()
    assert observed['complete'] is (not ambiguous)
    if not ambiguous:
        assert observed['context']['id'] == 'dino_diner.parking-notice'
        assert observed['objects'] == [{'id': 'notice'}]


def test_original_roaming_dinosaur_probe_does_not_hide_the_park():
    from copy import deepcopy
    from fdisbull import dinopark_scenes as scenes
    from fixtures_dinopark_scene_probes import PARK_COEL_OVERLAP
    pattern = json.loads(scenes.OPERATING_PATTERNS.read_text())['scenes']['park_view']
    unchanged = deepcopy(pattern)
    colors = {(s['x'], s['y']): s['rgb'] for s in PARK_COEL_OVERLAP['samples']}
    class Probe:
        # Missing observations raise; they are never invented as black pixels.
        def getpixel(self, point): return colors[point]
    assert not scenes.matches(Probe(), pattern)
    assert scenes.matches(Probe(), scenes.park_static_pattern(pattern))
    assert pattern == unchanged


@pytest.mark.parametrize('cash,working,live,pending,count', [
    (27535, 27260, 8, 19, 11), (27535, 27235, 8, 20, 12),
    (27535, 27260, 8, 20, None), (27535, 27259, 8, 19, None)])
def test_food_draft_resolves_applied_effect_without_guessing(monkeypatch, cash, working, live, pending, count):
    from fdisbull import dinopark_scenes as scenes
    monkeypatch.setattr(scenes, 'balances', lambda debug: {'cash': cash, 'working_cash': working, 'loan': 4290})
    monkeypatch.setattr(scenes, 'park_resources', lambda debug: {'guides': 1, 'small_feeders': live})
    monkeypatch.setattr(scenes, 'pending_small_feeders', lambda debug: pending)
    if count is None:
        with pytest.raises(RuntimeError, match='counters disagree'):
            scenes.food_draft_state(object())
    else:
        actual, evidence = scenes.food_draft_state(object())
        assert actual == count and evidence['pending_small_feeders'] == pending


def test_notice_return_waits_for_the_scene_without_sending_another_input(monkeypatch):
    from types import SimpleNamespace
    from fdisbull import dinopark_scenes as scenes
    text = SimpleNamespace(project=object(), debug=object(), event=lambda event: None,
                           patterns={n: n for n in ('park_view', 'shop_street', 'parking_hint', 'quarter_popup')})
    images = iter(['unqualified-transition'] * 4 + ['park_view'])
    elapsed = []
    monkeypatch.setattr(scenes, 'take_frame', lambda *a: ({'artifact': 'original-frame'}, next(images)))
    monkeypatch.setattr(scenes, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(scenes, 'run_guest', lambda debug, ms: elapsed.append(ms))
    frame, image = scenes.notice_return_frame(text, 'return', ('park_view', 'shop_street'))
    assert image == 'park_view' and elapsed == [500, 500, 500, 500]
