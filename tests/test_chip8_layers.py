"""Host-side transition guards for CHIP-8 native layers."""
from copy import deepcopy
import pytest
from fdisbull.qemu_chip8 import LAYERS_SUBSET,LAYERS_ENV_MODEL
from fdisbull.chip8_layers import LAYER_MODEL
from test_qemu_chip8_classic import classic


def machine():
    s,env,_=classic();s.identity['cpu_subset']=LAYERS_SUBSET;s.vm.fault['cpu-subset']=LAYERS_SUBSET
    env.update({'cpu-subset':LAYERS_SUBSET,'env-model':LAYERS_ENV_MODEL,'layer-model':LAYER_MODEL,'layer-generation':0})
    s.capabilities={'code_layers':True};s._rom=b'\0'*20;s.run_id='test';s.version={'id':'v'};s._reset_chip8_layers();s._reset_chip8_hooks()
    definitions={};s.project.debug_layer_info=lambda ident:deepcopy(definitions[ident])
    def add(ident,kind,address,old,new):
        definitions[ident]={'id':ident,'sha256':ident,'version':'v','address_model':'chip8-flat-4k',
            'chip8_profile':'chip8-classic-pilot-default-v1','kind':kind,
            'patches':[{'address':hex(address),'expected_hex':old,'data_hex':new}]}
    blank=bytes(4096).hex()
    native={'model':LAYER_MODEL,'generation':0,'execute-mask-hex':blank,'execute-bytes-hex':blank,
            'execute-base-hex':blank,'execution-bytes':0,'faulted':False,'fault-address':0,'fault-pc':0,
            'stop-owned':False,'backing-valid':True,'mismatch-address':0}
    old=s.vm.qmp.call
    def call(name,args=None,**kwargs):
        if name=='query-chip8-layers':return deepcopy(native)
        if name=='x-chip8-configure-layers':
            assert args['expected-generation']==native['generation'] and args['expected-state-generation']==env['state-generation']
            for entry in args['ram']:
                pos=entry['address'];data=bytes.fromhex(entry['data-hex']);assert s.vm.gdb.bytes[pos:pos+len(data)]==bytes.fromhex(entry['expected-hex'])
                s.vm.gdb.bytes[pos:pos+len(data)]=data
            mask=bytearray(4096);data=bytearray(4096);base=bytearray(4096)
            for entry in args['execute']:
                pos=entry['address'];chunk=bytes.fromhex(entry['data-hex']);guard=bytes.fromhex(entry['expected-hex'])
                assert s.vm.gdb.bytes[pos:pos+len(chunk)]==guard
                mask[pos:pos+len(chunk)]=b'\1'*len(chunk);data[pos:pos+len(chunk)]=chunk;base[pos:pos+len(chunk)]=guard
            native.update({'generation':native['generation']+1,'execute-mask-hex':mask.hex(),'execute-bytes-hex':data.hex(),
                           'execute-base-hex':base.hex(),'execution-bytes':sum(mask)})
            env['layer-generation']+=1;env['state-generation']+=1
            return deepcopy(native)
        return old(name,args,**kwargs)
    s.vm.qmp.call=call
    return s,add,native,env


def test_ram_fetch_stack_and_guest_write_conflict():
    s,add,native,env=machine();add('ram','ram',0x200,'00','01');add('fetch','execute',0x200,'00','02')
    s.layers(['ram','fetch']);assert s.code(0x200,length=1,view='ram')['hex']=='01'
    assert s.code(0x200,length=1,view='execute')['hex']=='02'
    s.vm.gdb.bytes[0x200]=3
    with pytest.raises(ValueError,match='conflicts'):s.layers([])
    cleared=s.layers([],conflict='keep_changed');assert cleared['preserved_changed_bytes'] and s.vm.gdb.bytes[0x200]==3


def test_overlapping_guards_and_checkpoint_definitions_checked_before_mutation():
    s,add,native,env=machine();add('a','ram',0x200,'00','01');add('b','execute',0x200,'ff','02')
    with pytest.raises(ValueError,match='guards disagree'):s.layers(['a','b'])
    assert native['generation']==0
    s.layers(['a']);state=s._chip8_layer_state();state['ram_applied']['512']=42
    with pytest.raises(ValueError,match='differs from definitions'):s._chip8_layer_state_validate(state,native)


def test_fetch_backing_conflict_stops_before_execution():
    s,add,native,env=machine();native.update({'backing-valid':False,'mismatch-address':0x200})
    result=s._execute('c',1000)
    assert result['outcome']=='layer_conflict' and s.vm.gdb.requests==[]


def test_dirty_fetch_guard_is_checkpointable_but_blocks_execution():
    s,add,native,env=machine();add('fetch','execute',0x200,'00','02')
    s.layers(['fetch']);native.update({'backing-valid':False,'mismatch-address':0x200,
                                      'faulted':True,'fault-address':0x200,'fault-pc':0x200,'stop-owned':True})
    state=s._chip8_layer_state()
    restored=s._chip8_layer_state_validate(state,native)
    assert restored['active']==['fetch'] and native['faulted'] and not native['backing-valid']
    assert s._execute('c',1000)['outcome']=='layer_conflict'


def test_sticky_fault_blocks_even_after_backing_is_repaired():
    s,add,native,env=machine();native.update({'faulted':True,'fault-address':0x200,'fault-pc':0x200,
                                              'backing-valid':True,'stop-owned':False})
    assert s._execute('c',1000)['outcome']=='layer_conflict'
    assert s.vm.gdb.requests==[]


def test_noncanonical_or_inconsistent_native_receipts_are_refused():
    from fdisbull.dosbox_rpc import DebuggerError
    for change in ({'stop-owned':True},{'fault-address':4096},{'mismatch-address':4096},
                   {'execute-bytes-hex':'01'+'00'*4095}):
        s,add,native,env=machine();native.update(change)
        with pytest.raises(DebuggerError):s._chip8_layer_query()


def test_proven_native_precondition_refusal_preserves_owner():
    from fdisbull.dosbox_rpc import DebuggerError
    s,add,native,env=machine();add('a','ram',0x200,'00','01');original=s.vm.qmp.call
    def rejected(method,args=None,**kwargs):
        if method=='x-chip8-configure-layers':raise DebuggerError('CHIP8_LAYER_PRECONDITION: generation changed')
        return original(method,args,**kwargs)
    s.vm.qmp.call=rejected
    with pytest.raises(DebuggerError,match='CHIP8_LAYER_PRECONDITION'):s.layers(['a'])
    assert not s.closed and s._layer_active==[] and native['generation']==0


def test_exhausted_generation_refuses_before_native_mutation():
    s,add,native,env=machine();native['generation']=env['layer-generation']=s._layer_generation=(1<<64)-1
    with pytest.raises(ValueError,match='exhausted'):s.layers([])
    assert not s.closed


def test_patch_budget_refuses_before_native_mutation():
    s,add,native,env=machine();add('a','ram',0x200,'00','01')
    definition=s.project.debug_layer_info('a');definition['patches']*=257
    s.project.debug_layer_info=lambda ident:definition
    with pytest.raises(ValueError,match='256 patches'):s.layers(['a'])
    assert native['generation']==0 and not s.closed


def test_fault_latched_at_native_stop_outranks_breakpoint():
    s,add,native,env=machine();s.breakpoint(0x200)
    def stop(command,timeout):
        native.update({'faulted':True,'fault-address':0x200,'fault-pc':0x200,'backing-valid':True,'stop-owned':False})
        return b'T05',False
    s.vm.gdb.execute=stop
    assert s._execute('c',1000)['outcome']=='layer_conflict'
