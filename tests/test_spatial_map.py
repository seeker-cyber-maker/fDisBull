from copy import deepcopy
from io import BytesIO
import pytest
from PIL import Image
from fdisbull.project import Project
from fdisbull.spatial_map import spatial_check, candidate_points, plan_route, render_spatial_map, save_spatial_map, load_spatial_map


def sample(digest='0'*64):
    return {'format':'fdisbull-spatial-map-1','source':{'sha256':digest,'context':'test','room':'1','resource':'picture-1'},'space':{'name':'game','width':8,'height':6,'unit':'game-unit'},'actor':{'width':2,'height':1,'anchor':[0,0]},'known':{'rect':[0,0,7,6]},'safe':{'rect':[0,0,6,6]},'layers':[{'id':'water','kind':'hazard','area':{'row_runs':[[2,2,4]]}},{'id':'door','kind':'obstacle','area':{'rect':[4,0,5,1]},'when':'closed'},{'id':'treasure','kind':'object','area':{'rect':[0,0,8,2]},'interaction_points':[[1,1]]}],'evidence':{'source':{'description':'test fixture'}}}


def test_footprint_unknown_conditions_and_candidates():
    d=sample()
    assert spatial_check(d,[1,2])['classification']=='blocked'
    assert spatial_check(d,[6,3])['classification']=='blocked'
    d['actor']['width']=1
    assert spatial_check(d,[7,3])['classification']=='unknown'
    assert spatial_check(d,[4,0])['classification']=='unknown'
    assert spatial_check(d,[4,0],conditions={'closed':False})['classification']=='clear'
    assert [2,2] not in candidate_points(d,clearance=1,limit=100,conditions={'closed':False})
    assert all(spatial_check(d,p,conditions={'closed':False})['classification']=='clear' for p in candidate_points(d,zone='treasure',limit=100,conditions={'closed':False}))


def test_route_budget_and_render():
    d=sample(); d['actor']['width']=1
    assert plan_route(d,[0,0],[5,5],conditions={'closed':False},maxnodes=1)['status']=='budget_exhausted'
    route=plan_route(d,[0,0],[5,5],conditions={'closed':False})
    assert route['status']=='found'
    assert all(abs(a[0]-b[0])+abs(a[1]-b[1])==1 for a,b in zip(route['path'],route['path'][1:]))
    rendered=render_spatial_map(d,conditions={'closed':False})
    im=Image.open(BytesIO(rendered['png']))
    assert im.size==(8,6) and im.getpixel((2,2))==(50,100,200)
    assert im.getpixel((7,4))==(128,128,128)


def test_restart_and_immutable_revisions(tmp_path):
    binary=tmp_path/'TEST.COM'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21'); db=tmp_path/'test.fdb'
    with Project.create(db,binary,image='com') as p:
        d=sample(p.version()['sha256']); first=save_spatial_map(p,'room',d)
        changed=deepcopy(d); changed['source']['room']='2'
        second=save_spatial_map(p,'room',changed,parent=first['id'])
        with pytest.raises(ValueError,match='parent'): save_spatial_map(p,'room',d,parent=first['id'])
    with Project(db) as p:
        assert load_spatial_map(p,first['id'])['document']['source']['room']=='1'
        assert load_spatial_map(p,second['id'])['document']['source']['room']=='2'
        p.db.execute('UPDATE spatial_maps SET sha256=? WHERE id=?',('0'*64,first['id'])); p.db.commit()
        with pytest.raises(ValueError,match='hash'): load_spatial_map(p,first['id'])


def test_empty_masks_unknown_and_known_non_safe():
    d=sample(); d['actor']={'width':1,'height':1,'anchor':[0,0]}; d['layers']=[]
    d['known']={'row_runs':[]}; d['safe']={'row_runs':[]}
    assert spatial_check(d,[2,2])['classification']=='unknown'
    assert candidate_points(d)==[]
    d['known']={'rect':[0,0,8,6]}
    assert spatial_check(d,[2,2])['classification']=='blocked'
    assert plan_route(d,[1,1],[2,2])['status']=='endpoint_not_clear'


def test_anchor_and_no_route():
    d=sample(); d['actor']={'width':3,'height':1,'anchor':[1,0]}
    assert spatial_check(d,[1,2])['classification']=='blocked'
    assert spatial_check(d,[0,3])['classification']=='blocked'
    d['actor']={'width':1,'height':1,'anchor':[0,0]}
    d['known']={'rect':[0,0,8,6]}; d['safe']={'rect':[0,0,8,6]}
    d['layers']=[{'id':'wall','kind':'obstacle','area':{'rect':[3,0,4,6]},'when':'wall_active'}]
    assert spatial_check(d,[3,2])['classification']=='unknown'
    assert plan_route(d,[1,2],[5,2],conditions={'wall_active':True})['status']=='no_route'
    assert plan_route(d,[1,2],[5,2],conditions={'wall_active':False})['status']=='found'


def test_composed_row_runs_and_empty_results():
    d=sample(); d['actor']={'width':1,'height':1,'anchor':[0,0]}; d['layers']=[]
    d['known']={'rect':[0,0,8,6]}
    runs={'row_runs':[[1,0,4],[2,2,6]]}
    d['safe']={'intersection':[{'rect':[2,1,5,3]},runs]}
    assert spatial_check(d,[2,1])['classification']=='clear'
    assert spatial_check(d,[1,1])['classification']=='blocked'
    assert spatial_check(d,[4,2])['classification']=='clear'
    d['safe']={'subtract':[{'union':[runs,{'rect':[6,4,8,5]}]},runs]}
    assert spatial_check(d,[6,4])['classification']=='clear'
    assert spatial_check(d,[2,1])['classification']=='blocked'
    d['safe']={'subtract':[runs,runs]}
    assert candidate_points(d)==[]
    d['known']={'intersection':[runs,{'row_runs':[]}]}; d['safe']={'row_runs':[]}
    assert spatial_check(d,[2,1])['classification']=='unknown'


def test_composite_geometry_depth_is_bounded():
    d=sample(); shape={'row_runs':[]}
    for _ in range(9): shape={'union':[shape,{'row_runs':[]}]}
    d['known']=shape; d['safe']={'row_runs':[]}
    with pytest.raises(ValueError,match='excessive'): spatial_check(d,[1,1])


def test_fast_candidates_match_detailed_checks_and_clearance():
    d=sample(); d['actor']={'width':3,'height':2,'anchor':[1,1]}
    for states in ({},{'closed':True},{'closed':False}):
        expected=[[x,y] for y in range(6) for x in range(8) if spatial_check(d,[x,y],conditions=states)['classification']=='clear']
        assert candidate_points(d,limit=100,conditions=states)==expected
        expected_set={tuple(p) for p in expected}
        with_clearance=[[x,y] for x,y in expected if all((x+dx,y+dy) in expected_set for dx in range(-1,2) for dy in range(-1,2))]
        assert candidate_points(d,limit=100,clearance=1,conditions=states)==with_clearance
        assert candidate_points(d,limit=100,origin=[7,5],conditions=states)==sorted(expected,key=lambda p:(abs(p[0]-7)+abs(p[1]-5),p[1],p[0]))
    assert candidate_points(d,clearance=64)==[]


def test_blocked_precedes_unknown_for_footprint():
    d=sample(); d['actor']={'width':2,'height':1,'anchor':[0,0]}
    d['layers']=[{'id':'maybe','kind':'obstacle','area':{'rect':[1,2,2,3]},'when':'active'}, {'id':'wall','kind':'obstacle','area':{'rect':[2,2,3,3]}}]
    result=spatial_check(d,[1,2])
    assert result['classification']=='blocked' and result['reasons']=={'blocked':['wall'],'unknown':['maybe']}
    assert [1,2] not in candidate_points(d,limit=100)


def test_screenshot_evidence_is_version_bound_and_rechecked(tmp_path):
    import hashlib
    from io import BytesIO
    from PIL import Image
    from fdisbull.debugger import DEBUG_DDL
    binary=tmp_path/'TEST.COM'; binary.write_bytes(b'\xb8\x00\x4c\xcd\x21'); db=tmp_path/'test.fdb'
    image=BytesIO(); Image.new('RGB',(2,2),'red').save(image,format='PNG'); data=image.getvalue(); digest=hashlib.sha256(data).hexdigest()
    with Project.create(db,binary,image='com') as p:
        p.db.executescript(DEBUG_DDL)
        version=p.version()['id']; p.db.execute("INSERT INTO debug_runs VALUES (?,?,?,?,?,?)",('run',version,'now',None,'closed','{}'))
        p.db.execute("INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)",('frame','run','frame.png','screenshot',digest,data,'{}'))
        p.db.commit()
        doc=sample(p.version()['sha256']); doc['evidence']['frame']={'artifact':'frame','sha256':digest,'description':'image identity only'}
        first=save_spatial_map(p,'room',doc)
        bad=deepcopy(doc); bad['evidence']['frame']['artifact']='missing'
        with pytest.raises(ValueError,match='Screenshot evidence'): save_spatial_map(p,'missing',bad)
        bad=deepcopy(doc); bad['evidence']['frame']['sha256']='0'*64
        with pytest.raises(ValueError,match='hash'): save_spatial_map(p,'wronghash',bad)
        bad=deepcopy(doc); del bad['evidence']['frame']['sha256']
        with pytest.raises(ValueError,match='SHA-256'): save_spatial_map(p,'missinghash',bad)
        p.db.execute("UPDATE debug_artifacts SET kind='state' WHERE id='frame'"); p.db.commit()
        with pytest.raises(ValueError,match='Screenshot evidence'): load_spatial_map(p,first['id'])
        p.db.execute("UPDATE debug_artifacts SET kind='screenshot-grid' WHERE id='frame'"); p.db.commit()
        assert load_spatial_map(p,first['id'])['id']==first['id']
        # A new image revision does not inherit an earlier version's artifact.
        patched=p.patch(hex(p.regions(version)[0].start),'90',version=version)
        later=p.version(patched['version']); cross=deepcopy(doc); cross['source']['sha256']=later['sha256']
        with pytest.raises(ValueError,match='selected project version'): save_spatial_map(p,'cross',cross,version=later['id'])
    with Project(db) as p:
        assert load_spatial_map(p,first['id'],version=version)['document']['evidence']['frame']['sha256']==digest
        p.db.execute("UPDATE debug_artifacts SET data=? WHERE id='frame'",(b'corrupt',)); p.db.commit()
        with pytest.raises(ValueError,match='hash'): load_spatial_map(p,first['id'],version=version)


def test_conditional_interaction_zone_and_authored_points():
    d=sample(); d['actor']={'width':1,'height':1,'anchor':[0,0]}
    zone=d['layers'][2]; zone['when']='visible'
    assert candidate_points(d,zone='treasure')==[]
    assert candidate_points(d,zone='treasure',conditions={'visible':False})==[]
    assert [1,1] in candidate_points(d,zone='treasure',limit=100,conditions={'visible':True,'closed':False})
    zone['interaction_points']=[[1,3]]
    with pytest.raises(ValueError,match='inside its zone'): candidate_points(d,zone='treasure',conditions={'visible':True})
