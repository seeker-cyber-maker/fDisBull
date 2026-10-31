"""Persisted selections, mixed UIL replay and generated C game slices."""

import ctypes
import json
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

# Source examples are deliberately omitted from release distributions.
pytest.importorskip("examples", reason="source-checkout examples are not packaged")

from examples.udc.game_variants import (
    build_native, register_game_variants, replay_model,
    select_game_variants,
)
from examples.udc.game_variants import five_dice, tic_tac_toe
from fdisbull.project import Project
from fdisbull.udc_c import generate_c
from fdisbull.udc_linux import decode_observation


def project_at(tmp_path):
    source = tmp_path / 'authored-source.bin'
    source.write_bytes(b'\xc3' + bytes(31))
    return Project.create(tmp_path / 'game-variants.fdb', source,
                          arch='x86', bits=16, base=0x1000)


def dice_expectation(seed):
    faces = []
    for _ in range(5):
        seed = (seed * 5 + 1) & 65535
        faces.append(seed % 6 + 1)
    return seed, faces


def test_persisted_model_selections_replay_and_mix_each_die(tmp_path):
    with project_at(tmp_path) as project:
        ttt = register_game_variants(project, 'tic-tac-toe')
        dice = register_game_variants(project, 'five-dice')
        terminal = select_game_variants(project, ttt, 'verbose')
        choices = ['clean', 'compact', 'verbose', 'clean', 'compact']
        turn = select_game_variants(project, dice, choices)
        source_sha = project.meta['source_sha256']

    with Project(tmp_path / 'game-variants.fdb') as project:
        assert project.meta['source_sha256'] == source_sha
        assert replay_model(project, terminal['id'], 'tic-tac-toe',
                            status=1, player=2)['outputs'] == {'message': 2}
        assert replay_model(project, terminal['id'], 'tic-tac-toe',
                            status=2, player=1)['outputs'] == {'message': 65535}
        observed = replay_model(project, turn['id'], 'five-dice', seed=12345)
        expected_seed, faces = dice_expectation(12345)
        assert observed['status'] == 'complete'
        assert observed['state']['$seed'] == expected_seed
        assert [observed['state'][f'$face{i}'] for i in range(1, 6)] == faces
        assert len(observed['calls']) == 5
        binding_ids = project.udl_selection_info(turn['id'], full=True)['document']['bindings']
        assert binding_ids == {f'roll{i}': dice['layers']['uil'][style]
                               for i, style in enumerate(choices, 1)}


def test_selected_c_shells_bind_exact_layers_and_qualify_uil_models(tmp_path):
    pytest.importorskip('z3')
    compiler = shutil.which('clang')
    if not compiler:
        pytest.skip('Clang unavailable')
    with project_at(tmp_path) as project:
        ttt = register_game_variants(project, 'tic-tac-toe')
        dice = register_game_variants(project, 'five-dice')
        first = select_game_variants(project, ttt, 'clean', backend='c-uil')
        second = select_game_variants(project, ttt, 'verbose', backend='c-uil')
        choices = ['clean', 'compact', 'verbose', 'compact', 'clean']
        turn = select_game_variants(project, dice, choices, backend='c-uil')

        built_first = build_native(project, first['id'], 'tic-tac-toe',
                                   tmp_path / 'ttt-clean', c_compiler=compiler,
                                   status=1, player=2)
        built_second = build_native(project, second['id'], 'tic-tac-toe',
                                    tmp_path / 'ttt-verbose', c_compiler=compiler,
                                    status=1, player=2)
        built_turn = build_native(project, turn['id'], 'five-dice',
                                  tmp_path / 'dice-mixed', c_compiler=compiler,
                                  seed=12345)
        built_windows_ttt = build_native(project, second['id'], 'tic-tac-toe',
                                         tmp_path / 'ttt-windows', c_compiler=compiler,
                                         target='windows-x64', status=1, player=2)
        built_windows_dice = build_native(project, turn['id'], 'five-dice',
                                          tmp_path / 'dice-windows', c_compiler=compiler,
                                          target='windows-x64', seed=12345)

    assert first['id'] != second['id']
    assert built_first['plan_sha256'] == built_second['plan_sha256']
    assert built_first['layer_ids']['terminal'] != built_second['layer_ids']['terminal']
    for built in (built_first, built_second, built_turn):
        assert Path(built['directory']).joinpath('program').is_file()
        assert Path(built['selection_capsule']).is_file()
        assert all(item['status'] in ('equivalent_under_contract', 'declared_notification_provider')
                   for item in built['qualification'].values())
        capsule = json.loads(Path(built['selection_capsule']).read_text())
        assert capsule['selection'] == built['selection']
        assert capsule['layer_ids'] == built['layer_ids']
        assert capsule['native_build_capsule_sha256']
        assert built['native_build_qualification']['native_execution'] is False
    for built in (built_windows_ttt, built_windows_dice):
        assert Path(built['directory']).joinpath('program.exe').is_file()
        assert Path(built['selection_capsule']).is_file()
        assert all(item['status'] in ('equivalent_under_contract', 'declared_notification_provider')
                   for item in built['qualification'].values())
        assert built['native_build_qualification']['native_execution'] is False


@pytest.mark.parametrize('game', ['tic-tac-toe', 'five-dice'])
def test_generated_c_runs_on_host_for_full_typed_input_domain(tmp_path, game):
    compiler = shutil.which('clang')
    if not compiler:
        pytest.skip('Clang unavailable')
    spec = tic_tac_toe if game == 'tic-tac-toe' else five_dice
    for style, program in spec.variants().items():
        ports = (['$status', '$player'], ['$message']) if game == 'tic-tac-toe' else (['$seed'], ['$next'])
        source, _, _ = generate_c({'backend': 'c-uil', 'program': program,
                                   'return': ports[1][0],
                                   'state_adapter': {'inputs': ports[0], 'outputs': ports[1]}})
        source_file = tmp_path / f'{game}-{style}.c'
        output_file = tmp_path / f'{game}-{style}.{"dylib" if platform.system() == "Darwin" else "so"}'
        source_file.write_text(source)
        command = [compiler, '-std=c11', '-O1', '-fPIC',
                   '-dynamiclib' if platform.system() == 'Darwin' else '-shared',
                   str(source_file), '-o', str(output_file)]
        subprocess.run(command, check=True, capture_output=True, timeout=30)
        function = ctypes.CDLL(str(output_file)).udc_block
        function.argtypes = (ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort))
        function.restype = ctypes.c_ulonglong
        inputs = ((status, player) for status in range(256) for player in range(256)) if game == 'tic-tac-toe' else range(65536)
        for item in inputs:
            values = item if game == 'tic-tac-toe' else (item,)
            input_words = (ctypes.c_ushort * len(values))(*values)
            output_words = (ctypes.c_ushort * 1)()
            status_and_return = function(input_words, output_words)
            expected = ({(0, 0): 0, (1, 1): 1, (1, 2): 2, (2, 0): 3}.get(item, 65535)
                        if game == 'tic-tac-toe' else (item * 5 + 1) & 65535)
            assert status_and_return == expected
            assert output_words[0] == expected


def test_selected_linux_c_shell_executes_when_host_matches_target(tmp_path):
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
        pytest.skip('Linux x86-64 native execution requires a matching host')
    pytest.importorskip('z3')
    compiler = shutil.which('clang')
    if not compiler:
        pytest.skip('Clang unavailable')
    with project_at(tmp_path) as project:
        ttt = register_game_variants(project, 'tic-tac-toe')
        chosen = select_game_variants(project, ttt, 'compact', backend='c-uil')
        built = build_native(project, chosen['id'], 'tic-tac-toe',
                             tmp_path / 'native', c_compiler=compiler,
                             status=1, player=2)
    frame = tmp_path / 'frame.bin'
    run = subprocess.run(['/bin/sh', '-c', 'exec "$1" 3>"$2"', 'udc-run',
                          str(tmp_path / 'native/program'), str(frame)],
                         capture_output=True, timeout=10)
    observed = decode_observation(frame.read_bytes(), built)
    assert run.returncode == observed['status'] == 0
    assert run.stdout == b'O wins'
    assert observed['state'] == {'$status': 1, '$player': 2, '$message': 2}
