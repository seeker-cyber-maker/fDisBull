"""Explicit original-DOS launch arguments and read-only D: CD media configuration.

No shell command passthrough, auto-detected extender, input patch or implicit
resource search. The existing debugger still owns its private process and C:.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import re
import stat

MAX_CD_BYTES = 2 * 1024 * 1024 * 1024


def _file_identity(path):
    path = Path(path).expanduser()
    if path.is_symlink():
        raise ValueError('CD inputs must not be symlinks')
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_CD_BYTES:
            raise ValueError('CD input must be a regular file of 1 byte..2 GiB')
        digest = sha256()
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
            if source.tell() > MAX_CD_BYTES:
                raise ValueError('CD input grew beyond its budget')
        after = os.fstat(source.fileno())
    def key(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if key(before) != key(after) or key(after) != key(path.stat()):
        raise ValueError('CD input changed during hashing')
    return {'path': str(path.resolve()), 'size': after.st_size, 'sha256': digest.hexdigest()}


def prepare_launch_options(arguments=None, cd_image=None):
    """Validate before spawning. Arguments are bounded, unquoted ASCII tokens.

    This intentionally refuses shell syntax and tokens containing whitespace.
    The DOS backend joins tokens into a command tail; arbitrary argv quoting is
    not a defined DOS API. More elaborate batch/environment setup is separate.
    """
    explicit = arguments is not None or cd_image is not None
    if arguments is None:
        arguments = []
    if (not isinstance(arguments, list) or len(arguments) > 32 or any(
            not isinstance(a, str) or re.fullmatch(r'[A-Za-z0-9_./:+,=@\\-]+', a) is None
            for a in arguments) or len(' '.join(arguments)) > 125):
        raise ValueError('DOS arguments require at most 32 unquoted ASCII tokens and a 125-byte joined tail')
    result = {'format': 'fdisbull-dos-launch-profile-1', 'explicit': explicit,
              'arguments': list(arguments), 'cd': None}
    if cd_image is None:
        return result
    path = Path(cd_image).expanduser()
    if path.is_symlink():
        raise ValueError('CD descriptor must not be a symlink')
    path = path.resolve(strict=True)
    # DOSBox parses this string, not a host shell. Do not admit its expansion or
    # separator characters, even though subprocess itself uses an argument list.
    if any(ord(c) < 32 or ord(c) > 126 or c in '"%&|<>^\\' for c in str(path)):
        raise ValueError('CD path contains unsupported DOSBox command characters')
    identities = [_file_identity(path)]
    if path.suffix.lower() in ('.cue', '.ins'):
        from .cue import inspect_cue_path
        layout = inspect_cue_path(path)
        if not layout['valid'] or not layout['complete']:
            raise ValueError('Invalid or unsupported CUE/INS layout: ' + '; '.join(layout.get('errors', [])))
        if not any(t['mode'].startswith('MODE1/') for t in layout['tracks']):
            raise ValueError('CD launch requires a supported data track')
        for name in sorted({t['file'] for t in layout['tracks']}):
            candidate = path.parent / name
            # Reject links in every reference component, not only final target.
            if any(p.is_symlink() for p in [candidate, *candidate.parents]):
                raise ValueError('CUE references must not traverse symlinks')
            if sum(item['size'] for item in identities) + candidate.stat().st_size > MAX_CD_BYTES:
                raise ValueError('Combined CD inputs exceed 2 GiB')
            identities.append(_file_identity(candidate))
        if identities[0]['sha256'] != layout['cue_sha256']:
            raise ValueError('CUE changed during validation')
    elif path.suffix.lower() == '.iso':
        from .disc import inspect_disc_path
        layout = inspect_disc_path(path, mode='MODE1/2048', max_entries=1000)
        if not layout['primary_metadata_valid'] or not layout['valid']:
            raise ValueError('ISO primary metadata did not validate')
    else:
        raise ValueError('CD launch accepts a validated .cue/.ins descriptor or cooked .iso')
    if sum(item['size'] for item in identities) > MAX_CD_BYTES:
        raise ValueError('Combined CD inputs exceed 2 GiB')
    result['cd'] = {'drive': 'D', 'type': 'iso', 'read_only_media': True,
                    'inputs': identities, 'startup_command': f'imgmount D "{path}" -t iso',
                    'mount_observed': False}
    return result


def bind_start(params, profile):
    """Copy a session-start request, bind command-tail intent, recheck media."""
    if not isinstance(params, dict) or not isinstance(params.get('target'), dict):
        raise ValueError('Expected an explicit DOS session target')
    requested = params['target'].get('arguments', [])
    if requested not in ([], profile['arguments']):
        raise ValueError('Conflicting DOS launch arguments')
    if profile['cd'] is not None:
        for expected in profile['cd']['inputs']:
            if _file_identity(expected['path']) != expected:
                raise ValueError('CD inputs changed before session start')
    result = deepcopy(params)
    result['target']['arguments'] = list(profile['arguments'])
    return result


def open_dos_session(project, executable, game_dir, *, arguments=None, cd_image=None,
                     version=None, window=False, spatial_mode=None, fair_play=False):
    """Use the existing native debugger with an explicit recorded launch profile."""
    from .debugger import DebugSession
    from .dosbox_rpc import DOSBoxRPC

    class ConfiguredDOSSession(DebugSession):
        def _open_rpc(self, executable, game_dir):
            return DOSBoxRPC(executable, game_dir, window=self.window,
                             on_spawn=self._spawn_callback, launch_arguments=arguments, cd_image=cd_image)

        def _transport_metadata(self):
            return {'launch_profile': deepcopy(self.rpc.launch_profile)}

    # Admission before DebugSession can create an alias or start the process.
    prepare_launch_options(arguments, cd_image)
    return ConfiguredDOSSession(project, executable, game_dir, version=version,
                                window=window, spatial_mode=spatial_mode, fair_play=fair_play)
