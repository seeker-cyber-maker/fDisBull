"""Movement contracts through real public routes and witnessed RAM bindings."""
from copy import deepcopy
import json
import time

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.debug_script import validate_script
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS
from fdisbull.qemu_input_schedule import INPUT_SCHEDULE_COMMANDS
from fdisbull.qemu_movement import validate_parameters
from test_qemu_dos_source_admission import owned
from test_qemu_runtime_memory import ram, ADDRESS


def define(project, *, timed=False, bad_stop=False):
    return project.debug_define_macros(dict(format='fdisbull-macro-set-1', name='move', macros={
        'start': dict(steps=[dict(op='keyboard.press' if timed else 'keyboard.key-down', key='a', **{'as':'down'})],
                      outputs={} if timed else {'held':'$down.lease'}),
        'stop': dict(parameters={'lease':{'type':'input-lease'}},
                     steps=[dict(op='keyboard.key-up',lease='$args.lease')]*(2 if bad_stop else 1)),
    }))['id']


def options(identifier):
    return dict(macro_set=identifier, start=dict(name='start'),
        stop=dict(name='stop',args=dict(lease='$start.outputs.held')),
        observations=dict(x={'runtime_memory':dict(binding='move-state',offset=2,type='u8')},
                          stopped={'runtime_memory':dict(binding='move-state',offset=3,type='u8')}),
        until=dict(field='x',op='ge',value=3), settle=dict(field='stopped',op='eq',value=1),
        progress=dict(fields=['x'],samples=2), guest_ms=100, slice_ms=10,
        cleanup_guest_ms=30, timeout_ms=3000)


@pytest.fixture
def moving(ram):
    o,s=ram,ram.session
    s.vm.qmp_commands=set(VIRTUAL_CLOCK_COMMANDS)|set(INPUT_SCHEDULE_COMMANDS)|{'input-send-event'}
    s.vm.machine_configuration['clock_profile']={'profile':'virtual'}
    s.capabilities.update(physical_input=True,virtual_clock_budget=True,virtual_input_schedule=True)
    s.rpc,s.guest_profile=s.vm,None
    s._automatic_internal_pending=None
    o.ram[:4]=b'AB\x00\x01'
    s.bind_runtime_memory('move-state',ADDRESS,length=4,expected_hex='4142',provenance='independent fixture state',space='physical')
    o.now,o.runs,o.deliveries=0,[],[]
    o.stop_on=None
    o.progress=True
    def clock():return dict(epoch='clock-epoch',virtual_ns=o.now,run=s.run_id)
    s.clock_observe=clock
    o.arms=[]
    def schedule(delta_ns):
        assert delta_ns>0
        state=s._input_storage();state['schedule']={'bound':True}
        receipt=dict(state='armed',delay_ns=delta_ns,sequences=[r['sequence'] for r in state['pending']])
        o.arms.append(receipt)
        return receipt
    s.input_schedule=schedule
    def advance(delta_ns,*,timeout_ms):
        begin=o.now;o.now+=delta_ns
        state=s._input_storage()
        edges=deepcopy(state['pending'])
        if edges:
            o.deliveries.extend(edges)
            s._input_mark_dispatched(state,edges,'qmp_accepted')
        if state.get('schedule'):state['schedule']['bound']=False
        if state['leases']:
            o.ram[3]=0
            if o.progress:o.ram[2]+=1
        else:o.ram[3]=1
        result=dict(outcome='stopped',timed_out=False,
            clock_budget=dict(epoch='clock-epoch',start_ns=begin,stopped_ns=o.now,deadline_reached=True),
            session=dict(state='stopped',stop_reason=dict(kind='stopped',breakpoint_ids=[],native_reply='T02thread:1;')))
        o.runs.append(result)
        if o.stop_on==len(o.runs):
            result['outcome']='breakpoint'
            result['session']['stop_reason'].update(kind='breakpoint',breakpoint_ids=[7],native_reply='T05thread:1;')
        return result
    s._clock_advance_with_hooks=advance
    o.identifier=define(o.project)
    return o


def events(o,name):
    return [json.loads(r[0]) for r in o.project.db.execute('SELECT evidence FROM debug_events WHERE operation=? ORDER BY sequence',(name,))]


def test_public_move_arrives_releases_and_persists_exact_result(moving):
    o,s=moving,moving.session
    workspace=DebugWorkspace();workspace.sessions[s.run_id]=s
    try:
        reply=respond(dict(method='debug-move',params=dict(project=str(o.project.path),run=s.run_id,**options(o.identifier))),debugger=workspace)
    finally:workspace.sessions.clear()
    assert reply['ok'],reply
    result=reply['result']
    assert result['ok'] and result['complete'] and result['outcome']=='arrived',result
    assert result['format']=='fdisbull-movement-result-1' and result['clock_domain']=='QEMU_CLOCK_VIRTUAL'
    assert result['guest_elapsed_ms']==30 and result['cleanup_guest_elapsed_ms']==10
    assert len(o.runs)==4 and [e['event']['data']['down'] for e in o.deliveries]==[True,False]
    assert result['cleanup']['settled'] and s.input_state()['leases']=={} and not s._input_pending()
    assert events(o,'movement')==[{k:v for k,v in result.items() if k!='artifact'}]
    assert len(events(o,'macro'))==2 and not o.closed


def test_script_local_stop_lease_is_not_an_outer_binding_named_start(moving):
    o=moving
    selected=options(o.identifier)
    for field in selected['observations'].values():field['runtime_memory']['binding']='$bound.id'
    script=dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
        dict(op='bind-runtime-memory',name='route-bound',address=ADDRESS,length=4,
             expected_hex='4142',provenance='authored nested route',space='physical',**{'as':'bound'}),
        dict(op='assert',value='outer',equals='outer',**{'as':'start'}),
        dict(op='move',**selected,**{'as':'movement'}),
        dict(op='assert',value='$movement.ok',equals=True)])
    result=o.session.script(script)
    assert result['ok'],result
    assert result['steps'][2]['result']['cleanup']['settled']
    assert not o.session.input_state()['leases']


def test_first_debugger_stop_never_runs_cleanup_or_injects_break(moving):
    o=moving;o.stop_on=1
    result=o.session.move(**options(o.identifier))
    assert result['outcome']=='stopped' and not result['ok']
    assert result['stop_result'] is o.runs[0] and result['guest_elapsed_ms']==10
    assert len(o.runs)==1 and len(o.deliveries)==1 and o.deliveries[0]['event']['data']['down']
    assert result['cleanup']['attempted'] and not result['cleanup']['settled'] and o.closed


def test_caller_hold_is_preserved_without_start_or_cleanup(moving):
    o=moving
    lease=o.session.keyboard_key_down('left')['lease']
    before=deepcopy(o.session.input_state())
    result=o.session.move(**options(o.identifier))
    assert result['outcome']=='initial_input_not_clear' and not result['cleanup']['attempted']
    assert o.session.input_state()==before and lease in before['leases']
    assert not o.runs and not o.closed


def test_stall_is_failure_even_after_qualified_release(moving):
    o=moving;o.progress=False
    result=o.session.move(**options(o.identifier))
    assert result['outcome']=='blocked' and result['classification']=='blocked_unknown'
    assert not result['ok'] and result['cleanup']['settled'] and not o.closed
    assert len(o.runs)==3


@pytest.mark.parametrize('change',[
    {'scene':'room'},{'target':[1,2]},{'position':{'x':'x','y':'x'}},{'spatial_map':'map'},
    {'progress':{'fields':['x'],'frames':2,'frame_field':'x'}},
    {'observations':{'x':{'memory':{'address':'0x100','type':'u8'}}}},
    {'observations':{'x':{'register':'registers.rax'}}},
])
def test_unsupported_forms_refuse_before_any_observation_or_input(moving,change):
    o=moving
    before=(len(o.peer.qmp_calls),len(o.reads),len(events(o,'macro')))
    with pytest.raises(ValueError):o.session.move(**dict(options(o.identifier),**change))
    assert before==(len(o.peer.qmp_calls),len(o.reads),len(events(o,'macro')))
    assert not o.runs and not o.closed


@pytest.mark.parametrize('timed,bad_stop',[(True,False),(False,True)])
def test_control_plan_refuses_unsupported_or_duplicate_release_before_input(moving,timed,bad_stop):
    o=moving;identifier=define(o.project,timed=timed,bad_stop=bad_stop)
    with pytest.raises(ValueError):o.session.move(**options(identifier))
    assert not o.runs and not o.session._input_pending() and not o.closed


@pytest.mark.parametrize('change',[
    {'slice_ms':0},{'max_polls':True},{'cleanup_guest_ms':10001},
    {'observations':{'x':{'runtime_memory':{'binding':'$bound.id','type':'u256'}}}},
    {'observations':{'x':{'runtime_memory':{'binding':'$bound.id','type':'u8','offset':-1}}}},
    {'observations':{'x':{'runtime_memory':{'binding':'$bound.id','type':'u8','endian':'middle'}}}},
    {'progress':{'fields':['x'],'samples':0}},
    {'until':{'field':'x','op':'invalid','value':'$bound.value'}},
])
def test_known_invalid_literal_with_reference_precedes_actual_ram_write(moving,change):
    o=moving
    selected=dict(options(o.identifier),**change)
    if 'observations' not in change:
        selected['observations']['x']['runtime_memory']['binding']='$bound.id'
    script=dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
        dict(op='write-runtime-memory',binding='move-state',offset=2,data_hex='01',expected_hex='00'),
        dict(op='move',**selected)])
    with pytest.raises((ValueError,TypeError)):o.session.script(script)
    assert not o.writes and not o.runs and o.ram[2]==0


def test_frozen_state_and_stale_binding_refuse_without_input(moving):
    o=moving;s=o.session
    s._qemu_cpu_delta_history=dict(frozen=True,valid=False)
    with pytest.raises(ValueError,match='frozen'):s.move(**options(o.identifier))
    s._qemu_cpu_delta_history=None
    s._runtime_epoch='source-run:process:2';s._process['capture_epoch']=s._runtime_epoch
    result=s.move(**options(o.identifier))
    assert not result['ok'] and not o.runs and not s._input_pending() and not o.closed


def test_expired_inherited_deadline_does_not_touch_input(moving):
    o=moving;o.session._rpc_deadline=time.monotonic()-1
    with pytest.raises(TimeoutError):o.session.move(**options(o.identifier))
    assert not o.runs and not o.closed and not o.session._input_pending()


def test_uncertain_advance_retains_original_receipt_when_cleanup_fails(moving):
    o=moving
    original=dict(native_stop='T05thread:1;',prefix='authored uncertain native receipt')
    error=TimeoutError('authored late stopped reply');error.result=original
    def failed(*args,**kwargs):raise error
    o.session._clock_advance_with_hooks=failed
    def bad_close():raise OSError('authored journal cleanup failure')
    o.session.close=bad_close
    with pytest.raises(TimeoutError) as caught:o.session.move(**options(o.identifier))
    assert caught.value is error and caught.value.result is original
    assert caught.value.movement_result['failure_result'] is original
    assert caught.value.movement_result['clock_progress_complete'] is False
    assert caught.value.movement_cleanup_error=='OSError'
    assert o.closed


def test_invalid_later_control_plan_precedes_actual_ram_write(moving):
    o=moving;identifier=define(o.project,bad_stop=True)
    script=dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
        dict(op='write-runtime-memory',binding='move-state',offset=2,data_hex='01',expected_hex='00'),
        dict(op='move',**options(identifier))])
    with pytest.raises(ValueError):o.session.script(script)
    assert not o.writes and not o.runs and o.ram[2]==0


def test_unknown_control_reference_cannot_hide_known_timed_press_before_write(moving):
    o=moving;identifier=define(o.project,timed=True)
    selected=options(identifier)
    selected['stop']['args']['lease']='$outer.lease'
    script=dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
        dict(op='write-runtime-memory',binding='move-state',offset=2,data_hex='01',expected_hex='00'),
        dict(op='move',**selected)])
    with pytest.raises(ValueError,match='literal'):o.session.script(script)
    assert not o.writes and not o.runs and o.ram[2]==0


def test_identical_progress_references_are_known_duplicates_before_write(moving):
    o=moving
    selected=options(o.identifier)
    selected['progress']['fields']=['$same.field','$same.field']
    script=dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
        dict(op='write-runtime-memory',binding='move-state',offset=2,data_hex='01',expected_hex='00'),
        dict(op='move',**selected)])
    with pytest.raises(ValueError,match='unique'):o.session.script(script)
    assert not o.writes and not o.runs and o.ram[2]==0


def test_public_signature_retains_the_existing_dosbox_contract():
    import inspect
    from fdisbull.movement import MovementSessionMixin
    from fdisbull.qemu_movement import QemuMovementMixin
    assert inspect.signature(QemuMovementMixin.move)==inspect.signature(MovementSessionMixin.move)
