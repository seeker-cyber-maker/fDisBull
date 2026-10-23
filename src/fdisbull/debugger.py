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

from .dosbox_rpc import DOSBoxRPC, DebuggerError
from .external_files import _file_name


DEBUG_DDL = '''
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


class DebugProjectMixin:
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


class DebugSession:
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
                         'game_dir':str(self.game_dir),'target':target,'static_load_segment':self.dos['load_segment']}
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
                    kind = result.get('stop_reason',{}).get('kind','stopped')
                    outcome = 'breakpoint' if kind=='breakpoint' else kind
                    break
                timing = self._timing()
                if guest_ms is not None and timing['guest_ticks']-before['guest_ticks'] >= guest_ms:
                    outcome = 'guest_time'
                    break
        finally:
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
        if result and result.get('stop_reason',{}).get('address'):
            result['stop_reason']['project_address'] = self.project_address(result['stop_reason']['address'])
        self._event('run',evidence)
        return evidence

    def project_address(self, address):
        if address.get('space') != 'segmented':
            return None
        runtime = int(address['segment'],16)*16+int(address['offset'],16)
        return hex(runtime-self.delta) if self.runtime_base <= runtime < self.runtime_base+self.module_size else None

    def registers(self):
        result = self.call('state.get_registers')
        result['project_address'] = self.project_address({'space':'segmented',
            'segment':result['segments']['cs'],'offset':result['instruction_pointer']})
        return result

    def breakpoint(self, address, *, cs=None):
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

    def delete_breakpoint(self, breakpoint_id):
        result = self.call('breakpoints.delete',{'breakpoint_id':breakpoint_id})
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

    def _artifact(self, name, kind, data, metadata):
        name = _file_name(name)
        if len(data) > 16*1024*1024:
            raise ValueError('Runtime artifact exceeds 16 MiB')
        identifier = uuid.uuid4().hex
        digest = hashlib.sha256(data).hexdigest()
        with self.project.transaction(True):
            used = self.project.db.execute('SELECT coalesce(sum(length(data)),0) FROM debug_artifacts').fetchone()[0]
            if used+len(data) > 256*1024*1024:
                raise ValueError('Project runtime artifact budget exceeds 256 MiB')
            self.project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
                (identifier,self.run_id,name,kind,digest,data,json.dumps(metadata)))
        result = dict(artifact=identifier,run=self.run_id,version=self.version['id'],name=name,kind=kind,
                      sha256=digest,size=len(data),metadata=metadata)
        self._event('artifact',result)
        return result

    def screenshot(self, name='screenshot.png'):
        result = self.call('video.screenshot')
        data = base64.b64decode(result.pop('png_base64'),validate=True)
        if not data.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(data).hexdigest()!=result['sha256']:
            raise DebuggerError('Screenshot signature/hash mismatch')
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            if image.size != (result['width'],result['height']):
                raise DebuggerError('Screenshot dimensions differ from metadata')
            image.verify()
        return self._artifact(name,'screenshot',data,result)

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
                   'debug-run':'run','debug-click':'click','debug-screenshot':'screenshot','debug-trace':'trace'}
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
