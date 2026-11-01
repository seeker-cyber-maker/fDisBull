"""Tests for the reviewed animation counter and fail-closed interfaces."""
import hashlib
import json
import pytest
import fdisbull.shadowrun_animation as animation
from fdisbull.game_il import GameMachine, author_program
from fdisbull.shadowrun_animation import ANIMATION_SOURCE, observed_poses, observed_right_walk_pose


def counter(accumulator, increment, threshold, index=3, flags=0xa4):
    machine = GameMachine(author_program(ANIMATION_SOURCE.read_text()))
    machine.set_state({'shadowrun_anim_accumulator': accumulator,
                       'shadowrun_anim_increment': increment,
                       'shadowrun_anim_threshold': threshold,
                       'shadowrun_anim_index': index, 'shadowrun_anim_flags': flags})
    machine.call('shadowrun_animation_tick')
    return machine.snapshot()


def test_counter_crossing_and_16bit_wrap():
    state = counter(0xfb0, 0x1e0, 0x1000)
    assert (state['shadowrun_anim_accumulator'], state['shadowrun_anim_index'],
            state['shadowrun_anim_flags']) == (0x190, 4, 0xa5)
    state = counter(0xffff, 1, 0x1000)
    assert (state['shadowrun_anim_accumulator'], state['shadowrun_anim_index'],
            state['shadowrun_anim_flags']) == (0, 3, 0xa4)


def test_positive_table_wrap():
    machine = GameMachine(author_program(ANIMATION_SOURCE.read_text()))
    for before, after in [(0, 0), (3, 3), (4, 0), (0xffff, 0xffff)]:
        machine.set_state({'shadowrun_anim_index': before, 'shadowrun_anim_positive_count': 4})
        machine.call('shadowrun_animation_positive_wrap')
        assert machine.snapshot()['shadowrun_anim_index'] == after


def test_invalid_source_refused():
    with pytest.raises(ValueError):
        observed_poses(b'', '/does-not-exist', [1])
    with pytest.raises(ValueError):
        observed_right_walk_pose(b'', 3, 0x28, 1)


def test_capture_payload_tamper_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(animation, 'checked_rom', lambda rom: None)
    rom = b'synthetic input'
    scene = tmp_path / 'native' / 'scene-000001'
    scene.mkdir(parents=True)
    (scene / 'vram.bin').write_bytes(b'tampered')
    receipt = {'format': 'fdisbull-private-genesis-scenes-1',
               'inputs': {'rom': {'sha256': hashlib.sha256(rom).hexdigest()},
                          'core': {'sha256': animation.CORE_SHA256}},
               'captures': [1],
               'files': {'native/scene-000001/vram.bin': {
                   'size': 8, 'sha256': hashlib.sha256(b'original').hexdigest()}}}
    (tmp_path / 'capture.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='payload mismatch'):
        observed_poses(rom, tmp_path, [1])
