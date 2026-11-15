"""Public source-bound CHIP-8 G2 maps on authored, locally pinned ROMs."""
import hashlib
import json
import sqlite3
import pytest
from fdisbull.cli import main,respond,public_addresses
from fdisbull.project import Project
from test_chip8_intake_public import authored,_intake

ENV='env:chip8-qemu-v6:1'


def _program(f):
    # CALL 208; conditional skip at 202; both paths jump 20a; 208 returns.
    raw=bytes.fromhex('2208 3001 120a 120a 00ee 120a')
    f['source'].write_bytes(raw);f['bytes']=raw
    f['entry'].update(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
        git_blob_sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest())
    f['path'].write_text(json.dumps(f['manifest'],sort_keys=True));f['pin']=hashlib.sha256(f['path'].read_bytes()).hexdigest()
    return raw


def _setup(f,tmp_path):
    raw=_program(f);path=tmp_path/'mapped.fdb';g0=_intake(f,path)
    reply=respond({'method':'chip8-closure-resolve','params':{'project':str(path),'environment':ENV}})
    assert reply['ok'],reply
    return path,g0,reply['result']['closure'],raw


def _schema(path):
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        return db.execute('select type,name,sql from sqlite_master order by type,name').fetchall()


def _build(path,closure,**kw):
    return respond({'method':'chip8-source-map','params':{'project':str(path),'closure':closure,**kw}})


def test_source_map_cli_json_project_cold_parity_and_no_redecode(authored,tmp_path,monkeypatch,capsys):
    import fdisbull.chip8_source_map as module
    path,g0,closure,raw=_setup(authored,tmp_path)
    reply=_build(path,closure,max_instructions=32,max_states=64,max_call_depth=4,
                 expected_intake_sha256=g0['intake_sha256'])
    assert reply['ok'],reply
    built=reply['result'];assert built['format']=='fdisbull-chip8-source-map-1'
    assert built['mapping'].startswith('chip8-map:') and built['source']['intake_sha256']==g0['intake_sha256']
    assert built['source']['closure']==closure
    def no_decode(*args,**kwargs):raise AssertionError('cached map must not decode')
    monkeypatch.setattr(module,'decode',no_decode)
    with Project(path) as project:
        cold=project.chip8_source_map_info(built['mapping'],expected_intake_sha256=g0['intake_sha256'])
        again=project.chip8_source_map(closure,max_instructions=32,max_states=64,max_call_depth=4,
                                       expected_intake_sha256=g0['intake_sha256'])
        assert cold==again and public_addresses(cold)==built and public_addresses(again)==built
    assert main(['chip8-source-map',str(path),closure,'--max-instructions','32','--max-states','64',
                 '--max-call-depth','4','--expected-intake-sha256',g0['intake_sha256']])==0
    cli=json.loads(capsys.readouterr().out);assert cli['ok'] and cli['result']==built
    info=respond({'method':'chip8-source-map-info','params':{'project':str(path),'mapping':built['mapping'],
        'expected_intake_sha256':g0['intake_sha256']}})
    assert info['ok'] and info['result']==built,info
    assert main(['chip8-source-map-info',str(path),built['mapping'],'--expected-intake-sha256',g0['intake_sha256']])==0
    cli=json.loads(capsys.readouterr().out);assert cli['ok'] and cli['result']==built
    assert authored['source'].read_bytes()==raw


@pytest.mark.parametrize('kwargs',[
    {'max_instructions':0},{'max_states':0},{'max_call_depth':-1},
    {'max_instructions':True},{'expected_intake_sha256':'0'*64},
])
def test_invalid_map_request_refuses_without_new_tables_or_objects(authored,tmp_path,kwargs):
    path,_,closure,_=_setup(authored,tmp_path);before=_schema(path)
    objects=sorted(p.name for p in authored['store'].iterdir())
    result=_build(path,closure,**kwargs)
    assert not result['ok'],result
    assert _schema(path)==before and sorted(p.name for p in authored['store'].iterdir())==objects


def test_unknown_closure_refuses_without_catalog_writes(authored,tmp_path):
    path,_,_,_=_setup(authored,tmp_path);before=_schema(path)
    objects=sorted(p.name for p in authored['store'].iterdir())
    result=_build(path,'closure:'+'0'*64)
    assert not result['ok'] and _schema(path)==before
    assert sorted(p.name for p in authored['store'].iterdir())==objects


def test_budget_frontier_is_retained_and_larger_walk_is_new_mapping(authored,tmp_path,monkeypatch):
    path,_,closure,_=_setup(authored,tmp_path)
    def no_analysis(*args,**kwargs):raise AssertionError('source map must not invoke Project.analyze')
    monkeypatch.setattr(Project,'analyze',no_analysis)
    with Project(path) as project:
        before=project.db.execute('select count(*) from instructions').fetchone()[0]
        small=project.chip8_source_map(closure,max_instructions=1,max_states=64,max_call_depth=4)
        assert small['frontiers'] and len(small['instructions'])==1
        larger=project.chip8_source_map(closure,max_instructions=32,max_states=64,max_call_depth=4)
        assert larger['mapping']!=small['mapping'] and len(larger['instructions'])>1
        assert project.chip8_source_map_info(small['mapping'])==small
        assert project.db.execute('select count(*) from instructions').fetchone()[0]==before


def test_hand_derived_call_return_skip_words_spans_and_ports(authored,tmp_path):
    path,_,closure,raw=_setup(authored,tmp_path)
    with Project(path) as project:
        result=project.chip8_source_map(closure,max_instructions=32,max_states=64,max_call_depth=4)
    expected={0x200:'2208',0x202:'3001',0x204:'120a',0x206:'120a',0x208:'00ee',0x20a:'120a'}
    rows={item['pc']:item for item in result['instructions']}
    assert {pc:item['word_hex'] for pc,item in rows.items()}==expected
    for pc,word in expected.items():
        part=raw[pc-0x200:pc-0x200+2]
        assert rows[pc]['span']=={'offset':pc-0x200,'length':2,'sha256':hashlib.sha256(part).hexdigest()}
        assert rows[pc]['decoded']['bytes']==word and rows[pc]['udl']['qualification']=='static-candidate'
    call=rows[0x200]['udl'];ret=rows[0x208]['udl'];skip=rows[0x202]['udl']
    assert call['control']['flow']=='call' and {'sp','stack'}<={p['name'] for p in call['writes']}
    assert ret['control']['flow']=='return' and {'sp','stack'}<={p['name'] for p in ret['reads']}
    assert skip['control']['flow']=='conditional' and {'pc','v0'}<={p['name'] for p in skip['reads']}
    states={s['id']:s for s in result['states']}
    def links(pc,stack):
        sid=next(s['id'] for s in states.values() if s['pc']==pc and s['return_stack']==stack)
        return {(e['kind'],states[e['target']]['pc'],tuple(states[e['target']]['return_stack']))
                for e in result['edges'] if e['source']==sid and e['target'] is not None}
    assert ('call',0x208,(0x202,)) in links(0x200,[])
    assert ('return',0x202,()) in links(0x208,[0x202])
    assert {('not_taken',0x204,()),('taken',0x206,())}<=links(0x202,[])
    assert result['coverage']['worklist_exhausted'] and not result['coverage']['budget_exhausted']
    assert not result['unclassified_spans'] and not result['frontiers']
