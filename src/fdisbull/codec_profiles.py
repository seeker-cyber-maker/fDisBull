"""Inert format catalog records and header probes for reusable legacy codecs.

No decompressor, processor or runtime is imported by recognition. In particular,
PKWARE DCL has no distinctive magic: two plausible option bytes are not evidence
of a DCL stream. Select that decoder explicitly from a qualified container.
"""
from __future__ import annotations
import struct


def definitions(definition, field, magic):
    provenance = ['docs/MADS_MEDIA_RUNTIME.md', 'src/fdisbull/codec_profiles.py']
    return [
        definition('fab', 'FAB compressed stream', 'compression', [magic(0, b'FAB')],
            [field('window_bits', 3, 'u8', 'Supported backward window: 10..13 bits'),
             field('initial_control', 4, 'u16le', 'LSB-first control word')], endian='little',
            limitations=['Header only; decoded size comes from the enclosing resource. Terminator, references and output length require explicit decoding.'], provenance=provenance),
        definition('pkware-dcl', 'PKWARE Data Compression Library stream', 'compression', [],
            [field('coded_literals', 0, 'u8', '0=uncoded, 1=Huffman-coded'),
             field('dictionary_bits', 1, 'u8', '4, 5 or 6')], endian='bitstream-lsb-first',
            limitations=['No automatic recognition: two option bytes are not a signature.',
                          'Not PKZIP method 6; use an explicit container profile and bounded decoder.'], provenance=provenance),
        definition('mads-hag', 'MADSCONCAT 1.0 resource archive', 'archive',
            [magic(0, b'MADSCONCAT 1.0\x1a\0')],
            [field('member_count', 16, 'u16le', 'Count of 22-byte directory records')], endian='little',
            limitations=['Header/directory extent only; member names, ranges and overlaps require the HAG reader.'], provenance=provenance),
        definition('mads-pack', 'MADSPACK 1.0 / 2.0 section container', 'container',
            [magic(0, b'MADSPACK 1.0\x1a\0'), magic(0, b'MADSPACK 2.0\x1a\0')],
            [field('section_count', 14, 'u16le', '1..16 entries in a fixed 176-byte header'),
             field('section_directory', 16, 'bytes[160]', 'Codec, priority, decoded size and stored size')], endian='little',
            limitations=['Header/section extents only; no decompression during recognition.',
                          'Codec 1 is DCL in version 1.0 and FAB in version 2.0; codec 3 is DCL.',
                          'A pack is not inherently a sprite, font, animation or conversation. Select the consumer explicitly.'], provenance=provenance),
    ]


def probe(prefix: bytes, source_size: int, result):
    """Return cheap structural facts, or None; never guess from a filename."""
    if prefix.startswith(b'FAB'):
        valid = len(prefix) >= 6 and 10 <= prefix[3] <= 13
        return result('fab', 'FAB compressed stream', 'compression', valid=valid,
            metadata={'window_bits': prefix[3] if len(prefix) > 3 else None},
            warnings=['Decoded length is not in the FAB header; obtain it from the enclosing format.'] +
                     ([] if valid else ['Truncated header or unsupported FAB window.']))
    if prefix.startswith(b'MADSCONCAT 1.0\x1a\0'):
        count = struct.unpack_from('<H', prefix, 16)[0] if len(prefix) >= 18 else 0
        end = 18 + 22 * count
        valid = len(prefix) >= 18 and 1 <= count <= 32768 and end <= source_size
        return result('mads-hag', 'MADSCONCAT 1.0 resource archive', 'archive', valid=valid,
            metadata={'member_count': count, 'directory_end': end, 'members_validated': False},
            warnings=[] if valid else ['Truncated or oversized HAG directory extent.'])
    if prefix.startswith(b'MADSPACK '):
        version = prefix[9:12].decode('ascii', 'backslashreplace')
        count = struct.unpack_from('<H', prefix, 14)[0] if len(prefix) >= 16 else 0
        valid = (len(prefix) >= 176 and prefix[:14] in (b'MADSPACK 1.0\x1a\0', b'MADSPACK 2.0\x1a\0')
                 and 1 <= count <= 16)
        end = 176
        if valid:
            for i in range(count):
                kind, _, size, stored = struct.unpack_from('<BBII', prefix, 16 + 10*i)
                end += stored
                if kind not in (0, 1, 3) or end > source_size or kind == 0 and size != stored:
                    valid = False
        return result('mads-pack', 'MADSPACK section container', 'container', valid=valid,
            metadata={'version': version, 'section_count': count, 'sections_end': end,
                      'decompressed': False, 'asset_type': 'not_inferred'},
            warnings=[] if valid else ['Unsupported version/codec, truncated table or invalid section extent.'])
    return None
