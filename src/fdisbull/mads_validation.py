#!/usr/bin/env python3
"""Validate caller-owned HAG resources; write only aggregate/hash receipts.

Media decoding is independent of the processor. --synthetic-model additionally
runs dialogs with explicitly synthetic zero variables and all-one RNG draws.
It does not reproduce native state, render gameplay or establish equivalence.
"""
from __future__ import annotations
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import struct

from fdisbull.mads_resources import HagArchive, MadsPack, read_cnd
from fdisbull.mads_media import (decode_sprites, decode_tiles, decode_background,
    decode_dsr, decode_font, decode_mask, decode_animation)



def companion(archive, name, receipts):
    """Select by explicit indices; accept duplicates only after full byte equality.

    The ordinary HAG API still refuses ambiguous names. This corpus harness
    records every identical occurrence rather than silently building a name map.
    """
    matches = [entry for entry in archive.members if entry.name.casefold() == name.casefold()]
    if not matches:
        raise ValueError('Companion resource is absent: ' + name)
    values = [archive.select(entry.index)[1] for entry in matches]
    if any(value != values[0] for value in values[1:]):
        raise ValueError('Companion resource has conflicting duplicate contents: ' + name)
    if len(matches) > 1:
        receipt = dict(archive_sha256=sha256(archive.source).hexdigest(), name=name,
                       indices=[entry.index for entry in matches],
                       resource_sha256=sha256(values[0]).hexdigest(), comparison='full-byte-equality')
        if receipt not in receipts:
            receipts.append(receipt)
    return values[0]


def validate(resources, *, synthetic_model=False):
    counts = Counter(); errors = []; sources = []; states = []; duplicates = []
    files = sorted(p for p in Path(resources).iterdir() if p.suffix.casefold() == '.hag')
    if not files: raise ValueError('No HAG inputs in selected directory')
    for file in files:
        archive = HagArchive.read(file)
        sources.append(dict(name=file.name, sha256=sha256(archive.source).hexdigest(),
                            size=len(archive.source), members=len(archive.members)))
        counts['archives'] += 1
        for entry in archive.members:
            ext = Path(entry.name).suffix.upper()
            raw = archive.source[entry.offset:entry.offset+entry.size]
            try:
                if ext == '.SS':
                    items, _ = decode_sprites(raw)
                    counts['sprite_resources'] += 1; counts['sprite_frames'] += len(items)
                    counts['empty_sprite_frames'] += sum(not item.pixels for item in items)
                elif ext.startswith('.TT') and (ext == '.TT' or ext[3:].isdigit()):
                    depth = ext != '.TT'
                    items, _ = decode_tiles(raw, depth=depth)
                    counts['depth_resources' if depth else 'picture_resources'] += 1
                    counts['depth_tiles' if depth else 'picture_tiles'] += len(items)
                    if not items: counts['empty_tile_resources'] += 1
                    else:
                        map_data = companion(archive, Path(entry.name).stem+'.MM'+ext[3:], duplicates)
                        decode_background(raw, map_data, depth=depth)
                        counts['depth_maps' if depth else 'backgrounds'] += 1
                elif ext == '.DSR':
                    items, _ = decode_dsr(raw)
                    counts['audio_banks'] += 1; counts['audio_samples'] += len(items)
                    counts['pcm_bytes'] += sum(len(item.pcm) for item in items)
                elif ext == '.FF':
                    items, _ = decode_font(raw)
                    counts['font_resources'] += 1; counts['glyph_planes'] += len(items)
                elif ext == '.AA':
                    decode_animation(raw); counts['animation_records'] += 1
                    if MadsPack.read(raw).version == '1.0': counts['legacy_animation_resources'] += 1
                elif ext.startswith(('.WW', '.PP')):
                    map_data = companion(archive, entry.name.split('.')[0]+'.MM', duplicates)
                    h = MadsPack.read(map_data).sections[0].data
                    nx, ny, width, height = struct.unpack_from('<4H', h, 4)
                    image, _ = decode_mask(raw, width=nx*width, height=ny*height)
                    counts['mask_resources'] += 1; counts['mask_pixels'] += len(image.pixels)
                elif ext == '.CNV' and synthetic_model:
                    from fdisbull.mads_processor import Conversation
                    from fdisbull.mads_runtime import ConversationRuntime
                    defaults = companion(archive, entry.name[:-4]+'.CND', duplicates)
                    conversation = Conversation.read(raw); metadata = read_cnd(defaults)
                    counts['conversation_resources'] += 1
                    # Every dialog still starts with the same explicit synthetic
                    # initial state. Reuse immutable resource parsing rather than
                    # decompressing the entire CNV/CND pair for each dialog.
                    model = ConversationRuntime(raw, defaults,
                        external_values={i: 0 for i in range(metadata['variable_count'])},
                        random_tape=[1]*1024)
                    initial = model.snapshot()
                    for index in range(len(conversation.dialogs)):
                        model.restore(initial)
                        model.start_dialog(index); checkpoint = model.snapshot()
                        result = model.run(max_steps=10000, timeout_ms=1000)
                        if result['stop_reason'] != 'done': raise ValueError('Model did not finish within budget')
                        after = model.snapshot()
                        model.restore(checkpoint); repeated = model.run(max_steps=10000, timeout_ms=1000)
                        if repeated['stop_reason'] != 'done' or model.snapshot() != after:
                            raise ValueError('Model checkpoint replay differed')
                        counts['model_dialogs'] += 1; counts['model_replays'] += 1
                        counts['model_dispatches'] += result['completed_dispatches']
                        counts['model_rng_draws'] += after['rng_position']
                        states.append(sha256(json.dumps(after,sort_keys=True).encode()).hexdigest())
                else:
                    counts['outside_selected_decode_scope'] += 1
            except (ValueError, OSError, struct.error) as error:
                errors.append(dict(archive=file.name, index=entry.index, name=entry.name, error=str(error)))
        if sha256(file.read_bytes()).hexdigest() != sources[-1]['sha256']:
            raise ValueError('Source changed during corpus validation')
    return dict(format='fdisbull-mads-corpus-check-1', counts=dict(counts), errors=errors,
                sources=sources, equivalent_duplicate_companions=duplicates, model_state_digest=sha256(''.join(states).encode()).hexdigest(),
                synthetic_model=synthetic_model, model_inputs='all-zero explicit variables, all-one inclusive RNG tape',
                original_engine_equivalence=False, all_requested_decodes_passed=not errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--synthetic-model', action='store_true')
    args = parser.parse_args()
    from fdisbull.output_artifacts import _private_directory
    _private_directory(args.output.parent)
    if args.output.exists() or args.output.is_symlink(): parser.error('Output must be a new file')
    result = validate(args.resources, synthetic_model=args.synthetic_model)
    with args.output.open('x', encoding='utf-8') as stream:
        import os
        os.chmod(stream.fileno(),0o600)
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(counts=result['counts'], errors=len(result['errors']),
                          original_engine_equivalence=False)))
    return int(bool(result['errors']))


if __name__ == '__main__': raise SystemExit(main())
