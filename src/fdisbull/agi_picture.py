"""Bounded AGI 2.915/2.917 EGA picture-resource decoding.

The input is a prepared picture, not an overlay or a live interpreter state.
Reference semantics: https://peterkelly.github.io/agi-re/spec/picture_resources.html
Movement also depends on runtime state: https://github.com/scummvm/scummvm/blob/master/engines/agi/checks.cpp
"""
from collections import Counter, deque
import hashlib
from pathlib import Path

WIDTH, HEIGHT = 160, 168
MAX_PAYLOAD = 2 * 1024 * 1024
MAX_WORK = 20_000_000


def extract_v2_resource(directory, volume_root, number):
    """Extract one entry from an AGI v2 directory and VOL.N without copying files."""
    if type(number) is not int or not 0 <= number < 256: raise ValueError('Invalid resource number')
    directory=Path(directory); root=Path(volume_root)
    if directory.stat().st_size > 768: raise ValueError('Directory exceeds 768 bytes')
    data=directory.read_bytes()
    if len(data)%3 or number*3+3>len(data): raise ValueError('Missing or malformed directory entry')
    a,b,c=data[number*3:number*3+3]
    if (a,b,c)==(255,255,255): raise ValueError('Resource is absent')
    volume=a>>4; offset=((a&15)<<16)|(b<<8)|c
    candidates=[p for p in root.iterdir() if p.name.lower()==f'vol.{volume}'.lower()]
    if len(candidates)!=1 or not candidates[0].is_file(): raise ValueError('Missing or ambiguous volume')
    with candidates[0].open('rb') as f:
        f.seek(offset); header=f.read(5)
        if len(header)!=5 or header[:2]!=b'\x12\x34' or header[2]!=volume: raise ValueError('Invalid v2 resource header')
        size=int.from_bytes(header[3:5],'little')
        if size>MAX_PAYLOAD: raise ValueError('Resource too large')
        payload=f.read(size)
    if len(payload)!=size: raise ValueError('Truncated resource')
    return {'payload':payload,'volume':volume,'offset':offset,'length':size,'sha256':hashlib.sha256(payload).hexdigest()}


# Radius masks described by the behavioral specification, expressed as row words.
_SHAPES = (
 (0x8000,), (0xe000,)*3, (0x7000,0xf800,0xf800,0xf800,0x7000),
 (0x3800,0x7c00,0xfe00,0xfe00,0xfe00,0x7c00,0x3800),
 (0x1c00,0x7f00,0xff80,0xff80,0xff80,0xff80,0xff80,0x7f00,0x1c00),
 (0x0e00,0x3f80,0x7fc0,0x7fc0,0xffe0,0xffe0,0xffe0,0x7fc0,0x7fc0,0x3f80,0x1f00),
 (0x0f80,0x3fe0,0x7ff0,0x7ff0,0xfff8,0xfff8,0xfff8,0xfff8,0xfff8,0x7ff0,0x7ff0,0x3fe0,0x0f80),
 (0x07c0,0x1ff0,0x3ff8,0x7ffc,0x7ffc,0xfffe,0xfffe,0xfffe,0xfffe,0xfffe,0x7ffc,0x7ffc,0x3ff8,0x1ff0,0x07c0),
)


def decode_picture(payload):
    """Decode a complete v2.917 stream; reject malformed or excessive input."""
    if not isinstance(payload,bytes) or not 1<=len(payload)<=MAX_PAYLOAD: raise ValueError('Invalid picture payload size')
    visual=bytearray([15])*(WIDTH*HEIGHT); priority=bytearray([4])*(WIDTH*HEIGHT)
    vis=pri=False; vc=pc=pen=0; index=0; work=0; counts=Counter(); ended=False
    def spend(n=1):
        nonlocal work
        work+=n
        if work>MAX_WORK: raise ValueError('Picture work budget exceeded')
    def put(x,y):
        spend(); i=y*WIDTH+x
        if 0<=i<len(visual):
            if vis: visual[i]=vc
            if pri: priority[i]=pc
    def pair():
        nonlocal index
        if index>=len(payload) or payload[index]>=0xf0: return None
        x=payload[index]; index+=1
        if index>=len(payload) or payload[index]>=0xf0: raise ValueError('Incomplete coordinate pair')
        y=payload[index]; index+=1
        return min(x,159),min(y,167)
    def line(x,y,x2,y2):
        dx=abs(x2-x); dy=abs(y2-y); major=max(dx,dy)
        if not major: put(x,y); return
        sx=1 if x2>x else -1; sy=1 if y2>y else -1
        ex=0 if dx>=dy else dy//2; ey=dx//2 if dx>=dy else 0
        put(x,y)
        for _ in range(major):
            ey=(ey+dy)&255
            if ey>=major: ey=(ey-major)&255; y+=sy
            ex=(ex+dx)&255
            if ex>=major: ex=(ex-major)&255; x+=sx
            put(x,y)
    def fill(x,y):
        if not vis and not pri: return
        surface=visual if vis else priority; target=15 if vis else 4
        if (vc if vis else pc)==target or surface[y*WIDTH+x]!=target: return
        todo=deque([(x,y)]); seen=bytearray(WIDTH*HEIGHT); seen[y*WIDTH+x]=1
        while todo:
            a,b=todo.popleft(); put(a,b)
            for nx,ny in ((a-1,b),(a+1,b),(a,b-1),(a,b+1)):
                if 0<=nx<WIDTH and 0<=ny<HEIGHT:
                    i=ny*WIDTH+nx
                    if not seen[i] and surface[i]==target: seen[i]=1; todo.append((nx,ny))
    def brush(x,y,seed):
        radius=pen&7; left=max(0,min(2*x-radius,320-2*radius))//2
        top=max(0,min(y-radius,167-2*radius)); state=seed|1
        for dy,word in enumerate(_SHAPES[radius]):
            for dx in range(radius+1):
                if not pen&0x10 and not word & (0x8000>>(2*dx)): continue
                if pen&0x20:
                    state=(state>>1) ^ (0xb8 if state&1 else 0)
                    if state&3 != 2: continue
                put(left+dx,top+dy)
    while index<len(payload):
        op=payload[index]; index+=1; spend()
        if op<0xf0: continue
        counts[f'{op:02x}']+=1
        if op==0xff: ended=True; break
        if op in (0xf0,0xf2,0xf9):
            if index>=len(payload): raise ValueError('Truncated raw operand')
            value=payload[index]; index+=1
            if op==0xf0: vis=True; vc=value&15
            elif op==0xf2: pri=True; pc=value&15
            else: pen=value
        elif op==0xf1: vis=False
        elif op==0xf3: pri=False
        elif op in (0xf4,0xf5,0xf6,0xf7):
            start=pair()
            if start is None: continue
            x,y=start; put(x,y); axis=0
            while index<len(payload) and payload[index]<0xf0:
                if op==0xf6:
                    point=pair()
                    if point is None: break
                    nx,ny=point
                elif op==0xf7:
                    d=payload[index]; index+=1
                    nx=min(159,(x+(-1 if d&128 else 1)*((d>>4)&7))&255)
                    ny=min(167,(y+(-1 if d&8 else 1)*(d&7))&255)
                else:
                    z=payload[index]; index+=1
                    vertical=(axis%2==0) == (op==0xf4); axis+=1
                    nx,ny=(x,min(z,167)) if vertical else (min(z,159),y)
                line(x,y,nx,ny); x,y=nx,ny
        elif op==0xf8:
            while index<len(payload) and payload[index]<0xf0:
                p=pair(); fill(*p)
        elif op==0xfa:
            while index<len(payload) and payload[index]<0xf0:
                seed=0
                if pen&0x20:
                    seed=payload[index]; index+=1
                    if index>=len(payload) or payload[index]>=0xf0: raise ValueError('Incomplete brush coordinates')
                p=pair(); brush(*p,seed)
        else: raise ValueError(f'Unsupported picture opcode {op:02x}')
    if not ended: raise ValueError('Picture has no terminator')
    return {'width':WIDTH,'height':HEIGHT,'visual':bytes(visual),'priority':bytes(priority),'complete':True,'priority_complete':True,'unsupported':[],'opcode_counts':dict(sorted(counts.items())),'payload_sha256':hashlib.sha256(payload).hexdigest()}


def priority_row_runs(decoded, values):
    """Select priority values as half-open row runs for spatial_map geometry."""
    if not isinstance(decoded,dict) or decoded.get('priority_complete') is not True or decoded.get('width')!=WIDTH or decoded.get('height')!=HEIGHT: raise ValueError('Priority plane is not complete')
    plane=decoded.get('priority')
    if not isinstance(plane,bytes) or len(plane)!=WIDTH*HEIGHT or not isinstance(values,(set,tuple,list)) or not values or any(type(v) is not int or not 0<=v<=15 for v in values): raise ValueError('Invalid priority plane or selection')
    allowed=set(values); runs=[]
    for y in range(HEIGHT):
        x=0
        while x<WIDTH:
            if plane[y*WIDTH+x] not in allowed: x+=1; continue
            start=x
            while x<WIDTH and plane[y*WIDTH+x] in allowed: x+=1
            runs.append([y,start,x])
    return {'row_runs':runs}
