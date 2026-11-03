"""Authored address-filter validation, without a source cartridge."""
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/capture_genesis_scene.py'
spec=importlib.util.spec_from_file_location('scene_trace',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_pc_and_work_ram_ranges_are_numeric_and_bounded():
    assert module.trace_ranges(['0x14000:0x16000']) == [(0x14000,0x16000)]
    assert module.trace_ranges(['0xff0100:0xff0200'],memory=True) == [(0xff0100,0xff0200)]
    for value in ('0:0','2:1','0:0x1000001','0:1:2','__import__("os"):1'):
        with pytest.raises(ValueError):module.trace_ranges([value])
    with pytest.raises(ValueError):module.trace_ranges(['0:1'],memory=True)
    with pytest.raises(ValueError):module.trace_ranges(['0:1']*17)
