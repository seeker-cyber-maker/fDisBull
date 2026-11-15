"""Project-free sequence routes and explicit-input simulation, authored assets."""
import json
import struct
import wave

import pytest

from fdisbull.cli import main, respond
from fdisbull.dinopark_media import decode_media, inspect_dinopark, simulate_animation
from fdisbull.dinopark_playback import PLAYBACK_PROFILE
from fdisbull.format_registry import format_catalog, identify_file


def actor_with_program():
    # One opaque pixel. The program selects it at (7,9), then terminates.
    commands = bytes((0x41, 0))
    sprite = struct.pack('<8H', 1, 1, 0, 0, 0, 0, len(commands), 1) + commands + b'\x01'
    program = bytes((0x1b, 0, 0x1c, 1, 0x40, 0, 7, 0x41, 0, 9, 0x12, 1, 3))
    sequence = struct.pack('<H', len(program)) + program + b'\x00'
    directory = 14 + len(sprite) + len(sequence)
    return b'UNC2' + struct.pack('<HIHH', 1, directory, 1, len(sequence)) + sprite + sequence + struct.pack('<I', 14)


def source(tmp_path):
    p = tmp_path / 'authored.ACT'
    p.write_bytes(actor_with_program())
    return p


def test_sequence_route_exposes_inspection_without_program_buffers(tmp_path):
    p = source(tmp_path)
    result = inspect_dinopark(p, adapter='dinopark-act-sequence')
    assert result['program_count'] == 1
    assert result['programs'][0]['unsupported_opcodes'] == []
    assert result['programs'][0]['instructions'][0]['mnemonic'] == 'set.sprite'
    assert all('operands' not in row and 'scratch' not in row for row in result['programs'][0]['instructions'])
    assert p.read_bytes() == actor_with_program()


def test_logical_tick_simulation_has_separate_scheduling_and_draw_phases(tmp_path):
    p = source(tmp_path)
    result = simulate_animation(p, ticks=[0, 1])
    assert result['ticks'][0]['draws'] == ()
    assert result['ticks'][1]['draws'] == ((0, 3, 7, 9, 0),)
    assert not result['native_runtime_tested'] and not result['rendered_graphics']
    assert not result['source_modified'] and p.read_bytes() == actor_with_program()


@pytest.mark.parametrize('ticks', [[], [True], [-1], [0x100000000], [0] * 129, iter([0])])
def test_simulation_rejects_implicit_unbounded_or_invalid_ticks(tmp_path, ticks):
    with pytest.raises(ValueError, match='ticks'):
        simulate_animation(source(tmp_path), ticks=ticks)


def test_catalog_keeps_pixel_and_sequence_reader_roles_separate(tmp_path):
    p = source(tmp_path)
    catalog = tmp_path / 'formats.sqlite'
    result = format_catalog(catalog_path=catalog)
    assert any(row['module_id'] == 'dinopark-act-sequence' for row in result['modules'])
    report = identify_file(p, catalog_path=catalog)['identification']
    roles = {row['module_id']: row['decoder_role'] for row in report['decoder_modules']}
    assert roles['dinopark-act'] == 'pixel-reader'
    assert roles['dinopark-act-sequence'] == 'animation-reader'


def test_sequence_cli_and_json_are_project_free(tmp_path, capsys):
    p = source(tmp_path)
    assert main(['media-inspect', str(p), '--adapter', 'dinopark-act-sequence']) == 0
    assert json.loads(capsys.readouterr().out)['result']['program_count'] == 1
    assert main(['dinopark-animate', str(p), '--tick', '0', '--tick', '1', '--program', '0']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] and result['result']['ticks'][1]['draws'] == [[0, 3, 7, 9, 0]]
    reply = respond({'method': 'dinopark-animate', 'params': dict(path=str(p), ticks=[0, 1])},
                    default_project='/nonexistent.fdb')
    assert reply['ok'] and not reply['result']['input_executed']


def abt_source(tmp_path):
    p = tmp_path/'authored.ABT'
    p.write_bytes(struct.pack('<HHB',4,7000,8)+b'xyz'+bytes((128,0x42,0x81)))
    return p


def test_explicit_native_consumer_profile_preserves_requested_and_device_rates(tmp_path):
    p=abt_source(tmp_path)
    report=inspect_dinopark(p,adapter='dinopark-abt-playback')
    assert report['requested']['rate_hz']==7000
    assert report['device']['effective_rate_hz']==dict(numerator=500000,denominator=71)
    output=tmp_path/'new-audio'
    result=decode_media(p,output,adapter='dinopark-abt',playback_profile=PLAYBACK_PROFILE)
    with wave.open(str(output/'samples.wav'),'rb') as f:
        assert (f.getframerate(),f.getnchannels())==(7000,1)
        assert f.readframes(4)==bytes((128,128,128,2))
    assert result['selection']['timing_source']=='explicit-recovered-consumer-profile'
    assert not result['selection']['consumer_playback']['current_input_native_playback_tested']
    assert result['selection']['consumer_playback']['device']==report['device']


@pytest.mark.parametrize('extra', [dict(sample_rate=7000),dict(channels=1),dict(sample_rate=7000,channels=1)])
def test_native_profile_cannot_silently_override_explicit_wav_adapter(tmp_path,extra):
    with pytest.raises(ValueError,match='cannot be combined'):
        decode_media(abt_source(tmp_path),tmp_path/'new-audio',adapter='dinopark-abt',
                     playback_profile=PLAYBACK_PROFILE,**extra)
    assert not (tmp_path/'new-audio').exists()
