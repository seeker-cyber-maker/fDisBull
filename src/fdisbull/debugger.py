"""Project-bound DOS runtime observations, separate from immutable static facts."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import time
import uuid
import tempfile

from .dosbox_rpc import DOSBoxRPC, DebuggerError
from .external_files import _file_name
from .code_layers import LayerProjectMixin, LayerSessionMixin, LAYER_DDL


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


class DebugProjectMixin(LayerProjectMixin):
    def debugger(self, executable, game_dir, *, version=None):
        return DebugSession(self, executable, game_dir, version=version)

    def debug_runs(self, version=None):
        v = self.version(version)['id']
        return {'version':v,'live_state_verified':False,'runs':[{**dict(r),'metadata':json.loads(r['metadata'])}
                for r in self.db.execute('SELECT * FROM debug_runs WHERE version=? ORDER BY created,id',(v,))]}

    def debug_artifacts(self, version=None, run=None):
        v = self.version(version)['id']
        rows = self.db.execute('''SELECT a.id,a.run,a.name,a.kind,a.sha256,length(a.data) AS size,a.metadata
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

    def debug_state_info(self, artifact):
        import zipfile
        row = self.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                              (artifact,)).fetchone()
        if row is None or row['kind']!='state':
            raise ValueError('Unknown native state artifact')
        data = bytes(row['data'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Stored state hash mismatch')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            components = [{'name':i.filename,'size':i.file_size,'compressed_size':i.compress_size} for i in archive.infolist()]
        return {'artifact':artifact,'version':row['version'],'sha256':row['sha256'],'size':len(data),
                'metadata':json.loads(row['metadata']),'components':components}

    def debug_fork_state(self, artifact, executable, game_dir, *, name='derived.sav', memory=None, registers=None):
        info = self.debug_state_info(artifact)
        memory = [] if memory is None else memory
        registers = {} if registers is None else registers
        if not isinstance(memory,list) or len(memory)>64 or not isinstance(registers,dict):
            raise ValueError('State edits require at most 64 memory edits and a register mapping')
        _file_name(name)
        from .debug_state import validate_edits, apply_edits
        validate_edits(memory,registers)
        if not memory and not registers:
            raise ValueError('A state fork requires at least one explicit edit')
        with self.debugger(executable,game_dir,version=info['version']) as debug:
            debug.load_state(artifact)
            edits = apply_edits(debug,memory,registers)
            debug._state_provenance = {'parent_artifact':artifact,'parent_sha256':info['sha256'],
                                       'edits':edits,'guest_execution_during_edits':False}
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
            used = self.db.execute('SELECT coalesce(sum(length(data)),0) FROM debug_artifacts').fetchone()[0]
            if used+len(data) > 256*1024*1024:
                raise ValueError('Project runtime artifact budget exceeds 256 MiB')
            self.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
                (identifier,run,name,kind,digest,data,json.dumps(metadata)))
            self.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                            (run,stamp(),'artifact',json.dumps(result)))
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


class DebugSession(LayerSessionMixin):
    """One explicitly owned emulator; closing the project also closes sessions."""
    def __init__(self, project, executable, game_dir, *, version=None):
        self.project = project
        self.rpc = None
        self.closed = False
        self.run_id = uuid.uuid4().hex
        self.version = project.version(version)
        if project.meta['format'] != 'MZ' or self.version['parent'] is not None:
            raise ValueError('Runtime launch requires the original, unpatched DOS MZ version; select version=1 explicitly if needed')
        self.dos = project._document(self.version['id'])['dos']
        self.game_dir = Path(game_dir).expanduser().resolve(strict=True)
        target = project.meta['filename']
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,8}\.[A-Za-z0-9]{1,3}',target):
            raise ValueError('DOS target must have a safe 8.3 filename')
        source = (self.game_dir / target).resolve(strict=True)
        if source.parent != self.game_dir or not source.is_file() or source.stat().st_size > 64*1024*1024:
            raise ValueError('Target must be a regular file directly inside game_dir, at most 64 MiB')
        if hashlib.sha256(source.read_bytes()).hexdigest() != project.meta['source_sha256']:
            raise ValueError('Game executable does not match the project source hash')
        executable = Path(executable).expanduser().resolve(strict=True)
        from . import __version__
        self.metadata = {'fdisbull_version':__version__,'source_sha256':project.meta['source_sha256'],'version_sha256':self.version['sha256'],
                         'executable':str(executable),'emulator_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
                         'runtime_profile':'real-normal-v1','game_dir':str(self.game_dir),'target':target,'static_load_segment':self.dos['load_segment']}
        try:
            self.rpc = DOSBoxRPC(executable,self.game_dir)
            result = self.rpc.call('session.start',{'target':{'command':target,'arguments':[]},
                'mounts':[{'drive':'C','host_path':str(self.game_dir)}],'break_at':'entry'})
            self.session_id = result['session_id']
            regs = self.call('state.get_registers')
            if regs['cpu_mode'] != 'real':
                raise DebuggerError('Expected real-mode MZ entry')
            header = self.dos['header_fields']
            self.runtime_load = int(regs['segments']['cs'],16) - header['e_cs']
            if (not 0x10 <= self.runtime_load <= 0xffff or
                    int(regs['instruction_pointer'],16) != header['e_ip']):
                raise DebuggerError('Runtime entry does not establish an unwrapped MZ load segment')
            self.static_base = self.dos['image_base']
            self.runtime_base = self.runtime_load * 16
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
            self.metadata.update(runtime_load_segment=self.runtime_load,entry_registers=regs,
                                 capabilities=self.rpc.capabilities,pid=self.rpc.process.pid)
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id,self.version['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            self._event('launch',result)
            project._live_debuggers.append(self)
        except BaseException:
            if self.rpc is not None:
                self.rpc.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def call(self, method, params=None):
        if self.closed:
            raise DebuggerError('Debugger session is closed')
        return self.rpc.call(method,{'session_id':self.session_id,**(params or {})})

    def _event(self, operation, evidence):
        with self.project.transaction(True):
            self.project.db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                                    (self.run_id,stamp(),operation,json.dumps(evidence)))
            state = evidence.get('state') or evidence.get('session',{}).get('state')
            if state:
                self.project.db.execute('UPDATE debug_runs SET state=? WHERE id=?',(state,self.run_id))

    def status(self):
        result = self.call('session.status')
        return {'run':self.run_id,'version':self.version['id'],'live':True,**result,'mapping':self.metadata}

    def _timing(self, enabled=None):
        if not self.rpc.capabilities.get('timing',{}).get('fast_forward'):
            raise DebuggerError('DOSBox build lacks execution.timing; rebuild with the current agent patch')
        return self.call('execution.timing',{} if enabled is None else {'fast_forward':enabled})

    def run(self, *, timeout_ms=10000, guest_ms=None, fast_forward=False):
        bounded(timeout_ms,'timeout_ms',1,600000)
        if guest_ms is not None:
            bounded(guest_ms,'guest_ms',1,3600000)
        if type(fast_forward) is not bool:
            raise ValueError('fast_forward must be boolean')
        before = self._timing()
        started = time.monotonic()
        deadline = started + timeout_ms/1000
        running = False
        result = None
        outcome = 'timeout'
        hook_hits = []
        timing = before
        try:
            self._timing(fast_forward)
            operation = self.call('execution.continue')
            running = True
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    break
                result = self.call('execution.wait',{'operation_id':operation['operation_id'],
                    'timeout_ms':max(1,min(10 if fast_forward else 50,int(remaining*1000)))})
                running = result.get('running',False)
                if not running:
                    hook_hit = self._dispatch_hook(result)
                    if hook_hit is not None:
                        hook_hits.append(hook_hit)
                        if time.monotonic() >= deadline:
                            break
                        operation = self.call('execution.continue')
                        running = True
                        continue
                    kind = result.get('stop_reason',{}).get('kind','stopped')
                    outcome = 'breakpoint' if kind=='breakpoint' else kind
                    break
                timing = self._timing()
                if guest_ms is not None and timing['guest_ticks']-before['guest_ticks'] >= guest_ms:
                    outcome = 'guest_time'
                    break
        finally:
            if not self.closed:
                try:
                    if running:
                        pause = self.call('execution.pause')
                        result = self.call('execution.wait',{'operation_id':pause['operation_id'],'timeout_ms':3000})
                        if result.get('running'):
                            raise DebuggerError('Target failed to pause after bounded run')
                    if result is None or result.get('state') != 'exited':
                        timing = self._timing(before['fast_forward'])
                except BaseException:
                    self.close()
                    raise
        evidence = {'run':self.run_id,'outcome':outcome,'timed_out':outcome=='timeout',
                    'requested_guest_ms':guest_ms,'guest_elapsed_ms':timing['guest_ticks']-before['guest_ticks'],
                    'host_elapsed_ms':round((time.monotonic()-started)*1000,3),
                    'fast_forward':fast_forward,'timing_after':timing,'session':result}
        evidence['hook_hits'] = hook_hits
        if result and result.get('stop_reason',{}).get('address'):
            result['stop_reason']['project_address'] = self.project_address(result['stop_reason']['address'])
        if result and result.get('stop_reason',{}).get('data_access'):
            access = result['stop_reason']['data_access']
            access['project_instruction'] = self.project_address(access['instruction'])
        self._event('run',evidence)
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
        result['project_address'] = self.project_address({'space':'segmented',
            'segment':result['segments']['cs'],'offset':result['instruction_pointer']})
        return result

    def breakpoint(self, address, *, cs=None, access='x', length=1, view='static'):
        if view not in ('static','execute'):
            raise ValueError('Breakpoint view must be static or execute')
        if access not in ('x','r','w','rw'):
            raise ValueError('access must be x, r, w, or rw')
        bounded(length,'length',1,256)
        if access != 'x':
            return self._data_breakpoint(address,cs=cs,access=access,length=length)
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
                          runtime_bytes=instruction['bytes'],bytes_verified=True,static_bytes_verified=False,
                          verification_view='execute',generation=observed['generation'])
            self._event('breakpoint',result)
            return result
        linear, selector = self.project._dos_parse_address(address,cs)
        offset = linear-self.static_base
        if not 0 <= offset < self.module_size:
            raise ValueError('Breakpoint is outside the original mapped MZ module')
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
        return result

    def _data_breakpoint(self, address, *, cs, access, length):
        if not self.rpc.capabilities.get('breakpoints',{}).get('data_access'):
            raise DebuggerError('DOSBox build lacks data-access breakpoints; rebuild the backend')
        linear, _ = self.project._dos_parse_address(address,cs)
        offset = linear-self.static_base
        if not 0 <= offset or offset+length > self.module_size:
            raise ValueError('Data breakpoint range is outside the original mapped MZ module')
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
                    'stop_semantics':'after_data_access_before_next_instruction'}
        self._event('data-breakpoint',evidence)
        return evidence

    def memory(self, address, *, cs=None, length=16):
        bounded(length,'length',1,65536)
        linear, _ = self.project._dos_parse_address(address,cs)
        offset = linear-self.static_base
        if offset < 0 or offset+length > self.module_size:
            raise ValueError('Memory range is outside the original mapped MZ module')
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

    def save_state(self, name='checkpoint.sav'):
        _file_name(name)
        if not self.rpc.capabilities.get('save_states'):
            raise DebuggerError('DOSBox build lacks native state operations')
        if self.call('input.mouse.state').get('mouse',{}).get('release_pending'):
            raise ValueError('Run until queued mouse releases complete before saving a state')
        before = self._disk_manifest()
        layer_state = self._layer_state()
        if layer_state['active']:
            self.layers(layer_state['active'])
        registers = self.registers()
        if registers['cpu_mode']!='real':
            raise ValueError('Native project checkpoints currently require real mode')
        with tempfile.TemporaryDirectory(prefix='fdisbull-state-') as directory:
            path = Path(directory)/'state.sav'
            self.call('state.save',{'path':str(path)})
            data = path.read_bytes()
        if before != self._disk_manifest():
            raise DebuggerError('Mounted game files changed while capturing state')
        metadata = {**self.metadata,'registers':registers,'disk_manifest':before,
                    'format':'dosbox-x-native','disk_restore':False,'code_layers':layer_state}
        if hasattr(self,'_state_provenance'):
            metadata['derivation'] = self._state_provenance
        return self._artifact(name,'state',data,metadata)

    def load_state(self, artifact):
        row = self.project.db.execute("""SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?""",(artifact,)).fetchone()
        if row is None or row['kind'] != 'state' or row['version'] != self.version['id']:
            raise ValueError('State must belong to the selected project version')
        metadata = json.loads(row['metadata']); data = bytes(row['data'])
        if hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('Stored state hash mismatch')
        for field in ('source_sha256','version_sha256','emulator_sha256','runtime_load_segment','runtime_profile','game_dir'):
            if metadata.get(field) != self.metadata.get(field):
                raise ValueError('State compatibility mismatch: '+field)
        if metadata['disk_manifest'] != self._disk_manifest():
            raise ValueError('Mounted game files differ from state; restore the matching files first')
        with tempfile.TemporaryDirectory(prefix='fdisbull-state-') as directory:
            path = Path(directory)/'state.sav'; path.write_bytes(data)
            try:
                result = self.call('state.load',{'path':str(path)})
                registers = self.registers()
                for field in ('general','segments','instruction_pointer','flags'):
                    if registers.get(field) != metadata['registers'].get(field):
                        raise DebuggerError('Restored CPU differs from saved state: '+field)
                self._restore_layer_state(metadata.get('code_layers',{}))
            except BaseException:
                self.close() # A partially failed native restore must never be resumed.
                raise
        result.update(artifact=artifact,sha256=row['sha256'],registers=registers,
                      framebuffer='invalidated_until_next_completed_frame')
        self._event('load-state',result)
        return result

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
        control=self._hooks.pop(breakpoint_id,None)
        if control is not None:
            control['breakpoints']=[i for i in control['breakpoints'] if i!=breakpoint_id]
        self._event('delete_breakpoint',result)
        return result

    def click(self, x, y, *, button='left', hold_ms=80, mode_id=None):
        bounded(x,'x',0,4095); bounded(y,'y',0,4095); bounded(hold_ms,'hold_ms',1,1000)
        if button not in ('left','right','middle'):
            raise ValueError('button must be left, right or middle')
        params = dict(x=x,y=y,button=button,hold_ms=hold_ms)
        if mode_id is not None:
            params['mode_id'] = bounded(mode_id,'mode_id',0,(1<<53)-1)
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
        return self.project._debug_artifact(self.run_id,name,kind,data,metadata)

    def screenshot(self, name='screenshot.png', *, grid=False, grid_step=32):
        from .screenshot_grid import validate_step
        _file_name(name)
        if type(grid) is not bool:
            raise ValueError('grid must be boolean')
        validate_step(grid_step)
        result = self.call('video.screenshot')
        data = base64.b64decode(result.pop('png_base64'),validate=True)
        if not data.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(data).hexdigest()!=result['sha256']:
            raise DebuggerError('Screenshot signature/hash mismatch')
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            if image.size != (result['width'],result['height']):
                raise DebuggerError('Screenshot dimensions differ from metadata')
            image.verify()
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
            event['project_address'] = self.project_address(event['address'])
            if event['project_address'] is not None:
                segment = int(event['address']['segment'],16)-self.runtime_load+self.dos['load_segment']
                event['project_segmented_address'] = (f"{segment:04x}:{int(event['address']['offset'],16):04x}"
                    if 0 <= segment <= 0xffff else None)
        self._layer_trace(events)
        result = {'run':run,'version':self.version['id'],'mapping':self.metadata,'events':events,
                  'requested_count':count,'complete':len(events)==count}
        return self._artifact(name,'trace',json.dumps(result,indent=2).encode(),
                              {'event_count':len(events),'complete':result['complete'],'run':run})

    def close(self):
        if self.closed:
            return
        result = {'state':'interrupted'}
        try:
            operation = self.call('session.stop')
            result = self.call('execution.wait',{'operation_id':operation['operation_id'],'timeout_ms':3000})
            if result.get('running'):
                result = {'state':'interrupted','reason':'stop deadline expired'}
        except Exception as error:
            result = {'state':'interrupted','error':str(error)}
        finally:
            self.rpc.close()
            self.closed = True
            result['process_reaped'] = self.rpc.process.poll() is not None
            try:
                self._event('close',result)
                with self.project.transaction(True):
                    self.project.db.execute('UPDATE debug_runs SET ended=? WHERE id=?',(stamp(),self.run_id))
            finally:
                if self in self.project._live_debuggers:
                    self.project._live_debuggers.remove(self)


class DebugWorkspace:
    """Live session ownership for the existing foreground JSON-lines server."""
    def __init__(self):
        self.sessions = {}

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
        methods = {'debug-status':'status','debug-registers':'registers','debug-breakpoint':'breakpoint','debug-delete-breakpoint':'delete_breakpoint',
                   'debug-run':'run','debug-click':'click','debug-click-frame':'click_frame','debug-screenshot':'screenshot','debug-trace':'trace',
                   'debug-memory':'memory','debug-save-state':'save_state','debug-load-state':'load_state','debug-script':'script'}
        methods.update({'debug-layer-stack':'layers','debug-layer-enable':'layer_enable','debug-layer-patch':'layer_patch',
                        'debug-code':'code','debug-capture-code':'capture_code','debug-branch':'branch',
                        'debug-cave':'cave','debug-hook':'hook','debug-hooks':'hooks','debug-delete-hook':'delete_hook'})
        if method=='debug-stop':
            if params:
                raise ValueError('Unexpected stop options')
            session.close()
            session.project.__exit__()
            del self.sessions[run]
            return {'run':run,'closed':True,'process_reaped':session.rpc.process.poll() is not None}
        return getattr(session,methods[method])(**params)

    def close(self):
        for session in self.sessions.values():
            try:
                session.close()
            finally:
                session.project.__exit__()
        self.sessions.clear()
