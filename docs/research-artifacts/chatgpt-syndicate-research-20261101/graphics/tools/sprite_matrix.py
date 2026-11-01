"""Byte-preserving sprite and animation caller experiments; outputs remain private."""
from pathlib import Path
import struct,json,zlib,hashlib
from probe_cpu64 import run,ROOT
OUT=ROOT/'evidence'/'sprite-contract-v1';OUT.mkdir(exist_ok=False)
B0=0x1001000;B1=0x1041000;N=128000;S=0x1080000;T=0x10f4000;E=0x1061000;F=0x10e0000
PAT=bytes(((i*37+(i//80)*13)^0x5A)&255 for i in range(N))
DATA=ROOT/'decoded/SYNDICAT/DATA'
real=(DATA/'HSPR-0.DAT').read_bytes();tab=(DATA/'HSPR-0.TAB').read_bytes();elems=(DATA/'HELE-0.ANI').read_bytes();frames=(DATA/'HFRA-0.ANI').read_bytes()
def pack(*v):return struct.pack('<'+'I'*len(v),*[x&0xffffffff for x in v])
def sprite_pixels(raw,w,h):
    pix=[]
    for y in range(h):
        row=[]
        for x in range(w):
            q=(y*((w+7)//8)+x//8)*5;bit=128>>(x&7)
            row.append((bool(raw[q]&bit),sum((1<<p) for p in range(4) if raw[q+1+p]&bit)))
        pix.append(row)
    return pix

def draw(dst,raw,w,h,x,y,variant,anchor=-1):
    if variant==3:return
    # Current experiment domain is entirely on-screen. Clipping is a separate
    # contract, not silently imported from the rectangle oracle.
    assert 0<=x and x+w<=640 and 0<y and y+h<=400 and h>0
    pix=sprite_pixels(raw,w,h)
    for sy in range(h):
        for sx in range(w):
            X=x+(w-1-sx if variant==1 else sx)
            Y=y+(h-1-sy+anchor if variant==2 else sy)
            keep,color=pix[sy][sx];at=Y*80+X//8;bit=128>>(X&7)
            for p in range(4):
                # Native operation is (destination & transparency) | color.
                # All valid sampled assets clear color bits under transparency.
                index=at+32000*p
                if not keep:dst[index]&=~bit&255
                if color&(1<<p):dst[index]|=bit

def authored(w,h):
    b=bytearray()
    for y in range(h):
        for group in range(w//8):
            vals=[0]*5
            for bit in range(8):
                x=group*8+bit;m=128>>bit;transparent=(x+y)%7==0
                if transparent:vals[0]|=m
                else:
                    col=(x*3+y*5+1)%16
                    for p in range(4):
                        if col&(1<<p):vals[p+1]|=m
            b.extend(vals)
    return bytes(b)

records=[]
basewrites={B0:b'\x00'*N,B1:PAT,0x55368:pack(B0),0x55374:pack(B1),0x80105:b'\2'}
def save(name,r,expected,extra):
    got=bytes.fromhex(r['observations'][hex(B1)]['after'])
    good=r['reason']=='returned' and got==bytes(expected) and r['owned_child_reaped']
    p=OUT/(name+'.json.zlib');p.write_bytes(zlib.compress(json.dumps(r).encode(),9))
    diff=[i for i,(a,b) in enumerate(zip(got,expected)) if a!=b]
    rec={'case':name,'reason':r['reason'],'steps':r['steps'],'oracle_match':good,'mismatching_bytes':len(diff),'sampled_dispatches':len(r['samples']),'receipt_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),**extra}
    if not good:rec['first_diffs']=[(i,got[i],expected[i]) for i in diff[:8]];print('FAIL',rec,flush=True)
    records.append(rec)

for w in (8,16,32,64):
    h=3;raw=authored(w,h)
    for variant in range(4):
        for align in (0,1,3,7):
            x=80+align;y=40
            exp=bytearray(PAT);draw(exp,raw,w,h,x,y,variant)
            ordinary=bytearray(PAT);draw(ordinary,raw,w,h,x,y,variant,anchor=0)
            writes={**basewrites,S:raw,T:struct.pack('<IBB',S,w,h),0x200ff04:pack(x,y,T,variant)}
            r=run(0x4cf23,writes=writes,observe=[(B1,N)],sample_at=[0x4d94f],max_steps=20000,seconds=15)
            save(f'authored-w{w}-v{variant}-a{align}',r,exp,{'input':'authored','width':w,'height':h,'variant':variant,'x_alignment':align,'conventional_anchor_matches':bytes.fromhex(r['observations'][hex(B1)]['after'])==ordinary})
    print('authored width done',w,flush=True)

# Actual resource sprite 800 is referenced by the two flag-2 element records.
o,w,h=struct.unpack_from('<IBB',tab,800*6);raw=real[o:o+((w+7)//8)*5*h]
for variant in range(4):
    for align in (0,1,3,7):
        x=80+align;y=40;exp=bytearray(PAT);draw(exp,raw,w,h,x,y,variant)
        writes={**basewrites,S:raw,T:struct.pack('<IBB',S,w,h),0x200ff04:pack(x,y,T,variant)}
        r=run(0x4cf23,writes=writes,observe=[(B1,N)],sample_at=[0x4d94f],max_steps=20000,seconds=15)
        save(f'actual-sprite800-v{variant}-a{align}',r,exp,{'input':'actual sprite 800, diagnostic position/variant','width':w,'height':h,'variant':variant,'x_alignment':align,'source_payload_sha256':hashlib.sha256(raw).hexdigest()})

# Compose complete actual frame + element + sprite tables using the unchanged
# original caller. Table pointers are explicitly supplied load-state bindings.
relocated=bytearray(tab)
for i in range(len(tab)//6):struct.pack_into('<I',relocated,i*6,S+struct.unpack_from('<I',tab,i*6)[0])
for frame in (1767,2306,2310):
    for align in (0,3):
        x=160+align;y=120;exp=bytearray(PAT);el=struct.unpack_from('<H',frames,frame*8)[0];seen=[]
        while el:
            assert el not in seen;seen.append(el)
            off,dx,dy,flags,el=struct.unpack_from('<HhhHH',elems,el*10)
            if off:
                ptr,w,h=struct.unpack_from('<IBB',tab,off);rdat=real[ptr:ptr+((w+7)//8)*5*h]
                if w and h:draw(exp,rdat,w,h,x+dx,y+dy,flags&3)
        # Back-buffer animation entry optionally plays a sound. These selected
        # records have a zero service byte, so no sound stub is supplied.
        assert frames[frame*8+4]==0
        writes={**basewrites,S:real,T:bytes(relocated),E:elems,F:frames,0x55314:pack(T),0x55338:pack(F),0x55340:pack(E),0x200ff04:pack(frame,x,y)}
        r=run(0x1e050,writes=writes,observe=[(B1,N)],sample_at=[0x4d94f],max_steps=90000,seconds=30)
        save(f'frame-{frame}-a{align}',r,exp,{'input':'original frame/element/sprite tables, diagnostic loaded bindings','frame':frame,'element_count':len(seen),'variant_counts':{str(v):sum((struct.unpack_from('<H',elems,i*10+6)[0]&3)==v for i in seen) for v in range(4)}})
        print('frame done',frame,align,r['reason'],r['steps'],flush=True)
(OUT/'summary.json').write_text(json.dumps(records,indent=2)+'\n')
print('TOTAL',len(records),'MATCH',sum(r['oracle_match'] for r in records),flush=True)
