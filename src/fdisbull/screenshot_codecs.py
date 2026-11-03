"""Bounded native screenshot decoding; stored screenshot artifacts stay PNG."""
import base64
import hashlib
import io

from PIL import Image

from .dosbox_rpc import DebuggerError


ENCODINGS = ('png', 'png-indexed', 'rgba-zstd')
MAX_FRAME_BYTES = 16 * 1024 * 1024


def validate_encoding(encoding, capabilities):
    if encoding not in ENCODINGS:
        raise ValueError('Screenshot encoding must be png, png-indexed or rgba-zstd')
    if encoding != 'png' and encoding not in capabilities.get('video', {}).get('screenshot_encodings', []):
        raise DebuggerError('Backend does not advertise screenshot encoding ' + encoding)
    if encoding == 'rgba-zstd':
        try:
            import zstandard  # noqa: F401
        except ImportError as error:
            raise DebuggerError('rgba-zstd screenshots require the optional fdisbull[screenshot] dependency') from error


def decode_screenshot(reply):
    """Validate wire identity and return PNG bytes plus canonical artifact metadata.

    Raw transport is separately attributed: its hash must never be substituted
    for the hash of the stored PNG. Completed-frame metadata is retained.
    """
    result = dict(reply)
    width, height = result.get('width'), result.get('height')
    if (type(width) is not int or type(height) is not int or
            not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height * 4 > MAX_FRAME_BYTES):
        raise DebuggerError('Screenshot dimensions exceed native bounds')
    raw = result.get('format') == 'rgba-zstd'
    field = 'data_base64' if raw else 'png_base64'
    try:
        payload = base64.b64decode(result.pop(field), validate=True)
    except (KeyError, ValueError, TypeError) as error:
        raise DebuggerError('Invalid screenshot payload') from error
    if hashlib.sha256(payload).hexdigest() != result.get('sha256'):
        raise DebuggerError('Screenshot signature/hash mismatch')
    if raw:
        expected = width * height * 4
        if (result.get('pixel_format') != 'RGBA8' or type(result.get('stride')) is not int or
                result['stride'] != width * 4 or type(result.get('uncompressed_bytes')) is not int or
                result['uncompressed_bytes'] != expected):
            raise DebuggerError('Invalid RGBA screenshot layout')
        try:
            import zstandard
        except ImportError as error:
            raise DebuggerError('rgba-zstd screenshots require the optional fdisbull[screenshot] dependency') from error
        try:
            frame = zstandard.get_frame_parameters(payload)
            if frame.content_size != expected or frame.window_size > MAX_FRAME_BYTES:
                raise DebuggerError('Zstandard screenshot frame exceeds declared dimensions')
            pixels = zstandard.ZstdDecompressor(max_window_size=MAX_FRAME_BYTES // 1024).decompress(
                payload, max_output_size=expected, allow_extra_data=False)
        except zstandard.ZstdError as error:
            raise DebuggerError('Invalid Zstandard screenshot frame') from error
        if len(pixels) != expected or hashlib.sha256(pixels).hexdigest() != result.get('raw_sha256'):
            raise DebuggerError('RGBA screenshot pixel identity mismatch')
        wire = {key: result[key] for key in ('format', 'sha256', 'pixel_format', 'stride',
                                           'uncompressed_bytes', 'raw_sha256')}
        wire.update(encoding='rgba-zstd', compressed_bytes=len(payload))
        image = Image.frombytes('RGBA', (width, height), pixels)
        output = io.BytesIO()
        image.save(output, format='PNG', compress_level=1)
        payload = output.getvalue()
        for key in ('pixel_format', 'stride', 'uncompressed_bytes', 'raw_sha256'):
            result.pop(key)
        result.update(format='png', encoding='png', sha256=hashlib.sha256(payload).hexdigest(), transport=wire)
    if result.get('format', 'png') != 'png' or not payload.startswith(b'\x89PNG\r\n\x1a\n'):
        raise DebuggerError('Screenshot signature/hash mismatch')
    with Image.open(io.BytesIO(payload)) as image:
        if image.size != (width, height):
            raise DebuggerError('Screenshot dimensions differ from metadata')
        image.verify()
    return payload, result
