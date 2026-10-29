"""Bounded AGI v2.917 logic byte-layout qualification, not an interpreter.

Operand widths and condition framing follow the AGI logic resource format:
https://github.com/scummvm/scummvm/blob/master/engines/agi/opcodes.cpp
Unsupported/version-dependent encodings fail closed; targets must land on
linear instruction boundaries. No control-flow reachability is asserted.
"""

# Fixed argument widths for v2 action opcodes 00..AD. Later/version-specific
# opcodes are deliberately unsupported by this narrow qualification profile.
_ACTION_WIDTHS = (
 0,1,1,2,2,2,2,2,2,2,2,2,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0,1,1,0,1,1,
 1,1,0,1,1,3,3,3,3,2,2,2,2,1,1,2,2,2,2,2,2,2,2,2,1,2,1,1,1,1,1,1,
 1,1,1,1,1,3,1,1,1,2,1,2,2,1,1,2,2,5,5,3,1,1,2,2,1,1,4,0,1,1,1,2,
 2,2,1,2,0,1,1,3,3,3,0,0,1,2,1,3,0,0,2,5,2,1,2,0,0,3,7,7,0,0,0,0,
 0,1,3,0,0,1,1,0,0,0,0,0,0,0,1,1,1,0,0,3,3,0,3,4,4,1,5,2,1,2,0,
 1,1,0,1,0,0,2,2,2,2,0,1,0,0)
_CONDITION_WIDTHS = {1:2,2:2,3:2,4:2,5:2,6:2,7:1,8:1,9:1,10:2,11:5,
                     12:1,13:0,15:2,16:5,17:5,18:5}


def logic_layout(payload):
    """Return instruction and condition offsets relative to resource payload."""
    if not isinstance(payload,bytes) or not 2<=len(payload)<=65536:
        raise ValueError('Invalid AGI logic resource length')
    size=int.from_bytes(payload[:2],'little'); end=2+size
    if not size or end>len(payload):raise ValueError('Invalid AGI code length')
    pc=2; starts=set(); targets=[]; conditions={}
    def need(n):
        if n<0 or pc+n>end:raise ValueError('Truncated AGI logic instruction')
    while pc<end:
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
            need(2);delta=int.from_bytes(payload[pc:pc+2],'little',signed=True);pc+=2;targets.append(pc+delta)
        else:
            if op>=len(_ACTION_WIDTHS):raise ValueError('Unsupported AGI v2.917 action')
            width=_ACTION_WIDTHS[op];need(width);pc+=width
    if any(target not in starts and target!=end for target in targets):
        raise ValueError('AGI branch target is not an instruction boundary')
    return {'code_start':2,'code_end':end,'instructions':sorted(starts),'conditions':conditions}
