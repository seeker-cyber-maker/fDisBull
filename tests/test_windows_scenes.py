"""Windows scene contracts through an isolated native-protocol peer.

The peer is an authored state machine; real Windows acceptance is separate.
"""
import base64
import io
import json
import time
import uuid

from PIL import Image
import pytest

from fdisbull.debugger import DebugSession
from fdisbull.project import Project
from fdisbull.scenes import SceneError
from fdisbull.windows_ui import WindowsUIMixin,WindowsInputError,WindowsCaptureUnavailable,_events
from fixtures_formats import pe64


class WindowsProgram(WindowsUIMixin):
    backend_name='wine-qemu'
    _artifact=DebugSession._artifact
    def __init__(self,project):
        self.project=project;self.version=project.version(1);self.run_id=uuid.uuid4().hex
        self.metadata={'source_sha256':project.meta['source_sha256'],'runtime_profile':'pe64-win32-debug-2'}
        self.mode_id=0;self._frame=None;self.counter=0;self.modal=False;self.native_revision=1
        self.calls=[];self.events=[];self.pending=[];self.window=123;self.rgb=None
        self.failure=None;self.stop='slice'
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                               (self.run_id,1,'now',None,'stopped',json.dumps(self.metadata)))
        self._windows_ui_initialize()
    def _event(self,name,result):self.events.append((name,result))
    def _address(self,address,length=1):return self.project._address(address)
    def status(self):return {'state':'stopped'}
    def memory(self,address,*,length,cs=None):return {'hex':self.counter.to_bytes(length,'little').hex()}
    def call(self,method,params=None,**kwargs):
        self.calls.append((method,params))
        if self.failure==method:raise TimeoutError('authored uncertain '+method)
        if method=='screenshot':
            rgb=self.rgb if self.rgb is not None else ((0,0,255) if self.modal else (255,0,0) if self.counter else (0,0,0))
            bgr=bytes([rgb[2],rgb[1],rgb[0],0])*4
            return {'width':2,'height':2,'window':self.window,'frame_revision':self.native_revision,
                    'bgra_base64':base64.b64encode(bgr).decode()}
        if method in ('keyboard','click'):
            self.pending.append(method);self.native_revision+=1
            return {'queued':len(params.get('events',[])) if method=='keyboard' else 3}
        if method=='keyboard-state':return {'pending':len(self.pending),'delivered_to_OS':0,'clock_ms':0,'revision':self.native_revision}
        if method=='slice':
            if self.pending:
                if self.pending.pop(0)=='keyboard' and self.modal:self.modal=False
                else:self.counter+=1
            self.native_revision+=1;time.sleep(.001)
            return {'state':'stopped','stop_reason':{'kind':self.stop,'address':'0x140001000'}}
        raise AssertionError(method)


@pytest.fixture
def program(tmp_path):
    exe=tmp_path/'authored.exe';exe.write_bytes(pe64())
    with Project.create(tmp_path/'windows.fdb',exe) as project:
        session=WindowsProgram(project)
        try:yield session
        finally:session._windows_ui_close()


def pixel(rgb):return {'pixels':{'samples':[{'x':0,'y':0,'rgb':rgb}]}}


def definition(frame,*,match=None,handlers=None):
    yes={'constant':True}
    return {'format':'fdisbull-scene-1','width':2,'height':2,
            'mode_id':frame['metadata']['mode_id'],'reference':frame['artifact'],
            'context':{'state':'authored Windows button','triggers':['fresh stopped fixture']},
            'match':match or yes,
            'handlers':handlers or [],
            'objects':[{'name':'button','context':{'state':'button','triggers':['fresh stopped fixture']},
                        'area':{'rect':[0,0,2,2]},'point':[0,0],'visible':yes,'enabled':yes,
                        'ready':pixel([0,0,0]),'outcome':pixel([255,0,0]),'outcome_phase':'state',
                        'action':{'kind':'click'},'guest_ms':1000,'timeout_ms':1000}]}


def test_keyboard_packets_keep_real_scan_order_timing_and_explicit_release(program):
    result=program.keyboard_press('up',modifiers=('ctrl',),hold_ms=17,gap_ms=9)
    method,params=next(c for c in program.calls if c[0]=='keyboard')
    assert method=='keyboard' and params['duration_ms']==26
    assert params['events']==[
        {'scan_code':29,'down':True,'extended':False,'delay_ms':0},
        {'scan_code':72,'down':True,'extended':True,'delay_ms':0},
        {'scan_code':72,'down':False,'extended':True,'delay_ms':17},
        {'scan_code':29,'down':False,'extended':False,'delay_ms':17}]
    assert result['dispatch_outcome']=='queued' and result['requested_events']==4
    assert result['application_consumption_verified'] is False and result['host_input_capture'] is False
    before=list(program.calls)
    with pytest.raises(ValueError,match='60000'):
        program.keyboard_type('a'*64,hold_ms=1000,gap_ms=1000)
    assert program.calls==before


def test_keyboard_ascii_shift_is_released_and_nonascii_refuses_before_dispatch(program):
    events=_events(text='A!z',hold_ms=10,gap_ms=3)
    assert [e['scan_code'] for e in events]==[42,30,30,42,42,2,2,42,44,44]
    assert [e['down'] for e in events]==[True,True,False,False,True,True,False,False,True,False]
    assert events[4]['delay_ms']==13 and events[8]['delay_ms']==26
    with pytest.raises(ValueError):program.keyboard_type('é')
    assert not program.calls
    state=program.keyboard.state()
    assert state['pending']==0 and state['application_consumption_verified'] is False


def test_owned_key_leases_cannot_duplicate_interrupt_or_survive_restore_epoch(program):
    lease=program.keyboard.key_down('up')['lease']
    assert program.calls[-1][1]['events']==[{'scan_code':72,'down':True,'extended':True,'delay_ms':0}]
    before=list(program.calls)
    with pytest.raises(ValueError,match='owned lease'):program.keyboard_key_down('up')
    with pytest.raises(ValueError,match='owned key lease'):program.keyboard_press('up')
    with pytest.raises(ValueError,match='owned key lease'):program.keyboard_type('a')
    assert program.calls==before
    released=program.keyboard.key_up(lease)
    assert released['consumed'] and program.calls[-1][1]['events'][0]['down'] is False
    with pytest.raises(ValueError,match='Unknown'):program.keyboard_key_up(lease)
    stale=program.keyboard_key_down('ctrl')['lease'];program._windows_invalidate_input_leases()
    with pytest.raises(ValueError,match='Unknown'):program.keyboard_key_up(stale)


def test_probe_identity_is_passive_and_changed_pixels_or_native_epoch_stale_click(program):
    first=program.frame_probe([[0,0],[1,1]])
    second=program.frame_probe([])
    assert first['frame_id']==second['frame_id'] and first['state_revision']==second['state_revision']
    assert first['samples'][0]['rgb']==[0,0,0]
    program.rgb=(1,2,3)
    with pytest.raises(ValueError,match='frame identity'):
        program.click(0,0,frame_id=first['frame_id'],mode_id=first['mode_id'])
    assert not program.pending
    current=program.frame_probe([]);program._windows_state_changed()
    with pytest.raises(ValueError,match='frame identity'):
        program.click(0,0,frame_id=current['frame_id'])
    assert not program.pending


def test_probe_refuses_incomplete_or_outside_capture_without_input(program,monkeypatch):
    with pytest.raises(ValueError,match='outside'):program.frame_probe([[2,0]])
    call=program.call
    def incomplete(method,params=None,**kwargs):
        result=call(method,params,**kwargs)
        if method=='screenshot':result['bgra_base64']=base64.b64encode(b'bad').decode()
        return result
    monkeypatch.setattr(program,'call',incomplete)
    with pytest.raises(ValueError,match='Incomplete'):program.frame_probe([])
    assert not program.pending


def test_no_hwnd_is_recoverable_unavailability_and_does_not_run_or_submit_input(program,monkeypatch):
    original=program.call
    persisted=[]
    monkeypatch.setattr(program,'_event',lambda name,value:persisted.append((name,json.loads(json.dumps(value)))))
    def no_window(method,params=None,**kwargs):
        if method=='screenshot':
            program.calls.append((method,params))
            return {'available':False,'reason':'no-visible-client-window'}
        return original(method,params,**kwargs)
    program.dot_mode(True)
    with monkeypatch.context() as patch:
        patch.setattr(program,'call',no_window)
        with pytest.raises(WindowsCaptureUnavailable) as caught:program.screenshot()
        assert caught.value.capture_receipt['available'] is False
        with pytest.raises(WindowsCaptureUnavailable):program.frame_probe([])
        advanced=program.scene_advance(slice_ms=10,timeout_ms=1000)
        assert advanced['outcome']=='slice' and 'spectator_capture_error' in advanced
        assert persisted[-1][0]=='scene-advance' and 'spectator_capture_error' in persisted[-1][1]
        dot=program.dot_mode();assert dot['capture_available'] is False and dot['capture_reason']=='no-visible-client-window'
        assert program.counter==0 and not program.pending
        assert not any(method in ('keyboard','click') for method,params in program.calls)
    assert program._windows_refresh_spectator()['width']==2
    assert program.dot_mode()['capture_available'] is True


def test_named_scene_action_uses_host_slice_and_keeps_native_stop_receipt(program):
    frame=program.screenshot();scene=program.project.debug_save_scene('windows-button',definition(frame))
    result=program.scene(scene['id']).act('button')
    assert result['status']=='matched' and result['complete'] and program.counter==1
    assert result['time_basis']=='host' and result['host_active_elapsed_ms']>0
    assert 'guest_elapsed_ms' not in result
    assert result['input']['dispatch_outcome']=='queued'
    assert len([c for c in program.calls if c[0]=='click'])==1
    assert len([c for c in program.calls if c[0]=='slice'])==1
    assert not any(c[0]=='run' for c in program.calls)


def test_scene_advance_uses_backend_guarded_slice_and_preserves_watch_stop(program,monkeypatch):
    guarded=[]
    def slice_native(budget,timeout):
        guarded.append((budget,timeout))
        return {'outcome':'watchpoint','state':'stopped','stop_reason':{
            'kind':'memory-access','before_access':True,'access_address':'0x140003000'}}
    monkeypatch.setattr(program,'_scene_slice',slice_native,raising=False)
    result=program.scene_advance(slice_ms=250,timeout_ms=1000)
    assert guarded==[(250,1000)] and not program.calls
    assert result['outcome']=='watchpoint'
    assert result['session']['stop_reason']['before_access'] is True
    assert result['time_basis']=='host' and result['scene_elapsed_ms']>=0


def test_known_popup_can_dismiss_before_main_action_and_other_modals_still_block(program):
    program.modal=True
    frame=program.screenshot()
    handler={'name':'caption','when':pixel([0,0,255]),'action':{'kind':'press','key':'escape'},
             'outcome':pixel([0,0,0])}
    scene=program.project.debug_save_scene('with-popup',definition(frame,handlers=[handler]))
    result=program.scene(scene['id']).act('button',handle_popups=True)
    assert result['status']=='matched' and result['complete'] and not program.modal and program.counter==1
    assert len([c for c in program.calls if c[0]=='keyboard'])==1
    assert len([c for c in program.calls if c[0]=='click'])==1
    assert result['handlers'][0]['dispatch_outcome']=='queued'
    assert result['handlers'][1]['status']=='matched'


@pytest.mark.parametrize('modal',[False,True])
def test_wait_failure_retains_single_main_or_popup_input_without_replay(program,modal):
    program.modal=modal;frame=program.screenshot()
    handlers=([{'name':'caption','when':pixel([0,0,255]),'action':{'kind':'press','key':'escape'},
               'outcome':pixel([0,0,0])}] if modal else [])
    scene=program.project.debug_save_scene('fault',definition(frame,handlers=handlers))
    program.failure='slice'
    with pytest.raises(SceneError) as caught:
        program.scene(scene['id']).act('button',handle_popups=modal)
    assert caught.value.result['input']['dispatch_outcome']=='queued'
    assert len(program.pending)==1
    assert len([c for c in program.calls if c[0] in ('click','keyboard')])==1
    assert caught.value.result['error_type']=='TimeoutError'


def test_input_transport_failure_retains_uncertain_dispatch_and_does_not_replay(program):
    frame=program.screenshot();scene=program.project.debug_save_scene('unknown',definition(frame))
    program.failure='click'
    with pytest.raises(SceneError) as caught:program.scene(scene['id']).act('button')
    result=caught.value.result
    assert result['status']=='input-unknown' and result['input']['dispatch_outcome']=='unknown'
    assert result['input']['attempted'] and result['input']['input_id']
    assert len([c for c in program.calls if c[0]=='click'])==1


@pytest.mark.parametrize('stop',['breakpoint','exception'])
def test_native_stop_is_not_silently_resumed_as_a_completed_scene_slice(program,stop):
    frame=program.screenshot();scene=program.project.debug_save_scene('stopped',definition(frame))
    program.stop=stop
    with pytest.raises(SceneError) as caught:program.scene(scene['id']).act('button')
    assert caught.value.result['status']=='stopped' and caught.value.result['stop']['outcome']==stop
    assert len([c for c in program.calls if c[0]=='slice'])==1
    assert len([c for c in program.calls if c[0]=='click'])==1


def test_windows_observation_wait_records_host_budget_without_guest_time_claim(program):
    program.keyboard_press('a')
    result=program.wait({'counter':{'kind':'memory','address':'0x140001020','length':1}},
                        {'observation':'counter','equals':'01'},active_ms=100,timeout_screenshot=None)
    assert result['complete'] and result['matched'] and result['time_basis']=='host'
    assert result['active_elapsed_ms']>0 and 'guest_elapsed_ms' not in result
    with pytest.raises(ValueError,match='fast-forward'):
        program.wait({'n':{'kind':'memory','address':'0x140001020','length':1}},
                     {'observation':'n','equals':'01'},active_ms=100,fast_forward=True)


def test_stored_windows_png_survives_project_reopen(program,tmp_path):
    program.rgb=(17,33,65);capture=program.screenshot('retained.png')
    output=tmp_path/'export.png';database=program.project.path
    # Export from another project handle, independent of the live session.
    with Project(database) as reopened:reopened.debug_export(capture['artifact'],output)
    image=Image.open(output);assert image.size==(2,2) and image.getpixel((0,0))==(17,33,65)


def test_windows_video_signature_prevents_cross_source_scene_reuse(program):
    from fdisbull.scenes import video_signature
    frame=program.frame_probe([]);signature=video_signature(frame)
    assert signature['backend']=='wine-qemu' and signature['source_sha256']==program.project.meta['source_sha256']
    changed=dict(frame,source_sha256='a'*64)
    assert video_signature(changed)!=signature
    program.metadata['files']=[{'path':'asset.bin','sha256':'b'*64}]
    assert video_signature(program.frame_probe([]))!=signature
    program.metadata['files']=[]
    program.metadata['runtime_inputs']={'qemu':{'path':'/first/location','sha256':'c'*64}}
    first=video_signature(program.frame_probe([]))
    program.metadata['runtime_inputs']['qemu']['path']='/different/location'
    assert video_signature(program.frame_probe([]))==first
