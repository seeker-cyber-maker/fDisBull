"""Immutable renderer checkpoint delta storage against a real project DB."""
from copy import deepcopy
import hashlib
import json
import pytest
from fdisbull.qemu_frame_storage import FORMAT, store, materialize, stored_size, validate_manifest
from fdisbull.qemu_dos_checkpoint import FORMAT as PROCESS_FORMAT
from test_qemu_dos_history import project, session


def captured(session,data):
    return dict(name='frame.qcow2',kind='state',data=data,size=len(data),sha256=hashlib.sha256(data).hexdigest(),
        metadata=dict(format=PROCESS_FORMAT,host_files_restored=False,
                      source_sha256=session.metadata['source_sha256'],version_sha256=session.metadata['version_sha256']))


@pytest.fixture
def state(session):
    session._artifact = lambda *args:session.project._debug_artifact(session.run_id,*args)
    m = dict(format=FORMAT,history_kind='renderer-frames',id='history',identity={},revision=0,
        parent_manifest=None,pending=None,nodes=[],max_steps=10,
        max_bytes=1024*1024,head=None,cursor=None,frame_config=dict(storage_mode='delta',
            keyframe_interval=3,max_frames=10,max_captures=10,max_bytes=1024*1024,period_ns=16666667,
            max_state_bytes=128*1024,max_image_bytes=1024))
    return session,m


def add(state,node_id,data,parent=None):
    session,m=state
    cp=store(session,m,node_id,parent,captured(session,data))
    frame=dict(kind='renderer-update' if parent else 'initial-paused',completed_guest_frame=None,
        image=dict(artifact='png',sha256='0'*64,size=20))
    if parent: frame.update(width=2,height=1,update_id=1,published_ns=1,pixel_sha256='0'*64)
    node=dict(id=node_id,parent=parent['id'] if parent else None,checkpoint=cp,edge={},frame=frame)
    m['nodes'].append(node);m['head']=m['cursor']=node_id
    return node


def test_full_delta_keyframes_branch_and_exact_materialization(state):
    session,m=state
    data=b'a'*65536
    root=add(state,'root',data)
    child=add(state,'child',data[:-1]+b'b',root)
    grand=add(state,'grand',data[:-1]+b'c',child)
    key=add(state,'key',data[:-1]+b'd',grand)
    branch=add(state,'branch',data[:-1]+b'e',root)
    assert [n['checkpoint']['storage']['kind'] for n in (root,child,grand,key,branch)] == ['full','delta','delta','full','delta']
    assert [n['checkpoint']['storage']['depth'] for n in (root,child,grand,key,branch)] == [0,1,2,0,1]
    assert materialize(session,m,grand)['data']==data[:-1]+b'c'
    assert materialize(session,m,branch)['data']==data[:-1]+b'e'
    assert stored_size(child['checkpoint']) < len(data)
    assert validate_manifest(m) <= m['max_bytes']


@pytest.mark.parametrize('kind',['payload','metadata','base','depth','wrong-version'])
def test_corruption_fails_before_reconstruction(state,kind):
    session,m=state; root=add(state,'root',b'a'*65536); child=add(state,'child',b'a'*65535+b'b',root)
    cp=child['checkpoint']
    if kind == 'payload':
        with session.project.transaction(True): session.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'corrupt',cp['artifact']))
    elif kind == 'metadata':
        with session.project.transaction(True): session.project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',(json.dumps({'wrong':1}),cp['artifact']))
    elif kind == 'base': cp['storage']['descriptor']['base_point']='elsewhere'
    elif kind == 'depth': cp['storage']['depth']=2
    else: session.version = dict(session.version,id='different-version')
    before=session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    with pytest.raises(ValueError): materialize(session,m,child)
    assert session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before


def test_incompressible_falls_back_to_full_and_budget_is_bounded(state):
    import random
    rng=random.Random(8)
    root=add(state,'root',rng.randbytes(65536))
    child=add(state,'child',rng.randbytes(65536),root)
    assert child['checkpoint']['storage']['kind']=='full'
    state[1]['max_bytes']=state[1]['frame_config']['max_bytes']=1
    with pytest.raises(ValueError,match='budget'): validate_manifest(state[1])


def test_identity_and_chain_checks_before_any_artifact(state):
    session,m=state; root=add(state,'root',b'a'*65536)
    before=session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    wrong=deepcopy(root);wrong['id']='not-owned'
    with pytest.raises(ValueError): store(session,m,'child',wrong,captured(session,b'b'*65536))
    assert session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before


def test_codec_deadline_prevents_storage_and_reconstruction(state):
    session,m=state; root=add(state,'root',b'a'*65536)
    count=session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    def expired(): raise TimeoutError('outer deadline expired')
    session._history_remaining_ms = expired
    with pytest.raises(TimeoutError): materialize(session,m,root)
    with pytest.raises(TimeoutError): store(session,m,'child',root,captured(session,b'b'*65536))
    assert session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == count


def test_references_are_bound_to_history_and_raw_metadata(state):
    session,m=state;root=add(state,'root',b'a'*65536); child=add(state,'child',b'a'*65535+b'b',root)
    changed=deepcopy(m); changed['id']='other-history'
    with pytest.raises(ValueError,match='binding'):
        materialize(session,changed,changed['nodes'][1])
    saved = session.metadata['source_sha256']
    session.metadata['source_sha256']='f'*64
    with pytest.raises(ValueError,match='source'):
        materialize(session,m,child)
    session.metadata['source_sha256']=saved


def test_selected_checkpoint_and_image_reserve_are_admitted_before_publication(state):
    import random
    session,m=state
    rng=random.Random(19)
    root=add(state,'root',rng.randbytes(65536))
    next_state=captured(session,rng.randbytes(65536))
    used=validate_manifest(m)
    metadata_size=len(json.dumps(next_state['metadata'],sort_keys=True,separators=(',',':')).encode())
    reserve=37
    required=used+next_state['size']+metadata_size+reserve
    m['max_bytes']=m['frame_config']['max_bytes']=required-1
    before=session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    with pytest.raises(ValueError,match='retained byte budget'):
        store(session,m,'child',root,next_state,reserve_bytes=reserve)
    assert session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before
    m['max_bytes']=m['frame_config']['max_bytes']=required
    result=store(session,m,'child',root,next_state,reserve_bytes=reserve)
    assert result['storage']['kind']=='full' and stored_size(result)==next_state['size']+metadata_size
    assert session.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before+1
