"""The original picked card moves independently from its disabled BUY button."""
import json

from PIL import Image
import pytest

from fdisbull import dinopark_purchase as purchase, dinopark_scenes as scenes


def picked_frame(dx=0):
    pattern=json.loads(scenes.OPERATING_PATTERNS.read_text())['scenes']['coel_picked']
    image=Image.new('RGB',(320,200),(1,2,3))
    for sample in pattern['samples']:
        image.putpixel((sample['x']+(dx if sample['y']<170 else 0),sample['y']),tuple(sample['rgb']))
    return image,pattern


@pytest.mark.parametrize('dx',[-8,0,8])
def test_exact_picked_card_and_fixed_disabled_button(dx):
    image,pattern=picked_frame(dx)
    assert dx in purchase.picked_card_offsets(image,pattern)


@pytest.mark.parametrize('fault',['left-limit','right-limit','card','button','selected-view'])
def test_picked_rule_preserves_all_anchors_and_its_narrow_motion_bound(fault):
    image,pattern=picked_frame(-8)
    if fault=='left-limit':image,pattern=picked_frame(-9)
    elif fault=='right-limit':image,pattern=picked_frame(9)
    elif fault=='card':image.putpixel((124,61),(1,2,3))
    elif fault=='button':
        s=next(s for s in pattern['samples'] if s['y']>=170)
        image.putpixel((s['x'],s['y']),(1,2,3))
    else:
        from test_dinopark_selected_catalogue import selected_frame
        image,_=selected_frame(-8)
    assert not purchase.picked_card_offsets(image,pattern)


@pytest.mark.parametrize('ready',[True,False])
def test_picked_wait_qualifies_a_retained_frame_without_renewing_guest_allowance(monkeypatch,ready):
    from test_dinopark_purchase_reconcile import shop
    real_matches=scenes.matches
    text,native,_=shop(monkeypatch)
    image,pattern=picked_frame(-8)
    if not ready:
        s=next(s for s in pattern['samples'] if s['y']>=170)
        image.putpixel((s['x'],s['y']),(1,2,3))
    text.patterns['coel_picked']=pattern
    text.dinosaur_order={'phase':'select','last_input_phase':'select',
                         'wait_guest_ms':{'coel_picked':12000}}
    monkeypatch.setattr(scenes,'take_frame',lambda *a,**k:({'artifact':'authored-picked'},image))
    monkeypatch.setattr(scenes,'matches',real_matches)
    if ready:
        assert purchase._wait(text,purchase.PurchaseBudget(),'coel_picked',native.money)['artifact']=='authored-picked'
    else:
        with pytest.raises(TimeoutError,match='guest budget'):
            purchase._wait(text,purchase.PurchaseBudget(),'coel_picked',native.money)
    assert native.clicks==native.runs==[]
    assert text.dinosaur_order['wait_guest_ms']['coel_picked']==12000
