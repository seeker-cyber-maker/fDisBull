"""Compose proved authored DLL callbacks and exact Wine APIs at real boundaries.

The environment may create fresh callback frames and machine contexts. Only
the caller's explicit owned-memory frame crosses those opaque loader/exit gaps.
This is conditional whole-module recovery, never a proof of Wine's loader.
"""
from copy import deepcopy
import hashlib
import time

from .pe_region_equivalence import _digest, _contract, _execute


ENVIRONMENT = {
    'dispatch': 'observed_single_thread_tls_dllmain_process_lifetime',
    'memory_frame': 'preserve_owned_images_globals_and_iat_between_callbacks',
    'initial_iat_binding': 'observed_named_exports_before_pe_entry',
    'wine_api_frame': 'fixed_verified_code_and_readonly_thunk_words',
    'termination': 'observed_exitprocess_no_return_low32_rcx',
    'segment_binding': 'explicit_win64_gs_teb_convention',
}
SCOPE = ('Whole authored PE64 module including the imported authored DLL TLS/DllMain '
         'initialization, report and teardown, and the exact captured Wine Set/GetLastError '
         'bodies, conditional on explicit loader dispatch, owned-memory frame, GS/TEB and '
         'ExitProcess terminal contracts; other loader/DLL/OS effects remain unproved')


def _id(reference):
    return reference['artifact'] if isinstance(reference, dict) else reference


def _cells(rows):
    result = {}
    for row in rows:
        address, raw = int(row['address'], 16), bytes.fromhex(row['hex'])
        if address < 0 or address + len(raw) > 1 << 64:
            raise ValueError('Composition memory wraps')
        for offset, byte in enumerate(raw):
            if address + offset in result:
                raise ValueError('Composition memory overlaps')
            result[address + offset] = byte
    return result


def _rows(cells):
    rows = []
    for address, byte in sorted(cells.items()):
        if rows and int(rows[-1]['address'], 16) + len(rows[-1]['hex']) // 2 == address:
            rows[-1]['hex'] += f'{byte:02x}'
        else:
            rows.append({'address': hex(address), 'hex': f'{byte:02x}'})
    return rows


def _admit_call_binding(bound, call, implementation=None):
    """Join the selected summary to the source import and immutable boundary."""
    docs, recovery = bound['documents'], bound['report']['recovery']
    name = call['name']
    imports = bound['exe']['imports']
    if name not in imports:
        raise ValueError('An external summary has no source import identity')
    bindings = {r['name']: r for r in docs[_id(recovery['bindings'])]['imports']}
    if (name not in bindings or call['iat_address'] != imports[name]['iat_address']
            or call['iat_address'] != bindings[name]['iat_address']
            or call['target'] != bindings[name]['target']):
        raise ValueError('Call name, IAT slot and target differ from the source-bound entry import')
    entry = docs[_id(recovery['entry'])]
    slot = int(call['iat_address'],16); cells = _cells(entry['memory'])
    if any(slot+k not in cells for k in range(8)) or int.from_bytes(bytes(cells[slot+k] for k in range(8)),'little') != int(call['target'],16):
        raise ValueError('Entry snapshot IAT bytes do not establish the selected call binding')
    if implementation is not None:
        imported=implementation['import']
        if (imported['name']!=name or imported['runtime_iat_address']!=call['iat_address']
                or imported['target']!=call['target'] or imported['callsite']!=call['callsite']
                or imported['return_address']!=call['return_address']):
            raise ValueError('API summary name/frame/IAT differs from its verified implementation')
    else:
        if call['entry'] is None or docs[_id(call['entry'])]['registers']['rip'] != call['target']:
            raise ValueError('A source import summary enters a different actual callee')


def _require_owned_poststate(z, memory, expected, prove):
    if not set(expected)<=memory.keys():
        raise ValueError('Teardown preconditions escape modeled owned memory')
    try:
        prove(z.And(*[memory[a]==b for a,b in expected.items()]))
    except ValueError as error:
        raise ValueError('Authored code does not establish the universal DLL/code state required for teardown') from error


def recover_loader_module(project, dll_project, evidence, *, environment_contract, timeout_ms=10000):
    """Recompute all contracts from immutable evidence before composing them.

    A proof attachment is never accepted as an axiom. The native API and DLL
    verifiers run again, and every caller/callee join and environment frame is
    checked independently of source-level postconditions.
    """
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000:
        raise ValueError('timeout_ms must be 1..60000')
    result = {'format': 'fdisbull-pe-loader-module-recovery-1', 'status': 'unknown',
              'scope': SCOPE, 'whole_module_recovery': None, 'contraction': None}
    try:
        if environment_contract != ENVIRONMENT:
            raise ValueError('Explicit loader dispatch, owned-memory frame, terminal and GS/TEB contracts are required')
        from .runtime_loader_analysis import load_loader_evidence
        bound = load_loader_evidence(project, dll_project, evidence)
        result['evidence'] = deepcopy(bound['receipts'])
        result['environment_contract'] = deepcopy(environment_contract)
        return _recover(bound, result, time.monotonic() + timeout_ms / 1000)
    except (ValueError, TypeError, KeyError, IndexError, ImportError) as error:
        return result | {'reason': str(error)}


def expand_loader_module_contraction(contraction, evidence):
    """Expand the exact evidence bundle; checksums identify, not authenticate."""
    if (not isinstance(contraction, dict)
            or contraction.get('format') != 'fdisbull-loader-module-contraction-1'
            or contraction.get('evidence_sha256') != _digest(evidence)):
        raise ValueError('Exact original loader-module evidence is required')
    body = {k: v for k, v in contraction.items() if k != 'sha256'}
    if contraction.get('sha256') != _digest(body):
        raise ValueError('Loader-module contraction identity differs')
    return deepcopy(evidence)


def _recover(bound, result, deadline):
    import z3 as z
    from .pe_dll_contracts import validate_dll_callback
    from .wine_api_contracts import validate_wine_api_contract
    documents, report = bound['documents'], bound['report']
    recovery = report['recovery']
    get = lambda ref: documents[_id(ref)]
    dll, exe = bound['dll'], bound['exe']
    protected = {int(r['address'], 16)+k for r in recovery['protected_ranges'] for k in range(r['length'])}
    ds = {k: int(v, 16) for k, v in dll['symbols'].items()}
    source_globals = _cells([dll['globals']])
    code = deepcopy(dll['code'])
    callbacks, proofs = [], []
    roles = []
    for reference in report['callbacks']:
        observation = get(reference)
        ip = int(observation['entry']['rip'], 16)
        reason = int(observation['entry']['general']['rdx'], 16) & 0xffffffff
        role = ('report' if ip == ds['dll_report'] else
                'tls-' + ('attach' if reason == 1 else 'detach') if ip == ds['dll_tls_callback'] else
                'dll-' + ('attach' if reason == 1 else 'detach') if ip == ds['dll_entry'] else None)
        if role is None or (role != 'report' and reason not in (0, 1)):
            raise ValueError('An unmodeled callback dispatch cannot be composed')
        stack = int(observation['entry']['general']['rsp'], 16)
        if set(range(stack,stack+8)) & protected:
            raise ValueError('A loader callback return frame aliases an owned image, global or IAT')
        # The return word belongs to this invocation's fresh frame. Only the
        # previously proved global/code invariant is carried across the loader.
        caller = int(observation['return_address'], 16)
        contract = {'phase': role, 'source_sha256': dll['sha256'], 'module': dll['module'],
            'symbols': deepcopy(dll['symbols']), 'entry_rsp': hex(stack), 'return_address': hex(caller),
            'reason': None if role == 'report' else reason,
            'entry_memory': _rows(source_globals | {stack+k: b for k, b in enumerate(caller.to_bytes(8, 'little'))}),
            'entry_code': dict(code, sha256=hashlib.sha256(bytes.fromhex(code['hex'])).hexdigest())}
        remaining = int((deadline-time.monotonic())*1000)
        if remaining < 1: raise ValueError('Loader module proof deadline exhausted')
        proof = validate_dll_callback(observation, contract=contract, timeout_ms=min(remaining, 10000))
        if proof['status'] != 'proved_for_authored_dll_callback':
            raise ValueError('DLL callback contract was not proved: ' + proof.get('reason', proof['status']))
        post = _cells(proof['post_memory'])
        source_globals = {a: post[a] for a in source_globals}
        code = deepcopy(proof['post_code'])
        callbacks.append({'artifact': _id(reference), 'observation': observation, 'proof': proof})
        proofs.append(proof); roles.append(role)
    if roles[:3] != ['tls-attach', 'dll-attach', 'report'] or sorted(roles[3:]) != ['dll-detach', 'tls-detach']:
        raise ValueError('The source module requires one attach pair, report and detach pair')
    result['dll_contracts'] = proofs
    entry_cells=_cells(get(recovery['entry'])['memory'])
    initialized_code=_cells([proofs[1]['post_code']])
    if any(entry_cells.get(a)!=b for a,b in initialized_code.items()):
        raise ValueError('Proved DLL initialization does not establish the entry code epoch')
    # Generic callback proofs above derive their next invariant, never taking
    # the next native sample as an axiom. Opaque gaps must separately satisfy
    # the explicitly assumed owned-memory frame in the observed execution.
    frame_checks = []
    exit_call = recovery['calls'][-1]
    expected_edges = [
        ('loader-to-tls-attach',None,callbacks[0]['observation']['entry']),
        ('tls-return-to-dll-attach',callbacks[0]['observation']['exit'],callbacks[1]['observation']['entry']),
        ('dll-return-to-exe-entry',callbacks[1]['observation']['exit'],get(recovery['entry'])['registers']),
        ('exit-to-detach-0',get(exit_call['entry'])['registers'],callbacks[3]['observation']['entry']),
        ('exit-to-detach-1',callbacks[3]['observation']['exit'],callbacks[4]['observation']['entry']),
        ('detach-return-to-process-exit',callbacks[4]['observation']['exit'],None)]
    if len(recovery['transitions']) != len(expected_edges):
        raise ValueError('Every opaque loader/exit gap requires its own ordered frame contract')
    for reference,(label,before_context,after_context) in zip(recovery['transitions'],expected_edges,strict=True):
        transition = get(reference)
        before = get(transition['before'])
        if transition['label']!=label or (before_context is not None and before['registers']!=before_context):
            raise ValueError('An opaque environment edge is detached from its proved predecessor')
        if after_context is not None and (transition['after'] is None or get(transition['after'])['registers']!=after_context):
            raise ValueError('An opaque environment edge is detached from its next actual invocation')
        a = _cells(before['memory'])
        if transition['after'] is None:
            if transition['outcome']['outcome'] != 'exited' or transition['outcome']!=report['terminal']:
                raise ValueError('A terminal environment edge needs a real process exit')
            frame_checks.append({'artifact': _id(reference), 'label': transition['label'],
                'status': 'terminal_receipt', 'postmortem_memory': 'unavailable'})
            continue
        after = get(transition['after']); b = _cells(after['memory'])
        # Before application entry the loader is allowed to resolve the EXE's
        # imports. The source-bound entry binding, not a guessed preservation
        # rule, establishes those words for authored code. The DLL has no imports.
        framed = protected - {int(r['address'],16)+k for r in recovery['protected_ranges']
            if r['role'].startswith('iat-') for k in range(r['length'])} if len(frame_checks)<3 else protected
        if not framed <= a.keys() or not framed <= b.keys() or any(a[p] != b[p] for p in framed):
            raise ValueError('Observed loader/ExitProcess execution violates the declared owned-memory frame')
        frame_checks.append({'artifact': _id(reference), 'label': transition['label'],
            'status': 'observed_frame_agreement', 'proof_status': 'explicit_environment_assumption',
            'preserved_bytes': len(framed), 'machine_context': 'fresh, not preserved',
            'import_binding': 'observed entry initialization' if len(frame_checks)<3 else 'preserved'})
    result['environment_edges'] = frame_checks
    api_proofs = {}
    api_fixed={}
    for reference in report['apis']:
        document = get(reference)
        proof = validate_wine_api_contract(document)
        if proof['status'] != 'proved_for_observed_implementation':
            raise ValueError('An actual Wine API contract did not reverify')
        api_proofs[_id(reference)] = proof
        info=document['implementation']['thread_info'];teb=int(info['teb'],16)
        frame=int(document['contexts']['entry']['general']['rsp'],16)
        private=_cells(document['implementation']['memory']['entry'])
        exempt=set(range(teb+0x30,teb+0x38)) | set(range(teb+0x68,teb+0x6c)) | set(range(frame,frame+8))
        private={a:b for a,b in private.items() if a not in exempt}
        for row in document['implementation']['code_reads']:
            for k,b in enumerate(bytes.fromhex(row['hex'])):
                a=int(row['address'],16)+k
                if a in private and private[a]!=b:raise ValueError('Verified API code and thunk words alias inconsistently')
                private[a]=b
        if set(private)&protected or set(private)&set(entry_cells):
            raise ValueError('Verified Wine implementation aliases authored code, globals, IAT or environment frame')
        for a,b in private.items():
            if a in api_fixed and api_fixed[a]!=b:
                raise ValueError('Wine code or readonly thunk preconditions change between verified calls')
            api_fixed[a]=b
    if len(api_proofs) != 8:
        raise ValueError('Whole module recovery needs all eight actual last-error calls')
    calls=recovery['calls']
    if ([c['name'] for c in calls] != ['dll_report', *['SetLastError','GetLastError']*4, 'ExitProcess']
            or [_id(c['implementation']) for c in calls if c['name'] in ('SetLastError','GetLastError')]
                != [_id(r) for r in report['apis']]
            or _id(calls[0]['callback']) != callbacks[2]['artifact']):
        raise ValueError('Every source call requires its own ordered proved implementation or callback')
    main = _main(z, bound, callbacks[2], api_proofs, deadline)
    # Main must begin with the state derived by the two initialization proofs.
    initial_dll = _cells(proofs[1]['post_memory'])
    entry_memory = _cells(get(recovery['entry'])['memory'])
    owned_dll = set(range(ds['dll_data_start'], ds['dll_data_end']))
    if any(entry_memory[a] != initial_dll[a] for a in owned_dll):
        raise ValueError('Proved DLL initialization does not establish the EXE entry invariant')
    if main['dll_report_post_memory'] != _rows({a: _cells(proofs[2]['post_memory'])[a] for a in owned_dll}):
        raise ValueError('Authored EXE call and DLL report contract do not compose')
    terminal = report['terminal']
    if terminal['outcome'] != 'exited' or terminal['session']['exit_code'] != main['exit_code']:
        raise ValueError('Proved ExitProcess argument and actual process exit differ')
    result.update(status='recovered_under_environment_contract', whole_module_recovery={
        'main': main, 'final_dll_memory': _rows(source_globals), 'final_dll_code': code,
        'exit_code': main['exit_code'], 'initialization': 'derived from original DLL globals and proved attach transfers',
        'teardown_order': roles[3:], 'termination': 'bounded authored paths; terminal environment contract and actual exit receipt',
        'native_api_proofs': {k: v['sha256'] for k, v in api_proofs.items()},
        'wine_api_frame': {'status':'explicit_fixed_image_precondition',
            'bytes':len(api_fixed),'sha256':_digest(_rows(api_fixed)),
            'noninterference':'Disjoint from all declared authored/main memory and code effects; opaque loader initialization remains conditional'},
        'callback_instruction_bound': sum(p['transfer']['termination_bound_instructions'] for p in proofs)},
        remaining_assumptions=deepcopy(ENVIRONMENT))
    contraction = {'format': 'fdisbull-loader-module-contraction-1',
        'evidence_sha256': _digest(report), 'receipts_sha256': _digest(bound['receipts']),
        'callback_contracts': [p['sha256'] for p in proofs],
        'api_contracts': {k: v['sha256'] for k, v in api_proofs.items()},
        'environment_contract': deepcopy(ENVIRONMENT), 'recovery_sha256': _digest(result['whole_module_recovery']),
        'expansion': 'Exact original reference bundle; owning project resolves its immutable native artifacts'}
    result['contraction'] = contraction | {'sha256': _digest(contraction)}
    result['sha256'] = _digest(result)
    return result


def _main(z, bound, report_callback, api_proofs, deadline):
    from .debug_semantics import normalize_trace
    from .wine_arch import register_names
    documents, report = bound['documents'], bound['report']
    recovery = report['recovery']; get = lambda ref: documents[_id(ref)]
    entry = get(recovery['entry'])
    code_ranges = [r for r in recovery['protected_ranges'] if r['role'].endswith('-code')]
    code_cells = {int(r['address'], 16)+k for r in code_ranges for k in range(r['length'])}
    entry_cells = _cells(entry['memory']); code = {a: entry_cells[a] for a in code_cells}
    addresses = sorted(set(entry_cells)-code_cells)
    stack = int(entry['registers']['general']['rsp'], 16)
    teb = int(entry['thread_info']['teb'], 16)
    free = set(range(stack-48, stack+8)) | set(range(teb+0x68, teb+0x6c))
    normalized, declared, names = _contract({'entry_registers': {'rsp': hex(stack)},
        'memory_model': 'private_ordinary_ram', 'memory_observation': 'ordered',
        'memory_ranges': [{'address': r['address'], 'length': r['length']} for r in entry['ranges']
                          if not r['role'].endswith('-code')]}, 64)
    if declared != addresses:
        raise ValueError('Main entry RAM does not cover the exact bounded contract')
    initial = {n: z.BitVec('module_entry_'+n, 64) for n in names}
    flags = z.BitVec('module_entry_flags', 32)
    memory = {a: z.BitVec(f'module_entry_ram_{a:x}', 8) if a in free else z.BitVecVal(entry_cells[a], 8)
              for a in addresses} | {a: z.BitVecVal(b, 8) for a, b in code.items()}
    assumptions = [initial['rsp']==stack, flags & 2 == 2]
    solver = z.Solver()
    def prove(claim):
        remaining = int((deadline-time.monotonic())*1000)
        if remaining < 1: raise ValueError('Whole-module proof deadline exhausted')
        solver.set(timeout=remaining);solver.push();solver.add(*assumptions, z.Not(claim))
        answer=solver.check();solver.pop()
        if answer != z.unsat: raise ValueError('A whole-module execution or contract implication is not proved')
    records=[]
    for reference in recovery['main_segments']:
        segment=get(reference)
        if segment['status']!='complete': raise ValueError('An authored module segment is incomplete')
        for i, step in enumerate(segment['steps']):
            if i and segment['steps'][i-1]['after']!=step['event']['registers']:
                raise ValueError('Authored native instruction contexts do not join')
            records.append({'sequence': bound['receipts'][_id(reference)]['sequence'], 'offset': i,
                'event': step['event'], 'after': step['after'],
                'before_memory': step['memory_before'], 'after_memory': step['memory_after']})
    for call in recovery['calls']:
        implementation=get(call['implementation']) if call['implementation'] is not None else None
        _admit_call_binding(bound,call,implementation)
        trace_ref=call['trace'] if call['trace'] is not None else get(call['implementation'])['trace']
        trace=get(trace_ref)
        if trace.get('complete') is not True or len(trace['events'])!=1:
            raise ValueError('Each import CALL requires its exact completed native instruction')
        before=get(call['before']); after=get(call['return'] if call['return'] is not None else call['entry'])
        if trace['events'][0]['registers']!=before['registers']:
            raise ValueError('A call summary is detached from its actual caller context')
        records.append({'sequence': bound['receipts'][_id(trace_ref)]['sequence'], 'offset':0,
            'event':trace['events'][0], 'after':after['registers'],
            'before_memory':before['memory'], 'after_memory':after['memory'], 'call':call})
    records.sort(key=lambda row:(row['sequence'],row['offset']))
    if not records or records[0]['event']['registers']!=entry['registers']:
        raise ValueError('Authored module recovery must start at the real PE entry')
    for left,right in zip(records,records[1:]):
        if left['after']!=right['event']['registers']:
            raise ValueError('Complete authored instruction/call-summary coverage is missing')
        if _cells(left['after_memory'])!=_cells(right['before_memory']):
            raise ValueError('An unexplained memory change separates authored instructions')
    events=[deepcopy(r['event']) for r in records]
    last=deepcopy(events[-1]);last.update(address=records[-1]['after']['rip'],project_address=None,
        registers=records[-1]['after'])
    normalize_trace('wine-qemu',[last],version=1);last['observation']['instruction_completed']=False
    events.append(last)
    checks={'snapshots':0};effects=[];exit_code=None;report_post=None
    def observe(index,stage,regs,live_flags,ram,sample):
        observed=_cells(records[index]['before_memory' if stage=='before' else 'after_memory'])
        if set(observed)!=set(ram) or any(sample(ram[a])!=b for a,b in observed.items()):
            raise ValueError('A native prefix memory snapshot contradicts whole-module recovery')
        checks['snapshots']+=1
    def handler(index,event,following,ctx):
        nonlocal exit_code,report_post
        call=records[index].get('call')
        if call is None or ctx['raw'][:2]!=b'\xff\x15' or len(ctx['raw'])!=6:
            raise ValueError('Unbound external control flow is outside whole-module recovery')
        site=int(call['callsite'],16);target=int(call['target'],16)
        if site!=int(event['address'],16) or int(call['return_address'],16)!=ctx['sequential']:
            raise ValueError('An imported CALL has a different actual return site')
        pointer,width=ctx['location'](ctx['instruction'].operands[0]);actual_target=ctx['read_memory'](pointer,width)
        prove(z.And(pointer==int(call['iat_address'],16),actual_target==target))
        caller_stack=ctx['registers']['rsp'];frame,width=ctx['memory_location'](caller_stack-8,8)
        prove((caller_stack & 15)==0)
        ctx['write_memory'](frame,8,z.BitVecVal(ctx['sequential'],64))
        callee_regs=dict(ctx['registers']);callee_regs['rsp']=frame
        effect={'name':call['name'],'callsite':hex(site),'target':hex(target),'return_address':hex(ctx['sequential'])}
        if call['name']=='dll_report':
            proof=report_callback['proof'];observation=report_callback['observation']
            _entry_join(z,callee_regs,ctx['flags'],observation['entry'],frame,proof['contract']['entry_rsp'],prove,ctx['observed'])
            for a,byte in _cells(proof['contract']['entry_memory']).items():
                if a not in ctx['memory']: raise ValueError('DLL report precondition escapes declared main memory')
                prove(ctx['memory'][a]==byte)
            current_code={
                int(proof['contract']['entry_code']['address'],16)+k:b
                for k,b in enumerate(bytes.fromhex(proof['contract']['entry_code']['hex']))}
            for a,byte in current_code.items():prove(ctx['memory'][a]==byte)
            transferred=_instantiate_dll_transfer(z,proof,callee_regs,ctx['flags'],ctx['memory'])
            for row in transferred['accesses']:
                a,w,value=row['address'],row['width'],row['value']
                location,_=ctx['memory_location'](a,w)
                if row['kind']=='read': prove(ctx['read_memory'](location,w)==value)
                else: ctx['write_memory'](location,w,value)
            for a,value in transferred['memory'].items(): prove(ctx['memory'][a]==value)
            ctx['registers'].update(transferred['registers'])
            prove(ctx['registers']['rsp']==caller_stack)
            if proof['transfer']['defined_flags_mask']!=0xffffffff:
                raise ValueError('A returning DLL summary leaves live FLAGS undefined')
            dll_data=bound['dll']['globals'];start=int(dll_data['address'],16)
            report_post=_rows({a:ctx['observed'](ctx['memory'][a]) for a in range(start,start+len(bytes.fromhex(dll_data['hex'])))})
            new_flags=transferred['flags'];effect['contract_sha256']=proof['sha256']
        elif call['name'] in ('SetLastError','GetLastError'):
            reference=_id(call['implementation']);document=get(reference);proof=api_proofs[reference]
            _entry_join(z,callee_regs,ctx['flags'],document['contexts']['entry'],frame,
                        document['contexts']['entry']['general']['rsp'],prove,ctx['observed'])
            if document['import']['target']!=hex(target) or document['import']['callsite']!=hex(site):
                raise ValueError('A verified API implementation belongs to a different call boundary')
            info=document['implementation']['thread_info']
            if int(info['teb'],16)!=teb or info['thread']!=entry['registers']['thread']:
                raise ValueError('A verified API implementation changes the selected thread/TEB')
            # Replaying the proved footprint also checks disjointness of every
            # fixed external thunk word from all caller-owned ordinary/code cells.
            for access in document['implementation']['accesses']:
                a,w=int(access['address'],16),access['width']
                cells=set(range(a,a+w))
                if cells<=ctx['memory'].keys():
                    address=z.BitVecVal(a,64)
                    if access['kind']=='write':
                        if a!=teb+0x68 or w!=4 or call['name']!='SetLastError':
                            raise ValueError('Unexpected API memory write')
                        ctx['write_memory'](address,w,z.Extract(31,0,callee_regs['rcx']))
                    else:
                        value=ctx['read_memory'](address,w)
                        if a==teb+0x30:
                            prove(value==teb)
                        elif a==int(document['contexts']['entry']['general']['rsp'],16):
                            prove(value==ctx['sequential'])
                        elif a!=teb+0x68:
                            raise ValueError('An API operand aliases unmodeled caller memory')
                elif cells & ctx['memory'].keys() or access['kind']!='read':
                    raise ValueError('An external API operand aliases caller memory or writes outside its proof')
            ctx['registers']['rax']=(z.BitVecVal(teb,64) if call['name']=='SetLastError' else
                z.ZeroExt(32,z.Concat(*[ctx['memory'][teb+0x68+k] for k in (3,2,1,0)])))
            new_flags=ctx['flags'];effect['contract_sha256']=proof['sha256']
            effect['implementation_footprint']=deepcopy(proof['footprint'])
        elif call['name']=='ExitProcess':
            entry_snapshot=get(call['entry'])
            _entry_join(z,callee_regs,ctx['flags'],entry_snapshot['registers'],frame,
                        entry_snapshot['registers']['general']['rsp'],prove,ctx['observed'])
            ctx['registers']['rsp']=frame
            argument=z.simplify(z.Extract(31,0,ctx['registers']['rcx']))
            if not z.is_bv_value(argument): raise ValueError('ExitProcess argument is not recovered exactly')
            exit_code=argument.as_long();effect['argument_low32']=exit_code;effects.append(effect)
            return {'flags':ctx['flags'],'terminated':True}
        else: raise ValueError('An imported call has no proved contract')
        if int(following['address'],16)!=ctx['sequential']:
            raise ValueError('A proved callee does not return to the original caller')
        effects.append(effect)
        return {'flags':new_flags,'terminated':False}
    trace={'events':events}
    final_cells=_cells(records[-1]['after_memory'])
    modeled=_execute(z,trace,64,initial,flags,memory,normalized,
        (entry_cells,final_cells),'loader_module',deadline,execution_code=code,
        external_handler=handler,state_observer=observe)
    if not modeled['terminated'] or exit_code is None:
        raise ValueError('A complete module must reach its observed terminal API')
    for obligation in modeled['proof_obligations']+modeled['safety']:
        prove(z.Implies(obligation['prefix'],obligation['valid']))
    prove(modeled['domain'])
    # A native sample can hide a symbolic store that happens to preserve a
    # value. Teardown may consume the report postcondition only after proving
    # its complete owned state for every admitted application entry state.
    dll_start=int(bound['dll']['globals']['address'],16)
    dll_length=len(bytes.fromhex(bound['dll']['globals']['hex']))
    after_report=_cells(report_callback['proof']['post_memory'])
    expected_owned={a:after_report[a] for a in range(dll_start,dll_start+dll_length)} | code
    expected_owned.update({int(r['address'],16)+k:entry_cells[int(r['address'],16)+k]
        for r in recovery['protected_ranges'] if r['role'].startswith('iat-') for k in range(r['length'])})
    _require_owned_poststate(z,modeled['memory'],expected_owned,prove)
    text=lambda v:z.simplify(v).sexpr()
    data=bound['exe']['globals'];start=int(data['address'],16)
    final_data={}
    for a in range(start,start+len(bytes.fromhex(data['hex']))):
        byte=z.simplify(modeled['memory'][a])
        if not z.is_bv_value(byte):
            raise ValueError('This bounded module profile requires an exact recovered final global image')
        final_data[a]=byte.as_long()
    return {'registers_at_exit_api_entry':{n:text(modeled['registers'][n]) for n in names},
        'flags_at_exit_api_entry':text(modeled['flags']),
        'memory_at_exit_api_entry':{hex(a):text(modeled['memory'][a]) for a in addresses},
        'exe_memory':_rows(final_data),
        'dll_report_post_memory':report_post,'exit_code':exit_code,
        'teardown_precondition':'Complete DLL globals, both code images and initialized IAT universally preserved by authored main and verified calls',
        'termination_bound_authored_instructions':len(records),
        'prefix_memory_snapshots_checked':checks['snapshots'],
        'instruction_fetch_checks':modeled['fetch_checks'],
        'execution_obligations':len(modeled['proof_obligations'])+len(modeled['safety']),
        'ordered_accesses':[{'kind':k,'address':text(a),'width':w,'value':text(v)} for k,a,w,v in modeled['accesses']],
        'calls':effects,'entry_contract':normalized,
        'initial_state':'Original EXE globals, proved DLL attach state, actual resolved IAT/TEB self; stack and prior last-error symbolic',
        'last_observation':'API entry before ExitProcess teardown; final process CPU context unavailable'}


def _entry_join(z,registers,flags,observed,frame,required_rsp,prove,sample):
    if any(sample(registers[n])!=int(value,16) for n,value in observed['general'].items()) or sample(flags)!=int(observed['rflags'],16):
        raise ValueError('A callee entry context does not match its actual architectural CALL')
    prove(frame==int(required_rsp,16))


def _instantiate_dll_transfer(z,proof,registers,flags,memory):
    declarations={name:z.Bool(name) if width=='Bool' else z.BitVec(name,width) for name,width in proof['symbols'].items()}
    substitutions=[]
    for name,var in declarations.items():
        if name.startswith('dll_entry_ram_'):
            address=int(name.removeprefix('dll_entry_ram_'),16)
            if address not in memory: raise ValueError('A proved DLL operand aliases undeclared main RAM')
            substitutions.append((var,memory[address]))
        elif name=='dll_entry_flags':substitutions.append((var,flags))
        elif name.startswith('dll_entry_'):
            substitutions.append((var,registers[name.removeprefix('dll_entry_')]))
    def parse(expression,width):
        output=z.BitVec('__callback_expression',width)
        ast=z.parse_smt2_string('(assert (= __callback_expression '+expression+'))',
            decls=declarations|{'__callback_expression':output})[0].arg(1)
        return z.simplify(z.substitute(ast,*substitutions))
    transfer=proof['transfer']
    return {'registers':{n:parse(e,64) for n,e in transfer['registers'].items()},
        'flags':parse(transfer['flags'],32),
        'memory':{int(a,16):parse(e,8) for a,e in transfer['memory_bytes'].items()},
        'accesses':[{'kind':r['kind'],'address':parse(r['address'],64),'width':r['width'],
                     'value':parse(r['value'],r['width']*8)} for r in transfer['ordered_accesses']]}
