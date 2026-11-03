"""Independent regression checks for the two-game NROM packer review."""
from pathlib import Path

import pytest

from fdisbull.nes_multicart import build_multicart


def _nrom(prg_byte: int, chr_byte: int) -> bytes:
    return (
        b"NES\x1a"
        + bytes((2, 1, 0, 0))
        + bytes(8)
        + bytes((prg_byte,)) * 32768
        + bytes((chr_byte,)) * 8192
    )


def test_game_prg_and_chr_images_remain_in_distinct_exact_banks(tmp_path):
    game1 = _nrom(0x31, 0x41)
    game2 = _nrom(0x32, 0x42)
    a, b = tmp_path / "a.nes", tmp_path / "b.nes"
    a.write_bytes(game1)
    b.write_bytes(game2)

    build_multicart((a, b), output=tmp_path / "cart", authored_compatible=True)
    image = (tmp_path / "cart" / "program.nes").read_bytes()

    assert len(image) == 16 + 4 * 32768 + 4 * 8192
    prg = image[16 : 16 + 4 * 32768]
    assert prg[:32768] != game1[16 : 16 + 32768]
    assert prg[32768:65536] == game1[16 : 16 + 32768]
    assert prg[65536:98304] == game2[16 : 16 + 32768]
    assert prg[98304:] == bytes(32768)

    chr = image[16 + 4 * 32768 :]
    assert chr[:8192] != game1[16 + 32768 :]
    assert chr[8192:16384] == game1[16 + 32768 :]
    assert chr[16384:24576] == game2[16 + 32768 :]
    assert chr[24576:] == bytes(8192)


def test_oversized_input_is_rejected_before_whole_file_read(tmp_path, monkeypatch):
    oversized = tmp_path / "oversized.nes"
    valid = tmp_path / "valid.nes"
    oversized.write_bytes(_nrom(0x31, 0x41) + b"x")
    valid.write_bytes(_nrom(0x32, 0x42))
    requested = oversized.resolve()
    read_bytes = Path.read_bytes

    def reject_unbounded_read(path):
        if path.resolve() == requested:
            raise AssertionError("oversized input reached Path.read_bytes")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_read)
    with pytest.raises(ValueError):
        build_multicart((oversized, valid), output=tmp_path / "cart", authored_compatible=True)
    assert not (tmp_path / "cart").exists()
