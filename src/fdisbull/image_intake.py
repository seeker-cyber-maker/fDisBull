"""Image-aware routing over existing CUE, sector and ISO readers; never mounts."""
from __future__ import annotations
import hashlib
import re
from pathlib import Path
from .archive_layers import safe_name
from .cue import inspect_cue_path
from .disc import _single_track
from .disc_sectors import DataTrackReader
from .iso9660 import inspect_iso


def file_identity(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError('input must be a regular nonsymlink file')
    return DataTrackReader._identity(path.stat())


def hash_file(path: Path) -> str:
    before = file_identity(path)
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''):
            h.update(b)
    if before != file_identity(path):
        raise ValueError('source changed during hash')
    return h.hexdigest()


def disc_plan(path, *, track_number=None, max_entries=10000) -> dict:
    """Follow one matching CUE/INS, retaining other tracks as explicit omissions."""
    path = Path(path).absolute()
    file_identity(path)
    descriptor = None
    if path.suffix.lower() in ('.cue', '.ins'):
        descriptor = path
    elif path.suffix.lower() in ('.gog', '.bin'):
        matches = []
        for candidate in path.parent.iterdir():
            if candidate.stem.casefold() != path.stem.casefold() or candidate.suffix.lower() not in ('.cue', '.ins'):
                continue
            layout = inspect_cue_path(candidate)
            if not layout['valid'] or not layout['complete']:
                raise ValueError('matching disc descriptor is invalid: '+str(layout.get('errors')))
            if any(Path(t['file_path']) == path.resolve() for t in layout['tracks']):
                matches.append(candidate)
        if len(matches) > 1:
            raise ValueError('ambiguous companion descriptors; select CUE/INS explicitly')
        if matches:
            descriptor = matches[0]
    if descriptor is not None:
        file_identity(descriptor)
        layout = inspect_cue_path(descriptor)
        if not layout['valid'] or not layout['complete']:
            raise ValueError('unsupported/invalid CUE layout: '+str(layout.get('errors')))
        tracks = layout['tracks']
    else:
        tracks = [_single_track(path, None)]
    data_tracks = [t for t in tracks if t['mode'] != 'AUDIO']
    if track_number is None:
        if len(data_tracks) != 1:
            raise ValueError('select an explicit data track when zero/multiple are present')
        selected = data_tracks[0]
    else:
        if type(track_number) is not int:
            raise ValueError('track number must be integer')
        hits = [t for t in data_tracks if t['number'] == track_number]
        if len(hits) != 1:
            raise ValueError('selected track is not supported data')
        selected = hits[0]
    with DataTrackReader(selected['file_path'], mode=selected['mode'],
                         start_sector=selected['file_index01_sector'],
                         sector_count=selected['program_sectors'],
                         expected_identity=selected['file_identity']) as reader:
        fs = inspect_iso(reader.read_sector, reader.sector_count, max_entries=max_entries)
    if not fs['valid'] or not fs['complete'] or not fs['volume_extent_fits']:
        raise ValueError('ISO primary tree incomplete or unsupported: '+str(fs.get('warnings')))
    names = set()
    for entry in fs['entries']:
        if not entry['available']:
            raise ValueError('unavailable ISO extent')
        name = safe_name('/'.join(re.sub(r';[0-9]+$', '', p) for p in entry['path'].lstrip('/').split('/')))
        if name.casefold() in names:
            raise ValueError('case-colliding ISO destinations')
        names.add(name.casefold())
        entry['output_name'] = name
    sources = []
    for p in dict.fromkeys([str(descriptor)] if descriptor else []):
        sources.append(dict(path=p, identity=file_identity(Path(p)), sha256=hash_file(Path(p))))
    for p in dict.fromkeys(t['file_path'] for t in tracks):
        sources.append(dict(path=p, identity=file_identity(Path(p)), sha256=hash_file(Path(p))))
    return dict(format='disc-filesystem', selected_track=selected, tracks=tracks,
                descriptor=str(descriptor) if descriptor else None, sources=sources,
                filesystem=fs, omissions=[dict(track=t['number'], mode=t['mode'],
                    program_sectors=t['program_sectors']) for t in tracks if t is not selected],
                preservation_equivalent=False, edc_ecc_verified=False,
                scope='primary ISO filesystem extraction; original tracks and descriptors remain authoritative')


def disc_payload(plan: dict, entry: dict, *, limit: int) -> bytes:
    if type(limit) is not int or not 0 <= entry['size'] <= limit <= 64*1024*1024:
        raise ValueError('disc member exceeds 64 MiB bounded API')
    if entry.get('kind') == 'directory':
        raise ValueError('directory is not a payload')
    t = plan['selected_track']
    with DataTrackReader(t['file_path'], mode=t['mode'],
                         start_sector=t['file_index01_sector'], sector_count=t['program_sectors'],
                         max_read_bytes=64*1024*1024, max_reads=32768,
                         expected_identity=t['file_identity']) as reader:
        chunks = [reader.read_sector(entry['extent_lba']+i)
                  for i in range((entry['size']+2047)//2048)]
    return b''.join(chunks)[:entry['size']]
