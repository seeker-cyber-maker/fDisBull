"""Invented MADS resources; no original game content or execution oracle."""
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from fdisbull.decoder_modules import analyze_input, builtin_registry, lift_input
from fdisbull.mads_processor import (COMMANDS, MODULE, PROFILE, Conversation,
                                     MADSConversationModule, MADSConversationProcessor)
from fdisbull.mads_resources import (HagArchive, MadsPack, decode_fab, read_cnd)
from fdisbull.processor import Location


class FabWriter:
    """Authored encoder for explicit token fixtures, not an upstream compressor."""
    def __init__(self, shift=12):
        self.data = bytearray(b'FAB' + bytes([shift]) + b'\0\0')
        self.word, self.used = 4, 0

    def bit(self, value):
        self.data[self.word + self.used//8] |= value << (self.used % 8)
        self.used += 1
        if self.used == 16:
            self.word, self.used = len(self.data), 0
            self.data += b'\0\0'

    def literal(self, value):
        self.bit(1)
        self.data.append(value)

    def stop(self):
        self.bit(0); self.bit(1)
        self.data += b'\0\0\0'
        return bytes(self.data)


def literal_fab(data):
    writer = FabWriter()
    for value in data:
        writer.literal(value)
    return writer.stop()


def pack(parts, compressed=False):
    header = bytearray(b'MADSPACK 2.0\x1a\0' + struct.pack('<H', len(parts)) + bytes(160))
    payload = bytearray()
    for i, raw in enumerate(parts):
        encoded = literal_fab(raw) if compressed else raw
        struct.pack_into('<BBII', header, 16+10*i, int(compressed), 0, len(raw), len(encoded))
        payload += encoded
    return bytes(header + payload)


def expr(code=255, left=0, right=0, variable=False):
    out = struct.pack('<H', code)
    if code != 255:
        out += struct.pack('<Bh', int(variable), left)
        if code != 0:
            out += struct.pack('<Bh', 0, right)
    return out


def cnv(scripts=None, compressed=False, prefix=b''):
    if scripts is None:
        scripts = [b'\x09' + expr() + expr(0, 42) + b'\x02\0' + b'\x00' + expr()]
    code = prefix + b''.join(scripts)
    header = bytearray(150)
    struct.pack_into('<7H', header, 0, 1, len(scripts), 0, 0, 0, 0, 0)
    struct.pack_into('<II', header, 118, 0, len(code))
    dialogs = bytearray()
    offset = len(prefix)
    for script in scripts:
        dialogs += struct.pack('<hhHH', -1, -1, offset, len(script))
        offset += len(script)
    return pack([bytes(header), struct.pack('<HHhhh', 0, len(scripts), 0, 1, 0),
                 bytes(dialogs), b'', b'', b'', code], compressed)


def hag(members):
    header = bytearray(b'MADSCONCAT 1.0\x1a\0' + struct.pack('<H', len(members)))
    offset = 18+22*len(members)
    data = bytearray()
    for name, raw in members:
        header += struct.pack('<II14s', offset, len(raw), name.encode('ascii'))
        data += raw
        offset += len(raw)
    return bytes(header+data)


def cnd(imports=()):
    header = bytearray(120)
    struct.pack_into('<4H', header, 0, 65535, 1, 3, len(imports))
    # Saved workspace is not a trustworthy initial-state count table.
    header[12:20] = b'\xff'*8
    parts = [bytes(header)]
    if imports:
        parts.append(struct.pack('<'+'H'*len(imports), *imports))
    parts += [b'\0\0', b''.join(struct.pack('<HhH', 0, n, 0) for n in (-1, 0, 7))]
    return pack(parts)


@pytest.mark.parametrize('length', [0, 1, 14, 15, 16, 17, 31, 32, 33, 255, 1025])
def test_fab_literals_cross_control_refills(length):
    raw = bytes(i % 256 for i in range(length))
    encoded = literal_fab(raw)
    decoded, consumed = decode_fab(encoded+b'opaque', len(raw))
    assert decoded == raw and consumed == len(encoded)


@pytest.mark.parametrize('shift', [10, 11, 12, 13])
def test_fab_short_overlapping_copy(shift):
    w = FabWriter(shift); w.literal(65)
    for bit in (0, 0, 1, 1):w.bit(bit)  # short length 5, distance 1
    w.data.append(255)
    assert decode_fab(w.stop(), 6)[0] == b'AAAAAA'


@pytest.mark.parametrize('extended', [None, 2, 20, 254, 255])
def test_fab_long_overlapping_copy(extended):
    w = FabWriter();w.literal(66);w.bit(0);w.bit(1)
    w.data += bytes([255, 0xf0 if extended is not None else 0xf1])
    if extended is not None:w.data.append(extended)
    count = 3 if extended is None else (extended+1)&255
    assert decode_fab(w.stop(), count+1)[0] == b'B'*(count+1)


def test_fab_marker_does_not_emit_bytes():
    w=FabWriter();w.literal(67);w.bit(0);w.bit(1);w.data += b'\0\0\x01'
    assert decode_fab(w.stop(), 1)[0] == b'C'


@pytest.mark.parametrize('mutation', ['header','window','underflow','short','overflow','no_stop'])
def test_fab_malformed_and_limits(mutation):
    good=literal_fab(b'AB')
    if mutation=='header':bad=b'NO!'+good[3:];size=2
    elif mutation=='window':bad=good[:3]+b'\x09'+good[4:];size=2
    elif mutation=='short':bad=good[:5];size=2
    elif mutation=='no_stop':bad=good[:-1];size=2
    elif mutation=='overflow':bad=good;size=1
    else:
        w=FabWriter()
        for b in (0,0,0,0):w.bit(b)
        w.data.append(255);bad=w.stop();size=2
    with pytest.raises(ValueError):decode_fab(bad,size)


@pytest.mark.parametrize('size', [True, -1, 32*1024*1024+1])
def test_fab_output_limits(size):
    with pytest.raises(ValueError):decode_fab(literal_fab(b''),size)


@pytest.mark.parametrize('compressed', [False,True])
def test_pack_metadata_and_opaque_tail(compressed):
    raw=pack([b'authored',b''],compressed)+b'tail'
    parsed=MadsPack.read(raw)
    assert [s.data for s in parsed.sections]==[b'authored',b'']
    assert parsed.metadata()['opaque_tail_bytes']==4
    assert parsed.metadata()['source_sha256']==sha256(raw).hexdigest()


@pytest.mark.parametrize('mutation', ['signature','count','kind','extent','output_limit','stored_length'])
def test_pack_refuses_bad_layout(mutation):
    raw=bytearray(pack([b'abc']))
    if mutation=='signature':raw[0]=0
    elif mutation=='count':struct.pack_into('<H',raw,14,17)
    elif mutation=='kind':raw[16]=5
    elif mutation=='extent':struct.pack_into('<I',raw,22,999)
    elif mutation=='output_limit':struct.pack_into('<I',raw,18,0xffffffff)
    elif mutation=='stored_length':struct.pack_into('<I',raw,18,2)
    with pytest.raises(ValueError):MadsPack.read(bytes(raw))


def test_hag_duplicate_names_need_index_and_preserve_source():
    raw=hag([('SAME.CNV',cnv()),('same.cnv',b'other')])
    archive=HagArchive.read(raw)
    with pytest.raises(ValueError,match='ambiguous'):archive.select('same.cnv')
    assert archive.select(0)[1]==cnv() and archive.select(1)[1]==b'other'
    assert archive.metadata()['member_count']==2 and archive.source==raw
    with pytest.raises(ValueError):archive.select(True)


@pytest.mark.parametrize('mutation', ['signature','count','directory','extent','overlap','name','unterminated'])
def test_hag_rejects_malformed(mutation):
    raw=bytearray(hag([('A.CNV',b'abcd'),('B.CNV',b'efgh')]))
    if mutation=='signature':raw[0]=0
    elif mutation=='count':struct.pack_into('<H',raw,16,65535)
    elif mutation=='directory':struct.pack_into('<I',raw,18,0)
    elif mutation=='extent':struct.pack_into('<I',raw,22,500)
    elif mutation=='overlap':struct.pack_into('<I',raw,40,64)
    elif mutation=='name':raw[26:30]=b'../x'
    else:raw[26:40]=b'x'*14
    with pytest.raises(ValueError):HagArchive.read(bytes(raw))


@pytest.mark.parametrize('imports',[(),(0,2)])
def test_cnd_defaults_never_bind_runtime_pointers(imports):
    result=read_cnd(cnd(imports))
    assert result['imports']==list(imports)
    assert [v['value'] for v in result['variables']]==[-1,0,7]
    assert all(not v['live_pointer_bound'] for v in result['variables'])
    assert result['opaque_header_bytes']==112 and result['runtime_state'] is False
    with pytest.raises(ValueError):read_cnd(cnd((4,)))


@pytest.mark.parametrize('opcode', list(COMMANDS))
def test_every_known_command_has_exact_span(opcode):
    encoded=bytes([opcode])
    encoded += expr()*(0 if opcode==6 else 3 if opcode==7 else 2 if opcode==9 else 1)
    if opcode in (1,2,3):encoded+=b'\x02\xff\xff\x03\0'
    elif opcode in (4,5):encoded+=b'\x02\x01\x02\x03\x04\0\x05\0\x06\0'
    elif opcode in (8,9):encoded+=b'\0\0'
    opened=MADSConversationModule().open(cnv([encoded]))
    decoded=opened.processor.decode(opened.program,opened.entry)
    assert decoded.facts['size']==len(encoded)
    assert decoded.facts['bytes']==encoded.hex() and decoded.facts['opcode']==opcode
    assert decoded.facts['qualification']=='encoded_instruction_facts_only'
    result=analyze_input(opened)
    assert result['runtime_execution'] is False
    if opcode==255:assert not result['complete']


@pytest.mark.parametrize('operation', [*range(14),255])
def test_expression_operands_and_ids_are_not_silently_evaluated(operation):
    encoded=b'\x09'+expr(operation,left=3,right=-7,variable=True)+expr(0,11)+b'\x02\0'
    opened=MADSConversationModule().open(cnv([encoded]))
    row=analyze_input(opened)['instructions'][0]['facts']
    assert row['conditions'][0]['operation']==operation
    assert row['conditions'][0]['evaluated'] is False
    assert row['variable_reads']==([] if operation==255 else [3])
    assert row['variable_writes']==[2]


@pytest.mark.parametrize('script',[b'\x10',b'\x09',b'\x00\x00',b'\x00\x00\x10',b'\x02'+expr()+b'\x02\x00'])
def test_unknown_and_truncated_commands_refuse(script):
    with pytest.raises(ValueError):MADSConversationModule().open(cnv([script]))


def test_goto_targets_use_global_section_offsets_but_must_stay_in_dialog():
    # One conditional branch, followed by END. Prefix must not be decoded.
    script=b'\x08'+expr()+struct.pack('<H',12)+b'\0'+expr()
    opened=MADSConversationModule().open(cnv([script],prefix=b'unknown'))
    result=analyze_input(opened)
    assert result['entry']['offset']==7 and result['complete']
    assert result['instructions'][0]['successors'][0]['target']['offset']==12
    bad=b'\x08'+expr()+struct.pack('<H',8)+b'\0'+expr()
    result=analyze_input(MADSConversationModule().open(cnv([bad],prefix=b'unknown')))
    assert not result['complete'] and result['issues'][0]['kind']=='unresolved_successor'


def test_no_cross_dialog_flow_and_budget_is_not_completeness():
    first=b'\x08'+expr()+b'\x05\0'
    opened=MADSConversationModule().open(cnv([first,b'\0'+expr()]))
    assert not analyze_input(opened)['complete']
    opened=MADSConversationModule().open(cnv())
    assert not analyze_input(opened,max_instructions=1)['complete']
    with pytest.raises(ValueError):opened.processor.decode(opened.program,Location(opened.entry.space,1))
    with pytest.raises(ValueError):opened.processor.decode(opened.program,Location('native.flat',0))


def test_bindings_capture_container_occurrence_and_isolate_returned_facts(tmp_path):
    p=tmp_path/'archive.hag';p.write_bytes(hag([('DIALOG.CNV',cnv()),('OTHER',b'one')]))
    registry=builtin_registry()
    first=registry.open(MODULE,p,member='DIALOG.CNV')
    before=analyze_input(first)
    p.write_bytes(hag([('DIALOG.CNV',cnv()),('OTHER',b'two')]))
    second=registry.open(MODULE,p,member='DIALOG.CNV')
    assert first.entry==second.entry and first.identity!=second.identity
    p.unlink()
    assert analyze_input(first)==before
    changed=first.processor.decode(first.program,first.entry)
    changed.facts['conditions'].clear()
    assert analyze_input(first)==before
    forged=replace(first,source_json=json.dumps(dict(first.source,source_sha256='0'*64)))
    with pytest.raises(ValueError):analyze_input(forged)
    with pytest.raises(ValueError,match='lifter'):lift_input(first,initial_state={})


@pytest.mark.parametrize('index', [True,-1,2,1.5])
def test_invalid_dialog_index_refuses(index):
    with pytest.raises(ValueError):MADSConversationModule().open(cnv(),function_index=index)


def test_cnv_rejects_wrong_profile_cnd_and_bad_counts():
    with pytest.raises(ValueError):MADSConversationModule().open(cnv(),profile='agi')
    with pytest.raises(ValueError):MADSConversationModule().open(cnd())
    with pytest.raises(ValueError):MADSConversationModule().open(cnv([b'']))
    parts=[s.data for s in MadsPack.read(cnv()).sections]
    header=bytearray(parts[0]);header[12]=6;parts[0]=bytes(header)
    with pytest.raises(ValueError):Conversation.read(pack(parts))


def test_standard_json_and_cli_catalog_without_project(tmp_path,capsys):
    from fdisbull.cli import main,respond
    p=tmp_path/'authored.cnv';p.write_bytes(cnv())
    response=respond({'method':'module-analyze','params':{'module':MODULE,'path':str(p)}},
                     default_project=str(tmp_path/'not-created.fdb'))
    assert response['ok'] and response['result']['complete'] and not (tmp_path/'not-created.fdb').exists()
    assert main(['module-analyze',MODULE,str(p)])==0
    assert json.loads(capsys.readouterr().out)['result']['module']['identity']==MODULE


def test_no_site_packages_no_native_decoder_required(tmp_path):
    p=tmp_path/'authored.cnv';p.write_bytes(cnv(compressed=True))
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'),PYTHONDONTWRITEBYTECODE='1')
    r=subprocess.run([sys.executable,'-B','-S','-m','fdisbull','request',
                      json.dumps({'method':'module-analyze','params':{'module':MODULE,'path':str(p)}})],
                     env=env,text=True,capture_output=True,timeout=20)
    assert r.returncode==0,r.stderr
    assert json.loads(r.stdout)['result']['complete']


def test_standalone_inspection_and_source_refusal(tmp_path,capsys):
    from fdisbull.mads_processor import main
    p=tmp_path/'authored.cnv';p.write_bytes(cnv())
    assert main(['inspect',str(p)])==0
    assert json.loads(capsys.readouterr().out)['result']['counts']['dialogs']==1
    assert main(['analyze',str(p)])==0
    assert json.loads(capsys.readouterr().out)['result']['complete']
    link=tmp_path/'link';link.symlink_to(p)
    assert main(['inspect',str(link)])==1
    assert json.loads(capsys.readouterr().out)['ok'] is False


def test_mads_guidance_is_in_an_admitted_bundled_reference():
    from fdisbull.cli import respond
    response=respond({'method':'agent-skill','params':{'reference':'references/media-modules.md'}})
    assert response['ok']
    text=response['result']['files']['references/media-modules.md']
    assert '## MADS conversations and containers' in text and MODULE in text
    assert 'static conversation processor' in text and 'not a playable MADS engine' in text
