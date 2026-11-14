"""Stopped, guarded flat CHIP-8 RAM and native fetch layer stacks."""
from .code_layers import groups
from .debug_state import byte_string
from .dosbox_rpc import DebuggerError

LAYER_MODEL='fdisbull-chip8-native-layers-1'
SIZE=4096


class _LayerPrecondition(Exception):
    pass


def _address(address,length):
    try:value=int(address,0) if isinstance(address,str) else address
    except ValueError:raise ValueError('Invalid CHIP-8 layer address') from None
    if type(value) is not int or type(length) is not int or length<1 or value<0 or value+length>SIZE:
        raise ValueError('CHIP-8 layer extent must fit 4 KiB')
    return value


def _chunks(before,after):
    return [dict(address=span[0],**{'expected-hex':bytes(before[a] for a in span).hex(),
                                    'data-hex':bytes(after[a] for a in span).hex()}) for span in groups(after)]


class Chip8LayerMixin:
    def _reset_chip8_layers(self):
        self._layer_active=[];self._layer_generation=0;self._layer_ram_base={};self._layer_ram_applied={}

    def _chip8_layer_query(self):
        info=self.vm.qmp.call('query-chip8-layers')
        if not isinstance(info,dict) or info.get('model')!=LAYER_MODEL:
            raise DebuggerError('Invalid CHIP-8 native layer identity')
        for key in ('generation','execution-bytes','fault-address','fault-pc','mismatch-address'):
            if type(info.get(key)) is not int or not 0<=info[key]<=((1<<64)-1 if key=='generation' else 0xffff if key=='fault-pc' else SIZE-1 if key in ('fault-address','mismatch-address') else SIZE):
                raise DebuggerError('Invalid CHIP-8 layer receipt '+key)
        for key in ('faulted','stop-owned','backing-valid'):
            if type(info.get(key)) is not bool:raise DebuggerError('Invalid CHIP-8 layer receipt '+key)
        for key in ('execute-mask-hex','execute-bytes-hex','execute-base-hex'):
            value=info.get(key)
            if not isinstance(value,str) or len(value)!=SIZE*2:
                raise DebuggerError('Invalid CHIP-8 layer receipt '+key)
            try:bytes.fromhex(value)
            except ValueError:raise DebuggerError('Invalid CHIP-8 layer receipt '+key) from None
        mask=bytes.fromhex(info['execute-mask-hex'])
        if any(x not in (0,1) for x in mask) or sum(mask)!=info['execution-bytes']:
            raise DebuggerError('Invalid CHIP-8 layer mask')
        data=bytes.fromhex(info['execute-bytes-hex']);base=bytes.fromhex(info['execute-base-hex'])
        if any(not mask[i] and (data[i] or base[i]) for i in range(SIZE)):
            raise DebuggerError('Noncanonical CHIP-8 inactive fetch bytes')
        if info['stop-owned'] and not info['faulted'] or not info['faulted'] and (info['fault-address'] or info['fault-pc']):
            raise DebuggerError('Invalid CHIP-8 layer fault receipt')
        if info['backing-valid'] and info['mismatch-address']!=0:
            raise DebuggerError('Invalid CHIP-8 layer backing receipt')
        return info

    def _chip8_layer_state(self):
        return dict(active=list(self._layer_active),generation=self._layer_generation,
                    ram_base={str(k):v for k,v in self._layer_ram_base.items()},
                    ram_applied={str(k):v for k,v in self._layer_ram_applied.items()},
                    definitions=[dict(id=i,sha256=self.project.debug_layer_info(i)['sha256']) for i in self._layer_active])

    def _chip8_layer_state_validate(self,state,native):
        if not isinstance(state,dict) or set(state)!={'active','generation','ram_base','ram_applied','definitions'}:
            raise ValueError('Invalid CHIP-8 layer checkpoint metadata')
        ids=state['active'];defs=state['definitions']
        if not isinstance(ids,list) or len(ids)>64 or not all(isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):
            raise ValueError('Invalid CHIP-8 saved layer stack')
        if type(state['generation']) is not int or state['generation']!=native['generation']:
            raise ValueError('Saved CHIP-8 layer generation differs')
        if not isinstance(defs,list) or len(defs)!=len(ids):raise ValueError('Invalid CHIP-8 layer definitions')
        expected={};ram={};execute={}
        for ident,entry in zip(ids,defs):
            d=self.project.debug_layer_info(ident)
            if entry!={'id':ident,'sha256':d['sha256']} or d['version']!=self.version['id'] or d.get('address_model')!='chip8-flat-4k':
                raise ValueError('Saved CHIP-8 layer definition differs')
            if d.get('chip8_profile')!='chip8-classic-pilot-default-v1' or d.get('kind') not in ('ram','execute'):
                raise ValueError('Saved CHIP-8 layer profile differs')
            for patch in d['patches']:
                before=byte_string(patch['expected_hex']);after=byte_string(patch['data_hex'])
                if len(before)!=len(after):raise ValueError('Saved CHIP-8 layer patch length differs')
                address=_address(patch['address'],len(before));target=ram if d['kind']=='ram' else execute
                for index,(old,new) in enumerate(zip(before,after)):
                    loc=address+index
                    if expected.setdefault(loc,old)!=old:raise ValueError('Saved CHIP-8 layer guards disagree')
                    target[loc]=new
        out=[]
        for key in ('ram_base','ram_applied'):
            value=state[key]
            if not isinstance(value,dict):raise ValueError('Invalid CHIP-8 RAM layer state')
            converted={}
            for k,v in value.items():
                if not isinstance(k,str) or not k.isdecimal() or str(int(k))!=k or not 0<=int(k)<SIZE or type(v) is not int or not 0<=v<=255:
                    raise ValueError('Invalid CHIP-8 RAM layer byte')
                converted[int(k)]=v
            out.append(converted)
        if out[1]!=ram or out[0]!={a:expected[a] for a in ram}:
            raise ValueError('Saved CHIP-8 RAM layer state differs from definitions')
        mask=bytes.fromhex(native['execute-mask-hex']);data=bytes.fromhex(native['execute-bytes-hex']);base=bytes.fromhex(native['execute-base-hex'])
        if any(bool(mask[a])!=(a in execute) or a in execute and (data[a]!=execute[a] or base[a]!=ram.get(a,expected[a])) for a in range(SIZE)):
            raise ValueError('Saved CHIP-8 fetch layer state differs from definitions')
        return dict(active=list(ids),generation=state['generation'],ram_base=out[0],ram_applied=out[1])

    def _chip8_layer_install_state(self,state):
        self._layer_active=state['active'];self._layer_generation=state['generation']
        self._layer_ram_base=state['ram_base'];self._layer_ram_applied=state['ram_applied']

    def _chip8_layer_require(self):
        if not self.capabilities.get('code_layers'):raise ValueError('CHIP-8 runtime lacks native layers')
        if self.project.db.in_transaction:raise ValueError('CHIP-8 layers require no caller transaction')
        self._stopped()

    def _chip8_space(self,address,length,space,cs=None):
        if cs is not None or space not in (None,'source','physical','linear'):
            raise ValueError('CHIP-8 layers require flat source, physical or linear addresses')
        value=_address(address,length)
        if space=='source' and not (0x200<=value and value+length<=0x200+len(self._rom)):
            raise ValueError('CHIP-8 source layer lies outside the original ROM')
        return value

    def layers(self,active=None,*,conflict='stop'):
        with self.vm.lock:
            self._chip8_layer_require();native=self._chip8_layer_query()
            if native['generation']!=self._layer_generation:raise DebuggerError('CHIP-8 layer generation differs')
            if conflict not in ('stop','keep_changed') or conflict=='keep_changed' and active!=[]:
                raise ValueError('keep_changed is only valid when clearing layers')
            if active is None:
                return dict(run=self.run_id,active=list(self._layer_active),generation=self._layer_generation,native=native,
                            layers=[self.project.debug_layer_info(i) for i in self._layer_active])
            if not isinstance(active,list) or len(active)>64 or any(not isinstance(i,str) for i in active) or len(set(active))!=len(active):
                raise ValueError('Invalid CHIP-8 layer stack')
            expected={};ram={};execute={};patch_count=0
            for ident in active:
                definition=self.project.debug_layer_info(ident)
                if definition['version']!=self.version['id'] or definition.get('address_model')!='chip8-flat-4k' or definition.get('chip8_profile')!='chip8-classic-pilot-default-v1':
                    raise ValueError('CHIP-8 layer definition identity differs')
                if definition['kind'] not in ('ram','execute'):raise ValueError('Invalid CHIP-8 layer kind')
                patch_count+=len(definition['patches'])
                if patch_count>256:raise ValueError('CHIP-8 active layers exceed 256 patches')
                for patch in definition['patches']:
                    before=byte_string(patch['expected_hex']);after=byte_string(patch['data_hex'])
                    if len(before)!=len(after):raise ValueError('CHIP-8 layer cannot resize memory')
                    address=_address(patch['address'],len(before));target=ram if definition['kind']=='ram' else execute
                    for offset,(old,new) in enumerate(zip(before,after)):
                        loc=address+offset
                        if expected.setdefault(loc,old)!=old:raise ValueError('Overlapping CHIP-8 layer guards disagree')
                        target[loc]=new
            current=dict(enumerate(self._memory(0,SIZE)));base=dict(current);preserved=[]
            for address,applied in self._layer_ram_applied.items():
                if current[address]==applied:base[address]=self._layer_ram_base[address]
                elif conflict=='keep_changed':preserved.append(dict(address=hex(address),observed_byte=current[address],layer_byte=applied))
                else:raise ValueError('Active CHIP-8 RAM layer conflicts with changed memory at '+hex(address))
            if any(base[a]!=b for a,b in expected.items()):raise ValueError('CHIP-8 layer expected base differs')
            post=base|ram;writes={a:post[a] for a in self._layer_ram_applied.keys()|ram.keys()}
            env=self.chip8_environment()
            if env['layer-generation']!=native['generation']:raise DebuggerError('CHIP-8 native layer generations differ')
            if native['generation']==(1<<64)-1 or env['state-generation']==(1<<64)-1:
                raise ValueError('CHIP-8 layer generation exhausted')
            args={'expected-generation':native['generation'],
                'expected-state-generation':env['state-generation'],'ram':_chunks(current,writes),
                'execute':_chunks(post,execute)}
            try:
                try:result=self.vm.qmp.call('x-chip8-configure-layers',args)
                except DebuggerError as error:
                    if 'CHIP8_LAYER_PRECONDITION' in str(error):raise _LayerPrecondition from error
                    raise
                observed=self._chip8_layer_query();after=self.chip8_environment()
                if result!=observed or observed['generation']!=native['generation']+1 or after['state-generation']!=env['state-generation']+1 or after['layer-generation']!=observed['generation']:
                    raise DebuggerError('CHIP-8 layer transition readback differs')
                mask=bytes.fromhex(observed['execute-mask-hex']);data=bytes.fromhex(observed['execute-bytes-hex']);back=bytes.fromhex(observed['execute-base-hex'])
                if any(bool(mask[i])!=(i in execute) or i in execute and (data[i]!=execute[i] or back[i]!=post[i]) for i in range(SIZE)):
                    raise DebuggerError('CHIP-8 fetch layer readback differs')
                if self._memory(0,SIZE)!=bytes(post[i] for i in range(SIZE)):raise DebuggerError('CHIP-8 RAM layer readback differs')
                self._layer_active=list(active);self._layer_generation=observed['generation']
                self._layer_ram_base={a:base[a] for a in ram};self._layer_ram_applied=ram
                result=dict(run=self.run_id,active=list(active),generation=self._layer_generation,native=observed,preserved_changed_bytes=preserved)
                self._event('layer-transition',result)
                return result
            except _LayerPrecondition as error:
                raise error.__cause__
            except BaseException:
                self.close();raise

    def layer_enable(self,layer,*,enabled=True):
        if type(enabled) is not bool:raise ValueError('enabled must be boolean')
        with self.vm.lock:
            self._chip8_layer_require()
            definition=self.project.debug_layer_info(layer)
            if definition['version']!=self.version['id'] or definition.get('address_model')!='chip8-flat-4k':
                raise ValueError('CHIP-8 layer definition identity differs')
            active=[i for i in self._layer_active if i!=layer]
            return self.layers(active+[layer] if enabled else active)

    def layer_patch(self,name,address,*,expected_hex,data_hex,kind='ram',activate=True,space=None):
        if type(activate) is not bool or kind not in ('ram','execute'):raise ValueError('Invalid CHIP-8 layer')
        before=byte_string(expected_hex);after=byte_string(data_hex)
        if len(before)!=len(after):raise ValueError('CHIP-8 layer cannot resize memory')
        with self.vm.lock:
            self._chip8_layer_require();value=self._chip8_space(address,len(before),space)
            result=self.project.debug_layer(name,kind=kind,patches=[dict(address=hex(value),expected_hex=before.hex(),data_hex=after.hex())],version=self.version['id'])
            if activate:result['activation']=self.layer_enable(result['layer'])
            return result

    def code(self,address,*,cs=None,length=32,view='execute',space=None):
        if view not in ('ram','execute'):raise ValueError('Invalid CHIP-8 code view')
        with self.vm.lock:
            self._chip8_layer_require();value=self._chip8_space(address,length,space,cs)
            raw=bytearray(self._memory(value,length));native=self._chip8_layer_query()
            if native['generation']!=self._layer_generation:raise DebuggerError('CHIP-8 layer generation differs')
            if view=='execute':
                if not native['backing-valid']:raise ValueError('CHIP-8 fetch layer backing changed')
                mask=bytes.fromhex(native['execute-mask-hex']);data=bytes.fromhex(native['execute-bytes-hex'])
                for i in range(length):
                    if mask[value+i]:raw[i]=data[value+i]
            return dict(address=hex(value),length=length,space=space or 'linear',view=view,hex=raw.hex(),generation=native['generation'])
