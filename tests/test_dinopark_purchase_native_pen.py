"""Original oracle readbacks place this qualified purchase in record ten."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull import dinopark_purchase as purchase


def original_record_ten_order():
    # Independently observed in the retained original-game oracle, including
    # command-complete buy coelophysis; the helper does not define this index.
    before = {'balances':{'cash':4500,'loan':5000,'working_cash':4500},
              'pens':[], 'month':0, 'expenses':[0]*12}
    after = {'balances':{'cash':3250,'loan':5000,'working_cash':3250},
             'pens':[{'pen':10,'species':4,'count':1}], 'month':0,
             'expenses':[1250]+[0]*11}
    order = {'id':'original-order', 'before':before,'species':4,'price':1250,
             'last_input_phase':'confirm', 'last_input':{'accepted':True,'delivery':'queued'}}
    return order, after


def test_original_record_ten_can_be_certified():
    order, after = original_record_ten_order()
    assert purchase.commit_proof(order,after)['after']['pens']==[{'pen':10,'species':4,'count':1}]


def test_wrong_native_record_cannot_substitute_for_the_observed_target():
    order, after = original_record_ten_order()
    after = deepcopy(after)
    after['pens'][0]['pen'] = 1
    with pytest.raises(ValueError,match='commit remains unqualified'):
        purchase.commit_proof(order,after)


@pytest.mark.parametrize('pen,allowed', [(10,True),(1,False)])
def test_retained_order_qualification_uses_the_same_observed_native_record(monkeypatch,pen,allowed):
    _, after = original_record_ten_order()
    after['pens'][0]['pen'] = pen
    text = SimpleNamespace(dinosaur_order={'run':'original'}, debug=SimpleNamespace(run_id='original'))
    monkeypatch.setattr(purchase,'native_state',lambda debug:after)
    if allowed: assert purchase.recovery_view(text)['pens'][0]['pen']==10
    else:
        with pytest.raises(ValueError,match='herd is not qualified'):
            purchase.recovery_view(text)
