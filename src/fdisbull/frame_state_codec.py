"""Lossless bounded deltas of opaque native payloads, never CPU/RAM undo."""
import hashlib
import json
import zlib


FORMAT = 'fdisbull-native-xor-zlib-1'
BLOCK = 64 * 1024
FIELDS = {'format', 'base_point', 'base_sha256', 'base_size', 'result_sha256',
          'result_size', 'depth', 'payload_sha256', 'descriptor_sha256', 'payload'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def descriptor(delta):
    return {key: value for key, value in delta.items() if key != 'payload'}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def retained_bytes(delta):
    return len(delta['payload']) + len(encoded(descriptor(delta)))


def rebase_depth(delta, depth):
    """A promoted keyframe changes only dependency depth, never native bytes."""
    result = dict(delta, depth=depth)
    result['descriptor_sha256'] = sha(encoded({k: v for k, v in descriptor(result).items() if k != 'descriptor_sha256'}))
    return result


def _xor(left, right, offset, size):
    a = left[offset:offset + size].ljust(size, b'\0')
    b = right[offset:offset + size].ljust(size, b'\0')
    # Each integer is at most BLOCK bytes. Keep the linear XOR in C instead
    # of paying one Python iteration per byte of a native checkpoint.
    return (int.from_bytes(a, 'little') ^ int.from_bytes(b, 'little')).to_bytes(size, 'little')


def encode(base, result, *, base_point, depth):
    """Return a delta only when payload plus its complete descriptor is smaller."""
    delta = dict(format=FORMAT, base_point=base_point, base_sha256=sha(base),
                 base_size=len(base), result_sha256=sha(result), result_size=len(result),
                 depth=depth, payload_sha256='0' * 64, descriptor_sha256='0' * 64)
    limit = len(result) - len(encoded(delta))
    if limit <= 0:
        return None
    compressor = zlib.compressobj(6)
    payload = bytearray()
    length = max(len(base), len(result))
    for offset in range(0, length, BLOCK):
        part = compressor.compress(_xor(base, result, offset, min(BLOCK, length - offset)))
        if len(payload) + len(part) >= limit:
            return None
        payload.extend(part)
    part = compressor.flush()
    if len(payload) + len(part) >= limit:
        return None
    payload.extend(part)
    delta['payload_sha256'] = sha(payload)
    delta['descriptor_sha256'] = sha(encoded({k: v for k, v in delta.items() if k != 'descriptor_sha256'}))
    delta['payload'] = bytes(payload)
    return delta


def validate(delta, *, result_sha256, result_size, max_bytes, max_depth):
    if not isinstance(delta, dict) or set(delta) != FIELDS:
        raise ValueError('Invalid native delta descriptor fields')
    if (delta['format'] != FORMAT or not isinstance(delta['payload'], bytes)
            or not isinstance(delta['base_point'], str) or not 1 <= len(delta['base_point']) <= 128):
        raise ValueError('Invalid native delta encoding')
    for name in ('base_sha256', 'result_sha256', 'payload_sha256', 'descriptor_sha256'):
        value = delta[name]
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid native delta hash')
    for name in ('base_size', 'result_size'):
        if type(delta[name]) is not int or not 1 <= delta[name] <= max_bytes:
            raise ValueError('Native delta length exceeds raw checkpoint limit')
    if type(delta['depth']) is not int or not 1 <= delta['depth'] <= max_depth:
        raise ValueError('Native delta chain depth exceeds its bound')
    if (delta['result_sha256'] != result_sha256 or delta['result_size'] != result_size
            or len(delta['payload']) > max_bytes or sha(delta['payload']) != delta['payload_sha256']
            or sha(encoded({k: v for k, v in descriptor(delta).items() if k != 'descriptor_sha256'})) != delta['descriptor_sha256']):
        raise ValueError('Native delta payload or descriptor hash mismatch')


def decode(base, delta, *, max_bytes, max_depth):
    if not isinstance(delta, dict):
        raise ValueError('Invalid native delta descriptor')
    validate(delta, result_sha256=delta.get('result_sha256'), result_size=delta.get('result_size'),
             max_bytes=max_bytes, max_depth=max_depth)
    if len(base) != delta['base_size'] or sha(base) != delta['base_sha256']:
        raise ValueError('Native delta base payload identity mismatch')
    length = max(delta['base_size'], delta['result_size'])
    decompressor = zlib.decompressobj()
    try:
        difference = decompressor.decompress(delta['payload'], length + 1)
    except zlib.error as error:
        raise ValueError('Invalid compressed native delta') from error
    if (len(difference) != length or not decompressor.eof or decompressor.unconsumed_tail
            or decompressor.unused_data):
        raise ValueError('Native delta decompression length or stream boundary mismatch')
    result = bytearray(length)
    for offset in range(0, length, BLOCK):
        size = min(BLOCK, length - offset)
        result[offset:offset + size] = _xor(base, difference, offset, size)
    del result[delta['result_size']:]
    result = bytes(result)
    if sha(result) != delta['result_sha256']:
        raise ValueError('Reconstructed native checkpoint hash mismatch')
    return result
