"""Bounded, stopped-memory FreeDOS 1.4 kernel-2043 workspace observation.

Layouts are from the pinned FreeDOS kernel's hdr/lol.h, hdr/sft.h,
 hdr/buffer.h and kernel/blockio.c. No guest calls or writes are made.
The caller must establish the exact kernel identity and stopped address-space
mapping, and must provide a RAM-only, unwrapped physical-memory reader.
"""
import struct

FORMAT = 'fdisbull-freedos-2043-handles-1'
SFT_SIZE = 0x3b


def _word(data, offset=0):
    return struct.unpack_from('<H', data, offset)[0]


def _dword(data, offset=0):
    return struct.unpack_from('<I', data, offset)[0]


def _far(data, offset=0):
    off, seg = struct.unpack_from('<HH', data, offset)
    return seg, off


def _addr(seg, off, length):
    if (type(seg) is not int or type(off) is not int or not 0 <= seg <= 0xffff
            or not 0 <= off <= 0xffff or off + length > 0x10000):
        raise ValueError('Invalid unwrapped FreeDOS far-memory range')
    address = seg * 16 + off
    if address + length > 0x100000:
        raise ValueError('FreeDOS observation requires low RAM; HMA is unqualified')
    return address


def _read(read, seg, off, length):
    result = read(_addr(seg, off, length), length)
    if not isinstance(result, bytes) or len(result) != length:
        raise ValueError('FreeDOS memory reader returned an incomplete range')
    return result


def _scan(read, segment, offset, child_psp):
    lol = _read(read, segment, offset, 0x4b)
    psp = _read(read, child_psp, 0, 0x38)
    if psp[:2] != b'\xcd\x20':
        raise ValueError('Child PSP signature differs')
    count = _word(psp, 0x32)
    if not 1 <= count <= 255:
        raise ValueError('Child PSP handle count exceeds supported bounds')
    jseg, joff = _far(psp, 0x34)
    jft = _read(read, jseg, joff, count)
    table = []
    seg, off = _far(lol, 4)
    seen = set()
    for _ in range(64):
        if (seg, off) == (0xffff, 0xffff):
            break
        if (seg, off) in seen or (seg, off) == (0, 0):
            raise ValueError('FreeDOS SFT chain is cyclic or null')
        seen.add((seg, off))
        header = _read(read, seg, off, 6)
        entries = _word(header, 4)
        if entries > 255 or len(table) + entries > 1024:
            raise ValueError('FreeDOS SFT chain exceeds supported bounds')
        raw = _read(read, seg, off + 6, entries * SFT_SIZE) if entries else b''
        for index in range(entries):
            entry = raw[index*SFT_SIZE:(index+1)*SFT_SIZE]
            refs, mode, flags = _word(entry), _word(entry, 2), _word(entry, 5)
            device = bool(flags & 0x80)
            name_raw = entry[0x20:0x2b]
            name = None
            if refs and not device:
                try:
                    stem = name_raw[:8].decode('ascii').rstrip(' ')
                    extension = name_raw[8:].decode('ascii').rstrip(' ')
                except UnicodeDecodeError as error:
                    raise ValueError('Unsupported non-ASCII FreeDOS SFT filename') from error
                if not stem or any(ord(c) < 32 or c in '/\\' for c in stem + extension):
                    raise ValueError('Invalid FreeDOS SFT filename')
                name = stem + ('.' + extension if extension else '')
            table.append(dict(index=len(table),references=refs,kind='device' if device else 'file',
                              mode=mode,access={0:'read',1:'write',2:'read-write'}.get(mode & 7,'unknown'),
                              flags=flags,drive=(flags & 0x3f) if not device else None,
                              dos_name=name,path=None,size=_dword(entry,0x11) if not device else None,
                              position=_dword(entry,0x15) if not device else None,
                              owner_psp=_word(entry,0x31),sharing='unknown',locks='unknown'))
        seg, off = _far(header)
    else:
        raise ValueError('FreeDOS SFT chain exceeds supported bounds')
    handles = []
    for number, index in enumerate(jft):
        if index == 0xff: continue
        if index >= len(table) or table[index]['references'] == 0:
            raise ValueError('Child PSP references an unknown or closed SFT entry')
        handles.append(dict(handle=number, sft_index=index, **{k:v for k,v in table[index].items() if k != 'index'}))
    buffers = []
    nbuf = _word(lol, 0x3f)
    bseg, first = _far(lol, 0x47)
    if not 1 <= nbuf <= 1024 or (bseg, first) == (0, 0):
        raise ValueError('FreeDOS buffer list has unsupported bounds')
    seen = set(); current = first
    for _ in range(nbuf):
        if current in seen: raise ValueError('FreeDOS buffer list closes early')
        seen.add(current)
        item = _read(read,bseg,current,10)
        buffers.append(dict(offset=current,unit=item[4],flags=item[5],block=_dword(item,6),
                            dirty=bool(item[5]&0x40),valid=bool(item[5]&0x20)))
        current=_word(item)
    if current != first:
        raise ValueError('FreeDOS buffer list does not match its declared count')
    return dict(handles=handles, open_sft=[entry for entry in table if entry['references']], buffers=buffers)


def observe_guest_files(read, list_of_lists_segment, list_of_lists_offset, child_psp):
    """Read two matching bounded snapshots; do not infer a flush or full path.

    The global SFT list includes entries belonging to other PSPs. A device
    handle is not an ordinary file; networked/ambiguous entries remain files.
    """
    first = _scan(read,list_of_lists_segment,list_of_lists_offset,child_psp)
    second = _scan(read,list_of_lists_segment,list_of_lists_offset,child_psp)
    if first != second: raise ValueError('FreeDOS file state changed during observation')
    files=[entry for entry in first['open_sft'] if entry['kind']=='file']
    dirty=[entry for entry in first['buffers'] if entry['dirty']]
    return dict(format=FORMAT,child_psp=child_psp,handles=first['handles'],open_sft=first['open_sft'],
                ordinary_open_count=len(files),buffers=first['buffers'],dirty_buffer_count=len(dirty),
                sharing='unknown',locks='unknown',flush_boundary='unknown',coherent='unknown',
                consistency='two equal stopped-memory observations; no atomicity or flush proof')
