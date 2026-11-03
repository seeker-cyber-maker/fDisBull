"""Bounded CHIP-8 scalar+display execution oracle (not a full game emulator).

All side effects stay inside Machine. Timer advance is an explicit host input.
Emulates classic CHIP-8 instructions only; extensions are marked unsupported.
No host I/O, audio playback, platform-specific vblank or key-release model.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import random
from .decoder import decode_table

FONT = bytes.fromhex('F0909090F0 2060202070 F010F080F0 F010F010F0 9090F01010 F080F010F0 F080F090F0 F010204040 F090F090F0 F090F010F0 F090F09090 E090E090E0 F0808080F0 E0909090E0 F080F080F0 F080F08080')

class Trap(Exception):
    def __init__(self, code:str, address:int, word:int|None=None):
        self.code,self.address,self.word=code,address,word
        super().__init__(f'{code} at {address:#05x}'+(' instruction '+hex(word) if word is not None else ''))

@dataclass
class Quirks:
    shift_vx: bool = False
    inc_i_on_load_store: bool = True
    reset_vf_logic: bool = True
    clip_sprites: bool = True
    jump_vx: bool = False

@dataclass
class Machine:
    memory: bytearray = field(default_factory=lambda: bytearray(4096))
    v: list[int] = field(default_factory=lambda: [0]*16)
    i: int = 0
    pc: int = 0x200
    stack: list[int] = field(default_factory=list)
    delay: int = 0
    sound: int = 0
    frame: bytearray = field(default_factory=lambda:bytearray(64*32))
    keys: set[int] = field(default_factory=set)
    quirks: Quirks = field(default_factory=Quirks)
    seed: int = 0
    steps: int = 0
    last_family: str|None = None
    waiting: bool = False
    rng: random.Random = field(init=False, repr=False)

    def __post_init__(self):
        self.rng = random.Random(self.seed)
        self.memory[0x50:0x50+len(FONT)] = FONT

    def load_rom(self, raw:bytes):
        if len(raw) > 4096-0x200:raise ValueError('ROM does not fit CHIP-8 4K profile')
        self.memory[0x200:0x200+len(raw)] = raw

    def mem_range(self, address:int, n:int, pc:int, word:int):
        if address < 0 or n < 0 or address+n > 4096:
            raise Trap('memory_oob',pc,word)

    def tick_60hz(self, ticks:int=1):
        if ticks < 0:raise ValueError('nonnegative timer ticks required')
        self.delay=max(0,self.delay-ticks)
        self.sound=max(0,self.sound-ticks)

    def step(self):
        pc0=self.pc
        if pc0 < 0 or pc0+1 >= 4096: raise Trap('fetch_oob',pc0)
        w=(self.memory[pc0]<<8)|self.memory[pc0+1]
        d=decode_table(w,'chip8')
        self.last_family=d.family
        if d.tier == 'invalid':raise Trap('invalid_opcode',pc0,w)
        if d.tier == 'legacy':raise Trap('legacy_system_call_unimplemented',pc0,w)
        if self.waiting and not self.keys:
            return 'waiting'
        x,y,kk,nnn,n=d.x,d.y,d.kk,d.nnn,d.n
        f=d.family
        self.pc=pc0+2
        if f == 'CLS': self.frame[:]=bytes(len(self.frame))
        elif f == 'RET':
            if not self.stack: raise Trap('stack_underflow',pc0,w)
            self.pc=self.stack.pop()
        elif f == 'JP': self.pc=nnn
        elif f == 'CALL':
            if len(self.stack)>=16:raise Trap('stack_overflow',pc0,w)
            self.stack.append(self.pc);self.pc=nnn
        elif f == 'SE_VX_KK':
            if self.v[x]==kk:self.pc+=2
        elif f == 'SNE_VX_KK':
            if self.v[x]!=kk:self.pc+=2
        elif f == 'SE_VX_VY':
            if self.v[x]==self.v[y]:self.pc+=2
        elif f == 'LD_VX_KK':self.v[x]=kk
        elif f == 'ADD_VX_KK':self.v[x]=(self.v[x]+kk)&255
        elif f == 'LD_VX_VY':self.v[x]=self.v[y]
        elif f == 'OR':
            self.v[x]|=self.v[y]
            if self.quirks.reset_vf_logic:self.v[15]=0
        elif f == 'AND':
            self.v[x]&=self.v[y]
            if self.quirks.reset_vf_logic:self.v[15]=0
        elif f == 'XOR':
            self.v[x]^=self.v[y]
            if self.quirks.reset_vf_logic:self.v[15]=0
        elif f == 'ADD_VX_VY':
            z=self.v[x]+self.v[y]; self.v[x]=z&255; self.v[15]=int(z>255)
        elif f == 'SUB':
            a,b=self.v[x],self.v[y];self.v[x]=(a-b)&255;self.v[15]=int(a>=b)
        elif f == 'SHR':
            z=self.v[x] if self.quirks.shift_vx else self.v[y]
            self.v[x]=z>>1;self.v[15]=z&1
        elif f == 'SUBN':
            a,b=self.v[x],self.v[y]; self.v[x]=(b-a)&255;self.v[15]=int(b>=a)
        elif f == 'SHL':
            z=self.v[x] if self.quirks.shift_vx else self.v[y]
            self.v[x]=(z<<1)&255; self.v[15]=int((z&128)!=0)
        elif f == 'SNE_VX_VY':
            if self.v[x]!=self.v[y]:self.pc+=2
        elif f == 'LD_I':self.i=nnn
        elif f == 'JP_V0':
            self.pc=(kk+self.v[x]) if self.quirks.jump_vx else (nnn+self.v[0])
        elif f == 'RND':self.v[x]=self.rng.randrange(256)&kk
        elif f == 'DRW':
            self.mem_range(self.i,n,pc0,w)
            px,py=self.v[x]%64,self.v[y]%32
            collision=0
            for row in range(n):
                bits=self.memory[self.i+row]
                for col in range(8):
                    if bits & (128>>col):
                        xx,yy=px+col,py+row
                        if self.quirks.clip_sprites and (xx>=64 or yy>=32):continue
                        idx=(yy%32)*64+(xx%64)
                        if self.frame[idx]:collision=1
                        self.frame[idx]^=1
            self.v[15]=collision
        elif f in ('SKP','SKNP'):
            key=self.v[x]
            # The VM's hex keypad has 16 positions. Other Vx values never match.
            pressed=key in self.keys
            if (f=='SKP' and pressed) or (f=='SKNP' and not pressed):self.pc+=2
        elif f == 'LD_VX_DT':self.v[x]=self.delay
        elif f == 'WAIT_KEY':
            if not self.keys:
                self.pc=pc0;self.waiting=True;return 'waiting'
            self.v[x]=min(self.keys);self.waiting=False
        elif f == 'LD_DT_VX':self.delay=self.v[x]
        elif f == 'LD_ST_VX':self.sound=self.v[x]
        elif f == 'ADD_I_VX':self.i=(self.i+self.v[x])&0xffff
        elif f == 'FONT':self.i=0x50+5*(self.v[x]&15)
        elif f == 'BCD':
            self.mem_range(self.i,3,pc0,w);z=self.v[x]
            self.memory[self.i:self.i+3]=bytes((z//100,(z//10)%10,z%10))
        elif f == 'SAVE':
            self.mem_range(self.i,x+1,pc0,w)
            self.memory[self.i:self.i+x+1]=bytes(self.v[:x+1])
            if self.quirks.inc_i_on_load_store:self.i+=x+1
        elif f == 'LOAD':
            self.mem_range(self.i,x+1,pc0,w)
            self.v[:x+1]=self.memory[self.i:self.i+x+1]
            if self.quirks.inc_i_on_load_store:self.i+=x+1
        else:raise Trap('known_but_unimplemented',pc0,w)
        self.steps+=1
        return 'executed'

    def state_digest(self):
        h=hashlib.sha256()
        h.update(self.memory)
        h.update(bytes(self.v))
        h.update(self.frame)
        for z in (self.i,self.pc,self.delay,self.sound,len(self.stack)):
            h.update(int(z).to_bytes(4,'little'))
        for s in self.stack:h.update(int(s).to_bytes(4,'little'))
        h.update(bytes(sorted(self.keys)))
        h.update(bytes((int(self.waiting),int(self.quirks.shift_vx),
                        int(self.quirks.inc_i_on_load_store),int(self.quirks.reset_vf_logic),
                        int(self.quirks.clip_sprites),int(self.quirks.jump_vx))))
        h.update(repr(self.rng.getstate()).encode('ascii'))
        return h.hexdigest()