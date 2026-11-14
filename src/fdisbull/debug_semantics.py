"""Additive observation contracts. Native evidence is never replaced."""

PE_TRACE_SEMANTICS = ('instructions completed by the selected stopped thread; '
                      'pre-instruction registers; peer threads held per step')


def contract(backend):
    if backend=='scummvm-kyra':
        return {'format':'fdisbull-debug-semantics-1','backend':backend,
                'native_hooks_available':False,
                'execution_breakpoint_stage':'before EMC2 opcode; script generation + decoded DATA word',
                'watchpoint_stage':'optional instrumented VM register/game flag accessors; direct writes unobserved',
                'trace_registers_stage':'EMC2 VM state, not original x86 CPU',
                'trace_completion':'bounded VM dispatch; nested callbacks need separate completion',
                'timing':'ScummVM virtual time only when advertised; original DOS equivalence unverified',
                'address_context':'loaded EMC2 DATA words and generation, not original DOS/file offsets',
                'guest_exit_reporting':'ScummVM engine lifecycle, not original DOS process exit'}
    if backend=='scummvm-gob':
        return {'format':'fdisbull-debug-semantics-1','backend':backend,
                'native_hooks_available':False,
                'execution_breakpoint_stage':'before encoded Gob function/draw/gob opcode; inspect family and script generation',
                'watchpoint_stage':'instrumented byte-range accessor; pointer and uninstrumented bulk paths remain outside coverage',
                'trace_registers_stage':'Gob script boundary; no original CPU registers',
                'trace_completion':'correlated starts and returns; an unfinished nested caller remains incomplete',
                'timing':'ScummVM virtual milliseconds; original DOS timing equivalence unverified',
                'address_context':'source-bound loaded TOT, generation and original byte offset',
                'guest_exit_reporting':'ScummVM engine lifecycle; original DOS process exit unavailable'}
    if backend=='scummvm-agi':
        return {'format':'fdisbull-debug-semantics-1','backend':backend,
                'native_hooks_available':False,
                'execution_breakpoint_stage':'before-AGI-opcode',
                'watchpoint_stage':'instrumented AGI accessor observed at next safe point; direct raw field accesses may be unobserved',
                'trace_registers_stage':'script boundary; inspect event',
                'trace_completion':'opcode starts and completed-opcode counts; completion of a nested caller remains unknown',
                'timing':'ScummVM virtual milliseconds; original DOS timing equivalence unverified',
                'address_context':'AGI resource identity, logic number and byte offset',
                'guest_exit_reporting':'ScummVM engine lifecycle; original DOS process exit unavailable'}
    dos=backend in ('dosbox','dosbox-qemu')
    pe=backend in ('wine-qemu','ida-wine-qemu')
    machine=backend in ('qemu-machine','qemu-dos')
    return {'format':'fdisbull-debug-semantics-1','backend':backend,
            **({'native_hooks_available':True} if dos else {}),
            'execution_breakpoint_stage':'before-instruction',
            'watchpoint_stage':'after-access; instruction completion unknown' if dos else 'before-access' if backend=='wine-qemu' else 'unsupported' if backend=='ida-wine-qemu' else 'unknown; inspect native reply',
            'trace_registers_stage':'before-instruction',
            'trace_completion':'fetch-observed; completion unknown' if dos else 'native step stops; instruction completion unknown' if machine else 'confirmed completed steps',
            'timing':'guest ticks supported' if dos else 'host bounded; stepping has no elapsed-time fidelity',
            'address_context':'explicit CPU address space; DOS paragraph projection requires observed real mode' if dos else 'selected process virtual address' if pe else 'selected vCPU; explicit address space',
            'guest_exit_reporting':('Requires lifecycle.dos_guest_exit; selected DOS PSP after process cleanup; '
                                    'distinct from debugger/session shutdown') if dos else 'inspect native exit evidence'}


def normalize_stop(backend,native,*,outcome,stopped_pc=None):
    dos=backend in ('dosbox','dosbox-qemu')
    access=native.get('data_access')
    watch=bool(access) or native.get('kind')=='watchpoint'
    trigger='watchpoint' if watch else outcome
    stage='stopped; stage unknown';completed=None;cause=None
    if dos and access:
        # The pending access is consumed at the next normal-core check. REP
        # can yield there with work remaining; an interrupt can also change PC.
        # Neither an access record nor a different PC certifies completion.
        stage='after-access';cause=access.get('instruction')
    elif backend=='wine-qemu' and watch and native.get('before_access'):
        stage='before-instruction';completed=False;cause=native.get('address')
    elif trigger=='breakpoint':
        stage='before-instruction';completed=False;cause=native.get('address')
    resume_pc = stopped_pc if dos and access else native.get('address')
    result = {'format':'fdisbull-debug-stop-1','trigger':trigger,'native_kind':native.get('kind'),
            'causing_instruction':cause,'resume_pc':resume_pc,
            'instruction_completed':completed,'registers_stage':stage,
            'context':'dos-cpu' if dos else 'process' if backend in ('wine-qemu','ida-wine-qemu') else 'machine'}
    if dos:
        result['cpu_mode']=native.get('cpu_mode')
    if dos and native.get('kind') in ('guest_exit','guest_tsr') and isinstance(native.get('guest_exit'),dict):
        # DOS has restored the parent context. It is not a final instruction or
        # register snapshot of the terminated target, and TSR is not normal exit.
        result.update(guest_exit=dict(native['guest_exit']),context='dos-process',
                      registers_stage='after-process-cleanup; target registers unavailable',
                      causing_instruction=None,resume_pc=None,instruction_completed=None)
    return result


def trace_decode_bits(event):
    """Decode a DOS fetch only from that record's observed CPU mode/width."""
    mode=event.get('cpu_mode')
    if mode=='real':return 16
    bits=event.get('code_bits')
    if mode in ('protected','v86') and type(bits) is int and bits in (16,32):return bits
    return None


def normalize_trace(backend,events,*,version,delta=0,budget_reached=False):
    dos=backend in ('dosbox','dosbox-qemu')
    machine=backend in ('qemu-machine','qemu-dos')
    for index,event in enumerate(events):
        context='flat' if backend in ('wine-qemu','ida-wine-qemu') else 'machine'
        address=event.get('address')
        if dos:
            context=None
            if event.get('cpu_mode')=='real' and isinstance(address,dict) and address.get('space')=='segmented':
                cs=int(address['segment'],16)-delta//16
                context=f'real:{cs:04x}' if 0<=cs<=0xffff else None
            else:
                # A protected selector, virtual-8086 context, or legacy record
                # without mode does not establish a DOS source paragraph.
                event['project_address']=None
                if 'project_segmented_address' in event:event['project_segmented_address']=None
        event['identity']={'source_version':version,'context':context,'runtime_address':address,
                           'project_address':event.get('project_address')}
        event['observation']={'registers_stage':'before-instruction',
                              # A QEMU T05 can follow exception dispatch or one
                              # REP iteration. It does not certify retirement.
                              'instruction_completed':False if dos and budget_reached and index==len(events)-1 else None if dos or machine else True,
                              'evidence':'pending fetch at trace budget' if dos and budget_reached and index==len(events)-1 else 'native fetch' if dos else 'native step stop; instruction completion unknown' if machine else 'confirmed native step'}
    return events
