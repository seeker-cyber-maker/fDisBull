"""PE64 guarded layer stacks and explicit RAM/execution code observations."""
from __future__ import annotations

import base64
import hashlib
import struct

from .code_layers import LayerSessionMixin, groups
from .dosbox_rpc import DebuggerError


class PELayerSessionMixin(LayerSessionMixin):
    def _layer_setup(self):
        super()._layer_setup()
        if not hasattr(self,'_execution'):
            self._execution={};self._execute_guards={};self._pending_exec=None;self._scratch=None

    def _layer_address(self,address,cs=None,length=1):
        if cs is not None:raise ValueError('PE64 layer addresses are flat')
        value=self._address(address,length)
        return value,value+self.delta,None

    def _view(self,address,*,cs=None,length=16,view='ram'):
        self._layer_setup()
        if view not in ('ram','execute'):raise ValueError('view must be ram or execute')
        if cs is not None:raise ValueError('PE64 layer addresses are flat')
        result=self.memory(address,length=length);raw=bytes.fromhex(result['hex'])
        value=int(result['project_address'],16);data=bytearray(raw)
        if view=='execute':
            for i,byte in enumerate(raw):
                if value+i in self._execution:
                    if byte!=self._execute_guards[value+i]:raise DebuggerError('Execution layer RAM guard changed at '+hex(value+i))
                    data[i]=self._execution[value+i]
        result.update(hex=data.hex(),ram_hex=raw.hex(),data_base64=base64.b64encode(data).decode(),
                      sha256=hashlib.sha256(data).hexdigest(),view=view,layer_generation=self._layer_generation)
        return result

    def _configure_pe_layers(self,params):
        self._layer_setup()
        if self._pending_exec:raise ValueError('LAYER_PRECONDITION_FAILED: Finish the pending execution-layer instruction before changing layers')
        writes=[];execution={};guards={}
        for kind in ('ram','execute'):
            for chunk in params[kind]:
                before=base64.b64decode(chunk['before'],validate=True);after=base64.b64decode(chunk['after'],validate=True)
                if not before or len(before)!=len(after):raise ValueError('Invalid layer transition chunk')
                address=chunk['address']-self.delta;self._address(address,len(before),executable=kind=='execute')
                if any(address<=bp<address+len(before) for bp in self.breakpoints.values()):
                    raise ValueError('LAYER_PRECONDITION_FAILED: Delete overlapping execution breakpoints before changing a code layer')
                if kind=='ram':
                    if self.memory(address,length=len(before))['hex']!=before.hex():raise ValueError('Layer transition guard changed')
                    writes.append((address,after))
                else:
                    execution.update({address+i:b for i,b in enumerate(after)})
                    guards.update({address+i:b for i,b in enumerate(before)})
        ranges=groups(execution)
        if len(ranges)>64:raise ValueError('PE execution layers exceed 64 guarded ranges')
        # The Win32 debug event holds every target thread throughout this transition.
        self.rpc.call('overlay',{'ranges':[]})
        for address,data in writes:
            self.rpc.call('write',{'address':address+self.delta,'data_hex':data.hex()})
            if self.memory(address,length=len(data))['hex']!=data.hex():raise DebuggerError('Layer write readback mismatch')
        for part in groups(guards):
            if self.memory(part[0],length=len(part))['hex']!=bytes(guards[a] for a in part).hex():
                raise DebuggerError('Execution layer precondition changed')
        self.rpc.call('overlay',{'ranges':[{'address':part[0]+self.delta,'length':len(part)} for part in ranges]})
        self._execution=execution;self._execute_guards=guards
        return {'generation':self._layer_generation+1,'mechanism':'paused Win32 edits; guarded relocated execution',
                'execution_buffer_bytes':4096 if execution else 0,'target_instructions_during_transition':0}

    def code(self,address,*,cs=None,length=32,view='execute'):
        from iced_x86 import Decoder
        observed=self._view(address,cs=cs,length=length,view=view)
        runtime=int(observed['runtime_address'],16);value=int(observed['project_address'],16);raw=bytes.fromhex(observed['hex'])
        instructions=[]
        for instruction in Decoder(64,raw,ip=runtime):
            if instruction.is_invalid:break
            offset=instruction.ip-runtime
            instructions.append({'runtime_address':hex(instruction.ip),'project_address':hex(value+offset),
                                 'size':instruction.len,'bytes':raw[offset:offset+instruction.len].hex(),'instruction':str(instruction)})
        return observed|{'instructions':instructions,'active_layers':list(self._layers),'generation':self._layer_generation,
                         'evidence':'runtime observation; static instructions and xrefs are unchanged'}

    def branch(self,name,address,*,mode='invert',activate=True):
        if mode not in ('invert','taken','fallthrough'):raise ValueError('Invalid branch mode')
        observed=self.code(address,length=8)
        if not observed['instructions']:raise ValueError('No decoded branch')
        raw=bytes.fromhex(observed['instructions'][0]['bytes'])
        if len(raw)==2 and 0x70<=raw[0]<=0x7f:
            data=bytes([raw[0]^1,raw[1]]) if mode=='invert' else bytes([0xeb,raw[1]]) if mode=='taken' else b'\x90'*2
        elif len(raw)==6 and raw[0]==0x0f and 0x80<=raw[1]<=0x8f:
            data=bytes([0x0f,raw[1]^1])+raw[2:] if mode=='invert' else (
                b'\xe9'+struct.pack('<i',int.from_bytes(raw[2:],'little',signed=True)+1)+b'\x90' if mode=='taken' else b'\x90'*6)
        else:raise ValueError('PE branch helper requires an unprefixed short/near Jcc')
        value=int(observed['project_address'],16)
        base=bytes(self._ram_base.get(value+i,b) for i,b in enumerate(bytes.fromhex(self._view(address,length=len(raw))['hex'])))
        return self.layer_patch(name,address,expected_hex=base.hex(),data_hex=data.hex(),kind='execute',activate=activate)

    def _unsupported(self,*args,**kwargs):
        raise ValueError('PE64 does not implement DOS virtual caves or breakpoint action hooks')
    cave=hook=hooks=delete_hook=_unsupported
