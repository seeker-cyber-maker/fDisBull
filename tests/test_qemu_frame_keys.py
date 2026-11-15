"""Host ownership, CAS, journal and timeline frame-key contracts."""
from copy import deepcopy
from types import MethodType
import pytest
from fdisbull.qemu_frame_keys import (FRAME_KEY_COMMANDS, QemuFrameKeysMixin,
    validate_frame_key_checkpoint, adopt_frame_keys)
from test_qemu_dos_frames import frames, start
from test_qemu_dos_history import project, session


@pytest.fixture
def keys(frames, monkeypatch):
    frames.__class__ = type('KeysHarness',(QemuFrameKeysMixin,type(frames)),{})
    frames.vm.qmp_commands |= FRAME_KEY_COMMANDS
    frames._input_schedule_bound = lambda: False
    frames._input_no_transaction = lambda: None
    monkeypatch.setattr('fdisbull.qemu_instrumented_checkpoint.preflight',lambda session:None)
    state = dict(**{'api-version':1,'epoch':1,'active':False,'valid':True,'generation':0,
        'held':[],'edge-capacity':2,'repeat-supported':False,'accepted-edges':0,
        'device-path':'/machine/kbd','device-type':'ps2-kbd','scan-enabled':True,
        'scancode-set':2,'translated':True,'modifier-mask':0,'fifo-count':0,
        'fifo-sha256':'0'*64,'controller-status':0,'controller-mode':0,
        'controller-pending':0,'controller-obsrc':0,'controller-obdata':0,
        'throttle-deadline-ns':0,'foreign-held':[]})
    state.update({'fifo-read-pointer':0,'fifo-write-pointer':0,
                  'fifo-command-pointer':-1,'write-command':-1})
    old = frames.vm.qmp.call
    def call(name,args=None,**kwargs):
        if name == 'x-fdisbull-query-frame-keys': return deepcopy(state)
        if name == 'x-fdisbull-apply-frame-key-edges':
            assert args['expected-generation'] == state['generation']
            held = set(state['held'])
            for edge in args['edges']:
                (held.add if edge['pressed'] else held.remove)(edge['key'])
            state.update(active=True,token=args['token'],held=sorted(held),
                         generation=state['generation']+1)
            state['accepted-edges'] += len(args['edges'])
            return deepcopy(state)
        if name == 'x-fdisbull-detach-frame-keys':
            assert not state['held']
            state['active']=False; state.pop('token'); state['generation'] += 1
            return deepcopy(state)
        return old(name,args)
    frames.vm.qmp.call = call
    frames.key_state = state
    return frames


def test_atomic_edges_and_alias_duplicate_validation(keys):
    receipt = keys.frame_inputs([dict(key='esc',pressed=True)])
    assert receipt['held'] == ['escape'] and keys.key_state['held'] == ['esc']
    with pytest.raises(ValueError): keys.frame_inputs([dict(key='escape',pressed=True)])
    assert keys.frame_inputs([dict(key='escape',pressed=False)])['held'] == []
    keys._frame_keys_before_physical_input()
    assert not keys.key_state['active']


def test_foreign_physical_and_capacity_refuse_before_effect(keys):
    keys.key_state['edge-capacity']=0
    with pytest.raises(ValueError,match='capacity'):
        keys.frame_inputs([dict(key='a',pressed=True)])
    assert not keys.key_state['active'] and not keys.events
    keys.vm._physical_input = dict(valid=True,pending=[],leases={'physical':{}})
    with pytest.raises(ValueError,match='released'):
        keys.frame_inputs([dict(key='a',pressed=True)])


def test_ordinary_foreign_hold_can_be_released_but_cannot_be_checkpointed(keys):
    keys.key_state['foreign-held'] = ['shift']
    keys._frame_keys_before_physical_input()
    with pytest.raises(ValueError,match='Foreign'):
        keys._frame_keys_checkpoint_preflight()
    assert not keys.closed and not keys.key_state['active']


def test_dirty_timeline_journal_and_no_pin(keys):
    start(keys)
    receipt = keys.frame_inputs([dict(key='a',pressed=True)])
    status = keys.timeline_status()
    assert status['current_dirty'] and status['valid'] and receipt['held']==['a']
    with pytest.raises(ValueError,match='dirty'):
        keys.timeline_pin()
    manifest = keys._frame_manifest()
    assert manifest['pending'] is None and manifest['pending_inputs'][0]['held']==['a']


def test_native_capacity_refusal_keeps_timeline_cursor(keys):
    root = start(keys)
    keys.key_state['edge-capacity']=0
    result = keys.timeline_advance(inputs=[dict(frame=0,edges=[dict(key='a',pressed=True)])])
    assert result['outcome']=='input_refused' and result['cursor']==root['cursor']
    assert not keys.key_state['active'] and not keys.closed


def test_scheduled_edges_captured_at_renderer_point(keys):
    start(keys)
    result = keys.timeline_advance(inputs=[dict(frame=0,edges=[dict(key='a',pressed=True)])])
    assert result['completed_frames'] == 1
    assert result['nodes'][-1]['frame']['keys'] == ['a']
    manifest = keys._frame_manifest()
    assert not manifest['input_dirty'] and manifest['pending_inputs'] == []
    assert manifest['input_journal'][0]['held'] == ['a']


def test_scheduled_future_capacity_preserves_committed_prefix(keys):
    start(keys)
    old = keys.capture_display
    def capture(*args,**kwargs):
        result = old(*args,**kwargs)
        keys.key_state['edge-capacity'] = 0
        return result
    keys.capture_display = capture
    result = keys.timeline_advance(frames=2,inputs=[
        dict(frame=0,edges=[dict(key='a',pressed=True)]),
        dict(frame=1,edges=[dict(key='a',pressed=False)])])
    assert result['outcome']=='input_refused' and result['recorded_frames']==1
    assert result['nodes'][-1]['frame']['keys']==['a'] and result['valid']
    assert keys.vm.qmp.calls.count('x-fdisbull-arm-display-frame') == 1


def test_apply_lost_reply_closes_without_replay(keys):
    old = keys.vm.qmp.call
    def lost(name,args=None,**kwargs):
        if name == 'x-fdisbull-apply-frame-key-edges':
            old(name,args,**kwargs)
            raise TimeoutError('lost response')
        return old(name,args,**kwargs)
    keys.vm.qmp.call = lost
    with pytest.raises(TimeoutError): keys.frame_inputs([dict(key='a',pressed=True)])
    assert keys.closed and keys.key_state['held']==['a']


def test_checkpoint_proof_and_adoption(keys):
    keys.frame_inputs([dict(key='a',pressed=True)])
    native=deepcopy(keys.key_state)
    fields={'active','generation','accepted-edges','held','device-path','device-type',
        'scan-enabled','scancode-set','translated','modifier-mask','fifo-count','fifo-sha256',
        'controller-status','controller-mode','controller-pending','controller-obsrc','controller-obdata','throttle-deadline-ns'}
    fields.update(('fifo-read-pointer','fifo-write-pointer','fifo-command-pointer','write-command'))
    saved={k:native[k] for k in fields};saved['source-epoch']=native['epoch']
    assert validate_frame_key_checkpoint(saved,epoch=1)==saved
    with pytest.raises(ValueError): validate_frame_key_checkpoint(saved,epoch=2)
    native['token']='fresh';native['epoch']=2
    assert adopt_frame_keys(keys.vm,native,expected_held=['a'])['token']=='fresh'


def test_idle_highwater_and_signed_throttle_checkpoint(keys):
    keys.key_state.update(generation=8,**{'throttle-deadline-ns':-1})
    assert keys.frame_inputs([dict(key='a',pressed=True)])['native']['generation'] == 9
    keys.frame_inputs([dict(key='a',pressed=False)])
    keys._frame_keys_before_physical_input()
    assert keys.key_state['generation'] == 11 and not keys.key_state['active']
    assert keys._frame_keys_query()['throttle-deadline-ns'] == -1


def test_standard_profile_checkpoint_never_queries_native_keys(keys):
    keys.vm.machine_configuration = {'clock_profile':{'profile':'standard'}}
    old = keys.vm.qmp.call
    def deny(name,args=None,**kwargs):
        if name.startswith('x-fdisbull-') and 'frame-key' in name:
            pytest.fail('standard profile must not query frame keys')
        return old(name,args,**kwargs)
    keys.vm.qmp.call = deny
    assert keys._frame_keys_checkpoint_preflight() is None
    keys._frame_keys_before_physical_input()


@pytest.mark.parametrize('field', ['generation','accepted-edges'])
def test_detach_counter_mismatch_closes_owner(keys,field):
    keys.frame_inputs([dict(key='a',pressed=True)])
    keys.frame_inputs([dict(key='a',pressed=False)])
    call = keys.vm.qmp.call
    def malformed(name,args=None,**kwargs):
        result = call(name,args,**kwargs)
        if name == 'x-fdisbull-detach-frame-keys': result[field] += 1
        return result
    keys.vm.qmp.call = malformed
    with pytest.raises(Exception,match='detach'):
        keys._frame_keys_before_physical_input()
    assert keys.closed


@pytest.fixture
def scheduled_input(keys):
    from fdisbull.qemu_input import QemuPhysicalInputMixin
    state = dict(valid=True,pending=[],leases={},schedule={'bound':True},
                 schedule_receipt={'requires_resolution':True},sequence=0)
    keys._input_storage = lambda:state
    keys._input_schedule_bound = lambda:bool(state['valid'] and state['schedule']['bound'])
    keys._input_prepare = MethodType(QemuPhysicalInputMixin._input_prepare,keys)
    keys._input_receipt = lambda delivery,**fields:dict(delivery=delivery,**fields)
    keys._input_persist = lambda *args:None
    keys._input_schedule_before_cancel = lambda:None
    keys.vm.qmp_commands.add('input-send-event')
    keys.vm.qmp_commands.update(__import__('fdisbull.qemu_input_schedule',fromlist=['INPUT_SCHEDULE_COMMANDS']).INPUT_SCHEDULE_COMMANDS)
    old = keys.vm.qmp.call
    def call(name,args=None,**kwargs):
        if name == 'query-status': return {'running':False}
        return old(name,args,**kwargs)
    keys.vm.qmp.call = call
    keys.clock_observe = lambda: {'stopped':True}
    return keys,state


def test_bound_schedule_can_observe_and_cancel_without_frame_query(scheduled_input):
    from fdisbull.qemu_input import QemuPhysicalInputMixin
    from fdisbull.qemu_input_schedule import QemuScheduledInputMixin
    keys,state = scheduled_input
    keys._frame_keys_before_physical_input = lambda:pytest.fail('must not query bound schedule')
    assert QemuScheduledInputMixin._input_schedule_context(keys) == {'stopped':True}
    receipt = QemuPhysicalInputMixin.input_cancel_pending(keys)
    assert receipt['delivery']=='cancelled_unsent' and state['schedule']['bound'] is False


def test_initial_schedule_admission_runs_frame_owner_guard(scheduled_input):
    from fdisbull.qemu_input_schedule import QemuScheduledInputMixin
    keys,state = scheduled_input
    state['schedule']['bound'] = False
    seen = []
    keys._frame_keys_before_physical_input = lambda:seen.append('guard')
    QemuScheduledInputMixin._input_schedule_context(keys)
    assert seen == ['guard']


def test_bound_schedule_and_frame_owner_is_refused(scheduled_input):
    from fdisbull.dosbox_rpc import DebuggerError
    from fdisbull.qemu_input_schedule import QemuScheduledInputMixin
    keys,state = scheduled_input
    keys.vm._frame_key_owner = {'token':'conflicting'}
    with pytest.raises(DebuggerError,match='owner|ownership|schedule'):
        QemuScheduledInputMixin._input_schedule_context(keys)
