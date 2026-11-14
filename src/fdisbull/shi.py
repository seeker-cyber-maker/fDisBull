"""Bounded Sherlock 1.50 SHI codec; no original images are bundled.

The supported profile is exactly 46 32x32 four-plane records. The palette and
record roles come from the qualified game profile, not fields in the SHI file.
See the packaged references/media-modules.md specification.
"""
from __future__ import annotations

from io import BytesIO

WIDTH = HEIGHT = 32
IMAGE_COUNT = 46
HEADER = b'\x04\x00\x01\x00\x20\x00\x20\x00'
RECORD_SIZE = 520
FILE_SIZE = IMAGE_COUNT * RECORD_SIZE
PIXEL_COUNT = WIDTH * HEIGHT
PROFILE = 'sherlock-1.50-46x32x32'

# Observed game palette: SHI stores only four-bit indices, never RGB values.
PALETTE = (
    (0, 0, 0), (85, 85, 85), (170, 85, 0), (255, 0, 0),
    (255, 170, 0), (255, 255, 0), (0, 255, 0), (0, 255, 170),
    (0, 170, 255), (0, 0, 255), (170, 0, 170), (170, 85, 255),
    (255, 0, 170), (255, 170, 170), (170, 170, 170), (255, 255, 255),
)
OVERLAYS = (
    ('not', 37, 38), ('between-left', 39, 40),
    ('between-middle', 41, 42), ('between-right', 43, 44),
)


def _fixed_bytes(value, size, label):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f'{label} must be bytes-like')
    if memoryview(value).nbytes != size:
        raise ValueError(f'{label} must be exactly {size} bytes')
    return bytes(value)


def decode_shi(payload):
    """Return 46 immutable 1024-byte row-major indexed images.

    Reject other lengths and every unsupported record header before decoding.
    All four-bit pixel values are legal, including mask and ink records.
    """
    data = _fixed_bytes(payload, FILE_SIZE, 'Sherlock SHI profile')
    for image_id in range(IMAGE_COUNT):
        offset = image_id * RECORD_SIZE
        if data[offset:offset + len(HEADER)] != HEADER:
            raise ValueError(f'Unsupported Sherlock SHI record header at image {image_id}')
    images = []
    for image_id in range(IMAGE_COUNT):
        pixels = bytearray(PIXEL_COUNT)
        offset = image_id * RECORD_SIZE + len(HEADER)
        for y in range(HEIGHT):
            for x in range(WIDTH):
                pixels[y * WIDTH + x] = sum(
                    ((data[offset + y * 16 + plane * 4 + x // 8]
                      >> (7 - x % 8)) & 1) << plane for plane in range(4)
                )
        images.append(bytes(pixels))
    return tuple(images)


def encode_shi(images):
    """Encode exactly 46 complete indexed images into the supported profile.

    Accept a list/tuple of bytes-like images, each 1024 bytes with values 0..15.
    No quantization, palette conversion, prefix encoding or input mutation occurs.
    """
    if not isinstance(images, (list, tuple)) or len(images) != IMAGE_COUNT:
        raise ValueError('Sherlock SHI encoding requires exactly 46 images')
    pixels = tuple(_fixed_bytes(item, PIXEL_COUNT, f'Image {image_id}')
                   for image_id, item in enumerate(images))
    for image_id, item in enumerate(pixels):
        if max(item) > 15:
            raise ValueError(f'Image {image_id} contains a palette index outside 0..15')
    data = bytearray(FILE_SIZE)
    for image_id, item in enumerate(pixels):
        offset = image_id * RECORD_SIZE
        data[offset:offset + len(HEADER)] = HEADER
        for y in range(HEIGHT):
            for x in range(WIDTH):
                value = item[y * WIDTH + x]
                for plane in range(4):
                    at = offset + len(HEADER) + y * 16 + plane * 4 + x // 8
                    data[at] |= ((value >> plane) & 1) << (7 - x % 8)
    return bytes(data)


def image_metadata(image_id):
    """Describe a stable zero-based record ID in the qualified game profile."""
    if type(image_id) is not int or not 0 <= image_id < IMAGE_COUNT:
        raise ValueError('SHI image ID must be 0..45')
    result = dict(image_id=image_id, width=WIDTH, height=HEIGHT,
                  pixel_format='indexed4', decoded_size=PIXEL_COUNT)
    if image_id < 36:
        result.update(role='game-item', row=image_id // 6, item=image_id % 6)
    elif image_id == 36:
        result['role'] = 'empty-tile'
    elif image_id == 45:
        result.update(role='separator', marker='left-of')
    else:
        for marker, mask_id, ink_id in OVERLAYS:
            if image_id in (mask_id, ink_id):
                result.update(role='mask' if image_id == mask_id else 'ink',
                              marker=marker, mask_id=mask_id, ink_id=ink_id)
                break
    return result


def profile_metadata():
    """Return fresh JSON-safe palette/role provenance, without source pixels."""
    return dict(
        profile=PROFILE, image_count=IMAGE_COUNT,
        record_header_words=[4, 1, 32, 32],
        palette=dict(format='rgb8', colors=[list(color) for color in PALETTE],
                     source='qualified-sherlock-1.50-game-profile', embedded=False),
        compositing=dict(domain='four-bit-palette-indices',
                         operation='(destination & mask) | ink',
                         alpha_compositing=False,
                         pairs=[dict(marker=marker, mask_id=mask, ink_id=ink)
                                for marker, mask, ink in OVERLAYS]),
        half_size_sampling=dict(width=16, height=16,
                                source_coordinates='(2*x, 2*y)', interpolation=False),
        extract_all_member='all',
    )


def _png_payload(pixels):
    """Encode validated indices; preserve mask bits, palette order and no alpha."""
    from PIL import Image

    image = Image.frombytes('P', (WIDTH, HEIGHT), pixels)
    image.putpalette([component for color in PALETTE for component in color])
    output = BytesIO()
    image.save(output, format='PNG', bits=4, optimize=False, compress_level=9)
    return output.getvalue()
