"""G1 package identity, source binding and static-cache contracts."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import pytest

from fdisbull.chip8_intake import create_intake
from fdisbull.chip8_packages import catalog,resolve,info,ISA_ID,ENV_ID,_validate_graph
from fdisbull.project import Project
from test_chip8_intake import inputs,_blob


def _tables(project):
    return [row['name'] for row in project.db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'chip8_package_%' ORDER BY name")]


def _make(inputs):
    root,rom,data,doc,manifest,put=inputs
    other=b'\x60\x02\x12\x00';path=root/'other.ch8';path.write_bytes(other)
    doc['programs'].append({'key':'other','title':'Other','author':'Tester','platform':'chip8',
        'git_blob_sha':_blob(other),'size':len(other),'sha256':hashlib.sha256(other).hexdigest()})
    pin=put();alias=root/'alias.ch8';alias.write_bytes(data)
    return root,rom,alias,path,pin,manifest,data


def _open(stack,root,rom,pin,manifest,name,member='authored'):
    return stack.enter_context(create_intake(root/name,rom,manifest_path=manifest,manifest_sha256=pin,member=member))


def test_catalog_and_cross_project_cold_reuse_without_analysis(inputs,monkeypatch):
    import fdisbull.chip8 as chip8
    root,rom,alias,other,pin,manifest,data=_make(inputs)
    monkeypatch.setattr(chip8,'decode',lambda *a,**k:pytest.fail('resolver must not decode'))
    monkeypatch.setattr(Project,'analyze',lambda *a,**k:pytest.fail('resolver must not analyze'))
    catalog1=catalog();assert [x['id'] for x in catalog1['packages']]==[ISA_ID,ENV_ID]
    with ExitStack() as stack:
        a=_open(stack,root,rom,pin,manifest,'a.fdb');b=_open(stack,root,alias,pin,manifest,'b.fdb');c=_open(stack,root,other,pin,manifest,'c.fdb','other')
        x=resolve(a,environment=ENV_ID);y=resolve(b,environment=ENV_ID);z=resolve(c,environment=ENV_ID)
        assert x['closure']==y['closure'] and x['packages']==z['packages'] and x['closure']!=z['closure']
        assert x['runtime'] is None and x['analysis'] is None and data.hex() not in json.dumps(x)
        assert info(a,x['closure'])==x and resolve(a,environment=ENV_ID)==x
    with Project(root/'a.fdb') as reopened:
        assert info(reopened,x['closure'])==x
    assert catalog()==catalog1


@pytest.mark.parametrize('requirements',[
    {'architecture':{'quirks':{'shift_source':'vx'}}},
    {'architecture':{'quirks':{'logic_vf':'preserve'}}},
    {'architecture':{'quirks':{'load_store_i':'preserve'}}},
    {'architecture':{'faults':{'memory_bytes':8192}}},
    {'environment':{'clock':{'timer_hz':50}}},
    {'environment':{'rng':{'model':'python-random'}}},
    {'environment':{'keypad':{'range_max':16}}},
    {'environment':{'display':{'sprite_edges':'wrap'}}},
    {'environment':{'audio':{'waveform':True}}},
    {'environment':{'missing':'unknown'}},
    {'architecture':{'registers':{'v_bits':True}}},
])
def test_incompatible_requirements_refuse_before_schema(inputs,requirements):
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'bad.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        with pytest.raises(ValueError,match='requirement'):resolve(project,environment=ENV_ID,requirements=requirements)
        assert _tables(project)==[]


def test_explicit_environment_pins_runtime_and_transactions(inputs):
    root,rom,data,doc,manifest,put=inputs;pin=put();packages=catalog()['packages'];pins={p['id']:p['sha256'] for p in packages}
    runtime=dict(profile='chip8-classic-pilot-default-v1',cpu_subset='fdisbull-chip8-frame-keys-6',
        env_model='fdisbull-chip8-display-keypad-timers-rng-layers-frames-keys-5',machine='chip8-test',memory=4096,
        qemu_sha256='a'*64,qemu_version='QEMU emulator version 10.0.13',checkpoint_tool_sha256=None)
    with create_intake(root/'runtime.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        for kw in ({'environment':'chip8'},{'environment':ENV_ID,'pins':{}},
                   {'environment':ENV_ID,'pins':pins|{'extra':'0'*64}},
                   {'environment':ENV_ID,'runtime':runtime|{'memory':8192}},
                   {'environment':ENV_ID,'runtime':runtime|{'path':'/private/qemu'}},
                   {'environment':ENV_ID,'include_analysis':1}):
            with pytest.raises(ValueError):resolve(project,**kw)
            assert _tables(project)==[]
        with project.transaction(True):
            with pytest.raises(ValueError,match='transaction'):resolve(project,environment=ENV_ID)
        result=resolve(project,environment=ENV_ID,pins=pins,runtime=runtime,
                       requirements={'architecture':{'quirks':{'shift_source':'vy'}}})
        assert result['runtime']=={'declaration':runtime,'verification':'caller-declared-unverified'}
        assert info(project,result['closure'])==result


def test_tamper_definition_closure_and_source_refuse(inputs):
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'tamper.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        result=resolve(project,environment=ENV_ID)
        with project.transaction(True):project.db.execute('UPDATE chip8_package_definitions SET document=? WHERE id=?',('{}',ISA_ID))
        with pytest.raises(ValueError,match='differs'):info(project,result['closure'])
        with pytest.raises(ValueError,match='differs'):resolve(project,environment=ENV_ID)
    with create_intake(root/'tamper2.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        result=resolve(project,environment=ENV_ID)
        with project.transaction(True):project.db.execute('UPDATE chip8_package_closures SET document=? WHERE id=?',('{}',result['closure']))
        with pytest.raises(ValueError,match='hash'):info(project,result['closure'])
    with create_intake(root/'tamper3.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        result=resolve(project,environment=ENV_ID)
        (root/'objects'/hashlib.sha256(data).hexdigest()).write_bytes(b'wrong')
        with pytest.raises(ValueError,match='object|identity'):info(project,result['closure'])


def test_existing_analysis_is_hashed_without_running_and_becomes_stale(inputs,monkeypatch):
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'analysis.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        monkeypatch.setattr(project,'analyze',lambda *a,**k:pytest.fail('unexpected analysis'))
        result=resolve(project,environment=ENV_ID,include_analysis=True)
        assert result['analysis']['tables']['instructions']['count']==0
        assert info(project,result['closure'])==result
        with project.transaction(True):project.db.execute("UPDATE work SET detail='changed' WHERE version=1")
        with pytest.raises(ValueError,match='stale'):info(project,result['closure'])
        assert project.db.execute('SELECT count(*) FROM chip8_package_closures').fetchone()[0]==1


def test_invalid_graph_and_absent_info_are_readonly(inputs):
    for graph in ([{'id':'a','kind':'x','depends_on':['missing']}]*3,
                  [{'id':'a','kind':'x','depends_on':['b']},{'id':'b','kind':'x','depends_on':['a']},{'id':'c','kind':'x','depends_on':[]}]):
        with pytest.raises(ValueError):_validate_graph(graph)
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'empty.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        with pytest.raises(ValueError,match='unavailable'):info(project,'closure:'+'0'*64)
        assert _tables(project)==[]


def test_changed_source_during_preflight_refuses_without_schema(inputs,monkeypatch):
    import fdisbull.chip8_packages as packages
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'race.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        original=packages._source_guard;calls=[]
        def changed(*args):
            actual=original(*args);calls.append(actual)
            return actual if len(calls)==1 else '0'*64
        monkeypatch.setattr(packages,'_source_guard',changed)
        with pytest.raises(ValueError,match='source changed'):resolve(project,environment=ENV_ID)
        assert _tables(project)==[]


def test_package_change_before_commit_rolls_back_definitions_and_closure(inputs,monkeypatch):
    import fdisbull.chip8_packages as packages
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'rollback.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        original=packages._definitions;calls=[]
        def changing():
            value=original();calls.append(1)
            if len(calls)>=3:value['architecture']['evidence']['status']='changed'
            return value
        monkeypatch.setattr(packages,'_definitions',changing)
        with pytest.raises(ValueError,match='changed'):resolve(project,environment=ENV_ID)
        assert _tables(project)==[] and not project.db.in_transaction


def test_missing_or_invalid_cached_instruction_bytes_refuse_before_storage(inputs):
    root,rom,data,doc,manifest,put=inputs;pin=put()
    with create_intake(root/'missing-instruction.fdb',rom,manifest_path=manifest,manifest_sha256=pin,member='authored') as project:
        with project.transaction(True):
            project.db.execute("INSERT INTO instructions VALUES (?,?,?,?,?,?,?,?,?)",(1,'chip8:16:big','0000000000000200',2,'','ld','v0,1','next',None))
        with pytest.raises(ValueError,match='instruction bytes'):resolve(project,environment=ENV_ID,include_analysis=True)
        assert _tables(project)==[]
