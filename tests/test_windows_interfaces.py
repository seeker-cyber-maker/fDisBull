"""Public Windows launch, script and dot-mode dispatch boundaries."""
from pathlib import Path
import base64

import pytest

from fdisbull.cli import METHODS,parser
from fdisbull.debug_script import execute_script,validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from fdisbull.wine_debugger import PEDebugSession
from fixtures_formats import pe64
from test_ne_loader import ne_file


@pytest.mark.parametrize('image,backend,module,cls',[
    (pe64,'wine-qemu','fdisbull.wine_debugger','PEDebugSession'),
    (ne_file,'wine-ne','fdisbull.win16_debugger','Win16DebugSession'),
])
def test_windows_factory_routes_spectator_and_memory_without_starting_another_backend(tmp_path,monkeypatch,image,backend,module,cls):
    source=tmp_path/'authored.exe';source.write_bytes(image());seen=[]
    def capture(*args,**kwargs):seen.append((args,kwargs));return 'owned-session'
    monkeypatch.setattr(module+'.'+cls,capture)
    with Project.create(tmp_path/'project.fdb',source) as project:
        assert project.debugger('qemu',tmp_path,backend=backend,kernel='kernel',initramfs='runtime',
                                dot_mode=True,memory_mib=8192)=='owned-session'
        assert seen[-1][1]['window'] is True and seen[-1][1]['memory_mib']==8192
        assert seen[-1][0][0] is project
        for invalid in ({'window':True,'dot_mode':False},{'dot_mode':'yes'},{'memory_mib':8193},
                        {'fair_play':True}):
            before=len(seen)
            with pytest.raises(ValueError):project.debugger('qemu',tmp_path,backend=backend,kernel='k',initramfs='r',**invalid)
            assert len(seen)==before


def test_dot_mode_and_steps_are_public_cli_and_live_json_methods(tmp_path):
    options=parser().parse_args(['debug','project.fdb','--executable','qemu','--game-dir','game',
                                '--backend','wine-ne','--kernel','k','--initramfs','r',
                                '--dot-mode','--memory-mib','8192'])
    assert options.window is True and options.memory_mib==8192
    assert {'debug-step','debug-spectator','debug-spectator-frame'}<=METHODS.keys()
    class Session:
        run_id='owned'
        project=type('P',(),{'path':Path(tmp_path/'project.fdb').resolve()})()
        def dot_mode(self,enabled=None):return {'enabled':enabled,'view_only':True}
        def spectator_frame(self):return {'frame':'retained'}
        def step(self,**kwargs):return kwargs
    workspace=DebugWorkspace();workspace.sessions['owned']=Session()
    assert workspace.invoke('debug-spectator',str(tmp_path/'project.fdb'),{'run':'owned','enabled':True})=={'enabled':True,'view_only':True}
    assert workspace.invoke('debug-spectator-frame',str(tmp_path/'project.fdb'),{'run':'owned'})=={'frame':'retained'}
    assert workspace.invoke('debug-step',str(tmp_path/'project.fdb'),{'run':'owned','count':2})=={'count':2}


@pytest.mark.parametrize('backend',['wine-qemu','wine-ne'])
def test_saved_windows_script_uses_actual_step_and_host_wait_signatures(backend):
    script={'format':'fdisbull-script-1','backend':backend,'steps':[
        {'op':'step','count':2},
        {'op':'wait','observations':{'value':{'kind':'memory','address':'0x401000','length':1}},
         'until':{'observation':'value','equals':'01'},'active_ms':100,'fast_forward':False}]}
    assert len(validate_script(script))==2
    script['steps'][-1]['active_ms']=0
    with pytest.raises(ValueError):validate_script(script)


def test_invalid_later_windows_wait_or_backend_refuses_before_any_edit_or_artifact():
    session=PEDebugSession.__new__(PEDebugSession)
    def mutation(*args,**kwargs):pytest.fail('Preflight reached guest mutation or artifact storage')
    session._artifact=mutation;session.write_memory=mutation
    script={'format':'fdisbull-script-1','backend':'wine-qemu','steps':[
        {'op':'write-memory','address':'0x401000','data_hex':'01','expected_hex':'00'},
        {'op':'wait','observations':{'value':{'kind':'memory','address':'0x401000','length':1}},
         'until':{'observation':'value','equals':'01'},'active_ms':100,'fast_forward':True}]}
    with pytest.raises(ValueError,match='fast-forward'):execute_script(session,script)
    script['backend']='wine-ne'
    with pytest.raises(ValueError,match='differs'):execute_script(session,script)


def test_separate_ida_guest_keeps_legacy_frame_protocol_and_refuses_new_controls_before_rpc():
    from fdisbull.ida_debugger import IDAPEDebugSession
    session=IDAPEDebugSession.__new__(IDAPEDebugSession)
    session.mode_id=0;session._frame=None;calls=[]
    def call(method,*args,**kwargs):
        calls.append(method)
        assert method=='screenshot'
        return {'window':'0x123','width':1,'height':1,'bgra_base64':base64.b64encode(bytes([0,0,255,0])).decode()}
    session.call=call
    session._artifact=lambda name,kind,data,metadata:{'name':name,'metadata':metadata,'png':data}
    frame=session.screenshot()
    assert frame['png'].startswith(b'\x89PNG') and frame['metadata']['mode_id']==1
    for operation in (lambda:session.keyboard_press('a'),lambda:session.frame_probe([]),
                      lambda:session.dot_mode(True),lambda:session.scene_act('scene','button')):
        with pytest.raises(ValueError,match='not qualified'):operation()
    assert calls==['screenshot']
