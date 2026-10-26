from fdisbull.cli import respond
from fdisbull.dos_services import describe_interrupt, service_catalog
from fdisbull.project import Project
from test_dos_loader import mz_file


def test_read_contract_retains_unknown_actual_transfer_and_unknown_selectors():
    service=describe_interrupt(0x21,dict(ax=0x3f00,bx=7,cx=8,ds=0x1234,dx=0x10))
    assert service['name']=='read_file'
    assert service['inputs']['bx']['value']==7
    assert service['memory_effects'][0]['address']=='0x12350'
    assert service['memory_effects'][0]['length']==8
    assert service['memory_effects'][0]['extent']=='upper_bound_on_success'
    assert not service['runtime_observed']
    unknown=describe_interrupt(0x21,dict(ax=[0x3f00,0x4000]))
    assert not unknown['known'] and not unknown['memory_effects']
    assert describe_interrupt(0x21,dict(ah=0xff))['name'] is None


def test_catalog_has_dos_bios_and_explicit_outputs():
    catalog=respond({'method':'dos-services'})
    assert catalog['ok']
    assert describe_interrupt(0x10,dict(ah=0xf))['outputs']['al']=='mode'
    assert describe_interrupt(0x20)['terminates']
    assert len(service_catalog()['entries'])>=30
    assert describe_interrupt(0x33,{}) is None


def test_stored_service_views_preserve_comments_raw_operands_patch_and_restart(tmp_path):
    binary=tmp_path/'SERVICES.EXE'
    # DS=CS; read(handle=7,length=8,buffer=DS:100), then terminate.
    binary.write_bytes(mz_file(bytes.fromhex('0e1fbb0700b90800ba0001b43fcd21b8004ccd21')+bytes(512)))
    database=tmp_path/'services.fdb'
    with Project.create(database,binary) as p:
        p.analyze(max_instructions=64)
        p.annotate('1000:000d','authored explanation',kind='comment',author='tester')
        row=next(r for r in p.disassembly('1000:000d',lines=1)['instructions'])
        assert row['bytes']=='cd21' and row['comment']=='authored explanation'
        assert row['comment_author']=='tester' and row['raw_operands']==row['operands']
        assert row['interrupt_service']['name']=='read_file'
        assert 'DOS.read_file' in row['display_operands']
        child=p.patch('1000:000c','40')['version']
        p.analyze(version=child,max_instructions=64)
        assert p.disassembly('1000:000d',lines=1,version=child)['instructions'][0]['interrupt_service']['name']=='write_file'
        assert p.disassembly('1000:000d',lines=1,version=1)['instructions'][0]['interrupt_service']['name']=='read_file'
    with Project(database) as p:
        row=p.disassembly('1000:000d',lines=1,version=1)['instructions'][0]
        assert row['interrupt_service']['memory_effects'][0]['address']=='0x10100'
