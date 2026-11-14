"""Authored native PCM receipts and private output/admission boundaries."""
import base64
import copy
import hashlib
import wave

import pytest

from fdisbull.dosbox_audio import (decode_mixer_capture, start_mixer_capture,
    mixer_capture_status, stop_mixer_capture, write_mixer_wav)


def receipt():
    pcm = bytes((0, 1, 255, 254, 0, 2, 255, 253))
    return dict(session_id='owned', capture_id=1, active=False, complete=True,
        truncated=False, stop_reason='requested', max_bytes=1024, byte_count=8,
        encoding='s16le', sample_rate=44100, channels=2, bits=16,
        captured_frames=2, first_mixer_frame=100, next_mixer_frame=102,
        start_guest_ticks=10, end_guest_ticks=20, last_data_guest_ticks=19,
        source='mixer_recording_conversion', data_base64=base64.b64encode(pcm).decode(),
        sha256=hashlib.sha256(pcm).hexdigest())


def test_exact_pcm_and_observer_receipt_roundtrip_to_new_wav(tmp_path):
    raw = receipt()
    captured = decode_mixer_capture(raw, session_id='owned', capture_id=1)
    assert captured.pcm_s16le == bytes((0, 1, 255, 254, 0, 2, 255, 253))
    assert 'data_base64' not in captured.report() and not captured.report()['guest_modified']
    out = tmp_path / 'observed.wav'
    result = write_mixer_wav(captured, out)
    with wave.open(str(out), 'rb') as f:
        assert (f.getframerate(), f.getnchannels(), f.getsampwidth(), f.getnframes()) == (44100, 2, 2, 2)
        assert f.readframes(2) == captured.pcm_s16le
    assert result['capture']['source'] == 'mixer_recording_conversion'
    with pytest.raises(FileExistsError):
        write_mixer_wav(captured, out)


@pytest.mark.parametrize('changes', [
    {'session_id':'other'}, {'capture_id':2}, {'capture_id':True},
    {'active':True}, {'complete':False}, {'encoding':'u8'}, {'channels':1},
    {'max_bytes':4194308}, {'byte_count':7}, {'byte_count':12},
    {'captured_frames':3}, {'next_mixer_frame':99}, {'sample_rate':0},
    {'end_guest_ticks':9}, {'last_data_guest_ticks':21}, {'truncated':1},
    {'stop_reason':''}, {'data_base64':'?'}, {'sha256':'0'*64},
])
def test_bad_identity_extent_clock_and_payload_refuse(changes):
    raw = receipt(); raw.update(changes)
    with pytest.raises(ValueError):
        decode_mixer_capture(raw, session_id='owned', capture_id=1)


def test_truncation_is_retained_and_never_claims_game_sample_completion():
    raw = receipt(); raw.update(truncated=True, stop_reason='byte_limit')
    result = decode_mixer_capture(raw, session_id='owned', capture_id=1).report()
    assert result['complete'] and result['truncated']
    assert 'game sample identity and completion require separate checks' in result['qualification']


def test_wav_rejects_git_and_symlink_parents(tmp_path):
    captured = decode_mixer_capture(receipt(), session_id='owned', capture_id=1)
    guarded = tmp_path/'guarded'; guarded.mkdir(); (guarded/'.git').mkdir()
    with pytest.raises(ValueError):
        write_mixer_wav(captured, guarded/'capture.wav')
    alias = tmp_path/'alias'; alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        write_mixer_wav(captured, alias/'capture.wav')


def test_calls_are_single_dispatch_with_owned_session_and_capture_id():
    class RPC:
        def __init__(self): self.calls=[]
        def call(self, method, params):
            self.calls.append((method, copy.copy(params)))
            raw = receipt()
            if method.endswith('.start'): raw.update(active=True, complete=False)
            if not method.endswith('.stop'): raw.pop('data_base64')
            return raw
    rpc=RPC()
    assert start_mixer_capture(rpc, 'owned', max_bytes=1024)['capture_id'] == 1
    assert mixer_capture_status(rpc, 'owned', 1)['byte_count'] == 8
    assert stop_mixer_capture(rpc, 'owned', 1).sample_rate == 44100
    assert [m for m,p in rpc.calls] == ['audio.capture.start','audio.capture.status','audio.capture.stop']
    assert all(p['session_id']=='owned' for m,p in rpc.calls)


def test_invalid_admission_and_uncertain_requests_are_not_retried():
    class RPC:
        calls=0
        def call(self,*args): self.calls+=1; raise OSError('uncertain observation')
    rpc=RPC()
    for maximum in [0, True, 5, 4194308]:
        with pytest.raises(ValueError): start_mixer_capture(rpc,'owned',max_bytes=maximum)
    assert rpc.calls == 0
    with pytest.raises(OSError): start_mixer_capture(rpc,'owned',max_bytes=4)
    assert rpc.calls == 1
