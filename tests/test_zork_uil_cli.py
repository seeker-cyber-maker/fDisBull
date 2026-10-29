"""Public conversion/player commands over a source-free authored miniature."""
import json
from pathlib import Path
import subprocess
import sys

from fdisbull.cli import main
from test_zork_uil import story_image


ROOT = Path(__file__).resolve().parents[1]


def test_conversion_cli_and_installed_style_player_are_connected(tmp_path, capsys):
    # print_char 'A'; new_line; quit. This is authored bytecode, not game data.
    story = tmp_path / 'authored.z3'
    story.write_bytes(story_image([0xe5, 0x7f, 65, 0xbb, 0xba]))
    package, mapping = tmp_path / 'authored.uil.json.gz', tmp_path / 'authored.udl.json.gz'
    assert main(['zork-uil', str(story), '--output', str(package), '--mapping', str(mapping)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['outputs']['uil']['bytes'] == package.stat().st_size
    assert receipt['outputs']['udl']['bytes'] == mapping.stat().st_size
    story.unlink()
    checkpoint = tmp_path / 'state.json'
    process = subprocess.run(
        [sys.executable, '-c',
         'import sys;sys.path.insert(0,sys.argv.pop(1));from fdisbull_player.__main__ import main;raise SystemExit(main())',
         str(ROOT / 'player'), '--uil', str(package), '--checkpoint', str(checkpoint)],
        cwd=tmp_path, input='', text=True, capture_output=True, timeout=10,
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout == 'A\n'
    state = json.loads(checkpoint.read_text())
    assert state['halted'] is True and state['halt_reason'] == 'quit'


def test_conversion_cli_refuses_overwrite_without_replacing_output(tmp_path, capsys):
    story = tmp_path / 'authored.z3'
    story.write_bytes(story_image([0xba]))
    package = tmp_path / 'keep.json'
    package.write_text('keep exactly')
    assert main(['zork-uil', str(story), '--output', str(package)]) == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'stopped'
    assert package.read_text() == 'keep exactly'
