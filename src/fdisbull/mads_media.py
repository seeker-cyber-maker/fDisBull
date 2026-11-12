"""Reusable MADS asset decoders, independent of its processor and ScummVM.

Byte-oriented APIs return immutable decoded planes/PCM with source metadata.
No game execution, guessed palettes, host filesystem traversal, or subprocess.
Source-assisted format work; see docs/MADS_MEDIA_RUNTIME.md for provenance.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import io
import struct
import wave
import zlib

from .mads_resources import MadsPack, snapshot, require, bounded_int, MAX_RESOURCE
from .codec_fab import decode_fab
from .codec_dcl import decode_dcl

MAX_PIXELS = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


def identity(data):
    return {'size': len(data), 'sha256': sha256(data).hexdigest()}


def _area(width, height, *, empty=False):
    bounded_int(width, 'width', 0 if empty else 1, 4096)
    bounded_int(height, 'height', 0 if empty else 1, 4096)
    require(width * height <= MAX_PIXELS, 'Decoded pixel budget exceeded')
    return width * height


def _unpack(kind, data, size):
    if kind == 0:
        require(size <= len(data), 'Truncated raw media payload')
        return data[:size], size
    if kind == 1:
        return decode_fab(data, size)
    if kind == 3:
        return decode_dcl(data, size)
    raise ValueError('Unsupported embedded media compression')


def _palette(data, *, fixed=False):
    require(len(data) >= 2, 'Missing palette count')
    count = struct.unpack_from('<H', data)[0]
    require(count <= 256 and len(data) >= 2 + 6 * (256 if fixed else count),
            'Invalid six-byte palette directory')
    colors, fields = [], []
    for i in range(count):
        r, g, b, slot, reserved, flags = data[2 + 6*i:8 + 6*i]
        require(max(r, g, b) <= 63, 'Palette component is not VGA six-bit')
        colors.append((r * 255 // 63, g * 255 // 63, b * 255 // 63))
        fields.append({'source_index': i, 'stored_slot': slot,
                       'reserved': reserved, 'flags': flags})
    return tuple(colors), fields


@dataclass(frozen=True)
class IndexedImage:
    width: int
    height: int
    pixels: bytes
    palette: tuple[tuple[int, int, int], ...] | None = None
    transparent: int | None = None
    origin: tuple[int, int] = (0, 0)

    def __post_init__(self):
        area = _area(self.width, self.height, empty=True)
        require(type(self.pixels) is bytes and len(self.pixels) == area,
                'Indexed plane length disagrees with dimensions')
        if self.transparent is not None:
            bounded_int(self.transparent, 'transparent index', 0, 255)
        if self.palette is not None:
            require(type(self.palette) is tuple and len(self.palette) <= 256,
                    'Expected immutable palette')
            for rgb in self.palette:
                require(type(rgb) is tuple and len(rgb) == 3 and all(
                    type(v) is int and 0 <= v <= 255 for v in rgb), 'Invalid RGB palette')
            require(all(v == self.transparent or v < len(self.palette) for v in self.pixels),
                    'Pixel index is outside supplied palette')

    def metadata(self):
        return dict(width=self.width, height=self.height, origin=list(self.origin),
                    pixels=identity(self.pixels), palette_entries=(None if self.palette is None else len(self.palette)),
                    transparent=self.transparent, empty=not self.pixels,
                    color_scope='resource-local palette; no live palette allocation/cycling')

    def rgba(self):
        require(self.palette is not None, 'Color export requires an explicitly supplied palette')
        require(bool(self.pixels), 'Empty frames have metadata but no PNG raster')
        palette = [bytes((*rgb, 255)) for rgb in self.palette]
        result = bytearray(len(self.pixels) * 4)
        for i, value in enumerate(self.pixels):
            if value != self.transparent:
                result[i*4:i*4+4] = palette[value]
        return bytes(result)

    def png(self):
        """Encode RGBA PNG losslessly using only the standard library."""
        data = self.rgba()
        def chunk(tag, payload):
            return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', zlib.crc32(tag + payload))
        scanlines = b''.join(b'\0' + data[y*self.width*4:(y+1)*self.width*4] for y in range(self.height))
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', self.width, self.height, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))


@dataclass(frozen=True)
class AudioSample:
    rate: int
    pcm: bytes
    channels: int = 1

    def __post_init__(self):
        bounded_int(self.rate, 'sample rate', 1, 65535)
        require(type(self.pcm) is bytes and len(self.pcm) <= MAX_TOTAL, 'PCM budget exceeded')
        require(type(self.channels) is int and self.channels == 1, 'Only the qualified unsigned-8 mono DSR profile is supported')

    def wav(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as out:
            out.setnchannels(self.channels); out.setsampwidth(1); out.setframerate(self.rate)
            out.writeframes(self.pcm)
        return buffer.getvalue()

    def metadata(self):
        return dict(rate=self.rate, channels=self.channels, sample_format='u8',
                    samples=len(self.pcm), pcm=identity(self.pcm))


def decode_sprite_pixels(data: bytes, width: int, height: int) -> tuple[bytes, int]:
    """Decode the bounded MADS scanline RLE stream to local palette indices."""
    area = _area(width, height, empty=True)
    require(type(data) is bytes and len(data) <= MAX_RESOURCE, 'Invalid sprite stream')
    pixels = bytearray([255]) * area
    at = x = y = 0

    def byte():
        nonlocal at
        require(at < len(data), 'Truncated sprite command')
        value = data[at]; at += 1
        return value

    def emit(count, value):
        nonlocal x
        require(y < height and x + count <= width, 'Sprite run crosses raster boundary')
        value = 255 if value == 253 else value
        pixels[y*width+x:y*width+x+count] = bytes([value]) * count
        x += count

    while at < len(data):
        marker = byte()
        if marker == 252:
            return bytes(pixels), at
        if marker == 255:
            y += 1; x = 0
            require(y <= height, 'Too many sprite rows')
            continue
        # FD selects an RLE-only row; other row prefixes select mixed literals.
        while True:
            value = byte()
            if value == 255:
                y += 1; x = 0
                require(y <= height, 'Too many sprite rows')
                break
            if marker == 253:
                emit(value, byte())
            elif value == 254:
                count, color = byte(), byte(); emit(count, color)
            else:
                emit(1, value)
    raise ValueError('Sprite stream lacks terminator')


def decode_sprites(source):
    pack = MadsPack.read(source)
    require(len(pack.sections) == 4, 'SS requires four sections')
    header, directory, palette_data, payload = (s.data for s in pack.sections)
    require(len(header) >= 40, 'Truncated SS header')
    mode, count = header[0], struct.unpack_from('<H', header, 38)[0]
    require(mode in (0, 1) and 1 <= count <= 4096 and len(directory) == 16*count,
            'Unsupported SS mode/frame directory')
    palette, fields = _palette(palette_data)
    records = tuple(struct.iter_unpack('<IIhhHH', directory))
    if mode == 0:
        spans = sorted(set((a, a+n) for a,n,_,_,_,_ in records if n))
        require(all(a[1] <= b[0] for a,b in zip(spans, spans[1:])),
                'Partially overlapping sprite frames')
    require(sum(w*h for _, _, _, _, w, h in records) <= MAX_TOTAL, 'Sprite-set pixel budget exceeded')
    images, details = [], []
    for i, (offset, size, left, top, width, height) in enumerate(records):
        _area(width, height, empty=True)
        require(size <= MAX_RESOURCE and offset <= len(payload), 'Invalid sprite frame extent')
        end = offset + size if mode == 0 else (records[i+1][0] if i+1 < count else len(payload))
        require(offset <= end <= len(payload), 'Invalid sprite frame ordering/extent')
        stored = payload[offset:end]
        data, used = (stored, len(stored)) if mode == 0 else decode_fab(stored, size)
        if not data and width * height == 0:
            pixels, consumed = b'', 0
        else:
            pixels, consumed = decode_sprite_pixels(data, width, height)
        image = IndexedImage(width, height, pixels, palette, 255, (left, top))
        images.append(image)
        details.append(dict(index=i, offset=offset, stored_bytes=len(stored),
                            compression_consumed=used, command_consumed=consumed,
                            command_tail_bytes=len(data)-consumed, **image.metadata()))
    return tuple(images), dict(format='mads-sprites-1', source=identity(pack.source),
                               mode=mode, frames=details, palette_fields=fields,
                               pack=pack.metadata(), execution=False)


def decode_tiles(source, *, depth=False):
    """TT tiles use offsets relative to the end of the MADSPACK sections."""
    require(type(depth) is bool, 'depth must be Boolean')
    pack = MadsPack.read(source)
    h = pack.sections[0].data
    require(len(h) >= 8, 'Truncated TT header')
    count, width, height, compression = struct.unpack_from('<4H', h)
    if count == 0:
        # The offset section is absent when no tiles exist. Do not interpret
        # stale unused palette entries as pixels or manufacture a background.
        require(len(pack.sections) == (1 if depth else 3) and pack.end == len(pack.source),
                'Empty TT has an unexpected directory or appended payload')
        _area(width, height)
        return (), dict(format='mads-tiles-1', source=identity(pack.source), depth=depth,
                        compression=compression, tiles=[], empty=True, width=width, height=height,
                        pack=pack.metadata(), execution=False, rendering_available=False)
    require(len(pack.sections) == (2 if depth else 4), 'TT section count disagrees with selected plane')
    bounded_int(count, 'tile count', 1, 4096)
    area = _area(width, height)
    require(area * count <= MAX_TOTAL, 'Tile-set expansion budget exceeded')
    directory = pack.sections[1].data
    require(len(directory) == 4*count, 'TT offset table length mismatch')
    offsets = [v[0] for v in struct.iter_unpack('<I', directory)]
    require(all(a <= b for a, b in zip(offsets, offsets[1:])), 'TT offsets are not ordered')
    payload = pack.source[pack.end:]
    require(all(v <= len(payload) for v in offsets), 'TT offset is outside appended payload')
    colors, fields = (None, []) if depth else _palette(pack.sections[2].data, fixed=True)
    cycles = []
    if not depth:
        cycle_data = pack.sections[3].data
        require(len(cycle_data) >= 2, 'Missing palette cycle count')
        n = struct.unpack_from('<H', cycle_data)[0]
        require(n <= 8 and len(cycle_data) >= 2+4*n, 'Palette cycle list exceeds bounds')
        cycles = [dict(color_count=a, first_list_color=b, stored_palette_color=c, ticks=d)
                  for a,b,c,d in struct.iter_unpack('<4B', cycle_data[2:2+4*n])]
    images, details = [], []
    for i, start in enumerate(offsets):
        end = offsets[i+1] if i+1 < count else len(payload)
        expected = ((width+1)//2 if depth else width)*height
        raw, consumed = _unpack(compression, payload[start:end], expected)
        if depth:
            stride = (width+1)//2
            pixels = bytes((raw[y*stride+x//2] >> (0 if x&1 else 4)) & 15
                           for y in range(height) for x in range(width))
        else:
            pixels = raw
        image = IndexedImage(width, height, pixels, colors)
        images.append(image)
        details.append(dict(index=i, source_offset=pack.end+start, stored_bytes=end-start,
                            consumed_bytes=consumed, opaque_tail_bytes=end-start-consumed,
                            **image.metadata()))
    return tuple(images), dict(format='mads-tiles-1', source=identity(pack.source),
                               depth=depth, compression=compression, tiles=details,
                               palette_fields=fields, palette_cycles=cycles,
                               pack=pack.metadata(), execution=False)


def decode_background(tile_source, map_source, *, depth=False):
    tiles, report = decode_tiles(tile_source, depth=depth)
    require(bool(tiles), 'Empty tile resource has no renderable background')
    pack = MadsPack.read(map_source)
    require(len(pack.sections) == 2 and len(pack.sections[0].data) >= 16, 'Invalid MM map header')
    _, _, nx, ny, tw, th, view_w, view_h = struct.unpack_from('<8H', pack.sections[0].data)
    require(1 <= nx*ny <= 16384 and (tw, th) == (tiles[0].width, tiles[0].height),
            'MM geometry does not match TT')
    width, height = nx*tw, ny*th
    _area(width, height)
    require(0 < view_w <= width and 0 < view_h <= height, 'MM viewport is outside tile canvas')
    directory = pack.sections[1].data
    require(len(directory) == 2*nx*ny, 'MM index table size mismatch')
    indices = tuple(v[0] for v in struct.iter_unpack('<H', directory))
    require(all(v < len(tiles) for v in indices), 'MM tile reference is outside TT')
    output = bytearray(width*height)
    for index, tile_id in enumerate(indices):
        x, y = (index % nx)*tw, (index // nx)*th
        tile = tiles[tile_id]
        for row in range(th):
            output[(y+row)*width+x:(y+row)*width+x+tw] = tile.pixels[row*tw:(row+1)*tw]
    image = IndexedImage(width, height, bytes(output), tiles[0].palette)
    return image, dict(format='mads-background-1', tile_source=report['source'],
                       map_source=identity(pack.source), viewport=[view_w, view_h],
                       tile_count=len(tiles), map_cells=len(indices), depth=depth,
                       image=image.metadata(), execution=False)


def decode_dsr(source):
    data = snapshot(source, MAX_TOTAL)
    require(len(data) >= 2, 'Missing DSR directory')
    count = struct.unpack_from('<H', data)[0]
    require(1 <= count <= 16384 and 2+18*count <= len(data), 'Invalid DSR count/directory')
    records = tuple(struct.iter_unpack('<HIIII', data[2:2+18*count]))
    require(sum(r[3] for r in records) <= MAX_TOTAL, 'DSR decoded PCM budget exceeded')
    samples, details, intervals = [], [], []
    for i, (rate, channels, stored, size, offset) in enumerate(records):
        require(2+18*count <= offset <= len(data) and stored <= len(data)-offset, 'DSR sample outside source')
        require(channels == 1, 'Unsupported DSR channel layout')
        pcm, used = decode_fab(data[offset:offset+stored], size)
        sample = AudioSample(rate, pcm, channels)
        samples.append(sample)
        details.append(dict(index=i, offset=offset, stored_bytes=stored, consumed_bytes=used,
                            opaque_tail_bytes=stored-used, **sample.metadata()))
        if stored: intervals.append((offset, offset+stored))
    spans = sorted(set(intervals))
    require(all(a[1] <= b[0] for a,b in zip(spans,spans[1:])), 'Partially overlapping DSR samples')
    return tuple(samples), dict(format='mads-dsr-1', source=identity(data), samples=details,
                                execution=False, playback_timing_verified=False)


def decode_font(source):
    """Decode 127 two-bit glyph planes. Colors remain caller-supplied, not guessed."""
    pack = MadsPack.read(source)
    require(len(pack.sections) == 1, 'FF requires one section')
    data = pack.sections[0].data
    require(len(data) >= 386, 'FF header is truncated')
    height, max_width = data[:2]
    require(1 <= height <= 255 and 1 <= max_width <= 16, 'Unsupported FF geometry')
    images, details = [], []
    for code in range(1, 128):
        width = data[1+code]
        offset = struct.unpack_from('<H', data, 130+2*(code-1))[0]
        require(width <= max_width, 'FF glyph exceeds maximum width')
        stride = (width+3)//4
        if width:
            require(386 <= offset <= len(data) and stride*height <= len(data)-offset, 'FF glyph outside section')
        pixels = bytes((data[offset+y*stride+x//4] >> (6-2*(x&3))) & 3
                       for y in range(height) for x in range(width))
        image = IndexedImage(width, height, pixels, transparent=0)
        images.append(image)
        details.append(dict(code=code, section_offset=offset, **image.metadata()))
    return tuple(images), dict(format='mads-font-1', source=identity(pack.source),
                               glyphs=details, max_width=max_width, height=height,
                               colors='four runtime-selected values; not embedded', execution=False)


def decode_mask(source, *, width, height):
    """WW/PP packed one-bit planes, without assigning collision/pathfinding intent."""
    _area(width,height)
    pack = MadsPack.read(source)
    require(len(pack.sections)==1, 'Bit mask requires one section')
    raw=pack.sections[0].data; stride=(width+7)//8
    require(len(raw)==stride*height, 'Mask size disagrees with explicit geometry')
    pixels=bytes((raw[y*stride+x//8] >> (7-(x&7))) & 1 for y in range(height) for x in range(width))
    image=IndexedImage(width,height,pixels)
    return image, dict(format='mads-mask-1',source=identity(pack.source),image=image.metadata(),execution=False)


def decode_animation(source):
    """Decode AA timeline/reference records, not live scene compositing or timing."""
    pack=MadsPack.read(source); h=pack.sections[0].data
    require(len(h)>=751, 'AA header truncated')
    ns,nmisc,nframes,nmsg,flags,spacing,bg,room=struct.unpack_from('<5Hh2H',h)
    require(ns<=50 and bg in (1,2,3,4), 'Unsupported AA header profile')
    def name(offset):
        return h[offset:offset+13].split(b'\0',1)[0].decode('ascii','backslashreplace')
    report=dict(format='mads-animation-1', source=identity(pack.source),
                pack=pack.metadata(), sprite_names=[name(49+13*i) for i in range(ns)],
                background_name=name(36), sound_name=name(699), dsr_name=name(725),font_name=name(738),
                flags=flags,char_spacing=spacing,background_type=bg,room=room,
                manual_flag=struct.unpack_from('<H',h,18)[0], manual_sprite_index=struct.unpack_from('<H',h,20)[0],
                scroll_position=list(struct.unpack_from('<hh',h,22)),scroll_ticks_raw=struct.unpack_from('<I',h,26)[0],
                execution=False, playback=False, time_unit='engine ticks, frequency unqualified')
    cursor=1; messages=[]; frames=[]; misc=[]
    if nmsg:
        require(cursor<len(pack.sections), 'Missing AA messages'); d=pack.sections[cursor].data;cursor+=1
        require(len(d)==96*nmsg, 'AA message record size mismatch')
        for i in range(nmsg):
            r=d[96*i:96*i+96]
            messages.append(dict(index=i,sound_id=struct.unpack_from('<h',r)[0],
                 text_sha256=sha256(r[2:66]).hexdigest(),position=list(struct.unpack_from('<hh',r,70)),
                 flags=struct.unpack_from('<H',r,74)[0],start_frame=struct.unpack_from('<H',r,90)[0],
                 end_frame=struct.unpack_from('<H',r,92)[0]))
    if nframes:
        require(cursor<len(pack.sections),'Missing AA frame list');d=pack.sections[cursor].data;cursor+=1
        size=10 if bg==4 else 12
        require(len(d)==nframes*size, 'AA frame record size mismatch')
        for i in range(nframes):
            r=d[i*size:(i+1)*size]
            frame,seq,sprite=struct.unpack_from('<HBB',r)
            if bg==4:
                sf=struct.unpack_from('<b',r,4)[0];depth=scale=None;frame=None
            else:
                sf=struct.unpack_from('<H',r,4)[0]
                sf=-(sf&32767) if sf&32768 else sf
                frame=-(frame&32767) if frame&32768 else frame
                depth,scale=struct.unpack_from('<bb',r,10)
            frames.append(dict(index=i,timeline_frame=frame,sequence=seq,sprite_index=sprite,
                        sprite_frame=sf,position=list(struct.unpack_from('<hh',r,6)),depth=depth,scale=scale))
    if nmisc:
        require(cursor<len(pack.sections),'Missing AA timing records');d=pack.sections[cursor].data;cursor+=1
        size=20 if bg==4 else 10
        require(len(d)==nmisc*size, 'AA timing record size mismatch')
        for i in range(nmisc):
            r=d[i*size:(i+1)*size]
            if bg==4:
                a,b,c,e,f=struct.unpack_from('<4Hh',r)
                misc.append(dict(index=i,probability=a,image_count=b,first_image=c,last_image=e,counter=f,
                                 spawns=list(r[10:12]),spawn_frames=list(struct.unpack_from('<HH',r,12)),
                                 sound_raw=struct.unpack_from('<H',r,16)[0],sound_frame=struct.unpack_from('<H',r,18)[0]))
            else:
                a,b,t,x,y,sx,sy=struct.unpack('<BbHhhbb',r)
                misc.append(dict(index=i,sound_id=a,message_index=b,ticks=t,position_adjust=[x,y],scroll=[sx,sy]))
    require(cursor==len(pack.sections),'Unrecognized extra AA section')
    report.update(messages=messages,frames=frames,timing=misc)
    return report
