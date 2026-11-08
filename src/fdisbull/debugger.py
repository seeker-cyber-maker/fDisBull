"""Project-bound DOS runtime observations, separate from immutable static facts."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import struct
import time
import uuid
import tempfile

from .dosbox_rpc import DOSBoxRPC, DebuggerError
from .dos_launch import LaunchAlias, guest_name
from .external_files import _file_name
from .code_layers import LayerProjectMixin, LayerSessionMixin, LAYER_DDL
from .debug_experiments import ExperimentProjectMixin, ExperimentSessionMixin
from .debug_rewind import RewindSessionMixin
from .debug_timeline import FrameTimelineSessionMixin, timeline_locked, _require_released_mouse
from .operation_budget import RpcAdmissionTimeout, run_cleanup_scope
from .debug_cpu_deltas import CpuDeltaSessionMixin
from .anchor_stones import AnchorStoneSessionMixin
from .runtime_code import RuntimeCodeMixin, RUNTIME_DDL
from .scenes import SceneProjectMixin, SceneSessionMixin, SCENE_DDL
from .screenshot_hooks import ScreenshotHookProjectMixin, ScreenshotHookSessionMixin, DDL as SCREENSHOT_HOOK_DDL
from .input_macros import MacroProjectMixin, MacroSessionMixin, MACRO_DDL
from .runtime_observations import RuntimeObservationMixin
from .memory_search_runtime import MemorySearchProjectMixin, MemorySearchSessionMixin
from .memory_rules import MemoryRuleProjectMixin, MemoryRuleSessionMixin
from .desqview_runtime import DesqviewSessionMixin
from .execution_trace import ExecutionTraceSessionMixin
from .event_search import EventSearchProjectMixin
from .movement import MovementSessionMixin
from .progressive_scenes import ProgressiveSceneProjectMixin, ProgressiveSceneSessionMixin
from .assisted_travel import AssistedTravelSessionMixin
from .text_projection import TextProjectionProjectMixin, TextProjectionSessionMixin
from .spatial import SpatialProjectMixin, SpatialSessionMixin, validate_mode


DEBUG_DDL = '''
CREATE TABLE IF NOT EXISTS debug_scripts(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 name TEXT NOT NULL, created TEXT NOT NULL, sha256 TEXT NOT NULL, script TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS debug_runs(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 created TEXT NOT NULL, ended TEXT, state TEXT NOT NULL, metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS debug_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL REFERENCES debug_runs(id),
 created TEXT NOT NULL, operation TEXT NOT NULL, evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS debug_artifacts(
 id TEXT PRIMARY KEY, run TEXT NOT NULL REFERENCES debug_runs(id), name TEXT NOT NULL,
 kind TEXT NOT NULL, sha256 TEXT NOT NULL, data BLOB NOT NULL, metadata TEXT NOT NULL);
'''


def bounded(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def stamp():
    from .project import now
    return now()


DEBUG_DDL += LAYER_DDL
DEBUG_DDL += RUNTIME_DDL
DEBUG_DDL += SCENE_DDL
DEBUG_DDL += SCREENSHOT_HOOK_DDL
DEBUG_DDL += MACRO_DDL


class DebugProjectMixin(EventSearchProjectMixin, MemoryRuleProjectMixin, MemorySearchProjectMixin, SpatialProjectMixin, TextProjectionProjectMixin, ProgressiveSceneProjectMixin, MacroProjectMixin, ScreenshotHookProjectMixin, SceneProjectMixin, RuntimeCodeMixin, ExperimentProjectMixin, LayerProjectMixin):
    def machine(self, executable, *, boot_image, version=None, boot_timeout_ms=30000, guest_profile=None,
                transport='unix', firmware=None, _on_spawn=None):
        if self.meta['format'] == 'NE':
            raise ValueError('NE static projects cannot launch through the raw machine backend')
        from .qemu_machine import MachineDebugSession
        return MachineDebugSession(self,executable,boot_image=boot_image,version=version,
                                   boot_timeout_ms=boot_timeout_ms,guest_profile=guest_profile,
                                   transport=transport,firmware=firmware,_on_spawn=_on_spawn)

    def debugger(self, executable, game_dir, *, version=None, backend=None, kernel=None,
                 initramfs=None, files=None, boot_timeout_ms=240000, state=None, remote_server=None, window=False,_on_spawn=None,
                 spatial_mode=None, fair_play=False, memory_mib=None, dot_mode=None, game_id=None, language=None, platform=None,
                 guest_profile=None, qemu_transport=None, qemu_firmware=None,
                 dos_boot_image=None, dos_mcopy=None, dos_startup_batch=None, dos_arguments=None):
        dos_process_options = (dos_boot_image, dos_mcopy, dos_startup_batch, dos_arguments)
        if any(value is not None for value in dos_process_options) and backend != 'qemu-dos':
            raise ValueError('DOS process boot/staging options require backend=qemu-dos')
        if guest_profile is not None and backend not in ('qemu-machine','qemu-dos'):
            raise ValueError('guest_profile requires a native QEMU full-system backend')
        if (qemu_transport is not None or qemu_firmware is not None) and backend not in ('qemu-machine','qemu-dos'):
            raise ValueError('qemu_transport and qemu_firmware require a native QEMU backend')
        if qemu_transport is not None and qemu_transport not in ('unix','pipe'):
            raise ValueError('qemu_transport must be unix or pipe')
        if dot_mode is not None:
            if type(dot_mode) is not bool:raise ValueError('dot_mode must be boolean')
            if window and not dot_mode:raise ValueError('Conflicting window and dot_mode options')
            window=dot_mode
        if type(window) is not bool:raise ValueError('window must be boolean')
        if memory_mib is not None:bounded(memory_mib,'memory_mib',16,8192)
        if memory_mib is not None and (self.meta['format'] not in ('PE','NE')
                or backend not in (None,'wine-qemu','wine-ne','ida-wine-qemu')):
            raise ValueError('memory_mib is a Windows guest option')
        if backend == 'scummvm-kyra':
            if (any(x is not None for x in (kernel, initramfs, files, state, remote_server,
                                           spatial_mode, language, platform)) or window or fair_play):
                raise ValueError('ScummVM Kyra currently supports only headless EMC2 VM controls')
            from .scummvm_kyra import ScummVMKyraSession
            return ScummVMKyraSession(self, executable, game_dir, version=version, game_id=game_id,
                                      boot_timeout_ms=boot_timeout_ms, _on_spawn=_on_spawn)
        if backend == 'scummvm-gob':
            if any(x is not None for x in (kernel, initramfs, files, state, remote_server, spatial_mode)) or window or fair_play:
                raise ValueError('ScummVM Gob uses an explicit variant and headless VM controls without native launch options')
            from .scummvm_gob import ScummVMGobSession
            return ScummVMGobSession(self, executable, game_dir, version=version,
                                     game_id=game_id or 'lit', language=language, platform=platform,
                                     boot_timeout_ms=boot_timeout_ms, _on_spawn=_on_spawn)
        if language is not None or platform is not None:
            raise ValueError('language and platform require backend=scummvm-gob')
        if backend == 'scummvm-agi':
            if any(x is not None for x in (kernel, initramfs, files, state, remote_server, spatial_mode)) or window or fair_play:
                raise ValueError('ScummVM AGI uses an explicit game_id and headless VM controls without native launch options')
            from .scummvm_debugger import ScummVMAGISession
            return ScummVMAGISession(self, executable, game_dir, version=version, game_id=game_id,
                                    boot_timeout_ms=boot_timeout_ms, _on_spawn=_on_spawn)
        if game_id is not None:
            raise ValueError('game_id requires a ScummVM backend')
        if spatial_mode is None: spatial_mode = 'physical' if fair_play else 'assisted'
        validate_mode(spatial_mode, fair_play)
        if (spatial_mode != 'assisted' or fair_play) and (backend not in (None, 'dosbox') or self.meta['format'] in ('PE','NE')):
            raise ValueError('Spatial game policy currently requires native DOSBox')
        if self.meta['format']=='NE':
            if backend not in (None,'wine-qemu','wine-ne'):
                raise ValueError('NE original programs require the Win16 Wine backend')
            if kernel is None or initramfs is None:
                raise ValueError('Win16 launch requires kernel and prepared Wine runtime')
            if remote_server is not None:raise ValueError('Win16 does not use an IDA remote server')
            from .win16_debugger import Win16DebugSession
            return Win16DebugSession(self,executable,game_dir,kernel=kernel,initramfs=initramfs,
                version=version,files=files,boot_timeout_ms=boot_timeout_ms,state=state,window=window,memory_mib=memory_mib)
        if type(window) is not bool:
            raise ValueError('window must be boolean')
        if window and backend not in (None,'dosbox','wine-qemu'):
            raise ValueError('dot-mode requires native DOSBox or a Windows spectator backend')
        if backend in ('qemu-machine','qemu-dos'):
            if any(x is not None for x in (kernel,initramfs,files,state,remote_server)):
                raise ValueError('Raw boot launch uses its project image without guest-controller options')
            options=dict(boot_image=Path(game_dir)/self.meta['filename'],version=version,
                         boot_timeout_ms=boot_timeout_ms,guest_profile=guest_profile,
                         transport=qemu_transport or 'unix',firmware=qemu_firmware,_on_spawn=_on_spawn)
            if backend=='qemu-dos':
                if self.meta['format'] in ('COM', 'MZ'):
                    if dos_boot_image is None:
                        raise ValueError('Native DOS COM/MZ launch requires a separate dos_boot_image')
                    from .qemu_dos_process import QemuDOSProcessSession
                    options['boot_image'] = dos_boot_image
                    return QemuDOSProcessSession(self, executable, game_dir,
                        mcopy=dos_mcopy, startup_batch='FDAUTO.BAT' if dos_startup_batch is None else dos_startup_batch,
                        arguments='' if dos_arguments is None else dos_arguments, **options)
                if any(value is not None for value in dos_process_options):
                    raise ValueError('DOS process options require a COM/MZ project; raw boot uses its own source disk')
                from .qemu_dos import QemuDOSSession
                return QemuDOSSession(self,executable,**options)
            return self.machine(executable,**options)
        if backend=='dosbox-qemu':
            if kernel is None or initramfs is None or state is not None or remote_server is not None:
                raise ValueError('DOSBox/QEMU launch requires kernel and prepared initramfs; load native states after launch')
            from .dos_qemu import DOSQemuSession
            return DOSQemuSession(self,executable,game_dir,kernel=kernel,initramfs=initramfs,version=version,
                                  files=files,boot_timeout_ms=boot_timeout_ms,_on_spawn=_on_spawn)
        if backend == 'ida-wine-qemu':
            if kernel is None or initramfs is None or remote_server is None:
                raise ValueError('IDA launch requires kernel, prepared IDA initramfs and remote_server')
            from .ida_debugger import IDAPEDebugSession
            return IDAPEDebugSession(self,executable,game_dir,kernel=kernel,initramfs=initramfs,
                version=version,files=files,boot_timeout_ms=boot_timeout_ms,state=state,remote_server=remote_server,window=window,memory_mib=memory_mib)
        if remote_server is not None:
            raise ValueError('remote_server requires backend=ida-wine-qemu')
        if backend == 'wine-qemu' or (backend is None and self.meta['format']=='PE'):
            if kernel is None or initramfs is None:
                raise ValueError('PE32/PE64 Wine/QEMU launch requires kernel and prepared initramfs')
            from .wine_debugger import PEDebugSession
            return PEDebugSession(self,executable,game_dir,kernel=kernel,initramfs=initramfs,
                version=version,files=files,boot_timeout_ms=boot_timeout_ms,state=state,window=window,memory_mib=memory_mib)
        if backend not in (None,'dosbox') or kernel is not None or initramfs is not None or files is not None or state is not None:
            raise ValueError('Unexpected DOS backend or Wine-only launch options')
        return DebugSession(self, executable, game_dir, version=version,window=window,_on_spawn=_on_spawn,
                            spatial_mode=spatial_mode, fair_play=fair_play)

    def debug_runs(self, version=None):
        v = self.version(version)['id']
        return {'version':v,'live_state_verified':False,'runs':[{**dict(r),'metadata':json.loads(r['metadata'])}
                for r in self.db.execute('SELECT * FROM debug_runs WHERE version=? ORDER BY created,id',(v,))]}

    def debug_artifacts(self, version=None, run=None):
        v = self.version(version)['id']
        rows = self.db.execute('''SELECT a.id,a.run,a.name,a.kind,a.sha256,fdb_length(a.data) AS size,a.metadata
            FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run
            WHERE r.version=? AND (? IS NULL OR r.id=?) ORDER BY a.rowid''',(v,run,run))
        return {'version':v,'artifacts':[{**dict(r),'metadata':json.loads(r['metadata'])} for r in rows]}

    def debug_save_script(self, name, script, version=None):
        from .debug_script import validate_script
        validate_script(script)
        name = _file_name(name)
        text = json.dumps(script, sort_keys=True, separators=(',',':'), allow_nan=False)
        identifier = uuid.uuid4().hex
        v = self.version(version)['id']
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self.transaction(True):
            self.db.execute('INSERT INTO debug_scripts VALUES (?,?,?,?,?,?)',
                            (identifier,v,name,stamp(),digest,text))
        return dict(script_id=identifier,version=v,name=name,sha256=digest)

    def debug_scripts(self, version=None):
        v = self.version(version)['id']
        return {'version':v,'scripts':[dict(r) for r in self.db.execute(
            'SELECT id,version,name,created,sha256 FROM debug_scripts WHERE version=? ORDER BY rowid',(v,))]}

    def debug_anchor_stone_info(self, artifact):
        """Inspect an Anchor Stone without changing legacy artifact formats."""
        return self.debug_state_info(artifact)

    def debug_state_info(self, artifact):
        import zipfile
        row = self.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                              (artifact,)).fetchone()
        if row is None or row['kind']!='state':
            raise ValueError('Unknown native state artifact')
        data = bytes(row['data'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Stored state hash mismatch')
        metadata=json.loads(row['metadata'])
        if metadata.get('format')=='scummvm-agi-native-slot-v1':
            return {'artifact':artifact,'version':row['version'],'sha256':row['sha256'],'size':len(data),
                    'metadata':metadata,'exact_vm_checkpoint':False}
        if metadata.get('format')=='fdisbull-qemu-native-1':
            from .wine_state import state_info
            return state_info(self,artifact)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            components = [{'name':i.filename,'size':i.file_size,'compressed_size':i.compress_size} for i in archive.infolist()]
        return {'artifact':artifact,'version':row['version'],'sha256':row['sha256'],'size':len(data),
                'metadata':json.loads(row['metadata']),'components':components}

    def debug_fork_state(self, artifact, executable, game_dir, *, name='derived.sav', memory=None, registers=None,
                         backend=None,kernel=None,initramfs=None,boot_timeout_ms=240000,window=False):
        info = self.debug_state_info(artifact)
        if info['metadata'].get('format')=='scummvm-agi-native-slot-v1':
            raise ValueError('ScummVM native save slots do not support DOS memory/register forks')
        memory = [] if memory is None else memory
        registers = {} if registers is None else registers
        if not isinstance(memory,list) or len(memory)>64 or not isinstance(registers,dict):
            raise ValueError('State edits require at most 64 memory edits and a register mapping')
        _file_name(name)
        pe=info['metadata'].get('format')=='fdisbull-qemu-native-1'
        if pe:
            from .wine_state import validate_edits,apply_edits
        else:
            from .debug_state import validate_edits,apply_edits
        validate_edits(memory,registers)
        if not memory and not registers:
            raise ValueError('A state fork requires at least one explicit edit')
        options=dict(backend=backend,kernel=kernel,initramfs=initramfs,boot_timeout_ms=boot_timeout_ms,window=window)
        if pe:
            options['state']=artifact
            # A state binds every explicitly uploaded asset, not only its EXE.
            # Reuse that allowlist and let launch reverify each source hash.
            options['files']=[item['path'] for item in info['metadata']['files']]
        elif backend=='dosbox-qemu':
            options['files']=[item['path'] for item in info['metadata'].get('source_files',info['metadata']['files'])]
        with self.debugger(executable,game_dir,version=info['version'],**options) as debug:
            if not pe:debug.load_state(artifact)
            edits = apply_edits(debug,memory,registers)
            debug._state_provenance = {'parent_artifact':artifact,'parent_sha256':info['sha256'],'edits':edits,
                                      **({'target_execution_during_edits':False,'guest_services_running':True} if pe else {'guest_execution_during_edits':False})}
            result = debug.save_state(name)
        return result

    def debug_export(self, artifact, output):
        row = self.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        if row is None:
            raise ValueError('Unknown debugger artifact')
        data = bytes(row['data'])
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Stored debugger artifact hash mismatch')
        destination = Path(output).expanduser().resolve()
        protected = [self.path,Path(str(self.path)+'-wal'),Path(str(self.path)+'-shm')]
        if any(destination==p or (destination.exists() and p.exists() and destination.samefile(p)) for p in protected):
            raise ValueError('Artifact export cannot overwrite the project or SQLite sidecars')
        destination.parent.mkdir(parents=True,exist_ok=True)
        metadata_row=self.db.execute('SELECT kind,metadata FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        if metadata_row['kind']=='state' and json.loads(metadata_row['metadata']).get('format')=='fdisbull-qemu-native-1':
            from .wine_state import export_state
            return export_state(self,artifact,destination)
        with destination.open('xb') as stream:
            stream.write(data)
        return {'artifact':artifact,'output':str(destination),'sha256':row['sha256'],'size':len(data)}

    def _debug_artifact(self, run, name, kind, data, metadata):
        name = _file_name(name)
        if len(data) > (128 if kind=='state' else 16)*1024*1024:
            raise ValueError('Runtime artifact exceeds per-kind size budget')
        row=self.db.execute('SELECT version FROM debug_runs WHERE id=?',(run,)).fetchone()
        if row is None:
            raise ValueError('Unknown debugger run')
        identifier = uuid.uuid4().hex
        digest = hashlib.sha256(data).hexdigest()
        result = dict(artifact=identifier,run=run,version=row['version'],name=name,kind=kind,
                      sha256=digest,size=len(data),metadata=metadata)
        with self.transaction(True):
            used = self.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0]
            if used+len(data) > 256*1024*1024:
                raise ValueError('Project runtime artifact budget exceeds 256 MiB')
            self.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
                (identifier,run,name,kind,digest,data,json.dumps(metadata)))
            self.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                            (run,stamp(),'artifact',self._external_text(json.dumps(result))))
        return result

    def debug_grid(self, artifact, *, name='coordinate-grid.png', step=32, target=None):
        """Derive a coordinate aid from an authentic saved frame, even after restart."""
        from .screenshot_grid import coordinate_grid
        from PIL import Image
        _file_name(name)
        row=self.db.execute('SELECT * FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        if row is None or row['kind']!='screenshot':
            raise ValueError('Grid requires an original screenshot artifact')
        data=bytes(row['data'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Stored screenshot hash mismatch')
        rendered,grid=coordinate_grid(data,step=step,target=target)
        metadata=json.loads(row['metadata'])
        with Image.open(io.BytesIO(data)) as image:
            if image.size!=(metadata['width'],metadata['height']):
                raise ValueError('Stored screenshot dimensions differ from metadata')
        grid.update(source_artifact=artifact,source_sha256=row['sha256'])
        metadata.update(coordinate_grid=grid,sha256=hashlib.sha256(rendered).hexdigest())
        return self._debug_artifact(row['run'],name,'screenshot-grid',rendered,metadata)


class DebugSession(ExecutionTraceSessionMixin, DesqviewSessionMixin, MemoryRuleSessionMixin, MemorySearchSessionMixin, FrameTimelineSessionMixin, AnchorStoneSessionMixin, CpuDeltaSessionMixin, RewindSessionMixin, SpatialSessionMixin, TextProjectionSessionMixin, AssistedTravelSessionMixin, ProgressiveSceneSessionMixin, MovementSessionMixin, MacroSessionMixin, RuntimeObservationMixin, ScreenshotHookSessionMixin, SceneSessionMixin, ExperimentSessionMixin, LayerSessionMixin):
    native_hooks_available = True
    @property
    def script_operations(self):
        from .debug_script import OPERATIONS, ENGINE_OPERATIONS
        return (set(OPERATIONS)|{'assert'})-{'write-memory','write-registers'}-set(ENGINE_OPERATIONS)

    """One explicitly owned emulator; closing the project also closes sessions."""
    def __init__(self, project, executable, game_dir, *, version=None,window=False,_on_spawn=None,
                 spatial_mode=None, fair_play=False):
        if spatial_mode is None: spatial_mode = 'physical' if fair_play else 'assisted'
        validate_mode(spatial_mode, fair_play)
        self._spatial_mode, self._fair_play = spatial_mode, fair_play
        self._allow_assisted_travel = spatial_mode == 'assisted' and not fair_play
        if type(window) is not bool:
            raise ValueError('window must be boolean')
        self.window = window
        self.project = project
        self._spawn_callback=_on_spawn
        self.rpc = None
        self._launch_alias = None
        self.closed = False
        self.run_id = uuid.uuid4().hex
        self.version = project.version(version)
        if project.meta['format'] not in ('MZ', 'COM') or self.version['parent'] is not None:
            raise ValueError('Runtime launch requires the original, unpatched DOS MZ or explicitly declared COM version; select version=1 explicitly if needed')
        self.dos = project._document(self.version['id'])['dos']
        self.game_dir = Path(game_dir).expanduser().resolve(strict=True)
        filename = project.meta['filename']
        target = guest_name(filename, project.meta['source_sha256'], project.meta['format'])
        source = (self.game_dir / filename).resolve(strict=True)
        if source.parent != self.game_dir or not source.is_file() or source.stat().st_size > 64*1024*1024:
            raise ValueError('Target must be a regular file directly inside game_dir, at most 64 MiB')
        source_data = source.read_bytes()
        if hashlib.sha256(source_data).hexdigest() != project.meta['source_sha256']:
            raise ValueError('Game executable does not match the project source hash')
        executable = Path(executable).expanduser().resolve(strict=True)
        from . import __version__
        self.metadata = {'fdisbull_version':__version__,'source_sha256':project.meta['source_sha256'],'version_sha256':self.version['sha256'],
                         'executable':str(executable),'emulator_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
                         'runtime_profile':'real-normal-com-v1' if project.meta['format']=='COM' else 'real-normal-v1','game_dir':str(self.game_dir),'target':target,
                         'source_filename':filename,'target_aliased':target!=filename,'static_load_segment':self.dos['load_segment'],
                         'window_requested':window,'native_hooks_available':self.native_hooks_available}
        try:
            self._prepare_launch_target(target, source_data)
            self.rpc = self._open_rpc(executable,self.game_dir)
            self.metadata.update(self._transport_metadata())
            result = self.rpc.call('session.start',{'target':{'command':target,'arguments':[]},
                'mounts':[{'drive':'C','host_path':str(self.game_dir)}],'break_at':'entry'})
            self.session_id = result['session_id']
            regs = self.call('state.get_registers')
            if regs['cpu_mode'] != 'real':
                raise DebuggerError('Expected real-mode DOS entry')
            header = self.dos['header_fields']
            is_com = project.meta['format'] == 'COM'
            self.runtime_load = int(regs['segments']['cs'],16) - (0 if is_com else header['e_cs'])
            if (not (0 if is_com else 0x10) <= self.runtime_load <= 0xffff or
                    int(regs['instruction_pointer'],16) != (0x100 if is_com else header['e_ip'])):
                raise DebuggerError('Runtime entry does not establish an unwrapped DOS load segment')
            self.static_base = self.dos['image_base']
            self.runtime_base = self.runtime_load * 16 + (0x100 if is_com else 0)
            self.delta = self.runtime_base - self.static_base
            self.module_size = self.dos['module_size']
            if self.runtime_base+self.module_size > 0x100000:
                raise DebuggerError('Runtime image would require A20 wrapping')
            region = next(r for r in project.regions(self.version['id']) if r.start==self.static_base)
            self.expected = bytearray(region.data[:self.module_size])
            for relocation in self.dos['relocations']:
                index = relocation['linear_address']-self.static_base
                value = struct.unpack_from('<H',self.expected,index)[0]
                struct.pack_into('<H',self.expected,index,(value+self.runtime_load-self.dos['load_segment']) & 0xffff)
            if is_com:
                if any(int(regs['segments'][name],16) != self.runtime_load for name in ('ds','es','ss')):
                    raise DebuggerError('COM startup DS, ES and SS must equal the PSP segment')
                length = min(16, self.module_size)
                observed = self.call('memory.read', {'address':{'space':'linear','offset':f'0x{self.runtime_base:08X}'}, 'length':length})
                if base64.b64decode(observed['data_base64'],validate=True) != self.expected[:length]:
                    raise DebuggerError('COM runtime entry bytes differ from the project source')
            self.metadata.update(runtime_load_segment=self.runtime_load,entry_registers=regs,
                                 capabilities=self.rpc.capabilities,pid=self.rpc.process.pid)
            if is_com:
                self.metadata['mapping_scope'] = 'COM file-backed span only; PSP, stack and dynamically loaded or overwritten code are not identified by address alone'
                self.metadata['entry_bytes_verified'] = length
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id,self.version['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            self._event('launch',result)
            project._live_debuggers.append(self)
        except BaseException:
            if self.rpc is not None:
                self.rpc.close()
            if self._launch_alias is not None:
                self._launch_alias.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _open_rpc(self,executable,game_dir):return DOSBoxRPC(executable,game_dir,window=self.window,on_spawn=self._spawn_callback)
    def _transport_metadata(self):return {}

    def _prepare_launch_target(self, target, data):
        if target != self.project.meta['filename']:
            self._launch_alias = LaunchAlias(self.game_dir, target, data)

    @property
    def machine(self):
        if not hasattr(self.rpc,'machine'):raise ValueError('This session has no outer machine context')
        return self.rpc.machine.bind(self.project,self.run_id)

    def contexts(self):
        primary='dos-cpu' if self.project.meta['format'] in ('MZ', 'COM') else 'process'
        contexts=[dict(id=primary,kind=primary,trace_phase='before-fetch; last record pending' if primary=='dos-cpu' else 'completed-step')]
        if hasattr(self.rpc,'machine'):contexts.append(dict(id='machine',kind='machine',parent_of=primary,capabilities=self.rpc.machine.capabilities))
        return dict(run=self.run_id,selected=primary,contexts=contexts)

    def context(self,name):
        if name==self.contexts()['selected']:return self
        if name=='machine':return self.machine
        raise ValueError('Unknown execution context')

    def write_memory(self, address, data_hex, *, expected_hex):
        raise ValueError('Direct guarded memory editing is currently a PE64 operation; use a DOS RAM layer')

    def write_registers(self,registers):
        raise ValueError('Direct guarded register editing is currently a PE64 operation; use a DOS state fork')

    @timeline_locked
    def call(self, method, params=None):
        if self.closed:
            raise DebuggerError('Debugger session is closed')
        for hook in ('_cpu_delta_before_call', '_rewind_before_call', '_timeline_before_call'):
            callback = getattr(self, hook, None)
            if callback is not None:
                callback(method, params) if hook == '_cpu_delta_before_call' else callback(method)
        deadline=getattr(self,'_rpc_deadline',None)
        options={}
        if deadline is not None:
            remaining=int((deadline-time.monotonic())*1000)
            admission=getattr(self,'_rpc_admission_ms',None) or 0
            if remaining<=0 or remaining < admission:
                raise RpcAdmissionTimeout('Shared debugger host-time budget expired before RPC dispatch')
            options['timeout_ms']=min(getattr(self,'_rpc_timeout_cap_ms',None) or 15000,remaining)
        return self.rpc.call(method,{'session_id':self.session_id,**(params or {})},**options)

    def _event(self, operation, evidence):
        if not hasattr(self, 'project'):
            return
        for key in ('delta_experiment', 'timeline_experiment'):
            experiment = getattr(self, 'metadata', {}).get(key)
            if experiment is not None:
                evidence = dict(evidence, **{key: experiment})
        with self.project.transaction(True):
            self.project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                                    (self.run_id,stamp(),operation,self.project._external_text(json.dumps(evidence))))
            state = evidence.get('state') or evidence.get('session',{}).get('state')
            if state:
                self.project.db.execute('UPDATE debug_runs SET state=? WHERE id=?',(state,self.run_id))

    def status(self):
        from .debug_semantics import contract
        result = self.call('session.status')
        return {'run':self.run_id,'version':self.version['id'],'live':True,**result,'mapping':self.metadata,
                'semantics':contract(self.metadata.get('backend','dosbox')),
                'native_hooks_available':self.native_hooks_available}

    def _timing(self, enabled=None):
        if not self.rpc.capabilities.get('timing',{}).get('fast_forward'):
            raise DebuggerError('DOSBox build lacks execution.timing; rebuild with the current agent patch')
        return self.call('execution.timing',{} if enabled is None else {'fast_forward':enabled})

    def wait(self, observations, until, *, guest_ms, slice_ms=50, timeout_ms=10000,
             fast_forward=True, max_polls=1000, timeout_screenshot='wait-timeout.png'):
        from .debug_wait import wait_until
        return wait_until(self, observations, until, guest_ms=guest_ms, slice_ms=slice_ms,
                          timeout_ms=timeout_ms, fast_forward=fast_forward, max_polls=max_polls,
                          timeout_screenshot=timeout_screenshot)

    def run(
        self, *, timeout_ms=10000, guest_ms=None, fast_forward=False, stop_on_hook=False
    ):
        bounded(timeout_ms, "timeout_ms", 1, 600000)
        if guest_ms is not None:
            bounded(guest_ms, "guest_ms", 1, 3600000)
        if type(fast_forward) is not bool:
            raise ValueError("fast_forward must be boolean")
        if type(stop_on_hook) is not bool:
            raise ValueError("stop_on_hook must be boolean")
        before = self._timing()
        started = time.monotonic()
        deadline = started + timeout_ms / 1000
        running = False
        result = None
        outcome = "timeout"
        hook_hits = []
        timing = before
        try:
            self._timing(fast_forward)
            operation = self.call("execution.continue")
            running = True
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                result = self.call(
                    "execution.wait",
                    {
                        "operation_id": operation["operation_id"],
                        "timeout_ms": max(
                            1, min(10 if fast_forward else 50, int(remaining * 1000))
                        ),
                    },
                )
                running = result.get("running", False)
                if not running:
                    hook_hit = self._dispatch_hook(result)
                    if hook_hit is not None:
                        hook_hits.append(hook_hit)
                        if stop_on_hook:
                            outcome = "hook"
                            break
                        if time.monotonic() >= deadline:
                            break
                        operation = self.call("execution.continue")
                        running = True
                        continue
                    kind = result.get("stop_reason", {}).get("kind", "stopped")
                    outcome = "breakpoint" if kind == "breakpoint" else kind
                    break
                timing = self._timing()
                if (
                    guest_ms is not None
                    and timing["guest_ticks"] - before["guest_ticks"] >= guest_ms
                ):
                    outcome = "guest_time"
                    break
        finally:
            if not self.closed:
                try:
                    with run_cleanup_scope(self):
                        if running:
                            try:
                                pause = self.call("execution.pause")
                                terminal_operation = pause["operation_id"]
                            except DebuggerError as error:
                                if not str(error).endswith("(TARGET_NOT_RUNNING)"):
                                    raise
                                # A real stop can win the race with our budget pause.
                                # Observe the existing operation; never continue/replay.
                                terminal_operation = operation["operation_id"]
                            result = self.call(
                                "execution.wait",
                                {
                                    "operation_id": terminal_operation,
                                    "timeout_ms": 3000,
                                },
                            )
                            if result.get("running"):
                                raise DebuggerError(
                                    "Target failed to pause after bounded run"
                                )
                            kind = result.get("stop_reason", {}).get("kind")
                            if not kind:
                                raise DebuggerError(
                                    "Bounded run ended without a terminal stop reason"
                                )
                            if kind != "pause":
                                outcome = kind
                        if result is None or result.get("state") != "exited":
                            timing = self._timing(before["fast_forward"])
                except BaseException:
                    self.close()
                    raise
        evidence = {
            "run": self.run_id,
            "outcome": outcome,
            "timed_out": outcome == "timeout",
            "requested_guest_ms": guest_ms,
            "guest_elapsed_ms": timing["guest_ticks"] - before["guest_ticks"],
            "host_elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            "fast_forward": fast_forward,
            "timing_after": timing,
            "session": result,
        }
        evidence["hook_hits"] = hook_hits
        from .debug_semantics import normalize_stop

        stopped_pc = None
        stopped_registers = None
        if result and result.get('state') != 'exited' and callable(getattr(self,'registers',None)):
            try:
                stopped_registers = self.registers()
                stopped_pc = {'space':'segmented',
                    'segment':stopped_registers['segments']['cs'],
                    'offset':stopped_registers['instruction_pointer']}
            except (DebuggerError, KeyError):
                pass  # Preserve native evidence when the stopped context is unavailable.
        real_mode = stopped_registers is not None and stopped_registers.get('cpu_mode') == 'real'
        stop_reason = (result or {}).get('stop_reason', {})
        if stop_reason.get('address'):
            stop_reason['project_address'] = self.project_address(stop_reason['address']) if real_mode else None
        if stop_reason.get('data_access'):
            access = stop_reason['data_access']
            access['project_instruction'] = (self.project_address(access['instruction'])
                if access.get('cpu_mode')=='real' else None)
            if access.get('cpu_mode')!='real':
                access['source_mapping']='causing instruction mode unqualified for DOS source projection'
        if stopped_registers is not None:
            stop_reason['cpu_mode'] = stopped_registers.get('cpu_mode')
        evidence["stop"] = normalize_stop(
            self.metadata.get("backend", "dosbox"),
            (result or {}).get("stop_reason", {}),
            outcome=outcome,
            stopped_pc=stopped_pc,
        )
        self._event("run", evidence)
        return evidence

    def project_address(self, address):
        if address.get('space') == 'linear':
            runtime = int(address['offset'],16)
        elif address.get('space') == 'segmented':
            runtime = int(address['segment'],16)*16+int(address['offset'],16)
        else:
            return None
        return hex(runtime-self.delta) if self.runtime_base <= runtime < self.runtime_base+self.module_size else None

    def registers(self):
        result = self.call('state.get_registers')
        result.update(cs=result['segments']['cs'],ip=result['instruction_pointer'])
        # Protected-mode CS is a selector, never a DOS paragraph. The stopped
        # CPU remains inspectable without inventing a static source address.
        result['project_address'] = (self.project_address({'space':'segmented',
            'segment':result['segments']['cs'],'offset':result['instruction_pointer']})
            if result.get('cpu_mode')=='real' else None)
        if result.get('cpu_mode')!='real':
            result['source_mapping']='unqualified protected/v86 selector; no DOS paragraph projection'
        return result

    def breakpoint(self, address, *, cs=None, access='x', length=1, view='static'):
        if self.call('state.get_registers').get('cpu_mode')!='real':
            raise ValueError('DOS source breakpoints require real mode; protected/v86 selectors need explicit runtime qualification')
        if view not in ('static','execute'):
            raise ValueError('Breakpoint view must be static or execute')
        if access not in ('x','r','w','rw'):
            raise ValueError('access must be x, r, w, or rw')
        bounded(length,'length',1,256)
        if access != 'x':
            result = self._data_breakpoint(address,cs=cs,access=access,length=length)
            return self._remember_breakpoints(dict(address=address,cs=cs,access=access,length=length,view=view),result)
        if length != 1:
            raise ValueError('Execution breakpoints use one instruction address')
        if view == 'execute':
            observed = self.code(address,cs=cs,length=15)
            if not observed.get('overlay_valid',True) or not observed['instructions']:
                raise ValueError('Execution view is stale or has no valid instruction')
            instruction = observed['instructions'][0]
            runtime_address = {'space':'segmented','segment':f"0x{int(instruction['cs'],16):04X}",
                               'offset':f"0x{int(instruction['ip'],16):08X}"}
            result = self.call('breakpoints.create',{'kind':'execution','address':runtime_address,'once':False})
            result.update(run=self.run_id,version=self.version['id'],project_address=instruction['project_address'],
                          project_cs=hex(int(instruction['cs'],16)-self.runtime_load+self.dos['load_segment']),
                          runtime_bytes=instruction['bytes'],bytes_verified=True,static_bytes_verified=False,
                          verification_view='execute',generation=observed['generation'])
            self._event('breakpoint',result)
            return self._remember_breakpoints(dict(address=address,cs=cs,access=access,length=length,view=view),result)
        linear, selector = self.project._dos_parse_address(address,cs)
        offset = linear-self.static_base
        if not 0 <= offset < self.module_size:
            raise ValueError('Breakpoint is outside the original mapped DOS module')
        snapshot = self.project.disassembly(address=address,cs=cs,version=self.version['id'],lines=1)
        rows = snapshot['instructions']
        if not rows or int(rows[0]['address'],16) != linear:
            raise ValueError('Analyze this address before setting a disassembly breakpoint')
        size = rows[0]['size']
        if selector is None:
            selector = rows[0]['cs']
        runtime_cs = selector + self.runtime_load-self.dos['load_segment']
        ip = linear-selector*16
        if not 0 <= runtime_cs <= 0xffff or ip+size > 0x10000:
            raise ValueError('Breakpoint translation would wrap the segment')
        runtime_address = {'space':'segmented','segment':f'0x{runtime_cs:04X}','offset':f'0x{ip:08X}'}
        observed = self.call('memory.read',{'address':runtime_address,'length':size})
        data = base64.b64decode(observed['data_base64'],validate=True)
        if data != bytes(self.expected[offset:offset+size]):
            raise DebuggerError('Runtime code bytes differ from the selected static instruction; breakpoint refused')
        result = self.call('breakpoints.create',{'kind':'execution','address':runtime_address,'once':False})
        result.update(run=self.run_id,version=self.version['id'],project_address=hex(linear),
                      project_cs=f'0x{selector:04X}',instruction_context=rows[0]['context'],runtime_bytes=data.hex(),bytes_verified=True)
        self._event('breakpoint',result)
        return self._remember_breakpoints(dict(address=address,cs=cs,access=access,length=length,view=view),result)

    def _data_breakpoint(self, address, *, cs, access, length):
        if not self.rpc.capabilities.get('breakpoints',{}).get('data_access'):
            raise DebuggerError('DOSBox build lacks data-access breakpoints; rebuild the backend')
        linear, _ = self.project._dos_parse_address(address,cs)
        offset = linear-self.static_base
        if not 0 <= offset or offset+length > self.module_size:
            raise ValueError('Data breakpoint range is outside the original mapped DOS module')
        results = []
        try:
            for i in range(length):
                runtime = self.runtime_base+offset+i
                result = self.call('breakpoints.create',{'kind':access,'once':False,
                    'address':{'space':'linear','offset':f'0x{runtime:08X}'}})
                result.update(project_address=hex(linear+i),access=access,bytes_verified=False)
                results.append(result)
        except BaseException:
            for result in results:
                self.delete_breakpoint(result['breakpoint_id'])
            raise
        evidence = {'run':self.run_id,'access':access,'length':length,'breakpoints':results,
                    'stop_semantics':'after_data_access_at_core_check_completion_unknown'}
        self._event('data-breakpoint',evidence)
        return evidence

    def memory(self, address, *, cs=None, length=16):
        if self.call('state.get_registers').get('cpu_mode')!='real':
            raise ValueError('DOS source memory requires real mode; use an explicitly qualified runtime RAM binding')
        bounded(length,'length',1,65536)
        linear, _ = self.project._dos_parse_address(address,cs)
        offset = linear-self.static_base
        if offset < 0 or offset+length > self.module_size:
            raise ValueError('Memory range is outside the original mapped DOS module')
        result = self.call('memory.read',{'address':{'space':'linear','offset':f'0x{linear+self.delta:08X}'},'length':length})
        result.update(project_address=hex(linear),hex=base64.b64decode(result['data_base64'],validate=True).hex())
        return result

    def _disk_manifest(self):
        entries = []; size = 0
        protected = {self.project.path,Path(str(self.project.path)+'-wal'),Path(str(self.project.path)+'-shm'),Path(str(self.project.path)+'-journal')}
        for path in sorted(self.game_dir.rglob('*')):
            if path.is_symlink():
                raise ValueError('Save states require a game directory without symbolic links')
            if not path.is_file() or path.resolve() in protected:
                continue
            size += path.stat().st_size
            if size > 256*1024*1024 or len(entries)>=4096:
                raise ValueError('Game directory exceeds state manifest budget')
            entries.append({'path':str(path.relative_to(self.game_dir)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        return entries

    @timeline_locked
    def save_state(self, name='checkpoint.sav', *, max_bytes=None):
        _file_name(name)
        checkpoint = DebugSession._capture_native_checkpoint(self, max_bytes=max_bytes)
        return self._artifact(name, 'state', checkpoint['data'], checkpoint['metadata'])

    @timeline_locked
    def _capture_native_checkpoint(self, *, max_bytes=None):
        """Capture a complete private payload, independent of durable artifacts."""
        if max_bytes is not None:
            bounded(max_bytes,'max_bytes',1,256*1024*1024)
        if getattr(self, '_spatial_guard_active', False) or getattr(self, '_spatial_guard_failed', False):
            raise ValueError('Cannot checkpoint a temporary or unrestored spatial guard')
        if not self.rpc.capabilities.get('save_states'):
            raise DebuggerError('DOSBox build lacks native state operations')
        _require_released_mouse(self.call('input.mouse.state').get('mouse', {}))
        if self.rpc.capabilities.get('input',{}).get('keyboard'):
            keyboard=self.keyboard_state()['keyboard']
            if keyboard['pending_events'] or keyboard['owned_keys']:
                raise ValueError('Run until queued keyboard input completes before saving a state')
        before = self._disk_manifest()
        layer_state = self._layer_state()
        registers = self.registers()
        if registers.get('cpu_mode') not in ('real','v86','protected'):
            raise ValueError('Native project checkpoint has an unknown CPU mode')
        if registers['cpu_mode']!='real' and (layer_state['active'] or layer_state.get('ram_applied')):
            raise ValueError('Disable real-mode code layers before a protected/v86 checkpoint')
        if layer_state['active']:
            self.layers(layer_state['active'])
        with tempfile.TemporaryDirectory(prefix='fdisbull-state-') as directory:
            path = Path(directory)/'state.sav'
            saved = self.call('state.save',{'path':str(path)})
            if path.stat().st_size > (max_bytes or 256*1024*1024):
                raise ValueError('Native state exceeds remaining rewind byte budget')
            data = path.read_bytes()
        if max_bytes is not None and len(data)>max_bytes:
            raise ValueError('Native state exceeds remaining rewind byte budget')
        if before != self._disk_manifest():
            raise DebuggerError('Mounted game files changed while capturing state')
        metadata = {**self.metadata,'registers':registers,'disk_manifest':before,
                    'format':'dosbox-x-native','disk_restore':False,'code_layers':layer_state,
                    'checkpoint_scope':'full native machine; CPU mode/descriptor state belongs to the serializer',
                    'register_verification':'exposed registers, CPU mode and observed address context'}
        if self.rpc.capabilities.get('frame_timeline'):
            metadata['frame_keys'] = saved.get('frame_keys', [])
        if hasattr(self,'_state_provenance'):
            metadata['derivation'] = self._state_provenance
        return dict(data=data, sha256=hashlib.sha256(data).hexdigest(), metadata=metadata)

    @timeline_locked
    def load_state(self, artifact):
        if getattr(self,'_cpu_delta_history',None) is None:
            return DebugSession._load_native_state(self,artifact)
        with self._cpu_delta_full_load():
            result = self._load_native_state(artifact)
            self._cpu_delta_loaded(self.metadata.get('delta_experiment'))
        return result

    def _load_native_state(self, artifact):
        row = self.project.db.execute("""SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?""",(artifact,)).fetchone()
        if row is None or row['kind'] != 'state' or row['version'] != self.version['id']:
            raise ValueError('State must belong to the selected project version')
        metadata = json.loads(row['metadata']); data = bytes(row['data'])
        result = DebugSession._restore_native_checkpoint(self,
            dict(data=data, sha256=row['sha256'], metadata=metadata))
        result['artifact'] = artifact
        self._event('load-state',result)
        return result

    @timeline_locked
    def _restore_native_checkpoint(self, checkpoint):
        """Restore and verify a full native payload, including frame input ownership."""
        metadata = checkpoint['metadata']; data = checkpoint['data']
        if hashlib.sha256(data).hexdigest()!=checkpoint['sha256']:
            raise ValueError('Stored state hash mismatch')
        for field in ('source_sha256','version_sha256','emulator_sha256','runtime_load_segment','runtime_profile','game_dir'):
            if metadata.get(field) != self.metadata.get(field):
                raise ValueError('State compatibility mismatch: '+field)
        if metadata['disk_manifest'] != self._disk_manifest():
            raise ValueError('Mounted game files differ from state; restore the matching files first')
        protected_snapshot=metadata['registers'].get('cpu_mode') in ('protected','v86')
        saved_layers=metadata.get('code_layers',{})
        if protected_snapshot and (saved_layers.get('active') or saved_layers.get('ram_applied')):
            raise ValueError('Protected/v86 checkpoint cannot restore real-mode code layers')
        frame_keys = metadata.get('frame_keys', [])
        from .keyboard_input import KEYS
        if (not isinstance(frame_keys, list) or any(not isinstance(key, str) or key not in KEYS for key in frame_keys)
                or len(set(frame_keys)) != len(frame_keys)):
            raise ValueError('Invalid saved frame input ownership')
        if frame_keys and not self.rpc.capabilities.get('frame_timeline'):
            raise ValueError('Backend cannot restore saved frame input ownership')
        with FrameTimelineSessionMixin._timeline_full_load(self), tempfile.TemporaryDirectory(prefix='fdisbull-state-') as directory:
            path = Path(directory)/'state.sav'; path.write_bytes(data)
            try:
                params = {'path':str(path)}
                if self.rpc.capabilities.get('frame_timeline'):
                    params['frame_keys'] = frame_keys
                result = self.call('state.load',params)
                if self.rpc.capabilities.get('frame_timeline') and result.get('frame_keys') != frame_keys:
                    raise DebuggerError('Restored frame input ownership differs from saved state')
                _require_released_mouse(self.call('input.mouse.state').get('mouse', {}))
                registers = self.registers()
                for field in ('general','segments','instruction_pointer','flags','cpu_mode'):
                    if registers.get(field) != metadata['registers'].get(field):
                        raise DebuggerError('Restored CPU differs from saved state: '+field)
                if ('address_context' in metadata['registers']
                        and registers.get('address_context')!=metadata['registers']['address_context']):
                    raise DebuggerError('Restored CPU differs from saved state: address_context')
                if protected_snapshot:
                    self._layer_setup();self._layers=[];self._ram_base={};self._ram_applied={}
                else:self._restore_layer_state(saved_layers)
            except BaseException:
                self.close() # A partially failed native restore must never be resumed.
                raise
        result.update(sha256=checkpoint['sha256'],registers=registers,
                      framebuffer='invalidated_until_next_completed_frame')
        self._keyboard_leases={}
        self._invalidate_runtime_bindings()
        self.metadata['execution_origin']='restored-full-native-checkpoint'
        self.metadata['checkpoint_intervention']=metadata.get('derivation')
        if metadata.get('derivation') is not None:self._state_provenance=metadata['derivation']
        elif hasattr(self,'_state_provenance'):del self._state_provenance
        result['intervention']={'kind':'full-native-checkpoint-restore',
                                'edited_fork':metadata.get('derivation') is not None,
                                'derivation':metadata.get('derivation'),
                                'live_session_ram_edit':False,'host_files_restored':False}
        for key in ('delta_experiment', 'timeline_experiment'):
            self.metadata.pop(key, None)
            if metadata.get(key) is not None:
                self.metadata[key] = metadata[key]
        FrameTimelineSessionMixin._timeline_loaded(self)
        return result

    @timeline_locked
    def script(self, script=None, *, script_id=None, timeout_ms=60000):
        from .debug_script import execute_script
        if (script is None)==(script_id is None):
            raise ValueError('Supply exactly one of script or script_id')
        if script_id is not None:
            row = self.project.db.execute('SELECT * FROM debug_scripts WHERE id=? AND version=?',
                (script_id,self.version['id'])).fetchone()
            if row is None:
                raise ValueError('Unknown script for selected project version')
            if hashlib.sha256(row['script'].encode()).hexdigest()!=row['sha256']:
                raise ValueError('Stored script hash mismatch')
            script = json.loads(row['script'])
        return execute_script(self,script,timeout_ms=timeout_ms)

    def delete_breakpoint(self, breakpoint_id):
        self._layer_setup()
        result = self.call('breakpoints.delete',{'breakpoint_id':breakpoint_id})
        self._forget_breakpoint(breakpoint_id)
        control=self._hooks.pop(breakpoint_id,None)
        if control is not None:
            control['breakpoints']=[i for i in control['breakpoints'] if i!=breakpoint_id]
        self._event('delete_breakpoint',result)
        return result

    @property
    def keyboard(self):
        from .keyboard_input import GuestKeyboard
        return GuestKeyboard(self)

    def _keyboard_call(self, operation, params=None):
        if self.rpc.capabilities.get('input',{}).get('keyboard')!='ibm_pc_controller_us_ascii_v1':
            raise DebuggerError('DOSBox build lacks guest keyboard input; rebuild the 0.16.0 backend')
        result=self.call('input.keyboard.'+operation,params or {})
        self._event('keyboard.'+operation,result)
        return result

    def keyboard_press(self, key, *, modifiers=(), hold_ms=40, gap_ms=40):
        from .keyboard_input import validate_keyboard
        validate_keyboard(key=key,modifiers=modifiers,hold_ms=hold_ms,gap_ms=gap_ms)
        return self._keyboard_call('press',dict(key=key,modifiers=','.join(modifiers),hold_ms=hold_ms,gap_ms=gap_ms))

    def keyboard_type(self, text, *, hold_ms=40, gap_ms=40):
        from .keyboard_input import validate_keyboard
        validate_keyboard(text=text,hold_ms=hold_ms,gap_ms=gap_ms)
        return self._keyboard_call('type',dict(text=text,hold_ms=hold_ms,gap_ms=gap_ms))

    def keyboard_state(self):
        return self._keyboard_call('state')

    def keyboard_key_down(self, key):
        from .keyboard_input import KEYS
        if key not in KEYS:raise ValueError('Unknown physical keyboard key')
        if not self.rpc.capabilities.get('input',{}).get('keyboard_held_leases'):
            raise ValueError('Backend lacks held-key leases')
        leases=getattr(self,'_keyboard_leases',{})
        if key in leases.values():raise ValueError('Physical key already has an owned lease')
        token=uuid.uuid4().hex
        result=self._keyboard_call('down',{'key':key,'lease':token})
        leases[token]=key;self._keyboard_leases=leases
        return {**result,'lease':token,'key':key,'run':self.run_id,'claim':'Physical make queued; game consumption not established.'}

    def keyboard_key_up(self, lease):
        leases=getattr(self,'_keyboard_leases',{})
        if not isinstance(lease,str) or lease not in leases:raise ValueError('Unknown, consumed or unrelated input lease')
        key=leases[lease]
        result=self._keyboard_call('up',{'lease':lease})
        del leases[lease]
        return {**result,'lease':lease,'key':key,'consumed':True,'claim':'Physical break queued; release must be observed.'}

    def proof_check(self,spec, *, timeout_ms=1000,author='agent',evidence=None):
        result=self.project.proof_check(spec,version=self.version['id'],timeout_ms=timeout_ms,author=author,
                                        evidence=[{'run':self.run_id},*(evidence or [])])
        self._event('proof-check',{'id':result['id'],'status':result['result']['status']})
        return result

    def click(self, x, y, *, button='left', hold_ms=80, mode_id=None, frame_id=None):
        bounded(x,'x',0,4095); bounded(y,'y',0,4095); bounded(hold_ms,'hold_ms',1,1000)
        if button not in ('left','right','middle'):
            raise ValueError('button must be left, right or middle')
        params = dict(x=x,y=y,button=button,hold_ms=hold_ms)
        if mode_id is not None:
            params['mode_id'] = bounded(mode_id,'mode_id',0,(1<<53)-1)
        if frame_id is not None:
            params['frame_id'] = bounded(frame_id,'frame_id',0,(1<<53)-1)
        result = self.call('input.mouse.click',params)
        self._event('click',result)
        return result

    def click_frame(self, x, y, *, name='click-frame.png', grid_step=8,
                    button='left', hold_ms=80, mode_id=None):
        """Capture, label the exact target, and queue its mode-bound click in one call."""
        from .screenshot_grid import validate_step
        _file_name(name);validate_step(grid_step)
        bounded(x,'x',0,4095);bounded(y,'y',0,4095);bounded(hold_ms,'hold_ms',1,1000)
        if button not in ('left','right','middle'):
            raise ValueError('button must be left, right or middle')
        if mode_id is not None:bounded(mode_id,'mode_id',0,(1<<53)-1)
        clean=self.screenshot(name[:248]+'.raw.png')
        metadata=clean['metadata']
        if x>=metadata['width'] or y>=metadata['height']:
            raise ValueError('Click target is outside the captured native frame')
        if mode_id is not None and mode_id!=metadata['mode_id']:
            raise ValueError('Click mode differs from the newly captured frame mode')
        frame=self.project.debug_grid(clean['artifact'],name=name,step=grid_step,target=[x,y])
        click=self.click(x,y,button=button,hold_ms=hold_ms,mode_id=metadata['mode_id'])
        result=dict(run=self.run_id,x=x,y=y,mode_id=metadata['mode_id'],frame=frame,click=click,
                    frame_phase='before_queued_click')
        self._event('click-frame',result)
        return result

    def _artifact(self, name, kind, data, metadata):
        for key in ('delta_experiment', 'timeline_experiment'):
            experiment = getattr(self, 'metadata', {}).get(key)
            if experiment is not None:
                metadata = dict(metadata, **{key: experiment})
        return self.project._debug_artifact(self.run_id,name,kind,data,metadata)

    def frame_rgba(self, *, encoding='rgba-zstd'):
        """Consume a completed frame in memory, without hooks or artifact writes.

        This observes the current completed frame. It does not pause or advance
        the guest; callers comparing observations should own a paused session.
        """
        from .screenshot_codecs import decode_frame_rgba, validate_encoding
        capabilities = {} if encoding == 'png' else getattr(getattr(self, 'rpc', None), 'capabilities', {})
        validate_encoding(encoding, capabilities)
        result = self.call('video.screenshot', {'encoding': encoding}) if encoding != 'png' else self.call('video.screenshot')
        return decode_frame_rgba(result)

    def screenshot(self, name='screenshot.png', *, grid=False, grid_step=32, hooks=True, encoding='png'):
        from .screenshot_grid import validate_step
        from .screenshot_codecs import validate_encoding
        _file_name(name)
        if type(grid) is not bool:
            raise ValueError('grid must be boolean')
        validate_step(grid_step)
        capabilities = {} if encoding == 'png' else getattr(getattr(self, 'rpc', None), 'capabilities', {})
        validate_encoding(encoding, capabilities)
        return self._capture_with_hooks(lambda evidence:self._screenshot_capture(name,grid,grid_step,evidence,encoding),hooks=hooks)

    def _screenshot_capture(self,name,grid,grid_step,hook_evidence,encoding='png'):
        from .screenshot_codecs import decode_screenshot
        result = self.call('video.screenshot', {'encoding': encoding}) if encoding != 'png' else self.call('video.screenshot')
        if hook_evidence and hook_evidence.get('require_fresh_frame'):
            before=hook_evidence['before_frame_id'];after=result.get('frame_id')
            if type(after) is not int or (before is not None and after<=before):
                raise DebuggerError('Screenshot preparation did not produce a newly completed frame')
        data, result = decode_screenshot(result)
        if hook_evidence is not None:result['screenshot_hooks']=hook_evidence
        if not grid:
            return self._artifact(name,'screenshot',data,result)
        raw=self._artifact(name[:248]+'.raw.png','screenshot',data,result)
        return self.project.debug_grid(raw['artifact'],name=name,step=grid_step)

    def trace(self, name='trace.json', *, count=512, timeout_ms=10000, fast_forward=False):
        _file_name(name)
        bounded(count,'count',1,10000)
        bounded(timeout_ms,'timeout_ms',1,600000)
        if type(fast_forward) is not bool:
            raise ValueError('fast_forward must be boolean')
        self.call('trace.start',{'detail':'normal','instruction_count':count})
        try:
            run = self.run(timeout_ms=timeout_ms,fast_forward=fast_forward)
            events = []; cursor = None; seen = set()
            while True:
                page = self.call('trace.read',{'cursor':cursor,'limit':1000})
                events.extend(page['events'])
                cursor = page.get('next_cursor')
                if len(events)>count or cursor in seen:
                    raise DebuggerError('Invalid trace pagination')
                if not cursor:
                    break
                seen.add(cursor)
        finally:
            self.call('trace.stop')
        for event in events:
            event['project_address'] = (self.project_address(event['address'])
                if event.get('cpu_mode')=='real' else None)
            if event['project_address'] is not None:
                segment = int(event['address']['segment'],16)-self.runtime_load+self.dos['load_segment']
                event['project_segmented_address'] = (f"{segment:04x}:{int(event['address']['offset'],16):04x}"
                    if 0 <= segment <= 0xffff else None)
        self._layer_trace(events)
        from .debug_semantics import normalize_trace,contract
        backend=self.metadata.get('backend','dosbox')
        normalize_trace(backend,events,version=self.version['id'],delta=self.delta,budget_reached=len(events)==count)
        result = {'run':run,'version':self.version['id'],'mapping':self.metadata,'events':events,
                  'requested_count':count,'complete':len(events)==count,'observation_contract':contract(backend)}
        return self._artifact(name,'trace',json.dumps(result,indent=2).encode(),
                              {'event_count':len(events),'complete':result['complete'],'run':run})

    @timeline_locked
    def close(self):
        if self.closed:
            return
        result = {'state':'interrupted'}
        cleanup_error = interrupted = None
        def failed(phase, error):
            nonlocal cleanup_error
            result.setdefault('cleanup_errors', []).append(
                {'phase':phase,'type':type(error).__name__,'message':str(error)})
            if cleanup_error is None:
                cleanup_error = error
        def cleanup(phase, function):
            try:
                return function()
            except BaseException as error:
                failed(phase, error)
        try:
            operation = self.call('session.stop')
            result = self.call('execution.wait',{'operation_id':operation['operation_id'],'timeout_ms':3000})
            if result.get('running'):
                result = {'state':'interrupted','reason':'stop deadline expired'}
        except Exception as error:
            result = {'state':'interrupted','error':str(error)}
        except BaseException as error:
            interrupted = error
            result = {'state':'interrupted','error':str(error)}
        finally:
            try:
                cleanup('rpc.close', lambda: self.rpc.close())
            finally:
                # The live cache and ownership must not outlive even a failed
                # transport/process cleanup. Further calls are terminal.
                self.closed = True
                self._frame_timeline = None
                self._keyboard_leases={}
            cleanup('runtime-bindings', lambda: self._invalidate_runtime_bindings())
            if getattr(self, '_launch_alias', None) is not None:
                result['launch_alias_cleanup'] = cleanup('launch-alias', self._launch_alias.close)
            process = getattr(self.rpc, 'process', None)
            result['process_reaped'] = None
            if process is not None:
                try:
                    result['process_reaped'] = process.poll() is not None
                except BaseException as error:
                    failed('process-status', error)
            try:
                cleanup('close-receipt', lambda: self._event('close',result))
                def record_ended():
                    with self.project.transaction(True):
                        self.project.db.execute('UPDATE debug_runs SET ended=? WHERE id=?',(stamp(),self.run_id))
                cleanup('run-ended', record_ended)
            finally:
                def remove_owner():
                    if self in self.project._live_debuggers:
                        self.project._live_debuggers.remove(self)
                cleanup('live-registry', remove_owner)
        if interrupted is not None:
            raise interrupted
        if cleanup_error is not None:
            raise cleanup_error


class DebugWorkspace:
    """Live session ownership for the existing foreground JSON-lines server."""
    def __init__(self):
        self.sessions = {}
        self.async_runs = {}

    def _async_result(self, run, operation, wait_ms=0):
        bounded(wait_ms,'wait_ms',0,1000)
        job=self.async_runs.get(operation)
        if job is None or job['run']!=run:raise ValueError('Unknown asynchronous run for this session')
        complete=job['done'].wait(wait_ms/1000)
        if complete:job['collected']=True
        return {'run':run,'operation':operation,'complete':complete,
                **({'result':job.get('result'),'error':job.get('error')} if complete else {'state':'running'})}

    def _start_async(self, session, params):
        import inspect
        import threading
        if session.metadata.get('backend') not in ('scummvm-agi','scummvm-gob'):
            raise ValueError('Asynchronous foreground runs currently require a ScummVM engine backend')
        if any(j['run']==session.run_id and not j['done'].is_set() for j in self.async_runs.values()):
            raise ValueError('This session already has an asynchronous run')
        if len(self.async_runs)>=64:
            retired=next((key for key,value in self.async_runs.items()
                          if value['done'].is_set() and value.get('collected')),None)
            if retired is None:raise ValueError('Collect completed asynchronous runs before starting another operation')
            del self.async_runs[retired]
        inspect.signature(session.run).bind(**params)
        operation=uuid.uuid4().hex
        job={'run':session.run_id,'done':threading.Event()}
        self.async_runs[operation]=job
        def execute():
            try:
                job['result']=session.run(**params)
                session._event('async-run-complete',{'operation':operation,'result':job['result']})
            except Exception as error:
                job['error']={'type':type(error).__name__,'message':str(error)}
                try:session._event('async-run-failed',{'operation':operation,'error':job['error']})
                except Exception as event_error:job['error']['receipt_error']=str(event_error)
            finally:job['done'].set()
        job['thread']=threading.Thread(target=execute,name='fdisbull-scummvm-run',daemon=True)
        try:job['thread'].start()
        except BaseException:
            del self.async_runs[operation]
            raise
        # Wait only for dispatch, not the bounded native run. This lets the
        # foreground server accept a subsequent pause request immediately.
        deadline=time.monotonic()+1
        with session._run_condition:
            while not session._run_sent and not job['done'].is_set():
                remaining=deadline-time.monotonic()
                if remaining<=0:break
                session._run_condition.wait(remaining)
        return self._async_result(session.run_id,operation)

    def _join_async(self, run):
        for operation,job in list(self.async_runs.items()):
            if job['run']==run:
                job['thread'].join(timeout=5)
                if job['thread'].is_alive():
                    raise DebuggerError('Engine closed but its asynchronous operation has not finished')
                del self.async_runs[operation]

    def invoke(self, method, project, params):
        from .project import Project
        if method=='debug-launch':
            db = Project(project)
            try:
                session = db.debugger(**params)
            except BaseException:
                db.__exit__()
                raise
            self.sessions[session.run_id] = session
            return session.status()
        run = params.pop('run',None)
        session = self.sessions.get(run)
        if session is None or session.project.path != Path(project).resolve():
            raise ValueError('Live run not owned by this server; use debug-runs for saved history')
        if method=='debug-run-result':
            return self._async_result(run,**params)
        pending=any(j['run']==run and not j['done'].is_set() for j in self.async_runs.values())
        if pending and method not in ('debug-status','debug-pause','debug-stop'):
            raise ValueError('Pause or collect the outstanding asynchronous run before another operation')
        if method=='debug-run-async':
            return self._start_async(session,params)
        methods = {'debug-spectator':'dot_mode','debug-spectator-frame':'spectator_frame',
                   'debug-memory-snapshot':'memory_snapshot','debug-memory-apply':'memory_apply',
                   'debug-memory-rule-tick':'memory_rule_tick','debug-memory-rule-run':'memory_rule_run',
                   'debug-desqview-observe':'desqview_observe',
                   'debug-memory-translation':'memory_translation','debug-qemm-observe':'qemm_observe',
                   'debug-status':'status','debug-dos-process':'dos_process_info','debug-registers':'registers','debug-breakpoint':'breakpoint','debug-delete-breakpoint':'delete_breakpoint',
                   'debug-engine-state':'engine_state','debug-write-engine-state':'write_engine_state',
                   'debug-read-variable':'read_variable','debug-write-variable':'write_variable',
                   'debug-hotspot-events':'hotspot_events',
                   'debug-step':'step','debug-watchpoint':'watchpoint','debug-delete-watchpoint':'delete_watchpoint',
                   'debug-resource':'resource_info',
                   'debug-read-resource':'resource','debug-patch-resource':'patch_resource','debug-engine-cycle':'run_until_cycle',
                   'debug-restore-resource':'restore_resource',
                   'debug-keyboard-press':'keyboard_press','debug-keyboard-type':'keyboard_type','debug-keyboard-state':'keyboard_state',
                   'debug-run':'run','debug-wait':'wait','debug-click':'click','debug-click-frame':'click_frame','debug-screenshot':'screenshot','debug-trace':'trace',
                   'debug-trace-until':'trace_until',
                   'debug-screenshot-hooks':'screenshot_hooks',
                   'debug-memory':'memory','debug-write-memory':'write_memory','debug-write-registers':'write_registers','debug-save-state':'save_state','debug-load-state':'load_state','debug-script':'script',
                   'debug-contexts':'contexts','debug-pause':'pause','debug-resume':'resume'}
        methods.update({'debug-save-anchor-stone':'save_anchor_stone','debug-load-anchor-stone':'load_anchor_stone'})
        methods.update({'debug-layer-stack':'layers','debug-layer-enable':'layer_enable','debug-layer-patch':'layer_patch',
                        'debug-code':'code','debug-capture-code':'capture_code','debug-branch':'branch',
                        'debug-cave':'cave','debug-hook':'hook','debug-hooks':'hooks','debug-delete-hook':'delete_hook'})
        methods.update({'debug-controls':'controls','debug-save-experiment':'save_experiment',
                        'debug-restore-experiment':'restore_experiment','debug-compare-experiment':'compare_experiment'})
        methods.update({'debug-rewind-start':'rewind_start','debug-rewind-status':'rewind_status',
                        'debug-rewind-record':'rewind_record','debug-rewind':'rewind'})
        methods.update({'debug-delta-start':'cpu_delta_start','debug-delta-status':'cpu_delta_status',
                        'debug-delta-record':'cpu_delta_record','debug-delta-rewind':'cpu_delta_rewind',
                        'debug-delta-recover':'cpu_delta_recover'})
        methods.update({'debug-frame-advance':'advance_frames','debug-frame-inputs':'frame_inputs',
                        'debug-timeline-start':'timeline_start','debug-timeline-status':'timeline_status',
                        'debug-timeline-advance':'timeline_advance','debug-timeline-rewind':'timeline_rewind',
                        'debug-timeline-stop':'timeline_stop','debug-timeline-pin':'timeline_pin',
                        'debug-timeline-image':'timeline_image'})
        methods.update({'debug-frame-probe':'frame_probe','debug-scene-check':'scene_check',
                        'debug-scene-assert':'scene_assert','debug-scene-click':'scene_click','debug-scene-act':'scene_act','debug-scene-wait':'scene_wait'})
        methods.update({'debug-keyboard-down':'keyboard_key_down','debug-keyboard-up':'keyboard_key_up',
                        'debug-macro':'macro','debug-move':'move','debug-bind-runtime-memory':'bind_runtime_memory',
                        'debug-runtime-memory':'runtime_memory','debug-write-runtime-memory':'write_runtime_memory','debug-proof-check':'proof_check','debug-scene-navigation':'scene_navigation'})
        methods.update({'debug-workflow-observe':'workflow_observe','debug-workflow-act':'workflow_act',
                        'debug-text-observe':'text_observe','debug-text-act':'text_act','debug-assisted-travel':'assisted_travel'})
        methods.update({'debug-spatial-policy':'spatial_policy','debug-spatial-action':'spatial_action'})
        context=params.pop('context',None)
        if method=='debug-stop':
            if params:
                raise ValueError('Unexpected stop options')
            session.close()
            self._join_async(run)
            session.project.__exit__()
            del self.sessions[run]
            return {'run':run,'closed':True,'process_reaped':session.rpc.process.poll() is not None}
        selected=session.context(context) if context is not None else session
        operation=getattr(selected,methods[method],None)
        if operation is None:
            if getattr(session,'metadata',{}).get('backend')=='qemu-dos':
                from .dos_migration import unavailable_operation
                raise ValueError(unavailable_operation(method))
            raise ValueError('Operation is unavailable in the selected execution context')
        return operation(**params)

    def close(self):
        for session in self.sessions.values():
            try:
                session.close()
                self._join_async(session.run_id)
            finally:
                session.project.__exit__()
        self.sessions.clear()
