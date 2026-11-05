"""No proprietary program or game data required for these unit tests."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

CODE = Path(__file__).resolve().parents[1]/'c2_agent_harness.py'
spec=importlib.util.spec_from_file_location('c2_agent_harness', CODE)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)


class NativeActionsTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.game=self.root/'game'
        self.game.mkdir()
        for n in ('C2CDTOOL.EXE','C2CD.BAT','C2CD.gog','C2CD.ins'):
            (self.game/n).write_bytes(b'written synthetic bytes')
        (self.game/'C2CD.BAT').write_text(':start\nc2cdtool quickfades startagain\n')
        (self.game/'C2CD.ins').write_text('TRACK 01 MODE1/2352\nTRACK 02 AUDIO\n')
        self.backend=Path('/bin/true')

    def harness(self, suffix='out'):
        # Unit tests patch a known fixture digest, not a private game binary.
        old=module.EXPECTED_EXE_SHA256
        try:
            module.EXPECTED_EXE_SHA256=module.sha256(self.game/'C2CDTOOL.EXE')
            return module.Harness(game_dir=self.game,backend=self.backend,out=self.root/suffix)
        finally:
            module.EXPECTED_EXE_SHA256=old

    def test_all_actions_are_inside_declared_video_surface(self):
        self.assertGreaterEqual(len(module.ACTIONS),10)
        for name,(x,y) in module.ACTIONS.items():
            self.assertTrue(0<=x<640 and 0<=y<400,name)

    def test_map_green_class(self):
        image=Image.new('RGB',(640,400),(0,150,0))
        self.assertGreater(module.green_fraction(image),0.95)

    def test_menu_red_class(self):
        image=Image.new('RGB',(640,400),(70,25,35))
        self.assertLess(module.green_fraction(image),0.05)

    def test_black_frame_not_game_map(self):
        self.assertLess(module.green_fraction(Image.new('RGB',(640,400),'black')),0.05)

    def test_valid_dos_slot_names(self):
        for slot in ('TEST1','BENCH2','ABC12345'):
            self.assertEqual(module.validate_slot(slot),slot)

    def test_invalid_slot_names_refused(self):
        for slot in ('','abcdefghi','../SAVE','ABC.GAM','bad path','x\\x','UNIC☃'):
            with self.assertRaises(ValueError):module.validate_slot(slot)

    def test_missing_executable_refused(self):
        (self.game/'C2CDTOOL.EXE').unlink()
        with self.assertRaisesRegex(ValueError,'Missing original runtime input'):
            module.Harness(game_dir=self.game,backend=self.backend,out=self.root/'out')

    def test_original_intro_route_refused_as_fairness_guard(self):
        (self.game/'C2CD.BAT').write_text(':start\nc2cdtool quickfades firsttime\n')
        with self.assertRaisesRegex(ValueError,'startagain'):self.harness()

    def test_changed_source_executable_refused(self):
        with self.assertRaisesRegex(ValueError,'hash differs'):
            module.Harness(game_dir=self.game,backend=self.backend,out=self.root/'out')

    def test_missing_audio_track_refused(self):
        (self.game/'C2CD.ins').write_text('TRACK 01 MODE1/2352\n')
        with self.assertRaisesRegex(ValueError,'two-track'):self.harness()

    def test_existing_output_refused(self):
        out=self.root/'out';out.mkdir();(out/'anything').write_text('x')
        with self.assertRaisesRegex(ValueError,'empty'):self.harness()

    def test_pinned_source_digest_is_content_sensitive(self):
        p=self.game/'C2CD.gog';h=module.sha256(p);p.write_bytes(b'changed')
        self.assertNotEqual(h,module.sha256(p))


if __name__=='__main__':unittest.main(verbosity=2)
