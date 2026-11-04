#!/usr/bin/env python3
"""Repeat the actual DOS Save/Load route with dialog and visible-state guards.

Uses the existing private-copy original-DOS controller. No game assets included.
Frozen UI fingerprints are derived from explicitly inspected original screens.
Unknown/transitioning screens refuse rather than triggering guessed actions.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from c2_agent_harness import Harness, sha256, validate_slot
from state_checks import DATE_ROI, HEADER_ROI, GlyphSignature, glyph_signature, require_roundtrip

# Hashes only, no original pixel payloads. These qualify this exact edition and
# rendering setup, not other languages, palettes, editions or arbitrary games.
SCENES = {
    'options': GlyphSignature(58, 16, '4fcdf3ea8dfc53de6c7d027b29036feafa820386bad556d05b29bcf10ec2ff76'),
    'load': GlyphSignature(86, 12, '3d7b3f05d3ab53b037c204a77f063972cb5c530ed736f8310bd55d2fddbf9fd4'),
    'save': GlyphSignature(86, 12, '066ec731b724b355f1f3c0a68fcde3cc1f29f72655a02cb41357551b1bae5a72'),
    'stock': GlyphSignature(129, 15, '857e12961ae2dc8383c6cb700a0d7b636777e8a865d4dcb1013be855280bab44'),
}


class GuardedHarness(Harness):
    def wait_scene(self, names, timeout=8):
        """Require two matching observations, bounded to this owner's screen."""
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            image = self.screenshot('guard-scene')
            try:
                signature = glyph_signature(image, HEADER_ROI)
            except ValueError:
                signature = None
            state = next((name for name in names if SCENES[name] == signature), None)
            if state is not None and previous == state:
                self.event('guarded_scene', scene=state)
                return state, image
            previous = state
            time.sleep(.15)
        raise AssertionError('Required scene did not settle: ' + ','.join(names))

    def ensure_options(self):
        state, _ = self.wait_scene(('stock', 'options'))
        if state == 'stock':
            self.click('map.opts')
            self.wait_scene(('options',))
        else:
            self.event('action_reused', action_name='map.opts', reason='already open; do not toggle')

    def save_guarded(self, slot):
        slot = validate_slot(slot.upper())
        path = self.game / (slot + '.GAM')
        if path.exists():
            raise ValueError('Refuse to overwrite an existing save')
        self.ensure_options()
        self.click('opts.save')
        self.wait_scene(('save',))
        self.xinput.type_ascii(slot)
        self.click('save.ok')
        self.wait_scene(('stock',))
        if not path.is_file() or path.stat().st_size != 11733:
            raise AssertionError('Expected original 11,733-byte save not produced')
        self.event('guarded_save', basename=path.name, bytes=path.stat().st_size, sha256=sha256(path))
        return path

    def load_guarded(self, slot, expected: GlyphSignature, *, from_main=False):
        slot = validate_slot(slot.upper())
        path = self.game / (slot + '.GAM')
        saves = sorted(p for p in self.game.iterdir() if p.suffix.casefold() == '.gam')
        if len(saves) != 1 or saves[0].name.casefold() != path.name.casefold():
            raise ValueError('Only one exact pinned save is admitted for first-row selection')
        before = sha256(path)
        if from_main:
            self.click('main.game')
            # Existing title/configuration route; dialog readiness is checked next.
            time.sleep(.6)
            self.click('game.load')
        else:
            self.ensure_options()
            self.click('opts.load')
        self.wait_scene(('load',))
        self.click('load.first')
        self.click('load.ok')
        _, image = self.wait_scene(('stock',))
        restored = glyph_signature(image, DATE_ROI)
        if restored != expected:
            raise AssertionError('Load returned but the saved visible date was not restored')
        if sha256(path) != before:
            raise AssertionError('Read-only load modified the save file')
        self.screenshot('fresh-date-restored' if from_main else 'same-date-restored')
        self.event('guarded_load', from_main=from_main, date=restored.as_dict(), save_unchanged=True)
        return restored

    def advance_date(self, original, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _, image = self.wait_scene(('stock',), timeout=max(.5, deadline-time.monotonic()))
            stamp = glyph_signature(image, DATE_ROI)
            if stamp != original:
                self.screenshot('changed-date-negative-control')
                self.event('changed_date_observed', date=stamp.as_dict())
                return stamp
            time.sleep(.4)
        raise AssertionError('No discriminating date change occurred in the bounded wait')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--backend', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--display', default=':109')
    parser.add_argument('--slot', default='GUARD1')
    args = parser.parse_args()
    h = GuardedHarness(game_dir=args.game_dir, backend=args.backend, out=args.output, display=args.display)
    receipt = {'format':'castles2-guarded-visible-state-study-1', 'status':'failed',
               'scope':'Original UI, one save, and visible date; not complete state or cold-agent A/B'}
    try:
        h.start_game()
        h.from_main_play()
        h.wait_scene(('stock',))
        # Reproduce the old harness's bad entry precondition deliberately.
        h.ensure_options()
        save = h.save_guarded(args.slot)  # Must reuse already-open options.
        _, image = h.wait_scene(('stock',))
        saved = glyph_signature(image, DATE_ROI)
        h.screenshot('saved-date')
        changed = h.advance_date(saved)
        try:
            require_roundtrip(saved, changed, changed)  # Omitted-load negative.
        except AssertionError:
            receipt['no_load_negative_rejected'] = True
        else:
            raise AssertionError('No-load negative was incorrectly accepted')
        restored = h.load_guarded(args.slot, saved)
        receipt['roundtrip'] = require_roundtrip(saved, changed, restored)
        h.stop_game()
        h.start_game()
        h.load_guarded(args.slot, saved, from_main=True)
        receipt.update(status='passed', saved_date=saved.as_dict(), changed_date=changed.as_dict(),
                       save_bytes=save.stat().st_size, save_sha256=sha256(save), fresh_process_restored=True)
    except Exception as exc:
        receipt['error'] = {'type':type(exc).__name__, 'message':str(exc)}
        raise
    finally:
        h.stop()
        receipt['elapsed_seconds'] = round(time.monotonic()-h.t0, 3)
        receipt['events'] = h.events
        (h.out/'guarded-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='events'}, indent=2))


if __name__ == '__main__':
    main()
