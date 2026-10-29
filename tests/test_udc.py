"""A real original-backed compiler path, independently checked at its seams."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import struct

import pytest

from fdisbull.interaction_il import execute_il
from fdisbull.project import Project
from fdisbull.udc import capture_dos_definition, compile_dos, definition_info, shared_programs, UDCQualificationError
from fdisbull.udl_blocks import lift_asm_block
from fdisbull import proofs


CODE = bytes.fromhex('b80a0005c8002d0100')


def image(tmp_path):
    # A tiny authored DOS program: compute 209, store it, print a title, spin.
    body = CODE + bytes.fromhex('a32001ba2201b409cd21ebfe')
    data = body.ljust(32, b'\x00') + b'\x00\x00UDC BLOCK GAME$'
    binary = tmp_path / 'BLOCKS.COM'; binary.write_bytes(data)
    return binary, data


def lift():
    return lift_asm_block(CODE, {'ax':'$money'}, inputs=[], outputs=['ax'])


def external_output(tmp_path, name):
    # pytest's temporary root has no Git ancestor.
    return tmp_path / name


def test_reconstruct_from_blocks_after_restart_without_source_file(tmp_path):
    binary, raw = image(tmp_path); resource = tmp_path/'data'; resource.write_bytes(b'authored resource')
    db = tmp_path/'private.fdb'
    with Project.create(db, binary, image='com') as p:
        p.attach_file(resource, name='resource')
        d = capture_dos_definition(p, 'original', resources={'DATA/INFO.TXT':'resource'})
    binary.unlink(); resource.unlink()
    with Project(db) as p:
        result = compile_dos(p, d['id'], external_output(tmp_path, 'result'))
        assert (Path(result['output'])/'BLOCKS.COM').read_bytes() == raw
        assert (Path(result['output'])/'DATA/INFO.TXT').read_bytes() == b'authored resource'
        assert result['qualification']['status'] == 'original_bytes_only'
        assert result['qualification']['semantic_blocks'] == 0
        assert result['generated_dos_lowering'] is False
        assert definition_info(p, d['id'])['sha256'] == d['sha256']
        manifest = json.loads((Path(result['output'])/'udc-manifest.json').read_text())
        assert manifest['artifacts'][0]['sha256'] == hashlib.sha256(raw).hexdigest()


@pytest.mark.skipif(proofs._load_z3() is None, reason='requires genuine Z3')
def test_asm_udl_uil_original_backing_roundtrip_and_negative(tmp_path):
    binary, raw = image(tmp_path)
    with Project.create(tmp_path/'private.fdb', binary, image='com') as p:
        d = capture_dos_definition(p, 'mapped', semantic_blocks=[{'id':'money','offset':0,'lift':lift()}])
        udl = shared_programs(p, d['id'], role='udl')['money']
        uil = shared_programs(p, d['id'])['money']
        assert udl['body'] == uil['body'] and udl['role'] == 'udl' and uil['role'] == 'uil'
        assert execute_il(uil)['state'] == {'$money':209}
        result = compile_dos(p, d['id'], tmp_path/'roundtrip', programs={'money':uil})
        assert (tmp_path/'roundtrip/BLOCKS.COM').read_bytes() == raw
        assert result['qualification']['proofs']['money']['status'] == 'equivalent_under_assumptions'
        # A shorter equivalent program may select the original backing only
        # under its declared register-boundary observation profile.
        equivalent = deepcopy(uil); equivalent['body'] = [{'id':'constant','op':'set','var':'$money','value':209}]
        assert compile_dos(p, d['id'], tmp_path/'equivalent', programs={'money':equivalent})['qualification']['byte_identity']
        wrong = deepcopy(uil); wrong['body'][-1]['value'] = 2
        with pytest.raises(UDCQualificationError) as error:
            compile_dos(p, d['id'], tmp_path/'wrong', programs={'money':wrong})
        assert error.value.verification['status'] == 'counterexample'
        assert not (tmp_path/'wrong').exists()


def test_unavailable_proof_never_becomes_parity(tmp_path, monkeypatch):
    binary, _ = image(tmp_path)
    monkeypatch.setattr(proofs, '_load_z3', lambda: None)
    with Project.create(tmp_path/'private.fdb', binary, image='com') as p:
        with pytest.raises(UDCQualificationError) as error:
            capture_dos_definition(p, 'mapped', semantic_blocks=[{'id':'money','offset':0,'lift':lift()}])
        assert error.value.verification['status'] == 'unavailable'
        d = capture_dos_definition(p, 'opaque')
        assert compile_dos(p, d['id'], tmp_path/'opaque')['qualification']['status'] == 'original_bytes_only'


def test_immutable_parent_and_patch_isolation(tmp_path):
    binary, raw = image(tmp_path)
    with Project.create(tmp_path/'private.fdb', binary, image='com') as p:
        first = capture_dos_definition(p, 'original')
        with pytest.raises(ValueError, match='parent'): capture_dos_definition(p, 'original')
        assert capture_dos_definition(p, 'original', parent=first['id'])['id'] == first['id']
        child = p.patch('1000:0101', '0b00')
        with pytest.raises(ValueError, match='version 1'):
            capture_dos_definition(p, 'child', version=child['version'])
        result = compile_dos(p, first['id'], tmp_path/'original')
        assert (Path(result['output'])/'BLOCKS.COM').read_bytes() == raw


def test_tampered_backing_missing_block_and_metadata_refused(tmp_path):
    binary, _ = image(tmp_path)
    with Project.create(tmp_path/'private.fdb', binary, image='com') as p:
        first = capture_dos_definition(p, 'one')
        p.db.execute('UPDATE udc_blocks SET data=? WHERE definition=?', (b'broken', first['id'])); p.db.commit()
        with pytest.raises(ValueError, match='integrity'): compile_dos(p, first['id'], tmp_path/'broken')
        assert not (tmp_path/'broken').exists()
        second = capture_dos_definition(p, 'two')
        p.db.execute('DELETE FROM udc_blocks WHERE definition=?', (second['id'],)); p.db.commit()
        with pytest.raises(ValueError, match='missing'): compile_dos(p, second['id'], tmp_path/'missing')
        p.db.execute('UPDATE udc_definitions SET document=? WHERE id=?', ('{}', second['id'])); p.db.commit()
        with pytest.raises(ValueError, match='integrity'): definition_info(p, second['id'])


def test_output_input_and_resource_guards(tmp_path):
    binary, _ = image(tmp_path); resource=tmp_path/'resource';resource.write_bytes(b'not a save')
    with Project.create(tmp_path/'private.fdb', binary, image='com') as p:
        p.attach_file(resource,name='r')
        for path in ('../escape','/absolute','A/../B','state.sav','UDC-MANIFEST.JSON','blocks.com','C:/outside','C:outside','A:stream','data.db-wal','dinosg.000','CON','NUL.txt'):
            with pytest.raises(ValueError): capture_dos_definition(p, 'bad', resources={path:'r'})
        with pytest.raises(ValueError): capture_dos_definition(p, 'bad', main_name='udc-manifest.json')
        with pytest.raises(ValueError): capture_dos_definition(p, 'bad', resources={'A':'r','A/B':'r'})
        with pytest.raises(ValueError): capture_dos_definition(p, 'bad', resources={'A':'r','a/B':'r'})
        with pytest.raises(ValueError): capture_dos_definition(p, 'bad', semantic_blocks=[{'id':'x','offset':0,'lift':[]}])
        d=capture_dos_definition(p,'good')
        existing=tmp_path/'existing';existing.mkdir()
        with pytest.raises(ValueError,match='new'):compile_dos(p,d['id'],existing)
        repo=tmp_path/'repository';repo.mkdir();(repo/'.git').write_text('gitdir: elsewhere')
        with pytest.raises(ValueError,match='outside Git'):compile_dos(p,d['id'],repo/'game')
        with pytest.raises(ValueError,match='every mapped'):compile_dos(p,d['id'],tmp_path/'extra',programs={'unexpected':{}})


def test_authorship_metadata_and_renamed_database_are_checked(tmp_path):
    binary, _ = image(tmp_path)
    resource=tmp_path/'renamed.txt';resource.write_bytes(b'SQLite format 3\x00' + bytes(128))
    with Project.create(tmp_path/'private.fdb',binary,image='com') as p:
        p.attach_file(resource,name='renamed')
        with pytest.raises(ValueError,match='SQLite'):
            capture_dos_definition(p,'bad',resources={'innocent.txt':'renamed'})
        d=capture_dos_definition(p,'good',author='original-author')
        p.db.execute('UPDATE udc_definitions SET author=? WHERE id=?',('changed-author',d['id']));p.db.commit()
        with pytest.raises(ValueError,match='integrity'):definition_info(p,d['id'])


def test_competing_directory_is_never_replaced(tmp_path,monkeypatch):
    binary, _ = image(tmp_path)
    target=tmp_path/'raced';original_mkdir=Path.mkdir
    with Project.create(tmp_path/'private.fdb',binary,image='com') as p:
        d=capture_dos_definition(p,'original')
        def compete(path,*args,**kwargs):
            if path==target:
                original_mkdir(path)
            return original_mkdir(path,*args,**kwargs)
        monkeypatch.setattr(Path,'mkdir',compete)
        with pytest.raises(FileExistsError):compile_dos(p,d['id'],target)
        assert target.is_dir() and list(target.iterdir())==[]


def test_capture_does_not_commit_the_callers_transaction(tmp_path):
    binary, _ = image(tmp_path)
    with Project.create(tmp_path/'private.fdb',binary,image='com') as p:
        with pytest.raises(RuntimeError):
            with p.transaction(True):
                capture_dos_definition(p,'rolled-back')
                raise RuntimeError('rollback')
        assert p.db.execute("select name from sqlite_master where name='udc_definitions'").fetchone() is None


def test_mz_fixups_and_overlay_are_preserved_but_not_misproved(tmp_path):
    header=bytearray(32)
    struct.pack_into('<14H',header,0,0x5a4d,64,1,1,2,1,0xffff,0,32,0,0,0,28,0)
    struct.pack_into('<HH',header,28,1,0)  # loader changes MOV AX's immediate.
    raw=bytes(header)+bytes.fromhex('b80000c3').ljust(32,b'\x00')+b'\x40'
    binary=tmp_path/'GAME.EXE';binary.write_bytes(raw)
    with Project.create(tmp_path/'private.fdb',binary) as p:
        opaque=capture_dos_definition(p,'original')
        assert (Path(compile_dos(p,opaque['id'],tmp_path/'opaque')['output'])/'GAME.EXE').read_bytes()==raw
        relocated=lift_asm_block(bytes.fromhex('b80000'),{'ax':'$x'},inputs=[],outputs=['ax'])
        with pytest.raises(ValueError,match='relocations'):
            capture_dos_definition(p,'false-constant',semantic_blocks=[{'id':'x','offset':32,'lift':relocated}])
        overlay=lift_asm_block(b'\x40',{'ax':'$x'},inputs=['ax'],outputs=['ax'])
        with pytest.raises(ValueError,match='outside'):
            capture_dos_definition(p,'overlay',semantic_blocks=[{'id':'x','offset':64,'lift':overlay}])
