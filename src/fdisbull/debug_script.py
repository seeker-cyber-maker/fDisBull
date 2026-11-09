"""A bounded, declarative JSON language for repeatable debugger routes."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import time

from .debugger import bounded
from .operation_budget import rpc_budget

ENGINE_OPERATIONS = {
    'engine-state':'engine_state', 'engine-set':'write_engine_state',
    'step':'step', 'watchpoint':'watchpoint', 'delete-watchpoint':'delete_watchpoint',
    'engine-resource':'resource', 'engine-patch-resource':'patch_resource',
    'engine-cycle':'run_until_cycle',
    'engine-read-variable':'read_variable','engine-write-variable':'write_variable',
    'engine-hotspot-events':'hotspot_events',
    'engine-restore-resource':'restore_resource',
}

OPERATIONS = {
    **ENGINE_OPERATIONS,
    'frame-probe':'frame_probe','scene-check':'scene_check','scene-assert':'scene_assert',
    'scene-click':'scene_click','scene-act':'scene_act','scene-wait':'scene_wait',
    'keyboard.press':'keyboard_press','keyboard.type':'keyboard_type','keyboard.state':'keyboard_state',
    'keyboard.key-down':'keyboard_key_down','keyboard.key-up':'keyboard_key_up',
    'mouse.move-relative':'mouse_move_relative','mouse.button-down':'mouse_button_down','mouse.button-up':'mouse_button_up',
    'input-state':'input_state','input-cancel-pending':'input_cancel_pending',
    'input-schedule':'input_schedule','input-schedule-observe':'input_schedule_observe',
    'input-schedule-retrace':'input_schedule_retrace',
    'clock-observe':'clock_observe','clock-advance':'clock_advance','capture-surface':'capture_surface',
    'audio-start':'audio_start','audio-observe':'audio_observe','audio-stop':'audio_stop','capture-audio':'capture_audio',
    'display-start':'display_start','display-observe':'display_observe','display-stop':'display_stop','capture-display':'capture_display',
    'retrace-observe':'retrace_observe',
    'retrace-wait':'retrace_wait',
    'clock-sync-start':'clock_sync_start','clock-sync-observe':'clock_sync_observe',
    'clock-sync-step':'clock_sync_step','clock-sync-stop':'clock_sync_stop',
    'macro':'macro','move':'move','assisted-travel':'assisted_travel','proof-check':'proof_check','scene-navigation':'scene_navigation',
    'spatial-policy':'spatial_policy','spatial-action':'spatial_action',
    'bind-runtime-memory':'bind_runtime_memory','runtime-memory':'runtime_memory','write-runtime-memory':'write_runtime_memory',
    'workflow-observe':'workflow_observe','workflow-act':'workflow_act','text-observe':'text_observe','text-act':'text_act',
    'wait':'wait',
    'screenshot-hooks':'screenshot_hooks',
    'step':'step', 'run':'run', 'click':'click', 'click-frame':'click_frame', 'screenshot':'screenshot', 'trace':'trace',
    'trace-until':'trace_until',
    'breakpoint':'breakpoint', 'delete-breakpoint':'delete_breakpoint',
    'save-state':'save_state', 'load-state':'load_state',
    'save-anchor-stone':'save_anchor_stone', 'load-anchor-stone':'load_anchor_stone',
    'rewind-start':'rewind_start', 'rewind-status':'rewind_status',
    'rewind-record':'rewind_record', 'rewind':'rewind',
    'delta-start':'cpu_delta_start', 'delta-status':'cpu_delta_status',
    'delta-record':'cpu_delta_record', 'delta-rewind':'cpu_delta_rewind',
    'delta-recover':'cpu_delta_recover',
    'frame-advance':'advance_frames', 'frame-inputs':'frame_inputs',
    'timeline-start':'timeline_start', 'timeline-status':'timeline_status',
    'timeline-advance':'timeline_advance', 'timeline-rewind':'timeline_rewind',
    'timeline-stop':'timeline_stop', 'timeline-pin':'timeline_pin', 'timeline-image':'timeline_image',
    'layer-stack':'layers', 'layer-enable':'layer_enable', 'layer-patch':'layer_patch',
    'code':'code', 'capture-code':'capture_code', 'branch':'branch', 'cave':'cave', 'hook':'hook',
    'hooks':'hooks', 'delete-hook':'delete_hook',
    'registers':'registers', 'memory':'memory', 'write-memory':'write_memory','write-registers':'write_registers', 'status':'status',
    'memory-translation':'memory_translation', 'qemm-observe':'qemm_observe',
    'memory-snapshot':'memory_snapshot', 'memory-apply':'memory_apply',
    'memory-rule-tick':'memory_rule_tick', 'memory-rule-run':'memory_rule_run',
    'desqview-observe':'desqview_observe',
}


def validate_script(script, *, session=None):
    from .debugger import DebugSession
    if (not isinstance(script,dict) or not {'format','steps'}<=set(script)
            or set(script)-{'format','steps','backend'} or script['format'] != 'fdisbull-script-1'):
        raise ValueError('Script requires format=fdisbull-script-1 and steps')
    backend=script.get('backend')
    supported_backends=('wine-qemu','wine-ne','scummvm-agi','scummvm-gob','scummvm-kyra','qemu-machine','qemu-dos')
    if backend is not None and backend not in supported_backends:
        raise ValueError('Unsupported explicit script backend; omit it for the legacy DOS grammar')
    owner=session if session is not None else DebugSession
    actual=None
    if session is not None:
        actual=getattr(session,'backend_name',None) or getattr(session,'metadata',{}).get('backend')
        if actual=='wine-ne-qemu':actual='wine-ne'
    if backend is not None:
        if session is not None:
            if backend!=actual:raise ValueError('Script backend differs from the live debugger')
        elif backend=='wine-qemu':
            from .wine_debugger import PEDebugSession
            owner=PEDebugSession
        elif backend=='wine-ne':
            from .win16_debugger import Win16DebugSession
            owner=Win16DebugSession
        elif backend=='qemu-machine':
            from .qemu_machine import MachineDebugSession
            owner=MachineDebugSession
        elif backend=='qemu-dos':
            from .qemu_dos_process import QemuDOSProcessSession
            owner=QemuDOSProcessSession
        elif backend=='scummvm-kyra':
            from .scummvm_kyra import ScummVMKyraSession
            owner=ScummVMKyraSession
        elif backend=='scummvm-gob':
            from .scummvm_gob import ScummVMGobSession
            owner=ScummVMGobSession
        else:
            from .scummvm_debugger import ScummVMAGISession
            owner=ScummVMAGISession
    outcomes={'breakpoint','watchpoint','guest_time','timeout','exited','pause'}
    if (backend or actual) == 'qemu-dos':
        # DOS return/residency leave the owned machine alive. Preserve the
        # separate 'exited' outcome for native machine termination.
        outcomes|={'guest_exit','guest_tsr'}
    if (backend or actual) in ('scummvm-agi','scummvm-gob','scummvm-kyra'):
        outcomes|={'budget','cycle','layer_conflict'}
    if len(json.dumps(script,allow_nan=False).encode()) > 1024*1024:
        raise ValueError('Script exceeds 1 MiB')
    expanded = []

    def visit(steps, depth=0):
        if not isinstance(steps,list) or not steps or depth>8:
            raise ValueError('Script steps must be lists with nesting at most eight')
        for step in steps:
            if not isinstance(step,dict) or not isinstance(step.get('op'),str):
                raise ValueError('Every step requires an op')
            op = step['op']
            if 'expect' in step and (op!='run' or step['expect'] not in outcomes):
                raise ValueError('expect must be a supported run outcome for this backend')
            if op=='repeat':
                if set(step) != {'op','count','steps'}:
                    raise ValueError('repeat requires count and steps')
                bounded(step['count'],'repeat count',1,1000)
                for _ in range(step['count']):
                    visit(step['steps'],depth+1)
            else:
                alias = step.get('as')
                if alias is not None and (not isinstance(alias,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',alias)):
                    raise ValueError('Step alias must be a simple identifier')
                params = {k:v for k,v in step.items() if k not in ('op','as','expect')}
                if op=='assert':
                    if set(params) != {'value','equals'}:
                        raise ValueError('assert requires value and equals')
                elif op in OPERATIONS:
                    if op=='trace-until' and (backend or actual) not in (None,'dosbox','dosbox-qemu','qemu-dos'):
                        raise ValueError('Live trace-until requires a qualified DOS boundary adapter')
                    if op in ('memory-snapshot','memory-apply','memory-rule-tick','memory-rule-run','desqview-observe') and (backend or actual) not in (None,'dosbox','dosbox-x','dosbox-qemu','qemu-machine','qemu-dos'):
                        raise ValueError('Unsupported operation for this backend: '+op)
                    if op == 'memory-rule-run' and (backend or actual) in ('qemu-machine','qemu-dos'):
                        raise ValueError('Periodic memory rules require DOSBox guest-time control')
                    operation_owner=owner
                    if session is None and backend is None and op in ENGINE_OPERATIONS and op!='step':
                        # Engine-only saved routes retain the AGI grammar; ordinary
                        # step routes keep the established DOS signature.
                        from .scummvm_debugger import ScummVMAGISession
                        operation_owner=ScummVMAGISession
                    operation=getattr(operation_owner,OPERATIONS[op],None)
                    if operation is None:raise ValueError('Unsupported operation for this backend: '+op)
                    if (session is not None and op=='write-registers'
                            and getattr(operation_owner,'register_edits_available',True) is False):
                        raise ValueError('Win16 register writes are not qualified for this runtime')
                    signature = inspect.signature(operation)
                    if session is None:signature.bind(None,**params)
                    else:signature.bind(**params)
                    if op=='trace-until':
                        # This first adapter admits literal predicates/actions.
                        # Validate the entire descriptor before an earlier step
                        # can mutate the guest; result references are refused.
                        from .execution_trace import validate_trace_until
                        def literal(value):
                            if isinstance(value,str) and value.startswith('$'):
                                raise ValueError('trace-until script parameters must be literal')
                            if isinstance(value,dict):
                                for child in value.values():literal(child)
                            elif isinstance(value,list):
                                for child in value:literal(child)
                        literal(params)
                        validate_trace_until(**params)
                        from .execution_clock import clock_predicates
                        if clock_predicates(params['until']):
                            if (backend or actual) != 'qemu-dos':
                                raise ValueError('Live virtual-time-range requires the native qemu-dos virtual clock profile')
                            if session is not None:
                                from .qemu_clock import _configuration
                                if _configuration(session.vm)['profile'] != 'virtual':
                                    raise ValueError('Live virtual-time-range requires the QEMU virtual clock profile')
                        if (backend or actual) == 'qemu-dos' and params.get('action') is not None:
                            raise ValueError('Native DOS trace-until queued input actions require clock/input causal-boundary support; queue physical edges and run to a boundary before tracing')
                    if op in ('rewind-start','rewind-record','rewind','delta-start','delta-record','delta-rewind'):
                        limits={'max_steps':(1,128),'max_bytes':(1,256*1024*1024),
                                'count':(1,128),'timeout_ms':(1,600000)}
                        if op=='delta-start':limits['max_bytes']=(1,2*1024**3)
                        for key,value in params.items():
                            if key in limits and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits[key])
                    if op=='delta-start':
                        from .debug_cpu_deltas import validate_ranges
                        validate_ranges(params['ranges'],allow_references=True)
                    if op=='delta-rewind' and 'policy' in params:
                        from .debug_cpu_deltas import validate_policy
                        validate_policy(params['policy'],allow_references=True)
                    if op.startswith('timeline-') or op in ('frame-advance','frame-inputs'):
                        from .debug_timeline import validate_edges, validate_schedule, validate_timeline_policy, validate_storage
                        limits={'frames':(0,4096) if op=='timeline-rewind' else (1,128),
                                'max_frames':(1,4096),'max_captures':(1,65536),'keyframe_interval':(1,128),
                                'max_bytes':(1,256*1024*1024),
                                'max_state_bytes':(1,256*1024*1024),
                                'max_image_bytes':(1,16*1024*1024),
                                'timeout_ms':(1,600000)}
                        for key,value in params.items():
                            if key in limits and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits[key])
                        if op=='frame-inputs':validate_edges(params['edges'],allow_references=True)
                        if op=='timeline-advance' and params.get('inputs') is not None:
                            validate_schedule(params['inputs'],params.get('frames',1),allow_references=True)
                        if op=='timeline-rewind' and params.get('policy') is not None:
                            validate_timeline_policy(params['policy'],allow_references=True)
                        if op in ('timeline-pin','timeline-image') and 'name' in params:
                            if not (isinstance(params['name'],str) and params['name'].startswith('$')):
                                from .external_files import _file_name
                                _file_name(params['name'])
                        if op=='timeline-start':
                            validate_storage(params.get('storage_mode','full'), params.get('keyframe_interval',8), allow_references=True)
                            sizes=[params.get('max_state_bytes',8*1024**2),
                                   params.get('max_image_bytes',2*1024**2),
                                   params.get('max_bytes',64*1024**2)]
                            if all(type(value) is int for value in sizes) and sum(sizes[:2])>sizes[2]:
                                raise ValueError('Frame timeline byte budget cannot reserve one state and image')
                    if op in ('keyboard.press','keyboard.type'):
                        if (backend or actual) in ('qemu-machine','qemu-dos'):
                            raise ValueError('Timed native QEMU input requires a qualified guest clock; use owned physical edges')
                        from .keyboard_input import validate_keyboard
                        # Validate every literal independently. One result reference
                        # must not hide a malformed static hold, gap or modifier.
                        samples={'key':'a','text':'a','hold_ms':40,'gap_ms':40,'modifiers':[]}
                        checked={k:(samples[k] if isinstance(v,str) and v.startswith('$') else v) for k,v in params.items()}
                        validate_keyboard(**checked)
                    if op=='wait':
                        from .debug_wait import validate_wait
                        if getattr(owner,'scene_time_basis',None)=='host':
                            checked=dict(params)
                            active=checked.pop('active_ms',None);legacy=checked.pop('guest_ms',None)
                            if (active is None)==(legacy is None):
                                raise ValueError('Windows wait requires exactly one active_ms or legacy guest_ms budget')
                            if checked.get('fast_forward',False) is not False:
                                raise ValueError('Windows waits do not support DOS fast-forward')
                            validate_wait(**checked,guest_ms=active if active is not None else legacy)
                        else:validate_wait(**params)
                    if op in ('scene-act','scene-click') and 'slice_ms' in params:
                        value=params['slice_ms']
                        if not (isinstance(value,str) and value.startswith('$')):
                            bounded(value,'slice_ms',1,1000)
                    if op=='write-runtime-memory':
                        from .debug_state import byte_string
                        literal={}
                        for key in ('data_hex','expected_hex'):
                            value=params[key]
                            if not (isinstance(value,str) and value.startswith('$')):
                                literal[key]=byte_string(value)
                        if len(literal)==2 and len(literal['data_hex'])!=len(literal['expected_hex']):
                            raise ValueError('Runtime RAM edits cannot resize a binding')
                        offset=params.get('offset',0)
                        if not (isinstance(offset,str) and offset.startswith('$')):
                            bounded(offset,'runtime view offset',0,65535)
                    if op=='step':
                        for key,limits in (('count',(1,10000)),('timeout_ms',(1,600000))):
                            value=params.get(key)
                            if value is not None and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits)
                    if op=='clock-advance':
                        from .qemu_clock import MAX_CLOCK_BUDGET_NS
                        for key,limits in (('delta_ns',(1,MAX_CLOCK_BUDGET_NS)),
                                           ('timeout_ms',(1,600000))):
                            value=params.get(key)
                            if key in params and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits)
                        if session is not None and not getattr(session,'capabilities',{}).get('virtual_clock_budget'):
                            raise ValueError('clock-advance requires the explicit QEMU virtual clock profile')
                    if op in ('input-schedule','input-schedule-observe'):
                        if session is not None and not getattr(session,'capabilities',{}).get('virtual_input_schedule'):
                            raise ValueError('Input scheduling requires the native input extension and virtual clock')
                        if op=='input-schedule':
                            value=params['delta_ns']
                            if not (isinstance(value,str) and value.startswith('$')):
                                from .qemu_input_schedule import validate_input_delay
                                validate_input_delay(value)
                    if op=='input-schedule-retrace':
                        if session is not None and not getattr(session,'capabilities',{}).get('retrace_input_schedule'):
                            raise ValueError('Retrace input scheduling requires the native extension and explicit precise retrace profile')
                        from .qemu_input_schedule import validate_retrace_input_parameters
                        literal={key:value for key,value in params.items()
                                 if key in ('edge','timeout_ms')
                                 and not (isinstance(value,str) and value.startswith('$'))}
                        validate_retrace_input_parameters(**literal)
                    if op in ('audio-start','audio-observe','audio-stop','capture-audio'):
                        if session is not None and not getattr(session,'capabilities',{}).get('audio_capture'):
                            raise ValueError('Audio operations require the explicit QEMU pc-speaker audio profile')
                        if op=='audio-start' and 'max_frames' in params:
                            value=params['max_frames']
                            if not (isinstance(value,str) and value.startswith('$')):
                                from .qemu_audio import validate_audio_capacity
                                validate_audio_capacity(value)
                    if op in ('display-start','display-observe','display-stop','capture-display'):
                        if session is not None and not getattr(session,'capabilities',{}).get('renderer_capture'):
                            raise ValueError('Renderer operations require the native display extension and virtual clock')
                        from .qemu_display import validate_display_period, validate_after_update
                        for key,validator in (('period_ns',validate_display_period),('after_update',validate_after_update)):
                            if key in params:
                                value=params[key]
                                if not (isinstance(value,str) and value.startswith('$')):validator(value)
                    if op=='retrace-observe':
                        if session is not None and not getattr(session,'capabilities',{}).get('retrace_observation'):
                            raise ValueError('retrace-observe requires the explicit native precise retrace profile')
                        if 'timeout_ms' in params:
                            value=params['timeout_ms']
                            if not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,'timeout_ms',1,600000)
                    if op=='retrace-wait':
                        if session is not None and not getattr(session,'capabilities',{}).get('retrace_wait'):
                            raise ValueError('retrace-wait requires the explicit native precise retrace profile')
                        from .qemu_retrace import validate_retrace_wait_parameters
                        literal={key:value for key,value in params.items()
                                 if not (isinstance(value,str) and value.startswith('$'))}
                        validate_retrace_wait_parameters(**literal)
                    if op in ('clock-sync-start','clock-sync-observe','clock-sync-step','clock-sync-stop'):
                        if session is not None and not getattr(session,'capabilities',{}).get('host_clock_sync'):
                            raise ValueError('Host clock synchronization requires the explicit QEMU virtual clock profile')
                        # Validate every literal before earlier mutations. A start
                        # in this same script may establish the live mapping later.
                        from .qemu_clock_sync import validate_clock_sync_options
                        literal={key:value for key,value in params.items()
                                 if not (isinstance(value,str) and value.startswith('$'))}
                        validate_clock_sync_options(**literal)
                    if op=='move':
                        from .movement import validate_movement, _call
                        _call(params['start']);_call(params['stop'])
                        validate_movement(**{k:v for k,v in params.items() if k not in ('macro_set','start','stop')})
                    if op=='keyboard.key-down':
                        from .keyboard_input import KEYS
                        if not isinstance(params['key'],str) or params['key'] not in KEYS:raise ValueError('Unknown physical keyboard key')
                    if op=='mouse.move-relative':
                        values=[]
                        for axis in ('dx','dy'):
                            value=params[axis]
                            if isinstance(value,str) and value.startswith('$'):continue
                            bounded(value,axis,-32767,32767);values.append(value)
                        if len(values)==2 and values==[0,0]:raise ValueError('Relative mouse movement requires a nonzero delta')
                    if op=='mouse.button-down':
                        if params['button'] not in ('left','middle','right'):
                            raise ValueError('Unknown physical mouse button')
                    if (op in ('mouse.button-up','keyboard.key-up')
                            and (backend or actual) in ('qemu-machine','qemu-dos')):
                        lease=params['lease']
                        if not (isinstance(lease,str) and lease.startswith('$')):
                            if type(lease) is not str or not 1<=len(lease)<=128:
                                raise ValueError('Expected an owned unused physical input lease')
                    if op in ('capture-surface','capture-audio','capture-display') and 'name' in params:
                        name=params['name']
                        if not (isinstance(name,str) and name.startswith('$')):
                            from .external_files import _file_name
                            _file_name(name)
                    if op=='screenshot-hooks' and params.get('configuration') is not None:
                        from .screenshot_hooks import validate_configuration
                        validate_configuration(params['configuration'])
                else:
                    raise ValueError('Unknown script operation: '+op)
                expanded.append(step)
                if len(expanded)>1000:
                    raise ValueError('Script exceeds 1000 expanded steps')
    visit(script['steps'])
    if not expanded:
        raise ValueError('Script must contain at least one operation')
    if (session is not None
            and getattr(session, 'metadata', {}).get('runtime_profile') == 'dos-exec-load-only-v1'
            and any(step['op'] in ('trace', 'trace-until') for step in expanded)
            and session.project.db.in_transaction):
        raise ValueError('Source tracing requires a project outside a caller-owned transaction')
    if session is not None and (backend or actual) in ('qemu-machine','qemu-dos'):
        guarded={'keyboard.key-down','keyboard.key-up','mouse.move-relative','mouse.button-down',
                 'mouse.button-up','input-cancel-pending','input-schedule','input-schedule-observe',
                 'input-schedule-retrace',
                 'clock-observe','clock-advance','capture-surface','screenshot',
                 'audio-start','audio-observe','audio-stop','capture-audio',
                 'display-start','display-observe','display-stop','capture-display','retrace-observe',
                 'retrace-wait','clock-sync-start','clock-sync-observe','clock-sync-step','clock-sync-stop'}
        project=getattr(session,'project',None)
        if project is not None and project.db.in_transaction:
            pending=(any(step['op']=='run' for step in expanded)
                     and getattr(session,'_input_pending',lambda:False)())
            if pending or any(step['op'] in guarded for step in expanded):
                raise ValueError('Native QEMU input/media observation requires a project outside a caller-owned transaction')
    return expanded


@rpc_budget
def execute_script(session, script, *, timeout_ms=60000, bindings=None, _after_step=None, _bindings_out=None):
    bounded(timeout_ms,'timeout_ms',1,600000)
    started = time.monotonic()
    deadline = min(started+timeout_ms/1000, session._rpc_deadline)
    steps = validate_script(script, session=session) # Reject malformed later steps before any guest mutation.
    # Check literal clock identities against the live native epoch before an
    # earlier script step can write or continue. Recheck at trace admission as
    # well: an earlier execution may have invalidated the process or clock.
    for step in steps:
        if step['op'] == 'trace-until':
            from .execution_clock import clock_predicates
            if clock_predicates(step['until']):
                session._trace_clock_preflight(step['until'])
    for step in steps:
        if step['op']=='delta-rewind' and 'policy' in step:
            from .debug_cpu_deltas import validate_policy
            validate_policy(step['policy'],registers=getattr(session,'_delta_registers',None),
                            allow_references=True)
        if step['op']=='delta-start' and 'max_bytes' in step:
            value=step['max_bytes']
            if not (isinstance(value,str) and value.startswith('$')):
                bounded(value,'max_bytes',1,getattr(session,'_delta_max_bytes',256*1024**2))
    if getattr(session,'script_operations',None) is not None:
        unsupported=[s['op'] for s in steps if s['op'] not in session.script_operations]
        if unsupported:
            raise ValueError('Unsupported operations for this backend: '+', '.join(sorted(set(unsupported))))
    frame_operations = {'frame-advance','frame-inputs','timeline-start','timeline-advance',
                        'timeline-rewind','timeline-pin','timeline-image'}
    capabilities = getattr(getattr(session,'rpc',None),'capabilities',{})
    if any(step['op'] in frame_operations for step in steps):
        if not isinstance(capabilities,dict) or not capabilities.get('frame_timeline'):
            raise ValueError('Frame/timeline script operations require backend frame_timeline capability')
    for step in steps:
        if step['op']=='macro':
            params={k:v for k,v in step.items() if k not in ('op','as','expect','timeout_ms')}
            session._macro_plan(**params)
        elif step['op']=='move':
            for key in ('start','stop'):
                call=step[key]
                session._macro_plan(step['macro_set'],call['name'],call.get('args',{}))
    restore_operations = {'load-state','load-anchor-stone','rewind','delta-recover','timeline-rewind'}
    def frame_owned_keys():
        from .keyboard_input import KEYS
        result = session.call('input.keyboard.state')
        keyboard = result.get('keyboard') if isinstance(result,dict) else None
        keys = keyboard.get('frame_keys') if isinstance(keyboard,dict) else None
        if not isinstance(keys,list) or any(not isinstance(key,str) or key not in KEYS for key in keys):
            raise ValueError('Native frame input ownership is unavailable')
        normalized = {'escape' if key=='esc' else key for key in keys}
        if len(normalized) != len(keys):
            raise ValueError('Native frame input ownership contains duplicate keys')
        return normalized
    frame_owned_before = None
    track_restored_input = (isinstance(capabilities,dict) and capabilities.get('frame_timeline')
                           and any(step['op'] in restore_operations for step in steps))
    if track_restored_input:
        # A full-state restore can introduce held input without dispatching
        # an edge. Existing entry ownership remains the caller's responsibility.
        try:
            frame_owned_before = frame_owned_keys()
        except ValueError as error:
            frozen = (getattr(session,'_cpu_delta_history',None) or {}).get('frozen')
            if not frozen or 'CPU delta partial state is frozen' not in str(error):
                raise
            # The delta guard deliberately refuses this query. Keep ownership
            # unknown while allowing the script's full recovery operation.
    frame_restore_attempted = False
    encoded = json.dumps(script,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if time.monotonic() >= deadline:
        raise TimeoutError('Script host-time budget expired before route publication')
    source = session._artifact('route.fdisbull.json','script',encoded,{'format':script['format']})
    results = dict(bindings or {}); records = []; failure = None
    owned_before=set(getattr(session,'_keyboard_leases',{}));keyboard_touched=False

    def resolve(value):
        if isinstance(value,str) and value.startswith('$'):
            parts = value[1:].split('.')
            current = results[parts[0]]
            for part in parts[1:]:
                current = current[int(part)] if isinstance(current,list) else current[part]
            return current
        if isinstance(value,list):
            return [resolve(item) for item in value]
        if isinstance(value,dict):
            return {k:resolve(v) for k,v in value.items()}
        return value

    for index, step in enumerate(steps):
        record = {'index':index,'op':step['op']}
        prior_input_touched = keyboard_touched
        try:
            remaining = int((deadline-time.monotonic())*1000)
            if remaining <= 0:
                raise TimeoutError('Script host-time budget expired')
            params = resolve({k:v for k,v in step.items() if k not in ('op','as','expect')})
            if step['op']=='input-schedule-retrace':
                # Validate resolved options before the budget clamp can turn
                # an invalid supplied timeout into a valid remaining integer.
                from .qemu_input_schedule import validate_retrace_input_parameters
                validate_retrace_input_parameters(**params)
            if step['op'] in ('run','clock-advance','retrace-observe','retrace-wait',
                             'input-schedule-retrace',
                             'clock-sync-start','clock-sync-observe','clock-sync-step','clock-sync-stop',
                             'trace','trace-until','step','engine-cycle','rewind-record','delta-record','frame-advance','timeline-advance','timeline-rewind','wait','scene-wait','scene-click','scene-act','macro','move','proof-check','spatial-action'):
                requested=params.get('timeout_ms')
                if requested is None:requested=remaining
                params['timeout_ms'] = min(requested,remaining,60000 if step['op'].startswith('scene-') else remaining)
            if step['op']=='assert':
                if params['value'] != params['equals']:
                    raise ValueError(f"Assertion failed: {params['value']!r} != {params['equals']!r}")
                result = {'matched':True}
            else:
                # Record intended input before dispatch so an uncertain failure
                # follows the same terminal cleanup as legacy keyboard input.
                prior_input_touched = keyboard_touched
                if ((step['op'].startswith('keyboard.') and step['op']!='keyboard.state')
                        or step['op'].startswith('mouse.') or step['op'] in ('input-cancel-pending','input-schedule','input-schedule-retrace')
                        or (step['op']=='trace-until' and params.get('action') is not None)
                        or (step['op']=='frame-inputs' and params['edges'])
                        or (step['op']=='timeline-advance' and any(item['edges'] for item in params.get('inputs') or []))):
                    keyboard_touched=True
                if track_restored_input and step['op'] in restore_operations:
                    frame_restore_attempted = True
                result = getattr(session,OPERATIONS[step['op']])(**params)
                if (step['op']=='trace-until' and result.get('action',{}).get('dispatch')
                        in ('not_requested','not_dispatched','skipped_initial_match')):
                    keyboard_touched = prior_input_touched
            record['result'] = result
            if step['op']=='wait' and not (result.get('complete') and result.get('matched')):
                raise ValueError('Wait did not match: '+result.get('outcome','incomplete'))
            if step['op']=='trace-until' and not (result.get('complete') and result.get('matched') and result.get('exact_stop')):
                raise ValueError('Trace predicate did not match at the current stop: '+result.get('outcome','incomplete'))
            if step['op'] in ('macro','move') and not result.get('ok'):
                raise ValueError('Semantic input did not complete')
            if step['op']=='run':
                expected = step.get('expect','guest_time' if 'guest_ms' in params else 'breakpoint')
                if result['outcome'] != expected:
                    raise ValueError(f"Run expected {expected}, observed {result['outcome']}")
            if step['op']=='trace' and not result['metadata']['complete']:
                raise ValueError('Trace stopped before the requested event count')
            if step['op']=='step':
                native_machine = getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')
                complete = (result.get('outcome')=='step' and result.get('timed_out') is False
                            if native_machine else result.get('completed'))
                if not complete:
                    raise ValueError('Step stopped before the requested instruction boundary')
            if step['op']=='engine-cycle' and result.get('outcome')!='cycle':
                raise ValueError('Engine did not reach the requested cycle boundary')
            if _after_step is not None:_after_step(step,result)
            if 'as' in step:
                results[step['as']] = result
            record.update(ok=True,result=result)
        except Exception as error:
            failure = {'index':index,'op':step['op'],'type':type(error).__name__,'message':str(error)}
            record.update(ok=False,error=failure)
            if hasattr(error,'result'):record['result']=error.result
            if (step['op']=='trace-until' and isinstance(getattr(error,'result',None),dict)
                    and error.result.get('action',{}).get('dispatch')
                    in ('not_requested','not_dispatched','skipped_initial_match')):
                keyboard_touched = prior_input_touched
        records.append(record)
        if failure:
            break
    cleanup=None
    restored_input_held = restore_ownership_unknown = False
    if failure and frame_restore_attempted and not keyboard_touched:
        try:
            current = frame_owned_keys()
            if frame_owned_before is None:
                restore_ownership_unknown = bool(current)
            else:
                restored_input_held = bool(current - frame_owned_before)
        except Exception:
            # An attempted restore with no verifiable ownership readback must
            # not leave a failed route free to resume an unknown held key.
            restore_ownership_unknown = True
    if failure and (keyboard_touched or restored_input_held or restore_ownership_unknown
                    or set(getattr(session,'_keyboard_leases',{}))-owned_before):
        # A failed route must not leave input depressed or execute through a stop.
        reason = ('Failed script frame input ownership is unknown after restore' if restore_ownership_unknown
                  else 'Failed script owned unreleased input')
        session.close();cleanup={'closed':True,'reason':reason}
    report = {'format':'fdisbull-script-result-1','script_artifact':source['artifact'],
              'script_sha256':hashlib.sha256(encoded).hexdigest(),'run':session.run_id,
              'ok':failure is None,'error':failure,'completed_steps':sum(r['ok'] for r in records),
              'requested_steps':len(steps),'host_elapsed_ms':round((time.monotonic()-started)*1000,3),
              'steps':records,'input_cleanup':cleanup}
    evidence = session._artifact('route-result.json','script-result',json.dumps(report,indent=2).encode(),
                                 {'ok':report['ok'],'completed_steps':report['completed_steps']})
    if _bindings_out is not None:_bindings_out.update(results)
    return {**report,'artifact':evidence['artifact']}
