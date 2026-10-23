"""Public DOS integration: real segmented analysis, not a flat raw workaround."""
import json
from pathlib import Path
import struct
import subprocess
import sys

from fdisbull.project import Project
from fdisbull.cli import respond
from test_dos_loader import mz_file


def callback_mz():
    module=bytearray(256)
    module[:11]=bytes.fromhex('ba08008eda9a00000400c3')
    module[0x40:0x44]=bytes.fromhex('b82a00cb')
    module[0x50]=0xcb
    struct.pack_into('<HH',module,0x80,0x10,4)
    struct.pack_into('<HH',module,0x84,0x20,8)
    module[0xa0:0xa9]=b'DINOSAUR\0'
    return mz_file(bytes(module),relocations=[(1,0),(8,0),(0x82,0),(0x86,0)],ss=15,sp=16)


def test_segmented_entry_far_calls_and_relocated_callback_seeds(tmp_path):
    binary=tmp_path/'callbacks.exe';binary.write_bytes(callback_mz())
    with Project.create(tmp_path/'dos.fdb',binary) as p:
        first=p.analyze(max_instructions=1)
        assert not first['stable'] and first['pending']>0
        result=p.analyze()
        assert result['stable'] and result['pending']==0
        assert p.disassembly('1004:0000')['instructions'][0]['mnemonic']=='mov'
        assert p.disassembly('1004:0010')['instructions'][0]['mnemonic']=='retf'
        assert any(x['source_segmented_address']=='1000:0005' for x in p.xrefs('1004:0000'))
        segments={s['segment']:s for s in p.segments()}
        assert 'code' in segments['1004']['roles']
        assert 'data' in segments['1008']['roles'] and 'code' not in segments['1008']['roles']
        assert all(r['start']!='0x10080' for r in p.code_regions())
        assert p.analyze()['new_facts']==0
        assert p.analyze()['attempted']==0


def test_cs_aliases_and_global_labels_survive_restart(tmp_path):
    module=bytearray(64);module[:3]=bytes.fromhex('e90d00');module[16]=0xc3
    binary=tmp_path/'alias.exe';binary.write_bytes(mz_file(bytes(module)))
    project=tmp_path/'alias.fdb'
    with Project.create(project,binary) as p:
        assert p.analyze()['stable']
        assert p.analyze(start='1001:0000')['stable']
        p.annotate('1000:0010','shared_return',kind='name')
        assert p.disassembly('1000:0010')['instructions'][0]['name']=='shared_return'
        assert p.disassembly('1001:0000')['instructions'][0]['name']=='shared_return'
        snapshot=p.disassembly('0x10010')
        assert snapshot['instructions'][0]['alternative_contexts']
    binary.unlink()
    with Project(project) as p:
        assert p.disassembly('1001:0000')['instructions'][0]['name']=='shared_return'
        assert len(p.code_regions())==3


def test_ip_wrap_uses_cs_window_not_flat_fallthrough(tmp_path):
    module=bytearray(65536);module[0]=0xc3;module[-1]=0x90
    binary=tmp_path/'wrap.exe';binary.write_bytes(mz_file(bytes(module),ip=65535))
    with Project.create(tmp_path/'wrap.fdb',binary) as p:
        assert p.analyze()['stable']
        assert {r[0] for r in p.db.execute('SELECT address FROM instructions')}=={'000000000001ffff','0000000000010000'}


def test_conflicting_ds_paths_retain_both_segmented_references(tmp_path):
    module=bytearray(128)
    module[:18]=bytes.fromhex('7407b804008ed8eb05b805008ed8a10000c3')
    module[0x40:0x42]=b'\x11\x11';module[0x50:0x52]=b'\x22\x22'
    binary=tmp_path/'join.exe';binary.write_bytes(mz_file(bytes(module),relocations=[(3,0),(10,0)]))
    with Project.create(tmp_path/'join.fdb',binary) as p:
        assert p.analyze()['stable']
        refs=p.disassembly('1000:000e',lines=1)['instructions'][0]['references']
        assert {r['target'] for r in refs}=={'0x10040','0x10050'}
        state=json.loads(p.db.execute("SELECT registers FROM dos_states WHERE address='000000000001000e'").fetchone()[0])
        assert state['ds']==[0x1004,0x1005]
        assert 'primary_data_segment' not in p._dos_metadata(1)


def test_patch_relocated_memory_reconstructs_unrelocated_source_and_preserves_parent(tmp_path):
    binary=tmp_path/'patch.exe';binary.write_bytes(callback_mz())
    with Project.create(tmp_path/'patch.fdb',binary) as p:
        p.analyze()
        p.annotate('1004:0000','callee',kind='name')
        # Repoint callback from segment1004 to segment1000 using loaded bytes.
        p.patch('1008:0002',bytes.fromhex('0010').hex())
        assert p.analyze()['stable']
        row=p.db.execute('SELECT source_bytes FROM binary_info WHERE version=2').fetchone()
        assert struct.unpack_from('<H',bytes(row[0]),64+0x82)[0]==0
        assert struct.unpack_from('<H',p.regions(2)[0].data,0x82)[0]==0x1000
        assert struct.unpack_from('<H',p.regions(1)[0].data,0x82)[0]==0x1004
        assert p.disassembly('1004:0000',version=1)['instructions'][0]['name']=='callee'
        assert p._dos_metadata(2)['load_segment']==0x1000


def test_public_cli_load_segment_and_segment_inventory(tmp_path):
    binary=tmp_path/'public.exe';binary.write_bytes(callback_mz())
    project=tmp_path/'public.fdb'
    r=respond({'method':'import','params':{'path':str(binary),'project':str(project),'load_segment':0x2000}})
    assert r['ok'],r
    r=respond({'method':'analyze','params':{'project':str(project)}})
    assert r['ok'] and r['result']['stable'],r
    for method in ('segments','code-regions'):
        r=respond({'method':method,'params':{'project':str(project)}})
        assert r['ok'] and r['result'],r
    r=respond({'method':'disasm','params':{'project':str(project),'address':'2004:0000'}})
    assert r['ok'] and r['result']['instructions'][0]['segmented_address']=='2004:0000'
    output=tmp_path/'dos.svg'
    r=respond({'method':'render','params':{'project':str(project),'address':'2004:0000','output':str(output)}})
    assert r['ok'] and output.exists(),r


def test_explicit_dos_seed_is_decoded_before_existing_queue_with_one_instruction_budget(tmp_path):
    # An interactive debugger address must not sit behind older recursive work.
    module=bytearray(b'\x90'*128)
    module[0x60:0x64]=bytes.fromhex('b87856cb')
    binary=tmp_path/'SEED.EXE';binary.write_bytes(mz_file(bytes(module),ss=0,sp=0x100))
    path=tmp_path/'seed.fdb'
    with Project.create(path,binary) as p:
        p.analyze(max_instructions=1)
    # The old entry traversal persists across restart.
    with Project(path) as p:
        result=p.analyze(start='1000:0060',max_instructions=1)
        instruction=p.disassembly('1000:0060',lines=1)['instructions']
        assert instruction and instruction[0]['bytes']=='b87856'
        assert not result['stable'] and result['pending']>0
        # Prioritizing the explicit address does not discard older work.
        p.analyze(max_instructions=1)
        prior=p.disassembly('1000:0001',lines=1)['instructions']
        assert prior and prior[0]['bytes']=='90'
