"""CHIP-8 sample timeline grammar and public dispatch."""
from types import SimpleNamespace
import pytest
from fdisbull.cli import METHODS
from fdisbull.debugger import DebugWorkspace
from fdisbull.debug_script import validate_script


def _script(*steps):return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':list(steps)}


def test_sample_timeline_script_accepts_stored_points():
    steps=[{'op':'timeline-start','max_frames':4,'as':'root'},
           {'op':'timeline-advance','frames':1},
           {'op':'timeline-rewind','timeline':'$root.timeline','point':'$root.point','frames':0},
           {'op':'timeline-image','timeline':'$root.timeline','point':'$root.point'}]
    assert validate_script(_script(*steps))==steps


@pytest.mark.parametrize('bad',[
    {'op':'timeline-start','max_frames':True},
    {'op':'timeline-start','storage_mode':'delta'},
    {'op':'timeline-advance','frames':0},
    {'op':'timeline-rewind','frames':-1},
    {'op':'timeline-rewind','policy':{'preserve':['v0']}},
])
def test_bad_sample_timeline_literals_refuse_whole_script(bad):
    with pytest.raises(ValueError):
        validate_script(_script({'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},bad))


def test_sample_timeline_workspace_routes(tmp_path):
    calls=[];workspace=DebugWorkspace()
    def method(name):
        def invoke(**kw):calls.append((name,kw));return {'method':name}
        return invoke
    owner=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),
        **{name:method(name) for name in ('timeline_start','timeline_status','timeline_advance','timeline_rewind','timeline_image','timeline_pin','timeline_stop','advance_frames')})
    workspace.sessions['chip8']=owner
    cases=[('debug-timeline-start',{'max_frames':4}),('debug-timeline-status',{'timeline':'t'}),
           ('debug-timeline-advance',{'frames':1}),('debug-timeline-rewind',{'timeline':'t','point':'p','frames':0}),
           ('debug-timeline-image',{'timeline':'t','point':'p'}),('debug-timeline-pin',{}),
           ('debug-timeline-stop',{}),('debug-frame-advance',{'frames':1})]
    for name,params in cases:
        assert name in METHODS
        workspace.invoke(name,tmp_path,{'run':'chip8',**params})
    assert [name for name,_ in calls]==['timeline_start','timeline_status','timeline_advance','timeline_rewind','timeline_image','timeline_pin','timeline_stop','advance_frames']
    assert calls[3][1]=={'timeline':'t','point':'p','frames':0}
