"""Static contract for the authored paged/LDT LE native carrier."""
import os
import shutil

import pytest

from fdisbull.le import load_runtime_le_carrier
from support.qemu_dos_le_fixture import build_paged_ldt_fixture


@pytest.mark.parametrize("paging,ldt", [(False, False), (False, True),
                                         (True, False), (True, True)])
def test_paged_ldt_carrier_declares_nonidentity_pages_and_cross_page_fixup(tmp_path, paging, ldt):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if nasm is None:
        pytest.skip("Supply NASM for the authored paged/LDT carrier")
    fixture = build_paged_ldt_fixture(tmp_path, nasm, paging=paging, ldt=ldt)
    image = load_runtime_le_carrier(fixture["path"].read_bytes())
    assert fixture["carrier"] == "mz-bw-mz-le-" + ("paged" if paging else "flat") + ("-ldt" if ldt else "-gdt")
    assert fixture["page_map"] == ((1, 2), (2, 1), (3, 3), (4, 4))
    assert fixture["ldt_code_selector"] == (0x0c if ldt else None)
    assert fixture["entry_address"] == 0x120000 + 4094
    assert fixture["entry_ip"] == (4094 if ldt else 0x120000 + 4094)
    assert fixture["counter_address"] == 0x130080
    assert fixture["code_physical"] == ((0x200000, 0x205000, 0x20A000) if paging else
                                         (0x120000, 0x121000, 0x122000))
    assert fixture["data_physical"] == (0x210000 if paging else 0x130000)
    fixups = image.metadata["le"]["fixups"]
    assert len(fixups) == 10
    assert [row["page_source_offset"] for row in fixups[:2]] == [4095, -1]
    assert fixups[1]["duplicate_of"] == 0
    assert fixups[0]["target_address"] == 0x20000 + 128
    assert fixups[0]["file_offset"] is None
    assert [part["size"] for part in fixups[0]["file_fragments"]] == [1, 3]
    assert len(fixture["witness_sites"]) == 8
    assert all(row["source_type"] == "offset32" for row in fixups)
    assert image.regions[0].data[4094:4104] == (
        b"\xb8" + (0x20000 + 128).to_bytes(4, "little") + b"\xff\x00\xeb\xf7\x90"
    )

    # The source matcher masks loader relocations; the stopped 96-byte
    # window must nevertheless identify exactly one original code offset.
    from fdisbull.qemu_dos_le_match import _Budget, masked_window_offsets
    original = image.regions[0].data
    window = bytearray(original[4094:4094 + 96])
    window[1:5] = fixture["counter_address"].to_bytes(4, "little")
    ranges = [(row["source_offset"], row["source_offset"] + row["width"])
              for row in fixups if row["source_object"] == 1]
    assert masked_window_offsets(original, bytes(window), ranges,
                                 _Budget(None, 524288, 16777216),
                                 backed=[(0, len(original))]) == {4094}
    source = (tmp_path / "le-paged-ldt-bootstrap.asm").read_text()
    for site in (4095, *fixture["witness_sites"]):
        assert f"mov dword [{0x120000 + site:#x}]," in source
    if paging:
        assert "[0x301488]" in source
        assert source.index("mov cr0,eax", source.index("mov cr3,eax")) < source.index("mov dword [0x120fff]")
    assert image.regions[1].data[:64] == bytes((0x40 + i * 3) & 0xff for i in range(64))
