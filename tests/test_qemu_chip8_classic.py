"""Host-only RNG profile identity and seed-control tests."""
from copy import deepcopy
import pytest
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_chip8 import (CLASSIC_SUBSET, CLASSIC_ENV_MODEL, RNG_MODEL,
                                  _validate_environment)
from test_qemu_chip8_devices import device


def classic():
    session,state,calls,artifacts=device()
    session.identity['cpu_subset']=CLASSIC_SUBSET
    session.vm.fault['cpu-subset']=CLASSIC_SUBSET
    state.update({'cpu-subset':CLASSIC_SUBSET,'env-model':CLASSIC_ENV_MODEL,
                  'rng-model':RNG_MODEL,'rng-seed':0,'rng-state':42,'rng-draws':7})
    old=session.vm.qmp.call
    def call(method,args=None,**kwargs):
        if method=='x-chip8-seed-rng':
            calls.append((method,deepcopy(args)))
            assert args['expected-generation']==state['state-generation']
            state.update({'rng-seed':args['seed'],'rng-state':args['seed'],'rng-draws':0,
                          'state-generation':state['state-generation']+1,'key-wait-stop-owned':False})
            return deepcopy(state)
        return old(method,args,**kwargs)
    session.vm.qmp.call=call
    return session,state,calls


def test_seed_is_guarded_and_preserves_cpu_and_unrelated_environment():
    session,state,calls=classic(); before=deepcopy(state);regs=session.registers()
    after=session.chip8_seed_rng(0xffffffff)
    assert (after['rng-seed'],after['rng-state'],after['rng-draws'])==(0xffffffff,0xffffffff,0)
    assert after['state-generation']==before['state-generation']+1 and session.registers()==regs
    assert [args['expected-generation'] for method,args in calls if method=='x-chip8-seed-rng']==[before['state-generation']]
    for bad in (-1,2**32,True,'0'):
        with pytest.raises(ValueError):session.chip8_seed_rng(bad)


def test_rng_receipt_identity_and_counter_bounds_and_legacy_refusal():
    session,state,_=classic()
    for key,value in [('rng-model','other'),('rng-seed',2**32),('rng-state',-1),('rng-draws',2**64)]:
        bad=deepcopy(state);bad[key]=value
        with pytest.raises(DebuggerError):_validate_environment(bad)
    legacy,*_=device()
    with pytest.raises(ValueError,match='RNG'):legacy.chip8_seed_rng(0)


def test_seed_readback_mismatch_closes_owner():
    session,state,_=classic(); call=session.vm.qmp.call
    def broken(method,args=None,**kwargs):
        answer=call(method,args,**kwargs)
        if method=='x-chip8-seed-rng':answer['rng-state']^=1
        return answer
    session.vm.qmp.call=broken
    with pytest.raises(DebuggerError) as error:session.chip8_seed_rng(9)
    assert session.closed and error.value.result['disposition'].endswith('do not replay')
