"""Read-only DOS AGI v2.917 view geometry and bound message captures.

This reads resource structure, not pixels on a live screen or engine state.
"""
from hashlib import sha256
from pathlib import Path

from .agi_source import validate_resource


def view_metadata(payload):
    if type(payload) is not bytes or not 5 <= len(payload) <= 65535:
        raise ValueError('invalid bounded v2 VIEW payload')
    def word(pos):
        if not 0 <= pos <= len(payload)-2:raise ValueError('truncated VIEW offset')
        return int.from_bytes(payload[pos:pos+2],'little')
    count=payload[2];description=word(3)
    if not count or 5+2*count>len(payload):raise ValueError('invalid VIEW loop directory')
    if description and (description>=len(payload) or b'\x00' not in payload[description:]):
        raise ValueError('invalid VIEW description')
    loops=[];total=0
    for index in range(count):
        start=word(5+index*2)
        if not 5+2*count <= start < len(payload):raise ValueError('invalid VIEW loop offset')
        cels=payload[start];total+=cels
        if not cels or total>1024 or start+1+2*cels>len(payload):
            raise ValueError('invalid VIEW cel directory or cel budget')
        result=[]
        for number in range(cels):
            cel=start+word(start+1+2*number)
            if cel<start+1+2*cels or cel+3>len(payload):raise ValueError('invalid VIEW cel offset')
            width,height=payload[cel:cel+2]
            if not 1<=width<=160 or not 1<=height<=168:raise ValueError('invalid VIEW dimensions')
            cursor=cel+3
            for _ in range(height):
                drawn=0
                while True:
                    if cursor>=len(payload):raise ValueError('truncated VIEW cel rows')
                    run=payload[cursor];cursor+=1
                    if run==0:break
                    length=run&15
                    if not length or drawn+length>width:raise ValueError('invalid VIEW run length')
                    drawn+=length
            result.append({'width':width,'height':height})
        loops.append(result)
    return {'sha256':sha256(payload).hexdigest(),'loops':loops}


def bind_native_view(source, runtime):
    """Bind unchanged bytes or a narrowly source-derived aliased mirror cache.

    AGI 2.917 mirrors some shared cels in place, changing their encoded rows
    and original-loop selector. Source bytes remain authoritative. This checks
    geometry and every effective loop/cel image, not the identity of a writer.
    All other bytes must match; this is not a general pixel-equivalence test.
    """
    view_metadata(source)
    if type(runtime) is not bytes or len(runtime)!=len(source):
        raise ValueError('native VIEW length differs')
    evidence={'source_sha256':sha256(source).hexdigest(),
              'runtime_sha256':sha256(runtime).hexdigest(),
              'byte_identical':source==runtime,'relation':'byte-identical','changed_cels':[]}
    if source==runtime:return evidence
    view_metadata(runtime)
    count=source[2];directory=5+2*count
    if source[:directory]!=runtime[:directory]:raise ValueError('native VIEW directory differs')
    word=lambda p:int.from_bytes(source[p:p+2],'little')
    aliases={};protected=[(0,directory)];boundaries={len(source)}
    description=word(3)
    if description:
        boundaries.add(description)
        protected.append((description,source.index(b'\0',description)+1))
    for loop in range(count):
        start=word(5+2*loop);end=start+1+2*source[start]
        if source[start:end]!=runtime[start:end]:raise ValueError('native VIEW cel directory differs')
        protected.append((start,end));boundaries.add(start)
        for cel in range(source[start]):
            address=start+word(start+1+2*cel)
            aliases.setdefault(address,set()).add(loop);boundaries.add(address)
    work=0
    allowed=bytearray(len(source))
    def decode(payload,start,limit):
        nonlocal work
        width,height,flags=payload[start:start+3];cursor=start+3;rows=[]
        work+=width*height
        if work>2*1024*1024:raise ValueError('native VIEW pixel budget exhausted')
        for _ in range(height):
            row=[]
            while True:
                if cursor>=limit:raise ValueError('native VIEW cel overlaps another structure')
                run=payload[cursor];cursor+=1
                if not run:break
                length=run&15
                if not length or len(row)+length>width:raise ValueError('invalid native VIEW run')
                row.extend([run>>4]*length)
            row.extend([flags&15]*(width-len(row)));rows.append(tuple(row))
        return tuple(rows),cursor
    ordered=sorted(boundaries)
    for start,loops in sorted(aliases.items()):
        limit=next(p for p in ordered if p>start)
        if start+3>limit:raise ValueError('native VIEW header overlaps another structure')
        if source[start:start+2]!=runtime[start:start+2]:raise ValueError('native VIEW dimensions differ')
        a,b=source[start+2],runtime[start+2]
        old,_=decode(source,start,limit);new,_=decode(runtime,start,limit)
        if source[start:limit]==runtime[start:limit]:continue
        old_loop,new_loop=(a>>4)&7,(b>>4)&7
        if not a&0x80 or a&0x8f!=b&0x8f or len(loops)<2 or old_loop not in loops or new_loop not in loops:
            raise ValueError('native VIEW is not an aliased mirror cache')
        expected=old if old_loop==new_loop else tuple(row[::-1] for row in old)
        if new!=expected:raise ValueError('native VIEW pixels differ')
        for loop in loops:
            work+=len(old)*len(old[0])
            if work>2*1024*1024:raise ValueError('native VIEW pixel budget exhausted')
            left=tuple(row[::-1] for row in old) if old_loop!=loop else old
            right=tuple(row[::-1] for row in new) if new_loop!=loop else new
            if left!=right:raise ValueError('native VIEW effective image differs')
        for p,q in protected:
            if start<q and p<limit:raise ValueError('native VIEW overlaps protected structure')
        # Re-encoding can grow into reserved cel space or leave unused tails.
        # These bytes are retained as a distinct runtime version, never called
        # identical to source. The next structural pointer bounds the allowance.
        allowed[start+2:limit]=b'\x01'*(limit-start-2)
        evidence['changed_cels'].append({'offset':start,'from_loop':old_loop,'to_loop':new_loop,'aliases':sorted(loops)})
    if not evidence['changed_cels'] or any(a!=b and not allowed[i] for i,(a,b) in enumerate(zip(source,runtime))):
        raise ValueError('native VIEW has changes outside mirrored cels')
    evidence['relation']='aliased-mirror-cache'
    return evidence


def capture_view(viewdir, volume_dir, view, *, profile):
    if profile!='2.917' or type(view) is not int or not 0<=view<=255:
        raise ValueError('explicit v2.917 profile and byte view ID required')
    with Path(viewdir).open('rb') as stream:directory=stream.read(769)
    if len(directory)>768 or len(directory)%3 or view*3+3>len(directory):
        raise ValueError('invalid VIEWDIR or absent entry')
    entry=int.from_bytes(directory[view*3:view*3+3],'big');volume=entry>>20;offset=entry&0xfffff
    if offset==0xfffff:raise ValueError('view resource absent')
    matches=[p for p in Path(volume_dir).iterdir() if p.is_file() and p.name.lower()==f'vol.{volume}']
    if len(matches)!=1:raise ValueError('expected exactly one VIEW volume')
    with matches[0].open('rb') as stream:data=stream.read(2*1024*1024+1)
    if len(data)>2*1024*1024 or offset+5>len(data) or data[offset:offset+3]!=b'\x12\x34'+bytes([volume]):
        raise ValueError('invalid or oversized VIEW volume')
    size=int.from_bytes(data[offset+3:offset+5],'little');end=offset+5+size
    if end>len(data):raise ValueError('truncated VIEW resource')
    metadata=view_metadata(data[offset+5:end])
    return {'view':view,'profile':profile,'metadata':metadata,
            'directory_sha256':sha256(directory).hexdigest(),
            'volume_sha256':sha256(data).hexdigest(),'resource_offset':offset,'resource_length':size}


def logic_messages(resource):
    validate_resource(resource)
    data=resource.payload;start=2+len(resource.code)
    if start+3>len(data):raise ValueError('truncated logic message section')
    count=data[start];size=int.from_bytes(data[start+1:start+3],'little')
    if count==0:return {resource.resource_sha256:{}}
    strings=start+3+2*count;end=start+1+size
    if size<2+2*count or end>len(data):raise ValueError('invalid logic message section')
    key=b'Avis Durgan';decoded=bytes(value^key[i%len(key)] for i,value in enumerate(data[strings:end]))
    result={}
    for i in range(count):
        offset=int.from_bytes(data[start+3+2*i:start+5+2*i],'little')
        if offset==0:result[str(i+1)]='';continue
        relative=start+1+offset-strings
        if not 0<=relative<len(decoded):raise ValueError('invalid logic message offset')
        terminator=decoded.find(b'\x00',relative)
        if terminator<0:raise ValueError('unterminated logic message')
        result[str(i+1)]=decoded[relative:terminator].decode('cp437')
    return {resource.resource_sha256:result}
