"""Selected-card motion and fixed BUY anchors are distinct original UI groups."""
from copy import deepcopy
import json

from PIL import Image
import pytest

from fdisbull import dinopark_purchase as purchase, dinopark_scenes as scenes


def selected_frame(dx=0, *, fixed_dx=0):
    # Authored pixels only: no original game screenshot is stored in source.
    pattern = json.loads(scenes.OPERATING_PATTERNS.read_text())['scenes']['coel_selected']
    image = Image.new('RGB', (320, 200), (1, 2, 3))
    for sample in pattern['samples']:
        offset = dx if sample['y'] < 170 else fixed_dx
        image.putpixel((sample['x'] + offset, sample['y']), tuple(sample['rgb']))
    return image, pattern


@pytest.mark.parametrize('dx', [-24, -16, -8, 0, 8, 24])
def test_all_selected_card_anchors_may_translate_together(dx):
    image, pattern = selected_frame(dx)
    assert dx in purchase.selected_card_offsets(image, pattern)


@pytest.mark.parametrize('fault', ['moving-anchor', 'fixed-anchor', 'fixed-moved', 'out-of-range', 'reject'])
def test_translation_never_weakens_fixed_or_card_predicates(fault):
    image, pattern = selected_frame(-8)
    if fault == 'moving-anchor': image.putpixel((126, 61), (1,2,3))
    elif fault == 'fixed-anchor': image.putpixel((176, 181), (1,2,3))
    elif fault == 'fixed-moved': image, pattern = selected_frame(-8, fixed_dx=2)
    elif fault == 'out-of-range': image, pattern = selected_frame(-25)
    else:
        pattern = deepcopy(pattern)
        pattern['reject'] = [{'samples':[{'x':0,'y':0,'rgb':[1,2,3]}], 'min_matches':1,'tolerance':0}]
    assert not purchase.selected_card_offsets(image, pattern)


def test_unrelated_scene_does_not_gain_the_selected_translation_rule():
    image, _ = selected_frame(-8)
    pattern = json.loads(scenes.OPERATING_PATTERNS.read_text())['scenes']['coel_picked']
    assert not scenes.matches(image, pattern)


@pytest.mark.parametrize('fault', ['species', 'price'])
def test_shifted_selected_frame_still_requires_original_species_and_price(monkeypatch, fault):
    from test_dinopark_purchase_reconcile import shop
    real_matches = scenes.matches
    text, native, events = shop(monkeypatch)
    frame, pattern = selected_frame(-16)
    from test_dinopark_picked_catalogue import picked_frame
    first_frame,first_pattern=picked_frame()
    text.patterns['coel_selected'] = pattern
    text.patterns['coel_picked'] = first_pattern
    take_frame, fake_matches = scenes.take_frame, scenes.matches
    monkeypatch.setattr(scenes, 'take_frame', lambda *a, **k:
        ({'artifact':'authored-selected'}, frame) if native.view == 'coel_selected' else
        ({'artifact':'authored-picked'}, first_frame) if native.view == 'coel_picked' else take_frame(*a, **k))
    monkeypatch.setattr(scenes, 'matches', lambda image, spec:
        real_matches(image, spec) if isinstance(image, Image.Image) else fake_matches(image, spec))
    if fault == 'species': native.species = 19
    else: native.price = 999
    with pytest.raises(ValueError, match='species or price'):
        text.buy_dinosaur()
    assert native.clicks == [(160,87),(160,103)]
    assert not text.dinosaur_bought
    assert not any(e.get('phase') == 'coelophysis_purchase_confirmed' for e in events)


def test_card_samples_cannot_be_combined_across_offsets():
    _, pattern = selected_frame()
    image = Image.new('RGB', (320,200), (1,2,3))
    for index, sample in enumerate(pattern['samples']):
        offset = (-24 if index % 2 else 24) if sample['y'] < 170 else 0
        image.putpixel((sample['x']+offset,sample['y']), tuple(sample['rgb']))
    assert not purchase.selected_card_offsets(image, pattern)


@pytest.mark.parametrize('state', ['ready-exhausted', 'wrong-exhausted', 'release', 'picked-phase'])
def test_selected_wait_keeps_phase_release_and_cumulative_allowance(monkeypatch, state):
    from test_dinopark_purchase_reconcile import shop
    real_matches = scenes.matches
    text, native, _ = shop(monkeypatch)
    image, pattern = selected_frame(-16)
    text.patterns['coel_selected'] = pattern
    text.patterns['coel_picked'] = json.loads(scenes.OPERATING_PATTERNS.read_text())['scenes']['coel_picked']
    text.dinosaur_order = {'phase':'price', 'last_input_phase':'price',
                           'wait_guest_ms':{'coel_selected':12000, 'coel_picked':12000}}
    monkeypatch.setattr(scenes, 'take_frame', lambda *a, **k: ({'artifact':'authored-selected'},image))
    monkeypatch.setattr(scenes, 'matches', real_matches)
    view = 'coel_picked' if state == 'picked-phase' else 'coel_selected'
    if state == 'wrong-exhausted': image.putpixel((176,181),(1,2,3))
    if state == 'release': native.release_pending = True
    if state == 'ready-exhausted':
        assert purchase._wait(text,purchase.PurchaseBudget(),view,native.money)['artifact']=='authored-selected'
    else:
        with pytest.raises(TimeoutError,match='guest budget'):
            purchase._wait(text,purchase.PurchaseBudget(),view,native.money)
    assert native.runs == native.clicks == []
    assert text.dinosaur_order['wait_guest_ms'][view] == 12000
