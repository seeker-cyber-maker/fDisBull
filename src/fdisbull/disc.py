"""CUE/Mode-1/ISO inspection; media is never executed or extracted."""
from __future__ import annotations

import os
from pathlib import Path

from .disc_sectors import DataTrackReader
from .iso9660 import inspect_iso
from .rom_disc import parse_sega_disc


def _single_track(path, mode):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError('disc input must be a regular file')
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        prefix = stream.read(16)
    if mode is None:
        mode = 'MODE1/2352' if prefix[:12] == b'\x00' + b'\xff' * 10 + b'\x00' else 'MODE1/2048'
    sector_size = {'MODE1/2352': 2352, 'MODE1/2048': 2048}.get(mode)
    if sector_size is None or not info.st_size or info.st_size % sector_size:
        raise ValueError('unsupported mode or non-sector-aligned disc file')
    count = info.st_size // sector_size
    return dict(number=1, mode=mode, file=path.name, file_path=str(path),
                file_identity=DataTrackReader._identity(info), file_size=info.st_size,
                sector_size=sector_size, file_start_sector=0, file_index01_sector=0,
                file_end_sector=count, stored_sectors=count, program_sectors=count,
                stored_pregap_sectors=0, pregap_sectors=0, postgap_sectors=0,
                disc_start_lba=0, disc_index01_lba=0, disc_end_lba=count)


def _comparison(track, tracks, filesystem):
    declared = filesystem.get('declared_sectors')
    if declared is None:
        return None
    audio = [t for t in tracks if t['mode'] == 'AUDIO']
    stored_audio = sum(t['stored_sectors'] for t in audio)
    timeline_end = max(t['disc_end_lba'] + t['postgap_sectors'] for t in tracks)
    difference = declared - track['program_sectors']
    return {'declared_volume_sectors': declared, 'data_track_program_sectors': track['program_sectors'],
            'declared_minus_data_track': difference, 'stored_audio_sectors': stored_audio,
            'stored_audio_pregap_sectors': sum(t['stored_pregap_sectors'] for t in audio),
            'audio_program_sectors': sum(t['program_sectors'] for t in audio),
            'generated_gap_sectors': sum(t['pregap_sectors'] + t['postgap_sectors'] for t in tracks),
            'cue_timeline_end_exclusive': timeline_end,
            'difference_equals_stored_audio': bool(audio) and difference == stored_audio,
            'declared_equals_cue_timeline_end': declared == timeline_end,
            'interpretation': 'Numerical accounting only; audio remains outside the filesystem data range and does not validate the declared volume semantics'}


def inspect_disc_path(path, *, mode=None, max_entries=10000,
                      max_directory_bytes=8 * 1024 * 1024, max_depth=32):
    """Inspect CUE tracks or one Mode-1 BIN/ISO and its primary ISO tree."""
    path = Path(path)
    report = {'report_format': 'fdisbull-disc-inspection-1', 'format': 'disc image',
              'valid': False, 'complete': False, 'loadable': False,
              'validation_scope': 'supported CUE layout and primary ISO metadata; file contents, EDC/ECC, audio and execution unverified',
              'warnings': [], 'data_tracks': []}
    if path.suffix.lower() in ('.cue', '.ins'):
        if mode is not None:
            raise ValueError('CUE declares track modes; mode override is not allowed')
        from .cue import inspect_cue_path
        layout = inspect_cue_path(path)
        report['cue'] = layout
        report['format'] = 'CUE/BIN disc'
        report['warnings'].extend(layout['warnings'])
        if not layout['valid'] or not layout['complete']:
            report['errors'] = layout.get('errors', [])
            return report
        tracks = layout['tracks']
    else:
        tracks = [_single_track(path, mode)]
        report['tracks'] = tracks
    for track in tracks:
        if track['mode'] == 'AUDIO':
            continue
        with DataTrackReader(track['file_path'], mode=track['mode'],
                             start_sector=track['file_index01_sector'],
                             sector_count=track['program_sectors'],
                             expected_identity=track['file_identity']) as reader:
            first = reader.read_sector(0)
            descriptor = parse_sega_disc(first, file_size=reader.sector_count * 2048)
            if descriptor is not None:
                descriptor['logical_header_offset'] = descriptor['header_offset']
                backing = reader.backing(0, descriptor['regions'][0]['file_size'])
                descriptor['physical_header_backing'] = backing
                descriptor['header_offset'] = backing['physical_sector_offset'] + backing['user_data_offset']
                descriptor['logical_regions'] = [
                    {'name': r['name'], 'kind': r['kind'], 'logical_offset': r['file_offset'], 'size': r['file_size']}
                    for r in descriptor.pop('regions')]
                descriptor['metadata'].update(sector_size=reader.sector_size,
                    sector_user_data_offset=reader.user_offset, framing=track['mode'],
                    track_origin='selected data-track program INDEX 01')
                descriptor['metadata']['source_mode'] = track['mode']
            filesystem = inspect_iso(reader.read_sector, reader.sector_count,
                                     max_entries=max_entries, max_directory_bytes=max_directory_bytes,
                                     max_depth=max_depth)
            for entry in filesystem['entries']:
                if entry['available']:
                    entry['backing'] = reader.backing(entry['extent_lba'], entry['size'])
            result = {'track_number': track['number'], 'mode': track['mode'],
                      'console_descriptor': descriptor, 'filesystem': filesystem,
                      'source': reader.provenance(), 'sector_accounting': _comparison(track, tracks, filesystem)}
        report['data_tracks'].append(result)
    if not report['data_tracks']:
        report['warnings'].append('No supported data track; audio metadata only')
        report['complete'] = True
        return report
    filesystems = [t['filesystem'] for t in report['data_tracks']]
    report['primary_metadata_valid'] = all(f['valid'] is True for f in filesystems)
    report['complete'] = all(f['complete'] for f in filesystems)
    report['valid'] = report['primary_metadata_valid'] and all(f['volume_extent_fits'] for f in filesystems)
    report['entry_extent_count'] = sum(len(f['entries']) for f in filesystems)
    report['all_entry_extents_available'] = report['complete'] and all(
        e['available'] for f in filesystems for e in f['entries'])
    return report
