"""Authored DOS workspace loader and nonce-bound v2 observation protocol."""
from __future__ import annotations
import hmac
import re
import struct
from .dos_process_helper import (REPORT_FIELDS, REPORT_MAGIC, REPORT_SIZE, READY, ERROR, TERMINATED,
                                 _RECORD_TYPES, _TERMINATION_TYPES, _nonce, _DEVICE_NAMES, _SHORT_COMPONENT)

REPORT_VERSION = 2
_REPORT_FILE_OFFSET = 4
_NONCE_FILE_OFFSET = 12
_TARGET_FILE_OFFSET = 101
_TARGET_BUFFER_SIZE = 128
_TAIL_FILE_OFFSET = 229
_TAIL_BUFFER_SIZE = 128
_PARENT_FILE_OFFSET = 357
_PARENT_BUFFER_SIZE = 128
_ERROR_STAGES = {1: 'helper_resize', 2: 'select_drive', 3: 'parent_directory', 4: 'exec'}
_COMPONENT = re.compile(rf"{_SHORT_COMPONENT}{{1,8}}(?:\.{_SHORT_COMPONENT}{{1,3}})?")
_LOADER_TEMPLATE = bytes.fromhex("""
    e949020046444250020060000000000000000000000000000000000000000000000000000000000000006401b1043c05
    04010000000000000000000000006501e501990002020000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    00000000000000000000000000000000000000000000000000000000000000000000000000000d000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000202020202020202020202000000000000000000000000000000000000000000000000000002020202020
    202020202020000000000000000000000000000000000000000000000000000000e5010000e50200000a030000000000
    000000000000000000000000fa8cc88ed0bc90078ed88ec0fcfba31c01b462cd21891e3801b80030cd21a3340188f830
    e4a33601b452cd21891e48018c064a01268b47fea34601b42fcd21891e45038c0647030e07e8a801c7064c010100bb99
    00b44acd210f827f01c7064c010200803e66013a75238a16650180e2df80ea4188164b03b40ecd21b419cd213a064b03
    7407b80f00f9e94f01c7064c010300ba6502b43bcd210f823e01bee601bfe502b80129cd21bf0a03b80129cd218cc8a3
    3303a33703a33b038ec0ba6501bb2f03c7064c010400b8014bcd212ea349038cc88ed0bc90078ed88ec09c8f063a01fb
    f7063a0101007409a14903a33201e9f100c41e3d038c062401891e3c01268b07a3280183c302891e2601a14103a32201
    a14303a32001b462cd21891e1e018b1e3801b450cd212ec5164503b41acd210e1fba0105b82225cd218e061e0126c706
    0a0001058cc826a30c008ec0fa8ed0bc9009fbc7064c010000c606090101e8b800fb2e803e6401017403f4ebf42e8b1e
    1e01b450cd212e8e1e1e01ba8000b41acd21fa31c089c389c189c289c689c789c56a029d2ea11e018ed88ec02ea12401
    8ed02e8b2626012ea12801fb2eff2e4103fa8cc88ed0bc90078ed88ec0fcfb8b1e3801b450cd21b44dcd21a33201c606
    090103e84300eb142ea332019c2e8f063a010e1fc606090102e82d00fbf4ebfcbaf90230c0eebafb02b080eebaf802b0
    01ee4230c0eebafb02b003eebafa02b007eebafc02b00beec3505152561e0e1ffcbe0401b96000ac88c4bafd02eca820
    74fb88e0baf802eee2ed1f5e5a5958c30000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
    0000000000000000000000000000000000000000000000000000000000000000
""")


def loader_code_ranges():
    if _LOADER_TEMPLATE[:1] != b'\xe9':
        raise ValueError('The DOS workspace helper entry must be a near jump')
    start = 3 + struct.unpack_from('<h', _LOADER_TEMPLATE, 1)[0]
    end = len(_LOADER_TEMPLATE) - 1024
    if not _PARENT_FILE_OFFSET + _PARENT_BUFFER_SIZE <= start < end:
        raise ValueError('The DOS workspace helper code and stack extents are inconsistent')
    return ((0, 3), (start, end))


def build_loader(target: str, command_tail: bytes, nonce: bytes) -> bytes:
    """Build the helper for an absolute, non-device ASCII DOS 8.3 path."""
    nonce = _nonce(nonce)
    if not isinstance(target, str) or not re.fullmatch(r'[A-Za-z]:\\[^\\]+(?:\\[^\\]+)*', target):
        raise ValueError('DOS workspace target must be an absolute drive and 8.3 path')
    components = target[3:].split('\\')
    if any(not _COMPONENT.fullmatch(part) or part.split('.')[0].upper() in _DEVICE_NAMES for part in components):
        raise ValueError('DOS workspace target requires non-device 8.3 path components')
    encoded = target.encode('ascii')
    if len(encoded) >= _TARGET_BUFFER_SIZE:
        raise ValueError('DOS workspace target exceeds 127 bytes')
    if not isinstance(command_tail, bytes) or len(command_tail) > 126 or any(x in command_tail for x in (0,10,13)):
        raise ValueError('DOS command tail must contain at most 126 CP437 bytes without NUL, CR or LF')
    parent = target.rsplit('\\', 1)[0]
    if len(components) == 1:
        parent += '\\'
    parent_bytes = parent.encode('ascii')
    result = bytearray(_LOADER_TEMPLATE)
    result[_NONCE_FILE_OFFSET:_NONCE_FILE_OFFSET+16] = nonce
    result[_TARGET_FILE_OFFSET:_TARGET_FILE_OFFSET+128] = (encoded + b'\0').ljust(128,b'\0')
    result[_TAIL_FILE_OFFSET:_TAIL_FILE_OFFSET+128] = (bytes([len(command_tail)]) + command_tail + b'\r').ljust(128,b'\0')
    result[_PARENT_FILE_OFFSET:_PARENT_FILE_OFFSET+128] = (parent_bytes + b'\0').ljust(128,b'\0')
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

    result = dict(format="fdisbull-dos-process-report-v2", schema=REPORT_VERSION,
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
