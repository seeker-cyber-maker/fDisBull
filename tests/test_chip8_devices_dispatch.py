"""Architecture-specific device JSON routes do not change DOS interfaces."""
from types import SimpleNamespace
import pytest
from fdisbull.cli import METHODS
from fdisbull.debugger import DebugWorkspace


def test_device_routes_use_selected_chip8_owner(tmp_path):
    workspace=DebugWorkspace()
    owner=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),
        chip8_environment=lambda:{'native':'environment'},
        chip8_keypad=lambda keys:{'held':keys},
        chip8_tick=lambda ticks:{'manual':ticks})
    workspace.sessions['chip8']=owner
    assert workspace.invoke('debug-chip8-environment',tmp_path,{'run':'chip8'})=={'native':'environment'}
    assert workspace.invoke('debug-chip8-keypad',tmp_path,{'run':'chip8','keys':[0,15]})=={'held':[0,15]}
    assert workspace.invoke('debug-chip8-tick',tmp_path,{'run':'chip8','ticks':3})=={'manual':3}


def test_device_routes_refuse_unavailable_context_and_are_discoverable(tmp_path):
    workspace=DebugWorkspace()
    workspace.sessions['legacy']=SimpleNamespace(project=SimpleNamespace(path=tmp_path.resolve()),metadata={'backend':'dosbox'})
    for method in ('debug-chip8-environment','debug-chip8-keypad','debug-chip8-tick'):
        assert method in METHODS
        with pytest.raises(ValueError,match='unavailable'):
            workspace.invoke(method,tmp_path,{'run':'legacy'})
