"""Deterministic linking of authored metadata; no native execution claims."""
from copy import deepcopy

import pytest

from fdisbull.common_uil import digest
from fdisbull.uil_catalog import build_catalog
from fdisbull.uil_link import (make_requirement, make_module, make_provider,
    resolve_modules, describe_components, resolve_native_link,
    validate_native_link, native_arithmetic, native_operation_arithmetic)


def requirement(name='core.add', version=1, **kwargs):
    return make_requirement(name, version, inputs=[{'type':'u16'}]*2,
                            outputs=[{'type':'u16'}], **kwargs)


def fixture():
    f={'variables':[{'type':'u16'}], 'constants':[{'type':'u16'}],
       'inputs':[0], 'outputs':[0], 'max_steps':100,
       'body':[{'op':'set','dst':0,'value':{'op':'add','type':'u16',
                                        'args':[{'var':0},{'const':0}]}}]}
    c=build_catalog([{'language':'common','function':deepcopy(f),'constants':['1'],
                      'origin_language':'rust'}])
    group=c['groups'][0]
    p={'format':'fdisbull-common-uil-1','capabilities':['core.scalar@1','core.calls@1'],
       'imports':[{'semantic_id':group['semantic_id'],'inputs':[{'type':'u16'}],
                   'outputs':[{'type':'u16'}],'effects':[]}],
       'functions':[f], 'entry':0}
    b={'format':'fdisbull-uil-presentation-1','program_sha256':digest(p),
       'functions':[{'constants':['1'],'initial':['0']}],'resources':[]}
    o={'format':'fdisbull-uil-orchestration-1','program_sha256':digest(p),
       'bindings':[{'import':0,'implementation':group['implementations'][0]['id']}],
       'ownership':'copy-in-copy-out','max_call_depth':32}
    return p,b,c,o


def test_generic_exact_selection_ignores_language_labels_and_input_order():
    r=requirement(); m=make_module('sum',[r])
    p=make_provider('typed-provider',[r],target='linux-x64',metadata={'language':'fortran'})
    a=resolve_modules([m],[p],target='linux-x64')
    assert a==resolve_modules([m],[p],target='linux-x64')
    assert a['bindings'][0]['provider']==p['id']
    assert a['sha256']


def test_ambiguity_requires_exact_pin_and_unsupported_pins_refuse():
    r=requirement(); m=make_module('sum',[r])
    a=make_provider('a',[r],target='linux-x64'); b=make_provider('b',[r],target='linux-x64')
    with pytest.raises(ValueError,match='ambiguous'):resolve_modules([m],[a,b],target='linux-x64')
    pins={m['id']:{r['id']:b['id']}}
    lock=resolve_modules([m],[a,b],target='linux-x64',pins=pins)
    assert lock['bindings'][0]['provider']==b['id']
    assert lock==resolve_modules([m],[b,a],target='linux-x64',pins=pins)
    with pytest.raises(ValueError,match='pin'):resolve_modules([m],[a,b],target='linux-x64',pins={'module:'+'0'*64:{r['id']:b['id']}})
    with pytest.raises(ValueError,match='pin'):resolve_modules([m],[a,b],target='linux-x64',pins={m['id']:{r['id']:'provider:'+'0'*64}})


@pytest.mark.parametrize('difference', ['target','abi','ownership','profile','version','type'])
def test_hard_contract_mismatches_never_choose_a_nearby_provider(difference):
    r=requirement(); changed=deepcopy(r)
    kwargs={}
    if difference=='target':kwargs['target']='windows-x64'
    elif difference=='type':changed=make_requirement('core.add',1,inputs=[{'type':'u8'}]*2,outputs=[{'type':'u8'}])
    else:
        settings={'abi':'another-abi','ownership':'borrowed','profile':'another-profile','version':2}
        changed=make_requirement('core.add', settings['version'] if difference=='version' else 1,
            inputs=[{'type':'u16'}]*2,outputs=[{'type':'u16'}],
            **({difference:settings[difference]} if difference!='version' else {}))
    p=make_provider('incompatible',[changed],target=kwargs.get('target','linux-x64'))
    with pytest.raises(ValueError,match='missing|incompatible'):
        resolve_modules([make_module('sum',[r])],[p],target='linux-x64')


def test_stale_ids_versions_and_dependency_cycles_refuse():
    r=requirement(); m=make_module('sum',[r]); p=make_provider('a',[r],target='linux-x64')
    broken=deepcopy(p);broken['name']='tampered'
    with pytest.raises(ValueError,match='identity'):resolve_modules([m],[broken],target='linux-x64')
    r2=requirement(version=2)
    with pytest.raises(ValueError,match='version'):resolve_modules([make_module('sum',[r,r2])],[p],target='linux-x64')
    ra=requirement('a');rb=requirement('b')
    pa=make_provider('a',[ra],target='linux-x64',requires=[rb])
    pb=make_provider('b',[rb],target='linux-x64',requires=[ra])
    with pytest.raises(ValueError,match='cycle'):resolve_modules([make_module('entry',[ra])],[pa,pb],target='linux-x64')


def test_cascade_exposes_actual_child_contracts_without_executing_metadata():
    show=requirement('show.image');decode=requirement('image.decode');blit=requirement('image.blit');atomic=requirement('atomic.copy')
    root=make_module('show',[show])
    top=make_provider('show-provider',[show],target='linux-x64',requires=[decode,blit])
    d=make_provider('decoder',[decode],target='linux-x64')
    b=make_provider('blitter',[blit],target='linux-x64',requires=[atomic])
    atom=make_provider('atomic',[atomic],target='linux-x64')
    choices=describe_components([root],[top,d,b,atom],target='linux-x64')
    assert choices['format']=='fdisbull-udc-component-choices-1'
    assert {n['id'] for n in choices['nodes']}=={root['id'],top['id'],d['id'],b['id'],atom['id']}
    assert {x['provider'] for x in resolve_modules([root],[top,d,b,atom],target='linux-x64')['bindings']}=={top['id'],d['id'],b['id'],atom['id']}
    assert choices['execution_authorized'] is False


@pytest.mark.parametrize('target',['macos-arm64','linux-x64','windows-x64'])
def test_native_lock_preserves_documents_binds_target_and_exact_math(target):
    docs=fixture(); before=deepcopy(docs)
    portable=resolve_native_link(*docs,target)
    assembly=resolve_native_link(*docs,target,arithmetic='native-asm')
    assert docs==before
    assert portable['closure']==assembly['closure']
    assert portable['sha256']!=assembly['sha256']
    assert validate_native_link(portable) is True
    assert native_arithmetic(portable,'functions',0)=='portable-c'
    assert native_arithmetic(assembly,'imports',0)=='native-asm'
    assert native_operation_arithmetic(assembly,'functions',0,'add')=='native-asm'


def test_per_operation_children_do_not_change_parent_common_contract():
    docs=fixture()
    base=resolve_native_link(*docs,'linux-x64')
    choices={'functions':{'0':{'components':{'add':'native-asm','mul':'portable-c'}}}}
    mixed=resolve_native_link(*docs,'linux-x64',module_requirements=choices)
    assert base['closure']==mixed['closure']
    assert native_arithmetic(mixed,'functions',0)=='portable-c'
    assert native_operation_arithmetic(mixed,'functions',0,'add')=='native-asm'
    assert native_operation_arithmetic(mixed,'functions',0,'mul')=='portable-c'
    assert native_operation_arithmetic(mixed,'imports',0,'add')=='portable-c'


def test_sound_version_two_unknown_modules_unused_choices_and_tampering_refuse():
    docs=fixture()
    extra={'functions':{'0':{'requires':[{'intrinsic':'sound.play','version':2}]}}}
    with pytest.raises(ValueError,match='missing|version'):resolve_native_link(*docs,'linux-x64',module_requirements=extra)
    with pytest.raises(ValueError):resolve_native_link(*docs,'linux-x64',module_requirements={'functions':{'99':{}}})
    with pytest.raises(ValueError):resolve_native_link(*docs,'linux-x64',module_requirements={'functions':{'0':{'components':{'divide':'native-asm'}}}})
    lock=resolve_native_link(*docs,'linux-x64')
    lock['modules']['functions']['0']['arithmetic']='native-asm'
    with pytest.raises(ValueError):native_arithmetic(lock,'functions',0)


def test_transitive_ambiguity_can_be_pinned_and_unreachable_pins_refuse():
    parent=requirement('parent');child=requirement('child')
    module=make_module('root',[parent])
    p=make_provider('parent',[parent],target='linux-x64',requires=[child])
    a=make_provider('child-a',[child],target='linux-x64')
    b=make_provider('child-b',[child],target='linux-x64')
    description=describe_components([module],[p,a,b],target='linux-x64')
    assert description['resolution']['status']=='unresolved'
    assert 'ambiguous' in description['resolution']['reason']
    lock=resolve_modules([module],[p,a,b],target='linux-x64',pins={p['id']:{child['id']:a['id']}})
    assert {x['id'] for x in lock['providers']}=={p['id'],a['id']}
    unreachable=make_provider('unreachable',[requirement('unused')],target='linux-x64',requires=[child])
    with pytest.raises(ValueError,match='unused'):
        resolve_modules([module],[p,a,b,unreachable],target='linux-x64',
                        pins={p['id']:{child['id']:a['id']},unreachable['id']:{child['id']:a['id']}})


def test_describe_cycle_is_finite_and_deep_dependencies_refuse_with_a_bound():
    a=requirement('a');b=requirement('b');m=make_module('root',[a])
    pa=make_provider('a',[a],target='linux-x64',requires=[b])
    pb=make_provider('b',[b],target='linux-x64',requires=[a])
    description=describe_components([m],[pa,pb],target='linux-x64')
    assert description['cycles'] and description['resolution']['status']=='unresolved'
    assert len(description['nodes'])==3
    requirements=[requirement('chain.'+str(i)) for i in range(70)]
    providers=[make_provider('p.'+str(i),[r],target='linux-x64',
        requires=[requirements[i+1]] if i+1<len(requirements) else []) for i,r in enumerate(requirements)]
    module=make_module('chain',[requirements[0]])
    with pytest.raises(ValueError,match='depth'):
        resolve_modules([module],providers,target='linux-x64')
    assert describe_components([module],providers,target='linux-x64')['depth_limited_nodes']


@pytest.mark.parametrize('changed',['target','provider','operation','edge','module','closure','extra'])
def test_rehashed_native_lock_cannot_hide_inconsistent_resolution(changed):
    lock=resolve_native_link(*fixture(),'linux-x64')
    if changed=='target':lock['target']='windows-x64'
    elif changed=='provider':lock['builtin_provider_ids'][0]='provider:'+'0'*64
    elif changed=='operation':lock['modules']['functions']['0']['components']['add']='native-asm'
    elif changed=='edge':
        lock['resolution']['bindings'][0]['provider']='provider:'+'0'*64
        lock['resolution']['sha256']=digest({k:v for k,v in lock['resolution'].items() if k!='sha256'})
    elif changed=='module':lock['modules']['functions'].pop('0')
    elif changed=='closure':lock['closure']['program_sha256']='not-a-hash'
    else:lock['unknown']=True
    lock['sha256']=digest({k:v for k,v in lock.items() if k!='sha256'})
    with pytest.raises(ValueError):validate_native_link(lock)


def test_effect_ownership_and_raw_metadata_are_hard_requirements():
    r=requirement(effects=['sound.play'])
    without_effect=requirement()
    with pytest.raises(ValueError,match='missing'):
        resolve_modules([make_module('root',[r])],[make_provider('p',[without_effect],target='linux-x64')],target='linux-x64')
    with pytest.raises(ValueError):make_module('bad',[r],metadata={'code_hex':'90'})
    with pytest.raises(ValueError):make_requirement('core.add',True)


def test_source_language_does_not_change_native_intrinsic_choices():
    p,b,c,o=fixture()
    a=resolve_native_link(p,b,c,o,'linux-x64')
    impl=c['groups'][0]['implementations'][0]
    from fdisbull.uil_catalog import implementation_id
    impl['language']='cobol';impl['id']=implementation_id(impl)
    o['bindings'][0]['implementation']=impl['id']
    changed=resolve_native_link(p,b,c,o,'linux-x64')
    assert a['builtin_provider_ids']==changed['builtin_provider_ids']
    assert a['closure']['program_sha256']==changed['closure']['program_sha256']
    assert native_operation_arithmetic(changed,'imports',0,'add')=='portable-c'


def test_selected_import_has_its_own_component_choices_and_exact_pin_checks():
    docs=fixture();impl=docs[2]['groups'][0]['implementations'][0]['id']
    options={'implementations':{impl:{'arithmetic':'native-asm','components':{'add':'portable-c'}}}}
    lock=resolve_native_link(*docs,'windows-x64',module_requirements=options)
    assert native_arithmetic(lock,'imports',0)=='native-asm'
    assert native_operation_arithmetic(lock,'imports',0,'add')=='portable-c'
    assert native_operation_arithmetic(lock,'imports',0,'mul')=='native-asm'
    assert native_operation_arithmetic(lock,'functions',0,'add')=='portable-c'
    assert validate_native_link(lock)
    bad={'functions':{'0':{'pins':{'requirement:'+'0'*64:'provider:'+'0'*64}}}}
    with pytest.raises(ValueError,match='pin'):resolve_native_link(*docs,'linux-x64',module_requirements=bad)


def test_duplicate_identity_unbounded_graph_and_unknown_target_refuse():
    r=requirement();m=make_module('a',[r]);p=make_provider('p',[r],target='linux-x64')
    with pytest.raises(ValueError,match='duplicate'):resolve_modules([m,m],[p],target='linux-x64')
    with pytest.raises(ValueError,match='target'):resolve_modules([m],[p],target='linux')
    with pytest.raises(ValueError):make_module('raw',[r],metadata={'payload':[1,2,3]})
    with pytest.raises(ValueError,match='budget'):resolve_modules([m]*1025,[],target='linux-x64')


def test_array_intrinsics_bind_element_length_and_index_type():
    p,b,c,o=fixture()
    f=p['functions'][0]
    f['variables']=[{'type':'u32-array','length':2},{'type':'u32'}]
    f['constants']=[{'type':'u32'}];f['inputs']=[0];f['outputs']=[0]
    f['body']=[{'op':'set','dst':1,'value':{'op':'load','array':0,'index':{'const':0}}},
               {'op':'store','array':0,'index':{'const':0},'value':{'var':1}}]
    p['capabilities'].append('core.array@1');b['program_sha256']=digest(p)
    b['functions']=[{'constants':['1'],'initial':[[0,0],'0']}];o['program_sha256']=digest(p)
    lock=resolve_native_link(p,b,c,o,'macos-arm64')
    module=next(m for m in lock['resolution']['modules'] if m['metadata']['kind']=='functions')
    reqs={r['intrinsic']:r for r in module['requires']}
    assert reqs['core.load']['inputs']==[{'type':'u32-array','length':2},{'type':'u32'}]
    assert reqs['core.load']['outputs']==[{'type':'u32'}]
    assert reqs['core.store']['outputs']==[{'type':'u32-array','length':2}]
    assert validate_native_link(lock)
