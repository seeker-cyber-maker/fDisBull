#!/usr/bin/env python3
"""Compare a source-fed collision component against a withheld SNES9x run.

The private original provides actor inputs for each rebuild; this is not an
actor-frame simulation or a claim of independent NPC movement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import canonical
from fdisbull.shadowrun_snes_field import ROM_SHA256, SNAPSHOT_SHA256, SAVE_SHA256
from fdisbull.shadowrun_snes_live import ACTOR_ARRAYS, SOURCE, machine_from_capture

CORE_SHA = '89fe8f7602428dbe532a19f098075182619c576383f177e641b19eb1f5fa19e8'
RECEIPT_SHA = 'b805b26d51dbeedfead1d4519bce74ea9c9108cdc8983a0cef90aa667fcfa44c'
OUTPUTS = {'live_heads': (0xe088, 256), 'live_records': (0xecfc, 264),
           'live_node_record': (0xef18, 1072), 'live_node_next': (0xf778, 1073),
           'live_owners': (0x1e214, 1584)}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def words(raw, offset, count):
    return [int.from_bytes(raw[i:i+2], 'little') for i in range(offset, offset+count*2, 2)]

def source_inputs(raw):
    state = {name: words(raw, offset, 44) for name, offset in ACTOR_ARRAYS.items()}
    count_word = words(raw, 0x14cc, 1)[0]
    if count_word & 1 or count_word // 2 + 1 > 44:
        raise ValueError('unsupported source actor order')
    count = count_word // 2 + 1
    state.update(live_order=words(raw, 0x14ce, count) + [0] * (44-count),
                 live_order_count=count, live_first_node=words(raw, 0xde86, 1)[0])
    return state

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('rom', 'original', 'output'):
        p.add_argument('--'+arg, required=True, type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    if out.exists() or any((x/'.git').exists() for x in (out, *out.parents)):
        raise ValueError('output must be a new private directory outside Git')
    receipt_raw = (a.original/'receipt.json').read_bytes()
    if sha(receipt_raw) != RECEIPT_SHA:
        raise ValueError('held-out receipt identity mismatch')
    r = json.loads(receipt_raw)
    rom = a.rom.read_bytes()
    save = (a.original/'save_ram.bin').read_bytes()
    if (sha(rom) != ROM_SHA256 or r['rom_sha256'] != ROM_SHA256 or
        r['core_sha256'] != CORE_SHA or r['system'] != 'snes' or r['patches'] or
        sha(save) != SAVE_SHA256 or r['save_ram_sha256'] != SAVE_SHA256 or
        r['frame_images_phase'] != 'after retro_run; frame is zero-based'):
        raise ValueError('source identity, patch, or frame phase mismatch')
    entries = {x['frame']: x for x in r['frame_ram']}
    if len(entries) != len(r['frame_ram']) or set(entries) != set(range(2999, 3061)):
        raise ValueError('held-out frame set incomplete')
    def source(frame):
        item = entries[frame]
        raw = (a.original/item['file']).read_bytes()
        if len(raw) != 131072 or sha(raw) != item['sha256']:
            raise ValueError('source frame identity mismatch')
        return raw
    initial = source(2999)
    if sha(initial) != SNAPSHOT_SHA256:
        raise ValueError('wrong captured seed')
    authoring_sha = sha(SOURCE.read_bytes())
    machine, _ = machine_from_capture(rom, initial, save)
    program_sha = sha(canonical(machine.program))
    summary = {'format': 'shadowrun-snes-source-fed-heldout-1', 'result': 'running',
               'receipt_sha256': RECEIPT_SHA, 'rom_sha256': sha(rom),
               'core_sha256': CORE_SHA, 'seed_sha256': sha(initial),
               'save_sha256': sha(save), 'authoring_sha256': authoring_sha,
               'program_sha256': program_sha, 'source_compared': 0,
               'source_elements_per_frame': sum(n for _, n in OUTPUTS.values()),
               'phase': 'actor inputs after frame N-1; collision compared after frame N',
               'scope': 'source-fed collision component; not actor evolution or NPC movement',
               'first_divergence': None}
    previous = initial
    for frame in range(3000, 3061):
        machine.set_state(source_inputs(previous))
        machine.call('shadowrun_snes_rebuild')
        state = machine.snapshot()
        if state['live_status'] != 1:
            summary.update(result='unsupported', first_divergence={'frame':frame, 'kind':'refused'})
            break
        current = source(frame)
        for name, (offset, count) in OUTPUTS.items():
            expected = (list(current[offset:offset+count]) if name == 'live_owners'
                        else words(current, offset, count))
            for index, (got, want) in enumerate(zip(state[name], expected, strict=True)):
                if got != want:
                    summary.update(result='diverged', first_divergence={
                        'frame':frame, 'field':name, 'index':index, 'model':got, 'source':want})
                    break
            if summary['first_divergence']:
                break
        if summary['first_divergence']:
            break
        summary['source_compared'] += 1
        previous = current
    else:
        summary['result'] = 'passed'
    if sha(SOURCE.read_bytes()) != authoring_sha:
        raise ValueError('model changed during comparison')
    out.mkdir(mode=0o700, parents=True)
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    if summary['result'] != 'passed':
        raise SystemExit(1)

if __name__ == '__main__':
    main()
