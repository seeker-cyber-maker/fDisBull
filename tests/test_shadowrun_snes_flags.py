from pathlib import Path
import hashlib

from fdisbull.game_il import GameMachine, author_program


SOURCE = Path(__file__).resolve().parents[1] / 'src/fdisbull/game_sources/shadowrun_snes_flags.c'


def test_source_merge_branches_and_existing_bits():
    machine = GameMachine(author_program(SOURCE.read_text()), {})
    # The two low scratch bits choose four source branches. Existing flag bits
    # survive; those selector bits are not copied in the nonzero cases.
    for scratch, expected in ((0x0804, 0xa964), (0x0805, 0xa964),
                              (0x0806, 0xab64), (0x0007, 0xa964)):
        machine.set_state({'shadowrun_snes_flags_in': 0xa160,
                           'shadowrun_snes_flags_scratch': scratch})
        machine.call('shadowrun_snes_flags_merge')
        assert machine.snapshot()['shadowrun_snes_flags_out'] == expected


def test_observed_actor_stage_change():
    machine = GameMachine(author_program(SOURCE.read_text()), {})
    for scratch, expected in ((0x0005, 0xa167), (0x0805, 0xa967)):
        machine.set_state({'shadowrun_snes_flags_in': 0xa163,
                           'shadowrun_snes_flags_scratch': scratch})
        machine.call('shadowrun_snes_flags_merge')
        assert machine.snapshot()['shadowrun_snes_flags_out'] == expected


def test_scan_uses_source_table_cells_and_refuses_unknown_sprite():
    ram = bytearray(131072)
    # A negative second height branches directly to selector 2 even when the
    # third height would otherwise be below the actor ($80:B375 -> B39D).
    for offset in range(0, 96, 6):
        ram[0x10c00 + offset:0x10c06 + offset] = bytes.fromhex('ff7fffff0000')
    data = bytes(ram)
    rom = bytearray(0xe0000)
    rom[0xd9f6a:0xd9f6d] = bytes.fromhex('102e21')
    rom = bytes(rom)
    program = author_program(SOURCE.read_text(), [
        {'id': 0, 'length': len(rom), 'sha256': hashlib.sha256(rom).hexdigest()},
        {'id': 1, 'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()}])
    machine = GameMachine(program, {0: rom, 1: data})
    machine.set_state({'shadowrun_snes_flag_x': 1428, 'shadowrun_snes_flag_y': 2008,
                       'shadowrun_snes_flag_z': 256, 'shadowrun_snes_flag_depth': 1718,
                       'shadowrun_snes_flag_camera_x': 328, 'shadowrun_snes_flag_camera_y': 147,
                       'shadowrun_snes_flag_sprite': 0x1f6a, 'shadowrun_snes_flags_in': 0xa167})
    machine.call('shadowrun_snes_flags_project')
    state = machine.snapshot()
    assert (state['shadowrun_snes_flag_status'], state['shadowrun_snes_flags_scratch'],
            state['shadowrun_snes_flags_out']) == (1, 0x806, 0xab67)
    machine.set_state({'shadowrun_snes_flag_sprite': 0x1234})
    machine.call('shadowrun_snes_flags_project')
    assert machine.snapshot()['shadowrun_snes_flag_status'] == 0
    machine.set_state({'shadowrun_snes_flag_sprite': 0x1f6a,
                       'shadowrun_snes_flag_camera_x': 1000})
    machine.call('shadowrun_snes_flags_project')
    assert machine.snapshot()['shadowrun_snes_flag_status'] == 0


def test_left_animation_reads_table_and_guards_regime():
    rom = bytearray(0xe0000)
    rom[0x60903] = 0x20
    rom[0x60920:0x60922] = (0x1f53).to_bytes(2, 'little')
    rom[0xd9f53] = 2
    data = bytes(rom)
    program = author_program(SOURCE.read_text(), [
        {'id': 0, 'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()}])
    machine = GameMachine(program, {0: data})
    machine.set_state({'shadowrun_snes_flag_phase': 120, 'shadowrun_snes_flag_timer': 1,
                       'shadowrun_snes_flag_selector': 40, 'shadowrun_snes_flag_sprite': 0x1f86})
    machine.call('shadowrun_snes_flag_animate_left')
    state = machine.snapshot()
    assert (state['shadowrun_snes_flag_animation_status'], state['shadowrun_snes_flag_phase'],
            state['shadowrun_snes_flag_timer'], state['shadowrun_snes_flag_selector'],
            state['shadowrun_snes_flag_sprite']) == (1, 9, 4, 34, 0x1f5c)
    machine.set_state({'shadowrun_snes_flag_timer': 0})
    machine.call('shadowrun_snes_flag_animate_left')
    assert machine.snapshot()['shadowrun_snes_flag_animation_status'] == 0


def test_cardinal_start_turn_and_idle_use_source_records():
    rom = bytearray(0xe0000)
    rom[0x608c6:0x608c8] = (0x88d8).to_bytes(2, 'little')
    rom[0x608ca:0x608cc] = (0x88f8).to_bytes(2, 'little')
    rom[0x608d8:0x608da] = bytes((0, 1))
    rom[0x608f8:0x608fa] = bytes((17, 132))
    rom[0x60901], rom[0x60903] = 0x10, 0x20
    rom[0x608e1], rom[0x608e3] = 0x0a, 0x0e
    for address, descriptor in ((0x60910, 0x1ee3), (0x60920, 0x1f53),
                                (0x608ea, 0x1e49), (0x608ee, 0x1e65)):
        rom[address:address + 2] = descriptor.to_bytes(2, 'little')
        rom[0xd8000 + descriptor] = 2
    data = bytes(rom)
    m = GameMachine(author_program(SOURCE.read_text(), [
        {'id': 0, 'length': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]), {0: data})
    m.set_state({'shadowrun_snes_flag_requested_direction': 3})
    m.call('shadowrun_snes_flag_walk_start')
    m.call('shadowrun_snes_flag_walk_tick')
    assert (m.snapshot()['shadowrun_snes_flag_sprite'], m.snapshot()['shadowrun_snes_flag_timer']) == (0x1f5c, 4)
    # A turn with timer 1 selects the new direction's first descriptor.
    m.set_state({'shadowrun_snes_flag_requested_direction': 1, 'shadowrun_snes_flag_timer': 1})
    m.call('shadowrun_snes_flag_walk_tick')
    assert (m.snapshot()['shadowrun_snes_flag_direction'], m.snapshot()['shadowrun_snes_flag_sprite']) == (1, 0x1eec)
    m.call('shadowrun_snes_flag_walk_stop')
    assert (m.snapshot()['shadowrun_snes_flag_sprite'], m.snapshot()['shadowrun_snes_flag_phase']) == (0x1e52, 0)
