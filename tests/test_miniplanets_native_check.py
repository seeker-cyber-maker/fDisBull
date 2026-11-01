"""Bound the private original-CPU transition checker before native execution."""
import copy
import json
from pathlib import Path
import runpy

import pytest


CHECK = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                          'scripts/check_miniplanets_native.py'))


def case():
    state = {name: 0 for name in CHECK['REQUIRED']}
    state.update({'$keys': 1, '$key_active': 1, '$jump': 16, '$angle': 2})
    return {'name': 'authored-input', 'before': state, 'after': dict(state)}


def test_case_reader_accepts_declared_states_without_mutation(tmp_path):
    value = [case()]
    original = copy.deepcopy(value)
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps(value))
    assert CHECK['load_cases'](path) == original
    assert value == original


@pytest.mark.parametrize('change', ['missing', 'boolean', 'overflow', 'negative',
                                    'two-keys', 'duplicate-name', 'unknown-field'])
def test_case_reader_refuses_incomplete_or_unbounded_inputs(tmp_path, change):
    value = [case()]
    if change == 'missing':
        del value[0]['before']['$phase']
    elif change == 'boolean':
        value[0]['before']['$x'] = True
    elif change == 'overflow':
        value[0]['after']['$y'] = 256
    elif change == 'negative':
        value[0]['before']['$jump'] = -1
    elif change == 'two-keys':
        value[0]['before']['$keys'] = 2
    elif change == 'duplicate-name':
        value.append(copy.deepcopy(value[0]))
    else:
        value[0]['extra'] = 'unexpected'
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        CHECK['load_cases'](path)


def test_controller_mapping_uses_original_game_bits():
    # Original joypad protocol U,D,L,R,B,C,A,Start, independently of public bits.
    assert [CHECK['native_buttons'](1 << bit) for bit in range(8)] == [
        8, 4, 1, 2, 64, 16, 128, 0]
    assert CHECK['native_buttons'](255) == 0xdf


def test_output_requires_fresh_private_directory(tmp_path):
    assert CHECK['_private_output'](tmp_path / 'new') == tmp_path / 'new'
    with pytest.raises(ValueError, match='new'):
        CHECK['_private_output'](tmp_path)
    (tmp_path / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='Git'):
        CHECK['_private_output'](tmp_path / 'new')
