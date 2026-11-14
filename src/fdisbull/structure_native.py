"""Bounded native source views and local data-flow facts, not runtime execution.

Uses the existing native decoder, with Capstone operand details. Unsupported
relocations stay explicitly unapplied in source-object views. No title-specific
addresses, item names, schema widths or semantic field names occur here.
"""
from __future__ import annotations
from collections import deque,Counter
from hashlib import sha256
import struct
from .decoder import decode


def exepack_candidates(data):
    """Recognize bounded 18-byte EXEPACK streams, including embedded headers.

    This returns a derived data view, not an executable/rebuilt MZ. Embedded
    headers are candidates even when all stream boundaries check. The original
    entry may reach additional wrappers. Relocations are not applied.
    Format: https://www.bamsoftware.com/software/exepack/
    """
    if data[:2]!=b'MZ' or len(data)<32:return []
    start=int.from_bytes(data[8:10],'little')*16
    if not 28<=start<len(data):return []
    out=[];pos=start;headers_tried=0
    while len(out)<4 and headers_tried<64:
        sig=data.find(b'RB\x8c\xc0\x05\x10\x00\x0e\x1f',pos)
        if sig<0:break
        pos=sig+2;header=sig-16;headers_tried+=1
        if header<start or (header-start)%16:continue
        h=struct.unpack_from('<9H',data,header)
        ip,cs,_,packed,sp,ss,paragraphs,skip,_=h
        size=paragraphs*16
        if skip!=1 or not 18<=packed<=4096 or header+packed>len(data) or not 1<=size<=2**20:continue
        compressed=header-start-(skip-1)*16;end=size-(skip-1)*16
        if not 0<compressed<=header-start<=size or compressed>end:continue
        buf=bytearray(size);buf[:header-start]=data[start:header]
        src=compressed;dst=end;steps=0
        try:
            while src>0 and buf[src-1]==255:src-=1
            while True:
                if src<3 or steps>=65536:raise ValueError('truncated/budgeted stream')
                cmd=buf[src-1];count=int.from_bytes(buf[src-3:src-1],'little');src-=3;steps+=1
                if not count or count>dst:raise ValueError('bad run extent')
                if cmd&254==176:
                    if src<1:raise ValueError('missing fill byte')
                    src-=1;buf[dst-count:dst]=bytes([buf[src]])*count;dst-=count
                elif cmd&254==178:
                    if count>src:raise ValueError('literal underflow')
                    buf[dst-count:dst]=buf[src-count:src];src-=count;dst-=count
                else:raise ValueError('bad opcode')
                if dst<src:raise ValueError('output overlaps unread prefix')
                if cmd&1:break
            if src!=dst:raise ValueError('unexplained prefix displacement')
            if not 0<=cs*16+ip<size:raise ValueError('entry outside view')
        except ValueError:continue
        out.append({'kind':'exepack-derived','bytes':bytes(buf),'bits':16,'base':0,'entry':cs*16+ip,
                    'entry_cs':cs,'entry_ip':ip,'sha256':sha256(buf).hexdigest(),
                    'source_header':header,'stream_records':steps,'prefix_bytes':src,
                    'qualification':'validated reverse-RLE stream; wrapper entry and relocation effects not qualified',
                    'file_mapping':None})
    return out


def le_source_views(data):
    """Read valid LE pages as object-relative source bytes, never a loaded image.

    The production loader may refuse selector fixups. This inspection layer
    deliberately does NOT apply fixups, resolve absolute references, or publish
    a loadable image. Relative edges within the same object remain useful.
    """
    from .image_views import secondary_header
    from .le import _HEADER_FIELDS
    s=secondary_header(data)
    if not s or s['format']!='LE':return []
    off=s['header_offset']
    if off+196>len(data) or data[off+2:off+8]!=b'\0'*6:raise ValueError('unsupported LE header')
    f=dict(zip(_HEADER_FIELDS,struct.unpack_from('<41I',data,off+12)))
    if not 1<=f['object_count']<=64 or not 1<=f['num_pages']<=16384 or f['page_size']!=4096:
        raise ValueError('LE page/object budget or page size')
    ot=off+f['object_table_offset'];pt=off+f['page_map_offset'];pg=f['data_pages_offset']
    if not 1<=f['start_obj']<=f['object_count']:
        raise ValueError('LE entry object outside directory')
    if min(ot,pt)<off+196 or ot+24*f['object_count']>len(data) or pt+4*f['num_pages']>len(data):raise ValueError('LE table bounds')
    page_rows=[data[pt+4*i:pt+4*i+4] for i in range(f['num_pages'])]
    last=max([int.from_bytes(p[:3],'big') for p in page_rows if p[3]==0],default=0)
    out=[];total=0;owned=set()
    for i in range(f['object_count']):
        size,base,flags,first,n,reserved=struct.unpack_from('<6I',data,ot+24*i)
        total+=size
        if not size or total>16*1024*1024 or n>(size+4095)//4096 or first<1 or first+n-1>len(page_rows):raise ValueError('LE object extent/profile')
        buf=bytearray(size);maps=[]
        for j in range(n):
            logical=first+j-1
            if logical in owned:raise ValueError('shared LE pages')
            owned.add(logical);p=page_rows[logical];num=int.from_bytes(p[:3],'big')
            if p[3]==3 and num==0:continue
            if p[3]!=0 or not 1<=num<=f['num_pages']:raise ValueError('unsupported LE page')
            length=f['last_page_size'] if num==last else 4096
            at=pg+(num-1)*4096
            if not 1<=length<=4096 or at<0 or at+length>len(data):raise ValueError('LE physical page bounds')
            take=min(length,size-j*4096);buf[j*4096:j*4096+take]=data[at:at+take]
            maps.append({'view_offset':j*4096,'file_offset':at,'size':take})
        if f['start_obj']==i+1 and not 0<=f['eip']<size:
            raise ValueError('LE entry offset outside object')
        if flags&4:
            out.append({'kind':'le-unrelocated-object','bytes':bytes(buf),'bits':32 if flags&0x2000 else 16,'base':base,
                        'entry':f['eip'] if f['start_obj']==i+1 and flags&0x2000 else None,
                        'declared_entry':f['eip'] if f['start_obj']==i+1 else None,
                        'analysis_entry_admitted':bool(f['start_obj']==i+1 and flags&0x2000),
                        'object':i+1,'file_mapping':maps,
                        'qualification':'object source bytes; fixups unapplied; no absolute target resolution; 16-bit LE selector entries are not traversed as real-mode code',
                        'sha256':sha256(buf).hexdigest()})
    return out


def embedded_le_views(data, *, max_candidates=64):
    """Find bounded, structurally checked nested MZ->LE envelopes in an MZ tail.

    The nested header supplies its own offset origin. Preserve absolute source
    locations without patching e_lfanew or pretending the wrapper was executed.
    Byte magic alone is insufficient; full admitted object/page checks must pass.
    """
    from .image_views import secondary_header
    if type(max_candidates) is not int or not 1<=max_candidates<=256:raise ValueError('candidate budget')
    if len(data)<28 or data[:2]!=b'MZ':return [],[]
    h=struct.unpack_from('<14H',data)
    tail=h[2]*512 if h[1]==0 else (h[2]-1)*512+h[1]
    if not 28<=h[4]*16<=tail<=len(data):return [],[]
    pos=tail;out=[];notes=[];attempts=0
    while attempts<max_candidates:
        off=data.find(b'MZ',pos)
        if off<0:break
        pos=off+2;attempts+=1;child=data[off:]
        if len(child)<64:continue
        c=struct.unpack_from('<14H',child);end=c[2]*512 if c[1]==0 else (c[2]-1)*512+c[1]
        if not c[2] or c[1]>=512 or not 64<=c[4]*16<=end<=len(child):continue
        if c[3] and (c[12]<28 or c[12]+4*c[3]>c[4]*16):continue
        sec=secondary_header(child)
        if not sec or sec['format']!='LE' or sec['header_offset']<end:continue
        try:views=le_source_views(child)
        except ValueError as exc:
            notes.append(f'nested LE at file {off}: {exc}');continue
        for v in views:
            v['source_envelope_offset']=off;v['le_header_offset']=off+sec['header_offset']
            v['kind']='embedded-le-unrelocated-object'
            for m in v['file_mapping']:m['file_offset']+=off
            out.append(v)
        if len(out)>=32:
            notes.append('embedded object-view budget');break
    if attempts>=max_candidates and data.find(b'MZ',pos)>=0:notes.append('embedded-header candidate budget')
    return out,notes


def native_views(data):
    if data[:2]!=b'MZ':return [],[]
    from .image_views import secondary_header
    secondary=secondary_header(data)
    if secondary:
        if secondary['format']=='LE':return le_source_views(data),['LE source-object analysis is unrelocated; production loader acceptance is separate.']
        return [],[f"{secondary['format']} native producer not selected in this DOS pilot"]
    packed=exepack_candidates(data)
    if packed:return packed,['Packed stream reconstructed as read-only data; original wrapper execution not observed.']
    if b'RB\x8c\xc0\x05\x10\x00\x0e\x1f' in data:
        return [],['EXEPACK signature found but admitted 18-byte/skip=1 reverse-RLE profile did not validate.']
    if len(data)<28:return [],['Truncated MZ']
    hdr=struct.unpack_from('<14H',data)
    end=hdr[2]*512 if hdr[1]==0 else (hdr[2]-1)*512+hdr[1];start=hdr[4]*16
    if not 28<=start<end<=len(data):return [],['Invalid MZ extents']
    nested,notes=embedded_le_views(data)
    if nested:notes.append('Nested MZ/LE envelopes found in retained tail; wrapper execution and fixups not inferred. 16-bit LE entry traversal remains unsupported.')
    return [{'kind':'mz-unrelocated','bytes':data[start:end],'bits':16,'base':0,
             'entry':hdr[11]*16+hdr[10],'entry_cs':hdr[11],'entry_ip':hdr[10],
             'file_mapping':[{'view_offset':0,'file_offset':start,'size':end-start}],
             'qualification':'unrelocated MZ source; segmented data references remain symbolic',
             'sha256':sha256(data[start:end]).hexdigest()}]+nested,notes


def native_facts(view, source, *, max_instructions=30000, candidate_functions=False):
    import capstone as cs
    from capstone.x86 import X86_OP_REG,X86_OP_MEM,X86_OP_IMM
    if view['entry'] is None:return [],[],{'instructions':0,'pending':0,'issues':['no entry seed']}
    data=view['bytes'];bits=view['bits'];base=view['base']
    cap=cs.Cs(cs.CS_ARCH_X86,cs.CS_MODE_16 if bits==16 else cs.CS_MODE_32);cap.detail=True
    roots=[(view.get('entry_cs',0),view.get('entry_ip',view['entry']))]
    if candidate_functions:
        # Heuristic function-entry seeds broaden the shortlist, not reachability.
        signatures=(b'\x55\x8b\xec', b'\x55\x89\xe5')
        for signature in signatures:
            start=0
            for _ in range(4096):
                at=data.find(signature,start)
                if at<0:break
                if bits==32 or at<65536:roots.append((0,at))
                start=at+1
    todo=deque(sorted(set(roots)));seen=set();rows={};issues=[];edges=[];nodes=[];attempts=0
    # Keys retain CS for near 16-bit branches. 32-bit keys are object offsets.
    while todo and attempts<max_instructions:
        seg,pc=todo.popleft();key=(seg,pc)
        if key in seen:continue
        seen.add(key);at=seg*16+pc if bits==16 else pc
        if not 0<=at<len(data):continue
        ip=pc if bits==16 else base+pc
        ins=next(cap.disasm(data[at:at+15],ip,count=1),None);attempts+=1
        if ins is None:issues.append({'offset':at,'error':'decode'});continue
        row={'ins':ins,'at':at,'key':key,'next':(seg,(pc+ins.size)&65535 if bits==16 else pc+ins.size)}
        rows[key]=row
        branches=[]
        if ins.mnemonic in ('ret','retf','iret','iretd','hlt','int3','ud2'):continue
        if ins.group(cs.CS_GRP_JUMP) or ins.group(cs.CS_GRP_CALL):
            if len(ins.operands)==1 and ins.operands[0].type==X86_OP_IMM:
                dest=ins.operands[0].imm
                branches.append((seg,dest&65535 if bits==16 else dest-base))
            elif len(ins.operands)==2 and bits==16 and all(o.type==X86_OP_IMM for o in ins.operands):
                # Segment relocation not reconstructed: retain unresolved far edge.
                issues.append({'offset':at,'error':'unresolved far transfer'})
            else:issues.append({'offset':at,'error':'indirect transfer'})
            if ins.mnemonic not in ('jmp','ljmp'):branches.append(row['next'])
        else:branches.append(row['next'])
        todo.extend(x for x in branches if x not in seen)
    # Only local, source-adjacent, single-entry chains. Calls and branches
    # are barriers to value propagation. No cross-call alias assumptions.
    predecessors=Counter(); previous={}
    for k,r in rows.items():
        if r['ins'].mnemonic not in ('jmp','ljmp','ret','retf','hlt','int3'):
            predecessors[r['next']]+=1;previous.setdefault(r['next'],[]).append(r)
        for o in r['ins'].operands:
            if o.type==X86_OP_IMM and (r['ins'].group(cs.CS_GRP_JUMP) or r['ins'].group(cs.CS_GRP_CALL)):
                predecessors[(k[0],o.imm&65535 if bits==16 else o.imm-base)]+=1
    space=source['sha256']+':'+view['kind']+':'+str(view.get('object',0))
    def evidence(r):
        at=r['at'];end=at+r['ins'].size
        ev={'source_sha256':source['sha256'],'view_sha256':view['sha256'],
            'space':space,'offset':at,'size':end-at}
        for m in view.get('file_mapping') or []:
            if m['view_offset']<=at and end<=m['view_offset']+m['size']:
                ev['file_offset']=m['file_offset']+at-m['view_offset'];break
        return ev
    def mem(o,ins):
        m=o.mem
        return {'segment':ins.reg_name(m.segment) or 'default','base':ins.reg_name(m.base),
                'index':ins.reg_name(m.index),'scale':m.scale,'displacement':m.disp,'width':o.size,
                'resolved_absolute':False,'address_bits':bits}
    consumed=set();match_sites=0
    for k,r in sorted(rows.items(),key=lambda kv:kv[1]['at']):
        ins=r['ins'];name=ins.mnemonic
        if name not in ('test','and') or len(ins.operands)!=2:continue
        # Direct memory test, or one immediately preceding MOV feeds this test.
        left,right=ins.operands;load=None;field=None
        if left.type==X86_OP_MEM:load=r;field=mem(left,ins)
        elif left.type==X86_OP_REG:
            prior=[q for q in previous.get(k,[]) if q['ins'].mnemonic in ('mov','movzx','movsx')]
            if len(prior)==1 and predecessors[k]==1:
                q=prior[0];op=q['ins'].operands
                if len(op)==2 and op[0].type==X86_OP_REG and op[0].reg==left.reg and op[1].type==X86_OP_MEM:
                    load=q;field=mem(op[1],q['ins'])
        if right.type==X86_OP_MEM:
            # The mask's other input can itself be the table read of interest.
            load=r;field=mem(right,ins)
        if load is None or right.type not in (X86_OP_IMM,X86_OP_REG,X86_OP_MEM):continue
        # Self tests and all-bits immediates are mere zero tests, not selective masks.
        if right.type==X86_OP_REG and left.type==X86_OP_REG and right.reg==left.reg:continue
        if right.type==X86_OP_IMM and right.imm & ((1<<(8*left.size))-1) in (0,(1<<(8*left.size))-1):continue
        # A TEST checks bits. AND changes its destination; retain that effect.
        nxt=rows.get(r['next'])
        intermediate=None
        if nxt and nxt['ins'].mnemonic=='cmp' and predecessors[r['next']]==1 and name=='and' and left.type==X86_OP_REG:
            operands=nxt['ins'].operands
            if len(operands)==2 and operands[0].type==X86_OP_REG and operands[0].reg==left.reg and operands[1].type==X86_OP_IMM and operands[1].imm==0:
                intermediate=nxt;nxt=rows.get(nxt['next'])
        if nxt is None or predecessors[nxt['key']]!=1 or nxt['ins'].mnemonic not in ('je','jne','jz','jnz'):continue
        checked=[load,r,nxt]+([intermediate] if intermediate else [])
        if any((d:=decode(data[q['at']:q['at']+15],q['ins'].address,'x86',bits)) is None or d['size']!=q['ins'].size for q in checked):
            issues.append({'offset':r['at'],'error':'decoder disagreement'});continue
        prefix=space+':'+str(r['at']);subject=field
        read={'id':prefix+':read','role':'read','subject':subject,'field':field,'evidence':evidence(load)}
        mask={'id':prefix+':mask','role':'mask','subject':subject,'operation':name,
              'mask':right.imm if right.type==X86_OP_IMM else {'runtime_operand':ins.op_str},
              'writes_destination':name=='and','evidence':evidence(r),
              'operand_text':ins.op_str,'zero_comparison':evidence(intermediate) if intermediate else None}
        gate={'id':prefix+':gate','role':'branch','test':'zero' if nxt['ins'].mnemonic in ('je','jz') else 'nonzero',
              'target':nxt['ins'].operands[0].imm,'fallthrough':nxt['ins'].address+nxt['ins'].size,
              'evidence':evidence(nxt),'scope':view['qualification']}
        nodes.extend((read,mask,gate));edges.extend(((read['id'],mask['id'],'value'),(mask['id'],gate['id'],'predicate')))
        if field['index'] and field['base'] not in ('bp','ebp','esp','sp'):
            indexed={**read,'id':prefix+':indexed','role':'indexed_read'};nodes.append(indexed);edges.append((indexed['id'],gate['id'],'predicate'))
        match_sites+=1
    from .structure_events import selector_facts
    en,ee,ec=selector_facts(rows,predecessors,evidence,mem,bits=bits,base=base)
    nodes.extend(en);edges.extend(ee)
    accesses=[]
    for _,row in sorted(rows.items(),key=lambda kv:kv[1]['at']):
        ins=row['ins']; operands=ins.operands
        if ins.mnemonic not in ('mov','movzx','movsx','cmp','test','and','or','xor','add','sub','inc','dec'):continue
        for oi,operand in enumerate(operands):
            if operand.type!=X86_OP_MEM or operand.mem.base or operand.mem.index:continue
            f=mem(operand,ins)
            # This is a symbolic effective-address expression. Live DS/SS and
            # relocations are not established, so it is never a concrete alias.
            role='write' if oi==0 and ins.mnemonic not in ('cmp','test') else 'read'
            accesses.append({'id':space+':memory:'+str(row['at'])+':'+str(oi),
                'kind':role,'storage':{'space':'x86-symbolic-'+f['segment'],'scope':space,
                'address':f['displacement']&((1<<bits)-1),'width':f['width']*8},
                'domain':'symbolic-state','evidence':evidence(row)})
    return nodes,edges,{'memory_accesses':accesses,'event_candidates':ec,'instructions':len(rows),'decode_attempts':attempts,'pending':len(todo),
                        'instruction_budget_exhausted':bool(todo),'mask_sites':match_sites,
                        'issues':issues[:50],'issue_count':len(issues),'runtime_observed':False,
                        'qualification':view['qualification'],'candidate_function_seeds':len(roots)-1,
                        'code_entry_qualification':'static decoded candidates; original execution/reachability not proven'}
