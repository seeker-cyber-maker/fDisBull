"""Public routing and static safety gates for selected QEMU CPU deltas."""
import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import MachineDebugSession
from test_qemu_io_public import raw_project, stopped_session


def script(*steps):
    return dict(format='fdisbull-script-1',backend='qemu-dos',steps=list(steps))


class RoutedDeltaSession(MachineDebugSession):
    @property
    def script_operations(self):
        return super().script_operations | {'delta-start','delta-record','delta-rewind','delta-status','delta-recover'}

    def cpu_delta_start(self,ranges,*,registers=None,max_steps=16,max_bytes=67108864,timeout_ms=60000):
        self.delta_calls.append(('start',ranges,registers,max_steps,timeout_ms))
        return dict(anchor={'artifact':'anchor'},registers=registers)

    def cpu_delta_rewind(self,count=1,*,policy=None,timeout_ms=60000):
        self.delta_calls.append(('rewind',count,policy,timeout_ms))
        return dict(partial_restored=True,full_machine_restored=False,devices_restored=False,
                    resume_safe=False,execution_allowed=False)


def routed(project,tmp_path):
    session,peer = stopped_session(project,tmp_path)
    session.__class__ = RoutedDeltaSession
    session.metadata['backend'] = 'qemu-dos'
    session.capabilities['cpu_delta'] = True
    session.delta_calls = []
    return session,peer


def test_native_selected_delta_grammar_accepts_explicit_registers():
    step = dict(op='delta-start',ranges=[dict(address='0x10000',length=2)],registers=['rax','rip'])
    assert validate_script(script(step)) == [step]


def test_native_selected_delta_json_routes_registers_and_freeze_receipt(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    workspace = DebugWorkspace(); workspace.sessions[session.run_id] = session
    try:
        params = dict(project=str(raw_project.path),run=session.run_id,context='machine',
                      ranges=[dict(address='0x10000',length=2)],registers=['rax','rip'],timeout_ms=400)
        reply = respond(dict(method='debug-delta-start',params=params),debugger=workspace)
        assert reply['ok'] and reply['result']['registers'] == ['rax','rip'], reply
        assert session.delta_calls == [('start',params['ranges'],['rax','rip'],16,400)] and not peer.calls
    finally:
        workspace.sessions.clear(); session.close()


def test_native_selected_delta_script_forwards_options(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    report = execute_script(session,script(dict(op='delta-start',
        ranges=[dict(address='0x10000',length=2)],registers=['rax','rip'],max_steps=4)),timeout_ms=500)
    assert report['ok'] and report['completed_steps'] == 1, report
    assert session.delta_calls[0][:4] == ('start',[dict(address='0x10000',length=2)],['rax','rip'],4)
    assert not peer.calls


def test_partial_resume_literal_refuses_whole_script_before_earlier_write(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    writes=[]
    session.write_memory = lambda *args,**kwargs:writes.append((args,kwargs))
    with pytest.raises(ValueError,match='partial.resume|partial resume'):
        execute_script(session,script(dict(op='write-memory',address=0x7c00,data_hex='90',expected_hex='00'),
            dict(op='delta-rewind',policy=dict(allow_partial_resume=True))))
    assert not writes and not session.delta_calls and not peer.calls


@pytest.mark.parametrize('outcome,recorded_count',[
    ('interrupted',1), ('context_changed',1), ('completed',2),
])
def test_incomplete_delta_record_stops_script_and_preserves_receipt(
        raw_project,tmp_path,outcome,recorded_count):
    session,peer = routed(raw_project,tmp_path)
    calls=[]
    writes=[]
    receipt=dict(outcome=outcome,requested_count=3,recorded_count=recorded_count,
                 records=[dict(index=1)],stop=dict(outcome='breakpoint'))

    def record(count=1,timeout_ms=10000):
        calls.append((count,timeout_ms))
        return receipt

    session.cpu_delta_record = record
    session.write_memory = lambda *args,**kwargs:writes.append((args,kwargs))
    report = execute_script(session,script(
        dict(op='delta-record',count=3,timeout_ms=5000),
        dict(op='write-memory',address=0x7c00,data_hex='90',expected_hex='00'),
    ),timeout_ms=200)
    assert not report['ok'] and report['completed_steps'] == 0, report
    assert len(report['steps']) == 1 and report['steps'][0]['result'] == receipt
    assert not report['steps'][0]['ok']
    assert len(calls) == 1 and calls[0][0] == 3 and 1 <= calls[0][1] <= 200
    assert not writes and not peer.calls
