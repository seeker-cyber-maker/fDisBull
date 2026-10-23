"""Immutable experiment layers and explicit RAM versus instruction-fetch views."""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import uuid

from .debug_state import byte_string, apply_edits
from .dosbox_rpc import DebuggerError
from .external_files import _file_name

LAYER_DDL='''
CREATE TABLE IF NOT EXISTS debug_layers(
 id TEXT PRIMARY KEY,version INTEGER NOT NULL REFERENCES versions(id),name TEXT NOT NULL,
 kind TEXT NOT NULL,created TEXT NOT NULL,sha256 TEXT NOT NULL,document TEXT NOT NULL);
'''


def limit(value,name,low,high):
    if type(value) is not int or not low<=value<=high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def groups(values):
    """Group sparse byte maps into bounded contiguous RPC ranges."""
    result=[]
    for address in sorted(values):
        if not result or address!=result[-1][-1]+1:
            result.append([address])
        else:result[-1].append(address)
    if len(result)>256:raise ValueError('Layer transition exceeds 256 contiguous ranges')
    return result


def encode_chunks(before,after):
    return [{'address':part[0],
             'before':base64.b64encode(bytes(before[a] for a in part)).decode(),
             'after':base64.b64encode(bytes(after[a] for a in part)).decode()}
            for part in groups(after)]


class LayerProjectMixin:
    def debug_layer(self,name,*,kind,patches,version=None):
        from .project import now
        _file_name(name)
        if self.meta['format']!='MZ' or kind not in ('ram','execute'):
            raise ValueError('DOS layers require kind=ram or execute')
        if not isinstance(patches,list) or not 1<=len(patches)<=64:
            raise ValueError('A layer requires 1..64 guarded patches')
        v=self.version(version)['id']; normalized=[]; touched=set()
        for patch in patches:
            if not isinstance(patch,dict) or set(patch) not in (
                    {'address','expected_hex','data_hex'},{'address','cs','expected_hex','data_hex'}):
                raise ValueError('Layer patch requires address, expected_hex, data_hex, and optional cs')
            address,_=self._dos_parse_address(patch['address'],patch.get('cs'))
            before=byte_string(patch['expected_hex']);after=byte_string(patch['data_hex'])
            if len(before)!=len(after):raise ValueError('A layer cannot resize memory')
            if not any(r.start<=address and address+len(before)<=r.start+len(r.data) for r in self.regions(v)):
                raise ValueError('Layer patch must fit one mapped DOS allocation region')
            positions=set(range(address,address+len(before)))
            if touched&positions:raise ValueError('Patch ranges overlap inside one layer')
            touched.update(positions)
            if len(touched)>65536:raise ValueError('Layer exceeds 64 KiB')
            normalized.append({'address':hex(address),'expected_hex':before.hex(),'data_hex':after.hex()})
        document=json.dumps({'kind':kind,'patches':normalized},sort_keys=True,separators=(',',':'))
        identifier=uuid.uuid4().hex;digest=hashlib.sha256(document.encode()).hexdigest()
        with self.transaction(True):
            if self.db.execute('SELECT count(*) FROM debug_layers WHERE version=?',(v,)).fetchone()[0]>=256:
                raise ValueError('Project version already has 256 immutable layers')
            self.db.execute('INSERT INTO debug_layers VALUES (?,?,?,?,?,?,?)',
                            (identifier,v,name,kind,now(),digest,document))
        return {'layer':identifier,'version':v,'name':name,'kind':kind,'sha256':digest,'patches':normalized}

    def debug_layer_info(self,layer):
        row=self.db.execute('SELECT * FROM debug_layers WHERE id=?',(layer,)).fetchone()
        if row is None:raise ValueError('Unknown code layer')
        if hashlib.sha256(row['document'].encode()).hexdigest()!=row['sha256']:
            raise ValueError('Stored layer hash mismatch')
        return {k:row[k] for k in ('id','version','name','kind','created','sha256')}|json.loads(row['document'])

    def debug_layers(self,version=None):
        v=self.version(version)['id']
        return {'version':v,'layers':[dict(row) for row in self.db.execute(
            'SELECT id,version,name,kind,created,sha256 FROM debug_layers WHERE version=? ORDER BY rowid',(v,))]}

    def debug_events(self,run,*,after=0,limit=1000):
        if self.db.execute('SELECT 1 FROM debug_runs WHERE id=?',(run,)).fetchone() is None:
            raise ValueError('Unknown debugger run')
        if type(after) is not int or after<0:raise ValueError('after must be a nonnegative sequence')
        if type(limit) is not int or not 1<=limit<=10000:raise ValueError('limit must be 1..10000')
        return {'run':run,'events':[dict(row)|{'evidence':json.loads(row['evidence'])} for row in self.db.execute(
            'SELECT sequence,created,operation,evidence FROM debug_events WHERE run=? AND sequence>? ORDER BY sequence LIMIT ?',
            (run,after,limit))]}


class LayerSessionMixin:
    def _layer_setup(self):
        if not hasattr(self,'_layers'):
            self._layers=[];self._ram_base={};self._ram_applied={};self._hooks={};self._layer_generations={}
            self._layer_generation=0

    def _layer_address(self,address,cs=None,length=1):
        linear,selector=self.project._dos_parse_address(address,cs)
        if not any(r.start<=linear and linear+length<=r.start+len(r.data) for r in self.project.regions(self.version['id'])):
            raise ValueError('Address must fit the mapped DOS allocation')
        runtime=linear+self.delta
        if not 0<=runtime or runtime+length>0xa0000:
            raise ValueError('Code layers require unwrapped conventional RAM below 0xa0000')
        return linear,runtime,selector

    def _view(self,address,*,cs=None,length=16,view='ram'):
        self._layer_setup()
        limit(length,'length',1,65536)
        if view not in ('ram','execute'):raise ValueError('view must be ram or execute')
        linear,runtime,selector=self._layer_address(address,cs,length)
        result=self.call('memory.read',{'address':{'space':'linear','offset':f'0x{runtime:08X}'},'length':length,'view':view})
        data=base64.b64decode(result['data_base64'],validate=True)
        if len(data)!=length or hashlib.sha256(data).hexdigest()!=result['sha256']:
            raise DebuggerError('Runtime memory length/hash mismatch')
        if 'layer_generation' in result:
            self._layer_generation=result['layer_generation']
            self._layer_generations.setdefault(self._layer_generation,list(self._layers))
        result.update(hex=data.hex(),project_address=hex(linear),runtime_address=hex(runtime),view=view)
        return result

    def layers(self,active=None,*,conflict='stop'):
        self._layer_setup()
        if conflict not in ('stop','keep_changed') or (conflict!='stop' and active!=[]):
            raise ValueError('conflict=keep_changed is only valid when clearing all layers')
        if active is None:
            return {'run':self.run_id,'active':list(self._layers),'generation':self._layer_generation,
                    'layers':[self.project.debug_layer_info(i) for i in self._layers]}
        if not self.rpc.capabilities.get('code_layers'):
            raise DebuggerError('Backend lacks guarded instruction-fetch layers; build the layers backend')
        if not isinstance(active,list) or len(active)>64 or any(not isinstance(x,str) for x in active) or len(set(active))!=len(active):
            raise ValueError('Active stack requires at most 64 unique layer IDs')
        definitions=[self.project.debug_layer_info(i) for i in active]
        if any(d['version']!=self.version['id'] for d in definitions):
            raise ValueError('Layer belongs to a different static version')
        patches=[(d['kind'],p) for d in definitions for p in d['patches']]
        if len(patches)>256:raise ValueError('Active layers exceed 256 patches')
        expected={};ranges=set(self._ram_applied)
        for kind,patch in patches:
            start,runtime,_=self._layer_address(patch['address'],length=len(bytes.fromhex(patch['data_hex'])))
            for i,byte in enumerate(bytes.fromhex(patch['expected_hex'])):
                if start+i in expected and expected[start+i]!=byte:
                    raise ValueError('Overlapping layer definitions disagree about their base bytes')
                expected[start+i]=byte;ranges.add(start+i)
        if len(ranges)>65536:raise ValueError('Active transition exceeds 64 KiB')
        current={}
        for part in groups(ranges):
            data=bytes.fromhex(self._view(hex(part[0]),length=len(part))['hex'])
            current.update(zip(part,data))
        base=dict(current)
        preserved=[]
        for a,byte in self._ram_applied.items():
            if current[a]!=byte:
                if conflict=='stop':
                    raise ValueError('Active RAM layer conflicts with changed memory at '+hex(a)+'; capture it before rebasing')
                preserved.append({'address':hex(a),'layer_byte':byte,'observed_byte':current[a]})
            else:base[a]=self._ram_base[a]
        for a,byte in expected.items():
            if base[a]!=byte:raise ValueError('Layer expected base bytes mismatch at '+hex(a))
        physical=dict(base);ram_positions=set();execution={}
        for kind,patch in patches:
            if kind=='ram':
                start=int(patch['address'],16)
                for i,byte in enumerate(bytes.fromhex(patch['data_hex'])):
                    physical[start+i]=byte;ram_positions.add(start+i)
        for kind,patch in patches:
            if kind=='execute':
                start=int(patch['address'],16)
                for i,byte in enumerate(bytes.fromhex(patch['data_hex'])):execution[start+i]=byte
        write_positions=set(self._ram_applied)|ram_positions
        # Both views change in one emulation-thread command after full preflight.
        def runtime_map(values):return {a+self.delta:b for a,b in values.items()}
        writes={a:physical[a] for a in write_positions}
        params={'ram':encode_chunks(runtime_map(current),runtime_map(writes)),
                'execute':encode_chunks(runtime_map(physical),runtime_map(execution))}
        before=list(self._layers)
        try:result=self.call('layers.configure',params)
        except Exception as error:
            self._event('layer-transition-failed',{'active_before':before,'requested':active,'error':str(error)})
            if 'LAYER_PRECONDITION_FAILED' not in str(error):self.close()
            raise
        self._ram_base={a:base[a] for a in ram_positions}
        self._ram_applied={a:physical[a] for a in ram_positions}
        self._layers=list(active);self._layer_generation=result['generation']
        self._layer_generations[self._layer_generation]=list(active)
        evidence={'run':self.run_id,'active_before':before,'active':list(active),'generation':self._layer_generation,
                  'ram_bytes':len(ram_positions),'execution_bytes':len(execution),
                  'guest_instructions_during_transition':0,'preserved_changed_bytes':preserved,'backend':result}
        self._event('layer-transition',evidence)
        return evidence

    def layer_enable(self,layer,*,enabled=True):
        self._layer_setup()
        if type(enabled) is not bool:raise ValueError('enabled must be boolean')
        if self.project.debug_layer_info(layer)['version']!=self.version['id']:
            raise ValueError('Layer belongs to a different static version')
        active=[i for i in self._layers if i!=layer]
        if enabled:active.append(layer)
        return self.layers(active)

    def layer_patch(self,name,address,*,expected_hex,data_hex,kind='ram',activate=True):
        if type(activate) is not bool:raise ValueError('activate must be boolean')
        result=self.project.debug_layer(name,kind=kind,version=self.version['id'],patches=[
            {'address':address,'expected_hex':expected_hex,'data_hex':data_hex}])
        if activate:result['activation']=self.layer_enable(result['layer'])
        return result

    def code(self,address,*,cs=None,length=32,view='execute'):
        from iced_x86 import Decoder,Formatter,FormatterSyntax
        self._layer_setup()
        result=self._view(address,cs=cs,length=length,view=view)
        linear,runtime,selector=self._layer_address(address,cs,length)
        if selector is not None:segment=selector+self.runtime_load-self.dos['load_segment']
        else:
            registers=self.registers();segment=int(registers['cs'],16)
            if not 0<=runtime-segment*16<=65535:segment=runtime>>4
        ip=runtime-segment*16
        if not 0<=segment<=65535 or ip+length>0x10000:
            raise ValueError('Code view crosses a 16-bit segment boundary; supply the intended CS')
        formatter=Formatter(FormatterSyntax.NASM);instructions=[]
        for instruction in Decoder(16,bytes.fromhex(result['hex']),ip=ip):
            offset=instruction.ip-ip
            if instruction.is_invalid:break
            instructions.append({'runtime_address':hex(runtime+offset),'project_address':hex(linear+offset),
                'cs':hex(segment),'ip':hex(instruction.ip),'size':instruction.len,
                'bytes':bytes.fromhex(result['hex'])[offset:offset+instruction.len].hex(),
                'instruction':formatter.format(instruction)})
        result.update(instructions=instructions,active_layers=list(self._layers),generation=self._layer_generation,
                      evidence='runtime observation; static analysis is unchanged')
        return result

    def capture_code(self,address,*,cs=None,length=64,view='execute',name='code-view.json'):
        result=self.code(address,cs=cs,length=length,view=view)
        return self._artifact(name,'code-snapshot',json.dumps(result,indent=2).encode(),
                              {'view':view,'project_address':result['project_address'],
                               'generation':result['generation'],'active_layers':result['active_layers']})

    def branch(self,name,address,*,mode='invert',activate=True):
        if mode not in ('invert','taken','fallthrough'):raise ValueError('Branch mode must be invert, taken, or fallthrough')
        code=self.code(address,length=8)
        if not code['instructions']:raise ValueError('No decoded runtime branch')
        raw=bytes.fromhex(code['instructions'][0]['bytes'])
        if len(raw)==2 and 0x70<=raw[0]<=0x7f:
            replacement=bytes([raw[0]^1,raw[1]]) if mode=='invert' else bytes([0xeb,raw[1]]) if mode=='taken' else b'\x90\x90'
        elif len(raw)==4 and raw[0]==0x0f and 0x80<=raw[1]<=0x8f:
            replacement=(bytes([0x0f,raw[1]^1])+raw[2:] if mode=='invert' else
                b'\xe9'+struct.pack('<H',(int.from_bytes(raw[2:],'little')+1)&65535)+b'\x90' if mode=='taken' else b'\x90'*4)
        else:raise ValueError('Branch helper supports unprefixed 16-bit short/near Jcc instructions')
        linear=int(code['project_address'],16)
        base=bytes(self._ram_base.get(linear+i,b) for i,b in enumerate(bytes.fromhex(self._view(address,length=len(raw))['hex'])))
        return self.layer_patch(name,address,expected_hex=base.hex(),data_hex=replacement.hex(),kind='execute',activate=activate)

    def cave(self,name,*,address,code_hex,return_to,activate=False):
        body=byte_string(code_hex)
        _,target,_=self._layer_address(return_to)
        # A normalized far pointer, never the flat address's low word.
        jump=b'\xea'+struct.pack('<HH',target&15,target>>4)
        data=body+jump
        observed=self._view(address,length=len(data))
        linear=int(observed['project_address'],16)
        before=bytes(self._ram_base.get(linear+i,b) for i,b in enumerate(bytes.fromhex(observed['hex']))).hex()
        result=self.layer_patch(name,address,expected_hex=before,data_hex=data.hex(),kind='execute',activate=activate)
        result.update(return_runtime_linear=hex(target),far_jump_hex=jump.hex(),guest_ram_bytes_written=0)
        return result

    def hook(self,address,*,actions,once=True,max_hits=1,cs=None,access='x',length=1):
        self._layer_setup()
        if type(once) is not bool:raise ValueError('once must be boolean')
        limit(max_hits,'max_hits',1,1000)
        if not isinstance(actions,list) or not 1<=len(actions)<=16:raise ValueError('Hook requires 1..16 explicit actions')
        for action in actions:
            if not isinstance(action,dict):raise ValueError('Hook actions must be objects')
            if action.get('op')=='layers' and set(action)=={'op','layers'}:
                ids=action['layers']
                if not isinstance(ids,list) or len(ids)>64 or len(set(ids))!=len(ids):raise ValueError('Invalid hook layer stack')
                for i in ids:
                    if self.project.debug_layer_info(i)['version']!=self.version['id']:raise ValueError('Hook layer version mismatch')
            elif action.get('op')=='redirect' and set(action)=={'op','address'}:self._layer_address(action['address'])
            elif action.get('op')=='registers' and set(action)=={'op','registers'}:
                from .debug_state import validate_edits
                validate_edits([],action['registers'])
            else:raise ValueError('Hook action must set layers, redirect, or edit checked registers')
        bp=self.breakpoint(address,cs=cs,access=access,length=length,view='execute' if access=='x' else 'static')
        ids=[bp['breakpoint_id']] if access=='x' else [b['breakpoint_id'] for b in bp['breakpoints']]
        token=uuid.uuid4().hex
        control={'hook':token,'breakpoints':ids,'actions':json.loads(json.dumps(actions)),
                 'once':once,'max_hits':max_hits,'hits':0,'dispatch':'paused_rpc','extra_guest_bytes':0,'location':bp}
        for identifier in ids:self._hooks[identifier]=control
        self._event('hook-create',control)
        return control.copy()

    def hooks(self):
        self._layer_setup()
        return {'run':self.run_id,'hooks':list({h['hook']:h.copy() for h in self._hooks.values()}.values())}

    def delete_hook(self,hook):
        self._layer_setup()
        control=next((h for h in self._hooks.values() if h['hook']==hook),None)
        if control is None:raise ValueError('Unknown live hook')
        for bp in control['breakpoints']:
            if bp in self._hooks:
                self.call('breakpoints.delete',{'breakpoint_id':bp});self._hooks.pop(bp,None)
        self._event('hook-delete',{'hook':hook})
        return {'hook':hook,'deleted':True}

    def _dispatch_hook(self,result):
        self._layer_setup()
        if result.get('stop_reason',{}).get('kind')!='breakpoint':return None
        identifier=result.get('stop_reason',{}).get('breakpoint_id')
        control=self._hooks.get(identifier)
        if control is None:return None
        evidence={'hook':control['hook'],'hit':control['hits']+1,'stop':result,'actions':[],
                  'dispatch':'paused_rpc','extra_guest_bytes':0}
        try:
            control['hits']+=1
            if control['once'] or control['hits']>=control['max_hits']:
                for bp in control['breakpoints']:
                    if bp in self._hooks:
                        self.call('breakpoints.delete',{'breakpoint_id':bp});self._hooks.pop(bp,None)
            for action in control['actions']:
                if action['op']=='layers':change=self.layers(action['layers'])
                elif action['op']=='registers':change=apply_edits(self,[],action['registers'])
                else:
                    _,target,_=self._layer_address(action['address'])
                    segment,offset=target>>4,target&15
                    self.call('state.set_register',{'register':'CS','value':segment})
                    self.call('state.set_register',{'register':'EIP','value':offset})
                    actual=self.registers()
                    if int(actual['cs'],16)*16+int(actual['ip'],16)!=target:raise DebuggerError('Hook redirect readback mismatch')
                    change={'runtime_linear':hex(target),'cs':hex(segment),'ip':hex(offset)}
                evidence['actions'].append({'op':action['op'],'result':change})
            self._event('hook-hit',evidence)
        except BaseException as error:
            self._event('hook-failed',evidence|{'error':str(error)})
            self.close() # A partial multi-action hook is never silently resumed.
            raise
        return evidence

    def _layer_state(self):
        self._layer_setup()
        return {'active':list(self._layers),'ram_base':{hex(a):b for a,b in self._ram_base.items()},
                'ram_applied':{hex(a):b for a,b in self._ram_applied.items()}}

    def _restore_layer_state(self,state):
        self._layer_setup()
        if not isinstance(state,dict) or set(state)-{'active','ram_base','ram_applied'}:
            raise ValueError('Invalid stored layer state')
        for name in ('ram_base','ram_applied'):
            values=state.get(name,{})
            if not isinstance(values,dict) or len(values)>65536 or any(
                    not isinstance(a,str) or not a.startswith('0x') or type(b) is not int or not 0<=b<=255 for a,b in values.items()):
                raise ValueError('Invalid stored RAM layer bytes')
        if set(state.get('ram_base',{}))!=set(state.get('ram_applied',{})):
            raise ValueError('Stored RAM layer base/applied addresses disagree')
        self._layers=[]
        self._ram_base={int(a,16):b for a,b in state.get('ram_base',{}).items()}
        self._ram_applied={int(a,16):b for a,b in state.get('ram_applied',{}).items()}
        active=state.get('active',[])
        if active or self._ram_applied:self.layers(active)
        else:self._view(hex(self.static_base),length=1)

    def _layer_trace(self,events):
        from iced_x86 import Decoder,Formatter,FormatterSyntax
        self._layer_setup();formatter=Formatter(FormatterSyntax.NASM)
        for event in events:
            if event.get('execution_bytes'):
                instruction=Decoder(16,bytes.fromhex(event['execution_bytes']),ip=int(event['address']['offset'],16)).decode()
                event['native_instruction']=event['instruction']
                event['instruction']=formatter.format(instruction)
                event['instruction_view']='execute'
                event['active_layers']=self._layer_generations.get(event.get('layer_generation'),[])
