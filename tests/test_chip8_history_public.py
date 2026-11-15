"""CHIP-8 history grammar and ordinary JSON dispatch without a guest."""
from types import SimpleNamespace
import pytest
from fdisbull.cli import METHODS
from fdisbull.debugger import DebugWorkspace
from fdisbull.debug_script import validate_script


def _script(*steps):return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':list(steps)}


def test_chip8_history_script_accepts_capture_and_explicit_node():
    steps=[{'op':'rewind-start','max_steps':4,'as':'root'},
           {'op':'rewind-record','advance':'capture'},
           {'op':'rewind','history':'$root.history','node':'$root.cursor'}]
    assert validate_script(_script(*steps))==steps


@pytest.mark.parametrize('bad',[
    {'op':'rewind-record','advance':'replay'},
    {'op':'rewind-record','advance':'capture','count':2},
    {'op':'rewind-start','max_steps':True},
    {'op':'rewind','count':0},
])
def test_invalid_chip8_history_script_refuses_whole_sequence(bad):
    with pytest.raises(ValueError):
        validate_script(_script({'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},bad))


def test_chip8_history_workspace_routes_forward_exact_parameters(tmp_path):
    calls=[];workspace=DebugWorkspace()
    owner=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),
        rewind_start=lambda **kw:calls.append(('start',kw)) or {'history':'h','cursor':'n'},
        rewind_status=lambda **kw:calls.append(('status',kw)) or {'valid':False},
        rewind_record=lambda **kw:calls.append(('record',kw)) or {'recorded_count':1},
        rewind=lambda **kw:calls.append(('rewind',kw)) or {'cursor':kw['node']})
    workspace.sessions['chip8']=owner
    for name,params in [('debug-rewind-start',{'max_steps':4}),('debug-rewind-status',{'history':'h'}),
                        ('debug-rewind-record',{'advance':'capture'}),('debug-rewind',{'history':'h','node':'n'})]:
        assert name in METHODS
        workspace.invoke(name,tmp_path,{'run':'chip8',**params})
    assert calls==[('start',{'max_steps':4}),('status',{'history':'h'}),
                   ('record',{'advance':'capture'}),('rewind',{'history':'h','node':'n'})]
