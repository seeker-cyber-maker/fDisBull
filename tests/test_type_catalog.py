"""Portable declarations retain provenance without copying target bindings."""
import copy
import json

import pytest

from fdisbull.project import Project


def project(tmp_path, name, base=0x1000):
    binary=tmp_path/(name+'.bin');binary.write_bytes(b'\xc3'+bytes(255))
    return Project.create(tmp_path/(name+'.fdb'),binary,arch='x86',bits=16,base=base)


def declared(p):
    p.define_type('Record',{'kind':'struct','size':8,'fields':[]},author='original analyst')
    p.define_type('RecordPointer',{'kind':'pointer','size':4,'target':'Record'},author='original analyst')
    p.define_type('Record',{'kind':'struct','size':8,'fields':[
        {'name':'amount','offset':0,'type':'u16'},
        {'name':'next','offset':2,'type':'RecordPointer'},
        {'name':'flags','offset':6,'type':'u16'}]},author='original analyst')
    p.define_type('Records',{'kind':'array','element':'Record','count':2},author='array analyst')


def catalog(tmp_path):
    with project(tmp_path,'source') as p:
        declared(p)
        return p.export_types()


def test_real_project_roundtrip_preserves_declarations_authors_but_no_bindings(tmp_path):
    with project(tmp_path,'source') as p:
        declared(p);p.apply_type(0x1040,'Records',name='source_ledger');p.annotate(0x1040,'private_source_name',kind='name')
        attached=tmp_path/'attached.bin';attached.write_bytes(bytes(32));p.attach_file(attached,name='source_attachment');p.apply_file_type('source_attachment','Record')
        before=p.regions(1)[0].data;export=p.export_types()
        assert export['format']=='fdisbull-types-1'
        assert set(export)=={'format','source','types'}
        assert str(tmp_path) not in json.dumps(export)
        assert [x['name'] for x in export['types']]==['Record','RecordPointer','Records']
        assert export['source']['source_sha256']==p.meta['source_sha256']
        assert p.regions(1)[0].data==before
    with project(tmp_path,'destination',0x2000) as p:
        before=p.regions(1)[0].data;receipt=p.import_types(export,author='destination reviewer')
        assert receipt['imported']==3 and receipt['skipped']==0 and receipt['bindings_imported']==0
        assert not p.types()['bindings'] and p.status()['counts']['annotations']==0
        assert p.external_files()['total']==0
        assert p.regions(1)[0].data==before
        assert p.import_types(export)['skipped']==3
        p.apply_type(0x2040,'Records',name='destination_ledger')
        assert p.typed_data(0x2040)['items'][0]['path']=='destination_ledger[0].amount'
    with Project(tmp_path/'destination.fdb') as p:
        again=p.export_types();row=again['types'][0]
        assert row['author']=='original analyst'
        assert row['origin']['source']==export['source']
        assert row['origin']['imported_by']=='destination reviewer'
        assert row['origin']['status']=='imported_interpretation'


def test_empty_catalog_is_a_coherent_noop(tmp_path):
    with project(tmp_path,'empty') as p:
        c=p.export_types();assert c['types']==[]
        before=p.db.total_changes;r=p.import_types(c)
        assert r['imported']==r['skipped']==0 and p.db.total_changes==before


def test_out_of_order_dependencies_and_recursive_pointer_are_validated_together(tmp_path):
    c=catalog(tmp_path);c['types'].reverse()
    with project(tmp_path,'destination') as p:
        assert p.import_types(c)['imported']==3
        assert next(x['layout'] for x in p.types()['types'] if x['layout']['name']=='Record')['size']==8


@pytest.mark.parametrize('change',[
    lambda c:c.update(bindings=[{'address':'0x1234'}]),
    lambda c:c['types'][0].update(native_effects={'writes':'0x1234'}),
    lambda c:c['source'].update(project='/private/machine/path'),
    lambda c:c['types'][0]['origin'].update(runtime_verified=True),
    lambda c:c['types'].append(copy.deepcopy(c['types'][0])),
    lambda c:c['types'][0].update(name='u16'),
    lambda c:c['types'][0]['definition'].update(fields=[{'name':'bad','offset':0,'type':'Missing'}]),
    lambda c:c['types'][0]['definition'].update(fields=[{'name':'self','offset':0,'type':'Record'}]),
    lambda c:c['types'][0]['definition'].update(bytes='deadbeef'),
    lambda c:c['types'][0].update(author=''),
    lambda c:c['source'].update(version=True),
    lambda c:c['types'][0]['origin'].update(status={}),
    lambda c:c['types'][0]['origin']['source'].update(source_sha256='unknown'),
])
def test_bad_or_conflicting_catalog_is_atomic(tmp_path,change):
    c=catalog(tmp_path);change(c)
    with project(tmp_path,'destination') as p:
        p.define_type('Existing',{'kind':'scalar','size':2})
        before=p.export_types();changes=p.db.total_changes
        with pytest.raises(ValueError):p.import_types(c)
        assert p.export_types()==before and p.db.total_changes==changes


def test_conflict_never_overwrites_destination_or_its_authorship(tmp_path):
    c=catalog(tmp_path)
    with project(tmp_path,'destination') as p:
        p.define_type('Record',{'kind':'struct','size':8,'fields':[]},author='destination author')
        before=p.export_types()
        with pytest.raises(ValueError,match='conflict'):p.import_types(c)
        assert p.export_types()==before
    with project(tmp_path,'same') as p:
        # A complete identical graph retains its destination authors on reimport.
        declared(p);p.define_type('Record',c['types'][0]['definition'],author='destination author')
        result=p.import_types(c);assert result['imported']==0 and result['skipped']==3
        assert p.export_types()['types'][0]['author']=='destination author'


@pytest.mark.parametrize('author_only',[False,True])
def test_origin_is_versioned_and_redefinition_does_not_launder_it(tmp_path,author_only):
    c=catalog(tmp_path)
    with project(tmp_path,'destination') as p:
        p.import_types(c,author='reviewer');original=p.export_types(version=1)
        child=p.patch(0x1000,'90')['version']
        assert p.export_types(version=child)['types'][0]['origin']==original['types'][0]['origin']
        definition=copy.deepcopy(c['types'][0]['definition'])
        if not author_only:definition['fields'][0]['name']='new_amount'
        p.define_type('Record',definition,version=child,author='local author')
        row=p.export_types(version=child)['types'][0]
        assert row['origin']['status']=='declared_interpretation'
        assert row['origin']['source']['version']==child and 'imported_by' not in row['origin']
        assert p.export_types(version=1)==original


@pytest.mark.parametrize('author_only',[False,True])
def test_old_writer_cannot_silently_reuse_stale_import_origin(tmp_path,author_only):
    c=catalog(tmp_path)
    with project(tmp_path,'destination') as p:
        p.import_types(c)
        if author_only:p.db.execute("UPDATE type_definitions SET author='old writer' WHERE name='Record'")
        else:
            definition=copy.deepcopy(c['types'][0]['definition']);definition['fields'][0]['name']='changed'
            p.db.execute('UPDATE type_definitions SET document=? WHERE name=?',(json.dumps(definition),'Record'))
        p.db.commit();row=p.export_types()['types'][0]
        assert row['origin']['status']=='changed_local_interpretation'
        assert row['origin']['source']==p.export_types()['source']
        assert 'imported_by' not in row['origin']


def test_fixed_near_segments_are_refused_not_silently_rebased(tmp_path):
    with project(tmp_path,'context_pointer') as p:
        p.define_type('ContextPointer',{'kind':'pointer','size':2,'target':'u8','address_space':'near','segment':0x1234})
        with pytest.raises(ValueError,match='context'):p.export_types()
    c=catalog(tmp_path);c['types'][1]['definition'].update(address_space='near',size=2,segment=0x1234)
    with project(tmp_path,'destination') as p:
        with pytest.raises(ValueError,match='context'):p.import_types(c)
        assert p.export_types()['types']==[]


def test_import_budget_checks_happen_before_any_writes(tmp_path):
    c=catalog(tmp_path)
    with project(tmp_path,'destination') as p:
        too_big=copy.deepcopy(c);too_big['source']['arch']='x'*(4*1024*1024)
        with pytest.raises(ValueError,match='4 MiB'):p.import_types(too_big)
        too_many=copy.deepcopy(c);too_many['types']*=1366
        with pytest.raises(ValueError,match='4096'):p.import_types(too_many)
        too_large=copy.deepcopy(c);too_large['types'][0]['definition']={'kind':'enum','size':4,'members':{('n'+str(i)).ljust(128,'x'):i for i in range(1024)}}
        with pytest.raises(ValueError,match='64 KiB'):p.import_types(too_large)
        assert p.export_types()['types']==[]


def test_reexport_chain_keeps_declared_root_and_last_operator(tmp_path):
    c=catalog(tmp_path)
    with project(tmp_path,'middle',0x2000) as p:
        p.import_types(c,author='first reviewer');forward=p.export_types()
    with project(tmp_path,'last',0x3000) as p:
        p.import_types(forward,author='second reviewer');row=p.export_types()['types'][0]
        assert row['origin']['source']==c['source'] and row['author']=='original analyst'
        assert row['origin']['imported_by']=='second reviewer'
        # Caller mutation after import cannot alter retained declarations.
        forward['types'][0]['definition']['fields'][0]['name']='forged_after_import'
        assert p.export_types()['types'][0]['definition']['fields'][0]['name']=='amount'


def test_selected_export_avoids_unrelated_context_bound_types(tmp_path):
    with project(tmp_path,'selectable') as p:
        declared(p)
        p.define_type('ContextPointer',{'kind':'pointer','size':2,'target':'u8','address_space':'near','segment':0x1234})
        with pytest.raises(ValueError,match='context'):p.export_types()
        before=p.db.total_changes
        selected=p.export_types(names=['Records'])
        assert [r['name'] for r in selected['types']]==['Record','RecordPointer','Records']
        assert p.db.total_changes==before
        assert p.export_types(names=[])['types']==[]
    with project(tmp_path,'receiving') as p:
        assert p.import_types(selected)['imported']==3
        assert [r['name'] for r in p.export_types()['types']]==['Record','RecordPointer','Records']


def test_selected_closure_follows_prototype_alias_array_and_union_dependencies(tmp_path):
    with project(tmp_path,'dependency_graph') as p:
        p.define_type('Payload',{'kind':'scalar','size':2})
        p.define_type('Alias',{'kind':'typedef','target':'Payload'})
        p.define_type('Args',{'kind':'array','element':'Alias','count':2})
        p.define_type('PayloadPointer',{'kind':'pointer','size':4,'target':'Payload'})
        p.define_type('Callback',{'kind':'function','returns':'PayloadPointer','arguments':[{'name':'values','type':'Args'}],'abi':'x86_16_cdecl_near'})
        p.define_type('CallbackPointer',{'kind':'pointer','size':4,'target':'Callback'})
        p.define_type('CallbackAlias',{'kind':'typedef','target':'CallbackPointer'})
        p.define_type('Wrapper',{'kind':'union','size':4,'fields':[{'name':'callback','type':'CallbackAlias'}]})
        p.define_type('Unrelated',{'kind':'scalar','size':1})
        result=p.export_types(names=['Wrapper'])
        assert {r['name'] for r in result['types']}=={'Payload','Alias','Args','PayloadPointer','Callback','CallbackPointer','CallbackAlias','Wrapper'}
    with project(tmp_path,'graph_receiver') as p:
        assert p.import_types(result)['imported']==8


@pytest.mark.parametrize('names',[['Missing'],['u16'],['Record','Record'],'Record',[True]])
def test_invalid_selected_names_do_not_mutate_the_project(tmp_path,names):
    with project(tmp_path,'invalid_selection') as p:
        declared(p);before=p.export_types();changes=p.db.total_changes
        with pytest.raises(ValueError):p.export_types(names=names)
        assert p.export_types()==before and p.db.total_changes==changes


def test_context_bound_dependency_inside_selected_closure_is_still_refused(tmp_path):
    with project(tmp_path,'context_dependency') as p:
        p.define_type('ContextPointer',{'kind':'pointer','size':2,'target':'u8','address_space':'near','segment':0x1234})
        p.define_type('Record',{'kind':'struct','size':2,'fields':[{'name':'address','offset':0,'type':'ContextPointer'}]})
        with pytest.raises(ValueError,match='context'):p.export_types(names=['Record'])
        with pytest.raises(ValueError,match='4096'):p.export_types(names=['Record']*4097)
