"""Host-only persistent frame-delta lifecycle using actual project artifacts."""
import hashlib
import json
import pytest
from test_qemu_dos_frames import frames
from test_qemu_dos_history import project, session
from fdisbull.qemu_dos_checkpoint import FORMAT as CHECKPOINT_FORMAT


@pytest.fixture
def delta_frames(frames,monkeypatch):
    captures=[]
    def capture(owner,name,max_bytes):
        data=b'A'*4095+bytes([len(captures)])
        captures.append(data)
        return dict(name=name,kind='state',data=data,size=len(data),sha256=hashlib.sha256(data).hexdigest(),
            metadata=dict(format=CHECKPOINT_FORMAT,host_files_restored=False,
                source_sha256=owner.metadata['source_sha256'],version_sha256=owner.metadata['version_sha256']))
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint.capture_process_state',capture)
    frames.authored_captures=captures
    return frames


def begin(frames,**kwargs):
    return frames.timeline_start(storage_mode='delta',keyframe_interval=3,max_frames=5,
        max_bytes=65536,max_state_bytes=8192,max_image_bytes=1024,**kwargs)


def count(frames,kind):
    return frames.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',(kind,)).fetchone()[0]


def test_delta_lifecycle_exact_pin_no_hidden_full_states(delta_frames):
    frames=delta_frames
    root=begin(frames)
    result=frames.timeline_advance(frames=2)
    assert root['storage_mode']=='delta' and result['full_state_points']==1 and result['delta_state_points']==2
    assert count(frames,'state')==1 and count(frames,'qemu-frame-state-delta')==2
    assert result['retained_encoded_state_payload_bytes'] < result['reconstructed_state_payload_bytes']
    pin=frames.timeline_pin()
    row=frames.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(pin['artifact'],)).fetchone()
    assert bytes(row['data']) == frames.authored_captures[-1]
    assert frames.timeline_image()['artifact']==result['nodes'][-1]['frame']['image']['artifact']


@pytest.mark.parametrize('which',['parent-delta','parent-png'])
def test_corrupt_parent_blocks_advance_before_intent_or_execution(delta_frames,which):
    frames=delta_frames;begin(frames);result=frames.timeline_advance()
    node=result['nodes'][-1]
    artifact=node['checkpoint']['artifact'] if which=='parent-delta' else node['frame']['image']['artifact']
    with frames.project.transaction(True):
        frames.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',artifact))
    before=(count(frames,'rewind-history'),len(frames.vm.qmp.calls),len(frames.authored_captures))
    with pytest.raises(ValueError): frames.timeline_advance()
    assert (count(frames,'rewind-history'),len(frames.vm.qmp.calls),len(frames.authored_captures)) == before
    assert not frames.closed


def test_budget_refusal_precedes_frame_execution(delta_frames):
    frames=delta_frames
    begin(frames)
    manifest=frames._frame_manifest()
    manifest['frame_config']['max_bytes']=frames._frame_bytes_used(manifest)+10
    before=(len(frames.vm.qmp.calls),len(frames.authored_captures))
    with pytest.raises(ValueError,match='reserve'):
        frames._frame_budget(manifest,manifest['nodes'][0])
    assert (len(frames.vm.qmp.calls),len(frames.authored_captures)) == before and not frames.closed


def test_nonordinary_stop_leaves_no_delta_or_new_node(delta_frames):
    frames=delta_frames;root=begin(frames);frames.ordinary=False
    result=frames.timeline_advance(frames=2)
    assert result['outcome']=='interrupted' and result['retained_nodes']==1 and not result['valid']
    assert count(frames,'state')==1 and count(frames,'qemu-frame-state-delta')==0
    assert len(frames.authored_captures)==1 and root['cursor'] is not None


def test_hash_valid_manifest_with_conflicting_limits_refuses_before_guest(delta_frames):
    frames=delta_frames;root=begin(frames)
    row=frames.project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?',(root['history'],)).fetchone()
    manifest=json.loads(bytes(row['data']))
    manifest['frame_config']['max_bytes'] += 1
    data=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    sha=hashlib.sha256(data).hexdigest()
    metadata=json.loads(row['metadata']);metadata['manifest_sha256']=sha
    with frames.project.transaction(True):
        frames.project.db.execute('UPDATE debug_artifacts SET data=?,sha256=?,metadata=? WHERE id=?',
                                  (data,sha,json.dumps(metadata),root['history']))
    before=(count(frames,'rewind-history'),len(frames.vm.qmp.calls),len(frames.authored_captures))
    with pytest.raises(ValueError,match='configuration'):
        frames.timeline_advance()
    assert (count(frames,'rewind-history'),len(frames.vm.qmp.calls),len(frames.authored_captures)) == before
    assert not frames.closed
