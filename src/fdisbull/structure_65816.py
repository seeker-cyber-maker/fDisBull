"""Bounded 65C816 facts with explicit abstract width and address context.

This is a static reader, not an emulator. Unknown post-call status is retained;
variable-length immediates are refused until their width is known again. No
claim of run-time reachability, scene identity, or target completion is made.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, replace
from hashlib import sha256

from .snes_decode import decode_one
from .structure_patterns import canonical

M_IMMEDIATE = frozenset((0x09, 0x29, 0x49, 0x69, 0x89, 0xA9, 0xC9, 0xE9))
X_IMMEDIATE = frozenset((0xA0, 0xA2, 0xC0, 0xE0))
CONDITIONAL = frozenset((0x10, 0x30, 0x50, 0x70, 0x90, 0xB0, 0xD0, 0xF0))
WRITE = frozenset(('sta','stx','sty','stz','inc','dec','asl','lsr','rol','ror','trb','tsb'))
READ = frozenset(('lda','ldx','ldy','cmp','cpx','cpy','and','ora','eor','bit','adc','sbc'))
ABSOLUTE = frozenset((0x0D,0x0E,0x0C,0x1C,0x2C,0x2D,0x2E,0x4D,0x4E,0x6D,0x6E,
                     0x8C,0x8D,0x8E,0x9C,0xAC,0xAD,0xAE,0xCC,0xCD,0xCE,0xEC,0xED,0xEE))
DIRECT = frozenset((0x04,0x05,0x06,0x14,0x24,0x25,0x26,0x45,0x46,0x64,0x65,0x66,
                   0x84,0x85,0x86,0xA4,0xA5,0xA6,0xC4,0xC5,0xC6,0xE4,0xE5,0xE6))
LONG = frozenset((0x0F,0x2F,0x4F,0x6F,0x8F,0xAF,0xCF,0xEF))


@dataclass(frozen=True)
class DecodeState:
    e: bool | None = None
    m8: bool | None = None
    x8: bool | None = None
    c: bool | None = None
    dbr: int | None = None
    dp: int | None = None

    @classmethod
    def parse(cls, value):
        if not isinstance(value,dict) or set(value)-set(cls.__dataclass_fields__):
            raise ValueError('invalid 65C816 state fields')
        for k in ('e','m8','x8','c'):
            if value.get(k) is not None and type(value[k]) is not bool:
                raise ValueError('status bits must be Boolean or unknown')
        for k,maximum in (('dbr',255),('dp',65535)):
            v=value.get(k)
            if v is not None and (type(v) is not int or not 0<=v<=maximum):
                raise ValueError('invalid data-bank/direct-page state')
        result=cls(**value)
        if result.e is True:
            if result.m8 is False or result.x8 is False:
                raise ValueError('emulation mode requires short accumulator/index widths')
            result=replace(result,m8=True,x8=True)
        return result


def advance_state(state: DecodeState, raw: bytes, mnemonic: str) -> DecodeState:
    """Only propagate proven status operations; never assume a call preserves P."""
    op=raw[0]
    if op==0x18: return replace(state,c=False)
    if op==0x38: return replace(state,c=True)
    if op==0xFB:
        e,c=state.c,state.e
        return replace(state,e=e,c=c,
                       m8=True if e is True else (None if e is None and state.m8 is not True else state.m8),
                       x8=True if e is True else (None if e is None and state.x8 is not True else state.x8))
    if op in (0xC2,0xE2):
        flag=raw[1]; m,x,c=state.m8,state.x8,state.c
        if flag & 0x20: m=True if op==0xE2 or state.e is True else False if state.e is False else None
        if flag & 0x10: x=True if op==0xE2 or state.e is True else False if state.e is False else None
        if flag & 1: c=op==0xE2
        return replace(state,m8=m,x8=x,c=c)
    if mnemonic in ('plp','rti'):
        return replace(state,m8=True if state.e is True else None,
                       x8=True if state.e is True else None,c=None)
    if mnemonic in ('cmp','cpx','cpy','adc','sbc','asl','lsr','rol','ror'):
        return replace(state,c=None)
    if mnemonic in ('plb','mvn','mvp'): return replace(state,dbr=None)
    if mnemonic in ('pld','tcd'): return replace(state,dp=None)
    return state


def probe(data: bytes, windows: list[dict], entries: list[dict], *,
          mapping_id: str, budget: int=12000, max_arm: int=12) -> dict:
    """Decode a bounded abstract CFG through admitted fixed CPU/file windows.

    Entries carry cpu_address and state. Different widths at one address remain
    distinct interpretations. Direct calls seed their callee with the incoming
    state, but the caller continuation starts with unknown returned state. A
    subsequent SEP/REP may establish some widths again. No stack or call summary
    is invented. Indirect transfers and bank-end instructions remain frontiers.
    """
    if not isinstance(data,bytes) or not 1<=len(data)<=64*1024*1024:
        raise ValueError('bounded byte source required')
    if not isinstance(mapping_id,str) or not mapping_id or len(mapping_id)>200:
        raise ValueError('mapping identity required')
    if type(budget) is not int or not 1<=budget<=100000 or type(max_arm) is not int or not 1<=max_arm<=64:
        raise ValueError('invalid instruction/arm budget')
    if not isinstance(windows,list) or not 1<=len(windows)<=256 or not isinstance(entries,list) or not 1<=len(entries)<=256:
        raise ValueError('invalid mapping/entry budget')
    for w in windows:
        if not isinstance(w,dict) or set(w)!={'cpu_start','file_start','size'} or any(type(v) is not int for v in w.values()):
            raise ValueError('invalid mapping window')
        if not 0<=w['cpu_start']<0x1000000 or not 1<=w['size']<=65536 or w['cpu_start']+w['size']>0x1000000:
            raise ValueError('invalid CPU extent')
        if w['file_start']<0 or w['file_start']+w['size']>len(data): raise ValueError('invalid source extent')
    windows=sorted(windows,key=lambda w:w['cpu_start'])
    if any(a['cpu_start']+a['size']>b['cpu_start'] for a,b in zip(windows,windows[1:])):
        raise ValueError('overlapping CPU windows')
    def offset(address):
        for w in windows:
            if w['cpu_start']<=address<w['cpu_start']+w['size']:
                return w['file_start']+address-w['cpu_start']
        return None
    roots=[]
    for entry in entries:
        if not isinstance(entry,dict) or set(entry)!={'cpu_address','state'} or type(entry['cpu_address']) is not int or offset(entry['cpu_address']) is None:
            raise ValueError('entry outside supplied mapping')
        roots.append((entry['cpu_address'],DecodeState.parse(entry['state'])))
    roots=sorted(set(roots),key=lambda k:(k[0],canonical(asdict(k[1]))))
    digest=sha256(data).hexdigest(); mh=sha256(canonical(windows).encode()).hexdigest()
    space=f'snes65816:{digest}:map:{mapping_id}:{mh}'
    todo=deque(roots); seen=set(); rows={}; incoming=defaultdict(set); successors=defaultdict(list); issues=[]
    for key in roots: incoming[key].add(('entry',key))
    def add(src,dst,kind):
        incoming[dst].add((kind,src)); successors[src].append((kind,dst))
        if dst not in seen: todo.append(dst)
    def problem(a,state,reason):
        issues.append({'address':a,'decode_context':asdict(state),'reason':reason})
    while todo and len(seen)<budget:
        key=todo.popleft()
        if key in seen: continue
        seen.add(key); a,state=key; off=offset(a)
        if off is None: problem(a,state,'unmapped continuation'); continue
        opcode=data[off]
        if opcode in M_IMMEDIATE and state.m8 is None or opcode in X_IMMEDIATE and state.x8 is None:
            problem(a,state,'unknown immediate width'); continue
        raw=bytearray()
        for k in range(4):
            p=offset(a+k)
            if p is None or p!=off+k or ((a+k)>>16)!=(a>>16): break
            raw.append(data[p])
        try: ins=decode_one(bytes(raw),a,m8=state.m8 is not False,x8=state.x8 is not False)
        except ValueError as exc: problem(a,state,str(exc)); continue
        raw=bytes(raw[:ins['size']]); ins['raw']=raw; ins['state']=state; ins['file_offset']=off
        rows[key]=ins; after=advance_state(state,raw,ins['mnemonic'])
        nxt=(a&0xff0000)|((a+ins['size'])&65535)
        if opcode in CONDITIONAL or opcode in (0x80,0x82):
            target=(a&0xff0000)|((nxt+int.from_bytes(raw[1:],'little',signed=True))&65535)
            tstate=after
            if opcode in (0x90,0xb0): tstate=replace(after,c=opcode==0xb0)
            add(key,(target,tstate),'branch')
            if opcode in CONDITIONAL:
                fstate=replace(after,c=opcode==0x90) if opcode in (0x90,0xb0) else after
                add(key,(nxt,fstate),'fallthrough')
        elif opcode in (0x4C,0x5C,0x20,0x22):
            target=int.from_bytes(raw[1:],'little')
            if opcode in (0x4C,0x20): target|=a&0xff0000
            add(key,(target,after),'call' if opcode in (0x20,0x22) else 'jump')
            if opcode in (0x20,0x22):
                add(key,(nxt,DecodeState()),'unqualified-return')
                problem(a,state,'call return status/banks unsummarized')
        elif opcode in (0x60,0x6B,0x40,0x00,0x02,0xDB):
            if opcode in (0x00,0x02): problem(a,state,'software interrupt continuation unresolved')
        elif opcode in (0x6C,0x7C,0xDC,0xFC,0xCB):
            problem(a,state,'interrupt wait' if opcode==0xCB else 'indirect transfer unresolved')
        else: add(key,(nxt,after),'fallthrough')
    overlap=set(); occupied={}
    for key,i in rows.items():
        state=key[1];width_context=(state.e,state.m8,state.x8)
        for address in range(key[0],key[0]+i['size']):
            slot=(width_context,address)
            for prior in occupied.get(slot,()):
                if prior[0]!=key[0]:overlap.update((prior,key))
            occupied.setdefault(slot,[]).append(key)
    def evidence(key):
        i=rows[key]
        return {'space':space,'source_sha256':digest,'mapping_id':mapping_id,
                'cpu_address':key[0],'file_offset':i['file_offset'],'size':i['size'],
                'instruction_sha256':sha256(i['raw']).hexdigest(),'decode_context':asdict(key[1]),
                'mnemonic':i['mnemonic'],'operand_text':i['operands']}
    def token(key): return str(key[0])+':'+sha256(canonical(asdict(key[1])).encode()).hexdigest()[:16]
    def unique(key): return key in rows and key not in overlap and len(incoming[key])==1
    def next_key(key):
        return next((dst for kind,dst in successors[key] if kind=='fallthrough'),None)
    def memory(key):
        i=rows[key]; raw=i['raw']; op=raw[0]; s=key[1]; m=i['mnemonic']
        if m not in READ|WRITE: return None
        width_flag=s.x8 if m in ('ldx','ldy','stx','sty','cpx','cpy') else s.m8
        if width_flag is None:return None
        width=8 if width_flag else 16
        if op in DIRECT and s.dp is not None: address=(s.dp+raw[1])&65535
        elif op in ABSOLUTE and s.dbr is not None: address=(s.dbr<<16)|int.from_bytes(raw[1:],'little')
        elif op in LONG: address=int.from_bytes(raw[1:],'little')
        else:return None
        bank,lo=address>>16,address&65535
        if width==16 and lo in (0x1fff,0x5fff,0xffff):return None
        if bank in (0x7e,0x7f):domain='state'; normalized=address; memspace='snes-wram'
        elif (bank<0x40 or 0x80<=bank<0xc0) and lo<0x2000:
            domain='state';normalized=0x7e0000+lo;memspace='snes-wram'
        elif (bank<0x40 or 0x80<=bank<0xc0) and 0x2000<=lo<0x6000:
            domain='device';normalized=lo;memspace='snes-io'
        else:domain='unresolved';normalized=address;memspace='snes-cpu-bus'
        return {'space':memspace,'scope':space,'address':normalized,'width':width},domain
    nodes=[];edges=[];accesses=[];frontiers=[]
    for key,i in sorted(rows.items(),key=lambda kv:(kv[0][0],token(kv[0]))):
        if key in overlap:continue
        m=i['mnemonic']; ev=evidence(key); mem=memory(key)
        if mem:
            accesses.append({'id':space+':access:'+token(key),'kind':'write' if m in WRITE else 'read',
                             'storage':mem[0],'domain':mem[1],'evidence':ev})
        if m=='wai':
            accesses.append({'id':space+':wait:'+token(key),'kind':'wait','evidence':ev,
                             'domain':'interrupt','release':'unresolved interrupt service'})
        nkey=next_key(key); n=rows.get(nkey)
        if m=='lda' and mem and n and unique(nkey) and n['raw'][0]==0x29:
            gkey=next_key(nkey);g=rows.get(gkey)
            if g and unique(gkey) and g['mnemonic'] in ('beq','bne'):
                prefix=space+':mask:'+token(key)
                r={'id':prefix+':read','role':'read','evidence':ev,'storage':mem[0],'expression':i['operands']}
                mask={'id':prefix+':mask','role':'mask','evidence':evidence(nkey),'value':int.from_bytes(n['raw'][1:],'little')}
                gate={'id':prefix+':gate','role':'branch','evidence':evidence(gkey),'condition':g['mnemonic']}
                nodes.extend((r,mask,gate));edges.extend(((r['id'],mask['id'],'value'),(mask['id'],gate['id'],'predicate')))
        if i['raw'][0] not in (0xC9,0xE0,0xC0) or not n or not unique(nkey) or n['mnemonic'] not in ('beq','bne'):continue
        prefix=space+':selector:'+token(key)
        s={'id':prefix+':test','role':'selector_test','evidence':ev,'register':{'cmp':'a','cpx':'x','cpy':'y'}[m],
           'value':int.from_bytes(i['raw'][1:],'little'),'width':8*(i['size']-1)}
        gate={'id':prefix+':gate','role':'branch','evidence':evidence(nkey),'condition':n['mnemonic']}
        nodes.extend((s,gate));edges.append((s['id'],gate['id'],'predicate'))
        for arm,start in successors[nkey]:
            at=start;path=[];visited=set();reason='arm budget'
            for _ in range(max_arm):
                if at in visited:reason='arm loop';break
                visited.add(at)
                if not unique(at):reason='join or undecoded continuation';break
                j=rows[at];path.append(evidence(at));operation=None
                if j['mnemonic'] in ('jsr','jsl'):operation='call'
                elif j['mnemonic'] in ('rts','rtl','rti'):operation='return'
                elif j['mnemonic'] in WRITE and memory(at):operation='memory_write'
                elif j['mnemonic']=='wai':operation='wait'
                if operation:
                    effect={'id':prefix+':'+arm,'role':'effect','evidence':evidence(at),'operation':operation,
                            'path_witness':path,'selector_relation':'equal' if ((arm=='branch')==(n['mnemonic']=='beq')) else 'not_equal',
                            'storage_or_callee_role':'unresolved'}
                    if memory(at):effect['storage']=memory(at)[0]
                    nodes.append(effect);edges.append((gate['id'],effect['id'],'controls'));reason=None;break
                if j['mnemonic'] not in ('lda','ldx','ldy','tax','tay','txa','tya','nop','clc','sec','rep','sep','jmp','jml','bra','brl'):
                    reason='opaque operation or nested decision';break
                succ=successors[at]
                if len(succ)!=1:reason='nonlinear continuation';break
                at=succ[0][1]
            if reason:frontiers.append({'selector':key[0],'arm':arm,'reason':reason})
    return {'nodes':nodes,'edges':edges,'accesses':accesses,'source_sha256':digest,'mapping_id':mapping_id,
            'decoded_candidate_instructions':len(rows),'abstract_states_visited':len(seen),'overlapping_starts':len(overlap),
            'instruction_budget_exhausted':bool(todo),'issues':issues,'arm_frontiers':frontiers,
            'runtime_observed':False,'mapping_provenance':'supplied static windows; CPU mode propagated only through supported facts'}
