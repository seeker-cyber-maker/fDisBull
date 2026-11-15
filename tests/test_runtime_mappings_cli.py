"""Public registry routing and CLI persistence, using authored source bytes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import METHODS, RUNTIME_MAPPING_WRITES, parser, respond
from fdisbull.project import Project


EVIDENCE = dict(kind='modeled',reference='authored:registry-cli',
                sha256=hashlib.sha256(b'authored registry CLI fixture').hexdigest())


@pytest.fixture
def project_path(tmp_path,monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(tmp_path/'objects'))
    source=tmp_path/'authored.bin';source.write_bytes(bytes.fromhex('b801000000c3'))
    path=tmp_path/'authored.fdb'
    with Project.create(path,source,arch='x86',bits=32,base=0x1000):
        pass
    return path


def definition(tmp_path,name,value):
    path=tmp_path/(name+'.json');path.write_text(json.dumps(value));return path


def request(project,method,**params):
    result=respond(dict(method=method,params=dict(project=str(project),**params)))
    assert result['ok'],result
    return result['result']


def cli(*args):
    environment=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'),
                     PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-m','fdisbull',*map(str,args)],env=environment,
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    response=json.loads(result.stdout);assert response['ok'],response
    return response['result']


def test_fresh_cli_task_map_and_alias_queries_reopen_the_same_registry(project_path,tmp_path):
    start=definition(tmp_path,'start',dict(run='modeled-run',external_id='task-label',evidence=EVIDENCE))
    task=cli('runtime-task-start',project_path,'--definition-file',start)['task']
    catalog=cli('runtime-objects',project_path,'--version',1)
    object_id=next(x['id'] for x in catalog['objects'] if x['id'].startswith('region:'))
    mapping=dict(task=task,object_id=object_id,object_offset=0,length=4,linear_start=0x2000,
                 physical_start=0x9000,selector=dict(value=0x40,base=0x1000,limit=0xffff,bits=32),
                 evidence=EVIDENCE)
    first=cli('runtime-map',project_path,'--definition-file',definition(tmp_path,'first-map',mapping))
    mapping.update(linear_start=0x3000,selector=None)
    second=request(project_path,'runtime-map',**mapping)
    physical=cli('runtime-resolve',project_path,task,'0x9001','--space','physical')
    assert {x['id'] for x in physical['matches']}=={first['binding'],second['binding']}
    assert all(x['object_offset']==1 for x in physical['matches'])
    selected=cli('runtime-resolve',project_path,task,'0x1001','--space','selector','--selector','0x40')
    assert [x['id'] for x in selected['matches']]==[first['binding']]
    assert selected['matches'][0]['linear_address']==0x2001
    assert all('not live authenticated' in x['qualification'] for x in physical['matches'])
    tasks=request(project_path,'runtime-tasks',run='modeled-run',offset=0,limit=1)
    assert tasks['tasks'][0]['id']==task
    page=request(project_path,'runtime-mappings',task=task,offset=0,limit=1)
    assert page['count']==2 and len(page['bindings'])==1 and page['truncated']


def test_write_definition_route_checkpoint_restore_and_end(project_path,tmp_path):
    task=request(project_path,'runtime-task-start',run='modeled-run',external_id='same-label',evidence=EVIDENCE)['task']
    object_id=request(project_path,'runtime-objects')['objects'][0]['id']
    map_file=definition(tmp_path,'map',dict(task=task,object_id=object_id,object_offset=0,length=2,linear_start=0x2000,evidence=EVIDENCE))
    first=request(project_path,'runtime-map',definition_file=str(map_file))
    checkpoint=request(project_path,'runtime-map-checkpoint',definition_file=str(definition(tmp_path,'checkpoint',dict(task=task,evidence=EVIDENCE))))['checkpoint']
    request(project_path,'runtime-unmap',definition_file=str(definition(tmp_path,'unmap',dict(task=task,bindings=[first['binding']],evidence=EVIDENCE))))
    assert request(project_path,'runtime-mappings',task=task)['bindings']==[]
    request(project_path,'runtime-map-restore',definition_file=str(definition(tmp_path,'restore',dict(task=task,checkpoint=checkpoint,evidence=EVIDENCE))))
    restored=request(project_path,'runtime-mappings',task=task)['bindings']
    assert len(restored)==1 and restored[0]['id']!=first['binding'] and restored[0]['restored_from']==first['binding']
    request(project_path,'runtime-task-end',definition_file=str(definition(tmp_path,'end',dict(task=task,evidence=EVIDENCE))))
    assert request(project_path,'runtime-mappings',task=task)['bindings']==[]
    replacement=request(project_path,'runtime-task-start',run='modeled-run',external_id='same-label',evidence=EVIDENCE)['task']
    assert replacement!=task
    events=request(project_path,'runtime-mapping-events',task=task,after=0,limit=2)
    assert len(events['events'])==2 and events['truncated'] and events['next_after']>0


@pytest.mark.parametrize('raw,fragment',[
    ('[]','JSON object'),
    ('{"run":"a","run":"b"}','duplicate'),
    ('{"evidence":{"kind":NaN}}','nonfinite'),
    ('{"project":"other.fdb"}','override project'),
    ('{"definition_file":"other.json"}','override project'),
    ('{','JSON'),
    (' '* (4*1024*1024+1),'4 MiB'),
])
def test_invalid_definition_refuses_before_opening_a_project(tmp_path,raw,fragment):
    path=tmp_path/'definition.json';path.write_text(raw)
    project=tmp_path/'must-not-be-created.fdb'
    reply=respond(dict(method='runtime-task-start',params=dict(project=str(project),definition_file=str(path))))
    assert not reply['ok'] and fragment.lower() in (reply['error']['type']+' '+reply['error']['message']).lower(),reply
    assert not project.exists()


@pytest.mark.parametrize('method,extra',[
    ('runtime-task-start',{'run':'also-supplied'}),
    ('runtime-map-snapshot',{'snapshot':'also-supplied'}),
    ('runtime-mappings',{}),
])
def test_definition_ambiguity_and_query_definition_forms_refuse(tmp_path,method,extra):
    path=definition(tmp_path,'definition',{})
    project=tmp_path/'must-not-be-created.fdb'
    reply=respond(dict(method=method,params=dict(project=str(project),definition_file=str(path),**extra)))
    assert not reply['ok'] and 'cannot be combined' in reply['error']['message']
    assert not project.exists()


def test_snapshot_route_is_local_and_does_not_accept_caller_masks(project_path):
    task=request(project_path,'runtime-task-start',run='modeled-run',external_id='task',evidence=EVIDENCE)['task']
    object_id=request(project_path,'runtime-objects')['objects'][0]['id']
    params=dict(project=str(project_path),task=task,snapshot='foreign-artifact-id',
                object_id=object_id,object_offset=0,length=1)
    reply=respond(dict(method='runtime-map-snapshot',params=params))
    assert not reply['ok'] and 'artifact' in reply['error']['message']
    reply=respond(dict(method='runtime-map-snapshot',params=dict(params,mask_hex='00')))
    assert not reply['ok']
    assert request(project_path,'runtime-mappings',task=task)['bindings']==[]


def test_all_mapping_methods_are_discoverable_and_parse_normal_flags():
    names={'runtime-objects','runtime-tasks','runtime-task-start','runtime-task-end','runtime-map',
           'runtime-map-snapshot','runtime-unmap','runtime-map-checkpoint','runtime-map-restore',
           'runtime-mappings','runtime-resolve','runtime-mapping-events'}
    assert names<=METHODS.keys()
    for name in RUNTIME_MAPPING_WRITES:
        args=parser().parse_args([name,'project.fdb','--definition-file','operation.json'])
        assert args.definition_file=='operation.json'
    args=parser().parse_args(['runtime-resolve','project.fdb','task','0x1234','--space','selector','--selector','0x40','--at','7'])
    assert (args.address,args.selector,args.at)==(0x1234,0x40,7)
    args=parser().parse_args(['runtime-tasks','project.fdb','--run','r','--offset','2','--limit','3'])
    assert (args.run,args.offset,args.limit)==('r',2,3)
