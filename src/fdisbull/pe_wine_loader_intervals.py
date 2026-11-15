"""Source-bound caller intervals around the proved Wine MODULE_InitDLL body.

Only the captured attach success epilogue and detach selection prefix are
admitted. List construction, other DLLs and the remaining loader gaps are not
summarized by this verifier.
"""
from copy import deepcopy
import hashlib
import struct
import time

import capstone

from ._wine_loader_step import typed_loader_step
from .debug_semantics import PE_TRACE_SEMANTICS
from .pe_region_equivalence import _digest
from .pe_wine_loader_contracts import _cells, _image, _number, _rows
from .wine_arch import register_names, validate_context


SCOPE = ('Bounded source-bound Wine attach success tail or detach selection prefix; '
         'generic protected memory and metadata, exact native GPR/FLAGS/access receipts. '
         'Outer scheduling, list construction, other DLLs and uncovered loader intervals remain unproved')


def _source(loader_source):
    """Read bounded original AMD64 PE/COFF identities and image bytes."""
    import lief
    if not isinstance(loader_source,bytes) or len(loader_source)<64:
        raise ValueError('Complete original Wine PE bytes required')
    pe=lief.PE.parse(list(loader_source))
    if pe is None or int(pe.header.machine)!=0x8664 or int(pe.optional_header.magic)!=0x20b:
        raise ValueError('Original AMD64 Wine PE required')
    try:
        off=struct.unpack_from('<I',loader_source,60)[0]
        if off>len(loader_source)-24:raise ValueError('PE header escapes source')
        count_sections=struct.unpack_from('<H',loader_source,off+6)[0]
        table,count=struct.unpack_from('<II',loader_source,off+12)
        optional=struct.unpack_from('<H',loader_source,off+20)[0]
        sections=off+24+optional;strings=table+18*count
        if (not 1<=count_sections<=96 or sections+40*count_sections>len(loader_source)
                or count>100000 or table+18*count+4>len(loader_source)):
            raise ValueError('Bounded Wine COFF/section table required')
        wanted={'process_attach.part.0','process_detach','MODULE_InitDLL','current_modref','process_detaching','__wine_dbch_module'}
        symbols={};index=0
        while index<count:
            row=loader_source[table+18*index:table+18*(index+1)];name=row[:8]
            if name[:4]==bytes(4):
                at=strings+struct.unpack('<I',name[4:])[0]
                if at>=len(loader_source):raise ValueError('COFF name escapes source')
                end=loader_source.find(b'\0',at,min(at+512,len(loader_source)))
                if end<0:raise ValueError('Unterminated Wine COFF name')
                name=loader_source[at:end]
            else:name=name.rstrip(b'\0')
            value,section,_,_,aux=struct.unpack('<IhHBB',row[8:])
            name=name.decode('ascii',errors='replace')
            if name in wanted:
                if not 1<=section<=count_sections:raise ValueError('Wine identity lacks a source section')
                rva=struct.unpack_from('<I',loader_source,sections+40*(section-1)+12)[0]+value
                if name in symbols and symbols[name]!=rva:raise ValueError('Ambiguous original Wine identity')
                symbols[name]=rva
            if index+1+aux>count:raise ValueError('COFF auxiliary entries escape source')
            index+=1+aux
        if set(symbols)!=wanted:raise ValueError('Original Wine caller identities missing')
        return pe,symbols
    except struct.error as error:
        raise ValueError('Malformed Wine PE/COFF metadata') from error


def build_wine_loader_interval_contract(interval, *, loader_source, subject_source,
                                       entry_code=None, entry_globals=None):
    """Bind source identities and the recorded owned-state sample.

    Dynamic PEB/list metadata are an entry contract. Their values are read from
    retained native memory; the transfer must derive selection from those reads.
    Protected values are symbolic in the proof. Composition must separately
    join their concrete entry image to the previously proved predecessor.
    """
    import lief
    pe,rvas=_source(loader_source);loader_sha=hashlib.sha256(loader_source).hexdigest()
    if interval['loader_module'].get('source_sha256')!=loader_sha:
        raise ValueError('Frozen loader source identity differs')
    if not isinstance(subject_source,bytes) or hashlib.sha256(subject_source).hexdigest()!=interval['subject_source_sha256']:
        raise ValueError('Original authored DLL identity differs')
    subject=lief.PE.parse(list(subject_source))
    if subject is None or int(subject.header.machine)!=0x8664 or subject.get_export() is None:
        raise ValueError('Original exported AMD64 authored DLL required')
    if interval['subject_module']['size']!=subject.optional_header.sizeof_image:
        raise ValueError('Native subject image extent differs from original DLL')
    lb=_number(interval['loader_module']['base']);sb=_number(interval['subject_module']['base'])
    symbols={e.name:hex(sb+e.address) for e in subject.get_export().entries}
    memory=_cells(interval['entry_memory'])
    def observed_image(start,end):
        if any(a not in memory for a in range(start,end)):raise ValueError('Complete observed protected source span required')
        raw=bytes(memory[a]for a in range(start,end))
        return {'address':hex(start),'hex':raw.hex(),'sha256':hashlib.sha256(raw).hexdigest()}
    if entry_code is None:
        entry_code=observed_image(_number(symbols['dll_code_start']),_number(symbols['dll_code_end']))
    if entry_globals is None:
        entry_globals=observed_image(_number(symbols['dll_data_start']),_number(symbols['dll_data_end']))
    code=_image(entry_code);data=_cells([entry_globals])
    if (set(code)!=set(range(_number(symbols['dll_code_start']),_number(symbols['dll_code_end'])))
            or set(data)!=set(range(_number(symbols['dll_data_start']),_number(symbols['dll_data_end'])))
            or len(data)!=64):
        raise ValueError('Complete explicit predecessor DLL code/global images required')
    def at(a,w):
        if any(a+k not in memory for k in range(w)):raise ValueError('Missing caller pointer/metadata/frame bytes')
        return int.from_bytes(bytes(memory[a+k] for k in range(w)),'little')
    role=interval['role'];sp=_number(interval['entry']['general']['rsp']);teb=_number(interval['thread_info']['teb'])
    if sp<0x50 or sp+0x80>1<<64:raise ValueError('Bounded caller stack wraps')
    addresses={'teb':hex(teb),'current_modref':hex(lb+rvas['current_modref']),
               'process_detaching':hex(lb+rvas['process_detaching']),'debug_channel':hex(lb+rvas['__wine_dbch_module'])}
    profile={}
    if role=='attach_success_tail':
        wm=_number(interval['entry']['general']['r12'])-0xa0
        if wm<0:raise ValueError('Invalid source caller WINE_MODREF')
        start=_number(interval['entry']['rip'])
        if not lb+rvas['process_attach.part.0']<=start<lb+rvas['process_detach']:
            raise ValueError('Attach tail starts outside its source caller')
        call=bytes(pe.get_content_from_virtual_address(pe.imagebase+start-lb-5,5))
        if (len(call)!=5 or call[0]!=0xe8 or start+int.from_bytes(call[1:],'little',signed=True)!=lb+rvas['MODULE_InitDLL']
                or not lb+rvas['process_attach.part.0']<=start<lb+rvas['process_detach']):
            raise ValueError('Attach tail is not a source MODULE_InitDLL return site')
        # This slice starts with the source caller's status transfer/test.
        if bytes(pe.get_content_from_virtual_address(pe.imagebase+start-lb,4))!=bytes.fromhex('89c685c0'):
            raise ValueError('Unsupported source attach success-tail entry')
        stop=at(sp+0x78,8);stack={'address':hex(sp),'length':0x80};nodes=[]
        addresses.update(modref=hex(wm))
    elif role=='detach_selection_prefix':
        start=lb+rvas['process_detach'];stop=lb+rvas['MODULE_InitDLL']
        peb=at(teb+0x60,8);ldr=at(peb+0x18,8);head=ldr+0x30
        node=at(head+8,8);nodes=[];wm=_number(interval['exit']['general']['rcx'])
        for _ in range(32):
            if node==head:raise ValueError('No selected authored DLL in the bounded initialization list')
            if node in nodes:raise ValueError('Initialization predecessor list contains a cycle')
            nodes.append(node)
            if node==wm+0x20:break
            node=at(node+8,8)
        else:raise ValueError('Initialization predecessor walk exceeds32 nodes')
        # Capture reciprocal links as part of the metadata invariant rather
        # than silently assuming arbitrary pointers form a loader list.
        previous=head
        for node in nodes:
            if at(node,8)!=previous:raise ValueError('Initialization list reciprocal link differs')
            previous=node
        profile={'nodes':[{'attached':bool(at(node+0x48,4)&0x80000),
                           'load_count_zero':at(node+0x4c,2)==0}for node in nodes],
                 'process_detaching_zero':at(lb+rvas['process_detaching'],4)==0}
        stack={'address':hex(sp-0x50),'length':0x58}
        addresses.update(modref=hex(wm),peb=hex(peb),ldr=hex(ldr),init_order_head=hex(head),selected_link=hex(wm+0x20))
    else:raise ValueError('Unsupported bounded loader interval role')
    if at(wm+0x30,8)!=sb:raise ValueError('Selected WINE_MODREF does not identify the source DLL')
    return {'role':role,'loader_source_sha256':loader_sha,
        'subject_source_sha256':interval['subject_source_sha256'],
        'controller_source_sha256':interval['controller_source_sha256'],
        'loader_module':deepcopy(interval['loader_module']),'subject_module':deepcopy(interval['subject_module']),
        'loader_rvas':rvas,'subject_symbols':symbols,'entry_code':deepcopy(entry_code),
        'entry_globals':deepcopy(entry_globals),'addresses':addresses,'walk_nodes':[hex(n)for n in nodes],
        'stack_range':stack,'guard_profile':profile,'predecessor_binding':'caller_must_join_protected_entry_to_prior_proof',
        'boundary':{'start_address':hex(start),'stop_address':hex(stop),
            'kind':'ret' if role=='attach_success_tail'else'callee-entry',
            'expected_stack_delta':0x80 if role=='attach_success_tail'else-0x50}}


def validate_wine_loader_interval(interval, *, contract, loader_source, timeout_ms=10000):
    """Prove one complete source-bound caller fragment without other callees."""
    if type(timeout_ms)is not int or not 1<=timeout_ms<=60000:raise ValueError('timeout_ms must be1..60000')
    result={'format':'fdisbull-wine-loader-interval-contract-1','status':'unknown','scope':SCOPE,
            'transfer':None,'counterexample':None}
    try:
        import z3 as z
        pe,rvas=_source(loader_source);role=contract['role']
        if (not isinstance(interval,dict) or interval.get('format')!='fdisbull-wine-loader-interval-1'
                or interval.get('status')!='complete' or interval.get('semantics')!=PE_TRACE_SEMANTICS
                or interval.get('role')!=role or interval.get('summaries',[])!=[]):
            raise ValueError('Complete exact native caller interval required')
        if (hashlib.sha256(loader_source).hexdigest()!=contract['loader_source_sha256']
                or contract['loader_module'].get('source_sha256')!=contract['loader_source_sha256']
                or contract['loader_rvas']!=rvas):raise ValueError('Original loader source identity differs')
        lm,sm=contract['loader_module'],contract['subject_module'];lb=_number(lm['base']);sb=_number(sm['base'])
        for owner,key in ((lm,'loader_module'),(sm,'subject_module')):
            if (owner.get('bits')!=64 or type(owner.get('size'))is not int or not 0<owner['size']<=1<<30
                    or _number(owner['base'])+owner['size']>1<<64
                    or any(owner.get(k)!=interval[key].get(k)for k in('name','base','size','bits','generation','source_sha256'))):
                raise ValueError('Caller source module ownership differs')
            for field in('modules_before','modules_after'):
                matches=[m for m in interval[field]['modules']if all(m.get(k)==owner.get(k)
                         for k in('name','base','size','bits','generation'))]
                if len(matches)!=1:raise ValueError('Caller loaded-module bookend ownership differs')
        if lm['size']!=pe.optional_header.sizeof_image or any(interval[k]!=contract[k]for k in('subject_source_sha256','controller_source_sha256')):
            raise ValueError('Caller source extent or subject/controller identity differs')
        entry,ending=interval['entry'],interval['exit'];validate_context(entry,64);validate_context(ending,64)
        sp=_number(entry['general']['rsp']);teb=_number(contract['addresses']['teb']);wm=_number(contract['addresses']['modref'])
        boundary=contract['boundary'];start=_number(boundary['start_address']);stop=_number(boundary['stop_address'])
        if (interval['boundary']!=boundary or _number(entry['rip'])!=start or _number(ending['rip'])!=stop
                or (role=='attach_success_tail' and boundary['kind']!='ret')
                or (role=='detach_selection_prefix' and (boundary['kind']!='callee-entry' or start!=lb+rvas['process_detach'] or stop!=lb+rvas['MODULE_InitDLL']))):
            raise ValueError('Actual caller start/stop boundary differs')
        ti=interval['thread_info'];binding=interval['segment_binding']
        if (ti.get('thread')!=entry['thread'] or ti.get('bits')!=64 or _number(ti['teb'])!=teb
                or ti.get('gs_base_register_observed')is not False
                or ti.get('teb_source')not in('CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase','CREATE_THREAD_DEBUG_EVENT.lpThreadLocalBase')
                or binding.get('segment')!='gs' or _number(binding['teb'])!=teb
                or binding.get('gs_base_register_observed')is not False):raise ValueError('Actual caller thread/GS convention differs')
        initial_bytes,exit_bytes=_cells(interval['entry_memory']),_cells(interval['exit_memory'])
        if set(initial_bytes)!=set(exit_bytes):raise ValueError('Caller memory union differs')
        def at(a,w):
            if any(a+k not in initial_bytes for k in range(w)):raise ValueError('Missing source caller metadata/frame bytes')
            return int.from_bytes(bytes(initial_bytes[a+k]for k in range(w)),'little')
        if at(wm+0x30,8)!=sb:raise ValueError('Selected caller metadata does not identify the authored source DLL')
        subject_code=_image(contract['entry_code']);subject_globals=_cells([contract['entry_globals']])
        if any(initial_bytes.get(a)!=b for a,b in (subject_code|subject_globals).items()):raise ValueError('Owned caller predecessor image differs')
        protected=_cells(interval['steps'][0]['protected_before']);roles={}
        for row in interval['protected_ranges']:
            name=row['role'];a=_number(row['address']);n=row['length']
            if not isinstance(name,str)or not name or name in roles or type(n)is not int or not 1<=n<=2048:raise ValueError('Canonical bounded protected roles required')
            roles[name]=(a,n)
        def check_roles(rows):
            actual={}
            for row in rows:
                if row.get('role')in actual:raise ValueError('Duplicate protected role')
                actual[row.get('role')]=(_number(row['address']),len(bytes.fromhex(row['hex'])))
            if actual!=roles:raise ValueError('Protected role/address/size differs')
        check_roles(interval['steps'][0]['protected_before'])
        if not set(subject_code|subject_globals)<=protected.keys()or any(initial_bytes.get(a)!=b for a,b in protected.items()):
            raise ValueError('Complete owned protected state required')
        code_cells={a+k for name,(a,n)in roles.items()if name.endswith('code')for k in range(n)}
        if not set(subject_code)<=code_cells:raise ValueError('Authored code epoch identity missing')
        low=_number(contract['stack_range']['address']);length=contract['stack_range']['length'];high=low+length
        expected_low,expected_length=(sp,0x80)if role=='attach_success_tail'else(sp-0x50,0x58)
        if (low!=expected_low or length!=expected_length or low<0 or high>1<<64
                or (sp&15!=(0 if role=='attach_success_tail'else 8))):
            raise ValueError('Bounded caller stack alignment/range differs')
        # Test ranges explicitly: an identical final sample cannot discharge
        # an intermediate write to any protected byte or executable text.
        if (set(range(low,high))&protected.keys() or low<lb+lm['size']and lb<high
                or low<sb+sm['size']and sb<high or low<teb+0x68 and teb<high):
            raise ValueError('Caller stack aliases protected/source/TEB memory')
        current=_number(contract['addresses']['current_modref']);detaching=_number(contract['addresses']['process_detaching'])
        if (current!=lb+rvas['current_modref']or detaching!=lb+rvas['process_detaching']
                or _number(contract['addresses']['debug_channel'])!=lb+rvas['__wine_dbch_module']
                or contract['predecessor_binding']!='caller_must_join_protected_entry_to_prior_proof'):
            raise ValueError('Caller global metadata/predecessor identity differs')
        metadata=set(range(wm+0x68,wm+0x6c));variable=set(protected)|metadata
        nodes=[_number(n)for n in contract['walk_nodes']]
        if role=='attach_success_tail':
            if (nodes or contract['guard_profile']!={} or _number(entry['general']['r12'])!=wm+0xa0
                    or at(wm+0x88,8)!=0 or at(lb+rvas['__wine_dbch_module'],1)&8):
                raise ValueError('Attach success/activation/debug metadata preconditions differ')
            call=bytes(pe.get_content_from_virtual_address(pe.imagebase+start-lb-5,5))
            if (len(call)!=5 or call[0]!=0xe8 or start+int.from_bytes(call[1:],'little',signed=True)!=lb+rvas['MODULE_InitDLL']
                    or not lb+rvas['process_attach.part.0']<=start<lb+rvas['process_detach']
                    or bytes(pe.get_content_from_virtual_address(pe.imagebase+start-lb,4))!=bytes.fromhex('89c685c0')
                    or at(sp+0x78,8)!=stop or boundary['expected_stack_delta']!=0x80):
                raise ValueError('Attach caller source return/frame differs')
            metadata.update(range(current,current+8));variable.update(range(current,current+8));variable.update(range(sp,sp+0x78))
        elif role=='detach_selection_prefix':
            peb=_number(contract['addresses']['peb']);ldr=_number(contract['addresses']['ldr']);head=_number(contract['addresses']['init_order_head'])
            if (not 1<=len(nodes)<=32 or len(set(nodes))!=len(nodes)or head!=ldr+0x30
                    or _number(contract['addresses']['selected_link'])!=wm+0x20 or nodes[-1]!=wm+0x20
                    or head in nodes or at(teb+0x30,8)!=teb or at(teb+0x60,8)!=peb
                    or at(peb+0x18,8)!=ldr or at(head+8,8)!=nodes[0]or boundary['expected_stack_delta']!=-0x50):
                raise ValueError('Actual source initialization-list selection chain differs')
            previous=head
            for i,node in enumerate(nodes):
                if at(node,8)!=previous or i+1<len(nodes)and at(node+8,8)!=nodes[i+1]:raise ValueError('Finite initialization-list links differ')
                metadata.update(range(node+0x48,node+0x4e));variable.update(range(node+0x48,node+0x4e));previous=node
            metadata.update(range(detaching,detaching+4));variable.update(range(detaching,detaching+4))
            profile={'nodes':[{'attached':bool(at(node+0x48,4)&0x80000),
                               'load_count_zero':at(node+0x4c,2)==0}for node in nodes],
                     'process_detaching_zero':at(detaching,4)==0}
            if contract['guard_profile']!=profile:raise ValueError('Declared source branch family differs from actual metadata')
        else:raise ValueError('Unsupported bounded caller role')
        if (metadata&protected.keys()or metadata&set(range(low,high))or any(a not in initial_bytes for a in metadata)
                or any(lb+int(s.virtual_address)<=a<lb+int(s.virtual_address)+max(int(s.virtual_size),int(s.size))
                       for s in pe.sections if int(s.characteristics)&0x20000000 for a in metadata)):
            raise ValueError('Caller metadata aliases protected/stack/executable source memory')
        if not variable<=initial_bytes.keys():raise ValueError('Complete symbolic metadata/stack/protected input bytes required')
        # These dynamic records must not alias the pointer chain or each
        # other's typed fields. Such aliases can disappear in the final sample.
        pointer_cells=set(range(wm+0x30,wm+0x38))
        if role=='attach_success_tail':
            pointer_cells.update(range(wm+0x88,wm+0x90))
        else:
            for a,w in [(teb+0x30,8),(teb+0x60,8),(peb+0x18,8),(head+8,8)]+[(n,16)for n in nodes]:
                pointer_cells.update(range(a,a+w))
        if (metadata&pointer_cells or pointer_cells&set(range(low,high))or pointer_cells&protected.keys()
                or len(metadata)!=(12 if role=='attach_success_tail'else 6*len(nodes)+4)):
            raise ValueError('Caller typed metadata aliases its pointer chain or another field')
        steps=interval['steps']
        if not isinstance(steps,list)or not 1<=len(steps)<=512:raise ValueError('Caller interval exceeds512 instructions')
        first={_number(a):i for a,i in interval['first_seen_steps'].items()}
        if set(first)!=set(initial_bytes)or any(type(i)is not int or not 0<=i<=len(steps)for i in first.values()):raise ValueError('Complete first-observation memory ledger required')
    except (ValueError,TypeError,KeyError,IndexError,ImportError)as error:
        return result|{'reason':str(error)}
    deadline=time.monotonic()+timeout_ms/1000;names=sorted(register_names(64)-{'rip','rflags'})
    initial={n:z.BitVec('interval_entry_'+n,64)for n in names};initial_flags=z.BitVec('interval_entry_flags',32)
    original={a:z.BitVec(f'interval_entry_ram_{a:x}',8)if a in variable else z.BitVecVal(b,8)for a,b in initial_bytes.items()}
    ram=dict(original);regs=dict(initial);flags=initial_flags;undefined=0;opaque={};domains=[];obligations=[];accesses=[];pending=None
    samples=[(v,z.BitVecVal(_number(entry['general'][n]),64))for n,v in initial.items()]+[(initial_flags,z.BitVecVal(_number(entry['rflags']),32))]
    samples.extend((original[a],z.BitVecVal(initial_bytes[a],8))for a in variable)
    fixed={initial['rsp']:sp};assumptions=[initial['rsp']==sp,(initial_flags&2)==2]
    word=lambda a,w:z.Concat(*[ram[a+k]for k in reversed(range(w))])if w>1 else ram[a]
    if role=='attach_success_tail':
        fixed[initial['r12']]=wm+0xa0;assumptions.extend([initial['r12']==wm+0xa0,z.Extract(31,0,initial['rax'])==0])
    else:
        state=word(detaching,4)
        for i,node in enumerate(nodes):
            chosen=z.And((word(node+0x48,4)&0x80000)!=0,z.Or(word(node+0x4c,2)==0,state!=0))
            assumptions.append(chosen if i==len(nodes)-1 else z.Not(chosen))
            branch=contract['guard_profile']['nodes'][i]
            assumptions.append(((word(node+0x48,4)&0x80000)!=0)==branch['attached'])
            if branch['attached']:
                assumptions.append((word(node+0x4c,2)==0)==branch['load_count_zero'])
                if not branch['load_count_zero']:
                    assumptions.append((state==0)==contract['guard_profile']['process_detaching_zero'])
    simplify=lambda v:z.simplify(z.substitute(v,*[(k,z.BitVecVal(vv,k.size()))for k,vv in fixed.items()]))
    cache={};solver=z.Solver()
    def observed(v):
        if z.is_bv_value(v):return v.as_long()
        key=v.get_id()
        if key not in cache:
            sample=z.simplify(z.substitute(v,*samples))
            if not z.is_bv_value(sample):raise ValueError('Caller expression lacks a native sample')
            cache[key]=(v,sample.as_long())
        return cache[key][1]
    def query(v):
        left=int((deadline-time.monotonic())*1000)
        if left<=0:raise ValueError('Caller proof deadline exhausted')
        solver.set(timeout=left);solver.push();solver.add(*assumptions,v);answer=solver.check();model=solver.model()if answer==z.sat else None;solver.pop()
        if answer==z.unknown:raise ValueError('Caller solver returned unknown')
        return answer,model
    ranges=[]
    for a in sorted(ram):
        if ranges and ranges[-1][1]==a:ranges[-1][1]+=1
        else:ranges.append([a,a+1])
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    try:
        if query(z.BoolVal(True))[0]!=z.sat:raise ValueError('Infeasible caller entry contract')
        # Check the observed machine actually belongs to the admitted domain.
        if not z.is_true(z.simplify(z.substitute(z.And(*assumptions),*samples))):raise ValueError('Native caller sample violates entry guards')
        for index,step in enumerate(steps):
            if time.monotonic()>=deadline:raise ValueError('Caller symbolic deadline exhausted')
            event,after=step['event'],step['after'];validate_context(event['registers'],64);validate_context(after,64)
            if (event.get('project_address')is not None or event['identity'].get('project_address')is not None
                    or event['identity'].get('source_version')!=1 or event['identity'].get('runtime_address')!=event['address']
                    or event['observation'].get('instruction_completed')is not True
                    or event['registers']['thread']!=entry['thread']or after['thread']!=entry['thread']
                    or event['registers']!=(steps[index-1]['after']if index else entry)):
                raise ValueError('Foreign caller context/identity/continuity differs')
            address=_number(event['address']);raw=bytes.fromhex(event.get('execution_bytes',event['bytes']));read=step['code_read'];rd=bytes.fromhex(read['hex'])
            if (read['address']!=event['address']or hashlib.sha256(rd).hexdigest()!=read['sha256']or not rd.startswith(raw)
                    or event.get('ram_bytes',raw.hex())!=raw.hex()
                    or any(read['module'].get(k)!=lm.get(k)for k in('name','base','size','bits','generation'))
                    or not lb<=address<address+len(raw)<=lb+lm['size']
                    or bytes(pe.get_content_from_virtual_address(pe.imagebase+address-lb,len(raw)))!=raw):
                raise ValueError('Executed caller code differs from frozen original Wine source')
            native=list(decoder.disasm(raw,address))
            if len(native)!=1 or native[0].size!=len(raw):raise ValueError('Caller code does not decode exactly')
            ins=native[0];position=0;pc_after=_number(after['rip'])
            def access(kind,pointer,width,value=None):
                nonlocal position
                pointer=simplify(pointer);a=observed(pointer)
                if width not in(1,2,4,8)or a+width>1<<64 or any(a+k not in ram for k in range(width)):raise ValueError('Caller access escapes exact observed union')
                # Caller addresses are metadata-derived, not data-indexed. Prove
                # the address itself, avoiding sample-equal alias substitution.
                obligations.append(('address_identity',index,z.And(*domains),pointer==a))
                if position>=len(step['accesses']):raise ValueError('Decoded caller access is missing')
                ledger=step['accesses'][position];position+=1
                if ledger['kind']!=kind or _number(ledger['address'])!=a or ledger['width']!=width:raise ValueError('Caller access footprint differs')
                if any(first[a+k]>index for k in range(width)):raise ValueError('Caller read precedes first observation')
                old=word(a,width)
                if observed(old).to_bytes(width,'little')!=bytes.fromhex(ledger['before_hex']):raise ValueError('Caller access before value differs')
                if kind=='write':
                    slots={sp-8,sp-0x10,sp-0x18,sp-0x20,sp-0x50}if role=='detach_selection_prefix'else set()
                    allowed=(width==8 and a in slots)or(width==4 and a==wm+0x68)or(role=='attach_success_tail'and width==8 and a==current)
                    if not allowed or set(range(a,a+width))&protected.keys():raise ValueError('Caller write violates exact stack/metadata/protected frame')
                    if value is None or value.size()!=8*width:raise ValueError('Caller store width/value differs')
                    for k in range(width):ram[a+k]=z.Extract(k*8+7,k*8,value)
                accesses.append((index,kind,pointer,width,value if kind=='write'else old))
                return old
            def on_call(target,seq,frame):
                nonlocal pending
                if role!='detach_selection_prefix'or index!=len(steps)-1 or pending is not None:raise ValueError('Only the terminal source MODULE call is admitted')
                obligations.append(('selected_module_call',index,z.And(*domains),z.And(target==stop,regs['rcx']==wm,regs['rdx']==0,
                    regs['r8']==z.ZeroExt(32,word(detaching,4)),frame==sp-0x50)))
                pending={'target':target,'return_address':seq,'rsp':frame,'arguments':{n:regs[n]for n in('rcx','rdx','r8')}}
                return stop
            def on_return(target,frame):
                if role!='attach_success_tail'or index!=len(steps)-1:raise ValueError('Only the terminal attach caller RET is admitted')
                obligations.append(('caller_return',index,z.And(*domains),z.And(target==stop,frame==sp+0x78)))
                return stop
            def fresh_af():
                fresh=z.Bool(f'interval_undefined_af_{index}');opaque[str(fresh)]='Bool';return fresh
            def opaque_store(width):raise ValueError('Floating/opaque stores are outside caller intervals')
            flags,undefined,next_pc=typed_loader_step(ins,z=z,registers=regs,flags=flags,undefined=undefined,teb=teb,
                access=access,simplify=simplify,fresh_af=fresh_af,opaque_store=opaque_store,on_call=on_call,
                on_return=on_return,on_branch=domains.append,native_flags=_number(event['registers']['rflags']))
            if next_pc!=pc_after or position!=len(step['accesses']):raise ValueError('Caller complete PC/access footprint differs')
            for row in step['accesses']:
                a,w=_number(row['address']),row['width']
                if observed(word(a,w)).to_bytes(w,'little')!=bytes.fromhex(row['after_hex']):raise ValueError('Caller complete-instruction memory after value differs')
            if any(observed(regs[n])!=_number(after['general'][n])for n in names)or observed(flags&(0xffffffff^undefined))!=_number(after['rflags'])&(0xffffffff^undefined):
                raise ValueError('Caller native GPR/defined FLAGS disagree with typed transfer')
            for field in('protected_before','protected_after'):check_roles(step[field])
            before,post=_cells(step['protected_before']),_cells(step['protected_after'])
            if set(before)!=set(protected)or set(post)!=set(protected)or before!=( _cells(steps[index-1]['protected_after'])if index else protected):raise ValueError('Caller protected state continuity differs')
            if any(observed(ram[a])!=b for a,b in post.items()):raise ValueError('Caller protected native sample differs')
        images=[deepcopy(row)for row in steps[0]['protected_before']if row['role'].endswith('code')]
        expected_epochs=[{'after_step':0,'images':images}]
        if interval['code_versions']!=expected_epochs:raise ValueError('Caller code epochs differ from its unchanged protected frame')
        if steps[-1]['after']!=ending or (role=='detach_selection_prefix')!=(pending is not None):raise ValueError('Caller terminal control boundary missing')
        if any(observed(ram[a])!=b for a,b in exit_bytes.items()):raise ValueError('Caller final memory union differs')
        for kind,index,prefix,claim in obligations:
            status,model=query(z.And(prefix,z.Not(claim)))
            if status!=z.unsat:
                return result|{'reason':'Unproved caller obligation: '+kind,'counterexample':{'step':index,'entry_general':{n:hex(model.eval(v,model_completion=True).as_long())for n,v in initial.items()}}}
        if query(z.Not(z.And(*domains)))[0]!=z.unsat:raise ValueError('Caller path does not cover admitted entry guards')
        if query(z.Or(*[ram[a]!=original[a]for a in protected]))[0]!=z.unsat:raise ValueError('Caller protected memory frame failed')
        if query(regs['rsp']!=initial['rsp']+boundary['expected_stack_delta'])[0]!=z.unsat:raise ValueError('Caller final stack delta failed')
        text=lambda v:z.simplify(v).sexpr()
        post={a:observed(ram[a])for a in ram}
        result.update(status='proved_for_observed_wine_loader_interval',role=role,
            symbols={**{str(v):64 for v in initial.values()},str(initial_flags):32,**{str(original[a]):8 for a in variable},**opaque},
            source={'interval_sha256':_digest(interval),'contract_sha256':_digest(contract),'loader_source_sha256':contract['loader_source_sha256'],
                'subject_source_sha256':contract['subject_source_sha256'],'controller_source_sha256':contract['controller_source_sha256']},
            transfer={'registers':{n:text(regs[n])for n in names},'flags':text(flags&(0xffffffff^undefined)),
                'defined_flags_mask':0xffffffff^undefined,'guard':text(z.And(*domains)),'entry_guard':text(z.And(*assumptions)),
                'protected_memory':{hex(a):text(ram[a])for a in sorted(protected)},
                'metadata_memory':{hex(a):text(ram[a])for a in sorted(metadata)},
                'stack_memory':{hex(a):text(ram[a])for a in range(low,high)if a in ram},
                'ordered_accesses':[{'step':i,'kind':k,'address':text(a),'width':w,'value':text(v)}for i,k,a,w,v in accesses],
                'pending_call':None if pending is None else {'target':text(pending['target']),'return_address':hex(pending['return_address']),
                    'rsp':text(pending['rsp']),'arguments':{n:text(v)for n,v in pending['arguments'].items()}}},
            post_memory=_rows(post),post_loader_memory=_rows({a:post[a]for a in metadata}),post_protected_memory=_rows({a:post[a]for a in protected}),code_versions=expected_epochs,
            checks={'instructions':len(steps),'accesses':len(accesses),'prior_guard_obligations':len(obligations),
                'path_cover':'complete','protected_memory':'Every byte preserved for all admitted input values'},
            remaining_assumptions=['Observed Win64 GS/TEB convention','Valid source-bound entry metadata and finite reciprocal initialization list',
                'Attach tail saved-stack values are arbitrary inputs; no caller-entry ABI identity is inferred',
                'List construction, outer scheduling, faults, concurrency, other DLLs and uncovered intervals remain unproved'])
        result['sha256']=_digest(result);return result
    except (ValueError,TypeError,KeyError,IndexError)as error:
        return result|{'reason':str(error)}


def expand_wine_loader_interval(proof,interval,contract):
    if (proof.get('status')!='proved_for_observed_wine_loader_interval'
            or proof.get('sha256')!=_digest({k:v for k,v in proof.items()if k!='sha256'})
            or proof.get('source',{}).get('interval_sha256')!=_digest(interval)
            or proof['source'].get('contract_sha256')!=_digest(contract)):
        raise ValueError('Exact original loader interval and source contract required')
    return {'interval':deepcopy(interval),'contract':deepcopy(contract)}
