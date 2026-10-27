"""Real guest rendering, persistent preparation and cleanup at failed boundaries."""
import io

from PIL import Image
import pytest

from fdisbull.project import Project
from fdisbull.screenshot_hooks import ScreenshotHookError, validate_configuration
from test_debugger import emulator
from test_dos_loader import mz_file


@pytest.fixture
def sprite(tmp_path):
    # Mode 13h; ES=A000; repeatedly repaint pixel 0 from an instruction immediate.
    data=mz_file(bytes.fromhex('b81300cd10b800a08ec0b00426a20000ebf8')+bytes(512),ss=0,sp=0x200)
    binary=tmp_path/'SPRITE.EXE';binary.write_bytes(data)
    path=tmp_path/'sprite.fdb'
    with Project.create(path,binary) as project:project.analyze(max_instructions=16)
    return path,binary,data


def color(project,frame):
    raw=project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(frame['artifact'],)).fetchone()[0]
    with Image.open(io.BytesIO(raw)) as image:return image.convert('RGB').getpixel((0,0))


def hide_sprite(debug):
    return debug.layer_patch('sprite clear color','1000:000b',expected_hex='04',data_hex='00',kind='execute')['layer']


def policy(layer):
    return dict(suspend_layers=[layer],pre=[dict(op='run',guest_ms=60,timeout_ms=3000,fast_forward=True)],
                post=[dict(op='registers')])


def test_real_screenshot_hooks_visible_capture_restore_grid_click_and_restart(sprite,emulator,tmp_path):
    path,binary,data=sprite
    with Project(path) as project,project.debugger(emulator,binary.parent) as debug:
        layer=hide_sprite(debug)
        debug.run(guest_ms=60,timeout_ms=3000,fast_forward=True)
        assert color(project,debug.screenshot(hooks=False))==(0,0,0)
        saved=debug.script(dict(format='fdisbull-script-1',steps=[
            dict(op='screenshot-hooks',configuration=policy(layer)),dict(op='screenshot',name='visible.png')]))
        assert saved['ok'],saved
        frame=saved['steps'][1]['result']
        assert color(project,frame)==(170,0,0)
        assert frame['metadata']['screenshot_hooks']['capture_layers']==[]
        assert frame['screenshot_hooks']['restore']==dict(ok=True,active=[layer])
        assert frame['screenshot_hooks']['post']['ok']
        debug.run(guest_ms=60,timeout_ms=3000,fast_forward=True)
        assert color(project,debug.screenshot(hooks=False))==(0,0,0)
        grid=debug.screenshot('grid.png',grid=True,grid_step=8)
        assert grid['metadata']['screenshot_hooks']['policy']==debug.screenshot_hooks()['id']
        clicked=debug.click_frame(80,80)
        assert clicked['click']['accepted'] and debug.layers()['active']==[layer]
        first_policy=debug.screenshot_hooks()['id']
    assert binary.read_bytes()==data
    with Project(path) as project,project.debugger(emulator,binary.parent) as debug:
        assert debug.screenshot_hooks()['id']==first_policy
        debug.layers([layer])
        debug.run(guest_ms=60,timeout_ms=3000,fast_forward=True)
        frame=debug.screenshot('reopened.png')
        assert color(project,frame)==(170,0,0) and debug.layers()['active']==[layer]
        project.debug_export(frame['artifact'],tmp_path/'reopened.png')
        child=project.patch('1000:000b','05')['version']
        assert not project.debug_screenshot_hooks(version=child)['configured']
        # The inverse policy hides only for capture and restores a visible baseline.
        debug.layers([])
        debug.screenshot_hooks(dict(pre=[dict(op='layer-enable',layer=layer),
                                          dict(op='run',guest_ms=60,fast_forward=True)]))
        invisible=debug.screenshot('temporary-invisible.png')
        assert color(project,invisible)==(0,0,0)
        assert invisible['metadata']['screenshot_hooks']['capture_layers']==[layer]
        assert debug.layers()['active']==[]
    assert binary.read_bytes()==data


def test_real_screenshot_hook_breakpoint_stop_and_failed_capture_restore_layers(sprite,emulator):
    path,binary,_=sprite
    with Project(path) as project,project.debugger(emulator,binary.parent) as debug:
        layer=hide_sprite(debug);debug.run(guest_ms=60,timeout_ms=3000,fast_forward=True)
        debug.screenshot_hooks(policy(layer))
        bp=debug.breakpoint('1000:000a')
        with pytest.raises(ScreenshotHookError) as failed:debug.screenshot()
        report=failed.value.result
        assert report['pre']['steps'][0]['result']['outcome']=='breakpoint'
        assert report['capture'] is None and report['restore']['active']==[layer]
        assert report['post']['ok'] and int(debug.registers()['ip'],16)==10
        debug.delete_breakpoint(bp['breakpoint_id'])
        checkpoint=debug.save_state();debug.load_state(checkpoint['artifact'])
        debug.screenshot_hooks(dict(suspend_layers=[layer],require_fresh_frame=False))
        with pytest.raises(ScreenshotHookError) as failed:debug.screenshot()
        assert failed.value.result['capture'] is None
        assert failed.value.result['restore']==dict(ok=True,active=[layer])
        assert debug.layers()['active']==[layer] and not debug.closed


def test_real_hook_failures_and_stale_frame_are_not_success(sprite,emulator):
    path,binary,_=sprite
    with Project(path) as project,project.debugger(emulator,binary.parent) as debug:
        layer=hide_sprite(debug);debug.run(guest_ms=60,timeout_ms=3000,fast_forward=True)
        debug.screenshot_hooks(dict(suspend_layers=[layer]))
        with pytest.raises(ScreenshotHookError) as failed:debug.screenshot()
        assert 'newly completed frame' in failed.value.result['errors'][0]['message']
        assert failed.value.result['restore']['active']==[layer]
        debug.screenshot_hooks(dict(suspend_layers=[layer],pre=[dict(op='assert',value=0,equals=1)],
                                    post=[dict(op='assert',value=0,equals=1)]))
        result=debug.script(dict(format='fdisbull-script-1',steps=[dict(op='screenshot'),dict(op='run',guest_ms=10)]))
        assert not result['ok'] and len(result['steps'])==1
        report=result['steps'][0]['result']
        assert not report['pre']['ok'] and not report['post']['ok'] and report['capture'] is None
        assert report['restore']['active']==[layer]


def test_real_post_hook_failure_preserves_capture_and_restores_layers(sprite,emulator):
    path,binary,_=sprite
    with Project(path) as project,project.debugger(emulator,binary.parent) as debug:
        layer=hide_sprite(debug);debug.run(guest_ms=60,timeout_ms=3000,fast_forward=True)
        config=policy(layer);config['post']=[dict(op='assert',value=0,equals=1)]
        debug.screenshot_hooks(config)
        with pytest.raises(ScreenshotHookError) as failed:debug.screenshot('post-failed.png')
        report=failed.value.result
        assert report['pre']['ok'] and not report['post']['ok']
        assert color(project,report['capture'])==(170,0,0)
        assert report['restore']==dict(ok=True,active=[layer])
        events=project.debug_events(debug.run_id)['events']
        assert events[-1]['operation']=='screenshot-hooks' and not events[-1]['evidence']['ok']
        assert events[-1]['evidence']['capture']['artifact']==report['capture']['artifact']


@pytest.mark.parametrize('case',['freshness-only','layer-after-repaint'])
def test_real_freshness_only_and_layer_change_after_repaint_reject_stale_frames(sprite,emulator,case):
    path,binary,_=sprite
    with Project(path) as project,project.debugger(emulator,binary.parent) as debug:
        layer=hide_sprite(debug);debug.layers([])
        debug.run(guest_ms=60,timeout_ms=3000,fast_forward=True)
        config=(dict(require_fresh_frame=True) if case=='freshness-only' else dict(pre=[
                dict(op='run',guest_ms=60,fast_forward=True),dict(op='layer-enable',layer=layer)]))
        debug.screenshot_hooks(config)
        with pytest.raises(ScreenshotHookError) as failed:debug.screenshot()
        report=failed.value.result
        assert report['capture'] is None and 'newly completed frame' in report['errors'][0]['message']
        assert report['restore']==dict(ok=True,active=[])


@pytest.mark.parametrize('config',[
    dict(pre=[dict(op='screenshot')]),dict(post=[dict(op='run',guest_ms=10)]),
    dict(pre=[dict(op='run',guest_ms=10,stop_on_hook=False)]),
    dict(pre=[dict(op='run',guest_ms=10,expect='breakpoint')]),
    dict(pre=[dict(op='keyboard.press',key='enter')]),dict(require_fresh_frame='yes'),
    dict(suspend_layers=['same','same']),dict(timeout_ms=60001),
])
def test_screenshot_hooks_reject_recursive_unbounded_and_post_execution(config):
    with pytest.raises((ValueError,TypeError)):validate_configuration(config)


def test_screenshot_hook_configuration_is_atomic_and_hash_checked(sprite):
    path,_,_=sprite
    with Project(path) as project:
        first=project.debug_screenshot_hooks(dict(post=[dict(op='registers')]))
        with pytest.raises(ValueError):project.debug_screenshot_hooks(dict(pre=[dict(op='screenshot')]))
        assert project.debug_screenshot_hooks()['id']==first['id']
        project.db.execute('UPDATE debug_screenshot_hooks SET document=? WHERE id=?',('{}',first['id']))
        project.db.commit()
        with pytest.raises(ValueError,match='hash mismatch'):project.debug_screenshot_hooks()
