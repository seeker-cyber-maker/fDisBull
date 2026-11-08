"""Format-level fact producers for existing AGI IR and raw Z3/Z5 stories.

No target names or hand-labelled game fields are used. The Z5 reader is a
bounded research producer, not a registered processor, VM or semantic lifter.
Reference: https://inform-fiction.org/zmachine/standards/z1point1/
"""
from __future__ import annotations
from collections import Counter, deque
from hashlib import sha256
from . import zmachine


def agi_facts(census, *, max_effects_per_guard=16):
    """Join decoded said groups and literal identities to short true arms.

    Full ordered conditions are retained. A said term can be negated or part
    of OR; an edge means participation in the condition, not that the term is
    sufficient or required. Joins, calls, and further conditionals are barriers.
    """
    nodes=[];edges=[];guards=effects=0
    groups={g['number']:g for g in census.get('vocabulary',{}).get('groups',[])}
    for logic in census['logics']:
        rows=logic.get('ir',{}).get('instructions',[])
        by={i['offset']:i for i in rows};pred=Counter()
        for i in rows:
            for s in i.get('successors',[]):
                if type(s.get('offset')) is int:pred[s['offset']]+=1
        src=logic['source'];prefix=src['sha256']+':logic:'+str(logic['logic'])
        def ev(i):
            return {'source_sha256':src['sha256'],'space':prefix,
                    'offset':i['offset'],'size':i['end_offset']-i['offset'],
                    'volume':src['volume'],'resource_offset':src['offset'],
                    'coordinate_system':'AGI payload, including two-byte code length'}
        for i in rows:
            cond=i.get('conditions',[])
            if i['operation']!='if' or not cond:continue
            gate={'id':prefix+':'+str(i['offset'])+':gate','role':'branch','evidence':ev(i),
                  'ordered_conditions':cond,'successors':i['successors'],
                  'entry_reachability':'not established'}
            causes=[]
            for n,c in enumerate(cond):
                op=c.get('operation');args=c.get('operands',[])
                if op=='said':
                    ids=c.get('word_groups')
                    if ids is None:ids=[int.from_bytes(bytes(args[k:k+2]),'little') for k in range(1,len(args),2)]
                    cause={'id':gate['id']+':words:'+str(n),'role':'word_pattern',
                           'groups':ids,'dictionary_bindings':[groups.get(k,{'number':k,'unresolved':True}) for k in ids],
                           'evidence':{**ev(i),'condition_offset':c.get('offset')}}
                    causes.append(cause)
                elif op in ('isset','has','obj.in.room') and args:
                    cause={'id':gate['id']+':test:'+str(n),'role':'entity_test',
                           'subject':('flag:' if op=='isset' else 'inventory-object:')+str(args[0]),
                           'operation':op,'operands':args,'evidence':{**ev(i),'condition_offset':c.get('offset')}}
                    causes.append(cause)
            if not causes:continue
            nodes.append(gate);nodes.extend(causes);guards+=1
            edges.extend((c['id'],gate['id'],'predicate') for c in causes)
            target=next((s.get('offset') for s in i['successors'] if s['kind']=='true'),None)
            visited=set()
            for _ in range(max_effects_per_guard):
                if target not in by or target in visited or pred[target]!=1:break
                visited.add(target);r=by[target];op=r['operation'];args=r['operands']
                if op in ('if','goto','return','call','call.v'):break
                subject=None
                if args and op in ('set','reset','toggle'):subject='flag:'+str(args[0])
                if args and op in ('get','drop','put'):subject='inventory-object:'+str(args[0])
                effect={'id':gate['id']+':effect:'+str(target),'role':'effect','operation':op,
                        'subject':subject,'operands':args,'evidence':ev(r)}
                nodes.append(effect);edges.append((gate['id'],effect['id'],'controls'));effects+=1
                # Blocking/unknown host actions may not return to the next statement.
                # Only explicit scalar assignments and flag operations extend the arm.
                if op not in ('assignn','assignv','increment','decrement','addn','addv','subn','subv','set','reset','toggle'):break
                successors=r.get('successors',[])
                if len(successors)!=1 or successors[0]['kind']!='fallthrough':break
                target=successors[0]['offset']
    return nodes,edges,{'condition_groups':guards,'guarded_effects':effects,
                        'scope':'short single-entry true arms; nested control and cross-call effects not inferred'}


def z_catalog(data):
    """Strict bounded dictionary and a validated candidate object-directory extent."""
    if not isinstance(data,bytes) or not 64<=len(data)<=2*1024*1024 or data[0] not in (3,5):
        raise ValueError('not an admitted Z3/Z5 story')
    v=data[0];word=lambda o:int.from_bytes(data[o:o+2],'big')
    length=word(26)*(2 if v==3 else 4);static=word(14);high=word(4)
    if not 64<=static<=high<length<=len(data) or length>(131072 if v==3 else 262144):raise ValueError('story extent/header')
    if not 64<=word(6)<length or not 64<=word(12)<=static-480:raise ValueError('entry/globals bounds')
    if (sum(data[64:length])&65535)!=word(28):raise ValueError('story checksum mismatch')
    d=word(8)
    if not static<=d<length:raise ValueError('dictionary out of static memory')
    at=d+1+data[d]
    if at+3>length:raise ValueError('dictionary header')
    width=data[at];count=int.from_bytes(data[at+1:at+3],'big',signed=True);enc=4 if v==3 else 6
    if count<0 or width<enc or at+3+count*width>length:raise ValueError('standard dictionary extent/order profile')
    default_alphabet=v==3 or word(52)==0
    words=[];previous=None
    for i in range(count):
        pos=at+3+i*width;encoded=data[pos:pos+enc]
        if previous is not None and encoded<=previous:raise ValueError('dictionary not strictly ordered')
        if not int.from_bytes(encoded[-2:],'big')&32768:raise ValueError('dictionary text not terminated')
        previous=encoded;label=None
        if default_alphabet:
            try:
                label,end=zmachine.decode_ztext(data,pos,max_chars=100)
                if end!=pos+enc:label=None
            except (ValueError,IndexError):pass
        words.append({'offset':pos,'text':label,'metadata_offset':pos+enc,'metadata_bytes':width-enc})
    obj=word(10);defaults=62 if v==3 else 126;stride=9 if v==3 else 14
    first=obj+defaults;boundary=static;rows=[];issues=[]
    if not 64<=obj or first>static:raise ValueError('object defaults')
    limit=min(255 if v==3 else 4096,(static-first)//stride)
    for idx in range(limit):
        pos=first+idx*stride
        if pos>=boundary:break
        if pos+stride>boundary:issues.append('partial inferred object row');break
        prop=word(pos+stride-2)
        if not first+stride<=prop<static:issues.append('invalid property pointer');break
        boundary=min(boundary,prop)
        if v==3:
            attrs=int.from_bytes(data[pos:pos+4],'big');parent,sibling,child=data[pos+4:pos+7]
        else:
            attrs=int.from_bytes(data[pos:pos+6],'big');parent,sibling,child=(word(pos+k) for k in (6,8,10))
        name_bytes=data[prop]*2;cursor=prop+1+name_bytes
        if cursor>static:issues.append('object short-name extent');break
        name=None
        if name_bytes and default_alphabet:
            try:
                name,end=zmachine.decode_ztext(data,prop+1,max_chars=512)
                if end!=cursor:name=None
            except (ValueError,IndexError):pass
        properties=[];last=64 if v==5 else 32
        for _ in range(64):
            if cursor>=static:issues.append('truncated property list');break
            header=data[cursor];cursor+=1
            if header==0:break
            if v==3:ident=header&31;size=(header>>5)+1
            else:
                ident=header&63
                if header&128:
                    if cursor>=static:issues.append('truncated property size');break
                    size=data[cursor]&63;size=size or 64;cursor+=1
                else:size=2 if header&64 else 1
            if ident==0 or ident>=last or cursor+size>static:issues.append('property order/extent');break
            properties.append({'number':ident,'offset':cursor,'size':size});cursor+=size;last=ident
        rows.append({'id':idx+1,'offset':pos,'width':stride,'attributes':attrs,'parent':parent,
                     'sibling':sibling,'child':child,'properties_offset':prop,'name':name,'properties':properties})
    if first+len(rows)*stride!=boundary:issues.append('object extent does not close exactly at first property table')
    if any(r[k]>len(rows) for r in rows for k in ('parent','sibling','child')):issues.append('object link outside inferred population')
    for r in rows:
        chain=set();p=r['id']
        while p and p<=len(rows):
            if p in chain:issues.append('parent cycle');break
            chain.add(p);p=rows[p-1]['parent']
    return {'version':v,'sha256':sha256(data).hexdigest(),'declared_bytes':length,'trailing_bytes':len(data)-length,
            'entry':word(6),'dictionary':{'offset':d,'entry_bytes':width,'count':count,'encoded_text_bytes':enc,
            'game_metadata_bytes':width-enc,'entries':words,'metadata_semantics':'unresolved'},
            'objects':{'offset':first,'stride':stride,'count':len(rows),'rows':rows,
            'extent_basis':'inferred contiguous directory ends at earliest property table',
            'status':'validated_candidate' if not issues else 'partial','issues':sorted(set(issues))},
            'default_alphabet':default_alphabet,'checksum':'matched','runtime_observed':False}


def decode_z_core(data,offset,version):
    """Version-explicit instruction layout for core Z3/Z5 opcodes, no execution."""
    two=dict(zmachine._TWO);one=dict(zmachine._ONE);zero=dict(zmachine._ZERO);var=dict(zmachine._VAR)
    stores=set(zmachine._STORES);branches=set(zmachine._BRANCHES)
    if version==5:
        two.update({25:'call_2s',26:'call_2n',27:'set_colour',28:'throw'})
        one.update({8:'call_1s',15:'call_1n'})
        zero.update({9:'catch',15:'piracy'});zero.pop(5);zero.pop(6);zero.pop(12)
        var.update({0:'call_vs',12:'call_vs2',13:'erase_window',14:'erase_line',15:'set_cursor',16:'get_cursor',
                    17:'set_text_style',18:'buffer_mode',22:'read_char',23:'scan_table',24:'not',25:'call_vn',
                    26:'call_vn2',27:'tokenise',28:'encode_text',29:'copy_table',30:'print_table',31:'check_arg_count'})
        stores.update(('call_2s','call_1s','call_vs','call_vs2','read','read_char','scan_table','catch'))
        branches.update(('scan_table','check_arg_count','piracy'));branches.difference_update(('save','restore'))
    if version not in (3,5):raise ValueError('unsupported version')
    start=offset
    def read(n=1):
        nonlocal offset
        if offset+n>len(data):raise ValueError('truncated instruction')
        value=int.from_bytes(data[offset:offset+n],'big');offset+=n;return value
    op=read()
    if op==190 and version==5:raise ValueError('extended opcode is an explicit discovery boundary')
    if op<128:
        family=two;num=op&31;kinds=[2 if op&64 else 1,2 if op&32 else 1]
    elif op<192:
        kind=op>>4&3;family=zero if kind==3 else one;num=op&15;kinds=[] if kind==3 else [kind]
    else:
        family=var if op&32 else two;num=op&31;kinds=[];ended=False
        types=[read()]
        if family is var and num in (12,26):types.append(read())
        for t in types:
            for shift in (6,4,2,0):
                kind=t>>shift&3
                if kind==3:ended=True
                elif ended:raise ValueError('operand after omitted')
                else:kinds.append(kind)
    if num not in family:raise ValueError('unsupported opcode')
    name=family[num];operands=[{'kind':('large','small','variable')[k],'value':read(2 if k==0 else 1)} for k in kinds]
    if family is two and not (2<=len(operands)<=4 if name=='je' else len(operands)==2):raise ValueError('two-operand arity')
    if family is var:
        arities={'call':(1,4),'storew':(3,3),'storeb':(3,3),'put_prop':(3,3),'read':(2,4),
                 'print_char':(1,1),'print_num':(1,1),'random':(1,1),'push':(1,1),'pull':(1,1),
                 'split_window':(1,1),'set_window':(1,1),'output_stream':(1,3),'input_stream':(1,1),
                 'sound_effect':(1,4),'call_vs':(1,4),'call_vs2':(1,8),'erase_window':(1,1),
                 'erase_line':(1,1),'set_cursor':(2,2),'get_cursor':(1,1),'set_text_style':(1,1),
                 'buffer_mode':(1,1),'read_char':(1,3),'scan_table':(3,4),'not':(1,1),
                 'call_vn':(1,4),'call_vn2':(1,8),'tokenise':(2,4),'encode_text':(4,4),
                 'copy_table':(3,3),'print_table':(2,4),'check_arg_count':(1,1)}
        lo,hi=arities[name]
        if not lo<=len(operands)<=hi:raise ValueError('variable opcode arity')
    r={'offset':start,'op':name,'operands':operands}
    if name in stores:r['store']=read()
    if name in branches:
        b=read();d=b&63
        if not b&64:
            d=d*256+read()
            if d&8192:d-=16384
        r['branch']={'when':bool(b&128),'return':bool(d) if d in (0,1) else None,
                     'target':offset+d-2 if d not in (0,1) else None}
    if name in ('print','print_ret'):
        for _ in range(16384):
            if read(2)&32768:break
        else:raise ValueError('inline text budget')
    r['end']=offset
    return r


def z_facts(data,cat,*,max_instructions=20000):
    """Decode reachable static candidates and match local literal-entity guards."""
    v=cat['version'];data=data[:cat['declared_bytes']];todo=deque([cat['entry']]);rows={};seen=set();issues=[]
    successors={};call_targets=set()
    def signed(x):return x-65536 if x&32768 else x
    while todo and len(seen)<max_instructions:
        pc=todo.popleft()
        if pc in seen:continue
        seen.add(pc)
        if not 64<=pc<len(data):issues.append({'offset':pc,'error':'out of code bounds'});continue
        try:r=decode_z_core(data,pc,v)
        except ValueError as e:issues.append({'offset':pc,'error':str(e)});continue
        rows[pc]=r;op=r['op'];ss=[]
        if op in ('rtrue','rfalse','ret','ret_popped','quit','print_ret','throw','restart'):pass
        elif op=='jump':
            a=r['operands'][0]
            if a['kind']!='variable':ss.append(r['end']+signed(a['value'])-2)
            else:issues.append({'offset':pc,'error':'indirect jump'})
        else:
            ss.append(r['end'])
            if r.get('branch',{}).get('target') is not None:ss.append(r['branch']['target'])
            if op.startswith('call'):
                a=r['operands'][0]
                if a['kind']=='variable':issues.append({'offset':pc,'error':'indirect call'})
                elif a['value']:
                    target=a['value']*(2 if v==3 else 4)
                    if target<len(data) and data[target]<=15:
                        entry=target+1+(2*data[target] if v==3 else 0);call_targets.add(entry);todo.append(entry)
                    else:issues.append({'offset':pc,'error':'invalid direct routine header'})
        successors[pc]=ss;todo.extend(ss)
    preds=Counter(t for ss in successors.values() for t in ss)
    for t in call_targets:preds[t]+=1
    nodes=[];edges=[];prefix=cat['sha256']+':z'+str(v)
    def ev(r):return {'source_sha256':cat['sha256'],'space':prefix,'offset':r['offset'],'size':r['end']-r['offset']}
    for pc,r in sorted(rows.items()):
        if r['op'] not in ('test_attr','jin','test'):continue
        args=r['operands'];ident=prefix+':'+str(pc)
        gate={'id':ident+':gate','role':'branch','evidence':ev(r),'predicate':r['op'],
              'operands':args,'branch':r.get('branch')}
        if r['op']=='test':continue # Native and VM bitmap semantics differ; do not conflate them.
        if r['op']=='test_attr' and len(args)==2:
            subject={'operand':args[0],'lifetime':'this instruction only'}
            read={'id':ident+':read','role':'read','subject':subject,
                  'field':'Z object attribute bitmap','evidence':ev(r)}
            mask={'id':ident+':mask','role':'mask','subject':subject,
                  'operation':'test_attr','attribute_operand':args[1],
                  'semantics':'test numbered object attribute; branch senses Boolean result',
                  'evidence':ev(r)}
            nodes.extend((read,mask,gate));edges.extend(((read['id'],mask['id'],'value'),(mask['id'],gate['id'],'predicate')))
        if not args or args[0]['kind']=='variable':continue
        subject='object:'+str(args[0]['value']);test={'id':ident+':test','role':'entity_test','subject':subject,
                'operation':r['op'],'evidence':ev(r),'operands':args}
        nodes.append(test)
        if r['op']!='test_attr':nodes.append(gate)
        edges.append((test['id'],gate['id'],'predicate'))
        # Follow each short single-entry arm until the first object mutation or barrier.
        for first in sorted(set(successors.get(pc,[]))) if len(set(successors.get(pc,[])))>1 or r.get('branch',{}).get('return') is not None else ():
            at=first
            for _ in range(8):
                q=rows.get(at)
                if q is None or preds[at]!=1:break
                if q['op'] in ('set_attr','clear_attr','insert_obj','remove_obj'):
                    operand=q['operands'][0]
                    if operand['kind']!='variable':
                        effect={'id':ident+':effect:'+str(at),'role':'effect','subject':'object:'+str(operand['value']),
                                'operation':q['op'],'operands':q['operands'],'evidence':ev(q),'arm_entry':first}
                        nodes.append(effect);edges.append((gate['id'],effect['id'],'controls'))
                    break
                if q.get('branch') or q['op'].startswith('call') or q['op'] in ('jump','quit','ret','rtrue','rfalse','read','read_char'):break
                ss=successors.get(at,[])
                if len(ss)!=1:break
                at=ss[0]
    return nodes,edges,{'instructions':len(rows),'attempted_offsets':len(seen),'pending':len(todo),
                        'instruction_budget_exhausted':bool(todo),'issues':issues[:100],'issue_count':len(issues),
                        'v5_lifter_available':False,'scope':'bounded layout and local literal-entity relationships, no VM execution'}
