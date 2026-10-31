"""Exact-edition DOS AGI source/command observation, without semantic claims.

Offsets identify the interpreter whose loaded code was observed for AGI SHA256
5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74.
The full invocation profile observes both evaluator and fast command fetches,
and requires the evaluator's actual stack-matched return to its caller.
"""
import base64
from copy import deepcopy
from hashlib import sha256
import time
from uuid import uuid4

from .agi_source import validate_resource
from .agi_resources import logic_messages

_ENGINE_SHA256 = '11bca817fecc1829f569c3751db7e74aedeb9e8ae970d49247d68607af04cc48'
_ENGINE_LENGTH = 0x9800

DISPATCH = 0x02c4
RETURN = 0x02fa
FETCH = 0x294a
FAST_FETCH = 0x0303
LOGIC_RETURN = 0x1306
DIALOGUE_WAIT = 0x4620
_TABLE = 0x061d
_SIGNATURE = bytes.fromhex('3cfc733e3c00743a3cad760a')
_CALL_SIGNATURE = bytes.fromhex('56ff971d0683c4028bf00bf67403acebbe')
_TABLE_EXPECTED = {30: 0x39b1, 33: 0x04d9, 35: 0x09ea, 36: 0x0a8f,
                   37: 0x7b53, 38: 0x7b90, 39: 0x7bdd, 41: 0x3a77}


class AGIDOSMonitor:
    """Observe bounded native action-handler returns in one paused session.

    CS:294a/SI=code_offset admits one leaf invocation before its first opcode.
    Legacy CS:02c4 observations admit one fetched action at a time. A foreign
    source pointer, unexpected stop or exhausted budget ends observation. The
    caller owns the session and qualifies the route/intervention that entered
    the routine. A snapshot or model result does not certify game reachability.
    """
    def __init__(self, session, resource, *, cs, ds, code_offset,
                 guest_ms=1000, timeout_ms=10000, max_instructions=128,
                 total_guest_ms=10000,total_timeout_ms=60000):
        validate_resource(resource)
        if any(type(v) is not int or not 0 <= v <= 65535 for v in (cs, ds, code_offset)):
            raise ValueError('invalid real-mode binding')
        if code_offset + len(resource.code) > 65536:
            raise ValueError('logic crosses data segment')
        if type(guest_ms) is not int or not 1 <= guest_ms <= 10000 or type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000 or type(max_instructions) is not int or not 1 <= max_instructions <= 128:
            raise ValueError('invalid monitor budget')
        if type(total_guest_ms) is not int or not 1<=total_guest_ms<=60000 or type(total_timeout_ms) is not int or not 1<=total_timeout_ms<=600000:
            raise ValueError('invalid total monitor budget')
        self.session, self.resource, self.cs, self.ds = session, resource, cs, ds
        self.code_offset, self.guest_ms, self.timeout_ms = code_offset, guest_ms, timeout_ms
        self.remaining = max_instructions
        self.guest_remaining=total_guest_ms;self.deadline=time.monotonic()+total_timeout_ms/1000
        self.failed = False
        self.history = []
        self._session_identity = self._identity()
        self.identity = {'format':'fdisbull-agi-dos-monitor-1', 'session_id': session.session_id,
                         'epoch': uuid4().hex, 'cs':cs, 'ds':ds,
                         'code_offset':code_offset, 'resource_sha256':resource.resource_sha256}
        if sha256(self._read(cs*16, _ENGINE_LENGTH)).hexdigest() != _ENGINE_SHA256:
            raise ValueError('unpacked interpreter fingerprint mismatch')
        if self._read(cs*16+DISPATCH, len(_SIGNATURE)) != _SIGNATURE or self._read(cs*16+0x02f5, len(_CALL_SIGNATURE)) != _CALL_SIGNATURE:
            raise ValueError('interpreter dispatcher signature mismatch')
        for opcode, address in _TABLE_EXPECTED.items():
            if int.from_bytes(self._read(ds*16+_TABLE+opcode*4,2),'little') != address:
                raise ValueError('interpreter command table mismatch')
        self._check_code()
        regs = session.registers()
        self.prefetch = self._word(regs['instruction_pointer']) in (FETCH, FAST_FETCH)
        if self._word(regs['segments']['cs']) != cs or self._word(regs['segments']['ds']) != ds or self._word(regs['instruction_pointer']) not in (DISPATCH,FETCH,FAST_FETCH):
            raise ValueError('not stopped at action dispatcher boundary')
        self._location(regs)
        if self.prefetch:
            if self._word(regs['instruction_pointer'])!=FETCH or self._location(regs)[0]!=0:
                raise ValueError('whole invocation requires the initial evaluator fetch')
            self._stack=(self._word(regs['segments']['ss']),self._word(regs['general']['esp']))
            record=int.from_bytes(self._read(ds*16+0x979,2),'little')
            if not 0<record<=65528:raise ValueError('invalid current logic record')
            descriptor=self._read(ds*16+record,8)
            if descriptor[2]!=resource.logic or int.from_bytes(descriptor[4:6],'little')!=code_offset or int.from_bytes(descriptor[6:8],'little')!=code_offset:
                raise ValueError('current logic record does not bind this initial source entry')
            ss,sp=self._stack
            if sp>65523:raise ValueError('wrapping evaluator frame is unqualified')
            frame=self._read(ss*16+sp+8,4)
            if int.from_bytes(frame[:2],'little')!=LOGIC_RETURN or int.from_bytes(frame[2:],'little')!=record:
                raise ValueError('initial evaluator call frame is unqualified')

    def _identity(self):
        s=self.session
        return (s.session_id,getattr(s,'run_id',None),getattr(s,'runtime_load',None),
                getattr(s,'_runtime_epoch',None),getattr(s,'closed',False),
                getattr(s,'version',{}).get('id'))

    @staticmethod
    def _word(value):
        return int(value, 16) & 0xffff if isinstance(value, str) else int(value) & 0xffff

    def _read(self, address, size):
        if type(address) is not int or type(size) is not int or size<0 or address<0 or address+size>0x100000:
            raise ValueError('native read outside real-mode profile')
        result = self.session.call('memory.read', {'address':{'space':'linear','offset':f'0x{address:08X}'}, 'length':size})
        raw = base64.b64decode(result['data_base64'], validate=True)
        if len(raw) != size: raise ValueError('incomplete native memory read')
        return raw

    @staticmethod
    def _owned_stop(stop,owned):
        reason=(stop.get('session') or {}).get('stop_reason',{})
        return (stop.get('outcome')=='breakpoint' and reason.get('kind')=='breakpoint'
                and reason.get('breakpoint_id') in owned and not reason.get('data_access'))

    def _check_code(self):
        if self._identity()!=self._session_identity or getattr(self.session,'closed',False):
            raise ValueError('native session identity changed')
        if hasattr(self.session,'layers') and self.session.layers()['active']:
            raise ValueError('active code layers are outside the original interpreter profile')
        if sha256(self._read(self.cs*16,_ENGINE_LENGTH)).hexdigest()!=_ENGINE_SHA256:
            raise ValueError('original interpreter code changed')
        if self._read(self.ds*16+self.code_offset,len(self.resource.code)) != self.resource.code:
            raise ValueError('native logic binding changed')

    def _location(self, regs):
        if self._word(regs['segments']['cs']) != self.cs or self._word(regs['segments']['ds']) != self.ds:
            raise ValueError('native segment binding changed')
        si = self._word(regs['general']['esi'])
        fetched=self._word(regs['instruction_pointer'])==DISPATCH
        off = si - self.code_offset - int(fetched)
        if not 0 <= off < len(self.resource.code): raise ValueError('native instruction outside bound logic')
        opcode = self._word(regs['general']['eax']) & 255 if fetched else self.resource.code[off]
        if self.resource.code[off] != opcode: raise ValueError('native opcode disagrees with bound logic')
        return off, opcode

    def snapshot(self):
        before=self.session.call('session.status')
        if before.get('state')!='stopped':raise ValueError('native capture requires a paused guest')
        self._check_code(); regs = self.session.registers()
        if self._word(regs['segments']['ds']) != self.ds: raise ValueError('native data segment changed')
        base=self.ds*16
        pointer=int.from_bytes(self._read(base+0x963,2),'little')
        if pointer + 14*43 > 65536: raise ValueError('object table outside data segment')
        result={'status':before,'registers':regs, 'data_0009_013f_hex':self._read(base+9,0x137).hex(),
                'object_table_offset':pointer, 'object_0_hex':self._read(base+pointer,43).hex(),
                'object_13_hex':self._read(base+pointer+13*43,43).hex()}
        after=self.session.call('session.status')
        if after.get('state')!='stopped' or any(before.get(k)!=after.get(k) for k in ('state_revision','frame_id','mode_id')):
            raise ValueError('native snapshot changed during capture')
        return result

    def step(self,*,dialogue_key=None):
        if dialogue_key is not None and dialogue_key not in ('enter','escape'):
            raise ValueError('dialogue_key must be enter, escape or None')
        if self.failed:raise ValueError('monitor requires reconciliation after an interrupted step')
        self._step_deadline=time.monotonic()+self.timeout_ms/1000
        self._step_guest_remaining=self.guest_ms
        if self.prefetch:return self._step_source(dialogue_key)
        if dialogue_key is not None:raise ValueError('dialogue input requires a whole-invocation monitor')
        before = self.snapshot(); regs=before['registers']
        if self._word(regs['instruction_pointer']) != DISPATCH: raise ValueError('not at dispatch boundary')
        off, opcode = self._location(regs)
        common={'offset':off,'opcode':opcode,'native_execution':True,'raw_before':before,'identity':dict(self.identity)}
        if opcode == 0 or opcode >= 0xfc:
            return dict(common,status='stopped',reason='control byte requires outer interpreter',stop=None)
        if self.remaining == 0: return dict(common,status='stopped',reason='instruction budget exhausted',stop=None)
        self.remaining -= 1
        self.failed=True
        bp=self.session.call('breakpoints.create', {'kind':'execution','once':True,
            'address':{'space':'segmented','segment':f'0x{self.cs:04X}','offset':f'0x{RETURN:08X}'}})
        try:
            stop=self._run()
        finally:
            # One-shot breakpoints may already be removed by the backend.
            try:self.session.call('breakpoints.delete',{'breakpoint_id':bp['breakpoint_id']})
            except Exception:pass
        after=self.snapshot(); r=after['registers']
        if not self._owned_stop(stop,[bp['breakpoint_id']]) or self._word(r['segments']['cs']) != self.cs or self._word(r['instruction_pointer']) != RETURN:
            return dict(common,status='stopped',reason='unexpected native stop',stop=stop,raw_after=after)
        next_offset=self._word(r['general']['eax'])-self.code_offset
        if not 0 <= next_offset <= len(self.resource.code):
            return dict(common,status='stopped',reason='handler returned outside bound logic',stop=stop,raw_after=after)
        self.failed=False
        return dict(common,status='completed',next_offset=next_offset,stop=stop,raw_after=after)

    def _run(self,*,guest_ms=None):
        wall=int((min(self.deadline,self._step_deadline)-time.monotonic())*1000)
        if wall<=0 or min(self.guest_remaining,self._step_guest_remaining)<=0:raise ValueError('total native run budget exhausted')
        result=self.session.run(guest_ms=min(guest_ms or self.guest_ms,self.guest_remaining,self._step_guest_remaining),
            timeout_ms=min(self.timeout_ms,wall),fast_forward=True,stop_on_hook=True)
        self.guest_remaining-=result.get('guest_elapsed_ms',0)
        self._step_guest_remaining-=result.get('guest_elapsed_ms',0)
        return result

    def _message_identity(self,number):
        """Bind the original decoded RAM string, before formatting, to input."""
        record=int.from_bytes(self._read(self.ds*16+0x979,2),'little')
        if not 0<record<=65526:raise ValueError('invalid current message record')
        descriptor=self._read(self.ds*16+record,10)
        if descriptor[2]!=self.resource.logic or descriptor[3]<number or int.from_bytes(descriptor[4:6],'little')!=self.code_offset:
            raise ValueError('native message record differs from source')
        table=int.from_bytes(descriptor[8:10],'little')
        if not 0<table<=65535-2*number-2:raise ValueError('invalid native message table')
        offset=int.from_bytes(self._read(self.ds*16+table+2*number,2),'little')
        text=logic_messages(self.resource)[self.resource.resource_sha256].get(str(number))
        if text is None or len(text)>1024 or not offset:raise ValueError('missing bounded source message')
        expected=text.encode('cp437')+b'\0'
        if table+offset+len(expected)>65536 or self._read(self.ds*16+table+offset,len(expected))!=expected:
            raise ValueError('native message bytes differ from source')
        return {'message_id':number,'resource_sha256':self.resource.resource_sha256,
                'text_sha256':sha256(expected[:-1]).hexdigest(),'length':len(expected)-1,
                'basis':'original decoded RAM text before formatting'}

    def _modal_wait(self):
        raw=self.snapshot();r=raw['registers']
        if self._word(r['segments']['cs'])!=self.cs or self._word(r['instruction_pointer'])!=DIALOGUE_WAIT:
            raise ValueError('not at the qualified dialogue wait')
        ss=self._word(r['segments']['ss']);sp=self._word(r['general']['esp'])
        if sp>65527 or int.from_bytes(self._read(ss*16+sp+6,2),'little')!=0x1d25:
            raise ValueError('dialogue wait call frame differs')
        if not int.from_bytes(self._read(self.ds*16+0xd15,2),'little'):
            raise ValueError('original dialogue window is not open')
        return raw

    def _keyboard_idle(self):
        state=self.session.keyboard_state();keys=state.get('keyboard',{})
        if any(type(keys.get(k)) is not int or keys[k]!=0 for k in ('pending_events','owned_keys','queued_guest_ms')):
            raise ValueError('dialogue keyboard input is not settled')
        return state

    def _dialogue_run(self,key,off,create,remove,common):
        if self.resource.code[off]!=101 or off+1>=len(self.resource.code):raise ValueError('dialogue policy requires source print')
        data=bytes.fromhex(common['raw_before']['data_0009_013f_hex'])
        if data[0x101]&1 or data[21]!=0:raise ValueError('dialogue key requires untimed blocking print')
        phase=common['dialogue']={'status':'awaiting_original_wait','key':key,'input_attempted':False,'stops':[]}
        phase['message']=self._message_identity(self.resource.code[off+1])
        wait=create(DIALOGUE_WAIT)
        stop=self._run();common['stop']=stop;phase['stops'].append(stop)
        if not self._owned_stop(stop,[wait]):raise ValueError('dialogue wait interrupted')
        phase['waiting_snapshot']=self._modal_wait()
        phase['keyboard_before']=self._keyboard_idle()
        first=self.session.screenshot(f'agi-dialogue-{off}-initial.png',hooks=False)
        phase['initial_frame']=first
        if not isinstance(first.get('artifact'),str) or not first['artifact']:
            raise ValueError('initial dialogue frame artifact is missing')
        remove(wait)
        # The native wait is already qualified. Allow a bounded video interval
        # with no input so a completed guest frame can represent the window.
        preview=self._run(guest_ms=50);common['stop']=preview;phase['stops'].append(preview)
        elapsed=preview.get('guest_elapsed_ms')
        if preview.get('outcome')!='guest_time' or type(elapsed) not in (int,float) or not elapsed>=50:
            raise ValueError('dialogue frame interval interrupted or incomplete')
        if not int.from_bytes(self._read(self.ds*16+0xd15,2),'little'):raise ValueError('dialogue closed before input')
        fresh=self.session.screenshot(f'agi-dialogue-{off}-waiting.png',hooks=False)
        phase['waiting_frame']=fresh
        if not isinstance(fresh.get('artifact'),str) or not fresh['artifact']:
            raise ValueError('fresh dialogue frame artifact is missing')
        a,b=first.get('metadata',{}),fresh.get('metadata',{})
        if (type(a.get('frame_id')) is not int or type(b.get('frame_id')) is not int or
            b['frame_id']<=a['frame_id'] or
            any(type(m) is not int or m<0 for m in (a.get('mode_id'),b.get('mode_id'))) or
            a['mode_id']!=b['mode_id']):
            raise ValueError('fresh dialogue frame was not captured')
        wait=create(DIALOGUE_WAIT)
        stop=self._run();common['stop']=stop;phase['stops'].append(stop)
        if not self._owned_stop(stop,[wait]):raise ValueError('dialogue readiness interrupted')
        phase['ready_snapshot']=self._modal_wait()
        self._keyboard_idle();remove(wait)
        phase['status']='input_attempted';phase['input_attempted']=True
        phase['input']=self.session.keyboard_press(key,hold_ms=1,gap_ms=1)
        stop=self._run();common['stop']=stop;phase['stops'].append(stop)
        phase['status']='awaiting_handler_return'
        return stop

    def _step_source(self,dialogue_key=None):
        before=self.snapshot();regs=before['registers']
        if self._word(regs['instruction_pointer']) not in (FETCH,FAST_FETCH):
            raise ValueError('not at source fetch boundary')
        off,opcode=self._location(regs)
        common=dict(offset=off,opcode=opcode,raw_before=before,identity=dict(self.identity),native_execution=True)
        if self.remaining==0:
            self.failed=True
            return dict(common,status='stopped',reason='instruction budget exhausted')
        if opcode in (22,23):
            self.failed=True
            return dict(common,status='stopped',reason='nested logic invocation is outside this monitor profile')
        self.remaining-=1
        owned=[];live=[];cleanup_errors=[];stop=None
        common['cleanup_errors']=cleanup_errors
        def cleanup():
            while live:
                ident=live.pop()
                try:self.session.call('breakpoints.delete',{'breakpoint_id':ident})
                except Exception as exc:cleanup_errors.append({'breakpoint_id':ident,'error':str(exc)})
        def create(point):
            bp=self.session.call('breakpoints.create',{'kind':'execution','once':False,
                'address':{'space':'segmented','segment':f'0x{self.cs:04X}','offset':f'0x{point:08X}'}})
            owned.append(bp['breakpoint_id']);live.append(bp['breakpoint_id'])
            return bp['breakpoint_id']
        def remove(ident):
            self.session.call('breakpoints.delete',{'breakpoint_id':ident});live.remove(ident)
        # Mark the attempt before continuing. Unknown transport outcomes must
        # never permit an implicit retry of the original operation.
        self.failed=True
        try:
            for point in ((LOGIC_RETURN,) if opcode==0 else (FETCH,FAST_FETCH)):
                create(point)
            stop=self._run() if dialogue_key is None else self._dialogue_run(dialogue_key,off,create,remove,common)
            common['stop']=stop
            # Removing our breakpoints can advance backend state_revision.
            # Finish those mutations before publishing a coherent snapshot.
            cleanup()
            try:after=self.snapshot()
            except Exception as exc:
                return dict(common,status='stopped',reason='native readback unavailable: '+str(exc))
            r=after['registers'];pc=self._word(r['instruction_pointer'])
            common.update(raw_after=after,stop=stop)
            if cleanup_errors:return dict(common,status='stopped',reason='breakpoint cleanup incomplete',cleanup_errors=cleanup_errors)
            if not self._owned_stop(stop,owned) or self._word(r['segments']['cs'])!=self.cs:
                return dict(common,status='stopped',reason='unexpected native stop')
            if opcode==0:
                ss,sp=self._stack
                if pc!=LOGIC_RETURN or self._word(r['segments']['ss'])!=ss or self._word(r['general']['esp'])!=(sp+10)&65535:
                    return dict(common,status='stopped',reason='logic return stack witness differs')
                result=dict(common,status='returned')
                self.history.append(result)
                return deepcopy(result)
            if pc not in (FETCH,FAST_FETCH):return dict(common,status='stopped',reason='unexpected native boundary')
            next_offset,_=self._location(r)
            if dialogue_key is not None:
                common['dialogue']['handler_return_observed']=True
                if int.from_bytes(self._read(self.ds*16+0xd15,2),'little'):
                    return dict(common,status='stopped',reason='original dialogue window did not close')
                common['dialogue']['keyboard_after']=self._keyboard_idle()
                common['dialogue'].update(status='completed',window_closed=True,input_settled=True)
            result=dict(common,status='completed',next_offset=next_offset)
            self.history.append(result);self.failed=False
            return deepcopy(result)
        except Exception as exc:
            # A lost response may follow real input/effects. Preserve the phase
            # and attempted action; never repeat a key or original operation.
            return dict(common,status='stopped',reason=str(exc))
        finally:
            # Retain every stop/attempt. Cleanup never continues the guest.
            cleanup()
