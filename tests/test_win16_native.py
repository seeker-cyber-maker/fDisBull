"""Opt-in native Win16 GUI/input/scene acceptance for one declared Snake build.

The profile is the repository's generated ``snake/builds/win16-final`` program
and INITIAL.BIN, not the original DOS game or a general Win16 compatibility
claim. Inputs are copied byte-for-byte into a fresh private workspace. This
exercises the original supplied NE code in Wine, observes one ordinary N-key
transition, resets with R, then recreates that transition through a named scene.
All images, databases and runtime evidence remain in the caller's output folder.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback
import urllib.error
import urllib.request

from PIL import Image
import pytest

from fdisbull.project import Project
from fdisbull.windows_ui import WindowsCaptureUnavailable
from fdisbull.win16_debugger import __file__ as adapter_source_file

SNAKE_EXE_SHA256='9efbfb2264508bd10f2b20d3614973bea36b8abb2074574f68002fe52aee4804'
SNAKE_INITIAL_SHA256='fb3d1d818f01776cd05e7daa7d851b6c948d398250afdfa5ac44894e9cf0b7fa'
# In this exact retained executable these are the four startup INT 21h sites.
SNAKE_STARTUP_INT21={'ne:2:0xa615','ne:2:0xa6ef','ne:2:0xa753','ne:2:0xaa63'}


def _snake_frame_ready(image):
    """A visible HWND may precede the child view's first asynchronous paint."""
    colors={color:count for count,color in image.getcolors(image.width*image.height)}
    return (colors.get((0,170,0),0)>=16 and colors.get((85,255,85),0)>=16
            and colors.get((0,0,0),0)>=1000 and colors.get((0,0,170),0)>=1000)


def _body_changes(before,after):
    colors=((0,170,0),(85,255,85),(0,0,0));changes=[]
    for y in range(115,before.height):
        for x in range(20,before.width-20):
            a,b=before.getpixel((x,y)),after.getpixel((x,y))
            if a!=b and a in colors and b in colors:changes.append((x,y,a,b))
    return changes


def _fault_number(value):
    if type(value) is int:return value
    if isinstance(value,str):return int(value,0)
    raise ValueError('Fault observation lacks an integer field')


def _access_violation(stop):
    try:
        return _fault_number(stop.get('exception_code'))==0xc0000005
    except (TypeError,ValueError):return False


def _retain_unknown_av(session,stop,output):
    """Retain a stopped fault before any ContinueDebugEvent/resume operation."""
    snapshot={'format':'fdisbull-win16-first-fault-1','before_forwarding':True,
              'stop':dict(stop),'errors':[]}
    try:
        registers=dict(session.call('registers'))
        snapshot['registers']=registers
    except Exception as error:
        snapshot['errors'].append({'observation':'registers','error':str(error)})
        registers=None
    if getattr(session.rpc,'capabilities',{}).get('context_diagnostics') is True:
        try:snapshot['native_contexts']=session.call('context-diagnostics')
        except Exception as error:snapshot['errors'].append({'observation':'native-contexts','error':str(error)})
    if registers is not None:
        try:
            if _fault_number(registers['thread'])!=_fault_number(stop['thread']):
                raise ValueError('Fault register thread differs from the pending exception thread')
            selector=_fault_number(registers['ss'])
            if not 0<selector<=65535 or selector&3!=3:
                raise ValueError('Fault SS is not a user stack selector')
            descriptor=dict(session.call('selector',{'selector':selector}))
            snapshot['stack_descriptor']=descriptor
            base=_fault_number(descriptor['base']);limit=_fault_number(descriptor['limit'])
            kind=_fault_number(descriptor['type'])
            if (_fault_number(descriptor['selector'])!=selector or descriptor.get('present') is not True
                    or type(descriptor.get('default_big')) is not bool or descriptor.get('dpl')!=3
                    or kind&0x1e!=0x12 or _fault_number(descriptor['thread'])!=_fault_number(stop['thread'])
                    or not 0<=base<=0xffffffff or not 0<=limit<=0xffffffff or base+limit>0xffffffff):
                raise ValueError('Fault SS is not an observed present writable non-expanding data descriptor')
            esp=_fault_number(registers['general']['esp'])
            if not 0<=esp<=0xffffffff:raise ValueError('Fault ESP exceeds the observed WOW32 context')
            pointer=esp if descriptor['default_big'] else esp&0xffff
            stack_limit=min(limit,0xffffffff if descriptor['default_big'] else 0xffff)
            if pointer>stack_limit:raise ValueError('Fault stack pointer exceeds its observed descriptor')
            offset=max(0,pointer-32);length=min(128,stack_limit+1-offset)
            if not 1<=length<=128 or base+offset+length>0x100000000:
                raise ValueError('Fault stack sample exceeds the observed linear address range')
            raw=session._read_runtime(base+offset,length)
            if len(raw)!=length:raise ValueError('Incomplete stopped fault stack read')
            after=dict(session.call('selector',{'selector':selector}))
            identity=('selector','base','limit','present','default_big','granularity','type','dpl',
                      'thread','module_revision','state_revision')
            if any(after.get(key)!=descriptor.get(key) for key in identity):
                raise ValueError('Fault stack descriptor changed during the stopped read')
            snapshot['stack']={'qualified':True,'selector':hex(selector),'pointer':hex(pointer),
                'offset':hex(offset),'linear_address':hex(base+offset),'length':length,'hex':raw.hex(),
                'descriptor':descriptor,'semantics':'observed SS descriptor; 16/32-bit stack address size'}
        except Exception as error:
            snapshot['errors'].append({'observation':'descriptor-qualified-stack','error':str(error)})
    path=Path(output)/'first-unknown-av.json'
    data=(json.dumps(snapshot,indent=2)+'\n').encode();path.write_bytes(data)
    return {'file':path.name,'sha256':hashlib.sha256(data).hexdigest(),
            'registers_captured':registers is not None,'stack_qualified':snapshot.get('stack',{}).get('qualified',False),
            'native_contexts_captured':'native_contexts' in snapshot,'errors':snapshot['errors']}


def _continue_to_slice(session,mark,output,receipt,*,count=20):
    for _ in range(count):
        outcome=session.run(timeout_ms=1500)
        if outcome['outcome']=='exception':
            stop=outcome['session']['stop_reason']
            forwarded=receipt.setdefault('forwarded_startup_int21',[])
            expected=(_access_violation(stop) and stop.get('first_chance')==1
                      and receipt.get('source_sha256')==SNAKE_EXE_SHA256
                      and stop.get('project_address') in SNAKE_STARTUP_INT21
                      and stop['project_address'] not in forwarded)
            if _access_violation(stop) and not expected:
                if 'first_unknown_av' not in receipt:
                    receipt['first_unknown_av']=_retain_unknown_av(session,stop,output)
                    mark('unknown-access-violation-retained-without-continuation',fault=receipt['first_unknown_av'])
                raise RuntimeError('Unexpected Win16 access violation; fault context retained before continuation')
            if expected:forwarded.append(stop['project_address'])
            mark('forwarding-observed-first-chance',stop=stop);continue
        if outcome['outcome'] in ('timeout','slice'):return outcome
        raise RuntimeError('Unexpected native outcome: '+str(outcome))
    raise RuntimeError('Exception forwarding budget exceeded')


def qualify_win16_snake(output,*,qemu,kernel,runtime,fixture,initial,debug_probes=True,trace_farcall=True,gpr_probe=False):
    original=Path(fixture).resolve(strict=True);initial_source=Path(initial).resolve(strict=True)
    if hashlib.sha256(original.read_bytes()).hexdigest()!=SNAKE_EXE_SHA256 or hashlib.sha256(initial_source.read_bytes()).hexdigest()!=SNAKE_INITIAL_SHA256:
     raise ValueError('Native Win16 scene acceptance requires the declared generated Snake executable/initial-state profile')
    OUT=Path(output);OUT.mkdir(parents=True,exist_ok=True);GAME=OUT/'game';GAME.mkdir()
    shutil.copyfile(original,GAME/'PROGRAM.EXE');shutil.copyfile(initial_source,GAME/'INITIAL.BIN')
    assert hashlib.sha256(original.read_bytes()).digest()==hashlib.sha256((GAME/'PROGRAM.EXE').read_bytes()).digest()
    assert hashlib.sha256(initial_source.read_bytes()).digest()==hashlib.sha256((GAME/'INITIAL.BIN').read_bytes()).digest()
    receipt={'format':'fdisbull-original-ne-public-1','status':'running','checks':[],'host_input_injected':False,'source_sha256':hashlib.sha256((GAME/'PROGRAM.EXE').read_bytes()).hexdigest(),'assistance':[],'debug_probes':debug_probes,'trace_farcall':trace_farcall and debug_probes,'gpr_probe':gpr_probe,'gpr_probe_kind':'paired-integer-edit-restore' if gpr_probe else None}
    start=time.monotonic();session=None;trace=None

    def mark(stage,**details):
     receipt['checks'].append(dict(stage=stage,elapsed_s=time.monotonic()-start,**details));(OUT/'qualification.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt['checks'][-1]),flush=True)

    def continue_to_slice(session,count=20):
     return _continue_to_slice(session,mark,OUT,receipt,count=count)
    try:
     with Project.create(OUT/'native.fdb',GAME/'PROGRAM.EXE',image='ne') as project:
      project.analyze(max_instructions=300)
      mark('retained-source-static-ne-entry',entry=project.meta['entry'])
      with project.debugger(qemu,GAME,backend='wine-qemu',kernel=kernel,initramfs=runtime,files=['PROGRAM.EXE','INITIAL.BIN'],window=True,boot_timeout_ms=600000,memory_mib=8192) as session:
       receipt['adapter_sha256']=hashlib.sha256(Path(adapter_source_file).read_bytes()).hexdigest();receipt['runtime_inputs']=session.metadata['runtime_inputs'];receipt['guest_runtime']=session.metadata['guest_runtime'];receipt['qemu_command']=session.rpc.command
       entry=session.registers();assert entry['project_address']=='ne:2:0xa568' and entry['cpu_mode']=='protected16';assert session.rpc.capabilities['save_states'] is True
       assert session.rpc.capabilities['register_edit'] is True and session.metadata['general_register_writes'] is True
       mark('actual-original-ne-entry',qemu_pid=session.rpc.process.pid,registers=entry,bindings=list(session.bindings.values()))
       if gpr_probe:
        original_eax=int(entry['general']['eax'],16)
        with pytest.raises(ValueError,match='only six checked'):
         session.write_registers({'esp':{'expected':int(entry['general']['esp'],16),'value':0}})
        with pytest.raises(ValueError,match='expected value differs'):
         session.write_registers({'eax':{'expected':original_eax^1,'value':original_eax}})
        before_context=session.call('context-diagnostics')
        changed=session.write_registers({'eax':{'expected':original_eax,'value':original_eax^1}})
        assert int(changed['after']['general']['eax'],16)==original_eax^1
        restored=session.write_registers({'eax':{'expected':original_eax^1,'value':original_eax}})
        observed=session.registers();after_context=session.call('context-diagnostics')
        for field in ('general','eip','eflags','cs','ds','ss','es','fs','gs','project_address'):
         assert observed[field]==entry[field]
        for view in ('native64','wow32'):
         assert before_context[view]['general']==after_context[view]['general']
         for field in ('rip','eip','rflags','eflags','cs','ds','ss','es','fs','gs'):
          if field in before_context[view]:assert before_context[view][field]==after_context[view][field]
        mark('actual-ne-checked-register-edit-restored-before-continuation',
             edited='eax',refused=['esp','stale-expected-eax'],readback=observed,
             before_context_sha256=hashlib.sha256(json.dumps(before_context,sort_keys=True).encode()).hexdigest(),
             after_context_sha256=hashlib.sha256(json.dumps(after_context,sort_keys=True).encode()).hexdigest())
       memory=session.memory('ne:2:0xa568',length=2);assert memory['hex']=='eb53'
       if debug_probes:
        bp=session.breakpoint('ne:2:0xa5bd');assert bp['bytes_verified']
        stepped=session.step(count=1);assert stepped['completed'] and stepped['events'][0]['cpu_mode']=='protected16'
        arrival=session.run(timeout_ms=10000);assert arrival['outcome']=='breakpoint',arrival
        assert session.registers()['project_address']=='ne:2:0xa5bd';session.delete_breakpoint(bp['breakpoint_id'])
        if trace_farcall:
         trace=session.trace('original-entry-call.json',count=1,timeout_ms=20000);assert trace['metadata']['complete']
         mark('actual-ne-memory-execution-breakpoint-step-trace',memory=memory,breakpoint=bp,step=stepped,trace=trace)
        else:mark('controlled-entry-jmp-step-and-breakpoint-without-far-call-trace',memory=memory,breakpoint=bp,step=stepped)
       else:mark('controlled-gui-arm-without-optional-entry-step-or-far-call-trace',memory=memory)
       continue_to_slice(session)
       frame=None
       for poll in range(12):
        try:
         candidate=session.screenshot('gui-readiness-'+str(poll)+'.png',hooks=False)
         path=OUT/('readiness-'+str(poll)+'.png');project.debug_export(candidate['artifact'],path)
         painted=Image.open(path).convert('RGB');painted.load()
         if _snake_frame_ready(painted):frame=candidate;break
         mark('visible-window-child-view-not-yet-painted',frame=candidate)
        except WindowsCaptureUnavailable as error:mark('window-not-yet-available',error=str(error))
        continue_to_slice(session)
       if frame is None:raise RuntimeError('No painted Snake child view within bounded progression')
       project.debug_export(frame['artifact'],OUT/'initial.png');initial=Image.open(OUT/'initial.png').convert('RGB');initial.load()
       mark('actual-ne-client-frame',frame=frame,dimensions=initial.size)
       # The supplied window explicitly asks for a game-view focus click. This
       # black board point lies outside its blue controls and initial snake.
       assert initial.getpixel((80,190))==(0,0,0)
       focus=session.click(80,190,hold_ms=40,mode_id=frame['metadata']['mode_id'])
       continue_to_slice(session)
       focused=session.screenshot('gui-focused-before-n.png',hooks=False)
       project.debug_export(focused['artifact'],OUT/'initial-focused.png')
       initial=Image.open(OUT/'initial-focused.png').convert('RGB');initial.load()
       assert _snake_frame_ready(initial)
       mark('physical-game-view-focus-click-before-keyboard-baseline',input=focus)
       # Learn one physical N-step outcome, reset with the ordinary R key, then
       # independently replay that observed transition through a named scene.
       queued=session.keyboard_press('n',hold_ms=40,gap_ms=40)
       # OS delivery, game commitment and completed drawing are separate. One
       # N is queued; further polls only resume execution and observe its result.
       key_deadline=time.monotonic()+30;candidates=[]
       for poll in range(12):
        if time.monotonic()>=key_deadline:break
        continue_to_slice(session)
        after=session.screenshot('gui-after-physical-n-'+str(poll)+'.png',hooks=False)
        path=OUT/('after-n-'+str(poll)+'.png');project.debug_export(after['artifact'],path)
        changed=Image.open(path).convert('RGB');changed.load();candidates=_body_changes(initial,changed)
        if time.monotonic()>=key_deadline:candidates=[];break
        if candidates:shutil.copyfile(path,OUT/'after-n.png');break
        mark('single-n-awaiting-game-commit-or-paint',poll=poll,input_id=queued['input_id'],keyboard=session.keyboard_state())
       if not candidates:raise RuntimeError('One physical N produced no body transition within12 input-free polls /30 host seconds')
       x,y,before_rgb,after_rgb=candidates[len(candidates)//2]
       mark('physical-ne-key-produced-observed-body-pixel',queued=queued,pixel=[x,y],before_rgb=before_rgb,after_rgb=after_rgb,changed_body_pixels=len(candidates))
       reset=session.keyboard_press('r',hold_ms=40,gap_ms=40);reset_deadline=time.monotonic()+30;reset_observed=False
       for poll in range(12):
        if time.monotonic()>=reset_deadline:break
        continue_to_slice(session)
        pixel=session.frame_probe([[x,y]])['samples'][0]['rgb']
        if time.monotonic()>=reset_deadline:break
        if pixel==list(before_rgb):reset_observed=True;break
        mark('single-r-awaiting-reset-paint',poll=poll,input_id=reset['input_id'])
       assert reset_observed,'One physical R did not restore the observed body pixel within its bounded presentation wait'
       mark('actual-ne-ordinary-r-reset',pixel=[x,y],restored_rgb=list(before_rgb),input_id=reset['input_id'])
       before=session.screenshot('gui-reset-before-scene.png',hooks=False)
       predicate=lambda rgb:{'pixels':{'samples':[{'x':x,'y':y,'rgb':list(rgb)}]}}
       scene=project.debug_save_scene('win16-snake-step',{'format':'fdisbull-scene-1','width':initial.width,'height':initial.height,'mode_id':before['metadata']['mode_id'],'reference':before['artifact'],'context':{'state':'native Win16 Snake paused after ordinary R reset','triggers':['normal program startup and reset key']},'match':predicate(before_rgb),'objects':[{'name':'snake.step','context':{'state':'paused board','triggers':['ordinary N key']},'area':{'rect':[x,y,x+1,y+1]},'point':[x,y],'visible':{'constant':True},'enabled':{'constant':True},'ready':predicate(before_rgb),'action':{'kind':'press','key':'n','hold_ms':40,'gap_ms':40},'outcome':predicate(after_rgb),'outcome_phase':'state','guest_ms':15000,'timeout_ms':30000}]})
       action=session.scene(scene['id']).act('snake.step',slice_ms=1000);assert action['complete'] and action['status']=='matched',action
       assert session.frame_probe([[x,y]])['samples'][0]['rgb']==list(after_rgb)
       mark('actual-ne-named-scene-replayed-physical-transition',scene_revision=scene['id'],action=action)
       dot=session.dot_mode();assert dot['enabled'] and dot['view_only'] and not dot['host_input_capture'];sequence=session.rpc.sequence
       with urllib.request.urlopen(dot['viewer_url'],timeout=3) as response:assert response.status==200
       with urllib.request.urlopen(dot['viewer_url']+'frame.png',timeout=3) as response:assert response.read().startswith(b'\x89PNG')
       try:urllib.request.urlopen(urllib.request.Request(dot['viewer_url']+'keyboard',data=b'n',method='POST'),timeout=3);raise AssertionError('Spectator accepted POST')
       except urllib.error.HTTPError as error:assert error.code==405
       assert session.rpc.sequence==sequence
       mark('actual-ne-dot-mode-retained-frame-http-no-host-input',native_rpc_sequence_unchanged=True)
       final=session.screenshot('gui-final.png',hooks=False)
       receipt['run']=session.run_id;receipt['mapping']=session.metadata
       for name in ('boot.log','qemu.log'):
        path=Path(session.rpc.temporary.name)/name
        if path.exists():shutil.copyfile(path,OUT/('guest-'+name))
      assert session.rpc.process.poll() is not None
      receipt['owned_process_reaped']=True
     with Project(OUT/'native.fdb') as reopened:
      reopened.debug_export(final['artifact'],OUT/'final.png')
      if trace is not None:
       reopened.debug_export(trace['artifact'],OUT/'original-entry-call.json')
       assert json.loads((OUT/'original-entry-call.json').read_text())['complete'] is True
     assert hashlib.sha256(original.read_bytes()).hexdigest()==SNAKE_EXE_SHA256
     assert hashlib.sha256(initial_source.read_bytes()).hexdigest()==SNAKE_INITIAL_SHA256
     assert hashlib.sha256((GAME/'PROGRAM.EXE').read_bytes()).hexdigest()==receipt['source_sha256']
     receipt['status']='passed';mark('owned-native-vm-closed-original-unchanged')
    except Exception as error:
     receipt.update(status='failed',error=str(error),traceback=traceback.format_exc())
     if session is not None:receipt['owned_process_reaped']=session.rpc.process.poll() is not None
     mark('failure');raise

    return receipt


def test_win16_scene_profile_rejects_changed_inputs_before_boot(tmp_path):
    fixture=tmp_path/'changed.exe';fixture.write_bytes(b'changed')
    initial=tmp_path/'changed.bin';initial.write_bytes(b'changed')
    with pytest.raises(ValueError,match='declared generated Snake'):
        qualify_win16_snake(tmp_path/'output',qemu='unused',kernel='unused',runtime='unused',fixture=fixture,initial=initial)
    assert not (tmp_path/'output').exists()


def test_snake_readiness_requires_painted_game_content_not_just_a_window():
    first_window=Image.new('RGB',(80,80),'white')
    first_window.paste((0,0,0),(0,0,80,20))
    assert _snake_frame_ready(first_window) is False
    painted=first_window.copy();painted.paste((0,0,170),(0,20,80,40))
    assert _snake_frame_ready(painted) is False
    painted.paste((0,170,0),(10,50,15,55));painted.paste((85,255,85),(15,50,20,55))
    assert _snake_frame_ready(painted) is True


def fault_session(*,esp=0x1045678,descriptor_changes=None,changed_after_read=False,diagnostics=False):
    from types import SimpleNamespace
    calls=[]
    registers={'thread':424,'ss':'0x2ff','general':{'esp':hex(esp)}}
    descriptor={'selector':0x2ff,'base':0xa40000,'limit':0xffff,'present':True,
                'default_big':False,'granularity':False,'type':19,'dpl':3,
                'thread':424,'module_revision':40,'state_revision':17}
    descriptor.update(descriptor_changes or {})
    def call(method,params=None):
        calls.append((method,params))
        if method=='registers':return registers
        if method=='context-diagnostics':return {'pending_event':{'thread':424},'native64':{'rip':'0x0'},'wow32':registers}
        if method=='selector':
            result=dict(descriptor)
            if changed_after_read and any(method=='read' for method,_ in calls):result['base']+=0x10000
            return result
        pytest.fail('Fault snapshot attempted a mutation or continuation: '+method)
    def read(address,length):calls.append(('read',{'address':address,'length':length}));return bytes(range(length))
    return SimpleNamespace(call=call,_read_runtime=read,rpc=SimpleNamespace(capabilities={'context_diagnostics':diagnostics})),calls


@pytest.mark.parametrize('esp,changes,offset,length',[
    (0x1045678,{},0x5658,128),
    (0x1045678,{'default_big':True,'base':0,'limit':0xffffffff},0x1045658,128),
    (0x104fffe,{},0xffde,34),
])
def test_fault_stack_uses_observed_address_size_and_descriptor_bounds(tmp_path,esp,changes,offset,length):
    session,calls=fault_session(esp=esp,descriptor_changes=changes,diagnostics=True)
    stop={'address':'0x0','exception_code':0xc0000005,'thread':424}
    retained=_retain_unknown_av(session,stop,tmp_path)
    data=(tmp_path/retained['file']).read_bytes();snapshot=json.loads(data)
    assert retained['sha256']==hashlib.sha256(data).hexdigest()
    assert retained['registers_captured'] and retained['stack_qualified'] and retained['native_contexts_captured']
    assert snapshot['stack']['offset']==hex(offset) and snapshot['stack']['length']==length
    assert snapshot['stack']['hex']==bytes(range(length)).hex()
    assert snapshot['stack']['linear_address']==hex(changes.get('base',0xa40000)+offset)
    assert [method for method,_ in calls]==['registers','context-diagnostics','selector','read','selector']


@pytest.mark.parametrize('changes',[
    {'present':False},{'type':27},{'type':23},{'default_big':0},{'dpl':0},
    {'base':0xfffff000},{'thread':428},{'limit':0x1000},
])
def test_fault_stack_refuses_invalid_descriptor_before_any_memory_read(tmp_path,changes):
    session,calls=fault_session(descriptor_changes=changes)
    retained=_retain_unknown_av(session,{'thread':424},tmp_path)
    snapshot=json.loads((tmp_path/retained['file']).read_text())
    assert retained['registers_captured'] and not retained['stack_qualified']
    assert 'stack' not in snapshot and snapshot['errors']
    assert not any(method=='read' for method,_ in calls)


def test_fault_stack_never_labels_bytes_with_a_changed_descriptor(tmp_path):
    session,calls=fault_session(changed_after_read=True)
    retained=_retain_unknown_av(session,{'thread':424},tmp_path)
    snapshot=json.loads((tmp_path/retained['file']).read_text())
    assert not retained['stack_qualified'] and 'stack' not in snapshot
    assert 'changed during' in snapshot['errors'][0]['error']


def test_unknown_zero_av_is_retained_then_fails_before_another_run(tmp_path):
    session,calls=fault_session();marks=[];receipt={}
    stop={'address':'0x0','raw_address':'0x0','exception_code':0xc0000005,'thread':424,'project_address':None}
    def run(**kwargs):calls.append(('run',kwargs));return {'outcome':'exception','session':{'stop_reason':stop}}
    session.run=run
    def mark(stage,**values):
        assert (tmp_path/'first-unknown-av.json').exists()
        marks.append(stage)
    with pytest.raises(RuntimeError,match='retained before continuation'):
        _continue_to_slice(session,mark,tmp_path,receipt)
    assert [method for method,_ in calls].count('run')==1
    assert marks==['unknown-access-violation-retained-without-continuation']
    assert receipt['first_unknown_av']['stack_qualified'] is True


def test_source_bound_startup_exception_remains_an_explicit_forwarded_event(tmp_path):
    from types import SimpleNamespace
    stop={'address':'0xa4aa25','exception_code':0xc0000005,'first_chance':1,'thread':424,'project_address':'ne:2:0xa615'}
    replies=iter([{'outcome':'exception','session':{'stop_reason':stop}},{'outcome':'slice'}]);marks=[]
    session=SimpleNamespace(run=lambda **kwargs:next(replies))
    receipt={'source_sha256':SNAKE_EXE_SHA256}
    assert _continue_to_slice(session,lambda stage,**values:marks.append(stage),tmp_path,receipt)=={'outcome':'slice'}
    assert marks==['forwarding-observed-first-chance'] and not list(tmp_path.iterdir())
    assert receipt['forwarded_startup_int21']==['ne:2:0xa615']


@pytest.mark.parametrize('location,first_chance,source_sha256,already_forwarded',[
    ('ne:2:0xa56d',1,SNAKE_EXE_SHA256,[]),  # OUTSB in the skipped compiler banner
    ('ne:2:0xa615',0,SNAKE_EXE_SHA256,[]),  # second chance is never an expected startup trap
    ('ne:2:0xa615',1,'other-source',[]),
    ('ne:2:0xa615',1,SNAKE_EXE_SHA256,['ne:2:0xa615']),
])
def test_unexpected_nonzero_or_unqualified_startup_av_is_retained_before_forwarding(
        tmp_path,location,first_chance,source_sha256,already_forwarded):
    session,calls=fault_session();marks=[]
    stop={'address':'0xa4aa25','exception_code':0xc0000005,'first_chance':first_chance,
          'thread':424,'project_address':location}
    def run(**kwargs):calls.append(('run',kwargs));return {'outcome':'exception','session':{'stop_reason':stop}}
    session.run=run
    receipt={'source_sha256':source_sha256,'forwarded_startup_int21':list(already_forwarded)}
    with pytest.raises(RuntimeError,match='retained before continuation'):
        _continue_to_slice(session,lambda stage,**values:marks.append(stage),tmp_path,receipt)
    assert [method for method,_ in calls].count('run')==1
    assert marks==['unknown-access-violation-retained-without-continuation']
    snapshot=json.loads((tmp_path/'first-unknown-av.json').read_text())
    assert snapshot['stop']['project_address']==location


def test_real_win16_original_ne_gui_keyboard_named_scene_and_dot_mode(tmp_path):
    names=('FDISBULL_NE_QEMU','FDISBULL_NE_KERNEL','FDISBULL_NE_INITRAMFS',
           'FDISBULL_NE_SNAKE_EXE','FDISBULL_NE_SNAKE_INITIAL')
    missing=[name for name in names if not os.environ.get(name)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_NE_GUI')=='1':
            pytest.fail('Missing real Win16 GUI acceptance inputs: '+', '.join(missing))
        pytest.skip('Requires explicit matching native runtime and declared generated Snake Win16 profile')
    qemu,kernel,runtime,fixture,initial=[os.environ[name] for name in names]
    probes=os.environ.get('FDISBULL_NE_GUI_NO_PROBES')!='1'
    farcall=os.environ.get('FDISBULL_NE_GUI_NO_FARCALL_TRACE')!='1'
    gpr=os.environ.get('FDISBULL_NE_GUI_GPR_PROBE')=='1'
    receipt=qualify_win16_snake(tmp_path,qemu=qemu,kernel=kernel,runtime=runtime,fixture=fixture,initial=initial,debug_probes=probes,trace_farcall=farcall,gpr_probe=gpr)
    assert receipt['status']=='passed'
