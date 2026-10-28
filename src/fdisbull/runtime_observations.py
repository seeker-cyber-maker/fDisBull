"""Explicit, session-bound DOS runtime observations; no static mapping claims."""
import base64
from copy import deepcopy
import json
import re
import uuid

from .scene_values import ObservationReads, scalar_type


def _int(value, low, high, label):
    if type(value) is not int or not low <= value <= high: raise ValueError('Invalid '+label)
    return value


def _paused(session):
    status = session.call('session.status')
    if status.get('state') != 'stopped': raise ValueError('Runtime observation requires a paused guest')
    registers = session.call('state.get_registers')
    if registers.get('cpu_mode') != 'real': raise ValueError('Runtime observation requires real mode')
    return status


def _same_stop(before,after):
    for key in ('state_revision','frame_id','mode_id'):
        if key in before and key in after and before[key]!=after[key]:raise ValueError('Runtime observation '+key+' changed')


def _read(session, address, length):
    result=session.call('memory.read', {'address':{'space':'linear','offset':f'0x{address:08X}'},'length':length})
    data=base64.b64decode(result['data_base64'],validate=True)
    if len(data)!=length: raise ValueError('Incomplete runtime memory capture')
    return data


class RuntimeObservationMixin:
    def _runtime_state(self):
        if not hasattr(self,'_runtime_bindings'):
            self._runtime_bindings={};self._runtime_names={};self._runtime_epoch=uuid.uuid4().hex
        return self._runtime_bindings

    def _invalidate_runtime_bindings(self):
        self._runtime_state()
        self._runtime_bindings.clear();self._runtime_names.clear();self._runtime_epoch=uuid.uuid4().hex

    def bind_runtime_memory(self,name,address,*,length,expected_hex,mask_hex=None,provenance):
        self._runtime_state()
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}',name):raise ValueError('Invalid runtime binding name')
        if name in self._runtime_names:raise ValueError('Runtime binding name already exists')
        _int(address,0,0xfffff,'runtime linear address');_int(length,1,65536,'runtime binding length')
        if address+length>0x100000:raise ValueError('Runtime binding crosses real-mode linear limit')
        try:
            expected=bytes.fromhex(expected_hex);mask=bytes.fromhex(mask_hex) if mask_hex is not None else bytes([255])*len(expected)
        except (TypeError,ValueError):raise ValueError('Invalid identity witness') from None
        if not expected or len(expected)>length or len(mask)!=len(expected) or not any(mask):raise ValueError('Invalid identity witness')
        if not isinstance(provenance,(dict,list,str)) or not provenance:raise ValueError('Nonempty provenance required')
        if len(json.dumps(provenance,allow_nan=False,ensure_ascii=False).encode('utf-8'))>65536:raise ValueError('Runtime provenance exceeds 64 KiB')
        before=_paused(self)
        actual=_read(self,address,len(expected))
        _same_stop(before,_paused(self))
        if any((a&m)!=(b&m) for a,b,m in zip(actual,expected,mask,strict=True)):raise ValueError('Runtime identity witness mismatch')
        identity={'run':self.run_id,'version':self.version['id'],'runtime_load':self.runtime_load,'epoch':self._runtime_epoch,
                  'source_sha256':self.metadata.get('source_sha256'),'version_sha256':self.metadata.get('version_sha256')}
        binding=dict(id=uuid.uuid4().hex,name=name,address=address,length=length,expected_hex=expected.hex(),mask_hex=mask.hex(),provenance=deepcopy(provenance),identity=identity,witness_hex=actual.hex())
        self._runtime_bindings[binding['id']]=binding;self._runtime_names[name]=binding['id']
        self._event('runtime-memory-bind',binding)
        return deepcopy(binding)

    def runtime_memory(self,binding,*,offset=0,length=16):
        self._runtime_state()
        key=self._runtime_names.get(binding,binding)
        if key not in self._runtime_bindings:raise ValueError('Unknown or invalidated runtime binding')
        item=self._runtime_bindings[key];identity=item['identity']
        current={'run':self.run_id,'version':self.version['id'],'runtime_load':self.runtime_load,'epoch':self._runtime_epoch,
                 'source_sha256':self.metadata.get('source_sha256'),'version_sha256':self.metadata.get('version_sha256')}
        if current!=identity:raise ValueError('Runtime binding context changed')
        _int(offset,0,item['length']-1,'runtime view offset');_int(length,1,item['length'],'runtime view length')
        if offset+length>item['length']:raise ValueError('Runtime view exceeds binding')
        before=_paused(self)
        expected=bytes.fromhex(item['expected_hex']);mask=bytes.fromhex(item['mask_hex'])
        witness=_read(self,item['address'],len(expected))
        if any((a&m)!=(b&m) for a,b,m in zip(witness,expected,mask,strict=True)):raise ValueError('Runtime identity witness mismatch')
        data=_read(self,item['address']+offset,length)
        _same_stop(before,_paused(self))
        if self._runtime_epoch!=identity['epoch'] or self.run_id!=identity['run'] or self.version['id']!=identity['version'] or self.runtime_load!=identity['runtime_load'] or self.metadata.get('source_sha256')!=identity['source_sha256'] or self.metadata.get('version_sha256')!=identity['version_sha256']:
            raise ValueError('Runtime binding context changed')
        result={'binding':item['id'],'name':item['name'],'offset':offset,'length':length,'hex':data.hex(),
                'identity':dict(identity),'witness_hex':witness.hex(),'expected_hex':item['expected_hex'],'mask_hex':item['mask_hex']}
        self._event('runtime-memory-read',result)
        return result


def _path(value,path):
    if not isinstance(path,str) or not path:raise ValueError('Expected dotted observation path')
    for part in path.split('.'):
        if not isinstance(value,dict) or part not in value:raise ValueError('Missing observation path '+path)
        value=value[part]
    return value


def validate_observations(specs):
    from .scene_values import memory_ref, runtime_memory_ref
    if not isinstance(specs,dict) or not 1<=len(specs)<=16:raise ValueError('Expected 1..16 named observations')
    for name,spec in specs.items():
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}',name) or not isinstance(spec,dict) or len(spec)!=1:raise ValueError('Invalid named observation')
        kind,data=next(iter(spec.items()))
        if kind=='memory':memory_ref(data)
        elif kind=='runtime_memory':runtime_memory_ref(data)
        elif kind in ('register','status','frame'):
            if not isinstance(data,str) or not data:raise ValueError('Expected dotted observation path')
        else:raise ValueError('Unknown observation kind')
    return specs


def capture_observations(session,specs):
    validate_observations(specs)
    reads=ObservationReads(session);values={};errors={};context={}
    identity=lambda: (session.run_id, session.version['id'], getattr(session,'runtime_load',None), getattr(session,'_runtime_epoch',None), getattr(session,'closed',False))
    try:
        initial=identity();context={'run':session.run_id,'version':session.version['id'],'status':_paused(session)}
    except Exception as error:
        return {'values':{},'captures':[],'complete':False,'errors':{'context':str(error)},'context':context}
    regs=status=frame=None
    for name,spec in specs.items():
        try:
            if not isinstance(name,str) or not name or not isinstance(spec,dict) or len(spec)!=1:raise ValueError('Invalid named observation')
            kind,data=next(iter(spec.items()))
            if kind=='memory':
                from .scene_values import memory_ref
                memory_ref(data);values[name]=reads.scalar(data)
            elif kind=='runtime_memory':
                from .scene_values import runtime_memory_ref
                runtime_memory_ref(data);values[name]=reads.runtime_scalar(data)
            elif kind=='register':
                if regs is None:regs=session.registers()
                values[name]=_path(regs,data)
            elif kind=='status':
                if status is None:status=session.status()
                values[name]=_path(status,data)
            elif kind=='frame':
                if frame is None:frame=session.frame_probe([])
                values[name]=_path(frame,data)
            else:raise ValueError('Unknown observation kind')
        except Exception as error:errors[name]=str(error)
    try:
        final_status=_paused(session)
        if identity()!=initial:raise ValueError('Observation session context changed')
        for key in ('state_revision','frame_id','mode_id'):
            if key in context['status'] and key in final_status and context['status'][key]!=final_status[key]:raise ValueError('Observation '+key+' changed')
        context['end_status']=final_status
    except Exception as error:errors['context']=str(error)
    return {'values':values,'captures':list(reads.captures.values()),'complete':not errors,'errors':errors,'context':context}
