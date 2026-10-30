"""Deterministic final-pause races; real DOS execution coverage is separate."""
import pytest

from fdisbull.debugger import DebugSession
from fdisbull.dosbox_rpc import DebuggerError


class PauseRace:
    run=DebugSession.run

    def __init__(self,rejected=False,kind='breakpoint',uncertain=False):
        self.closed=False;self.run_id='pause-race';self.metadata={};self.events=[];self.calls=[]
        self.rejected=rejected;self.kind=kind;self.uncertain=uncertain;self.timing_calls=0

    def _timing(self,enabled=None):
        self.timing_calls+=1
        return dict(fast_forward=False,guest_ticks=0 if self.timing_calls<3 else 20)

    def call(self,method,params=None):
        self.calls.append((method,params))
        if method=='execution.continue':return dict(operation_id='continue')
        if method=='execution.pause':
            if self.rejected:raise DebuggerError('Target must be running (TARGET_NOT_RUNNING)')
            return dict(operation_id='pause')
        if method=='execution.wait':
            if len([c for c in self.calls if c[0]=='execution.wait'])==1:return dict(running=True)
            if self.uncertain:return dict(running=True)
            state='exited' if self.kind in ('exited','guest_exit','guest_tsr') else 'failed' if self.kind=='error' else 'stopped'
            return dict(running=False,state=state,stop_reason=dict(kind=self.kind,breakpoint_id='owned-hook'))
        raise AssertionError(method)

    def _dispatch_hook(self,result):raise AssertionError('Do not dispatch actions at the final budget boundary')
    def _event(self,operation,result):self.events.append((operation,result))
    def close(self):self.closed=True


@pytest.mark.parametrize('rejected',[False,True])
@pytest.mark.parametrize('kind',['breakpoint','error','exited','guest_exit','guest_tsr'])
def test_terminal_stop_wins_race_with_bounded_pause_without_resume(rejected,kind):
    target=PauseRace(rejected,kind)
    result=target.run(guest_ms=10,timeout_ms=1000,fast_forward=True,stop_on_hook=True)
    assert result['outcome']==kind and not target.closed
    assert result['session']['stop_reason']['kind']==kind
    assert len([c for c in target.calls if c[0]=='execution.continue'])==1
    assert [c for c in target.calls if c[0]=='execution.wait'][-1][1]['operation_id']==('continue' if rejected else 'pause')


def test_uncertain_final_pause_still_closes_owned_session():
    target=PauseRace(rejected=True,uncertain=True)
    with pytest.raises(DebuggerError,match='failed to pause'):target.run(guest_ms=10)
    assert target.closed
