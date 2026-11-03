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


def _snake_frame_ready(image):
    """A visible HWND may precede the child view's first asynchronous paint."""
    colors={color:count for count,color in image.getcolors(image.width*image.height)}
    return (colors.get((0,170,0),0)>=16 and colors.get((85,255,85),0)>=16
            and colors.get((0,0,0),0)>=1000 and colors.get((0,0,170),0)>=1000)


def qualify_win16_snake(output,*,qemu,kernel,runtime,fixture,initial,debug_probes=True):
    original=Path(fixture).resolve(strict=True);initial_source=Path(initial).resolve(strict=True)
    if hashlib.sha256(original.read_bytes()).hexdigest()!=SNAKE_EXE_SHA256 or hashlib.sha256(initial_source.read_bytes()).hexdigest()!=SNAKE_INITIAL_SHA256:
     raise ValueError('Native Win16 scene acceptance requires the declared generated Snake executable/initial-state profile')
    OUT=Path(output);OUT.mkdir(parents=True,exist_ok=True);GAME=OUT/'game';GAME.mkdir()
    shutil.copyfile(original,GAME/'PROGRAM.EXE');shutil.copyfile(initial_source,GAME/'INITIAL.BIN')
    assert hashlib.sha256(original.read_bytes()).digest()==hashlib.sha256((GAME/'PROGRAM.EXE').read_bytes()).digest()
    assert hashlib.sha256(initial_source.read_bytes()).digest()==hashlib.sha256((GAME/'INITIAL.BIN').read_bytes()).digest()
    receipt={'format':'fdisbull-original-ne-public-1','status':'running','checks':[],'host_input_injected':False,'source_sha256':hashlib.sha256((GAME/'PROGRAM.EXE').read_bytes()).hexdigest(),'assistance':[],'debug_probes':debug_probes}
    start=time.monotonic();session=None;trace=None

    def mark(stage,**details):
     receipt['checks'].append(dict(stage=stage,elapsed_s=time.monotonic()-start,**details));(OUT/'qualification.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt['checks'][-1]),flush=True)

    def continue_to_slice(session,count=20):
     for _ in range(count):
      outcome=session.run(timeout_ms=1500)
      if outcome['outcome']=='exception':
       mark('forwarding-observed-first-chance',stop=outcome['session']['stop_reason']);continue
      if outcome['outcome'] in ('timeout','slice'):return outcome
      raise RuntimeError('Unexpected native outcome: '+str(outcome))
     raise RuntimeError('Exception forwarding budget exceeded')
    try:
     with Project.create(OUT/'native.fdb',GAME/'PROGRAM.EXE',image='ne') as project:
      project.analyze(max_instructions=300)
      mark('retained-source-static-ne-entry',entry=project.meta['entry'])
      with project.debugger(qemu,GAME,backend='wine-qemu',kernel=kernel,initramfs=runtime,files=['PROGRAM.EXE','INITIAL.BIN'],window=True,boot_timeout_ms=600000,memory_mib=8192) as session:
       receipt['adapter_sha256']=hashlib.sha256(Path(adapter_source_file).read_bytes()).hexdigest();receipt['runtime_inputs']=session.metadata['runtime_inputs'];receipt['guest_runtime']=session.metadata['guest_runtime'];receipt['qemu_command']=session.rpc.command
       entry=session.registers();assert entry['project_address']=='ne:2:0xa568' and entry['cpu_mode']=='protected16';assert session.rpc.capabilities['save_states'] is False
       mark('actual-original-ne-entry',qemu_pid=session.rpc.process.pid,registers=entry,bindings=list(session.bindings.values()))
       memory=session.memory('ne:2:0xa568',length=2);assert memory['hex']=='eb53'
       if debug_probes:
        bp=session.breakpoint('ne:2:0xa5bd');assert bp['bytes_verified']
        stepped=session.step(count=1);assert stepped['completed'] and stepped['events'][0]['cpu_mode']=='protected16'
        arrival=session.run(timeout_ms=10000);assert arrival['outcome']=='breakpoint',arrival
        assert session.registers()['project_address']=='ne:2:0xa5bd';session.delete_breakpoint(bp['breakpoint_id'])
        trace=session.trace('original-entry-call.json',count=1,timeout_ms=20000);assert trace['metadata']['complete']
        mark('actual-ne-memory-execution-breakpoint-step-trace',memory=memory,breakpoint=bp,step=stepped,trace=trace)
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
       queued=session.keyboard_press('n',hold_ms=40,gap_ms=40);continue_to_slice(session)
       after=session.screenshot('gui-after-physical-n.png',hooks=False);project.debug_export(after['artifact'],OUT/'after-n.png')
       changed=Image.open(OUT/'after-n.png').convert('RGB');changed.load()
       candidates=[]
       for y in range(115,initial.height):
        for x in range(20,initial.width-20):
         a,b=initial.getpixel((x,y)),changed.getpixel((x,y))
         if a!=b and a in ((0,170,0),(85,255,85),(0,0,0)) and b in ((0,170,0),(85,255,85),(0,0,0)):
          candidates.append((x,y,a,b))
       if not candidates:raise RuntimeError('Physical N key produced no qualified snake-body pixel transition')
       x,y,before_rgb,after_rgb=candidates[len(candidates)//2]
       mark('physical-ne-key-produced-observed-body-pixel',queued=queued,pixel=[x,y],before_rgb=before_rgb,after_rgb=after_rgb,changed_body_pixels=len(candidates))
       session.keyboard_press('r',hold_ms=40,gap_ms=40);continue_to_slice(session)
       assert session.frame_probe([[x,y]])['samples'][0]['rgb']==list(before_rgb)
       before=session.screenshot('gui-reset-before-scene.png',hooks=False)
       predicate=lambda rgb:{'pixels':{'samples':[{'x':x,'y':y,'rgb':list(rgb)}]}}
       scene=project.debug_save_scene('win16-snake-step',{'format':'fdisbull-scene-1','width':initial.width,'height':initial.height,'mode_id':before['metadata']['mode_id'],'reference':before['artifact'],'context':{'state':'native Win16 Snake paused after ordinary R reset','triggers':['normal program startup and reset key']},'match':predicate(before_rgb),'objects':[{'name':'snake.step','context':{'state':'paused board','triggers':['ordinary N key']},'area':{'rect':[x,y,x+1,y+1]},'point':[x,y],'visible':{'constant':True},'enabled':{'constant':True},'ready':predicate(before_rgb),'action':{'kind':'press','key':'n','hold_ms':40,'gap_ms':40},'outcome':predicate(after_rgb),'outcome_phase':'state','guest_ms':15000,'timeout_ms':30000}]})
       action=session.scene(scene['id']).act('snake.step');assert action['complete'] and action['status']=='matched',action
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
    receipt=qualify_win16_snake(tmp_path,qemu=qemu,kernel=kernel,runtime=runtime,fixture=fixture,initial=initial,debug_probes=probes)
    assert receipt['status']=='passed'
