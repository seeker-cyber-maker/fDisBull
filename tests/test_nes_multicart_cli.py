"""The packaging UDC is usable without an analysis project or emulator."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from fdisbull.console_udc import compile_console_rom


def invoke(*args):
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    process = subprocess.run([sys.executable, '-m', 'fdisbull', *map(str, args)],
                             capture_output=True, text=True, env=env, timeout=30)
    return process.returncode, json.loads(process.stdout)


def source_game(value):
    program = {'format': 'fdisbull-il-1', 'role': 'uil',
               'variables': {'$value': {'type': 'u8', 'initial': value}},
               'resources': {}, 'body': []}
    return compile_console_rom(program, target='nes')['rom']


def test_profiles_are_projectless_and_describe_the_compatibility_boundary():
    code, reply = invoke('nes-multicart-profiles')
    assert code == 0 and reply['ok']
    profile = reply['result']['profiles'][0]
    assert profile['target_mapper'] == 225 and profile['input_mapper'] == 0
    assert profile['game_count'] == 2
    assert 'cartridge RAM' in profile['caller_attestation']


def test_public_build_preserves_each_generated_game_and_inspects_the_output(tmp_path):
    inputs = [tmp_path / 'one.nes', tmp_path / 'two.nes']
    payloads = [source_game(value) for value in (3, 7)]
    for path, raw in zip(inputs, payloads):
        path.write_bytes(raw)
    output = tmp_path / 'multicart'
    code, reply = invoke('nes-multicart-build', *inputs, '--output', output,
                         '--authored-compatible')
    assert code == 0 and reply['ok']
    image = (output / 'program.nes').read_bytes()
    assert reply['result']['rom_sha256'] == hashlib.sha256(image).hexdigest()
    # Mapper 225 selects PRG and CHR independently; both source windows survive.
    prg_start, chr_start = 16, 16 + 131072
    for slot, raw in enumerate(payloads, 1):
        assert image[prg_start + slot * 32768:prg_start + (slot + 1) * 32768] == raw[16:32784]
        assert image[chr_start + slot * 8192:chr_start + (slot + 1) * 8192] == raw[32784:]
    assert [p.read_bytes() for p in inputs] == payloads
    code, inspected = invoke('nes-multicart-inspect', output / 'program.nes')
    assert code == 0 and inspected['ok'] and inspected['result']['mapper'] == 225
    assert inspected['result']['unique_game_count'] == 'unknown'


def test_missing_compatibility_assertion_fails_without_creating_output(tmp_path):
    paths = [tmp_path / 'a.nes', tmp_path / 'b.nes']
    for n, path in enumerate(paths):
        path.write_bytes(source_game(n))
    output = tmp_path / 'refused'
    code, reply = invoke('nes-multicart-build', *paths, '--output', output)
    assert code != 0 and not reply['ok']
    assert not output.exists()
