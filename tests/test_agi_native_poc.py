import importlib.util
from pathlib import Path
import pytest

SCRIPT = Path(__file__).parents[1] / "examples" / "agi" / "compile_compact_linux.py"
spec = importlib.util.spec_from_file_location("agi_native_poc", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def projection(action="ui.print"):
    return {
        "format":"fdisbull-agi-state-projection-3",
        "source":{"logic":7,"resource_sha256":"1"*64},
        "uil":{
            "format":"fdisbull-il-2","role":"uil",
            "variables":{
                "$flag":{"type":"bool","initial":False},
                "$mode":{"type":"bool","initial":False},
                "$timer":{"type":"u8","initial":0},
            },
            "resources":{},"entry":"entry",
            "continuations":{
                "entry":{"body":[],"transfer":{"op":"if","condition":{"op":"eq","left":{"var":"$flag"},"right":True},"then":"show","else":"done"}},
                "show":{"body":[{"id":"e","op":"effect","contract":"fdisbull.agi.object-resource.2.917.v1","action":action,
                    "args":{"message":3,"output_mode":{"var":"$mode"},"window_timer":{"var":"$timer"}},
                    "outputs":{"output_mode":"$mode","window_timer":"$timer"},"binding":"1"*64}],
                    "transfer":{"op":"goto","target":"done"}},
                "done":{"body":[],"transfer":{"op":"return"}},
            },"evidence":{}
        }
    }


def test_emits_bounded_native_c_without_resource_text():
    source=module.emit_c(projection(),source_logic=7,source_sha256="1"*64)
    assert "SOURCE_LOGIC 7" in source
    assert "ui.print" in source
    assert "emit_print(3)" in source
    assert "message text" not in source
    assert "prior_mode?prior_timer:0" in source


def test_refuses_unimplemented_effect_provider():
    with pytest.raises(ValueError,match="ui.print"):
        module.emit_c(projection("object.draw"))
