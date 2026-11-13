"""Complete real PE instructions, including guarded relocated execution layers."""
from __future__ import annotations

import base64
import time

from iced_x86 import BlockEncoder, Decoder, FlowControl

from .dosbox_rpc import DebuggerError
from .wine_watch import access_facts, check_fetch_watch_alias
from .wine_arch import instruction_pointer, ip_name, validate_context


class PEExecutionMixin:
    def _native_registers(self):
        """Validate the actual flat process context before decoding or execution.

        Public registers may rewrite a pending layer's scratch PC. Execution
        needs the raw PC, with the same architecture/selector checks.
        """
        result=self.call('registers')
        if hasattr(self,'bits'):
            try:
                validate_context(result,self.bits)
                if self.bits==32 and int(result.get('cs','0x0'),16)&4:
                    raise DebuggerError('Observed segmented context requires the Win16 NE adapter; PE32 addresses remain flat')
            except Exception:
                self.close();raise
        return result

    def _cpu_code(self,rip):
        return base64.b64decode(self.call('code',{'address':rip})['data_base64'],validate=True)

    def _overlay_at(self,registers):
        self._layer_setup();rip=int(instruction_pointer(registers),16);address=rip-self.delta
        if not any(address+i in self._execution for i in range(15)):return None
        raw=self._cpu_code(rip);data=bytearray(raw)
        for i,byte in enumerate(raw):
            if address+i in self._execution:
                if byte!=self._execute_guards[address+i]:raise DebuggerError('Execution layer RAM guard changed before execution')
                data[i]=self._execution[address+i]
        instruction=Decoder(getattr(self,'bits',64),bytes(data),ip=rip).decode()
        if instruction.is_invalid:raise DebuggerError('Execution layer decodes an invalid instruction')
        if bytes(data[:instruction.len])==raw[:instruction.len]:return None
        return raw,bytes(data),instruction

    def _start_overlay(self,registers,observed):
        raw,data,instruction=observed
        if instruction.flow_control not in (FlowControl.NEXT,FlowControl.CONDITIONAL_BRANCH,
                                             FlowControl.UNCONDITIONAL_BRANCH,FlowControl.INDIRECT_BRANCH):
            raise ValueError('PE execution overlays currently require ordinary instructions or Jcc/JMP; calls/returns are unsupported')
        if self._scratch is None:self._scratch=int(self.call('scratch')['address'],16)
        encoder=BlockEncoder(getattr(self,'bits',64));encoder.add(instruction)
        encoded=encoder.encode(self._scratch)
        physical=Decoder(getattr(self,'bits',64),encoded,ip=self._scratch).decode()
        if physical.is_invalid or physical.len!=len(encoded):
            raise ValueError('Execution overlay requires a single relocatable physical instruction')
        self.call('write',{'address':self._scratch,'data_hex':encoded.hex()})
        self._pending_exec={'before':registers,'raw':raw,'execution':data,'instruction':instruction,
                            'scratch':self._scratch,'encoded':encoded,'next':instruction.next_ip}
        self.call('setregs',{'values':{ip_name(registers):self._scratch}})
        # Fetch now happens in the private buffer: re-arm source RAM so even an
        # alternate instruction's data read of its own original bytes is watched.
        self.call('guard-arm')

    def _finish_overlay(self):
        pending=self._pending_exec;registers=self._native_registers();rip=int(instruction_pointer(registers),16)
        if rip==pending['scratch']+len(pending['encoded']):
            self.call('setregs',{'values':{ip_name(registers):pending['next']}})
        self._pending_exec=None

    def _watch_stop(self,state):
        stop=state['stop_reason']
        if stop['kind']!='memory-access':return False
        registers=self._native_registers();rip=int(instruction_pointer(registers),16)
        if stop['access_code']==8:
            try:
                check_fetch_watch_alias(self._cpu_code(rip),registers,int(stop['access_address'],16),
                                        [(w['address']+self.delta,w['address']+self.delta+w['length']) for w in self.watchpoints.values()])
            except ValueError:
                self.close();raise
            return False
        try: facts=access_facts(self._cpu_code(rip),registers,int(stop['access_address'],16),stop['access_code'])
        except ValueError:
            self.close();raise
        matches=[]
        for identifier,watch in self.watchpoints.items():
            low=watch['address']+self.delta;high=low+watch['length']
            if any(item['address']<high and low<item['address']+item['length'] and
                   (item['read'] and 'r' in watch['access'] or item['write'] and 'w' in watch['access']) for item in facts['ranges']):
                matches.append(identifier)
        if not matches:return False
        stop.update(kind='watchpoint',breakpoint_ids=matches,access_facts=facts,registers=self.registers())
        if self._pending_exec:
            stop.update(native_address=stop['address'],address=instruction_pointer(self._pending_exec['before']))
        return True

    def _timeout_state(self):
        state=self.call('status')
        state['stop_reason'].update(native_kind=state['stop_reason']['kind'],kind='timeout')
        return state

    def _step_instruction(self,deadline):
        """Return an event only after its real (possibly relocated) instruction completes."""
        self._layer_setup()
        if self._pending_exec:
            pending=self._pending_exec;before=pending['before'];raw=pending['raw'];executed=pending['execution']
        else:
            before=self._native_registers();rip=int(instruction_pointer(before),16);raw=self._cpu_code(rip);executed=raw
            observed=self._overlay_at(before)
            if observed:
                self._start_overlay(before,observed);executed=observed[1]
        while True:
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:return None,self._timeout_state()
            state=self.call('step',{'timeout_ms':remaining},timeout_ms=remaining+15000)
            kind=state['stop_reason']['kind']
            if kind=='memory-access':
                if self._watch_stop(state):return None,state
                if state['stop_reason']['access_code']==8 and not self._pending_exec:
                    observed=self._overlay_at(self._native_registers())
                    if observed:self._start_overlay(before,observed);executed=observed[1]
                continue
            if kind!='step':return None,state
            instruction=Decoder(getattr(self,'bits',64),executed,ip=int(instruction_pointer(before),16)).decode()
            if instruction.is_invalid:raise DebuggerError('Completed instruction could not be decoded')
            event={'address':instruction_pointer(before),'bytes':executed[:instruction.len].hex(),'registers':before,
                   'ram_bytes':raw[:instruction.len].hex(),'execution_bytes':executed[:instruction.len].hex(),
                   'active_layers':list(self._layers),'layer_generation':self._layer_generation}
            if self._pending_exec:
                event['native_address']=hex(self._pending_exec['scratch']);event['native_bytes']=self._pending_exec['encoded'].hex()
                self._finish_overlay();state=self.call('status')
            return event,state

    def _continue_native(self,deadline,*,native_method='run'):
        self._layer_setup()
        while True:
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:return self._timeout_state()
            registers=self._native_registers()
            if self._pending_exec or self._execution and self._overlay_at(registers):
                _,state=self._step_instruction(deadline)
            else:state=self.call(native_method,{'timeout_ms':remaining},timeout_ms=remaining+15000)
            kind=state['stop_reason']['kind']
            if kind=='memory-access':
                if self._watch_stop(state):return state
                _,state=self._step_instruction(deadline)
                kind=state['stop_reason']['kind']
            if kind!='step':return state

    def _trace_native(self,count,deadline):
        events=[];state=self.call('status')
        while len(events)<count and time.monotonic()<deadline:
            event,state=self._step_instruction(deadline)
            if event is None:break
            events.append(event)
            rip=int(instruction_pointer(self._native_registers()),16)
            if rip in self.breakpoints.values():
                state=self.call('bp-check');break
        return {'events':events,'complete':len(events)==count,'session':state}
