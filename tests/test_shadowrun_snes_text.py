"""Source text bitstream decoding and fail-closed boundaries."""
import hashlib
from fdisbull.game_il import GameMachine,author_program
from fdisbull.shadowrun_snes_text import SOURCE


def _machine(rom):
    return GameMachine(author_program(SOURCE.read_text(),[{'id':0,'length':len(rom),
      'sha256':hashlib.sha256(rom).hexdigest()}]),{0:bytes(rom)})


def test_text_reads_leaf_pairs_and_source_terminator():
    rom=bytearray(1<<20);rom[0x59f6:0x59f8]=(0x100).to_bytes(2,'little')
    rom[0xe8000:0xe8004]=(0xc1c2).to_bytes(2,'little')+(0x8a00).to_bytes(2,'little')
    rom[0xe8100:0xe8102]=bytes((0x40,0))
    m=_machine(rom);m.set_state({'shadowrun_snes_text_id':0x3b});m.call('shadowrun_snes_text_decode',0);s=m.snapshot()
    assert (s['shadowrun_snes_text_status'],s['shadowrun_snes_text_length'])==(1,2)
    assert s['shadowrun_snes_text_output'][:3]==[65,66,0]


def test_encoded_pointer_is_not_a_text_id_or_cpu_address():
    rom=bytearray(1<<20)
    rom[0xe8000:0xe8004]=(0xc1c2).to_bytes(2,'little')+(0x8a00).to_bytes(2,'little')
    rom[0xe8100:0xe8102]=bytes((0x40,0))
    rom[0xabc8+65]=5;rom[0xabc8+66]=7
    m=_machine(rom);m.set_state({'shadowrun_snes_text_encoded_pointer':0x100})
    m.call('shadowrun_snes_text_decode_pointer',0);m.call('shadowrun_snes_text_measure',0)
    s=m.snapshot()
    assert s['shadowrun_snes_text_output'][:3]==[65,66,0]
    assert (s['shadowrun_snes_text_measure_status'],s['shadowrun_snes_text_measured_pixels'])==(1,12)
    m.set_state({'shadowrun_snes_text_output':[124]+[0]*255,'shadowrun_snes_text_length':1})
    m.call('shadowrun_snes_text_measure',0)
    assert m.snapshot()['shadowrun_snes_text_measure_status']==0


def test_selector_icon_glyphs_have_source_font_width_without_rewriting_text():
    rom=bytearray(1<<20);rom[0xabc8+14]=8;rom[0xabc8+15]=8
    m=_machine(rom);m.set_state({'shadowrun_snes_text_status':1,
        'shadowrun_snes_text_length':2,'shadowrun_snes_text_output':[14,15]+[0]*254,
        'shadowrun_snes_text_layout_base':100,'shadowrun_snes_text_layout_cursor_in':100,
        'shadowrun_snes_text_layout_width':5,'shadowrun_snes_text_layout_height':3})
    m.call('shadowrun_snes_text_layout',0)
    assert m.snapshot()['shadowrun_snes_text_layout_status']==0
    m.set_state({'shadowrun_snes_text_layout_icon_glyphs':1})
    m.call('shadowrun_snes_text_layout',0);s=m.snapshot()
    assert (s['shadowrun_snes_text_layout_status'],s['shadowrun_snes_text_layout_cursor'],
        s['shadowrun_snes_text_layout_subpixel'])==(1,102,0)
    assert s['shadowrun_snes_text_output'][:2]==[14,15]


def test_text_rejects_other_id_and_nonterminating_tree():
    rom=bytearray(1<<20);rom[0x59f6:0x59f8]=(0x100).to_bytes(2,'little')
    m=_machine(rom);m.set_state({'shadowrun_snes_text_id':0x1340});m.call('shadowrun_snes_text_decode',0)
    assert m.snapshot()['shadowrun_snes_text_status']==0
    m.set_state({'shadowrun_snes_text_id':0x3b});m.call('shadowrun_snes_text_decode',0)
    assert m.snapshot()['shadowrun_snes_text_status']==0


def test_negative_table_pointer_selects_second_rom_bank():
    rom=bytearray(1<<20);rom[0x59f8:0x59fa]=(0x8100).to_bytes(2,'little')
    rom[0xe8000:0xe8004]=(0xc1c2).to_bytes(2,'little')+(0x8a00).to_bytes(2,'little')
    rom[0xf0100:0xf0102]=bytes((0x40,0))
    m=_machine(rom);m.set_state({'shadowrun_snes_text_id':0x3c});m.call('shadowrun_snes_text_decode',0);s=m.snapshot()
    assert (s['shadowrun_snes_text_status'],s['shadowrun_snes_text_bank'],s['shadowrun_snes_text_length'])==(1,0x9e,2)
    assert s['shadowrun_snes_text_output'][:3]==[65,66,0]


def test_tree_accepts_source_valid_odd_child_offset():
    rom=bytearray(1<<20);rom[0x59f6:0x59f8]=(0x100).to_bytes(2,'little')
    rom[0xe8000:0xe8004]=bytes((1,0,0xc1,0x8a))
    rom[0xe8100:0xe8102]=bytes((0x20,0))
    m=_machine(rom);m.set_state({'shadowrun_snes_text_id':0x3b});m.call('shadowrun_snes_text_decode',0);s=m.snapshot()
    assert (s['shadowrun_snes_text_status'],s['shadowrun_snes_text_length'])==(1,1)
    assert s['shadowrun_snes_text_output'][:2]==[65,0]


def test_plain_layout_uses_font_widths_and_wraps_exact_fit():
    rom=bytearray(1<<20)
    for code in (32,65,66):rom[0xabc8+code]=4
    m=_machine(rom);data=[65,65,65,32,66,66]+[0]*250
    m.set_state({'shadowrun_snes_text_status':1,'shadowrun_snes_text_length':6,
                 'shadowrun_snes_text_output':data,'shadowrun_snes_text_layout_base':100,
                 'shadowrun_snes_text_layout_cursor_in':100,
                 'shadowrun_snes_text_layout_width':4,'shadowrun_snes_text_layout_height':4})
    m.call('shadowrun_snes_text_layout',0);s=m.snapshot()
    assert (s['shadowrun_snes_text_layout_status'],s['shadowrun_snes_text_layout_cursor'],
            s['shadowrun_snes_text_layout_subpixel'],s['shadowrun_snes_text_layout_line'])==(1,103,0,1)
    data[1]=124;m.set_state({'shadowrun_snes_text_output':data})
    m.call('shadowrun_snes_text_layout',0)
    assert m.snapshot()['shadowrun_snes_text_layout_status']==0


def test_three_row_window_accepts_one_line_and_refuses_a_wrap():
    rom=bytearray(1<<20)
    for code in (32,65,66):rom[0xabc8+code]=4
    m=_machine(rom);data=[65,65,32,66]+[0]*252
    m.set_state({'shadowrun_snes_text_status':1,'shadowrun_snes_text_length':4,
                 'shadowrun_snes_text_output':data,'shadowrun_snes_text_layout_base':100,
                 'shadowrun_snes_text_layout_cursor_in':100,
                 'shadowrun_snes_text_layout_width':5,'shadowrun_snes_text_layout_height':3})
    m.call('shadowrun_snes_text_layout',0);s=m.snapshot()
    assert (s['shadowrun_snes_text_layout_status'],s['shadowrun_snes_text_layout_cursor'],
            s['shadowrun_snes_text_layout_subpixel'],s['shadowrun_snes_text_layout_line'])==(1,102,0,0)
    m.set_state({'shadowrun_snes_text_layout_width':4})
    m.call('shadowrun_snes_text_layout',0)
    assert m.snapshot()['shadowrun_snes_text_layout_status']==0


def test_plain_layout_advances_past_partially_occupied_last_tile():
    rom=bytearray(1<<20);rom[0xabc8+65]=6
    m=_machine(rom);m.set_state({'shadowrun_snes_text_status':1,'shadowrun_snes_text_length':1,
        'shadowrun_snes_text_output':[65]+[0]*255,'shadowrun_snes_text_layout_base':100,
        'shadowrun_snes_text_layout_cursor_in':100,'shadowrun_snes_text_layout_width':22,
        'shadowrun_snes_text_layout_height':3})
    m.call('shadowrun_snes_text_layout',0);s=m.snapshot()
    assert (s['shadowrun_snes_text_layout_status'],s['shadowrun_snes_text_layout_cursor'],
            s['shadowrun_snes_text_layout_subpixel'])==(1,101,6)
