"""Observe an already-entered original DOS AGI print handler.

This is source-bound observation, not a whole-invocation or gameplay proof.
It never writes guest memory, code or registers. A key is attempted at most
once and only after a qualified untimed modal wait and a fresh guest frame.
"""
import base64
from copy import deepcopy
from hashlib import sha256
import time
from uuid import uuid4

from .agi_dos import AGIDOSMonitor, _ENGINE_LENGTH, _ENGINE_SHA256, DIALOGUE_WAIT, RETURN
from .agi_source import validate_resource

_PRINT_HANDLER = 0x1c06


class AGIDOSPrintObserver:
    """Admit a stopped original print command and retain one outcome."""
    def __init__(self, session, resources, *, cs, ds):
        if any(type(x) is not int or not 0 <= x <= 65535 for x in (cs, ds)):
            raise ValueError('invalid real-mode binding')
        if not isinstance(resources,dict) or not resources or len(resources)>256:
            raise ValueError('invalid resource mapping')
        for n,r in resources.items():
            validate_resource(r)
            if type(n) is not int or n!=r.logic: raise ValueError('resource mapping mismatch')
        self.session,self.cs,self.ds=session,cs,ds
        self._session_identity=AGIDOSMonitor._identity(self)
        self._report=None
        status=session.call('session.status')
        if status.get('state')!='stopped' or type(status.get('state_revision')) is not int:
            raise ValueError('print admission requires a paused guest with a state revision')
        self._check_engine()
        if int.from_bytes(self._read(ds*16+0x61d+101*4,2),'little')!=_PRINT_HANDLER:
            raise ValueError('original print command table differs')
        regs=session.registers();self._segments(regs)
        if self._word(regs['instruction_pointer'])!=_PRINT_HANDLER:raise ValueError('not at original print entry')
        self.ss=self._word(regs['segments']['ss']);self.sp=self._word(regs['general']['esp'])
        if self.sp>65533 or int.from_bytes(self._read(self.ss*16+self.sp,2),'little')!=RETURN:
            raise ValueError('print dispatcher return frame differs')
        record=int.from_bytes(self._read(ds*16+0x979,2),'little')
        if not 0<record<=65526:raise ValueError('invalid current logic record')
        desc=self._read(ds*16+record,10);number=desc[2]
        if number not in resources:raise ValueError('current logic is not captured')
        self.resource=resources[number];self.code_offset=int.from_bytes(desc[4:6],'little')
        self.record=record
        if self.code_offset+len(self.resource.code)>65536:raise ValueError('logic outside data segment')
        self._check_binding()
        si=self._word(regs['general']['esi']);off=si-self.code_offset-1
        if not 0<=off<len(self.resource.code)-1 or self.resource.code[off]!=101:
            raise ValueError('print operand is not source-bound')
        self.offset=off;self.message_id=self.resource.code[off+1]
        if not self.message_id or self._read(ds*16+si,1)!=bytes([self.message_id]):
            raise ValueError('print message argument differs')
        self.message=AGIDOSMonitor._message_identity(self,self.message_id)
        data=self._read(ds*16+9,0x102)
        self.output_mode=bool(data[0x101]&1);self.window_timer=data[21]
        self.mode='nonblocking' if self.output_mode else 'timed' if self.window_timer else 'blocking'
        after=session.call('session.status')
        if after.get('state')!='stopped' or any(status.get(k)!=after.get(k) for k in ('state_revision','frame_id','mode_id')):
            raise ValueError('native print admission changed during capture')
        self._admission_revision=after['state_revision']
        self.identity={'format':'fdisbull-agi-print-observer-1','session_id':session.session_id,
                       'epoch':uuid4().hex,'cs':cs,'ds':ds,'record':record,
                       'resource_sha256':self.resource.resource_sha256,'state_revision':self._admission_revision}

    _word=staticmethod(AGIDOSMonitor._word)
    _owned_stop=staticmethod(AGIDOSMonitor._owned_stop)

    def _read(self,address,size):
        item=self.session.call('memory.read',{'address':{'space':'linear','offset':f'0x{address:08X}'},'length':size})
        result=base64.b64decode(item['data_base64'],validate=True)
        if len(result)!=size:raise ValueError('incomplete native read')
        return result

    def _segments(self,regs):
        if self._word(regs['segments']['cs'])!=self.cs or self._word(regs['segments']['ds'])!=self.ds:
            raise ValueError('print segment binding changed')

    def _check_engine(self):
        if AGIDOSMonitor._identity(self)!=self._session_identity or getattr(self.session,'closed',False):
            raise ValueError('native session identity changed')
        if hasattr(self.session,'layers') and self.session.layers()['active']:
            raise ValueError('active code layers are outside original profile')
        if sha256(self._read(self.cs*16,_ENGINE_LENGTH)).hexdigest()!=_ENGINE_SHA256:
            raise ValueError('unpacked interpreter fingerprint mismatch')

    def _check_binding(self):
        self._check_engine()
        if int.from_bytes(self._read(self.ds*16+0x979,2),'little')!=self.record:
            raise ValueError('current logic record changed')
        desc=self._read(self.ds*16+self.record,10)
        if desc[2]!=self.resource.logic or int.from_bytes(desc[4:6],'little')!=self.code_offset:
            raise ValueError('current logic descriptor changed')
        if self._read(self.ds*16+self.code_offset,len(self.resource.code))!=self.resource.code:
            raise ValueError('native logic binding changed')

    def _idle(self):
        state=self.session.keyboard_state();keys=state.get('keyboard',{})
        if any(type(keys.get(k)) is not int or keys[k]!=0 for k in ('pending_events','owned_keys','queued_guest_ms')):
            raise ValueError('keyboard input is not settled')
        return state

    def _modal(self):
        self._check_binding();r=self.session.registers();self._segments(r)
        if self._word(r['instruction_pointer'])!=DIALOGUE_WAIT:raise ValueError('not at original dialogue wait')
        ss=self._word(r['segments']['ss']);sp=self._word(r['general']['esp'])
        if sp>65527 or int.from_bytes(self._read(ss*16+sp+6,2),'little')!=0x1d25:
            raise ValueError('dialogue wait call frame differs')
        if not int.from_bytes(self._read(self.ds*16+0xd15,2),'little'):raise ValueError('dialogue window is not open')
        return r

    def readback(self):
        return deepcopy(self._report)

    def _check_admission(self):
        status=self.session.call('session.status')
        if status.get('state')!='stopped' or status.get('state_revision')!=self._admission_revision:
            raise ValueError('print admission state changed before execution')

    def finish(self,dialogue_key='enter',*,frame_name='agi-print',guest_ms=1000,timeout_ms=10000,total_guest_ms=10000,total_timeout_ms=60000):
        if self._report is not None:return self.readback()
        if dialogue_key not in ('enter','escape',None):raise ValueError('invalid dialogue key')
        if not isinstance(frame_name,str) or not frame_name or len(frame_name)>128:raise ValueError('invalid frame name')
        if any(type(v) is not int or not 1<=v<=limit for v,limit in ((guest_ms,10000),(timeout_ms,60000),(total_guest_ms,60000),(total_timeout_ms,600000))):raise ValueError('invalid observation budget')
        self._report={'format':'fdisbull-agi-print-observation-1','identity':deepcopy(self.identity),
            'logic':self.resource.logic,'source_offset':self.offset,'message_id':self.message_id,
            'message':deepcopy(self.message),'mode':self.mode,'status':'incomplete',
            'native_execution':False,'native_execution_attempted':False,'input_attempted':False,'handler_return_observed':False,
            'window_closed':False,'input_settled':False,'frame':None,'stops':[],'cleanup_errors':[]}
        report=self._report;live=[];deadline=time.monotonic()+total_timeout_ms/1000;remaining=total_guest_ms
        def create(point):
            bp=self.session.call('breakpoints.create',{'kind':'execution','once':False,'address':{'space':'segmented','segment':f'0x{self.cs:04X}','offset':f'0x{point:08X}'}})
            live.append(bp['breakpoint_id']);return bp['breakpoint_id']
        def remove(ident):
            self.session.call('breakpoints.delete',{'breakpoint_id':ident});live.remove(ident)
        def run(ms=None):
            nonlocal remaining
            wall=int((deadline-time.monotonic())*1000)
            if wall<=0 or remaining<=0:raise ValueError('native observation budget exhausted')
            report['native_execution_attempted']=True
            if report['native_execution'] is not True:report['native_execution']=None
            result=self.session.run(guest_ms=min(ms or guest_ms,remaining),timeout_ms=min(timeout_ms,wall),fast_forward=True,stop_on_hook=True)
            report['native_execution']=True;report['stops'].append(result)
            elapsed=result.get('guest_elapsed_ms')
            if type(elapsed) not in (int,float) or elapsed<0 or elapsed>remaining:raise ValueError('invalid native elapsed time')
            remaining-=elapsed
            return result
        try:
            self._check_admission()
            self._check_binding()
            r=self.session.registers();self._segments(r)
            if self._word(r['instruction_pointer'])!=_PRINT_HANDLER or self._word(r['segments']['ss'])!=self.ss or self._word(r['general']['esp'])!=self.sp or self._read(self.ss*16+self.sp,2)!=RETURN.to_bytes(2,'little'):
                raise ValueError('print admission became stale')
            si=self._word(r['general']['esi'])
            data=self._read(self.ds*16+9,0x102)
            if si!=self.code_offset+self.offset+1 or self._read(self.ds*16+si,1)!=bytes([self.message_id]) or bool(data[0x101]&1)!=self.output_mode or data[21]!=self.window_timer:
                raise ValueError('print operand or mode changed after admission')
            self._check_admission()
            if self.mode=='blocking':
                if dialogue_key is None:raise ValueError('blocking print requires a key')
                wait=create(DIALOGUE_WAIT);stop=run()
                if not self._owned_stop(stop,[wait]):raise ValueError('dialogue wait interrupted')
                report['waiting_registers']=self._modal();report['keyboard_before']=self.session.keyboard_state()
                first=self.session.screenshot(frame_name+'-initial.png',hooks=False)
                if not isinstance(first.get('artifact'),str) or not first['artifact']:raise ValueError('initial frame missing')
                remove(wait)
                # A parser Enter release can still be queued at the first wait.
                # Guard the original return while allowing the queue to settle;
                # never clear or modify existing input.
                preview_return=create(RETURN);preview=run(50)
                if self._owned_stop(preview,[preview_return]):
                    r=self.session.registers();self._segments(r)
                    report['handler_return_observed']=(self._word(r['instruction_pointer'])==RETURN and self._word(r['segments']['ss'])==self.ss and self._word(r['general']['esp'])==(self.sp+2)&65535)
                    raise ValueError('print handler returned before dialogue frame qualification')
                if preview.get('outcome')!='guest_time' or preview.get('guest_elapsed_ms',0)<50:raise ValueError('dialogue frame interval interrupted')
                remove(preview_return)
                if not int.from_bytes(self._read(self.ds*16+0xd15,2),'little'):raise ValueError('dialogue closed before input')
                fresh=self.session.screenshot(frame_name+'-waiting.png',hooks=False);a=first.get('metadata',{});b=fresh.get('metadata',{})
                if not isinstance(fresh.get('artifact'),str) or not fresh['artifact'] or type(a.get('frame_id')) is not int or type(b.get('frame_id')) is not int or b['frame_id']<=a['frame_id'] or type(a.get('mode_id')) is not int or type(b.get('mode_id')) is not int or a['mode_id']<0 or a['mode_id']!=b['mode_id']:
                    raise ValueError('fresh dialogue frame not qualified')
                report['frame']=fresh
                wait=create(DIALOGUE_WAIT);stop=run()
                if not self._owned_stop(stop,[wait]):raise ValueError('dialogue readiness interrupted')
                report['ready_registers']=self._modal();self._idle()
                if AGIDOSMonitor._message_identity(self,self.message_id)!=self.message:raise ValueError('native message identity changed')
                remove(wait)
                if int((deadline-time.monotonic())*1000)<=0 or remaining<=0:raise ValueError('native observation budget exhausted before input')
                ret=create(RETURN)
                if int((deadline-time.monotonic())*1000)<=0 or remaining<=0:raise ValueError('native observation budget exhausted before input')
                report['input_attempted']=True
                report['input']=self.session.keyboard_press(dialogue_key,hold_ms=1,gap_ms=1)
                if not isinstance(report['input'],dict) or report['input'].get('accepted') is not True:
                    raise ValueError('dialogue input was not accepted')
            else:
                ret=create(RETURN)
            stop=run()
            if not self._owned_stop(stop,[ret]):raise ValueError('print handler return interrupted')
            self._check_binding();r=self.session.registers();self._segments(r)
            if self._word(r['instruction_pointer'])!=RETURN or self._word(r['segments']['ss'])!=self.ss or self._word(r['general']['esp'])!=(self.sp+2)&65535:
                raise ValueError('print return frame differs')
            report['handler_return_observed']=True
            if self.mode=='blocking':
                if int.from_bytes(self._read(self.ds*16+0xd15,2),'little'):raise ValueError('dialogue window did not close')
                report['window_closed']=True;report['keyboard_after']=self._idle();report['input_settled']=True
            report['status']='completed'
        except Exception as exc:report['error']=str(exc)
        finally:
            while live:
                ident=live.pop()
                try:self.session.call('breakpoints.delete',{'breakpoint_id':ident})
                except Exception as exc:report['cleanup_errors'].append({'breakpoint_id':ident,'error':str(exc)})
            if report['cleanup_errors']:
                report['status']='incomplete';report['error']='breakpoint cleanup incomplete'
        return self.readback()
