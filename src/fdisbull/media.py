"""Shipped non-executing media adapters; reports omit complete member payloads."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat

MAX_SOURCE = 64 * 1024 * 1024
MAX_OUTPUT = MAX_SOURCE
SPEC = 'references/media-modules.md'
KINT_SPEC = 'references/kint6-sherlock7.md'
PNG_ADAPTERS = ('sherlock7-images', 'kint6-user-buttons', 'kint6-user-overlays')
INSPECT_ADAPTERS = ('mz-envelope', 'agi-v2', 'kint6-ke') + PNG_ADAPTERS


def media_modules():
    """Discover implemented entry points, dependencies and explicit limits."""
    from .mads_media_adapters import catalog
    return {
        'format': 'fdisbull-media-modules-1', 'specification': SPEC,
        'modules': catalog() + [
            dict(name='doom-wad', layer='archive-and-media',
                 api='fdisbull.wad_media.inspect_wad_media / extract_wad_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='Bounded Doom IWAD/PWAD lumps with optional explicit base dependencies',
                 limits='64 MiB per source, 20000 lumps; raw ranges and bounded format decoding; no runtime rendering, actor behavior or native acceptance',
                 specification='docs/WAD_MEDIA.md'),
            dict(name='mve', layer='asset-framing',
                 api='fdisbull.mve.inspect_mve / frame_mve',
                 methods=['media-inspect', 'mve-frame'], dependencies=['ffmpeg on PATH for framing'],
                 capabilities=['bounded-opcode-inspection', 'native-video-framing', 'independent-video-audio-comparison'],
                 variants='Explicitly admitted Interplay MVE indexed-video profiles; old opcode 0x06 / 0x10 corpus',
                 limits='64 MiB source/output; bounded frames/decoded work; retain frame positions, control/audio packets and selected indexed images/palettes; unsupported layouts refuse; native playback is a separate gate'),
            dict(name='castles2-slb', layer='audio-container',
                 api='fdisbull.castles2_audio.decode_slb / inspect_slb',
                 methods=['media-inspect', 'media-decode'], dependencies=[],
                 capabilities=['bounded-slot-directory', 'exact-payload-partition', 'explicit-slot-selection'],
                 variants='Explicit Castles II context; footer and 12-byte hashed directory slots; no global signature',
                 limits='64 MiB source; 65536 slots; preserves repeated-key variants; timing and native randomized selection require separate profiles/context'),
            dict(name='castles2-slb-playback', layer='asset-playback-profile',
                 api='fdisbull.castles2_audio.bind_slb_playback',
                 methods=['media-inspect', 'media-decode'], dependencies=[],
                 capabilities=['explicit-consumer-profile', 'exact-device-rate-rational', 'integer-WAV-adapter'],
                 variants='Explicit original Castles II AIL/Sound Blaster unsigned-8 mono footer-selector 11/22 route',
                 limits='No literal kHz inference; exact DSP timing is separate from rounded WAV timing; no implicit duplicate-key/RNG selection or current-input native-playback claim'),
            dict(name='dinopark-abt-playback', layer='asset-playback-profile',
                 api='fdisbull.dinopark_playback.bind_abt_playback',
                 methods=['media-inspect', 'media-decode'], dependencies=[],
                 capabilities=['explicit-consumer-profile', 'requested-PCM-timing', 'exact-device-rate-rational'],
                 variants='Explicit original DinoPark DigPak / shipped SBPRO default unsigned-8 mono route',
                 limits='Decoded ABT required; exact pinned consumer/driver profile; requested WAV rate separate from quantized DSP timing; no dynamic stereo, other drivers or current-input native-playback claim'),
            dict(name='dinopark-act-sequence', layer='guest-animation',
                 api='fdisbull.dinopark_animation.inspect_animation / describe_animation / AnimationRuntime',
                 methods=['media-inspect', 'dinopark-animate'], dependencies=[],
                 capabilities=['sequence-token-decode', 'bounded-actor-interpreter', 'explicit-logical-ticks'],
                 variants='DinoPark ACT sequence reader and explicitly supported actor-runtime subset',
                 limits='Bounded instructions, actors and per-tick work; explicit time/signals/visibility; no assumed scheduling Hz, automatic game callbacks or whole-game animation recovery'),
            dict(name='dinopark-act', layer='asset-decoding',
                 api='fdisbull.dinopark_images.decode_act / describe_act',
                 methods=['media-inspect', 'media-decode'], dependencies=['Pillow for PNG export'],
                 capabilities=['sprite-index-decode', 'opacity-mask', 'opaque-sequence-inventory'],
                 variants='DinoPark UNC2 and legacy UNCS actor profiles',
                 limits='8 MiB source; bounded total pixels/work; exact indices and opacity; sequences opaque, external palette, no clipping or actor-playback semantics'),
            dict(name='dinopark-pic', layer='asset-decoding',
                 api='fdisbull.dinopark_images.decode_pic / describe_pic',
                 methods=['media-inspect', 'media-decode'], dependencies=['Pillow for PNG export'],
                 capabilities=['indexed-frame-decode', 'six-bit-palette', 'padded-row-decode'],
                 variants='DinoPark UNCP picture directory with raw narrow and compressed wider rows',
                 limits='8 MiB source; bounded frame/pixel/work budgets; preserve padded stride and raw six-bit palette; host RGB expansion and presentation remain explicit'),
            dict(name='dinopark-abt', layer='asset-decoding',
                 api='fdisbull.dinopark_audio.decode_abt / inspect_abt',
                 methods=['media-inspect', 'media-decode'], dependencies=[],
                 capabilities=['unsigned-sample-expansion', 'opaque-header-inventory'],
                 variants='Explicit consumer-qualified DinoPark ABT; no global magic',
                 limits='1 MiB source; 65535 output samples; 2 million work units; raw rate/opaque header preserved; WAV timing/channels require caller adapters'),
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
                 variants='Inno Setup 5.5.7 and 5.6.2 Unicode GOG installers with the supported loader, header and data profile',
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
            dict(name='kint6-ke', layer='executable-container',
                 api='fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=[],
                 variants='KINT 6 little-endian .KE with a 512-byte header and exact declared CODE size',
                 limits='64 MiB source; virtual ZERO/STACK/HEAP declarations only; no execution, allocation or inferred code/data split',
                 specification=KINT_SPEC),
            *[dict(name=name, layer='asset-decoding',
                   api='fdisbull.sherlock7_media.decode_png_atlas / fdisbull.media.inspect_media / extract_media',
                   methods=['media-inspect', 'media-extract'], dependencies=['Pillow'],
                   variants=variant,
                   limits='Explicit profile; 64 MiB input/output, 16 MiPixel decoded; raw RGBA crops with pixel provenance; no UI-sheet inference or renderer equivalence',
                   specification=KINT_SPEC)
              for name, variant in zip(PNG_ADAPTERS, (
                  'Sherlock 7 PNG: 8 by 10 cells, 64 tiles and documented control/overlay regions',
                  'KINT 6 user buttons: two 12 by 5 unit columns, 1..251 rows',
                  'KINT 6 user overlays: two 12 by 5 unit columns, 1..251 rows'))],
            dict(name='sherlock-shi', layer='asset-decoding',
                 api='fdisbull.shi.decode_shi / encode_shi; fdisbull.media.inspect_media / extract_media',
                 methods=['media-inspect', 'media-extract'], dependencies=['Pillow for PNG extraction'],
                 variants='Sherlock 1.50: 46 fixed 32x32 four-plane records',
                 limits='Exactly 23920 bytes; strict headers; indices 0..15; external game palette; mask/ink semantics retained; no other SHI profiles'),
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
          'westwood-pak', 'westwood-cps', 'westwood-wsa', 'westwood-emc2', 'castles2-bob', 'kint6-ke', 'sherlock-shi', *PNG_ADAPTERS):
        raise ValueError('Unsupported adapter; discover media-modules first')
    if adapter == 'kint6-ke' or adapter in PNG_ADAPTERS:
        if volume_root is not None or number is not None:
            raise ValueError('KINT/Sherlock adapters do not accept AGI resource parameters')
        return _prepare_kint(path, adapter)
    if adapter == 'sherlock-shi':
        if volume_root is not None or number is not None:
            raise ValueError('Sherlock SHI does not accept AGI resource parameters')
        from .shi import FILE_SIZE, HEADER, RECORD_SIZE, decode_shi, image_metadata, profile_metadata
        data = _snapshot(path, FILE_SIZE)
        images = decode_shi(data)
        members = []
        for image_id, pixels in enumerate(images):
            offset = image_id * RECORD_SIZE
            members.append(dict(name=f'image-{image_id:02d}', input_role='container',
                offset=offset, payload_offset=offset + len(HEADER),
                payload_size=RECORD_SIZE - len(HEADER),
                **_identity(data[offset:offset + RECORD_SIZE]),
                **image_metadata(image_id), pixels_sha256=_identity(pixels)['sha256']))
        result = dict(format='fdisbull-media-members-1', adapter=adapter, adapter_version=1,
                      inputs=[dict(role='container', **_identity(data))], members=members,
                      **profile_metadata(), input_executed=False, qualification='structural-only',
                      specification=SPEC,
                      unknowns=['Header words 4 and 1 are fixed profile markers; broader field semantics are unqualified.',
                                'Palette and record roles are external game-profile facts, not embedded SHI metadata.',
                                'Other SHI variants and whole-game behavior are not qualified.'])
        return result, {item['name']: images[item['image_id']] for item in members}
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


def _prepare_kint(path, adapter):
    data = _snapshot(path, MAX_SOURCE)
    common = dict(format='fdisbull-media-members-1', adapter=adapter, adapter_version=1,
                  inputs=[dict(role='container', **_identity(data))],
                  input_executed=False, specification=KINT_SPEC)
    if adapter == 'kint6-ke':
        from .kint6_format import inspect_ke_bytes
        container = inspect_ke_bytes(data)
        header_size = container['header_bytes']
        members = [('header', 0, data[:header_size]), ('body', header_size, data[header_size:])]
        common.update(container=container, qualification='structural-only',
                      members=[dict(name=name, input_role='container', offset=offset,
                                    guest_offset=offset, **_identity(payload))
                               for name, offset, payload in members],
                      unknowns=['The body intermixes instructions and initialized data; no boundary is inferred.',
                                'ZERO, STACK and HEAP exist only at runtime and are not extracted.',
                                'Header revision/extension bytes do not establish a verified minimum runtime version.'])
        return common, {name: payload for name, _, payload in members}
    from .sherlock7_media import decode_png_atlas
    atlas, payloads = decode_png_atlas(data, profile=adapter)
    result = dict(atlas, **common)
    # A decoded rectangle cannot be mapped to a contiguous compressed-file range.
    result['members'] = [dict(item, input_role='container', offset=None,
                              **_identity(payloads[item['name']])) for item in atlas['members']]
    return result, payloads


def inspect_media(path, *, adapter, volume_root=None, number=None, index_path=None, **options):
    """Inventory immutable member ranges with source and member digests."""
    if adapter == 'doom-wad':
        if volume_root is not None or number is not None or index_path is not None:
            raise ValueError('WAD inspection does not accept AGI/FLIC parameters')
        from .wad_media import inspect_wad_media
        return inspect_wad_media(path, **options)
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
    if adapter in ('mve', 'castles2-slb', 'castles2-slb-playback'):
        if volume_root is not None or number is not None:
            raise ValueError('MVE/SLB inspection does not accept AGI resource parameters')
        if adapter == 'mve':
            from .mve import inspect_mve
            return inspect_mve(path)
        from .castles2_media import inspect_castles2
        return inspect_castles2(path, adapter=adapter)
    if adapter in ('dinopark-act', 'dinopark-pic', 'dinopark-abt', 'dinopark-act-sequence', 'dinopark-abt-playback'):
        if volume_root is not None or number is not None:
            raise ValueError('DinoPark decoding does not accept AGI parameters')
        from .dinopark_media import inspect_dinopark
        return inspect_dinopark(path, adapter=adapter)
    if adapter == 'smacker':
        if volume_root is not None or number is not None:
            raise ValueError('Smacker does not accept AGI resource parameters')
        from .smacker import inspect_smk
        return inspect_smk(path)
    result, _ = _prepare(path, adapter, volume_root, number)
    return result


def decode_media(path, output, *, adapter, slot=None, **options):
    """Dispatch explicit asset adapters without guessing a format or timing."""
    if adapter == 'castles2-slb':
        from .castles2_media import decode_slb_media
        return decode_slb_media(path, output, slot=slot, **options)
    if slot is not None:
        raise ValueError('slot is only supported by the Castles II SLB decoder')
    from .dinopark_media import decode_media as decode_dinopark
    return decode_dinopark(path, output, adapter=adapter, **options)


def extract_media(path, output, *, adapter, member, volume_root=None, number=None,
                  max_output_bytes=MAX_OUTPUT, **options):
    """Extract one member (or all PNG crops) to a new private directory."""
    if adapter == 'doom-wad':
        if volume_root is not None or number is not None:
            raise ValueError('WAD extraction does not accept AGI parameters')
        from .wad_media import extract_wad_media
        return extract_wad_media(path, output, member=member, max_output_bytes=max_output_bytes, **options)
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT:
        raise ValueError('max_output_bytes must be 1..67108864')
    result, payloads = _prepare(path, adapter, volume_root, number, **options)
    is_shi = adapter == 'sherlock-shi'
    if is_shi:
        from .shi import _png_payload
        payloads = {name: _png_payload(value) for name, value in payloads.items()}
    bulk = member == 'all' and (adapter in PNG_ADAPTERS or is_shi)
    if not isinstance(member, str) or (not bulk and member not in payloads):
        raise ValueError('Unknown member; inspect this source first')
    names = list(payloads) if bulk else [member]
    if sum(len(payloads[name]) for name in names) > max_output_bytes:
        raise ValueError('Selected members exceed output budget')
    filenames = {}
    for name in names:
        if adapter in PNG_ADAPTERS or is_shi:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}(?:\.png)?', name):
                raise ValueError('Decoder returned an unsafe member name')
            filenames[name] = name if name.endswith('.png') else name + '.png'
        else:
            filenames[name] = 'payload.bin'
    if len(set(filenames.values())) != len(filenames):
        raise ValueError('Decoder returned duplicate output filenames')
    from .output_artifacts import _private_directory
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if not destination.parent.is_dir():
        raise ValueError('Output parent must already exist and be private')
    # Reuse the tool's ownership, symlink and Git/worktree boundary checks.
    _private_directory(destination.parent)
    destination.mkdir(mode=0o700)  # Exclusive; existing paths and links refused.
    try:
        _private_directory(destination)
        extracted = []
        for name in names:
            with (destination / filenames[name]).open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(payloads[name])
            selected = next(item for item in result['members'] if item['name'] == name)
            extracted.append(dict(selected, path=filenames[name]))
        result.update(output=str(destination), extracted=extracted if bulk else extracted[0],
                      manifest='media-manifest.json')
        if is_shi:
            result['extracted'] = dict(member=member, format='indexed-png', images=[
                dict(image_id=next(item['image_id'] for item in result['members'] if item['name'] == name),
                     source_member=name, path=filenames[name], **_identity(payloads[name]))
                for name in names])
        with (destination / 'media-manifest.json').open('x', encoding='utf-8') as stream:
            os.chmod(stream.fileno(), 0o600)
            json.dump(result, stream, indent=2, ensure_ascii=True)
            stream.write('\n')
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise
