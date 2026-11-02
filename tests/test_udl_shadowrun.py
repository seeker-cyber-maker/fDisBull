"""Authored vectors for the bounded Shadowrun interfaces; no game bytes."""
import hashlib
from io import BytesIO

from PIL import Image
import pytest

from fdisbull import udl_shadowrun as subject
from fdisbull.game_il import GameMachine


@pytest.fixture
def authored_rom(monkeypatch):
    data = bytearray(subject.ROM_SIZE)
    table = [(index * 0x1234 + 5) & 0xffff for index in range(16)]
    for index, value in enumerate(table):
        offset = subject.TABLE_START + 2 * index
        data[offset:offset+2] = value.to_bytes(2, 'big')
    raw = bytes(data)
    sha = lambda x: hashlib.sha256(x).hexdigest()
    monkeypatch.setattr(subject, 'ROM_SHA256', sha(raw))
    monkeypatch.setattr(subject, 'INPUT_SHA256', sha(raw[subject.INPUT_START:subject.INPUT_END]))
    monkeypatch.setattr(subject, 'TABLE_SHA256', sha(raw[subject.TABLE_START:subject.TABLE_END]))
    monkeypatch.setattr(subject, 'HEADING_SHA256', sha(raw[subject.HEADING_START:subject.HEADING_END]))
    return raw, table


def test_input_procedure_retains_held_edges_and_rom_table(authored_rom):
    rom, table = authored_rom
    program = subject.lift_input(rom)
    machine = GameMachine(program, {0: rom})
    for previous in (0, 1, 0x80, 0x100, 0xa55a, 0xffff):
        for current in range(256):
            machine.set_state({'shadowrun_pad_held': previous})
            machine.call('shadowrun_input_tick', current)
            assert machine.snapshot() == {
                'shadowrun_pad_held': current,
                'shadowrun_pad_sample': ((((previous ^ current) & current) << 8) | current) & 0xffff,
                'shadowrun_direction_angle': table[current & 15],
            }
    assert 'movement' in program['evidence']['excluded']


def test_cartridge_and_scoped_code_fail_closed(authored_rom, monkeypatch):
    rom, _ = authored_rom
    with pytest.raises(ValueError, match='exact reviewed'):
        subject.lift_input(rom[:-1] + bytes([rom[-1] ^ 1]))
    monkeypatch.setattr(subject, 'INPUT_SHA256', '0' * 64)
    with pytest.raises(ValueError, match='code or table differs'):
        subject.lift_input(rom)


@pytest.mark.parametrize(('heading', 'target', 'expected'), [
    (0, 0, 0), (0x100, 0, 0), (0x800, 0, 0), (0x801, 0, 1),
    (0xff00, 0x100, 0x100), (0xf000, 0, 0xf800),
    (0x8000, 0, 0x8800), (0x7fff, 0, 0x77ff),
])
def test_heading_wrap_and_boundaries(authored_rom, heading, target, expected):
    rom, _ = authored_rom
    machine = GameMachine(subject.lift_heading(rom))
    machine.set_state({'shadowrun_heading': heading, 'shadowrun_heading_target': target})
    machine.call('shadowrun_heading_tick')
    assert machine.snapshot() == {'shadowrun_heading': expected, 'shadowrun_heading_target': target}


def png(color=(0, 0, 0), size=(320, 224)):
    output = BytesIO()
    Image.new('RGB', size, color).save(output, format='PNG')
    return output.getvalue()


def test_observed_frame_projection_is_bounded_and_blank(authored_rom):
    rom, _ = authored_rom
    data = png()
    projection = subject.project_observed_frame(rom, data)
    assert projection['chr'] == bytes(4096)
    assert projection['nametable'] == bytes(960)
    assert projection['attributes'] == bytes(64)
    assert len(projection['palette']) == 16
    assert projection['evidence']['unique_tiles'] == 1
    assert projection['evidence']['observed_png_sha256'] == hashlib.sha256(data).hexdigest()
    assert 'sprites and animation frozen' in projection['evidence']['limits']
    with pytest.raises(ValueError, match='320x224'):
        subject.project_observed_frame(rom, png(size=(256, 224)))


def test_absolute_atlas_coverage_and_four_nametables(authored_rom):
    rom, _ = authored_rom
    size = 512 * 480
    coverage = bytearray(b'\1' * size)
    coverage[0] = 0
    projected = subject.project_world_atlas(
        rom, bytes(size * 3), bytes(coverage), bytes(size), world_y0=0)
    assert len(projected['nametables']) == 4
    assert all(len(table) == 1024 for table in projected['nametables'])
    assert projected['evidence']['viewport'] == [256, 224]
    assert projected['evidence']['source_patterns'] == 1
    valid = projected['camera_valid']
    assert len(valid) == 8192
    assert valid[0] & 1 == 0
    assert valid[0] & 2 != 0
    assert valid[-1] & 128 != 0
    with pytest.raises(ValueError, match='Conflicting'):
        subject.project_world_atlas(rom, bytes(size * 3), bytes(coverage),
                                    b'\1' + bytes(size - 1), world_y0=0)


def test_authored_stoker_labels_fit_free_chr_slots():
    from fdisbull.udc_nes_shadowrun import _authored_stoker_screens
    original = bytes(8192)
    chars, screens = _authored_stoker_screens(original, 210)
    assert len(chars) == len(original)
    assert chars[:210 * 16] == original[:210 * 16]
    assert any(chars[210 * 16:256 * 16])
    assert len(screens) == 4 * 1040
    assert all(any(screens[i * 1040:i * 1040 + 960]) for i in range(4))
    with pytest.raises(ValueError, match='few tiles'):
        _authored_stoker_screens(original, 250)


def test_stoker_exit_projects_observed_position_and_heading():
    from fdisbull.game_il import author_program
    interaction = subject.SOURCE.with_name('shadowrun_interaction.c').read_text()
    composition = subject.SOURCE.with_name('shadowrun_opening_stoker.c').read_text()
    # The focused modal-exit test supplies no fabricated scene or ROM data.
    stubs = '''
    unsigned char shadowrun_player_event_flags, shadowrun_opening_status;
    unsigned char shadowrun_unresolved_event, shadowrun_player_flags;
    unsigned char shadowrun_probe_corners[4];
    unsigned int shadowrun_camera_freeze_c, shadowrun_player_x, shadowrun_player_y;
    unsigned int shadowrun_player_heading, shadowrun_player_target_heading;
    unsigned int shadowrun_player_proposed_x, shadowrun_player_proposed_y;
    unsigned int shadowrun_scene_mode, shadowrun_event_mode, shadowrun_collision_status;
    unsigned int shadowrun_camera_player_x, shadowrun_camera_player_y, shadowrun_camera_heading;
    unsigned int shadowrun_camera_x, shadowrun_camera_y, shadowrun_camera_scroll_ax, shadowrun_camera_scroll_ay;
    unsigned int shadowrun_camera_scroll_bx, shadowrun_camera_scroll_by, shadowrun_camera_stream_x, shadowrun_camera_stream_y;
    void shadowrun_input_tick(unsigned char x) {}
    void shadowrun_opening_frame(unsigned char x) {}
    void shadowrun_camera_tick(void) {}
    '''
    machine = GameMachine(author_program(interaction + stubs + composition), {})
    machine.set_state({'shadowrun_stoker_ui_mode':4, 'shadowrun_stoker_ui_previous':64,
                       'shadowrun_player_x':0x3d3a, 'shadowrun_player_y':0x2a62,
                       'shadowrun_player_heading':0, 'shadowrun_player_target_heading':0,
                       'shadowrun_player_event_flags':0x20,
                       'shadowrun_interaction_event_latch':0x20,
                       'shadowrun_interaction_trigger_busy':0xffff,
                       'shadowrun_camera_x':0x3570, 'shadowrun_camera_y':0x2220,
                       'shadowrun_camera_scroll_ax':0x1234, 'shadowrun_camera_scroll_ay':0x1234,
                       'shadowrun_camera_scroll_bx':0x1234, 'shadowrun_camera_scroll_by':0x1234,
                       'shadowrun_camera_stream_x':0, 'shadowrun_camera_stream_y':0,
                       'shadowrun_camera_freeze_c':0xffff})
    machine.call('shadowrun_opening_stoker_frame', 0)
    state = machine.snapshot()
    assert (state['shadowrun_player_x'],state['shadowrun_player_y'],
            state['shadowrun_player_heading'],state['shadowrun_player_target_heading']) == (0x3d3a,0x2bc0,0x8000,0x8000)
    assert state['shadowrun_player_event_flags'] == state['shadowrun_camera_freeze_c'] == 0
    assert (state['shadowrun_camera_x'],state['shadowrun_camera_y']) == (0x3500,0x2200)
    assert all(state[k]==0 for k in ('shadowrun_camera_scroll_ax','shadowrun_camera_scroll_ay',
                                      'shadowrun_camera_scroll_bx','shadowrun_camera_scroll_by'))
    assert state['shadowrun_camera_stream_x'] == state['shadowrun_camera_stream_y'] == 0xffff
