import copy
import struct

import pytest

from fdisbull.omf_catalog import omf_signatures
from fdisbull.project import Project
from fdisbull.summaries import builtin_signatures
from test_dos_loader import mz_file


@pytest.mark.parametrize('signature',[s for s in builtin_signatures() if s.get('identity_only')],ids=lambda s:s['id'])
def test_every_bundled_dos_identity_decodes_and_requires_the_entire_body(signature):
    from test_summaries import instructions
    from fdisbull.summaries import match_signatures
    rows=instructions(bytes.fromhex(signature['bytes']),bits=16)
    matches=match_signatures(rows,arch='x86',bits=16)
    assert any(m['signature_id']==signature['id'] and m['identity_only'] for m in matches)
    assert not match_signatures(rows[:-1],signatures=[signature],arch='x86',bits=16)


def _record(kind,payload):
    data=bytes([kind])+struct.pack('<H',len(payload)+1)+payload
    return data+bytes([-sum(data)&255])


def _library(extra=b''):
    def name(text):return bytes([len(text)])+text.encode()
    body=bytes.fromhex('b8341289c3c3')
    module=(_record(0x80,name('sample.asm'))+_record(0x96,name('_TEXT')+name('CODE'))+
            _record(0x98,b'\x48\x06\0\x01\x02\0')+
            _record(0x90,b'\0\x01'+name('_sample')+b'\0\0\0')+
            _record(0xa0,b'\x01\0\0'+body)+extra+_record(0x8a,b'\0'))
    return _record(0xf0,bytes(12))+module+bytes(-len(module)%16)+_record(0xf1,bytes(12))


def test_omf_symbols_and_closed_body_and_exclusions():
    catalog=omf_signatures(_library(),source='authored OMF test object')
    assert catalog['signatures'][0]['name']=='sample'
    assert catalog['signatures'][0]['bytes']=='b8341289c3c3'
    assert catalog['signatures'][0]['identity_only']
    rejected=omf_signatures(_library(_record(0x9c,b'\0')),source='authored')
    assert not rejected['signatures'] and rejected['extraction']['excluded']['module requires linker fixups']==1
    with pytest.raises(ValueError):omf_signatures(_library()[:-5],source='truncated')
    oversized=_library(_record(0x98,b'\x48\xff\xff\x01\x02\0')*17)
    excluded=omf_signatures(oversized,source='bounded segment allocation')
    assert excluded['extraction']['excluded']['module segment budget exceeded']==1


def test_bundled_runtime_names_are_real_catalog_entries_not_effect_contracts(tmp_path):
    signatures=[s for s in builtin_signatures() if s.get('identity_only')]
    assert not any(s['bits']==16 for s in builtin_signatures(arch='x86',bits=64))
    assert len(signatures)==182
    assert {'strlen','memcpy','strcpy','strcmp','memset'}<={s['name'] for s in signatures}
    signature=next(s for s in signatures if s['name']=='strlen' and s['abi']=='x86_16_cdecl_near')
    binary=tmp_path/'LIBRARY.EXE';binary.write_bytes(mz_file(bytes.fromhex(signature['bytes'])+bytes(512)))
    db=tmp_path/'runtime.fdb'
    with Project.create(db,binary) as p:
        p.auto_analyze(max_instructions=100,max_functions=4)
        assert p.disassembly('1000:0000',lines=1)['instructions'][0]['name']=='strlen'
        assert not p.summaries()['items']  # Identity does not invent segmented memory effects.
        original=p.function_analysis('1000:0000')['result']['signature_matches']
        child=p.patch('1000:0005','d6')['version']
        assert all(row['name']!='strlen' for row in p.disassembly('1000:0000',lines=1,version=child)['instructions'])
        p.auto_analyze(version=child,max_instructions=100,max_functions=4)
        assert p.disassembly('1000:0000',lines=1,version=child)['instructions'][0]['name']!='strlen'
        assert p.function_analysis('1000:0000',version=1)['result']['signature_matches']==original
    with Project(db) as p:
        assert p.disassembly('1000:0000',lines=1,version=1)['instructions'][0]['name']=='strlen'
        p.annotate('1000:0000','my_length',version=1,kind='name')
        assert p.disassembly('1000:0000',lines=1,version=1)['instructions'][0]['name']=='my_length'


def test_capture_export_import_and_bad_catalog_atomicity(tmp_path):
    source=tmp_path/'body.bin';source.write_bytes(bytes.fromhex('b8341289c3c3'))
    with Project.create(tmp_path/'first.fdb',source,arch='x86',bits=16,base=0x1000) as p:
        p.auto_analyze()
        captured=p.capture_signature(0x1000,'known_routine',author='tester')
        assert captured['signature']['provenance']['author']=='tester'
        catalog=p.export_signatures()
    moved=tmp_path/'moved.bin';moved.write_bytes(b'\x90'+source.read_bytes())
    with Project.create(tmp_path/'second.fdb',moved,arch='x86',bits=16,base=0x2000) as p:
        p.import_signatures(catalog);p.analyze(start=0x2001);p.auto_analyze()
        assert p.disassembly(0x2001,lines=1)['instructions'][0]['name']=='known_routine'
        before=p.signatures()
        bad=copy.deepcopy(catalog);bad['signatures'].append(dict(catalog['signatures'][0],id='bad',bytes='zz'))
        with pytest.raises(ValueError):p.import_signatures(bad)
        assert p.signatures()==before


def test_ambiguous_equal_bodies_do_not_assign_a_name(tmp_path):
    source=tmp_path/'body.bin';source.write_bytes(bytes.fromhex('b8341289c3c3'))
    with Project.create(tmp_path/'ambiguous.fdb',source,arch='x86',bits=16,base=0x1000) as p:
        p.auto_analyze()
        p.capture_signature(0x1000,'one');p.capture_signature(0x1000,'two');p.auto_analyze()
        matches=p.function_analysis(0x1000)['result']['signature_matches']
        assert {m['name'] for m in matches}=={'one','two'}
        assert p.disassembly(0x1000,lines=1)['instructions'][0]['name'] not in ('one','two')
