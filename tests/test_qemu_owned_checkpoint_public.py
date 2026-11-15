"""Explicit machine recovery must not widen source-bound checkpoint routes."""
import json

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_dos_process import QemuDOSProcessSession
from fdisbull.qemu_machine import MachineDebugSession
from test_qemu_io_public import raw_project, stopped_session


def route(*steps, backend='qemu-dos'):
    return dict(format='fdisbull-script-1',backend=backend,steps=list(steps))


class RoutedMachineSession(MachineDebugSession):
    @property
    def script_operations(self):
        return super().script_operations | {'save-machine-state','load-machine-state'}

    def save_machine_state(self,name='dos-owned-machine.qcow2',*,max_bytes=None):
        self.calls.append(('save',name,max_bytes))
        return dict(artifact='machine-artifact')

    def load_machine_state(self,artifact,*,timeout_ms=60000):
        self.calls.append(('load',artifact,timeout_ms))
        return dict(machine_state_restored=True,source_binding_restored=False)


def routed(project,tmp_path):
    session,peer=stopped_session(project,tmp_path)
    session.__class__=RoutedMachineSession
    session.metadata['backend']='qemu-dos'
    session.capabilities['owned_machine_checkpoints']=True
    session.calls=[]
    return session,peer


def test_explicit_machine_routes_are_discoverable_and_literal_admitted():
    steps=[dict(op='save-machine-state',name='owned.qcow2',max_bytes=100,**{'as':'saved'}),
           dict(op='load-machine-state',artifact='$saved.artifact',timeout_ms=500)]
    assert validate_script(route(*steps))==steps
    for name in ('save-machine-state','load-machine-state'):
        assert name in OPERATIONS and 'debug-'+name in METHODS


@pytest.mark.parametrize('step',[
    dict(op='save-machine-state',name='../escape'),
    dict(op='save-machine-state',name='$controls.name'),
    dict(op='save-machine-state',max_bytes=True),
    dict(op='save-machine-state',max_bytes=128*1024**2+1),
    dict(op='load-machine-state',artifact='id',timeout_ms=0),
    dict(op='load-machine-state',artifact='id',timeout_ms=True),
    dict(op='load-machine-state',artifact='id',timeout_ms='$controls.timeout'),
    dict(op='load-machine-state',artifact=42),
    dict(op='load-machine-state',artifact=''),
])
def test_malformed_new_operation_refuses_before_earlier_effect(raw_project,tmp_path,step):
    session,peer=routed(raw_project,tmp_path)
    try:
        with pytest.raises((ValueError,TypeError)):
            execute_script(session,route(dict(op='save-machine-state'),step))
        assert session.calls==[] and peer.calls==[]
    finally:
        session.close()


@pytest.mark.parametrize('backend',[None,'dosbox','qemu-machine','qemu-chip8'])
def test_other_backend_cannot_admit_owned_machine_grammar(backend):
    with pytest.raises(ValueError):
        validate_script(route(dict(op='save-machine-state'),backend=backend))


def test_json_and_script_use_distinct_methods_and_inherit_budget(raw_project,tmp_path):
    session,peer=routed(raw_project,tmp_path)
    workspace=DebugWorkspace();workspace.sessions[session.run_id]=session
    common=dict(project=str(raw_project.path),run=session.run_id,context='machine')
    try:
        reply=respond(dict(method='debug-save-machine-state',params={**common,'name':'owned.qcow2','max_bytes':400}),debugger=workspace)
        assert reply['ok'],reply
        loaded=respond(dict(method='debug-load-machine-state',params={**common,'artifact':'id','timeout_ms':300}),debugger=workspace)
        assert loaded['ok'] and loaded['result']['source_binding_restored'] is False
        report=execute_script(session,route(dict(op='save-machine-state',**{'as':'saved'}),
            dict(op='load-machine-state',artifact='$saved.artifact',timeout_ms=600000)),timeout_ms=200)
        assert report['ok'],report
        assert session.calls[:2]==[('save','owned.qcow2',400),('load','id',300)]
        assert session.calls[-1][0:2]==('load','machine-artifact')
        assert 1<=session.calls[-1][2]<=200 and peer.calls==[]
        session.capabilities['owned_machine_checkpoints']=False
        denied=respond(dict(method='debug-load-machine-state',params={**common,'artifact':'id'}),debugger=workspace)
        assert not denied['ok']
        with pytest.raises(ValueError,match='not enabled'):
            validate_script(route(dict(op='save-machine-state')),session=session)
    finally:
        workspace.sessions.clear();session.close()


def test_ordinary_load_never_falls_back_to_machine_loader(raw_project,tmp_path,monkeypatch):
    session,peer=stopped_session(raw_project,tmp_path)
    session.__class__=QemuDOSProcessSession
    session._process={}
    with raw_project.transaction(True):
        raw_project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?,?,?,?,?)',
            ('machine-id',session.run_id,'owned.qcow2','machine-state','unused',b'bad',
             json.dumps(dict(format='fdisbull-qemu-owned-machine-qcow2-v1'))))
    monkeypatch.setattr(session,'_load_entry_state_v1',lambda *a,**kw:pytest.fail('Wrong loader dispatched'))
    with pytest.raises(ValueError,match='require load_machine_state'):
        session.load_state('machine-id')
    assert peer.calls==[]
    # Native test-peer close has no DOS lifecycle; restore its base class.
    session.__class__=MachineDebugSession
    session.close()
