"""A bounded, declarative JSON language for repeatable debugger routes."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import time
from functools import wraps

from .debugger import bounded
from .operation_budget import rpc_budget
from .qemu_video_checkpoint import VIDEO_SOURCE_PROFILES, video_frame_size, video_vm_size
from .qemu_video_frame import VIDEO_FRAME_SCRIPT_OPERATIONS, validate_video_frame_script_parameters
from .qemu_video_frame_state import validate_video_frame_state_parameters
from .qemu_stopped_control import validate_stopped_control_parameters

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
    **VIDEO_FRAME_SCRIPT_OPERATIONS,
    'video-frame-state-observe':'video_frame_state_observe',
    'stopped-control-arm':'stopped_control_arm',
    'frame-probe':'frame_probe','scene-check':'scene_check','scene-assert':'scene_assert',
    'scene-click':'scene_click','scene-act':'scene_act','scene-wait':'scene_wait',
    'keyboard.press':'keyboard_press','keyboard.type':'keyboard_type','keyboard.state':'keyboard_state',
    'keyboard.key-down':'keyboard_key_down','keyboard.key-up':'keyboard_key_up',
    'mouse.move-relative':'mouse_move_relative','mouse.button-down':'mouse_button_down','mouse.button-up':'mouse_button_up',
    'mouse.button-click':'mouse_button_click',
    'mouse.move-mapped':'mouse_move_mapped',
    'input-state':'input_state','input-cancel-pending':'input_cancel_pending',
    'input-schedule':'input_schedule','input-schedule-observe':'input_schedule_observe',
    'input-schedule-retrace':'input_schedule_retrace',
    'clock-observe':'clock_observe','clock-advance':'clock_advance','capture-surface':'capture_surface',
    'audio-start':'audio_start','audio-observe':'audio_observe','audio-stop':'audio_stop','capture-audio':'capture_audio',
    'mixer-observe':'mixer_observe',
    'display-start':'display_start','display-observe':'display_observe','display-stop':'display_stop','capture-display':'capture_display',
    'display-probe':'display_probe',
    'vga-configuration':'vga_configuration_observe',
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
    'save-machine-state':'save_machine_state', 'load-machine-state':'load_machine_state',
    'save-le-source-state':'save_le_source_state', 'load-le-source-state':'load_le_source_state',
    'le-rewind-start':'le_rewind_start', 'le-rewind-status':'le_rewind_status',
    'le-rewind-record':'le_rewind_record', 'le-rewind':'le_rewind',
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
            or set(script)-{'format','steps','backend','video_source_profile'}
            or script['format'] != 'fdisbull-script-1'):
        raise ValueError('Script requires format=fdisbull-script-1 and steps')
    backend=script.get('backend')
    supported_backends=('wine-qemu','wine-ne','scummvm-agi','scummvm-gob','scummvm-kyra','qemu-machine','qemu-dos','qemu-chip8')
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
        elif backend=='qemu-chip8':
            from .qemu_chip8 import Chip8DebugSession
            owner=Chip8DebugSession
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
    vm = getattr(session, 'vm', None)
    if 'video_source_profile' in script:
        profile = script['video_source_profile']
        if (backend not in ('qemu-machine', 'qemu-dos') or type(profile) is not str
                or profile not in VIDEO_SOURCE_PROFILES):
            raise ValueError('Script video source profile requires an explicit native QEMU backend and known profile')
        if session is not None and profile != getattr(vm, 'machine_configuration', {}).get('video_source_profile'):
            raise ValueError('Script video source profile differs from the live debugger')
        probe_size = video_frame_size(VIDEO_SOURCE_PROFILES[profile][0])
    else:
        probe_size = video_vm_size(vm)
    if (backend or actual) in (None, 'dosbox', 'dosbox-x', 'dosbox-qemu', 'qemu-dos'):
        # Both DOS process implementations distinguish a selected program's
        # return or residency from the native emulator exiting.
        outcomes|={'guest_exit','guest_tsr'}
    if (backend or actual) in ('qemu-machine','qemu-dos'):
        outcomes.add('hook')
    if (backend or actual) == 'qemu-chip8':
        outcomes|={'hook','key_wait','layer_conflict','exception','stopped'}
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
                        from .memory_rules import MAX_TICKS
                        for key,limits in (('ticks',(1,MAX_TICKS)),('interval_ms',(1,60000)),
                                           ('timeout_ms',(1,60000))):
                            value=params.get(key)
                            if key in params and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits)
                        if session is not None:
                            from .qemu_memory_rules import admit_native_rule_run
                            admit_native_rule_run(session)
                    if op in ('save-state','load-state','save-anchor-stone','load-anchor-stone') and (backend or actual) in ('qemu-machine','qemu-dos'):
                        if (backend or actual) != 'qemu-dos':
                            raise ValueError('Unsupported operation for native QEMU scripts: '+op)
                        from .qemu_checkpoint_script import validate_parameters
                        validate_parameters(op,params,session=session)
                    if op in ('save-machine-state','load-machine-state'):
                        if (backend or actual) != 'qemu-dos':
                            raise ValueError('Owned-machine scripts require the qemu-dos backend')
                        if session is not None:
                            if not getattr(session,'capabilities',{}).get('owned_machine_checkpoints'):
                                raise ValueError('Owned-machine checkpoints are not enabled')
                            if session.project.db.in_transaction:
                                raise ValueError('Owned-machine scripts require no caller transaction')
                        if 'name' in params:
                            from .external_files import _file_name
                            _file_name(params['name'])
                            if params['name'].startswith('$'):
                                raise ValueError('Owned-machine checkpoint names must be literal')
                        for key, bounds in (('max_bytes',(1,128*1024*1024)),('timeout_ms',(1,600000))):
                            if key in params:
                                bounded(params[key],key,*bounds)
                        if 'artifact' in params and (not isinstance(params['artifact'],str) or not params['artifact']):
                            raise ValueError('Owned-machine artifact must be a nonempty identifier or result reference')
                        if 'rebind_protected_source' in params and type(params['rebind_protected_source']) is not bool:
                            raise ValueError('rebind_protected_source must be a literal Boolean')
                    if op in ('save-le-source-state','load-le-source-state','le-rewind-start',
                              'le-rewind-status','le-rewind-record','le-rewind'):
                        if (backend or actual) != 'qemu-dos':
                            raise ValueError('LE source scripts require the qemu-dos backend')
                        if session is not None:
                            capability = 'le_source_histories' if op.startswith('le-rewind') else 'le_source_checkpoints'
                            if not getattr(session,'capabilities',{}).get(capability):
                                raise ValueError('LE source checkpoints/history are not enabled')
                            if session.project.db.in_transaction:
                                raise ValueError('LE source scripts require no caller transaction')
                        if 'name' in params:
                            from .external_files import _file_name
                            _file_name(params['name'])
                            if params['name'].startswith('$'):
                                raise ValueError('LE source checkpoint names must be literal')
                        from .qemu_dos_le_checkpoint import MAX_DESCRIPTOR
                        for key, limits in (('timeout_ms',(1,600000)), ('max_steps',(1,128)),
                                            ('max_bytes',(MAX_DESCRIPTOR+1,1024**3 if op=='le-rewind-start' else 128*1024**2))):
                            if key in params:
                                bounded(params[key],key,*limits)
                        for key in ('artifact','history','node'):
                            if key in params and (not isinstance(params[key],str) or not params[key]):
                                raise ValueError('LE source references must be nonempty identifiers or result references')
                        if op=='le-rewind-record':
                            if params.get('advance','capture') != 'capture' or type(params.get('count',1)) is not int or params.get('count',1) != 1:
                                raise ValueError('LE source history records one explicit capture; stepping is unsupported')
                        if op=='le-rewind' and 'count' in params:
                            bounded(params['count'],'count',1,128)
                    if op in ('click', 'click-frame') and (backend or actual) in ('qemu-machine', 'qemu-dos'):
                        raise ValueError('Unsupported operation for this backend script: ' + op)
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
                    if op in ('trace','trace-until') and (backend or actual)=='qemu-dos':
                        from .qemu_dos_trace import _select_source_view, _validate_source_view
                        if session is None:_validate_source_view(params.get('source_view'))
                        else:_select_source_view(session,params.get('source_view'))
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
                        descriptor=dict(params)
                        if (backend or actual)=='qemu-dos':descriptor.pop('source_view',None)
                        validate_trace_until(**descriptor)
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
                        if (op.startswith('rewind') and (backend or actual) in ('qemu-dos','qemu-chip8')
                                and session is not None):
                            if not getattr(session,'capabilities',{}).get('rewind'):
                                message=('Native history scripts require enabled full process checkpoints'
                                         if (backend or actual)=='qemu-dos' else
                                         'CHIP-8 history scripts require enabled full checkpoints')
                                raise ValueError(message)
                            if session.project.db.in_transaction:
                                raise ValueError('Native history scripts require a project outside a caller-owned transaction')
                        limits={'max_steps':(1,128),'max_bytes':(1,256*1024*1024),
                                'count':(1,128),'timeout_ms':(1,600000)}
                        if op=='delta-start' and (backend or actual)!='qemu-chip8':limits['max_bytes']=(1,2*1024**3)
                        if op=='rewind-start' and (backend or actual) in ('qemu-dos','qemu-chip8'):
                            limits['max_bytes']=(1,1024**3)
                        for key,value in params.items():
                            if key in limits and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits[key])
                        if (backend or actual) in ('qemu-dos','qemu-chip8') and op=='rewind-record':
                            advance=params.get('advance','step')
                            if not (isinstance(advance,str) and advance.startswith('$')) and advance not in ('step','capture'):
                                raise ValueError('Native rewind advance must be step or capture')
                            if advance=='capture' and type(params.get('count',1)) is int and params.get('count',1)!=1:
                                raise ValueError('Explicit checkpoint capture records one stopped boundary')
                    if op=='delta-start':
                        from .debug_cpu_deltas import validate_ranges
                        validate_ranges(params['ranges'],allow_references=True)
                        if (backend or actual)=='qemu-chip8':
                            from .chip8_cpu_undo_runtime import validate_ranges as chip8_ranges, validate_registers
                            chip8_ranges(params['ranges'],allow_references=True)
                            validate_registers(params.get('registers'),allow_references=True)
                    if op in ('delta-start','delta-record','delta-rewind','delta-recover') and (backend or actual)=='qemu-chip8':
                        if session is not None:
                            if not getattr(session,'capabilities',{}).get('selected_cpu_ram_undo'):
                                raise ValueError('CHIP-8 selected CPU/RAM undo requires v6 and a checkpoint tool')
                            if session.project.db.in_transaction:
                                raise ValueError('CHIP-8 selected CPU/RAM scripts require no caller transaction')
                        if op=='delta-recover' and 'timeout_ms' in params:
                            value=params['timeout_ms']
                            if not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,'timeout_ms',1,600000)
                    if op=='delta-rewind' and 'policy' in params:
                        from .debug_cpu_deltas import validate_policy
                        selected_registers=None
                        if (backend or actual)=='qemu-chip8':
                            from .chip8_cpu_undo_runtime import REGISTERS, validate_ranges as chip8_ranges
                            selected_registers=REGISTERS
                            if isinstance(params['policy'],dict) and params['policy'].get('preserve_memory') not in (None,[]):
                                chip8_ranges(params['policy']['preserve_memory'],allow_references=True)
                        validate_policy(params['policy'],registers=selected_registers,allow_references=True)
                        if ((backend or actual) in ('qemu-dos','qemu-chip8') and isinstance(params['policy'],dict)
                                and params['policy'].get('allow_partial_resume') is True):
                            raise ValueError('Native selected CPU/RAM undo does not permit partial resume')
                    if op.startswith('timeline-') or op in ('frame-advance','frame-inputs'):
                        from .debug_timeline import validate_edges, validate_schedule, validate_timeline_policy, validate_storage
                        native_frames = (backend or actual) in ('qemu-dos','qemu-chip8')
                        chip8_frames = (backend or actual) == 'qemu-chip8'
                        source_step = (op == 'frame-advance' and (backend or actual) in ('qemu-machine','qemu-dos')
                            and session is not None and bool(getattr(session,'capabilities',{}).get('frame_step')))
                        if (session is not None and op == 'frame-advance'
                                and (backend or actual) == 'qemu-machine' and not source_step):
                            raise ValueError('Source frame advancement requires the frame_step capability')
                        if chip8_frames:
                            from .chip8_keys import validate_edges, validate_schedule
                            if op == 'timeline-rewind' and params.get('policy') not in (None, {}):
                                raise ValueError('CHIP-8 frame histories restore full checkpoints without partial policies')
                            if op == 'timeline-start':
                                if params.get('period_ns',16666667) != 16666667:
                                    raise ValueError('CHIP-8 frame histories require the native 60 Hz sampling period')
                                if (session is not None and params.get('storage_mode','full') == 'delta'
                                        and not getattr(session,'capabilities',{}).get('frame_delta_storage')):
                                    raise ValueError('CHIP-8 lossless delta storage requires native v6 and a checkpoint tool')
                        if native_frames:
                            if (op == 'frame-inputs' or op == 'timeline-advance'
                                    and params.get('inputs') not in (None, [])):
                                if session is not None and not getattr(session,'capabilities',{}).get('frame_key_ownership'):
                                    raise ValueError('Native frame key input requires its ownership extension')
                            if session is not None and op in ('frame-advance','timeline-start',
                                    'timeline-advance','timeline-rewind','timeline-pin'):
                                capabilities = getattr(session,'capabilities',{})
                                source_timeline = _source_timeline_step(op, params, backend or actual)
                                if (op == 'timeline-start' and params.get('frame_source') == 'source-raster'
                                        and not capabilities.get('source_raster_timeline')):
                                    raise ValueError('Source raster timeline requires native source stepping and checkpoints')
                                if (not source_step and not capabilities.get('frame_timeline')
                                        and not (source_timeline and capabilities.get('source_raster_timeline'))):
                                    raise ValueError('Native frame histories require the renderer-frame fence and full checkpoints')
                                if session.project.db.in_transaction:
                                    raise ValueError('Native frame histories require a project outside a caller-owned transaction')
                            if op == 'timeline-rewind' and params.get('policy') is not None and not chip8_frames:
                                raise ValueError('Native renderer histories restore full checkpoints; partial policies are unqualified')
                        limits={'frames':(0,4096) if op=='timeline-rewind' else (1,128),
                                'max_frames':(1,4096),'max_captures':(1,65536),'keyframe_interval':(1,128),
                                'max_bytes':(1,256*1024*1024),
                                'max_state_bytes':(1,256*1024*1024),
                                'max_image_bytes':(1,16*1024*1024),
                                'timeout_ms':(1,600000)}
                        if native_frames:
                            limits.update(frames=(1,128), max_frames=(1,128),
                                max_captures=(1,128), max_bytes=(1,1024**3),
                                max_state_bytes=(1,128*1024**2),
                                period_ns=(1000000,1000000000))
                            if op == 'timeline-rewind': limits['frames']=(0,128)
                        for key,value in params.items():
                            if key in limits and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits[key])
                        if op=='frame-inputs':validate_edges(params['edges'],allow_references=True)
                        if op=='timeline-advance' and params.get('inputs') is not None:
                            validate_schedule(params['inputs'],params.get('frames',1),allow_references=True)
                        if op=='timeline-rewind' and params.get('policy') is not None and not chip8_frames:
                            validate_timeline_policy(params['policy'],allow_references=True)
                        if op in ('timeline-pin','timeline-image') and 'name' in params:
                            if not (isinstance(params['name'],str) and params['name'].startswith('$')):
                                from .external_files import _file_name
                                _file_name(params['name'])
                        if op=='timeline-start':
                            source = params.get('frame_source')
                            if source not in (None, 'renderer', 'source-raster'):
                                raise ValueError('frame_source must be renderer or source-raster')
                            if source == 'source-raster' and params.get('period_ns',16666667) != 16666667:
                                raise ValueError('Source raster timing uses the native stream period')
                            validate_storage(params.get('storage_mode','full'), params.get('keyframe_interval',8), allow_references=True)
                            sizes=[params.get('max_state_bytes',(128 if native_frames else 8)*1024**2),
                                   params.get('max_image_bytes',2*1024**2),
                                   params.get('max_bytes',(512 if native_frames else 64)*1024**2)]
                            if all(type(value) is int for value in sizes) and sum(sizes[:2])>sizes[2]:
                                raise ValueError('Frame timeline byte budget cannot reserve one state and image')
                    if op in ('keyboard.press','keyboard.type'):
                        if (backend or actual) in ('qemu-machine','qemu-dos'):
                            capability = ('virtual_keyboard_type' if op=='keyboard.type'
                                          else 'virtual_keyboard_press')
                            if session is not None and not getattr(session,'capabilities',{}).get(capability):
                                operation = 'text' if op=='keyboard.type' else 'press'
                                raise ValueError('Timed keyboard '+operation+' requires its native extension and a qualified guest clock (explicit virtual profile)')
                        from .keyboard_input import validate_keyboard
                        # Validate every literal independently. One result reference
                        # must not hide a malformed static hold, gap or modifier.
                        samples={'key':'a','text':'a','hold_ms':40,'gap_ms':40,'modifiers':[]}
                        checked={k:(samples[k] if isinstance(v,str) and v.startswith('$') else v) for k,v in params.items()}
                        validate_keyboard(**checked)
                    if op=='wait':
                        from .debug_wait import validate_wait
                        if (backend or actual) in ('qemu-machine','qemu-dos'):
                            from .qemu_wait import validate_qemu_wait_parameters, validate_qemu_wait_session
                            validate_qemu_wait_parameters(**params)
                            if session is not None:
                                validate_qemu_wait_session(session, guest_ms=params['guest_ms'],
                                                          slice_ms=params.get('slice_ms',50))
                        elif getattr(owner,'scene_time_basis',None)=='host':
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
                    if op in ('scene-check','scene-assert') and (backend or actual)=='qemu-dos':
                        from .runtime_scenes import validate_parameters
                        validate_parameters(**params,allow_references=True)
                        if session is not None:
                            from .qemu_scenes import preflight
                            preflight(session,**params,allow_references=True)
                    if op=='scene-wait' and (backend or actual)=='qemu-dos':
                        from .qemu_scene_wait import validate_parameters, preflight
                        validate_parameters(**params,allow_references=True)
                        if session is not None:
                            preflight(session,**params,allow_references=True)
                    if op=='scene-act' and (backend or actual)=='qemu-dos':
                        from .qemu_scene_act import validate_parameters, preflight
                        validate_parameters(**params,allow_references=True)
                        if session is not None:
                            preflight(session,**params,allow_references=True)
                    if session is not None:
                        from .runtime_scenes import require_frame_scene
                        frame_scenes=[]
                        if (op in ('scene-navigation','scene-click','scene-act','scene-wait','move')
                                and not (op in ('scene-wait','scene-act') and (backend or actual)=='qemu-dos')):
                            frame_scenes.append(params.get('scene'))
                        if op in ('scene-check','scene-assert') and (backend or actual)!='qemu-dos':
                            frame_scenes.append(params.get('scene'))
                        plan=params.get('plan') if op=='assisted-travel' else params.get('travel_plan') if op=='spatial-action' else None
                        if isinstance(plan,dict):
                            frame_scenes.extend(plan.get(key) for key in ('scene_revision','destination_scene'))
                        map_revision=params.get('map_revision') if op=='spatial-action' else params.get('spatial_map') if op=='move' else None
                        if isinstance(map_revision,str) and not map_revision.startswith('$'):
                            frame_scenes.append(session.project.debug_spatial_map_info(map_revision,version=session.version['id'])['document']['source']['context'])
                        for selected_scene in frame_scenes:
                            if isinstance(selected_scene,str) and not selected_scene.startswith('$'):
                                require_frame_scene(session.project.debug_scene_info(selected_scene,version=session.version['id']))
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
                    if op=='proof-check' and (backend or actual)=='qemu-dos':
                        from .qemu_proofs import validate_proof_parameters
                        validate_proof_parameters(**params, allow_references=True, session=session)
                    if ((backend or actual)=='qemu-dos'
                            and op in ('bind-runtime-memory','runtime-memory','write-runtime-memory')):
                        from .qemu_runtime_memory import validate_script_parameters
                        validate_script_parameters(op, params, session=session)
                    if op=='step':
                        for key,limits in (('count',(1,10000)),('timeout_ms',(1,600000))):
                            value=params.get(key)
                            if key in params and not (isinstance(value,str) and value.startswith('$')):
                                bounded(value,key,*limits)
                        if (backend or actual) in ('qemu-machine','qemu-dos'):
                            from .qemu_step_over import validate_step_mode
                            mode, count = params.get('mode','into'), params.get('count',1)
                            if not (isinstance(mode,str) and mode.startswith('$')):
                                validate_step_mode(mode,1 if isinstance(count,str) and count.startswith('$') else count)
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
                    if op=='mixer-observe':
                        if session is not None and not getattr(session,'capabilities',{}).get('mixer_gain_readback'):
                            raise ValueError('Mixer gain readback requires the optional native mixer extension and audio profile')
                    if op in ('audio-start','audio-observe','audio-stop','capture-audio'):
                        if session is not None and not getattr(session,'capabilities',{}).get('audio_capture'):
                            raise ValueError('Audio operations require an explicit QEMU audio profile')
                        if op=='audio-start' and 'max_frames' in params:
                            value=params['max_frames']
                            if not (isinstance(value,str) and value.startswith('$')):
                                from .qemu_audio import validate_audio_capacity
                                validate_audio_capacity(value)
                        if op=='audio-start' and 'capture_format' in params:
                            value=params['capture_format']
                            if not (isinstance(value,str) and value.startswith('$')):
                                from .qemu_audio import validate_audio_capture_format
                                validate_audio_capture_format(value)
                                if (value=='s16-stereo' and session is not None
                                        and not getattr(session,'capabilities',{}).get('audio_stereo_capture')):
                                    raise ValueError('Audio stereo capture requires the sb16-opl profile and optional native format extension')
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
                    if op=='display-probe':
                        if session is not None and not getattr(session,'capabilities',{}).get('renderer_probe'):
                            raise ValueError('Renderer probe requires its native extension and virtual clock')
                        from .qemu_display import validate_display_probe_parameters
                        validate_display_probe_parameters(**params, allow_references=True)
                    if op == 'frame-probe' and (backend or actual) in ('qemu-machine','qemu-dos'):
                        if session is not None and not getattr(session,'capabilities',{}).get('frame_contract'):
                            raise ValueError('Frame probe requires the owned QEMU source-raster contract')
                        from .qemu_video_frame import validate_video_frame_probe
                        validate_video_frame_probe(**params, allow_references=True, frame_size=probe_size)
                    if op in VIDEO_FRAME_SCRIPT_OPERATIONS:
                        if (backend or actual) not in ('qemu-machine','qemu-dos'):
                            raise ValueError('Source video frames require an explicit native QEMU backend')
                        capability = 'video_frame_control' if op == 'video-frame-advance' else 'video_frame_capture'
                        if session is not None and not getattr(session,'capabilities',{}).get(capability):
                            raise ValueError('Source video frames require their native extension and explicit virtual/precise profiles')
                        validate_video_frame_script_parameters(op, params, allow_references=True,
                                                              frame_size=probe_size)
                    if op == 'video-frame-state-observe':
                        if (backend or actual) not in ('qemu-machine','qemu-dos'):
                            raise ValueError('Source raster state observation requires an explicit native QEMU backend')
                        if session is not None and not getattr(session,'capabilities',{}).get('video_frame_state_observe'):
                            raise ValueError('Source raster state observation requires its native input queries and owned control authority')
                        if (params.get('native_control_token') is not None and session is not None
                                and not getattr(session,'capabilities',{}).get('native_stopped_control')):
                            raise ValueError('Native stopped-control observation requires the native_stopped_control capability')
                        validate_video_frame_state_parameters(**params, allow_references=True)
                    if op == 'stopped-control-arm':
                        if (backend or actual) not in ('qemu-machine','qemu-dos'):
                            raise ValueError('Native stopped-control requires an explicit native QEMU backend')
                        if session is not None and not getattr(session,'capabilities',{}).get('native_stopped_control'):
                            raise ValueError('Native stopped-control requires the native_stopped_control capability')
                        validate_stopped_control_parameters(**params, allow_references=True)
                    if op=='vga-configuration':
                        if session is not None and not getattr(session,'capabilities',{}).get('vga_configuration'):
                            raise ValueError('VGA configuration requires its native extension and virtual/precise profiles')
                        from .qemu_vga_configuration import validate_vga_configuration_parameters
                        validate_vga_configuration_parameters(**params, allow_references=True)
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
                        if (backend or actual)=='qemu-dos':
                            from .qemu_movement import validate_parameters, control_plans
                            validate_parameters(**params, allow_references=True)
                            if session is not None:
                                control_plans(session,params['macro_set'],params['start'],params['stop'],allow_references=True)
                        else:
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
                    if op=='mouse.button-click':
                        if session is not None and not getattr(session,'capabilities',{}).get('virtual_mouse_click'):
                            raise ValueError('Timed physical mouse click requires its native extension and explicit virtual clock profile')
                        from .qemu_mouse_click import validate_mouse_click_parameters
                        # A result reference in one field cannot hide another
                        # field's invalid literal before earlier script effects.
                        samples={'button':'left','hold_ms':80}
                        checked={key:(samples[key] if isinstance(value,str) and value.startswith('$') else value)
                                 for key,value in params.items()}
                        validate_mouse_click_parameters(**checked)
                    if op=='mouse.move-mapped':
                        if session is not None and not getattr(session,'capabilities',{}).get('mapped_mouse_motion'):
                            raise ValueError('Mapped mouse motion requires its native extension and explicit virtual/precise profiles')
                        from .qemu_mapped_mouse import validate_mapped_mouse_parameters
                        validate_mapped_mouse_parameters(**params, allow_references=True)
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
                    if op in ('capture-surface','capture-display') and params.get('max_bytes') is not None:
                        value=params['max_bytes']
                        if not (isinstance(value,str) and value.startswith('$')):
                            bounded(value,'max_bytes',1,16*1024**2)
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
    if (backend or actual) == 'qemu-dos':
        from .qemu_spatial_policy import validate_policy_script
        validate_policy_script(expanded, session=session)
        from .qemu_screenshot_hooks import validate_hook_script
        validate_hook_script(expanded, session=session)
    if (session is not None
            and getattr(session, 'metadata', {}).get('runtime_profile') == 'dos-exec-load-only-v1'
            and any(step['op'] in ('trace', 'trace-until') for step in expanded)
            and session.project.db.in_transaction):
        raise ValueError('Source tracing requires a project outside a caller-owned transaction')
    if session is not None and (backend or actual) in ('qemu-machine','qemu-dos'):
        guarded={'keyboard.key-down','keyboard.key-up','keyboard.press','keyboard.type','mouse.move-relative','mouse.move-mapped','mouse.button-down','mouse.button-click',
                 'mouse.button-up','input-cancel-pending','input-schedule','input-schedule-observe',
                 'input-schedule-retrace',
                 'clock-observe','clock-advance','wait','memory-rule-run','capture-surface','screenshot','frame-probe',
                 'audio-start','audio-observe','audio-stop','capture-audio','mixer-observe',
                 'display-start','display-observe','display-stop','capture-display','display-probe','vga-configuration','retrace-observe',
                 'retrace-wait','clock-sync-start','clock-sync-observe','clock-sync-step','clock-sync-stop'}
        guarded.update(VIDEO_FRAME_SCRIPT_OPERATIONS)
        guarded.add('video-frame-state-observe')
        guarded.add('stopped-control-arm')
        guarded.add('frame-advance')
        project=getattr(session,'project',None)
        if project is not None and project.db.in_transaction:
            pending=(any(step['op']=='run' for step in expanded)
                     and getattr(session,'_input_pending',lambda:False)())
            if pending or any(step['op'] in guarded for step in expanded):
                raise ValueError('Native QEMU input/media observation requires a project outside a caller-owned transaction')
    return expanded


def _suppress_automatic_keeps(function):
    """Resolve the QEMU controller lazily for non-QEMU script users."""
    @wraps(function)
    def invoke(*args, **kwargs):
        from .qemu_save_stop import no_automatic_keeps
        return no_automatic_keeps(function)(*args, **kwargs)
    return invoke


def _source_timeline_step(op, params, backend):
    if backend != 'qemu-dos' or not op.startswith('timeline-'):
        return False
    if op != 'timeline-start':
        return True
    return (params.get('frame_source') == 'source-raster'
            or 'timeline' in params and params.get('frame_source') is None)


@rpc_budget
@_suppress_automatic_keeps
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
    native_frames = getattr(session,'metadata',{}).get('backend') in ('qemu-dos','qemu-chip8')
    source_steps = ((getattr(session,'backend_name',None) or getattr(session,'metadata',{}).get('backend'))
        in ('qemu-machine','qemu-dos') and bool(getattr(session,'capabilities',{}).get('frame_step')))
    capabilities = (getattr(session,'capabilities',{}) if native_frames or source_steps else
                    getattr(getattr(session,'rpc',None),'capabilities',{}))
    backend = getattr(session,'metadata',{}).get('backend')
    if any(step['op'] in frame_operations and not (native_frames and step['op']=='frame-inputs')
            and not (source_steps and step['op']=='frame-advance')
            and not (isinstance(capabilities,dict) and capabilities.get('source_raster_timeline')
                     and _source_timeline_step(step['op'],step,backend)) for step in steps):
        if not isinstance(capabilities,dict) or not capabilities.get('frame_timeline'):
            raise ValueError('Frame/timeline script operations require backend frame_timeline capability')
    for step in steps:
        if step['op']=='macro':
            params={k:v for k,v in step.items() if k not in ('op','as','expect','timeout_ms')}
            session._macro_plan(**params)
        elif step['op']=='move':
            if getattr(session,'metadata',{}).get('backend')=='qemu-dos':
                from .qemu_movement import control_plans
                control_plans(session,step['macro_set'],step['start'],step['stop'],allow_references=True)
            else:
                for key in ('start','stop'):
                    call=step[key]
                    session._macro_plan(step['macro_set'],call['name'],call.get('args',{}))
    restore_operations = {'load-state','load-machine-state','load-le-source-state','le-rewind',
                          'load-anchor-stone','rewind','delta-recover','timeline-rewind'}
    def frame_owned_keys():
        from .keyboard_input import KEYS
        result = session.keyboard_state() if native_frames else session.call('input.keyboard.state')
        keyboard = result.get('keyboard') if isinstance(result,dict) else None
        keys = keyboard.get('frame_keys') if isinstance(keyboard,dict) else None
        if not isinstance(keys,list) or any(not isinstance(key,str) or key not in KEYS for key in keys):
            raise ValueError('Native frame input ownership is unavailable')
        normalized = {'escape' if key=='esc' else key for key in keys}
        if len(normalized) != len(keys):
            raise ValueError('Native frame input ownership contains duplicate keys')
        return normalized
    frame_owned_before = None
    native_key_tracking = native_frames and bool(capabilities.get('frame_key_ownership'))
    timeline_input = isinstance(capabilities,dict) and (
        capabilities.get('frame_timeline') or capabilities.get('source_raster_timeline'))
    track_restored_input = ((not native_frames or native_key_tracking) and timeline_input
                           and any(step['op'] in restore_operations for step in steps))
    track_native_edges = native_key_tracking and any(step['op'] in ('frame-inputs','timeline-advance') for step in steps)
    if track_restored_input or track_native_edges:
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
    frame_restore_completed = False
    native_frame_touched = False
    entry_released = set()
    entry_reacquired = set()

    def record_accepted_frame_edges(receipt):
        if not isinstance(receipt, dict) or frame_owned_before is None:
            return
        from .qemu_frame_keys import _CANONICAL
        for edge in receipt.get('edges', []):
            if not isinstance(edge,dict) or type(edge.get('pressed')) is not bool:
                continue
            key = _CANONICAL.get(edge.get('key'),edge.get('key'))
            key = 'escape' if key == 'esc' else key
            if key not in frame_owned_before:
                continue
            if edge['pressed']:
                if key in entry_released:
                    entry_reacquired.add(key)
            else:
                entry_released.add(key)

    def record_frame_result(op, result):
        if op == 'frame-inputs':
            record_accepted_frame_edges(result)
        elif op == 'timeline-advance' and isinstance(result,dict):
            for item in result.get('frames',[]):
                if isinstance(item,dict):
                    record_accepted_frame_edges(item.get('frame',{}).get('input'))
            for receipt in result.get('pending_inputs',[]):
                record_accepted_frame_edges(receipt)
    encoded = json.dumps(script,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if time.monotonic() >= deadline:
        raise TimeoutError('Script host-time budget expired before route publication')
    source = session._artifact('route.fdisbull.json','script',encoded,{'format':script['format']})
    results = dict(bindings or {}); records = []; failure = None; primary_failure = None
    from .qemu_checkpoint_script import OPERATIONS as CHECKPOINT_OPERATIONS
    checkpoint_script = (getattr(session,'metadata',{}).get('backend')=='qemu-dos'
                         and any(step['op'] in CHECKPOINT_OPERATIONS for step in steps))
    action_script = (getattr(session,'metadata',{}).get('backend')=='qemu-dos'
                     and any(step['op']=='scene-act' for step in steps))
    action_owner = None
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
            unresolved = {k:v for k,v in step.items() if k not in ('op','as','expect')}
            if step['op']=='move' and getattr(session,'metadata',{}).get('backend')=='qemu-dos':
                # Only this already validated local lease namespace belongs to
                # the movement start, even if an outer binding is named start.
                from .qemu_movement import local_lease_reference
                def stop_arguments(value):
                    if local_lease_reference(value):return value
                    if isinstance(value,dict):return {k:stop_arguments(v) for k,v in value.items()}
                    if isinstance(value,list):return [stop_arguments(v) for v in value]
                    return resolve(value)
                stop_value=unresolved.pop('stop')
                params=resolve(unresolved)
                if isinstance(stop_value,dict):
                    params['stop']={k:(stop_arguments(v) if k=='args' else resolve(v)) for k,v in stop_value.items()}
                else:params['stop']=resolve(stop_value)
            else:
                params = resolve(unresolved)
            if checkpoint_script and step['op'] in CHECKPOINT_OPERATIONS:
                from .qemu_checkpoint_script import validate_parameters
                validate_parameters(step['op'],params,session=session,references=False)
            if step['op'] in ('load-machine-state','save-le-source-state','load-le-source-state',
                              'le-rewind-start','le-rewind-record','le-rewind'):
                if 'timeout_ms' in params:
                    bounded(params['timeout_ms'],'timeout_ms',1,600000)
                params['timeout_ms']=min(params.get('timeout_ms',60000),remaining)
            if checkpoint_script and step['op']=='load-state':
                params['timeout_ms']=min(params.get('timeout_ms',60000),remaining)
            if native_key_tracking and step['op']=='frame-inputs':
                params['timeout_ms']=min(params.get('timeout_ms',remaining),remaining)
            if native_frames and step['op'] in ('delta-start','delta-record','delta-rewind','delta-recover'):
                params['timeout_ms']=min(params.get('timeout_ms',remaining),remaining)
            if step['op']=='input-schedule-retrace':
                # Validate resolved options before the budget clamp can turn
                # an invalid supplied timeout into a valid remaining integer.
                from .qemu_input_schedule import validate_retrace_input_parameters
                validate_retrace_input_parameters(**params)
            if (step['op']=='keyboard.press'
                    and getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')):
                from .qemu_keyboard_press import validate_keyboard_press_parameters
                validate_keyboard_press_parameters(**params)
            if (step['op']=='keyboard.type'
                    and getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')):
                from .qemu_keyboard_type import validate_keyboard_type_parameters
                validate_keyboard_type_parameters(**params)
            if step['op']=='mouse.button-click':
                from .qemu_mouse_click import validate_mouse_click_parameters
                validate_mouse_click_parameters(**params)
            if step['op']=='mouse.move-mapped':
                from .qemu_mapped_mouse import validate_mapped_mouse_parameters
                validate_mapped_mouse_parameters(**params)
            if step['op']=='display-probe':
                from .qemu_display import validate_display_probe_parameters
                validate_display_probe_parameters(**params)
            if step['op'] == 'frame-probe' and (getattr(session,'backend_name',None)
                    or getattr(session,'metadata',{}).get('backend')) in ('qemu-machine','qemu-dos'):
                from .qemu_video_frame import validate_video_frame_probe
                validate_video_frame_probe(**params, frame_size=video_vm_size(getattr(session, 'vm', None)))
                params['timeout_ms'] = min(params.get('timeout_ms', 1000), remaining)
            if step['op'] == 'frame-advance' and source_steps:
                from .qemu_frame_step import validate_source_frame_advance
                validate_source_frame_advance(**params)
                params['timeout_ms'] = min(params.get('timeout_ms', 10000), remaining)
            if step['op'] in VIDEO_FRAME_SCRIPT_OPERATIONS:
                validate_video_frame_script_parameters(step['op'], params,
                                                       frame_size=video_vm_size(getattr(session, 'vm', None)))
                default = 5000 if step['op'] == 'video-frame-advance' else 1000
                params['timeout_ms'] = min(params.get('timeout_ms', default), remaining)
            if step['op'] == 'video-frame-state-observe':
                validate_video_frame_state_parameters(**params)
                params['timeout_ms'] = min(params.get('timeout_ms', 1000), remaining)
            if step['op'] == 'stopped-control-arm':
                validate_stopped_control_parameters(**params)
                params['timeout_ms'] = min(params.get('timeout_ms', 1000), remaining)
            if step['op']=='vga-configuration':
                from .qemu_vga_configuration import validate_vga_configuration_parameters
                validate_vga_configuration_parameters(**params)
            if (step['op']=='step'
                    and getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')):
                # Resolve and validate before the common timeout clamp; a large
                # invalid literal/reference must not become a valid allowance.
                from .qemu_steps import validate_step_parameters
                from .qemu_step_over import validate_step_mode
                validate_step_mode(params.get('mode','into'),params.get('count',1))
                validate_step_parameters(**{key:value for key,value in params.items() if key!='mode'})
            if (step['op']=='scene-wait' and getattr(session,'metadata',{}).get('backend')=='qemu-dos'):
                from .qemu_scene_wait import validate_parameters
                validate_parameters(**params)
            if action_script and step['op']=='scene-act':
                from .qemu_scene_act import preflight
                # Resolved values are still declarations. Validate before a
                # remaining-time clamp could make an invalid timeout valid.
                preflight(session, **params)
            if step['op'] in ('run','clock-advance','retrace-observe','retrace-wait',
                             'input-schedule-retrace','display-probe','vga-configuration','mouse.move-mapped',
                             'clock-sync-start','clock-sync-observe','clock-sync-step','clock-sync-stop',
                             'trace','trace-until','step','engine-cycle','rewind-record','delta-record','frame-advance','timeline-advance','timeline-rewind','wait','scene-wait','scene-click','scene-act','macro','move','proof-check','spatial-action'):
                requested=params.get('timeout_ms')
                if (requested is None and step['op']=='proof-check'
                        and getattr(session,'metadata',{}).get('backend')=='qemu-dos'):
                    requested=1000
                if requested is None:requested=min(1000,remaining) if step['op'] in ('display-probe','vga-configuration','mouse.move-mapped') else remaining
                params['timeout_ms'] = min(requested,remaining,60000 if step['op'].startswith('scene-') else remaining)
            if (step['op']=='memory-rule-run'
                    and getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')):
                params['timeout_ms']=min(params.get('timeout_ms',10000),remaining,60000)
            if step['op']=='assert':
                if params['value'] != params['equals']:
                    raise ValueError(f"Assertion failed: {params['value']!r} != {params['equals']!r}")
                result = {'matched':True}
            else:
                # Record intended input before dispatch so an uncertain failure
                # follows the same terminal cleanup as legacy keyboard input.
                prior_input_touched = keyboard_touched
                frame_edges = ((step['op']=='frame-inputs' and params['edges'])
                        or (step['op']=='timeline-advance' and any(item['edges'] for item in params.get('inputs') or [])))
                if frame_edges and native_key_tracking:
                    native_frame_touched = True
                if ((step['op'].startswith('keyboard.') and step['op']!='keyboard.state')
                        or step['op'].startswith('mouse.') or step['op'] in ('input-cancel-pending','input-schedule','input-schedule-retrace')
                        or (step['op']=='trace-until' and params.get('action') is not None)
                        or (frame_edges and not native_key_tracking)):
                    keyboard_touched=True
                if track_restored_input and step['op'] in restore_operations:
                    frame_restore_attempted = True
                checkpoint_owner = session.vm if checkpoint_script and step['op'] in CHECKPOINT_OPERATIONS else None
                if action_script and step['op']=='scene-act':
                    # This operation owns its single attempted arm and failure
                    # disposition. A readiness refusal never touches input; a
                    # known first stop retains its holds without legacy cleanup.
                    action_owner = session.vm
                result = getattr(session,OPERATIONS[step['op']])(**params)
                if checkpoint_owner is not None and step['op'].startswith('load-'):
                    replacement = session.vm
                    if (getattr(replacement,'lock',None) is not checkpoint_owner.lock or not isinstance(result,dict)
                            or result.get('capture_epoch') != getattr(session,'_runtime_epoch',None)
                            or result.get('checkpoint_epoch') != getattr(session,'_checkpoint_epoch',None)):
                        error = ValueError('Checkpoint script restore owner differs from its returned receipt')
                        error.result = result
                        raise error
                    checkpoint_owner = replacement
                if (step['op']=='macro'
                        and getattr(session,'metadata',{}).get('backend')=='qemu-dos'):
                    # A returned native lease is owned by this outer route.
                    # Preserve entry holds for observation-only macros, but do
                    # not strand an inner macro's input if a later step fails.
                    inner_steps=(result.get('execution') or {}).get('steps',[])
                    before_input=(result.get('input_before') or {}).get('physical')
                    after_input=(result.get('input_after') or {}).get('physical')
                    if (any(item.get('op') in ('keyboard.key-down','keyboard.key-up','keyboard.press','keyboard.type')
                            for item in inner_steps)
                            or isinstance(before_input,dict) and isinstance(after_input,dict) and before_input!=after_input):
                        keyboard_touched=True
                if native_key_tracking:
                    record_frame_result(step['op'],result)
                if track_restored_input and step['op'] in restore_operations:
                    frame_restore_completed = True
                if (step['op']=='trace-until' and result.get('action',{}).get('dispatch')
                        in ('not_requested','not_dispatched','skipped_initial_match')):
                    keyboard_touched = prior_input_touched
            record['result'] = result
            if step['op'] == 'video-frame-advance':
                if (not isinstance(result,dict) or result.get('format') != 'fdisbull-video-frame-advance-1'
                        or result.get('advance_completed') is not True):
                    raise ValueError('Source frame advance stopped before its owned completion stop')
            if action_script and step['op']=='scene-act' and time.monotonic() >= deadline:
                from .qemu_scene_act import _quarantine
                error = TimeoutError('Scene action returned after the script deadline')
                error.result = error.scene_act_result = result
                _quarantine(session,action_owner,error)
                raise error
            if checkpoint_script and step['op'] in CHECKPOINT_OPERATIONS and time.monotonic() >= deadline:
                error = TimeoutError('Checkpoint step returned after the script deadline')
                error.result = result
                from .qemu_dos_checkpoint import _close_failed
                checkpoint_owner._fdisbull_control_quarantine = 'late checkpoint script result'
                _close_failed(session,error,checkpoint_owner)
                raise error
            if ((native_frames and step['op'] in ('timeline-advance','frame-advance'))
                    or source_steps and step['op']=='frame-advance'):
                if (not isinstance(result,dict) or result.get('outcome') != 'completed'
                        or result.get('completed_frames') != params.get('frames',1)):
                    raise ValueError('Frame advancement stopped before completing the requested native frame boundaries')
            if native_frames and step['op']=='delta-record':
                if (not isinstance(result,dict) or result.get('outcome') != 'completed'
                        or result.get('recorded_count') != params.get('count',1)):
                    raise ValueError('Selected CPU/RAM recording stopped before the requested native intervals')
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
                native_machine = getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos','qemu-chip8')
                complete = (result.get('outcome')=='step' and result.get('timed_out') is False
                            if native_machine else result.get('completed'))
                if (getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')
                        and params.get('mode','into')=='over'):
                    from .qemu_step_over import FORMAT as STEP_OVER_FORMAT
                    complete = (result.get('format') == STEP_OVER_FORMAT
                                and result.get('step_over_completed') is True
                                and result.get('timed_out') is False)
                    if not complete:
                        error = ValueError('CALL step-over stopped without its required completion evidence')
                        error.result = result
                        raise error
                if (getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')
                        and params.get('count',1)>1):
                    from .qemu_steps import FORMAT
                    complete = (complete and result.get('format') == FORMAT
                                and result.get('complete') is True
                                and result.get('requested_count') == params['count']
                                and result.get('completed_count') == params['count'])
                if not complete:
                    if (getattr(session,'metadata',{}).get('backend') in ('qemu-machine','qemu-dos')
                            and params.get('count',1)>1):
                        raise ValueError('Counted steps stopped before the requested native step boundaries')
                    raise ValueError('Step stopped before the requested instruction boundary')
            if step['op']=='engine-cycle' and result.get('outcome')!='cycle':
                raise ValueError('Engine did not reach the requested cycle boundary')
            if _after_step is not None:_after_step(step,result)
            if 'as' in step:
                results[step['as']] = result
            record.update(ok=True,result=result)
        except Exception as error:
            primary_failure = error
            failure = {'index':index,'op':step['op'],'type':type(error).__name__,'message':str(error)}
            record.update(ok=False,error=failure)
            if hasattr(error,'result'):record['result']=error.result
            if step['op'] in VIDEO_FRAME_SCRIPT_OPERATIONS:
                for field in ('video_frame_evidence','video_frame_advance_evidence'):
                    detail = getattr(error,field,None)
                    if isinstance(detail,dict) and detail is not getattr(error,'result',None):
                        record[field] = detail
                cleanup = getattr(error,'video_frame_cleanup_error',None)
                if isinstance(cleanup,str):record['video_frame_cleanup_error'] = cleanup
            if step['op'] == 'video-frame-state-observe':
                detail = getattr(error,'video_frame_state_evidence',None)
                if isinstance(detail,dict) and detail is not getattr(error,'result',None):
                    record['video_frame_state_evidence'] = detail
                for field in ('video_frame_state_cleanup_error', 'video_frame_cleanup_error',
                              'video_frame_file_cleanup_error', 'video_frame_state_evidence_error',
                              'native_stopped_control_cleanup_error'):
                    detail = getattr(error,field,None)
                    if isinstance(detail,str):record[field] = detail
            if step['op'] == 'stopped-control-arm':
                detail = getattr(error,'native_stopped_control_evidence',None)
                if isinstance(detail,dict) and detail is not getattr(error,'result',None):
                    record['native_stopped_control_evidence'] = detail
                detail = getattr(error,'native_stopped_control_cleanup_error',None)
                if isinstance(detail,str):record['native_stopped_control_cleanup_error'] = detail
            if checkpoint_script and step['op'] in CHECKPOINT_OPERATIONS and hasattr(error,'checkpoint_result'):
                record['checkpoint_result']=error.checkpoint_result
            if checkpoint_script and step['op'] in CHECKPOINT_OPERATIONS:
                cleanup_errors={field:getattr(error,field) for field in
                    ('machine_cleanup_error','new_machine_cleanup_error')
                    if isinstance(getattr(error,field,None),str)}
                if cleanup_errors:record['checkpoint_cleanup']=cleanup_errors
            if (step['op']=='scene-wait' and getattr(session,'metadata',{}).get('backend')=='qemu-dos'
                    and isinstance(getattr(error,'scene_wait_result',None),dict)
                    and error.scene_wait_result is not getattr(error,'result',None)):
                record['scene_wait_result']=error.scene_wait_result
            if action_script and step['op']=='scene-act':
                partial = getattr(error,'scene_act_result',None)
                if isinstance(partial,dict) and partial is not getattr(error,'result',None):
                    record['scene_act_result']=partial
                cleanup_errors={field:getattr(error,field) for field in
                    ('scene_act_cleanup_error','scene_act_owner_cleanup_error','scene_act_evidence_error')
                    if isinstance(getattr(error,field,None),str)}
                if cleanup_errors:record['scene_act_cleanup']=cleanup_errors
            if (step['op']=='trace-until' and isinstance(getattr(error,'result',None),dict)
                    and error.result.get('action',{}).get('dispatch')
                    in ('not_requested','not_dispatched','skipped_initial_match')):
                keyboard_touched = prior_input_touched
        records.append(record)
        if failure:
            break
    cleanup=None
    restored_input_held = restore_ownership_unknown = False
    if failure and (frame_restore_attempted or native_frame_touched) and not keyboard_touched:
        try:
            current = frame_owned_keys()
            if frame_owned_before is None:
                restore_ownership_unknown = bool(current)
            else:
                restored_input_held = bool(current - frame_owned_before
                    or current.intersection(entry_reacquired)
                    or native_key_tracking and frame_restore_completed and current)
        except Exception:
            # An attempted restore with no verifiable ownership readback must
            # not leave a failed route free to resume an unknown held key.
            restore_ownership_unknown = True
    if failure and (keyboard_touched or restored_input_held or restore_ownership_unknown
                    or set(getattr(session,'_keyboard_leases',{}))-owned_before):
        # A failed route must not leave input depressed or execute through a stop.
        reason = ('Failed script frame input ownership is unknown after restore' if restore_ownership_unknown
                  else 'Failed script owned unreleased input')
        if checkpoint_script or action_script:
            try:
                session.close()
                cleanup={'closed':True,'reason':reason}
            except BaseException as error:
                cleanup={'closed':getattr(session,'closed',False),'reason':reason,
                         'error':{'type':type(error).__name__,'message':str(error)}}
                if primary_failure is not None:
                    primary_failure.script_cleanup_error=cleanup['error']
                else:
                    raise
        else:
            session.close();cleanup={'closed':True,'reason':reason}
    report = {'format':'fdisbull-script-result-1','script_artifact':source['artifact'],
              'script_sha256':hashlib.sha256(encoded).hexdigest(),'run':session.run_id,
              'ok':failure is None,'error':failure,'completed_steps':sum(r['ok'] for r in records),
              'requested_steps':len(steps),'host_elapsed_ms':round((time.monotonic()-started)*1000,3),
              'steps':records,'input_cleanup':cleanup}
    try:
        if (checkpoint_script or action_script) and time.monotonic() >= deadline:
            raise primary_failure or TimeoutError('Checkpoint script deadline expired before report publication'
                if checkpoint_script else 'Scene action script deadline expired before report publication')
        evidence = session._artifact('route-result.json','script-result',json.dumps(report,indent=2).encode(),
                                     {'ok':report['ok'],'completed_steps':report['completed_steps']})
        if (checkpoint_script or action_script) and time.monotonic() >= deadline:
            report = {**report,'artifact':evidence['artifact']}
            raise primary_failure or TimeoutError('Checkpoint script report publication exceeded its deadline'
                if checkpoint_script else 'Scene action script report publication exceeded its deadline')
    except BaseException as error:
        if checkpoint_script and not action_script:
            from .qemu_checkpoint_script import retain_script_failure
            if primary_failure is not None and error is not primary_failure:
                primary_failure.script_publication_error={'type':type(error).__name__,'message':str(error)}
                retain_script_failure(primary_failure,report)
                raise primary_failure from error
            retain_script_failure(error,report)
        if action_script:
            primary = primary_failure or error
            if error is not primary:
                primary.script_publication_error={'type':type(error).__name__,'message':str(error)}
            primary.script_result=report
            primary._qemu_scene_action_script_error=True
            # Preserve the action's own first-stop/refusal disposition when
            # the original error merely reaches its expired report boundary.
            action_input_attempted = any(
                record['op']=='scene-act' and any(
                    isinstance(receipt,dict) and receipt.get('format')=='fdisbull-scene-action-1'
                    and receipt.get('input',{}).get('attempted') is True
                    for receipt in (record.get('result'),record.get('scene_act_result')))
                for record in records)
            if action_owner is not None and action_input_attempted and error is not primary_failure:
                from .qemu_scene_act import _quarantine
                _quarantine(session,action_owner,primary)
            if primary is not error:
                raise primary from error
        raise
    if _bindings_out is not None:_bindings_out.update(results)
    return {**report,'artifact':evidence['artifact']}
