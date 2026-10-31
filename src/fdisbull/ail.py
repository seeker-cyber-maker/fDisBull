"""Bounded recognition of Miles AIL 2 real-mode driver libraries.

The directory declares callable offsets, not a DOS process entry. Addresses
are module-relative. No relocation, hardware probe or driver code is executed.
"""
from __future__ import annotations

import hashlib
import struct

from .model import Image, Region, Seed

AIL_REFERENCE = 'https://github.com/Tronix286/AIL2/blob/master/AIL.INC'
_NAMES = {
    100:'describe_driver', 101:'detect_device', 102:'initialize_driver',
    103:'service_driver', 104:'shutdown_driver',
    120:'index_voc_block', 121:'register_sound_buffer', 122:'sound_buffer_status',
    123:'play_voc_file', 124:'voc_playback_status', 125:'start_digital_playback',
    126:'stop_digital_playback', 127:'pause_digital_playback',
    128:'resume_digital_playback', 129:'set_digital_volume', 130:'digital_volume',
    131:'set_digital_pan', 132:'digital_pan', 133:'format_voc_file',
    134:'format_sound_buffer', 150:'state_table_size', 151:'register_sequence',
    152:'release_sequence_handle', 153:'timbre_cache_size', 154:'define_timbre_cache',
    155:'timbre_request', 156:'install_timbre', 157:'protect_timbre',
    158:'unprotect_timbre', 159:'timbre_status', 170:'start_sequence',
    171:'stop_sequence', 173:'resume_sequence', 174:'sequence_status',
    175:'relative_volume', 176:'relative_tempo', 177:'set_relative_volume',
    178:'set_relative_tempo', 179:'beat_count', 180:'bar_count', 181:'branch_index',
    182:'controller_value', 183:'set_controller_value', 185:'channel_notes',
    186:'send_channel_voice_message', 187:'send_sysex_message', 188:'write_display',
    189:'install_callback', 190:'cancel_callback', 191:'lock_channel',
    192:'map_sequence_channel', 193:'release_channel', 194:'true_sequence_channel',
}


def ail_signature(data: bytes) -> bool:
    """A family marker, never sufficient on its own to accept a library."""
    if not isinstance(data, bytes) or len(data) < 4:
        return False
    offset = int.from_bytes(data[:2], 'little')
    notice = data[2:min(offset, 512)]
    return (32 <= offset <= 512 and notice.startswith(b'Copyright (C) ')
            and (b'John Miles' in notice or b'Miles Design' in notice))


def _descriptor(data, offset, directory_end):
    # A candidate returned by MOV AX,imm16 in the describe_driver prologue.
    # Retain this inference explicitly; arbitrary driver code is never run.
    from iced_x86 import Decoder, Mnemonic, OpKind, Register
    pointer = None
    for instruction in Decoder(16, data[offset:offset+64], ip=offset):
        if instruction.mnemonic == Mnemonic.MOV and instruction.op0_register == Register.AX and instruction.op1_kind == OpKind.IMMEDIATE16:
            pointer = instruction.immediate16
            break
        if instruction.mnemonic in (Mnemonic.RET, Mnemonic.RETF, Mnemonic.JMP, Mnemonic.CALL):
            break
    if pointer is None or not directory_end <= pointer <= len(data)-24:
        return None
    version, kind, suffix, names, segment, io, irq, dma, drq, rate, display = struct.unpack_from('<HH4sHHhhhhHH', data, pointer)
    if not version or kind not in (1, 2, 3) or not directory_end <= names < len(data):
        return None
    end = data.find(b'\0\0', names, min(len(data), names+4096))
    if end < 0:
        return None
    labels = data[names:end].split(b'\0')
    if any(any(c < 32 or c > 126 for c in label) for label in labels):
        return None
    return dict(file_offset=pointer, address=pointer, minimum_api_version=version,
        driver_type=kind, timbre_suffix=suffix.rstrip(b'\0').decode('ascii', errors='replace'),
        supported_device_names=[s.decode('ascii') for s in labels],
        device_names_offset=names, stored_device_names_segment=segment,
        default_io=io, default_irq=irq, default_dma=dma, default_drq=drq,
        service_rate_hz=rate, display_size=display, runtime_observed=False,
        evidence='candidate descriptor from describe_driver MOV AX immediate; not executed')


def inspect_ail(data: bytes) -> dict:
    if not isinstance(data, bytes) or not 1 <= len(data) <= 0x10000:
        raise ValueError('AIL driver requires 1..65536 bytes')
    if not ail_signature(data):
        raise ValueError('AIL driver copyright/family marker is absent')
    directory = int.from_bytes(data[:2], 'little')
    if directory > len(data) or data[directory-1] != 0x1a:
        raise ValueError('truncated or invalid AIL copyright/header extent')
    exports = []
    seen = set()
    at = directory
    while True:
        if at+2 > len(data):
            raise ValueError('truncated AIL function directory; terminator missing')
        function = struct.unpack_from('<H', data, at)[0]
        if function == 0xffff:
            end = at+2
            break
        if at+4 > len(data) or len(exports) >= 512:
            raise ValueError('AIL function directory extent/count exceeds bounds')
        offset = struct.unpack_from('<H', data, at+2)[0]
        if function in seen or function < 100:
            raise ValueError('duplicate or invalid AIL function id')
        seen.add(function)
        exports.append(dict(name='AIL.'+_NAMES.get(function, f'function_{function}'),
            ordinal=function, function_id=function, address=offset, file_offset=offset,
            directory_file_offset=at, code_seed_eligible=True,
            source='AIL function directory', contract_source=AIL_REFERENCE))
        at += 4
    if not {100, 101, 102, 103, 104} <= seen:
        raise ValueError('AIL directory lacks required driver functions 100..104')
    if any(not end <= e['address'] < len(data) for e in exports):
        raise ValueError('AIL function offset is outside file-backed payload')
    descriptor = _descriptor(data, next(e['address'] for e in exports if e['ordinal']==100), end)
    return dict(format='fdisbull-ail-driver-1', address_space='module-relative',
        runtime_segment=None, directory_offset=directory, directory_end=end,
        copyright=data[2:directory-1].decode('ascii', errors='replace'),
        exports=exports, descriptor=descriptor, entrypoint=None,
        warnings=['Static function declarations do not establish reachability, runtime binding or hardware support.']+
            ([] if descriptor else ['Driver descriptor was not inferred; describe_driver was not executed.']))


def load_ail(data: bytes, *, entry=None) -> Image:
    metadata = inspect_ail(data)
    seeds = [Seed(e['address'], e['name'], 'ail_function_directory') for e in metadata['exports']]
    if entry is not None:
        if type(entry) is not int or not metadata['directory_end'] <= entry < len(data):
            raise ValueError('AIL analysis entry must be inside the file-backed payload')
        seeds.insert(0, Seed(entry, 'explicit_entry', 'explicit_entry'))
    return Image('AIL', 'x86', 16, entry, [Region('ail_module', 0, data, True, True)],
        seeds, dict(selected_image='ail', entrypoint_present=entry is not None,
            source_sha256=hashlib.sha256(data).hexdigest(),
            mapping='AIL module-relative offsets; runtime segment and relocations unbound',
            ail=metadata, file_mappings=[dict(virtual_address=0, file_offset=0, file_size=len(data))]),
        source_bytes=data)
