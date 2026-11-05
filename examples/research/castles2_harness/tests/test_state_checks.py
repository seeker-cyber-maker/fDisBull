"""Authored image controls only; no proprietary screenshots or saved games."""
import sys
from pathlib import Path
import unittest
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from state_checks import DATE_ROI, glyph_signature, require_roundtrip
from c2_agent_harness import green_fraction


def fixture(shift=0, changed=False, background=(60,32,8)):
    im=Image.new('RGB',(640,400),(0,150,0))
    draw=ImageDraw.Draw(im)
    draw.rectangle(DATE_ROI,fill=background)
    draw.rectangle((478,323+shift,485,333+shift),fill=(243,231,93))
    draw.rectangle((489,325+shift,494,330+shift),fill=(243,231,93))
    if changed:
        draw.rectangle((498,326+shift,501,330+shift),fill=(243,231,93))
    return im


class StateChecks(unittest.TestCase):
    def test_slide_translation_not_semantic_change(self):
        self.assertEqual(glyph_signature(fixture(),DATE_ROI), glyph_signature(fixture(shift=6),DATE_ROI))
    def test_changed_visible_value_is_rejected(self):
        self.assertNotEqual(glyph_signature(fixture(),DATE_ROI),glyph_signature(fixture(changed=True),DATE_ROI))
    def test_background_texture_not_part_of_glyph_identity(self):
        self.assertEqual(glyph_signature(fixture(),DATE_ROI),glyph_signature(fixture(background=(89,48,20)),DATE_ROI))
    def test_blank_is_unknown_not_success(self):
        with self.assertRaises(ValueError):glyph_signature(Image.new('RGB',(640,400),'black'),DATE_ROI)
    def test_wrong_resolution_refused(self):
        with self.assertRaises(ValueError):glyph_signature(Image.new('RGB',(800,600)),DATE_ROI)
    def test_unsafe_region_refused(self):
        for roi in [(-1,0,640,400),(0,0,641,400),(10,0,5,20)]:
            with self.assertRaises(ValueError):glyph_signature(fixture(),roi)
    def test_non_discriminating_control_refused(self):
        same=glyph_signature(fixture(),DATE_ROI)
        with self.assertRaisesRegex(AssertionError,'Non-discriminating'):require_roundtrip(same,same,same)
    def test_omitted_load_fails_despite_green_map(self):
        a=glyph_signature(fixture(),DATE_ROI); b=glyph_signature(fixture(changed=True),DATE_ROI)
        self.assertGreater(green_fraction(fixture()),.5)
        self.assertGreater(green_fraction(fixture(changed=True)),.5)
        with self.assertRaisesRegex(AssertionError,'Restoration not demonstrated'):require_roundtrip(a,b,b)
    def test_positive_roundtrip(self):
        a=glyph_signature(fixture(),DATE_ROI); b=glyph_signature(fixture(changed=True),DATE_ROI)
        self.assertTrue(require_roundtrip(a,b,a)['saved_visible_state_restored'])

if __name__=='__main__':unittest.main()
