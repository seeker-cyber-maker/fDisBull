"""Optional independent Frotz check of an authored v3 scalar experiment.

No game data is used. This tests only the chosen output and normal termination
in one interpreter; it does not establish DOS-interpreter or game compatibility.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from fdisbull.zmachine_udc import capture_zmachine_definition, compile_zmachine_definition
from tests.test_zmachine_udc import story


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def test_authored_story_source_exact_and_experiment_in_dfrotz(tmp_path):
    configured = os.environ.get('FDISBULL_DFROTZ')
    if not configured:
        pytest.skip('Set FDISBULL_DFROTZ to an independently built Frotz executable')
    executable = Path(configured).resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        pytest.fail('FDISBULL_DFROTZ must name an executable file')
    executable_bytes = executable.read_bytes()
    # ADD 17,0 to global 0x13; PRINT_NUM global 0x13; NEW_LINE; QUIT.
    original = story(bytes.fromhex('14110013e6bf13bbba'), padding=b'')
    definition = capture_zmachine_definition(original)
    baseline = compile_zmachine_definition(definition)
    changed = compile_zmachine_definition(definition, mode='experiment',
        assumptions={'no_code_data_alias': True, 'scalar_values_not_addresses': True},
        edits=[{'offset': 900, 'expected_hex': '14110013', 'replacement_hex': '14220013'}])
    assert bytes.fromhex(baseline['bytes']) == original
    assert changed['qualification'] == 'unverified_experiment'
    assert not changed['equivalence_proven'] and not changed['native_execution']
    outcomes = []
    for label, payload, expected in (
        ('source', original, '17'), ('baseline', bytes.fromhex(baseline['bytes']), '17'),
        ('experiment', bytes.fromhex(changed['bytes']), '34')):
        path = tmp_path / f'{label}.z3'
        path.write_bytes(payload)
        args = [str(executable), '-q', '-m', '-p', '-Z3', str(path)]
        try:
            result = subprocess.run(args, input=b'', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=10, check=False)
            row = {'variant': label, 'argv': args, 'story_sha256': _sha(payload),
                   'stdout': result.stdout.decode('utf-8', errors='replace'),
                   'stderr': result.stderr.decode('utf-8', errors='replace'),
                   'exit_code': result.returncode, 'timeout': False, 'expected': expected}
        except subprocess.TimeoutExpired as error:
            row = {'variant': label, 'argv': args, 'story_sha256': _sha(payload),
                   'stdout': (error.stdout or b'').decode('utf-8', errors='replace'),
                   'stderr': (error.stderr or b'').decode('utf-8', errors='replace'),
                   'exit_code': None, 'timeout': True, 'expected': expected}
        assert path.read_bytes() == payload
        outcomes.append(row)
    assert executable.read_bytes() == executable_bytes
    compiler_source = Path(__file__).resolve().parents[1] / 'src/fdisbull/zmachine_udc.py'
    receipt = {'scope': 'authored v3 output and termination in Frotz; not DOS compatibility',
               'interpreter_sha256': _sha(executable_bytes), 'definition_sha256': definition['sha256'],
               'compiler_source_sha256': _sha(compiler_source.read_bytes()),
               'source_sha256': _sha(original), 'outcomes': outcomes,
               'general_equivalence_proven': False}
    (tmp_path / 'native-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    for result in outcomes:
        assert not result['timeout'] and result['exit_code'] == 0, result
        assert result['stderr'] == '', result
        assert result['stdout'] == result['expected'] + '\n', result
