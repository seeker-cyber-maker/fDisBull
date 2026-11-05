from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1] / "examples" / "nes_c_python_before_uil" / "experiment.py"


def load_experiment():
    spec = importlib.util.spec_from_file_location("nes_c_python_before_uil", EXPERIMENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_authored_tick_shape_and_effect_partition():
    module = load_experiment()
    blocks = module.blocks()
    regions = module.regions(blocks)
    assert len(module.TICK) == 56
    assert sum(block["instructions"] for block in blocks) == 28
    assert len(blocks) == 8
    assert [region["kind"] for region in regions] == [
        "pure_logic_candidate", "effect_boundary", "effect_boundary"
    ]
    assert regions[1]["blocks"][0]["effects"] == ["apu.write"]
    assert regions[2]["blocks"][0]["effects"] == ["ppu.write"]


def test_fixed_width_python_matches_native_and_unmasked_boundary_fails():
    module = load_experiment()
    cases = [(0,0,0),(0x10,0,0),(0x10,252,0),(0x10,253,0),(0x10,254,0),
             (0x10,255,0),(0,90,1),(0x10,90,4)]
    failures=[]
    for buttons,x,cooldown in cases:
        expected=module.run_6502(buttons,x,cooldown)[:-1]
        assert module.python_tick(buttons,x,cooldown)==expected
        if module.python_tick_unmasked(buttons,x,cooldown)!=expected:
            failures.append((buttons,x,cooldown))
    assert failures == [(0x10,253,0),(0x10,254,0),(0x10,255,0)]


def test_rom_is_authored_nrom_with_reset_vectors():
    module = load_experiment()
    rom=module.build_rom()
    assert rom[:4]==b"NES\x1a"
    assert rom[4:8]==bytes([2,0,0,0])
    assert len(rom)==32784
    prg=rom[16:]
    assert prg[:len(module.TICK)]==module.TICK
    assert prg[0x7FFA:0x8000]==bytes([0,0x81,0,0x81,0,0x81])
