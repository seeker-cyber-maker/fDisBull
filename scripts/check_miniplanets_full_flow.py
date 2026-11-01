#!/usr/bin/env python3
"""Run the actual-ROM UIL reference game and explicitly assisted flow branches.

This checks authored source translation and integration. It is not an original
CPU comparison or proof that all stages have been completed by ordinary play.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from fdisbull.udl_miniplanets_full import lift_full_game
from check_miniplanets_native import _private_output
from verify_miniplanets_level import plans


def sha(raw): return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    rom = Path(args.rom).read_bytes()
    recovered = lift_full_game(rom)
    program = recovered['program']
    out = _private_output(args.output)
    out.mkdir()
    sources = ('src/fdisbull/game_sources/miniplanets_full.c',
               'src/fdisbull/game_sources/miniplanets_actors.c',
               'src/fdisbull/game_il.py', 'src/fdisbull/udl_miniplanets_full.py',
               'scripts/check_miniplanets_full_flow.py')
    frozen = {p: sha((ROOT / p).read_bytes()) for p in sources}
    summary = {'format': 'miniplanets-full-reference-flow-1', 'status': 'running',
               'source_sha256': sha(rom), 'program_sha256': sha(canonical(program)),
               'tree_sha256': sha(json.dumps(program['tree'], sort_keys=True, separators=(',', ':')).encode()),
               'source_hashes': frozen, 'stages': [], 'branches': [],
               'environment': {'hv16': 'constant0 declared hardware adapter',
                               'sound_busy': 'constant0; original audio engine qualified separately'},
               'claim_ceiling': 'UIL reference execution; stage selection and terminal branches assisted; not natural all-level completion or NES parity'}
    machine = GameMachine(program, {0: rom}, environment={'hv16': [0], 'sound_busy': [0]})
    counts = Counter()
    frame_total = step_total = 0

    def call(name, *args):
        nonlocal step_total
        result = machine.call(name, *args)
        step_total += result['steps']
        if machine.snapshot()['actor_capacity_fault']:
            raise AssertionError('source profile exceeded its declared actor capacity')
        return result

    def frame(buttons=0):
        nonlocal frame_total
        machine.set_state({'input_buttons': buttons})
        call('game_frame')
        frame_total += 1
        for event in machine.events: counts[(event['kind'], event['id'])] += 1
        machine.events.clear()
        return machine.snapshot()

    def state(**values): machine.set_state(values)
    def branch(label, **facts): summary['branches'].append({'name': label, **facts})
    def tap(buttons): frame(buttons);frame(0)
    try:
        call('game_boot')
        assert machine.snapshot()['mode'] == 0
        # All original maps/objects are loaded through UIL procedures, never
        # copied into UIL state by this test. Header parsing is independent.
        actors = Counter()
        for index in range(55):
            state(stage=index, actor_capacity_fault=0)
            call('begin_stage', 0)  # Declared assisted stage selection/intro skip.
            s = machine.snapshot()
            h = 0x655CA + index * 8
            p = int.from_bytes(rom[h:h + 4], 'big')
            assert s['world'] == list(rom[p:p + 256])
            assert s['stage_name'] == rom[h + 4]
            original = []
            q = p + 256
            while rom[q] != 255:
                original.extend(rom[q:q + 4]);q += 4
            assert s['objects'][:len(original)] == original
            assert all(s['objects'][i] == 0 for i in range(len(original), 192, 4))
            types = Counter(original[::4]);actors.update(types)
            assert s['keys_left'] == types[1] + types[24]
            assert [s[k] for k in ('player_x','player_y','player_angle','player_action',
                                   'player_jump','player_spring','player_win','player_die')] == [0,0,2,0,16,0,0,0]
            for tick in range(16): frame(0)
            summary['stages'].append({'index': index, 'name_bcd': rom[h + 4],
                'original_objects': len(original)//4, 'keys': types[1] + types[24],
                'map_sha256': sha(rom[p:p + 256]), 'opening_updates': 16,
                'assisted': 'stage selected and intro skipped; original data loaded by UIL'})
        assert sum(actors.values()) == 479
        summary['placed_actor_counts'] = dict(sorted(actors.items()))

        # An established input-only route is executed by the full engine, now
        # retaining the clock, score tally, life threshold and stage transition.
        state(stage=0, invict=255, joy_hold=0, input_buttons=0)
        call('start_game')
        call('init_level')  # Explicit presentation intro skip.
        first_key = first_win = None
        for tick, buttons in enumerate(plans()['complete_level'], 1):
            s = frame(buttons)
            assert not s['player_die']
            if s['keys_left'] == 0 and first_key is None: first_key = tick
            if s['player_win'] != 0 and first_win is None: first_win = tick
        assert (first_key, first_win) == (472, 784)
        remaining_seconds = int(f"{s['time_secs']:x}")
        for tick in range(600):
            s = frame(0)
            if s['stage'] == 1: break
        else: raise AssertionError('win/tally did not advance the stage')
        assert s['score'] == int(str(remaining_seconds * 100), 16)
        assert s['lives'] == 5
        branch('stage1_input_route_clock_tally_and_advance', first_key_tick=first_key,
               first_win_tick=first_win, seconds_at_goal_bcd=remaining_seconds,
               score_bcd=s['score'], next_stage=s['stage'], assisted='stage load and intro skip only; route uses buttons')

        state(stage=0, invict=255)
        call('begin_stage', 0)
        state(player_jump=0, time_secs=0, time_frames=1, joy_hold=0)
        frame(0)
        assert machine.snapshot()['player_die'] == 1
        for tick in range(100):
            s = frame(0)
            if s['lives'] == 4: break
        assert (s['lives'], s['invict'], s['mode']) == (4, 0, 1)
        branch('timer_death_life_loss_and_restart', assisted='timer set at original zero-second borrow boundary')

        state(ingame_status=1, shake_timer=10, time_frames=60, anim=0, joy_hold=0)
        s = frame(0)
        assert (s['shake_timer'], s['time_frames'], s['anim']) == (9, 60, 0)
        s = frame(64)
        assert (s['shake_timer'], s['time_frames'], s['anim'], s['ingame_status']) == (8, 59, 1, 0)
        branch('source_pause_and_render_side_shake', assisted='paused state and shake countdown initialized')

        state(stage=9)
        call('begin_stage', 0)
        state(lives=1, player_die=95, joy_hold=0)
        frame(0);frame(0)
        assert machine.snapshot()['mode'] == 3
        frame(64)
        assert machine.snapshot()['mode'] == 4
        frame(0);s = frame(66)  # Start has priority over simultaneous Left.
        assert (s['mode'], s['stage'], s['lives'], s['score']) == (8, 9, 5, 0)
        branch('last_life_game_over_continue', assisted='last-life death boundary initialized; menus use buttons')

        # Every actual shipped password, including Muteki, passes its original
        # digit-packing and ROM-table lookup via the procedural UIL handler.
        passwords = []
        for i in range(8):
            p = 0x48FDC + i*4
            value = int.from_bytes(rom[p:p+2], 'big')
            digits = [((value >> shift) & 15) for shift in (12,8,4,0)]
            entered = int.from_bytes(bytes(digits), 'big')
            call('enter_password')
            state(entered_password=entered, joy_press=128)
            call('update_password_dial')
            s = machine.snapshot()
            assert (s['password_quit'], s['muteki'], s['stage']) == (1, rom[p+2], rom[p+3])
            passwords.append({'index': i, 'stage': s['stage'], 'muteki': s['muteki']})
        branch('all_password_destinations', cases=passwords, assisted='entered digits initialized; original packing/lookup executed')

        call('enter_title');state(joy_hold=0)
        for tick in range(84): frame(0)
        tap(8);tap(8);frame(64)
        assert machine.snapshot()['mode'] == 6
        frame(0);before = machine.snapshot()['time_setting'];tap(1)
        assert machine.snapshot()['time_setting'] == (before+1)%5
        tap(8);before = machine.snapshot()['life_setting'];tap(2)
        assert machine.snapshot()['life_setting'] == (before-1)%5
        tap(8);tap(16);tap(64)
        assert machine.snapshot()['mode'] == 0
        branch('title_options_and_sound_test', assisted='none within button-driven menu sequence')

        for button in (4,4,8,8,2,1,2,1): tap(button)
        assert machine.snapshot()['debug_ok'] == 255
        if not machine.snapshot()['title_show_menu']:
            tap(64)  # During logo zoom, the first Start only opens the menu.
        frame(64)
        assert machine.snapshot()['mode'] == 9
        branch('title_cheat_and_debug_selection', assisted='none within button-driven cheat/menu sequence')
        for sequence in range(6):
            state(attract_seq=sequence, joy_hold=0)
            call('start_attract')
            p = int.from_bytes(rom[0x65782+sequence*4:0x65786+sequence*4], 'big')
            assert machine.snapshot()['stage'] == rom[p]
            frame(0)
            assert machine.snapshot()['attract_mode'] == 255
            frame(64)
            assert machine.snapshot()['mode'] == 0
        branch('all_six_original_attract_streams_and_exit', assisted='attract sequence selected; first replay pair and Start exit executed')

        state(stage=8, stage_name=0x19, end_game=1, invict=0, mode=1, score=0, joy_hold=0)
        call('level_over')
        assert machine.snapshot()['mode'] == 2
        for tick in range(2000):
            s = frame(0)
            if s['mode'] != 2: break
        assert (s['stage'], s['mode'], s['score']) == (9, 8, 0x5000)
        branch('boss_stage_clear_bonus_and_world_advance', assisted='boss win boundary initialized; complete original tally phases executed')

        state(stage=45, invict=255)
        call('enter_credits')
        assert (machine.snapshot()['stage'], machine.snapshot()['mode']) == (46, 8)
        state(stage=45, invict=0)
        call('enter_credits')
        assert machine.snapshot()['mode'] == 7
        state(stage=54, invict=255)
        call('enter_credits')
        assert machine.snapshot()['mode'] == 7
        visible_text = False
        for tick in range(12000):
            s = frame(0)
            visible_text = visible_text or any(s['credits_text'])
            if s['mode'] == 0: break
        else: raise AssertionError('original staff-roll flow did not return to title')
        assert visible_text
        branch('ending_hidden_world_and_complete_staff_roll', assisted='ending/Invict boundaries initialized; complete typewriter/timing flow executed')
        summary['frame_updates'] = frame_total
        summary['uil_steps'] = step_total
        summary['emitted_event_counts'] = [{'kind': k, 'id': i, 'count': n} for (k,i),n in sorted(counts.items())]
        summary['inputs_unchanged'] = frozen == {p: sha((ROOT / p).read_bytes()) for p in sources}
        summary['status'] = 'passed' if summary['inputs_unchanged'] else 'source-changed'
    except Exception as exc:
        summary['status'] = 'failed'
        summary['failure'] = str(exc)
        raise
    finally:
        (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('stages','emitted_event_counts')}, indent=2))


if __name__ == '__main__': main()
