"""The persisted UIL selection invokes the selected host-compiled C blocks."""

import shutil

import pytest

from examples.udc.game_variants import (
    register_game_variants, replay_compiled, select_game_variants,
)
from examples.udc.game_variants import compiled_replay
from fdisbull.project import Project


def project_at(tmp_path):
    source = tmp_path / 'authored-source.bin'
    source.write_bytes(b'\xc3' + bytes(31))
    return Project.create(tmp_path / 'replay.fdb', source,
                          arch='x86', bits=16, base=0x1000)


def prerequisites():
    pytest.importorskip('z3')
    compiler = shutil.which('clang')
    if not compiler:
        pytest.skip('Clang unavailable')
    return compiler


def test_tic_tac_toe_replay_runs_each_selected_compiled_style(tmp_path):
    compiler = prerequisites()
    with project_at(tmp_path) as project:
        registered = register_game_variants(project, 'tic-tac-toe')
        choices = {style: select_game_variants(project, registered, style,
                                                backend='c-uil')['id']
                   for style in ('clean', 'compact', 'verbose')}
    with Project(tmp_path / 'replay.fdb') as project:
        for style, selection_id in choices.items():
            result = replay_compiled(project, selection_id, 'tic-tac-toe',
                                     c_compiler=compiler, status=1, player=2)
            assert result['execution'] == 'host-compiled-c'
            assert result['outputs'] == {'message': 2}
            assert result['selection'] == selection_id
            assert result['calls'][0]['binding'] == 'terminal'
            invalid = replay_compiled(project, selection_id, 'tic-tac-toe',
                                      c_compiler=compiler, status=2, player=1)
            assert invalid['outputs'] == {'message': 65535}


def test_five_dice_replay_invokes_mixed_compiled_layers_in_uil_order(tmp_path):
    compiler = prerequisites()
    with project_at(tmp_path) as project:
        registered = register_game_variants(project, 'five-dice')
        styles = ['clean', 'compact', 'verbose', 'compact', 'clean']
        selection = select_game_variants(project, registered, styles,
                                         backend='c-uil')
    with Project(tmp_path / 'replay.fdb') as project:
        result = replay_compiled(project, selection['id'], 'five-dice',
                                 c_compiler=compiler, seed=12345)
        expected_seed = 12345
        faces = []
        for _ in range(5):
            expected_seed = (expected_seed * 5 + 1) & 65535
            faces.append(expected_seed % 6 + 1)
        assert result['execution'] == 'host-compiled-c'
        assert result['status'] == 'complete'
        assert result['state']['$seed'] == expected_seed
        assert [result['state'][f'$face{i}'] for i in range(1, 6)] == faces
        assert [call['binding'] for call in result['calls']] == [f'roll{i}' for i in range(1, 6)]
        assert [call['layer'] for call in result['calls']] == [
            registered['layers']['c-uil'][style] for style in styles]


def test_compiled_replay_rejects_a_model_only_selection(tmp_path):
    compiler = prerequisites()
    with project_at(tmp_path) as project:
        registered = register_game_variants(project, 'tic-tac-toe')
        selected = select_game_variants(project, registered, 'clean')
        with pytest.raises(ValueError, match='c-uil|compiled'):
            replay_compiled(project, selected['id'], 'tic-tac-toe',
                            c_compiler=compiler, status=1, player=1)


def test_compiled_replay_detects_generated_code_disagreement(tmp_path, monkeypatch):
    compiler = prerequisites()
    with project_at(tmp_path) as project:
        registered = register_game_variants(project, 'tic-tac-toe')
        selected = select_game_variants(project, registered, 'clean', backend='c-uil')
        wrong_source = ('unsigned long long udc_block(const unsigned short *in, '
                        'unsigned short *out) { (void)in; out[0] = 0; return 0; }\n')
        monkeypatch.setattr(compiled_replay, 'generate_c',
                            lambda module: (wrong_source, ['$player', '$status'], ['$message']))
        with pytest.raises(ValueError, match='differs from reference UIL'):
            replay_compiled(project, selected['id'], 'tic-tac-toe',
                            c_compiler=compiler, status=1, player=2)
