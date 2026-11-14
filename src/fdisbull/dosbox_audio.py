"""Bounded mixer observations from an explicitly selected native backend.

The optional audio-capture backend overlay owns capture on the emulation thread.
These helpers never retry uncertain calls, turn on speakers, modify guest state,
or mistake a closed capture window for completed game playback.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import wave

from .output_artifacts import _private_directory

MAX_CAPTURE_BYTES = 4 * 1024 * 1024


def _uint(value, name, maximum=0xFFFFFFFFFFFFFFFF):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be an unsigned bounded integer')
    return value


def _identity(session_id, capture_id=None):
    if type(session_id) is not str or not 1 <= len(session_id) <= 256 or any(ord(c) < 32 for c in session_id):
        raise ValueError('session_id must name the owned native session')
    if capture_id is not None:
        _uint(capture_id, 'capture_id', 0xFFFFFFFF)
        if capture_id == 0:
            raise ValueError('capture_id must identify a started capture')


def start_mixer_capture(rpc, session_id, *, max_bytes=MAX_CAPTURE_BYTES):
    """Start one bounded observation while the owned original target is stopped."""
    _identity(session_id)
    _uint(max_bytes, 'max_bytes', MAX_CAPTURE_BYTES)
    if max_bytes == 0 or max_bytes % 4:
        raise ValueError('max_bytes must contain complete stereo PCM16 frames')
    result = rpc.call('audio.capture.start', dict(session_id=session_id, max_bytes=max_bytes))
    if not isinstance(result, dict) or result.get('session_id') != session_id:
        raise ValueError('Capture start response belongs to another session')
    _uint(result.get('capture_id'), 'capture_id', 0xFFFFFFFF)
    _identity(session_id, result['capture_id'])
    if result.get('active') is not True or result.get('max_bytes') != max_bytes:
        raise ValueError('Capture start response did not confirm the requested observation')
    return result


def mixer_capture_status(rpc, session_id, capture_id):
    """Read bounded metadata without transferring PCM or operating the game."""
    _identity(session_id, capture_id)
    result = rpc.call('audio.capture.status', dict(session_id=session_id, capture_id=capture_id))
    if (not isinstance(result, dict) or result.get('session_id') != session_id or
            result.get('capture_id') != capture_id or 'data_base64' in result):
        raise ValueError('Capture status identity or payload shape is invalid')
    return result


@dataclass(frozen=True)
class MixerCapture:
    session_id: str
    capture_id: int
    pcm_s16le: bytes
    sample_rate: int
    first_mixer_frame: int
    next_mixer_frame: int
    start_guest_ticks: int
    end_guest_ticks: int
    last_data_guest_ticks: int
    truncated: bool
    stop_reason: str

    def report(self):
        return dict(format='fdisbull-mixer-capture-1', session_id=self.session_id,
            capture_id=self.capture_id, sample_rate=self.sample_rate, channels=2,
            bits=16, encoding='s16le', bytes=len(self.pcm_s16le),
            sha256=hashlib.sha256(self.pcm_s16le).hexdigest(),
            captured_frames=len(self.pcm_s16le)//4, first_mixer_frame=self.first_mixer_frame,
            next_mixer_frame=self.next_mixer_frame, start_guest_ticks=self.start_guest_ticks,
            end_guest_ticks=self.end_guest_ticks, last_data_guest_ticks=self.last_data_guest_ticks,
            complete=True, truncated=self.truncated, stop_reason=self.stop_reason,
            source='mixer_recording_conversion', guest_modified=False,
            qualification='closed bounded mixer observation; game sample identity and completion require separate checks')


def decode_mixer_capture(result, *, session_id, capture_id):
    """Validate a stopped, session-bound PCM response before retaining its bytes."""
    _identity(session_id, capture_id)
    if (not isinstance(result, dict) or result.get('session_id') != session_id or
            result.get('capture_id') != capture_id or result.get('active') is not False or
            result.get('complete') is not True):
        raise ValueError('Mixer capture is not a closed observation of the expected session/id')
    _uint(result.get('capture_id'), 'capture_id', 0xFFFFFFFF)
    if (result.get('encoding') != 's16le' or result.get('channels') != 2 or
            result.get('bits') != 16 or result.get('source') != 'mixer_recording_conversion'):
        raise ValueError('Unsupported native mixer sample representation')
    maximum = _uint(result.get('max_bytes'), 'max_bytes', MAX_CAPTURE_BYTES)
    count = _uint(result.get('byte_count'), 'byte_count', maximum)
    if not maximum or maximum % 4 or count % 4:
        raise ValueError('Mixer capture does not contain complete bounded frames')
    frames = _uint(result.get('captured_frames'), 'captured_frames')
    first = _uint(result.get('first_mixer_frame'), 'first_mixer_frame')
    end = _uint(result.get('next_mixer_frame'), 'next_mixer_frame')
    if frames != count // 4 or end - first != frames:
        raise ValueError('Mixer frame counters do not match captured bytes')
    rate = _uint(result.get('sample_rate'), 'sample_rate', 192000)
    if count and not rate:
        raise ValueError('Nonempty capture has no sample rate')
    start_tick = _uint(result.get('start_guest_ticks'), 'start_guest_ticks')
    end_tick = _uint(result.get('end_guest_ticks'), 'end_guest_ticks')
    last_tick = _uint(result.get('last_data_guest_ticks'), 'last_data_guest_ticks')
    if end_tick < start_tick or count and not start_tick <= last_tick <= end_tick:
        raise ValueError('Mixer guest clock interval is inconsistent')
    truncated, reason = result.get('truncated'), result.get('stop_reason')
    if type(truncated) is not bool or type(reason) is not str or not 1 <= len(reason) <= 80:
        raise ValueError('Missing capture completion reason')
    encoded, expected = result.get('data_base64'), result.get('sha256')
    if (type(encoded) is not str or len(encoded) > 4 * ((count + 2) // 3) or
            type(expected) is not str or re.fullmatch('[0-9a-f]{64}', expected) is None):
        raise ValueError('Mixer payload length or digest is invalid')
    try:
        pcm = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError('Invalid mixer PCM encoding') from error
    if len(pcm) != count or hashlib.sha256(pcm).hexdigest() != expected:
        raise ValueError('Mixer PCM length or digest does not match its receipt')
    return MixerCapture(session_id, capture_id, pcm, rate, first, end, start_tick,
                        end_tick, last_tick, truncated, reason)


def stop_mixer_capture(rpc, session_id, capture_id):
    """Close a capture and verify its bytes; no automatic RPC retry."""
    _identity(session_id, capture_id)
    return decode_mixer_capture(rpc.call('audio.capture.stop',
        dict(session_id=session_id, capture_id=capture_id)), session_id=session_id, capture_id=capture_id)


def write_mixer_wav(capture, output):
    """Write an actual observed mixer stream to a new private WAV file."""
    if not isinstance(capture, MixerCapture) or not capture.pcm_s16le or not capture.sample_rate:
        raise ValueError('WAV export requires a nonempty closed mixer capture')
    # Recheck even manually constructed public dataclass instances.
    if (type(capture.pcm_s16le) is not bytes or len(capture.pcm_s16le) > MAX_CAPTURE_BYTES or
            len(capture.pcm_s16le) % 4 or type(capture.sample_rate) is not int or
            not 1 <= capture.sample_rate <= 192000):
        raise ValueError('Invalid bounded mixer data or sample rate')
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(output))))
    _private_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Mixer WAV output must be a new private file')
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        with wave.open(stream, 'wb') as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(capture.sample_rate)
            writer.writeframes(capture.pcm_s16le)
    return dict(path=str(destination), bytes=destination.stat().st_size,
                sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), capture=capture.report())
