"""Explicit, session-bound runtime observations; no inferred source mappings."""
import base64
from copy import deepcopy
import hashlib
import json
import re
import uuid

from .scene_values import ObservationReads, scalar_type
from .debug_timeline import timeline_locked


def _int(value, low, high, label):
    if type(value) is not int or not low <= value <= high: raise ValueError('Invalid '+label)
    return value


def _paused(session):
    backend=getattr(session,'backend_name',None)
    windows=backend in ('wine-qemu','wine-ne-qemu','ida-wine-qemu')
    status = session.status() if windows else session.call('session.status')
    if status.get('state') != 'stopped': raise ValueError('Runtime observation requires a paused guest')
    registers = session.registers() if windows else session.call('state.get_registers')
    mode=registers.get('cpu_mode')
    modes=('protected16','protected32','long64') if windows else ('real','v86','protected')
    if backend=='wine-ne-qemu':modes=(*modes,'protected32-carrier')
    if mode not in modes:raise ValueError('Runtime observation has an unknown CPU mode')
    return {**status,'observation_cpu_mode':mode,
            'observation_address_context':deepcopy(registers.get('address_context'))}


def _memory_context(status,space):
    """Physical RAM has no CPU translation; linear bindings pin observed paging.

    A paged linear allocation needs page-translation provenance beyond CR3.
    Keep that case explicit instead of guessing a process/selector identity.
    """
    if space not in ('linear','physical'):raise ValueError('Runtime address space must be linear or physical')
    if space=='physical':return {'space':'physical','translation':'physical RAM; no DOS paragraph or CPU paging translation'}
    mode=status['observation_cpu_mode'];context=status.get('observation_address_context')
    if mode=='real' and context is None:return {'space':'linear','cpu_mode':'real','context':'legacy real-mode backend'}
    required={'cpu_mode','paging_enabled','cr0','cr3','cr4','a20_enabled','code_bits','stack_bits'}
    if not isinstance(context,dict) or not required<=set(context):
        raise ValueError('Protected/v86 linear bindings require observed address_context; rebuild the backend or choose explicit physical RAM')
    if context['cpu_mode']!=mode or type(context['paging_enabled']) is not bool or type(context['a20_enabled']) is not bool:
        raise ValueError('Invalid observed runtime address context')
    try:
        if any(not isinstance(context[name],str) or not re.fullmatch(r'0x[0-9a-fA-F]{1,8}',context[name]) for name in ('cr0','cr3','cr4')):
            raise ValueError('Invalid control register encoding')
        controls={name:int(context[name],16) for name in ('cr0','cr3','cr4')}
    except (TypeError,ValueError):raise ValueError('Invalid observed runtime control registers') from None
    if any(not 0<=value<=0xffffffff for value in controls.values()) or bool(controls['cr0']&0x80000000)!=context['paging_enabled']:
        raise ValueError('Inconsistent observed runtime paging context')
    if bool(controls['cr0']&1)!=(mode in ('protected','v86')) or context['code_bits'] not in (16,32) or context['stack_bits'] not in (16,32):
        raise ValueError('Inconsistent observed runtime CPU context')
    if context['paging_enabled']:
        raise ValueError('Paged linear bindings require qualified page mappings; use an explicitly observed physical RAM address')
    return {'space':'linear','cpu_mode':mode,'paging_enabled':False,'a20_enabled':context['a20_enabled']}


def _same_stop(before,after):
    for key in ('state_revision','frame_id','mode_id','observation_cpu_mode','observation_address_context'):
        if key in before and key in after and before[key]!=after[key]:raise ValueError('Runtime observation '+key+' changed')


def _read(session, address, length, space='linear'):
    result=session.call('memory.read', {'address':{'space':space,'offset':f'0x{address:08X}'},'length':length})
    data=base64.b64decode(result['data_base64'],validate=True)
    if len(data)!=length: raise ValueError('Incomplete runtime memory capture')
    return data


class RuntimeMemoryWriteError(RuntimeError):
    """A dispatched live write failed verification; the owned guest is closed."""
    def __init__(self,receipt,error):
        self.result=receipt
        super().__init__('Runtime RAM edit outcome requires inspection: '+str(error))


class RuntimeObservationMixin:
    def _runtime_state(self):
        if getattr(self,'backend_name',None) in ('wine-qemu','wine-ne-qemu','ida-wine-qemu'):
            raise ValueError('DOS runtime RAM bindings do not apply to Windows; use the adapter\'s source/selector-qualified memory interface')
        if not hasattr(self,'_runtime_bindings'):
            self._runtime_bindings={};self._runtime_names={};self._runtime_epoch=uuid.uuid4().hex
        return self._runtime_bindings

    def _invalidate_runtime_bindings(self):
        self._runtime_state()
        self._runtime_bindings.clear();self._runtime_names.clear();self._runtime_epoch=uuid.uuid4().hex

    @timeline_locked
    def bind_runtime_memory(self,name,address,*,length,expected_hex,mask_hex=None,provenance,space='linear'):
        self._runtime_state()
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}',name):raise ValueError('Invalid runtime binding name')
        if name in self._runtime_names:raise ValueError('Runtime binding name already exists')
        _int(address,0,0xffffffff,'runtime address');_int(length,1,65536,'runtime binding length')
        if address+length>0x100000000:raise ValueError('Runtime binding crosses the 32-bit address limit')
        try:
            expected=bytes.fromhex(expected_hex);mask=bytes.fromhex(mask_hex) if mask_hex is not None else bytes([255])*len(expected)
        except (TypeError,ValueError):raise ValueError('Invalid identity witness') from None
        if not expected or len(expected)>length or len(mask)!=len(expected) or not any(mask):raise ValueError('Invalid identity witness')
        if not isinstance(provenance,(dict,list,str)) or not provenance:raise ValueError('Nonempty provenance required')
        if len(json.dumps(provenance,allow_nan=False,ensure_ascii=False).encode('utf-8'))>65536:raise ValueError('Runtime provenance exceeds 64 KiB')
        before=_paused(self)
        domain=_memory_context(before,space)
        if space=='linear' and before['observation_cpu_mode']=='real' and address+length>0x100000:
            raise ValueError('Runtime binding crosses real-mode linear limit')
        actual=_read(self,address,len(expected),space)
        _same_stop(before,_paused(self))
        if any((a&m)!=(b&m) for a,b,m in zip(actual,expected,mask,strict=True)):raise ValueError('Runtime identity witness mismatch')
        identity={'run':self.run_id,'version':self.version['id'],'runtime_load':self.runtime_load,'epoch':self._runtime_epoch,
                  'source_sha256':self.metadata.get('source_sha256'),'version_sha256':self.metadata.get('version_sha256'),
                  'memory_context':domain}
        binding=dict(id=uuid.uuid4().hex,name=name,address=address,space=space,length=length,expected_hex=expected.hex(),mask_hex=mask.hex(),provenance=deepcopy(provenance),identity=identity,witness_hex=actual.hex(),
                     observed_cpu_mode=before['observation_cpu_mode'],mapping_claim='explicit runtime RAM witness; no static source or selector inference')
        self._runtime_bindings[binding['id']]=binding;self._runtime_names[name]=binding['id']
        self._event('runtime-memory-bind',binding)
        return deepcopy(binding)

    @timeline_locked
    def runtime_memory(self,binding,*,offset=0,length=16):
        self._runtime_state()
        key=self._runtime_names.get(binding,binding)
        if key not in self._runtime_bindings:raise ValueError('Unknown or invalidated runtime binding')
        item=self._runtime_bindings[key];identity=item['identity']
        before=_paused(self)
        current={'run':self.run_id,'version':self.version['id'],'runtime_load':self.runtime_load,'epoch':self._runtime_epoch,
                 'source_sha256':self.metadata.get('source_sha256'),'version_sha256':self.metadata.get('version_sha256')}
        current['memory_context']=_memory_context(before,item.get('space','linear'))
        if current!=identity:raise ValueError('Runtime binding context changed')
        _int(offset,0,item['length']-1,'runtime view offset');_int(length,1,item['length'],'runtime view length')
        if offset+length>item['length']:raise ValueError('Runtime view exceeds binding')
        expected=bytes.fromhex(item['expected_hex']);mask=bytes.fromhex(item['mask_hex'])
        witness=_read(self,item['address'],len(expected),item.get('space','linear'))
        if any((a&m)!=(b&m) for a,b,m in zip(witness,expected,mask,strict=True)):raise ValueError('Runtime identity witness mismatch')
        data=_read(self,item['address']+offset,length,item.get('space','linear'))
        _same_stop(before,_paused(self))
        if self._runtime_epoch!=identity['epoch'] or self.run_id!=identity['run'] or self.version['id']!=identity['version'] or self.runtime_load!=identity['runtime_load'] or self.metadata.get('source_sha256')!=identity['source_sha256'] or self.metadata.get('version_sha256')!=identity['version_sha256']:
            raise ValueError('Runtime binding context changed')
        result={'binding':item['id'],'name':item['name'],'offset':offset,'length':length,'hex':data.hex(),
                'identity':dict(identity),'witness_hex':witness.hex(),'expected_hex':item['expected_hex'],'mask_hex':item['mask_hex']}
        self._event('runtime-memory-read',result)
        return result

    @timeline_locked
    def write_runtime_memory(self,binding,data_hex,*,expected_hex,offset=0):
        """Guard and verify a live RAM edit without saving or restoring a state."""
        from .debug_state import byte_string
        data=byte_string(data_hex);expected=byte_string(expected_hex)
        if len(data)!=len(expected):raise ValueError('Runtime RAM edits cannot resize a binding')
        observed=self.runtime_memory(binding,offset=offset,length=len(data))
        if observed['hex']!=expected.hex():raise ValueError('Runtime RAM edit expected bytes mismatch; write refused')
        layers=getattr(self,'_layer_state',None)
        if callable(layers) and layers().get('active'):
            raise ValueError('Disable code layers before an explicit runtime RAM edit')
        item=self._runtime_bindings[observed['binding']]
        address={'space':item.get('space','linear'),'offset':f'0x{item["address"]+offset:08X}'}
        before=_paused(self)
        if _memory_context(before,address['space'])!=item['identity']['memory_context']:
            raise ValueError('Runtime RAM edit address context changed; write refused')
        receipt={'kind':'live-runtime-ram-edit','run':self.run_id,'binding':item['id'],
                 'address':address,'length':len(data),'state_restore_used':False,
                 'before_hex':expected.hex(),'after_hex':None,'verified':False,'dispatch_outcome':'unknown'}
        self._event('runtime-memory-write-attempt',receipt)
        try:
            self.call('memory.write',{'address':address,'expected_sha256':hashlib.sha256(expected).hexdigest(),
                                      'data_base64':base64.b64encode(data).decode()})
            actual=_read(self,item['address']+offset,len(data),address['space'])
            after=_paused(self)
            if (_memory_context(after,address['space'])!=item['identity']['memory_context']
                    or after['observation_cpu_mode']!=before['observation_cpu_mode']
                    or after['observation_address_context']!=before['observation_address_context']
                    or actual!=data):
                raise ValueError('Runtime RAM edit readback or address context mismatch')
            current_identity={'epoch':self._runtime_epoch,'run':self.run_id,
                              'version':self.version['id'],'runtime_load':self.runtime_load,
                              'source_sha256':self.metadata.get('source_sha256'),
                              'version_sha256':self.metadata.get('version_sha256')}
            if any(item['identity'][key]!=value for key,value in current_identity.items()) or item['id'] not in self._runtime_bindings:
                raise ValueError('Runtime RAM binding changed during the write')
            witness=_read(self,item['address'],len(bytes.fromhex(item['expected_hex'])),address['space'])
            mask=bytes.fromhex(item['mask_hex']);identity=bytes.fromhex(item['expected_hex'])
            valid=not any((a&m)!=(b&m) for a,b,m in zip(witness,identity,mask,strict=True))
        except BaseException as error:
            receipt.update(error_type=type(error).__name__,error=str(error))
            try:self._event('runtime-memory-write-unknown',receipt)
            finally:
                try:self.close()
                finally:raise RuntimeMemoryWriteError(receipt,error) from error
        if not valid:
            del self._runtime_bindings[item['id']];self._runtime_names.pop(item['name'],None)
        receipt.update(after_hex=actual.hex(),verified=True,dispatch_outcome='readback-verified',
                       binding_invalidated=not valid,frame_presentation_verified=False)
        self._event('runtime-memory-write',receipt)
        return receipt


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
        _same_stop(context['status'],final_status)
        context['end_status']=final_status
    except Exception as error:errors['context']=str(error)
    return {'values':values,'captures':list(reads.captures.values()),'complete':not errors,'errors':errors,'context':context}
