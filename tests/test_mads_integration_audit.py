"""Regression coverage for installed discovery, CLI parity and packaging fixes."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

import pytest
from test_mads_media_runtime import (sprite, tiles, tile_map, dsr, font, animation,
    dcl_literals, assignment)
from test_mads_processor import literal_fab, pack, hag, cnv, cnd
from fdisbull.mads_media_adapters import NAMES
from fdisbull.media import media_modules
from fdisbull.cli import main, parser


@pytest.mark.parametrize('adapter', sorted(NAMES))
def test_normal_cli_admits_every_registered_media_adapter(adapter, tmp_path, capsys):
    inputs={
        'fab':literal_fab(b'test'), 'pkware-dcl':dcl_literals(b'test'),
        'mads-hag':hag([('AUTHORED',b'test')]), 'mads-pack':pack([b'test']),
        'mads-sprite':sprite(), 'mads-tiles':tiles(), 'mads-depth':tiles(True),
        'mads-background':tiles(), 'mads-depth-map':tiles(True),
        'mads-mask':pack([b'\x80\x40']), 'mads-font':font(),
        'mads-dsr':dsr(), 'mads-animation':animation(),
    }
    path=tmp_path/'input';path.write_bytes(inputs[adapter])
    args=['--max-output-bytes','1048576','media-inspect',str(path),'--adapter',adapter]
    if adapter=='fab':args+=['--expected-size','4']
    if adapter=='mads-mask':args+=['--width','2','--height','2']
    if adapter in ('mads-background','mads-depth-map'):
        m=tmp_path/'map';m.write_bytes(tile_map());args+=['--map-path',str(m)]
    assert main(args)==0
    result=json.loads(capsys.readouterr().out)
    assert result['ok'],result
    assert result['result']['adapter']==adapter


def test_catalog_and_cli_choices_cannot_drift():
    for method in ('media-inspect','media-extract'):
        expected={m['name'] for m in media_modules()['modules'] if method in m['methods']}
        p=parser();subs=next(a for a in p._actions if hasattr(a,'choices') and isinstance(a.choices,dict))
        option=next(a for a in subs.choices[method]._actions if a.dest=='adapter')
        assert set(option.choices)==expected


def test_normal_cli_archive_index_and_private_export(tmp_path,capsys):
    tmp_path.chmod(0o700);p=tmp_path/'source.hag'
    p.write_bytes(hag([('S.SS',sprite()),('S.SS',sprite())]));before=p.read_bytes()
    out=tmp_path/'out'
    assert main(['media-extract',str(p),str(out),'--adapter','mads-sprite',
                 '--source-index','1','--member','indices'])==0
    r=json.loads(capsys.readouterr().out)
    assert r['ok'],r
    assert (out/'payload.bin').read_bytes()==b'\0\1\1\xff' and p.read_bytes()==before
    assert r['result']['inputs'][1]['member_index']==1


def test_normal_cli_map_and_source_index_zero(tmp_path,capsys):
    p=tmp_path/'tiles';p.write_bytes(hag([('A.TT',tiles())]))
    m=tmp_path/'map';m.write_bytes(hag([('A.MM',tile_map())]))
    assert main(['media-inspect',str(p),'--adapter','mads-background','--source-index','0',
                 '--map-path',str(m),'--map-index','0'])==0
    r=json.loads(capsys.readouterr().out);assert r['ok'],r
    assert len(r['result']['inputs'])==4


@pytest.mark.parametrize('flags',[['--source-index','0','--source-member','X'],['--map-index','0','--map-member','X']])
def test_cli_rejects_competing_selectors_before_reading(flags):
    with pytest.raises(SystemExit) as e:main(['media-inspect','not-opened','--adapter','mads-sprite',*flags])
    assert e.value.code==2


@pytest.mark.parametrize('adapter,data,expected',[('fab',literal_fab(b'a'),'fab'),
    ('mads-hag',hag([('X',b'a')]),'mads-hag'),('mads-pack',pack([b'a']),'mads-pack')])
def test_file_identify_routes_containers_without_decoding(tmp_path,adapter,data,expected,monkeypatch):
    from fdisbull.format_registry import identify_file
    from fdisbull import codec_fab, codec_dcl
    def forbidden(*a,**kw):raise AssertionError('Recognition must not decompress')
    monkeypatch.setattr(codec_fab,'decode_fab',forbidden)
    monkeypatch.setattr(codec_dcl,'decode_dcl',forbidden)
    p=tmp_path/'misleading.exe';p.write_bytes(data)
    r=identify_file(p)['identification']
    assert r['format_id']==expected and r['header_valid'] and not r['full_decode']
    assert adapter in {x['module_id'] for x in r['decoder_modules']}


def test_dcl_option_bytes_are_not_a_magic_signature(tmp_path):
    from fdisbull.format_registry import identify_file, format_catalog
    for i,raw in enumerate((b'\x00\x04',dcl_literals(b'test'))):
        p=tmp_path/str(i);p.write_bytes(raw)
        assert identify_file(p)['identification']['format_id'] is None
    d=next(x for x in format_catalog()['formats'] if x['format_id']=='pkware-dcl')
    assert d['signatures']==[]


@pytest.mark.parametrize('bad',[b'FAB',b'FAB\x09\0\0',b'MADSCONCAT 1.0\x1a\0\x01\0',b'MADSPACK 2.0\x1a\0\x01\0'])
def test_header_probe_rejects_incomplete_headers(tmp_path,bad):
    from fdisbull.format_registry import identify_file
    p=tmp_path/'x';p.write_bytes(bad)
    assert identify_file(p)['identification']['header_valid'] is False


def test_codecs_import_without_any_mads_or_native_dependency(tmp_path):
    code="""import sys
from fdisbull.codec_fab import decode_fab
from fdisbull.codec_dcl import decode_dcl
assert decode_dcl(bytes.fromhex('00048224258f807f'),13)[0]==b'AIAIAIAIAIAIA'
assert not any(x.startswith(('fdisbull.mads_', 'fdisbull.scummvm', 'fdisbull.processor')) for x in sys.modules)
print('independent')
"""
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    r=subprocess.run([sys.executable,'-S','-c',code],env=env,cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert r.returncode==0,r.stderr


def test_packaged_validator_reuse_preserves_fresh_dialog_initial_state(tmp_path):
    from fdisbull.mads_validation import validate
    from fdisbull.mads_runtime import ConversationRuntime
    from fdisbull.mads_resources import read_cnd
    raw=cnv([assignment(1),assignment(2)])
    from fdisbull.mads_resources import MadsPack
    parts=[part.data for part in MadsPack.read(cnd()).sections]
    header=bytearray(parts[0]);struct.pack_into('<H',header,2,2)
    parts[0]=bytes(header);parts[1]=bytes(4);defaults=pack(parts)
    (tmp_path/'authored.hag').write_bytes(hag([('CONV001.CNV',raw),('CONV001.CND',defaults)]))
    report=validate(tmp_path,synthetic_model=True)
    assert not report['errors'] and report['counts']['model_dialogs']==2
    states=[]
    for index in range(2):
        engine=ConversationRuntime(raw,defaults,external_values={i:0 for i in range(read_cnd(defaults)['variable_count'])},random_tape=[1]*1024)
        engine.start_dialog(index);engine.run(10000,timeout_ms=1000)
        states.append(hashlib.sha256(json.dumps(engine.snapshot(),sort_keys=True).encode()).hexdigest())
    assert report['model_state_digest']==hashlib.sha256(''.join(states).encode()).hexdigest()
