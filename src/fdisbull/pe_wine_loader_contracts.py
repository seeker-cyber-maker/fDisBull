"""Bounded source-linked Wine MODULE_InitDLL normal-path contracts.

The verifier consumes actual instruction/access ledgers, never names as
semantics. Protected images are checked after every step. Floating context
stores have explicit opaque values and exact bounded write footprints.
"""
from copy import deepcopy
import hashlib
import struct
import time

import capstone

from .debug_semantics import PE_TRACE_SEMANTICS
from .pe_dll_contracts import validate_dll_callback
from .pe_region_equivalence import _digest
from ._wine_loader_step import typed_loader_step
from .wine_arch import register_names, validate_context


SCOPE = ('Complete captured source-linked MODULE_InitDLL normal path, including the single source TLS '
         'callback, DllMain, PE-directory/NT-header lookup and context-save leaves; generic owned DLL '
         'globals with event_count 0..6 and irrelevant GPR/defined FLAGS. Mapping/dispatch into '
         'MODULE_InitDLL, faults, exceptions, other threads and uncovered loader intervals remain unproved')


def _number(value):
    if isinstance(value, str) and value.startswith('0x'): value=int(value,16)
    if type(value) is not int or not 0<=value<1<<64: raise ValueError('Exact PE64 address required')
    return value


def _cells(rows):
    if not isinstance(rows,list) or len(rows)>256: raise ValueError('Bounded exact memory rows required')
    cells={}
    for row in rows:
        address,raw=_number(row['address']),bytes.fromhex(row['hex'])
        if not raw or len(raw)*2!=len(row['hex']) or address+len(raw)>1<<64:
            raise ValueError('Memory evidence is empty, noncanonical or wraps')
        for k,b in enumerate(raw):
            if address+k in cells: raise ValueError('Memory rows overlap')
            cells[address+k]=b
    if len(cells)>16384: raise ValueError('Loader capsule memory exceeds 16 KiB')
    return cells


def _rows(cells):
    rows=[]
    for a,b in sorted(cells.items()):
        if rows and int(rows[-1]['address'],16)+len(rows[-1]['hex'])//2==a: rows[-1]['hex']+=f'{b:02x}'
        else: rows.append({'address':hex(a),'hex':f'{b:02x}'})
    return rows


def _image(row):
    raw=bytes.fromhex(row['hex'])
    if row['sha256']!=hashlib.sha256(raw).hexdigest(): raise ValueError('Source image byte digest differs')
    return _cells([{'address':row['address'],'hex':row['hex']}])


def _build_wine_loader_contract(capsule, *, loader_source, subject_source,
                               entry_code=None, entry_globals=None):
    """Derive source metadata, never a callback target from an incoming GPR.

    The attach defaults are the original authored DLL image. Detach requires
    the caller's previously proved code/global invariant explicitly; native
    exit samples are not substituted for that antecedent.
    """
    import lief
    if not isinstance(loader_source,bytes) or not isinstance(subject_source,bytes) or len(loader_source)<64 or len(subject_source)<64:
        raise ValueError('Complete original PE byte strings are required')
    subject_sha=hashlib.sha256(subject_source).hexdigest();loader_sha=hashlib.sha256(loader_source).hexdigest()
    if capsule['loader_module'].get('source_sha256')!=loader_sha:
        raise ValueError('Supplied loader bytes differ from their captured frozen source identity')
    if capsule['subject_source_sha256']!=subject_sha:raise ValueError('Authored DLL original bytes differ')
    loader,subject=lief.PE.parse(list(loader_source)),lief.PE.parse(list(subject_source))
    if loader is None or subject is None:raise ValueError('Preserved loader and authored DLL PE bytes required')
    if (int(loader.header.machine)!=0x8664 or int(subject.header.machine)!=0x8664
            or int(loader.optional_header.magic)!=0x20b or int(subject.optional_header.magic)!=0x20b
            or not subject.has_tls or subject.get_export() is None):
        raise ValueError('Native AMD64 loader and exported TLS DLL sources are required')
    sb=_number(capsule['subject_module']['base']);delta=sb-subject.imagebase
    symbols={entry.name:hex(sb+entry.address) for entry in subject.get_export().entries}
    phase={1:'attach',0:'detach'}[capsule['selection']['reason_low32']]
    def image(address,raw):return {'address':hex(address),'hex':raw.hex(),'sha256':hashlib.sha256(raw).hexdigest()}
    start,end=(_number(symbols[n]) for n in ('dll_code_start','dll_code_end'))
    data_start,data_end=(_number(symbols[n]) for n in ('dll_data_start','dll_data_end'))
    if entry_code is None:
        if phase!='attach':raise ValueError('Detach requires the previously proved DLL code epoch')
        entry_code=image(start,bytes(subject.get_content_from_virtual_address(start-delta,end-start)))
    if entry_globals is None:
        if phase!='attach':raise ValueError('Detach requires the previously proved DLL global invariant')
        entry_globals={'address':hex(data_start),'hex':bytes(subject.get_content_from_virtual_address(data_start-delta,data_end-data_start)).hex()}
    entry_code=deepcopy(entry_code);entry_globals=deepcopy(entry_globals)
    entry_code['sha256']=hashlib.sha256(bytes.fromhex(entry_code['hex'])).hexdigest()
    directory=subject.data_directories[9]
    raw=bytearray(subject.get_content_from_virtual_address(subject.imagebase+directory.rva,40))
    for offset in range(0,32,8):
        value=int.from_bytes(raw[offset:offset+8],'little')
        if value:raw[offset:offset+8]=(value+delta).to_bytes(8,'little')
    array_address=subject.tls.addressof_callbacks+delta
    array=bytearray(subject.get_content_from_virtual_address(subject.tls.addressof_callbacks,16))
    for offset in (0,8):
        value=int.from_bytes(array[offset:offset+8],'little')
        if value:array[offset:offset+8]=(value+delta).to_bytes(8,'little')
    # COFF names are source facts; runtime addresses are then source RVA+base.
    peoff=struct.unpack_from('<I',loader_source,60)[0]
    if peoff>len(loader_source)-24:raise ValueError('Original Wine PE header escapes source bytes')
    count_sections=struct.unpack_from('<H',loader_source,peoff+6)[0]
    table,count=struct.unpack_from('<II',loader_source,peoff+12)
    optional=struct.unpack_from('<H',loader_source,peoff+20)[0]
    section_table=peoff+24+optional;strings=table+18*count
    if not 1<=count_sections<=96 or section_table+40*count_sections>len(loader_source):
        raise ValueError('Original Wine section table escapes source bytes')
    wanted={'module_init':'MODULE_InitDLL','tls_callbacks':'call_tls_callbacks',
            'entry_wrapper':'call_dll_entry_point','setjmpex':'__wine_setjmpex',
            'image_directory':'RtlImageDirectoryEntryToData','image_nt_header':'RtlImageNtHeader'}
    found={};index=0
    if count>100000 or table+18*count+4>len(loader_source):raise ValueError('Missing bounded original Wine COFF symbol table')
    while index<count:
        row=loader_source[table+18*index:table+18*(index+1)];name=row[:8]
        if name[:4]==bytes(4):
            offset=strings+struct.unpack('<I',name[4:])[0]
            if offset>=len(loader_source):raise ValueError('COFF name escapes source')
            stop=loader_source.find(b'\0',offset,min(offset+512,len(loader_source)))
            if stop<0:raise ValueError('Unterminated bounded COFF name')
            name=loader_source[offset:stop]
        else:name=name.rstrip(b'\0')
        value,section,_,_,aux=struct.unpack('<IhHBB',row[8:])
        decoded=name.decode('ascii',errors='replace')
        for key,expected in wanted.items():
            if decoded==expected:
                if not 1<=section<=count_sections:raise ValueError('Wine function lacks a source section')
                rva=struct.unpack_from('<I',loader_source,section_table+40*(section-1)+12)[0]+value
                if key in found and found[key]!=rva:raise ValueError('Ambiguous Wine function source identity')
                found[key]=rva
        index+=1+aux
    if set(found)!=set(wanted):raise ValueError('Original source lacks the selected Wine loader function identities')
    sp=_number(capsule['entry']['general']['rsp'])
    if sp<4096:raise ValueError('Dispatcher frame lacks its bounded private stack margin')
    return {'phase':phase,'controller_source_sha256':capsule['controller_source_sha256'],
        'subject_source_sha256':subject_sha,'loader_source_sha256':loader_sha,
        'loader_module':deepcopy(capsule['loader_module']),'subject_module':deepcopy(capsule['subject_module']),
        'subject_symbols':symbols,'loader_rvas':found,
        'subject_header':image(sb,subject_source[:subject.optional_header.sizeof_headers]),
        'tls_directory':image(sb+directory.rva,bytes(raw)),'callback_array':image(array_address,bytes(array)),
        'entry_code':entry_code,'entry_globals':entry_globals,'stack_range':{'address':hex(sp-4096),'length':4160}}


def build_wine_loader_contract(capsule, *, loader_source, subject_source,
                              entry_code=None, entry_globals=None):
    """Build source-derived metadata; detach requires its proved predecessor."""
    try:
        return _build_wine_loader_contract(capsule,loader_source=loader_source,subject_source=subject_source,
                                          entry_code=entry_code,entry_globals=entry_globals)
    except struct.error as error:
        raise ValueError('Malformed bounded PE/COFF source metadata') from error


def validate_wine_loader_capsule(capsule, *, contract, loader_source, timeout_ms=10000):
    """Prove an exact normal-path invocation and its protected-memory frame."""
    if type(timeout_ms) is not int or not 1<=timeout_ms<=60000: raise ValueError('timeout_ms must be 1..60000')
    result={'format':'fdisbull-wine-loader-contract-1','status':'unknown','scope':SCOPE,
            'counterexample':None,'transfer':None}
    try:
        if (not isinstance(capsule,dict) or capsule.get('format')!='fdisbull-wine-loader-dispatch-capsule-1'
                or capsule.get('status')!='complete' or capsule.get('semantics')!=PE_TRACE_SEMANTICS
                or capsule.get('summaries')!=[]): raise ValueError('A complete native instruction/access capsule is required')
        if not isinstance(loader_source,bytes) or hashlib.sha256(loader_source).hexdigest()!=contract['loader_source_sha256']:
            raise ValueError('Original Wine loader PE byte identity differs')
        import lief
        pe=lief.PE.parse(list(loader_source))
        if pe is None or int(pe.header.machine)!=0x8664 or int(pe.optional_header.magic)!=0x20b:
            raise ValueError('Original AMD64 Wine loader PE required')
        lm,sm=contract['loader_module'],contract['subject_module']
        if lm.get('source_sha256')!=contract['loader_source_sha256']:
            raise ValueError('Loader source byte identity differs from its captured module identity')
        for field,key in ((lm,'loader_module'),(sm,'subject_module')):
            if field['bits']!=64 or any(field.get(k)!=capsule[key].get(k) for k in ('name','base','size','bits','generation')):
                raise ValueError('Observed loader/subject module ownership differs')
        if any(capsule[k]!=contract[k] for k in ('controller_source_sha256','subject_source_sha256')):
            raise ValueError('Controller and authored DLL source identities differ')
        lb,sb=_number(lm['base']),_number(sm['base'])
        if (type(lm.get('size'))is not int or type(sm.get('size'))is not int
                or not 0<lm['size']<=1<<30 or not 0<sm['size']<=1<<30
                or lb+lm['size']>1<<64 or sb+sm['size']>1<<64
                or lm['size']!=pe.optional_header.sizeof_image):
            raise ValueError('Loaded module extents differ from the original loader image or wrap')
        symbols={n:_number(v) for n,v in contract['subject_symbols'].items()}
        rvas={n:_number(v) for n,v in contract['loader_rvas'].items()}
        phase=contract['phase'];reason={'attach':1,'detach':0}[phase]
        entry,ending=capsule['entry'],capsule['exit'];validate_context(entry,64);validate_context(ending,64)
        stack,caller=_number(entry['general']['rsp']),_number(capsule['return_address'])
        wm,teb=_number(capsule['selection']['modref']),_number(capsule['thread_info']['teb'])
        low=_number(contract['stack_range']['address']);length=contract['stack_range']['length'];high=low+length
        if (type(length) is not int or not 64<=length<=8192 or high>1<<64 or not low<=stack<high
                or entry['rip']!=hex(lb+rvas['module_init']) or stack&15!=8
                or _number(entry['general']['rdx'])&0xffffffff!=reason
                or _number(entry['general']['rcx'])!=wm or _number(entry['rflags'])&2!=2
                or capsule['selection']['reason_low32']!=reason or _number(capsule['selection']['dll_base'])!=sb
                or capsule['thread_info']['thread']!=entry['thread'] or capsule['thread_info']['bits']!=64
                or capsule['thread_info']['gs_base_register_observed'] is not False
                or capsule['thread_info'].get('teb_source')not in ('CREATE_PROCESS_DEBUG_EVENT.lpThreadLocalBase','CREATE_THREAD_DEBUG_EVENT.lpThreadLocalBase')
                or capsule['segment_binding'].get('segment')!='gs' or _number(capsule['segment_binding']['teb'])!=teb
                or capsule['segment_binding'].get('gs_base_register_observed')is not False):
            raise ValueError('Loader entry/frame/thread/reason preconditions differ')
        initial_bytes,exit_bytes=_cells(capsule['entry_memory']),_cells(capsule['exit_memory'])
        if set(initial_bytes)!=set(exit_bytes): raise ValueError('Entry/exit access union differs')
        def raw_at(address,width):
            if any(address+k not in initial_bytes for k in range(width)): raise ValueError('Missing source/metadata/frame bytes')
            return bytes(initial_bytes[address+k] for k in range(width))
        def num_at(address,width): return int.from_bytes(raw_at(address,width),'little')
        expected_header=_image(contract['subject_header']);tls=_image(contract['tls_directory']);array=_image(contract['callback_array'])
        subject_code=_image(contract['entry_code']);subject_globals=_cells([contract['entry_globals']])
        for cells in (expected_header,array,subject_code,subject_globals):
            if any(initial_bytes.get(a)!=b for a,b in cells.items()): raise ValueError('Capsule entry differs from its source/predecessor image')
        # The normal dispatcher reads AddressOfCallbacks only; unused TLS
        # directory fields need not be invented as native observations.
        if any(a in initial_bytes and initial_bytes[a]!=b for a,b in tls.items()):
            raise ValueError('Observed TLS directory bytes differ from relocated source')
        if len(subject_globals)!=64 or min(subject_globals)!=symbols['dll_data_start'] or max(subject_globals)+1!=symbols['dll_data_end']:
            raise ValueError('Complete authored DLL global state is required')
        nt=sb+num_at(sb+0x3c,4)
        if (raw_at(sb,2)!=b'MZ' or raw_at(nt,4)!=b'PE\0\0' or num_at(nt+0x18,2)!=0x20b
                or num_at(nt+0x84,4)<=9 or sb+num_at(nt+0xd0,4)!=min(tls) or num_at(nt+0xd4,4)!=40
                or min(tls)+40!=max(tls)+1 or num_at(min(tls)+24,8)!=min(array)
                or len(array)!=16 or num_at(min(array),8)!=symbols['dll_tls_callback'] or num_at(min(array)+8,8)!=0
                or sb+num_at(nt+0x28,4)!=symbols['dll_entry']
                or num_at(wm+0x30,8)!=sb or num_at(wm+0x38,8)!=symbols['dll_entry']
                or num_at(wm+0x6b,1)&0x40 or num_at(wm+0x6e,2)!=0xffff
                or num_at(teb+0x30,8)!=teb or num_at(stack,8)!=caller):
            raise ValueError('PE/TLS array and WINE_MODREF fields do not establish the selected source DLL')
        protected=_cells(capsule['steps'][0]['protected_before'])
        role_ranges={}
        for row in capsule['protected_ranges']:
            role=row['role'];a=_number(row['address']);size=row['length']
            if not isinstance(role,str) or not role or role in role_ranges or type(size)is not int or not 1<=size<=2048:
                raise ValueError('Canonical protected source roles must be unique bounded ranges')
            role_ranges[role]=(a,size)
        def check_roles(rows):
            actual={}
            for row in rows:
                if row.get('role')in actual:raise ValueError('Duplicate protected observation role')
                actual[row.get('role')]=(_number(row['address']),len(bytes.fromhex(row['hex'])))
            if actual!=role_ranges:raise ValueError('Protected code/data roles differ from their canonical source ranges')
        check_roles(capsule['steps'][0]['protected_before'])
        labelled_code={a+k for role,(a,size)in role_ranges.items() if role.endswith('code') for k in range(size)}
        if not set(subject_code)<=labelled_code:
            raise ValueError('Every authored DLL code byte requires its explicit code-epoch identity')
        if not (set(subject_code)|set(subject_globals))<=protected.keys() or set(protected)&set(range(low,high)):
            raise ValueError('Protected source images/globals are incomplete or alias dispatcher stack')
        seh=set(range(teb,teb+8))
        if (seh&protected.keys() or low<teb+8 and teb<high
                or any(lb<=a<lb+lm['size'] or sb<=a<sb+sm['size'] for a in seh)
                or low<lb+lm['size'] and lb<high or low<sb+sm['size'] and sb<high):
            raise ValueError('Dispatcher stack/TEB exception chain aliases protected or executable source memory')
        steps=capsule['steps']
        if not isinstance(steps,list) or not 1<=len(steps)<=2048: raise ValueError('Loader capsule exceeds 2048 steps')
        spans=capsule['callback_spans'];callbacks=capsule['callbacks']
        if len(spans)!=2 or len(callbacks)!=2 or [s['role'] for s in spans]!=['tls-'+phase,'dll-'+phase]:
            raise ValueError('The capsule must dispatch exactly its source TLS callback followed by DllMain')
        proofs=[];pred_globals=dict(subject_globals);pred_code=dict(contract['entry_code'])
        for span,callback in zip(spans,callbacks,strict=True):
            first,last=span['first_step'],span['last_step'];body=steps[first:last+1]
            if not body or callback['entry']!=body[0]['event']['registers'] or callback['exit']!=body[-1]['after']:
                raise ValueError('Callback contract is detached from its exact capsule span')
            if len(callback['steps'])!=len(body) or any(c['event']!=s['event'] or c['after']!=s['after']
                    for c,s in zip(callback['steps'],body,strict=True)):
                raise ValueError('A callback view rewrites its original native instructions')
            sp=_number(callback['entry']['general']['rsp']);ret=_number(callback['return_address'])
            cc={'phase':span['role'],'source_sha256':contract['subject_source_sha256'],'module':sm,'symbols':symbols,
                'entry_memory':_rows(pred_globals|{sp+k:b for k,b in enumerate(ret.to_bytes(8,'little'))}),
                'entry_code':pred_code,'entry_rsp':hex(sp),'return_address':hex(ret),'reason':reason}
            proof=validate_dll_callback(callback,contract=cc,timeout_ms=min(timeout_ms,10000))
            if proof['status']!='proved_for_authored_dll_callback': raise ValueError('Authored callback contract was not proved: '+proof.get('reason',proof['status']))
            post=_cells(proof['post_memory']);pred_globals={a:post[a] for a in subject_globals}
            pred_code=proof['post_code']|{'sha256':hashlib.sha256(bytes.fromhex(proof['post_code']['hex'])).hexdigest()}
            proofs.append(proof)
        import z3 as z
    except (ValueError,TypeError,KeyError,IndexError,ImportError) as error:
        return result|{'reason':str(error)}
    deadline=time.monotonic()+timeout_ms/1000
    names=sorted(register_names(64)-{'rip','rflags'});initial={n:z.BitVec('loader_entry_'+n,64) for n in names}
    initial_flags=z.BitVec('loader_entry_flags',32)
    owned=set(subject_globals);seh_cells=set(range(teb,teb+8));symbolic_cells=owned|seh_cells
    ram={a:z.BitVec(f'loader_entry_ram_{a:x}',8) if a in symbolic_cells else z.BitVecVal(b,8) for a,b in initial_bytes.items()}
    original=dict(ram);regs=dict(initial);flags=initial_flags;undefined=0;opaque_symbols={};samples=[]
    count=z.Concat(*[ram[symbols['dll_event_count']+k] for k in (3,2,1,0)])
    assumptions=[initial['rsp']==stack,initial['rcx']==wm,z.Extract(31,0,initial['rdx'])==reason,
                 (initial_flags&2)==2,z.ULE(count,6)]
    samples=[(v,z.BitVecVal(_number(entry['general'][n]),64)) for n,v in initial.items()]+[(initial_flags,z.BitVecVal(_number(entry['rflags']),32))]
    samples += [(ram[a],z.BitVecVal(initial_bytes[a],8)) for a in symbolic_cells]
    cache={};solver=z.Solver();domains=[];obligations=[];all_accesses=[];call_stack=[];calls=[];callback_calls=[];written=set();seen_bytes={}
    def observed(value):
        if z.is_bv_value(value): return value.as_long()
        key=value.get_id()
        if key not in cache:
            evaluated=z.simplify(z.substitute(value,*samples))
            if not z.is_bv_value(evaluated): raise ValueError('A native loader expression is not concrete')
            cache[key]=(value,evaluated.as_long())
        return cache[key][1]
    def query(claim):
        remaining=int((deadline-time.monotonic())*1000)
        if remaining<=0: raise ValueError('Loader formal proof deadline exhausted')
        solver.set(timeout=remaining);solver.push();solver.add(*assumptions,claim);answer=solver.check()
        model=solver.model() if answer==z.sat else None;solver.pop()
        if answer==z.unknown: raise ValueError('Loader formal solver returned unknown')
        return answer,model
    def sample_error(message): raise ValueError(message)
    def simplify(value):
        return z.simplify(z.substitute(value,(initial['rsp'],z.BitVecVal(stack,64)),(initial['rcx'],z.BitVecVal(wm,64))))
    def word(address,width): return ram[address] if width==1 else z.Concat(*[ram[address+k] for k in reversed(range(width))])
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
    try:
        if int.from_bytes(bytes(initial_bytes[symbols['dll_event_count']+k] for k in range(4)),'little')>6:
            raise ValueError('Two source callbacks require predecessor event_count 0..6')
        if query(z.BoolVal(True))[0]!=z.sat: raise ValueError('Infeasible dispatcher entry contract')
        spans_by_first={s['first_step']:s for s in spans};span_by_index={i:s for s in spans for i in range(s['first_step'],s['last_step']+1)}
        first_seen={_number(a):i for a,i in capsule['first_seen_steps'].items()}
        if set(first_seen)!=set(ram) or any(type(i)is not int or not 0<=i<=len(steps) for i in first_seen.values()):
            raise ValueError('Initial-memory first-observation ledger is incomplete')
        initial_seen={a for a,i in first_seen.items() if i==0}
        code_images=lambda rows:[deepcopy(r) for r in rows if (r.get('role') or '').endswith('code')]
        epochs=[{'after_step':0,'images':code_images(steps[0]['protected_before'])}]
        ranges=[]
        for a in sorted(ram):
            if ranges and ranges[-1][1]==a:ranges[-1][1]+=1
            else:ranges.append([a,a+1])
        for index,step in enumerate(steps):
            if time.monotonic()>=deadline: raise ValueError('Loader symbolic model deadline exhausted')
            event,after=step['event'],step['after'];validate_context(event['registers'],64);validate_context(after,64)
            if (event.get('project_address')is not None or event['identity'].get('project_address')is not None
                    or event['identity'].get('source_version')!=1 or event['identity'].get('runtime_address')!=event['address']
                    or event['observation'].get('instruction_completed')is not True
                    or event['registers']['thread']!=entry['thread'] or after['thread']!=entry['thread']
                    or (index and event['registers']!=steps[index-1]['after'])
                    or (index==0 and event['registers']!=entry)):
                raise ValueError('Raw foreign loader context/identity/continuity differs')
            address=_number(event['address']);raw=bytes.fromhex(event.get('execution_bytes',event['bytes']));read=step['code_read']
            rd=bytes.fromhex(read['hex'])
            if (read['address']!=event['address'] or hashlib.sha256(rd).hexdigest()!=read['sha256'] or not rd.startswith(raw)
                    or event.get('ram_bytes',raw.hex())!=raw.hex()): raise ValueError('Exact hashed loader code read differs')
            is_subject=sb<=address<sb+sm['size'];owner=sm if is_subject else lm
            if any(read['module'].get(k)!=owner.get(k) for k in ('name','base','size','bits','generation')):
                raise ValueError('An instruction has a different loaded source owner')
            if is_subject:
                if index not in span_by_index: raise ValueError('An undeclared authored callback entered the capsule')
                if any(address+k not in subject_code for k in range(len(raw))): raise ValueError('Authored callback code escaped its source image')
                obligations.append(('callback_fetch',index,z.And(*domains),z.And(*[ram[address+k]==b for k,b in enumerate(raw)])))
            else:
                if not (lb<=address and address+len(raw)<=lb+lm['size']): raise ValueError('Loader PC escapes its mapped source')
                actual=bytes(pe.get_content_from_virtual_address(pe.imagebase+address-lb,len(raw)))
                if actual!=raw: raise ValueError('Executed Wine instruction differs from original preserved ntdll PE bytes')
            native=list(decoder.disasm(raw,address))
            if len(native)!=1 or native[0].size!=len(raw): raise ValueError('Loader bytes do not decode exactly')
            ins=native[0];seq=address+len(raw);pc_after=_number(after['rip']);access_position=0;current_accesses=[]
            def access(kind,pointer,width,value=None):
                nonlocal access_position
                pointer=simplify(pointer);a=observed(pointer)
                if width not in (1,2,4,8,16) or a+width>1<<64 or any(a+k not in ram for k in range(width)):
                    raise ValueError('Decoded loader memory access escapes the complete observed union')
                valid=z.Or(*[z.And(z.UGE(pointer,start),z.ULE(pointer,end-width)) for start,end in ranges if end-start>=width])
                obligations.append(('memory_safety',index,z.And(*domains),valid))
                if access_position>=len(step['accesses']):raise ValueError('A decoded loader access is missing')
                ledger=step['accesses'][access_position];access_position+=1
                if (ledger['kind']!=kind or _number(ledger['address'])!=a or ledger['width']!=width):raise ValueError('Native memory access ledger differs from actual operand semantics')
                def byte(pointer):
                    p=z.simplify(pointer)
                    if z.is_bv_value(p):return ram[p.as_long()]
                    out=z.BitVecVal(0,8)
                    for aa in owned:out=z.If(pointer==aa,ram[aa],out)
                    return out
                if not z.is_bv_value(pointer):
                    obligations.append(('symbolic_owned_address',index,z.And(*domains),z.And(z.UGE(pointer,min(owned)),z.ULE(pointer,max(owned)-width+1))))
                old=byte(pointer) if width==1 else z.Concat(*[byte(pointer+k) for k in reversed(range(width))])
                if observed(old).to_bytes(width,'little')!=bytes.fromhex(ledger['before_hex']):raise ValueError('Native operand before value differs')
                for k in range(width):
                    if first_seen[a+k]>index:raise ValueError('A memory cell was used before its first-observation declaration')
                if kind=='write':
                    if value is None:raise ValueError('Missing loader store value')
                    if value.size()!=8*width:raise ValueError('Store width differs')
                    if index not in span_by_index:
                        stack_write=z.And(z.UGE(pointer,low),z.ULE(pointer,high-width))
                        seh_write=z.And(pointer==teb,width==8)
                        obligations.append(('dispatcher_owned_frame',index,z.And(*domains),z.Or(stack_write,seh_write)))
                    if z.is_bv_value(pointer):
                        for k in range(width):ram[a+k]=z.Extract(k*8+7,k*8,value)
                    else:
                        for k in range(width):
                            for aa in owned:ram[aa]=z.If(pointer+k==aa,z.Extract(k*8+7,k*8,value),ram[aa])
                    written.update(range(a,a+width))
                final=value if kind=='write' else old
                current_accesses.append((kind,pointer,width,final));all_accesses.append((index,kind,pointer,width,final))
                return old
            def on_call(target,seq,frame):
                obligations.append(('call_target',index,z.And(*domains),target==pc_after))
                call_stack.append((seq,frame))
                calls.append({'step':index,'target':hex(pc_after),'return_address':hex(seq),
                    'target_expression':target,'entry_arguments':{n:regs[n] for n in ('rcx','rdx','r8','r9','rsp')}})
                if pc_after in (symbols['dll_tls_callback'],symbols['dll_entry']):
                    role='tls-'+phase if pc_after==symbols['dll_tls_callback'] else 'dll-'+phase
                    obligations.append(('callback_arguments',index,z.And(*domains),z.And(regs['rcx']==sb,z.Extract(31,0,regs['rdx'])==reason,
                        regs['r8']==0 if role.startswith('tls-') else regs['r8']==initial['r8'])))
                    callback_calls.append(role)
                return pc_after
            def on_return(target,frame):
                if call_stack:
                    ret,saved=call_stack.pop();obligations.append(('internal_return',index,z.And(*domains),z.And(frame==saved,target==ret)))
                    return ret
                if index!=len(steps)-1:raise ValueError('Outer loader RET is not final')
                obligations.append(('outer_return',index,z.And(*domains),z.And(frame==stack,target==caller)))
                return caller
            def fresh_af():
                fresh=z.Bool(f'loader_undefined_af_{index}');opaque_symbols[str(fresh)]='Bool'
                return fresh
            def opaque_store(width):
                symbol=z.BitVec(f'loader_opaque_fp_store_{index}',8*width)
                opaque_symbols[str(symbol)]=8*width
                ledger=step['accesses'][access_position]
                samples.append((symbol,z.BitVecVal(int.from_bytes(bytes.fromhex(ledger['after_hex']),'little'),8*width)))
                return symbol
            flags,undefined,expected_pc=typed_loader_step(ins,z=z,registers=regs,flags=flags,undefined=undefined,
                teb=teb,access=access,simplify=simplify,fresh_af=fresh_af,opaque_store=opaque_store,
                on_call=on_call,on_return=on_return,on_branch=domains.append,
                native_flags=_number(event['registers']['rflags']))
            if expected_pc!=pc_after or access_position!=len(step['accesses']):raise ValueError('Native PC or complete access footprint disagrees with typed loader transfer')
            # Every ledger after_hex is sampled after the *whole* instruction,
            # including the read row of a read/modify/write memory operation.
            for ledger in step['accesses']:
                a,w=_number(ledger['address']),ledger['width']
                if observed(word(a,w)).to_bytes(w,'little')!=bytes.fromhex(ledger['after_hex']):
                    raise ValueError('Native complete-instruction memory after value differs')
            if any(observed(regs[n])!=_number(after['general'][n]) for n in names) or observed(flags&(0xffffffff^undefined))!=_number(after['rflags'])&(0xffffffff^undefined):
                raise ValueError('Native GPR/defined FLAGS disagree with loader transfer')
            before_protected=_cells(step['protected_before']);after_protected=_cells(step['protected_after'])
            check_roles(step['protected_before']);check_roles(step['protected_after'])
            if set(before_protected)!=set(protected) or set(after_protected)!=set(protected):raise ValueError('Per-step protected source frame is incomplete')
            if index and before_protected!=_cells(steps[index-1]['protected_after']):raise ValueError('Protected memory continuity differs')
            if any(observed(ram[a])!=b for a,b in after_protected.items()):raise ValueError('Native protected post-state disagrees with the symbolic transfer')
            before_images,after_images=code_images(step['protected_before']),code_images(step['protected_after'])
            code_write=any(a['kind']=='write' and any(_number(r['address'])<_number(a['address'])+a['width'] and
                _number(a['address'])<_number(r['address'])+len(r['hex'])//2 for r in before_images) for a in step['accesses'])
            if code_write or before_images!=after_images:
                epochs.append({'after_step':index+1,'images':after_images,'classified_code_write':code_write})
        if call_stack or steps[-1]['after']!=ending or callback_calls!=['tls-'+phase,'dll-'+phase]:raise ValueError('Dispatcher call/RET coverage or callback order is incomplete')
        if capsule['code_versions']!=epochs:raise ValueError('Every code-writing instruction and intermediate code epoch must be preserved exactly')
        if any(observed(ram[a])!=b for a,b in exit_bytes.items()):raise ValueError('Native complete exit-memory ledger differs')
        for kind,index,prefix,valid in obligations:
            status,model=query(z.And(prefix,z.Not(valid)))
            if status!=z.unsat:
                value=lambda v:hex(model.eval(v,model_completion=True).as_long())
                return result|{'reason':'Unproved loader obligation: '+kind,'counterexample':{'step':index,'entry_general':{n:value(v) for n,v in initial.items()}}}
        if query(z.Not(z.And(*domains)))[0]!=z.unsat:raise ValueError('Captured dispatcher path does not cover all admitted callback inputs')
        expected_owned=_cells([proofs[-1]['post_code']])
        # Generic postconditions come from the independently proved callback
        # transfers; the complete instruction model must establish them too.
        for n in ('rbx','rbp','rdi','rsi','r12','r13','r14','r15'):
            if query(regs[n]!=initial[n])[0]!=z.unsat:raise ValueError('Dispatcher fails its nonvolatile register frame')
        if query(z.Or(regs['rsp']!=initial['rsp']+8,regs['rax']!=0))[0]!=z.unsat:
            raise ValueError('Normal source DLL initialization did not return STATUS_SUCCESS in its balanced frame')
        immutable=set(protected)-owned-set(subject_code)
        if query(z.Or(*[ram[a]!=original[a] for a in immutable]))[0]!=z.unsat:
            raise ValueError('Dispatcher failed protected-image noninterference')
        if any(query(ram[a]!=b)[0]!=z.unsat for a,b in expected_owned.items()):raise ValueError('Dispatcher does not establish its callback-derived code epoch')
        if query(z.Or(*[ram[a]!=original[a] for a in seh_cells]))[0]!=z.unsat:
            raise ValueError('Normal dispatcher path does not restore the arbitrary prior TEB exception chain')
        specialize=[(ramvar,z.BitVecVal(initial_bytes[a],8)) for a,ramvar in original.items() if a in symbolic_cells]
        post={}
        for a in protected:
            value=z.simplify(z.substitute(ram[a],*specialize))
            if not z.is_bv_value(value):raise ValueError('Exact predecessor does not specialize protected loader output')
            post[a]=value.as_long()
        if any(post[a]!=b for a,b in pred_globals.items()):raise ValueError('Callback-derived exact global invariant and full dispatcher transfer differ')
        text=lambda v:z.simplify(v).sexpr()
        result.update(status='proved_for_observed_wine_loader_capsule',phase=phase,
            symbols={**{str(v):64 for v in initial.values()},str(initial_flags):32,
                     **{str(original[a]):8 for a in symbolic_cells},**opaque_symbols},
            source={'capsule_sha256':_digest(capsule),'contract_sha256':_digest(contract),
                'loader_source_sha256':contract['loader_source_sha256'],'subject_source_sha256':contract['subject_source_sha256'],
                'controller_source_sha256':contract['controller_source_sha256']},
            callback_contracts=proofs,calls=[{**{k:v for k,v in c.items() if k not in ('target_expression','entry_arguments')},
                'target_expression':text(c['target_expression']),
                'entry_arguments':{n:text(v) for n,v in c['entry_arguments'].items()}} for c in calls],
            opaque_context_store_symbols=opaque_symbols,
            transfer={'registers':{n:text(regs[n]) for n in names},'flags':text(flags&(0xffffffff^undefined)),
                'defined_flags_mask':0xffffffff^undefined,'globals':{hex(a):text(ram[a]) for a in sorted(owned)},
                'protected_memory':{hex(a):text(ram[a]) for a in sorted(protected)},
                'teb_exception_chain':{hex(a):text(ram[a]) for a in sorted(seh_cells)},
                'ordered_accesses':[{'step':i,'kind':k,'address':text(a),'width':w,'value':text(v)} for i,k,a,w,v in all_accesses],
                'post_code':proofs[-1]['post_code'],'guard':text(z.And(*domains))},
            post_protected_memory=_rows(post),post_globals=_rows({a:post[a] for a in owned}),
            code_versions=epochs,
            checks={'instructions':len(steps),'accesses':len(all_accesses),'prior_guard_obligations':len(obligations),
                'path_cover':'complete','tls_callback_then_dllmain':'proved_from_source_metadata_and_native_indirect_calls',
                'protected_memory':'Only independently proved authored callbacks may write protected globals/code',
                'directory_getter':'Actual complete captured PE-header lookup; no getter summary assumed',
                'context_save':'Exact GPR/RET/footprint with opaque unobserved floating context store values'},
            remaining_assumptions=['Observed Win64 GS/TEB convention','Nonexception normal mapped-PE path',
                'Correct initial source-linked WINE_MODREF/PE metadata and valid stack memory',
                'Outer loader scheduling, other modules, faults, concurrency and uncovered intervals remain unproved'])
        result['sha256']=_digest(result)
        return result
    except (ValueError,TypeError,KeyError,IndexError) as error:
        return result|{'reason':str(error)}


def expand_wine_loader_contract(proof,capsule,contract):
    if (proof.get('status')!='proved_for_observed_wine_loader_capsule'
            or proof.get('sha256')!=_digest({k:v for k,v in proof.items() if k!='sha256'})
            or proof.get('source',{}).get('capsule_sha256')!=_digest(capsule)
            or proof['source'].get('contract_sha256')!=_digest(contract)):
        raise ValueError('Exact original loader capsule and source contract required')
    return {'capsule':deepcopy(capsule),'contract':deepcopy(contract)}
