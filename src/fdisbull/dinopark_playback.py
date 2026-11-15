"""Explicit playback timing for the recovered original DinoPark/SBPRO route.

ABT's byte codec remains independent of playback. This profile binds its decoded
unsigned sample sequence to the original game's DigPak descriptor and the shipped
SBPRO.COM driver's default mono path. It does not execute an input, choose the
profile from its filename, or certify playback of a newly supplied resource.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import re

from .dinopark_audio import ABTAudio, MAX_OUTPUT_BYTES, MAX_SOURCE_BYTES

PLAYBACK_PROFILE = 'dinopark-digpak-sbpro-mono-v1'
CONSUMER_EXECUTABLE_SHA256 = '2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
DRIVER_SHA256 = '1e28ed9fb22880a74a98f9104fb5c0a3e5dd97002586216a3da6748721ac4730'


def _fraction(value):
    return dict(numerator=value.numerator, denominator=value.denominator)


@dataclass(frozen=True)
class ABTPlayback:
    """Immutable requested timing and separately quantized device timing."""

    profile: str
    source_sha256: str
    decoded_sha256: str
    sample_count: int
    requested_rate_hz: int
    channels: int
    dsp_time_constant: int
    nominal_duration_seconds: Fraction
    effective_device_rate_hz: Fraction
    effective_device_duration_seconds: Fraction

    def report(self):
        """Return hash-only metadata; no encoded, decoded or opaque payload."""
        return dict(
            format='fdisbull-dinopark-abt-playback-1', profile=self.profile,
            source_sha256=self.source_sha256, decoded_sha256=self.decoded_sha256,
            sample_count=self.sample_count,
            requested=dict(
                rate_hz=self.requested_rate_hz, channels=self.channels,
                sample_representation='unsigned-8-bit PCM',
                nominal_duration_seconds=_fraction(self.nominal_duration_seconds),
                timing_source='original-DigPak-consumer-profile',
            ),
            device=dict(
                driver='SBPRO.COM', play_mode='default-8-bit-mono',
                dsp_command=0x40, dsp_time_constant=self.dsp_time_constant,
                divisor_microseconds=256-self.dsp_time_constant,
                rate_model='ideal-Sound-Blaster-time-constant-clock',
                effective_rate_hz=_fraction(self.effective_device_rate_hz),
                effective_duration_seconds=_fraction(self.effective_device_duration_seconds),
                duration_scope='uninterrupted sample payload; excludes startup, stop, IRQ and mixer tails',
            ),
            consumer=dict(
                executable_sha256=CONSUMER_EXECUTABLE_SHA256,
                driver_sha256=DRIVER_SHA256,
                header_rate_offset=2, header_rate_bytes=2,
                header_byte_order='little', descriptor_frequency_offset=10,
                sample_length_offset=0, descriptor_length_offset=4,
                playback_interrupt=0x66, playback_selector=0x68b,
            ),
            qualification='recovered-original-consumer-and-driver-timing',
            current_input_native_playback_tested=False,
            host_speaker_audibility_tested=False,
            source_modified=False, input_executed=False,
            limitations=[
                'The caller explicitly selects this exact consumer/driver mono profile; byte decoding alone does not establish playback semantics.',
                'Requested WAV timing and quantized Sound Blaster device timing are distinct; rational device rates must not be rounded into a native-timing claim.',
                'Hardware/backend-specific rate limits, high-speed modes, integer rate rounding, interpolation, filtering and mixer gain are separate from this ideal DSP timer model.',
                'Dynamic stereo mode, other drivers, arbitrary rates, interrupted or looped playback, mixing and whole-game sound equivalence are outside this profile.',
                'The three other ABT header bytes remain opaque and do not select a channel count or device mode.',
                'Static recovery and separate normal-runtime observations qualify the route, not native execution or audible playback of this current input.',
            ],
        )


def bind_abt_playback(decoded, *, profile):
    """Bind a completed ABT decode to an explicitly selected timing profile.

    Original DINOPARK.EXE copies the little-endian word at ABT offset two into
    SNDSTRUC's frequency word at offset ten. Its selected SBPRO.COM consumes that
    word, in default mono mode, as an unsigned rate for DSP command 40h. The
    driver divides 1,000,000 by that rate with integer truncation and negates the
    low byte for the DSP time constant. The admitted domain keeps the divisor in
    1..256, avoiding wraparound and divide faults in unsupported header values.

    This function is metadata-only and does not change or resample PCM. A caller
    creating a WAV uses requested_rate_hz; effective_device_rate_hz is exact
    rational metadata describing the device timer, not a WAV header integer.
    """
    if type(profile) is not str or profile != PLAYBACK_PROFILE:
        raise ValueError('Unknown or unsupported DinoPark playback profile')
    if not isinstance(decoded, ABTAudio):
        raise ValueError('Playback requires a completed decoded ABT object')
    if (type(decoded.pcm_u8) is not bytes or
            type(decoded.declared_samples) is not int or
            not 1 <= decoded.declared_samples <= MAX_OUTPUT_BYTES or
            len(decoded.pcm_u8) != decoded.declared_samples or
            type(decoded.rate_field) is not int or not 0 <= decoded.rate_field <= 65535 or
            type(decoded.block_samples) is not int or not 1 <= decoded.block_samples <= 255 or
            type(decoded.opaque_header) is not bytes or len(decoded.opaque_header) != 3 or
            type(decoded.source_sha256) is not str or
            re.fullmatch(r'[0-9a-f]{64}', decoded.source_sha256) is None or
            type(decoded.consumed_bytes) is not int or
            type(decoded.encoded_bytes) is not int or
            not 9 <= decoded.consumed_bytes == decoded.encoded_bytes <= MAX_SOURCE_BYTES):
        raise ValueError('Inconsistent decoded ABT metadata cannot bind playback')
    rate = decoded.rate_field
    if not 3892 <= rate <= 65535:
        raise ValueError('ABT rate is outside the supported non-wrapping SBPRO mono timing domain')
    divisor = 1_000_000 // rate
    count = len(decoded.pcm_u8)
    return ABTPlayback(
        profile=profile, source_sha256=decoded.source_sha256,
        decoded_sha256=hashlib.sha256(decoded.pcm_u8).hexdigest(),
        sample_count=count, requested_rate_hz=rate, channels=1,
        dsp_time_constant=(256-divisor)&255,
        nominal_duration_seconds=Fraction(count, rate),
        effective_device_rate_hz=Fraction(1_000_000, divisor),
        effective_device_duration_seconds=Fraction(count*divisor, 1_000_000),
    )
