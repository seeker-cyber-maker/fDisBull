"""Complete captured source-DLL leaf of Wine's normal process_attach path.

Integer SIMD list construction is exact. The nested MODULE_InitDLL body is
re-proved, with every live read joined and every ordered write replayed.
"""
from copy import deepcopy
import hashlib
import time

import capstone

from ._wine_loader_step import typed_loader_step
from .debug_semantics import PE_TRACE_SEMANTICS
from .pe_region_equivalence import _digest
from .pe_wine_loader_contracts import (_cells, _image, _number, _rows,
    build_wine_loader_contract, validate_wine_loader_capsule)
from .pe_wine_loader_intervals import _source
from .wine_arch import register_names, validate_context

SCOPE=('Complete normal process_attach source-DLL leaf: empty dependencies/notifications, '
       'null activation context, exact XMM0/1 initialization-list insertion and re-proved '
       'MODULE_InitDLL/authored callbacks. Outer scheduling, other DLLs, exceptions, '
       'concurrency and uncovered loader intervals remain unproved')


def _native_step_identity(step,expected_before,thread):
    event,after=step['event'],step['after'];validate_context(event['registers'],64);validate_context(after,64)
    if (event.get('project_address')is not None or event['identity'].get('project_address')is not None
            or type(event['identity'].get('source_version'))is not int or event['identity']['source_version']!=1
            or event['identity'].get('runtime_address')!=event['address']
            or event['identity'].get('context')!='flat'
            or event['observation'].get('registers_stage')!='before-instruction'
            or event['observation'].get('instruction_completed')is not True
            or event['registers']['rip']!=event['address']
            or event.get('active_layers')!=[] or type(event.get('layer_generation'))is not int or event['layer_generation']!=0
            or 'native_address'in event or 'native_bytes'in event
            or event['registers']['thread']!=thread or after['thread']!=thread
            or event['registers']!=expected_before):
        raise ValueError('Full-leaf foreign context/identity/continuity differs')


def _symbols(pe,names):
    result={}
    for symbol in pe.symbols:
        if symbol.name not in names:continue
        if not 1<=symbol.section_idx<=len(pe.sections):raise ValueError('Wine symbol lacks a source section')
        value=int(pe.sections[symbol.section_idx-1].virtual_address)+symbol.value
        if symbol.name in result and result[symbol.name]!=value:raise ValueError('Ambiguous Wine source identity')
        result[symbol.name]=value
    if set(result)!=set(names):raise ValueError('Wine notification source identities missing')
    return result


def build_wine_process_attach_contract(capsule,*,loader_source,subject_source,module_capsule):
    import lief
    pe,rvas=_source(loader_source);rvas|=_symbols(pe,{'call_ldr_notifications','ldr_notifications'})
    sha=hashlib.sha256(loader_source).hexdigest()
    if capsule['loader_module'].get('source_sha256')!=sha:raise ValueError('Frozen Wine source identity differs')
    subject=lief.PE.parse(list(subject_source))if isinstance(subject_source,bytes)else None
    if (subject is None or int(subject.header.machine)!=0x8664 or list(subject.imports)
            or list(subject.delay_imports)or hashlib.sha256(subject_source).hexdigest()!=capsule['subject_source_sha256']):
        raise ValueError('Original AMD64 authored DLL without imports required')
    memory=_cells(capsule['entry_memory'])
    def at(a,w):
        if any(a+k not in memory for k in range(w)):raise ValueError('Missing full-leaf metadata/list/frame bytes')
        return int.from_bytes(bytes(memory[a+k]for k in range(w)),'little')
    entry=capsule['entry'];sp=_number(entry['general']['rsp']);node=_number(entry['general']['rcx'])
    wm=at(node,8)-0xa0;teb=_number(capsule['thread_info']['teb']);peb=at(teb+0x60,8);ldr=at(peb+0x18,8);head=ldr+0x30
    if wm<0 or sp<4096 or sp+64>1<<64:raise ValueError('Full-leaf DDAG/frame identity wraps')
    nodes=[];cursor=at(head,8);previous=head
    while cursor!=head:
        if cursor in nodes or len(nodes)>=32:raise ValueError('Initialization list is cyclic or exceeds32 nodes')
        if at(cursor+8,8)!=previous:raise ValueError('Initialization-list backward link differs')
        nodes.append(cursor);previous=cursor;cursor=at(cursor,8)
    if at(head+8,8)!=previous:raise ValueError('Initialization-list tail differs')
    module_contract=build_wine_loader_contract(module_capsule,loader_source=loader_source,subject_source=subject_source)
    lb=_number(capsule['loader_module']['base'])
    return {'loader_source_sha256':sha,'subject_source_sha256':capsule['subject_source_sha256'],
        'controller_source_sha256':capsule['controller_source_sha256'],
        'loader_module':deepcopy(capsule['loader_module']),'subject_module':deepcopy(capsule['subject_module']),
        'loader_rvas':rvas,'subject_symbols':module_contract['subject_symbols'],
        'module_contract':module_contract,'module_capsule_sha256':_digest(module_capsule),
        'addresses':{'node':hex(node),'modref':hex(wm),'teb':hex(teb),'peb':hex(peb),'ldr':hex(ldr),
            'init_order_head':hex(head),'old_tail':hex(previous),'current_modref':hex(lb+rvas['current_modref']),
            'process_detaching':hex(lb+rvas['process_detaching']),'notification_head':hex(lb+rvas['ldr_notifications']),
            'debug_channel':hex(lb+rvas['__wine_dbch_module'])},
        'init_order_nodes':[hex(n)for n in nodes],'stack_range':{'address':hex(sp-4096),'length':4160},
        'boundary':{'start_address':hex(lb+rvas['process_attach.part.0']),'stop_address':hex(at(sp,8)),
            'kind':'ret','expected_stack_delta':8},
        'guard_profile':{'reserved_nonzero':True,'flags_high_byte_zero':True,'new_node_unlinked':True,
                         'empty_dependencies':True,'empty_notifications':True,'null_activation_context':True},
        'subject_no_imports':True,'predecessor_binding':'original_source_DLL_before_its_first_process_attach'}


def validate_wine_process_attach(capsule,*,contract,loader_source,module_capsule,timeout_ms=30000):
    if type(timeout_ms)is not int or not 1<=timeout_ms<=60000:raise ValueError('timeout_ms must be1..60000')
    result={'format':'fdisbull-wine-process-attach-contract-1','status':'unknown','scope':SCOPE,
            'transfer':None,'counterexample':None};began=time.monotonic()
    try:
        import z3 as z
        pe,rvas=_source(loader_source);rvas|=_symbols(pe,{'call_ldr_notifications','ldr_notifications'})
        if (capsule.get('format')!='fdisbull-wine-process-attach-1'or capsule.get('status')!='complete'
                or capsule.get('semantics')!=PE_TRACE_SEMANTICS or capsule.get('summaries',[])!=[]):
            raise ValueError('Complete native full process_attach capsule required')
        if (hashlib.sha256(loader_source).hexdigest()!=contract['loader_source_sha256']
                or contract['loader_module'].get('source_sha256')!=contract['loader_source_sha256']
                or contract['loader_rvas']!=rvas or contract['subject_no_imports']is not True
                or contract['predecessor_binding']!='original_source_DLL_before_its_first_process_attach'):
            raise ValueError('Full-leaf original source identities differ')
        lm,sm=contract['loader_module'],contract['subject_module'];lb=_number(lm['base']);sb=_number(sm['base'])
        for owner,key in((lm,'loader_module'),(sm,'subject_module')):
            if owner['bits']!=64 or _number(owner['base'])+owner['size']>1<<64 or any(owner.get(k)!=capsule[key].get(k)for k in('name','base','size','bits','generation','source_sha256')):
                raise ValueError('Full-leaf source ownership differs')
            for field in('modules_before','modules_after'):
                if sum(all(m.get(k)==owner.get(k)for k in('name','base','size','bits','generation'))for m in capsule[field]['modules'])!=1:
                    raise ValueError('Full-leaf loaded-module bookends differ')
        if lm['size']!=pe.optional_header.sizeof_image or any(capsule[k]!=contract[k]for k in('controller_source_sha256','subject_source_sha256')):
            raise ValueError('Full-leaf source extents differ')
        entry,ending=capsule['entry'],capsule['exit'];validate_context(entry,64);validate_context(ending,64)
        addresses={k:_number(v)for k,v in contract['addresses'].items()}
        node,wm,teb,peb,ldr,head,tail=(addresses[k]for k in('node','modref','teb','peb','ldr','init_order_head','old_tail'))
        current,detaching,notify,debug=(addresses[k]for k in('current_modref','process_detaching','notification_head','debug_channel'))
        sp=_number(entry['general']['rsp']);stop=_number(contract['boundary']['stop_address'])
        if (capsule['boundary']!=contract['boundary']or contract['boundary']!={'start_address':hex(lb+rvas['process_attach.part.0']),
                'stop_address':hex(stop),'kind':'ret','expected_stack_delta':8}
                or _number(entry['rip'])!=lb+rvas['process_attach.part.0']or _number(ending['rip'])!=stop
                or _number(entry['general']['rcx'])!=node or sp&15!=8
                or current!=lb+rvas['current_modref']or detaching!=lb+rvas['process_detaching']
                or notify!=lb+rvas['ldr_notifications']or debug!=lb+rvas['__wine_dbch_module']):
            raise ValueError('Full-leaf entry/boundary/source metadata differs')
        ti=capsule['thread_info'];binding=capsule['segment_binding']
        if (ti['thread']!=entry['thread']or ti['bits']!=64 or _number(ti['teb'])!=teb
                or ti.get('gs_base_register_observed')is not False
                or ti.get('teb_source')not in('CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase','CREATE_THREAD_DEBUG_EVENT.lpThreadLocalBase')
                or binding.get('segment')!='gs'or _number(binding['teb'])!=teb or binding.get('gs_base_register_observed')is not False):
            raise ValueError('Full-leaf thread/GS convention differs')
        initial_bytes,exit_bytes=_cells(capsule['entry_memory']),_cells(capsule['exit_memory'])
        if set(initial_bytes)!=set(exit_bytes):raise ValueError('Full-leaf memory union differs')
        def at(a,w):
            if any(a+k not in initial_bytes for k in range(w)):raise ValueError('Missing full-leaf source metadata/frame bytes')
            return int.from_bytes(bytes(initial_bytes[a+k]for k in range(w)),'little')
        if (at(sp,8)!=stop or at(node,8)!=wm+0xa0 or at(node+8,8)!=wm+0xa0
                or at(wm+0xa0,8)!=node or at(wm+0xa8,8)!=node or at(node+0x28,8)!=0
                or at(wm+0x20,8)!=0 or at(wm+0x28,8)!=0 or at(wm+0x30,8)!=sb
                or at(wm+0x88,8)!=0 or at(teb+0x30,8)!=teb or at(teb+0x60,8)!=peb or at(peb+0x18,8)!=ldr
                or head!=ldr+0x30 or at(detaching,4)!=0 or at(notify,8)!=notify or at(notify+8,8)!=notify or at(debug,1)&8):
            raise ValueError('Source DDAG/empty dependency/notification/new-list profile differs')
        nodes=[_number(n)for n in contract['init_order_nodes']]
        if len(nodes)>32 or len(set(nodes))!=len(nodes)or head in nodes or wm+0x20 in nodes or tail!=(nodes[-1]if nodes else head):
            raise ValueError('Bounded initialization-list nodes differ')
        ring=[head]+nodes
        for i,n in enumerate(ring):
            if at(n,8)!=ring[(i+1)%len(ring)]or at(n+8,8)!=ring[(i-1)%len(ring)]:raise ValueError('Complete reciprocal initialization ring differs')
        list_ranges=[(n,n+16)for n in ring]+[(wm+0x20,wm+0x30)]
        if any(a<d and c<b for i,(a,b)in enumerate(list_ranges)for c,d in list_ranges[i+1:]):raise ValueError('Initialization entries partially overlap')
        low=_number(contract['stack_range']['address']);high=low+contract['stack_range']['length']
        if low!=sp-4096 or high!=sp+64 or low<0:raise ValueError('Full-leaf stack range differs')
        steps=capsule['steps'];span=capsule['module_span'];first,last=span['first_step'],span['last_step']
        if not 1<=len(steps)<=2048 or not 0<first<=last<len(steps)-1:raise ValueError('Full-leaf instruction/span bounds differ')
        for i,step in enumerate(steps):
            _native_step_identity(step,steps[i-1]['after']if i else entry,entry['thread'])
        if (contract['module_capsule_sha256']!=_digest(module_capsule)or module_capsule['entry']!=steps[first]['event']['registers']
                or module_capsule['exit']!=steps[last]['after']or module_capsule['steps']!=steps[first:last+1]):
            raise ValueError('MODULE view is detached from its exact full-leaf span')
        if any(module_capsule[k]!=capsule[k]for k in('loader_module','subject_module','controller_source_sha256','subject_source_sha256')):
            raise ValueError('Nested MODULE source owners differ from the full leaf')
        protected=_cells(steps[0]['protected_before']);roles={r['role']:(_number(r['address']),r['length'])for r in capsule['protected_ranges']}
        if len(roles)!=len(capsule['protected_ranges']):raise ValueError('Duplicate protected source role')
        def check_roles(rows):
            if len(rows)!=len(roles)or {r['role']:(_number(r['address']),len(bytes.fromhex(r['hex'])))for r in rows}!=roles:raise ValueError('Protected full-leaf role/range differs')
        check_roles(steps[0]['protected_before'])
        module_contract=contract['module_contract'];code=_image(module_contract['entry_code']);globals0=_cells([module_contract['entry_globals']]);owned=set(globals0)
        if any(module_contract[k]!=contract[k]for k in('loader_module','subject_module','controller_source_sha256','subject_source_sha256','loader_source_sha256')):
            raise ValueError('Nested MODULE source contract differs from the full leaf')
        if len(owned)!=64 or not set(code|globals0)<=protected.keys()or any(initial_bytes.get(a)!=b for a,b in (code|globals0).items()):
            raise ValueError('Original source-DLL code/global initial image differs')
        if any(initial_bytes.get(a)!=b for a,b in protected.items()):raise ValueError('Full-leaf entry protected snapshot differs from initial RAM')
        metadata=set(range(wm+0x68,wm+0x6e))|set(range(current,current+8))|set(range(wm+0x20,wm+0x30))|set(range(head+8,head+16))|set(range(tail,tail+8))
        immutable=set(range(node,node+16))|set(range(node+0x28,node+0x30))|set(range(wm+0xa0,wm+0xb0))|set(range(wm+0x30,wm+0x48))|set(range(wm+0x88,wm+0x90))
        immutable|=set(range(notify,notify+16))|set(range(teb+0x30,teb+0x38))|set(range(teb+0x60,teb+0x68))|set(range(peb+0x18,peb+0x20))
        ring_cells={a for n in ring for a in range(n,n+16)}
        if (ring_cells&(immutable|protected.keys()|set(range(low,high))|set(range(teb,teb+8)))
                or ring_cells&(set(range(wm+0x68,wm+0x6e))|set(range(current,current+8)))):
            raise ValueError('Existing list nodes alias another live source field')
        if (metadata&immutable or metadata&protected.keys()or set(range(low,high))&(metadata|immutable|protected.keys())
                or set(range(teb,teb+8))&(metadata|immutable|protected.keys())
                or low<lb+lm['size']and lb<high or low<sb+sm['size']and sb<high
                or any(a not in initial_bytes for a in metadata|immutable|set(range(teb,teb+8)))):
            raise ValueError('Mutable loader fields alias protected/stack/immutable metadata')
        if any(lb+int(s.virtual_address)<=a<lb+int(s.virtual_address)+max(int(s.virtual_size),int(s.size))for s in pe.sections if int(s.characteristics)&0x20000000 for a in metadata|set(range(teb,teb+8))):
            raise ValueError('Mutable loader metadata aliases source text')
        fields=[(wm+0x68,wm+0x6c),(wm+0x6c,wm+0x6e),(current,current+8),(wm+0x20,wm+0x30),(head+8,head+16),(tail,tail+8)]
        if any(a<d and c<b for i,(a,b)in enumerate(fields)for c,d in fields[i+1:]):raise ValueError('Distinct mutable loader fields alias')
        seen={_number(a):i for a,i in capsule['first_seen_steps'].items()}
        if set(seen)!=set(initial_bytes)or any(type(i)is not int or not 0<=i<=len(steps)for i in seen.values()):raise ValueError('Complete first-observation ledger required')
        module_proof=validate_wine_loader_capsule(module_capsule,contract=module_contract,loader_source=loader_source,timeout_ms=min(timeout_ms,30000))
        if module_proof['status']!='proved_for_observed_wine_loader_capsule':raise ValueError('Nested MODULE proof failed: '+module_proof.get('reason','unknown'))
    except (ValueError,TypeError,KeyError,IndexError,ImportError)as error:return result|{'reason':str(error)}
    deadline=began+timeout_ms/1000;names=sorted(register_names(64)-{'rip','rflags'})
    initial={n:z.BitVec('process_attach_entry_'+n,64)for n in names};initial_flags=z.BitVec('process_attach_entry_flags',32)
    initial_vectors={n:z.BitVec('process_attach_entry_'+n,128)for n in('xmm0','xmm1')};vectors=dict(initial_vectors)
    variables=(set(protected)-set(code))|owned|set(range(wm+0x68,wm+0x6e))|set(range(current,current+8))|set(range(teb,teb+8))
    original={a:z.BitVec(f'process_attach_entry_ram_{a:x}',8)if a in variables else z.BitVecVal(b,8)for a,b in initial_bytes.items()};ram=dict(original)
    regs=dict(initial);flags=initial_flags;undefined=0;extra={};domains=[];obligations=[];accesses=[];calls=[];callstack=[]
    samples=[(v,z.BitVecVal(_number(entry['general'][n]),64))for n,v in initial.items()]+[(initial_flags,z.BitVecVal(_number(entry['rflags']),32))]
    samples.extend((original[a],z.BitVecVal(initial_bytes[a],8))for a in variables)
    def word(a,w):return ram[a]if w==1 else z.Concat(*[ram[a+k]for k in reversed(range(w))])
    count_addr=_number(contract['subject_symbols']['dll_event_count']);count=word(count_addr,4);flagword=word(wm+0x68,4)
    assumptions=[initial['rsp']==sp,initial['rcx']==node,initial['rdx']!=0,(initial_flags&2)==2,z.ULE(count,6),
                 (flagword&0x81000)==0,(flagword&0xff000000)==0]
    fixed=[(initial['rsp'],z.BitVecVal(sp,64)),(initial['rcx'],z.BitVecVal(node,64))]
    simplify=lambda v:z.simplify(z.substitute(v,*fixed));cache={};solver=z.Solver()
    def observed(v):
        if z.is_bv_value(v):return v.as_long()
        key=v.get_id()
        if key not in cache:
            vv=z.simplify(z.substitute(v,*samples))
            if not z.is_bv_value(vv):raise ValueError('Full-leaf value has no native sample')
            cache[key]=(v,vv.as_long())
        return cache[key][1]
    def query(v):
        left=int((deadline-time.monotonic())*1000)
        if left<=0:raise ValueError('Full-leaf formal deadline exhausted')
        solver.set(timeout=left);solver.push();solver.add(*assumptions,v);answer=solver.check();model=solver.model()if answer==z.sat else None;solver.pop()
        if answer==z.unknown:raise ValueError('Full-leaf solver returned unknown')
        return answer,model
    def prove(kind,index,claim):obligations.append((kind,index,z.And(*domains),claim))
    def select(pointer,w):
        pointer=simplify(pointer)
        if z.is_bv_value(pointer):return word(pointer.as_long(),w)
        prove('symbolic_owned_address',index,z.And(z.UGE(pointer,min(owned)),z.ULE(pointer,max(owned)-w+1)))
        def byte(p):
            out=z.BitVecVal(0,8)
            for a in owned:out=z.If(p==a,ram[a],out)
            return out
        return byte(pointer)if w==1 else z.Concat(*[byte(pointer+k)for k in reversed(range(w))])
    def store(pointer,w,value):
        pointer=simplify(pointer)
        if z.is_bv_value(pointer):
            a=pointer.as_long()
            for k in range(w):ram[a+k]=z.Extract(8*k+7,8*k,value)
        else:
            for a in owned:
                for k in range(w):ram[a]=z.If(pointer+k==a,z.Extract(8*k+7,8*k,value),ram[a])
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    index=0
    try:
        if query(z.BoolVal(True))[0]!=z.sat or not z.is_true(z.simplify(z.substitute(z.And(*assumptions),*samples))):raise ValueError('Full-leaf entry guards exclude the native sample')
        while index<len(steps):
            if time.monotonic()>=deadline:raise ValueError('Full-leaf symbolic deadline exhausted')
            step=steps[index]
            if index==first:
                if any(a not in ram or observed(ram[a])!=b for a,b in _cells(module_capsule['entry_memory']).items()):
                    raise ValueError('Nested MODULE entry RAM receipt differs from the evolving outer sample')
                for item in module_capsule['steps']:
                    raw=bytes.fromhex(item['event'].get('execution_bytes',item['event']['bytes']));ins=next(decoder.disasm(raw,_number(item['event']['address'])))
                    if any(ins.reg_name(r)in vectors for r in ins.regs_access()[1]):raise ValueError('Nested MODULE modifies a tracked pointer XMM register')
                if not callstack or callstack[-1][0]!=_number(module_capsule['return_address']):raise ValueError('Nested MODULE return is not the pending caller frame')
                declarations={n:z.Bool(n)if w=='Bool'else z.BitVec(n,w)for n,w in module_proof['symbols'].items()};sub=[]
                for n,v in declarations.items():
                    if n=='loader_entry_flags':replacement=flags
                    elif n.startswith('loader_entry_ram_'):replacement=ram[int(n.rsplit('_',1)[1],16)]
                    elif n.startswith('loader_entry_'):replacement=regs[n[len('loader_entry_'):]]
                    else:
                        fresh=z.Bool('process_attach_'+n)if v.sort()==z.BoolSort()else z.BitVec('process_attach_'+n,v.size());extra[str(fresh)]='Bool'if v.sort()==z.BoolSort()else v.size();replacement=fresh
                        if n.startswith('loader_opaque_fp_store_'):
                            si=int(n.rsplit('_',1)[1]);row=next(a for a in module_capsule['steps'][si]['accesses']if a['kind']=='write'and a['width']*8==v.size())
                            samples.append((fresh,z.BitVecVal(int.from_bytes(bytes.fromhex(row['after_hex']),'little'),v.size())))
                    sub.append((v,replacement))
                parsed_cache={}
                def parsed(text,width):
                    key=(text,width)
                    if key not in parsed_cache:
                        if text in declarations:expr=declarations[text]
                        elif text.startswith('#x')and width!='Bool':expr=z.BitVecVal(int(text[2:],16),width)
                        elif width=='Bool'and text in('true','false'):expr=z.BoolVal(text=='true')
                        else:
                            out=z.Bool('attach_summary_out')if width=='Bool'else z.BitVec('attach_summary_out',width)
                            expr=z.parse_smt2_string('(assert (= attach_summary_out '+text+'))',decls=declarations|{'attach_summary_out':out})[0].arg(1)
                        parsed_cache[key]=z.simplify(z.substitute(expr,*sub))
                    return parsed_cache[key]
                prove('module_guard_join',index,parsed(module_proof['transfer']['guard'],'Bool'))
                prove('module_entry_join',index,z.And(regs['rsp']==_number(module_capsule['entry']['general']['rsp']),
                    regs['rcx']==wm,z.Extract(31,0,regs['rdx'])==1,(flags&2)==2,z.ULE(word(count_addr,4),6)))
                unrelated=set(protected)-owned-set(code);unrelated_ranges=[]
                for a in sorted(unrelated):
                    if unrelated_ranges and unrelated_ranges[-1][1]==a:unrelated_ranges[-1][1]+=1
                    else:unrelated_ranges.append([a,a+1])
                for a in module_proof['transfer']['ordered_accesses']:
                    index=first+a['step'];pointer=parsed(a['address'],64);w=a['width'];value=parsed(a['value'],8*w)
                    sampled_address=observed(pointer)
                    if any(sampled_address+k not in seen or seen[sampled_address+k]>index for k in range(w)):
                        raise ValueError('Nested MODULE access precedes the full-leaf first observation')
                    prove('module_pointer_nonwrap',index,z.ULE(pointer,(1<<64)-w))
                    prove('module_nonDLL_access_frame',index,z.And(*[z.Or(z.ULT(pointer+w-1,lo),z.UGE(pointer,hi))for lo,hi in unrelated_ranges]))
                    previous=select(pointer,w)
                    if a['kind']=='read':prove('module_live_read_join',index,previous==value)
                    else:
                        prove('module_write_frame_join',index,z.Or(z.And(z.UGE(pointer,low),z.ULE(pointer,high-w)),
                            z.And(pointer==teb,w==8),z.And(z.UGE(pointer,min(owned)),z.ULE(pointer,max(owned)-w+1)),
                            z.And(z.UGE(pointer,min(code)),z.ULE(pointer,max(code)-w+1))))
                        store(pointer,w,value)
                    accesses.append((index,a['kind'],pointer,w,value))
                for n in names:regs[n]=parsed(module_proof['transfer']['registers'][n],64)
                if module_proof['transfer']['defined_flags_mask']!=0xffffffff:raise ValueError('Nested MODULE final FLAGS are not fully defined')
                flags=parsed(module_proof['transfer']['flags'],32);undefined=0
                _,frame=callstack.pop();prove('module_return_frame_join',last,regs['rsp']==frame+8)
                if any(observed(regs[n])!=_number(steps[last]['after']['general'][n])for n in names):raise ValueError('Joined MODULE GPR sample differs')
                if any(observed(ram[a])!=b for a,b in _cells(module_capsule['exit_memory']).items()):
                    raise ValueError('Nested MODULE exit RAM receipt differs from its composed transfer')
                index=last+1;continue
            event,after=step['event'],step['after']
            address=_number(event['address']);raw=bytes.fromhex(event.get('execution_bytes',event['bytes']));read=step['code_read'];rd=bytes.fromhex(read['hex'])
            if (read['address']!=event['address']or hashlib.sha256(rd).hexdigest()!=read['sha256']or not rd.startswith(raw)
                    or event.get('ram_bytes',raw.hex())!=raw.hex()or any(read['module'].get(k)!=lm.get(k)for k in('name','base','size','bits','generation'))
                    or not lb<=address<address+len(raw)<=lb+lm['size']or bytes(pe.get_content_from_virtual_address(pe.imagebase+address-lb,len(raw)))!=raw):
                raise ValueError('Full-leaf executed code differs from original Wine source')
            native=list(decoder.disasm(raw,address))
            if len(native)!=1 or native[0].size!=len(raw):raise ValueError('Full-leaf instruction does not decode exactly')
            ins=native[0];position=0;pc_after=_number(after['rip'])
            def access(kind,pointer,w,value=None):
                nonlocal position
                pointer=simplify(pointer);a=observed(pointer)
                if w not in(1,2,4,8,16)or a+w>1<<64 or any(a+k not in ram for k in range(w)):raise ValueError('Full-leaf access escapes complete union')
                prove('outer_address_identity',index,pointer==a)
                if position>=len(step['accesses']):raise ValueError('Full-leaf access receipt missing')
                row=step['accesses'][position];position+=1
                if row['kind']!=kind or _number(row['address'])!=a or row['width']!=w or any(seen[a+k]>index for k in range(w)):
                    raise ValueError('Full-leaf access footprint/first observation differs')
                old=word(a,w)
                if observed(old).to_bytes(w,'little')!=bytes.fromhex(row['before_hex']):raise ValueError('Full-leaf native operand before value differs')
                if kind=='write':
                    if value is None or value.size()!=8*w:raise ValueError('Full-leaf store width/value differs')
                    if not (low<=a and a+w<=high or set(range(a,a+w))<=metadata)or set(range(a,a+w))&protected.keys():
                        raise ValueError('Outer write violates stack/metadata/protected frame')
                    store(pointer,w,value)
                accesses.append((index,kind,pointer,w,value if kind=='write'else old));return old
            def on_call(target,seq,frame):
                dest=pc_after
                if dest not in(lb+rvas['call_ldr_notifications'],lb+rvas['MODULE_InitDLL']):raise ValueError('Dependency/activation/debug callee reached')
                if dest==lb+rvas['MODULE_InitDLL']and index+1!=first:raise ValueError('MODULE call does not enter its proved span')
                prove('source_callee_target',index,target==dest);callstack.append((seq,frame));calls.append({'step':index,'target':hex(dest),'return_address':hex(seq),
                    'target_expression':target,'entry_arguments':{n:regs[n]for n in('rcx','rdx','r8','r9','rsp')}});return dest
            def on_return(target,frame):
                if callstack:
                    dest,saved=callstack.pop();prove('internal_return',index,z.And(frame==saved,target==dest));return dest
                if index!=len(steps)-1:raise ValueError('Outer RET is not final')
                prove('outer_return',index,z.And(frame==sp,target==stop));return stop
            def fresh_af():
                v=z.Bool(f'process_attach_undefined_af_{index}');extra[str(v)]='Bool';return v
            def opaque_store(w):raise ValueError('Outer pointer construction may not use opaque stores')
            flags,undefined,next_pc=typed_loader_step(ins,z=z,registers=regs,flags=flags,undefined=undefined,teb=teb,access=access,simplify=simplify,
                fresh_af=fresh_af,opaque_store=opaque_store,on_call=on_call,on_return=on_return,on_branch=domains.append,
                native_flags=_number(event['registers']['rflags']),vectors=vectors)
            if next_pc!=pc_after or position!=len(step['accesses']):raise ValueError('Full-leaf PC/complete access transfer differs')
            for row in step['accesses']:
                a,w=_number(row['address']),row['width']
                if observed(word(a,w)).to_bytes(w,'little')!=bytes.fromhex(row['after_hex']):raise ValueError('Full-leaf complete-instruction memory differs')
            if any(observed(regs[n])!=_number(after['general'][n])for n in names)or observed(flags&(0xffffffff^undefined))!=_number(after['rflags'])&(0xffffffff^undefined):
                raise ValueError('Full-leaf native GPR/defined FLAGS differ')
            index+=1
        epochs=[{'after_step':0,'images':[deepcopy(r)for r in steps[0]['protected_before']if r['role'].endswith('code')]}]
        for i,step in enumerate(steps):
            for field in('protected_before','protected_after'):check_roles(step[field])
            before,post=_cells(step['protected_before']),_cells(step['protected_after'])
            if before!=(_cells(steps[i-1]['protected_after'])if i else protected):raise ValueError('Full-leaf protected native continuity differs')
            images=[deepcopy(r)for r in step['protected_after']if r['role'].endswith('code')]
            changed=any(a['kind']=='write'and any(p<=_number(a['address'])+a['width']-1 and _number(a['address'])<p+n for name,(p,n)in roles.items()if name.endswith('code'))for a in step['accesses'])
            if changed or images!=epochs[-1]['images']:epochs.append({'after_step':i+1,'images':images,'classified_code_write':changed})
            if not first<=i<=last and before!=post:raise ValueError('Outer loader instructions changed protected source bytes')
        if epochs!=capsule['code_versions']:raise ValueError('Full-leaf code epochs omit or change a version')
        if callstack or steps[-1]['after']!=ending or [c['target']for c in calls]!=[hex(lb+rvas['call_ldr_notifications']),hex(lb+rvas['MODULE_InitDLL'])]:
            raise ValueError('Full-leaf callee/termination coverage differs')
        if any(observed(ram[a])!=b for a,b in exit_bytes.items()):raise ValueError('Full-leaf complete exit RAM sample differs')
        for kind,i,prefix,claim in obligations:
            answer,model=query(z.And(prefix,z.Not(claim)))
            if answer!=z.unsat:return result|{'reason':'Unproved full-leaf obligation: '+kind,'counterexample':{'step':i,'entry_general':{n:hex(model.eval(v,model_completion=True).as_long())for n,v in initial.items()}}}
        if query(z.Not(z.And(*domains)))[0]!=z.unsat:raise ValueError('Full-leaf path does not cover admitted guards')
        for n in('rbx','rbp','rsi','rdi','r12','r13','r14','r15'):
            if query(regs[n]!=initial[n])[0]!=z.unsat:raise ValueError('Complete caller nonvolatile frame failed')
        if query(z.Or(regs['rsp']!=initial['rsp']+8,regs['rax']!=0))[0]!=z.unsat:raise ValueError('Complete caller stack/status frame failed')
        if query(z.Or(*[ram[a]!=original[a]for a in set(protected)-owned-set(code)]))[0]!=z.unsat:raise ValueError('Non-DLL protected frame failed')
        if query(z.Or(*[ram[a]!=original[a]for a in range(current,current+8)]))[0]!=z.unsat:raise ValueError('Current module metadata was not restored')
        if query(z.Or(*[ram[a]!=original[a]for a in range(teb,teb+8)]))[0]!=z.unsat:raise ValueError('Arbitrary prior TEB exception chain was not restored')
        postring=[head]+nodes+[wm+0x20]
        for i,n in enumerate(postring):
            if query(z.Or(word(n,8)!=postring[(i+1)%len(postring)],word(n+8,8)!=postring[(i-1)%len(postring)]))[0]!=z.unsat:
                raise ValueError('Complete initialization-list append shape failed')
        text=lambda v:z.simplify(v).sexpr();post={a:observed(v)for a,v in ram.items()}
        result.update(status='proved_for_observed_wine_process_attach',
            symbols={**{str(v):64 for v in initial.values()},str(initial_flags):32,**{str(v):128 for v in initial_vectors.values()},
                **{str(original[a]):8 for a in variables},**extra},
            source={'process_attach_sha256':_digest(capsule),'capsule_sha256':_digest(capsule),'contract_sha256':_digest(contract),
                'module_capsule_sha256':_digest(module_capsule),'loader_source_sha256':contract['loader_source_sha256'],
                'subject_source_sha256':contract['subject_source_sha256'],'controller_source_sha256':contract['controller_source_sha256']},
            module_contract=module_proof,calls=[{k:({n:text(v)for n,v in value.items()}if k=='entry_arguments'else text(value)if k=='target_expression'else value)for k,value in c.items()}for c in calls],
            transfer={'registers':{n:text(regs[n])for n in names},'flags':text(flags&(0xffffffff^undefined)),'defined_flags_mask':0xffffffff^undefined,
                'vectors':{n:text(v)for n,v in vectors.items()},'entry_guard':text(z.And(*assumptions)),'guard':text(z.And(*domains)),
                'protected_memory':{hex(a):text(ram[a])for a in sorted(protected)},'metadata_memory':{hex(a):text(ram[a])for a in sorted(metadata)},
                'stack_memory':{hex(a):text(ram[a])for a in range(low,high)if a in ram},'teb_exception_chain':{hex(a):text(ram[a])for a in range(teb,teb+8)},
                'initialization_list':{hex(a):text(ram[a])for n in postring for a in range(n,n+16)},
                'ordered_accesses':[{'step':i,'kind':k,'address':text(a),'width':w,'value':text(v)}for i,k,a,w,v in accesses]},
            post_memory=_rows(post),post_protected_memory=_rows({a:post[a]for a in protected}),post_loader_memory=_rows({a:post[a]for a in metadata}),code_versions=epochs,
            checks={'instructions':len(steps),'outer_instructions':len(steps)-(last-first+1),'accesses':len(accesses),'prior_guard_obligations':len(obligations),
                'path_cover':'complete','initialization_list':'Complete bounded reciprocal ring with source DLL appended',
                'integer_simd':'Exact128-bit XMM0/1 pointer construction; no opaque pointer stores',
                'module_join':'Re-proved exact native view, every live read joined and every ordered write replayed'},
            remaining_assumptions=['Observed Win64 GS/TEB convention','Source-bound entry DDAG/list metadata, empty dependencies and notifications, null activation context',
                'Nonexception normal path with nonzero reserved argument; Flags high byte zero',
                'Opaque context-save FP/XMM6..15 values are bounded inputs, not a lossless FP-state theorem',
                'Outer scheduling, other DLLs, faults, concurrency and uncovered intervals remain unproved'])
        result['sha256']=_digest(result);return result
    except (ValueError,TypeError,KeyError,IndexError)as error:return result|{'reason':str(error)}


def expand_wine_process_attach(proof,capsule,contract,module_capsule):
    if (proof.get('status')!='proved_for_observed_wine_process_attach'or proof.get('sha256')!=_digest({k:v for k,v in proof.items()if k!='sha256'})
            or proof['source']['capsule_sha256']!=_digest(capsule)or proof['source']['contract_sha256']!=_digest(contract)
            or proof['source']['module_capsule_sha256']!=_digest(module_capsule)):
        raise ValueError('Exact full-leaf capsule, contract and nested MODULE required')
    return {'capsule':deepcopy(capsule),'contract':deepcopy(contract),'module_capsule':deepcopy(module_capsule)}
