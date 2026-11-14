"""Public full/delta renderer history grammar and forwarding."""
import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from test_qemu_io_public import raw_project, stopped_session
from test_qemu_dos_frames_public import RoutedFramesSession


def script(*steps):
    return dict(format='fdisbull-script-1',backend='qemu-dos',steps=list(steps))


class RoutedDeltaSession(RoutedFramesSession):
    def timeline_start(self,max_frames=16,max_bytes=512*1024**2,max_state_bytes=128*1024**2,
        max_image_bytes=2*1024**2,max_captures=128,storage_mode='full',keyframe_interval=8,
        period_ns=16666667,*,timeline=None,timeout_ms=60000):
        self.frame_calls.append((storage_mode,keyframe_interval,period_ns,timeline,timeout_ms))
        return dict(timeline='retained',point='root',storage_mode=storage_mode,
                    completed_guest_frame=None)


def routed(project,tmp_path):
    session,peer = stopped_session(project,tmp_path)
    session.__class__ = RoutedDeltaSession
    session.metadata['backend'] = 'qemu-dos'
    session.capabilities['frame_timeline'] = True
    session.frame_calls = []
    return session,peer


@pytest.mark.parametrize('storage',['full','delta'])
def test_native_timeline_storage_grammar(storage):
    step = dict(op='timeline-start',storage_mode=storage,keyframe_interval=2)
    assert validate_script(script(step)) == [step]


def test_json_delta_options_reach_owned_session(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    workspace = DebugWorkspace(); workspace.sessions[session.run_id] = session
    try:
        reply = respond(dict(method='debug-timeline-start',params=dict(project=str(raw_project.path),
            run=session.run_id,context='machine',storage_mode='delta',keyframe_interval=3,
            period_ns=20_000_000,timeout_ms=400)),debugger=workspace)
        assert reply['ok'] and reply['result']['storage_mode'] == 'delta', reply
        assert session.frame_calls == [('delta',3,20_000_000,None,400)] and peer.calls == []
    finally:
        workspace.sessions.clear(); session.close()


def test_saved_script_delta_options_reach_owned_session(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    report = execute_script(session,script(dict(op='timeline-start',storage_mode='delta',
        keyframe_interval=2,period_ns=20_000_000)),timeout_ms=500)
    assert report['ok'] and report['steps'][0]['result']['storage_mode'] == 'delta', report
    assert session.frame_calls[0][:3] == ('delta',2,20_000_000) and peer.calls == []


@pytest.mark.parametrize('step',[dict(op='timeline-start',storage_mode='unknown'),
    dict(op='timeline-start',storage_mode='delta',keyframe_interval=0),
    dict(op='timeline-start',storage_mode='delta',keyframe_interval=129)])
def test_invalid_delta_options_reject_script_before_guest(step):
    with pytest.raises(ValueError): validate_script(script(step))
