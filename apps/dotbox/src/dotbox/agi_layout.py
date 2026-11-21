# Extracted from first-party fDisBull v0.34.1; no license reassignment.
# Source commit: 011f1b8cb281edda208026aee9cdb238b800b2d7
# Original path: src/fdisbull/agi_layout.py
# Original SHA-256: 4c81c70c000128141c964cb29a913ded5e9e1a05d9ff1622e9c580afbbf94edb
# https://github.com/seeker-cyber-maker/fDisBull/blob/011f1b8cb281edda208026aee9cdb238b800b2d7/src/fdisbull/agi_layout.py

"""Bounded AGI v2.917 logic byte-layout qualification, not an interpreter.

Operand widths and condition framing follow the AGI logic resource format:
https://github.com/scummvm/scummvm/blob/master/engines/agi/opcodes.cpp
Unsupported/version-dependent encodings fail closed; targets must land on
linear instruction boundaries. No control-flow reachability is asserted.

DotBox qualifies only the common IF skip range 0..0x7fff. ScummVM reads IF
displacements as unsigned while the behavioral specification describes signed
displacements; high-bit IF values remain opaque pending native qualification.
GOTO remains signed. Sources for this deliberately narrower profile:
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/op_test.cpp
https://github.com/scummvm/scummvm/blob/f7403b6efaae2f033e8abea80b3fb6bee5303369/engines/agi/logic.h
https://peterkelly.github.io/agi-re/spec/logic_bytecode.html
"""

# Fixed argument widths for v2 action opcodes 00..AD. Later/version-specific
# opcodes are deliberately unsupported by this narrow qualification profile.
_ACTION_WIDTHS = (
 0,1,1,2,2,2,2,2,2,2,2,2,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,1,1,0,1,1,
 1,1,0,1,1,3,3,3,3,2,2,2,2,1,1,2,2,2,2,2,2,2,2,2,1,2,1,1,1,1,1,1,
 1,1,1,1,1,3,1,1,1,2,1,2,2,1,1,2,2,5,5,3,1,1,2,2,1,1,4,0,1,1,1,2,
 2,2,1,2,0,1,1,3,3,3,0,0,1,2,1,3,0,0,2,5,2,1,2,0,0,3,7,7,0,0,0,0,
 0,1,3,0,0,1,1,0,0,0,0,0,0,0,1,1,1,0,0,3,3,0,3,4,4,1,5,2,1,2,0,
 1,1,0,1,0,0,2,2,2,2,0,1,0,0,0)
_CONDITION_WIDTHS = {0:0,1:2,2:2,3:2,4:2,5:2,6:2,7:1,8:1,9:1,10:2,11:5,
                     12:1,13:0,15:2,16:5,17:5,18:5}


class LogicBudgetExceeded(ValueError):
    """A declared span or next instruction cannot be admitted within budget."""

    def __init__(self, message, scope='instructions'):
        super().__init__(message)
        self.scope = scope


def logic_code_span(payload):
    """Validate the declared code extent without walking any instructions."""
    if not isinstance(payload,bytes) or not 2<=len(payload)<=65536:
        raise ValueError('Invalid AGI logic resource length')
    size=int.from_bytes(payload[:2],'little'); end=2+size
    if not size or end>len(payload):raise ValueError('Invalid AGI code length')
    return 2, end


def logic_layout(payload, *, max_instructions=65534, usage=None):
    """Return bounded offsets, charging attempted records even on later errors."""
    if type(max_instructions) is not int or not 0 <= max_instructions <= 1000000:
        raise ValueError('max_instructions must be an integer in 0..1000000')
    _, end = logic_code_span(payload)
    if usage is None:
        usage = {}
    usage['instructions_attempted'] = 0
    pc=2; starts=set(); targets=[]; conditions={}
    def need(n):
        if n<0 or pc+n>end:raise ValueError('Truncated AGI logic instruction')
    while pc<end:
        if usage['instructions_attempted'] >= max_instructions:
            raise LogicBudgetExceeded('Global instruction budget cannot cover this complete LOGIC')
        usage['instructions_attempted'] += 1
        start=pc;starts.add(start); op=payload[pc];pc+=1
        if op==0xfe:
            need(2);delta=int.from_bytes(payload[pc:pc+2],'little',signed=True);pc+=2;targets.append(pc+delta)
        elif op==0xff:
            in_or=False;negated=False;count=0
            while True:
                need(1); loc=pc;cond=payload[pc];pc+=1
                if cond==0xff:
                    if in_or or negated or not count:raise ValueError('Invalid AGI condition markers')
                    break
                if cond==0xfc:
                    if negated:raise ValueError('Invalid AGI condition markers')
                    in_or=not in_or;continue
                if cond==0xfd:
                    if negated:raise ValueError('Invalid AGI condition markers')
                    negated=True;continue
                if cond==14:
                    need(1);words=payload[pc];pc+=1
                    if not words:raise ValueError('Empty AGI said condition')
                    width=2*words
                else:
                    if cond not in _CONDITION_WIDTHS:raise ValueError('Unsupported AGI condition')
                    width=_CONDITION_WIDTHS[cond]
                need(width);pc+=width;conditions[loc]={'opcode':cond,'end':pc,'negated':negated};negated=False;count+=1
            need(2);delta=int.from_bytes(payload[pc:pc+2],'little')
            if delta & 0x8000:
                raise ValueError('High-bit IF displacement is unqualified in the common AGI 2.917 profile')
            pc+=2;targets.append(pc+delta)
        else:
            if op>=len(_ACTION_WIDTHS):raise ValueError('Unsupported AGI v2.917 action')
            width=_ACTION_WIDTHS[op];need(width);pc+=width
    if any(target not in starts and target!=end for target in targets):
        raise ValueError('AGI branch target is not an instruction boundary')
    return {'code_start':2,'code_end':end,'instructions':sorted(starts),'conditions':conditions}
