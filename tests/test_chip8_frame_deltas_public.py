"""Public CHIP-8 lossless sample-history configuration."""
from types import SimpleNamespace
import pytest
from fdisbull.cli import METHODS, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.debug_script import validate_script


def _script(*steps):return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':list(steps)}


@pytest.mark.parametrize('storage',['full','delta'])
def test_frame_storage_script_grammar(storage):
    step={'op':'timeline-start','storage_mode':storage,'keyframe_interval':2}
    assert validate_script(_script(step))==[step]


@pytest.mark.parametrize('step',[{'op':'timeline-start','storage_mode':'other'},
    {'op':'timeline-start','storage_mode':'delta','keyframe_interval':0},
    {'op':'timeline-start','storage_mode':'delta','keyframe_interval':129}])
def test_bad_storage_refuses_whole_script(step):
    with pytest.raises(ValueError):
        validate_script(_script({'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},step))


def test_delta_options_forwarded_by_workspace(tmp_path):
    calls=[];workspace=DebugWorkspace()
    def timeline_start(**kwargs):calls.append(kwargs);return {'storage_mode':'delta'}
    workspace.sessions['chip8']=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),timeline_start=timeline_start)
    assert 'debug-timeline-start' in METHODS
    result=workspace.invoke('debug-timeline-start',tmp_path,{'run':'chip8','storage_mode':'delta','keyframe_interval':3})
    assert result['storage_mode']=='delta' and calls==[{'storage_mode':'delta','keyframe_interval':3}]


def test_json_delta_options_reach_owned_session(tmp_path):
    calls=[];workspace=DebugWorkspace()
    def timeline_start(**kwargs):calls.append(kwargs);return {'storage_mode':'delta'}
    workspace.sessions['chip8']=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),timeline_start=timeline_start)
    try:
        reply=respond({'method':'debug-timeline-start','params':{'project':str(tmp_path),'run':'chip8',
            'storage_mode':'delta','keyframe_interval':3,'timeout_ms':400}},debugger=workspace)
        assert reply['ok'] and reply['result']['storage_mode']=='delta',reply
        assert calls==[{'storage_mode':'delta','keyframe_interval':3,'timeout_ms':400}]
    finally:workspace.sessions.clear()
