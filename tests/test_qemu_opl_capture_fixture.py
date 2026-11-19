"""Host signal-format checks for the native OPL witnesses; no VM evidence."""
import base64
from copy import deepcopy
import json
import math
import struct

import pytest

from test_qemu_opl_native import (
    CORE4_REFUSALS, _assert_keyoff, _corrupt_checkpoint_payload,
    _corrupt_core4, _pcm_lanes, _pitches,
)


MONO = dict(rate=32000, channels=1, sample_format='u8', bytes_per_frame=1)
STEREO = dict(rate=32000, channels=2, sample_format='s16', bytes_per_frame=4)


def test_checkpoint_pcm_decoder_preserves_legacy_mono_and_signed_lane_order():
    assert _pcm_lanes(bytes([0, 128, 255]), MONO) == [[0, 128, 255]]
    raw = struct.pack('<4h', -32768, 32767, 123, -456)
    assert _pcm_lanes(raw, STEREO) == [[-32768, 123], [32767, -456]]
    assert _pcm_lanes(b'', STEREO) == [[], []]


@pytest.mark.parametrize('raw,format_override', [
    (b'\x00\x00\x00', {}),
    (b'\x00' * 4, dict(channels=1)),
    (b'\x00' * 4, dict(bytes_per_frame=2)),
    (b'\x00' * 4, dict(rate=48000)),
])
def test_checkpoint_pcm_decoder_refuses_inconsistent_geometry(raw, format_override):
    with pytest.raises(AssertionError):
        _pcm_lanes(raw, {**STEREO, **format_override})


def test_checkpoint_pitch_oracle_checks_each_signed_channel_without_byte_or_lane_mixup():
    frames = 6400
    left = [round(300 + 5000 * math.sin(2 * math.pi * 440 * n / 32000)) for n in range(frames)]
    right = [round(-200 + 3000 * math.sin(2 * math.pi * 880 * n / 32000)) for n in range(frames)]
    raw = struct.pack('<' + 'h' * (2 * frames), *(value for pair in zip(left, right) for value in pair))
    assert _pitches(raw, STEREO) == pytest.approx([440, 880], rel=0.015)


def test_checkpoint_keyoff_requires_both_signed_lanes_to_be_silent():
    _assert_keyoff(bytes([128]) * 4096, MONO)
    _assert_keyoff(bytes(4096 * 4), STEREO)
    raw = struct.pack('<' + 'h' * (4096 * 2), *(value for _ in range(4096) for value in (0, 1000)))
    with pytest.raises(AssertionError):
        _assert_keyoff(raw, STEREO)


def _authored_core4(order='<'):
    # A synthetic wire sentinel, not a native mixer snapshot. The tests below
    # qualify only the corruption builder and enclosing identity bookkeeping.
    header = bytearray(496)
    struct.pack_into(order + '6Q', header, 0, 0x4644424155443034, 4,
                     16, 1234 if order == '<' else 4321, 0, 1)
    geometry = struct.pack(order + '7Q', 32000, 2, 16, 1, int(order == '>'), 4, 128000)
    return bytes(header) + geometry + b'authored-core-body'


@pytest.mark.parametrize('order', ['<', '>'])
@pytest.mark.parametrize('damage', list(CORE4_REFUSALS))
def test_core4_corruption_changes_only_the_selected_wire_region(order, damage):
    original = _authored_core4(order)
    encoded = base64.b64encode(original).decode('ascii')
    raw = base64.b64decode(_corrupt_core4(encoded, damage), validate=True)
    if damage == 'truncated-geometry':
        assert len(raw) == 551 and raw == original[:551]
    elif damage == 'core3-with-stereo-tap':
        assert len(raw) == len(original) - 56
        assert struct.unpack_from(order + '2Q', raw) == (0x4644424155443033, 3)
        assert struct.unpack_from(order + 'Q', raw, 40)[0] == 1
        assert raw[16:496] == original[16:496] and raw[496:] == original[552:]
    else:
        geometry = list(struct.unpack_from(order + '7Q', raw, 496))
        expected = [32000, 2, 16, 1, int(order == '>'), 4, 128000]
        field, value = {'bad-rate': (0, 48000), 'bad-channels': (1, 1),
                        'bad-bytes-per-frame': (5, 2)}[damage]
        expected[field] = value
        assert geometry == expected
        assert raw[:496] == original[:496] and raw[552:] == original[552:]


@pytest.mark.parametrize('stale_state_hash', [False, True])
def test_core4_corruption_rehashes_all_envelopes_and_preserves_other_state(stale_state_hash):
    from fdisbull import qemu_dos_checkpoint as checkpoint
    state = dict(audio={'profile': 'sb16-opl', 'active': True,
        'info': dict(rate=32000, channels=2, format='s16'),
        'core-base64': base64.b64encode(_authored_core4()).decode('ascii'),
        'pcm-base64': 'AAAAAA=='}, clock=dict(epoch=7), unrelated=dict(sentinel=True))
    text = json.dumps(state)
    record = dict(state=text, sha256=checkpoint._sha(text.encode()), icount=19)
    bundle = dict(format=checkpoint.FORMAT, instrumentation=record, unrelated=dict(sentinel=23))
    metadata = dict(sidecar_sha256=checkpoint._sha(checkpoint._json(bundle)),
        instrumentation=dict(sha256=record['sha256'], audio_profile='sb16-opl'), unrelated='retained')
    machine = b'authored machine sentinel'
    data = checkpoint._archive(machine, bundle)
    before = checkpoint._sha(checkpoint._json(metadata))
    changed, changed_metadata = _corrupt_checkpoint_payload(data, metadata, 'bad-rate',
        stale_state_hash=stale_state_hash)
    decoded_machine, decoded = checkpoint._unarchive(changed)
    assert decoded_machine == machine and decoded['unrelated'] == bundle['unrelated']
    assert checkpoint._sha(checkpoint._json(metadata)) == before
    assert changed_metadata['sidecar_sha256'] == checkpoint._sha(checkpoint._json(decoded))
    actual_record = decoded['instrumentation']
    actual_hash = checkpoint._sha(actual_record['state'].encode())
    assert (actual_record['sha256'] != actual_hash) is stale_state_hash
    assert changed_metadata['instrumentation']['sha256'] == actual_record['sha256']
    assert actual_record['icount'] == record['icount']
    actual_state = json.loads(actual_record['state'])
    expected_state = deepcopy(state)
    expected_state['audio']['core-base64'] = _corrupt_core4(state['audio']['core-base64'], 'bad-rate')
    assert checkpoint._sha(checkpoint._json(actual_state)) == checkpoint._sha(checkpoint._json(expected_state))
    restored_metadata = deepcopy(changed_metadata)
    restored_metadata['sidecar_sha256'] = metadata['sidecar_sha256']
    restored_metadata['instrumentation']['sha256'] = metadata['instrumentation']['sha256']
    assert restored_metadata == metadata
