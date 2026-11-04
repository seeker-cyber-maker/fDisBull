"""Shipped, non-executing media adapters; reports never contain source bytes."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

MAX_SOURCE = 64 * 1024 * 1024
MAX_OUTPUT = MAX_SOURCE
SPEC = 'references/media-modules.md'


def media_modules():
    """Discover implemented entry points, dependencies and explicit limits."""
    return {
        'format': 'fdisbull-media-modules-1', 'specification': SPEC,
        'modules': [
            dict(name='smacker', layer='asset-framing',
                 api='fdisbull.smacker.inspect_smk / frame_smk',
                 methods=['media-inspect', 'smk-frame'],
                 dependencies=['ffmpeg on PATH and ffprobe on PATH for framing'],
                 variants='Bounded non-ring, unscaled SMK2 with block-aligned dimensions',
                 limits='64 MiB source/output; native FULL/SKIP framing with exact retained images/palettes and complete original audio; independent decode is separate from original-game playback'),
            dict(name='avi-capture', layer='recorded-observation',
                 api='fdisbull.capture_audit.audit_capture', methods=['capture-audit'],
                 dependencies=['ffmpeg on PATH', 'ffprobe on PATH'],
                 variants='Finalized AVI segments with one video stream and fixed decoded dimensions',
                 limits='Full-frame RGBA hashes before sampling; bounded input/metadata/output and host time; no guest-clock mapping, input replay or game-success claim',
                 specification='docs/TAS_CAPTURE_AUDIT.md'),
            dict(name='mz-envelope', layer='executable-container',
                 api='fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='Classic MZ accepted by dos.load_mz at segment 0x10',
                 limits='64 MiB source; 1 MiB real-mode allocation; opaque tail only; no decompression or overlay directory recovery'),
            dict(name='agi-v2', layer='resource-container',
                 api='fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='AGI v2 three-byte directory, five-byte uncompressed VOL.N header',
                 limits='768-byte directory; resource 0..255; 64 MiB volume; no AGI v3/LZW'),
            dict(name='gog-inno', layer='archive',
                 api='fdisbull.gog_unpack.list_gog / unpack_gog',
                 methods=['gog-list', 'gog-unpack'], dependencies=['native innoextract on PATH'],
                 variants='GOG Inno Setup variants accepted by installed innoextract',
                 limits='External reader version and timeout recorded; no general archive/disk reader or hard decompression-size budget'),
            dict(name='agi-picture', layer='asset-decoding',
                 api='fdisbull.agi_picture.decode_picture', methods=[], dependencies=[],
                 variants='Prepared AGI 2.915/2.917 EGA picture stream',
                 limits='2 MiB payload; fixed 160x168 planes; 20 million work units; not runtime walkability'),
        ],
        'input_executed': False,
        'extension': 'Add bounded adapter, authored tests, indexed specification and catalog entry; no dynamic plugins are loaded',
    }


def _snapshot(path, limit):
    """Read a regular file through a bounded descriptor, never a pipe/device."""
    source = Path(path).expanduser()
    if source.is_symlink():
        raise ValueError('Source file must not be a symlink')
    fd = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Source must be a regular file within its size limit')
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(data) > limit or (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('Source changed or exceeded its size limit')
    return data


def _identity(data):
    return dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())


def _prepare(path, adapter, volume_root, number):
    if not isinstance(adapter, str) or adapter not in ('mz-envelope', 'agi-v2'):
        raise ValueError('Unsupported adapter; discover media-modules first')
    inputs = []
    if adapter == 'mz-envelope':
        if volume_root is not None or number is not None:
            raise ValueError('MZ envelope does not accept AGI resource parameters')
        from .dos import load_mz
        data = _snapshot(path, MAX_SOURCE)
        # Reuse the canonical validator. These are original file ranges, not
        # relocated memory bytes and not a new executable loader.
        dos = load_mz(data, load_segment=0x10).metadata['dos']
        header, end = dos['header_size'], dos['declared_file_size']
        members = [('header', 0, data[:header]), ('module', header, data[header:end])]
        if end < len(data):
            members.append(('tail', end, data[end:]))
        inputs.append(dict(role='container', **_identity(data)))
        unknowns = ['Tail structure and compression are unknown; no overlay entries, addresses or semantics inferred.']
    else:
        if volume_root is None or type(number) is not int or not 0 <= number < 256:
            raise ValueError('AGI v2 requires volume_root and resource number 0..255')
        from .agi_picture import extract_v2_resource
        directory_path = Path(path).expanduser()
        directory = _snapshot(directory_path, 768)
        if len(directory) % 3 or number * 3 + 3 > len(directory):
            raise ValueError('Missing or malformed directory entry')
        entry = directory[number * 3:number * 3 + 3]
        if entry == b'\xff\xff\xff':
            raise ValueError('Resource is absent')
        volume = entry[0] >> 4
        root = Path(volume_root).expanduser()
        candidates = [p for p in root.iterdir() if p.name.casefold() == f'vol.{volume}']
        if len(candidates) != 1:
            raise ValueError('Missing or ambiguous volume')
        volume_bytes = _snapshot(candidates[0], MAX_SOURCE)
        recovered = extract_v2_resource(directory_path, root, number)
        offset = recovered['offset'] + 5
        payload = recovered['payload']
        if (directory != _snapshot(directory_path, 768)
                or volume_bytes != _snapshot(candidates[0], MAX_SOURCE)
                or volume_bytes[offset:offset + len(payload)] != payload):
            raise ValueError('Resource inputs changed during extraction')
        inputs.extend([dict(role='directory', **_identity(directory)),
                       dict(role=f'volume-{volume}', **_identity(volume_bytes))])
        members = [('resource', offset, payload)]
        unknowns = ['Resource type and interpreter semantics require separate qualification.']
    result = dict(format='fdisbull-media-members-1', adapter=adapter, adapter_version=1,
                  inputs=inputs, members=[dict(name=name, input_role=inputs[-1]['role'],
                      offset=offset, **_identity(payload)) for name, offset, payload in members],
                  input_executed=False, qualification='structural-only', unknowns=unknowns,
                  specification=SPEC)
    if adapter == 'agi-v2':
        result['resource_number'] = number
    return result, {name: payload for name, _, payload in members}


def inspect_media(path, *, adapter, volume_root=None, number=None):
    """Inventory immutable member ranges with source and member digests."""
    if adapter == 'smacker':
        if volume_root is not None or number is not None:
            raise ValueError('Smacker does not accept AGI resource parameters')
        from .smacker import inspect_smk
        return inspect_smk(path)
    result, _ = _prepare(path, adapter, volume_root, number)
    return result


def extract_media(path, output, *, adapter, member, volume_root=None, number=None,
                  max_output_bytes=MAX_OUTPUT):
    """Copy one bounded member to a fresh private directory outside Git."""
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT:
        raise ValueError('max_output_bytes must be 1..67108864')
    result, payloads = _prepare(path, adapter, volume_root, number)
    if not isinstance(member, str) or member not in payloads:
        raise ValueError('Unknown member; inspect this source first')
    payload = payloads[member]
    if len(payload) > max_output_bytes:
        raise ValueError('Member exceeds output budget')
    from .output_artifacts import _private_directory
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if not destination.parent.is_dir():
        raise ValueError('Output parent must already exist and be private')
    # Reuse the tool's ownership, symlink and Git/worktree boundary checks.
    _private_directory(destination.parent)
    destination.mkdir(mode=0o700)  # Exclusive; existing paths and links refused.
    try:
        _private_directory(destination)
        with (destination / 'payload.bin').open('xb') as stream:
            os.chmod(stream.fileno(), 0o600)
            stream.write(payload)
        selected = next(item for item in result['members'] if item['name'] == member)
        result.update(output=str(destination), extracted=dict(selected, path='payload.bin'),
                      manifest='media-manifest.json')
        with (destination / 'media-manifest.json').open('x', encoding='utf-8') as stream:
            os.chmod(stream.fileno(), 0o600)
            json.dump(result, stream, indent=2, ensure_ascii=True)
            stream.write('\n')
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise
