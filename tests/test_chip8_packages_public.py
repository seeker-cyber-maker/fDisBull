"""Public G1 CHIP-8 closure routing and refusal before publication."""
import json
import sqlite3
import pytest
from fdisbull.cli import main,respond
from fdisbull.project import Project
from test_chip8_intake_public import authored,_intake

ENV='env:chip8-qemu-v6:1'
ISA='isa:chip8-classic-qemu-v6:1'


def _schema(path):
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        return db.execute("select type,name,sql from sqlite_master order by type,name").fetchall()


def _resolve(path,**kwargs):
    return respond({'method':'chip8-closure-resolve','params':{'project':str(path),**kwargs}})


def test_public_package_catalog_cli_json_parity(capsys):
    from fdisbull.chip8_packages import catalog
    reply=respond({'method':'chip8-packages','params':{}})
    assert reply['ok'] and reply['result']==catalog(),reply
    assert main(['chip8-packages'])==0
    cli=json.loads(capsys.readouterr().out)
    assert cli['ok'] and cli['result']==reply['result']


def test_environment_is_mandatory_and_bad_environment_refuses_without_ddl(authored,tmp_path):
    path=tmp_path/'source.fdb';_intake(authored,path)
    before=_schema(path);objects=sorted(p.name for p in authored['store'].iterdir())
    for args in ({},{'environment':'env:missing:999'},{'environment':None}):
        reply=_resolve(path,**args)
        assert not reply['ok'],reply
        assert _schema(path)==before and sorted(p.name for p in authored['store'].iterdir())==objects


def test_project_method_rejects_bad_intake_pin_before_ddl(authored,tmp_path):
    path=tmp_path/'pin.fdb';_intake(authored,path);before=_schema(path)
    with Project(path) as project:
        with pytest.raises(ValueError):project.chip8_closure_resolve(environment=ENV,expected_intake_sha256='0'*64)
    assert _schema(path)==before


def test_cold_same_rom_and_second_rom_reuse_only_package_definitions(authored,tmp_path):
    import hashlib
    doc=authored['manifest'];raw2=bytes.fromhex('6002 1200')+b'\x7f'
    second=dict(doc['programs'][0],key='second',title='Second authored target',size=len(raw2),
        sha256=hashlib.sha256(raw2).hexdigest(),git_blob_sha=hashlib.sha1(b'blob '+str(len(raw2)).encode()+b'\0'+raw2).hexdigest())
    doc['programs'].append(second);authored['path'].write_text(json.dumps(doc,sort_keys=True))
    authored['pin']=hashlib.sha256(authored['path'].read_bytes()).hexdigest()
    alias=tmp_path/'alias.ch8';alias.write_bytes(authored['bytes'])
    target2=tmp_path/'second.ch8';target2.write_bytes(raw2)
    p1=tmp_path/'one.fdb';pa=tmp_path/'alias.fdb';p2=tmp_path/'second.fdb'
    _intake(authored,p1);_intake(authored,pa,alias)
    receipt=respond({'method':'chip8-intake','params':{'project':str(p2),'path':str(target2),
        'manifest_path':str(authored['path']),'manifest_sha256':authored['pin'],'member':'second'}})
    assert receipt['ok'],receipt
    first=_resolve(p1,environment=ENV);again=_resolve(pa,environment=ENV);other=_resolve(p2,environment=ENV)
    assert first['ok'] and again['ok'] and other['ok'],(first,again,other)
    a,b,c=first['result'],again['result'],other['result']
    assert a['format']=='fdisbull-chip8-closure-1' and a['closure']==b['closure']
    assert a['source']==b['source'] and a['source']!=c['source'] and a['closure']!=c['closure']
    assert a['packages']==b['packages']==c['packages']
    assert a['packages']['architecture']['id']==ISA and a['packages']['environment']['id']==ENV
    with Project(p1) as project:
        cold=project.chip8_closure_info(a['closure'])
        assert cold==a and project.chip8_closure_resolve(environment=ENV)==a
    assert authored['source'].read_bytes()==alias.read_bytes()==authored['bytes'] and target2.read_bytes()==raw2


def test_public_json_cli_resolve_and_info_match(authored,tmp_path,capsys):
    path=tmp_path/'cli.fdb';g0=_intake(authored,path)
    reply=_resolve(path,environment=ENV,expected_intake_sha256=g0['intake_sha256'])
    assert reply['ok'],reply
    resolved=reply['result'];assert resolved['runtime'] is None and resolved['analysis'] is None
    assert main(['chip8-closure-resolve',str(path),'--environment',ENV,
                 '--expected-intake-sha256',g0['intake_sha256']])==0
    out=json.loads(capsys.readouterr().out);assert out['ok'] and out['result']==resolved
    result=respond({'method':'chip8-closure-info','params':{'project':str(path),'closure':resolved['closure'],
        'expected_intake_sha256':g0['intake_sha256']}})
    assert result['ok'] and result['result']==resolved,result
    assert main(['chip8-closure-info',str(path),resolved['closure'],'--expected-intake-sha256',g0['intake_sha256']])==0
    out=json.loads(capsys.readouterr().out);assert out['ok'] and out['result']==resolved
    bad=respond({'method':'chip8-closure-info','params':{'project':str(path),'closure':resolved['closure'],
        'expected_intake_sha256':'0'*64}})
    assert not bad['ok']


@pytest.mark.parametrize('kwargs',[
    {'requirements':{'architecture':{'profile':'other-profile'}}},
    {'requirements':{'environment':{'unknown-capability':True}}},
    {'pins':{}},
    {'pins':{ISA:'0'*64,ENV:'f'*64}},
    {'runtime':{'profile':'incomplete'}},
    {'include_analysis':'yes'},
])
def test_bad_capabilities_pins_and_runtime_refuse_without_catalog_publication(authored,tmp_path,kwargs):
    path=tmp_path/'bad.fdb';_intake(authored,path)
    before=_schema(path);objects=sorted(p.name for p in authored['store'].iterdir())
    reply=_resolve(path,environment=ENV,**kwargs)
    assert not reply['ok'],reply
    assert _schema(path)==before and sorted(p.name for p in authored['store'].iterdir())==objects


def test_explicit_runtime_and_existing_analysis_are_bounded_and_unverified(authored,tmp_path,monkeypatch,capsys):
    from fdisbull.chip8_packages import catalog
    path=tmp_path/'optional.fdb';g0=_intake(authored,path)
    packages={item['id']:item for item in catalog()['packages']}
    pins={ISA:packages[ISA]['sha256'],ENV:packages[ENV]['sha256']}
    requirements={'architecture':{'profile':packages[ISA]['contract']['profile']},
                  'environment':{'profile':packages[ENV]['contract']['profile']}}
    runtime={'profile':'chip8-classic-pilot-default-v1','cpu_subset':'fdisbull-chip8-frame-keys-6',
      'env_model':'fdisbull-chip8-display-keypad-timers-rng-layers-frames-keys-5','machine':'chip8-test',
      'memory':4096,'qemu_sha256':'a'*64,'qemu_version':'declared test version','checkpoint_tool_sha256':None}
    def no_analysis(*args,**kwargs):raise AssertionError('closure must not run analysis')
    monkeypatch.setattr(Project,'analyze',no_analysis)
    result=_resolve(path,environment=ENV,pins=pins,requirements=requirements,runtime=runtime,include_analysis=True,
                    expected_intake_sha256=g0['intake_sha256'])
    assert result['ok'],result
    closure=result['result']
    assert closure['runtime']['verification']=='caller-declared-unverified' and closure['runtime']['declaration']==runtime
    assert closure['analysis']['source_sha256']==authored['entry']['sha256']
    assert set(closure['analysis']['tables'])=={'instructions','functions','xrefs','work','analysis_state'}
    assert main(['chip8-closure-resolve',str(path),'--environment',ENV,'--pins',json.dumps(pins),
                 '--requirements',json.dumps(requirements),'--runtime',json.dumps(runtime),'--include-analysis',
                 '--expected-intake-sha256',g0['intake_sha256']])==0
    cli=json.loads(capsys.readouterr().out);assert cli['ok'] and cli['result']==closure
