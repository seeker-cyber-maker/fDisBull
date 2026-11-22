"""Real DOS EXEC processes on the native QEMU machine controller.

The boot disk, prepared disk, and analyzed executable have separate identities.
DOS creates the PSP, relocates MZ images and performs termination. The authored
guest helper reports those boundaries; the host verifies them against stopped
memory before exposing a source binding. This is an observation protocol, not
an authentication boundary against a guest that controls its whole machine.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import struct
import tempfile
import time
import uuid

from .dos_launch import guest_name
from .dosbox_rpc import DebuggerError
from .qemu_dos import QemuDOSSession
from .qemu_dos_checkpoint import process_save_operation
from .qemu_machine import (MachineContext, MachineDebugSession, QemuMachine,
                           machine_operation, machine_trace_operation)
from .qemu_dos_trace import QemuDOSSourceTraceMixin
from .qemu_dos_tasks import QemuDOSTaskMixin
from .qemu_dos_task_views import QemuDOSTaskViewMixin, COMMANDS as TASK_VIEW_COMMANDS
from .qemu_dos_scheduler import QemuDOSSchedulerMixin, COMMANDS as SCHEDULER_COMMANDS
from .qemu_dos_preemption import COMMAND as PREEMPTION_COMMAND
from .qemu_dos_history import QemuDOSHistoryMixin
from .qemu_dos_frames import QemuDOSFramesMixin, FRAME_COMMANDS
from .qemu_frame_keys import QemuFrameKeysMixin, FRAME_KEY_COMMANDS, REPEAT_QUERY
from .qemu_cpu_deltas import QemuCpuDeltaMixin
from .qemu_experiments import QemuExperimentMixin
from .qemu_workspace import QemuDOSWorkspaceMixin as QemuWorkspaceMixin
from .qemu_dos_source_admission import QemuDOSSourceAdmissionMixin
from .qemu_dos_le_binding import QemuDOSLEBindingMixin
from .qemu_macros import QemuMacroSessionMixin
from .qemu_runtime_memory import QemuRuntimeMemoryMixin
from .qemu_proofs import QemuProofMixin
from .qemu_spatial_policy import QemuSpatialPolicyMixin, initial_policy
from .qemu_movement import QemuMovementMixin
from .qemu_scenes import QemuSceneObservationMixin
from .qemu_screenshot_hooks import QemuScreenshotHookMixin
from .qemu_pending_events import pending_status_operation, pending_status_owner
from .qemu_int33_mouse import observe_int33_mouse
from .qemu_int33_mouse_control import (mouse_button_down_int33, mouse_move_int33,
                                     validate_int33_input)
from .qemu_video_frame import validate_video_frame_parameters


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _word(data, offset):
    return struct.unpack_from('<H', data, offset)[0]


def _async_process_operation(function):
    return machine_trace_operation(function, label='DOS asynchronous control',
                                   default_timeout_ms=30000)


def _pending_dos_status(function):
    return pending_status_operation(_async_process_operation(function), dos=True)


def relocated_source(source, dos, image_format, report):
    """Derive the real load span from DOS's returned entry, not PSP+10h.

    Reapply each relocation to original file bytes in its original order. A
    duplicate relocation therefore adds the runtime segment twice. Unwritten
    minimum allocation and appended overlay bytes are not compared as though
    DOS loaded them into the module. Account for the exact startup stack words
    written by DOS only where they intersect the file-backed module.
    """
    if image_format == 'COM':
        segment = report['child_psp']
        if report['entry_cs'] != segment or report['entry_ip'] != 0x100:
            raise DebuggerError('DOS COM entry does not match the observed PSP:0100')
        if report['stack_ss'] != segment:
            raise DebuggerError('DOS COM stack is outside its startup PSP segment')
        expected = source
        runtime_base = segment * 16 + 0x100
    elif image_format == 'MZ':
        header = dos['header_fields']
        segment = (report['entry_cs'] - header['e_cs']) & 0xffff
        if report['entry_ip'] != header['e_ip']:
            raise DebuggerError('DOS MZ entry differs from its original header')
        if (report['stack_ss'] != (segment + header['e_ss']) & 0xffff
                or report['stack_sp'] != header['e_sp']):
            raise DebuggerError('DOS MZ startup stack differs from its original header')
        expected = bytearray(source[dos['header_size']:dos['declared_file_size']])
        for relocation in dos['relocations']:
            offset = relocation['file_offset'] - dos['header_size']
            struct.pack_into('<H', expected, offset, (_word(expected, offset) + segment) & 0xffff)
        expected = bytes(expected)
        runtime_base = segment * 16
    else:
        raise ValueError('Native DOS process launch requires original COM or classic MZ input')
    entry = report['entry_cs'] * 16 + report['entry_ip']
    stack = report['stack_ss'] * 16 + report['stack_sp']
    if (not expected or runtime_base + len(expected) > 0x100000
            or not runtime_base <= entry < runtime_base + len(expected)
            or stack > 0x100000):
        raise DebuggerError('DOS process requires an unwrapped, file-backed real-mode entry')
    expected = bytearray(expected)
    relocated_sha256 = _sha(expected)
    writes = []
    startup_words = []
    if image_format == 'COM':
        startup_words.append(('com-near-return-zero', report['stack_sp'], 0))
    startup_words.append(('load-only-initial-ax', report['raw_stack_sp'], report['initial_ax']))
    for kind, offset, value in startup_words:
        address = report['stack_ss'] * 16 + offset
        start, end = max(address, runtime_base), min(address+2, runtime_base+len(expected))
        if start < end:
            index = start-runtime_base
            replacement = struct.pack('<H', value)[start-address:end-address]
            writes.append(dict(kind=kind, runtime_address=start,
                file_offset=dos['header_size']+index, module_offset=index,
                before_hex=bytes(expected[index:index+end-start]).hex(), after_hex=replacement.hex()))
            expected[index:index+end-start] = replacement
    return bytes(expected), dict(static_base=dos['image_base'], runtime_base=runtime_base,
                         module_size=len(expected), load_segment=segment,
                         delta=runtime_base-dos['image_base'], entry_linear=entry,
                         stack_linear=stack, file_offset=dos['header_size'],
                         relocated_module_sha256=relocated_sha256, loader_writes=writes)


def observe_mcbs(read, first_segment, *, maximum=512):
    """Walk the observed DOS allocation chain; stale freed headers do not count."""
    if type(first_segment) is not int or not 1 <= first_segment < 0xffff:
        raise DebuggerError('DOS did not supply a valid first MCB segment')
    segment = first_segment
    blocks = []
    for _ in range(maximum):
        raw = read(segment * 16, 16)
        if len(raw) != 16 or raw[0] not in (ord('M'), ord('Z')):
            raise DebuggerError('Observed DOS MCB chain is malformed')
        paragraphs = _word(raw, 3)
        following = segment + paragraphs + 1
        if following > 0x10000:
            raise DebuggerError('Observed DOS allocation wraps the real-mode address space')
        blocks.append(dict(mcb_segment=segment, segment=segment+1,
                           owner_psp=_word(raw, 1), paragraphs=paragraphs,
                           start=(segment+1)*16, end=following*16,
                           terminal=raw[0] == ord('Z')))
        if raw[0] == ord('Z'):
            return blocks
        segment = following
    raise DebuggerError('Observed DOS MCB chain exceeds its bounded inventory')


def observe_devices(read, segment, offset, *, maximum=64):
    """Observe a validated DOS 3.1+ NUL chain, without certifying device I/O."""
    address = segment * 16 + offset + 0x22
    scope = 'DOS List-of-Lists NUL chain; registration is not device I/O qualification'
    if not 0 <= address <= 0x100000-18:
        return dict(status='unknown', reason='List-of-Lists address is outside the admitted range', scope=scope)
    first = read(address, 18)
    if first[10:18] != b'NUL     ' or not _word(first, 4) & 0x8000:
        return dict(status='unknown', reason='Expected NUL device header was not observed', scope=scope)
    seen = set()
    headers = []
    for _ in range(maximum):
        if address in seen or not 0 <= address <= 0x100000-18:
            return dict(status='incomplete', reason='Invalid or cyclic device chain', headers=headers, scope=scope)
        seen.add(address)
        raw = read(address, 18)
        attributes = _word(raw, 4)
        headers.append(dict(address=address, attributes=attributes,
                            character=bool(attributes & 0x8000),
                            name=raw[10:18].decode('ascii', errors='replace').rstrip() if attributes & 0x8000 else None,
                            block_units=None if attributes & 0x8000 else raw[10],
                            strategy_offset=_word(raw, 6), interrupt_offset=_word(raw, 8)))
        next_offset, next_segment = struct.unpack_from('<HH', raw)
        if next_offset == 0xffff:
            return dict(status='observed', headers=headers, scope=scope)
        address = next_segment * 16 + next_offset
    return dict(status='incomplete', reason='Device header budget exhausted', headers=headers, scope=scope)


class QemuDOSProcessSession(QemuScreenshotHookMixin, QemuSceneObservationMixin, QemuMovementMixin, QemuSpatialPolicyMixin, QemuProofMixin, QemuRuntimeMemoryMixin, QemuMacroSessionMixin, QemuDOSLEBindingMixin, QemuDOSSourceAdmissionMixin, QemuWorkspaceMixin, QemuExperimentMixin, QemuCpuDeltaMixin, QemuFrameKeysMixin, QemuDOSFramesMixin, QemuDOSHistoryMixin, QemuDOSSchedulerMixin, QemuDOSTaskViewMixin, QemuDOSTaskMixin, QemuDOSSourceTraceMixin, MachineDebugSession):
    """One source-bound DOS process and its still-owned machine, per cold boot.

    All controls retain machine address semantics and a single breakpoint
    registry. Process observations accompany them; a vCPU is never relabeled
    as a DOS task. The internal return breakpoint is reserved until observed.
    """
    backend_id = 'qemu-dos'
    observe_int33_mouse = machine_trace_operation(
        observe_int33_mouse, label='Stopped INT33 mouse observation',
        parameter_validator=validate_video_frame_parameters)
    mouse_move_int33 = machine_trace_operation(
        mouse_move_int33, label='Positioned INT33 mouse motion',
        parameter_validator=validate_int33_input)
    mouse_button_down_int33 = machine_trace_operation(
        mouse_button_down_int33, label='Positioned INT33 mouse press',
        parameter_validator=validate_int33_input)

    def __init__(self, project, executable, game_dir, *, boot_image=None, mcopy=None,
                 startup_batch='FDAUTO.BAT', arguments='', version=None,
                 boot_timeout_ms=30000, guest_profile=None, transport='unix',
                 firmware=None, clock_profile='standard', audio_profile='off', retrace_profile='standard',
                 checkpoint_tool=None, _on_spawn=None, directory=None, file_mode=None, freedos_runtime=None,
                 generation=None, spatial_mode=None, fair_play=False, frame_key_repeat_profile=None):
        from .dos_process_image import prepare_process_disk
        from .debugger import stamp

        self.closed = False
        self._staging = None
        self.vm = None
        self._return_breakpoint = None
        self._launching = True
        self._serial_buffer = bytearray()
        self._process = None
        self._owned_machine_restored = False
        self._published = False
        self._spatial_mode, self._fair_play = initial_policy(spatial_mode, fair_play)
        self._allow_assisted_travel = self._spatial_mode == 'assisted' and not self._fair_play
        self._dos_workspace_enabled = (boot_image is None or directory is not None
                                       or file_mode is not None or freedos_runtime is not None or generation is not None)
        workspace_launch = None
        self._epoch_number = 1
        if project.db.in_transaction:
            raise ValueError('DOS process launch requires a project outside a caller-owned transaction')
        selected = project.version(version)
        if project.meta['format'] not in ('COM', 'MZ') or selected['parent'] is not None:
            raise ValueError('Native DOS process launch requires an original unpatched COM/MZ project')
        dos = project._document(selected['id'])['dos']
        if dos.get('secondary_format'):
            raise ValueError('Native DOS process launch does not qualify secondary executable stubs')
        if type(boot_timeout_ms) is not int or not 1 <= boot_timeout_ms <= 600000:
            raise ValueError('DOS process startup timeout must be 1..600000 ms')
        self._deadline = time.monotonic() + boot_timeout_ms / 1000
        from .qemu_clock import machine_clock_configuration
        machine_clock_configuration(clock_profile, 1)
        from .qemu_audio import machine_audio_configuration
        machine_audio_configuration(audio_profile, clock_profile)
        from .qemu_retrace import machine_retrace_configuration
        machine_retrace_configuration(retrace_profile, clock_profile)
        if frame_key_repeat_profile is not None:
            from .qemu_frame_keys import DOSBOX_REPEAT_PROFILE
            if frame_key_repeat_profile != DOSBOX_REPEAT_PROFILE or clock_profile != 'virtual':
                raise ValueError('DOSBox repeat pacing requires the dosbox-millisecond profile and a virtual clock')
        if not isinstance(arguments, str):
            raise ValueError('DOS arguments must be a CP437 command-tail string')
        try:
            tail = arguments.encode('cp437')
        except UnicodeEncodeError as error:
            raise ValueError('DOS arguments must fit CP437') from error
        if len(tail) > 126 or any(byte in tail for byte in (0, 10, 13)):
            raise ValueError('DOS command tail requires at most 126 bytes without NUL/CR/LF')
        if generation is None:
            game_directory = Path(game_dir).expanduser().resolve(strict=True)
            source = (game_directory / project.meta['filename']).resolve(strict=True)
            if source.parent != game_directory or not source.is_file() or source.stat().st_size > 64*1024*1024:
                raise ValueError('DOS source must be a regular file directly inside game_dir, at most 64 MiB')
            if _sha(source.read_bytes()) != project.meta['source_sha256']:
                raise ValueError('DOS executable does not match the project source hash')
        if self._dos_workspace_enabled:
            from .dos_workspace_launch import prepare_workspace
            self._staging = tempfile.TemporaryDirectory(prefix='fdisbull-dos-process-')
            try:
                workspace_launch = prepare_workspace(project, game_dir, directory, file_mode,
                                                       freedos_runtime, boot_image, self._staging.name,
                                                       generation=generation, version_id=selected['id'])
            except BaseException:
                self._staging.cleanup()
                raise
            image = workspace_launch['image']
            source = workspace_launch['source']
            self._workspace_target = workspace_launch['target']
            self._workspace_runtime_component = workspace_launch['runtime_component']
            self._workspace_launch_identity = dict(runtime=workspace_launch['runtime_component'],
                layout=workspace_launch['layout']['partitions'], source_dospath=workspace_launch['source_dospath'])
        else:
            image = Path(boot_image).expanduser().resolve(strict=True)
        try:
            profile = QemuDOSSession._admit_guest_profile('dos' if guest_profile is None else guest_profile, image)
            copy_tool = shutil.which('mcopy') if mcopy is None else mcopy
            if copy_tool is None:
                raise ValueError('Native DOS process staging requires mcopy; supply dos_mcopy explicitly')
            source_data = source.read_bytes()
            if _sha(source_data) != project.meta['source_sha256']:
                raise ValueError('Staged DOS source differs from the project source hash')
            nonce = secrets.token_bytes(16)
            target = guest_name(source.name, project.meta['source_sha256'], project.meta['format'])
            guest_target = (workspace_launch['target'] if workspace_launch else
                            profile['machine']['boot_drive'] + '\\' + target)
            helper = self._helper_module().build_loader(guest_target, tail, nonce)
            self._nonce = nonce
            self._helper = helper
            self._tail = tail
            self._checkpoint_source = source
            self._checkpoint_entry_clean = False
            self._checkpoint_epoch = 0
            self.dos = dos
            self.version = selected
            self.guest_profile = profile
            self.run_id = uuid.uuid4().hex
            self._runtime_epoch = self.run_id + ':process:1'
            self._remaining()
        except BaseException:
            if self._staging is not None:
                self._staging.cleanup()
            raise
        try:
            if self._staging is None:
                self._staging = tempfile.TemporaryDirectory(prefix='fdisbull-dos-process-')
            staged = prepare_process_disk(image, source, project.meta['source_sha256'], helper,
                Path(self._staging.name)/'dos-runtime.img', mcopy=copy_tool,
                startup_batch=startup_batch, target_name=target, image_format=project.meta['format'],
                deadline=self._deadline, stage_source=not self._dos_workspace_enabled,
                program_guest_path=guest_target if self._dos_workspace_enabled else None)
            if staged['original_boot_image']['sha256'] != profile['boot_image']['sha256']:
                raise ValueError('DOS boot image changed between profile admission and staging')
            self._checkpoint_launch = dict(executable=executable, boot_image=staged['prepared_boot_image']['path'],
                boot_image_sha256=staged['prepared_boot_image']['sha256'], paused=True,
                cpu_model=profile['machine']['cpu'], memory_mib=profile['machine']['memory_mib'],
                cpus=1, boot_device=profile['machine']['boot_device'],
                timeout_ms=self._remaining(), transport=transport, firmware=firmware,
                clock_profile=clock_profile, audio_profile=audio_profile,
                retrace_profile=retrace_profile, checkpoint_tool=checkpoint_tool)
            if frame_key_repeat_profile is not None:
                self._checkpoint_launch['frame_key_repeat_profile'] = frame_key_repeat_profile
            vm = QemuMachine(**self._checkpoint_launch, on_spawn=_on_spawn)
            MachineContext.__init__(self, vm)
            self.rpc = vm
            vm.context = self
            vm.close_observer = self._on_machine_closed
            self._set_deadline(self._deadline)
            self._channel = vm.serial(self._deadline)
            vm.qmp.call('cont', timeout_ms=self._remaining())
            vm.machine_stopped = False
            ready, ready_bytes = self._receive_report(self._deadline)
            if ready['type'] == 'error':
                raise DebuggerError('DOS loader failed during ' + ready.get('error_stage', 'preparation')
                                   + ': DOS error ' + str(ready['dos_result']))
            if ready['type'] != 'ready':
                raise DebuggerError('DOS loader did not report a fresh READY boundary')
            vm.qmp.call('stop', timeout_ms=self._remaining())
            vm.machine_stopped = True
            self._ready = ready
            self._ready_bytes = ready_bytes
            self._validate_helper(ready, ready_bytes)
            parked = MachineContext.breakpoint(self, ready['helper_segment']*16 + ready['ready_wait_ip'])
            stopped = MachineContext.run(self, timeout_ms=self._remaining())
            if parked['breakpoint_id'] not in stopped['session']['stop_reason']['breakpoint_ids']:
                raise DebuggerError('DOS helper did not reach its verified READY park')
            MachineContext.delete_breakpoint(self, parked['breakpoint_id'])
            self._validate_entry_memory(project, source_data, ready)
            self._return_breakpoint = MachineContext.breakpoint(
                self, ready['helper_segment']*16 + ready['exit_wait_ip'])['breakpoint_id']
            entry_point = MachineContext.breakpoint(self, self._process['source_mapping']['entry_linear'])
            MachineContext.write_memory(self, ready['helper_segment']*16 + ready['control_offset'],
                                        '01', expected_hex='00', space='virtual')
            entry_stop = MachineContext.run(self, timeout_ms=self._remaining())
            if entry_point['breakpoint_id'] not in entry_stop['session']['stop_reason']['breakpoint_ids']:
                raise DebuggerError('DOS process did not stop at its observed first instruction')
            MachineContext.delete_breakpoint(self, entry_point['breakpoint_id'])
            registers = entry_stop['registers']
            if registers['cpu_mode'] != 'real':
                raise DebuggerError('DOS process entry binding currently requires observed real mode')
            values = registers['registers']
            if any(int(values[name], 16) != ready['child_psp'] for name in ('ds', 'es')):
                raise DebuggerError('DOS process entry DS/ES do not identify its selected PSP')
            if (int(values['ss'], 16) != ready['stack_ss']
                    or int(values.get('rsp', values.get('esp')), 16) & 0xffff != ready['stack_sp']):
                raise DebuggerError('DOS process entry stack differs from the loader report')
            self._process['entry_registers'] = registers
            self._process['state'] = 'active'
            self._vectors_before = self._read(0, 1024)
            self.project = project
            # MachineContext initialization deliberately resets project/run_id;
            # bind only after the native entry and source evidence succeeded.
            self.run_id = self._runtime_epoch.split(':', 1)[0]
            self.capabilities.update(dos_process_observation=True,
                dos_process_launch='original real-mode COM/MZ through DOS EXEC load-only',
                dos_process_exit='nonce-bound helper callback and DOS return status; machine remains owned',
                dos_driver_observation='validated device-header chain; successful device I/O unqualified',
                source_trace='stopped boundaries in the initial verified real-mode DOS module',
                source_trace_clock=vm.machine_configuration['clock_profile']['profile'] == 'virtual',
                execution_event_search=True, input_macros=True,
                screenshot_hooks='stopped-surface passive reads and guarded layers; require_fresh_frame=false only',
                runtime_memory_bindings=True,
                bounded_model_proofs=True,
                spatial_policy=True,
                witnessed_movement='held keyboard leases; runtime_memory scalars; sample progress; native virtual clock only',
                spatial_policy_scope='voluntary host permission only; no frame, action, assistance or memory authority',
                runtime_memory_scope='witnessed ordinary physical RAM or observed unpaged linear RAM; no source/task/allocation lifetime inference',
                trace_until='source-bound predicates; virtual-time ranges with the virtual profile; queued input unqualified',
                desqview_observation=True,
                qemm_observation=profile['memory_manager']['configured'] == 'qemm',
                native_dos_tasks='x-fdisbull-query-task-context' in vm.qmp_commands,
                native_task_views=TASK_VIEW_COMMANDS <= vm.qmp_commands,
                native_cpu_scheduler=SCHEDULER_COMMANDS <= vm.qmp_commands,
                native_irq_preemption=PREEMPTION_COMMAND in vm.qmp_commands,
                memory_search='paused snapshots; process lifetime epoch changes on exit/residency')
            self.capabilities['dos_directory_layers'] = bool(workspace_launch is not None)
            self.capabilities['dos_directory_layers_live'] = False
            from .qemu_workspace_output import qualified_runtime
            self.capabilities['dos_output_capture'] = bool(workspace_launch is not None
                and checkpoint_tool is not None and qualified_runtime(workspace_launch['runtime_component'])
                and 'x-fdisbull-dos-checkpoint-status' in vm.qmp_commands)
            from .qemu_dos_provenance import COMMANDS as SAVE_WITNESS_COMMANDS, ARM_SAVE
            self.capabilities['dos_guest_create_provenance'] = bool(self.capabilities['dos_output_capture']
                and SAVE_WITNESS_COMMANDS <= vm.qmp_commands)
            self.capabilities['dos_save_keep_policy'] = self.capabilities['dos_guest_create_provenance']
            self.capabilities['dos_save_operations'] = bool(self.capabilities['dos_guest_create_provenance']
                and ARM_SAVE in vm.qmp_commands)
            from .qemu_save_stop import COMMANDS as SAVE_STOP_COMMANDS
            self.capabilities['dos_save_safe_stop'] = bool(self.capabilities['dos_save_operations']
                and SAVE_STOP_COMMANDS <= vm.qmp_commands)
            self.capabilities['rewind'] = checkpoint_tool is not None and 'x-fdisbull-dos-checkpoint-status' in vm.qmp_commands
            self.capabilities['rewind_scope'] = 'persistent stopped full-checkpoint boundaries; private disk, layers, hooks and native task/IRQ state'
            self.capabilities['frame_timeline'] = bool(self.capabilities['rewind']
                and self.capabilities['renderer_capture'] and FRAME_COMMANDS <= vm.qmp_commands)
            from .qemu_source_timeline import source_timeline_capable
            self.capabilities['source_raster_timeline'] = source_timeline_capable(self)
            self.capabilities['frame_timeline_unit'] = 'completed synchronous renderer publication followed by a safe CPU stop'
            self.capabilities['frame_timeline_storage'] = ['full','delta'] if self.capabilities['frame_timeline'] else []
            self.capabilities['frame_timeline_capture'] = 'complete native checkpoint at every point; delta mode changes retained storage only'
            self.capabilities['selected_cpu_ram_undo'] = bool(self.capabilities['rewind'] and self.capabilities['code_layers'])
            self.capabilities['selected_undo_resume'] = False
            self.capabilities['comparative_trials'] = bool(self.capabilities['rewind'] and self.capabilities['code_layers'])
            self.capabilities['comparative_trials_scope'] = 'same full native anchor and bounded script; explicit global or saved selected-task stack; captured observations only; final full baseline recovery'
            self.capabilities['selected_cpu_ram_undo_scope'] = 'selected exposed registers and source RAM view; stable ownership only; partial undo freezes until full native recovery'
            self.capabilities['frame_timeline_input'] = 'released input only; frame key ownership is unqualified'
            self.capabilities['frame_key_ownership'] = bool(self.capabilities['source_trace_clock']
                and FRAME_KEY_COMMANDS <= vm.qmp_commands)
            self.capabilities['frame_key_repeat'] = bool(self.capabilities['frame_key_ownership']
                and REPEAT_QUERY in vm.qmp_commands)
            if self.capabilities['frame_key_ownership']:
                self.capabilities['frame_timeline_input'] = 'owned stopped frame-key edges and checkpoint restore; ordinary leases and schedules excluded'
            self.capabilities['save_states'] = checkpoint_tool is not None
            self.capabilities['owned_machine_checkpoints'] = bool(self.capabilities['rewind'])
            self.capabilities['le_source_checkpoints'] = bool(self.capabilities['rewind'])
            self.capabilities['le_source_histories'] = bool(self.capabilities['rewind'])
            self.capabilities['le_source_checkpoint_scope'] = 'qualified stopped LE relation; no DOS task/allocation lifetime'
            self.capabilities['owned_machine_checkpoint_scope'] = (
                'owned VM and private disk; original DOS source binding is retired on restore')
            self.capabilities['dos_protected_source_admission'] = True
            self.capabilities['runtime_scene_observation'] = bool(self.capabilities.get('virtual_clock_budget'))
            self.capabilities['runtime_scene_wait'] = bool(self.capabilities.get('virtual_clock_budget'))
            self.capabilities['runtime_scene_act'] = bool(self.capabilities.get('virtual_clock_budget')
                and self.capabilities.get('virtual_keyboard_press'))
            self.capabilities['runtime_scene_scope'] = 'explicit scene-2/3 witnessed RAM observations; scene-3 named fixed keyboard presses; no frame or source lifetime authority'
            self.capabilities['dos_protected_source_binding'] = 'owned stopped LE source revalidation; not task/allocation lifetime'
            self.capabilities['source_trace'] = 'initial real16 DOS module or explicitly bound protected32 embedded LE source'
            self.metadata = dict(backend=self.backend_id, context='machine',
                runtime_profile='dos-exec-load-only-v1', source_sha256=project.meta['source_sha256'],
                version_sha256=selected['sha256'], runtime_inputs=vm.inputs,
                machine_configuration=vm.machine_configuration, guest_profile=profile,
                process_disk=staged, process=deepcopy(self._process), capabilities=self.capabilities,
                address_mapping='machine virtual/physical controls; source_mapping describes the verified initial load',
                guest_control='exclusive COM2 UART and an authored parent EXEC helper')
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id, selected['id'], stamp(), None, 'stopped', json.dumps(self.metadata)))
                self._event('dos-process-entry', dict(process=deepcopy(self._process), native_stop=entry_stop))
            self._published = True
            if workspace_launch is not None:
                from .qemu_workspace import init_state
                init_state(self, workspace_launch['capture'], workspace_launch['runtime_component'],
                           workspace_launch['layout']['partitions'], workspace_launch['source_dospath'], workspace_launch['mode'],
                           generation=workspace_launch['generation'])
                self._persist_process()
            project._live_debuggers.append(self)
            self._launching = False
            self._checkpoint_entry_clean = True
            self._history_bind()
            self._set_deadline(None)
        except BaseException:
            try:
                if self.vm is not None:
                    self.vm.close()
            finally:
                self.closed = True
                if self in project._live_debuggers:
                    project._live_debuggers.remove(self)
                if self._staging is not None:
                    self._staging.cleanup()
            raise

    def _set_deadline(self, deadline):
        self._deadline = deadline
        if self.vm is not None:
            self.vm.operation_deadline = deadline
            for channel in (self.vm.qmp, self.vm.gdb):
                if channel is not None:
                    channel.operation_deadline = deadline

    def _advance_epoch(self):
        from .qemu_session_revision import session_revision
        session_revision(self.vm).effect()
        self._le_source_retire('DOS capture epoch changed')
        self._epoch_number = getattr(self, '_epoch_number', 1) + 1
        run_id = self.run_id or self._runtime_epoch.split(':', 1)[0]
        self._runtime_epoch = run_id + ':process:' + str(self._epoch_number)
        self._process['capture_epoch'] = self._runtime_epoch

    def _on_machine_closed(self):
        """Invalidate ownership even when an inherited control fails closed."""
        self._dos_async_pending = None
        if self._process is None or self._process.get('machine_closed'):
            return
        self._advance_epoch()
        self._process['machine_closed'] = True
        mapping = self._process['source_mapping']
        mapping.update(live=False, live_ranges=[])
        if self._process['state'] in ('loaded', 'active'):
            self._process['state'] = 'observation_failed'
            mapping['status'] = 'invalidated-on-machine-close'
        elif self._process['state'] == 'resident':
            mapping['status'] = 'invalidated-on-machine-close'
        if getattr(self, '_published', False):
            try:
                self._persist_process()
            except Exception as error:
                # Cleanup must succeed even if the evidence store has failed.
                self._process['persistence_error'] = type(error).__name__

    def _remaining(self):
        remaining = int((self._deadline-time.monotonic())*1000)
        if remaining <= 0:
            raise TimeoutError('DOS process operation deadline expired')
        return remaining

    def _read(self, address, length):
        if type(address) is not int or type(length) is not int or not 0 <= address < address+length <= 0x100000:
            raise DebuggerError('DOS process observation requires an unwrapped real-mode range')
        asynchronous = getattr(self, '_dos_async_pending', None)
        if asynchronous is not None:
            self._async_owner_current(asynchronous)
        remote = self.vm.debugger()
        parts = []
        for offset in range(0, length, 65536):
            if asynchronous is not None:
                self._async_owner_current(asynchronous)
            timeout = self._remaining() if self._deadline is not None else 5000
            parts.append(remote.memory(address+offset, min(65536, length-offset),
                                       space='virtual', timeout_ms=timeout))
            if asynchronous is not None:
                self._async_owner_current(asynchronous)
        return b''.join(parts)

    def _helper_module(self):
        if getattr(self, '_dos_workspace_enabled', False):
            from . import dos_workspace_helper
            return dos_workspace_helper
        from . import dos_process_helper
        return dos_process_helper

    def _receive_report(self, deadline):
        from .dos_process_helper import REPORT_SIZE
        asynchronous = getattr(self, '_dos_async_pending', None)
        while len(self._serial_buffer) < REPORT_SIZE:
            if asynchronous is not None:
                self._async_owner_current(asynchronous)
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('DOS helper report deadline expired')
            self._channel.settimeout(remaining)
            part = self._channel.recv(REPORT_SIZE-len(self._serial_buffer))
            if asynchronous is not None:
                self._async_owner_current(asynchronous)
            if not part:
                raise DebuggerError('DOS helper control channel closed')
            self._serial_buffer.extend(part)
        raw = bytes(self._serial_buffer[:REPORT_SIZE])
        del self._serial_buffer[:REPORT_SIZE]
        return self._helper_module().parse_report(raw, self._nonce), raw

    def _validate_helper(self, report, raw):
        from .dos_process_helper import REPORT_SIZE
        segment = report['helper_segment']
        if segment != report['helper_psp'] or not 1 <= segment < 0xffff:
            raise DebuggerError('DOS helper did not identify its own PSP')
        for key, length in (('report_offset', REPORT_SIZE), ('control_offset', 1),
                            ('ready_wait_ip', 1), ('exit_wait_ip', 1)):
            offset = report[key]
            if not 0x100 <= offset <= 0x100+len(self._helper)-length:
                raise DebuggerError('DOS helper reported a location outside its staged image')
        if self._read(segment*16+report['report_offset'], REPORT_SIZE) != raw:
            raise DebuggerError('DOS helper UART report differs from stopped guest memory')
        for key in ('ready_wait_ip', 'exit_wait_ip'):
            offset = report[key]
            expected = self._helper[offset-0x100:offset-0x100+4]
            if self._read(segment*16+offset, len(expected)) != expected:
                raise DebuggerError('DOS helper park code differs from its staged source')

    def _validate_entry_memory(self, project, source, report):
        if MachineContext.registers(self)['cpu_mode'] != 'real':
            raise DebuggerError('DOS process binding currently requires observed real mode')
        blocks = observe_mcbs(self._read, report['first_mcb_segment'])
        child = report['child_psp']
        allocation = next((b for b in blocks if b['segment'] == child and b['owner_psp'] == child), None)
        if allocation is None:
            raise DebuggerError('Selected DOS PSP does not own an observed MCB allocation')
        helper = next((b for b in blocks if b['segment'] == report['helper_psp']
                       and b['owner_psp'] == report['helper_psp']), None)
        if helper is None or not (allocation['end'] <= helper['start'] or helper['end'] <= allocation['start']):
            raise DebuggerError('DOS child and helper allocation identities are inconsistent')
        psp = self._read(child*16, 256)
        if psp[:2] != b'\xcd\x20' or _word(psp, 0x16) != report['helper_psp']:
            raise DebuggerError('DOS PSP signature or parent identity differs from the selected child')
        if psp[0x80] != len(self._tail) or psp[0x81:0x82+len(self._tail)] != self._tail+b'\r':
            raise DebuggerError('DOS PSP command tail differs from the requested bytes')
        expected, mapping = relocated_source(source, self.dos, project.meta['format'], report)
        if not (allocation['start'] <= mapping['runtime_base']
                and mapping['runtime_base']+len(expected) <= allocation['end']
                and allocation['start'] <= mapping['stack_linear'] <= allocation['end']):
            raise DebuggerError('DOS module or stack lies outside the selected process allocation')
        observed = self._read(mapping['runtime_base'], len(expected))
        if observed != expected:
            raise DebuggerError('DOS-loaded module bytes differ from the source, relocations and exact loader writes')
        mapping.update(status='initial-load-verified', current_bytes='not continuously revalidated',
                       source_sha256=project.meta['source_sha256'], expected_module_sha256=_sha(expected),
                       observed_module_sha256=_sha(observed), live=True,
                       live_ranges=[dict(runtime_address=mapping['runtime_base'],
                                         project_address=mapping['static_base'], length=len(expected))])
        self._process = dict(state='loaded', psp_segment=child, parent_psp_segment=report['helper_psp'],
            entry={key:report['entry_'+key] for key in ('cs', 'ip')},
            source_mapping=mapping, allocation=allocation, environment_segment=_word(psp, 0x2c),
            command_tail=dict(encoding='cp437', length=len(self._tail), hex=self._tail.hex()),
            environment='inherited by DOS EXEC; host environment is not imported',
            default_fcbs=dict(first=psp[0x5c:0x68].hex(), second=psp[0x6c:0x78].hex()),
            dos_version=dict(major=report['dos_version'] & 0xff, minor=report['dos_version'] >> 8,
                             oem=report['dos_oem']),
            drivers=observe_devices(self._read, report['list_of_lists_segment'], report['list_of_lists_offset']),
            termination=None, capture_epoch=self._runtime_epoch,
            evidence='DOS EXEC load-only report, observed PSP/MCB, full relocated file-backed bytes and native entry breakpoint')
        self._process['entry'].update(ss=report['stack_ss'], sp=report['stack_sp'], ax=report['initial_ax'])

    def _persist_process(self):
        self.metadata['process'] = deepcopy(self._process)
        with self.project.transaction(True):
            self.project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?',
                                    (json.dumps(self.metadata), self.run_id))

    def _observe_return(self, result):
        from .dos_process_helper import REPORT_SIZE
        ready = self._ready
        expected_pc = ready['helper_segment']*16 + ready['exit_wait_ip']
        regs = result.get('registers')
        if not regs or regs['cpu_mode'] != 'real' or int(regs['linear_pc'], 16) != expected_pc:
            raise DebuggerError('DOS process return trap did not establish the helper callback context')
        raw = self._read(ready['helper_segment']*16+ready['report_offset'], REPORT_SIZE)
        report = self._helper_module().parse_report(raw, self._nonce)
        serial, serial_bytes = self._receive_report(self._deadline)
        if raw != serial_bytes or report['type'] != 'terminated' or serial['type'] != 'terminated':
            raise DebuggerError('DOS process return reports disagree')
        for key in ('helper_segment', 'helper_psp', 'child_psp', 'entry_cs', 'entry_ip',
                    'stack_ss', 'stack_sp', 'report_offset', 'exit_wait_ip', 'first_mcb_segment'):
            if report[key] != ready[key]:
                raise DebuggerError('DOS process return changed the selected launch identity')
        result_ax = report['dos_result']
        termination_type = result_ax >> 8
        if termination_type not in (0, 1, 2, 3):
            raise DebuggerError('DOS returned an unsupported process termination category')
        resident = termination_type == 3
        blocks = observe_mcbs(self._read, ready['first_mcb_segment'])
        retained = [b for b in blocks if b['owner_psp'] == ready['child_psp']]
        vectors = self._read(0, 1024)
        changes = []
        for vector in range(256):
            start = vector*4
            before, after = self._vectors_before[start:start+4], vectors[start:start+4]
            if before != after:
                offset, segment = struct.unpack('<HH', after)
                target = segment*16+offset
                changes.append(dict(vector=vector, before=before.hex(), after=after.hex(),
                                    handler_linear=target,
                                    in_retained_allocation=any(b['start'] <= target < b['end'] for b in retained)))
        status_owner = pending_status_owner(self)
        if status_owner is not None:
            status_owner.verified_return(self._dos_async_pending, report, raw, serial_bytes)
        self._advance_epoch()
        termination = dict(type=('normal', 'control_break', 'critical_error', 'resident')[termination_type],
            code=result_ax & 0xff, dos_ax=result_ax, resident=resident,
            psp_segment=ready['child_psp'], parent_psp_segment=ready['helper_psp'],
            source='authored DOS EXEC helper and DOS AH=4Dh return status',
            stage='observed parent callback after DOS return',
            instruction_mechanism='not inferred from DOS termination category',
            retained_allocations=retained, changed_vectors=changes,
            vector_scope='before/after observations; vector changes alone do not prove causation')
        mapping = self._process['source_mapping']
        mapping['live_ranges'] = []
        if resident and not getattr(self, '_owned_machine_restored', False):
            for block in retained:
                start = max(block['start'], mapping['runtime_base'])
                end = min(block['end'], mapping['runtime_base']+mapping['module_size'])
                if start < end:
                    mapping['live_ranges'].append(dict(runtime_address=start,
                        project_address=mapping['static_base']+start-mapping['runtime_base'], length=end-start))
        mapping.update(live=bool(mapping['live_ranges']), status=(
            'retired-by-owned-machine-restore' if getattr(self, '_owned_machine_restored', False) else
            'resident-allocation-intersection' if resident else 'invalidated-on-process-exit'))
        self._process.update(state='resident' if resident else 'exited', termination=termination,
                             capture_epoch=self._runtime_epoch)
        if status_owner is not None:
            status_owner.accept_return_state()
        outcome = 'guest_tsr' if resident else 'guest_exit'
        result = deepcopy(result)
        result['native_machine_stop'] = deepcopy(result['session']['stop_reason'])
        result.update(outcome=outcome, process=deepcopy(self._process))
        result['session']['stop_reason'] = dict(kind=outcome, guest_exit=termination,
                                               address=hex(expected_pc), breakpoint_ids=[])
        result['stop'].update(trigger=outcome, context='dos-process', guest_exit=termination,
                              registers_stage='parent helper after DOS return; not target final registers',
                              causing_instruction=None, instruction_completed=None)
        try:
            from .qemu_step_over import observe_step_over_guest_return
            observe_step_over_guest_return(self, result)
            MachineContext.delete_breakpoint(self, self._return_breakpoint)
            self._return_breakpoint = None
            self._persist_process()
            self._event('dos-process-return', result)
            if getattr(self, '_layer_active', None):
                # DOS may already have released or transferred the allocation.
                # Reverting RAM here could overwrite the new owner of a page.
                self._event('layer-process-ended', {'active': list(self._layer_active),
                                                    'disposition': 'owner_closed'})
                if status_owner is not None:
                    status_owner.permit_closed_return()
                self.close()
                result['process'] = deepcopy(self._process)
                result['session']['state'] = 'closed'
            else:
                for hook in self.hooks()['hooks']:
                    self.delete_hook(hook['hook'])
        except BaseException as error:
            # The nonce-bound DOS return and process classification are already
            # observed. Cleanup or persistence cannot reduce them to a generic
            # machine breakpoint when the owner is subsequently closed.
            if getattr(error, 'result', None) is None:
                error.result = result
            raise
        return result

    def _process_checkpoint_preflight(self, *, entry):
        import select
        from .qemu_input import require_released_machine_input
        if self.closed or self.vm.checkpoint_disk is None or self._checkpoint_launch['checkpoint_tool'] is None:
            raise ValueError('Restricted DOS process checkpoints are not enabled')
        from .qemu_image import verify
        verify(self.vm)
        if self.project.db.in_transaction:
            raise ValueError('Checkpoint requires a project outside a caller-owned transaction')
        self._stopped()
        if getattr(self, '_layer_active', None):
            raise ValueError('Clear native layers before process checkpointing')
        if set(self.breakpoints) - ({self._return_breakpoint} if self._return_breakpoint else set()):
            raise ValueError('Remove user breakpoints and hooks before process checkpointing')
        require_released_machine_input(self.vm)
        if self._serial_buffer:
            raise ValueError('Process checkpoint requires a drained helper channel')
        channel = self._channel
        reader = getattr(channel, 'reader', channel)
        if select.select([reader], [], [], 0)[0]:
            raise ValueError('Process checkpoint requires a drained helper channel')
        if entry and (not self._checkpoint_entry_clean or self._process['state'] != 'active'
                      or self._return_breakpoint not in self.breakpoints):
            raise ValueError('Process checkpoint requires the original verified entry boundary')

    def _process_checkpoint_verify_entry(self):
        from .qemu_dos_trace import _ownership
        self._process_checkpoint_preflight(entry=True)
        current = self.registers()
        saved = self._process['entry_registers']
        for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
            if current.get(field) != saved.get(field):
                raise ValueError('Process checkpoint entry CPU changed: ' + field)
        _ownership(self, {'capture_epoch': self._runtime_epoch})
        source = self._checkpoint_source.read_bytes()
        if _sha(source) != self.project.meta['source_sha256']:
            raise ValueError('Process checkpoint source identity changed')
        expected, mapping = relocated_source(source, self.dos, self.project.meta['format'], self._ready)
        recorded = self._process['source_mapping']
        if (self._process['psp_segment'] != self._ready['child_psp']
                or self._process['parent_psp_segment'] != self._ready['helper_psp']
                or any(recorded.get(key) != value for key,value in mapping.items())
                or recorded.get('source_sha256') != self.project.meta['source_sha256']
                or recorded.get('expected_module_sha256') != _sha(expected)):
            raise ValueError('Process checkpoint source identity or mapping changed')
        tail = self._read(self._ready['child_psp']*16 + 0x80, len(self._tail)+2)
        if tail != bytes([len(self._tail)]) + self._tail + b'\r':
            raise ValueError('Process checkpoint command tail changed')
        if self._read(mapping['runtime_base'], len(expected)) != expected:
            raise ValueError('Process checkpoint source mapping changed')
        self._validate_helper(self._ready, self._ready_bytes)
        if self._read(0, 1024) != self._vectors_before:
            raise ValueError('Process checkpoint entry vectors changed')
        return current

    @process_save_operation
    def save_state(self, name='dos-process-checkpoint.qcow2', *, max_bytes=None):
        if getattr(self, '_owned_machine_restored', False):
            raise ValueError('Owned-machine recovery retired the DOS source binding; use save_machine_state')
        from .qemu_dos_checkpoint import COMMAND, save_process_state
        if COMMAND in self.vm.qmp_commands:
            return save_process_state(self, name, max_bytes)
        return self._save_entry_state_v1(name, max_bytes=max_bytes)

    @machine_operation
    def save_machine_state(self, name='dos-owned-machine.qcow2', *, max_bytes=None):
        """Capture this owned VM without asserting current DOS source ownership."""
        from .qemu_owned_checkpoint import save_owned_machine_state
        return save_owned_machine_state(self, name, max_bytes=max_bytes)

    def load_machine_state(self, artifact, *, timeout_ms=60000, rebind_protected_source=False):
        """Recover a machine; optionally admit a fresh stopped LE source view."""
        from .qemu_owned_checkpoint import load_owned_machine_state
        return load_owned_machine_state(self, artifact, timeout_ms=timeout_ms,
                                        rebind_protected_source=rebind_protected_source)

    @machine_operation
    def save_le_source_state(self, name='dos-le-source.json', *, max_bytes=None, timeout_ms=60000):
        """Persist a qualified LE descriptor joined to a complete machine state."""
        from .qemu_dos_le_checkpoint import save_le_source_state
        return save_le_source_state(self, name, max_bytes=max_bytes, timeout_ms=timeout_ms)

    def load_le_source_state(self, artifact, *, timeout_ms=60000):
        from .qemu_dos_le_checkpoint import load_le_source_state
        return load_le_source_state(self, artifact, timeout_ms=timeout_ms)

    def le_rewind_start(self, max_steps=16, max_bytes=536870912, *, history=None, timeout_ms=60000):
        return self._le_history_call('rewind_start', timeout_ms, max_steps=max_steps,
                                     max_bytes=max_bytes, history=history, timeout_ms=timeout_ms)

    def le_rewind_status(self, *, history=None):
        return self._le_history_call('rewind_status', 60000, history=history)

    def le_rewind_record(self, count=1, timeout_ms=60000, *, advance='capture'):
        return self._le_history_call('rewind_record', timeout_ms, count=count,
                                     timeout_ms=timeout_ms, advance=advance)

    def le_rewind(self, count=1, *, history=None, node=None, timeout_ms=60000):
        return self._le_history_call('rewind', timeout_ms, count=count, history=history,
                                     node=node, timeout_ms=timeout_ms)

    def _le_history_call(self, operation, budget_ms, **parameters):
        # Provider/guard installation is part of the same stable owner lock
        # and deadline as the operation, including replacement on restore.
        from .qemu_dos_le_history import get_provider
        from .qemu_owned_checkpoint import _operation
        with _operation(self, budget_ms):
            return getattr(get_provider(self), operation)(**parameters)

    def _save_entry_state_v1(self, name='dos-process-checkpoint.qcow2', *, max_bytes=None):
        from .external_files import _file_name
        from .qemu_checkpoint import snapshot_job, validate_qcow_header
        _file_name(name)
        if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= 128*1024*1024):
            raise ValueError('Checkpoint byte budget must be 1..134217728')
        limit = max_bytes or 128*1024*1024
        registers = self._process_checkpoint_verify_entry()
        tag = 'fdb-' + uuid.uuid4().hex
        try:
            snapshot_job(self.vm, 'save', tag=tag, vmstate='disk0', devices=['disk0'])
            with self.vm.checkpoint_disk.open('rb') as stream:
                data = stream.read(limit+1)
            if len(data) > limit:
                raise ValueError('Checkpoint exceeds its byte budget')
            validate_qcow_header(data[:104], self.vm.checkpoint_virtual_size)
            metadata = dict(format='fdisbull-qemu-dos-entry-qcow2-v1', tag=tag, run=self.run_id,
                source_sha256=self.metadata['source_sha256'], version_sha256=self.metadata['version_sha256'],
                runtime_inputs=deepcopy(self.vm.inputs), machine_configuration=deepcopy(self.vm.machine_configuration),
                guest_profile=deepcopy(self.guest_profile), registers=registers, process=deepcopy(self._process),
                ready_sha256=_sha(self._ready_bytes), helper_sha256=_sha(self._helper),
                nonce_sha256=_sha(self._nonce), vectors_sha256=_sha(self._vectors_before),
                checkpoint_scope='same-session original COM/MZ entry; one private DOS disk',
                host_files_restored=False)
            return self._artifact(name, 'state', data, metadata)
        except BaseException:
            self.close()
            raise

    def load_state(self, artifact, *, timeout_ms=60000):
        from .qemu_dos_checkpoint import PROCESS_FORMATS, load_process_state
        row = self.project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
        if row is not None and json.loads(row['metadata']).get('format') == 'fdisbull-qemu-dos-le-checkpoint-1':
            raise ValueError('LE source checkpoints require load_le_source_state; no MZ source authority is restored')
        if row is not None and json.loads(row['metadata']).get('format') == 'fdisbull-qemu-owned-machine-qcow2-v1':
            raise ValueError('Owned-machine artifacts require load_machine_state; no DOS source binding is restored')
        if row is not None and json.loads(row['metadata']).get('format') in PROCESS_FORMATS:
            return load_process_state(self, artifact, timeout_ms)
        return self._load_entry_state_v1(artifact, timeout_ms=timeout_ms)

    def _load_entry_state_v1(self, artifact, *, timeout_ms=60000):
        from .operation_budget import request_deadline
        from .qemu_checkpoint import snapshot_job
        deadline = request_deadline(self, timeout_ms)
        def remaining():
            value = int((deadline-time.monotonic())*1000)
            if value <= 0:
                raise TimeoutError('DOS process checkpoint restore deadline expired')
            return min(value, 600000)
        owner = self.vm
        wait = min(10, max(0, deadline-time.monotonic()))
        if not owner.lock.acquire(timeout=wait):
            raise TimeoutError('DOS process checkpoint restore lock timed out')
        try:
            if self.vm is not owner:
                raise ValueError('Machine owner changed before process checkpoint restore')
            from .qemu_machine import _machine_operation_guard
            _machine_operation_guard(owner, 'load_state', (artifact,), {'timeout_ms': timeout_ms})
            self._process_checkpoint_preflight(entry=False)
            row = self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?', (artifact,)).fetchone()
            if row is None or row['kind'] != 'state' or row['version'] != self.version['id'] or row['run'] != self.run_id:
                raise ValueError('Process checkpoint must belong to this live session and version')
            data = bytes(row['data']); metadata = json.loads(row['metadata'])
            from .qemu_image import ProducerMismatch, require_record, verify
            require_record(metadata.get('runtime_inputs'))
            expected = dict(format='fdisbull-qemu-dos-entry-qcow2-v1', run=self.run_id,
                source_sha256=self.metadata['source_sha256'], version_sha256=self.metadata['version_sha256'],
                runtime_inputs=self.vm.inputs, machine_configuration=self.vm.machine_configuration,
                guest_profile=self.guest_profile, ready_sha256=_sha(self._ready_bytes),
                helper_sha256=_sha(self._helper), nonce_sha256=_sha(self._nonce), vectors_sha256=_sha(self._vectors_before))
            if _sha(data) != row['sha256'] or any(metadata.get(k) != v for k,v in expected.items()):
                raise ValueError('Process checkpoint identity or hash mismatch')
            if _sha(self._checkpoint_source.read_bytes()) != self.metadata['source_sha256']:
                raise ValueError('Process checkpoint source identity changed')
            remaining(); new = None
            try:
                with tempfile.TemporaryDirectory(prefix='fdisbull-process-checkpoint-') as directory:
                    image = Path(directory)/'state.qcow2'; image.write_bytes(data)
                    new = QemuMachine(**dict(self._checkpoint_launch, timeout_ms=remaining()), _checkpoint_image=image)
                if new.inputs != owner.inputs or new.machine_configuration != owner.machine_configuration:
                    raise ProducerMismatch('Fresh process checkpoint machine identity differs')
                new.operation_deadline = deadline; new.qmp.operation_deadline = deadline
                verify(new,deadline)
                snapshot_job(new, 'load', tag=metadata['tag'], vmstate='disk0', devices=['disk0'], timeout_ms=remaining())
                context = MachineContext(new); actual = context.registers()
                for field in ('registers', 'instruction_pointer', 'cpu_mode', 'address_state'):
                    if actual.get(field) != metadata['registers'].get(field):
                        raise DebuggerError('Restored process CPU differs: ' + field)
                remaining(); new.lock = owner.lock
                owner.close_observer = None
                owner.close()
                self.vm = self.rpc = new; new.context = self; new.close_observer = self._on_machine_closed
                self._history_bind()
                self._channel = new.serial(deadline); self._serial_buffer = bytearray()
                self.breakpoints = {}; self.next_bp = 1
                self._reset_native_layers()
                self._process = deepcopy(metadata['process']); self._advance_epoch()
                self._return_breakpoint = MachineContext.breakpoint(self, self._ready['helper_segment']*16 + self._ready['exit_wait_ip'])['breakpoint_id']
                self._checkpoint_entry_clean = True
                self._set_deadline(deadline)
                self._process_checkpoint_verify_entry()
                self._owned_machine_restored = False
                self._checkpoint_epoch += 1
                self._persist_process()
                result = dict(artifact=artifact, sha256=row['sha256'], checkpoint_epoch=self._checkpoint_epoch,
                              capture_epoch=self._runtime_epoch, source_binding_restored=True,
                              host_files_restored=False, process=deepcopy(self._process))
                self._event('load-state', result); remaining()
                self._set_deadline(None)
                return result
            except BaseException as error:
                if new is not None:
                    try:new.close()
                    except BaseException as cleanup:error.new_machine_cleanup_error=type(cleanup).__name__
                if not isinstance(error,ProducerMismatch):
                    try:self.close()
                    except BaseException as cleanup:error.machine_cleanup_error=type(cleanup).__name__
                raise
        finally:
            owner.lock.release()

    def _async_owner_current(self, context, *, check_deadline=True):
        """Every composed observation stays on the captured process owner."""
        vm = context['vm']
        if (self.vm is not vm or vm.qmp is not context['qmp']
                or vm.gdb is not context['remote']
                or self.project is not context['project'] or self.run_id != context['run']
                or self._process is not context['process']
                or self._channel is not context['serial']
                or self._ready != context['ready'] or self._ready_bytes != context['ready_bytes']
                or self._nonce != context['nonce'] or self._helper != context['helper']):
            raise DebuggerError('DOS asynchronous process owner or helper identity changed')
        if vm.process is not None and vm.process.poll() is not None:
            raise DebuggerError('DOS asynchronous machine exited before stop observation')
        if any(channel is None or (hasattr(channel, 'socket') and channel.socket is None)
               for channel in (context['qmp'], context['remote'])):
            raise DebuggerError('DOS asynchronous owner lost its original native channel')
        bounds = [getattr(self, '_deadline', None), getattr(self, '_rpc_deadline', None),
                  getattr(vm, 'operation_deadline', None),
                  *[getattr(channel, 'operation_deadline', None)
                    for channel in (context['qmp'], context['remote']) if channel is not None]]
        if check_deadline and any(bound is not None and time.monotonic() >= bound for bound in bounds):
            raise TimeoutError('DOS asynchronous operation deadline expired')

    def _dos_async_operation_guard(self, name, args, kwargs):
        context = getattr(self, '_dos_async_pending', None)
        if context is None:
            return
        self._async_owner_current(context, check_deadline=name is not None)
        if name is None or not context['dispatched']:
            return
        if context.get('enriching'):
            if name in ('registers', 'memory', 'memory_snapshot', 'memory_translation', 'tracking_status'):
                return
            if getattr(self, '_automatic_tracking_callback_active', False):
                if name == 'breakpoint':
                    return
                if (name == 'delete_breakpoint' and len(args) == 1 and not kwargs
                        and self.breakpoints.get(args[0], {}).get('owner') == 'automatic-runtime-tracking'):
                    return
            raise ValueError('DOS asynchronous stop enrichment permits only passive reads and tracker-owned controls')
        if name in ('status', 'pause', 'resume', 'close', 'dos_process_info', 'tracking_status'):
            return
        if context.get('reconciling') and (name == 'hooks' or (
                name == 'delete_breakpoint' and args == (context['breakpoint'],) and not kwargs)):
            return
        raise ValueError('Pause or observe the pending DOS asynchronous run before other controls')

    def _async_control_outer_expired(self, vm, result, error):
        context = getattr(self, '_dos_async_pending', None)
        if context is not None and context['dispatched'] and context['vm'] is vm:
            self._close_async_failure(error, context, 'DOS asynchronous control exceeded its deadline', result=result)
            self._dos_async_pending = None

    def _stopped(self):
        context = getattr(self, '_dos_async_pending', None)
        if context is None:
            return MachineContext._stopped(self)
        self._async_owner_current(context)
        state = context['qmp'].call('query-status')
        self._async_owner_current(context)
        if type(state.get('running')) is not bool:
            raise DebuggerError('DOS asynchronous control lacks native running state')
        if state['running']:
            raise ValueError('Pause the machine context before inspecting or changing CPU state')
        context['vm'].machine_stopped = True
        return context['remote']

    def _resume_breakpoint_exemptions(self):
        context = getattr(self, '_dos_async_pending', None)
        if context is None:
            if self._return_breakpoint is not None or self._process['state'] == 'active':
                raise ValueError('DOS resume requires its verified private return control')
            return frozenset()
        self._async_owner_current(context)
        ready = self._helper_module().parse_report(self._ready_bytes, self._nonce)
        identifier = self._return_breakpoint
        expected = dict(kind=1, access='x', length=1, owner='user',
                        address=ready['helper_segment']*16+ready['exit_wait_ip'])
        if (ready['type'] != 'ready' or ready != self._ready
                or self._process['state'] != 'active'
                or self._process['psp_segment'] != ready['child_psp']
                or self._process['parent_psp_segment'] != ready['helper_psp']
                or identifier != context['breakpoint']
                or self.breakpoints.get(identifier) != expected):
            raise ValueError('DOS resume private return control differs from the verified launch')
        self._stopped()
        offset = ready['exit_wait_ip'] - 0x100
        expected_code = self._helper[offset:offset+4]
        if len(expected_code) != 4 or self._read(expected['address'], 4) != expected_code:
            raise ValueError('DOS resume helper return code differs from its staged identity')
        return frozenset((identifier,))

    def _resume_dispatch_started(self):
        context = getattr(self, '_dos_async_pending', None)
        if context is not None:
            self._async_owner_current(context)
            context['dispatched'] = True
        self._dos_async_stop = None
        self._checkpoint_entry_clean = False

    @_async_process_operation
    def resume(self):
        previous = getattr(self, '_dos_async_pending', None)
        if previous is not None:
            observed = self.status()
            if observed['state'] == 'running':
                raise ValueError('Pause or observe the pending DOS asynchronous run before resume')
            # Preserve an already arrived stop. This invocation did not send a
            # second continue or step past the process's parent-return control.
            return observed
        if self._process['state'] != 'active':
            return MachineDebugSession.resume(self)
        owner = self.vm
        context = dict(vm=owner, qmp=owner.qmp, remote=owner.gdb,
            project=self.project, run=self.run_id, process=self._process,
            serial=self._channel, ready=deepcopy(self._ready), ready_bytes=self._ready_bytes,
            nonce=self._nonce, helper=self._helper, breakpoint=self._return_breakpoint,
            dispatched=False)
        if context['remote'] is None:
            raise ValueError('DOS resume requires its retained private GDB control')
        self._dos_async_pending = context
        try:
            self._stopped()
            return MachineDebugSession.resume(self)
        except BaseException as error:
            if context['dispatched'] or self.vm is not owner:
                self._close_async_failure(error, context, 'failed DOS asynchronous resume')
            self._dos_async_pending = None
            raise

    def _close_async_failure(self, error, context, reason, *, result=None):
        """Never close a replacement owner after a failed original operation."""
        if getattr(error, 'result', None) is None and result is not None:
            error.result = result
        if context.get('cleanup_attempted'):
            return
        context['cleanup_attempted'] = True
        owner = context['vm']
        if not getattr(owner, '_fdisbull_control_quarantine', None):
            owner._fdisbull_control_quarantine = reason
        if self.vm is owner:
            from .qemu_machine import _tracking
            try:
                _tracking(self, 'close', reason)
            except BaseException as retirement:
                error.dos_process_tracking_retirement_error = type(retirement).__name__
        try:
            owner.close()
        except BaseException as cleanup:
            error.dos_process_cleanup_error = type(cleanup).__name__

    def _observe_async_stop(self, result, context):
        from .qemu_machine import _machine_registers, _tracking
        from .debug_semantics import normalize_stop
        self._async_owner_current(context)
        context['vm'].machine_stopped = True
        registers = _machine_registers(context['vm'], context['remote'], qmp=context['qmp'])
        self._async_owner_current(context)
        expected_pc = context['ready']['helper_segment']*16+context['ready']['exit_wait_ip']
        if registers['cpu_mode'] == 'real' and registers['linear_pc'] == hex(expected_pc):
            # QMP continue does not promise a GDB stop packet. Preserve the
            # actual native state and unknown trigger, then qualify DOS return
            # separately using the complete nonce-bound memory/serial reports.
            reason = dict(kind='stopped', address=hex(expected_pc), breakpoint_ids=[],
                          native_reply=None, classification_complete=False,
                          native_state=deepcopy(result['native_state']))
            stop = dict(context='machine', outcome='stopped', timed_out=False,
                        session=dict(state='stopped', stop_reason=reason), registers=registers,
                        breakpoints=[], stop=normalize_stop('qemu-machine', reason, outcome='stopped'))
            result['process_stop'] = stop
            self._resume_breakpoint_exemptions()
            if (getattr(self, '_dos_scheduler', None) or {}).get('enabled'):
                raise DebuggerError('Disable the native scheduler before returning to DOS')
            context['reconciling'] = True
            try:
                returned = self._observe_return(stop)
            finally:
                context['reconciling'] = False
            status_owner = pending_status_owner(self)
            if status_owner is not None:
                status_owner.complete_return(context, returned)
            self._dos_async_stop = deepcopy(returned)
            result['process_stop'] = returned
            if returned['session']['state'] == 'closed':
                result['state'] = 'closed'
                self._dos_async_pending = None
                return result
            self._async_owner_current(context)
        context['enriching'] = True
        try:
            _tracking(self, 'after_stop', 'DOS asynchronous stop')
            self._async_owner_current(context)
            tracker = getattr(self, '_automatic_runtime_tracker', None)
            if tracker is not None:
                result['automatic_runtime_tracking'] = tracker.status()
            else:
                result.pop('automatic_runtime_tracking', None)
            self._async_owner_current(context)
        finally:
            context['enriching'] = False
        self._dos_async_pending = None
        return result

    @_async_process_operation
    def pause(self):
        context = getattr(self, '_dos_async_pending', None)
        if context is None:
            return MachineDebugSession.pause(self)
        result = None
        try:
            result = self.status()
            if result['state'] != 'running':
                return result
            self._async_owner_current(context)
            context['qmp'].call('stop')
            self._async_owner_current(context)
            context['vm'].machine_stopped = True
            return self.status()
        except BaseException as error:
            self._close_async_failure(error, context, 'failed DOS asynchronous pause', result=result)
            self._dos_async_pending = None
            raise

    def _close_failed_execution(self, error, reason, *, result=None):
        """Retain an arrived stop and primary failure through terminal cleanup."""
        from .qemu_step_over import step_over_vm
        vm = step_over_vm(self)
        if getattr(error, 'result', None) is None and result is not None:
            error.result = result
        if not getattr(vm, '_fdisbull_control_quarantine', None):
            vm._fdisbull_control_quarantine = reason
        from .qemu_machine import _tracking
        try:
            _tracking(self, 'close', reason)
        except BaseException as retirement_error:
            error.dos_process_tracking_retirement_error = type(retirement_error).__name__
        try:
            vm.close()
        except BaseException as cleanup_error:
            error.dos_process_cleanup_error = type(cleanup_error).__name__

    def _execute(self, command, timeout_ms):
        # A rejected queued-input/transaction request has not executed the
        # guest. Preserve its live process and queue for an explicit run or
        # cancellation; only failures after dispatch enter terminal cleanup.
        from .qemu_step_over import step_over_vm, guard_step_over_owner
        if getattr(self, '_dos_async_pending', None) is not None:
            raise ValueError('Pause or observe the pending DOS asynchronous run before bounded execution')
        vm = step_over_vm(self)
        guard_step_over_owner(self)
        self._execution_preflight(command, timeout_ms)
        if not self._launching:
            self._checkpoint_entry_clean = False
        save_stop_before=None
        if not self._launching:
            from .qemu_save_stop import before_execute
            save_stop_before=before_execute(self,command)
        result = None
        try:
            result = MachineContext._execute(self, command, timeout_ms)
            if save_stop_before is not None:
                from .qemu_save_stop import after_execute
                result=after_execute(self,result,save_stop_before)
            guard_step_over_owner(self, check_deadline=False, allow_exited=result['outcome']=='exited')
        except BaseException as error:
            # Native execution can finish before its event is persisted. A
            # logging failure must not preserve an unobserved live process.
            if not self._launching:
                self._close_failed_execution(error, 'failed DOS process execution publication', result=result)
            raise
        if not self._launching and result['outcome'] == 'exited':
            try:
                vm.close()
            except BaseException as error:
                self._close_failed_execution(error, 'failed DOS native-exit cleanup', result=result)
                raise
        if not self._launching and self._return_breakpoint is not None:
            ids = result['session']['stop_reason']['breakpoint_ids']
            if self._return_breakpoint in ids:
                if (getattr(self,'_dos_scheduler',None) or {}).get('enabled'):
                    error = DebuggerError('Disable the native scheduler before returning to DOS')
                    self._close_failed_execution(error, 'DOS return requires a disabled native scheduler', result=result)
                    raise error
                previous_deadline = self._deadline
                previous_vm = vm.operation_deadline
                previous_channels = [(channel, channel.operation_deadline)
                                     for channel in (vm.qmp, vm.gdb) if channel is not None]
                deadlines = [time.monotonic()+5, previous_deadline, previous_vm,
                             *[bound for _, bound in previous_channels]]
                self._set_deadline(min(bound for bound in deadlines if bound is not None))
                try:
                    return self._observe_return(result)
                except BaseException as error:
                    # The foreground process may already be gone. An invalid
                    # report cannot safely be retried or relabeled a success.
                    self._close_failed_execution(error, 'failed DOS process return observation', result=result)
                    raise
                finally:
                    self._deadline = previous_deadline
                    vm.operation_deadline = previous_vm
                    for channel, bound in previous_channels:
                        channel.operation_deadline = bound
        if not self._launching:
            from .qemu_dos_scheduler import after_scheduler_stop
            result = after_scheduler_stop(self,result)
            result['process'] = deepcopy(self._process)
        return result

    def delete_breakpoint(self, breakpoint_id):
        if breakpoint_id == self._return_breakpoint:
            raise ValueError('The DOS parent-return breakpoint is reserved until process completion')
        return MachineContext.delete_breakpoint(self, breakpoint_id)

    @machine_operation
    def dos_process_info(self):
        """Return persistent process identity; machine controls stay separate."""
        if getattr(self.vm,'_fdisbull_control_quarantine',None):
            # An ended owner's diagnostic must not repeat failed native cleanup.
            return deepcopy(self._process)
        if getattr(self, '_dos_async_pending', None) is not None:
            self.status()
        process = self.vm.process
        if process is not None and process.poll() is not None:
            self.vm.close()
        return deepcopy(self._process)

    @_pending_dos_status
    def status(self):
        context = getattr(self, '_dos_async_pending', None)
        owner = self.vm
        revision = owner.session_revision

        def require_original_revision():
            pending_status_owner(self)
            if self.vm is not owner or getattr(owner, 'session_revision', None) is not revision:
                raise DebuggerError('DOS status owner or session revision changed')

        result = None
        try:
            if context is not None:
                self._async_owner_current(context)
            result = MachineDebugSession.status(self)
            require_original_revision()
            if context is not None:
                self._async_owner_current(context)
                if type(result['native_state'].get('running')) is not bool:
                    raise DebuggerError('DOS asynchronous control lacks native running state')
                if context['dispatched'] and not result['native_state']['running']:
                    result = self._observe_async_stop(result, context)
            require_original_revision()
            result['process'] = deepcopy(self._process)
            stopped = getattr(self, '_dos_async_stop', None)
            if (stopped is not None
                    and stopped['process']['capture_epoch'] == self._process['capture_epoch']):
                result['process_stop'] = deepcopy(stopped)
            # DOS return/tracker callbacks can change the cooperative revision
            # after the base machine reply. Publish the original owner's final
            # snapshot, including valid return paths that closed its channels.
            require_original_revision()
            final_revision = revision.snapshot()
            require_original_revision()
            result.update(final_revision)
            return result
        except BaseException as error:
            if context is not None and context['dispatched']:
                self._close_async_failure(error, context, 'failed DOS asynchronous stop observation', result=result)
                self._dos_async_pending = None
            raise

    @property
    def script_operations(self):
        return super().script_operations | {'screenshot-hooks', 'scene-check', 'scene-assert', 'scene-wait', 'scene-act', 'macro', 'move', 'proof-check', 'spatial-policy', 'bind-runtime-memory', 'runtime-memory', 'write-runtime-memory',
            'save-state', 'load-state', 'save-anchor-stone', 'load-anchor-stone',
            'save-machine-state', 'load-machine-state',
            'save-le-source-state', 'load-le-source-state', 'le-rewind-start', 'le-rewind-status',
            'le-rewind-record', 'le-rewind',
            'trace-until', 'rewind-start', 'rewind-status', 'rewind-record', 'rewind',
            'delta-start','delta-status','delta-record','delta-rewind','delta-recover',
            'frame-advance', 'frame-inputs', 'timeline-start', 'timeline-status', 'timeline-advance',
            'timeline-rewind', 'timeline-stop', 'timeline-pin', 'timeline-image'}

    def close(self):
        if self.closed:
            return
        context = getattr(self, '_dos_async_pending', None)
        if context is not None and context.get('enriching'):
            self._dos_async_operation_guard('close', (), {})
        try:
            if self._process is not None and getattr(self, 'project', None) is not None:
                if not self._process.get('machine_closed'):
                    self._advance_epoch()
                self._process['machine_closed'] = True
                self._process['source_mapping']['live'] = False
                self._process['source_mapping']['live_ranges'] = []
                if self._process['state'] == 'active':
                    self._process['state'] = 'session_closed'
                    self._process['source_mapping']['status'] = 'invalidated-on-session-close'
                self._persist_process()
        finally:
            # Persistence failure cannot retain an owned emulator or disk.
            # The base close reaps the process before touching its database.
            try:
                MachineDebugSession.close(self)
            finally:
                live = getattr(self.project, '_live_debuggers', [])
                if self in live:
                    live.remove(self)
                if self._staging is not None:
                    self._staging.cleanup()
