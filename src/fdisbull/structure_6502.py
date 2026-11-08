"""Read-only 6502 fact producer for the retained fDisBull pattern matcher.

Source fact producer, not an emulator. A caller must
provide a qualified, fixed CPU-to-file mapping and entry addresses. No game
names, menu offsets, input bit meanings or scene identifiers occur in this file.
Mapping-changing writes and unresolved indirect transfers stop traversal.
"""
from __future__ import annotations
from collections import Counter, deque
from hashlib import sha256
import json

# Official 6502 writes. Indirect destinations may reach mapper space.
STORES = {'sta', 'stx', 'sty', 'inc', 'dec', 'asl', 'lsr', 'rol', 'ror'}
BRANCHES = {'beq', 'bne', 'bcc', 'bcs', 'bmi', 'bpl', 'bvc', 'bvs'}
PREPARATION = {'lda','ldx','ldy','tax','tay','txa','tya','inx','iny','dex','dey',
               'and','ora','eor','clc','sec','cld','sed','nop'}


def probe(data: bytes, windows: list[dict], entries: list[int], *,
          mapping_id: str, budget: int = 12000, max_arm: int = 12, mapper: int | None = None) -> dict:
    """Return source-bound facts; caller-supplied maps are not authenticated here.

    Each window is {cpu_start, file_start, size}. Code roots are also caller
    supplied. Branch/call traversal is potential reachability, not execution.
    Calls are barriers to local value/flag propagation, but their target and
    return continuation are independent discovery roots. No indirect call or
    jump is guessed, and possible mapper writes stop even if the stored value
    happens to equal an earlier value.
    """
    import capstone as cs
    from capstone.mos65xx import MOS65XX_OP_MEM, MOS65XX_OP_IMM
    if not isinstance(data, bytes) or not data or len(data) > 64*1024*1024:
        raise ValueError('require a nonempty bounded byte source')
    if not isinstance(mapping_id,str) or not mapping_id or len(mapping_id)>200 or type(budget) is not int or not 1 <= budget <= 100000:
        raise ValueError('require mapping identity and bounded budget')
    if type(max_arm) is not int or not 1 <= max_arm <= 64:
        raise ValueError('invalid arm bound')
    if mapper is not None and (type(mapper) is not int or mapper not in (0,66,227)):
        raise ValueError('unsupported mapper profile')
    if not windows or len(windows)>64 or not entries or len(entries)>256:
        raise ValueError('invalid mapping/entry budget')
    for w in windows:
        if set(w) != {'cpu_start','file_start','size'} or any(type(x) is not int for x in w.values()):
            raise ValueError('invalid window')
        if not 0 <= w['cpu_start'] < 65536 or w['size']<=0 or w['cpu_start']+w['size']>65536:
            raise ValueError('invalid CPU window')
        if w['file_start']<0 or w['file_start']+w['size']>len(data):
            raise ValueError('invalid file window')
    ordered=sorted(windows,key=lambda x:x['cpu_start'])
    if any(a['cpu_start']+a['size']>b['cpu_start'] for a,b in zip(ordered,ordered[1:])):
        raise ValueError('overlapping CPU mapping')
    def offset(a):
        for w in ordered:
            if w['cpu_start']<=a<w['cpu_start']+w['size']:
                return w['file_start']+a-w['cpu_start']
        return None
    if any(type(a) is not int or offset(a) is None for a in entries):
        raise ValueError('entry outside mapping')
    digest=sha256(data).hexdigest()
    map_hash=sha256(json.dumps(ordered,sort_keys=True).encode()).hexdigest()
    space=f'nes6502:{digest}:map:{mapping_id}:{map_hash}'
    decoder=cs.Cs(cs.CS_ARCH_MOS65XX,cs.CS_MODE_MOS65XX_6502)
    decoder.detail=True
    rows={}; incoming={}; todo=deque(sorted(set(entries))); issues=[]
    for e in entries:incoming.setdefault(e,set()).add(('entry',e))
    def add(src,dst):
        incoming.setdefault(dst,set()).add(('edge',src))
        if dst not in rows:todo.append(dst)
    def write(i):
        return i.mnemonic in STORES and i.operands and i.operands[0].type==MOS65XX_OP_MEM
    def barrier(i):
        if not write(i) or mapper==0:return False
        # Indexed low-memory windows are safe only when all possible 8-bit
        # index values stay below mapper space. Indirect pointers stay unknown.
        if '(' in i.op_str:return True
        return i.operands[0].mem+(255 if ',' in i.op_str else 0)>=(0x5000 if mapper==227 else 0x8000)
    while todo and len(rows)<budget:
        a=todo.popleft()
        if a in rows:continue
        off=offset(a)
        if off is None:
            issues.append({'address':a,'reason':'unmapped target'});continue
        raw=[]
        for k in range(3):
            p=offset(a+k)
            if p is None or p!=off+k:break
            raw.append(data[p])
        i=next(decoder.disasm(bytes(raw),a,count=1),None)
        if i is None:
            issues.append({'address':a,'reason':'unsupported/truncated instruction'});continue
        rows[a]=i;nxt=a+i.size
        if barrier(i):
            issues.append({'address':a,'reason':'possible mapper write; mapping continuation unresolved'});continue
        if i.mnemonic in BRANCHES:
            add(a,int(i.operands[0].mem)&65535);add(a,nxt)
        elif i.mnemonic=='jmp':
            if i.bytes[0]==0x4c:add(a,int(i.operands[0].mem))
            else:issues.append({'address':a,'reason':'indirect jump unresolved'})
        elif i.mnemonic=='jsr':
            add(a,int(i.operands[0].mem));add(a,nxt)
        elif i.mnemonic in ('rts','rti','brk'):
            pass
        elif nxt<=65535:add(a,nxt)
        else:issues.append({'address':a,'reason':'program counter wrap boundary'})
    overlap=set();occupied={}
    for a,i in sorted(rows.items()):
        for k in range(a,a+i.size):
            if k in occupied and occupied[k]!=a:overlap.update((a,occupied[k]))
            occupied[k]=a
    def evidence(i):
        off=offset(i.address)
        return {'space':space,'source_sha256':digest,'cpu_address':i.address,
                'file_offset':off,'size':i.size,'instruction_sha256':sha256(bytes(i.bytes)).hexdigest(),
                'mapping_id':mapping_id,'mnemonic':i.mnemonic,'operand_text':i.op_str}
    def unique(a):return a in rows and a not in overlap and len(incoming.get(a,set()))==1
    nodes=[];edges=[];frontiers=[];accesses=[]
    for a,i in sorted(rows.items()):
        if a in overlap:continue
        if i.operands and i.operands[0].type==MOS65XX_OP_MEM and '(' not in i.op_str and ',' not in i.op_str:
            address=int(i.operands[0].mem)
            role=('write' if write(i) else 'read' if i.mnemonic in ('lda','ldx','ldy','cmp','cpx','cpy','and','ora','eor','bit','adc','sbc') else None)
            if role:
                ev=evidence(i)
                if address<0x2000:
                    storage={'space':'nes-work-ram','address':address & 0x7ff,'width':8,'scope':space}
                    domain='state'
                else:
                    storage={'space':'nes-cpu-bus','address':address,'width':8,'scope':space}
                    domain=('device' if address<0x6000 else 'unresolved')
                accesses.append({'id':space+':access:'+str(a),'kind':role,'storage':storage,'evidence':ev,'domain':domain})
        n=rows.get(a+i.size)
        # Exact value->predicate connection, with no intervening instruction.
        if i.mnemonic=='lda' and i.operands[0].type==MOS65XX_OP_MEM and n and unique(n.address) and n.mnemonic=='and' and n.operands[0].type==MOS65XX_OP_IMM:
            g=rows.get(n.address+n.size)
            if g and unique(g.address) and g.mnemonic in ('beq','bne'):
                prefix=f'{space}:{a}:mask'
                r={'id':prefix+':read','role':'read','evidence':evidence(i),'expression':i.op_str}
                m={'id':prefix+':mask','role':'mask','evidence':evidence(n),'value':int(n.operands[0].imm)}
                gate={'id':prefix+':gate','role':'branch','evidence':evidence(g),'condition':g.mnemonic}
                nodes.extend((r,m,gate));edges.extend(((r['id'],m['id'],'value'),(m['id'],gate['id'],'predicate')))
        if i.mnemonic not in ('cmp','cpx','cpy') or not i.operands or i.operands[0].type!=MOS65XX_OP_IMM:continue
        if n is None or not unique(n.address) or n.mnemonic not in ('beq','bne'):continue
        prefix=f'{space}:{a}:selector'
        s={'id':prefix+':test','role':'selector_test','evidence':evidence(i),'register':{'cmp':'a','cpx':'x','cpy':'y'}[i.mnemonic],'value':int(i.operands[0].imm),'width':8}
        g={'id':prefix+':gate','role':'branch','evidence':evidence(n),'condition':n.mnemonic}
        nodes.extend((s,g));edges.append((s['id'],g['id'],'predicate'))
        if i.mnemonic=='cmp':
            prior=list(incoming.get(a,()))
            comb=rows.get(prior[0][1]) if len(prior)==1 and prior[0][0]=='edge' else None
            if comb and comb.mnemonic in ('ora','and','eor') and comb.operands and comb.operands[0].type==MOS65XX_OP_MEM and unique(comb.address):
                prec=list(incoming.get(comb.address,()))
                load=rows.get(prec[0][1]) if len(prec)==1 and prec[0][0]=='edge' else None
                if load and load.mnemonic=='lda' and load.operands[0].type==MOS65XX_OP_MEM and load.address not in overlap:
                    l={'id':prefix+':left','role':'read','evidence':evidence(load),'expression':load.op_str}
                    r={'id':prefix+':right','role':'read','evidence':evidence(comb),'expression':comb.op_str}
                    c={'id':prefix+':combine','role':'bit_combine','evidence':evidence(comb),'operation':comb.mnemonic,'width':8}
                    nodes.extend((l,r,c));edges.extend(((l['id'],c['id'],'left_value'),(r['id'],c['id'],'right_value'),(c['id'],s['id'],'value')))

        for arm,start in [('taken',int(n.operands[0].mem)),('fallthrough',n.address+n.size)]:
            at=start;seen=set();path=[];reason='arm budget'
            for _ in range(max_arm):
                if at in seen:reason='arm loop';break
                seen.add(at)
                if not unique(at):reason='join, missing decode or overlapping code';break
                j=rows[at];path.append(evidence(j));operation=None
                if j.mnemonic=='jsr':operation='call'
                elif j.mnemonic in ('rts','rti'):operation='return'
                elif write(j):operation='memory_write'
                if operation:
                    e={'id':prefix+':'+arm,'role':'effect','evidence':evidence(j),
                       'operation':operation,'path_witness':path,
                       'selector_relation':'equal' if (arm=='taken')==(n.mnemonic=='beq') else 'not_equal',
                       'mapping_boundary':barrier(j),'storage_or_callee_role':'unresolved'}
                    nodes.append(e);edges.append((g['id'],e['id'],'controls'));reason=None;break
                if j.mnemonic=='jmp' and j.bytes[0]==0x4c:at=int(j.operands[0].mem);continue
                if j.mnemonic not in PREPARATION:reason='opaque operation or nested branch';break
                at=j.address+j.size
            if reason:frontiers.append({'selector':a,'arm':arm,'reason':reason})
    return {'nodes':nodes,'edges':edges,'source_sha256':digest,'mapping_id':mapping_id,
            'decoded_candidate_instructions':len(rows),'overlapping_starts':len(overlap),
            'instruction_budget_exhausted':bool(todo),'issues':issues,'arm_frontiers':frontiers,
            'accesses':accesses,'runtime_observed':False,'mapping_provenance':'caller-qualified; not inferred by producer'}
