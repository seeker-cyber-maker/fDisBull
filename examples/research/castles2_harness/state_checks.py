"""Narrow, deterministic visible-state checks, not OCR or a strategic save parser."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from PIL import Image

DATE_ROI = (469, 315, 596, 356)
HEADER_ROI = (465, 230, 600, 249)


@dataclass(frozen=True)
class GlyphSignature:
    width: int
    height: int
    sha256: str

    def as_dict(self) -> dict:
        return asdict(self)


def glyph_signature(image: Image.Image, roi: tuple[int, int, int, int]) -> GlyphSignature:
    """Hash gold glyph shapes after trimming translation within a fixed region.

    Bounds and pixel thresholds are edition/display-specific. No recognition of
    dates, digits or other semantic values occurs. Shape equality proves only
    equality of this selected visible mask, not all game state.
    """
    if image.size != (640, 400):
        raise ValueError('Expected the admitted 640x400 original-game surface')
    if len(roi) != 4 or not (0 <= roi[0] < roi[2] <= 640 and 0 <= roi[1] < roi[3] <= 400):
        raise ValueError('Invalid fixed observation region')
    crop = image.convert('RGB').crop(roi)
    mask = Image.new('1', crop.size)
    mask.putdata([r >= 180 and g >= 155 and b <= 150
                  for r, g, b in crop.get_flattened_data()])
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError('No admitted glyph pixels in observation region')
    trimmed = mask.crop(bounds)
    return GlyphSignature(*trimmed.size, hashlib.sha256(trimmed.tobytes()).hexdigest())


def require_roundtrip(saved: GlyphSignature, changed: GlyphSignature,
                      restored: GlyphSignature) -> dict:
    """Require both a discriminating no-load control and an actual restoration."""
    if changed == saved:
        raise AssertionError('Non-discriminating control: state did not visibly change')
    if restored != saved:
        raise AssertionError('Restoration not demonstrated: saved glyphs were not restored')
    return {'changed_control_rejected': True, 'saved_visible_state_restored': True}
