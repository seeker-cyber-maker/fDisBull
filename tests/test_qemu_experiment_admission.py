"""Bounded experiment admission and immutable logical layer identity."""
from copy import deepcopy

import pytest

from fdisbull.qemu_experiments import _logical_layer_hash, _validate_script


def route(*steps):
    return dict(format='fdisbull-script-1',backend='qemu-dos',steps=list(steps))


def test_implicit_trace_count_uses_native_default_128():
    trace=dict(op='trace')
    assert len(_validate_script(None,route(*[trace]*8))) == 8
    with pytest.raises(ValueError,match='trace budget'):
        _validate_script(None,route(*[trace]*9))


def test_trace_budget_combines_default_and_explicit_counts():
    assert len(_validate_script(None,route(*([dict(op='trace')]*7+[dict(op='trace',count=128)])))) == 8
    with pytest.raises(ValueError,match='trace budget'):
        _validate_script(None,route(*([dict(op='trace')]*7+[dict(op='trace',count=129)])))
    with pytest.raises(ValueError,match='literal|count'):
        _validate_script(None,route(dict(op='trace',count='$controls.trace_count')))


def test_expanded_step_and_memory_budgets_are_bounded():
    assert len(_validate_script(None,route(dict(op='repeat',count=128,steps=[dict(op='registers')]))))==128
    with pytest.raises(ValueError,match='128|steps'):
        _validate_script(None,route(dict(op='repeat',count=129,steps=[dict(op='registers')])))
    assert len(_validate_script(None,route(dict(op='memory',address='0x10000',length=32768,space='virtual'),
                                                dict(op='memory',address='0x18000',length=32768,space='virtual'))))==2
    with pytest.raises(ValueError,match='memory|64 KiB'):
        _validate_script(None,route(dict(op='memory',address='0x10000',length=32768,space='virtual'),
                                    dict(op='memory',address='0x18000',length=32769,space='virtual')))


def test_unsupported_machine_memory_domain_refuses_before_any_capture():
    with pytest.raises(ValueError,match='physical or virtual'):
        _validate_script(None,route(dict(op='memory',address='0x10000',length=2,space='linear')))


@pytest.mark.parametrize('step',[
    dict(op='screenshot',grid=True),
    dict(op='keyboard.press',key='a'),
    dict(op='rewind-record'),
    dict(op='delta-record'),
])
def test_mutating_routes_and_grid_screenshots_are_refused(step):
    with pytest.raises(ValueError):
        _validate_script(None,route(step))


def layer():
    return dict(id='original',version='v1',name='private',kind='ram',created='2026-01-01',sha256='old',
        patches=[dict(address='0x10000',expected_hex='0000',data_hex='3412')],
        native_binding=dict(run='run1',epoch='epoch1',space='physical',
            spans=[dict(address='0x110000',length=2)],
            task_identity=dict(monitor_uuid='a'*32,cookie=161,incarnation=1)))


def test_cloned_layer_hash_ignores_row_and_fresh_owner_identity():
    original=layer(); clone=deepcopy(original)
    clone.update(id='clone',created='2026-02-02',sha256='new',run='new-run')
    clone['native_binding'].update(run='run2',epoch='epoch2')
    assert _logical_layer_hash(original)==_logical_layer_hash(clone)


@pytest.mark.parametrize('change', ['cookie','backing','kind','patch','version'])
def test_logical_layer_hash_binds_material_identity(change):
    original=layer(); other=deepcopy(original)
    if change=='cookie': other['native_binding']['task_identity']['cookie']=178
    elif change=='backing': other['native_binding']['spans'][0]['address']='0x111000'
    elif change=='kind': other['kind']='execute'
    elif change=='patch': other['patches'][0]['data_hex']='7856'
    else: other['version']='v2'
    assert _logical_layer_hash(original)!=_logical_layer_hash(other)
