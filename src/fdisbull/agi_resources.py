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
