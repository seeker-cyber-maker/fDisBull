"""Host-only renderer history contracts with a fake QMP fence."""
from copy import deepcopy
import hashlib
import io
from types import SimpleNamespace
import pytest

from fdisbull.qemu_dos_frames import FRAME_COMMANDS, QemuDOSFramesMixin
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS
from fdisbull.qemu_display import DISPLAY_COMMANDS
from test_qemu_dos_history import project, session


class FrameWire:
    def __init__(self, owner):
        self.owner = owner
        self.operation_deadline = None
        self.calls = []
        self.receipt = None
    def call(self, name, args):
        self.calls.append(name)
        if name == 'x-fdisbull-arm-display-frame':
            self.receipt = {'api-version':1,'epoch':1,'state':'armed',
                'token':args['token'],'display-token':args['display-token'],
                'baseline-update-id':self.owner.updates,'updates':self.owner.updates,
                'stop-pending':False,'stop-consumed':False}
        elif name == 'x-fdisbull-query-display-frame':
            if self.owner.ordinary and self.receipt['state'] == 'armed':
                self.owner.updates += 1
                self.receipt.update(state='completed', updates=self.owner.updates,
                    **{'completed-update-id':self.owner.updates,'published-ns':100+self.owner.updates,
                       'stop-consumed':True})
        elif name == 'x-fdisbull-cancel-display-frame':
            if self.receipt['state'] != 'completed': self.receipt['state'] = 'cancelled'
        else: raise AssertionError(name)
        return deepcopy(self.receipt)


@pytest.fixture
def frames(session):
    session.__class__ = type('FrameHarness',(QemuDOSFramesMixin,type(session)),{})
    session.vm.qmp_commands = set(session.vm.qmp_commands) | FRAME_COMMANDS | DISPLAY_COMMANDS | VIRTUAL_CLOCK_COMMANDS
    session.vm.machine_configuration = {'clock_profile':{'profile':'virtual'}}
    session.vm.qmp = FrameWire(session)
    session.updates = 0; session.ordinary = True; session.display_state = 'idle'
    session.display_observe = lambda: {'state':session.display_state,'observation_period_ns':12345678,
        'native':{'token':'window','updates':session.updates,'epoch':1},'update_id':session.updates,
        'published_ns':100+session.updates,'width':2,'height':1}
    def start(*,period_ns):
        session.display_state = 'observing'
        return session.display_observe()
    session.display_start = start
    def capture(name, *, max_bytes=None):
        from PIL import Image
        pixels = b'\x00' * 6
        output = io.BytesIO()
        Image.frombytes('RGB',(2,1),pixels).save(output,format='PNG')
        return session.project._debug_artifact(session.run_id,name,'screenshot',output.getvalue(),
            {'pixel_sha256':hashlib.sha256(pixels).hexdigest()})
    session.capture_surface = capture
    session.capture_display = capture
    session._artifact = lambda *args: session.project._debug_artifact(session.run_id,*args)
    session._run_with_hooks = lambda **kwargs: ({'outcome':'stopped','timed_out':False,'hook_hits':[],
        'session':{'state':'stopped','stop_reason':{'kind':'stopped','breakpoint_ids':[],
                   'native_reply':'T02'}}} if session.ordinary else
        {'outcome':'hook','timed_out':False,'hook_hits':[{'hook':'h'}],
         'session':{'state':'stopped','stop_reason':{'kind':'breakpoint','breakpoint_ids':['b'],
                    'native_reply':'T05'}}})
    return session


def start(frames):
    return frames.timeline_start(max_frames=5,max_bytes=65536,max_state_bytes=8192,max_image_bytes=1024)


def test_completed_publications_make_persistent_points_and_stored_image(frames):
    root = start(frames)
    assert root['unit'] == 'completed synchronous renderer update' and root['completed_guest_frame'] is None
    assert root['nodes'][0]['frame']['kind'] == 'initial-paused'
    result = frames.timeline_advance(frames=2)
    assert result['completed_frames'] == 2 and len(result['nodes']) == 3
    assert [node['frame']['update_id'] for node in result['nodes'][1:]] == [1,2]
    assert frames.timeline_image()['artifact'] == result['nodes'][-1]['frame']['image']['artifact']
    assert frames.timeline_pin()['kind'] == 'state'
    assert frames.vm.qmp.calls.count('x-fdisbull-arm-display-frame') == 2
    assert frames.vm.qmp.calls.count('x-fdisbull-cancel-display-frame') == 2


def test_hook_interrupt_ends_without_child_or_extra_resume(frames):
    root = start(frames); frames.ordinary = False
    result = frames.timeline_advance(frames=2)
    assert result['outcome'] == 'interrupted' and result['completed_frames'] == 0
    assert result['stop']['outcome'] == 'hook' and result['retained_nodes'] == 1
    assert result['valid'] is False and root['cursor'] is not None
    assert frames.vm.qmp.calls.count('x-fdisbull-arm-display-frame') == 1
    assert frames.vm.qmp.calls.count('x-fdisbull-cancel-display-frame') == 1


@pytest.mark.parametrize('kwargs',[
    {'storage_mode':'delta'}, {'max_frames':0}, {'period_ns':0},
])
def test_invalid_start_refuses_before_artifact_or_native_action(frames,kwargs):
    before = frames.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    with pytest.raises(ValueError): frames.timeline_start(**kwargs)
    assert frames.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == before
    assert frames.vm.qmp.calls == []


def test_input_and_partial_policy_refused_before_effect(frames):
    root = start(frames)
    calls = list(frames.vm.qmp.calls)
    with pytest.raises(ValueError): frames.timeline_advance(inputs=[{'frame':0,'edges':[]}])
    with pytest.raises(ValueError): frames.timeline_rewind(policy={'preserve_memory':[]})
    assert frames.vm.qmp.calls == calls and frames.timeline_status()['cursor'] == root['cursor']


def test_corrupt_cached_image_refuses_before_restore(frames):
    root = start(frames)
    frames.timeline_advance()
    image = root['nodes'][0]['frame']['image']['artifact']
    with frames.project.transaction(True):
        frames.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'bad',image))
    before = list(frames.calls)
    with pytest.raises(ValueError,match='image.*corrupt'):
        frames.timeline_rewind(point=root['cursor'])
    assert frames.calls == before and not frames.closed


def test_lost_fence_arm_reply_closes_and_leaves_pending(frames):
    start(frames)
    call = frames.vm.qmp.call
    def fail(name,args):
        if name == 'x-fdisbull-arm-display-frame': raise TimeoutError('lost arm reply')
        return call(name,args)
    frames.vm.qmp.call = fail
    with pytest.raises(TimeoutError): frames.timeline_advance()
    assert frames.closed
    row = frames.project.db.execute("SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid DESC LIMIT 1").fetchone()
    assert __import__('json').loads(bytes(row['data']))['pending']['kind'] == 'renderer-frame'


def test_unrecorded_advance_invalidates_prior_cursor(frames):
    start(frames)
    result = frames.advance_frames()
    assert result['completed_frames'] == 1 and result['completed_guest_frame'] is None
    assert frames.timeline_status()['valid'] is False


def test_fence_completed_during_pending_hook_step_does_not_continue(frames):
    start(frames)
    frames._qemu_hook_pending = 'already-hit-hook'
    steps = []
    def step_pending(**kwargs):
        steps.append('step')
        assert frames._frame_stop_after_step() is True
        return {'outcome':'step','timed_out':False,'hook_hits':[],
                'session':{'state':'stopped','stop_reason':{'kind':'stopped',
                           'breakpoint_ids':[],'native_reply':'T05'}}}
    frames._run_with_hooks = step_pending
    result = frames.timeline_advance(frames=2)
    assert result['outcome'] == 'interrupted' and result['completed_frames'] == 0
    assert result['recorded_frames'] == 0
    fence = result['stop']['renderer_frame_fence']
    assert fence['publication_completed'] is True and fence['ordinary_stop'] is False
    assert fence['observed']['completed-update-id'] == 1
    assert fence['final']['published-ns'] == 101
    import json
    last = frames.project.db.execute("SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid DESC LIMIT 1").fetchone()
    journal = json.loads(bytes(last['data']))
    assert journal['pending'] is None
    assert journal['last_stop']['renderer_frame_fence'] == fence
    assert steps == ['step'] and frames._qemu_hook_pending == 'already-hit-hook'
    assert frames.vm.qmp.calls.count('x-fdisbull-arm-display-frame') == 1
    assert frames.vm.qmp.calls.count('x-fdisbull-cancel-display-frame') == 1


def test_bounded_image_failure_closes_with_pending_and_no_screenshot_artifact(frames):
    def refuse(name, *, max_bytes=None):
        assert max_bytes == 12
        raise ValueError('PNG exceeds its bounded byte budget')
    frames.capture_surface = refuse
    with pytest.raises(ValueError,match='byte budget'):
        frames.timeline_start(max_frames=3,max_bytes=65536,max_state_bytes=8192,max_image_bytes=12)
    assert frames.closed
    assert frames.project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='screenshot'").fetchone()[0] == 0
    last = frames.project.db.execute("SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid DESC LIMIT 1").fetchone()
    assert __import__('json').loads(bytes(last['data']))['pending']['kind'] == 'renderer-root'


def test_bad_fence_generation_closes_and_preserves_intent(frames):
    start(frames)
    call = frames.vm.qmp.call
    def mismatch(name,args):
        result = call(name,args)
        if name == 'x-fdisbull-query-display-frame': result['epoch'] += 1
        return result
    frames.vm.qmp.call = mismatch
    with pytest.raises(Exception,match='frame-fence'):
        frames.timeline_advance()
    assert frames.closed
    row = frames.project.db.execute("SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid DESC LIMIT 1").fetchone()
    assert __import__('json').loads(bytes(row['data']))['pending']['kind'] == 'renderer-frame'


def test_arm_epoch_must_match_observed_window_before_execution(frames):
    start(frames)
    call = frames.vm.qmp.call
    def wrong_epoch(name,args):
        result = call(name,args)
        if name == 'x-fdisbull-arm-display-frame': result['epoch'] += 1
        return result
    frames.vm.qmp.call = wrong_epoch
    frames._run_with_hooks = lambda **kwargs: pytest.fail('guest execution must not begin')
    with pytest.raises(Exception,match='frame-fence'):
        frames.timeline_advance()
    assert frames.closed


def test_cached_png_pixels_are_bound_to_publication_before_restore(frames):
    start(frames)
    point = frames.timeline_advance()['nodes'][-1]
    point['frame']['pixel_sha256'] = '0' * 64
    with pytest.raises(ValueError,match='pixels differ'):
        frames._history_validate_node_before_restore(point)
    assert not frames.closed


def test_unrecorded_frame_receipt_is_durable_or_session_closes(frames):
    result = frames.advance_frames()
    assert result['completed_frames'] == 1
    assert [name for name,_ in frames.events].count('machine-frame-advance') == 1
    def fail(name,value):
        if name == 'machine-frame-advance': raise OSError('journal failure')
    frames._event = fail
    with pytest.raises(OSError,match='journal failure') as caught:
        frames.advance_frames()
    assert frames.closed and caught.value.result['fence']['state'] == 'completed'
