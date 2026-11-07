"""Fail-closed contracts for authored DOS patch runners; no original inputs."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


HELPERS = Path(__file__).parents[1] / 'research/dos-memory-tools/2026-11-07'
sys.path.insert(0, str(HELPERS))
try:
    import native_witness_checks as checks
    import run_fix_experiment as fix
    import native_patch_experiment as update
finally:
    sys.path.pop(0)


def completion_records(offset=0x12D, segment=0x814, eax='0x02010024'):
    """Authored observations with independently selected source/runtime PCs."""
    address = {'space': 'segmented', 'segment': hex(segment), 'offset': hex(offset)}
    source = hex(0x10000 + offset)
    armed = {'address': copy.deepcopy(address), 'breakpoint_id': 'bp-finished',
             'session_id': 'test-session', 'run': 'test-run', 'kind': 'execution',
             'bytes_verified': True, 'project_address': source, 'project_cs': '0x1000'}
    complete = {'run': 'test-run', 'outcome': 'breakpoint', 'timed_out': False,
                'session': {'session_id': 'test-session', 'state': 'stopped',
                            'stop_reason': {'kind': 'breakpoint', 'breakpoint_id': 'bp-finished',
                                            'address': copy.deepcopy(address),
                                            'project_address': source, 'cpu_mode': 'real'}},
                'stop': {'trigger': 'breakpoint', 'native_kind': 'breakpoint',
                         'causing_instruction': copy.deepcopy(address),
                         'resume_pc': copy.deepcopy(address), 'cpu_mode': 'real',
                         'instruction_completed': False, 'registers_stage': 'before-instruction'}}
    registers = {'segments': {'cs': hex(segment)}, 'instruction_pointer': hex(offset),
                 'session_id': 'test-session', 'cpu_mode': 'real', 'project_address': source,
                 'cs': hex(segment), 'ip': hex(offset), 'general': {'eax': eax}}
    return armed, complete, registers


@pytest.mark.parametrize('offset,segment', [(0x12D, 0x814), (0x143, 0x7F00)])
def test_completion_accepts_exact_relocated_endpoint_and_records_nonzero_al(offset, segment):
    result = checks.verify_completion(*completion_records(offset, segment), run_id='test-run', offset=offset)
    assert result['exact_completion_breakpoint_verified'] is True
    assert (result['runtime_cs'], result['runtime_ip']) == (segment, offset)
    assert result['dos_ax'] == 36
    assert result['dos_termination_type_ah'] == 0
    assert result['dos_return_code_al'] == 36
    assert result['exit_al_is_not_a_success_test'] is True


@pytest.mark.parametrize('mutation', [
    'timeout', 'missing_timeout', 'budget_stop', 'wrong_breakpoint', 'wrong_stop_address',
    'wrong_resume_pc', 'wrong_cs', 'wrong_ip', 'wrong_project_address', 'wrong_run',
    'wrong_session', 'unverified_bytes', 'wrong_authored_offset', 'stale_alias',
    'missing_stop', 'instruction_already_completed', 'abnormal_dos_termination',
])
def test_false_completion_claims_are_rejected(mutation):
    armed, complete, registers = completion_records()
    if mutation == 'timeout':
        complete['timed_out'] = True
    elif mutation == 'missing_timeout':
        del complete['timed_out']
    elif mutation == 'budget_stop':
        complete['outcome'] = 'guest_time_budget'
    elif mutation == 'wrong_breakpoint':
        complete['session']['stop_reason']['breakpoint_id'] = 'bp-wrapper-failed'
    elif mutation == 'wrong_stop_address':
        complete['session']['stop_reason']['address']['offset'] = '0x12f'
    elif mutation == 'wrong_resume_pc':
        complete['stop']['resume_pc']['offset'] = '0x12f'
    elif mutation == 'wrong_cs':
        registers['segments']['cs'] = '0x815'
    elif mutation == 'wrong_ip':
        registers['instruction_pointer'] = '0x12f'
    elif mutation == 'wrong_project_address':
        complete['session']['stop_reason']['project_address'] = '0x1012f'
    elif mutation == 'wrong_run':
        complete['run'] = 'another-run'
    elif mutation == 'wrong_session':
        registers['session_id'] = 'another-session'
    elif mutation == 'unverified_bytes':
        armed['bytes_verified'] = False
    elif mutation == 'wrong_authored_offset':
        armed['address']['offset'] = '0x12f'
    elif mutation == 'stale_alias':
        registers['ip'] = '0x12f'
    elif mutation == 'missing_stop':
        del complete['stop']
    elif mutation == 'instruction_already_completed':
        complete['stop']['instruction_completed'] = True
    elif mutation == 'abnormal_dos_termination':
        registers['general']['eax'] = '0x124'
    with pytest.raises(ValueError):
        checks.verify_completion(armed, complete, registers, run_id='test-run', offset=0x12D)


def test_an_unrelated_breakpoint_is_not_completion_even_if_output_matches():
    armed, complete, registers = completion_records()
    complete['session']['stop_reason']['breakpoint_id'] = 'unrelated'
    # The former observer accepted this one field, even at a different stop.
    assert complete['outcome'] == 'breakpoint'
    output = checks.file_effects({'target': b'before'}, {'target': b'after'}, {'target': b'after'})
    assert output['all_expected_file_bytes_match'] is True
    with pytest.raises(ValueError, match='exact armed'):
        checks.verify_completion(armed, complete, registers, run_id='test-run', offset=0x12D)


@pytest.mark.parametrize('case,before,after', [
    ('real', b'0123456789abcdef\0xyz', b'0123456789abcdefjxyz'),
    ('already_fixed', b'0123456789abcdefjxyz', b'0123456789abcdefjxyz'),
    ('wrong_byte', b'0123456789abcdefUxyz', b'0123456789abcdefUxyz'),
    ('short', b'0123456789abcdef', b'0123456789abcdefj'),
    ('missing', None, None),
])
def test_declared_configuration_cases_preserve_all_other_bytes(case, before, after):
    assert fix.config_case(b'0123456789abcdef\0xyz', case) == (before, after)


@pytest.mark.parametrize('change', ['unexpected', 'missing', 'wrong_target', 'unrelated_change', 'longer_eof'])
def test_complete_file_comparison_rejects_more_than_target_byte_changes(change):
    before = {'GW.CFG': b'0123456789abcdef\0tail', 'untouched': b'unchanged'}
    expected = {'GW.CFG': b'0123456789abcdefjtail', 'untouched': b'unchanged'}
    observed = dict(expected)
    if change == 'unexpected':
        observed['extra'] = b'new'
    elif change == 'missing':
        del observed['GW.CFG']
    elif change == 'wrong_target':
        observed['GW.CFG'] = before['GW.CFG']
    elif change == 'unrelated_change':
        observed['untouched'] = b'changed'
    elif change == 'longer_eof':
        observed['GW.CFG'] += b'X'
    result = checks.file_effects(before, expected, observed)
    assert result['all_expected_file_bytes_match'] is False
    assert result['missing_files'] or result['unexpected_files'] or result['different_files']


def test_full_manifest_success_and_empty_expected_rejection():
    before = {'target': b'before', 'other': b'original'}
    after = {'target': b'after', 'other': b'original'}
    result = checks.file_effects(before, after, dict(after))
    assert result['all_expected_file_bytes_match'] is True
    assert result['changed_files'] == ['target']
    assert result['observed_files']['other'] == checks.identity(b'original')
    with pytest.raises(ValueError, match='must not be empty'):
        checks.file_effects({}, {}, {})


@pytest.mark.parametrize('source,expected_hash', [
    ('fix_bootstrap', fix.BOOTSTRAP_SHA), ('patch_bootstrap', update.BOOTSTRAP_SHA),
])
def test_authored_bootstrap_build_is_pinned_and_one_changed_byte_is_rejected(tmp_path, source, expected_hash):
    if not shutil.which('as') or not shutil.which('ld') or sys.platform != 'linux':
        pytest.skip('Independent wrapper build requires GNU binutils on Linux')
    obj, executable = tmp_path / (source + '.o'), tmp_path / (source + '.com')
    subprocess.run(['as', '--32', '-o', str(obj), str(HELPERS / (source + '.S'))], check=True)
    subprocess.run(['ld', '-m', 'elf_i386', '-Ttext', '0x100', '--oformat', 'binary',
                    '-o', str(executable), str(obj)], check=True)
    data = executable.read_bytes()
    assert checks.require_hash(data, expected_hash, 'BOOT.COM')['sha256'] == expected_hash
    damaged = bytes([data[0] ^ 1]) + data[1:]
    with pytest.raises(ValueError, match='identity does not match'):
        checks.require_hash(damaged, expected_hash, 'BOOT.COM')


@pytest.mark.parametrize('kind', ['case_collision', 'directory', 'symlink'])
def test_snapshot_never_silently_ignores_or_aliases_directory_entries(tmp_path, kind):
    (tmp_path / 'target').write_bytes(b'authored')
    if kind == 'case_collision':
        (tmp_path / 'TARGET').write_bytes(b'other')
    elif kind == 'directory':
        (tmp_path / 'nested').mkdir()
    elif kind == 'symlink':
        (tmp_path / 'linked').symlink_to(tmp_path / 'target')
    with pytest.raises(ValueError):
        checks.snapshot_directory(tmp_path)


def test_new_private_output_rejects_git_ancestry_and_existing_directories(tmp_path):
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    (checkout / '.git').write_text('gitdir: test-control')
    with pytest.raises(ValueError, match='outside a Git checkout'):
        checks.new_private_output(checkout / 'private')
    assert not (checkout / 'private').exists()
    out = checks.new_private_output(tmp_path / 'private')
    assert out.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        checks.new_private_output(out)


def test_wrong_fix_input_retains_failure_receipt_before_execution(tmp_path, monkeypatch):
    files = {}
    for name in ('patcher', 'config', 'bootstrap', 'emulator'):
        files[name] = tmp_path / name
        files[name].write_bytes(b'authored invalid input')
    output = tmp_path / 'result'
    monkeypatch.setattr(fix.subprocess, 'run', lambda *a, **k: pytest.fail('Execution before input admission'))
    argv = [arg for name, path in files.items() for arg in ('--' + name, str(path))]
    with pytest.raises(ValueError, match='GW_FIX.EXE identity'):
        fix.main(argv + ['--case', 'real', '--output', str(output)])
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['qualified'] is False
    assert receipt['final_files'] == {}
    assert 'completion_verification' not in receipt
    assert list((output / 'disk').iterdir()) == []


def test_unknown_vendor_predecessor_retains_failure_receipt(tmp_path, monkeypatch):
    before = tmp_path / 'before'
    before.mkdir()
    (before / 'GW').write_bytes(b'authored unrecognized predecessor')
    (before / 'INSTALL.PRO').write_bytes(b'authored unrecognized installation')
    output = tmp_path / 'result'
    monkeypatch.setattr(update.subprocess, 'run', lambda *a, **k: pytest.fail('Execution before input admission'))
    argv = ['--before', str(before), '--output', str(output)]
    for name in ('patch', 'candidate', 'bootstrap', 'emulator'):
        argv.extend(['--' + name, str(tmp_path / name)])
    with pytest.raises(ValueError, match='outside the inspected input profiles'):
        update.main(argv)
    receipt = json.loads((output / 'receipt.json').read_text())
    assert receipt['qualified'] is False
    assert receipt['completed_at_bootstrap'] is False
    assert receipt['final_files'] == {}
