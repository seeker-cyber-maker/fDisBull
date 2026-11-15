"""Failure boundaries of the bounded source-seeded scripted slice."""
import hashlib

import pytest

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_npc import SOURCE as NPC_SOURCE
from fdisbull.shadowrun_snes_script import SOURCE as SCRIPT_SOURCE
from fdisbull import shadowrun_snes_scripted as scripted


def _machine():
    rom = bytes(1 << 20)
    npc = NPC_SOURCE.read_text().replace(
        'typedef unsigned char u8;\ntypedef unsigned int u16;\n'
        'typedef unsigned long u32;\nu8 rom8(u8 region,u32 offset);\n', '')
    source = '\n'.join((SCRIPT_SOURCE.read_text(), npc, scripted._DECL,
                        scripted._LOAD, scripted._SAVE, scripted._FRAME))
    program = author_program(source, [{'id':0, 'length':len(rom),
                                      'sha256':hashlib.sha256(rom).hexdigest()}])
    return GameMachine(program, {0:rom})


def test_profile_rejects_wrong_checkpoint(monkeypatch):
    rom = bytes(1 << 20)
    monkeypatch.setattr(scripted, 'ROM_SHA256', hashlib.sha256(rom).hexdigest())
    with pytest.raises(ValueError, match='wrong source main-loop checkpoint'):
        scripted.machine_from_scripted_capture(rom, bytes(131072), bytes(8192))


def test_profile_budget_refuses_without_advancing():
    machine = _machine()
    machine.set_state({'scripted_passes':60})
    machine.call('shadowrun_snes_frame', 0)
    state = machine.snapshot()
    assert (state['shadowrun_snes_frame_status'], state['scripted_failure'],
            state['scripted_passes']) == (2, 2, 60)


def test_full_task_list_cycle_refuses_before_actor_updates():
    machine = _machine()
    waits=[0xffff]*48
    machine.set_state({'task_list_head':0, 'task_next':[0]*48, 'task_wait':waits})
    machine.call('shadowrun_snes_frame', 0)
    state = machine.snapshot()
    assert (state['shadowrun_snes_frame_status'], state['scripted_failure'],
            state['scripted_passes']) == (2, 19, 0)
