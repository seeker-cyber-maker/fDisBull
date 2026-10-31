"""Recover a strict bounded binary-6502 slice into existing shared IL.

This is newly authored semantic code, not an upstream recompiler wrapper.
Hardware, indirect addressing, calls, backward jumps and incoming stack values
are refused. Direct RAM references require explicit logical bindings.
"""
from __future__ import annotations
from dataclasses import dataclass
from .model import Admission, Bindings, NativeBacking, RecoveredBlock, Refused, canonical, label
from fdisbull.interaction_il import validate_il, ILInvalid


# Explicit accepted instruction encodings. No permissive unknown-opcode path.
OPS = {}
for name, values in {
    'lda': ((0xa9,'imm'),(0xa5,'zp'),(0xad,'abs'),(0xb5,'zpx'),(0xbd,'absx'),(0xb9,'absy')),
    'ldx': ((0xa2,'imm'),(0xa6,'zp'),(0xae,'abs')),
    'ldy': ((0xa0,'imm'),(0xa4,'zp'),(0xac,'abs')),
    'sta': ((0x85,'zp'),(0x8d,'abs'),(0x95,'zpx'),(0x9d,'absx'),(0x99,'absy')),
    'stx': ((0x86,'zp'),(0x8e,'abs')), 'sty': ((0x84,'zp'),(0x8c,'abs')),
    'adc': ((0x69,'imm'),(0x65,'zp'),(0x6d,'abs')),
    'sbc': ((0xe9,'imm'),(0xe5,'zp'),(0xed,'abs')),
    'cmp': ((0xc9,'imm'),(0xc5,'zp'),(0xcd,'abs')),
    'cpx': ((0xe0,'imm'),), 'cpy': ((0xc0,'imm'),),
}.items():
    for opcode, mode in values:
        OPS[opcode] = (name, mode, 3 if mode.startswith('abs') else 2)
for opcode, name in {
    0x18:'clc',0x38:'sec',0xb8:'clv',0xd8:'cld',0xea:'nop',
    0x48:'pha',0x68:'pla',0xaa:'tax',0xa8:'tay',0x8a:'txa',0x98:'tya',
    0xe8:'inx',0xc8:'iny',0xca:'dex',0x88:'dey',
}.items():
    OPS[opcode] = (name,'impl',1)
for opcode, name in {0xf0:'beq',0xd0:'bne',0x90:'bcc',0xb0:'bcs',
                     0x30:'bmi',0x10:'bpl',0x50:'bvc',0x70:'bvs'}.items():
    OPS[opcode] = (name,'rel',2)
OPS[0x4c] = ('jmp','abs',3)


def ref(name): return {'var': name}
def eq(a,b): return {'op':'eq','left':a,'right':b}
def inv(c): return {'op':'not','condition':c}
def both(*c): return {'op':'and','conditions':list(c)}
def either(a,b): return inv(both(inv(a),inv(b)))
def bit(v,n): return {'op':'bit_test','value':v,'bit':n}
def same(a,b): return either(both(a,b),both(inv(a),inv(b)))


@dataclass(frozen=True)
class Instruction:
    offset: int
    name: str
    mode: str
    width: int
    operand: int | None


def decode(backing: NativeBacking) -> tuple[Instruction, ...]:
    code = backing.code
    result = []
    offset = 0
    while offset < len(code):
        try:
            name, mode, width = OPS[code[offset]]
        except KeyError as exc:
            raise Refused(f'unsupported opcode 0x{code[offset]:02x} at +0x{offset:x}') from exc
        if offset + width > len(code):
            raise Refused('truncated instruction at +' + hex(offset))
        operand = int.from_bytes(code[offset+1:offset+width], 'little') if width > 1 else None
        result.append(Instruction(offset,name,mode,width,operand))
        offset += width
    boundaries = {i.offset for i in result} | {len(code)}
    for i in result:
        if i.mode == 'rel' or i.name == 'jmp':
            target = (i.offset + 2 + (i.operand if i.operand < 128 else i.operand-256)
                      if i.mode == 'rel' else i.operand-backing.entry)
            if target not in boundaries or target <= i.offset:
                raise Refused('only forward in-slice, instruction-aligned branches are admitted')
    return tuple(result)


class Builder:
    def __init__(self, backing, bindings):
        self.backing, self.bindings = backing, bindings
        self.reg = {r:label(n) for r,n in bindings.registers}
        self.ram = {a:label(n) for a,n in bindings.ram}
        self.variables = {name: {'type': 'bool' if r in 'cznv' else 'u8',
                                  'initial': False if r in 'cznv' else 0}
                          for r,name in self.reg.items()}
        for name in self.ram.values():
            if name.startswith('$tmp_'):
                raise Refused('tmp_ is reserved for private values')
            self.variables[name] = {'type':'u8','initial':0}
        if any(n.startswith('$tmp_') for n in self.reg.values()):
            raise Refused('tmp_ is reserved for private values')
        self.ids = 0
        self.temps = 0
        self.origin = 0
        self.source_map = []
        self.max_stack = 0
        self.visits = 0

    def stmt(self, op, **fields):
        self.ids += 1
        if self.ids > 750:
            raise Refused('expanded statement budget exceeded')
        ident = f'b{self.ids}'
        self.source_map.append({'id':ident, 'source_offset':self.origin})
        return {'id':ident,'op':op,**fields}

    def assign(self, name, value, op='set'):
        return self.stmt(op, var=name, value=value)

    def temporary(self, body, value, typ='u8'):
        name = '$tmp_' + str(self.temps)
        self.temps += 1
        self.variables[name] = {'type':typ,'initial':0}
        body.append(self.assign(name,value))
        return name

    def set_condition(self, body, name, c):
        yes = self.assign(name,True)
        no = self.assign(name,False)
        body.append(self.stmt('if',condition=c,then=[yes],**{'else':[no]}))

    def nz(self, body, value):
        self.set_condition(body,self.reg['n'],bit(value,7))
        self.set_condition(body,self.reg['z'],eq(value,0))

    def memory(self, instruction, known):
        address = instruction.operand
        if instruction.mode in {'zpx','absx','absy'}:
            index = known['y' if instruction.mode == 'absy' else 'x']
            if index is None:
                raise Refused('dynamic index needs an explicit array-capable profile')
            address = (address + index) & (255 if instruction.mode == 'zpx' else 65535)
        if not 0 <= address < 0x2000:
            raise Refused('MMIO, external RAM and ROM reads need a qualified service profile')
        address &= 0x7ff
        if 0x100 <= address < 0x200:
            raise Refused('explicit source stack-page access conflicts with stack abstraction')
        if address not in self.ram:
            raise Refused(f'unnamed RAM location: 0x{address:x}')
        return self.ram[address]

    def operand(self, instruction, known):
        return instruction.operand if instruction.mode == 'imm' else ref(self.memory(instruction, known))

    def path(self, decoded, offset, stack, known, depth=0):
        if depth > 8:
            raise Refused('control-flow expansion depth exceeded')
        body = []
        by_offset = {i.offset:i for i in decoded}
        end = len(self.backing.code)
        while offset < end:
            self.visits += 1
            if self.visits > 128:
                raise Refused('expanded instruction budget exceeded')
            i = by_offset[offset]
            self.origin = i.offset
            name, mode = i.name, i.mode
            if mode == 'rel':
                target = offset + 2 + (i.operand if i.operand < 128 else i.operand-256)
                flag, value = {'beq':('z',True),'bne':('z',False),'bcc':('c',False),
                               'bcs':('c',True),'bmi':('n',True),'bpl':('n',False),
                               'bvc':('v',False),'bvs':('v',True)}[name]
                yes = self.path(decoded,target,list(stack),dict(known),depth+1)
                no = self.path(decoded,offset+i.width,list(stack),dict(known),depth+1)
                self.origin = i.offset
                body.append(self.stmt('if',condition=eq(ref(self.reg[flag]),value),
                                      then=yes,**{'else':no}))
                return body
            if name == 'jmp':
                offset = i.operand-self.backing.entry
                continue
            if name in {'lda','ldx','ldy'}:
                r = name[-1]
                value = self.operand(i,known)
                body.append(self.assign(self.reg[r],value))
                self.nz(body,ref(self.reg[r]))
                known[r] = i.operand if mode == 'imm' else None
            elif name in {'sta','stx','sty'}:
                body.append(self.assign(self.memory(i,known),ref(self.reg[name[-1]])))
            elif name in {'clc','sec','clv'}:
                body.append(self.assign(self.reg['v' if name == 'clv' else 'c'],name == 'sec'))
            elif name in {'cld','nop'}:
                # Decimal is already disabled by admission. NOP has no projected effects.
                pass
            elif name == 'pha':
                if len(stack) >= 32:
                    raise Refused('saved-value budget exceeded')
                stack.append((self.temporary(body,ref(self.reg['a'])),known['a']))
                self.max_stack = max(self.max_stack,len(stack))
            elif name == 'pla':
                if not stack:
                    raise Refused('incoming/unknown stack values are not admitted')
                saved,constant = stack.pop()
                body.append(self.assign(self.reg['a'],ref(saved)))
                self.nz(body,ref(self.reg['a']))
                known['a'] = constant
            elif name in {'tax','tay','txa','tya'}:
                source,dest = name[1],name[2]
                body.append(self.assign(self.reg[dest],ref(self.reg[source])))
                self.nz(body,ref(self.reg[dest]))
                known[dest] = known[source]
            elif name in {'inx','iny','dex','dey'}:
                r = name[-1]
                body.append(self.assign(self.reg[r],1,'add' if name[0] == 'i' else 'subtract'))
                self.nz(body,ref(self.reg[r]))
                if known[r] is not None:
                    known[r] = (known[r]+(1 if name[0]=='i' else -1)) & 255
            elif name in {'adc','sbc','cmp','cpx','cpy'}:
                register = 'a' if name in {'adc','sbc','cmp'} else name[-1]
                before = self.temporary(body,ref(self.reg[register]))
                right = self.temporary(body,self.operand(i,known))
                total = self.temporary(body,ref(before),'u16')
                if name == 'adc':
                    body.append(self.assign(total,ref(right),'add'))
                    increment = self.assign(total,1,'add')
                    body.append(self.stmt('if',condition=eq(ref(self.reg['c']),True),
                                          then=[increment],**{'else':[]}))
                else:
                    body.append(self.assign(total,256,'add'))
                    body.append(self.assign(total,ref(right),'subtract'))
                    if name == 'sbc':
                        decrement = self.assign(total,1,'subtract')
                        body.append(self.stmt('if',condition=eq(ref(self.reg['c']),False),
                                              then=[decrement],**{'else':[]}))
                result = self.temporary(body,0)
                # Shared IL SET is range-checked; ADD performs explicit modulo narrowing.
                body.append(self.assign(result,ref(total),'add'))
                self.set_condition(body,self.reg['c'],bit(ref(total),8))
                if name in {'adc','sbc'}:
                    body.append(self.assign(self.reg['a'],ref(result)))
                    sign_same = same(bit(ref(before),7),bit(ref(right),7))
                    sign_changed = inv(same(bit(ref(before),7),bit(ref(result),7)))
                    self.set_condition(body,self.reg['v'],both(sign_same if name=='adc' else inv(sign_same),sign_changed))
                    known['a'] = None
                self.nz(body,ref(result))
            else:
                raise Refused('unimplemented admitted instruction: ' + name)
            offset += i.width
        if stack:
            raise Refused('all exits must restore the saved-value stack depth')
        return body


def recover(backing: NativeBacking, bindings: Bindings, admission: Admission = Admission()) -> RecoveredBlock:
    admission.validate()
    decoded = decode(backing)
    builder = Builder(backing, bindings)
    body = builder.path(decoded,0,[],{'a':None,'x':None,'y':None})
    document = {'format':'fdisbull-il-1','role':'uil','variables':builder.variables,
                'resources':{},'body':body}
    try:
        validate_il(document)
    except ILInvalid as exc:
        raise Refused('shared-IL admission failed: '+str(exc)) from exc
    return RecoveredBlock(backing,bindings,admission,canonical(document),
                          canonical(builder.source_map),len(decoded),builder.max_stack)
