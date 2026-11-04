"""Bounded SMK2 inspection and native FULL/SKIP cinematic framing.

Inputs are media, never executed. Optional FFmpeg readers independently decode
immutable snapshots through pipes; decoded images/PCM are never written to disk.
A successful media result does not certify playback in any original game.
"""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time

from .media import MAX_SOURCE, _snapshot
from .output_artifacts import _private_directory

MAX_OUTPUT = 64 * 1024 * 1024
MAX_FRAMES = 10000
MAX_PIXELS = 1024 * 1024
MAX_DECODED = 512 * 1024 * 1024
MAX_RETAINED = 128 * 1024 * 1024
MAX_TREE_ALLOCATION = 8 * 1024 * 1024
MAX_DECODER_ALLOCATION = 64 * 1024 * 1024
MAX_AUDIO_RATE = 192000
RUNS = tuple(range(1, 60)) + (128, 256, 512, 1024, 2048)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class _Frame:
    offset: int
    size: int
    flags: int
    palette_bytes: int
    audio_end: int


class _SMK:
    def __init__(self, data):
        if len(data) < 104 or data[:4] != b'SMK2':
            raise ValueError('Expected a complete SMK2 header; SMK4 is unsupported')
        self.data = data
        self.width, self.height, self.count, self.rate, self.flags = struct.unpack_from('<IIIiI', data, 4)
        if not self.width or not self.height or self.width % 4 or self.height % 4:
            raise ValueError('SMK2 geometry must be positive and divisible by four')
        if self.width * self.height > MAX_PIXELS:
            raise ValueError('SMK2 pixel budget exceeded')
        if not 1 <= self.count <= MAX_FRAMES:
            raise ValueError('SMK2 frame count exceeds its limit')
        if self.count * (self.width * self.height + 1024) > MAX_DECODED:
            raise ValueError('SMK2 decoded video byte budget exceeded')
        if self.flags:
            raise ValueError('SMK2 ring-frame, scaling and unknown flags are unsupported')
        self.tree_bytes, *allocations = struct.unpack_from('<5I', data, 52)
        if not self.tree_bytes or any(a % 4 for a in allocations) or sum(allocations) > MAX_TREE_ALLOCATION:
            raise ValueError('Invalid or excessive SMK2 Huffman tree allocation')
        self.allocations = allocations
        self.audio_profiles = {}
        for track, word in enumerate(struct.unpack_from('<7I', data, 72)):
            if not word:
                continue
            rate, flags = word & 0xffffff, word >> 24
            if not rate or not flags & 0x40:
                raise ValueError('SMK2 audio header has an incoherent track declaration')
            if rate > MAX_AUDIO_RATE or flags & 0x0f:
                raise ValueError('Unsupported SMK2 audio rate or codec flags')
            self.audio_profiles[track] = {
                'sample_rate': rate, 'channels': 2 if flags & 0x10 else 1,
                'codec_name': ('smackaudio' if flags & 0x80 else
                               'pcm_s16le' if flags & 0x20 else 'pcm_u8'),
            }
        table_end = 104 + 5 * self.count
        self.payload_offset = table_end + self.tree_bytes
        if self.payload_offset > len(data):
            raise ValueError('Truncated SMK2 frame tables or Huffman trees')
        self.sizes = struct.unpack_from('<' + 'I' * self.count, data, 104)
        self.types = data[104 + 4 * self.count:table_end]
        self.frames = []
        position = self.payload_offset
        for size, flags in zip(self.sizes, self.types):
            amount = size & ~3
            if amount < 4 or position + amount > len(data):
                raise ValueError('Invalid or truncated SMK2 frame extent')
            packet = memoryview(data)[position:position + amount]
            palette = int(packet[0]) * 4 if flags & 1 else 0
            if (flags & 1 and not palette) or palette > amount:
                raise ValueError('Invalid SMK2 palette packet length')
            end = palette
            for track in range(7):
                if flags & (2 << track):
                    if track not in self.audio_profiles:
                        raise ValueError('SMK2 audio packet references an undeclared audio track')
                    if end + 4 > amount:
                        raise ValueError('Truncated SMK2 audio chunk header')
                    length = struct.unpack_from('<I', packet, end)[0]
                    if length < 4 or end + length > amount:
                        raise ValueError('Invalid SMK2 audio chunk length')
                    end += length
            if end >= amount:
                raise ValueError('SMK2 frame has no video payload')
            self.frames.append(_Frame(position, amount, flags, palette, end))
            position += amount
        # Original RAD output may carry a short alignment trailer. Never guess
        # about an unexplained appended payload or let an arbitrarily large one pass.
        self.trailer = data[position:]
        if len(self.trailer) > 3 or any(self.trailer):
            raise ValueError('Unexplained SMK2 trailer')

    def audio(self, frame):
        return self.data[frame.offset + frame.palette_bytes:frame.offset + frame.audio_end]

    def report(self):
        track_frames = [sum(bool(f.flags & (2 << t)) for f in self.frames) for t in range(7)]
        audio_rates = struct.unpack_from('<7I', self.data, 72)
        return {
            'format': 'fdisbull-smk-inspection-1', 'adapter': 'smacker-smk2',
            'source': {'bytes': len(self.data), 'sha256': _sha(self.data)},
            'signature': 'SMK2', 'width': self.width, 'height': self.height,
            'logical_frames': self.count, 'physical_frames': self.count,
            'rate_field': self.rate, 'flags': self.flags,
            'frame_size_table': {'offset': 104, 'bytes': self.count * 4},
            'frame_type_table': {'offset': 104 + self.count * 4, 'bytes': self.count},
            'huffman_trees': {'offset': 104 + self.count * 5, 'bytes': self.tree_bytes,
                              'decoded_allocation_bytes': self.allocations},
            'frame_payload_offset': self.payload_offset,
            'palette_packets': sum(bool(f.flags & 1) for f in self.frames),
            'audio_tracks': [{'track': i, 'frame_packets': n, 'header_word': audio_rates[i]}
                             for i, n in enumerate(track_frames) if n],
            'trailer_bytes': len(self.trailer), 'input_executed': False,
            'qualification': 'container-structure-only',
            'unknowns': ['Huffman/video/audio decoding requires the independent reader.',
                         'Original-game playback, seeking and sound output are not established.'],
        }


def inspect_smk(path):
    """Inventory bounded SMK2 header/table/chunk structure, without source bytes."""
    return _SMK(_snapshot(path, MAX_SOURCE)).report()


class _BitsOut:
    def __init__(self):
        self.data = bytearray()
        self.bits = 0

    def bit(self, value):
        if self.bits % 8 == 0:
            self.data.append(0)
        self.data[-1] |= (value & 1) << (self.bits % 8)
        self.bits += 1

    def number(self, value, count):
        for bit in range(count):
            self.bit(value >> bit)

    def code(self, bits):
        for bit in bits:
            self.bit(bit)


def _tree(output, needed):
    """Write a native bigtree with explicit escape leaves and exact allocation."""
    values = sorted(set(needed))
    used = set(values)
    escapes = [i for i in range(65535, -1, -1) if i not in used][:3]
    if len(escapes) != 3:
        raise ValueError('SMK2 FULL tree needs three unused escape words')
    output.bit(1)
    for _ in range(2):
        output.bit(1)

        def small(items):
            if len(items) == 1:
                output.bit(0)
                output.number(items[0], 8)
            else:
                output.bit(1)
                mid = len(items) // 2
                small(items[:mid])
                small(items[mid:])

        small(list(range(256)))
        output.bit(0)
    for value in escapes:
        output.number(value, 16)
    codes = {}
    items = sorted(values + escapes)

    def big(symbols, path):
        if len(symbols) == 1:
            output.bit(0)
            value = symbols[0]
            # The balanced byte tree's path is MSB-first, while literal
            # numbers in its header are packed LSB-first.
            for byte in (value & 255, value >> 8):
                output.code(tuple((byte >> bit) & 1 for bit in range(7, -1, -1)))
            if value not in escapes:
                codes[value] = path
        else:
            output.bit(1)
            mid = len(symbols) // 2
            big(symbols[:mid], path + (0,))
            big(symbols[mid:], path + (1,))

    big(items, ())
    output.bit(0)
    nodes = 2 * len(items) - 1
    return codes, nodes * 4


def _runs(blocks):
    result = []
    for run in (2048, 1024, 512, 256, 128):
        while blocks >= run:
            result.append(run)
            blocks -= run
    while blocks:
        run = min(blocks, 59)
        result.append(run)
        blocks -= run
    return result


def _words(image, width, height):
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            for row in range(4):
                offset = (y + row) * width + x
                yield image[offset + 2] | image[offset + 3] << 8
                yield image[offset] | image[offset + 1] << 8


def _palette(image, pixels):
    original = image[pixels:]
    output = bytearray([193])
    for index in range(256):
        blue, green, red, _ = original[index * 4:index * 4 + 4]
        # Original SMK palettes have six-bit RGB components. Decoder validation
        # below rejects any source palette which this representation cannot retain.
        output.extend((red >> 2, green >> 2, blue >> 2))
    return bytes(output) + bytes(3)


def _remaining(deadline):
    value = deadline - time.monotonic()
    if value <= 0:
        raise ValueError('SMK framing exceeded its host timeout')
    return value


@contextmanager
def _reader(command, data, deadline):
    """Bound stdin, stderr and host lifetime while the caller streams stdout."""
    _remaining(deadline)
    stderr = bytearray()
    expired = threading.Event()
    overflow = threading.Event()
    def feed():
        try:
            with process.stdin:
                view = memoryview(data)
                for start in range(0, len(view), 1024 * 1024):
                    process.stdin.write(view[start:start + 1024 * 1024])
        except (BrokenPipeError, OSError):
            pass

    def drain():
        with process.stderr:
            while True:
                block = process.stderr.read(8192)
                if not block:
                    return
                remaining = 65536 - len(stderr)
                stderr.extend(block[:remaining])
                if len(block) > remaining:
                    overflow.set()
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    return

    def expire():
        expired.set()
        try:
            process.kill()
        except ProcessLookupError:
            pass

    workers = []
    timer = None
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    try:
        workers = [threading.Thread(target=feed, daemon=True), threading.Thread(target=drain, daemon=True)]
        timer = threading.Timer(max(.001, deadline - time.monotonic()), expire)
        timer.daemon = True
        for worker in workers:
            worker.start()
        timer.start()
        yield process.stdout
        process.wait(timeout=_remaining(deadline))
        if expired.is_set():
            raise ValueError('SMK decoder exceeded its host timeout')
        if overflow.is_set():
            raise ValueError('SMK decoder error output exceeded its byte budget')
        if process.returncode:
            raise ValueError('SMK decoder failed: ' + stderr.decode(errors='replace')[-1000:])
    except subprocess.TimeoutExpired as error:
        raise ValueError('SMK decoder exceeded its host timeout') from error
    finally:
        if timer is not None:
            timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        for worker in workers:
            if worker.ident is not None:
                worker.join(timeout=2)
        for pipe in (process.stdin, process.stdout, process.stderr):
            pipe.close()
    if stderr.strip():
        raise ValueError('SMK decoder reported an error: ' + stderr.decode(errors='replace')[-1000:])


def _command(executable, *arguments):
    return [executable, '-max_alloc', str(MAX_DECODER_ALLOCATION), '-v', 'error',
            '-protocol_whitelist', 'pipe', '-f', 'smk', '-i', 'pipe:0', *arguments]


def _probe(data, executable, deadline):
    command = _command(executable, '-show_entries', 'stream=index,codec_type,codec_name,channels,sample_rate',
                       '-of', 'json')
    with _reader(command, data, deadline) as pipe:
        raw = pipe.read(65537)
        if len(raw) > 65536:
            raise ValueError('SMK probe metadata exceeds its byte budget')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise ValueError('SMK probe returned invalid JSON') from error
    streams = value.get('streams')
    if not isinstance(streams, list) or len(streams) > 8:
        raise ValueError('SMK probe returned invalid streams')
    video = [s for s in streams if s.get('codec_type') == 'video']
    if len(video) != 1 or video[0].get('codec_name') != 'smackvideo':
        raise ValueError('Independent reader did not identify Smacker video')
    return [s for s in streams if s.get('codec_type') == 'audio']


def _audio_coverage(smk, streams):
    """Require one independently identified stream for every declared track.

    FFmpeg numbers Smacker audio streams after video, in ascending header-slot
    order. Unused declared tracks are still checked as complete (possibly empty)
    streams; packet references to undeclared slots already refuse in _SMK.
    """
    if len(streams) != len(smk.audio_profiles):
        raise ValueError('Independent SMK reader did not cover all declared audio tracks')
    if any(not isinstance(stream, dict) or type(stream.get('index')) is not int for stream in streams):
        raise ValueError('Independent SMK reader returned invalid audio stream identities')
    ordered = sorted(streams, key=lambda stream: stream['index'])
    result = []
    for ordinal, (track, profile) in enumerate(smk.audio_profiles.items(), 1):
        stream = ordered[ordinal - 1]
        rate = stream.get('sample_rate')
        if isinstance(rate, str) and rate.isascii() and rate.isdecimal():
            rate = int(rate)
        if (stream['index'] != ordinal or stream.get('codec_name') != profile['codec_name']
                or type(stream.get('channels')) is not int
                or stream['channels'] != profile['channels']
                or type(rate) is not int or rate != profile['sample_rate']):
            raise ValueError('Independent SMK audio codec/channel/rate differs from its declared track')
        result.append({**stream, 'source_track': track})
    return result


def _read_exact(pipe, count):
    parts = []
    while count:
        block = pipe.read(count)
        if not block:
            break
        parts.append(block)
        count -= len(block)
    return b''.join(parts)


def _images(data, smk, executable, deadline, keep, selected=None):
    command = _command(executable, '-map', '0:v:0', '-an', '-sn', '-dn', '-fps_mode', 'passthrough',
                       '-pix_fmt', 'pal8', '-f', 'rawvideo', 'pipe:1')
    pixels = smk.width * smk.height
    size = pixels + 1024
    images = {}
    meaningful = None
    with _reader(command, data, deadline) as pipe:
        for index in range(smk.count):
            frame = _read_exact(pipe, size)
            if len(frame) != size:
                raise ValueError('SMK decoder produced an incomplete frame sequence')
            if index < keep or index >= smk.count - keep or (selected and index in selected):
                images[index] = frame
            if meaningful is None:
                palette = frame[pixels:]
                bright = {i for i in range(256) if max(palette[i * 4:i * 4 + 3]) >= 32}
                if sum(n for i, n in Counter(frame[:pixels]).items() if i in bright) >= max(1, pixels // 100):
                    meaningful = index
                    images[index] = frame
        if pipe.read(1):
            raise ValueError('SMK decoder produced excessive frames')
    return images, meaningful


def _pcm(data, stream, executable, deadline):
    channels = stream.get('channels')
    if type(channels) is not int or not 1 <= channels <= 2 or type(stream.get('index')) is not int:
        raise ValueError('Unsupported SMK audio stream metadata')
    digest = hashlib.sha256()
    count = 0
    command = _command(executable, '-map', f"0:{stream['index']}", '-vn', '-sn', '-dn',
                       '-c:a', 'pcm_s16le', '-f', 's16le', 'pipe:1')
    with _reader(command, data, deadline) as pipe:
        while True:
            block = pipe.read(1024 * 1024)
            if not block:
                break
            count += len(block)
            if count > MAX_DECODED:
                raise ValueError('SMK decoded audio byte budget exceeded')
            digest.update(block)
    if count % (2 * channels):
        raise ValueError('SMK decoder returned partial PCM samples')
    return {'pcm_bytes': count, 'pcm_sha256': digest.hexdigest(), 'samples_per_channel': count // (2 * channels)}


def _encode(smk, images, limit, deadline):
    words = set()
    for image in images.values():
        words.update(_words(image, smk.width, smk.height))
        _remaining(deadline)
    runs = _runs(smk.width * smk.height // 16)
    types = {(RUNS.index(run) << 2) | kind for run in runs for kind in (1, 2)}
    trees = _BitsOut()
    _, mmap_size = _tree(trees, {0})
    _, mclr_size = _tree(trees, {0})
    full_codes, full_size = _tree(trees, words)
    type_codes, type_size = _tree(trees, types)
    hold = _BitsOut()
    for run in runs:
        hold.code(type_codes[(RUNS.index(run) << 2) | 2])
    frames, sizes, frame_types = [], [], []
    used = 104 + smk.count * 5 + len(trees.data) + len(smk.trailer)
    for index, original in enumerate(smk.frames):
        audio = smk.audio(original)
        flags = original.flags & ~1
        if index in images:
            image = images[index]
            payload = _BitsOut()
            values = iter(_words(image, smk.width, smk.height))
            for run in runs:
                payload.code(type_codes[(RUNS.index(run) << 2) | 1])
                for _ in range(run * 8):
                    payload.code(full_codes[next(values)])
            frame = _palette(image, smk.width * smk.height) + audio + payload.data
            flags |= 1
        else:
            frame = audio + hold.data
        frame += bytes((-len(frame)) % 4)
        used += len(frame)
        if used > limit:
            raise ValueError('Framed SMK exceeds output byte budget')
        frames.append(frame)
        sizes.append(len(frame))
        frame_types.append(flags)
        _remaining(deadline)
    header = bytearray(smk.data[:104])
    struct.pack_into('<5I', header, 52, len(trees.data), mmap_size, mclr_size, full_size, type_size)
    return (bytes(header) + struct.pack('<' + 'I' * smk.count, *sizes) + bytes(frame_types)
            + bytes(trees.data) + b''.join(frames) + smk.trailer)


def frame_smk(path, output, *, keep_frames=32, max_output_bytes=MAX_OUTPUT,
              ffmpeg='ffmpeg', ffprobe='ffprobe', timeout=120):
    """Frame one SMK2 into a new private directory after complete verification.

    The output budget includes both framed.smk and smk-manifest.json. Logical
    frame count/timing and compressed audio stay unchanged. Independent decoding
    verifies every retained PAL8 image/palette and every complete PCM track.
    """
    if type(keep_frames) is not int or not 1 <= keep_frames <= 64:
        raise ValueError('keep_frames must be 1..64')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT:
        raise ValueError('max_output_bytes must be 1..67108864')
    if type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise ValueError('timeout must be positive and at most 600 seconds')
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('SMK output must be a new directory')
    if not destination.parent.is_dir():
        raise ValueError('SMK output parent must already exist')
    _private_directory(destination.parent)
    readers = []
    for executable in (ffmpeg, ffprobe):
        resolved = shutil.which(os.fspath(executable))
        if not resolved:
            raise ValueError('Required independent SMK decoder is unavailable: ' + os.fspath(executable))
        readers.append(resolved)
    ffmpeg, ffprobe = readers
    deadline = time.monotonic() + timeout
    data = _snapshot(path, MAX_SOURCE)
    smk = _SMK(data)
    if min(smk.count, keep_frames * 2 + 1) * (smk.width * smk.height + 1024) > MAX_RETAINED:
        raise ValueError('SMK retained-image memory budget exceeded')
    audio_streams = _audio_coverage(smk, _probe(data, ffprobe, deadline))
    images, meaningful = _images(data, smk, ffmpeg, deadline, keep_frames)
    framed = _encode(smk, images, max_output_bytes, deadline)
    if len(framed) >= len(data):
        raise ValueError('Framing does not reduce this SMK; output refused')
    derived = _SMK(framed)
    if any(smk.audio(a) != derived.audio(b) or (a.flags & ~1) != (b.flags & ~1)
           for a, b in zip(smk.frames, derived.frames)):
        raise ValueError('Framing changed original compressed audio packets')
    replay, _ = _images(framed, derived, ffmpeg, deadline, keep_frames, selected=set(images))
    if not set(images) <= set(replay) or any(image != replay[i] for i, image in images.items()):
        raise ValueError('Independent decoder found a retained image/palette mismatch')
    audio = []
    for stream in audio_streams:
        original_pcm = _pcm(data, stream, ffmpeg, deadline)
        derived_pcm = _pcm(framed, stream, ffmpeg, deadline)
        if original_pcm != derived_pcm:
            raise ValueError('Independent decoder found an audio PCM mismatch')
        audio.append({'stream_index': stream['index'], 'source_track': stream['source_track'],
                      'codec_name': stream['codec_name'], 'channels': stream['channels'],
                      'sample_rate': stream.get('sample_rate'), **original_pcm, 'exact_pcm_match': True})
    if _snapshot(path, MAX_SOURCE) != data:
        raise ValueError('SMK source changed during framing')
    result = {
        'format': 'fdisbull-smk-framing-1', 'adapter': 'smacker-smk2',
        'source': {'bytes': len(data), 'sha256': _sha(data)},
        'framed': {'path': 'framed.smk', 'bytes': len(framed), 'sha256': _sha(framed)},
        'saved_bytes': len(data) - len(framed), 'width': smk.width, 'height': smk.height,
        'logical_frames': smk.count, 'rate_field': smk.rate,
        'retained_frame_indices': sorted(images), 'first_meaningful_frame': meaningful,
        'native_hold_frames': smk.count - len(images),
        'retained_pal8_sha256': {str(i): _sha(image) for i, image in images.items()},
        'all_retained_images_and_palettes_exact': True, 'complete_video_decode': True,
        'compressed_audio_packets_byte_identical': True, 'audio': audio,
        'tree_policy': 'Four initialized bigtrees, explicit escape leaves, exact node allocations',
        'palette_policy': 'Exact source palette at each retained image; preceding image/palette held between them',
        'input_executed': False, 'executables_modified': False,
        'qualification': 'independent-decoder-verified-framing',
        'native_game_playback': 'not_run', 'duration_changed': False,
        'decoder_commands': {'ffmpeg': ffmpeg, 'ffprobe': ffprobe},
        'decoder_max_allocation_bytes': MAX_DECODER_ALLOCATION,
        'output': str(destination), 'manifest': 'smk-manifest.json',
        'unknowns': ['Original-game playback, seeking, audible output and full-game behavior require separate tests.'],
    }
    encoded = (json.dumps(result, indent=2, ensure_ascii=True) + '\n').encode()
    if len(framed) + len(encoded) > max_output_bytes:
        raise ValueError('Framed media and manifest exceed output byte budget')
    # No output directory or partial media exists before all validation succeeds.
    destination.mkdir(mode=0o700)
    try:
        _private_directory(destination)
        for name, content in (('framed.smk', framed), ('smk-manifest.json', encoded)):
            with (destination / name).open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(content)
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise
