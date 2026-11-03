import random
import json

import pytest

from fdisbull.game_il import GameMachine, canonical
from fdisbull import psg_il
from fdisbull.psg_il import lift_psg


def _reference(state):
    out = {key: value[:] if isinstance(value, list) else value
           for key, value in state.items()}
    if state['audio_sfx_phase']:
        return out
    for slot in range(2):
        for channel in range(8, 12):
            index = slot * 16 + channel
            psg = slot * 4 + channel - 8
            out['audio_psg_pulse_period'][psg] = state['audio_pulse_period'][index]
            out['audio_psg_triangle_period'][psg] = state['audio_triangle_period'][index]
            phase = state['audio_envelope_phase'][index]
            level = state['audio_psg_level'][index]
            if phase == 1:
                total = level + state['audio_psg_ar'][index]
                if total > 255 or total >= state['audio_psg_tl'][index]:
                    level = state['audio_psg_tl'][index]
                    out['audio_envelope_phase'][index] = 2
                else:
                    level = total
            elif phase == 2:
                rate = state['audio_psg_dr'][index]
                result = (level - rate) & 0xff
                if level < rate or result < state['audio_psg_sl'][index]:
                    level = state['audio_psg_sl'][index]
                    out['audio_envelope_phase'][index] = 3
                else:
                    level = result
            else:
                rate = (state['audio_psg_sr'][index] if phase == 3
                        else state['audio_psg_rr'][index])
                level = max(0, level - rate)
            out['audio_psg_level'][index] = level
            out['audio_envelope'][index] = level >> 4
    return out


def _reference_volume(state):
    out = [value for value in state['audio_current_volume']]
    gain = (15, 12, 9, 8, 6, 5, 4, 3, 2, 2, 2, 1, 1, 1, 1, 0)
    for channel in range(8, 12):
        index = channel + 16 if state['audio_owner'][channel] else channel
        level = state['audio_psg_level'][index]
        if state['audio_pan'][index] == 0 or level < 16:
            out[channel] = 0
        else:
            attenuation = min(40, state['audio_attenuation'][index])
            amount = (attenuation * 3) // 8 + 15 - (level >> 4)
            out[channel] = gain[min(15, amount)]
    return out


def test_lift_psg_is_source_bound_game_il_without_external_regions():
    program = lift_psg()
    assert program['format'] == 'fdisbull-game-il-2'
    assert program['regions'] == []
    assert program['evidence']['kind'] == 'authored-bounded-psg'
    assert program['evidence']['source_sha256']
    assert program['evidence']['profile'] == 'miniplanets-nes-psg-envelope-volume-1'
    assert program['evidence']['entries'] == [
        'audio_render_psg', 'audio_render_psg_volume']
    assert any('set_state' in limit for limit in program['evidence']['limits'])
    assert program == json.loads(psg_il.ARTIFACT_PATH.read_text())
    assert {item['decl']['name'] for item in program['tree']['ext']
            if item['node'] == 'FuncDef'} == {
                'audio_render_psg', 'audio_render_psg_volume'}
    assert canonical(program) == canonical(lift_psg())


def test_lift_psg_fails_closed_when_packaged_artifact_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(psg_il, 'ARTIFACT_PATH', tmp_path / 'missing.json')
    with pytest.raises(ValueError, match='artifact is unavailable'):
        lift_psg()


def test_lift_psg_fails_closed_when_packaged_artifact_is_modified(tmp_path, monkeypatch):
    modified = json.loads(psg_il.ARTIFACT_PATH.read_text())
    modified['evidence']['profile'] = 'unexpected-profile'
    path = tmp_path / 'modified.json'
    path.write_text(json.dumps(modified), encoding='utf-8')
    monkeypatch.setattr(psg_il, 'ARTIFACT_PATH', path)
    with pytest.raises(ValueError, match='differs from the source-derived program'):
        lift_psg()


def test_psg_phase_gate_preserves_every_field_and_period():
    machine = GameMachine(lift_psg())
    state = machine.snapshot()
    state['audio_sfx_phase'] = 1
    state['audio_envelope_phase'][8] = 1
    state['audio_psg_level'][8] = 100
    state['audio_psg_ar'][8] = 20
    state['audio_pulse_period'][8] = 0x1234
    state['audio_triangle_period'][8] = 0xabcd
    state['audio_psg_pulse_period'][0] = 0x5678
    state['audio_psg_triangle_period'][0] = 0x9876
    machine.set_state(state)
    before = machine.snapshot()
    machine.call('audio_render_psg')
    assert machine.snapshot() == before


def test_psg_envelope_and_period_mapping_match_independent_state_model():
    rng = random.Random(0x505347)
    machine = GameMachine(lift_psg())
    phases = (0, 1, 2, 3, 4, 5, 255)
    rates = (0, 1, 15, 127, 254, 255)
    for case in range(128):
        state = machine.snapshot()
        state['audio_sfx_phase'] = 0
        for slot in range(2):
            for channel in range(8, 12):
                index = slot * 16 + channel
                state['audio_envelope_phase'][index] = phases[(case + channel + slot) % len(phases)]
                state['audio_psg_level'][index] = rng.randrange(256)
                for name in ('audio_psg_tl', 'audio_psg_ar', 'audio_psg_sl',
                             'audio_psg_dr', 'audio_psg_sr', 'audio_psg_rr'):
                    state[name][index] = rng.choice(rates)
                state['audio_pulse_period'][index] = rng.randrange(65536)
                state['audio_triangle_period'][index] = rng.randrange(65536)
        expected = _reference(state)
        machine.set_state(state)
        machine.call('audio_render_psg')
        assert machine.snapshot() == expected, f'PSG state mismatch in case {case}'


def test_psg_attack_overflow_decay_borrow_and_zero_release_edges():
    machine = GameMachine(lift_psg())
    state = machine.snapshot()
    for index, phase, level, rate, target in (
        (8, 1, 250, 10, 255),       # 8-bit carry clamps and advances attack
        (9, 1, 4, 3, 7),            # exact target threshold advances attack
        (10, 2, 3, 4, 9),           # subtraction borrow clamps to sustain
        (11, 2, 17, 4, 12),         # result below sustain clamps
        (24, 4, 0, 255, 0),         # optimized release-zero state
        (25, 3, 3, 4, 0),           # sustain underflow clamps to zero
    ):
        state['audio_envelope_phase'][index] = phase
        state['audio_psg_level'][index] = level
        if phase == 1:
            state['audio_psg_ar'][index] = rate
            state['audio_psg_tl'][index] = target
        elif phase == 2:
            state['audio_psg_dr'][index] = rate
            state['audio_psg_sl'][index] = target
        elif phase == 3:
            state['audio_psg_sr'][index] = rate
        else:
            state['audio_psg_rr'][index] = rate
    expected = _reference(state)
    machine.set_state(state)
    machine.call('audio_render_psg')
    assert machine.snapshot() == expected


def test_psg_volume_owner_pan_and_attenuation_match_fixed_lookup_tables():
    machine = GameMachine(lift_psg())
    for case in range(64):
        state = machine.snapshot()
        for index in range(32):
            state['audio_psg_level'][index] = (case * 37 + index * 29) & 255
            state['audio_attenuation'][index] = (case * 13 + index * 11) & 255
            state['audio_pan'][index] = (case + index * 3) & 255
        for channel in range(8, 12):
            state['audio_owner'][channel] = (case + channel) % 3
        expected = _reference_volume(state)
        machine.set_state(state)
        machine.call('audio_render_psg_volume')
        assert machine.snapshot()['audio_current_volume'] == expected, case
