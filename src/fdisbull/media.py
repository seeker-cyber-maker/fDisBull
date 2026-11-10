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
    from .mads_media_adapters import catalog
    return {
        'format': 'fdisbull-media-modules-1', 'specification': SPEC,
        'modules': catalog() + [
            dict(name='flic', layer='container-inspection',
                 api='fdisbull.flic.inspect_flic', methods=['media-inspect'], dependencies=[],
                 variants='Standard FLI/FLC, Bullfrog compact12 and bounded TFTD VID/IDX',
                 limits='64 MiB source; complete bounded packet/chunk extent census and explicit ring/prefix/codec gaps; no pixel/audio decoding, framing or native compatibility'),
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
                 methods=['gog-list', 'gog-unpack'], dependencies=[],
                 variants='Inno Setup 5.6.2 Unicode GOG installers with the supported loader, header and data profile',
                 limits='Native bounded reader; unsupported versions, external slices, encryption and checksum failures are refused; no installer execution, general archive/disk reader or runtime-equivalence claim'),
            dict(name='gog-galaxy-upx', layer='captured-executable-reconstruction',
                 api='fdisbull.gog_galaxy.rebuild_galaxy_capture / rebuild_galaxy_files',
                 methods=['python-module:gog_galaxy_cli'], dependencies=[],
                 variants='Caller-captured PE32/PE32+ mapped image from a UPX0/UPX1 Galaxy wrapper',
                 limits='No download, launch, attachment, anti-debugging bypass or export enumeration; qualified capture/OEP/export inputs required; output is an unsigned analysis reconstruction'),
            dict(name='westwood-pak', layer='resource-container',
                 api='fdisbull.westwood_media.inspect_pak; fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='Westwood PAK v2/v3; validated offset/name directory and opaque tails',
                 limits='64 MiB input; bounded member count; duplicate names require index selector; no packer execution'),
            dict(name='castles2-bob', layer='asset-decoding',
                 api='fdisbull.castles2_bob.decode_bob; fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='Castles II CD RGB888 256-colour BOB bitmap; 8-bit indexed raster',
                 limits='4 MiB pixels, 4096 per dimension, exact 772-byte prefix; no alpha, timing, animation grouping or original-game parity'),
            dict(name='westwood-cps', layer='asset-decoding',
                 api='fdisbull.westwood_media.decode_cps; fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='DOS-PC CPS raw/Format3 RLE/Format4 LCW; palette optional',
                 limits='2 MiB input; 1 MiB decoded indices; unknown geometry except 320x200; no palette synthesis'),
            dict(name='westwood-wsa', layer='asset-decoding',
                 api='fdisbull.westwood_media.inspect_wsa / decode_wsa_frames; fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='Kyrandia early/early-flags and Lands late header; LCW+XOR Delta',
                 limits='64 MiB input; 2000 frames; bounded first-frame export only when not chained; no playback timing'),
            dict(name='westwood-emc2', layer='script-container',
                 api='fdisbull.westwood_media.parse_emc2; fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='IFF FORM/EMC2 ORDR/TEXT/DATA; no script execution',
                 limits='8 MiB input; declared entry offset validation; game-specific syscall semantics excluded'),
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


def _prepare(path, adapter, volume_root, number, **options):
    from .mads_media_adapters import NAMES, prepare
    if isinstance(adapter, str) and adapter in NAMES:
        if volume_root is not None:
            raise ValueError('Independent media adapters do not accept volume_root')
        return prepare(path, adapter, number=number, **options)
    if options:
        raise ValueError('Extra parameters apply only to independent media adapters')
    if not isinstance(adapter, str) or adapter not in ('mz-envelope', 'agi-v2',
          'westwood-pak', 'westwood-cps', 'westwood-wsa', 'westwood-emc2',
          'castles2-bob'):
        raise ValueError('Unsupported adapter; discover media-modules first')
    inputs = []
    metadata = {}
    if adapter == 'castles2-bob':
        if volume_root is not None or number is not None:
            raise ValueError('Castles II BOB is standalone and rejects volume arguments')
        from .castles2_bob import decode_bob, PIXEL_OFFSET
        data = _snapshot(path, min(MAX_SOURCE, PIXEL_OFFSET + 4 * 1024 * 1024))
        image = decode_bob(data)
        inputs.append(dict(role='container', **_identity(data)))
        members = [('palette-rgb', 4, data[4:PIXEL_OFFSET]),
                   ('indices', PIXEL_OFFSET, image.pixels),
                   ('preview-png', None, image.png())]
        metadata = dict(bob_dimensions={'width': image.width, 'height': image.height},
                        bob_palette_encoding='RGB888', bob_palette_entries=256,
                        bob_pixel_encoding='indexed8', bob_pixel_offset=PIXEL_OFFSET)
        unknowns = ['One static BOB bitmap, not an independently verified animation timeline.',
                    'No color-key transparency inferred, including for magenta palette entries.',
                    'PNG is a lossless decoded visualization; original game rendering/compositing is unverified.']
    elif adapter == 'mz-envelope':
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
    elif adapter.startswith('westwood-'):
        if volume_root is not None or number is not None:
            raise ValueError('Westwood adapter does not accept AGI volume parameters')
        from .westwood_media import (inspect_pak, decode_cps, encode_cps_png,
                                     inspect_wsa, decode_wsa_frames, parse_emc2)
        limit = 64 * 1024 * 1024 if adapter not in ('westwood-cps', 'westwood-emc2') else (
            2 * 1024 * 1024 if adapter == 'westwood-cps' else 8 * 1024 * 1024)
        data = _snapshot(path, limit)
        inputs.append(dict(role='container', **_identity(data)))
        if adapter == 'westwood-pak':
            report = inspect_pak(data)
            members = []
            for item in report['members']:
                selector = (f"#{item['index']}:{item['name']}" if item['duplicate_name']
                            else item['name'])
                members.append((selector, item['offset'],
                                data[item['offset']:item['offset'] + item['size']]))
            metadata = dict(pak_layout=report['format'],
                            pak_opaque_tail_bytes=report['opaque_tail_bytes'])
            unknowns = ['Member bytes are intact; nested compression, game roles, and hidden tail are separate.']
        elif adapter == 'westwood-cps':
            image = decode_cps(data)
            members = [('indices', None, image.pixels)]
            if image.palette is not None:
                members.append(('palette6', 10, image.palette))
                if image.width == 320 and image.height == 200:
                    members.append(('preview-png', None, encode_cps_png(image)))
            metadata = dict(cps_compression=image.compression, cps_decoded_size=image.declared_size,
                            cps_dimensions=(dict(width=image.width, height=image.height)
                                            if image.width is not None else None),
                            cps_palette_bytes=(len(image.palette) if image.palette else 0))
            unknowns = ['Derived indexed pixels are not an original byte range.',
                        'If palette is absent, color rendering requires separately identified original palette.']
        elif adapter == 'westwood-wsa':
            report = inspect_wsa(data)
            metadata = {('wsa_' + key): value for key, value in report.items()
                        if key not in ('format', 'offsets', 'size', 'sha256', 'input_executed')}
            members = []
            if not report['missing_first_frame']:
                _, frames = decode_wsa_frames(data, max_frames=1)
                members = [('frame0-indices', None, frames[0])]
            unknowns = ['WSA frame state is delta-dependent; only an independently initialized first frame is exported.',
                        'Frame timing, palette state, composite positioning and chained animations are not established.']
        else:
            script = parse_emc2(data)
            members = [(tag, part['offset'], data[part['offset']:part['offset'] + part['size']])
                       for tag, part in script['chunks'].items()]
            metadata = dict(emc2_valid_entries=script['valid_entry_count'],
                            emc2_entry_slots=len(script['entry_slots']),
                            emc2_data_words=script['word_count'])
            unknowns = ['Script payload is interpreted code, not native machine instructions.',
                        'Entry policy and syscall binding must be qualified separately per game.']
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
    result.update(metadata)
    return result, {name: payload for name, _, payload in members}


def inspect_media(path, *, adapter, volume_root=None, number=None, index_path=None, **options):
    """Inventory immutable member ranges with source and member digests."""
    from .mads_media_adapters import NAMES
    if isinstance(adapter, str) and adapter in NAMES:
        if index_path is not None:
            raise ValueError('Use map_path, not index_path, for a MADS tile map')
        return _prepare(path, adapter, volume_root, number, **options)[0]
    if options:
        raise ValueError('Extra parameters apply only to independent media adapters')
    if adapter == 'flic':
        if volume_root is not None or number is not None:
            raise ValueError('FLIC does not accept AGI resource parameters')
        from .flic import inspect_flic
        return inspect_flic(path, index_path=index_path)
    if index_path is not None:
        raise ValueError('index_path is only supported by the FLIC inspector')
    if adapter == 'smacker':
        if volume_root is not None or number is not None:
            raise ValueError('Smacker does not accept AGI resource parameters')
        from .smacker import inspect_smk
        return inspect_smk(path)
    result, _ = _prepare(path, adapter, volume_root, number)
    return result


def extract_media(path, output, *, adapter, member, volume_root=None, number=None,
                  max_output_bytes=MAX_OUTPUT, **options):
    """Copy one bounded member to a fresh private directory outside Git."""
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT:
        raise ValueError('max_output_bytes must be 1..67108864')
    result, payloads = _prepare(path, adapter, volume_root, number, **options)
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
