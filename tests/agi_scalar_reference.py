"""Independent nominal AGI scalar test oracle; not a game interpreter.

Reads authored or privately supplied raw code without production decoder/lifter
helpers. It models only the stated scalar/control subset, with explicit cached
entries and global component stops. No engine devices, parser or runtime work.
IF skips are unsigned and GOTO is signed; primary reference is pinned ScummVM
f7403b6efaae2f033e8abea80b3fb6bee5303369, engines/agi/op_test.cpp.
"""

def raw_condition(code, cursor, state):
    terms, group, negate = [], None, False
    variables, flags = set(), set()
    while True:
        op = code[cursor]; cursor += 1
        if op == 0xff:
            if group is not None or negate: raise ValueError('bad markers')
            return all(terms), cursor, variables, flags
        if op == 0xfc:
            if negate: raise ValueError('bad markers')
            if group is None: group = []
            else: terms.append(any(group)); group = None
            continue
        if op == 0xfd:
            if negate: raise ValueError('bad not')
            negate=True;continue
        if not 1 <= op <= 7: raise ValueError('unsupported predicate')
        index=code[cursor];cursor+=1
        if op == 7:
            flags.add(index); value=state[f'$agi_f{index}']
        else:
            variables.add(index);a=state[f'$agi_v{index}']; operand=code[cursor];cursor+=1
            if op%2==0:
                variables.add(operand);b=state[f'$agi_v{operand}']
            else:b=operand
            value=(a==b) if op<=2 else (a<b) if op<=4 else (a>b)
        if negate:value=not value;negate=False
        (terms if group is None else group).append(value)


def oracle(codes, root, entry, stops, entries, state, *, max_steps=128, max_depth=8):
    state=dict(state);logic=root;pc=entry;stack=[];trace=[]
    for _ in range(max_steps):
        trace.append((logic,pc));code=codes[logic]
        if (logic,pc) in stops:
            return state,trace,list(stack),'stop'
        op=code[pc];pc+=1
        if op==0:
            if not stack:return state,trace,[],'return'
            logic,pc=stack.pop();continue
        if op==0x16:
            target=code[pc];pc+=1
            if target not in entries or target not in codes or len(stack)>=max_depth:raise ValueError('unknown call')
            stack.append((logic,pc));logic=target;pc=entries[target];continue
        if op==0xfe:
            delta=int.from_bytes(code[pc:pc+2],'little',signed=True);pc+=2;pc+=delta;continue
        if op==0xff:
            match,pc,_,_=raw_condition(code,pc,state)
            delta=int.from_bytes(code[pc:pc+2],'little');pc+=2
            if not match:pc+=delta
            continue
        if op not in (*range(1,9),12,13,14):raise ValueError('unsupported opcode')
        index=code[pc];pc+=1
        if op in (12,13,14):
            name=f'$agi_f{index}'
            state[name]=True if op==12 else False if op==13 else not state[name]
            continue
        name=f'$agi_v{index}'
        if op==1:state[name]=min(255,state[name]+1)
        elif op==2:state[name]=max(0,state[name]-1)
        else:
            arg=code[pc];pc+=1
            value=state[f'$agi_v{arg}'] if op in (4,6,8) else arg
            if op in (3,4):state[name]=value
            elif op in (5,6):state[name]=(state[name]+value)&255
            else:state[name]=(state[name]-value)&255
    raise ValueError('oracle instruction budget')


def referenced(code,pc):
    # Discover selected condition inputs by reading its raw encoding, without
    # importing the production decoder. Try all variable/flag ids as zero.
    state={f'$agi_v{i}':0 for i in range(256)}|{f'$agi_f{i}':False for i in range(256)}
    if code[pc]!=0xff:raise ValueError('expected if')
    _,end,vs,fs=raw_condition(code,pc+1,state)
    delta=int.from_bytes(code[end:end+2],'little');end+=2
    return vs,fs,(end,end+delta)


def oracle_selftest():
    # Authored bytecode cases, with manually derived outcomes.
    # IF false displacement 0x8000 is unsigned: target is 7 + 32768.
    huge=bytes.fromhex('ff010101ff0080') + bytes(32769)
    out,trace,stack,kind=oracle({0:huge},0,0,{(0,32775)},{},{'$agi_v1':0})
    assert trace==[(0,0),(0,32775)] and kind=='stop' and not stack
    assert referenced(huge,0)[2] == (7,32775)
    # GOTO displacement remains signed: end at 6 plus -6 reaches offset zero.
    back=bytes.fromhex('000000fefaff')
    out,trace,stack,kind=oracle({0:back},0,3,{(0,0)},{},{})
    assert trace==[(0,3),(0,0)] and kind=='stop'
    code=bytes.fromhex('010102020401030501010603010701020803010e0700')
    state={'$agi_v1':255,'$agi_v2':0,'$agi_v3':99,'$agi_f7':False}
    actual,_,stack,kind=oracle({0:code},0,0,set(),{},state)
    assert actual=={'$agi_v1':98,'$agi_v2':0,'$agi_v3':101,'$agi_f7':True}
    assert stack==[] and kind=='return'
    caller=bytes.fromhex('160103010900');callee=bytes.fromhex('03020700')
    state={'$agi_v1':0,'$agi_v2':0}
    actual,trace,stack,kind=oracle({0:caller,1:callee},0,0,set(),{1:0},state)
    assert actual=={'$agi_v1':9,'$agi_v2':7} and trace==[(0,0),(1,0),(1,3),(0,2),(0,5)]
    actual,trace,stack,kind=oracle({0:caller,1:callee},0,0,{(1,0)},{1:0},state)
    assert actual==state and trace==[(0,0),(1,0)] and stack==[(0,2)] and kind=='stop'
    terms=bytes.fromhex('fc010105fd0707fc050302')
    code=b'\xff'+terms+b'\xff\x06\x00'+bytes.fromhex('03020afe030003021400')
    for a,flag,c,expected in [(5,True,3,10),(0,False,3,10),(0,True,3,20),(5,False,2,20)]:
        out,_,_,_=oracle({0:code},0,0,set(),{}, {'$agi_v1':a,'$agi_v2':0,'$agi_v3':c,'$agi_f7':flag})
        assert out['$agi_v2']==expected
