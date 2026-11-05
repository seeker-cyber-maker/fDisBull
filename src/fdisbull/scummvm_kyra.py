"""Experimental Kyra/EMC2 debugger controller for a *separately patched* ScummVM.

A contract and source-evidence scaffold, not an in-house Kyra engine and not an
interpreter for original DOS x86. Ordinary ScummVM has no Kyra agent protocol
and is deliberately refused by the transport handshake.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
import uuid

from .debugger import DebugSession, bounded, stamp
from .external_files import _file_name
from .keyboard_input import validate_keyboard
from .scummvm_rpc import ScummVMError, ScummVMRPC

_ENGINE = 'scummvm-kyra'
_GAME_IDS = frozenset(('kyra1', 'lol'))
_HEX64 = re.compile(r'^[0-9a-f]{64}$')
_SCRIPT_NAME = re.compile(r'^[A-Za-z0-9_.$-]{1,64}$')
_REQUIRED = frozenset(('state.get', 'step', 'run', 'break.add', 'break.remove',
                       'frame.get', 'input', 'trace.start', 'trace.stop', 'trace.get'))
_MAX_FILES = 8192
_MAX_BYTES = 768 * 1024 * 1024
_MAX_IMAGE = 2048


def _digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode('utf-8')).hexdigest()


def _manifest(game_dir):
    """Stream-hash *all* source files; never retain original resource bytes."""
    entries, total = [], 0
    for item in sorted(game_dir.rglob('*')):
        if item.is_symlink():
            raise ValueError('Kyra input tree may not contain symlinks')
        if not item.is_file():
            if not item.is_dir():
                raise ValueError('Kyra input tree contains an unsupported member')
            continue
        if len(entries) >= _MAX_FILES:
            raise ValueError('Kyra input tree exceeds file-count budget')
        size = item.stat().st_size
        if size < 0 or total + size > _MAX_BYTES:
            raise ValueError('Kyra input tree exceeds 768 MiB budget')
        before = item.stat()
        sha = hashlib.sha256()
        with item.open('rb') as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                sha.update(chunk)
        after = item.stat()
        if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
            raise ValueError('Kyra source changed during manifest construction')
        total += size
        entries.append({'path': item.relative_to(game_dir).as_posix(),
                        'size': size, 'sha256': sha.hexdigest()})
    if not entries:
        raise ValueError('Kyra input tree is empty')
    return entries


def validate_kyra_hello(hello, *, game_id, required=_REQUIRED):
    """Reject stock ScummVM, AGI/Gob sidecars and unqualified variants."""
    if game_id not in _GAME_IDS:
        raise ValueError('Kyra scaffold supports only kyra1 and lol')
    if not isinstance(hello, dict) or hello.get('engine') != 'kyra':
        raise ScummVMError('Not an instrumented Kyra engine')
    if (hello.get('protocol') != 'fdisbull-scummvm-agent'
            or type(hello.get('protocol_version')) is not int
            or hello['protocol_version'] != 1
            or type(hello.get('bridge_version')) is not int
            or hello['bridge_version'] != 1
            or hello.get('profile') != 'kyra-emc2-v1'):
        raise ScummVMError('Kyra bridge protocol is absent or incompatible')
    variant = hello.get('variant')
    if (not isinstance(variant, dict) or variant.get('recognized_detection') is not True
            or variant.get('game_id') != game_id):
        raise ScummVMError('Kyra native game detection differs from requested edition')
    caps = hello.get('capabilities')
    if not isinstance(caps, list) or any(not isinstance(v, str) for v in caps):
        raise ScummVMError('Kyra backend returned invalid capabilities')
    missing = set(required) - set(caps)
    if missing:
        raise ScummVMError('Kyra bridge lacks required capabilities: ' + ', '.join(sorted(missing)))
    return variant


def validate_kyra_state(state, game_id):
    """Check *typed* VM location. Script offsets are DATA words, not file bytes."""
    if not isinstance(state, dict) or state.get('game_id') != game_id:
        raise ScummVMError('Kyra VM state has wrong game identity')
    phase = state.get('phase')
    if phase not in ('before_opcode', 'after_opcode', 'backend_yield', 'idle'):
        raise ScummVMError('Kyra VM state has unknown boundary')
    if (type(state.get('guest_ms')) is not int or state['guest_ms'] < 0
            or type(state.get('frame_revision')) is not int or state['frame_revision'] < 0):
        raise ScummVMError('Kyra VM state has invalid clock/frame counter')
    script = state.get('script')
    ip = state.get('ip_word')
    if script is None:
        if ip is not None or phase not in ('backend_yield', 'idle'):
            raise ScummVMError('Kyra absent script has a non-idle execution position')
    else:
        if (not isinstance(script, dict) or not isinstance(script.get('name'), str)
                or not _SCRIPT_NAME.fullmatch(script['name'])
                or type(script.get('generation')) is not int or script['generation'] < 1
                or type(script.get('data_words')) is not int
                or not 1 <= script['data_words'] <= (16 * 1024 * 1024) // 2
                or not isinstance(script.get('loaded_data_sha256'), str)
                or not _HEX64.fullmatch(script['loaded_data_sha256'])
                or type(ip) is not int or not 0 <= ip < script['data_words']):
            raise ScummVMError('Kyra VM state has invalid loaded script or DATA-word offset')
    game = state.get('game')
    if not isinstance(game, dict):
        raise ScummVMError('Kyra game state must be a typed mapping')
    allowed = {'kyra1': {'room'}, 'lol': {'level', 'block', 'direction'}}[game_id]
    for name in allowed & game.keys():
        if type(game[name]) is not int or not 0 <= game[name] <= 65535:
            raise ScummVMError('Kyra game-state field has invalid type or range')
    regs = state.get('registers')
    if regs is not None and (not isinstance(regs, list) or len(regs) > 32
                             or any(type(r) is not int or not -32768 <= r <= 65535 for r in regs)):
        raise ScummVMError('Kyra reported invalid EMC2 registers')
    return state


def _position(state):
    script = state['script']
    if script is None:
        return None
    return {'space': 'kyra-emc2', 'script': script['name'],
            'generation': script['generation'], 'word_offset': state['ip_word'],
            'offset': state['ip_word'] * 2, 'offset_origin': 'decoded_DATA_chunk',
            'loaded_data_sha256': script['loaded_data_sha256'],
            'phase': state['phase']}


class ScummVMKyraSession(DebugSession):
    """Source-guarded controller for Kyra's externally instrumented EMC2 VM."""
    native_hooks_available = False

    @property
    def script_operations(self):
        return {'assert', 'status', 'run', 'engine-state', 'step', 'breakpoint',
                'delete-breakpoint', 'watchpoint', 'delete-watchpoint', 'trace',
                'screenshot', 'frame-probe', 'keyboard.press', 'keyboard.type',
                'keyboard.state', 'click'}

    def __init__(self, project, executable, game_dir, *, game_id, version=None,
                 boot_timeout_ms=240000, window=False, _on_spawn=None):
        if window:
            raise ValueError('Kyra scaffold requires an owned headless ScummVM sidecar')
        if game_id in ('kyra:kyra1', 'kyra:lol'):
            game_id = game_id.split(':', 1)[1]
        if game_id not in _GAME_IDS:
            raise ValueError('Kyra scaffold supports only kyra1 and lol')
        self.project = project
        self.version = project.version(version)
        if self.version['parent'] is not None:
            raise ValueError('Kyra replacement engine requires the original unpatched project version')
        self.game_dir = Path(game_dir).expanduser().resolve(strict=True)
        if not self.game_dir.is_dir():
            raise ValueError('Kyra target must be a directory')
        if self.game_dir == project.path.parent or self.game_dir in project.path.parents:
            raise ValueError('Kyra runtime project must be outside original game directory')
        owner = self.game_dir / project.meta['filename']
        if owner.is_symlink() or not owner.is_file() or owner.resolve().parent != self.game_dir:
            raise ValueError('Project owner must be a direct regular game file')
        source_hash = hashlib.sha256(owner.read_bytes()).hexdigest()
        if source_hash != project.meta['source_sha256']:
            raise ValueError('Kyra original source differs from project identity')
        self.manifest = _manifest(self.game_dir)
        self.manifest_sha256 = _digest_json(self.manifest)
        executable = Path(executable).expanduser().resolve(strict=True)
        self.run_id = uuid.uuid4().hex
        self.closed = False
        self._guest_exited = False
        self._run_active = False
        self._run_lock = threading.Lock()
        self._control_lock = threading.RLock()
        self._breakpoints = {}
        self._watchpoints = {}
        self._state_revision = 0
        self._last_frame = None
        self.rpc = None
        self.game_id = game_id
        self.metadata = {'backend': _ENGINE, 'execution_context': 'kyra-emc2',
                         'native_hooks_available': False,
                         'replacement_engine': True, 'original_x86_executed': False,
                         'game_id': game_id, 'version_sha256': self.version['sha256'],
                         'source_sha256': source_hash, 'resource_manifest': self.manifest,
                         'resource_manifest_sha256': self.manifest_sha256,
                         'executable': str(executable),
                         'scummvm_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                         'runtime_profile': 'experimental-kyra-emc2-agent-v1',
                         'address_scope': 'EMC2 decoded DATA words, not original DOS CPU/file offsets',
                         'watch_scope': 'only explicitly instrumented native accessors'}
        try:
            self.rpc = ScummVMRPC(executable, self.game_dir, engine='kyra',
                                  game_id=game_id, runtime_parent=project.path.parent,
                                  boot_timeout_ms=boot_timeout_ms, on_spawn=_on_spawn)
            self.metadata['variant'] = validate_kyra_hello(self.rpc.hello, game_id=game_id)
            self.metadata['backend_hello'] = self.rpc.hello
            self.metadata['pid'] = self.rpc.process.pid
            first = self._read_state()
            self.metadata['initial_position'] = _position(first)
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                                   (self.run_id, self.version['id'], stamp(), None,
                                    'stopped', json.dumps(self.metadata)))
            project._live_debuggers.append(self)
            self._event('launch', {'backend': _ENGINE, 'state': 'stopped',
                                   'position': _position(first)})
        except BaseException:
            if self.rpc is not None:
                self.rpc.close()
            raise

    def _verify_manifest(self):
        if _digest_json(_manifest(self.game_dir)) != self.manifest_sha256:
            raise ScummVMError('Kyra original game resource manifest changed')

    def _call(self, op, params=None, *, timeout_ms=15000):
        if self.closed or self.rpc is None:
            raise ScummVMError('Kyra session is closed')
        if self._run_active and op not in ('run', 'step', 'pause'):
            raise ScummVMError('Kyra execution is running; no parallel observation/mutation')
        return self.rpc.call(op, params, timeout_ms=timeout_ms)

    def _read_state(self):
        return validate_kyra_state(self._call('state.get'), self.game_id)

    def contexts(self):
        return {'run': self.run_id, 'selected': 'kyra-emc2',
                'contexts': [{'id':'kyra-emc2','kind':'bytecode-vm',
                              'source_address':'script + loaded generation + decoded DATA word'}]}

    def context(self, name):
        if name != 'kyra-emc2':
            raise ValueError('Only the Kyra EMC2 context is exposed')
        return self

    def engine_state(self):
        self._verify_manifest()
        state = self._read_state()
        return {**state, 'run':self.run_id, 'backend':_ENGINE,
                'position':_position(state), 'state_revision':self._state_revision,
                'resource_manifest_sha256':self.manifest_sha256,
                'loaded_script_original_bytes_verified':False,
                'state_origin':'ScummVM replacement interpreter, not original DOS execution'}

    def status(self):
        if self._run_active:
            return {'run':self.run_id,'backend':_ENGINE,'state':'running',
                    'native_hooks_available':False,'position':None}
        if self._guest_exited:
            return {'run':self.run_id,'backend':_ENGINE,'state':'exited',
                    'native_hooks_available':False}
        state=self.engine_state()
        return {'run':self.run_id,'backend':_ENGINE,'state':'stopped',
                'position':state['position'],'mapping':self.metadata,
                'native_hooks_available':False,'capabilities':self.rpc.capabilities}

    @staticmethod
    def _stop(reply):
        if not isinstance(reply, dict) or not isinstance(reply.get('stop'), dict):
            raise ScummVMError('Kyra run lacks structured stop receipt')
        stop=reply['stop']
        if (stop.get('reason') not in ('step','budget','breakpoint','watchpoint',
                                    'host_timeout','guest_budget','pause','quit')
                or type(stop.get('instructions')) is not int or not 0 <= stop['instructions'] <= 1_000_000):
            raise ScummVMError('Kyra run returned invalid stop reason or opcode count')
        return stop

    def run(self, *, max_instructions=100000, timeout_ms=10000, guest_ms=None,
            fast_forward=False, stop_on_hook=False, until_cycle=False):
        if until_cycle or stop_on_hook or fast_forward:
            raise ValueError('Kyra scaffold has no native hooks, deterministic cycle or fast-forward contract')
        bounded(max_instructions,'max_instructions',1,1_000_000)
        bounded(timeout_ms,'timeout_ms',1,600000)
        if guest_ms is not None:
            bounded(guest_ms,'guest_ms',1,3_600_000)
            if not self.rpc.capabilities.get('virtual_time'):
                raise ValueError('Kyra bridge does not advertise a qualified virtual clock')
        self._verify_manifest()
        if not self._run_lock.acquire(blocking=False):
            raise ScummVMError('Another Kyra run is active')
        started=time.monotonic()
        try:
            before=self._read_state()
            self._run_active=True
            try:
                params={'max_instructions':max_instructions,'max_ms':timeout_ms}
                if guest_ms is not None:
                    params['max_guest_ms']=guest_ms
                stop=self._stop(self._call('run',params,timeout_ms=timeout_ms+2000))
            finally:
                self._run_active=False
            self._guest_exited = stop['reason'] == 'quit'
            after=None if self._guest_exited else self._read_state()
            if after is not None and after['guest_ms'] < before['guest_ms']:
                self.close()
                raise ScummVMError('Kyra virtual time moved backwards')
            self._verify_manifest()
            self._state_revision += 1
            outcome={'host_timeout':'timeout','guest_budget':'guest_time','quit':'exited'}.get(stop['reason'],stop['reason'])
            receipt={'run':self.run_id,'backend':_ENGINE,'outcome':outcome,
                     'stop':{'context':'kyra-emc2','position':_position(after) if after else None,
                             'trigger':outcome, 'instruction_completed':None},
                     'native_stop':stop,'executed':stop['instructions'],
                     'guest_elapsed_ms':None if after is None else after['guest_ms']-before['guest_ms'],
                     'host_elapsed_ms':round((time.monotonic()-started)*1000,3),
                     'state_revision':self._state_revision,
                     'original_dos_equivalence':'unverified'}
            self._event('run',receipt)
            return receipt
        finally:
            self._run_lock.release()

    def resume(self, **kwargs):
        return self.run(**kwargs)

    def step(self, count=1, *, timeout_ms=10000):
        bounded(count,'count',1,256)
        bounded(timeout_ms,'timeout_ms',1,600000)
        self._verify_manifest()
        if not self._run_lock.acquire(blocking=False):
            raise ScummVMError('Another Kyra run is active')
        try:
            start=self._read_state()
            self._run_active=True
            try:
                stop=self._stop(self._call('step',{'count':count,'max_ms':timeout_ms},
                                           timeout_ms=timeout_ms+2000))
            finally:
                self._run_active=False
            self._guest_exited=stop['reason']=='quit'
            self._verify_manifest()
            self._state_revision+=1
            reply={'run':self.run_id,'backend':_ENGINE,'requested':count,
                   'completed':stop['reason']=='step' and stop['instructions']==count,
                   'before':_position(start), 'native_stop':stop,
                   'state_revision':self._state_revision}
            self._event('step',reply)
            return reply
        finally:
            self._run_lock.release()

    def breakpoint(self, address, *, cs=None, access='x', length=1, view='static'):
        if cs is not None or access!='x' or length!=1 or view not in ('static','execute'):
            raise ValueError('Kyra VM breakpoint cannot use native CPU/byte-range options')
        self._verify_manifest()
        if not isinstance(address, dict) or set(address) != {'script','generation','offset','loaded_data_sha256'}:
            raise ValueError('Breakpoint requires exact script, generation, DATA-byte offset and loaded hash')
        state=self._read_state();pos=_position(state)
        if pos is None:
            raise ValueError('Cannot bind a Kyra breakpoint without a loaded script')
        if any(address[k]!=pos[k] for k in ('script','generation','loaded_data_sha256')):
            raise ValueError('Stale Kyra breakpoint source/generation guard')
        offset=bounded(address['offset'],'offset',0,state['script']['data_words']*2-2)
        if offset%2:
            raise ValueError('EMC2 breakpoint must align to a 16-bit DATA word')
        with self._control_lock:
            self._call('break.add',address)
            identifier=next((k for k,v in self._breakpoints.items() if v==address),None)
            if identifier is None:
                identifier=uuid.uuid4().hex
                self._breakpoints[identifier]=dict(address)
        result={'run':self.run_id,'backend':_ENGINE,'breakpoint_id':identifier,
                'address':{'space':'kyra-emc2',**address,'offset_origin':'decoded_DATA_chunk'},
                'source_verification':'loaded bridge hash only; original resource binding pending'}
        self._event('breakpoint',result)
        return result

    def watchpoint(self, kind, index, *, access='w', length=None):
        if 'watch.add' not in self.rpc.capabilities['features']:
            raise ValueError('Kyra bridge does not advertise instrumented accessor watches')
        if kind not in ('register','game_flag') or access not in ('r','w','rw'):
            raise ValueError('Kyra watches require a register/game_flag accessor and r/w/rw')
        bounded(index,'index',0,15 if kind=='register' else 255)
        if length not in (None,1):
            raise ValueError('Kyra accessor watch length must be one element')
        param={'kind':kind,'index':index,'access':access}
        with self._control_lock:
            self._call('watch.add',param)
            identifier=next((k for k,v in self._watchpoints.items() if v==param),None)
            if identifier is None:
                identifier=uuid.uuid4().hex
                self._watchpoints[identifier]=param
        result={'run':self.run_id,'backend':_ENGINE,'watchpoint_id':identifier,
                'accessor_only':True,'all_native_writes_covered':False,**param}
        self._event('watchpoint',result)
        return result

    def delete_breakpoint(self, breakpoint_id):
        with self._control_lock:
            if breakpoint_id in self._breakpoints:
                self._call('break.remove',self._breakpoints[breakpoint_id])
                del self._breakpoints[breakpoint_id]
            elif breakpoint_id in self._watchpoints:
                self._call('watch.remove',self._watchpoints[breakpoint_id])
                del self._watchpoints[breakpoint_id]
            else:
                raise ValueError('Unknown Kyra native breakpoint/watchpoint ID')
        return {'run':self.run_id,'deleted':breakpoint_id,'backend':_ENGINE}

    def delete_watchpoint(self, watchpoint_id):
        return self.delete_breakpoint(watchpoint_id)

    def trace(self, name='trace.json', *, count=128, timeout_ms=10000, fast_forward=False):
        _file_name(name)
        bounded(count,'count',1,2048)
        if fast_forward:
            raise ValueError('Kyra fast-forward is unqualified')
        self._verify_manifest()
        self._call('trace.start',{'limit':count})
        try:
            result=self.run(max_instructions=count,timeout_ms=timeout_ms)
        finally:
            self._call('trace.stop')
        trace=self._call('trace.get',{'limit':count})
        events=trace.get('entries')
        if not isinstance(events,list) or len(events)>count:
            raise ScummVMError('Kyra bridge returned invalid trace length')
        for event in events:
            if (not isinstance(event,dict) or not isinstance(event.get('script'),str)
                    or type(event.get('word_offset')) is not int or event['word_offset']<0
                    or type(event.get('opcode')) is not int or not 0<=event['opcode']<=18):
                raise ScummVMError('Kyra bridge returned invalid EMC2 trace record')
        report={'backend':_ENGINE,'events':events,'native_stop':result['native_stop'],
                'source_coverage':'bridge-reported loaded script offsets, not original DOS CPU',
                'complete':len(events)<=count and result['outcome'] not in ('timeout','exited')}
        artifact=self._artifact(name,'trace',json.dumps(report,sort_keys=True).encode(),
                                {'backend':_ENGINE,'events':len(events),
                                 'source_manifest_sha256':self.manifest_sha256})
        return {'run':self.run_id,**artifact,'event_count':len(events),
                'complete':report['complete']}

    def _frame(self):
        self._verify_manifest()
        response=self._call('frame.get')
        w,h=response.get('width'),response.get('height')
        if (type(w) is not int or type(h) is not int or not 1<=w<=_MAX_IMAGE
                or not 1<=h<=_MAX_IMAGE or response.get('pixel_format')!='rgb24'
                or type(response.get('revision')) is not int or response['revision']<0):
            raise ScummVMError('Kyra bridge returned invalid committed display metadata')
        try:
            raw=base64.b64decode(response['rgb24_base64'],validate=True)
        except (ValueError,KeyError) as error:
            raise ScummVMError('Kyra bridge returned invalid RGB24 frame') from error
        if len(raw)!=w*h*3:
            raise ScummVMError('Kyra bridge returned truncated RGB24 display')
        stamp_data={'sha256':hashlib.sha256(raw).hexdigest(),
                    'revision':response['revision'],'source':self.manifest_sha256,
                    'backend':_ENGINE,'state_revision':self._state_revision}
        info={'width':w,'height':h,'mode_id':response.get('mode_id',0),
              'revision':response['revision'],'frame_id':_digest_json(stamp_data),
              'pixel_format':'rgb24'}
        self._last_frame=info
        return info,raw

    def frame_probe(self, points):
        if not isinstance(points,list) or not 1<=len(points)<=4096:
            raise ValueError('Kyra frame probes require 1..4096 coordinates')
        info,data=self._frame()
        samples=[]
        for xy in points:
            if (not isinstance(xy,(list,tuple)) or len(xy)!=2
                    or any(type(v) is not int for v in xy)):
                raise ValueError('Invalid Kyra frame pixel coordinate')
            x,y=xy
            if not (0<=x<info['width'] and 0<=y<info['height']):
                raise ValueError('Pixel outside committed Kyra frame')
            at=(y*info['width']+x)*3
            samples.append({'x':x,'y':y,'rgb':list(data[at:at+3])})
        return {'run':self.run_id,'backend':_ENGINE,'frame':info,'pixels':samples}

    def screenshot(self,name='screenshot.png',*,grid=False,grid_step=32,hooks=True):
        from PIL import Image
        _file_name(name)
        info,data=self._frame()
        img=Image.frombytes('RGB',(info['width'],info['height']),data)
        stream=io.BytesIO()
        img.save(stream,format='PNG')
        metadata={'backend':_ENGINE,'game_id':self.game_id,'frame':info,
                  'manifest_sha256':self.manifest_sha256,
                  'frame_origin':'last committed ScummVM Kyra display',
                  'native_hooks_available':False,'screenshot_hooks':{'requested':hooks,'available':False}}
        if not grid:
            return self._artifact(name,'screenshot',stream.getvalue(),metadata)
        original=self._artifact(name[:248]+'.raw.png','screenshot',stream.getvalue(),metadata)
        return self.project.debug_grid(original['artifact'],name=name,step=grid_step)

    def keyboard_press(self,key,*,modifiers=(),hold_ms=40,gap_ms=40):
        self._verify_manifest()
        validate_keyboard(key=key,modifiers=modifiers,hold_ms=hold_ms,gap_ms=gap_ms)
        if modifiers:
            raise ValueError('Kyra bridge does not qualify modifier chords')
        request={'kind':'key','key':'escape' if key=='esc' else key,
                 'action':'press','hold_ms':hold_ms,'gap_ms':gap_ms}
        return self._input_receipt(request)

    def keyboard_type(self,text,*,hold_ms=40,gap_ms=40):
        self._verify_manifest()
        validate_keyboard(text=text,hold_ms=hold_ms,gap_ms=gap_ms)
        return self._input_receipt({'kind':'text','text':text,
                                    'hold_ms':hold_ms,'gap_ms':gap_ms})

    def _input_receipt(self,params):
        response=self._call('input',params)
        if type(response.get('queued')) is not int or response['queued']<1:
            self.close()
            raise ScummVMError('Kyra bridge did not acknowledge input queueing')
        self._state_revision+=1
        result={'run':self.run_id,'backend':_ENGINE,'queued':response['queued'],
                'input':params,'consumed':False,'state_revision':self._state_revision}
        self._event('input',result)
        return result

    def keyboard_state(self):
        if 'input.status' not in self.rpc.capabilities['features']:
            return {'run':self.run_id,'backend':_ENGINE,'pending_events':None,
                    'consumption_verified':False}
        return {'run':self.run_id,'backend':_ENGINE,
                'keyboard':self._call('input.status'), 'consumption_verified':False}

    def click(self,x,y,*,button='left',hold_ms=80,mode_id=None,frame_id=None):
        bounded(x,'x',0,4095)
        bounded(y,'y',0,4095)
        bounded(hold_ms,'hold_ms',1,1000)
        if button not in ('left','right'):
            raise ValueError('Kyra supports only left/right mouse buttons')
        info,_=self._frame()
        if x>=info['width'] or y>=info['height']:
            raise ValueError('Click outside current Kyra display')
        if mode_id is not None and mode_id!=info['mode_id']:
            raise ValueError('Stale Kyra pixel mode')
        if frame_id is not None and frame_id!=info['frame_id']:
            raise ValueError('Stale Kyra frame identity')
        return self._input_receipt({'kind':'mouse','action':'click','button':button,
                                    'x':x,'y':y,'hold_ms':hold_ms,'gap_ms':0})

    def write_engine_state(self,*args,**kwargs):
        raise ValueError('Kyra state edits are unsupported until native validation')

    def save_state(self,*args,**kwargs):
        raise ValueError('Kyra VM checkpoints are unsupported; no DOS state equivalence')

    def load_state(self,*args,**kwargs):
        raise ValueError('Kyra VM checkpoints are unsupported; no DOS state equivalence')

    def patch_resource(self,*args,**kwargs):
        raise ValueError('Kyra loaded-script patching is unsupported')

    def registers(self):
        raise ValueError('Kyra exposes VM registers in engine_state, not native CPU registers')

    def close(self):
        if self.closed:
            return
        try:
            if self.rpc is not None:
                try:
                    self.rpc.call('quit',timeout_ms=3000)
                except (OSError,ScummVMError):
                    pass
                self.rpc.close()
        finally:
            self.closed=True
            try:
                with self.project.transaction(True):
                    self.project.db.execute('UPDATE debug_runs SET ended=? WHERE id=?',
                                            (stamp(),self.run_id))
            finally:
                if self in self.project._live_debuggers:
                    self.project._live_debuggers.remove(self)
