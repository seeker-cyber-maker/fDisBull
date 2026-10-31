"""Authored route-control checks, not original-game parity."""
import pytest
import time
from types import SimpleNamespace
from examples.agi.verify_goat import GoatRun


def waiting(states,elapsed=0):
    run=object.__new__(GoatRun);run.guest_elapsed=elapsed;run.polls=0
    def state():return states[min(run.polls,len(states)-1)]
    def advance(ms):run.polls+=1;run.guest_elapsed+=100
    run.state=state;run.advance=advance
    return run


def test_committed_predicate_initially_true_does_not_execute():
    run=waiting([{'committed':True}])
    assert run.wait(lambda s:s['committed'],'commit')=={'committed':True}
    assert run.polls==0


def test_handler_return_is_not_yet_committed_state():
    run=waiting([{'committed':False},{'committed':False},{'committed':True}])
    assert run.wait(lambda s:s['committed'],'commit')['committed']
    assert run.polls==2 and run.guest_elapsed==200


def test_wait_charges_measured_progress_and_refuses_missing_commit():
    run=waiting([{'committed':False}],elapsed=500)
    with pytest.raises(RuntimeError,match='did not complete within budget'):
        run.wait(lambda s:s['committed'],'commit',budget=200)
    assert run.guest_elapsed==700


def test_lost_run_response_retains_attempt_without_claiming_no_execution():
    run=object.__new__(GoatRun);run.guest_elapsed=0;run.deadline=time.monotonic()+5;run.journal=[]
    def lost(**kwargs):raise TimeoutError('response lost after dispatch')
    run.d=SimpleNamespace(run=lost)
    with pytest.raises(TimeoutError):run.advance(100)
    assert run.journal==[{'kind':'run','attempted':True,'result':None}]


def test_print_observer_cannot_restart_exhausted_route_budget(monkeypatch):
    import examples.agi.verify_goat as module
    run=object.__new__(GoatRun);run.guest_elapsed=239999;run.deadline=time.monotonic()+0.5
    run.journal=[];run.messages=[];run.bp='print';run.resources={};run.cs=0x1000;run.ds=0x20000
    run.d=SimpleNamespace(call=lambda *a,**k:{},run=lambda **kwargs:{'outcome':'breakpoint','guest_elapsed_ms':0,'session':{'stop_reason':{'breakpoint_id':'print'}}})
    seen={}
    class Observer:
        def __init__(self,*args,**kwargs):pass
        def finish(self,**kwargs):
            if kwargs:seen.update(kwargs)
            return {'status':'incomplete','error':'budget','stops':[]}
        def readback(self):return self.finish()
    monkeypatch.setattr(module,'AGIDOSPrintObserver',Observer)
    with pytest.raises(RuntimeError,match='message did not complete'):run.advance(1)
    assert seen['total_guest_ms']==1 and 0<seen['total_timeout_ms']<=500


def test_natural_entry_transport_loss_records_unknown_attempt():
    run=object.__new__(GoatRun);run.guest_elapsed=0;run.deadline=time.monotonic()+5;run.journal=[];run.bp='print';run.cs=0x1000
    def call(method,*args):return {'breakpoint_id':'entry'} if method=='breakpoints.create' else {}
    def lost(**kwargs):raise TimeoutError('entry response lost')
    run.d=SimpleNamespace(call=call,run=lost)
    with pytest.raises(TimeoutError):run.qualify_follow()
    assert run.journal==[{'kind':'entry-search','attempted':True,'result':None}]
