import hashlib

from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_snes_dialogue import SOURCE as DIALOGUE
from fdisbull.shadowrun_snes_script import SOURCE as SCRIPT


def machine(record):
    rom = bytearray(1048576)
    rom[0x68000:0x68000 + len(record)] = record
    rom = bytes(rom)
    program = author_program(SCRIPT.read_text() + '\n' + DIALOGUE.read_text(),
                             [{'id': 0, 'length': len(rom),
                               'sha256': hashlib.sha256(rom).hexdigest()}])
    m = GameMachine(program, {0: rom})
    shared = [0] * 65536
    shared[0x3ca3:0x3ca6] = [4, 9, 255]
    m.set_state({'task_shared': shared, 'dialogue_record': 0x8000})
    return m


def test_record_adds_sorted_keywords_and_exposes_script_and_text():
    # Entry 0x20 adds keywords 2 and 9, starts script 0x1234, draws 0x5678.
    m = machine(bytes([0, 0, 0, 0, 0x20, 8, 0x82, 2, 9, 0x34, 0x12, 0x78, 0x56, 0xf8]))
    m.set_state({'dialogue_selector': 0x20})
    m.call('shadowrun_snes_dialogue_entry', 0)
    s = m.snapshot()
    assert (s['dialogue_status'], s['dialogue_has_script'], s['dialogue_script'],
            s['dialogue_text']) == (1, 1, 0x1234, 0x5678)
    assert s['task_shared'][0x3ca3:0x3ca7] == [2, 4, 9, 255]


def test_unknown_selector_uses_source_fallback():
    m = machine(bytes([0, 0, 0, 0, 0xfd, 4, 0, 0x34, 0x12, 0xf8]))
    m.set_state({'dialogue_selector': 0x33})
    m.call('shadowrun_snes_dialogue_entry', 0)
    s = m.snapshot()
    assert (s['dialogue_status'], s['dialogue_has_script'], s['dialogue_text']) == (1, 0, 0x1234)


def test_malformed_entry_refuses_without_writing_shared_state():
    m = machine(bytes([0, 0, 0, 0, 0x20, 2, 0x80, 0xf8]))
    m.set_state({'dialogue_selector': 0x20})
    before = m.snapshot()['task_shared']
    m.call('shadowrun_snes_dialogue_entry', 0)
    s = m.snapshot()
    assert s['dialogue_status'] == 0 and s['task_shared'] == before
