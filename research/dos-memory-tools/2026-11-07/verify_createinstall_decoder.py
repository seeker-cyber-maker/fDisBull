"""Compare the authored decoder with the installer's original x86 decoder.

Runs only VA401303 and its local helpers under Unicorn, in an authored flat
32-bit context. VirtualAlloc/VirtualFree are bounded emulated callbacks. No
Windows process is started, no installer entrypoint runs, and no original
program performs host I/O. Every stream is checked byte-for-byte, including its
consumed-bit count and explicit return endpoint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import unicorn
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_EFLAGS

from createinstall_decoder import decode
from intake_versions import executable_header
from unpack_win085 import EXPECTED_SHA256, EXPECTED_SIZE, inspect_installer, read_installer


IMAGE = 0x400000
INPUT = 0x200000
OUTPUT = 0x300000
RING = 0x500000
STATE = 0x600000
ALLOC = 0x700000
FREE = 0x700010
RETURN = 0x700020
STACK = 0x800000
START = 0x401303
MAX_INSTRUCTIONS = 20_000_000
TIMEOUT_MICROSECONDS = 10_000_000
MAX_INVENTORY_BYTES = 128 * 1024
STREAM_FIELDS = ("name", "compressed_start", "compressed_bytes", "compressed_bits",
                 "decoded_size", "sha256")


def validate_inventory(supplied: dict, canonical: dict) -> list[dict]:
    """Require complete coverage of the independently re-parsed container.

    An empty or duplicated stream list is not an all-stream witness. Metadata
    from the JSON never supplies emulation allocation sizes or slice bounds;
    the returned rows come from the complete pinned-container parse.
    """
    if not isinstance(supplied, dict):
        raise ValueError("Inventory must be an object")
    for field in ("schema", "source", "final_offset", "file_length",
                  "decoded_member_bytes", "declared_uncompressed"):
        if supplied.get(field) != canonical[field]:
            raise ValueError("Inventory/container identity or extent mismatch: " + field)
    rows = supplied.get("streams")
    expected = canonical["streams"]
    if not isinstance(rows, list) or len(rows) != 9 or len(expected) != 9:
        raise ValueError("Inventory must cover all nine installer streams exactly once")
    for actual, reference in zip(rows, expected):
        if not isinstance(actual, dict) or any(
            type(actual.get(key)) is not type(reference[key]) or actual[key] != reference[key]
            for key in STREAM_FIELDS
        ):
            raise ValueError("Inventory stream identity, order, or extent mismatch")
    return expected


def aligned(size: int) -> int:
    return max(4096, (size + 4095) & -4096)


def run_original(installer: bytes, compressed: bytes, expected_length: int) -> dict:
    if len(installer) != EXPECTED_SIZE or hashlib.sha256(installer).hexdigest() != EXPECTED_SHA256:
        raise ValueError("Wrong installer identity")
    if not 0 < len(compressed) <= EXPECTED_SIZE or type(expected_length) is not int or not 0 < expected_length <= 1024 * 1024:
        raise ValueError("Original decoder input/output budget exceeded")
    machine = Uc(UC_ARCH_X86, UC_MODE_32)
    machine.mem_map(IMAGE, 0xA000)
    machine.mem_write(IMAGE, installer[:1024])
    for section in executable_header(installer)["pe_section_table"]:
        begin = section["raw_offset"]
        machine.mem_write(IMAGE + section["rva"], installer[begin:begin + section["raw_size"]])
    machine.mem_map(INPUT, aligned(len(compressed)))
    machine.mem_write(INPUT, compressed)
    machine.mem_map(OUTPUT, aligned(expected_length))
    machine.mem_map(RING, aligned(21903))
    machine.mem_map(STATE, 4096)
    machine.mem_map(ALLOC, 4096)
    machine.mem_map(STACK, 65536)

    def u32(address: int) -> int:
        return struct.unpack("<I", machine.mem_read(address, 4))[0]

    def set32(address: int, value: int) -> None:
        machine.mem_write(address, struct.pack("<I", value))

    # Exact callback setup recovered from the wrapper before its decoder call.
    for address, value in ((0x4035CC, INPUT), (0x4030C8, OUTPUT),
                           (0x4047B4, 0x401000), (0x4047B8, 0x40101F),
                           (0x4047BC, 0x40103F), (0x4047C0, 0),
                           (0x4060CC, ALLOC), (0x4060C4, FREE)):
        set32(address, value)
    esp = STACK + 0xFF00
    set32(esp, RETURN)
    set32(esp + 4, STATE)
    machine.reg_write(UC_X86_REG_ESP, esp)
    machine.reg_write(UC_X86_REG_EFLAGS, 2)
    calls = []

    def callback(uc: Uc, address: int, size: int, _) -> None:
        stack = uc.reg_read(UC_X86_REG_ESP)
        destination = u32(stack)
        if address == ALLOC:
            arguments = [u32(stack + 4 + 4 * i) for i in range(4)]
            if arguments != [0, 21903, 0x3000, 4]:
                raise ValueError("Unexpected VirtualAlloc request")
            uc.reg_write(UC_X86_REG_EAX, RING)
            consumed = 20
        elif address == FREE:
            arguments = [u32(stack + 4 + 4 * i) for i in range(3)]
            if arguments != [RING, 0, 0x8000]:
                raise ValueError("Unexpected VirtualFree request")
            uc.reg_write(UC_X86_REG_EAX, 1)
            consumed = 16
        else:
            raise ValueError("Unexpected external callback")
        calls.append({"address": hex(address), "arguments": arguments})
        uc.reg_write(UC_X86_REG_ESP, stack + consumed)
        uc.reg_write(UC_X86_REG_EIP, destination)

    def fail_callback(uc, address, size, _):
        raise ValueError("Original decoder invoked its error callback")

    def check_input(uc, access, address, size, value, _):
        if address + size > INPUT + len(compressed):
            raise ValueError("Original decoder read beyond compressed stream")

    def check_output(uc, access, address, size, value, _):
        if address + size > OUTPUT + expected_length:
            raise ValueError("Original decoder wrote beyond declared output")

    machine.hook_add(UC_HOOK_CODE, callback, begin=ALLOC, end=FREE)
    machine.hook_add(UC_HOOK_CODE, fail_callback, begin=0x401000, end=0x401000)
    machine.hook_add(UC_HOOK_MEM_READ, check_input, begin=INPUT, end=INPUT + aligned(len(compressed)) - 1)
    machine.hook_add(UC_HOOK_MEM_WRITE, check_output, begin=OUTPUT, end=OUTPUT + aligned(expected_length) - 1)
    started = time.monotonic()
    machine.emu_start(START, RETURN, timeout=TIMEOUT_MICROSECONDS, count=MAX_INSTRUCTIONS)
    elapsed = time.monotonic() - started
    if machine.reg_read(UC_X86_REG_EIP) != RETURN:
        raise ValueError("Original decoder did not reach the exact return endpoint within budget")
    if u32(STATE + 8) != expected_length or u32(0x4030D4) != expected_length:
        raise ValueError("Original decoder output counts differ from declared length")
    consumed_bytes = u32(0x4047CC)
    consumed_bits = consumed_bytes * 8 - u32(0x4030CC)
    return {"data": bytes(machine.mem_read(OUTPUT, expected_length)),
            "consumed_bytes": consumed_bytes, "consumed_bits": consumed_bits,
            "return_eip": hex(machine.reg_read(UC_X86_REG_EIP)),
            "callbacks": calls, "elapsed_seconds": elapsed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("new_report", type=Path)
    args = parser.parse_args()
    installer = read_installer(args.installer)
    with args.inventory.open("rb") as source:
        inventory_bytes = source.read(MAX_INVENTORY_BYTES + 1)
    if len(inventory_bytes) > MAX_INVENTORY_BYTES:
        raise ValueError("Inventory byte budget exceeded")
    inventory = json.loads(inventory_bytes)
    canonical, _private_payloads = inspect_installer(installer)
    streams = validate_inventory(inventory, canonical)
    del _private_payloads
    rows = []
    for item in streams:
        start = item["compressed_start"]
        stream = installer[start:start + item["compressed_bytes"]]
        authored = decode(stream, output_limit=item["decoded_size"])
        original = run_original(installer, stream, item["decoded_size"])
        if original["data"] != authored.data:
            raise ValueError("Original/authored decoded-byte mismatch: " + item["name"])
        if (original["consumed_bytes"], original["consumed_bits"]) != (authored.consumed_bytes, authored.consumed_bits):
            raise ValueError("Original/authored compressed-endpoint mismatch")
        digest = hashlib.sha256(original.pop("data")).hexdigest()
        if digest != item["sha256"]:
            raise ValueError("Retained reconstruction identity mismatch")
        rows.append({"name": item["name"], "decoded_size": len(authored.data),
                     "sha256": digest, "exact_output_equal": True, **original})
        print(json.dumps({"name": item["name"], "exact_output_equal": True,
                          "seconds": original["elapsed_seconds"]}), flush=True)
    report = {"schema": "gw-win085-original-decoder-witness-1", "installer_sha256": EXPECTED_SHA256,
              "engine": "Unicorn", "engine_version": unicorn.__version__,
              "original_decoder_entry": hex(START), "exact_return_endpoint": hex(RETURN),
              "instruction_budget_per_stream": MAX_INSTRUCTIONS,
              "time_budget_microseconds_per_stream": TIMEOUT_MICROSECONDS,
              "authored_context": "Flat32-bit PE mapping at preferred base; zeroed buffers and state; bounded VirtualAlloc/VirtualFree callbacks; input/output extent guards",
              "scope": "Original decompressor slice only, not Windows installer or application execution",
              "inventory_coverage": "All nine streams matched against a fresh complete pinned-container parse",
              "streams": rows, "all_outputs_and_consumed_bit_endpoints_match": True}
    with args.new_report.open("x") as output:
        output.write(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
