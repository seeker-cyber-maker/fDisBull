"""Separate LE source state/history routes cannot relabel ordinary MZ state."""
import json

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from fdisbull.qemu_machine import MachineDebugSession
from test_qemu_io_public import raw_project, stopped_session
from test_qemu_owned_checkpoint import runtime


def route(*steps, backend='qemu-dos'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


class LESession(MachineDebugSession):
    @property
    def script_operations(self):
        return super().script_operations | {'save-le-source-state', 'load-le-source-state',
            'le-rewind-start', 'le-rewind-status', 'le-rewind-record', 'le-rewind'}

    def save_le_source_state(self, name='dos-le-source.json', *, max_bytes=None, timeout_ms=60000):
        self.calls.append(('save',name,max_bytes,timeout_ms))
        return dict(artifact='le-artifact',size=100,charged_size=1000)

    def load_le_source_state(self, artifact, *, timeout_ms=60000):
        self.calls.append(('load',artifact,timeout_ms))
        return dict(source_binding_restored=False,le_source_checkpoint_restored=True)

    def le_rewind_start(self,max_steps=16,max_bytes=536870912,*,history=None,timeout_ms=60000):
        self.calls.append(('start',history,timeout_ms))
        return dict(history='le-history')

    def le_rewind_status(self,*,history=None):
        self.calls.append(('status',history))
        return dict(history=history)

    def le_rewind_record(self,count=1,timeout_ms=60000,*,advance='capture'):
        self.calls.append(('record',count,advance,timeout_ms))
        return dict(recorded_count=count)

    def le_rewind(self,count=1,*,history=None,node=None,timeout_ms=60000):
        self.calls.append(('rewind',history,node,timeout_ms))
        return dict(source_binding_restored=False,le_source_checkpoint_restored=True)


def routed(project,tmp_path):
    session,peer=stopped_session(project,tmp_path)
    session.__class__=LESession
    session.metadata['backend']='qemu-dos'
    session.capabilities.update(le_source_checkpoints=True,le_source_histories=True)
    session.calls=[]
    return session,peer


@pytest.mark.parametrize('step',[
    dict(op='save-le-source-state',name='../escape'),
    dict(op='save-le-source-state',name='$old.name'),
    dict(op='save-le-source-state',max_bytes=True),
    dict(op='save-le-source-state',max_bytes=8*1024**2),
    dict(op='save-le-source-state',max_bytes=128*1024**2+1),
    dict(op='load-le-source-state',artifact=42),
    dict(op='load-le-source-state',artifact='id',timeout_ms=0),
    dict(op='load-le-source-state',artifact='id',timeout_ms='$old.budget'),
    dict(op='le-rewind-start',max_steps=True),
    dict(op='le-rewind-start',max_steps=129),
    dict(op='le-rewind-start',max_bytes=1024**3+1),
    dict(op='le-rewind-start',max_bytes=1),
    dict(op='le-rewind-record',advance='step'),
    dict(op='le-rewind-record',advance='$old.advance'),
    dict(op='le-rewind-record',count=2),
    dict(op='le-rewind-record',count=True),
    dict(op='le-rewind',node=123),
    dict(op='le-rewind',count=0),
])
def test_bad_le_route_refuses_before_earlier_capture(raw_project,tmp_path,step):
    session,peer=routed(raw_project,tmp_path)
    try:
        with pytest.raises((ValueError,TypeError)):
            execute_script(session,route(dict(op='save-le-source-state'),step))
        assert session.calls==[] and peer.calls==[]
    finally: session.close()


@pytest.mark.parametrize('backend',[None,'dosbox','qemu-machine','qemu-chip8'])
def test_le_routes_require_explicit_native_dos_backend(backend):
    with pytest.raises(ValueError):
        validate_script(route(dict(op='save-le-source-state'),backend=backend))


def test_le_json_and_scripts_are_separate_and_share_script_budget(raw_project,tmp_path):
    session,peer=routed(raw_project,tmp_path)
    workspace=DebugWorkspace();workspace.sessions[session.run_id]=session
    common=dict(project=str(raw_project.path),run=session.run_id,context='machine')
    try:
        methods=[('save-le-source-state',dict(name='le.json',max_bytes=16*1024**2)),
                 ('load-le-source-state',dict(artifact='id')),
                 ('le-rewind-start',dict(max_steps=2)),('le-rewind-status',{}),
                 ('le-rewind-record',{}),('le-rewind',dict(node='node-id'))]
        for name,params in methods:
            assert name in OPERATIONS and 'debug-'+name in METHODS
            reply=respond(dict(method='debug-'+name,params={**common,**params}),debugger=workspace)
            assert reply['ok'],reply
        session.calls=[]
        report=execute_script(session,route(dict(op='save-le-source-state',**{'as':'saved'}),
            dict(op='load-le-source-state',artifact='$saved.artifact'),
            dict(op='le-rewind-start',**{'as':'dag'}),
            dict(op='le-rewind-record'),
            dict(op='le-rewind',history='$dag.history',node='node-id')),timeout_ms=500)
        assert report['ok'],report
        assert [c[0] for c in session.calls]==['save','load','start','record','rewind']
        assert session.calls[1][1]=='le-artifact' and session.calls[-1][1:3]==('le-history','node-id')
        assert all(1<=c[-1]<=500 for c in session.calls) and peer.calls==[]
        for name,capability in [('load-le-source-state','le_source_checkpoints'),('le-rewind','le_source_histories')]:
            session.capabilities[capability]=False
            denied=respond(dict(method='debug-'+name,params={**common,**({'artifact':'id'} if 'load' in name else {'node':'id'})}),debugger=workspace)
            assert not denied['ok']
        with pytest.raises(ValueError,match='not enabled'):
            validate_script(route(dict(op='save-le-source-state')),session=session)
    finally: workspace.sessions.clear();session.close()


def test_old_mz_and_fork_routes_refuse_le_companion_before_guest_effect(raw_project,tmp_path,monkeypatch):
    session,peer=stopped_session(raw_project,tmp_path);session.__class__=QemuDOSProcessSession
    with raw_project.transaction(True):
        raw_project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
            ('le-id',session.run_id,'le.json','le-source-state','unused',b'bad',
             json.dumps(dict(format='fdisbull-qemu-dos-le-checkpoint-1'))))
    try:
        with pytest.raises(ValueError,match='require load_le_source_state'):
            session.load_state('le-id')
        monkeypatch.setattr(raw_project,'debug_state_info',lambda artifact:dict(metadata=dict(format='fdisbull-qemu-dos-le-checkpoint-1')))
        with pytest.raises(ValueError,match='state forks'):
            raw_project.debug_fork_state('le-id','unused','unused')
        assert peer.calls==[]
    finally: session.__class__=MachineDebugSession;session.close()


def test_le_provider_installation_and_call_share_original_lock_and_deadline(runtime,monkeypatch):
    import time
    from types import SimpleNamespace
    from fdisbull import qemu_dos_le_history
    session=runtime.session;owner=session.vm
    inherited=time.monotonic()+1;session._rpc_deadline=inherited;order=[]
    def install(selected):
        assert selected is session and owner.lock._is_owned()
        assert session.vm is owner and session._deadline<=inherited
        order.append('install')
        def status(*,history):
            assert owner.lock._is_owned() and session._deadline<=inherited
            order.append('status');return dict(history=history)
        return SimpleNamespace(rewind_status=status)
    monkeypatch.setattr(qemu_dos_le_history,'get_provider',install)
    assert session.le_rewind_status(history='stored-history')==dict(history='stored-history')
    assert order==['install','status']
    assert session._deadline is None and owner.operation_deadline is None
    assert session._rpc_deadline==inherited
    session._rpc_deadline=time.monotonic()-1
    with pytest.raises(TimeoutError):session.le_rewind_status()
    assert order==['install','status']
