#!/usr/bin/env python3
"""Compare a normal party sprite clock and its first wound pass to source."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.shadowrun_party_clock import SOURCE, lift_party_clock
from fdisbull.shadowrun_player_reaction import lift_player_reaction


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    for name in ('rom', 'capture', 'output'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    root = Path(args.capture)
    receipt_hash = sha((root / 'native/receipt.json').read_bytes())
    if receipt_hash != '731cb1ec2f51c207d3acaf3443a4de0c231bd4db9922a9b7f0c57a6333858ff6':
        raise ValueError('unexpected prepared movement capture')
    cap = json.loads((root / 'capture.json').read_text())
    def frame(n):
        key = f'native/scene-{n:06d}/ram.bin'
        raw = (root / key).read_bytes()
        if len(raw) != 65536 or sha(raw) != cap['files'][key]['sha256']:
            raise ValueError(f'source frame {n} changed')
        return bytes(raw[i ^ 1] for i in range(65536))
    def word(b, i):
        return int.from_bytes(b[i:i+2], 'big')
    def long(b, i):
        return int.from_bytes(b[i:i+4], 'big')
    rom = Path(args.rom).read_bytes()
    program = lift_party_clock(rom)
    m = GameMachine(program, {0: rom})
    start = frame(5999)
    m.set_state({'shadowrun_party_kind': 3, 'shadowrun_anim_increment': word(start,0x118),
                 'shadowrun_anim_accumulator': word(start,0x11a),
                 'shadowrun_anim_threshold': word(start,0x11c),
                 'shadowrun_anim_index': word(start,0x11e)})
    for n in range(6000,6021):
        observed = frame(n)
        # Movement inputs are source outputs for this component comparison;
        # the clock itself is advanced from its own prior state.
        m.set_state({'shadowrun_party_callback': long(observed,0x13a),
                     'shadowrun_party_heading': word(observed,0x12e),
                     'shadowrun_party_transition_heading': word(observed,0x136),
                     'shadowrun_party_speed': word(observed,0x1ca),
                     'shadowrun_party_flags_low': observed[0x111]})
        m.call('shadowrun_party_pose_tick')
        if not m.snapshot()['shadowrun_party_clock_supported']:
            raise AssertionError(('pose',n))
        m.call('shadowrun_party_clock_tick'); state = m.snapshot()
        actual = tuple(state[k] for k in ('shadowrun_party_pose','shadowrun_anim_increment',
                                          'shadowrun_anim_accumulator','shadowrun_anim_index'))
        expected = tuple(word(observed,i) for i in (0x116,0x118,0x11a,0x11e))
        if not state['shadowrun_party_clock_supported'] or actual != expected:
            raise AssertionError((n,actual,expected))
    before = frame(6020); after = frame(6021); state = m.snapshot()
    reaction = GameMachine(lift_player_reaction(rom), {0: rom})
    reaction.set_state({'shadowrun_reaction_kind':3,'shadowrun_reaction_flags':before[0x110],
                        'shadowrun_reaction_flags_low':before[0x111],
                        'shadowrun_reaction_hp':after[0x14c],
                        'shadowrun_reaction_max_hp':before[0x19c],
                        'shadowrun_reaction_heading':word(after,0x12e),
                        'shadowrun_reaction_increment':state['shadowrun_anim_increment'],
                        'shadowrun_reaction_accumulator':state['shadowrun_anim_accumulator'],
                        'shadowrun_reaction_threshold':state['shadowrun_anim_threshold'],
                        'shadowrun_reaction_index':state['shadowrun_anim_index']})
    for call in ('shadowrun_reaction_start','shadowrun_reaction_advance','shadowrun_reaction_select'):
        reaction.call(call)
        if not reaction.snapshot()['shadowrun_reaction_supported']:
            raise AssertionError(call)
    rs = reaction.snapshot()
    got = tuple(rs['shadowrun_reaction_'+k] for k in ('callback','animation','increment','accumulator','index'))
    expected = (long(after,0x13a),word(after,0x116),word(after,0x118),word(after,0x11a),word(after,0x11e))
    if got != expected:
        raise AssertionError((got,expected))
    out = Path(args.output); out.mkdir(mode=0o700,parents=True)
    result = {'status':'passed','source_capture_receipt_sha256':receipt_hash,
              'source_sha256':sha(SOURCE.read_bytes()),'program_sha256':sha(canonical(program)),
              'normal_source_frames_matched':21,'reaction_first_sprite_frame_matched':6021,
              'movement_increment_at_hit':state['shadowrun_anim_increment'],
              'scope':'Assisted original capture; movement inputs supplied to clock comparison, persistent clock state model-owned. Sprite upload and whole movement parity excluded.'}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
