"""Public behavior at persistence, analysis and agent-command boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fdisbull.project import Project, number
from fdisbull.cli import respond

# call 0x100a; test eax,eax; jne 0x100a; ret; mov eax,42; ret; unreachable nops
CODE = bytes.fromhex('e80500000085c07501c3b82a000000c39090')

@pytest.fixture
def project(tmp_path):
    binary = tmp_path/'sample.bin'
    binary.write_bytes(CODE)
    p = Project.create(tmp_path/'sample.fdb',binary,arch='x86',bits=64,base=0x1000)
    yield p
    p.db.close()

def test_recursive_control_flow_does_not_decode_after_return(project):
    result = project.analyze()
    assert result['pending'] == 0
    rows = project.disassembly()['instructions']
    assert [r['address'] for r in rows] == ['0x1000','0x1005','0x1007','0x1009','0x100a','0x100f']
    refs = project.xrefs('0x100a')
    assert {(r['source'],r['kind']) for r in refs} == {('0x1000','call'),('0x1007','branch')}
    assert [f['address'] for f in project.functions()] == ['0x1000','0x100a']
    assert project.analyze()['decoded'] == 0

def test_budget_continues_from_persisted_work_queue(project):
    first = project.analyze(max_instructions=1)
    assert first['decoded']==1 and first['budget_exhausted']
    assert project.status()['work']['pending'] > 0
    assert project.analyze()['pending'] == 0
    assert project.status()['counts']['instructions'] == 6

def test_annotations_survive_reanalysis_and_versioning(project):
    project.analyze()
    project.annotate('0x100a','answer',kind='name',author='TiGa')
    project.annotate('0x100a','Observed constant, meaning unverified',author='TiGa')
    project.analyze(start='0x100a')
    assert project.functions()[1]['name']=='answer'
    child = project.patch('0x100b','2b',label='changed immediate',origin='test patch')
    assert child['version']==2
    assert project.status()['counts']['instructions']==0
    assert project.disassembly(version=1)['instructions'][4]['bytes']=='b82a000000'
    project.analyze()
    row = project.disassembly()['instructions'][4]
    assert row['bytes']=='b82b000000' and row['name']=='answer'
    assert row['comment_author']=='TiGa' and row['comment_inherited_from']==1
    assert project.versions()[0]['sha256'] != project.versions()[1]['sha256']

def test_failed_patch_is_atomic(project):
    before = project.versions()
    with pytest.raises(ValueError,match='entirely'):
        project.patch('0x1011','9090')
    assert project.versions()==before
    with pytest.raises(ValueError,match='invalid patch'):
        project.patch('0x1000','not bytes')
    assert project.versions()==before

def test_unsigned_high_addresses_and_loop_termination(tmp_path):
    binary = tmp_path/'loop.bin'
    binary.write_bytes(bytes.fromhex('ebfe'))
    base = 0xffff800000001000
    with Project.create(tmp_path/'high.fdb',binary,arch='x86',bits=64,base=base) as p:
        assert p.analyze(max_instructions=50)['decoded']==1
        assert p.xrefs(hex(base))[0]['target']==hex(base)
        assert p.functions()[0]['address']==hex(base)

@pytest.mark.parametrize('value',[-1,2**64,True,1.5,{},None])
def test_bad_addresses_rejected(value):
    with pytest.raises((ValueError,TypeError)):
        number(value)

def test_unresolved_indirect_is_visible_and_not_followed(tmp_path):
    binary=tmp_path/'indirect.bin'
    binary.write_bytes(bytes.fromhex('ffe09090'))
    with Project.create(tmp_path/'indirect.fdb',binary,arch='x86',bits=64,base=0x2000) as p:
        assert p.analyze()['decoded']==1
        assert p.issues()[0]['detail']=='unresolved indirect control flow'
        assert p.xrefs('0x2000',direction='from')==[]

def test_original_input_not_required_after_process_restart(tmp_path):
    binary = tmp_path/'restart.bin'
    binary.write_bytes(CODE)
    db = tmp_path/'restart.fdb'
    env = {**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    def cli(*args):
        r=subprocess.run([sys.executable,'-m','fdisbull',*map(str,args)],env=env,capture_output=True,text=True)
        assert r.returncode==0,r.stderr+r.stdout
        return json.loads(r.stdout)['result']
    cli('import',binary,db,'--arch','x86','--base','0x1000')
    cli('analyze',db)
    cli('rename',db,'0x100a','persisted_answer')
    binary.unlink()
    assert cli('functions',db)[1]['name']=='persisted_answer'
    rows=cli('disasm',db)['instructions']
    assert rows[4]['bytes']=='b82a000000'
    out=tmp_path/'restart.svg'
    cli('render',db,out)
    assert 'persisted_answer' in out.read_text()

def test_agent_stream_recovers_from_errors(project):
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
    data='not-json\n'+json.dumps({'id':1,'method':'unknown'})+'\n'+json.dumps({'id':2,'method':'analyze'})+'\n'+json.dumps({'id':3,'method':'status'})+'\n'
    r=subprocess.run([sys.executable,'-m','fdisbull','serve','--project',str(project.path)],input=data,text=True,capture_output=True,env=env)
    assert r.returncode==0,r.stderr
    replies=[json.loads(line) for line in r.stdout.splitlines()]
    assert [x['ok'] for x in replies]==[False,False,True,True]
    assert replies[3]['result']['counts']['instructions']==6
    assert replies[3]['id']==3

def test_existing_project_not_overwritten(project,tmp_path):
    binary=tmp_path/'other.bin'
    binary.write_bytes(b'\xc3')
    with pytest.raises(FileExistsError):
        Project.create(project.path,binary,arch='x86')
    assert project.status()['source_sha256']

def test_out_of_mapping_seed_rejected_without_mutating_queue(project):
    before=project.status()['work']
    with pytest.raises(ValueError,match='executable'):
        project.analyze(start=0x123456)
    assert project.status()['work']==before

def test_render_requires_real_analysis(project,tmp_path):
    response=respond({'id':5,'method':'render','params':{'project':str(project.path),'output':str(tmp_path/'empty.png')}})
    assert not response['ok'] and 'analyze first' in response['error']['message']

@pytest.mark.parametrize('kwargs',[{'version':float('inf')},{'version':True},{'version':1.2}])
def test_malformed_version_gets_error_response(project,kwargs):
    r=respond({'id':6,'method':'status','params':{'project':str(project.path),**kwargs}})
    assert not r['ok']

@pytest.mark.parametrize('suffix',['','.alias','-wal','-shm'])
def test_export_cannot_overwrite_database_or_sidecars(project,tmp_path,suffix):
    project.analyze()
    if suffix=='.alias':
        target=tmp_path/'alias.svg'
        os.link(project.path,target)
    else:
        target=Path(str(project.path)+suffix)
    r=respond({'method':'render','params':{'project':str(project.path),'output':str(target),'format':'svg'}})
    assert not r['ok'] and 'cannot overwrite' in r['error']['message']
    assert project.status()['counts']['instructions']==6

def test_invalid_format_is_structured_error(project,tmp_path):
    r=respond({'method':'render','params':{'project':str(project.path),'output':str(tmp_path/'out.png'),'format':1}})
    assert not r['ok']
