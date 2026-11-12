"""Host-only device receipt, ownership and API tests; no native guest runs."""
from copy import deepcopy
import hashlib
import io
import pytest
from PIL import Image
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_chip8 import DEVICE_SUBSET,ENV_MODEL,PROFILE,_validate_environment
from test_qemu_chip8 import session as cpu_session


def environment():
    pixels=bytes([0,1]+[0]*2046)
    return dict(profile=PROFILE,**{'cpu-subset':DEVICE_SUBSET,'env-model':ENV_MODEL,
        'width':64,'height':32,'pixels-hex':pixels.hex(),'pixels-sha256':hashlib.sha256(pixels).hexdigest(),
        'frame-generation':1,'key-mask':0,'key-wait':False,'key-wait-stop-owned':False,
        'delay-timer':3,'sound-timer':2,'sound-active':True,'virtual-ticks':9,'manual-ticks':1,
        'phase-numerator':2,'virtual-now-ns':123,'next-deadline-ns':456,'state-generation':7})


def device():
    s=cpu_session();s.identity={'cpu_subset':DEVICE_SUBSET};s.vm.fault['cpu-subset']=DEVICE_SUBSET
    state=environment();calls=[];artifacts=[]
    def call(method,args=None,**kwargs):
        calls.append((method,deepcopy(args)))
        if method=='query-status':return {'running':False}
        if method=='query-chip8-fault':return deepcopy(s.vm.fault)
        if method=='query-chip8-environment':return deepcopy(state)
        if method in ('x-chip8-set-keys','x-chip8-debug-ticks'):
            assert args['expected-generation']==state['state-generation']
            state['state-generation']+=1;state['key-wait-stop-owned']=False
            if method=='x-chip8-set-keys':state['key-mask']=args['key-mask']
            else:
                n=args['count'];state['manual-ticks']+=n
                state['delay-timer']=max(0,state['delay-timer']-n)
                state['sound-timer']=max(0,state['sound-timer']-n)
                state['sound-active']=state['sound-timer']>0
            return deepcopy(state)
        raise AssertionError(method)
    s.vm.qmp.call=call
    def artifact(name,kind,data,metadata):
        artifacts.append((name,kind,data,metadata))
        return dict(artifact='image-1',sha256=hashlib.sha256(data).hexdigest(),size=len(data))
    s._artifact=artifact
    return s,state,calls,artifacts


def test_keypad_and_manual_ticks_are_stopped_cas_and_preserve_cpu():
    s,state,calls,_=device();before=s.registers()
    receipt=s.chip8_keypad([0,3,15]);assert receipt['key-mask']==0x8009
    receipt=s.chip8_tick(2)
    assert (receipt['delay-timer'],receipt['sound-timer'],receipt['sound-active'])==(1,0,False)
    assert (receipt['manual-ticks'],receipt['virtual-ticks'],receipt['phase-numerator'])==(3,9,2)
    assert s.registers()==before
    assert [x[1]['expected-generation'] for x in calls if x[0].startswith('x-chip8')]==[7,8]
    for bad in ([True],[16],[1,1],'1'):
        with pytest.raises(ValueError):s.chip8_keypad(bad)
    for bad in (0,65536,True):
        with pytest.raises(ValueError):s.chip8_tick(bad)


def test_frame_rgba_and_stored_png_have_exact_opaque_pixels():
    s,state,calls,artifacts=device();frame=s.frame_rgba()
    assert (frame['width'],frame['height'],frame['format'])==(64,32,'rgba8888')
    assert frame['rgba'][:8]==bytes.fromhex('000000ff ffffffff')
    assert frame['sha256']==hashlib.sha256(frame['rgba']).hexdigest()
    saved=s.screenshot();assert saved['pixel_sha256']==frame['sha256']
    with Image.open(io.BytesIO(artifacts[0][2])) as image:
        assert image.mode=='RGBA' and image.size==(64,32) and image.tobytes()==frame['rgba']


def test_corrupt_frame_or_nonatomic_device_result_fails_closed():
    s,state,calls,_=device();bad=deepcopy(state);bad['pixels-sha256']='0'*64
    with pytest.raises(DebuggerError):_validate_environment(bad)
    real=s.vm.qmp.call
    def broken(method,args=None,**kwargs):
        result=real(method,args,**kwargs)
        if method=='x-chip8-set-keys':result['key-mask']^=1
        return result
    s.vm.qmp.call=broken
    with pytest.raises(DebuggerError) as error:s.chip8_keypad([1])
    assert s.closed and error.value.result['before']['key-mask']==0
    assert error.value.result['disposition'].endswith('do not replay')


def test_owned_wait_stop_and_stale_wait_breakpoint_are_distinct():
    s,state,calls,_=device();s.vm.gdb.bytes[0x200:0x202]=bytes.fromhex('f00a')
    state.update({'key-wait':True,'key-wait-stop-owned':True})
    result=s.step();assert result['outcome']=='key_wait' and result['registers']['linear_pc']=='0x200'
    s.breakpoint(0x200)
    state['key-wait-stop-owned']=False
    result=s.run();assert result['outcome']=='breakpoint'
    assert result['session']['stop_reason']['breakpoint_ids']


def test_fresh_owned_wait_is_not_mislabelled_by_same_pc_breakpoint():
    s,state,calls,_=device();s.vm.gdb.bytes[0x200:0x202]=bytes.fromhex('f00a')
    s.breakpoint(0x200)
    state.update({'key-wait':True,'key-wait-stop-owned':True})
    result=s.step()
    assert result['outcome']=='key_wait'
    assert result['session']['stop_reason']['breakpoint_ids']==[]
