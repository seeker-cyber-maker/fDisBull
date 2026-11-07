"""Bounded CUE/BINARY track layout inspection; no image contents are interpreted."""

from pathlib import Path, PureWindowsPath
import hashlib
import os
import re
import shlex
import stat

_MAX_TEXT = 1024 * 1024
_MODES = {"AUDIO": 2352, "MODE1/2352": 2352, "MODE1/2048": 2048}
_METADATA = {"REM", "TITLE", "PERFORMER", "SONGWRITER", "CATALOG", "ISRC", "CDTEXTFILE"}


def _error(message):
    return {"valid": False, "complete": False, "warnings": [], "errors": [message], "tracks": []}


def _frames(value):
    match = re.fullmatch(r"(\d{2,}):(\d{2}):(\d{2})", value)
    if not match:
        raise ValueError("invalid MSF timestamp")
    minute, second, frame = map(int, match.groups())
    if second >= 60 or frame >= 75:
        raise ValueError("invalid MSF timestamp")
    return (minute * 60 + second) * 75 + frame


def _safe_reference(name):
    windows = PureWindowsPath(name)
    if (not name or '\x00' in name or windows.is_absolute() or windows.drive
            or name.startswith(('/', '\\')) or any(part in ('..', '') for part in name.replace('\\', '/').split('/'))):
        raise ValueError("unsafe file reference")
    return name.replace('\\', '/')


def parse_cue(text: str) -> dict:
    """Parse a supported CUE subset, returning a fail-closed result on error."""
    if not isinstance(text, str):
        return _error("CUE text must be a string")
    try:
        if len(text.encode('utf-8')) > _MAX_TEXT:
            raise ValueError("CUE text exceeds 1 MiB")
        tracks, warnings = [], []
        current_file = None
        track = None
        files_used = set()
        for lineno, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith(';') or line.startswith('//'):
                continue
            # Backslashes are ambiguous between CUE paths and shell-style escapes.
            if line.upper().startswith('FILE ') and '\\' in line:
                raise ValueError("unsafe file reference")
            tokens = shlex.split(line, posix=True)
            if not tokens:
                continue
            command = tokens[0].upper()
            if command in _METADATA:
                warnings.append(f"line {lineno}: metadata {command} ignored")
                continue
            if command == 'FILE':
                if len(tokens) != 3 or tokens[2].upper() != 'BINARY':
                    raise ValueError("only BINARY FILE is supported")
                current_file = _safe_reference(tokens[1])
                # Reopening a file later makes boundaries ambiguous.
                if current_file in files_used:
                    raise ValueError("repeated FILE declaration")
                files_used.add(current_file)
                track = None
            elif command == 'TRACK':
                if len(tokens) != 3 or current_file is None or not re.fullmatch(r'[0-9]{1,2}', tokens[1]):
                    raise ValueError("invalid TRACK")
                number = int(tokens[1])
                mode = tokens[2].upper()
                if not 1 <= number <= 99 or (tracks and number <= tracks[-1]['number']) or mode not in _MODES:
                    raise ValueError("unsupported or out-of-order TRACK")
                if len(tracks) >= 99:
                    raise ValueError("too many tracks")
                track = {"number": number, "mode": mode, "file": current_file, "sector_size": _MODES[mode], "indices": {}, "pregap_sectors": 0, "postgap_sectors": 0}
                tracks.append(track)
            elif command == 'INDEX':
                if track is None or len(tokens) != 3 or tokens[1] not in ('0', '1', '00', '01'):
                    raise ValueError("unsupported or invalid INDEX")
                index = f'{int(tokens[1]):02d}'
                if index in track['indices'] or (index == '00' and '01' in track['indices']) or track.get('_postgap'):
                    raise ValueError("duplicate or out-of-order INDEX")
                track['indices'][index] = _frames(tokens[2])
            elif command in ('PREGAP', 'POSTGAP'):
                if track is None or len(tokens) != 2:
                    raise ValueError("invalid gap")
                marker = '_' + command.lower()
                if track.get(marker) or (command == 'PREGAP' and track['indices']) or (command == 'POSTGAP' and '01' not in track['indices']):
                    raise ValueError("duplicate or out-of-order gap")
                track[marker] = True
                track[command.lower() + '_sectors'] = _frames(tokens[1])
            else:
                raise ValueError(f"unsupported directive {command}")
        if not tracks:
            raise ValueError("no tracks")
        if len({t['file'] for t in tracks}) != len(files_used):
            raise ValueError("FILE without TRACK")
        for track in tracks:
            indices = track['indices']
            if '01' not in indices or ('00' in indices and indices['00'] > indices['01']):
                raise ValueError("missing or invalid INDEX 01")
            track.pop('_pregap', None)
            track.pop('_postgap', None)
        return {"valid": True, "complete": False, "warnings": warnings, "errors": [], "tracks": tracks}
    except (ValueError, UnicodeError) as exc:
        return _error(str(exc))


def _identity(info):
    return {"dev": info.st_dev, "ino": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def inspect_cue_path(path) -> dict:
    """Resolve track files within the CUE directory and calculate half-open ranges."""
    try:
        cue = Path(path)
        if not stat.S_ISREG(cue.stat().st_mode):
            raise ValueError("CUE must be a regular file")
        with cue.open('rb') as source:
            before = _identity(os.fstat(source.fileno()))
            data = source.read(_MAX_TEXT + 1)
            after = _identity(os.fstat(source.fileno()))
        if before != after or before != _identity(cue.stat()):
            raise ValueError("CUE changed during read")
        if len(data) > _MAX_TEXT:
            raise ValueError("CUE text exceeds 1 MiB")
        result = parse_cue(data.decode('utf-8-sig'))
        if not result['valid']:
            return result
        result['cue_sha256'] = hashlib.sha256(data).hexdigest()
        result['cue_identity'] = before
        root = cue.resolve().parent
        tracks = result['tracks']
        infos = {}
        identities = set()
        for track in tracks:
            name = track['file']
            if name not in infos:
                resolved = (root / name).resolve(strict=True)
                if not resolved.is_relative_to(root) or not stat.S_ISREG(resolved.stat().st_mode):
                    raise ValueError("track file must be a regular file inside the CUE directory")
                info = resolved.stat()
                identity = (info.st_dev, info.st_ino)
                if identity in identities:
                    raise ValueError("multiple FILE references resolve to the same file")
                identities.add(identity)
                infos[name] = (resolved, info.st_size, track['sector_size'], _identity(info))
            resolved, size, sector_size, identity = infos[name]
            if sector_size != track['sector_size']:
                raise ValueError("shared file has differing sector sizes")
            if size % sector_size:
                raise ValueError("track file size is not sector aligned")
            track.update(file_path=str(resolved), file_size=size, file_sector_count=size // sector_size, file_identity=identity)
        lba = 0
        for i, track in enumerate(tracks):
            idx = track['indices']
            start = idx.get('00', idx['01'])
            if (i == 0 or tracks[i - 1]['file'] != track['file']) and start != 0:
                raise ValueError("unassigned prefix before first track in file")
            end = track['file_sector_count']
            if i + 1 < len(tracks) and tracks[i + 1]['file'] == track['file']:
                nxt = tracks[i + 1]['indices']
                end = nxt.get('00', nxt['01'])
            if not 0 <= start <= idx['01'] < end <= track['file_sector_count']:
                raise ValueError("track indices outside file or overlap")
            stored = end - start
            stored_pregap = idx['01'] - start
            lba += track['pregap_sectors']
            track.update(file_start_sector=start, file_index01_sector=idx['01'], file_end_sector=end,
                         stored_pregap_sectors=stored_pregap, stored_sectors=stored,
                         program_sectors=end - idx['01'], disc_start_lba=lba,
                         disc_index01_lba=lba + stored_pregap, disc_end_lba=lba + stored)
            lba += stored + track['postgap_sectors']
        result['complete'] = True
        return result
    except (OSError, ValueError, UnicodeError) as exc:
        return _error(str(exc))
