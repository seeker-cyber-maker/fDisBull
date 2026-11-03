import pytest
from fdisbull.nes_multicart import build_multicart, inspect_multicart_path, multicart_profiles


def rom(marker=1, flag=0):
    prg=bytearray(32768);prg[:8]=bytes([0xa9,marker,0x85,0,0x4c,4,0x80,0]);prg[-6:]=b'\x00\x80'*3
    return b'NES\x1a'+bytes([2,1,flag,0])+bytes(8)+prg+bytes(8192)


def test_build_two_attested_games_and_reject_mismatch(tmp_path):
    a,b=tmp_path/'a.nes',tmp_path/'b.nes';a.write_bytes(rom(1));b.write_bytes(rom(2))
    with pytest.raises(ValueError,match='attest'):build_multicart([a,b],output=tmp_path/'x')
    m=build_multicart([a,b],output=tmp_path/'ok',authored_compatible=True)
    p=tmp_path/'ok'/'program.nes';info=inspect_multicart_path(p)
    assert info['mapper']==225 and info['prg_rom_bytes']==131072 and info['chr_rom_bytes']==32768
    assert m['games']==2 and p.read_bytes()[16+32768:16+65536]==a.read_bytes()[16:32784]
    assert p.read_bytes()[16+131072+8192:16+131072+16384] == a.read_bytes()[32784:]
    assert p.read_bytes()[16+131072+16384:16+131072+24576] == b.read_bytes()[32784:]
    assert multicart_profiles()['profiles'][0]['game_count']==2
    b.write_bytes(rom(2,1))
    with pytest.raises(ValueError,match='mirroring'):build_multicart([a,b],output=tmp_path/'bad',authored_compatible=True)


def test_unsupported_inputs_are_rejected(tmp_path):
    a,b=tmp_path/'a.nes',tmp_path/'b.nes';a.write_bytes(rom());b.write_bytes(rom(2,0x20))
    with pytest.raises(ValueError):build_multicart([a,b],output=tmp_path/'bad',authored_compatible=True)
    assert not (tmp_path/'bad').exists()


def test_changed_input_during_build_is_rejected_and_output_removed(tmp_path, monkeypatch):
    from fdisbull import nes_multicart
    a, b = tmp_path/'a.nes', tmp_path/'b.nes'
    a.write_bytes(rom(1)); b.write_bytes(rom(2))
    original = nes_multicart._read_bounded
    calls = 0
    def mutate_on_readback(path, limit, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            a.write_bytes(rom(9))
        return original(path, limit, **kwargs)
    monkeypatch.setattr(nes_multicart, '_read_bounded', mutate_on_readback)
    with pytest.raises(ValueError, match='changed'):
        build_multicart([a,b], output=tmp_path/'bad', authored_compatible=True)
    assert not (tmp_path/'bad').exists()
    assert not list(tmp_path.glob('.nes-multicart-*'))
