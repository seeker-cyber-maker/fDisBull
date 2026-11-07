"""Bounded classic DOS EXEPACK reader; no original program is executed.

References: EXEPACK format documentation and xu4's AVATAR wrapper description.
Supports 16/18-byte headers, skip_len=1, and the observed 35-byte wrapper.
Unknown variants refuse. Rebuilt MZ is analysis-only until native qualification.
"""
from __future__ import annotations
import hashlib
import struct


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def mz_info(data: bytes) -> dict:
    _require(isinstance(data, bytes) and 28 <= len(data) <= 16*1024*1024, 'MZ input bounds')
    w = struct.unpack_from('<14H', data)
    sig, last, pages, rels, paras, minimum, maximum, ss, sp, checksum, ip, cs, rel_at, overlay = w
    _require(sig == 0x5a4d and pages and last < 512, 'invalid DOS MZ header')
    end = (pages-1)*512 + (last or 512)
    head = paras*16
    _require(28 <= head < end <= len(data), 'invalid DOS MZ extents')
    _require(not rels or 28 <= rel_at <= head-4*rels, 'invalid MZ relocations')
    relocations = [struct.unpack_from('<HH', data, rel_at+4*i) for i in range(rels)]
    _require(all(s*16+o+2 <= end-head for o,s in relocations), 'relocation outside image')
    return dict(header_bytes=head, declared_bytes=end, appended_bytes=len(data)-end,
                module_bytes=end-head, cs=cs, ip=ip, ss=ss, sp=sp,
                minalloc=minimum, maxalloc=maximum, relocations=relocations,
                entry_file_offset=head+cs*16+ip, overlay=overlay)


def unpack_exepack(data: bytes, *, max_output=1024*1024) -> tuple[bytes, dict]:
    _require(type(max_output) is int and 16 <= max_output <= 16*1024*1024, 'invalid output budget')
    m = mz_info(data)
    _require(not m['relocations'] and m['overlay'] == 0, 'not an admitted EXEPACK envelope')
    head, entry = m['header_bytes'], m['entry_file_offset']
    cs, ip, wrapper = m['cs'], m['ip'], None
    if ip not in (16,18):
        patterns = ((0,b'\x8c\xd8\x8e\xc0\x05'),(7,b'\x8e\xd0\xbc'),(12,b'\x2d'),
                    (15,b'\x50\xb8'),(19,b'\x50\x31\xc0\x89\xc3\x89\xc1\x89\xc2\x89\xc5\x89\xc6\x89\xc7\xcb'))
        _require(entry+35 <= m['declared_bytes'] and all(data[entry+p:entry+p+len(b)] == b for p,b in patterns),
                 'unknown packed MZ entry; no guessed EXEPACK scan')
        inner_ss = struct.unpack_from('<H', data, entry+5)[0]-16
        cs = inner_ss-struct.unpack_from('<H', data, entry+13)[0]
        ip = struct.unpack_from('<H', data, entry+17)[0]
        _require(cs >= 0 and ip == 18, 'unsupported wrapped EXEPACK entry')
        wrapper = dict(format='ultima-entry-wrapper', offset=entry, bytes=35)
    at = head+cs*16
    _require(head < at and at+ip <= m['declared_bytes'], 'EXEPACK header outside source')
    fields = struct.unpack_from('<'+str(ip//2)+'H', data, at)
    real_ip, real_cs, mem_start, block_size, real_sp, real_ss, paragraphs = fields[:7]
    skip = fields[7] if ip == 18 else 1
    _require(fields[-1] == 0x4252 and skip == 1, 'unsupported EXEPACK signature/skip convention')
    end = at+block_size
    _require(at+ip < end <= (entry if wrapper else m['declared_bytes']), 'EXEPACK block bounds')
    size = paragraphs*16
    packed = data[head:at]
    _require(0 < len(packed) <= size <= max_output, 'EXEPACK expansion limit')
    image = bytearray(size)
    image[:len(packed)] = packed
    src, dst, padding, runs = len(packed), size, 0, 0
    while src and packed[src-1] == 255:
        src -= 1; padding += 1
    _require(padding <= 15, 'unsupported alignment padding')
    while True:
        _require(src >= 3 and runs <= len(packed), 'missing EXEPACK terminator')
        src -= 1; op = packed[src]
        src -= 2; count = struct.unpack_from('<H', packed, src)[0]
        _require(op in (0xb0,0xb1,0xb2,0xb3) and count <= dst, 'invalid EXEPACK run')
        dst -= count
        if op & 0xfe == 0xb0:
            _require(src >= 1, 'truncated EXEPACK fill')
            src -= 1; image[dst:dst+count] = bytes([packed[src]])*count
        else:
            _require(count <= src, 'truncated EXEPACK copy')
            src -= count; image[dst:dst+count] = packed[src:src+count]
        runs += 1
        if op & 1:
            break
    # Unchanged leading bytes are allowed only when both cursors agree.
    _require(src == dst, 'unexplained EXEPACK leading bytes')
    marker = b'Packed file is corrupt'
    q = data.find(marker, at+ip, end)
    _require(q >= 0 and data.find(marker,q+1,end) < 0, 'unknown/ambiguous relocation-table boundary')
    q += len(marker)
    rels = []
    for group in range(16):
        _require(q+2 <= end, 'truncated relocation group')
        n = struct.unpack_from('<H',data,q)[0]; q += 2
        _require(q+2*n <= end, 'truncated relocation entries')
        for _ in range(n):
            offset = struct.unpack_from('<H',data,q)[0]; q += 2
            _require(group*65536+offset+2 <= size, 'relocation exceeds decoded image')
            rels.append((offset,group*4096))
    _require(q == end and len(set(rels)) == len(rels), 'ambiguous relocation tail/duplicates')
    _require(real_cs*16+real_ip < size, 'decoded entry outside image')
    return bytes(image), dict(format='dos-exepack', source_sha256=hashlib.sha256(data).hexdigest(),
        header_offset=at, header_bytes=ip, wrapper=wrapper, image_bytes=size,
        image_sha256=hashlib.sha256(image).hexdigest(), runs=runs, leading_bytes=src,
        padding_bytes=padding, relocations=rels, cs=real_cs, ip=real_ip, ss=real_ss, sp=real_sp,
        source_mz=m, original_execution=False, runnable_verified=False,
        opaque_tail_bytes=len(data)-end)


def rebuild_mz(image: bytes, report: dict) -> bytes:
    """Reconstruct an unexecuted analysis envelope; preserve allocation capacity."""
    rels = report['relocations']
    header = ((28+4*len(rels)+15)//16)*16
    total = header+len(image)
    source = report['source_mz']
    old_paras = (source['module_bytes']+15)//16+source['minalloc']
    stack_paras = (report['ss']*16+report['sp']+15)//16
    minimum = max(0, old_paras-len(image)//16, stack_paras-len(image)//16)
    _require(minimum <= 65535 and len(rels) <= 65535, 'rebuilt MZ fields overflow')
    out = bytearray(header)
    struct.pack_into('<14H',out,0,0x5a4d,total%512,(total+511)//512,len(rels),header//16,
                     minimum,max(source['maxalloc'],minimum),report['ss'],report['sp'],0,
                     report['ip'],report['cs'],28,0)
    for i,(offset,segment) in enumerate(rels):
        struct.pack_into('<HH',out,28+4*i,offset,segment)
    result = bytes(out)+image
    mz_info(result)
    return result
