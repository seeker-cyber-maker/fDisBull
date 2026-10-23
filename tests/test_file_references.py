"""File-offset evidence stays separate from native flow and survives editing."""
import json
import struct
import xml.etree.ElementTree as ET

import pytest

from fdisbull.cli import main, respond
from fdisbull.project import Project
from fdisbull.render import render_snapshot


def make_project(tmp_path, mode='x86'):
    source=tmp_path/'program.bin'
    if mode=='mz':
        header=bytearray(64);module=bytearray(64)
        struct.pack_into('<14H',header,0,0x5a4d,128,1,0,4,0,0xffff,0,0,0,0,0,28,0)
        module[:4]=bytes.fromhex('8b4710cb')
        source.write_bytes(header+module)
        return Project.create(tmp_path/'project.fdb',source),0x10000
    code=bytes.fromhex('201040b9c0035fd6') if mode=='arm64' else bytes.fromhex('8b4310c3')
    source.write_bytes(code)
    return Project.create(tmp_path/'project.fdb',source,arch=mode,base=0x1000),0x1000


def attach_table(project,tmp_path):
    data=bytearray(64);struct.pack_into('<4I',data,16,250,500,750,1250)
    source=tmp_path/'VARS.DAT';source.write_bytes(data)
    project.attach_file(source,kind='resource')
    project.define_type('FourWords',dict(kind='array',element='u32',count=4))
    project.define_type('Parameters',dict(kind='struct',size=64,fields=[dict(name='increments',offset=16,type='FourWords')]))
    project.apply_file_type('VARS.DAT','Parameters',name='parameters')
    return source


@pytest.mark.parametrize('mode',['x86','arm64','mz'])
def test_authored_links_share_typed_labels_in_native_views_without_native_edges(tmp_path,mode):
    project,entry=make_project(tmp_path,mode)
    with project:
        project.analyze();attach_table(project,tmp_path)
        original=project.disassembly(entry,lines=1)['instructions'][0]
        native_edges=list(project.db.execute('SELECT * FROM xrefs'))
        versions=project.versions()
        reference=project.file_reference(entry,'VARS.DAT',16,width=4,count=4,stride=4,
                                         evidence='Buffer relation supplied by analyst; index is bounded 0..3.',access='read')['reference']
        assert reference['active'] and not reference['stale'] and not reference['runtime_observed']
        assert reference['identity_basis']=='authored_file_reference'
        assert [x['name'] for x in reference['locations']]==[f'parameters.increments[{i}]' for i in range(4)]
        shown=project.disassembly(entry,lines=1)['instructions'][0]
        assert shown['file_references']==[reference]
        assert shown['operands']==original['operands'] and shown['references']==original['references']
        assert 'file VARS.DAT+0x10' in shown['display_operands']
        cfg=project.cfg(entry)
        assert cfg['nodes'][0]['file_references']==[reference]
        assert list(project.db.execute('SELECT * FROM xrefs'))==native_edges
        assert project.versions()==versions
        assert project.file_xrefs('VARS.DAT',20,size=4)['items'][0]['matched_elements']==dict(first=1,last=1)
        project.define_type('Parameters',dict(kind='struct',size=64,fields=[dict(name='adjustments',offset=16,type='FourWords')]))
        assert project.typed_file('VARS.DAT')['items'][0]['path']=='parameters.adjustments[0]'
        assert 'parameters.adjustments[0]' in project.disassembly(entry,lines=1)['instructions'][0]['display_operands']
        assert project.file_xrefs('VARS.DAT',16)['items'][0]['locations'][0]['name']=='parameters.adjustments[0]'
        svg=tmp_path/'typed.svg'
        render_snapshot(project.disassembly(entry,lines=1),svg)
        ET.parse(svg)
        assert 'parameters.adjustments[0]' in svg.read_text()


def test_exact_strided_overlap_does_not_report_padding_or_other_file(tmp_path):
    project,entry=make_project(tmp_path)
    with project:
        project.analyze();source=attach_table(project,tmp_path)
        project.attach_file(source,name='other.save',kind='save')
        project.file_reference(entry,'VARS.DAT',16,width=2,count=4,stride=4,evidence='Four low words only.')
        assert project.file_xrefs('VARS.DAT',18,size=2)['total']==0
        assert project.file_xrefs('VARS.DAT',17,size=4)['total']==1
        assert project.file_xrefs('other.save',16,size=16)['total']==0
        assert project.file_xrefs('VARS.DAT',30,size=1)['total']==0


def test_patch_revalidates_instruction_bytes_and_preserves_parent_and_restart(tmp_path):
    project,entry=make_project(tmp_path)
    path=project.path
    with project:
        project.analyze();source=attach_table(project,tmp_path)
        project.file_reference(entry,'VARS.DAT',16,width=4,evidence='Verified separately from native address identity.')
        child=project.patch(entry,'90')['version']
        assert project.file_xrefs('VARS.DAT',16,version=child)['items'][0]['state']=='stale_bytes'
        assert project.file_xrefs('VARS.DAT',16,version=child,include_stale=False)['total']==0
        assert project.file_xrefs('VARS.DAT',16,version=1)['items'][0]['active']
        project.analyze(version=child)
        shown=project.disassembly(entry,version=child,lines=1)['instructions'][0]
        assert shown['file_references'][0]['stale'] and 'file VARS.DAT' not in shown['display_operands']
        restored=project.patch(entry,'8b',version=child)['version']
        assert project.file_xrefs('VARS.DAT',16,version=restored)['items'][0]['state']=='awaiting_decode'
        project.analyze(version=restored)
        assert project.file_xrefs('VARS.DAT',16,version=restored)['items'][0]['active']
        source.unlink()
    with Project(path) as reopened:
        assert reopened.file_xrefs('VARS.DAT',16,version=1)['items'][0]['active']
        assert reopened.file_xrefs('VARS.DAT',16,version=child)['items'][0]['stale']
        assert reopened.typed_file('VARS.DAT')['items'][3]['value']==1250


def test_dos_reference_source_needs_exact_cs_interpretation(tmp_path):
    project,entry=make_project(tmp_path,'mz')
    with project:
        project.analyze();attach_table(project,tmp_path)
        project.analyze(start='0fff:0010')
        with pytest.raises(ValueError,match='multiple CS'):
            project.file_reference(entry,'VARS.DAT',16,evidence='Ambiguous source must not pick a CS silently.')
        project.file_reference('1000:0000','VARS.DAT',16,evidence='Reference for the 1000 CS interpretation.')
        a=project.disassembly('1000:0000',lines=1)['instructions'][0]
        b=project.disassembly('0fff:0010',lines=1)['instructions'][0]
        assert len(a['file_references'])==1 and b['file_references']==[]


@pytest.mark.parametrize('invalid',[
    dict(evidence=None),dict(evidence=''),dict(count=True),dict(width=0),dict(stride=0),
    dict(offset=64),dict(offset=60,width=4,count=2),dict(access='execute'),dict(cs=0x1000)])
def test_invalid_file_links_are_atomic(tmp_path,invalid):
    project,entry=make_project(tmp_path)
    with project:
        project.analyze();attach_table(project,tmp_path)
        args=dict(address=entry,file='VARS.DAT',offset=16,evidence='Supplied analyst relation.');args.update(invalid)
        with pytest.raises(ValueError):project.file_reference(**args)
        assert project.db.execute('SELECT COUNT(*) FROM file_references').fetchone()[0]==0


def test_cli_and_json_cover_external_files_and_type_references(tmp_path,capsys):
    project,entry=make_project(tmp_path)
    path=str(project.path)
    with project:project.analyze()
    source=tmp_path/'values.dat';source.write_bytes(struct.pack('<4I',250,500,750,1250))
    definition=tmp_path/'layout.json';definition.write_text(json.dumps(dict(kind='array',element='u32',count=4)))
    commands=[['attach-file',path,str(source),'--kind','resource'],
              ['define-type',path,'Values',str(definition)],
              ['apply-file-type',path,'values.dat','Values','--name','parameters'],
              ['file-reference',path,hex(entry),'values.dat','0x4','--width','4','--evidence','Offset verified by analyst.'],
              ['files',path],['file-bytes',path,'values.dat','--offset','0x4','--size','4'],
              ['file-data',path,'values.dat'],['file-xrefs',path,'values.dat','0x4','--active-only']]
    results=[]
    for command in commands:
        assert main(command)==0,command
        result=json.loads(capsys.readouterr().out);assert result['ok'],result
        results.append(result['result'])
    assert results[-3]['bytes']=='f4010000'
    assert results[-2]['items'][1]['value']==500
    assert results[-1]['items'][0]['active']
    response=respond(dict(method='file-xrefs',params=dict(project=path,file='values.dat',offset=4)))
    assert response['ok'] and response['result']['total']==1


def test_many_file_references_keep_single_instruction_renderable_and_report_truncation(tmp_path):
    project,entry=make_project(tmp_path)
    with project:
        project.analyze()
        source=tmp_path/'data.bin';source.write_bytes(bytes(128))
        project.attach_file(source)
        for offset in range(128):
            project.file_reference(entry,'data.bin',offset,evidence='Separate authored byte relation.')
        shown=project.disassembly(entry,lines=1)['instructions'][0]
        assert len(shown['file_references'])==8
        assert shown['file_reference_summary']==dict(total=128,returned=8,truncated=True)
        assert len(shown['display_operands'])<2048 and '125 additional file references' in shown['display_operands']
        render_snapshot(project.disassembly(entry,lines=1),tmp_path/'many.svg')
        assert project.file_xrefs('data.bin',0,size=128,limit=2)['has_more']
        assert project.file_xrefs('data.bin',0,size=128,limit=128)['total']==128


def test_typed_file_item_budget_does_not_repeat_expanded_nested_layouts(tmp_path):
    project,_=make_project(tmp_path)
    with project:
        source=tmp_path/'nested.bin';source.write_bytes(bytes(16384))
        project.attach_file(source)
        project.define_type('Small',dict(kind='struct',size=128,fields=[dict(name=f'b{i}',offset=i,type='u8') for i in range(128)]))
        project.define_type('Large',dict(kind='struct',size=16384,fields=[dict(name=f'r{i}',offset=i*128,type='Small') for i in range(128)]))
        applied=project.apply_file_type('nested.bin','Large')
        result=project.typed_file('nested.bin',max_items=1)
        assert len(result['items'])==1 and result['truncated'] and result['layout_expanded'] is False
        assert len(json.dumps(applied))<65536 and len(json.dumps(result))<65536
        assert result['layout']['fields'][0]['type']=='Small'


def test_schema5_migration_adds_file_tables_without_changing_native_versions(tmp_path):
    project,entry=make_project(tmp_path)
    path=project.path
    with project:
        project.analyze();project.annotate(entry,'entry_name',kind='name')
        before=project.versions();native=project.regions(1)[0].data
        with project.transaction(True):
            for table in ('file_references','file_type_bindings','external_files'):project.db.execute(f'DROP TABLE {table}')
            project.db.execute("UPDATE metadata SET value='5' WHERE key='schema'")
    with Project(path) as reopened:
        assert reopened.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0]=='6'
        assert reopened.versions()==before and reopened.regions(1)[0].data==native
        assert reopened.disassembly(entry,lines=1)['instructions'][0]['name']=='entry_name'
        assert reopened.external_files()['total']==0
