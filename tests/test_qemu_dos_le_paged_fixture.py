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


def test_tracking_carrier_contains_guest_owned_remap_selector_and_outside_cycle(tmp_path):
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if nasm is None:
        pytest.skip("Supply NASM for the authored tracking carrier")
    from support.qemu_dos_le_fixture import (
        PAGED_CODE_PHYSICAL, PAGED_LDT_CODE_SELECTOR, PAGED_TRACKING_CONTROLLER,
        PAGED_TRACKING_PHYSICAL, PAGED_TRACKING_SELECTOR_B, PAGED_TRACKING_TARGET,
    )

    fixture = build_paged_ldt_fixture(tmp_path, nasm, paging=True, ldt=True, tracking=True)
    image = load_runtime_le_carrier(fixture["path"].read_bytes())
    code = image.regions[0].data
    controller = code[PAGED_TRACKING_CONTROLLER:PAGED_TRACKING_CONTROLLER + 62]
    expected = (
        b"\x9a" + PAGED_TRACKING_TARGET.to_bytes(4, "little") + PAGED_LDT_CODE_SELECTOR.to_bytes(2, "little")
        + b"\xc7\x05" + (0x301484).to_bytes(4, "little") + (PAGED_TRACKING_PHYSICAL | 3).to_bytes(4, "little")
        + bytes.fromhex("0f20d8 0f22d8")
        + b"\x9a" + PAGED_TRACKING_TARGET.to_bytes(4, "little") + PAGED_LDT_CODE_SELECTOR.to_bytes(2, "little")
        + b"\x9a" + PAGED_TRACKING_TARGET.to_bytes(4, "little") + PAGED_TRACKING_SELECTOR_B.to_bytes(2, "little")
        + b"\xc7\x05" + (0x301484).to_bytes(4, "little") + (PAGED_CODE_PHYSICAL[1] | 3).to_bytes(4, "little")
        + bytes.fromhex("0f20d8 0f22d8")
        + b"\x9a" + (0x140000).to_bytes(4, "little") + (8).to_bytes(2, "little")
        + b"\xeb" + bytes([(-62) & 0xff])
    )
    assert len(expected) == 62
    assert controller == expected
    assert code[PAGED_TRACKING_TARGET:PAGED_TRACKING_TARGET + 2] == b"\x46\xcb"
    assert fixture["tracking_start_cs"] == PAGED_LDT_CODE_SELECTOR
    assert fixture["tracking_start_ip"] == PAGED_TRACKING_CONTROLLER
    assert fixture["entry_offset"] == PAGED_TRACKING_CONTROLLER
    assert fixture["tracking_start_pc"] == 0x120000 + PAGED_TRACKING_CONTROLLER
    assert fixture["tracking_target_physical"] == PAGED_CODE_PHYSICAL[1] + 0x400
    assert fixture["tracking_alternate_physical"] == PAGED_TRACKING_PHYSICAL + 0x400
    assert fixture["tracking_selector_b"] == PAGED_TRACKING_SELECTOR_B
    assert fixture["tracking_milestones"] == (
        (PAGED_LDT_CODE_SELECTOR, PAGED_TRACKING_CONTROLLER, 0x20a100),
        (PAGED_LDT_CODE_SELECTOR, PAGED_TRACKING_TARGET, 0x205400),
        (PAGED_LDT_CODE_SELECTOR, PAGED_TRACKING_TARGET, 0x215400),
        (PAGED_TRACKING_SELECTOR_B, PAGED_TRACKING_TARGET, 0x215400),
        (8, 0x140000, 0x140000),
    )
    bootstrap = (tmp_path / "le-paged-ldt-bootstrap.asm").read_text()
    assert "mov edi,0x215000" in bootstrap and "mov ecx,0x1000" in bootstrap
    assert "mov word [0x140000],0xcb47" in bootstrap

    # Recreate the guest's relocated LE code bytes and prove that every
    # retained in-LE instruction boundary has one source placement. The
    # outside GDT target is intentionally not present in the LE object.
    from fdisbull.qemu_dos_le_match import _Budget, masked_window_offsets
    runtime = bytearray(code)
    fixups = image.metadata["le"]["fixups"]
    for row in fixups:
        if row["source_object"] == 1 and row["source_type"] == "offset32":
            site = row["source_offset"]
            value = 0x130000 + row["target_offset"]
            runtime[site:site + 4] = value.to_bytes(4, "little")
    ranges = [(row["source_offset"], row["source_offset"] + row["width"])
              for row in fixups if row["source_object"] == 1]
    pcs = (0x1400, 0x1401, 0x2100, 0x2107, 0x2111, 0x2114,
           0x2117, 0x211e, 0x2125, 0x212f, 0x2132, 0x2135, 0x213c)
    for pc in pcs:
        observed = bytes(runtime[pc:pc + 96])
        assert len(observed) == 96
        assert masked_window_offsets(code, observed, ranges,
            _Budget(None, 524288, 16777216), backed=[(0, len(code))]) == {pc}
    outside = b"\x47\xcb" + bytes(94)
    assert masked_window_offsets(code, outside, ranges,
        _Budget(None, 524288, 16777216), backed=[(0, len(code))]) == set()
