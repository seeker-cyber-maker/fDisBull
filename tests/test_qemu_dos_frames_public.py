"""Public JSON/script contracts for native renderer-publication timelines."""
import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import OPERATIONS, execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.qemu_machine import MachineDebugSession
from test_qemu_io_public import raw_project, stopped_session


def script(*steps, backend='qemu-dos'):
    return dict(format='fdisbull-script-1', backend=backend, steps=list(steps))


class RoutedFramesSession(MachineDebugSession):
    @property
    def script_operations(self):
        return super().script_operations | {'timeline-start','timeline-advance','timeline-rewind',
            'timeline-status','timeline-image','timeline-pin','timeline-stop'}

    def timeline_start(self, max_frames=16, max_bytes=512*1024**2, max_state_bytes=128*1024**2,
                       max_image_bytes=2*1024**2, max_captures=128, storage_mode='full',
                       keyframe_interval=8, period_ns=16666667, *, timeline=None, timeout_ms=60000):
        self.frame_calls.append(('start', period_ns, timeline, timeout_ms))
        return dict(timeline='manifest',point='root',unit='completed synchronous renderer update',completed_guest_frame=None)

    def timeline_advance(self, frames=1, inputs=None, timeout_ms=60000):
        self.frame_calls.append(('advance',frames,inputs,timeout_ms))
        return dict(timeline='manifest2',point='child',outcome='completed',completed_frames=frames,completed_guest_frame=None)

    def timeline_rewind(self, frames=1, policy=None, *, timeline=None, point=None, timeout_ms=60000):
        self.frame_calls.append(('rewind',frames,policy,timeline,point,timeout_ms))
        return dict(timeline=timeline,point=point,completed_guest_frame=None)

    def timeline_image(self, name='frame.png', *, timeline=None, point=None):
        self.frame_calls.append(('image',name,timeline,point))
        return dict(artifact='cached-png',point=point,completed_guest_frame=None)


def routed(project,tmp_path):
    session, peer = stopped_session(project,tmp_path)
    session.__class__ = RoutedFramesSession
    session.metadata['backend'] = 'qemu-dos'
    session.capabilities['frame_timeline'] = True
    session.frame_calls = []
    return session,peer


def test_renderer_timeline_routes_and_saved_script_are_discoverable():
    for name in ('timeline-start','timeline-advance','timeline-rewind','timeline-status',
                 'timeline-image','timeline-pin','timeline-stop'):
        assert 'debug-' + name in METHODS
        assert name in OPERATIONS
    steps = [dict(op='timeline-start',period_ns=20_000_000),
             dict(op='timeline-advance',frames=1),
             dict(op='timeline-rewind',timeline='$saved.timeline',point='$saved.point')]
    assert validate_script(script(*steps)) == steps


def test_json_timeline_routes_forward_manifest_and_point(raw_project,tmp_path):
    session, peer = routed(raw_project,tmp_path)
    workspace = DebugWorkspace(); workspace.sessions[session.run_id] = session
    try:
        reply = respond(dict(method='debug-timeline-rewind',params=dict(project=str(raw_project.path),
            run=session.run_id,context='machine',timeline='manifest',point='node',timeout_ms=400)),debugger=workspace)
        assert reply['ok'] and reply['result']['point'] == 'node', reply
        assert reply['result']['completed_guest_frame'] is None
        assert session.frame_calls == [('rewind',1,None,'manifest','node',400)] and peer.calls == []
    finally:
        workspace.sessions.clear(); session.close()


def test_saved_script_forwards_publication_period_and_remaining_budget(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    report = execute_script(session,script(dict(op='timeline-start',period_ns=20_000_000),
        dict(op='timeline-advance',frames=1,timeout_ms=500)),timeout_ms=200)
    assert report['ok'] and report['completed_steps'] == 2, report
    assert report['steps'][1]['result']['completed_guest_frame'] is None
    assert session.frame_calls[0][0:3] == ('start',20_000_000,None)
    assert session.frame_calls[1][0:3] == ('advance',1,None)
    assert 1 <= session.frame_calls[1][3] <= 200 and peer.calls == []


@pytest.mark.parametrize('step', [dict(op='timeline-start',storage_mode='delta'),
    dict(op='timeline-start',period_ns=0), dict(op='timeline-advance',frames=0),
    dict(op='timeline-advance',inputs=[dict(frame=1,edges=[])]),
    dict(op='timeline-rewind',frames=-1)])
def test_malformed_renderer_timeline_script_refuses_before_execution(step):
    with pytest.raises(ValueError):
        validate_script(script(step))
