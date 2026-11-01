"""Bounded SCI1-late script/vocabulary extractor; no guest code execution.
Layout and LZW1 behavior checked against ScummVM resource/decompressor sources.
This reader does not handle view/picture rearrangement or other SCI profiles.
"""
from pathlib import Path
import struct, hashlib, json
ROOT=Path(__file__).resolve().parent
GAME=ROOT/'intake/space_quest/app/vga'
def lzw1(src:bytes, expected:int)->bytes:
    bitpos=0; output=bytearray(); entries={}; width=9; size=258; limit=511
    while len(output)<expected:
        if bitpos+width>len(src)*8: raise ValueError('truncated LZW code')
        value=0
        for i in range(width):
            at=bitpos+i; value=(value<<1)|((src[at//8]>>(7-at%8))&1)
        bitpos+=width
        if value>=size: raise ValueError(f'LZW code exceeds table {value}/{size}')
        if value==257: break
        if value==256:
            entries={};width=9;size=258;limit=511;continue
        begin=len(output)
        if value<256: output.append(value)
        else:
            off,n=entries[value]
            for i in range(n):
                if len(output)>=expected: raise ValueError('LZW output beyond declared size')
                output.append(output[off+i])
        if size<4096:
            if size==limit and width<12: width+=1;limit=(1<<width)-1
            entries[size]=(begin,len(output)-begin+1);size+=1
    if len(output)!=expected: raise ValueError(f'wrong decompressed size {len(output)} != {expected}')
    return bytes(output)
def main():
    table=(GAME/'RESOURCE.MAP').read_bytes();types=[]
    for o in range(0,len(table),3):
        t,pos=struct.unpack_from('<BH',table,o);types.append((t,pos))
        if t==255:break
    out=ROOT/'resources';out.mkdir(exist_ok=True)
    rec=[]
    for (t,a),(_,b) in zip(types,types[1:]):
        if t not in (0x82,0x86):continue
        if (b-a)%6:raise ValueError('directory remainder')
        for pos in range(a,b,6):
            num,packed=struct.unpack_from('<HI',table,pos);vol=packed>>28;off=packed&0xfffffff
            path=GAME/f'RESOURCE.{vol:03}';v=path.read_bytes()
            ht,hn,clen,ulen,method=struct.unpack_from('<BHHHH',v,off)
            if (ht,hn)!=(t,num):raise ValueError('resource header does not match map')
            compressed=v[off+9:off+9+clen-4]
            if len(compressed)!=clen-4:raise ValueError('truncated resource')
            if method==0: raw=compressed
            elif method==2:raw=lzw1(compressed,ulen)
            else:raise ValueError(f'unsupported compression {method}')
            if len(raw)!=ulen:raise ValueError('length')
            name=f'{"script" if t==0x82 else "vocab"}.{num:03}'
            (out/name).write_bytes(raw)
            rec.append(dict(name=name,volume=vol,offset=off,packed_size=clen-4,size=ulen,method=method,sha256=hashlib.sha256(raw).hexdigest(),packed_sha256=hashlib.sha256(compressed).hexdigest()))
    (ROOT/'resource_manifest.json').write_text(json.dumps(rec,indent=2))
    print('extracted',len(rec),'resources',sum(x['size'] for x in rec),'bytes')
    for n in (28,43,45,58,704):
        r=next(x for x in rec if x['name']==f'script.{n:03}');print(r)
    v=(out/'vocab.997').read_bytes();n=struct.unpack_from('<H',v,0)[0]+1;names=[]
    for i in range(n):
        off=struct.unpack_from('<H',v,2+2*i)[0];ln=struct.unpack_from('<H',v,off)[0];s=v[off+2:off+2+ln].decode('ascii');names.append(s)
    (ROOT/'selectors.json').write_text(json.dumps(names,indent=2))
    for key in ['cel','timesShownID','detailLevel','register','script','cycleSpeed','moveSpeed']:
        print(key,[(i,s) for i,s in enumerate(names) if s==key])
if __name__=='__main__':main()
