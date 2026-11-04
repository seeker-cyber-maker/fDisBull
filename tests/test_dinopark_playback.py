"""Authored timing vectors for an explicitly selected original consumer."""
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import struct

import pytest

from fdisbull.dinopark_audio import decode_abt
from fdisbull.dinopark_playback import (
    PLAYBACK_PROFILE, bind_abt_playback,
)


def sample(rate=11000):
    return decode_abt(struct.pack('<HHB',4,rate,8)+b'xyz'+b'\x80\x43')


def test_requested_timing_and_quantized_device_clock_stay_distinct():
    audio=sample(11000)
    timing=bind_abt_playback(audio,profile=PLAYBACK_PROFILE)
    assert timing.requested_rate_hz==11000 and timing.channels==1
    assert timing.nominal_duration_seconds==Fraction(1,2750)
    assert timing.dsp_time_constant==166
    assert timing.effective_device_rate_hz==Fraction(100000,9)
    assert timing.effective_device_duration_seconds==Fraction(9,25000)
    # The decoded bytes remain the same; profile binding is metadata only.
    assert audio.pcm_u8==b'\x80'*4


@pytest.mark.parametrize('requested,time_constant,effective',[
    (6000,90,Fraction(500000,83)),
    (7000,114,Fraction(500000,71)),
    (10000,156,Fraction(10000)),
    (22000,211,Fraction(200000,9)),
    (3892,0,Fraction(15625,4)),
    (3906,0,Fraction(15625,4)),
    (3907,1,Fraction(200000,51)),
    (65535,241,Fraction(200000,3)),
])
def test_division_truncation_matches_original_unsigned_dsp_programming(requested,time_constant,effective):
    timing=bind_abt_playback(sample(requested),profile=PLAYBACK_PROFILE)
    assert timing.dsp_time_constant==time_constant
    assert timing.effective_device_rate_hz==effective


def test_report_hashes_opaque_data_and_declares_profile_scope():
    audio=sample()
    report=bind_abt_playback(audio,profile=PLAYBACK_PROFILE).report()
    assert report['profile']==PLAYBACK_PROFILE
    assert report['requested']['rate_hz']==11000
    assert report['requested']['channels']==1
    assert report['requested']['sample_representation']=='unsigned-8-bit PCM'
    assert report['device']['effective_rate_hz']==dict(numerator=100000,denominator=9)
    assert report['device']['effective_duration_seconds']==dict(numerator=9,denominator=25000)
    assert report['source_sha256']==audio.source_sha256
    assert report['decoded_sha256']==hashlib.sha256(audio.pcm_u8).hexdigest()
    assert report['consumer']['executable_sha256']=='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
    assert report['consumer']['driver_sha256']=='1e28ed9fb22880a74a98f9104fb5c0a3e5dd97002586216a3da6748721ac4730'
    assert not report['current_input_native_playback_tested']
    assert not report['host_speaker_audibility_tested']
    assert not report['source_modified'] and not report['input_executed']
    encoded=json.dumps(report)
    assert 'xyz' not in encoded and 'pcm_u8' not in encoded and 'data_base64' not in encoded
    assert 'opaque_header_hex' not in encoded


@pytest.mark.parametrize('rate',[0,1,16,3891])
def test_rates_that_wrap_the_supported_device_divisor_refuse(rate):
    with pytest.raises(ValueError,match='rate'):
        bind_abt_playback(sample(rate),profile=PLAYBACK_PROFILE)


@pytest.mark.parametrize('profile',['',None,True,'other-driver','dinopark-digpak-sbpro-stereo-v1'])
def test_unknown_or_implicit_profiles_refuse(profile):
    with pytest.raises(ValueError,match='profile'):
        bind_abt_playback(sample(),profile=profile)


def test_profile_must_be_explicit():
    with pytest.raises(TypeError):bind_abt_playback(sample())


@pytest.mark.parametrize('changes',[
    dict(pcm_u8=bytearray(b'\x80'*4)),dict(pcm_u8=b''),dict(declared_samples=3),
    dict(declared_samples=True),dict(rate_field=True),dict(rate_field=65536),
    dict(block_samples=0),dict(opaque_header=b''),dict(source_sha256='fake'),
    dict(consumed_bytes=0),dict(encoded_bytes=100),
])
def test_forged_decoded_metadata_cannot_silently_bind(changes):
    with pytest.raises(ValueError,match='decoded'):
        bind_abt_playback(replace(sample(),**changes),profile=PLAYBACK_PROFILE)


def test_foreign_object_cannot_supply_playback_fields():
    with pytest.raises(ValueError,match='decoded'):
        bind_abt_playback(object(),profile=PLAYBACK_PROFILE)
