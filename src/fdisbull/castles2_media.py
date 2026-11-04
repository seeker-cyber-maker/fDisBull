"""Private selected-sample exports over the explicit Castles II SLB profile."""
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

MAX_OUTPUT_BYTES = 64 * 1024 * 1024


def inspect_castles2(path, *, adapter):
    from .castles2_audio import decode_slb, bind_slb_playback, MAX_SOURCE_BYTES
    library = decode_slb(_snapshot(path, MAX_SOURCE_BYTES))
    if adapter == 'castles2-slb':
        return library.report()
    if adapter == 'castles2-slb-playback':
        return bind_slb_playback(library).report()
    raise ValueError('Select an explicit Castles II SLB adapter')


def decode_slb_media(path, output, *, slot, playback_profile=None,
                     sample_rate=None, channels=None, index=None, palette_path=None,
                     palette_index=0, palette_policy='shift2',
                     max_output_bytes=MAX_OUTPUT_BYTES):
    """Export one original slot as PCM WAV with a declared integer timing adapter.

    Selecting an SLB key is deliberately insufficient: the original player can
    randomize duplicate variants. The caller supplies the directory slot. Exact
    rational device timing is retained separately from the integer WAV rate.
    """
    from .castles2_audio import decode_slb, bind_slb_playback, MAX_SOURCE_BYTES
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError('Decoded output byte budget must be 1..67108864')
    if playback_profile is None:
        raise ValueError('SLB WAV export requires an explicit playback_profile')
    if sample_rate is not None or channels is not None:
        raise ValueError('SLB playback profile excludes sample_rate and channels overrides')
    if index is not None or palette_path is not None or palette_index != 0 or palette_policy != 'shift2':
        raise ValueError('SLB export does not accept image/palette selection parameters')
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Decoded output must be a new private directory')
    if not destination.parent.is_dir():
        raise ValueError('Decoded output parent must already exist')
    _private_directory(destination.parent)
    raw = _snapshot(path, MAX_SOURCE_BYTES)
    library = decode_slb(raw)
    playback = bind_slb_playback(library, profile=playback_profile)
    selection = playback.sample_report(slot)
    pcm = library.sample(slot)
    # Reject an obviously excessive WAV before creating a second PCM container.
    if len(pcm) + 44 > max_output_bytes:
        raise ValueError('Selected WAV exceeds the output byte budget')
    data = io.BytesIO()
    with wave.open(data, 'wb') as writer:
        writer.setnchannels(1)
        writer.setsampwidth(1)
        writer.setframerate(playback.wave_sample_rate)
        writer.writeframes(pcm)
    wav = data.getvalue()
    if _snapshot(path, MAX_SOURCE_BYTES) != raw:
        raise ValueError('Source changed during SLB export')
    result = dict(format='fdisbull-media-decoding-export-1', adapter='castles2-slb',
        source=dict(bytes=len(raw), sha256=library.source_sha256),
        selection=selection,
        outputs=[dict(path='samples.wav', bytes=len(wav), sha256=hashlib.sha256(wav).hexdigest())],
        output=str(destination), manifest='decode-manifest.json',
        input_executed=False, source_modified=False, executables_modified=False,
        native_runtime_tested=False,
        qualification='explicit-consumer-profile selected PCM extraction; integer WAV rate is an adapter, not exact hardware timing')
    manifest = (json.dumps(result, indent=2, ensure_ascii=True) + '\n').encode()
    if len(wav) + len(manifest) > max_output_bytes:
        raise ValueError('Decoded WAV and manifest exceed the output byte budget')
    destination.mkdir(mode=0o700)
    try:
        _private_directory(destination)
        for name, value in [('samples.wav', wav), ('decode-manifest.json', manifest)]:
            with (destination / name).open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(value)
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise
