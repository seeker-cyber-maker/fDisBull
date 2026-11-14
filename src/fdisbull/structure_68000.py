"""Bounded Motorola 68000 facts for a declared static Genesis cartridge view.

This is not a CPU emulator. Unknown indirect transfers and cartridge-control
writes remain frontiers. Unresolved indirect stores preserve an explicit
fixed-mapping assumption; their destinations and effects are not invented.
"""
from __future__ import annotations
from collections import deque
from hashlib import sha256
import json


def probe(data: bytes, windows: list[dict], entries: list[int], *,
          mapping_id: str, budget: int=30000, max_arm: int=12) -> dict:
    import capstone as cs
    from capstone import m68k as m
    if not isinstance(data,bytes) or not 1<=len(data)<=64*1024*1024:raise ValueError('bounded immutable source required')
    if not isinstance(mapping_id,str) or not 1<=len(mapping_id)<=200:raise ValueError('mapping identity required')
    if type(budget) is not int or not 1<=budget<=100000 or type(max_arm) is not int or not 1<=max_arm<=64:raise ValueError('invalid work budget')
    if not isinstance(windows,list) or not 1<=len(windows)<=64 or not isinstance(entries,list) or not 1<=len(entries)<=256:raise ValueError('bounded windows and roots required')
    for w in windows:
        if not isinstance(w,dict) or set(w)!={'cpu_start','file_start','size'} or any(type(x) is not int for x in w.values()):raise ValueError('invalid mapping')
        if w['cpu_start']<0 or w['file_start']<0 or w['size']<1 or w['cpu_start']+w['size']>1<<24 or w['file_start']+w['size']>len(data):raise ValueError('mapping outside source/address domain')
    windows=sorted(windows,key=lambda x:x['cpu_start'])
    if any(a['cpu_start']+a['size']>b['cpu_start'] for a,b in zip(windows,windows[1:])):raise ValueError('overlapping CPU mappings')
    def offset(a):
        for w in windows:
            if w['cpu_start']<=a<w['cpu_start']+w['size']:return w['file_start']+a-w['cpu_start']
        return None
    if any(type(a) is not int or a%2 or offset(a) is None for a in entries):raise ValueError('unmapped/odd entry')
    digest=sha256(data).hexdigest();mh=sha256(json.dumps(windows,sort_keys=True).encode()).hexdigest()
    space=f'genesis68000:{digest}:map:{mapping_id}:{mh}'
    decoder=cs.Cs(cs.CS_ARCH_M68K,cs.CS_MODE_BIG_ENDIAN|cs.CS_MODE_M68K_000);decoder.detail=True
    rows={};incoming={};todo=deque(sorted(set(entries)));issues=[];accesses=[];attempted=set();successors={}
    for a in entries:incoming.setdefault(a,set()).add(('root',a))
    def base(i):return i.mnemonic.split('.')[0]
    def width(i):return {'b':8,'w':16,'l':32}.get(i.mnemonic.rsplit('.',1)[-1])
    def absolute(o,i):
        if o.type!=m.M68K_OP_MEM:return None
        if o.address_mode==m.M68K_AM_ABSOLUTE_DATA_LONG:return int(o.imm)&0xffffff
        if o.address_mode==m.M68K_AM_ABSOLUTE_DATA_SHORT:
            v=int(o.imm)&65535;return (v if v<32768 else v-65536)&0xffffff
        if o.address_mode==m.M68K_AM_PCI_DISP:return (i.address+2+o.mem.disp)&0xffffff
        return None
    def destination(i):
        for o in i.operands:
            if o.type==m.M68K_OP_BR_DISP:return (i.address+2+o.br_disp.disp)&0xffffff
        if len(i.operands)==1:return absolute(i.operands[0],i)
        return None
    def stores(i):
        b=base(i);ops=i.operands
        if not ops:return []
        if b in ('move','movea','movem','movep','clr','neg','negx','not','add','sub','and','or','eor','addi','subi','andi','ori','eori','addq','subq','bset','bclr','bchg','tas','asl','asr','lsl','lsr','rol','ror','roxl','roxr') or (b.startswith('s') and b not in ('stop','suba')):
            return [len(ops)-1] if ops[-1].type==m.M68K_OP_MEM else []
        return []
    def transfer(i):return base(i) in ('jsr','bsr','jmp','bra') or i.group(cs.CS_GRP_JUMP)
    def end(i):return base(i) in ('rts','rte','rtr','stop','reset','illegal','trap','trapv')
    def add(a,b):
        incoming.setdefault(b,set()).add(('edge',a));successors.setdefault(a,[]).append(b)
        if b not in attempted:todo.append(b)
    while todo and len(attempted)<budget:
        a=todo.popleft()
        if a in attempted:continue
        attempted.add(a);off=offset(a)
        if a%2 or off is None:
            issues.append({'address':a,'reason':'unmapped or odd code target'});continue
        raw=bytearray()
        for k in range(22):
            if offset(a+k)!=off+k:break
            raw.append(data[off+k])
        i=next(decoder.disasm(bytes(raw),a,count=1),None)
        if i is None or not i.id or i.size%2:
            issues.append({'address':a,'reason':'unsupported/truncated 68000 instruction'});continue
        rows[a]=i;b=base(i);n=a+i.size
        destinations=[absolute(i.operands[k],i) for k in stores(i)]
        # Static ROM writes / mapper controls invalidate this view. Unresolved
        # addresses are disclosed, not silently resolved from stale registers.
        if any(v is not None and (v<0x400000 or 0xa13000<=v<=0xa130ff) for v in destinations):
            issues.append({'address':a,'reason':'cartridge-control/ROM write; mapping continuation unresolved'});continue
        if end(i):
            if b in ('stop','reset','trap','trapv','illegal'):issues.append({'address':a,'reason':'system/interrupt continuation unresolved','operation':b})
            continue
        if transfer(i):
            t=destination(i)
            if t is None:issues.append({'address':a,'reason':'indirect transfer unresolved','operation':b})
            else:add(a,t)
            if b not in ('jmp','bra'):add(a,n)
        else:add(a,n)
    overlap=set();occupied={}
    for a,i in sorted(rows.items()):
        for p in range(a,a+i.size):
            if p in occupied and occupied[p]!=a:overlap.update((a,occupied[p]))
            occupied[p]=a
    def ev(i):return {'space':space,'source_sha256':digest,'cpu_address':i.address,'file_offset':offset(i.address),
        'mapping_id':mapping_id,'size':i.size,'instruction_sha256':sha256(bytes(i.bytes)).hexdigest(),
        'mnemonic':i.mnemonic,'operand_text':i.op_str}
    def unique(a):return a in rows and a not in overlap and len(incoming.get(a,set()))==1
    def expression(o,i):
        if o.type==m.M68K_OP_REG:return {'register':i.reg_name(o.reg),'width':width(i)}
        if o.type==m.M68K_OP_IMM:return {'immediate':int(o.imm),'width':width(i)}
        if o.type==m.M68K_OP_MEM:return {'address_mode':o.address_mode,'absolute':absolute(o,i),
            'base':i.reg_name(o.mem.base_reg or (o.reg if o.address_mode in (3,4,5) else 0)),
            'index':i.reg_name(o.mem.index_reg),'displacement':o.mem.disp,'width':width(i)}
        return {'operand_type':o.type,'unresolved':True}
    nodes=[];edges=[];frontiers=[];unresolved_stores=0
    for a,i in sorted(rows.items()):
        if a in overlap:continue
        b=base(i);ops=i.operands;writes=stores(i);w=width(i)
        if b=='stop':accesses.append({'id':space+f':wait:{a}','kind':'wait','evidence':ev(i)})
        unresolved_stores+=sum(absolute(ops[k],i) is None for k in writes)
        if w and b not in ('lea','pea') and not transfer(i):
            for k,o in enumerate(ops):
                addr=absolute(o,i)
                if addr is None:continue
                kinds=['write'] if k in writes else ['read']
                if k in writes and b not in ('move','movem','movep','clr'):kinds.insert(0,'read')
                for kind in kinds:
                    domain='state' if 0xff0000<=addr<=0xffffff else 'device' if 0xa00000<=addr<=0xa1ffff or 0xc00000<=addr<=0xc0001f else 'unresolved'
                    accesses.append({'id':space+f':access:{a}:{k}:{kind}','kind':kind,'domain':domain,
                        'storage':{'scope':space,'space':'genesis-24bit-bus','address':addr,'width':w},'evidence':ev(i)})
        nxt=rows.get(a+i.size)
        if not nxt or not unique(nxt.address) or base(nxt) not in ('beq','bne'):continue
        prefix=space+f':predicate:{a}'
        gate={'id':prefix+':gate','role':'branch','condition':base(nxt),'evidence':ev(nxt)}
        predicate=None;selector=None
        if b=='cmpi' and len(ops)==2 and ops[0].type==m.M68K_OP_IMM and ops[1].type in (m.M68K_OP_REG,m.M68K_OP_MEM):
            selector={'id':prefix+':selector','role':'selector_test','operand':expression(ops[1],i),'value':int(ops[0].imm),'width':w,'evidence':ev(i)}
            nodes.extend((selector,gate));edges.append((selector['id'],gate['id'],'predicate'));predicate=selector
        elif b in ('andi','btst') and len(ops)==2 and ops[0].type==m.M68K_OP_IMM:
            loaded=None;memop=None
            if ops[1].type==m.M68K_OP_MEM:loaded=i;memop=ops[1]
            elif ops[1].type==m.M68K_OP_REG:
                prev=list(incoming.get(a,set()))
                p=rows.get(prev[0][1]) if len(prev)==1 and prev[0][0]=='edge' else None
                if p and p.address not in overlap and base(p)=='move' and p.address+p.size==a and len(p.operands)==2 and p.operands[0].type==m.M68K_OP_MEM and p.operands[1].type==m.M68K_OP_REG and p.operands[1].reg==ops[1].reg:
                    bit=int(ops[0].imm)%32
                    if (b=='andi' and width(p)==w) or (b=='btst' and width(p) and bit<width(p)):
                        loaded=p;memop=p.operands[0]
            if loaded is not None:
                bits=(8 if ops[1].type==m.M68K_OP_MEM else 32)
                mask=1<<(int(ops[0].imm)%bits) if b=='btst' else int(ops[0].imm)
                if b=='andi' and mask in (0,(1<<(w or 32))-1):continue
                read={'id':prefix+':read','role':'read','expression':expression(memop,loaded),'evidence':ev(loaded)}
                masknode={'id':prefix+':mask','role':'mask','value':mask,'operation':b,'evidence':ev(i)}
                nodes.extend((read,masknode,gate));edges.extend(((read['id'],masknode['id'],'value'),(masknode['id'],gate['id'],'predicate')))
        if selector is None:continue
        target=destination(nxt)
        for path,dest in (('taken',target),('fallthrough',nxt.address+nxt.size)):
            seen=set();witness=[];reason='arm budget'
            for _ in range(max_arm):
                if dest in seen:reason='loop';break
                seen.add(dest)
                if not unique(dest):reason='join/undecoded/overlapping continuation';break
                r=rows[dest];rb=base(r);witness.append(ev(r));kind=None;payload={}
                if rb in ('jsr','bsr'):kind='call';payload={'target':destination(r),'callee_summary':'unknown'}
                elif rb in ('rts','rte','rtr'):kind='return'
                elif stores(r):kind='memory_write';payload={'destination':expression(r.operands[-1],r),'operation':rb}
                if kind:
                    effect={'id':prefix+':effect:'+path,'role':'effect','kind':kind,'evidence':ev(r),
                        'path':path,'equality':(path=='taken')==(base(nxt)=='beq'),'witness':witness,**payload}
                    nodes.append(effect);edges.append((gate['id'],effect['id'],'controls'));reason=None;break
                if transfer(r) or end(r):reason='transfer/system boundary';break
                if rb not in ('move','moveq','movea','lea','clr','addq','subq','andi','ori','eori','nop','ext','swap'):
                    reason='opaque intermediate operation';break
                dest=r.address+r.size
            if reason:frontiers.append({'predicate':a,'path':path,'reason':reason})
    return {'nodes':nodes,'edges':edges,'accesses':accesses,'decoded_candidate_instructions':len(rows),
        'decode_attempts':len(attempted),'pending_roots':len(set(todo)-attempted),'budget_exhausted':bool(set(todo)-attempted),
        'overlapping_instruction_starts':sorted(overlap),'unresolved':issues,'arm_frontiers':frontiers,
        'unresolved_indirect_stores':unresolved_stores,
        'qualification':'bounded static linear-ROM candidate; no runtime register, banking, peripheral or scene-state inference'}
