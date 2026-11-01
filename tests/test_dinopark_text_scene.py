import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('dinopark_text', Path(__file__).parents[1] / 'examples/dinopark_text/scene.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_menu_travel_plans_bounded_original_transitions():
    assert module.navigation_route('park', 'go diner', park_opened=True) == [
        ('go street', 'street'), ('go diner', 'dino_diner')]
    assert module.navigation_route('dino_diner', 'go bank', park_opened=True) == [
        ('go street', 'street'), ('go office', 'office'), ('go bank', 'bank')]
    assert module.navigation_route('office', 'go park', park_opened=False) is None
    assert module.navigation_route('park', 'go park', park_opened=True) == []
    assert module.navigation_route('office', 'buy coelophysis', park_opened=True) is None


@pytest.mark.parametrize('name', ['../park', 'My Park', '', 'a' * 33, '/park'])
def test_save_names_cannot_escape_library(name):
    with pytest.raises(ValueError, match='Save names'):
        module.save_name(name)


def test_native_save_validation_detects_corruption_and_resource_drift(tmp_path):
    import json
    native = tmp_path / 'DINOSG.000'
    native.write_bytes(b'DINOSG' + b'\0' * 4147)
    source = {'DINOPARK.EXE': module.EXPECTED_EXE, 'VARS.DAT': module.EXPECTED_VARS}
    payload = {'resources': source, 'patterns': {'main': module.digest(module.PATTERNS),
               'shop': module.digest(module.SHOP_PATTERNS), 'save': module.digest(module.SAVE_PATTERNS)},
               'native_sha256': module.digest(native), 'saved_fields': module.native_fields(native.read_bytes()),
               'qualifications': dict.fromkeys(module.QUALIFICATIONS, True)}
    manifest = tmp_path / 'save.json'
    manifest.write_text(json.dumps({'format': 'dinopark-native-save-1', 'payload': payload,
                                   'sha256': module.document_hash(payload)}))
    assert module.read_save_bundle(tmp_path, source) == (payload, native)
    # Legacy bundles keep their original bytes/three identities. New bundles
    # additionally pin the street guard, and an explicit wrong pin is refused.
    legacy_bytes = manifest.read_bytes()
    module.read_save_bundle(tmp_path, source)
    assert manifest.read_bytes() == legacy_bytes
    payload['patterns'] = module.pattern_hashes()
    def write_manifest():
        manifest.write_text(json.dumps({'format': 'dinopark-native-save-1', 'payload': payload,
                                       'sha256': module.document_hash(payload)}))
    write_manifest()
    assert module.read_save_bundle(tmp_path, source) == (payload, native)
    payload['patterns']['street'] = 'incompatible-street-profile'
    write_manifest()
    with pytest.raises(ValueError, match='scene qualification'):
        module.read_save_bundle(tmp_path, source)
    payload['patterns'] = module.pattern_hashes()
    write_manifest()
    with pytest.raises(ValueError, match='resources'):
        module.read_save_bundle(tmp_path, {**source, 'VARS.DAT': 'changed'})
    native.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='Native game save'):
        module.read_save_bundle(tmp_path, source)
    payload['qualifications']['fence_bought'] = False
    manifest.write_text(json.dumps({'format': 'dinopark-native-save-1', 'payload': payload,
                                   'sha256': module.document_hash(payload)}))
    with pytest.raises(ValueError, match='qualified running-park'):
        module.read_save_bundle(tmp_path, source)


def test_native_save_offsets_check_independent_cash_loan_food_and_guide():
    import struct
    data = bytearray(b'DINOSG' + b'\0' * 4147)
    struct.pack_into('<i', data, 3434, 1938)
    struct.pack_into('<i', data, 3906, 5000)
    struct.pack_into('<h', data, 3854, 19)
    struct.pack_into('<h', data, 3886, 1)
    fields = module.native_fields(data)
    assert fields['cash'] == '92070000'
    assert fields['loan'] == '88130000'
    assert fields['food'].startswith('1300')
    assert fields['staff'][12:16] == '0100'
    with pytest.raises(ValueError, match='save format'):
        module.native_fields(data[:-1])


def test_failed_original_load_never_restores_route_qualifications(monkeypatch):
    events = []
    scene = module.TextScene(Debug(), 'office', None, event=events.append)
    monkeypatch.setattr(module, 'live_saved_fields', lambda _: {'cash': 'different'})
    with pytest.raises(RuntimeError, match='resume withheld'):
        scene.restore_qualifications({'saved_fields': {'cash': 'saved'}})
    assert not any(getattr(scene, key) for key in module.QUALIFICATIONS)
    assert events[-1]['matched'] is False


def test_save_refuses_duplicate_or_unqualified_names_before_input(tmp_path):
    debug = Debug()
    scene = module.TextScene(debug, 'office', None)
    scene.save_library = tmp_path
    assert 'setup' in scene.save_preflight('park')
    for key in module.QUALIFICATIONS:
        setattr(scene, key, True)
    (tmp_path / 'park').mkdir()
    assert 'already exists' in scene.save_preflight('park')
    assert 'No input was sent' in scene.save_preflight('../park')
    assert scene.save_preflight('newpark') is None
    assert debug.calls == []


def street_profile():
    import json
    return json.loads(module.STREET_PATTERNS.read_text())['scenes']['street']


def test_street_profile_uses_strict_static_building_samples():
    from PIL import Image, ImageDraw
    profile = street_profile()
    assert profile['min_matches'] == len(profile['samples']) >= 32
    assert profile['tolerance'] == 0
    image = Image.new('RGB', (320, 200))
    for sample in profile['samples']:
        assert sample['y'] < 100
        assert not (100 <= sample['x'] <= 219 and sample['y'] < 40)
        assert not (sample['x'] < 97 and 53 <= sample['y'] <= 95)
        assert not (124 <= sample['x'] <= 213 and 60 <= sample['y'] <= 93)
        image.putpixel((sample['x'], sample['y']), tuple(sample['rgb']))
    assert module.matches(image, profile)
    draw = ImageDraw.Draw(image)
    # Foreground walkers can reach the lower storefronts, above the road.
    draw.rectangle((0, 100, 319, 199), fill=(123, 34, 56))
    draw.rectangle((100, 0, 219, 38), fill=(12, 98, 32))
    draw.rectangle((0, 53, 96, 95), fill=(111, 222, 33))
    assert module.matches(image, profile)
    first = profile['samples'][0]
    image.putpixel((first['x'], first['y']), (1, 2, 3))
    assert not module.matches(image, profile)


def test_street_recognition_excludes_recognized_overlays_in_both_paths():
    from PIL import Image
    profile = street_profile()
    notice = {'samples': [{'x': 160, 'y': 100, 'rgb': [123, 45, 67]}],
              'min_matches': 1, 'tolerance': 0}
    profile['reject'] = [notice]
    image = Image.new('RGB', (320, 200))
    for sample in profile['samples']:
        image.putpixel((sample['x'], sample['y']), tuple(sample['rgb']))
    assert module.matches(image, profile)
    image.putpixel((160, 100), (123, 45, 67))
    assert not module.matches(image, profile)
    predicate = module.pixel_predicate(profile)
    assert predicate['all'][0]['pixels']['min_matches'] == len(profile['samples'])
    assert predicate['all'][1]['not']['pixels']['samples'] == notice['samples']


def test_street_profile_rejects_blank_and_wrong_view_pixels():
    from PIL import Image
    profile = street_profile()
    assert not module.matches(Image.new('RGB', (320, 200)), profile)
    assert not module.matches(Image.new('RGB', (320, 200), (239, 239, 239)), profile)


class Debug:
    def __init__(self):
        self.calls = []
        self.fail = False

    def scene_assert(self, scene, *, object=None):
        self.calls.append(('assert', scene, object))
        return {'status': 'matched'}

    def scene_click(self, scene, obj):
        self.calls.append(('click', scene, obj))
        if self.fail:
            raise RuntimeError('uncertain guest result')
        return {'status': 'matched', 'observation': 'evidence'}

    def memory(self, address, length):
        return {'hex': (5000).to_bytes(length, 'little').hex()}


def test_look_and_scene_actions_use_live_checks():
    debug = Debug()
    scene = module.TextScene(debug, 'office-revision', 'bank-revision')
    assert 'office' in scene.act('look')
    assert debug.calls == [('assert', 'office-revision', 'office.bank')]
    assert 'bank' in scene.act('go bank')
    assert debug.calls[-2:] == [('click', 'office-revision', 'office.bank'), ('assert', 'bank-revision', 'bank.back')]
    assert scene.current == 'bank'
    assert 'office' in scene.act('go office')
    assert debug.calls[-2:] == [('click', 'bank-revision', 'bank.back'), ('assert', 'office-revision', 'office.bank')]


def test_unknown_action_and_failed_input_do_not_fabricate_transition():
    debug = Debug()
    scene = module.TextScene(debug, 'office-revision', 'bank-revision')
    assert 'not available' in scene.act('go office')
    assert debug.calls == []
    debug.fail = True
    with pytest.raises(RuntimeError, match='uncertain'):
        scene.act('go bank')
    assert scene.current == 'office'


def test_financial_action_is_refused_outside_bank_or_unqualified_balance():
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office-revision', 'bank-revision', event=events.append)
    assert 'not available' in scene.act('repay')
    scene.current = 'bank'
    assert 'No additional credit' in scene.act('borrow')
    assert not any(call[0] == 'click' for call in debug.calls)
    assert events[0]['phase'] == 'refused' and events[0]['input'] == 'not_sent'


def test_unexpected_modal_balance_withholds_acknowledgment(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', project=object(),
                             patterns={'paid_popup': {}}, event=events.append)
    scene.current = 'bank'
    values = iter([{'cash': 5000, 'loan': 5000, 'working_cash': 5000},
                   {'cash': 4900, 'loan': 5000, 'working_cash': 5000}])
    monkeypatch.setattr(module, 'balances', lambda _: next(values))
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'frame'}, object()))
    monkeypatch.setattr(module, 'matches', lambda *args: True)
    monkeypatch.setattr(module, 'run_guest', lambda d, ms: d.calls.append(('run', ms)))
    with pytest.raises(RuntimeError, match='acknowledgment withheld'):
        scene.transact('repay')
    assert [e['phase'] for e in events] == ['intent', 'modal']
    assert events[-1]['observed']['cash'] == 4900


def test_startup_waits_for_office_without_replaying_input(monkeypatch):
    debug = Debug()
    frames = iter([({'artifact': 'blank'}, 'blank'), ({'artifact': 'office'}, 'office')])
    monkeypatch.setattr(module, 'take_frame', lambda *args: next(frames))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(module, 'run_guest', lambda d, ms: d.calls.append(('run', ms)))
    result = module.wait_for_office(None, debug, {'office': 'office', 'bank': 'bank'})
    assert result['artifact'] == 'office'
    assert debug.calls == [('run', 500)]


def test_transaction_waits_for_readiness_after_acknowledgment(monkeypatch):
    class BankDebug(Debug):
        def keyboard_press(self, key):
            self.calls.append(('press', key))
            return {'accepted': True, 'delivery': 'queued'}
        def scene_wait(self, scene, **kwargs):
            self.calls.append(('wait', scene, kwargs['object']))
    debug = BankDebug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', project=object(),
                             patterns={'paid_popup': {}, 'bank': {}}, event=events.append)
    scene.current = 'bank'
    values = iter([{'cash': 5000, 'loan': 5000, 'working_cash': 5000},
                   {'cash': 5000, 'loan': 5000, 'working_cash': 5000},
                   {'cash': 0, 'loan': 0, 'working_cash': 5000}])
    monkeypatch.setattr(module, 'balances', lambda _: next(values))
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'frame'}, object()))
    monkeypatch.setattr(module, 'matches', lambda *args: True)
    monkeypatch.setattr(module, 'run_guest', lambda d, ms: d.calls.append(('run', ms)))
    assert 'Repayment completed' in scene.transact('repay')
    assert ('wait', 'bank', 'bank.back') in debug.calls
    assert [e['phase'] for e in events] == ['intent', 'modal', 'result']


def test_dinosaur_purchase_without_qualified_land_sends_no_input():
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', event=events.append)
    scene.current = 'dinomart'
    scene.mart = 'mart'
    assert 'No input was sent' in scene.act('buy coelophysis')
    assert not any(call[0] == 'click' for call in debug.calls)
    assert events[-1]['phase'] == 'refused'


def test_dinomart_closed_before_first_land_purchase():
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', event=events.append)
    scene.current = 'street'
    assert 'closed' in scene.act('go dinomart')
    assert debug.calls == []
    assert events[-1]['input'] == 'not_sent'


def test_fence_purchase_requires_qualified_occupied_pen():
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', event=events.append)
    scene.current = 'general_store'
    assert 'No input was sent' in scene.act('buy wood fence')
    assert not any(call[0] == 'click' for call in debug.calls)
    assert events[-1]['phase'] == 'refused'


def test_employment_and_diner_closed_before_land():
    for command in ('go employment', 'go diner', 'go store'):
        debug = Debug()
        events = []
        scene = module.TextScene(debug, 'office', 'bank', event=events.append)
        scene.current = 'street'
        assert 'closed' in scene.act(command)
        assert debug.calls == []
        assert events[-1]['input'] == 'not_sent'


def test_vegasaurus_insufficient_cash_withholds_all_input(monkeypatch):
    debug = Debug(); events = []
    scene = module.TextScene(debug, 'office', None, event=events.append)
    scene.current = 'dinomart'
    monkeypatch.setattr(module, 'balances', lambda _: {'cash': 24999, 'loan': 0, 'working_cash': 24999})
    assert 'No input was sent' in scene.act('buy vegasaurus')
    assert debug.calls == [] and events[-1]['phase'] == 'refused'


@pytest.mark.parametrize('defect', [None, 'refund', 'expense', 'ownership', 'calendar', 'selection'])
def test_vegasaurus_proof_requires_refund_expense_and_unchanged_ownership(defect):
    from copy import deepcopy
    initial = {'balances': {'cash': 27175, 'loan': 4290, 'working_cash': 27175},
               'calendar': [0, 6, 0, 6], 'expenses': [1250] + [0] * 11,
               'pens': 'occupied-coelophysis', 'species': 'one-coelophysis', 'selection': 19, 'dinosaurs': 1}
    staged = deepcopy(initial)
    staged['balances']['working_cash'] = 2175
    staged['expenses'][6] = 25000
    refunded = deepcopy(staged)
    refunded['balances']['working_cash'] = 27175
    states = [initial, staged, deepcopy(staged), refunded]
    if defect == 'refund': states[-1]['balances']['working_cash'] = 27174
    if defect == 'expense': states[-1]['expenses'][6] = 0
    if defect == 'ownership': states[-1]['species'] = 'new-animal'
    if defect == 'calendar': states[1]['calendar'][2] += 1
    if defect == 'selection': states[0]['selection'] = 18
    if defect:
        with pytest.raises(RuntimeError): module.verify_vegasaurus_order(states)
    else:
        proof = module.verify_vegasaurus_order(states)
        assert proof['committed_cash_before'] == proof['committed_cash_after'] == 27175
        assert proof['dinosaurs_before'] == proof['dinosaurs_after'] == 1
        assert proof['reservation_released'] == proof['expense_posted'] == 25000


def test_vegasaurus_refund_proof_allows_native_month_settlement_during_animation():
    from copy import deepcopy
    before = {'balances': {'cash': 27029, 'loan': 4411, 'working_cash': 27029},
              'calendar': [0, 5, 29, 5], 'expenses': [1250] + [0] * 11,
              'pens': 'occupied-coelophysis', 'species': 'one-coelophysis', 'selection': 19, 'dinosaurs': 1}
    reserved = deepcopy(before)
    reserved['balances']['working_cash'] = 2029
    reserved['expenses'][5] = 25000
    release_before = deepcopy(reserved)
    release_before['balances'] = {'cash': 27098, 'loan': 4290, 'working_cash': 2098}
    release_before['calendar'] = [0, 6, 0, 6]
    released = deepcopy(release_before)
    released['balances']['working_cash'] = 27098
    proof = module.verify_vegasaurus_order([before, reserved, release_before, released])
    assert proof['reservation_released'] == 25000
    assert proof['committed_cash_before'] == 27029 and proof['committed_cash_after'] == 27098
    assert proof['expense_month'] == 5 and proof['cash_change_during_animation'] == 69
    assert proof['loan_before'] == 4411 and proof['loan_after'] == 4290


def test_dinomart_description_has_no_unobserved_purchase_outcome(monkeypatch):
    scene = module.TextScene(Debug(), 'office', None)
    scene.current, scene.mart = 'dinomart', 'mart'
    monkeypatch.setattr(module, 'balances', lambda _: {'cash': 30000, 'loan': 0, 'working_cash': 30000})
    text = scene.describe().lower()
    assert 'vegasaurus' in text and '$25,000' in text and 'read vegasaurus' in text
    assert not any(word in text for word in ('refund', 'fake', 'joke', 'gag', 'no animal', 'disabled'))


def test_encyclopedia_request_outside_dinomart_withholds_input():
    debug = Debug()
    scene = module.TextScene(debug, 'office', None)
    assert 'No input was sent' in scene.act('read vegasaurus')
    assert debug.calls == []


def test_store_exit_observes_views_without_freezing_operating_balances(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', None, event=events.append)
    scene.current, scene.street = 'general_store', 'street'
    scene.locations['general_store'] = 'store'
    scene.patterns = {'general_store': 'cover', 'fence_tab': 'tab', 'fence_selected': 'selected'}
    values = iter([{'cash': 5697, 'loan': 5000, 'working_cash': 5697},
                   {'cash': 5697, 'loan': 5000, 'working_cash': 5697},
                   {'cash': 6358, 'loan': 4885, 'working_cash': 6358}])
    monkeypatch.setattr(module, 'balances', lambda _: next(values))
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'cover'}, 'cover'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    clicks = []; observations = []
    monkeypatch.setattr(scene, 'shop_click', lambda point, ms, name, **kwargs: clicks.append((point, name)))
    def observe(view, expected, name, **kwargs):
        observations.append((view, expected))
        assert expected == {}, 'Navigation must not pin a changing financial snapshot'
    monkeypatch.setattr(scene, 'shop_observe', observe)
    monkeypatch.setattr(scene, 'describe', lambda: 'street')
    assert scene.leave_store() == 'street'
    assert scene.current == 'street'
    assert [p for p, _ in clicks] == [(205, 105), (263, 165), (160, 54), (188, 187)]
    assert events[-1]['after']['cash'] == 6358
    assert events[-1]['after']['loan'] == 4885


def test_store_exit_with_unresolved_reservation_withholds_navigation(monkeypatch):
    debug = Debug(); events = []
    scene = module.TextScene(debug, 'office', None, event=events.append)
    scene.current = 'general_store'
    monkeypatch.setattr(module, 'balances', lambda _: {'cash': 4000, 'loan': 5000, 'working_cash': 3000})
    assert 'No input was sent' in scene.leave_store()
    assert scene.current == 'general_store'
    assert debug.calls == []
    assert events[-1]['phase'] == 'refused'


def test_resource_reads_distinguish_guide_and_small_feeder_fields():
    class ResourceDebug:
        def memory(self, address, length):
            assert length == 2
            return {'hex': {'4020:6f8e': '0100', '4020:6f94': '1400'}[address]}
    assert module.park_resources(ResourceDebug()) == {'guides': 1, 'small_feeders': 20}


def test_snapshot_reads_live_counts_and_rejects_invalid_pen():
    import struct
    class SnapshotDebug:
        def __init__(self):
            self.pens = bytearray(200)
            for i in range(10):
                struct.pack_into('<hh', self.pens, i * 20 + 14, -1, 0)
            struct.pack_into('<hh', self.pens, 14, 3, 2)
        def memory(self, address, length):
            values = {'4020:4384': bytes(self.pens), '4020:6f94': struct.pack('<9h', 19, *([0] * 8)),
                      '4020:ccfc': b'\0\0', '4020:ccfe': b'\0\0', '4020:6fcb': b'\x08\0',
                      '4020:6fc9': b'\x01\0', '4020:5c3a': (1234).to_bytes(4, 'little'),
                      '4020:6fc0': b'\0\0\0\0',
                      '4020:bfbb': (5000).to_bytes(4, 'little'), '4020:bad4': (1234).to_bytes(4, 'little'),
                      '4020:6f8e': b'\x01\0'}
            return {'hex': values[address][:length].hex()}
    debug = SnapshotDebug()
    result = module.park_snapshot(debug)
    assert (result['dinosaurs'], result['food_bins'][0], result['guides']) == (2, 19, 1)
    assert result['pens'] == [{'pen': 1, 'species_id': 3, 'count': 2}]
    struct.pack_into('<hh', debug.pens, 14, -1, 1)
    with pytest.raises(RuntimeError, match='dinosaur count unknown'):
        module.park_snapshot(debug)


@pytest.mark.parametrize(('scene_name', 'command'), [
    ('employment', 'hire tour guide'),
    ('dino_diner', 'buy 20 small feeders'),
    ('street', 'open park'),
])
def test_unqualified_preparation_sends_no_input(scene_name, command):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', event=events.append)
    scene.current = scene_name
    assert 'No input was sent' in scene.act(command)
    assert not any(call[0] == 'click' for call in debug.calls)
    assert events[-1]['phase'] == 'refused' and events[-1]['input'] == 'not_sent'


def test_wrong_pending_guide_count_stops_before_commit():
    class PendingDebug:
        def memory(self, address, length):
            assert (address, length) == ('4020:b9fc', 2)
            return {'hex': '0000'}
    events = []
    scene = module.TextScene(PendingDebug(), 'office', 'bank', event=events.append)
    with pytest.raises(RuntimeError, match='pending guide'):
        scene.observe_pending_guide(1, 'guide staged')
    assert events[-1]['count'] == 0


def test_food_increment_failure_does_not_repeat_or_confirm(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', event=events.append)
    scene.current = 'dino_diner'
    scene.locations['dino_diner'] = 'diner'
    scene.guide_hired = True
    calls = []
    monkeypatch.setattr(module, 'balances', lambda _: {'cash': 2250, 'loan': 5000, 'working_cash': 2250})
    monkeypatch.setattr(module, 'park_resources', lambda _: {'guides': 1, 'small_feeders': 0})
    monkeypatch.setattr(module, 'pending_small_feeders', lambda _: 0)
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'menu'}, 'cover'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    scene.patterns = {'dino_diner': 'cover', 'food_menu': 'menu', 'food_selected': 'selected'}
    monkeypatch.setattr(scene, 'observe_resources', lambda *args: {'guides': 1, 'small_feeders': 0})
    monkeypatch.setattr(scene, 'shop_click', lambda point, ms, name, **kwargs: calls.append(name))
    def observe(view, expected, name, **kwargs):
        if name == 'food-staged-01':
            raise RuntimeError('food increment uncertain')
    monkeypatch.setattr(scene, 'shop_observe', observe)
    with pytest.raises(RuntimeError, match='increment uncertain'):
        scene.buy_food()
    assert calls == ['open meat menu', 'select small feeders', 'add small feeder 1']
    assert scene.food_bought is False


def test_restock_rejects_unexpected_pending_food_before_more_input(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', event=events.append)
    scene.current = 'dino_diner'
    scene.locations['dino_diner'] = 'diner'
    scene.guide_hired = scene.food_bought = scene.park_opened = True
    scene.patterns = {'dino_diner': 'cover', 'food_menu': 'menu', 'food_selected': 'selected'}
    values = iter([{'cash': 3000, 'loan': 5000, 'working_cash': 3000},
                   {'cash': 3000, 'loan': 5000, 'working_cash': 3000},
                   {'cash': 3000, 'loan': 5000, 'working_cash': 2975}])
    pending = iter([19, 19])
    monkeypatch.setattr(module, 'balances', lambda _: next(values))
    monkeypatch.setattr(module, 'park_resources', lambda _: {'guides': 1, 'small_feeders': 19})
    monkeypatch.setattr(module, 'pending_small_feeders', lambda _: next(pending))
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'menu'}, 'menu'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(scene, 'shop_observe', lambda *args, **kwargs: None)
    calls = []
    monkeypatch.setattr(scene, 'shop_click', lambda point, ms, name, **kwargs: calls.append(name))
    with pytest.raises(RuntimeError, match='food stock reservation'):
        scene.buy_food()
    assert calls == ['select small feeders', 'add small feeder 1']
    assert events[-1]['pending'] == 19


class FoodCommitDebug(Debug):
    def __init__(self):
        super().__init__()
        self.stage = 0

    def breakpoint(self, address):
        self.calls.append(('breakpoint', address))
        return {'breakpoint_id': address, 'bytes_verified': True}

    def delete_breakpoint(self, identifier):
        self.calls.append(('delete', identifier))

    def click(self, x, y, *, hold_ms):
        self.calls.append(('confirm', x, y))
        return {'accepted': True, 'delivery': 'queued'}

    def run(self, **kwargs):
        self.stage += 1
        if self.stage > 2:
            return {'outcome': 'guest_time', 'guest_elapsed_ms': 6000}
        identifier = ['2d0a:2810', '2d0a:283d'][self.stage - 1]
        return {'outcome': 'breakpoint', 'guest_elapsed_ms': 0,
                'session': {'stop_reason': {'breakpoint_id': identifier}}}


class FoodCommitProject:
    def analyze(self, **kwargs):
        return {'stable': False, 'budget_exhausted': True}


def food_commit_state(committed=False):
    return {'balances': {'cash': 3500 if committed else 4000, 'working_cash': 3500, 'loan': 5000},
            'live_food': [38 if committed else 18] + [0] * 8, 'pending_food': [38] + [0] * 8,
            'calendar': [0, 0, 20, 6], 'expenses': 510 if committed else 10}


def test_food_purchase_is_proven_at_commit_before_later_stock_use(monkeypatch):
    debug = FoodCommitDebug()
    events = []
    scene = module.TextScene(debug, 'office', None, project=FoodCommitProject(), event=events.append)
    states = iter([food_commit_state(), food_commit_state(True)])
    monkeypatch.setattr(module, 'food_order_state', lambda _: next(states), raising=False)
    result = scene.confirm_food_order()
    assert result['stock_at_commit'] == 38 and result['price'] == 500
    assert scene.food_bought is True
    assert events[-1]['phase'] == 'food_purchase_committed'
    assert len([x for x in debug.calls if x[0] == 'confirm']) == 1
    assert len([x for x in debug.calls if x[0] == 'delete']) == 2


@pytest.mark.parametrize('defect', ['stock', 'cash', 'expense'])
def test_food_commit_rejects_incorrect_native_delivery_or_accounting(monkeypatch, defect):
    debug = FoodCommitDebug()
    scene = module.TextScene(debug, 'office', None, project=FoodCommitProject(), event=lambda _: None)
    after = food_commit_state(True)
    if defect == 'stock':
        after['live_food'][0] = 37
    elif defect == 'cash':
        after['balances']['cash'] = 3400
    else:
        after['expenses'] = 1010
    states = iter([food_commit_state(), after])
    monkeypatch.setattr(module, 'food_order_state', lambda _: next(states), raising=False)
    with pytest.raises(RuntimeError, match='commit'):
        scene.confirm_food_order()
    assert scene.food_bought is False
    assert len([x for x in debug.calls if x[0] == 'confirm']) == 1


@pytest.mark.parametrize('late_view_failure', [False, True])
def test_food_order_keeps_confirmed_purchase_when_return_consumes_food(monkeypatch, late_view_failure):
    debug = FoodCommitDebug()
    events = []
    scene = module.TextScene(debug, 'office', None, project=FoodCommitProject(), event=events.append)
    scene.current, scene.street = 'dino_diner', 'street'
    scene.locations['dino_diner'] = 'diner'
    scene.guide_hired = scene.food_bought = scene.park_opened = True
    scene.patterns = {'dino_diner': 'cover', 'food_menu': 'menu', 'food_selected': 'selected'}
    quantity = [0]
    def add(point, ms, name, **kwargs):
        if name.startswith('add small feeder '):
            quantity[0] += 1
    def money(_):
        if debug.stage >= 2:
            return {'cash': 3500, 'loan': 5000, 'working_cash': 3500}
        return {'cash': 4000, 'loan': 5000, 'working_cash': 4000 - 25 * quantity[0]}
    def resources(_=None):
        return {'guides': 1, 'small_feeders': 37 if debug.stage > 2 else 18}
    def observe(*args, **kwargs):
        if late_view_failure and debug.stage > 2:
            raise RuntimeError('late display failure')
    states = iter([food_commit_state(), food_commit_state(True)])
    monkeypatch.setattr(module, 'food_order_state', lambda _: next(states))
    monkeypatch.setattr(module, 'balances', money)
    monkeypatch.setattr(module, 'park_resources', resources)
    monkeypatch.setattr(module, 'pending_small_feeders', lambda _: 18 + quantity[0])
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'menu'}, 'menu'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(scene, 'shop_click', add)
    monkeypatch.setattr(scene, 'shop_observe', observe)
    if late_view_failure:
        with pytest.raises(RuntimeError, match='purchase confirmed.*do not repeat'):
            scene.buy_food()
        assert events[-1]['phase'] == 'food_followup_failed'
        assert events[-1]['purchase_outcome'] == 'confirmed'
    else:
        message = scene.buy_food()
        assert 'Stock at confirmation: 38' in message and 'Stock now: 37' in message
        assert scene.current == 'street'
        assert events[-1]['stock_change_after_commit'] == -1
        assert events[-1]['purchase_outcome'] == 'confirmed'
    assert scene.food_bought is True
    assert quantity[0] == 20
    assert len([x for x in debug.calls if x[0] == 'confirm']) == 1


def test_unverified_commit_boundary_withholds_confirmation_and_cleans_controls():
    class UnverifiedDebug(FoodCommitDebug):
        def breakpoint(self, address):
            return {'breakpoint_id': address, 'bytes_verified': address != '2d0a:283d'}
    debug = UnverifiedDebug()
    scene = module.TextScene(debug, 'office', None, project=FoodCommitProject(), event=lambda _: None)
    with pytest.raises(RuntimeError, match='identity was not verified'):
        scene.confirm_food_order()
    assert not any(x[0] == 'confirm' for x in debug.calls)
    assert [x for x in debug.calls if x[0] == 'delete'] == [('delete', '2d0a:2810'), ('delete', '2d0a:283d')]


def test_unexpected_native_stop_never_repeats_food_confirmation():
    class StoppedDebug(FoodCommitDebug):
        def run(self, **kwargs):
            return {'outcome': 'timeout'}
    debug = StoppedDebug()
    scene = module.TextScene(debug, 'office', None, project=FoodCommitProject(), event=lambda _: None)
    with pytest.raises(RuntimeError, match='boundary not reached'):
        scene.confirm_food_order()
    assert scene.food_bought is False
    assert len([x for x in debug.calls if x[0] == 'confirm']) == 1
    assert len([x for x in debug.calls if x[0] == 'delete']) == 2


def test_advance_stops_on_notice_without_acknowledging_or_repeating(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', project=object(),
                             patterns={'quarter_popup': 'quarter', 'parking_hint': 'parking'}, event=events.append)
    scene.current, scene.park_opened, scene.park = 'park', True, 'park-revision'
    snapshot = {'year_index': 0, 'month_index': 0, 'day_of_month_counter': 5,
                'weekly_counter': 5, 'balances': {'cash': 100, 'loan': 5000},
                'guides': 1, 'food_bins': [20] + [0] * 8, 'pens': [], 'dinosaurs': 0}
    monkeypatch.setattr(scene, 'observe_park_status', lambda label: (snapshot, 'status'))
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'notice'}, 'quarter'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(module, 'run_guest', lambda d, ms: d.calls.append(('run', ms)) or {'outcome': 'guest_time'})
    assert 'notice interrupted' in scene.advance_time()
    assert debug.calls == [('run', 1000)]
    assert events[-1]['phase'] == 'interrupted'


def test_unknown_notice_acknowledgment_is_never_retried():
    debug = Debug()
    scene = module.TextScene(debug, 'office', 'bank', event=lambda _: None)
    scene.current, scene.park_opened, scene.notice_outcome_unknown = 'park', True, True
    assert 'No input was sent' in scene.acknowledge_notice()
    assert debug.calls == []


def test_notice_that_remains_after_enter_is_indeterminate(monkeypatch):
    class NoticeDebug(Debug):
        def keyboard_press(self, key):
            self.calls.append(('press', key))
            return {'accepted': True, 'delivery': 'queued'}
    debug = NoticeDebug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', project=object(),
                             patterns={'quarter_popup': 'quarter', 'parking_hint': 'parking'}, event=events.append)
    scene.current, scene.park_opened = 'park', True
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'frame'}, 'quarter'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    monkeypatch.setattr(module, 'run_guest', lambda d, ms: d.calls.append(('run', ms)))
    assert 'outcome is unknown' in scene.acknowledge_notice()
    assert scene.notice_outcome_unknown is True
    assert 'No input was sent' in scene.acknowledge_notice()
    assert 'No input was sent' in scene.act('go street')
    assert [call for call in debug.calls if call[0] == 'press'] == [('press', 'enter')]
    assert events[-2]['phase'] == 'indeterminate' and events[-1]['phase'] == 'refused'


def test_unqualified_parking_notice_receives_no_input(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', project=object(),
                             patterns={'quarter_popup': 'quarter', 'parking_hint': 'parking'}, event=events.append)
    scene.current, scene.park_opened = 'park', True
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'frame'}, 'parking'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    assert 'not qualified' in scene.acknowledge_notice()
    assert debug.calls == [] and events[-1]['input'] == 'not_sent'


def test_inventory_after_balance_changes_points_to_status():
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', event=events.append)
    scene.current, scene.dinosaur_bought, scene.park_opened = 'street', True, True
    assert 'Use status' in scene.check_inventory()
    assert debug.calls == [] and events[-1]['input'] == 'not_sent'


def test_notice_during_park_reentry_is_not_reported_as_success(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', project=object(),
                             patterns={'quarter_popup': 'quarter', 'parking_hint': 'parking'}, event=events.append)
    scene.current, scene.park_opened = 'street', True
    monkeypatch.setattr(scene, 'observe_park_status', lambda label: ({'day': 1}, 'status'))
    monkeypatch.setattr(scene, 'shop_click', lambda *args, **kwargs: None)
    monkeypatch.setattr(module, 'take_frame', lambda *args: ({'artifact': 'frame'}, 'quarter'))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == pattern)
    with pytest.raises(RuntimeError, match='notice during park entry'):
        scene.revisit_park()
    assert scene.current == 'street' and events[-1]['phase'] == 'indeterminate'


def test_placement_waits_for_recognized_view_without_replaying_input(monkeypatch):
    debug = Debug()
    events = []
    scene = module.TextScene(debug, 'office', 'bank', project=object(),
                             patterns={'placement': {}}, event=events.append)
    frames = iter([({'artifact': 'loading'}, 'loading'), ({'artifact': 'ready'}, 'ready')])
    monkeypatch.setattr(module, 'take_frame', lambda *args: next(frames))
    monkeypatch.setattr(module, 'matches', lambda image, pattern: image == 'ready')
    monkeypatch.setattr(module, 'run_guest', lambda d, ms: d.calls.append(('run', ms)))
    result = scene.shop_observe('placement', {'cash': 5000}, 'placement', wait_slices=2)
    assert result['artifact'] == 'ready'
    assert debug.calls == [('run', 500)]
    assert [event['matched'] for event in events] == [False, True]
