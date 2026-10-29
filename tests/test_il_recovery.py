import json
from copy import deepcopy
import pytest

from fdisbull.il_recovery import recover_v3_attributes, save_il, load_il
from fdisbull.interaction_il import change_role, execute_il
from fdisbull.project import Project


def source():
    return b'\x03' + bytes(63) + bytes.fromhex('4b860b4b8603')


def recovered():
    return recover_v3_attributes(source(),[64,67],source_file='story',object_variable=134,
                                 bindings={11:'$opened',3:'$seen'})


def test_source_facts_lower_to_same_udl_and_uil_blocks():
    doc=recovered()
    assert doc['body'][0]['value'] is True
    assert doc['evidence']['source-40']['range']==[64,67]
    assert execute_il(doc)==execute_il(change_role(doc,'uil'))
    assert execute_il(doc)['state']=={'$opened':True,'$seen':True}
    wrong=bytearray(source());wrong[64]=0x4a
    with pytest.raises(ValueError):
        recover_v3_attributes(bytes(wrong),[64],source_file='story',object_variable=134,bindings={11:'$opened'})
    with pytest.raises(ValueError):
        recover_v3_attributes(source(),[64],source_file='story',object_variable=133,bindings={11:'$opened'})


def test_restart_immutable_revisions_and_checked_source(tmp_path):
    binary=tmp_path/'TEST.COM';binary.write_bytes(b'\xb8\x00\x4c\xcd\x21')
    story=tmp_path/'story';story.write_bytes(source());db=tmp_path/'private.fdb'
    with Project.create(db,binary,image='com') as p:
        p.attach_file(story,name='story')
        first=save_il(p,'action',recovered())
        second=save_il(p,'action',change_role(recovered(),'uil'),parent=first['id'])
        with pytest.raises(ValueError,match='parent'):save_il(p,'action',recovered(),parent=first['id'])
    with Project(db) as p:
        assert load_il(p,first['id'])['document']['role']=='udl'
        assert load_il(p,second['id'])['document']['role']=='uil'
        assert first['id']!=second['id']
        bad=deepcopy(recovered());bad['evidence']['source-40']['bytes']='00'
        with pytest.raises(ValueError,match='evidence'):save_il(p,'bad',bad)
        p.db.execute('UPDATE external_files SET data=? WHERE name=?',(b'corrupted','story'));p.db.commit()
        with pytest.raises(ValueError,match='hash'):load_il(p,first['id'])


def test_qualification_is_explicit_and_refuses_other_state():
    doc=recovered()
    doc['body'].insert(0,{'id':'qualify','op':'require','condition':{'op':'eq','left':{'var':'$opened'},'right':False}})
    assert execute_il(doc)['complete']
    state={'$opened':True,'$seen':True}
    result=execute_il(doc,state)
    assert result['status']=='refused' and result['state']==state and result['events']==[]
