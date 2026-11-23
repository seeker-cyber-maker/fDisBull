"""Authored VBE 101h input-status witness shared by both native producers."""
from fractions import Fraction
from math import ceil, floor
import struct

from support.paired_video_frame_oracle import Interval, PIT_HZ, unwrap_counts


LINE_NS = Fraction(800_000_000, 29_403)
LINE_TICKS = LINE_NS * PIT_HZ / 10**9
FRAME_LINES, DISPLAY_LINES, RETRACE_START, RETRACE_END = 525, 480, 490, 492
EDGE_LIMIT = 3900
RECORD_BYTES = 10

_PROBE = r'''
vbe_timing_probe:
    pushf
    cli
    push cs
    pop ds
    mov byte [timing_go],2

    ; Program channel 2 for a free-running descending 16-bit count.
    in al,61h
    and al,0fch
    out 61h,al
    mov al,0b4h
    out 43h,al
    xor al,al
    out 42h,al
    out 42h,al
    in al,61h
    or al,1
    out 61h,al

    mov dx,3dah
    mov di,edge_journal
    xor si,si
    xor bp,bp
    mov cl,0ffh
vbe_poll:
    call vbe_latch_pit
    mov bx,ax
status_in:
    in al,dx
status_out:
    and al,09h
    mov ch,al
    call vbe_latch_pit
    cmp cl,ch
    je vbe_next_poll
    cmp di,edge_end
    jae vbe_timing_fault
    mov [di],si
    mov [di+2],bp
    mov [di+4],bx
    mov [di+6],ax
    mov [di+8],cx
    add di,10
    inc word [edge_count]
    cmp cl,0ffh
    je vbe_next_poll
    test ch,8
    jnz vbe_next_poll
    test cl,8
    jz vbe_next_poll
    inc byte [vbe_falls]
    cmp byte [vbe_falls],4
    jne vbe_next_poll
    mov byte [timing_result],1
    jmp vbe_timing_restore

vbe_next_poll:
    mov si,bx
    mov bp,ax
    mov cl,ch
    dec dword [vbe_polls_left]
    jnz vbe_poll

vbe_timing_fault:
    mov byte [timing_result],2
vbe_timing_restore:
    popf
timing_done:
    cmp byte [advance],3
    jne timing_done
    jmp banked

vbe_latch_pit:
    mov al,80h
    out 43h,al
    in al,42h
    mov ah,al
    in al,42h
    xchg al,ah
    ret

timing_go: db 0
timing_result: db 0
vbe_falls: db 0
vbe_polls_left: dd 350000
edge_count: dw 0
edge_journal: times 3900*10 db 0
edge_end:
db 'VRT8'
dw timing_go, status_in, status_out, timing_done, timing_result, edge_count, edge_journal
'''
SYMBOLS = ('timing_go', 'status_in', 'status_out', 'timing_done',
           'timing_result', 'edge_count', 'edge_journal')


def source_with_status_probe(original):
    patch = 'banked:\n    cmp byte [advance],3'
    marker = "db 'VGA3'\n"
    assert original.count(patch) == original.count(marker) == 1
    return original.replace(patch, 'banked:\n    cmp byte [timing_go],1\n'
                            '    je vbe_timing_probe\n    cmp byte [advance],3').replace(marker, _PROBE + marker)


def symbols(code):
    pages = len(code) - 62
    footer = pages - 18
    assert code[pages:pages + 4] == b'VGA3'
    assert code[footer:footer + 4] == b'VRT8'
    labels = struct.unpack('<5H', code[pages + 4:pages + 14])
    result = dict(zip(SYMBOLS, struct.unpack('<7H', code[footer + 4:pages]), strict=True))
    assert result['status_out'] == result['status_in'] + 1
    assert code[result['status_in'] - 0x100] == 0xec
    assert result['edge_journal'] - 0x100 + EDGE_LIMIT * RECORD_BYTES == footer
    return labels, result


def _gap(first, second):
    return Interval(second.lo - first.hi, second.hi - first.lo)


def _contains(window, value):
    return window.lo <= value <= window.hi


def read_edges(data):
    assert data and len(data) % RECORD_BYTES == 0 and len(data) <= EDGE_LIMIT * RECORD_BYTES
    raw = list(struct.iter_unpack('<HHHHBB', data))
    lows = unwrap_counts([record[2] for record in raw])
    result = []
    for index, (record, current) in enumerate(zip(raw, lows, strict=True)):
        prior_lo, prior_hi, current_lo, current_hi, old, new = record
        width = (current_lo - current_hi) & 0xffff
        assert width < 32768 and new in (0, 1, 9)
        sample = Interval(current - 1, current + width + 1)
        if index == 0:
            assert old == 0xff and prior_lo == prior_hi == 0
            result.append(dict(old=old, new=new, sample=sample, edge=None))
            continue
        assert old == result[-1]['new'] and old != new and old in (0, 1, 9)
        before = (prior_lo - current_lo) & 0xffff
        beforehand = (prior_hi - current_lo) & 0xffff
        assert 0 <= beforehand <= before < 32768
        edge = Interval(current - before - 1, current + width + 1)
        result.append(dict(old=old, new=new, sample=sample, edge=edge))
    return result


def status_lattice(records, *, line=LINE_TICKS):
    """Check actual producer polling against predeclared closed status windows."""
    changes = records[1:]
    widest = max(rec['edge'].hi - rec['edge'].lo for rec in changes)
    # Disjoint half-line brackets keep observed edges uniquely assignable.
    # Polling can miss a pulse since horizontal blank is only 0.18 lines.
    assert widest < line / 2, widest
    rises = [rec['edge'] for rec in changes if not rec['old'] & 8 and rec['new'] & 8]
    falls = [rec['edge'] for rec in changes if rec['old'] & 8 and not rec['new'] & 8]
    assert 3 <= len(rises) <= 4 and len(falls) == 4
    widths = []
    for index, rise in enumerate(rises):
        latest = rises[index + 1].lo if index + 1 < len(rises) else falls[-1].hi + 1
        fall = [end for end in falls if rise.hi < end.lo < latest]
        assert len(fall) == 1
        width = _gap(rise, fall[0])
        assert _contains(width, (RETRACE_END - RETRACE_START) * line), width
        widths.append(width.json())

    periods = []
    frames = []
    for rise, later in zip(rises, rises[1:]):
        period = _gap(rise, later)
        assert _contains(period, FRAME_LINES * line), period
        periods.append(period.json())

        # Anchor each frame to its guest-observed retrace rise. Horizontal
        # changes interior to visible lines must have exactly one explanation.
        origins = Interval(later.lo - RETRACE_START * line, later.hi - RETRACE_START * line)
        first_active = []
        counts = [set(), set()]
        for record in changes:
            position = _gap(origins, record['edge'])
            if 481 * line < position.lo and position.hi < 524 * line:
                assert record['old'] & 1 and record['new'] & 1
            if (record['old'] ^ record['new']) != 1:
                continue
            if record['new'] == 0 and _contains(position, 0):
                first_active.append(position.json())
            if position.lo <= 2 * line or position.hi >= 477 * line:
                continue
            high = record['new'] == 1
            phase = line * (Fraction(80, 100) if high else Fraction(98, 100))
            low_index = ceil((position.lo - phase) / line)
            high_index = floor((position.hi - phase) / line)
            assert low_index == high_index, (position, high, low_index, high_index)
            assert low_index not in counts[high]
            counts[high].add(low_index)
        assert len(first_active) == 1
        for items in counts:
            positions = sorted(items)
            assert len(positions) >= 250
            assert positions[0] <= 16 and positions[-1] >= 460
            assert all(right - left <= 3 for left, right in zip(positions, positions[1:]))
        frames.append(dict(first_active=first_active[0], hblank_rises=len(counts[1]),
                           hblank_falls=len(counts[0])))
    return dict(vertical_periods_ticks=periods, vertical_widths_ticks=widths,
                widest_edge_bracket_ticks=int(widest), complete_visible_frames=frames)
