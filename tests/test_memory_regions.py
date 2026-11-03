"""Persistent source-region identity and explicit behavior-variant admission."""
from copy import deepcopy

import pytest

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull import udc_memory_regions as regions
from fdisbull.udc_memory_layers import validate_contract as exact_memory_contract


def binary(op,left,right):
    return {'op':op,'left':left,'right':right}


def model():
    value=binary('and',binary('add',binary('mul',{'load':0},5),1),255)
    return {'format':'fdisbull-memory-uil-1','role':'uil','memory':{'words':16},'variables':{},
        'functions':{'update':{'max_steps':20,'body':[{'id':'update.seed','op':'store','index':0,'value':value}]}}}


def descriptor():
    return {'name':'rng','source':{'function':'update','entry':'update.seed','count':1},
        'reads':[0],'output':{'index':0,'min':0,'max':255}}


def contract(program=None):
    program=program or model();arena={'arena':{'type':'u32-array','words':16}}
    return {'format':'fdisbull-block-contract-1','name':'word-update-region','inputs':arena,'outputs':arena,
        'behavior':{'kind':'memory-region','program':program,'region':descriptor()},'effects':[]}


def implementation(program,alternate=False):
    body=deepcopy(program['functions']['update']['body']);body[0].pop('id')
    if alternate:body[0]['value']=binary('and',binary('xor',{'load':0},255),255)
    return {'format':'fdisbull-memory-uil-1','role':'uil','memory':{'words':16},'variables':{},
        'functions':{'rng':{'max_steps':1,'body':body}}}


def layer(contract_id,target='wasm32-memory-1',alternate=False):
    return {'format':'fdisbull-udl-layer-1','name':('alternate' if alternate else 'original')+'.'+target,
        'contract':contract_id,'assurance':'intentional-behavior-variant' if alternate else 'exact-source-region',
        'implementation':{'backend':'memory-region','target':target,'program':implementation(model(),alternate),'function':'rng'}}


def at(tmp_path):
    source=tmp_path/'authored.com';source.write_bytes(bytes.fromhex('b8004ccd21'))
    return Project.create(tmp_path/'regions.fdb',source,image='com')


def fixtures(project):
    cid=regions.register_contract(project,contract())['id'];selections={}
    for variant,alternate in [('original',False),('alternate',True)]:
        selections[variant]={}
        for backend,target in zip(('wasm','webgpu'),regions.TARGETS):
            ident=regions.register_layer(project,layer(cid,target,alternate))['id']
            selections[variant][backend]=regions.select_layers(project,variant+'.'+backend,{'rng':ident},
                program=model(),target=target)['id']
    document={'format':regions.FORMAT,'module_uil_sha256':digest(model()),'allow_behavior_variants':True,
        'slots':{'rng':{'label':'Word generator','default':'original','variants':{
            name:{'label':name,'selections':value} for name,value in selections.items()}}}}
    return document,selections


def test_regions_reopen_with_truthful_source_and_realization_identities(tmp_path):
    canonical=model();before=deepcopy(canonical)
    with at(tmp_path) as project:
        document,selections=fixtures(project)
        result=regions.prepare_regions(project,canonical,document)
    with Project(tmp_path/'regions.fdb') as project:
        assert project.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        reopened=regions.prepare_regions(project,canonical,document)
        assert reopened==result
        for variant in selections:
            implementation_program,target,identities=regions.resolve(project,selections[variant]['wasm'],'rng')
            assert target=='wasm32-memory-1'
            assert identities['module_uil_sha256']==digest(canonical)
            assert identities['implementation_uil_sha256']==digest(implementation_program)
            assert identities['implementation_uil_sha256']!=digest(canonical)
            assert identities['assurance']==('exact-source-region' if variant=='original' else 'intentional-behavior-variant')
    assert canonical==before==model()
    assert result['module_uil_sha256']==digest(canonical)
    assert result['execution_uil_sha256']==digest(result['execution_program'])!=digest(canonical)
    assert set(result['execution_program']['functions'])=={'update','rng'}
    assert result['execution_program']['functions']['update']==canonical['functions']['update']
    helper=result['execution_program']['functions']['rng']
    assert helper['max_steps']==1 and 'id' not in helper['body'][0]


def test_region_profile_does_not_widen_exact_memory_contracts(tmp_path):
    with pytest.raises(ValueError):exact_memory_contract(contract())
    wrong=contract();wrong['behavior']={'kind':'memory-uil','program':model(),'function':'update'}
    with pytest.raises(ValueError):regions.validate_contract(wrong)


def test_constant_word_update_can_declare_an_empty_read_footprint():
    value=contract()
    value['behavior']['program']['functions']['update']['body'][0]['value']=7
    value['behavior']['region']['reads']=[]
    assert regions.validate_contract(value)==value


@pytest.mark.parametrize('mutate',[
    lambda c:c.update(domain={}),
    lambda c:c['behavior'].update(unrealized_adapter=True),
    lambda c:c['behavior']['region']['source'].update(count=2),
    lambda c:c['behavior']['region']['source'].update(entry='missing'),
    lambda c:c['behavior']['region'].update(name='update'),
    lambda c:c['behavior']['region'].update(reads=[1]),
    lambda c:c['behavior']['region'].update(reads=[0,0]),
    lambda c:c['behavior']['region'].update(reads=[16]),
    lambda c:c['behavior']['region']['output'].update(index=1),
    lambda c:c['behavior']['region']['output'].update(max=-1),
    lambda c:c['behavior']['region']['output'].update(min=256),
    lambda c:c['behavior']['program']['functions']['update']['body'][0].update(index={'load':0}),
    lambda c:c['behavior']['program']['functions']['update']['body'][0].update(value={'load':{'load':0}}),
])
def test_contract_rejects_unrealized_or_broad_source_boundary(mutate):
    value=contract();mutate(value)
    with pytest.raises(ValueError):regions.validate_contract(value)


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(adapter={}),
    lambda d:d.update(assurance='equivalent'),
    lambda d:d.update(assurance={}),
    lambda d:d.update(assurance='intentional-behavior-variant'),
    lambda d:d['implementation'].update(backend='memory-uil'),
    lambda d:d['implementation'].update(function='update'),
    lambda d:d['implementation'].update(program=model()),
    lambda d:d['implementation']['program']['memory'].update(words=17),
    lambda d:d['implementation']['program']['variables'].update({'$x':{'type':'u32','initial':0}}),
    lambda d:d['implementation']['program']['functions']['rng'].update(max_steps=2),
    lambda d:d['implementation']['program']['functions']['rng']['body'].append({'op':'store','index':0,'value':0}),
    lambda d:d['implementation']['program']['functions']['rng']['body'][0].update(index=1),
    lambda d:d['implementation']['program']['functions']['rng']['body'][0].update(value={'load':1}),
])
def test_layer_rejects_false_assurance_or_broader_implementation(tmp_path,mutate):
    with at(tmp_path) as project:
        cid=regions.register_contract(project,contract())['id'];value=layer(cid);mutate(value)
        with pytest.raises(ValueError):regions.register_layer(project,value)


def test_alternative_cannot_claim_exact_source(tmp_path):
    with at(tmp_path) as project:
        cid=regions.register_contract(project,contract())['id'];value=layer(cid,alternate=True)
        value['assurance']='exact-source-region'
        with pytest.raises(ValueError):regions.register_layer(project,value)


@pytest.mark.parametrize('mutate',[
    lambda d:d.update(ignored=True),
    lambda d:d.update(allow_behavior_variants=False),
    lambda d:d.update(allow_behavior_variants=1),
    lambda d:d.update(module_uil_sha256='0'*64),
    lambda d:d['slots']['rng'].update(default='alternate'),
    lambda d:d['slots']['rng'].update(default='missing'),
    lambda d:d['slots']['rng'].update(ignored=True),
    lambda d:d['slots']['rng']['variants']['original']['selections'].update(wasm='missing'),
    lambda d:d['slots']['rng']['variants']['original'].update(ignored=True),
    lambda d:d['slots']['rng']['variants']['original'].update(label=''),
    lambda d:d['slots']['rng']['variants']['original']['selections'].pop('webgpu'),
])
def test_plan_requires_explicit_policy_and_exact_default(tmp_path,mutate):
    with at(tmp_path) as project:
        document,_=fixtures(project);mutate(document)
        with pytest.raises((ValueError,KeyError)):regions.prepare_regions(project,model(),document)


def test_exact_only_plan_needs_no_behavior_variant_permission(tmp_path):
    with at(tmp_path) as project:
        document,_=fixtures(project)
        document['allow_behavior_variants']=False;document['slots']['rng']['variants'].pop('alternate')
        assert regions.prepare_regions(project,model(),document)['slots']['rng']['default']=='original'


def test_resolve_revalidates_unknown_fields_in_generic_immutable_records(tmp_path):
    with at(tmp_path) as project:
        document,selections=fixtures(project)
        selected=project.udl_selection_info(selections['original']['wasm'],full=True)['document']
        stored_layer=project.udl_layer_info(selected['bindings']['rng'],full=True)['document']
        stored_layer['adapter']={'ignored':True}
        bypass=project.store_udl_layer(stored_layer)['id']
        bad=project.store_udl_selection({**selected,'name':'bypass','bindings':{'rng':bypass}})['id']
        with pytest.raises(ValueError):regions.resolve(project,bad,'rng')
        unknown=project.store_udl_selection({**selected,'name':'unknown','unrealized':True})['id']
        with pytest.raises(ValueError):regions.resolve(project,unknown,'rng')


def test_plan_refuses_backend_or_source_descriptor_mismatch(tmp_path):
    with at(tmp_path) as project:
        document,selections=fixtures(project)
        document['slots']['rng']['variants']['original']['selections']['webgpu']=selections['original']['wasm']
        with pytest.raises(ValueError):regions.prepare_regions(project,model(),document)
        document,_=fixtures(project)
        changed=contract();changed['behavior']['region']['output']['max']=254
        cid=regions.register_contract(project,changed)['id']
        alternate_layer=regions.register_layer(project,layer(cid,'webgpu-wgsl-memory-1',True))['id']
        selected=regions.select_layers(project,'different-output-domain',{'rng':alternate_layer},
            program=model(),target='webgpu-wgsl-memory-1')['id']
        document['slots']['rng']['variants']['alternate']['selections']['webgpu']=selected
        with pytest.raises(ValueError):regions.prepare_regions(project,model(),document)
