#!/usr/bin/env python3
"""Compare existing internal Zork providers with the new read-only debugger probe.

Uses caller-owned private story and generated IR/scene packages. Output contains
aggregate counts and hashes only. This does not run or qualify ScummVM, Frotz or
DOSBox, and it is not evidence of whole-game equivalence.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import time
import sys

from fdisbull.zmachine_probe import StoryBinding, make_word16_probe, compare_prompt_states
from fdisbull_player.word16 import Word16Runtime, load_program
from fdisbull_player.scene_runtime import SceneRuntime, load_package

# Reuse the repository's authored bounded house/window regression input cases.
HOUSE_CASE = ['open mailbox', 'open mailbox', 'take leaflet', 'close mailbox', 'open mailbox',
              'southwest', 'east', 'north', 'east', 'in', 'open window', 'in', 'out',
              'south', 'west', 'open mailbox']
WINDOW_CASE = ['north', 'east', 'examine window', 'in',
               'close window', 'close window', 'close window', 'close window',
               'examine window', 'open window', 'open window', 'in',
               'close window', 'out', 'close window', 'close window',
               'open window', 'out', 'open window', 'close window', 'open it',
               'examine window', 'look through window', 'in', 'close window',
               'open window', 'out']


class GuardedSceneRuntime(SceneRuntime):
    """Trap retained IR for behavior the existing semantic layer claims replaced."""
    def __init__(self, *args, **kwargs):
        self.forbidden_ir = set()
        super().__init__(*args, **kwargs)

    def _record_low_level_block(self, pc, binding=None):
        if pc in self.forbidden_ir:
            raise AssertionError(f'Recovered behavior fell back to original IR at {pc:#x}')
        return super()._record_low_level_block(pc, binding=binding)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def game_result(result):
    excluded = {'steps', 'recovery', 'scene_recovery', 'revision', 'stop_reason', 'host_timeout_scope'}
    return {key: value for key, value in result.items() if key not in excluded}


def check(story_path, program_path, scene_path, *, seed=12, case="all", checkpoint_receipt=None):
    story = story_path.read_bytes()
    binding = StoryBinding(story)
    print('Loading private IR', file=sys.stderr, flush=True)
    program = load_program(program_path)
    print('Loading private scene package', file=sys.stderr, flush=True)
    package = load_package(scene_path)
    if package['base_intents']['low_level_ir'] != program:
        raise ValueError('Scene package must preserve the exact supplied low-level IR')
    rows = []
    for name, commands in (('house', HOUSE_CASE), ('window', WINDOW_CASE)):
        if case != 'all' and name != case:
            continue
        print(f'{name}: initializing providers', file=sys.stderr, flush=True)
        baseline = Word16Runtime(program, seed=seed)
        scene = GuardedSceneRuntime(package, seed=seed)
        probe = make_word16_probe(program, story, seed=seed, trace_capacity=256)
        if name == 'house':
            scene.forbidden_ir.update(pc for site in package['udl']['dispatch']['sites']
                                      for pc in site['source_pcs'])
            scene.forbidden_ir.update(package['udl']['selection']['source_operations'].values())
            scene.forbidden_ir.update(package['udl']['movement']['source_operations'])
        window_blocks = {pc for key in ('callback', 'helper', 'selection')
                         for pc in package['udl']['interaction'][key]['source_pcs']}
        print(f'{name}: comparing prompt boundaries', file=sys.stderr, flush=True)
        compared = []
        for index, command in enumerate([None, *commands]):
            if name == 'window':
                scene.forbidden_ir.difference_update(window_blocks)
                if command and command.startswith(('open ', 'close ')):
                    scene.forbidden_ir.update(window_blocks)
            results = []
            for engine in (baseline, scene, probe):
                result = engine.run(1000000) if command is None else engine.command(command, 1000000)
                if result['status'] != 'input':
                    raise AssertionError(f'{name} boundary {index}: input not reached')
                results.append(result)
            state = baseline.snapshot()
            same_result = all(game_result(result) == game_result(results[0]) for result in results[1:])
            same_state = state == scene.low_level_snapshot() == probe.snapshot()
            projections = [binding.projection(bytes(engine.memory), input_pending=engine.pending_input is not None,
                                              text=result['text'], command_index=index)
                           for engine, result in zip((baseline, scene, probe), results)]
            projections_equal = all(compare_prompt_states(projections[0], item)['matched']
                                    for item in projections[1:])
            if not (same_result and same_state and projections_equal):
                raise AssertionError(f'{name} boundary {index}: provider mismatch; private diagnosis required')
            compared.append({'index': index, 'result_equal': same_result,
                             'full_state_equal': same_state, 'prompt_projection_equal': projections_equal,
                             'state_sha256': digest(state)})
        # A baseline checkpoint can restore the probe because its execution
        # continuation belongs to the unchanged consumer, not a new VM format.
        checkpoint = baseline.snapshot()
        saved_revision = probe.revision
        probe.command('inventory', 1000000, expected_revision=saved_revision)
        probe.restore(checkpoint)
        if probe.snapshot() != checkpoint or probe.revision <= saved_revision:
            raise AssertionError('Checkpoint restore or stale-input revision failed')
        rows.append({'case': name, 'commands': len(commands), 'boundaries': len(compared),
                     'all_results_equal': True, 'all_full_states_equal': True,
                     'all_prompt_projections_equal': True,
                     'baseline_checkpoint_restored_to_probe': True,
                     'semantic_scene_stats': deepcopy(scene.scene_stats),
                     'semantic_intent_stats': deepcopy(scene.recovery_stats),
                     'semantic_ir_fallback_traps_enabled': True,
                     'boundary_evidence_sha256': digest(compared),
                     'final_full_state_sha256': digest(checkpoint)})
        if checkpoint_receipt is not None:
            checkpoint_receipt(rows[-1])
        print(f'{name}: {len(compared)} boundaries matched', file=sys.stderr, flush=True)
        del baseline, scene, probe
    if story_path.read_bytes() != story:
        raise AssertionError('Original story changed')
    return {'format': 'fdisbull-zmachine-internal-comparison-1',
            'story': binding.identity(), 'file_bytes': len(story),
            'providers': ['unchanged-word16', 'existing-scene-intents', 'word16-debugger-probe'],
            'seed': seed, 'cases': rows, 'commands': sum(r['commands'] for r in rows),
            'boundaries': sum(r['boundaries'] for r in rows), 'original_unchanged': True,
            'native_scummvm_run': False, 'fresh_original_dos_or_frotz_run': False,
            'claim': 'Same-ancestry model/probe regressions, not independent original-to-model equivalence'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--story', type=Path, required=True)
    parser.add_argument('--ir', type=Path, required=True)
    parser.add_argument('--scenes', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=('all', 'house', 'window'), default='all')
    args = parser.parse_args()
    # Never overwrite a receipt or any input, even when its suffix is unexpected.
    if args.output.exists():
        parser.error('Output must be a new file')
    started = time.monotonic()
    result = check(args.story, args.ir, args.scenes, case=args.case)
    result['host_elapsed_seconds'] = round(time.monotonic() - started, 3)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'commands': result['commands'], 'boundaries': result['boundaries'],
                      'all_matched': True, 'native_scummvm_run': False, 'receipt': str(args.output)}))


if __name__ == '__main__':
    main()
