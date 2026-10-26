"""Conservative 16-bit OMF library identities from public symbols and code.

Modules with fixups, iterated data, unsupported records or incomplete bodies
are excluded. This is deliberately not a linker or a FLIRT file reader.
"""
from __future__ import annotations

import hashlib
from collections import Counter

import iced_x86 as ix


class _Cursor:
    def __init__(self,data):self.data=data;self.pos=0
    def take(self,count):
        if self.pos+count>len(self.data):raise ValueError('Truncated OMF field')
        value=self.data[self.pos:self.pos+count];self.pos+=count;return value
    def byte(self):return self.take(1)[0]
    def word(self):return int.from_bytes(self.take(2),'little')
    def index(self):
        value=self.byte()
        return ((value&0x7f)<<8)|self.byte() if value&0x80 else value
    def name(self):return self.take(self.byte()).decode('ascii')


def _closed_body(data,start,end):
    pending=[start];instructions={};occupied=set();returned=False
    while pending:
        address=pending.pop()
        if address in instructions:continue
        if len(instructions)>=4096 or not start<=address<end:return None
        instruction=ix.Decoder(16,data[address:end],ip=address).decode()
        size=instruction.len
        if instruction.is_invalid or address+size>end or occupied&set(range(address,address+size)):return None
        instructions[address]=size;occupied.update(range(address,address+size))
        flow=instruction.flow_control
        if flow==ix.FlowControl.RETURN:
            if instruction.mnemonic not in (ix.Mnemonic.RET,ix.Mnemonic.RETF):return None
            returned=True
        elif flow==ix.FlowControl.UNCONDITIONAL_BRANCH:
            pending.append(instruction.near_branch_target)
        elif flow==ix.FlowControl.CONDITIONAL_BRANCH:
            pending.extend([instruction.near_branch_target,address+size])
        elif flow==ix.FlowControl.NEXT:pending.append(address+size)
        else:return None
    last=max(a+n for a,n in instructions.items())
    if not returned or occupied!=set(range(start,last)) or last-start<6:return None
    return data[start:last]


def omf_signatures(data, *, source, abi='x86_16_cdecl_near'):
    """Return an auditable candidate catalog; excluded modules stay explicit."""
    from .frames import ABI_PROFILES
    if not isinstance(data,bytes) or not 16<=len(data)<=16*1024*1024:
        raise ValueError('OMF library must contain 16 bytes..16 MiB')
    if not isinstance(source,str) or not source.strip():raise ValueError('OMF source provenance is required')
    if abi not in ABI_PROFILES or ABI_PROFILES[abi]['bits']!=16:raise ValueError('OMF requires a DOS16 ABI')
    if data[0]!=0xf0:raise ValueError('Expected an OMF library header')
    page=int.from_bytes(data[1:3],'little')+3
    if not 16<=page<=32768 or page&(page-1):raise ValueError('Invalid OMF library page size')
    digest=hashlib.sha256(data).hexdigest();pos=page;module=None;signatures=[];excluded=Counter();modules=0;ended=False;bad_checksum=False

    def finish(records):
        nonlocal modules
        modules+=1
        names=[''];segments=[None];publics=[];ledatas=[];storage=0
        module_name=''
        for kind,payload in records:
            cursor=_Cursor(payload)
            if kind==0x80:module_name=cursor.name()
            elif kind==0x96:
                while cursor.pos<len(payload):names.append(cursor.name())
            elif kind==0x98:
                attributes=cursor.byte()
                if attributes>>5==0 or attributes&3:raise ValueError('unsupported segment addressing')
                size=cursor.word();name=cursor.index();cls=cursor.index();cursor.index()
                storage+=size
                if storage>1024*1024 or len(segments)>256:raise ValueError('module segment budget exceeded')
                if max(name,cls)>=len(names):raise ValueError('bad segment name index')
                segments.append(dict(size=size,code=names[cls].upper()=='CODE',data=bytearray(size),covered=set()))
            elif kind==0x90:
                cursor.index();segment=cursor.index()
                if segment==0:raise ValueError('absolute public symbol')
                while cursor.pos<len(payload):
                    name=cursor.name();offset=cursor.word();cursor.index()
                    publics.append((segment,offset,name))
            elif kind==0xa0:
                segment=cursor.index();offset=cursor.word();ledatas.append((segment,offset,cursor.take(len(payload)-cursor.pos)))
            elif kind in (0x9c,0x9d):raise ValueError('module requires linker fixups')
            elif kind not in (0x88,0x8a,0x8c,0x94,0x9a,0xb0,0xb4,0xb6,0xc6,0xc8):
                raise ValueError('unsupported record '+hex(kind))
        for segment,offset,chunk in ledatas:
            if not 0<segment<len(segments):raise ValueError('bad LEDATA segment')
            entry=segments[segment]
            if offset+len(chunk)>entry['size']:raise ValueError('LEDATA exceeds segment')
            addresses=set(range(offset,offset+len(chunk)))
            if addresses&entry['covered']:raise ValueError('overlapping LEDATA')
            entry['data'][offset:offset+len(chunk)]=chunk;entry['covered']|=addresses
        found=[]
        for segment,offset,name in publics:
            if not 0<segment<len(segments):raise ValueError('bad public segment')
            entry=segments[segment]
            if not entry['code']:continue
            end=min([o for s,o,n in publics if s==segment and o>offset]+[entry['size']])
            body=_closed_body(bytes(entry['data']),offset,end)
            if body is None or not set(range(offset,offset+len(body)))<=entry['covered']:continue
            canonical=name[1:] if name.startswith('_') else name
            if not canonical or not canonical.replace('_','').isalnum():continue
            found.append(dict(id=f'omf.{digest[:16]}.{segment}.{offset}.{canonical}',name=canonical,
                arch='x86',bits=16,bytes=body.hex(),abi=abi,identity_only=True,
                source=source,confidence='public OMF symbol; closed contiguous fixup-free body',
                provenance=dict(library_sha256=digest,module=module_name,segment=segment,offset=offset,
                                public_symbol=name,method='OMF public metadata plus bounded native control-flow traversal')))
        signatures.extend(found)
        if not found:excluded['no eligible closed code body']+=1

    while pos+3<=len(data):
        kind=data[pos];length=int.from_bytes(data[pos+1:pos+3],'little');end=pos+3+length
        if not length or end>len(data):raise ValueError('Truncated OMF record')
        if kind==0xf1:
            if module is not None:raise ValueError('Unfinished OMF module')
            ended=True;break
        checksum_ok=sum(data[pos:end])%256==0
        if kind==0x80:
            if module is not None:raise ValueError('Nested OMF module')
            module=[]
            bad_checksum=False
        if module is None:raise ValueError('OMF record outside module')
        # A zero checksum byte explicitly omits validation in some old tools.
        if not checksum_ok and data[end-1]!=0:bad_checksum=True
        module.append((kind,data[pos+3:end-1]))
        pos=end
        if kind in (0x8a,0x8b):
            if bad_checksum:
                modules+=1;excluded['module checksum mismatch']+=1
            else:
                try:finish(module)
                except (ValueError,UnicodeError) as error:excluded[str(error)]+=1
            module=None;pos=(pos+page-1)//page*page
    if not ended:raise ValueError('Missing OMF library end record')
    return dict(format='fdisbull-signatures-1',source=source,source_sha256=digest,signatures=signatures,
                extraction=dict(modules=modules,accepted_signatures=len(signatures),excluded=dict(excluded),
                                scope='Fixup-free contiguous returning routines; no external calls, indirect transfers or compiler attribution inference'))
