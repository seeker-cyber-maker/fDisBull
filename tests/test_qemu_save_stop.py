"""Synthetic stop ownership and publication protocol; not native execution evidence."""
from copy import deepcopy
import time
import pytest
from fdisbull import qemu_save_stop as stop
from fdisbull import qemu_dos_provenance as witness
from test_qemu_workspace import session
from test_qemu_dos_save_admission import configured_save
from test_dos_save_operations import create


def packet():
    return {'api-version':1,'model':stop.MODEL,'observer-token':'','epoch':1,'generation':1,
        'observer-generation':1,'enabled':False,'state':'idle','sequence':0,'acknowledged':True,
        'pending':False,'event-count':0,'witness-generation':0,'return-pc':0,'return-cs':0,
        'return-ss':0,'return-sp':0,'reason':''}


def configured(session,tmp_path):
    debug=configured_save(session,tmp_path);old=debug.vm.qmp
    debug.vm.qmp_commands|=stop.COMMANDS
    class Qmp:
        auxiliary=packet();calls=[];lose_ack=False
        @property
        def info(self):return old.info
        @info.setter
        def info(self,value):old.info=value
        def call(self,command,args=None):
            self.calls.append(command)
            if command not in stop.COMMANDS:return old.call(command,args)
            self.auxiliary['observer-token']=self.info['token']
            self.auxiliary['observer-generation']=self.info['generation']
            if command in (stop.SET,stop.ACK):
                assert args['token']==self.auxiliary['observer-token']
                assert args['epoch']==self.auxiliary['epoch']
                assert args['expected-generation']==self.auxiliary['generation']
                self.auxiliary['generation']+=1
                if command==stop.SET:self.auxiliary['enabled']=args['enabled']
                else:
                    assert args['sequence']==self.auxiliary['sequence']
                    self.auxiliary['acknowledged']=True
                    if self.lose_ack:raise OSError('lost ACK reply')
            return deepcopy(self.auxiliary)
    debug.vm.qmp=Qmp();dest=tmp_path/'keeps';dest.mkdir()
    debug.workspace_keep_policy('SAVE.DAT',dest,mode='save',safe_stop=True)
    debug.vm.operation_deadline=time.monotonic()+10
    return debug


def complete(debug,state='consumed'):
    binding=debug._dos_save_witness;p=create()
    p.update(token=binding['observer_token'],generation=2,**{'source-ranges':binding['source_ranges'],
        'child-psp':binding['child_psp'],'int21-vector':binding['int21_vector']})
    for e in p['events']:e['caller-pc']=0x1100;e['return-pc']=0x1102
    debug.vm.qmp.info=p
    a=debug.vm.qmp.auxiliary;a.update(state=state,sequence=1,acknowledged=False,generation=a['generation']+1,
        **{'event-count':4,'witness-generation':2,'return-pc':0x1102,'return-cs':0x100,
           'return-ss':0x300,'return-sp':0xfffe})


def execution(kind='stopped',reply='T02'):
    return dict(outcome=kind,timed_out=False,session=dict(state='stopped',stop_reason=dict(
        kind=kind,breakpoint_ids=[],native_reply=reply,address='0x1102')),
        registers={'linear_pc':'0x1102','registers':{'cs':'0x100','ss':'0x300','rsp':'0xfffe'}},
        stop={'trigger':kind,'context':'machine','native_kind':kind})


@pytest.mark.parametrize('field,value',[('state','pending'),('epoch',0),('sequence',True),('return-sp',65536)])
def test_bad_stop_packets_refuse(field,value):
    p=packet();p[field]=value
    with pytest.raises(ValueError):stop.validate(p)


def test_only_fresh_owned_stop_can_publish_once(session,tmp_path,monkeypatch):
    debug=configured(session,tmp_path);published=[]
    import fdisbull.qemu_workspace as workspace
    monkeypatch.setattr(workspace,'_seal_workspace',lambda s:{'checkpoint':'checkpoint','workspace':{'generation':{'artifact':'g'}}})
    monkeypatch.setattr(witness,'service_policy',lambda s,sealed:published.append(sealed) or {'outcome':'kept'})
    with stop.SaveRunScope(debug) as scope:
        before=stop.before_execute(debug,'c');assert before['enabled']
        complete(debug)
        result=stop.after_execute(debug,execution(),before)
        assert result['outcome']=='save_boundary'
        scope.finish(result)
    assert len(published)==1 and result['save_keep']['policy']['outcome']=='kept'
    assert debug.vm.qmp.auxiliary['acknowledged'] and not debug.vm.qmp.auxiliary['enabled']
    assert result['native_save_machine_stop']['kind']=='stopped'
    assert result['save_stop_cleanup']['acknowledgement']['artifact']


def test_ready_without_new_attempt_is_not_a_stop_claim(session,tmp_path):
    debug=configured(session,tmp_path)
    with stop.SaveRunScope(debug) as scope:
        before=stop.before_execute(debug,'c');complete(debug)
        debug.vm.qmp.auxiliary.update(state='idle',sequence=0,acknowledged=True)
        result=stop.after_execute(debug,execution(),before);scope.finish(result)
    assert result['outcome']=='stopped' and 'save_keep' not in result


@pytest.mark.parametrize('deferred',[False,True])
def test_competing_control_keeps_original_cause_without_publication(session,tmp_path,deferred):
    debug=configured(session,tmp_path)
    with stop.SaveRunScope(debug) as scope:
        before=stop.before_execute(debug,'c');complete(debug,'consumed' if deferred else 'preempted')
        result=execution() if deferred else execution('breakpoint','T05')
        if deferred:debug.breakpoints={'control':dict(access='x',address=0x1102)}
        else:result['session']['stop_reason']['breakpoint_ids']=['control']
        observed=stop.after_execute(debug,result,before);scope.finish(observed)
    assert observed['outcome']==('stopped' if deferred else 'breakpoint')
    assert observed['save_boundary_conflict'] and 'save_keep' not in observed
    assert observed['session']['stop_reason']['breakpoint_ids']==([] if deferred else ['control'])


def test_script_and_history_disable_automatic_native_stops(session,tmp_path):
    debug=configured(session,tmp_path)
    @stop.no_automatic_keeps
    def scripted(s):
        with stop.SaveRunScope(s) as scope:
            assert not scope.owns and stop.before_execute(s,'c')['enabled'] is False
    scripted(debug);assert debug._save_keep_suppressed_depth==0
    debug._history_busy=True
    with stop.SaveRunScope(debug) as scope:
        assert not scope.owns and stop.before_execute(debug,'c')['enabled'] is False


def test_restored_consumed_attempt_is_acknowledged_without_republication(session,tmp_path):
    debug=configured(session,tmp_path);complete(debug)
    with stop.SaveRunScope(debug) as scope:
        before=stop.before_execute(debug,'c')
        assert before['acknowledged'] and len(scope.reconciled)==1
        result=stop.after_execute(debug,execution(),before);scope.finish(result)
    assert result['outcome']=='stopped' and 'save_keep' not in result
    assert len(result['save_stop_prior_acknowledgements'])==1


def test_failed_keep_preserves_checkpoint_and_export_effects_without_ack_replay(session,tmp_path,monkeypatch):
    debug=configured(session,tmp_path)
    import fdisbull.qemu_workspace as workspace
    monkeypatch.setattr(workspace,'_seal_workspace',lambda s:{'checkpoint':'checkpoint','workspace':{'generation':{'artifact':'g'}}})
    def fail(s,sealed):
        error=OSError('journal failed');error.result={'export':{'durable':True},'outcome':'needs-reconciliation'};raise error
    monkeypatch.setattr(witness,'service_policy',fail)
    with pytest.raises(OSError,match='journal failed') as raised:
        with stop.SaveRunScope(debug) as scope:
            before=stop.before_execute(debug,'c');complete(debug)
            scope.finish(stop.after_execute(debug,execution(),before))
    assert debug.closed
    assert raised.value.result['execution']['save_keep']['checkpoint']=='checkpoint'
    assert raised.value.result['keep_effects']['export']['durable']
    assert stop.ACK not in debug.vm.qmp.calls


def test_lost_ack_reply_closes_with_durable_ack_record(session,tmp_path):
    debug=configured(session,tmp_path);complete(debug);debug.vm.qmp.lose_ack=True
    with pytest.raises(OSError,match='lost ACK reply') as raised:
        with stop.SaveRunScope(debug):stop.before_execute(debug,'c')
    assert debug.closed
    assert raised.value.result['control_effects']['acknowledgement_record']['artifact']


def test_aux_checkpoint_rotates_owner_without_reissuing_stop(session,tmp_path):
    debug=configured(session,tmp_path);saved=witness.capture_checkpoint(debug)
    debug.vm.qmp.info.update(epoch=2,generation=3)
    debug.vm.qmp.auxiliary.update(epoch=2,generation=4)
    witness.verify_loaded(debug.vm,saved)
    assert not any(c in (stop.SET,stop.ACK) for c in debug.vm.qmp.calls)
    debug.vm.qmp.auxiliary['enabled']=True
    with pytest.raises(ValueError,match='differs'):witness.verify_loaded(debug.vm,saved)


def test_missing_expected_owner_refuses_before_remote_execution(session,tmp_path,monkeypatch):
    debug=configured(session,tmp_path);debug.vm.qmp.info['active']=False
    debug._launching=False;debug._execution_preflight=lambda *a:None;calls=[]
    from fdisbull.qemu_dos_process import QemuDOSProcessSession
    from fdisbull.qemu_machine import MachineContext
    monkeypatch.setattr(MachineContext,'_execute',lambda *a:calls.append(a))
    with pytest.raises(ValueError,match='owner is missing'):
        QemuDOSProcessSession._execute(debug,'c',1000)
    assert not calls and debug.closed


def test_close_persistence_failure_does_not_erase_keep_effects(session,tmp_path,monkeypatch):
    debug=configured(session,tmp_path)
    import fdisbull.qemu_workspace as workspace
    monkeypatch.setattr(workspace,'_seal_workspace',lambda s:{'checkpoint':'checkpoint','workspace':{'generation':{'artifact':'g'}}})
    def fail(s,sealed):
        error=OSError('export receipt failed');error.result={'export':{'durable':True}};raise error
    original_close=debug.close
    def close():
        original_close();raise OSError('close persistence failed')
    monkeypatch.setattr(debug,'close',close)
    monkeypatch.setattr(witness,'service_policy',fail)
    with pytest.raises(OSError,match='export receipt failed') as raised:
        with stop.SaveRunScope(debug) as scope:
            before=stop.before_execute(debug,'c');complete(debug)
            scope.finish(stop.after_execute(debug,execution(),before))
    assert debug.closed
    assert raised.value.result['previous']['keep_effects']['export']['durable']
    assert raised.value.result['closing_error']=='close persistence failed'
