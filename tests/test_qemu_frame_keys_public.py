"""Public grammar and routing for native owned frame keyboard edges."""
import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script, validate_script
from fdisbull.debugger import DebugWorkspace
from test_qemu_io_public import raw_project, stopped_session
from test_qemu_dos_frames_public import RoutedFramesSession


def script(*steps):
    return dict(format='fdisbull-script-1',backend='qemu-dos',steps=list(steps))


class RoutedFrameKeysSession(RoutedFramesSession):
    @property
    def script_operations(self):
        return super().script_operations | {'frame-inputs','frame-advance'}

    def keyboard_state(self):
        return {'keyboard':{'frame_keys':sorted(self.held),'frame_edge_capacity':2,
                            'native':{'repeat-supported':False}}}

    def frame_inputs(self,edges,*,timeout_ms=1000):
        self.frame_calls.append(('inputs',edges,timeout_ms))
        for edge in edges:
            if edge['pressed']: self.held.add(edge['key'])
            else: self.held.remove(edge['key'])
        return dict(held=sorted(self.held),edges=edges,guest_consumed=None,repeat_supported=False)


def routed(project,tmp_path):
    session,peer = stopped_session(project,tmp_path)
    session.__class__ = RoutedFrameKeysSession
    session.metadata['backend'] = 'qemu-dos'
    session.capabilities.update(frame_timeline=True,frame_key_ownership=True)
    session.frame_calls = []; session.held = set()
    return session,peer


def test_native_frame_input_script_grammar_and_zero_rewind():
    steps = [dict(op='frame-inputs',edges=[dict(key='shift',pressed=True)]),
             dict(op='timeline-advance',frames=3,inputs=[dict(frame=0,edges=[dict(key='a',pressed=True)])]),
             dict(op='timeline-rewind',frames=0)]
    assert validate_script(script(*steps)) == steps


def test_json_frame_inputs_forwards_physical_edges(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    workspace = DebugWorkspace(); workspace.sessions[session.run_id] = session
    edges = [dict(key='shift',pressed=True),dict(key='a',pressed=True)]
    try:
        reply = respond(dict(method='debug-frame-inputs',params=dict(project=str(raw_project.path),
            run=session.run_id,context='machine',edges=edges,timeout_ms=400)),debugger=workspace)
        assert reply['ok'] and reply['result']['held'] == ['a','shift'], reply
        assert reply['result']['guest_consumed'] is None and reply['result']['repeat_supported'] is False
        assert session.frame_calls == [('inputs',edges,400)] and not peer.calls
    finally:
        workspace.sessions.clear(); session.close()


def test_old_native_without_frame_key_capability_rejects_whole_script_before_write(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    session.capabilities['frame_key_ownership'] = False
    writes = []
    session.write_memory = lambda *args,**kwargs:writes.append((args,kwargs))
    with pytest.raises(ValueError,match='frame.key|ownership|extension|capability'):
        execute_script(session,script(dict(op='write-memory',address=0x7c00,data_hex='90',expected_hex='00'),
            dict(op='frame-inputs',edges=[dict(key='a',pressed=True)])))
    assert writes == [] and peer.calls == []


@pytest.mark.parametrize('step', [dict(op='timeline-start',storage_mode='unknown'),
    dict(op='timeline-rewind',frames=-1),dict(op='timeline-rewind',policy={'preserve_memory':[]}),
    dict(op='frame-inputs',edges=[dict(key='a',pressed=True),dict(key='a',pressed=True)])])
def test_native_frame_key_script_invalid_forms_reject(step):
    with pytest.raises(ValueError): validate_script(script(step))


@pytest.mark.parametrize('op,outcome', [('timeline-advance','input_refused'),
                                         ('timeline-advance','interrupted'),
                                         ('frame-advance','interrupted')])
def test_incomplete_frame_advance_stops_script_with_actual_result(raw_project,tmp_path,op,outcome):
    session,peer = routed(raw_project,tmp_path)
    calls = []
    def stopped(**kwargs):
        calls.append('advance')
        return dict(outcome=outcome,completed_frames=0,stop={'outcome':'hook'})
    setattr(session, 'timeline_advance' if op == 'timeline-advance' else 'advance_frames', stopped)
    report = execute_script(session,script(dict(op=op,frames=1),
        dict(op='frame-inputs',edges=[dict(key='a',pressed=True)])))
    assert not report['ok'] and report['steps'][0]['result']['outcome'] == outcome
    assert calls == ['advance'] and session.frame_calls == [] and not session.closed


def test_released_then_reacquired_entry_hold_closes_on_later_failure(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    session.held.add('a')
    report = execute_script(session,script(
        dict(op='frame-inputs',edges=[dict(key='a',pressed=False)]),
        dict(op='frame-inputs',edges=[dict(key='a',pressed=True)]),
        dict(op='assert',value=1,equals=2)))
    assert not report['ok'] and report['input_cleanup']['closed'] and session.closed


def test_untouched_entry_hold_survives_preflight_refusal(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    session.held.add('a')
    def refused(*args,**kwargs): raise ValueError('capacity unavailable')
    session.frame_inputs = refused
    report = execute_script(session,script(dict(op='frame-inputs',edges=[dict(key='a',pressed=False)])))
    assert not report['ok'] and report['input_cleanup'] is None and not session.closed


def test_successful_restore_with_hold_closes_on_later_failure(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    session.held.add('a')
    report = execute_script(session,script(dict(op='timeline-rewind',frames=0),
        dict(op='assert',value=1,equals=2)))
    assert not report['ok'] and report['input_cleanup']['closed'] and session.closed


def test_interrupted_timeline_uses_accepted_pending_edges_for_cleanup(raw_project,tmp_path):
    session,peer = routed(raw_project,tmp_path)
    session.held.add('a')
    session.timeline_advance = lambda **kwargs: dict(outcome='interrupted',completed_frames=0,
        frames=[],pending_inputs=[dict(edges=[dict(key='a',pressed=False)]),
                                  dict(edges=[dict(key='a',pressed=True)])])
    report = execute_script(session,script(dict(op='timeline-advance',frames=1,
        inputs=[dict(frame=0,edges=[dict(key='a',pressed=False)])])))
    assert not report['ok'] and report['input_cleanup']['closed'] and session.closed
