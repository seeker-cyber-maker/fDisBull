import pytest
from fdisbull.navigation_geometry import validate_navigation, navigation_check, route_first_boundary


def definition():
    return {'space':'room-coordinates','width':8,'height':8,
            'actor':{'width':2,'height':2,'anchor':[0,1]},
            'walkable':{'subtract':[{'rect':[0,0,8,8]},{'rect':[6,0,8,8]}]},
            'colliders':[{'id':'door','area':{'rect':[3,0,4,8]},'when':{'constant':True}}],
            'anchors':[{'id':'start','point':[0,1]}], 'portals':[],
            'provenance':{'extraction_rule':'manual','source_facts':['map'], 'evidence_status':'inferred'}}


def test_footprint_and_unknown_condition():
    doc=definition(); validate_navigation(doc)
    assert navigation_check(doc,[1,1])['classification']=='clear'
    assert navigation_check(doc,[2,1])['classification']=='unknown'
    assert navigation_check(doc,[2,1],conditions={'door':True})['classification']=='blocked'
    assert navigation_check(doc,[2,1],conditions={'door':False})['classification']=='clear'
    assert navigation_check(doc,[0,0])['classification']=='blocked'


def test_route_checks_between_endpoints():
    result=route_first_boundary(definition(),[[0,1],[5,1]],conditions={'door':True})
    assert result['result']['point']==[2,1]
    assert result['result']['classification']=='blocked'


def test_explicit_game_space_required():
    doc=definition();doc['space']='native-frame'
    with pytest.raises(ValueError):validate_navigation(doc)


def test_route_limits_and_rounded_diagonal():
    doc=definition();doc['actor']={'width':1,'height':1,'anchor':[0,0]}
    doc['colliders'][0]['area']={'rect':[1,0,2,1]}
    hit=route_first_boundary(doc,[[0,0],[2,1]],conditions={'door':True})
    assert hit['result']['point']==[1,0]
    with pytest.raises(ValueError,match='4096'):route_first_boundary(doc,[[0,0]]*4097)
    doc['width']=64;doc['height']=64;doc['walkable']={'rect':[0,0,64,64]}
    with pytest.raises(ValueError,match='65536'):route_first_boundary(doc,[[0,0],[63,63]]*1024)
