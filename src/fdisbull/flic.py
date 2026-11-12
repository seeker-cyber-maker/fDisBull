"""Bounded FLI/FLC packet inventory, including two game-specific envelopes.

Only header, packet and declared subchunk extents are checked. No palette,
pixel, audio or native consumer decoder is invoked and no source is rewritten.

Independent layout references:
https://github.com/FFmpeg/FFmpeg/blob/3a3f5e24a95b744d237d0cb01dccb647e44b9457/libavformat/flic.c
https://github.com/FFmpeg/FFmpeg/blob/3a3f5e24a95b744d237d0cb01dccb647e44b9457/libavcodec/flicvideo.c
https://github.com/swfans/syndwarsfx/blob/cd03fb2c5a50a5ec8002f2b45252475ab39cbf6e/bflibrary/include/bfflic.h
"""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
import struct

from .media import MAX_SOURCE, _snapshot

MAX_PACKETS = 65536
MAX_SUBCHUNKS = 131072
MAX_REPORTED_PACKETS = 4096
MAX_INDEX_BYTES = (MAX_PACKETS + 1) * 4
FRAME_TYPES = {0xF1FA, 0xF5FA}
CHUNK_NAMES = {
    4: '256-level-palette', 7: 'word-delta', 11: '64-level-palette',
    12: 'byte-delta', 13: 'black', 15: 'byte-run', 16: 'copy',
    18: 'postage-stamp', 25: 'DTA-byte-run', 26: 'DTA-copy', 27: 'DTA-delta',
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _subchunks(raw, start, end, counter, remaining):
    if end - start < 16:
        raise ValueError('Truncated FLIC frame header')
    count = struct.unpack_from('<H', raw, start + 6)[0]
    if count > remaining:
        raise ValueError('FLIC subchunk inventory budget exceeded')
    position = start + 16
    for _ in range(count):
        if position + 6 > end:
            raise ValueError('Truncated FLIC subchunk header')
        size, kind = struct.unpack_from('<IH', raw, position)
        if size < 6 or position + size > end:
            raise ValueError('FLIC subchunk extent exceeds its frame')
        counter[kind] += 1
        position += size
    # Do not reinterpret unexplained bytes as another subchunk. They can be
    # reported as an opaque frame tail without claiming full packet semantics.
    return count, end - position


def inspect_flic(path, *, index_path=None):
    """Inventory one <=64MiB immutable FLI/FLC and an optional TFTD IDX.

    The optional IDX check establishes that unsigned words equal the observed
    audio-plus-visual packet-group lengths and terminate with 0xffffffff. It
    does not prove the original game's seeking/timing interpretation.
    """
    raw = _snapshot(path, MAX_SOURCE)
    if len(raw) < 12:
        raise ValueError('Truncated FLI/FLC header')
    size_field, magic, declared, width, height = struct.unpack_from('<I4H', raw)
    if magic not in (0xAF11, 0xAF12, 0xAF44):
        raise ValueError('Expected a recognized FLI/FLC/FLX header')
    if not 0 < width <= 4096 or not 0 < height <= 4096:
        raise ValueError('Unsupported or invalid FLIC geometry')
    if not 0 < declared <= MAX_PACKETS:
        raise ValueError('Unsupported or invalid declared FLIC frame count')
    # Offset16 is a standard header's speed field too. A matching word alone
    # would mistake an ordinary slow clip for a compact Bullfrog frame. Admit
    # only the compound twelve-byte profile qualified by the current corpus.
    compact = (magic == 0xAF12 and size_field == 12 and len(raw) >= 28
               and struct.unpack_from('<H', raw, 16)[0] == 0xF1FA
               and 16 <= struct.unpack_from('<I', raw, 12)[0] <= len(raw) - 12)
    header_bytes = 12 if compact else 128
    if len(raw) < header_bytes:
        raise ValueError('Truncated standard 128-byte FLIC header')
    if magic == 0xAF44:
        if index_path is not None:
            raise ValueError('An IDX companion is unsupported for the extended FLX profile')
        return dict(format='fdisbull-flic-inspection-1', adapter='flic',
                    source=dict(bytes=len(raw), sha256=_sha(raw)),
                    profile='extended-flx', status='recognized-unsupported-layout',
                    header_bytes=header_bytes, declared_frames=declared,
                    width=width, height=height, packet_inventory_complete=False,
                    full_decode=False, native_runtime_tested=False,
                    input_executed=False, source_modified=False,
                    recovery_required=['Extended FLX packet profile is not inventoried by this reader.'])
    tftd = (not compact and len(raw) >= 134
            and struct.unpack_from('<H', raw, 132)[0] == 0xAAAA)
    if index_path is not None and not tftd:
        raise ValueError('An IDX companion is supported only for the TFTD audio envelope')
    if not compact and not tftd and size_field > len(raw):
        raise ValueError('FLIC declared file length exceeds available source')
    profile = 'bullfrog-compact-12' if compact else 'tftd-audio-128' if tftd else 'standard-128'
    records = []
    top_types, sub_types = Counter(), Counter()
    position = header_bytes
    packets = subchunks = frame_tails = opaque_tail_bytes = 0
    audio_bytes = audio_packets = frame_packets = 0
    group_lengths = []
    pending_audio = None
    grouping_exact = True
    warnings = []
    while position < len(raw):
        if packets >= MAX_PACKETS:
            raise ValueError('FLIC packet inventory budget exceeded')
        if position + 6 > len(raw):
            raise ValueError('Truncated FLIC packet preamble')
        declared_size, kind = struct.unpack_from('<IH', raw, position)
        if kind == 0xAAAA:
            if not tftd:
                raise ValueError('Audio packet outside the supported TFTD envelope')
            # The stored size counts PCM payload only; the six-byte preamble
            # and ten-byte extension are additional physical bytes.
            extent = declared_size + 16
            if not declared_size:
                raise ValueError('Empty unsupported TFTD audio packet')
        else:
            extent = declared_size
            if extent < 6:
                raise ValueError('Invalid FLIC packet length')
        end = position + extent
        if end > len(raw):
            raise ValueError('FLIC packet extent exceeds available source')
        top_types[kind] += 1
        row = dict(offset=position, bytes=extent, stored_size=declared_size,
                   type=f'0x{kind:04x}')
        if kind in FRAME_TYPES:
            frame_packets += 1
            count, tail = _subchunks(raw, position, end, sub_types, MAX_SUBCHUNKS - subchunks)
            subchunks += count
            row['subchunks'] = count
            if tail:
                frame_tails += 1
                opaque_tail_bytes += tail
                row['opaque_tail_bytes'] = tail
        elif kind == 0xAAAA:
            audio_packets += 1
            audio_bytes += declared_size
            row['payload_offset'] = position + 16
            row['payload_bytes'] = declared_size
        else:
            row['payload_semantics'] = 'opaque; packet extent only'
        if tftd:
            if kind == 0xAAAA:
                if pending_audio is not None:
                    grouping_exact = False
                pending_audio = extent
            elif kind in FRAME_TYPES or kind == 0xF100:
                if pending_audio is None:
                    grouping_exact = False
                else:
                    group_lengths.append(pending_audio + extent)
                    pending_audio = None
            else:
                grouping_exact = False
        if len(records) < MAX_REPORTED_PACKETS:
            records.append(row)
        packets += 1
        position = end
    if pending_audio is not None:
        grouping_exact = False
    if frame_tails:
        warnings.append('Frame tails remain opaque; packet/subchunk extents are inventoried, not complete payload semantics.')
    if not compact and size_field != len(raw):
        warnings.append('Stored file-size field differs from actual source; variant-specific semantics are not inferred.')
    if compact:
        frame_relation = ('equal' if frame_packets == declared else 'one-extra-frame-chunk'
                          if frame_packets == declared + 1 else 'different')
    elif tftd:
        frame_relation = 'custom-prefix-and-frame-count; logical timing not verified'
    else:
        frame_relation = ('equal' if frame_packets == declared else 'one-extra-frame-chunk'
                          if frame_packets == declared + 1 else 'different')
    if frame_relation == 'one-extra-frame-chunk':
        warnings.append('One additional frame packet may be a loop/ring frame; its decoded relationship is unverified.')
    elif frame_relation == 'different':
        warnings.append('Observed frame-packet count differs from header; keep this variant flagged for recovery.')
    index = dict(status='not_supplied', semantic_interpretation='not_verified')
    if index_path is not None:
        idx = _snapshot(index_path, MAX_INDEX_BYTES)
        if not grouping_exact or len(idx) != 4 * (len(group_lengths) + 1):
            raise ValueError('TFTD IDX length or packet grouping does not match observed source')
        words = struct.unpack('<' + 'I' * (len(idx) // 4), idx)
        if words[-1] != 0xFFFFFFFF or list(words[:-1]) != group_lengths:
            raise ValueError('TFTD IDX words differ from observed packet-group extents')
        index.update(status='packet-group-lengths-match', bytes=len(idx), sha256=_sha(idx),
                     entries=len(group_lengths), terminator='0xffffffff')
    unknown_top = {f'0x{k:04x}': n for k, n in top_types.items()
                   if k not in FRAME_TYPES | {0xAAAA, 0xF100, 0xF1FB}}
    unknown_sub = {f'0x{k:04x}': n for k, n in sub_types.items() if k not in CHUNK_NAMES}
    recovery = ['Pixel/palette decoding, independent playback and original-consumer compatibility are not tested by inventory.']
    if unknown_top or unknown_sub:
        recovery.append('Unknown packet/subchunk types require decoder recovery; their extents alone are known.')
    if frame_tails or frame_relation == 'different':
        recovery.append('Unexplained frame tails/counts require variant qualification.')
    if tftd:
        recovery.append('TFTD prefix payload and IDX seeking/timing semantics require original-consumer qualification.')
        if index_path is None:
            recovery.append('Supply the exact IDX companion to verify packet-group length correspondence.')
    return dict(format='fdisbull-flic-inspection-1', adapter='flic',
                source=dict(bytes=len(raw), sha256=_sha(raw)), profile=profile,
                status='structural-inventory', header_bytes=header_bytes,
                header=dict(magic=f'0x{magic:04x}', size_field=size_field,
                            declared_frames=declared, width=width, height=height,
                            depth_field=None if compact else struct.unpack_from('<H', raw, 12)[0],
                            rate_field=None if compact else struct.unpack_from('<I', raw, 16)[0]),
                packets=packets, frame_packets=frame_packets, frame_count_relation=frame_relation,
                subchunks=subchunks, top_packet_types={f'0x{k:04x}': n for k, n in top_types.items()},
                subchunk_types={f'0x{k:04x}': dict(count=n, name=CHUNK_NAMES.get(k, 'unknown'))
                                for k, n in sub_types.items()},
                unknown_top_packet_types=unknown_top, unknown_subchunk_types=unknown_sub,
                opaque_frame_tail_bytes=opaque_tail_bytes,
                chunks=records, returned_chunk_records=len(records),
                chunk_records_truncated=packets > len(records),
                packet_inventory_complete=True,
                audio=dict(packets=audio_packets, payload_bytes=audio_bytes,
                           header_profile='PCM-u8/mono/22050 reference envelope; not decoded' if tftd else None,
                           packet_grouping_exact=grouping_exact if tftd else None),
                companion_index=index, warnings=warnings, recovery_required=recovery,
                full_decode=False, native_runtime_tested=False, input_executed=False,
                source_modified=False, rewrite_supported=False)
