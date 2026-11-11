"""Authored DOS EXEC helper construction and its bounded observation protocol.

The readable implementation is dos_guest/process_loader.asm. Production does
not need an assembler: the immutable template below was assembled from that
source, and a dedicated test compares it with a fresh NASM build. Only the
selected root filename, command tail and nonce are patched.

The helper inherits the actual DOS environment, builds default FCBs with DOS
AH=29h, and selects the target's drive/root directory. It uses the running
DOS kernel's AX=4B01h loader; no target bytes or synthetic PSP are installed by
this module. Other startup general registers are zeroed where DOS does not
provide a documented initial value. The fixed initial FLAGS are 0202h.

A decoded report is an observation to validate against the stopped machine,
not proof that a source binding, residency or operating-system profile is
correct. The host must cross-check the helper, PSP/MCBs and loaded source.
"""
from __future__ import annotations

import hmac
import re
import struct


REPORT_MAGIC = MAGIC = b"FDBP"
REPORT_VERSION = 1
REPORT_SIZE = 96
READY = 1
ERROR = 2
TERMINATED = 3

# File offsets exclude the DOS-supplied 100h-byte PSP. These offsets are also
# asserted by the NASM source, independently of its instruction encoding.
_REPORT_FILE_OFFSET = 4
_NONCE_FILE_OFFSET = _REPORT_FILE_OFFSET + 8
_TARGET_FILE_OFFSET = 101
_TARGET_BUFFER_SIZE = 16
_TAIL_FILE_OFFSET = 117
_TAIL_BUFFER_SIZE = 128

REPORT_FIELDS = {
    "helper_segment": 24,
    "child_psp": 26,
    "entry_cs": 28,
    "entry_ip": 30,
    "stack_ss": 32,
    "stack_sp": 34,
    "initial_ax": 36,
    "control_offset": 38,
    "ready_wait_ip": 40,
    "exit_wait_ip": 42,
    "report_offset": 44,
    "dos_result": 46,
    "dos_version": 48,
    "dos_oem": 50,
    "helper_psp": 52,
    "exec_flags": 54,
    "raw_stack_sp": 56,
    "target_offset": 58,
    "command_tail_offset": 60,
    "helper_paragraphs": 62,
    "initial_flags": 64,
    "first_mcb_segment": 66,
    "list_of_lists_offset": 68,
    "list_of_lists_segment": 70,
    "failure_stage": 72,
}

_RECORD_TYPES = {READY: "ready", ERROR: "error", TERMINATED: "terminated"}
_ERROR_STAGES = {1: "helper_resize", 2: "select_drive", 3: "root_directory", 4: "exec"}
_TERMINATION_TYPES = {0: "normal", 1: "control_c", 2: "critical_error", 3: "resident"}

# Ordinary ASCII short filenames. Shell separators, path traversal, wildcards,
# alternate streams and device aliases have no role in this root staging ABI.
_SHORT_COMPONENT = r"[A-Za-z0-9!#$%&'()\-@^_\x60{}~]"
_TARGET_PATTERN = re.compile(
    rf"(?:(?P<drive>[A-Za-z]):\\)?"
    rf"(?P<base>{_SHORT_COMPONENT}{{1,8}})"
    rf"(?:\.(?P<extension>{_SHORT_COMPONENT}{{1,3}}))?"
)
_DEVICE_NAMES = frozenset(
    ("CON", "PRN", "AUX", "NUL", "CLOCK$", "CONIN$", "CONOUT$")
    + tuple(f"COM{number}" for number in range(1, 10))
    + tuple(f"LPT{number}" for number in range(1, 10))
)

# Authored bytes only. The trailing zeros are the helper's two private stacks.
# Any source edit must regenerate this template and pass the assembly gate.
_LOADER_TEMPLATE = bytes.fromhex(
"""
    e95b010046444250010060000000000000000000000000000000000000000000
    000000000000000000006401c3034e0404010000000000000000000000006501
    75018b0002020000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000d000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000020202020202020202020
    2000000000000000000000000000000000000000000000000000002020202020
    2020202020200000000000000000000000000000000000000000000000000000
    0075010000f50100001a0200000000000000000000000000000000005c00fa8c
    c88ed0bca2068ed88ec0fcfba31c01b462cd21891e3801b80030cd21a3340188
    f830e4a33601b452cd21891e48018c064a01268b47fea34601b42fcd21891e55
    028c0657020e07e8a801c7064c010100bb8b00b44acd210f827f01c7064c0102
    00803e66013a75238a16650180e2df80ea4188165b02b40ecd21b419cd213a06
    5b027407b80f00f9e94f01c7064c010300ba5c02b43bcd210f823e01be7601bf
    f501b80129cd21bf1a02b80129cd218cc8a34302a34702a34b028ec0ba6501bb
    3f02c7064c010400b8014bcd212ea359028cc88ed0bca2068ed88ec09c8f063a
    01fbf7063a0101007409a15902a33201e9f100c41e4d028c062401891e3c0126
    8b07a3280183c302891e2601a15102a32201a15302a32001b462cd21891e1e01
    8b1e3801b450cd212ec5165502b41acd210e1fba1304b82225cd218e061e0126
    c7060a0013048cc826a30c008ec0fa8ed0bca208fbc7064c010000c606090101
    e8b800fb2e803e6401017403f4ebf42e8b1e1e01b450cd212e8e1e1e01ba8000
    b41acd21fa31c089c389c189c289c689c789c56a029d2ea11e018ed88ec02ea1
    24018ed02e8b2626012ea12801fb2eff2e5102fa8cc88ed0bca2068ed88ec0fc
    fb8b1e3801b450cd21b44dcd21a33201c606090103e84300eb142ea332019c2e
    8f063a010e1fc606090102e82d00fbf4ebfcbaf90230c0eebafb02b080eebaf8
    02b001ee4230c0eebafb02b003eebafa02b007eebafc02b00beec3505152561e
    0e1ffcbe0401b96000ac88c4bafd02eca82074fb88e0baf802eee2ed1f5e5a59
    58c3000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
    0000
"""
)


def loader_code_ranges():
    """File spans for the immutable jump and contiguous helper instructions.

    The authored source jumps past its mutable report/EXEC data to start.
    Its only trailing mutable storage consists of two 512-byte stacks.
    """
    if _LOADER_TEMPLATE[:1] != b"\xe9":
        raise ValueError("The DOS helper entry must be its authored near jump")
    start = 3 + struct.unpack_from("<h", _LOADER_TEMPLATE, 1)[0]
    end = len(_LOADER_TEMPLATE) - 1024
    if not _TAIL_FILE_OFFSET + _TAIL_BUFFER_SIZE <= start < end:
        raise ValueError("The DOS helper code and stack extents are inconsistent")
    return ((0, 3), (start, end))


def _nonce(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) != 16:
        raise ValueError("The DOS process helper requires a 16-byte nonce")
    return value


def build_loader(target: str, command_tail: bytes, nonce: bytes) -> bytes:
    """Build a private helper for one root 8.3 target and a CP437 byte tail.

    A:\\NAME.COM selects drive A and its root. NAME.COM uses the current
    drive's root. Subdirectories and DOS device names are rejected. The command
    tail excludes its length byte and terminating carriage return; it may
    contain at most 126 bytes and must not contain NUL, CR or LF.
    """
    nonce = _nonce(nonce)
    match = _TARGET_PATTERN.fullmatch(target) if isinstance(target, str) else None
    if match is None or match.group("base").upper() in _DEVICE_NAMES:
        raise ValueError("DOS target must be a root 8.3 filename, optionally A:\\NAME.COM, not a device")
    encoded_target = target.encode("ascii")
    if len(encoded_target) >= _TARGET_BUFFER_SIZE:
        raise ValueError("DOS target exceeds the helper's root filename buffer")
    if (not isinstance(command_tail, bytes) or len(command_tail) > 126
            or any(byte in command_tail for byte in (0, 10, 13))):
        raise ValueError("DOS command tail must contain at most 126 CP437 bytes without NUL, CR or LF")

    result = bytearray(_LOADER_TEMPLATE)
    result[_NONCE_FILE_OFFSET:_NONCE_FILE_OFFSET + 16] = nonce
    result[_TARGET_FILE_OFFSET:_TARGET_FILE_OFFSET + _TARGET_BUFFER_SIZE] = (
        encoded_target + b"\0"
    ).ljust(_TARGET_BUFFER_SIZE, b"\0")
    result[_TAIL_FILE_OFFSET:_TAIL_FILE_OFFSET + _TAIL_BUFFER_SIZE] = (
        bytes((len(command_tail),)) + command_tail + b"\r"
    ).ljust(_TAIL_BUFFER_SIZE, b"\0")
    return bytes(result)


def parse_report(data: bytes, nonce: bytes) -> dict:
    """Decode exactly one framed helper record, refusing stale/malformed data.

    Resident status is populated only for a terminated report. AH=4Dh category
    3 covers both INT 27h and AH=31h and does not identify which instruction
    path the target used. Pointers to helper data/code must match this template;
    other returned addresses still require live memory and source validation.
    """
    nonce = _nonce(nonce)
    if not isinstance(data, bytes) or len(data) != REPORT_SIZE:
        raise ValueError("Expected one complete 96-byte DOS process report")
    magic, version, record_type, size = struct.unpack_from("<4sBBH", data)
    if magic != REPORT_MAGIC or version != REPORT_VERSION or size != REPORT_SIZE:
        raise ValueError("Unsupported DOS process report header")
    if record_type not in _RECORD_TYPES:
        raise ValueError("Unknown DOS process report type")
    if not hmac.compare_digest(data[8:24], nonce):
        raise ValueError("DOS process report belongs to a different launch nonce")
    if any(data[74:]):
        raise ValueError("DOS process report has nonzero reserved fields")

    values = {name: struct.unpack_from("<H", data, offset)[0]
              for name, offset in REPORT_FIELDS.items()}
    for name in ("control_offset", "ready_wait_ip", "exit_wait_ip", "report_offset",
                 "target_offset", "command_tail_offset", "helper_paragraphs", "initial_flags"):
        expected = struct.unpack_from(
            "<H", _LOADER_TEMPLATE, _REPORT_FILE_OFFSET + REPORT_FIELDS[name]
        )[0]
        if values[name] != expected:
            raise ValueError("DOS process report helper layout differs: " + name)
    if not values["helper_segment"] or values["helper_psp"] != values["helper_segment"]:
        raise ValueError("DOS process report does not identify its COM helper PSP")
    if values["dos_oem"] > 255:
        raise ValueError("DOS process report OEM value is not a byte")

    result = dict(format="fdisbull-dos-process-report-v1", schema=REPORT_VERSION,
                  type=_RECORD_TYPES[record_type], record_type=record_type,
                  nonce=nonce.hex(), **values)
    result.update(dos_major=values["dos_version"] & 255,
                  dos_minor=values["dos_version"] >> 8)
    if record_type == ERROR:
        if values["failure_stage"] not in _ERROR_STAGES or not values["exec_flags"] & 1:
            raise ValueError("DOS process error report lacks its failed DOS operation")
        result.update(error_code=values["dos_result"],
                      error_stage=_ERROR_STAGES[values["failure_stage"]])
    else:
        if values["failure_stage"] or values["exec_flags"] & 1 or not values["child_psp"]:
            raise ValueError("DOS process report does not describe a loaded child")
        if (values["raw_stack_sp"] + 2) & 0xffff != values["stack_sp"]:
            raise ValueError("DOS process report did not remove the load-only AX stack word")
        if record_type == TERMINATED:
            method = values["dos_result"] >> 8
            result.update(termination_type=method,
                          termination=_TERMINATION_TYPES.get(method, "unknown"),
                          exit_code=values["dos_result"] & 255,
                          resident=method == 3,
                          termination_instruction="not_observed")
    return result
