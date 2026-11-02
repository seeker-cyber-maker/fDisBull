"""Emit a bounded banked reader for sorted, disjoint source-ROM spans.

The returned snippets are inserted at the existing rom8 and rom16 entry
points.  A miss falls through to the pre-existing platform reader; no ROM
contents are included in generated source.
"""
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ArenaReader:
    declarations: str
    byte_lookup: str
    word_lookup: str


def emit_arena_reader(spans: Sequence[tuple[int, int]], data_bank: int) -> ArenaReader:
    """Generate lookup code; ends are exclusive and the bank holds <= 8192 bytes.

    Address zero is excluded to preserve the existing reader's 32-bit wraparound
    behavior for a word at the maximum offset in this platform.
    """
    if not 0 <= data_bank <= 255:
        raise ValueError('invalid arena data bank')
    if not spans or len(spans) >= 255 or spans[0][0] == 0:
        raise ValueError('invalid arena span count')
    offsets = []
    size = 0
    previous = 0
    for lo, hi in spans:
        if not (0 <= lo < hi <= 0xffffffff) or lo < previous:
            raise ValueError('arena spans must be sorted, nonempty and disjoint')
        offsets.append(size)
        size += hi - lo
        previous = hi
    if size > 8192:
        raise ValueError('arena data exceeds one bank')
    declarations = (
        'extern const u8 shadowrun_arena_tables[];\n'
        'void __fastcall__ shadowrun_data_select(u8);\n'
        'static const u32 arena_lo[]={' + ','.join(f'0x{lo:x}UL' for lo, _ in spans) + '};\n'
        'static const u32 arena_hi[]={' + ','.join(f'0x{hi:x}UL' for _, hi in spans) + '};\n'
        'static const u16 arena_base[]={' + ','.join(f'{x}U' for x in offsets) + '};\n'
        'static u8 arena_find(u32 offset) {\n'
        f'    u8 lo=0,hi={len(spans)}U,mid;\n'
        '    while(lo<hi) {\n'
        '        mid=lo+((hi-lo)>>1);\n'
        '        if(offset<arena_lo[mid]) hi=mid;\n'
        '        else if(offset>=arena_hi[mid]) lo=mid+1U;\n'
        '        else return mid;\n'
        '    }\n'
        '    return 255U;\n'
        '}\n'
    )
    index = '(u16)((u16)offset-(u16)arena_lo[arena_i])+arena_base[arena_i]'
    byte_lookup = (
        '    {u8 arena_i;if(region==0) {arena_i=arena_find(offset);'
        f'if(arena_i!=255U) {{shadowrun_data_select({data_bank}U);'
        f'return shadowrun_arena_tables[{index}];}}}}}}\n'
    )
    word_lookup = (
        '    {u8 arena_i;u16 arena_pos;arena_i=arena_find(offset);'
        'if(arena_i!=255U && offset<arena_hi[arena_i]-1UL) {'
        f'arena_pos={index};shadowrun_data_select({data_bank}U);'
        'return ((u16)shadowrun_arena_tables[arena_pos]<<8)|'
        'shadowrun_arena_tables[arena_pos+1U];}}\n'
    )
    return ArenaReader(declarations, byte_lookup, word_lookup)
