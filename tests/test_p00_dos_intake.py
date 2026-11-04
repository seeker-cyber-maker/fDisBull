"""No proprietary binaries. Synthetic P00 admission, identity and refusal tests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import pytest

SRC = Path(__file__).resolve().parents[1] / 'scripts' / 'p00_dos_intake.py'
SPEC = importlib.util.spec_from_file_location('p00_dos_intake', SRC)
p00 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p00)


@pytest.mark.parametrize('s', [
    '', '../x', 'game/../../hello.com', '/absolute', 'C:/escape',
    'game\\nested', 'GAME//extra', 'game/\x00evil',
])
def test_bad_paths_fail_closed(s):
    with pytest.raises(p00.IntakeRefused):
        p00.safe_name(s)


def test_role_classifier_is_conservative():
    assert p00.role('GAME/HELLO.COM') == 'game_candidate'
    assert p00.role('DOSBOX/DOSBox.exe') == 'distribution_support'
    assert p00.role('__support/launcher.conf') == 'distribution_support'
    assert p00.role('manual.pdf') == 'documentation'
    assert p00.role('unknown.data') == 'game_candidate'


def mz_image(secondary=None):
    b = bytearray(320)
    b[0:2] = b'MZ'
    if secondary:
        b[60:64] = struct.pack('<I', 128)
        b[128:128 + len(secondary)] = secondary
        if secondary == b'PE\0\0':
            b[128 + 24:128 + 26] = b'\x0b\x01'
    return bytes(b)


@pytest.mark.parametrize('payload,suffix,expected', [
    (mz_image(), '.exe', 'DOS-MZ-candidate'),
    (mz_image(b'NE'), '.exe', 'Win16-NE'),
    (mz_image(b'PE\0\0'), '.exe', 'PE32-or-PE'),
    (b'\xB8\x00\x4c\xcd\x21', '.com', 'DOS-COM-candidate-raw'),
    (b'unrecognized', '.exe', 'unknown-executable-format'),
])
def test_header_classification_does_not_decode_code(tmp_path, payload, suffix, expected):
    p = tmp_path / ('target' + suffix)
    p.write_bytes(payload)
    assert p00.executable_format(p) == expected


def test_verify_extraction_rejects_stale_files_and_extra_members(tmp_path, monkeypatch):
    installer = tmp_path / 'installer.exe'; installer.write_bytes(b'authored input')
    folder = tmp_path / 'private'; (folder / 'GAME').mkdir(parents=True)
    content = b'authored COM bytes'; f = folder / 'GAME' / 'HELLO.COM'; f.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    upstream = hashlib.sha256(installer.read_bytes()).hexdigest()
    listing = {'files': ['GAME/HELLO.COM'], 'source_sha256': upstream}
    monkeypatch.setattr(p00, 'list_gog', lambda path: listing)
    manifest = {'format':'fdisbull-gog-unpack-1', 'extractor': {'implementation':'fdisbull-native-inno'}, 'source_sha256': upstream, 'include': [],
                'files': [{'path': 'GAME/HELLO.COM','size':len(content),'sha256':sha}]}
    (folder / p00.MANIFEST).write_text(json.dumps(manifest))
    receipt, mode = p00.verify_extraction(installer, folder)
    assert mode == 'verified_reuse' and len(receipt['files']) == 1
    f.write_bytes(b'tampered')
    with pytest.raises(p00.IntakeRefused):p00.verify_extraction(installer, folder)
    f.write_bytes(content)
    extra = folder / 'GAME' / 'surprise'; extra.write_bytes(b'x')
    with pytest.raises(p00.IntakeRefused):p00.verify_extraction(installer, folder)


def test_verify_extraction_rejects_symlink_without_following(tmp_path, monkeypatch):
    installer = tmp_path / 'installer.exe';installer.write_bytes(b'x')
    folder = tmp_path / 'private';folder.mkdir()
    (folder / 'bad').symlink_to(installer)
    sha = hashlib.sha256(b'x').hexdigest()
    monkeypatch.setattr(p00, 'list_gog', lambda path: {'files':['bad'], 'source_sha256':sha})
    (folder / p00.MANIFEST).write_text(json.dumps({
        'format':'fdisbull-gog-unpack-1','extractor':{'implementation':'fdisbull-native-inno'}, 'source_sha256':sha,'include':[], 'files':[{'path':'bad','size':1,'sha256':sha}]}))
    with pytest.raises(p00.IntakeRefused):p00.verify_extraction(installer,folder)


def mock_disc(monkeypatch, volume='AUTHORED'):
    sector_acc = {'declared_volume_sectors':2,'data_track_program_sectors':3}
    def fake(path, **kwargs):
        return {'valid':True,'complete':True,'data_tracks':[{'mode':'MODE1/2352',
            'filesystem':{'volume_id':volume,'valid':True,'complete':True,'entries':[
                {'kind':'directory','path':'/FIXTURE','size':2048,'extent_lba':0,'extent_sectors':1},
                {'kind':'file','path':'/GAME/HELLO.COM;1','size':5,'extent_lba':1,'extent_sectors':1,'available':True}]},
            'sector_accounting':sector_acc}]}
    monkeypatch.setattr(p00, 'inspect_disc_path', fake)


def test_disc_member_hash_and_unclassified_tail(tmp_path, monkeypatch):
    mock_disc(monkeypatch)
    payload = b'\xB8\x00\x4C\xCD\x21'
    raw = bytearray(3*2352)
    for i in range(3):raw[i*2352:i*2352+12] = b'\x00' + b'\xff'*10 + b'\x00';raw[i*2352+15] = 1
    raw[2352+16:2352+16+len(payload)] = payload
    image = tmp_path / 'AUTHORED.GOG';image.write_bytes(raw)
    sha = hashlib.sha256(payload).hexdigest()
    sums,files = p00.index_iso(image,[{'path':'GAME/HELLO.COM','size':5,'sha256':sha}])
    assert sums['primary_tree_files'] == 1
    assert sums['matches_loose_by_content'] == 1
    assert sums['remaining_unclassified_sectors'] == 1
    assert not sums['audio_validated'] and not sums['track_layout_known']
    assert files[0]['sha256'] == sha
    raw[2352:2352+12] = b'corrupted!!!'
    image.write_bytes(raw)
    with pytest.raises(p00.IntakeRefused):p00.index_iso(image,[])


def test_public_aggregate_excludes_private_member_paths():
    receipt={'target_label_user_declared':'authored','source':{
       'sha256':'a'*64,'size':128,'installer_profile':'fixture'},
       'extraction':{'files':1,'bytes':5,'role_file_counts':{'game_candidate':1},
                     'role_bytes':{'game_candidate':5}},
       'executable_candidates':[{'path':'SECRET/ORIGINAL.COM','format_hint':'DOS-COM-candidate-raw',
                                  'role':'game_candidate'}],
       'disc_images':[],'qualification':{'run_or_original_semantic_evidence':False},
       'metrics':{'total_wall_s':0.1, 'source_and_member_verification_s':0.08, 'nested_iso_metadata_and_member_hashing_s':0, 'classification_and_receipt_s':0.02}}
    summary=p00.public_summary(receipt)
    assert 'SECRET/' not in json.dumps(summary)
    assert summary['executable_summary']=={'DOS-COM-candidate-raw':1}
    assert not summary['qualification']['run_or_original_semantic_evidence']


def test_direct_raw_dos_fixture_uses_same_contract(tmp_path):
    target=tmp_path/'HELLO.COM';target.write_bytes(b'\xB8\x00\x4C\xCD\x21')
    r=p00.intake_raw('raw-control',target)
    assert r['source']['kind']=='direct-dos-artifact'
    assert r['extraction']['files']==1
    assert r['executable_candidates'][0]['format_hint']=='DOS-COM-candidate-raw'
    assert r['qualification']['run_or_original_semantic_evidence'] is False
    assert p00.public_summary(r)['source_kind']=='direct-dos-artifact'


def test_direct_raw_dos_refuses_unqualified_binary(tmp_path):
    target=tmp_path/'NOTDOS.EXE';target.write_bytes(b'unknown bytes')
    with pytest.raises(p00.IntakeRefused):p00.intake_raw('unknown',target)