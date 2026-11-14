"""Public routing and script admission for native comparative trials."""
import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import MachineDebugSession
from test_qemu_io_public import raw_project, stopped_session


class RoutedExperimentSession(MachineDebugSession):
    def controls(self):
        self.calls.append(('controls',))
        return dict(breakpoints=[],hooks=[])

    def save_experiment(self,name,*,script=None,script_id=None,observations=None):
        self.calls.append(('save',name,script,script_id,observations))
        return dict(artifact='experiment-id')

    def restore_experiment(self,experiment):
        self.calls.append(('restore',experiment))
        return dict(experiment=experiment,hit_counts_restored=True)

    def compare_experiment(self,experiment,*,layers,timeout_ms=60000):
        self.calls.append(('compare',experiment,layers,timeout_ms))
        return dict(ok=True,baseline_restored=True,comparison=dict(complete=True,observed_difference=False))


def test_native_experiment_json_routes_preserve_explicit_arguments(raw_project,tmp_path):
    session,peer=stopped_session(raw_project,tmp_path)
    session.__class__=RoutedExperimentSession
    session.metadata['backend']='qemu-dos';session.calls=[]
    workspace=DebugWorkspace();workspace.sessions[session.run_id]=session
    route=dict(format='fdisbull-script-1',backend='qemu-dos',steps=[dict(op='registers')])
    common=dict(project=str(raw_project.path),run=session.run_id,context='machine')
    try:
        for method,params in [
            ('debug-controls',{}),
            ('debug-save-experiment',dict(name='trial.json',script=route,observations=[dict(address='0x10000',length=2)])),
            ('debug-restore-experiment',dict(experiment='experiment-id')),
            ('debug-compare-experiment',dict(experiment='experiment-id',layers=['candidate'],timeout_ms=500)),
        ]:
            reply=respond(dict(method=method,params={**common,**params}),debugger=workspace)
            assert reply['ok'],reply
        assert session.calls == [
            ('controls',),('save','trial.json',route,None,[dict(address='0x10000',length=2)]),
            ('restore','experiment-id'),('compare','experiment-id',['candidate'],500)]
        assert not peer.calls
    finally:
        workspace.sessions.clear();session.close()


def test_experiment_script_uses_existing_bounded_operation_grammar():
    steps=[dict(op='step'),dict(op='registers'),dict(op='memory',address='0x10000',length=2),
           dict(op='trace',count=2),dict(op='screenshot'),dict(op='assert',value=1,equals=1)]
    assert validate_script(dict(format='fdisbull-script-1',backend='qemu-dos',steps=steps))==steps
