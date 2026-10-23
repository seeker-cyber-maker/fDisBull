"""Public loader/decoder checks with independent expected machine-code values."""
import hashlib
import shutil
import subprocess

import pytest

from fdisbull.decoder import decode
from fdisbull.loader import load_image
from fixtures_formats import macho_arm64, pe64


def test_pe64_maps_virtual_addresses_and_exported_function(tmp_path):
    source = tmp_path / "sample.exe"
    payload = pe64()
    source.write_bytes(payload)
    image = load_image(source)
    assert (image.format, image.arch, image.bits, image.entry) == ("PE", "x86", 64, 0x140001000)
    code = next(region for region in image.regions if region.name == ".text")
    assert code.start == 0x140001000 and code.executable and not code.writable
    assert code.data[:6] == bytes.fromhex("e80b000000c3")
    assert any(seed.address == 0x140001010 and seed.name == "helper" for seed in image.seeds)
    assert image.metadata["source_sha256"] == hashlib.sha256(payload).hexdigest()


def test_thin_macho_arm64_maps_entry_and_actual_instruction(tmp_path):
    source = tmp_path / "sample.macho"
    source.write_bytes(macho_arm64())
    image = load_image(source)
    assert (image.format, image.arch, image.bits, image.entry) == ("Mach-O", "arm64", 64, 0x100000100)
    code = next(region for region in image.regions if region.executable)
    offset = image.entry - code.start
    instruction = decode(code.data[offset:offset + 4], image.entry, image.arch, image.bits)
    assert instruction["flow"] == "call" and instruction["target"] == 0x100000108


def test_real_elf_retains_entry_and_named_function(tmp_path):
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("gcc is required to build the ELF fixture")
    assembly = tmp_path / "sample.s"
    assembly.write_text(".text\n.global _start\n.type _start,@function\n_start:\n call helper\n ret\n.type helper,@function\nhelper:\n mov $42,%eax\n ret\n")
    executable = tmp_path / "sample.elf"
    subprocess.run([compiler, "-nostdlib", "-no-pie", "-Wl,--build-id=none", str(assembly), "-o", str(executable)],
                   check=True, capture_output=True)
    image = load_image(executable)
    assert (image.format, image.arch, image.bits) == ("ELF", "x86", 64)
    assert any(seed.name == "helper" for seed in image.seeds)
    assert any(region.executable and region.start <= image.entry < region.start + len(region.data) for region in image.regions)


def test_raw16_and_provenance_digest(tmp_path):
    source = tmp_path / "sample.bin"
    payload = bytes.fromhex("e80100c3c3")
    source.write_bytes(payload)
    image = load_image(source, arch="x86", bits=16, base=0x100)
    assert (image.format, image.bits, image.entry) == ("raw", 16, 0x100)
    assert image.metadata["source_sha256"] == hashlib.sha256(payload).hexdigest()
    instruction = decode(image.regions[0].data, image.entry, image.arch, image.bits)
    assert (instruction["size"], instruction["flow"], instruction["target"]) == (3, "call", 0x104)


def test_x86_control_flow_and_rip_reference():
    instruction = decode(bytes.fromhex("e805000000"), 0x1000, "x86", 64)
    assert instruction["flow"] == "call" and instruction["target"] == 0x100A
    instruction = decode(bytes.fromhex("75fe"), 0x1000, "x86", 64)
    assert instruction["flow"] == "conditional" and instruction["target"] == 0x1000
    instruction = decode(bytes.fromhex("488b0520000000"), 0x1000, "x86", 64)
    assert instruction["flow"] == "next" and instruction["data_refs"] == [0x1027]
    assert decode(b"\xc3", 0x1000, "x86", 32)["flow"] == "return"


def test_indirect_and_segmented_far_branches_remain_unresolved():
    indirect = decode(bytes.fromhex("ff1500000000"), 0x1000, "x86", 64)
    assert (indirect["flow"], indirect["target"], indirect["data_refs"]) == ("indirect_call", None, [0x1006])
    far = decode(bytes.fromhex("ea34127856"), 0x1000, "x86", 16)
    assert far["flow"] == "indirect_jump" and far["target"] is None


def test_arm64_direct_conditional_and_return():
    call = decode(bytes.fromhex("02000094"), 0x1000, "arm64", 64)
    conditional = decode(bytes.fromhex("40000054"), 0x1000, "arm64", 64)
    assert (call["flow"], call["target"]) == ("call", 0x1008)
    assert (conditional["flow"], conditional["target"]) == ("conditional", 0x1008)
    assert decode(bytes.fromhex("c0035fd6"), 0x1000, "arm64", 64)["flow"] == "return"


def test_invalid_and_truncated_instructions_do_not_become_code():
    assert decode(b"\x0f", 0x1000, "x86", 64) is None
    assert decode(bytes.fromhex("0f3f"), 0x1000, "x86", 64) is None
    assert decode(b"\0\0", 0x1000, "arm64", 64) is None
    assert decode(bytes.fromhex("ffffffff"), 0x1000, "arm64", 64) is None
    assert decode(bytes.fromhex("c0035fd6"), 0x1001, "arm64", 64) is None


def test_malformed_mz_and_unknown_formats_fail_explicitly(tmp_path):
    source = tmp_path / "sample.exe"
    source.write_bytes(b"MZ" + bytes(62))
    with pytest.raises(ValueError, match="page count"):
        load_image(source)
    source.write_bytes(b"arbitrary text")
    with pytest.raises(ValueError, match="unsupported file format"):
        load_image(source)


def test_raw_address_and_alignment_boundaries(tmp_path):
    source = tmp_path / "sample.bin"
    source.write_bytes(bytes.fromhex("c0035fd6"))
    with pytest.raises(ValueError, match="aligned"):
        load_image(source, arch="arm64", base=1)
    with pytest.raises(ValueError, match="flat address space"):
        load_image(source, arch="x86", bits=16, base=0xFFFF)
    with pytest.raises(ValueError, match="outside"):
        load_image(source, arch="x86", entry=0x100)
    source.write_bytes(b"")
    with pytest.raises(ValueError, match="nonempty"):
        load_image(source, arch="x86")
