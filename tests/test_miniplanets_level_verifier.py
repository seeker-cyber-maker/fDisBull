"""Receipt guards are contract checks, not simulated emulator qualification."""
from pathlib import Path
import json
import runpy
from types import SimpleNamespace
import pytest

V = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/verify_miniplanets_level.py'))


@pytest.mark.parametrize('bad_field', ['core_sha256', 'rom_sha256'])
def test_host_rejects_receipt_identity_drift(tmp_path, monkeypatch, bad_field):
    rom=tmp_path/'authored.nes';rom.write_bytes(b'authored fixture')
    expected=V['sha'](rom.read_bytes());out=tmp_path/'run'
    def fake_run(*args, **kwargs):
        out.mkdir()
        receipt={'core_sha256':V['NES_SHA'],'rom_sha256':expected}
        receipt[bad_field]='0'*64
        (out/'receipt.json').write_text(json.dumps(receipt))
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(V['subprocess'],'run',fake_run)
    with pytest.raises(AssertionError,match='receipt identity'):
        V['host']('qualified-core',rom,'nes',10,[],[],out,expected)


def test_host_refuses_rom_drift_before_launch(tmp_path, monkeypatch):
    rom=tmp_path/'authored.nes';rom.write_bytes(b'changed fixture')
    def forbidden(*args, **kwargs):raise AssertionError('launch should not happen')
    monkeypatch.setattr(V['subprocess'],'run',forbidden)
    with pytest.raises(AssertionError,match='ROM changed before'):
        V['host']('qualified-core',rom,'nes',10,[],[],tmp_path/'run','0'*64)
