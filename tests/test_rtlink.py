"""Authored MZ/RTLink structures; no original game data or runtime claims."""
from hashlib import sha256
import json
from pathlib import Path
import struct

import pytest

from fdisbull.rtlink import inspect_bytes, inspect_rtlink, export_rtlink, disassemble_rtlink


def authored(*, shortfall=0):
    # Header=64, resident=512; two relocations identify the table and a far call.
    data = bytearray(640 - shortfall)
    struct.pack_into('<14H', data, 0, 0x5a4d, 0, 1, 2, 4, 0, 0xffff, 0, 0xfffe, 0, 0, 0, 0x1c, 0)
    struct.pack_into('<HHHH', data, 0x1c, 0, 4, 3, 20)
    # RTLink table anchored at file 64+4*16+48 =176.
    for ordinal in range(2):
        at = 176 + ordinal*32
        struct.pack_into('<H', data, at, 0x40)
        struct.pack_into('<I', data, at+8, 512+ordinal*64)
        struct.pack_into('<H', data, at+14, ordinal+2)
        bank = 512+ordinal*64
        struct.pack_into('<8H', data, bank, 4, 2, 0x262, 0, 1, 0, 0, 0)
        struct.pack_into('<HH', data, bank+16, 4, 0)
        data[bank+32:bank+40] = b'\x55\x8b\xec\x90\x00\x00\x5d\xc3'
    data[300:306] = b'RTLink'
    # Dynamic thunk: alias1 resolves table ID2, offset0.
    data[384:398] = b'\x9a\x00\x00\x00\x00\xea\x00\x00\x00\x00\x01\x00\x00\x00'
    return bytes(data)


def test_bank_directory_relocations_and_thunks():
    data = authored(); r = inspect_bytes(data)
    assert r['overlay_count'] == 2 and r['relocation_count'] == 2
    assert r['overlays'][0]['file_offset'] == 544
    assert r['candidate_thunks'][0]['overlay_id'] == 2
    assert r['candidate_thunks'][0]['target_file_offset'] == 544
    assert r['source']['sha256'] == sha256(data).hexdigest()
    assert not r['input_executed'] and not r['output_runnable'] and not r['relocations_applied']


@pytest.mark.parametrize('shortfall', [1, 4, 15])
def test_partial_last_paragraph_is_explicit_and_never_exported_as_original(shortfall, tmp_path):
    data = authored(shortfall=shortfall); path = tmp_path/'GAME.EXE';path.write_bytes(data)
    r = inspect_bytes(data)
    assert r['unbacked_declared_bytes'] == shortfall
    assert r['all_declared_payload_bytes_backed'] is False
    assert r['overlays'][-1]['size'] == 32-shortfall
    receipt = export_rtlink(path, tmp_path/'derived')
    flat = (tmp_path/'derived/analysis-flat.bin').read_bytes()
    assert len(flat) == r['flat_size'] and flat[-(32-shortfall):] == data[-(32-shortfall):]
    assert receipt['runnable'] is False
    assert path.read_bytes() == data


def test_actual_existing_decoder_and_private_export(tmp_path):
    path = tmp_path/'GAME.EXE';path.write_bytes(authored())
    before = path.read_bytes()
    r = disassemble_rtlink(path, overlay=2, count=3)
    assert [x['mnemonic'] for x in r['instructions']] == ['push', 'mov', 'nop']
    assert r['instructions'][0]['file_offset'] == 544
    export_rtlink(path, tmp_path/'view')
    mapping = json.loads((tmp_path/'view/rtlink-map.json').read_text())
    flat = (tmp_path/'view/analysis-flat.bin').read_bytes()
    for m in mapping['mappings']:
        assert flat[m['flat_offset']:m['flat_offset']+m['size']] == before[m['file_offset']:m['file_offset']+m['size']]
    with pytest.raises(FileExistsError): export_rtlink(path,tmp_path/'view')
    assert path.read_bytes() == before


@pytest.mark.parametrize('damage', ['signature','id','zero_end','header','count','reloc','overlap','truncated','no_table'])
def test_malformed_or_unknown_layouts_fail_closed(damage):
    data = bytearray(authored())
    if damage == 'signature': data[300:306] = b'xxxxxx'
    if damage == 'id': struct.pack_into('<H', data, 176+14, 7)
    if damage == 'zero_end': data[240] = 1
    if damage == 'header': struct.pack_into('<H', data, 512+2, 5)
    if damage == 'count': struct.pack_into('<H', data, 512+8, 1000)
    if damage == 'reloc': struct.pack_into('<H', data, 512+16, 32)
    if damage == 'overlap': struct.pack_into('<I',data,208+8,512)
    if damage == 'truncated': data = data[:-17]
    if damage == 'no_table': struct.pack_into('<H',data,0x1c,1)
    with pytest.raises(ValueError): inspect_bytes(bytes(data))


def test_legacy_0x3c_not_unconditionally_a_new_header_pointer():
    data = bytearray(authored())
    # More relocation entries, all valid, extend across offset0x3c.
    struct.pack_into('<H',data,6,9)
    for i in range(2,9): struct.pack_into('<HH',data,0x1c+i*4,i*2,0)
    assert inspect_bytes(bytes(data))['overlay_count'] == 2


@pytest.mark.parametrize('overlay,offset,count', [(True,0,1),(999,0,1),(2,-1,1),(2,32,1),(2,0,257),(2,0,True)])
def test_disassembly_requires_backed_bank_and_budget(tmp_path,overlay,offset,count):
    p=tmp_path/'a.exe';p.write_bytes(authored())
    with pytest.raises(ValueError): disassemble_rtlink(p,overlay=overlay,offset=offset,count=count)


def test_source_links_and_git_exports_refused(tmp_path):
    p=tmp_path/'a.exe';p.write_bytes(authored())
    link=tmp_path/'link.exe';link.symlink_to(p)
    with pytest.raises(ValueError): inspect_rtlink(link)
    checkout=tmp_path/'checkout';checkout.mkdir();(checkout/'.git').mkdir()
    with pytest.raises(ValueError): export_rtlink(p,checkout/'bad')
