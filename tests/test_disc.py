import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.disc import inspect_disc_path
from fdisbull.disc_sectors import DataTrackReader
from fdisbull.roms import inspect_rom_path
from test_iso9660 import image, both


def raw(blocks):
    return b''.join(b'\x00' + b'\xff' * 10 + b'\x00' + b'\x00\x02\x00\x01' + bytes(b) + bytes(288)
                    for b in blocks)


def test_cooked_iso_cli_and_nested_backings(tmp_path):
    path = tmp_path / 'test.iso'
    path.write_bytes(b''.join(image()))
    result = inspect_disc_path(path)
    assert result['valid'] and result['complete'] and result['all_entry_extents_available']
    fs = result['data_tracks'][0]['filesystem']
    assert fs['volume_id'] == 'TEST' and len(fs['entries']) == 3
    assert fs['content_verified'] is False
    one = next(x for x in fs['entries'] if x['path'] == '/ONE.BIN;1')
    assert one['backing']['physical_sector_offset'] == 25 * 2048
    assert one['backing']['contiguous']
    proc = subprocess.run([sys.executable, '-m', 'fdisbull', 'disc-inspect', str(path)],
                          capture_output=True, text=True, check=True,
                          env={**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1] / 'src')})
    cli = json.loads(proc.stdout)
    assert cli.get('result', cli)['complete']


def test_cue_audio_reconciles_count_without_extending_filesystem(tmp_path):
    blocks = image()
    blocks[0][:16] = b'SEGA SEGASATURN '
    blocks[17][80:88] = both(35, 4)
    (tmp_path / 'data.bin').write_bytes(raw(blocks))
    (tmp_path / 'audio.bin').write_bytes(bytes(5 * 2352))
    cue = tmp_path / 'disc.cue'
    cue.write_text('FILE "data.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 01 00:00:00\n'
                   'FILE "audio.bin" BINARY\n TRACK 02 AUDIO\n INDEX 00 00:00:00\n INDEX 01 00:00:02\n')
    result = inspect_disc_path(cue)
    assert not result['valid'] and result['complete'] and result['primary_metadata_valid']
    track = result['data_tracks'][0]
    assert track['filesystem']['available_sectors'] == 30
    assert result['all_entry_extents_available']
    accounting = track['sector_accounting']
    assert accounting['difference_equals_stored_audio']
    assert accounting['declared_equals_cue_timeline_end']
    assert accounting['stored_audio_pregap_sectors'] == 2
    assert accounting['audio_program_sectors'] == 3
    descriptor = track['console_descriptor']
    assert descriptor['header_offset'] == 16
    assert descriptor['metadata']['source_mode'] == 'MODE1/2352'
    entry = next(e for e in track['filesystem']['entries'] if e['path'] == '/ONE.BIN;1')
    assert entry['backing']['physical_sector_offset'] == 25 * 2352
    assert entry['backing']['user_data_offset'] == 16 and not entry['backing']['contiguous']
    assert inspect_rom_path(cue)['report_format'] == 'fdisbull-disc-inspection-1'


def test_data_index_offset_and_raw_framing_are_preserved(tmp_path):
    blocks = image()
    path = tmp_path / 'data.bin'
    path.write_bytes(bytes(2 * 2352) + raw(blocks))
    cue = tmp_path / 'disc.cue'
    cue.write_text('FILE "data.bin" BINARY\n TRACK 01 MODE1/2352\n INDEX 00 00:00:00\n INDEX 01 00:00:02\n')
    result = inspect_disc_path(cue)
    assert result['complete'] and result['valid']
    entry = result['data_tracks'][0]['filesystem']['entries'][0]
    assert entry['backing']['physical_sector_offset'] == (2 + 21) * 2352
    with path.open('r+b') as stream:
        stream.seek((2 + 17) * 2352 + 15)
        stream.write(b'\x02')
    result = inspect_disc_path(cue)
    assert not result['complete']
    assert result['data_tracks'][0]['filesystem']['valid'] is None


def test_sector_budgets_identity_and_replacement(tmp_path):
    path = tmp_path / 'data.bin'
    path.write_bytes(raw(image()))
    with DataTrackReader(path, mode='MODE1/2352', max_read_bytes=2352, max_reads=1) as reader:
        assert len(reader.read_sector(0)) == 2048
        with pytest.raises(ValueError, match='budget'):
            reader.read_sector(1)
        with pytest.raises(ValueError, match='outside'):
            reader.read_sector(30)
    with pytest.raises(ValueError, match='identity'):
        DataTrackReader(path, mode='MODE1/2352', expected_identity={})
    with pytest.raises(ValueError, match='changed'):
        with DataTrackReader(path, mode='MODE1/2352'):
            old = tmp_path / 'old.bin'
            path.rename(old)
            path.write_bytes(raw(image()))


def test_sega_cd_software_fields_have_covering_backing(tmp_path):
    blocks = image()
    blocks[0][:16] = b'SEGADISCSYSTEM  '
    blocks[0][0x120:0x125] = b'TITLE'
    path = tmp_path / 'cd.bin'
    path.write_bytes(raw(blocks))
    descriptor = inspect_disc_path(path)['data_tracks'][0]['console_descriptor']
    assert descriptor['metadata']['domestic_title'] == 'TITLE'
    assert descriptor['physical_header_backing']['logical_size'] == 512
    assert descriptor['physical_header_backing']['user_data_offset'] == 16
    assert descriptor['logical_regions'][0]['size'] == 512
