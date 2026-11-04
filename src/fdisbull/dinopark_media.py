"""Private selected-resource exports over the bounded DinoPark byte decoders."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import wave

from .media import _snapshot
from .output_artifacts import _private_directory

ADAPTERS = ('dinopark-act', 'dinopark-pic', 'dinopark-abt')
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _decoded(path, adapter):
    if adapter == 'dinopark-abt':
        from .dinopark_audio import decode_abt, MAX_SOURCE_BYTES
        raw = _snapshot(path, MAX_SOURCE_BYTES)
        decoded = decode_abt(raw)
        return raw, decoded, decoded.report()
    if adapter in ('dinopark-act', 'dinopark-pic'):
        from .dinopark_images import decode_act, decode_pic, describe_act, describe_pic, MAX_SOURCE
        raw = _snapshot(path, MAX_SOURCE)
        decoder, describe = (decode_act, describe_act) if adapter == 'dinopark-act' else (decode_pic, describe_pic)
        decoded = decoder(raw)
        return raw, decoded, describe(decoded)
    raise ValueError('Select an explicit DinoPark ACT, PIC or ABT adapter')


def inspect_dinopark(path, *, adapter):
    """Completely decode the admitted byte profile, returning metadata/hashes only."""
    return _decoded(path, adapter)[2]


def _selected(items, index):
    if type(index) is not int or not 0 <= index < len(items):
        raise ValueError('Selected sprite/frame index is outside the decoded resource')
    return items[index]


def _png(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def decode_media(path, output, *, adapter, index=None, palette_path=None,
                 palette_index=0, palette_policy='shift2', sample_rate=None,
                 channels=None, max_output_bytes=MAX_OUTPUT_BYTES):
    """Export a selected decoded image or an explicitly timed unsigned-8 WAV.

    ACT without an external palette exports exact index/mask diagnostic PNGs.
    PIC exports indexed PNG with an explicit six-to-eight-bit palette policy.
    WAV rate/channels are caller adapters, never inferred from an opaque header.
    No output is created before decoding, adapter validation and byte admission.
    """
    if adapter not in ADAPTERS:
        raise ValueError('Select an explicit DinoPark ACT, PIC or ABT adapter')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError('max_output_bytes must be 1..67108864')
    if palette_policy not in ('shift2', 'replicate6'):
        raise ValueError('Unknown six-bit palette export policy')
    if type(palette_index) is not int or palette_index < 0:
        raise ValueError('palette_index must be nonnegative')
    if adapter == 'dinopark-abt':
        if index is not None or palette_path is not None or palette_index != 0 or palette_policy != 'shift2':
            raise ValueError('ABT does not accept image selection or palette adapters')
        if type(sample_rate) is not int or not 1 <= sample_rate <= 192000 or type(channels) is not int or channels not in (1, 2):
            raise ValueError('WAV export requires explicit sample_rate (1..192000) and channels (1 or 2); ABT header timing is not assumed')
    elif sample_rate is not None or channels is not None:
        raise ValueError('Image decoding does not accept WAV timing/channel adapters')
    if adapter == 'dinopark-act' and palette_path is None and palette_index != 0:
        raise ValueError('palette_index requires an external ACT palette source')
    if adapter == 'dinopark-pic' and (palette_path is not None or palette_index != 0):
        raise ValueError('PIC palettes belong to their decoded frames; no external palette adapter')
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Decoded output must be a new private directory')
    if not destination.parent.is_dir():
        raise ValueError('Decoded output parent must already exist')
    _private_directory(destination.parent)
    raw, decoded, report = _decoded(path, adapter)
    files = {}
    selection = {}
    palette_raw = None
    if adapter == 'dinopark-abt':
        pcm = decoded.pcm_u8
        if len(pcm) % channels:
            raise ValueError('Decoded sample bytes do not form complete caller-selected WAV frames')
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(1)
            writer.setframerate(sample_rate)
            writer.writeframes(pcm)
        files['samples.wav'] = stream.getvalue()
        selection.update(sample_representation='unsigned-8-bit sequence', sample_rate=sample_rate,
                         channels=channels, timing_source='explicit-caller-adapter',
                         original_playback_timing_qualified=False)
    else:
        from PIL import Image
        from .dinopark_images import decode_pic, palette_rgb, MAX_SOURCE
        index = 0 if index is None else index
        item = _selected(decoded.sprites if adapter == 'dinopark-act' else decoded.frames, index)
        selection.update(index=index, width=item.width, height=item.height)
        if adapter == 'dinopark-pic':
            palette = item.palette6
        elif palette_path is not None:
            palette_raw = _snapshot(palette_path, MAX_SOURCE)
            palette_file = decode_pic(palette_raw)
            palette = _selected(palette_file.frames, palette_index).palette6
            selection['palette_source'] = dict(sha256=_sha(palette_raw), frame_index=palette_index)
        else:
            palette = None
        if adapter == 'dinopark-act':
            files['indices.png'] = _png(Image.frombytes('L', (item.width, item.height), item.indices))
            files['opacity.png'] = _png(Image.frombytes('L', (item.width, item.height), item.opacity))
        if palette is not None:
            rgb = palette_rgb(palette, policy=palette_policy)
            image = Image.frombytes('P', (item.width, item.height), item.indices)
            image.putpalette(rgb)
            if adapter == 'dinopark-act':
                image = image.convert('RGBA')
                image.putalpha(Image.frombytes('L', (item.width, item.height), item.opacity))
            files['image.png'] = _png(image)
            selection.update(palette_policy=palette_policy, raw_palette6_sha256=_sha(palette),
                             host_RGB_display_qualified=False)
        else:
            selection['presentation'] = 'diagnostic index and opacity planes; external ACT palette not supplied'
    # Rebind both snapshots after processing so a moving source cannot be accepted.
    limit = 1024 * 1024 if adapter == 'dinopark-abt' else 8 * 1024 * 1024
    if _snapshot(path, limit) != raw:
        raise ValueError('Source changed during media decoding')
    if palette_raw is not None and _snapshot(palette_path, 8 * 1024 * 1024) != palette_raw:
        raise ValueError('External palette source changed during media decoding')
    result = dict(format='fdisbull-media-decoding-export-1', adapter=adapter,
        source=dict(bytes=len(raw), sha256=_sha(raw)), decoded=report, selection=selection,
        outputs=[dict(path=name, bytes=len(content), sha256=_sha(content)) for name, content in files.items()],
        output=str(destination), manifest='decode-manifest.json', input_executed=False,
        source_modified=False, executables_modified=False, native_runtime_tested=False,
        qualification='complete-bounded-byte-decoding; selected authored media export')
    manifest = (json.dumps(result, indent=2, ensure_ascii=True) + '\n').encode()
    if sum(map(len, files.values())) + len(manifest) > max_output_bytes:
        raise ValueError('Decoded media and manifest exceed the output byte budget')
    destination.mkdir(mode=0o700)
    try:
        _private_directory(destination)
        for name, content in {**files, 'decode-manifest.json': manifest}.items():
            with (destination / name).open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(content)
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise
