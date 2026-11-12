"""Source-bound Gob VM debugging through an explicitly patched ScummVM.

Execution coordinates are complete TOT-file offsets, including the header.
ScummVM is a replacement interpreter; this module never exposes DOS CPU state.
This profile is limited to Lost in Time's lit/lit1/lit2 Inter_v3 family.
The copied display/input/lifecycle helpers have no AGI state or resource logic.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import threading
import time
import uuid

from .debugger import DebugSession, bounded, stamp
from .external_files import _file_name
from .keyboard_input import validate_keyboard
from .operation_budget import rpc_budget
from .scummvm_debugger import _control_operation, _digest, _manifest
from .scummvm_rpc import ScummVMError, ScummVMRPC


def _fnv1a64(data):
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return f'{value:016x}'


def _unpack_member(data, compression):
    """Bounded Gob STK LZSS decoder, matching engines/gob/dataio.cpp.

    Reject truncated streams and ambiguous uninitialized dictionary reads.
    This supports the single-chunk compression used by the qualified target;
    compression-2 Geisha resources are deliberately outside this profile.
    """
    if compression == 0:
        return data
    if compression != 1 or len(data) < 4:
        raise ValueError('Unsupported or truncated Gob archive compression')
    size = int.from_bytes(data[:4], 'little')
    if not 1 <= size <= 16 * 1024 * 1024:
        raise ValueError('Gob decompressed member exceeds 16 MiB')
    dictionary = [32] * 4078 + [None] * 18
    output, cursor, ring, command = bytearray(), 4, 4078, 0
    def byte():
        nonlocal cursor
        if cursor >= len(data):
            raise ValueError('Truncated Gob compressed member')
        result = data[cursor]
        cursor += 1
        return result
    while len(output) < size:
        command >>= 1
        if not command & 0x100:
            command = byte() | 0xff00
        if command & 1:
            values = [byte()]
            for value in values:
                output.append(value)
                dictionary[ring] = value
                ring = (ring + 1) % 4096
        else:
            first, second = byte(), byte()
            offset, length = first | ((second & 0xf0) << 4), (second & 15) + 3
            for index in range(length):
                value = dictionary[(offset + index) % 4096]
                if value is None:
                    raise ValueError('Gob compressed member reads uninitialized dictionary bytes')
                output.append(value)
                if len(output) == size:
                    break
                dictionary[ring] = value
                ring = (ring + 1) % 4096
    return bytes(output)


def _script_end(payload):
    """Loaded code prefix, from the full TOT header's text/resource offsets."""
    if len(payload) < 128:
        raise ValueError('Gob TOT source is shorter than its 128-byte header')
    boundaries = [len(payload)]
    for offset in (48, 52):
        value = int.from_bytes(payload[offset:offset+4], 'little')
        if value not in (0, 0xffffffff):
            boundaries.append(value)
    end = min(boundaries)
    if end < 128:
        raise ValueError('Gob TOT source code prefix ends inside its header')
    return end


class ScummVMGobSession(DebugSession):
    """One owned Gob Inter_v3 process and persisted, immutable observations."""

    native_hooks_available = False

    @property
    def script_operations(self):
        return {'assert','status','run','trace','screenshot','frame-probe','scene-check',
                'scene-assert','scene-click','scene-act','scene-wait','keyboard.press',
                'keyboard.type','keyboard.state','keyboard.key-down','keyboard.key-up',
                'click','click-frame','breakpoint','delete-breakpoint','engine-state',
                'engine-set','engine-read-variable','engine-write-variable','engine-hotspot-events','step',
                'watchpoint','delete-watchpoint','engine-resource'}

    def __init__(self, project, executable, game_dir, *, game_id='lit', language=None,
                 platform=None, version=None, boot_timeout_ms=240000, window=False,
                 _on_spawn=None):
        if window:
            raise ValueError('ScummVM Gob agent currently requires headless mode')
        self.project = project
        self._project_owner_thread = threading.get_ident()
        self.version = project.version(version)
        if self.version['parent'] is not None:
            raise ValueError('ScummVM launch requires original project version 1; patched versions remain separate')
        self.game_dir = Path(game_dir).expanduser().resolve(strict=True)
        if not self.game_dir.is_dir():
            raise ValueError('Expected a Gob game directory')
        if self.game_dir == project.path.parent or self.game_dir in project.path.parents:
            raise ValueError('Keep mutable project/runtime outside the read-only Gob game directory')
        owner = self.game_dir / project.meta['filename']
        if owner.is_symlink() or not owner.is_file() or owner.resolve().parent != self.game_dir:
            raise ValueError('Project source must be an original file directly in the game directory')
        source_sha256 = hashlib.sha256(owner.read_bytes()).hexdigest()
        if source_sha256 != project.meta['source_sha256']:
            raise ValueError('Game source does not match retained project source')
        self.manifest = _manifest(self.game_dir)
        self.manifest_sha256 = _digest(self.manifest)
        self.run_id, self.closed, self._guest_exited = uuid.uuid4().hex, False, False
        self._run_condition, self._run_lock = threading.Condition(), threading.Lock()
        self._control_lock = threading.RLock()
        self._run_active = self._run_sent = False
        self._run_stop = self._run_error = None
        self._state_revision, self._last_frame = 0, None
        self._breakpoints, self._watches, self._resource_layers = {}, {}, {}
        self._source_cache = {}
        self._queued_keyboard, self._keyboard_leases = 0, {}
        self._launch_alias, self.rpc = None, None
        executable = Path(executable).expanduser().resolve(strict=True)
        self.metadata = {
            'backend':'scummvm-gob','execution_context':'gob-vm',
            'replacement_engine':True,'original_x86_executed':False,'game_id':game_id,
            'native_hooks_available':self.native_hooks_available,
            'language_requested':language,'platform_requested':platform,
            'source_sha256':source_sha256,'version_sha256':self.version['sha256'],
            'resource_manifest_sha256':self.manifest_sha256,'resource_manifest':self.manifest,
            'resource_layers_sha256':'0' * 64,'resource_count':len(self.manifest),
            'executable':str(executable),'scummvm_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
            'game_dir':str(self.game_dir),'runtime_profile':'gob-inter-v3',
            'fdisbull_version':__import__('fdisbull').__version__,
            'state_scope':'No Gob native save or exact VM checkpoint contract is qualified',
            'watch_scope':'overlapping scalar accessor reads/writes; pointer and unhooked bulk writes excluded'}
        try:
            self.rpc = ScummVMRPC(executable,self.game_dir,game_id=game_id,engine='gob',
                language=language,platform=platform,runtime_parent=project.path.parent,
                boot_timeout_ms=boot_timeout_ms,on_spawn=_on_spawn)
            self.metadata.update(game_id=self.rpc.game_id,backend_hello=self.rpc.hello,
                                 detected_variant=self.rpc.hello['variant'],pid=self.rpc.process.pid)
            required = {'state','frame','run','step','memory.read','script.read'}
            missing = required - set(self.rpc.capabilities['features'])
            if missing:
                raise ScummVMError('Gob backend lacks required capabilities: ' + ', '.join(sorted(missing)))
            initial = self._read_state()
            self.metadata['initial_position'] = self._position(initial)
            binding = self._script_binding(initial)
            self.metadata['initial_script_source'] = {key:value for key,value in binding.items()
                                                      if key != '_bytes'}
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id,self.version['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            self._event('launch',{'state':'stopped','position':self._position(initial),
                'backend':'scummvm-gob','resource_manifest_sha256':self.manifest_sha256})
            project._live_debuggers.append(self)
        except BaseException:
            if self.rpc is not None:
                self.rpc.close()
            raise

    def _call(self, op, params=None, *, timeout_ms=15000, on_sent=None):
        from .operation_budget import RpcAdmissionTimeout
        if self.closed or self.rpc is None:
            raise ScummVMError('ScummVM session is closed')
        if self._run_active and op not in ('run','step'):
            raise ScummVMError('Gob execution is active; pause and confirm its stop first')
        deadline = getattr(self,'_rpc_deadline',None)
        if deadline is not None:
            remaining = int((deadline-time.monotonic())*1000)
            if remaining <= 0 or remaining < (getattr(self,'_rpc_admission_ms',None) or 0):
                raise RpcAdmissionTimeout('Shared debugger host-time budget expired before Gob RPC dispatch')
            timeout_ms = min(timeout_ms,getattr(self,'_rpc_timeout_cap_ms',None) or 15000,remaining)
        options = {'timeout_ms':timeout_ms}
        if on_sent is not None:
            options['on_sent'] = on_sent
        return self.rpc.call(op,params,**options)

    def _verify_manifest(self):
        try:
            unchanged = _manifest(self.game_dir) == self.manifest
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            self.close()
            raise ScummVMError('Original Gob game resources changed during this ScummVM run')

    def _invalid_reply(self, message):
        # A malformed successful reply is protocol corruption, not a normal
        # engine refusal. Reap the owner before another mutation is possible.
        if self.rpc is not None:
            self.rpc.close()
        raise ScummVMError(message)

    @staticmethod
    def _assert_no_layer_conflict(state):
        if state.get('layer_conflict'):
            raise ScummVMError('Gob source generation conflict requires a fresh session')

    def _refresh_resource_layers(self, state=None):
        # Loaded-resource mutation is unsupported; never invent an AGI layer.
        return None

    def _layer_digest(self):
        return '0' * 64

    def _require_paused(self):
        if self._run_active:
            raise ScummVMError('Gob execution is active; pause and confirm its stop first')

    def _read_state(self):
        state = self._call('state.get').get('state')
        if not isinstance(state,dict):
            self._invalid_reply('Gob backend omitted VM state')
        script, arena = state.get('script'), state.get('variables')
        if (state.get('engine') != 'gob' or not isinstance(script,dict)
                or not isinstance(script.get('name'),str) or not script['name']
                or type(script.get('generation')) is not int or script['generation'] < 1
                or type(script.get('size')) is not int or not 1 <= script['size'] <= 16*1024*1024
                or script.get('offset_origin') != 'tot_file_start'
                or script.get('raw_header_included') is not True
                or type(state.get('offset')) is not int or not 0 <= state['offset'] <= script['size']
                or not isinstance(arena,dict) or arena.get('arena') != 'variables'
                or arena.get('endian') != 'little' or type(arena.get('size')) is not int
                or not 0 <= arena['size'] <= 16*1024*1024
                or state.get('phase') not in ('before_opcode','backend_yield','after_opcode')
                or not isinstance(state.get('hotspots'),list)):
            self._invalid_reply('Gob backend returned invalid typed VM state')
        return state

    @staticmethod
    def _position(state):
        script = state['script']
        return {'space':'gob-vm','script':script['name'],'generation':script['generation'],
                'offset':state['offset'],'offset_origin':'tot_file_start',
                'phase':state.get('phase'),'family':state.get('family'),
                'loaded_fnv1a64':script.get('fnv1a64')}

    def contexts(self):
        return {'run':self.run_id,'selected':'gob-vm','contexts':[{'id':'gob-vm',
                'kind':'bytecode-vm','trace_phase':'explicit opcode start/completion events',
                'source_address':'TOT identity + loaded generation + full TOT-file byte offset'}]}

    def context(self, name):
        if name != 'gob-vm':
            raise ValueError('ScummVM Gob exposes only the gob-vm context')
        return self

    def engine_state(self):
        self._verify_manifest()
        state = self._read_state()
        binding = self._script_binding(state)
        return {**state,'run':self.run_id,'backend':'scummvm-gob',
                'current_script':state['script'],'position':self._position(state),
                'variant':self.metadata['detected_variant'],
                'script_source':{key:value for key,value in binding.items() if key != '_bytes'},
                'state_revision':self._state_revision,'resource_manifest_sha256':self.manifest_sha256,
                'resource_layers_sha256':self._layer_digest(),
                'readiness':{'phase':state['phase'],'handler_completion_verified':False},
                'state_origin':'ScummVM replacement Gob engine; not original DOS CPU',
                'watch_scope':self.metadata['watch_scope']}

    def status(self):
        if self._run_active:
            return {'run':self.run_id,'version':self.version['id'],'live':not self.closed,
                    'state':'running','backend':'scummvm-gob','mapping':self.metadata,
                    'native_hooks_available':self.native_hooks_available,
                    'position':None,'position_scope':'pending native stop'}
        if self._guest_exited:
            return {'run':self.run_id,'version':self.version['id'],'live':not self.closed,
                    'state':'exited','backend':'scummvm-gob','mapping':self.metadata,
                    'native_hooks_available':self.native_hooks_available}
        state = self.engine_state()
        return {'run':self.run_id,'version':self.version['id'],'live':not self.closed,
                'state':'stopped','backend':'scummvm-gob','position':state['position'],
                'native_hooks_available':self.native_hooks_available,
                'guest_ms':state.get('guest_ms'),'readiness':state['readiness'],
                'state_revision':self._state_revision,'mapping':self.metadata,
                'capabilities':self.rpc.capabilities,'resource_layers_sha256':self._layer_digest()}

    def hotspot_events(self):
        """Return capped native dispatch evidence, separate from queued clicks."""
        self._verify_manifest()
        if 'hotspots.events' not in self.rpc.capabilities['features']:
            raise ValueError('Gob backend does not expose hotspot dispatch evidence')
        reply = self._call('hotspots.events')
        if (not isinstance(reply.get('entries'),list) or len(reply['entries']) > 2048
                or type(reply.get('dispatches')) is not int or reply['dispatches'] < 0
                or type(reply.get('truncated')) is not bool):
            self._invalid_reply('Gob backend returned invalid hotspot dispatch evidence')
        result = {'run':self.run_id,'backend':'scummvm-gob',**reply,
                  'state_revision':self._state_revision,
                  'scope':'native hotspot handler dispatch; action completion remains separately observed'}
        self._event('hotspot-events',result)
        return result

    @staticmethod
    def _typed(width, signed, endian):
        if type(width) is not int or width not in (1,2,4) or type(signed) is not bool or endian != 'little':
            raise ValueError('Gob variables require width 1, 2 or 4, boolean signed, and little endian')

    def _read_memory(self, offset, length, *, width=1, signed=False, state=None):
        bounded(offset,'offset',0,16*1024*1024)
        bounded(length,'length',1,4096)
        self._typed(width,signed,'little')
        state = state or self._read_state()
        if offset+length > state['variables']['size']:
            raise ValueError('Gob variable range lies outside allocated arena')
        reply = self._call('memory.read',{'offset':offset,'length':length,'width':width,'signed':signed})
        if (reply.get('arena') != 'variables' or reply.get('endian') != 'little'
                or reply.get('size') != state['variables']['size']):
            self._invalid_reply('Gob backend returned an inconsistent variable arena identity')
        try:
            data = bytes.fromhex(reply['hex'])
        except (KeyError,TypeError,ValueError) as error:
            self._invalid_reply('Gob backend returned malformed variable bytes')
        if len(data) != length:
            self._invalid_reply('Gob backend returned incomplete variable bytes')
        return data

    def read_variable(self, offset, *, width=1, signed=False, endian='little'):
        self._verify_manifest()
        self._typed(width,signed,endian)
        state = self._read_state()
        data = self._read_memory(offset,width,width=width,signed=signed,state=state)
        return {'run':self.run_id,'backend':'scummvm-gob','arena':'variables','offset':offset,
                'width':width,'signed':signed,'endian':endian,'hex':data.hex(),
                'value':int.from_bytes(data,endian,signed=signed),'state_revision':self._state_revision,
                'arena_size':state['variables']['size'],'position':self._position(state),
                'resource_manifest_sha256':self.manifest_sha256}

    def write_variable(self, offset, value, *, width=1, signed=False, endian='little', expected=None):
        if not self._run_lock.acquire(blocking=False):
            raise ScummVMError('Gob execution is active; pause and confirm its stop before mutation')
        try:
            return self._write_variable_paused(offset,value,width=width,signed=signed,
                                               endian=endian,expected=expected)
        finally:
            self._run_lock.release()

    def _write_variable_paused(self, offset, value, *, width=1, signed=False,
                               endian='little', expected=None):
        self._verify_manifest()
        self._typed(width,signed,endian)
        low, high = (-(1 << (width*8-1)),(1 << (width*8-1))-1) if signed else (0,(1 << (width*8))-1)
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Gob value lies outside the declared integer width/signedness')
        if expected is not None and (type(expected) is not int or not low <= expected <= high):
            raise ValueError('Gob expected value lies outside the declared integer width/signedness')
        before = self.read_variable(offset,width=width,signed=signed,endian=endian)
        if expected is not None and before['value'] != expected:
            raise ValueError('Gob variable precondition differs from expected value')
        if 'memory.write' not in self.rpc.capabilities['features']:
            raise ValueError('Gob backend does not support guarded variable writes')
        script = self._read_state()['script']
        reply = self._call('memory.write',{'offset':offset,'expected_hex':before['hex'],
            'data_hex':value.to_bytes(width,endian,signed=signed).hex(),
            'script':script['name'],'generation':script['generation']})
        self._state_revision += 1
        after = self.read_variable(offset,width=width,signed=signed,endian=endian)
        if after['value'] != value:
            self.close()
            raise ScummVMError('Gob variable write was not confirmed')
        result = {**after,'before':before['value'],'after':after['value'],'native_result':reply,
                  'assisted_state':True,'reachability_verified':False}
        self._event('write-engine-state',result)
        return result

    def write_engine_state(self, kind, index, value, *, expected=None, width=None,
                           signed=None, endian='little'):
        kinds = {'u8':(1,False),'i8':(1,True),'u16':(2,False),'i16':(2,True),
                 'u32':(4,False),'i32':(4,True),'variable':(1,False)}
        if kind not in kinds:
            raise ValueError('Gob state kind must be u8/i8/u16/i16/u32/i32/variable; index is byte offset')
        selected_width, selected_signed = kinds[kind]
        if width is not None:
            selected_width = width
        if signed is not None:
            selected_signed = signed
        return self.write_variable(index,value,width=selected_width,signed=selected_signed,
                                   endian=endian,expected=expected)

    engine_set = write_engine_state

    def run(self, *, max_instructions=1000000, timeout_ms=10000, guest_ms=None,
            fast_forward=False, stop_on_hook=False, until_cycle=False):
        if until_cycle:
            raise ValueError('Gob has no qualified AGI cycle/checkpoint boundary')
        if not self._run_lock.acquire(blocking=False):
            raise ScummVMError('Another Gob execution is active')
        try:
            return self._run_budgeted(max_instructions=max_instructions,timeout_ms=timeout_ms,
                guest_ms=guest_ms,fast_forward=fast_forward,stop_on_hook=stop_on_hook)
        finally:
            self._run_lock.release()

    @rpc_budget
    def _run_budgeted(self, *, max_instructions=1000000, timeout_ms=10000, guest_ms=None,
                      fast_forward=False, stop_on_hook=False):
        self._verify_manifest()
        bounded(max_instructions,'max_instructions',1,1000000)
        bounded(timeout_ms,'timeout_ms',1,600000)
        if type(fast_forward) is not bool or type(stop_on_hook) is not bool:
            raise ValueError('fast_forward and stop_on_hook must be boolean')
        if stop_on_hook:
            raise ValueError('Gob native DOS hooks are unavailable')
        if guest_ms is not None:
            bounded(guest_ms,'guest_ms',1,3600000)
            if not self.rpc.capabilities.get('virtual_time'):
                raise ValueError('Gob backend does not qualify virtual guest-time runs')
        before, started = self._read_state(), time.monotonic()
        self._script_binding(before)
        remaining = min(int((self._rpc_deadline-time.monotonic())*1000),
                        getattr(self,'_rpc_timeout_cap_ms',None) or timeout_ms)
        if remaining < 100:
            raise TimeoutError('Gob run host budget expired before dispatch')
        params = {'max_instructions':max_instructions,'max_ms':max(1,remaining-min(500,max(50,remaining//10)))}
        if guest_ms is not None:
            params['max_guest_ms'] = guest_ms
        with self._native_execution():
            reply = self._call('run',params,timeout_ms=remaining,on_sent=self._mark_run_sent)
            stop = self._validate_stop(reply)
            with self._run_condition:
                self._run_stop = stop
        self._state_revision += 1
        self._queued_keyboard = 0
        self._guest_exited = stop['reason'] == 'quit'
        after = None if self._guest_exited else self._read_state()
        if after is not None:
            self._script_binding(after)
        elapsed = None
        if after is not None and type(before.get('guest_ms')) is int and type(after.get('guest_ms')) is int:
            elapsed = after['guest_ms']-before['guest_ms']
            if elapsed < 0:
                self.close()
                raise ScummVMError('Gob virtual clock moved backwards')
        if guest_ms is not None and elapsed is None:
            self.close()
            raise ScummVMError('Gob guest-time request omitted qualified elapsed time')
        self._verify_manifest()
        outcome = {'guest_budget':'guest_time','host_timeout':'timeout','quit':'exited'}.get(stop['reason'],stop['reason'])
        result = {'run':self.run_id,'backend':'scummvm-gob','outcome':outcome,
                  'stop':{'context':'gob-vm','trigger':outcome,
                          'position':self._position(after) if after else None,'instruction_completed':None},
                  'native_stop':stop,'executed':stop.get('instructions'),'guest_elapsed_ms':elapsed,
                  'host_elapsed_ms':round((time.monotonic()-started)*1000,3),
                  'requested_guest_ms':guest_ms,'requested_instructions':max_instructions,
                  'fast_forward_requested':fast_forward,'hook_hits':[],'native_hooks_available':False,
                  'state_revision':self._state_revision,'state':'exited' if self._guest_exited else 'stopped'}
        self._event('run',result)
        return result

    def _validate_stop(self, reply):
        stop = reply.get('stop')
        if (not isinstance(stop,dict) or not isinstance(stop.get('reason'),str)
                or type(stop.get('instructions')) is not int or stop['instructions'] < 0):
            self.close()
            raise ScummVMError('Gob execution ended without a structured stop')
        return stop

    def resume(self, **kwargs):
        return self.run(**kwargs)

    def run_until_cycle(self, **kwargs):
        raise ValueError('Gob has no qualified AGI cycle/checkpoint boundary')

    def step(self, count=1, *, timeout_ms=10000):
        if not self._run_lock.acquire(blocking=False):
            raise ScummVMError('Another Gob execution is active')
        try:
            return self._step_budgeted(count=count,timeout_ms=timeout_ms)
        finally:
            self._run_lock.release()

    @rpc_budget
    def _step_budgeted(self, count=1, *, timeout_ms=10000):
        self._verify_manifest()
        bounded(count,'count',1,10000)
        records = []
        for _ in range(count):
            remaining = min(int((self._rpc_deadline-time.monotonic())*1000),
                            getattr(self,'_rpc_timeout_cap_ms',None) or timeout_ms)
            if remaining < 100:
                break
            before = self._read_state()
            self._script_binding(before)
            with self._native_execution():
                stop = self._validate_stop(self._call('step',{'max_ms':max(1,remaining-min(500,max(50,remaining//10)))},
                    timeout_ms=remaining,on_sent=self._mark_run_sent))
                with self._run_condition:
                    self._run_stop = stop
            self._state_revision += 1
            self._queued_keyboard = 0
            if stop['reason'] != 'quit':
                self._script_binding(self._read_state())
            records.append({'before':self._position(before),'stop':stop,
                'completed_opcode_count':stop['instructions'],
                'before_position_instruction_completed':None})
            if stop['reason'] not in ('step','budget'):
                self._guest_exited = stop['reason'] == 'quit'
                break
        self._verify_manifest()
        result = {'run':self.run_id,'backend':'scummvm-gob','steps':records,
                  'completed':len(records) == count and all(r['stop']['reason'] in ('step','budget')
                    and r['completed_opcode_count'] == 1 for r in records),
                  'state_revision':self._state_revision}
        self._event('step',result)
        return result

    def _source_candidates(self, name):
        """Read-only archive identity candidates; native lookup picks precedence."""
        result = []
        wanted = name.replace('\\','/').rsplit('/',1)[-1].casefold()
        for record in self.manifest:
            path = self.game_dir / record['path']
            if path.name.casefold() == wanted:
                data = path.read_bytes()
                result.append((data,{'container':record['path'],'container_sha256':record['sha256'],
                    'member':None,'member_file_offset':0,'packed_size':len(data),'compression':0,
                    'packed_sha256':hashlib.sha256(data).hexdigest(),'packed_fnv1a64':_fnv1a64(data)}))
            elif path.suffix.casefold() in ('.stk','.itk'):
                raw = path.read_bytes()
                if len(raw) < 2:
                    continue
                count = int.from_bytes(raw[:2],'little')
                if count > 10000 or 2+count*22 > len(raw):
                    continue
                for index in range(count):
                    at = 2+index*22
                    entry = raw[at:at+22]
                    member = entry[:13].split(b'\0',1)[0].decode('latin1')
                    if member.casefold() != wanted:
                        continue
                    size, offset = int.from_bytes(entry[13:17],'little'),int.from_bytes(entry[17:21],'little')
                    if offset+size > len(raw):
                        raise ValueError('Gob archive member span exceeds source container')
                    packed, compression = raw[offset:offset+size],int(bool(entry[21]))
                    data = _unpack_member(packed,compression)
                    result.append((data,{'container':record['path'],'container_sha256':record['sha256'],
                        'member':member,'member_file_offset':offset,'packed_size':size,'compression':compression,
                        'packed_sha256':hashlib.sha256(packed).hexdigest(),'packed_fnv1a64':_fnv1a64(packed)}))
        return result

    def _script_binding(self, state=None):
        state = state or self._read_state()
        script = state['script']
        key = (script['name'],script['generation'],script.get('fnv1a64'))
        if key in self._source_cache:
            return self._source_cache[key]
        data = bytearray()
        for offset in range(0,script['size'],4096):
            length = min(4096,script['size']-offset)
            reply = self._call('script.read',{'script':script['name'],'generation':script['generation'],
                                             'offset':offset,'length':length})
            try:
                part = bytes.fromhex(reply['current_hex'])
            except (KeyError,ValueError,TypeError) as error:
                self._invalid_reply('Gob script.read returned malformed bytes')
            if len(part) != length or reply.get('generation',script['generation']) != script['generation']:
                self._invalid_reply('Gob loaded script changed during paused source verification')
            data.extend(part)
        if script.get('fnv1a64') is not None and _fnv1a64(data) != script['fnv1a64']:
            self._invalid_reply('Gob loaded script digest disagrees with observed bytes')
        candidates = [(payload,source) for payload,source in self._source_candidates(script['name'])
                      if _script_end(payload) == len(data) and payload[:len(data)] == data]
        native_source = script.get('source')
        if isinstance(native_source,dict) and native_source.get('container'):
            candidates = [(payload,source) for payload,source in candidates
                          if source['container'].casefold() == native_source['container'].casefold()]
            for native_key, source_key in (('offset','member_file_offset'),('size','packed_size'),
                    ('compression','compression'),('raw_fnv1a64','packed_fnv1a64')):
                if native_key in native_source:
                    candidates = [(payload,source) for payload,source in candidates
                                  if source[source_key] == native_source[native_key]]
            if native_source.get('kind') == 'archive' and native_source.get('member'):
                candidates = [(payload,source) for payload,source in candidates
                              if source['member'] is not None and
                              source['member'].casefold() == native_source['member'].casefold()]
        if len(candidates) != 1:
            self._invalid_reply('Gob loaded script original source is absent or ambiguous; source-bound execution refused')
        payload, source = candidates[0]
        binding = {**source,'script':script['name'],'generation':script['generation'],
                   'decompressed_size':len(payload),'decompressed_sha256':hashlib.sha256(payload).hexdigest(),
                   'loaded_size':len(data),'loaded_source_offset':0,
                   'loaded_span_origin':'TOT code prefix before text/resource tables',
                   'loaded_sha256':hashlib.sha256(data).hexdigest(),'loaded_fnv1a64':_fnv1a64(data),
                   'offset_origin':'tot_file_start','raw_header_included':True,'bytes_verified':True,
                   'lookup_precedence_verified':isinstance(native_source,dict),
                   'resource_manifest_sha256':self.manifest_sha256,'_bytes':bytes(data)}
        self._source_cache[key] = binding
        return binding

    def resource(self, script=None, offset=0, length=16, *, generation=None):
        self._verify_manifest()
        bounded(offset,'offset',0,16*1024*1024)
        bounded(length,'length',0,4096)
        state = self._read_state()
        if script is not None and str(script).casefold() != state['script']['name'].casefold():
            raise ValueError('Gob resources expose only the current loaded script')
        if generation is not None and generation != state['script']['generation']:
            raise ValueError('Gob loaded script generation differs from requested source')
        binding = self._script_binding(state)
        data = binding['_bytes']
        if offset+length > len(data):
            raise ValueError('Gob resource range lies outside loaded script')
        self._verify_manifest()
        return {'run':self.run_id,'backend':'scummvm-gob','script':state['script']['name'],
                'generation':state['script']['generation'],'offset':offset,'length':length,'size':len(data),
                'current_hex':data[offset:offset+length].hex(),'original_hex':data[offset:offset+length].hex(),
                'source':{k:v for k,v in binding.items() if k != '_bytes'},'scope':'verified_original_loaded_tot'}

    def resource_info(self, kind, number=None):
        if kind not in ('script','tot'):
            raise ValueError('Gob resource kind must be script or tot')
        return self.resource(number,0,0)

    def code(self, address, *, cs=None, length=16):
        if (cs is not None or not isinstance(address,dict) or
                not {'script','generation','offset'} <= set(address) or
                set(address)-{'script','generation','offset','family'}):
            raise ValueError('Gob code address must include script, generation and offset')
        bounded(length,'length',1,4096)
        record = self.resource(address['script'],address['offset'],length,generation=address['generation'])
        return {**record,'address':{'space':'gob-vm',**address,'offset_origin':'tot_file_start'},
                'hex':record['current_hex'],'decoded':False,'execution_bytes_verified':True}

    @_control_operation
    def breakpoint(self, address, *, cs=None, access='x', length=1, view='static'):
        if cs is not None or access != 'x' or length != 1 or view not in ('static','execute'):
            raise ValueError('Gob breakpoint addresses one VM opcode; CPU options do not apply')
        record = self.code(address,length=1)
        params = {**address,'expected_hex':record['hex']}
        self._call('break.add',params)
        # expected_hex is a fresh source guard, not native control identity.
        # An omitted/empty family selects the same native wildcard control.
        def identity(point):
            family = point.get('family')
            return (point['script'], point['generation'], point['offset'],
                    family if isinstance(family, str) else '')
        identifier = next((key for key, point in self._breakpoints.items()
                           if identity(point) == identity(params)), None)
        if identifier is None:
            identifier = uuid.uuid4().hex
            self._breakpoints[identifier] = params
        result = {'run':self.run_id,'backend':'scummvm-gob','breakpoint_id':identifier,
                  'address':{'space':'gob-vm',**address},'bytes_verified':True,'source':record['source']}
        self._event('breakpoint',result)
        return result

    @_control_operation
    def watchpoint(self, kind, index, *, access='w', length=None):
        widths = {'variable':1,'u8':1,'i8':1,'u16':2,'i16':2,'u32':4,'i32':4}
        if kind not in widths or access not in ('r','w','rw'):
            raise ValueError('Gob watchpoint requires typed variable byte offset and access r/w/rw')
        length = widths[kind] if length is None else bounded(length,'length',1,4096)
        self._read_memory(index,length)
        params = {'offset':index,'length':length,'access':access}
        self._call('watch.add',params)
        identifier = next((key for key, point in self._watches.items()
                           if point == params), None)
        if identifier is None:
            identifier = uuid.uuid4().hex
            self._watches[identifier] = params
        result = {'run':self.run_id,'backend':'scummvm-gob','watchpoint_id':identifier,
                  'kind':kind,'index':index,**params,'stop_scope':self.metadata['watch_scope'],
                  'all_writes_covered':False}
        self._event('watchpoint',result)
        return result

    @_control_operation
    def delete_breakpoint(self, breakpoint_id):
        if breakpoint_id in self._breakpoints:
            self._call('break.remove',self._breakpoints[breakpoint_id])
            del self._breakpoints[breakpoint_id]
            kind = 'breakpoint'
        elif breakpoint_id in self._watches:
            self._call('watch.remove',self._watches[breakpoint_id])
            del self._watches[breakpoint_id]
            kind = 'watchpoint'
        else:
            raise ValueError('Unknown Gob breakpoint/watchpoint ID')
        result = {'run':self.run_id,'backend':'scummvm-gob','deleted':breakpoint_id,'kind':kind}
        self._event('delete-breakpoint',result)
        return result

    def delete_watchpoint(self, watchpoint_id):
        return self.delete_breakpoint(watchpoint_id)

    @rpc_budget
    def trace(self, name='trace.json', *, count=512, timeout_ms=10000, fast_forward=False):
        self._verify_manifest()
        _file_name(name)
        bounded(count,'count',1,2048)
        if 'trace.start' not in self.rpc.capabilities['features']:
            raise ValueError('Gob backend does not expose capped opcode tracing')
        binding = self._script_binding()
        self._call('trace.clear')
        self._call('trace.start')
        try:
            stop = self.run(max_instructions=count,timeout_ms=timeout_ms,fast_forward=fast_forward)
        finally:
            self._call('trace.stop')
        native = self._call('trace.get')
        events = native.get('entries')
        if not isinstance(events,list) or len(events) > 2048:
            raise ScummVMError('Gob backend returned invalid capped trace')
        verified_events = []
        for event in events:
            if not isinstance(event,dict) or type(event.get('offset')) is not int:
                raise ScummVMError('Gob backend returned malformed trace event')
            source = {'scope':'unmapped_script_generation','bytes_verified':False}
            if (event.get('script') == binding['script'] and event.get('generation') == binding['generation']
                    and 0 <= event['offset'] < len(binding['_bytes'])):
                source = {k:v for k,v in binding.items() if k != '_bytes'}
                source['original_hex'] = f"{binding['_bytes'][event['offset']]:02x}"
            verified_events.append({**event,'original_source':source})
        report = {'run':self.run_id,'backend':'scummvm-gob','events':verified_events,
                  'requested_count':count,'stop':stop,'truncated':native.get('truncated') is True,
                  'complete':native.get('truncated') is False and stop.get('executed') == count,
                  'resource_manifest_sha256':self.manifest_sha256,
                  'observation_contract':'Explicit native opcode start/completion events; nested caller completion is not inferred'}
        return self._artifact(name,'trace',json.dumps(report,indent=2).encode(),
            {'backend':'scummvm-gob','event_count':len(events),'complete':report['complete'],
             'resource_manifest_sha256':self.manifest_sha256})

    def registers(self):
        raise ValueError('ScummVM Gob exposes engine_state, not original x86 registers')

    def memory(self, address, *, cs=None, length=16):
        self._verify_manifest()
        if cs is not None:
            raise ValueError('Gob variable arena has no DOS segment address')
        if isinstance(address,dict) and set(address) == {'offset'}:
            address = address['offset']
        data = self._read_memory(address,length)
        return {'run':self.run_id,'backend':'scummvm-gob','arena':'variables',
                'offset':address,'length':length,'hex':data.hex(),'original_dos_memory':False}

    def save_state(self, name='state.sav'):
        raise ValueError('Gob native saves and exact VM checkpoints are not qualified; script-mediated game saves require separate orchestration')

    def load_state(self, artifact):
        raise ValueError('Gob native load/checkpoint restoration is not qualified')

    def patch_resource(self, *args, **kwargs):
        raise ValueError('Gob loaded-resource patching is unsupported; original and loaded script bytes remain immutable')

    def restore_resource(self, *args, **kwargs):
        raise ValueError('Gob loaded-resource patching/restoration is unsupported')

    def _event(self, operation, evidence):
        if threading.get_ident() == self._project_owner_thread:
            return super()._event(operation, evidence)
        # Project's SQLite connection is owner-thread-bound. A concurrent
        # controller thread records its own event through the same file/store
        # contract without sharing that connection across threads.
        from .target_storage import STORAGE, connect
        db = connect(self.project.path, external=self.project.meta.get('storage') == STORAGE,
                     store=getattr(self.project.db, 'store', None))
        try:
            db.execute('BEGIN IMMEDIATE')
            payload = json.dumps(evidence)
            if hasattr(db, 'store'):
                payload = db.store.put(payload)
            db.execute('INSERT INTO debug_events(run,created,operation,evidence) VALUES (?,?,?,?)',
                       (self.run_id, stamp(), operation, payload))
            state = evidence.get('state') or evidence.get('session', {}).get('state')
            if state:
                db.execute('UPDATE debug_runs SET state=? WHERE id=?', (state, self.run_id))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


    def _mark_run_sent(self):
        with self._run_condition:
            self._run_sent = True
            self._run_condition.notify_all()


    @contextmanager
    def _native_execution(self):
        with self._run_condition:
            if self._run_active:
                raise ScummVMError('An Gob run or step is already active')
            self._run_active = True
            self._run_sent = False
            self._run_stop = None
            self._run_error = None
        try:
            yield
        except BaseException as error:
            with self._run_condition:
                self._run_error = str(error)
            raise
        finally:
            with self._run_condition:
                self._run_active = False
                self._run_condition.notify_all()


    def pause(self, *, timeout_ms=5000):
        """Request an in-flight Gob run to stop, with explicit ack-only scope."""
        bounded(timeout_ms, 'timeout_ms', 1, 600000)
        deadline = time.monotonic() + timeout_ms / 1000
        with self._run_condition:
            while self._run_active and not self._run_sent:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    break
                self._run_condition.wait(remaining_seconds)
            active = self._run_active
            sent = self._run_sent
            stop = self._run_stop
            error = self._run_error
        if not active:
            if error is not None:
                raise ScummVMError('Gob run ended before pause could confirm a stop: ' + error)
            status = self.status()
            return {'run': self.run_id, 'acknowledged': False,
                    'already_stopped': status['state'] == 'stopped',
                    'confirmed_stopped': status['state'] == 'stopped',
                    'state': status['state'], 'stop': stop}
        if not sent:
            return {'run': self.run_id, 'acknowledged': False,
                    'confirmed_stopped': False, 'state': 'running', 'stop': None,
                    'reason': 'run-request-not-yet-sent'}
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            return {'run': self.run_id, 'acknowledged': False,
                    'confirmed_stopped': False, 'state': 'running', 'stop': None,
                    'reason': 'pause-host-budget-expired'}
        acknowledgement = self.rpc.call('pause', timeout_ms=remaining)
        with self._run_condition:
            while self._run_active:
                remaining_seconds = deadline - time.monotonic()
                if remaining_seconds <= 0:
                    break
                self._run_condition.wait(remaining_seconds)
            active = self._run_active
            stop = self._run_stop
            error = self._run_error
        if error is not None:
            raise ScummVMError('Gob run ended without a confirmed stop after pause: ' + error)
        confirmed = not active and isinstance(stop, dict)
        result = {'run': self.run_id, 'acknowledged': True,
                  'native_acknowledgement': acknowledgement,
                  'confirmed_stopped': confirmed,
                  'state': 'running' if active else 'exited' if stop and stop.get('reason') == 'quit' else 'stopped',
                  'stop': stop if confirmed else None}
        self._event('pause', result)
        return result


    def _frame(self):
        self._verify_manifest()
        state = self._read_state()
        if state.get('layer_conflict'):
            raise ScummVMError('Gob source generation conflict; frame cannot qualify an existing scene')
        self._refresh_resource_layers(state)
        binding = self._script_binding(state)
        reply = self._call('frame.get')
        width, height = reply.get('width'), reply.get('height')
        if (type(width) is not int or type(height) is not int or
                not 1 <= width <= 4096 or not 1 <= height <= 4096 or
                width * height > 2_000_000 or reply.get('format') != 'rgb24' or
                type(reply.get('revision')) is not int or reply['revision'] < 0):
            raise ScummVMError('Gob backend returned invalid committed frame metadata')
        try:
            pixels = base64.b64decode(reply['data_base64'], validate=True)
        except (KeyError, ValueError) as error:
            raise ScummVMError('Gob backend returned malformed RGB frame') from error
        if len(pixels) != width * height * 3:
            raise ScummVMError('Gob backend returned incomplete RGB frame')
        self._verify_manifest()
        pixel_sha256 = hashlib.sha256(pixels).hexdigest()
        frame_id = int(_digest([self._state_revision, reply['revision'], pixel_sha256])[:13], 16)
        mode_id = int(_digest([width, height, 'rgb24'])[:13], 16)
        metadata = {'run': self.run_id, 'version': self.version['id'],
                    'backend': 'scummvm-gob',
                    'scummvm_sha256': self.metadata['scummvm_sha256'],
                    'resource_manifest_sha256': self.manifest_sha256,
                    'resource_layers_sha256': self._layer_digest(),
                    'script': state['script']['name'],
                    'script_generation': state['script']['generation'],
                    'script_loaded_sha256': binding['loaded_sha256'],
                    'script_decompressed_sha256': binding['decompressed_sha256'],
                    'frame_id': frame_id, 'mode_id': mode_id,
                    'state_revision': self._state_revision,
                    'frame_commit_revision': reply['revision'],
                    'frame_guest_ms': reply.get('guest_ms'),
                    'frame_sha256': pixel_sha256,
                    'display': reply.get('display', state.get('display')),
                    'width': width, 'height': height, 'source_bpp': 24,
                    'double_width': False, 'double_height': False,
                    'frame_origin': 'last committed ScummVM display at Gob pause'}
        self._last_frame = (metadata, pixels)
        return metadata, pixels


    def frame_probe(self, points):
        if not isinstance(points, list) or len(points) > 4096:
            raise ValueError('Frame probe requires a list of at most 4096 points')
        metadata, pixels = self._frame()
        samples = []
        for point in points:
            if (not isinstance(point, (list, tuple)) or len(point) != 2 or
                    type(point[0]) is not int or type(point[1]) is not int):
                raise ValueError('Expected integer [x,y] frame point')
            x, y = point
            if not 0 <= x < metadata['width'] or not 0 <= y < metadata['height']:
                raise ValueError('Frame point lies outside the committed display')
            index = (y * metadata['width'] + x) * 3
            samples.append({'x': x, 'y': y, 'rgb': list(pixels[index:index+3])})
        result = {**metadata, 'format': 'rgb-samples', 'samples': samples}
        self._event('frame-probe', result)
        return result


    def screenshot(self, name='screenshot.png', *, grid=False, grid_step=32, hooks=True):
        from PIL import Image
        from .screenshot_grid import validate_step
        _file_name(name)
        if type(grid) is not bool or type(hooks) is not bool:
            raise ValueError('grid and hooks must be boolean')
        validate_step(grid_step)
        metadata, pixels = self._frame()
        buffer = io.BytesIO()
        Image.frombytes('RGB', (metadata['width'], metadata['height']), pixels).save(buffer, format='PNG')
        data = buffer.getvalue()
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ScummVMError('PNG conversion of Gob display failed')
        metadata = {**metadata, 'sha256': hashlib.sha256(data).hexdigest(),
                    'screenshot_hooks': {'available': False, 'requested': hooks}}
        if not grid:
            return self._artifact(name, 'screenshot', data, metadata)
        original = self._artifact(name[:248] + '.raw.png', 'screenshot', data, metadata)
        return self.project.debug_grid(original['artifact'], name=name, step=grid_step)


    def keyboard_press(self, key, *, modifiers=(), hold_ms=40, gap_ms=40):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        validate_keyboard(key=key, modifiers=modifiers, hold_ms=hold_ms, gap_ms=gap_ms)
        if modifiers:
            raise ValueError('ScummVM Gob input does not provide key modifiers')
        key = 'escape' if key == 'esc' else key
        timed = 'input.virtual_timing' in self.rpc.capabilities['features']
        if timed:
            params = {'kind': 'key', 'key': key, 'action': 'press',
                      'hold_ms': hold_ms, 'gap_ms': gap_ms}
        elif key in ('enter', 'left', 'right', 'up', 'down', 'escape', 'backspace', 'space'):
            params = {'kind': 'key', 'key': key}
        elif len(key) == 1 and key.isascii() and key.isprintable():
            params = {'kind': 'text', 'text': key}
        else:
            raise ValueError('ScummVM Gob backend cannot queue this physical key')
        reply = self._call('input', params)
        result = self._input_evidence('keyboard.press', params, reply, hold_ms, gap_ms)
        return result


    def keyboard_type(self, text, *, hold_ms=40, gap_ms=40):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        validate_keyboard(text=text, hold_ms=hold_ms, gap_ms=gap_ms)
        params = {'kind': 'text', 'text': text}
        if 'input.virtual_timing' in self.rpc.capabilities['features']:
            params.update(hold_ms=hold_ms, gap_ms=gap_ms)
        reply = self._call('input', params)
        return self._input_evidence('keyboard.type', params, reply, hold_ms, gap_ms)


    def _input_evidence(self, name, params, reply, hold_ms, gap_ms):
        if type(reply.get('queued')) is not int or reply['queued'] < 1:
            self.close()
            raise ScummVMError('Gob backend did not confirm queued input events')
        self._queued_keyboard += reply['queued']
        self._state_revision += 1
        result = {'run': self.run_id, 'backend': 'scummvm-gob',
                  'input': params, 'queued': reply['queued'], 'consumed': False,
                  'hold_ms_requested': hold_ms, 'gap_ms_requested': gap_ms,
                  'timing_applied': 'input.virtual_timing' in self.rpc.capabilities['features'],
                  'queue_status': {key: reply.get(key) for key in
                                   ('pending','guest_ms','queue_tail_guest_ms','next_due_guest_ms')
                                   if key in reply},
                  'state_revision': self._state_revision}
        self._event(name, result)
        return result


    def keyboard_state(self):
        if 'input.status' in self.rpc.capabilities['features']:
            reply = self._call('input.status')
            if (type(reply.get('pending')) is not int or reply['pending'] < 0 or
                    not isinstance(reply.get('held_keycodes'), list) or
                    not isinstance(reply.get('leases'), list)):
                raise ScummVMError('Gob backend returned invalid input queue status')
            native_ids = {entry.get('lease') for entry in reply['leases']
                          if isinstance(entry, dict)}
            for identifier in list(self._keyboard_leases):
                if identifier not in native_ids:
                    del self._keyboard_leases[identifier]
            return {'run': self.run_id, 'backend': 'scummvm-gob',
                    'keyboard': {'pending_events': reply['pending'],
                                 'owned_keys': [entry['key'] for entry in self._keyboard_leases.values()],
                                 'held_keycodes': reply['held_keycodes'],
                                 'leases': reply['leases'],
                                 'queue_tail_guest_ms': reply.get('queue_tail_guest_ms'),
                                 'next_due_guest_ms': reply.get('next_due_guest_ms'),
                                 'guest_ms': reply.get('guest_ms'),
                                 'dispatch_complete': reply['pending'] == 0,
                                 'game_consumption_verified': False}}
        return {'run': self.run_id, 'keyboard':
                {'queued_events_since_run': self._queued_keyboard,
                 'pending_events': None, 'owned_keys': [],
                 'consumption_verified': False}, 'backend': 'scummvm-gob'}


    def keyboard_key_down(self, key):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        validate_keyboard(key=key)
        if 'input.key_leases' not in self.rpc.capabilities['features']:
            raise ValueError('ScummVM Gob backend does not expose held-key leases')
        if any(entry['key'] == key for entry in self._keyboard_leases.values()):
            raise ValueError('Gob key already has an owned live lease')
        reply = self._call('input', {'kind':'key','key':key,'action':'down','gap_ms':0})
        lease = reply.get('lease')
        if type(lease) is not int or lease < 1 or reply.get('queued') != 1:
            self.close()
            raise ScummVMError('Gob backend did not confirm owned key-down lease')
        self._keyboard_leases[lease] = {'key':key,'release_scheduled':False}
        self._state_revision += 1
        result = {'run':self.run_id,'key':key,'lease':lease,'queued':1,
                  'down_delivered':False,'state_revision':self._state_revision}
        self._event('keyboard.key-down', result)
        return result


    def keyboard_key_up(self, lease):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        if type(lease) is not int or lease not in self._keyboard_leases or self._keyboard_leases[lease]['release_scheduled']:
            raise ValueError('Unknown or already releasing Gob key lease')
        reply = self._call('input', {'kind':'key','action':'up','lease':lease,'gap_ms':0})
        if reply.get('lease') != lease or reply.get('queued') != 1:
            self.close()
            raise ScummVMError('Gob backend did not confirm owned key-up event')
        self._keyboard_leases[lease]['release_scheduled'] = True
        self._state_revision += 1
        result = {'run':self.run_id,'key':self._keyboard_leases[lease]['key'],
                  'lease':lease,'queued':1,'release_delivered':False,
                  'state_revision':self._state_revision}
        self._event('keyboard.key-up', result)
        return result


    def click(self, x, y, *, button='left', hold_ms=80, mode_id=None, frame_id=None):
        self._verify_manifest()
        self._assert_no_layer_conflict(self._read_state())
        bounded(x, 'x', 0, 4095)
        bounded(y, 'y', 0, 4095)
        bounded(hold_ms, 'hold_ms', 1, 1000)
        if button not in ('left', 'right'):
            raise ValueError('ScummVM Gob backend supports left or right mouse buttons')
        frame, _ = self._frame()
        if x >= frame['width'] or y >= frame['height']:
            raise ValueError('Click is outside the committed frame')
        if mode_id is not None and mode_id != frame['mode_id']:
            raise ValueError('Click mode differs from the current committed frame')
        if frame_id is not None and frame_id != frame['frame_id']:
            raise ValueError('Click frame differs from the current committed frame')
        timed = 'input.virtual_timing' in self.rpc.capabilities['features']
        if timed:
            replies = [self._call('input', {'kind':'mouse','action':'click',
                                            'button':button,'x':x,'y':y,
                                            'hold_ms':hold_ms,'gap_ms':0})]
        else:
            replies = []
            try:
                for action in ('move', 'down', 'up'):
                    params = {'kind': 'mouse', 'action': action, 'button': button, 'x': x, 'y': y}
                    replies.append(self._call('input', params))
            except BaseException:
                # A submitted prefix must not be reissued as a second click.
                if replies:
                    self._event('click-partial', {'run': self.run_id, 'x': x, 'y': y,
                                                   'submitted_actions': ('move', 'down', 'up')[:len(replies)],
                                                   'complete': False})
                    self.close()
                raise
        if any(type(reply.get('queued')) is not int or reply['queued'] < 1 for reply in replies):
            self.close()
            raise ScummVMError('Gob backend did not confirm the complete mouse event sequence')
        self._state_revision += 1
        result = {'run': self.run_id, 'backend': 'scummvm-gob', 'x': x, 'y': y,
                  'button': button, 'queued': sum(reply['queued'] for reply in replies),
                  'consumed': False, 'hold_ms_requested': hold_ms,
                  'timing_applied': timed, 'mode_id': frame['mode_id'],
                  'frame_id': frame['frame_id'], 'state_revision': self._state_revision}
        self._event('click', result)
        return result


    def close(self):
        if self.closed:
            return
        result = {'state': 'exited' if self._guest_exited else 'interrupted',
                  'backend': 'scummvm-gob'}
        try:
            if self.rpc is not None and self.rpc.sock is not None:
                try:
                    self.rpc.call('quit', timeout_ms=3000)
                except Exception as error:
                    result['quit_error'] = str(error)
        finally:
            if self.rpc is not None:
                self.rpc.close()
                result['process_reaped'] = self.rpc.process.poll() is not None
            self.closed = True
            try:
                self._event('close', result)
                with self.project.transaction(True):
                    self.project.db.execute('UPDATE debug_runs SET ended=? WHERE id=?',
                                            (stamp(), self.run_id))
            finally:
                if self in self.project._live_debuggers:
                    self.project._live_debuggers.remove(self)

