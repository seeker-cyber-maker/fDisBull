import struct

from fdisbull.cli import respond
from fdisbull.loader import load_image
from fdisbull.project import Project
from fixtures_formats import pe64


def dll_bytes(entry=True):
    data=bytearray(pe64())
    struct.pack_into('<H',data,0x96,0x2022)
    if not entry:
        struct.pack_into('<I',data,0x98+16,0)
    return bytes(data)


def test_entryless_dll_import_uses_exports_without_fabricating_entry(tmp_path):
    dll=tmp_path/'entryless.dll';dll.write_bytes(dll_bytes(False))
    image=load_image(dll)
    assert image.metadata['entrypoint_present'] is False
    assert not any(s.source=='entry' for s in image.seeds)
    with Project.create(tmp_path/'module.fdb',dll) as p:
        assert p.analyze()['stable']
        assert p.disassembly(0x140001010,lines=1)['instructions'][0]['mnemonic']=='ret'
        assert not p.db.execute("SELECT 1 FROM work WHERE address='0000000140000000'").fetchone()


def test_on_demand_export_analysis_is_persistent_and_scoped(tmp_path):
    dll=tmp_path/'sample.dll';dll.write_bytes(dll_bytes())
    project=tmp_path/'selected.fdb'
    response=respond({'method':'analyze-module','params':{'path':str(dll),'project':str(project),'export':'helper'}})
    assert response['ok'],response
    assert response['result']['analysis']['stable']
    with Project(project) as p:
        assert {r[0] for r in p.db.execute('SELECT address FROM instructions')}=={'0000000140001010'}
        assert p.analyze()['attempted']==0
        parent=p.version()['sha256']
        result=p.represent(0x140001010,'byte',defer=True)
        assert result['analysis'] is None
        assert p.version()['sha256']==parent and not p.db.execute('SELECT 1 FROM instructions').fetchone()
        assert p.analyze()['stable']
        p.represent(0x140001010,'code')
        assert {r[0] for r in p.db.execute('SELECT address FROM instructions')}=={'0000000140001010'}


def test_unexplored_range_is_retained_without_scalar_or_instruction_facts(tmp_path):
    binary=tmp_path/'bytes.bin';binary.write_bytes(bytes.fromhex('b82a000000c3'))
    with Project.create(tmp_path/'bytes.fdb',binary,arch='x86',base=0x1000) as p:
        p.analyze()
        original=p.regions(1)[0].data
        result=p.represent(0x1000,'unexplored',size=5,defer=True)
        assert result['analysis'] is None
        assert p.analyze()['stable'] and p.items()==[]
        assert not p.db.execute('SELECT 1 FROM instructions').fetchone()
        assert p.regions(1)[0].data==original
        p.represent(0x1000,'code',size=5)
        assert p.disassembly(0x1000,lines=1)['instructions'][0]['mnemonic']=='mov'


def test_module_selection_failure_does_not_create_project(tmp_path):
    dll=tmp_path/'sample.dll';dll.write_bytes(dll_bytes())
    project=tmp_path/'absent.fdb'
    response=respond({'method':'analyze-module','params':{'path':str(dll),'project':str(project),'export':'missing'}})
    assert not response['ok'] and not project.exists()


def test_held_upper_half_of_pointer_cannot_promote_truncated_pointer(tmp_path):
    from test_autoanalysis import raw_image
    path=tmp_path/'pointer.bin';path.write_bytes(raw_image())
    with Project.create(tmp_path/'pointer.fdb',path,arch='x86',base=0x1000) as p:
        p.analyze()
        assert any(r['address']=='0x1040' for r in p.disassembly()['instructions'])
        p.represent(0x1034,'unexplored',size=1)
        assert not any(r['address']=='0x1040' for r in p.disassembly()['instructions'])
        assert not any(r['kind']=='resolved_call' for r in p.xrefs(0x1040))
