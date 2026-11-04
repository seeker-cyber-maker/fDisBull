"""Bounded old-profile Interplay MVE inspection and verified native framing.

This deliberately admits the 8-bit 0x06/0x10 family, not later 0x11 codecs.
Framing changes video packets only. Original audio, timers, presentation calls,
palettes and chunk ordering stay intact. Independent decoding is a separate
qualification from consumption by an original DOS player.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import struct
import subprocess
import tempfile
import time

from .media import MAX_SOURCE, _snapshot
from .output_artifacts import _private_directory

HEADER = b'Interplay MVE File\x1a\x00\x1a\x00\x00\x01\x33\x11'
MAX_OUTPUT = 64 * 1024 * 1024
MAX_PIXELS = 320 * 200
MAX_FRAMES = 20000
MAX_CHUNKS = 100000
MAX_OPERATIONS = 300000
MAX_DECODED = 256 * 1024 * 1024
MAX_RETAINED = 32 * 1024 * 1024
MAX_TAIL_FRAMES = 512
MAX_DECODER_ALLOCATION = 64 * 1024 * 1024
PROFILE = 'interplay-mve-old8-v1'
_VISUAL = frozenset((6, 14, 15, 16))
_VERSIONS = {0: (0,), 1: (0,), 2: (0,), 3: (0,), 4: (0,),
             5: (1, 2), 6: (0,), 7: (1,), 8: (0,), 9: (0,),
             10: (0,), 12: (0,), 14: (0,), 15: (0,), 16: (0,)}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class _Operation:
    offset: int
    opcode: int
    version: int
    payload: bytes

    def encoded(self):
        return struct.pack('<HBB', len(self.payload), self.opcode, self.version) + self.payload


@dataclass(frozen=True)
class _Chunk:
    kind: int
    operations: tuple[_Operation, ...]


class _MVE:
    def __init__(self, data):
        if not isinstance(data, bytes) or not len(HEADER) <= len(data) <= MAX_SOURCE:
            raise ValueError('MVE must be bounded immutable bytes with a complete header')
        if data[:26] != HEADER:
            raise ValueError('Unsupported or incomplete Interplay MVE signature/version')
        self.data = data
        self.chunks = []
        self.chunk_sizes = []
        self.presented_chunks = []
        self.width = self.height = self.sample_rate = self.frame_microseconds = None
        self.audio_bytes = 0
        self.audio_frames = 0
        self.video_packets = 0
        self.video_codec = None
        self.counts = Counter()
        init_counts = Counter()
        position = 26
        operation_count = 0
        terminated = False
        while position < len(data):
            if len(self.chunks) >= MAX_CHUNKS or position + 4 > len(data):
                raise ValueError('MVE chunk budget or truncated chunk header')
            amount, kind = struct.unpack_from('<HH', data, position)
            position += 4
            end = position + amount
            self.chunk_sizes.append(amount)
            if kind not in range(6) or end > len(data):
                raise ValueError('Unsupported MVE chunk type or truncated extent')
            if terminated and not (kind == 5 and amount == 0 and end == len(data)):
                raise ValueError('Unexpected MVE data after end-of-stream')
            operations = []
            while position < end:
                if position + 4 > end or operation_count >= MAX_OPERATIONS:
                    raise ValueError('MVE operation budget or truncated operation header')
                offset = position
                length, opcode, version = struct.unpack_from('<HBB', data, position)
                position += 4
                if position + length > end:
                    raise ValueError('MVE operation extends outside its chunk')
                payload = data[position:position + length]
                position += length
                if opcode not in _VERSIONS or version not in _VERSIONS[opcode]:
                    raise ValueError(f'Unsupported MVE operation/version {opcode:#x}.{version}')
                operation = _Operation(offset, opcode, version, payload)
                operations.append(operation)
                self.counts[f'{opcode:02x}.{version}'] += 1
                operation_count += 1
                if opcode in (0, 1, 4) and length:
                    raise ValueError('MVE control operation must have an empty payload')
                if opcode == 0:
                    if kind != 4:
                        raise ValueError('MVE end-of-stream must be in its shutdown chunk')
                    terminated = True
                elif opcode == 2:
                    init_counts[opcode] += 1
                    if length != 6:
                        raise ValueError('Invalid MVE timer extent')
                    period, divisor = struct.unpack('<IH', payload)
                    if not period or not divisor or period * divisor > 10000000:
                        raise ValueError('Unsupported MVE timer interval')
                    self.frame_microseconds = period * divisor
                elif opcode == 3:
                    init_counts[opcode] += 1
                    if length != 8:
                        raise ValueError('Unsupported MVE audio initialization extent')
                    _, flags, rate, buffer_size = struct.unpack('<4H', payload)
                    if flags or not 1 <= rate <= 48000 or not buffer_size:
                        raise ValueError('MVE framing requires original uncompressed unsigned-8 mono audio')
                    self.sample_rate = rate
                elif opcode == 5:
                    init_counts[opcode] += 1
                    if length != (6 if version == 1 else 8):
                        raise ValueError('Unsupported MVE video initialization extent')
                    width, height, buffers = struct.unpack_from('<3H', payload)
                    if buffers != 1 or version == 2 and struct.unpack_from('<H', payload, 6)[0]:
                        raise ValueError('MVE true-color/extra-buffer profiles are unsupported')
                    self.width, self.height = width * 8, height * 8
                    if not width or not height or self.width * self.height > MAX_PIXELS:
                        raise ValueError('MVE geometry exceeds the old-8-bit framing profile')
                elif opcode == 7:
                    if length != 6:
                        raise ValueError('Unsupported MVE presentation operation')
                elif opcode in (8, 9):
                    if length < 6:
                        raise ValueError('Truncated MVE audio packet')
                    _, mask, samples = struct.unpack_from('<3H', payload)
                    if not samples:
                        raise ValueError('Empty MVE audio payload duration')
                    if opcode == 8:
                        if mask != 1 or length != 6 + samples:
                            raise ValueError('MVE PCM extent/stream mask is unsupported')
                        self.audio_bytes += samples
                        self.audio_frames += 1
                    elif length != 6 or mask not in (0xfffe, 0xffff):
                        raise ValueError('Unsupported MVE alternate-stream silence packet')
                elif opcode == 10 and length != 6:
                    raise ValueError('Unsupported MVE display-mode extent')
                elif opcode == 12:
                    init_counts[opcode] += 1
                    if length < 4:
                        raise ValueError('Truncated MVE palette')
                    start, count = struct.unpack_from('<HH', payload)
                    needed = 4 + count * 3
                    if not count or start + count > 256 or length not in (needed, needed + 1):
                        raise ValueError('Invalid MVE palette range/extent')
                    if any(x > 63 for x in payload[4:needed]) or any(payload[needed:]):
                        raise ValueError('Unsupported MVE palette depth/alignment')
                elif opcode in (14, 15) and (not length or length % 2):
                    raise ValueError('MVE old-codec maps must contain complete words')
                elif opcode in (6, 16):
                    if self.video_codec is None:
                        self.video_codec = opcode
                    elif self.video_codec != opcode:
                        raise ValueError('MVE framing requires one homogeneous old-codec family per movie')
                    if self.width is None or length < 15:
                        raise ValueError('MVE video packet precedes geometry or is incomplete')
                    words = struct.unpack_from('<7H', payload)
                    if words[2:4] != (0, 0) or words[4:6] != (self.width // 8, self.height // 8):
                        raise ValueError('MVE subrectangle or changed-geometry video is unsupported')
                    if opcode == 6 and length < 14 + self.width * self.height // 32 + 1:
                        raise ValueError('MVE 0x06 packet lacks its complete tile map/payload')
                    self.video_packets += 1
            if kind == 5 and (amount or end != len(data)):
                raise ValueError('MVE end chunk must be empty and final')
            videos = [o for o in operations if o.opcode in (6, 16)]
            displays = [o for o in operations if o.opcode == 7]
            if len(videos) > 1 or len(displays) > 1 or displays and not videos:
                raise ValueError('MVE framing requires at most one video and display per chunk')
            maps = {o.opcode for o in operations if o.opcode in (14, 15)}
            if videos and videos[0].opcode == 16 and maps != {14, 15}:
                raise ValueError('MVE 0x10 frame requires local skip and decode maps')
            if videos and videos[0].opcode == 6 and maps:
                raise ValueError('MVE 0x06 frame cannot use external maps')
            if maps and not videos:
                raise ValueError('MVE detached decoding maps are unsupported')
            if displays:
                self.presented_chunks.append(len(self.chunks))
            self.chunks.append(_Chunk(kind, tuple(operations)))
        self.count = len(self.presented_chunks)
        if (not self.chunks or self.chunks[0].kind != 2 or self.chunks[-1].kind != 5
                or self.counts['00.0'] != 1 or not terminated):
            raise ValueError('Incomplete MVE initialization/shutdown sequence')
        if any(init_counts[o] != 1 for o in (2, 3, 5, 12)):
            raise ValueError('MVE framing requires one fixed timer, audio, video and palette initialization')
        if not 1 <= self.count <= MAX_FRAMES or not self.audio_frames:
            raise ValueError('MVE frame count/audio coverage is outside the admitted profile')
        if self.count * (self.width * self.height + 1024) > MAX_DECODED:
            raise ValueError('MVE decoded video budget exceeded')

    def nonvisual(self):
        return tuple((c.kind, tuple(o.encoded() for o in c.operations if o.opcode not in _VISUAL))
                     for c in self.chunks)

    def report(self):
        return dict(format='fdisbull-mve-inspection-1', adapter='mve', profile=PROFILE,
            source=dict(bytes=len(self.data), sha256=_sha(self.data)), width=self.width,
            height=self.height, logical_frames=self.count, video_packets=self.video_packets,
            video_codec_opcode=self.video_codec,
            frame_microseconds=self.frame_microseconds,
            duration_microseconds=self.count * self.frame_microseconds,
            duration_basis='logical presentation count times fixed timer; not measured native elapsed time',
            audio=dict(codec='pcm_u8', channels=1, sample_rate=self.sample_rate,
                       packet_count=self.audio_frames, pcm_bytes=self.audio_bytes),
            chunk_count=len(self.chunks), maximum_chunk_payload_bytes=max(self.chunk_sizes),
            operation_counts=dict(self.counts),
            full_decode=False, writer_supported=True, input_executed=False,
            framing_admission='requires complete independent decoding, bounded original-tail recovery and no source chunk growth',
            source_modified=False, executables_modified=False, native_runtime_tested=False,
            qualification='bounded old-profile container/header extents; codec and original playback not tested')


def inspect_mve_bytes(data):
    """Inspect bounded immutable old-profile MVE bytes without executing a reader."""
    return _MVE(data).report()


def inspect_mve(path):
    """Inspect an original regular file; reject links, devices and oversized inputs."""
    return inspect_mve_bytes(_snapshot(path, MAX_SOURCE))


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError('MVE decoder/framing deadline exceeded')
    return remaining


def _decoded(path, executable, arguments, deadline):
    _remaining(deadline)
    command = [executable, '-nostdin', '-hide_banner', '-v', 'error', '-max_alloc',
               str(MAX_DECODER_ALLOCATION), '-threads', '1', '-f', 'ipmovie',
               '-i', str(path), *arguments, 'pipe:1']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    diagnostic = bytearray()
    amount = 0
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ, 'output')
        selector.register(process.stderr, selectors.EVENT_READ, 'error')
        while selector.get_map():
            events = selector.select(_remaining(deadline))
            if not events:
                _remaining(deadline)
            for key, _ in events:
                block = os.read(key.fileobj.fileno(), 65536)
                if not block:
                    selector.unregister(key.fileobj)
                elif key.data == 'error':
                    diagnostic.extend(block)
                    if len(diagnostic) > 16384:
                        raise ValueError('MVE independent decoder diagnostic budget exceeded')
                else:
                    amount += len(block)
                    if amount > MAX_DECODED:
                        raise ValueError('MVE independent decoder output budget exceeded')
                    yield block
        code = process.wait(timeout=_remaining(deadline))
        if code or diagnostic:
            raise ValueError('MVE independent decoder rejected the stream: ' +
                             diagnostic.decode('utf-8', errors='replace')[:2000])
    except subprocess.TimeoutExpired as error:
        raise ValueError('MVE independent decoder deadline exceeded') from error
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


class _PixelMismatch(ValueError):
    pass


def _images(path, movie, executable, deadline, keep, *, expected=None, tail_start=None):
    size = movie.width * movie.height + 1024
    retained = {}
    hashes = []
    buffer = bytearray()
    index = 0
    args = ['-map', '0:v:0', '-an', '-sn', '-dn', '-fps_mode', 'passthrough',
            '-pix_fmt', 'pal8', '-f', 'rawvideo']
    with closing(_decoded(path, executable, args, deadline)) as blocks:
        for block in blocks:
            buffer.extend(block)
            while len(buffer) >= size:
                image = bytes(buffer[:size])
                del buffer[:size]
                if index >= movie.count:
                    raise ValueError('MVE decoder produced excessive frames')
                if index < keep or index >= movie.count - keep:
                    retained[index] = image
                if expected is not None:
                    desired = expected.get(index)
                    if desired is not None and image != desired:
                        raise _PixelMismatch(f'MVE retained pixel/palette mismatch at frame {index}')
                    if desired is None and index < tail_start and image != expected[keep - 1]:
                        raise _PixelMismatch(f'MVE hold pixel/palette mismatch at frame {index}')
                hashes.append(_sha(image))
                index += 1
    if buffer or index != movie.count:
        raise ValueError('MVE decoder produced an incomplete frame sequence')
    return retained, hashes


def _pcm(path, movie, executable, deadline):
    digest = hashlib.sha256()
    amount = 0
    args = ['-map', '0:a:0', '-vn', '-sn', '-dn', '-c:a', 'pcm_u8', '-f', 'u8']
    with closing(_decoded(path, executable, args, deadline)) as blocks:
        for block in blocks:
            digest.update(block)
            amount += len(block)
    if amount != movie.audio_bytes:
        raise ValueError('MVE decoder audio coverage differs from the admitted PCM packets')
    return dict(pcm_bytes=amount, samples_per_channel=amount, pcm_sha256=digest.hexdigest(),
                sample_rate=movie.sample_rate, channels=1, encoding='u8')


def _tail_candidates(count, keep_frames):
    # No source operation is replayed at runtime by this search: these are pure
    # bounded offline decoder trials over immutable candidate snapshots.
    limit = min(MAX_TAIL_FRAMES, count - keep_frames - 1)
    candidate = keep_frames
    values = []
    while candidate <= limit:
        values.append(candidate)
        candidate *= 2
    if values and values[-1] != limit:
        values.append(limit)
    return tuple(values)


def _encode(movie, keep_frames, tail_frames, limit, deadline):
    blocks = movie.width * movie.height // 64
    hold = b'\x00\xc0' * blocks + b'\x00'
    skip = struct.pack('<H', 1) * ((blocks + 14) // 15)
    keep_through = movie.presented_chunks[keep_frames - 1]
    tail_chunk = movie.presented_chunks[movie.count - tail_frames]
    output = bytearray(HEADER)
    holds = 0
    maximum_chunk = max(movie.chunk_sizes)
    for index, chunk in enumerate(movie.chunks):
        rewritten = keep_through < index < tail_chunk
        payload = bytearray()
        for operation in chunk.operations:
            if rewritten and operation.opcode in (14, 15):
                continue
            if rewritten and operation.opcode in (6, 16):
                if movie.video_codec == 16:
                    # Fifteen tile bits plus a sentinel per skip word. 0001
                    # means unchanged tiles. Preserve the source codec family;
                    # an old native player's bank layout can differ from a
                    # modern decoder even when the decoded pixels agree.
                    for opcode, content in ((14, skip), (15, b'\x00\x00')):
                        payload.extend(_Operation(0, opcode, 0, content).encoded())
                    body = operation.payload[:14] + b'\x00'
                else:
                    body = operation.payload[:14] + hold
                payload.extend(struct.pack('<HBB', len(body), movie.video_codec, 0) + body)
                holds += 1
            else:
                payload.extend(operation.encoded())
        if len(payload) > maximum_chunk:
            raise ValueError('Framed MVE chunk exceeds the original maximum payload extent')
        output.extend(struct.pack('<HH', len(payload), chunk.kind))
        output.extend(payload)
        if len(output) > limit:
            raise ValueError('Framed MVE exceeds output byte budget')
        _remaining(deadline)
    return bytes(output), holds, tail_chunk


def frame_mve(path, output, *, keep_frames=32, max_output_bytes=MAX_OUTPUT,
              timeout=120, ffmpeg=None):
    """Frame with exact opening/ending N images and bounded original-tail recovery.

    Native holds replace middle packets within the original homogeneous codec
    family. The ending is original source packets, never an oversized invented
    keyframe. Deterministic tail trials N,2N,4N... are capped by MAX_TAIL_FRAMES
    and non-overlap. Any needed warm-up interval is explicit: its fully decoded
    images are recorded, but are not called originals or pure holds. No output
    chunk may exceed the maximum payload extent already present in the source.
    """
    if type(keep_frames) is not int or not 1 <= keep_frames <= 64:
        raise ValueError('keep_frames must be 1..64')
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT:
        raise ValueError('max_output_bytes must be 1..67108864')
    if type(timeout) not in (int, float) or not 0 < timeout <= 600:
        raise ValueError('timeout must be positive and at most 600 seconds')
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('MVE output must be a new directory')
    if not destination.parent.is_dir():
        raise ValueError('MVE output parent must already exist')
    _private_directory(destination.parent)
    executable = shutil.which(os.fspath(ffmpeg or 'ffmpeg'))
    if not executable:
        raise ValueError('Required independent MVE decoder is unavailable')
    deadline = time.monotonic() + timeout
    data = _snapshot(path, MAX_SOURCE)
    movie = _MVE(data)
    if min(movie.count, keep_frames * 2) * (movie.width * movie.height + 1024) > MAX_RETAINED:
        raise ValueError('MVE retained-image memory budget exceeded')
    if movie.count <= keep_frames * 2:
        raise ValueError('MVE has no intermediate frame interval to replace')
    attempts = []
    with tempfile.TemporaryDirectory(prefix='.mve-check-', dir=destination.parent) as temp:
        original_path = Path(temp) / 'original.mve'
        original_path.write_bytes(data)
        images, source_hashes = _images(original_path, movie, executable, deadline, keep_frames)
        framed_path = Path(temp) / 'framed.mve'
        for tail_frames in _tail_candidates(movie.count, keep_frames):
            framed, holds, tail_chunk = _encode(movie, keep_frames, tail_frames, max_output_bytes, deadline)
            if len(framed) >= len(data):
                raise ValueError('Framing does not reduce this MVE; output refused')
            derived = _MVE(framed)
            if (movie.nonvisual() != derived.nonvisual() or movie.presented_chunks != derived.presented_chunks
                    or movie.video_packets != derived.video_packets or movie.video_codec != derived.video_codec):
                raise ValueError('MVE framing altered audio/control/palette/presentation structure')
            for left, right in zip(movie.chunks[tail_chunk:], derived.chunks[tail_chunk:]):
                if left.kind != right.kind or tuple(o.encoded() for o in left.operations) != tuple(o.encoded() for o in right.operations):
                    raise ValueError('MVE original ending packets were altered')
            framed_path.write_bytes(framed)
            tail_start = movie.count - tail_frames
            try:
                replay, replay_hashes = _images(framed_path, derived, executable, deadline, keep_frames,
                                               expected=images, tail_start=tail_start)
            except _PixelMismatch as error:
                attempts.append(dict(tail_frames=tail_frames, status='retained-image-mismatch', reason=str(error)))
                continue
            if replay != images:
                raise ValueError('MVE retained-image comparison failed')
            attempts.append(dict(tail_frames=tail_frames, status='complete-video-verified'))
            break
        else:
            raise ValueError('No bounded original MVE tail restores every retained ending image')
        audio = _pcm(original_path, movie, executable, deadline)
        if audio != _pcm(framed_path, derived, executable, deadline):
            raise ValueError('Independent MVE decoder found an audio PCM mismatch')
    if _snapshot(path, MAX_SOURCE) != data:
        raise ValueError('MVE source changed during framing')
    _remaining(deadline)
    result = dict(format='fdisbull-mve-framing-1', adapter='mve', profile=PROFILE,
        source=dict(bytes=len(data), sha256=_sha(data)),
        framed=dict(path='framed.mve', bytes=len(framed), sha256=_sha(framed)),
        saved_bytes=len(data) - len(framed), width=movie.width, height=movie.height,
        logical_frames=movie.count, video_packets=movie.video_packets,
        video_codec_opcode=movie.video_codec, codec_family_preserved=True,
        frame_microseconds=movie.frame_microseconds,
        duration_microseconds=movie.count * movie.frame_microseconds,
        duration_basis='logical presentation count times fixed timer; not measured native elapsed time',
        timer_and_presentation_schedule_preserved=True,
        retained_frame_indices=sorted(images), native_hold_packets=holds,
        retention_policy='Exact first N and last N presented images; middle native holds; any original-packet warm-up is explicit',
        retained_prefix_frames=keep_frames, retained_final_frames=keep_frames,
        original_packet_tail_frames=tail_frames, tail_search_cap_frames=MAX_TAIL_FRAMES,
        tail_search_attempts=attempts,
        pure_hold_frame_range=[keep_frames, tail_start - 1],
        warmup_frame_range=([tail_start, movie.count - keep_frames - 1] if tail_frames > keep_frames else None),
        warmup_frames_differing_from_source=[i for i in range(tail_start, movie.count - keep_frames)
                                             if replay_hashes[i] != source_hashes[i]],
        decoded_frame_pal8_sha256=replay_hashes,
        original_tail_packets_byte_identical=True,
        maximum_source_chunk_payload_bytes=max(movie.chunk_sizes),
        maximum_framed_chunk_payload_bytes=max(derived.chunk_sizes),
        chunk_payload_growth=False,
        retained_pal8_sha256={str(i): _sha(image) for i, image in images.items()},
        complete_video_decode=True, all_retained_images_and_palettes_exact=True,
        every_pure_hold_image_and_palette_exact=True,
        every_warmup_image_fully_decoded=True,
        audio_packets_byte_identical=True, audio={**audio, 'exact_pcm_match': True},
        nonvisual_operations_byte_identical_at_original_chunk=True,
        timer_and_presentation_operations_byte_identical=True, duration_changed=False,
        encoding=('Old0x06 previous-frame C000 holds; original ending packets'
                  if movie.video_codec == 6 else
                  'Old0x10 unchanged-tile skip maps; original ending packets'),
        input_executed=False, source_modified=False, executables_modified=False,
        native_runtime_tested=False, native_game_playback='not_run',
        qualification='independent-decoder-verified-framing', decoder=executable,
        decoder_max_allocation_bytes=MAX_DECODER_ALLOCATION,
        output=str(destination), manifest='mve-manifest.json',
        unknowns=['Original-game playback, seeking, audible output and whole-game behavior require separate tests.'])
    encoded = (json.dumps(result, indent=2, ensure_ascii=True) + '\n').encode()
    if len(framed) + len(encoded) > max_output_bytes:
        raise ValueError('Framed MVE and manifest exceed output byte budget')
    _remaining(deadline)
    destination.mkdir(mode=0o700)
    try:
        _private_directory(destination)
        for name, content in (('framed.mve', framed), ('mve-manifest.json', encoded)):
            with (destination / name).open('xb') as stream:
                os.chmod(stream.fileno(), 0o600)
                stream.write(content)
            _remaining(deadline)
        _remaining(deadline)
        return result
    except BaseException:
        shutil.rmtree(destination)
        raise
