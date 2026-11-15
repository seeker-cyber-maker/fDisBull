"""Public CHIP-8 frame-key script grammar and routing."""
from types import SimpleNamespace
import pytest
from fdisbull.debug_script import validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.cli import METHODS


def _script(*steps):return {'format':'fdisbull-script-1','backend':'qemu-chip8','steps':list(steps)}
def _edge(key,pressed):return {'key':key,'pressed':pressed}


def test_chip8_owned_key_script_grammar_and_zero_rewind():
    steps=[{'op':'frame-inputs','edges':[_edge('0',True)]},
           {'op':'timeline-advance','frames':1,'inputs':[{'frame':0,'edges':[_edge('0',False)]}]},
           {'op':'timeline-rewind','frames':0}]
    assert validate_script(_script(*steps))==steps


@pytest.mark.parametrize('edges',[[ _edge('g',True)],[_edge('0',1)],[_edge('a',True),_edge('a',False)]])
def test_invalid_chip8_edges_refuse_whole_script(edges):
    with pytest.raises(ValueError):
        validate_script(_script({'op':'write-memory','address':0x300,'data_hex':'01','expected_hex':'00'},
                                {'op':'frame-inputs','edges':edges}))


def test_chip8_frame_inputs_workspace_route(tmp_path):
    calls=[];workspace=DebugWorkspace()
    def frame_inputs(**kwargs):calls.append(kwargs);return {'held':['0']}
    owner=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),frame_inputs=frame_inputs)
    workspace.sessions['chip8']=owner
    assert 'debug-frame-inputs' in METHODS
    result=workspace.invoke('debug-frame-inputs',tmp_path,{'run':'chip8','edges':[_edge('0',True)],'timeout_ms':400})
    assert result['held']==['0'] and calls==[{'edges':[_edge('0',True)],'timeout_ms':400}]
