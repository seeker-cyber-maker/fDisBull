"""Independent format/arithmetic expectations for build-to-original witnesses."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct

import pytest

from fdisbull.source_native import unpack_exepack, packed_provenance, parse_cod, parse_link_map, map_procedure, static_call_sites
from fdisbull.source_catalog import SourceCatalog


def _packed(module, *, fill=False):
    if fill:
        assert module == b'HEAD' + bytes(28)
        stream = b'HEAD' + b'\0' + struct.pack('<H', 28) + b'\xb1'
    else:
        stream = module + struct.pack('<H', len(module)) + b'\xb3'
    stream += b'\xff' * (-len(stream) % 16)
    trailer = b'\x90' * 5 + b'Packed file is corrupt' + bytes(32)
    exepack = struct.pack('<8H', 0xc, 2, 0, 16 + len(trailer), 0x80, 0, len(module) // 16, 0x4252) + trailer
    length = 32 + len(stream) + len(exepack)
    header = [0x5a4d, length % 512, (length + 511) // 512, 0, 2, 0, 0xffff, 0, 0x80, 0, 16, len(stream) // 16, 28, 0]
    return struct.pack('<14H', *header) + bytes(4) + stream + exepack


def test_exepack_literal_fill_and_original_file_provenance():
    module = bytes(range(64))
    source = _packed(module) + b'ORIGINAL OVERLAY'
    view = unpack_exepack(source)
    assert view['module'] == module
    assert view['resident_only'] and not view['runnable_game']
    assert view['original_overlay_size'] == len(b'ORIGINAL OVERLAY')
    span = packed_provenance(view, 12, 7)
    assert span == [dict(module_offset=12, size=7, kind='literal', packed_offset=44)]
    assert source[44:51] == module[12:19]
    h = struct.unpack_from('<14H', view['image'])
    declared = (h[2] - 1) * 512 + h[1] if h[1] else h[2] * 512
    assert declared == len(view['image'])
    assert view['image'][h[4] * 16:] == module
    fill = unpack_exepack(_packed(b'HEAD' + bytes(28), fill=True))
    assert fill['module'] == b'HEAD' + bytes(28)
    assert packed_provenance(fill, 4, 28)[0]['kind'] == 'fill'
    with pytest.raises(ValueError):
        packed_provenance(view, 62, 4)


@pytest.mark.parametrize('mutation', ['signature', 'opcode', 'length', 'tail', 'relocation', 'header18'])
def test_bad_or_unqualified_exepack_profiles_are_refused(mutation):
    raw = bytearray(_packed(bytes(range(64))))
    h = struct.unpack_from('<14H', raw)
    base = h[4] * 16 + h[11] * 16
    if mutation == 'signature':
        raw[base + 14] = 0
    elif mutation == 'opcode':
        raw[32 + 66] = 0xba
    elif mutation == 'length':
        struct.pack_into('<H', raw, 32 + 64, 0xffff)
    elif mutation == 'tail':
        struct.pack_into('<H', raw, base + 6, 17)
    elif mutation == 'relocation':
        struct.pack_into('<H', raw, base + 16 + 5 + len(b'Packed file is corrupt'), 1)
        struct.pack_into('<H', raw, base + 16 + 5 + len(b'Packed file is corrupt') + 2, 0xffff)
    else:
        struct.pack_into('<H', raw, 20, 18)
    with pytest.raises(ValueError):
        unpack_exepack(bytes(raw))


MAP = """ Start Stop Length Name Class
 Resident
 00028H 00037H 00010H CODE1 CODE
 00038H 00038H 00000H EMPTY CODE
 0002:000C Res _f
 0002:000C Res _f
"""
COD = """CODE1 SEGMENT WORD PUBLIC 'CODE'
; Line 1
_f PROC FAR
 *** 000004 b8 07 00   mov ax,7
; Line 2
 *** 000007 cb         ret
_f ENDP
"""


def test_linker_word_alignment_and_discontinuous_source_sites():
    raw = bytearray(bytes(range(64)))
    raw[44:48] = b'\xb8\x07\x00\xcb'
    view = unpack_exepack(_packed(bytes(raw)))
    mapped = map_procedure(parse_link_map(MAP), parse_cod(COD), view, '_f')
    span = mapped['spans'][0]
    assert (span['segment'], span['offset'], span['module_offset'], span['size']) == (2, 12, 44, 4)
    line = map_procedure(parse_link_map(MAP), parse_cod(COD), view, '_f', 2)
    assert line['spans'][0]['offset'] == 15 and line['spans'][0]['size'] == 1
    broken = MAP.replace('0002:000C', '0002:000D')
    with pytest.raises(ValueError, match='bases disagree'):
        map_procedure(parse_link_map(broken), parse_cod(COD), view, '_f')
    with pytest.raises(ValueError, match='no emitted'):
        map_procedure(parse_link_map(MAP), parse_cod(COD), view, '_f', 9)
    with pytest.raises(ValueError, match='ambiguous'):
        parse_link_map(MAP + ' 0003:0000 Res _f\n')
    with pytest.raises(ValueError, match='unterminated'):
        parse_cod(COD.replace('_f ENDP', ''))


def test_direct_call_witness_uses_native_operands_not_the_source_mnemonic_alone():
    module = bytearray(bytes(range(64)))
    module[44:49] = b'\x9a\x0c\x00\x03\x00'
    view = unpack_exepack(_packed(bytes(module)))
    link = parse_link_map(MAP + ' 0003:000C Res _target\n')
    cod = parse_cod(COD.replace('b8 07 00   mov ax,7', '9a 0c 00 03 00 call FAR PTR _target')
                    .replace('000007 cb', '000009 cb'))
    sites = static_call_sites(link, cod, view, '_f', ['_target'])
    assert len(sites) == 1
    assert sites[0]['segment'] == 2 and sites[0]['offset'] == 12
    assert sites[0]['module_offset'] == 44 and not sites[0]['runtime_observed']
    wrong_target = parse_link_map(MAP + ' 0003:000D Res _target\n')
    assert not static_call_sites(wrong_target, cod, view, '_f', ['_target'])


def _build_fixture(tmp_path, edition):
    root = tmp_path / edition
    (root / 'src').mkdir(parents=True)
    text = b'int f(void) { return 7; }\n'
    (root / 'src/DEMO.C').write_bytes(text)
    module = bytearray(bytes(range(64)))
    module[44:48] = b'\xb8\x07\x00\xcb'
    original = _packed(bytes(module))
    path = root / 'original.exe'
    path.write_bytes(original)
    directory = root / 'build'
    directory.mkdir()
    (directory / 'DEMO.C').write_bytes(text)
    (directory / 'DEMO.COD').write_text(COD.replace('; Line 2', '; Line 1'))
    (directory / 'CIV.MAP').write_text(MAP)
    (directory / 'CIV.EXE').write_bytes(original)
    before = bytearray(original)
    for i in (12, 13, 18, 19):
        before[i] ^= 1
    (directory / 'CIVRAW.EXE').write_bytes(before)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    outputs = [dict(path=n, expected=digest(directory / n), actual=digest(directory / n), match=True)
               for n in ('CIV.EXE', 'CIVRAW.EXE')]
    receipt = dict(schema='fdisbull-civd-build-1', verified=True, revision=edition,
                   original_sha256=digest(path), source_inputs=[dict(path='src/DEMO.C', sha256=digest(root / 'src/DEMO.C'))],
                   artifacts=[dict(path=p.name, sha256=digest(p)) for p in directory.iterdir() if p.suffix != '.C'],
                   outputs=outputs, startup_correction=[dict(file_offset=i, raw=a, corrected=b)
                   for i, (a, b) in enumerate(zip(before, original)) if a != b])
    (directory / 'build-receipt.json').write_text(json.dumps(receipt))
    return root, directory, path


def test_build_links_transfer_only_after_independent_target_checks_and_restart(tmp_path):
    pytest.importorskip('tree_sitter')
    pytest.importorskip('tree_sitter_c')
    first, directory, original = _build_fixture(tmp_path, 'v1')
    second, target_dir, target_original = _build_fixture(tmp_path, 'v2')
    db = tmp_path / 'source.sqlite'
    with SourceCatalog.create(db) as catalog:
        snapshots = [catalog.import_tree(r, ['src/DEMO.C'], 'repo', e, e, 'reconstructed-source',
                                          target_path=p)['id']
                     for r, p, e in ((first, original, 'v1'), (second, target_original, 'v2'))]
        assert catalog.builds()['total'] == 0
        build = catalog.register_build(snapshots[0], directory, original)
        entity = catalog.entities(snapshot=snapshots[0], name='f')['items'][0]['id']
        mapping = catalog.map_native(entity, build['id'], directory, original)
        assert mapping['document']['spans'][0]['module_offset'] == 44
        assert not mapping['document']['semantic_equivalence']
        transferred = catalog.propagate_native_map(mapping['id'], snapshots[1], target_dir, target_original)
        assert transferred['document']['native_bytes_identical']
        assert transferred['document']['source_body_identical']
        assert not transferred['document']['inherited_native_address']
        assert not transferred['document']['layer_admission']
        assert catalog.native_maps()['total'] == 2
        assert catalog.map_transfers()['total'] == 1
        (target_dir / 'DEMO.COD').write_text('changed')
        with pytest.raises(ValueError, match='artifact changed'):
            catalog.propagate_native_map(mapping['id'], snapshots[1], target_dir, target_original)
        assert catalog.native_maps()['total'] == 2
    with SourceCatalog(db) as reopened:
        assert reopened.map_transfers()['items'][0] == transferred
        assert reopened.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not reopened.db.execute('PRAGMA foreign_key_check').fetchall()


def test_native_endpoint_is_a_qualified_derived_view_and_keeps_parent_on_patch(tmp_path):
    pytest.importorskip('tree_sitter')
    pytest.importorskip('tree_sitter_c')
    from fdisbull.project import Project
    root, directory, original = _build_fixture(tmp_path, 'v1')
    view = unpack_exepack(original.read_bytes())
    image = root / 'resident.exe'
    image.write_bytes(view['image'])
    with Project.create(root / 'resident.fdb', image) as project:
        parent = project.version(1)['sha256']
        project.patch(0x10000 + 45, '08', version=1)
        assert project.version(1)['sha256'] == parent
    with SourceCatalog.create(tmp_path / 'sources.sqlite') as catalog:
        snapshot = catalog.import_tree(root, ['src/DEMO.C'], 'repo', 'v1', 'v1', 'reconstructed-source',
                                       target_path=original)['id']
        build = catalog.register_build(snapshot, directory, original)
        entity = catalog.entities(name='f')['items'][0]['id']
        result = catalog.map_native(entity, build['id'], directory, original, project=root / 'resident.fdb')
        assert catalog.map_native(entity, build['id'], directory, original, project=root / 'resident.fdb') == result
        endpoint = result['document']['analysis_endpoint']
        assert endpoint['document']['source']['version'] == 1
        assert endpoint['document']['source']['source_sha256'] == hashlib.sha256(image.read_bytes()).hexdigest()
        assert result['document']['original_sha256'] == hashlib.sha256(original.read_bytes()).hexdigest()
        with Project(root / 'resident.fdb') as reopened:
            assert reopened.snippet_info(endpoint['id'])['id'] == endpoint['id']
        with Project.create(root / 'packed.fdb', original):
            pass
        with pytest.raises(ValueError, match='derived resident'):
            catalog.map_native(entity, build['id'], directory, original, project=root / 'packed.fdb')
