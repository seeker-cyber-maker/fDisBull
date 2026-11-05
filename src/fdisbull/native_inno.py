"""Bounded native Inno Setup 5.5.7/5.6.2 Unicode/GOG Galaxy reader.

Experimental fDisBull P00 format adapter. No installer execution, subprocesses, or
external innoextract dependency. This is a new implementation based on the
publicly documented format and independent fixture measurements. The zlib-
licensed innoextract project by Daniel Scharrer was consulted as a format
reference: https://github.com/dscharrer/innoextract (not bundled or copied).

Claim ceiling: Inno 5.5.7/5.6.2 Unicode, these GOG packaging conventions only. All
other variants MUST refuse instead of guessing their layout.
"""
from __future__ import annotations

import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import struct
import time
import zlib
from dataclasses import dataclass
from typing import BinaryIO, Iterator

MAGIC = b"rDlPtS"  # Inno loader table signature (12 bytes)
BLOCK_MAGIC = b"zlb\x1a"
# Preserve the historical default for callers constructing authored fixtures.
SUPPORTED = "Inno Setup Setup Data (5.6.2) (u)"
PROFILE_557 = "Inno Setup Setup Data (5.5.7) (u)"
SUPPORTED_PROFILES = (PROFILE_557, SUPPORTED)
MAX_SOURCE_BYTES = 3_000_000_000
MAX_HEADER_SIZE = 25_000_000
MAX_MEM_FILE = 80_000_000
MAX_ENTRIES = 50_000
MAX_STRING = 2_000_000
MAX_OUTPUT_FILE = 2_000_000_000

class InnoRefused(ValueError):
    """Unsupported version/shape, corrupt input, integrity failure or unsafe output."""


def check(cond: bool, message: str) -> None:
    if not cond:
        raise InnoRefused(message)


def read_at(f: BinaryIO, off: int, n: int, size: int) -> bytes:
    check(off >= 0 and n >= 0 and n <= size - off, f"out-of-range read @{off:#x} + {n}")
    f.seek(off)
    buf = f.read(n)
    check(len(buf) == n, f"short read @{off:#x}")
    return buf


class Cursor:
    def __init__(self, raw: bytes):
        self.raw = memoryview(raw)
        self.at = 0
    def take(self, n: int) -> bytes:
        check(0 <= n <= len(self.raw)-self.at, f"truncated header @{self.at}")
        b = bytes(self.raw[self.at:self.at+n]); self.at += n
        return b
    def u8(self) -> int: return self.take(1)[0]
    def u16(self) -> int: return struct.unpack("<H", self.take(2))[0]
    def u32(self) -> int: return struct.unpack("<I", self.take(4))[0]
    def u64(self) -> int: return struct.unpack("<Q", self.take(8))[0]
    def string(self, decode: bool = True) -> str | bytes:
        n = self.u32()
        check(n <= MAX_STRING, f"string too long: {n}")
        s = self.take(n)
        if not decode: return s
        check(n % 2 == 0, "odd UTF-16LE string length")
        try: return s.decode("utf-16le", "strict")
        except UnicodeError as e: raise InnoRefused("bad UTF-16LE string") from e
    def at_end(self) -> bool: return self.at == len(self.raw)

HEAD_STRINGS = """app_name app_versioned_name app_id app_copyright app_publisher app_publisher_url app_support_phone app_support_url app_updates_url app_version default_dir_name default_group_name base_filename uninstall_files_dir uninstall_name uninstall_icon app_mutex default_user_name default_user_organisation default_serial app_readme_file app_contact app_comments app_modify_path create_uninstall_registry_key uninstallable close_applications_filter setup_mutex changes_environment changes_associations license_text info_before info_after compiled_code""".split()
COUNTS = "language message permission type component task directory file data icon ini registry delete uninstall_delete run uninstall_run".split()


def get_loader(f: BinaryIO, size: int):
    check(100_000 <= size <= MAX_SOURCE_BYTES, "unreasonable installer size")
    f.seek(0)
    sample = f.read(min(size, 4_000_000))
    pos = 0
    while True:
        pos = sample.find(MAGIC, pos)
        check(pos >= 0, "Inno loader offset table missing")
        if pos + 44 <= len(sample):
            vals = struct.unpack_from("<8I", sample, pos + 12)
            rev, special, exe, exe_size, exe_check, header, data, checksum = vals
            if (rev == 1 and zlib.crc32(sample[pos:pos+40]) == checksum
                and 0 < data < header < exe <= size):
                return dict(table_offset=pos, revision=rev, header_offset=header,
                            data_offset=data, exe_offset=exe)
        pos += 1


def read_block(f: BinaryIO, off: int, size: int) -> tuple[bytes,int]:
    hdr = read_at(f, off, 9, size)
    crc, stored_size, compressed = struct.unpack("<IIB", hdr)
    check(crc == zlib.crc32(hdr[4:]), "invalid block header CRC32")
    check(0 < stored_size <= MAX_HEADER_SIZE and compressed in (0,1), "invalid block framing")
    b=bytearray(); rem=stored_size; at=off+9
    while rem:
        check(rem >= 5, "truncated inner chunk")
        word = read_at(f, at, 4, size); at += 4
        take=min(4096,rem-4)
        frag = read_at(f,at,take,size);at += take
        check(zlib.crc32(frag) == struct.unpack('<I',word)[0], 'damaged inner block chunk')
        b.extend(frag); rem-=take+4
    if not compressed: return bytes(b),at
    check(len(b)>5,'short LZMA1 header')
    try:
        setting=lzma._decode_filter_properties(lzma.FILTER_LZMA1, bytes(b[:5]))
        dec=lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[setting])
        out=dec.decompress(bytes(b[5:]),max_length=MAX_HEADER_SIZE)
    except lzma.LZMAError as e:raise InnoRefused('invalid LZMA1 header') from e
    check(dec.eof and len(out)<=MAX_HEADER_SIZE, 'header exceeds memory limit or incomplete')
    return out,at


def parse_header0(raw: bytes, *, profile: str = SUPPORTED):
    check(profile in SUPPORTED_PROFILES, f"unsupported data profile: {profile}")
    # These two strings were added in 5.6.1. Treating 5.5.7 as 5.6.2 shifts
    # every following count/table; selecting a profile must change the parser.
    names = [name for name in HEAD_STRINGS if profile != PROFILE_557 or name not in
             {"changes_environment", "changes_associations"}]
    c=Cursor(raw)
    strs={name:c.string(decode=name not in {'compiled_code','license_text','info_before','info_after'}) for name in names}
    counts={name:c.u32() for name in COUNTS}
    check(all(0 <= x <= MAX_ENTRIES for x in counts.values()),'count exceeds bound')
    c.take(20)  # OS version range
    c.take(8)   # wizard colours
    c.take(1)   # alpha enum
    c.take(20+8) # hashed password, salt
    c.take(8+4) # additional space, disk slices
    ui = c.take(10)  # installed/allowed architecture and UI flags
    # The sixth byte is the compression method, not a per-file flag.
    # Only stored/LZMA2 payloads are implemented by this adapter.
    check(ui[5] in (0, 4), f"unsupported payload compression method: {ui[5]}")
    strs['compression_method'] = ui[5]
    c.take(8)   # uninstall display size
    c.take(6)   # packed header capability bits
    for _ in range(counts['language']):
        for _ in range(10):c.string(False)
        c.take(4+4*4+1) # language id, font sizes and RTL
    for _ in range(counts['message']):
        c.string();c.string(False);c.take(4)
    for _ in range(counts['permission']):c.string(False)
    for _ in range(counts['type']):
        for _ in range(4):c.string()
        c.take(20+1+1+8)
    for _ in range(counts['component']):
        for _ in range(5):c.string()
        c.take(8+4+1+20+1+8)
    for _ in range(counts['task']):
        for _ in range(6):c.string()
        c.take(4+1+20+1)
    for _ in range(counts['directory']):
        for _ in range(7):c.string()
        c.take(4+20+2+1)
    files=[]
    for i in range(counts['file']):
        record=[c.string() for _ in range(10)]
        c.take(20)
        location=c.u32();attr=c.u32();external_size=c.u64();permission=c.u16()
        flags=int.from_bytes(c.take(4),'little'); typ=c.u8()
        files.append({'source':record[0],'destination':record[1],
                      'components':record[4],'tasks':record[5],'languages':record[6],
                      'check':record[7],'after':record[8],'before':record[9],
                      'location':location,'attr':attr,'external_size':external_size,
                      'flags':flags,'type':typ})
    # This exact source profile assumes the remaining primary stream contains
    # icon/registry/INI etc., not necessary for file payload recovery. Stop
    # parsing at file table and preserve remaining opaque bytes as residual.
    return strs,counts,files,len(raw)-c.at


def parse_header1(raw:bytes,n:int):
    check(n*74 == len(raw), 'unexpected data table size')
    c=Cursor(raw);out=[]
    for i in range(n):
        first=c.u32();last=c.u32();chunkoff=c.u32();fileoff=c.u64()
        sz=c.u64();chunk_size=c.u64();sha1=c.take(20).hex()
        filetime=c.u64();verhi=c.u32();verlo=c.u32();flags=c.u16()
        check(first==0 and last==0,'multiple external installer slices not supported')
        check(fileoff==0,'nonzero file offset in solid Inno chunks unsupported')
        check(sz <= MAX_OUTPUT_FILE,'individual item too large')
        out.append({'index':i,'chunk_relative_offset':chunkoff,'size':sz,
                    'chunk_size':chunk_size,'sha1':sha1,'flags':flags,
                    'first_slice':first,'last_slice':last})
    check(c.at_end(),'data metadata trailing bytes')
    return out


def parse_call(expr:str, name:str) -> list[str] | None:
    """Parse a strict GOG Pascal function call, never evaluate untrusted code."""
    names=(name,name+'_dependency')
    for fn in names:
        mt=re.fullmatch(r'\s*'+re.escape(fn)+r'\s*\((.*)\)\s*;?\s*',expr,re.S)
        if not mt:continue
        text=mt.group(1); result=[];p=0
        while p<len(text):
            while p<len(text) and text[p].isspace():p+=1
            if p>=len(text):break
            if text[p]=="'":
                p+=1;buf=[]
                while True:
                    check(p<len(text),'unterminated Pascal string')
                    ch=text[p];p+=1
                    if ch=="'":
                        if p<len(text) and text[p]=="'":p+=1;buf.append("'")
                        else:break
                    else:buf.append(ch)
                token=''.join(buf)
            else:
                start=p
                while p<len(text) and text[p] not in ', ':p+=1
                token=text[start:p]
                check(bool(re.fullmatch(r'\d+',token)),'unsupported Pascal argument')
            result.append(token)
            while p<len(text) and text[p].isspace():p+=1
            if p==len(text):break
            check(text[p]==',','bad Pascal separator')
            p+=1
        return result
    return None


def undo_call_filter_5309(raw:bytes)->bytes:
    """Reverse the Inno >=5.3.9 x86 CALL/JMP address normalization.

    Each 64 KiB block is processed independently and a candidate 5-byte
    instruction crossing a block boundary stays untouched. Widths are 24-bit
    modulo arithmetic, and bit 23 controls the high-byte sign folding.
    """
    out=bytearray(raw)
    i=0
    while i < len(out):
        opcode=out[i]
        if opcode in (0xE8,0xE9) and len(out)-i>=5 and 0x10000-(i&0xffff)>=5:
            if out[i+4] in (0,0xff):
                relative=(int.from_bytes(out[i+1:i+4],'little')-(i+5)) & 0xffffff
                out[i+1:i+4]=relative.to_bytes(3,'little')
                if relative&0x800000:out[i+4] ^= 0xff
            i+=5
        else:i+=1
    return bytes(out)


def safe_path(s:str)->str:
    s=s.replace('\\','/').strip()
    check(bool(s) and not s.startswith('/') and not re.match(r'^[A-Za-z]:',s), 'absolute path refused')
    check('\x00' not in s, 'NUL in path')
    parts=s.split('/')
    check(all(part not in ('','.','..') and not part.startswith('{') for part in parts),f'unsafe/unexpanded path {s!r}')
    check(all(':' not in part for part in parts),'reserved path component')
    return '/'.join(parts)


def build_inventory(files:list[dict], data:list[dict]):
    target=[];pending=None
    for row in files:
        name=row['destination']; location=row['location']
        if not name:continue
        if row['type'] != 0:continue
        check(0 <= location < len(data),'file location outside data table')
        before=parse_call(row['before'],'before_install')
        after=parse_call(row['after'],'after_install')
        if before:
            check(pending is None,'GOG multipart start while previous incomplete')
            check(len(before)>=3 and re.fullmatch('[0-9a-fA-F]{32}',before[0]),'GOG MD5 missing')
            count=int(before[2]);check(1<=count<=10000,'invalid multipart count')
            canonical=safe_path(before[1])
            pending={'path':canonical,'md5':before[0].lower(), 'locations':[],
                     'parts':[], 'remaining':count,'kind':'galaxy'}
            target.append(pending)
        if after:
            check(pending is not None,'orphan GOG payload part')
            check(len(after)>=3 and after[1].isdigit() and after[2].isdigit(),'bad GOG after size')
            check(int(after[1])==data[location]['size'],'part compressed size metadata mismatch')
            pending['locations'].append(location)
            pending['parts'].append({'uncompressed_size':int(after[2]),'compressed_size':int(after[1])})
            pending['remaining']-=1
            check(pending['remaining']>=0,'too many GOG parts')
            if pending['remaining']==0:
                pending['size']=sum(x['uncompressed_size'] for x in pending['parts']);pending.pop('remaining')
                check(pending['size']<=MAX_OUTPUT_FILE,'output file exceeds limit')
                pending=None
            continue
        check(pending is None,'interrupted GOG multipart sequence')
        if before:raise InnoRefused('GOG start without GOG after')
        prefix_match=re.match(r'^\{(app|tmp|commonappdata)\}[\\/](.+)$',name,flags=re.I)
        if prefix_match:
            clean=safe_path(prefix_match.group(1).lower()+'/'+prefix_match.group(2))
            target.append({'path':clean,'locations':[location],'kind':'direct','size':data[location]['size']})
    check(pending is None,'unfinished GOG multipart')
    unique=set()
    for r in target:
        key=r['path'].casefold()
        check(key not in unique,f'casefold-colliding output path: {r["path"]}')
        unique.add(key)
    return target


@dataclass
class NativeInno:
    path:Path
    size:int
    source_sha256:str
    offsets:dict
    header:dict
    counts:dict
    files:list[dict]
    locations:list[dict]
    inventory:list[dict]
    header_residual_size:int
    profile:str=SUPPORTED

    @classmethod
    def open(cls,path:Path|str, *,deadline:float|None=None):
        if deadline is not None:check(time.monotonic()<=deadline,'installer parsing deadline exceeded')
        path=Path(path)
        check(path.is_file() and not path.is_symlink(),'source is not an ordinary file')
        size=path.stat().st_size
        with path.open('rb') as f:
            offsets=get_loader(f,size)
            version=read_at(f,offsets['header_offset'],64,size).rstrip(b'\0').decode('ascii','strict')
            check(version in SUPPORTED_PROFILES,f'unsupported data profile: {version}; no external fallback')
            h0,nxt=read_block(f,offsets['header_offset']+64,size)
            h1,end=read_block(f,nxt,size)
            check(end==offsets['exe_offset'],'loader offsets do not delimit two header blocks')
            header,counts,files,residual=parse_header0(h0, profile=version)
            locations=parse_header1(h1,counts['data'])
            inventory=build_inventory(files,locations)
            f.seek(0)
            h=hashlib.sha256()
            for b in iter(lambda:f.read(1024*1024),b''):
                if deadline is not None:check(time.monotonic()<=deadline,'hashing deadline exceeded')
                h.update(b)
        return cls(path,size,h.hexdigest(),offsets,header,counts,files,locations,inventory,residual,version)

    def describe(self):
        return {'source_file':self.path.name, 'source_sha256':self.source_sha256,
                'format':self.profile,'data_offset':self.offsets['data_offset'],
                'header':{'file_count':self.counts['file'], 'data_count':self.counts['data'],
                          'main_header_opaque_tail_bytes':self.header_residual_size},
                'output_files':len(self.inventory),
                'total_output_bytes':sum(i['size'] for i in self.inventory),
                'files': [{'path':i['path'],'size':i['size'],'part_count':len(i['locations']),
                           'kind':i['kind']} for i in self.inventory]}

    def _read_location(self,f:BinaryIO,item:dict) -> bytes:
        loc=self.locations[item['index']]
        absolute=self.offsets['data_offset']+loc['chunk_relative_offset']
        check(read_at(f,absolute,4,self.size)==BLOCK_MAGIC,'invalid data chunk magic')
        off=absolute+4
        compressed=bool(loc['flags'] & 0x80)
        check(not (loc['flags'] & 0x40),'encrypted data not supported')
        check(loc['chunk_size'] <= MAX_OUTPUT_FILE and off+loc['chunk_size']<=self.size,'chunk outside source')
        payload=read_at(f,off,loc['chunk_size'],self.size)
        if compressed:
            check(self.header['compression_method'] == 4, 'compressed chunk requires LZMA2 header profile')
            check(len(payload)>1,'short compressed chunk')
            try:
                settings=lzma._decode_filter_properties(lzma.FILTER_LZMA2, payload[:1])
                dec=lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[settings])
                data=dec.decompress(payload[1:],max_length=min(MAX_OUTPUT_FILE,loc['size']+1))
            except lzma.LZMAError as e:raise InnoRefused('bad LZMA2 data') from e
            check(dec.eof, 'incomplete LZMA2 chunk')
        else: data=payload
        check(len(data)==loc['size'],'data size does not match header')
        if loc['flags'] & 0x10:
            data=undo_call_filter_5309(data)
        check(hashlib.sha1(data).hexdigest()==loc['sha1'],'data SHA1 mismatch')
        return data

    def extract_one(self,path:str)->bytes:
        matches=[i for i in self.inventory if i['path'].casefold()==path.casefold()]
        check(len(matches)==1,'target not found or ambiguous')
        item=matches[0]
        check(item['size']<=MAX_MEM_FILE,'file too large for in-memory single-target API')
        with self.path.open('rb') as f:
            pieces=[]
            for idx,location in enumerate(item['locations']):
                datum=self._read_location(f,{'index':location})
                if item['kind']=='galaxy':
                    try:
                        inflater=zlib.decompressobj()
                        part=inflater.decompress(datum,item['parts'][idx]['uncompressed_size']+1)
                        part+=inflater.flush()
                        check(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail,'incomplete zlib galaxy part')
                    except zlib.error as e: raise InnoRefused('invalid GOG zlib part') from e
                    check(len(part)==item['parts'][idx]['uncompressed_size'],'GOG uncompressed part size mismatch')
                    pieces.append(part)
                else:pieces.append(datum)
        full=b''.join(pieces)
        check(len(full)==item['size'],'final size mismatch')
        if item['kind']=='galaxy':
            check(hashlib.md5(full).hexdigest()==item['md5'],'GOG final MD5 mismatch')
        return full

    def extract_selected(self,output:Path|str,selected:list[str], *,emit_manifest:bool=True, deadline:float|None=None):
        # never overwrite user files, fail without side effects if destination exists
        out=Path(output)
        check(not out.exists() and not out.is_symlink(), 'destination must not exist')
        chosen=[]
        for pattern in selected:
            hits=[i for i in self.inventory if i['path'].casefold()==pattern.casefold()]
            check(len(hits)==1,f'not found or ambiguous: {pattern}')
            chosen.append(hits[0])
        check(len({i['path'].casefold() for i in chosen})==len(chosen),'repeated output name')
        start_stat=self.path.stat()
        out.mkdir(parents=True,exist_ok=False)
        written=[]
        try:
            for i in chosen:
                child=out.joinpath(*PurePosixPath(i['path']).parts)
                child.parent.mkdir(parents=True,exist_ok=True)
                digest=hashlib.sha256(); combined_md5=hashlib.md5(); total=0
                with child.open('xb') as dest, self.path.open('rb') as source:
                    for idx,location in enumerate(i['locations']):
                        if deadline is not None:check(time.monotonic()<=deadline,'extraction deadline exceeded')
                        payload=self._read_location(source,{'index':location})
                        if i['kind']=='galaxy':
                            try:
                                inflater=zlib.decompressobj()
                                expected=i['parts'][idx]['uncompressed_size']
                                payload=inflater.decompress(payload, expected+1)
                                payload+=inflater.flush()
                                check(inflater.eof and not inflater.unconsumed_tail and not inflater.unused_data,'invalid GOG part terminator')
                            except zlib.error as err: raise InnoRefused('damaged GOG zlib part') from err
                            check(len(payload)==expected,'GOG part length mismatch')
                        check(total+len(payload) <= MAX_OUTPUT_FILE,'final file exceeds allowed size')
                        dest.write(payload);digest.update(payload);combined_md5.update(payload);total+=len(payload)
                    if deadline is not None:check(time.monotonic()<=deadline,'extraction deadline exceeded')
                    check(total==i['size'],'reconstruction length mismatch')
                    if i['kind']=='galaxy':
                        check(combined_md5.hexdigest()==i['md5'],'final GOG MD5 mismatch')
                written.append({'path':i['path'],'bytes':total,'sha256':digest.hexdigest()})
            end_stat=self.path.stat()
            check((start_stat.st_size,start_stat.st_mtime_ns,start_stat.st_ino)==(end_stat.st_size,end_stat.st_mtime_ns,end_stat.st_ino), 'source changed during extraction')
            if emit_manifest:
                (out/'gog-native-manifest.json').write_text(json.dumps({'profile':self.profile,
                    'source_sha256':self.source_sha256,'files':written},indent=2)+'\n')
        except Exception:
            # do not erase uncertain outputs after failure: caller explicitly reviews partials
            raise
        return written