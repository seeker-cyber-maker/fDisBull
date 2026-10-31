"""Bounded, read-only AGI 2.917 logic inspection; not a VM or persisted project.

Format references: ScummVM engines/agi/loader_v2.cpp and
https://peterkelly.github.io/agi-re/spec/logic_bytecode.html.
Only explicitly modeled instruction encodings are decoded.
"""
from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from .processor import ProcessorInfo, Location, Successor, DecodedInstruction, decode_instruction

# Encoding lengths only; no assertion that actions have been executed.
_ACTIONS = {1:('increment',1),2:('decrement',1),3:('assignn',2),4:('assignv',2),
            5:('addn',2),6:('addv',2),7:('subn',2),8:('subv',2),
            9:('lindirectv',2),10:('rindirect',2),11:('lindirectn',2),
            12:('set',1),13:('reset',1),14:('toggle',1),15:('set.v',1),
            16:('reset.v',1),17:('toggle.v',1),20:('load.logics',1),21:('load.logics.v',1),
            101:('print',1),102:('print.v',1)}
_COND_LENGTHS = {0:0,1:2,2:2,3:2,4:2,5:2,6:2,7:1,8:1,9:1,10:2,
                 11:5,12:1,13:0,15:2,16:5,17:5,18:5}


@dataclass(frozen=True)
class AGILogicResource:
    code: bytes
    payload: bytes
    logic: int
    profile: str
    space: str
    directory_sha256: str
    volume_sha256: str
    volume: int
    resource_offset: int
    resource_length: int
    code_offset: int
    resource_sha256: str
    _directory: bytes = field(repr=False)
    _volume: bytes = field(repr=False)

    def provenance(self):
        return {name: getattr(self, name) for name in (
            'logic', 'profile', 'space', 'directory_sha256', 'volume_sha256',
            'volume', 'resource_offset', 'resource_length', 'code_offset', 'resource_sha256')}

class AGI2917Processor:
    def __init__(self, space):
        self.info=ProcessorInfo('fdisbull.agi.2.917.subset','1',space,'byte',('decode','static_successors'),None)

    def decode(self, code, location):
        pos=location.offset
        if pos>=len(code): return None
        op=code[pos]; cursor=pos+1; edges=[]; conditions=[]
        def require(n):
            if cursor+n>len(code): raise ValueError(f'truncated instruction at {pos:#x}')
        def edge(kind,target):
            edges.append(Successor(kind,Location(location.space,target) if 0<=target<len(code) else None,
                                   'encoded displacement' if 0<=target<len(code) else f'out-of-range target {target}'))
        if op==0: name='return'
        elif op==0xfe:
            require(2); delta=int.from_bytes(code[cursor:cursor+2],'little',signed=True);cursor+=2
            name='goto';edge('branch',cursor+delta)
        elif op==0xff:
            name='if'; in_or=False; negate=False
            while True:
                require(1); cond=code[cursor];cursor+=1
                if cond==0xff:
                    if in_or or negate: raise ValueError(f'malformed condition markers at {pos:#x}')
                    break
                if cond==0xfc:
                    if negate: raise ValueError(f'malformed condition markers at {pos:#x}')
                    in_or=not in_or;conditions.append({'marker':'or'});continue
                if cond==0xfd:
                    if negate: raise ValueError(f'malformed condition markers at {pos:#x}')
                    negate=True;conditions.append({'marker':'not'});continue
                if cond==14:
                    require(1); n=1+code[cursor]*2
                elif cond in _COND_LENGTHS: n=_COND_LENGTHS[cond]
                else: raise ValueError(f'unsupported condition {cond:#x} at {pos:#x}')
                require(n); conditions.append({'opcode':cond,'operands':list(code[cursor:cursor+n])});cursor+=n;negate=False
            require(2);delta=int.from_bytes(code[cursor:cursor+2],'little',signed=True);cursor+=2
            edge('true',cursor);edge('false',cursor+delta)
        elif op in _ACTIONS:
            name,n=_ACTIONS[op];require(n);cursor+=n;edge('fallthrough',cursor)
        else:
            name='unsupported'; edges.append(Successor('unknown',None,'unsupported opcode; no length inferred'))
        facts={'opcode':op,'mnemonic':name,'size':cursor-pos,'bytes':code[pos:cursor].hex()}
        if op == 3:
            facts['operands'] = [{'kind':'variable', 'index':code[pos+1]},
                                 {'kind':'u8', 'value':code[pos+2]}]
        elif op in (12, 13):
            facts['operands'] = [{'kind':'flag', 'index':code[pos+1]}]
        if conditions: facts['conditions']=conditions
        return DecodedInstruction(location,facts,tuple(edges))


def load_logic(logdir, volume_dir, logic, *, profile):
    if profile!='2.917': raise ValueError('only explicit AGI 2.917 subset is supported')
    if isinstance(logic,bool) or not isinstance(logic,int) or not 0<=logic<=255: raise ValueError('logic must be 0..255')
    with Path(logdir).open('rb') as stream:
        directory=stream.read(769)
    if len(directory)>768 or len(directory)%3: raise ValueError('invalid LOGDIR size')
    if logic*3+3>len(directory): raise ValueError('logic directory entry absent')
    entry=int.from_bytes(directory[logic*3:logic*3+3],'big'); volume=entry>>20; offset=entry&0xfffff
    if offset==0xfffff: raise ValueError('logic resource absent')
    root=Path(volume_dir)
    existing=[p for p in root.iterdir() if p.name.lower()==f'vol.{volume}' and p.is_file()]
    if len(existing)!=1: raise ValueError('expected exactly one matching VOL file')
    path=existing[0]
    with path.open('rb') as stream:
        data=stream.read(2*1024*1024+1)
    if len(data)>2*1024*1024: raise ValueError('volume exceeds 2 MiB limit')
    if offset+5>len(data) or data[offset:offset+2]!=b'\x12\x34': raise ValueError('invalid or truncated v2 resource header')
    if data[offset+2]!=volume: raise ValueError('volume header number mismatch')
    length=int.from_bytes(data[offset+3:offset+5],'little');start=offset+5;end=start+length
    if end>len(data) or length<2: raise ValueError('truncated logic resource')
    payload=data[start:end]; code_length=int.from_bytes(payload[:2],'little')
    if not code_length: raise ValueError('empty logic bytecode')
    if 2+code_length>len(payload): raise ValueError('truncated logic bytecode')
    code=payload[2:2+code_length]; space=f'agi.logic.{logic}.{sha256(payload).hexdigest()}'
    return AGILogicResource(code=code, payload=payload, logic=logic, profile=profile, space=space,
        directory_sha256=sha256(directory).hexdigest(), volume_sha256=sha256(data).hexdigest(),
        volume=volume, resource_offset=offset, resource_length=length, code_offset=start+2,
        resource_sha256=sha256(payload).hexdigest(), _directory=directory, _volume=data)


def inspect_logic(logdir, volume_dir, logic, *, profile, max_instructions=1000):
    if isinstance(max_instructions,bool) or not isinstance(max_instructions,int) or not 1<=max_instructions<=10000: raise ValueError('max_instructions must be 1..10000')
    resource=load_logic(logdir, volume_dir, logic, profile=profile)
    code=resource.code; code_length=len(code); space=resource.space
    processor=AGI2917Processor(space); pending=deque([0] if code else []); seen=set(); instructions=[]; errors=[]
    while pending and len(instructions)<max_instructions:
        pc=pending.popleft()
        if pc in seen: continue
        seen.add(pc)
        try: decoded=decode_instruction(processor,code,Location(space,pc))
        except ValueError as e: errors.append({'offset':pc,'error':str(e)});continue
        if decoded is None: continue
        instructions.append({'offset':pc,**decoded.facts,'successors':[{'kind':e.kind,'offset':e.target.offset if e.target else None,'evidence':e.evidence} for e in decoded.successors]})
        for e in decoded.successors:
            if e.target is not None and e.target.offset not in seen: pending.append(e.target.offset)
    # A branch into a previously decoded instruction cannot establish a valid
    # instruction boundary. Keep the evidence but never mark traversal complete.
    spans=sorted((i['offset'],i['offset']+i['size']) for i in instructions)
    overlaps=any(start<previous_end for (_,previous_end),(start,_) in zip(spans,spans[1:]))
    return {'format':'fdisbull-agi-logic-1','profile':profile,'support':'partial static decode; not execution',
            'logic':logic,'directory_sha256':resource.directory_sha256,'volume_sha256':resource.volume_sha256,
            'volume':resource.volume,'resource_offset':resource.resource_offset,'resource_length':resource.resource_length,'code_offset':resource.code_offset,
            'code_length':code_length,'space':space,'instructions':instructions,'errors':errors,'overlapping_instructions':overlaps,
            'budget_reached':bool(pending),'complete':not pending and not errors and not overlaps and all(i['mnemonic']!='unsupported' and all(e['offset'] is not None for e in i['successors']) for i in instructions)}
