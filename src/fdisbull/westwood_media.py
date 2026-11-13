"""Bounded, non-executing Westwood media readers (PAK, CPS, WSA, EMC2).

Do not publish payloads: these APIs operate on caller-owned bytes and return
metadata or in-memory decoded buffers. Retained files are not game provenance.
CPS/WAS codecs are structural decoders, not a playback-equivalence claim.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import struct

MAX_SOURCE = 64 * 1024 * 1024
MAX_PIXELS = 1024 * 1024
MAX_MEMBERS = 10000


def _u16(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ValueError('truncated 16-bit field')
    return struct.unpack_from('<H', data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError('truncated 32-bit field')
    return struct.unpack_from('<I', data, offset)[0]


def _check(data: bytes, maximum=MAX_SOURCE):
    if type(data) is not bytes or len(data) > maximum:
        raise ValueError('expected bounded immutable bytes')


def inspect_pak(data: bytes) -> dict:
    """PAK v2/v3 index. Never identifies a member by magic or executes it.

    In v3 an empty-named terminal offset may leave an *opaque hidden tail*.
    It is kept out of the last named member instead of silently swallowing it.
    """
    _check(data)
    if len(data) < 9:
        raise ValueError('PAK header too short')
    first = _u32(data, 0)
    if not 9 <= first <= min(len(data), 2 * 1024 * 1024):
        raise ValueError('PAK first-member offset out of range')
    pos = 0
    entries = []
    end_named = None
    while pos < first:
        off = _u32(data, pos)
        pos += 4
        if off == 0:
            if pos != first or not entries:
                raise ValueError('PAK end marker misplaced')
            break
        if off < first or off > len(data):
            raise ValueError('PAK member offset outside payload')
        terminator = data.find(b'\x00', pos, first)
        if terminator < 0 or terminator-pos > 64:
            raise ValueError('PAK filename not bounded')
        name_data = data[pos:terminator]
        pos = terminator + 1
        if not name_data:
            if not entries or end_named is not None:
                raise ValueError('PAK invalid v3 last-member marker')
            end_named = off
            continue
        if end_named is not None or len(entries) >= MAX_MEMBERS:
            raise ValueError('PAK entries after terminal marker or above budget')
        try:
            name = name_data.decode('ascii')
        except UnicodeDecodeError as exc:
            raise ValueError('PAK filename is not ASCII') from exc
        if (not name or name in ('.', '..') or '/' in name or '\\' in name or ':' in name
                or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise ValueError('unsafe PAK filename')
        if entries and off < entries[-1]['offset']:
            raise ValueError('PAK decreasing member offsets')
        entries.append(dict(name=name, offset=off, index=len(entries)))
    else:
        raise ValueError('PAK end marker missing')
    if end_named is not None and (end_named < entries[-1]['offset'] or end_named > len(data)):
        raise ValueError('PAK invalid final member end')
    names = Counter(item['name'].casefold() for item in entries)
    for i, entry in enumerate(entries):
        entry['duplicate_name'] = names[entry['name'].casefold()] > 1
        end = entries[i+1]['offset'] if i+1 < len(entries) else (end_named if end_named is not None else len(data))
        if end < entry['offset']:
            raise ValueError('PAK overlapping members')
        payload = data[entry['offset']:end]
        entry.update(size=len(payload), sha256=sha256(payload).hexdigest())
    tail = len(data)-(end_named if end_named is not None else len(data))
    return dict(format='westwood-pak-v3' if end_named is not None else 'westwood-pak-v2',
                size=len(data), sha256=sha256(data).hexdigest(), members=entries,
                opaque_tail_bytes=tail, member_content_verified=True, input_executed=False)


def _copy_history(out: bytearray, pos: int, count: int, limit: int) -> None:
    if count <= 0 or pos < 0 or pos >= len(out) or len(out)+count > limit:
        raise ValueError('LCW invalid history reference or output limit')
    # Must permit overlapping LZ expansions (copy previous byte repeatedly).
    for _ in range(count):
        out.append(out[pos]); pos += 1


def decode_lcw(data: bytes, *, expected_size: int | None = None,
               max_output: int = MAX_PIXELS, allow_unterminated: bool = False) -> bytes:
    """Westwood LCW (Format80), absolute or leading-zero-relative mode.

    No guessing on invalid input, bounded output and source command reads.
    """
    _check(data)
    if not isinstance(max_output, int) or type(max_output) is bool or not 1 <= max_output <= 16*1024*1024:
        raise ValueError('invalid LCW output budget')
    if expected_size is not None and (type(expected_size) is not int or not 0 <= expected_size <= max_output):
        raise ValueError('invalid expected LCW size')
    pos = 1 if data[:1] == b'\x00' else 0
    relative = pos == 1
    out = bytearray()
    terminated = False
    while pos < len(data):
        op = data[pos]; pos += 1
        if op == 0x80:
            terminated = True
            break
        if op & 0x80 == 0:
            if pos >= len(data): raise ValueError('LCW truncated short copy')
            count = ((op & 0x70) >> 4) + 3
            dist = ((op & 0x0F) << 8) | data[pos]; pos += 1
            _copy_history(out, len(out)-dist, count, max_output)
        elif op & 0x40 == 0:
            count = op & 0x3f
            if not count or pos+count > len(data) or len(out)+count > max_output:
                raise ValueError('LCW invalid literal length')
            out.extend(data[pos:pos+count]); pos += count
        elif op == 0xFE:
            if pos+3 > len(data): raise ValueError('LCW truncated fill command')
            count = _u16(data, pos); value = data[pos+2]; pos += 3
            if not count or len(out)+count > max_output: raise ValueError('LCW fill size out of range')
            out.extend(bytes([value])*count)
        else:
            if op == 0xFF:
                if pos+4 > len(data): raise ValueError('LCW truncated long copy')
                count = _u16(data, pos); where = _u16(data, pos+2); pos += 4
            else:
                if pos+2 > len(data): raise ValueError('LCW truncated medium copy')
                count = (op & 0x3F) + 3; where = _u16(data, pos); pos += 2
            _copy_history(out, len(out)-where if relative else where, count, max_output)
    if not terminated and not allow_unterminated:
        raise ValueError('LCW terminator missing')
    if pos != len(data) and any(x != 0 for x in data[pos:]):
        raise ValueError('LCW unexpected trailing bytes')
    if expected_size is not None and len(out) != expected_size:
        raise ValueError('LCW output size mismatch')
    return bytes(out)


def decode_rle3(data: bytes, *, expected_size: int, max_output: int = MAX_PIXELS) -> bytes:
    """Westwood CPS PC Format 3, including big-endian long repeat."""
    _check(data)
    if (type(expected_size) is not int or not 0 <= expected_size <= max_output
            or max_output > 16 * 1024 * 1024):
        raise ValueError('RLE3 output budget invalid')
    out=bytearray(); pos=0
    while pos < len(data):
        code = data[pos]; pos += 1
        if code == 0:
            if pos+3 > len(data): raise ValueError('RLE3 truncated long repeat')
            count = struct.unpack_from('>H',data,pos)[0]; value=data[pos+2]; pos+=3
            if not count: raise ValueError('RLE3 zero repeat count')
            chunk = bytes((value,))*count
        elif code & 0x80:
            if pos >= len(data): raise ValueError('RLE3 truncated repeat')
            count=256-code; chunk=bytes((data[pos],))*count; pos+=1
        else:
            count=code
            if pos+count > len(data): raise ValueError('RLE3 truncated literal')
            chunk=data[pos:pos+count];pos+=count
        if len(out)+len(chunk)>expected_size:
            raise ValueError('RLE3 output overrun')
        out.extend(chunk)
    if len(out)!=expected_size: raise ValueError('RLE3 output truncated')
    return bytes(out)


@dataclass(frozen=True)
class CPSImage:
    pixels: bytes
    palette: bytes | None
    compression: int
    declared_size: int
    width: int | None
    height: int | None


def decode_cps(data: bytes) -> CPSImage:
    """Decode DOS-PC CPS types 0 (raw), 3 (RLE), 4 (LCW) to indexed pixels.

    Odd-size small CPS payloads are returned as raw indexed buffers with
    unknown geometry; we never guess that they are a 320x200 screenshot.
    """
    _check(data, 2*1024*1024)
    if len(data) < 10: raise ValueError('CPS header truncated')
    size,method,output_size,palette_size=struct.unpack_from('<HHIH',data)
    if method not in (0,3,4): raise ValueError('CPS compression not supported')
    if size != (len(data)-2 if method in (0,4) else len(data)):
        raise ValueError('CPS declared file size mismatch')
    if not 0 < output_size <= MAX_PIXELS:
        raise ValueError('CPS decoded size exceeds limit')
    if palette_size not in (0,768) or len(data)<10+palette_size:
        raise ValueError('unsupported CPS palette layout')
    palette=data[10:10+palette_size] or None
    compressed=data[10+palette_size:]
    if method==0:
        if len(compressed)!=output_size: raise ValueError('CPS raw size mismatch')
        pixels=compressed
    elif method==3:
        pixels=decode_rle3(compressed,expected_size=output_size)
    else:
        pixels=decode_lcw(compressed,expected_size=output_size)
    return CPSImage(pixels,palette,method,output_size,
                    320 if output_size==64000 else None,
                    200 if output_size==64000 else None)


def inspect_wsa(data: bytes) -> dict:
    """Bounded offset/palette census for Kyrandia's early and LoL's late WSA.

    Frames remain compressed; a reader does not infer playback rate or initial
    state across linked animations. Use decode_wsa_frames for supported frames.
    """
    _check(data)
    if len(data) < 20: raise ValueError('WSA truncated')
    frames = _u16(data,0)
    if not 0 < frames <= 2000: raise ValueError('WSA frame-count budget')
    candidates=[]
    for variant,header in [('early',8),('early-flags',10),('late',14)]:
        if variant in ('early','early-flags'):
            width,height,delta=_u16(data,2),_u16(data,4),_u16(data,6)
            flags=0 if variant=='early' else _u16(data,8)
            xy=(0,0)
        else:
            xy=(_u16(data,2),_u16(data,4));width,height,delta,flags=(_u16(data,6),_u16(data,8),_u16(data,10),_u16(data,12))
        if not 0 < width*height <= MAX_PIXELS or not 0 < delta <= MAX_PIXELS or flags & ~(3 if variant=='late' else 1):
            continue
        count=frames+2
        table_end=header+4*count
        if table_end > len(data):continue
        offsets=[_u32(data,header+4*i) for i in range(count)]
        palette_size=768 if flags & 1 else 0
        base=table_end+palette_size
        if base>len(data):continue
        nonzero=[o for o in offsets if o]
        if any(o+palette_size>len(data) or o<table_end for o in nonzero):continue
        if any(b<a for a,b in zip(nonzero,nonzero[1:])):continue
        if offsets[0] not in (0,table_end):continue
        # Last offset is 0 if no loop delta, else the preceding offset is loop.
        if (offsets[-1] == 0 and offsets[-2] + palette_size != len(data)) or (offsets[-1] and offsets[-1]+palette_size!=len(data)):
            continue
        if not any(nonzero): continue
        candidates.append(dict(variant=variant,frames=frames,x=xy[0],y=xy[1],
            width=width,height=height,delta_buffer_declared=delta,flags=flags,
            palette_bytes=palette_size,offsets=offsets,header_end=table_end,
            missing_first_frame=offsets[0]==0,has_loop_delta=offsets[-1]!=0,
            xor_flag=bool(flags & 2)))
    if len(candidates)!=1:raise ValueError('WSA header unsupported or ambiguous')
    report=candidates[0]
    report.update(format='westwood-wsa',size=len(data),sha256=sha256(data).hexdigest(),
                  frame_data_verified=False,input_executed=False)
    return report


def _apply_xor_delta(stream: bytes, target: bytearray) -> None:
    """Format40 byte XOR delta; every command range is checked."""
    pos=0;cur=0;end=False
    while pos<len(stream):
        op=stream[pos]; pos+=1
        if op & 0x80:
            if op!=0x80:
                cur+=op & 0x7f
                if cur>len(target):raise ValueError('WSA skip overflow')
                continue
            if pos+2>len(stream):raise ValueError('WSA long command truncated')
            command=_u16(stream,pos);pos+=2
            if command==0: end=True; break
            case=command>>14;count=command&0x3fff if case>=2 else command
            if case<2:
                cur+=count
                if cur>len(target):raise ValueError('WSA long skip overflow')
                continue
            if case==2:
                if pos+count>len(stream):raise ValueError('WSA XOR data truncated')
                payload=stream[pos:pos+count];pos+=count
            else:
                if pos>=len(stream):raise ValueError('WSA XOR fill truncated')
                payload=bytes([stream[pos]])*count;pos+=1
        elif op:
            if pos+op>len(stream):raise ValueError('WSA XOR short truncated')
            payload=stream[pos:pos+op];pos+=op
        else:
            if pos+2>len(stream):raise ValueError('WSA XOR repeat truncated')
            count,value=stream[pos],stream[pos+1];pos+=2
            if not count:raise ValueError('WSA XOR repeat zero count')
            payload=bytes([value])*count
        if cur+len(payload)>len(target):raise ValueError('WSA XOR output overflow')
        for b in payload:
            target[cur]^=b;cur+=1
    if not end:raise ValueError('WSA XOR end marker missing')
    if pos!=len(stream) and any(x!=0 for x in stream[pos:]):
        raise ValueError('WSA XOR trailing bytes')


def decode_wsa_frames(data: bytes, *, max_frames=1, previous: bytes | None=None) -> tuple[dict,list[bytes]]:
    """Decode selected indexed WSA animation frames in memory, never run them.

    Chained (no initial frame) animations require caller's exact previous
    decoded frame, which must be provenance-bound by the caller.
    """
    info=inspect_wsa(data)
    if type(max_frames) is not int or not 1<=max_frames<=min(info['frames'],256):
        raise ValueError('WSA frame count out of budget')
    area=info['width']*info['height']
    if max_frames*area>16*1024*1024:raise ValueError('WSA decoded-frame budget')
    if previous is None:
        if info['missing_first_frame']:
            raise ValueError('WSA requires previous chained animation state')
        image=bytearray(area)
    else:
        if type(previous) is not bytes or len(previous)!=area:
            raise ValueError('WSA previous frame does not match dimensions')
        image=bytearray(previous)
    offset_list=info['offsets']; pal=info['palette_bytes']
    frames=[]
    for frame in range(max_frames):
        start,end=offset_list[frame],offset_list[frame+1]
        if not start and frame==0:
            frames.append(bytes(image));continue
        if not start or not end or end<start or end+pal>len(data):
            raise ValueError('WSA frame extent invalid')
        packed=data[start+pal:end+pal]
        delta=decode_lcw(packed,max_output=min(MAX_PIXELS,info['delta_buffer_declared']+37),allow_unterminated=True)
        _apply_xor_delta(delta,image)
        frames.append(bytes(image))
    return {key:value for key,value in info.items() if key!='offsets'},frames


def parse_emc2(data: bytes) -> dict:
    """Byte-exact IFF FORM/EMC2 parsing; a script is not executed."""
    _check(data,8*1024*1024)
    if len(data)<28 or data[:4]!=b'FORM' or data[8:12]!=b'EMC2':
        raise ValueError('not a Westwood FORM/EMC2 script')
    size=struct.unpack_from('>I',data,4)[0]
    if size!=len(data):raise ValueError('EMC2 nonconforming FORM size')
    pos=12; chunks={}; spans={}
    while pos<len(data):
        if pos+8>len(data):raise ValueError('EMC2 truncated chunk header')
        tag=data[pos:pos+4]; n=struct.unpack_from('>I',data,pos+4)[0];pos+=8
        if tag not in (b'ORDR',b'TEXT',b'DATA') or tag in chunks or n>len(data)-pos:
            raise ValueError('EMC2 unexpected/duplicate/out-of-bounds chunk')
        spans[tag.decode()]=dict(offset=pos,size=n)
        chunks[tag]=data[pos:pos+n];pos+=n
        if n&1:
            if pos>=len(data) or data[pos]!=0:raise ValueError('EMC2 missing odd chunk padding')
            pos+=1
    if b'ORDR' not in chunks or b'DATA' not in chunks or len(chunks[b'ORDR'])%2 or len(chunks[b'DATA'])%2:
        raise ValueError('EMC2 missing or odd-size word chunk')
    entries=list(struct.unpack('>'+ 'H'*(len(chunks[b'ORDR'])//2),chunks[b'ORDR']))
    words=list(struct.unpack('>'+ 'H'*(len(chunks[b'DATA'])//2),chunks[b'DATA']))
    if any(e!=0xffff and e>=len(words) for e in entries):
        raise ValueError('EMC2 entry outside word buffer')
    return dict(format='westwood-emc2',size=len(data),sha256=sha256(data).hexdigest(),
                chunks=spans,entry_slots=entries,word_count=len(words),
                valid_entry_count=sum(e!=0xffff for e in entries),input_executed=False)


def encode_cps_png(image: CPSImage) -> bytes:
    """PNG preview only when source contains a complete 6-bit VGA palette.

    This is a derived visualization, never a claim of display/video parity.
    Unpaletted images require a verified external palette, not invented RGB.
    Uses Python stdlib so the fDisBull tool wheel needs no image dependency.
    """
    import zlib

    if not isinstance(image, CPSImage) or image.width != 320 or image.height != 200:
        raise ValueError('CPS preview requires verified 320x200 indexed image')
    if image.palette is None or len(image.palette) != 768:
        raise ValueError('CPS preview requires a source-embedded VGA palette')
    if len(image.pixels) != 64000:
        raise ValueError('CPS preview buffer length mismatch')
    # VGA DAC channels have 6 bits; PNG PLTE entries have 8 bits.
    pal=bytes(min(255, (value*255+31)//63) for value in image.palette)

    def chunk(tag, value):
        return (struct.pack('>I',len(value)) + tag + value
                + struct.pack('>I',zlib.crc32(tag+value)&0xffffffff))

    scanlines=b''.join(b'\x00'+image.pixels[i:i+320] for i in range(0,64000,320))
    return (b'\x89PNG\r\n\x1a\n'
            +chunk(b'IHDR',struct.pack('>IIBBBBB',320,200,8,3,0,0,0))
            +chunk(b'PLTE',pal)
            +chunk(b'IDAT',zlib.compress(scanlines,6))
            +chunk(b'IEND',b''))
