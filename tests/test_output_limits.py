"""Output retention must not change execution or manufacture complete evidence."""
import json
import pytest

from fdisbull.output_artifacts import OutputArtifactStore
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.interaction_il import execute_il


def program():
    return {'format':'fdisbull-il-1','role':'uil',
            'variables':{'$money':{'type':'u16','initial':0}},
            'resources':{'message':{'kind':'text','text':'X'*4000}},
            'body':[{'id':'award','op':'add','var':'$money','value':200}]+
                   [{'id':f'text{i}','op':'text','resource':'message'} for i in range(40)]}


def test_large_result_retains_the_complete_original_with_execution_scope(tmp_path):
    store=OutputArtifactStore(tmp_path/'outputs');policy=OutputPolicy(4096,store=store)
    original=execute_il(program())
    result=policy.bound(original)
    assert result['format']=='fdisbull-output-ref-1' and not result['complete']
    assert result['status']=='artifact_required' and result['execution']['complete'] is True
    assert result['execution']['status']=='complete' and result['retry_safe'] is False
    ident=result['artifact']['id']
    assert store.select(ident,'/state')['value']=={'$money':200}
    assert store.select(ident,'/events/39/resource_data/text')['value']=='X'*4000
    assert store.select(ident,'')['complete'] is False
    assert store.select(ident,'')['reason']=='selection_too_large'
    assert json.loads(store._read_verified(ident))==original
    assert len(policy.render(result).encode())+1<=4096 and not policy.delivery_failed
    assert OutputArtifactStore(tmp_path/'outputs').info(ident)==result['artifact']


def test_small_values_and_exact_wire_byte_boundary_are_unchanged(tmp_path):
    policy=OutputPolicy(4096,artifact_dir=tmp_path/'not-created')
    value={'text':'x'*(4096-len('{"text":""}')-1)}
    assert len(policy.render(value).encode())+1==4096
    assert policy.bound(value) is value and not (tmp_path/'not-created').exists()
    larger={'text':value['text']+'x'}
    assert policy.bound(larger)['status']=='artifact_required'
    # Count actual escaped wire bytes, not the shorter Unicode input encoding.
    assert policy.bound({'text':'\u263a'*700})['status']=='artifact_required'


def test_storage_failure_and_serialization_failure_never_claim_rollback(tmp_path):
    unsafe=tmp_path/'repo';unsafe.mkdir();(unsafe/'.git').mkdir()
    policy=OutputPolicy(4096,artifact_dir=unsafe/'outputs')
    result=policy.bound({'complete':True,'status':'complete','state':{'committed':True},'text':'X'*10000})
    assert result['status']=='output_unavailable' and result['artifact'] is None
    assert result['execution']['complete'] is True and result['retry_safe'] is False
    assert result['total_bytes'] is None and policy.delivery_failed
    assert result['reason']=='inside_git'
    bad=OutputPolicy(4096).bound({'complete':False,'value':float('nan')})
    assert bad['status']=='output_unavailable' and bad['reason']=='serialization_failed'
    assert bad['execution']['complete'] is False


def test_large_failed_rpc_retains_error_without_promoting_it(tmp_path):
    policy=OutputPolicy(4096,artifact_dir=tmp_path/'outputs')
    original={'id':'failed','ok':False,'error':{'type':'ObservedError','message':'X'*20000}}
    result=policy.bound(original)
    assert result['id']=='failed' and result['ok'] is False
    assert result['output']['execution']['ok'] is False
    assert result['output']['execution']['complete'] is None
    ident=result['output']['artifact']['id']
    assert policy.store().select(ident,'/error/message',max_bytes=10)['complete'] is False
    assert policy.store().select(ident,'/error/type')['value']=='ObservedError'
    assert len(policy.render(result))+1<=4096


def test_unknown_execution_fields_are_not_invented_or_partially_labeled(tmp_path):
    policy=OutputPolicy(4096,artifact_dir=tmp_path/'outputs')
    result=policy.bound({'status':'a'*100,'events':['X'*10000]})
    assert result['execution']=={'returned':True,'ok':None,'complete':None,'status':None}
    assert policy.store().select(result['artifact']['id'],'/status')['value']=='a'*100


def test_real_mutation_is_not_repeated_when_delivery_fails(tmp_path):
    from fdisbull.project import Project
    from fdisbull.cli import respond
    binary=tmp_path/'GAME.COM';original=bytes.fromhex('b8004ccd21')+b'\x90'*4091;binary.write_bytes(original)
    project=tmp_path/'private.fdb'
    with Project.create(project,binary,image='com'):pass
    unsafe=tmp_path/'repo';unsafe.mkdir();(unsafe/'.git').mkdir()
    request={'id':'once','method':'patch','params':{'project':str(project),'address':'1000:0100','data':'90'*3000}}
    with output_policy_context(OutputPolicy(4096,artifact_dir=unsafe/'outputs')):
        result=respond(request)
    assert result['ok'] is True and result['result']['status']=='output_unavailable'
    with Project(project) as p:
        assert p.db.execute('SELECT COUNT(*) FROM versions').fetchone()[0]==2
        assert p.regions(1)[0].data==original
        assert p.regions(2)[0].data[:3000]==b'\x90'*3000
    assert binary.read_bytes()==original


def test_oversized_request_identity_is_rejected_before_mutation(tmp_path):
    from fdisbull.project import Project
    from fdisbull.cli import respond
    binary=tmp_path/'GAME.COM';binary.write_bytes(bytes.fromhex('b8004ccd21'))
    project=tmp_path/'private.fdb'
    with Project.create(project,binary,image='com'):pass
    request={'id':'X'*10000,'method':'comment','params':{'project':str(project),'address':'1000:0100','text':'not committed'}}
    result=respond(request)
    assert not result['ok'] and result['id'] is None
    with Project(project) as p:assert p.db.execute('SELECT COUNT(*) FROM annotations').fetchone()[0]==0


@pytest.mark.parametrize('value',[True,4095,1048577,'65536'])
def test_invalid_policy_limits_are_refused(value):
    with pytest.raises(ValueError):OutputPolicy(value)
