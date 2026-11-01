"""Exact opaque payload identity and bounded decompression, independent of native IO."""
from copy import deepcopy
import hashlib
import json
import random
import zlib

import pytest

from fdisbull import frame_state_codec as codec


def signed(delta, payload):
    value = dict(delta, payload=payload, payload_sha256=hashlib.sha256(payload).hexdigest())
    header = {k: v for k, v in value.items() if k not in ('payload', 'descriptor_sha256')}
    value['descriptor_sha256'] = hashlib.sha256(json.dumps(header, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return value


@pytest.mark.parametrize('length', [8192, 8192-137, 8192+137])
def test_exact_binary_roundtrip_including_variable_lengths(length):
    base = bytes(range(256)) * 32
    result = bytearray((base + bytes(137))[:length])
    result[123:127] = b'\x00\xff\x81\x00'
    result = bytes(result)
    delta = codec.encode(base, result, base_point='point-0', depth=1)
    assert delta is not None and codec.retained_bytes(delta) < len(result)
    restored = codec.decode(base, delta, max_bytes=16384, max_depth=7)
    assert restored == result and hashlib.sha256(restored).digest() == hashlib.sha256(result).digest()


def test_incompressible_or_tiny_deltas_fall_back_to_complete_payloads():
    assert codec.encode(b'a', b'b', base_point='p', depth=1) is None
    rng = random.Random(7)
    assert codec.encode(rng.randbytes(8192), rng.randbytes(8192), base_point='p', depth=1) is None


@pytest.mark.parametrize('payload', [
    b'invalid-zlib', zlib.compress(bytes(8192))[:-1],
    zlib.compress(bytes(8192)) + b'extra', zlib.compress(bytes(8193)),
    zlib.compress(bytes(1024*1024)),
])
def test_even_rehashed_payloads_cannot_expand_past_declared_bounds_or_hide_extra_streams(payload):
    delta = codec.encode(bytes(8192), bytes(8192), base_point='p', depth=1)
    malformed = signed(delta, payload)
    with pytest.raises(ValueError):
        codec.decode(bytes(8192), malformed, max_bytes=8192, max_depth=7)


@pytest.mark.parametrize('field,value', [('result_size', True), ('base_size', 8193), ('depth', 8), ('base_point', ''), ('format', 'other')])
def test_malformed_descriptor_domain_is_rejected(field, value):
    delta = codec.encode(bytes(8192), bytes(8192), base_point='p', depth=1)
    bad = deepcopy(delta)
    bad[field] = value
    with pytest.raises(ValueError):
        codec.decode(bytes(8192), bad, max_bytes=8192, max_depth=7)


def test_wrong_base_is_not_a_restoration_candidate():
    base = bytes(8192)
    delta = codec.encode(base, base, base_point='p', depth=1)
    with pytest.raises(ValueError, match='base payload'):
        codec.decode(b'x'+base[1:], delta, max_bytes=8192, max_depth=7)
