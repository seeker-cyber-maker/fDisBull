"""Host acceptance of the newly authored S16 fixture and independent oracles."""
from dataclasses import replace
import base64
from copy import deepcopy
import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import time
from types import SimpleNamespace

import pytest

from support.qemu_sb16_s16_recovery_fixture import (
    BLOCK_BYTES, BLOCKS, ENCODINGS, FIELDS, FRONTIERS, GEOMETRIES,
    POSITIVE_CASES, PROFILE, REPORT_SIZE, RING_BYTES, UNSAFE_CASES, VoiceCase,
    assembly, block_pcm, build_fixture, expected_dma_progress, parse_report, ring_pcm,
)


def _report(**values):
    return (b'S16R' + b''.join(values.get(name, 0).to_bytes(width, 'little')
            for name, width in FIELDS) + bytes(2 * BLOCKS))


def test_new_authorship_and_case_ids_are_explicit_and_unique():
    assert PROFILE == 'fdisbull-sb16-s16-recovery-20261119-1'
    assert len(POSITIVE_CASES) == 18 and len(UNSAFE_CASES) == 5
    names = [case.name for case in (*POSITIVE_CASES, *UNSAFE_CASES)]
    assert len(names) == len(set(names))
    for case in (*POSITIVE_CASES, *UNSAFE_CASES):
        assert VoiceCase(**case.record()) == case
    assert {case.frontier for case in POSITIVE_CASES} == set(FRONTIERS)
    assert {case.encoding for case in UNSAFE_CASES} >= {'s8', 'u16'}


def test_single_cycle_geometry_keeps_progress_before_completion():
    # Native gate 01 observed these first credits under the fixed 32000-Hz
    # headless output graph. This checks fixture geometry, not native timing.
    expected = {1: (4096, 514, 8000), 2: (8192, 4096, 32000)}
    for case in POSITIVE_CASES[:4]:
        block_bytes, initial_credit, rate = expected[case.channels]
        assert not case.auto and case.frontier == 'running'
        assert case.bits == 16 and case.rate == rate
        assert case.block_bytes == block_bytes
        assert 0 < initial_credit < case.block_bytes <= case.dma_bytes == RING_BYTES
        assert case.block_bytes % (2 * case.channels) == 0


def test_partial_stereo_witnesses_stay_misaligned_after_block_growth():
    cases = {case.geometry: case for case in UNSAFE_CASES}
    partial_block, partial_ring = cases['partial-block'], cases['partial-ring']
    assert partial_block.channels == partial_ring.channels == 2
    assert partial_block.bits == partial_ring.bits == 16
    assert (partial_block.block_bytes, partial_block.dma_bytes) == (8194, 8192)
    assert (partial_ring.block_bytes, partial_ring.dma_bytes) == (8192, 8190)
    assert partial_block.block_bytes % 4 == partial_ring.dma_bytes % 4 == 2
    # Each negative witness exceeds its DMA extent by exactly the partial
    # stereo frame; it is captured at started, before a progress requirement.
    assert partial_block.block_bytes - partial_block.dma_bytes == 2
    assert partial_ring.block_bytes - partial_ring.dma_bytes == 2


@pytest.mark.parametrize('fields', [
    dict(name='../escape'), dict(name=''), dict(channels=True), dict(channels=3),
    dict(auto=1), dict(fifo=0), dict(rate=True), dict(rate=4999), dict(rate=45001),
    dict(frontier='anything'), dict(encoding='float'), dict(geometry='anything'),
    dict(capture_format='s16'), dict(auto=True, frontier='future-rate'),
    dict(auto=True, frontier='inactive'),
    dict(channels=1, geometry='partial-block'),
    dict(channels=2, geometry='partial-ring', frontier='masked'),
])
def test_invalid_fixture_profile_refuses_before_assembly(fields):
    with pytest.raises(ValueError):
        assembly(replace(VoiceCase('control'), **fields))


def test_report_keeps_signed_voice_and_dma_word_units_explicit():
    raw = _report(bits=16, channels=2, initial_address=0x8000,
                  selected_address=0x8400, initial_count=4095, selected_count=3071)
    report = parse_report(raw)
    assert len(raw) == REPORT_SIZE and report['generations'] == [0] * BLOCKS
    assert expected_dma_progress(report['initial_address'], report['selected_address']) == {
        'units': 1024, 'bytes': 2048}
    assert expected_dma_progress(0x8000, 0x8400, bits=8)['bytes'] == 1024


@pytest.mark.parametrize('raw', [b'', b'S16R', b'BAD!' + bytes(REPORT_SIZE - 4),
                               _report() + b'\x00', _report()[:-1], bytearray(_report())])
def test_report_refuses_truncation_wrong_magic_and_nonbytes(raw):
    with pytest.raises(ValueError):
        parse_report(raw)


@pytest.mark.parametrize('start,end,bits', [
    (65535, 0, 16), (-1, 0, 16), (0, 65536, 16),
    (True, 1, 16), (0, 1, True), (0, 1, 32),
])
def test_dma_progress_never_infers_wrap_or_sample_width(start, end, bits):
    with pytest.raises(ValueError):
        expected_dma_progress(start, end, bits=bits)


def test_independent_signed_source_spans_both_signs_and_asymmetric_channels():
    raw = block_pcm(0, 0)
    words = struct.unpack('<128h', raw)
    assert min(words) < 0 < max(words)
    assert all(left != right for left, right in zip(words[::2], words[1::2]))
    assert raw[:8] == struct.pack('<4H', 0x1357, 0x6288, 0xb1b9, 0x00ea)
    assert block_pcm(31, 65535) != raw
    generations = [0] * BLOCKS
    initial = ring_pcm(generations)
    assert len(initial) == RING_BYTES
    generations[7] = 1
    changed = ring_pcm(generations)
    assert changed[:7 * BLOCK_BYTES] == initial[:7 * BLOCK_BYTES]
    assert changed[8 * BLOCK_BYTES:] == initial[8 * BLOCK_BYTES:]
    assert changed[7 * BLOCK_BYTES:8 * BLOCK_BYTES] == block_pcm(7, 1)


@pytest.mark.parametrize('block,generation,bits', [
    (-1, 0, 16), (BLOCKS, 0, 16), (True, 0, 16), (0, -1, 16),
    (0, 65536, 16), (0, True, 16), (0, 0, 32),
])
def test_ring_oracle_refuses_unknown_block_or_generation(block, generation, bits):
    with pytest.raises(ValueError):
        block_pcm(block, generation, bits=bits)


def _nasm():
    value = os.environ.get('NASM') or shutil.which('nasm')
    if not value:
        if os.environ.get('FDISBULL_REQUIRE_S16_RECOVERY_ASSEMBLY') == '1':
            pytest.fail('Pinned NASM is required for the S16 recovery assembly gate')
        pytest.skip('NASM is needed for authored guest assembly')
    return value


@pytest.mark.parametrize('case', (*POSITIVE_CASES, *UNSAFE_CASES), ids=lambda x: x.name)
def test_actual_assembled_report_static_arena_and_frontiers(tmp_path, case):
    code, offsets = build_fixture(tmp_path, _nasm(), case)
    raw = code[offsets['report'] - 256:offsets['report_end'] - 256]
    report = parse_report(raw)
    assert len(code) < 0xff00
    assert (report['bits'], report['channels'], report['fifo'], report['auto']) == (
        case.bits, case.channels, int(case.fifo), int(case.auto))
    assert report['frontier'] == FRONTIERS.index(case.frontier)
    assert report['geometry'] == GEOMETRIES.index(case.geometry)
    assert report['encoding'] == ENCODINGS.index(case.encoding)
    assert report['rate'] == case.rate and report['future_rate'] == 22050
    assert report['block_bytes'] == case.block_bytes and report['dma_bytes'] == case.dma_bytes
    assert report['failure'] == report['irq_count'] == report['stage'] == 0
    for label in ('ready', 'started', 'selected', 'busy'):
        assert code[offsets[label] - 256] == 0x90
    assert code[offsets['arena'] - 256:offsets['arena'] - 256 + 16384] == bytes(16384)


@pytest.mark.parametrize('case', POSITIVE_CASES[:8], ids=lambda x: x.name)
def test_emitted_dsp_count_is_channel_samples_without_a_stereo_multiplier(tmp_path, case):
    from capstone import CS_ARCH_X86, CS_MODE_16, Cs
    code, offsets = build_fixture(tmp_path, _nasm(), case)
    raw = code[offsets['start_voice'] - 256:offsets['fill_block'] - 256]
    operations = list(Cs(CS_ARCH_X86, CS_MODE_16).disasm(raw, offsets['start_voice']))
    assert sum(op.size for op in operations) == len(raw)
    values, pending, targets = [], None, set()
    for op in operations:
        if op.mnemonic == 'mov' and op.op_str.startswith('al, '):
            pending = int(op.op_str.split(', ')[1], 0)
        elif op.mnemonic == 'call':
            assert pending is not None
            values.append(pending)
            targets.add(op.op_str)
            pending = None
        else:
            assert op.mnemonic == 'ret'
    assert len(targets) == 1 and len(values) == 4
    assert values[0] == (0xb0 | (int(case.auto) << 2) | (int(case.fifo) << 1))
    assert values[1] == (0x10 | ((case.channels - 1) << 5))
    assert 1 + values[2] + (values[3] << 8) == case.block_bytes // 2


def _clock():
    return dict(format='authored-clock-double', context='machine', run='run-a',
        epoch='observation-a', sequence=1, host_monotonic_ns=100,
        session=dict(state='stopped', scope='all machine vCPUs'),
        native_state=dict(running=False, singlestep=False, status='debug'),
        clock_profile=dict(profile='virtual'), virtual_ns=5,
        counter=dict(value=10, native=dict(mode='none', icount=10)),
        virtual_clock=dict(domain='QEMU_CLOCK_VIRTUAL', native={
            'api-version': 1, 'epoch': 1, 'status': 'debug', 'virtual-ns': 5,
            'running': False, 'pending-stop': False, 'budget-supported': True,
            'budget-state': 'stopped', 'budget-token': 'original',
            'budget-start-ns': 1, 'budget-deadline-ns': 5,
            'budget-fired-ns': 5, 'budget-stopped-ns': 5}))


@pytest.mark.parametrize('field,value', [
    ('epoch', 2), ('pending-stop', True), ('status', 'paused'), ('budget-state', 'cancelled'),
    ('budget-start-ns', 2), ('budget-deadline-ns', 6), ('budget-fired-ns', 6),
    ('budget-stopped-ns', 6), ('budget-token', 'other'), ('unknown-native-field', 1),
])
def test_passive_clock_comparison_does_not_drop_hidden_native_changes(field, value):
    from test_qemu_sb16_s16_recovery_native import stationary_clock
    before = _clock()
    after = deepcopy(before)
    after.update(sequence=2, host_monotonic_ns=101)
    stationary_clock(before, after)
    after['virtual_clock']['native'][field] = value
    with pytest.raises(AssertionError):
        stationary_clock(before, after)


@pytest.mark.parametrize('field,value', [('sequence', 1), ('sequence', 0),
                                       ('host_monotonic_ns', 100), ('host_monotonic_ns', 99)])
def test_observation_metadata_must_itself_advance(field, value):
    from test_qemu_sb16_s16_recovery_native import stationary_clock
    before = _clock()
    after = deepcopy(before)
    after.update(sequence=2, host_monotonic_ns=101)
    after[field] = value
    with pytest.raises(AssertionError):
        stationary_clock(before, after)


def _state():
    return dict(cpu=dict(registers={'eax': '0x00000001'}, hidden_register='keep'),
        report_hex='00', report=dict(stage=2), arena_hex='0000', ring_hex='00',
        device=dict(voice=True, dma=5), pcm_hex='0080', pcm_sha256='known', chunks=[{'frames': 2}],
        clock=_clock(), audio=dict(window='first', sample_format={'rate': 32000},
            native={'epoch': 1, 'token': 'first', 'frames': 2, 'channels': 1}))


@pytest.mark.parametrize('section,field,value', [
    ('cpu', 'hidden_register', 'changed'), ('report', 'stage', 3),
    ('device', 'dma', 1), ('native-clock', 'budget-fired-ns', 6),
    ('native-clock', 'unknown-field', True), ('native-audio', 'frames', 3),
    ('native-audio', 'channels', 2), ('clock', 'virtual_ns', 6),
])
def test_restored_full_future_oracle_keeps_cpu_and_all_native_content(section, field, value):
    from test_qemu_sb16_s16_recovery_native import assert_exact
    expected = _state()
    actual = deepcopy(expected)
    actual['clock'].update(run='new-run', epoch='fresh-observation', sequence=1, host_monotonic_ns=200)
    actual['clock']['native_state']['status'] = 'paused'
    actual['clock']['virtual_clock']['native'].update(epoch=2, status='paused')
    actual['clock']['virtual_clock']['native']['budget-token'] = 'fresh-budget'
    actual['audio']['window'] = 'fresh-window'
    actual['audio']['native'].update(epoch=2, token='fresh-window')
    assert_exact(actual, expected, restored=True)
    target = (actual['clock']['virtual_clock']['native'] if section == 'native-clock' else
              actual['audio']['native'] if section == 'native-audio' else actual[section])
    target[field] = value
    with pytest.raises(AssertionError):
        assert_exact(actual, expected, restored=True)


@pytest.mark.parametrize('order,byte_order', [('<', 1234), ('>', 4321)])
@pytest.mark.parametrize('damage', ['unsupported-width', 'out-of-range-rate',
                                  'zero-resampler-increment', 'destination-signedness'])
def test_core_corruption_changes_only_the_declared_native_scalar(order, byte_order, damage):
    from test_qemu_sb16_s16_recovery_native import CORE2_FIELDS, CORRUPTIONS, corrupt_core2
    values = dict.fromkeys(CORE2_FIELDS, 0)
    values.update(magic=0x4644424155443032, version=2, sample_size=16, byte_order=byte_order,
                  has_sw=1, sw_bits=16, sw_signed=1, sw_freq=11025, rate_increment=3)
    raw = struct.pack(order+str(len(CORE2_FIELDS))+'Q', *(values[key] for key in CORE2_FIELDS))+b'payload-stays-exact'
    changed = base64.b64decode(corrupt_core2(base64.b64encode(raw).decode(), damage), validate=True)
    field, value, _ = CORRUPTIONS[damage]
    offset = 8*CORE2_FIELDS.index(field)
    assert changed[:offset] == raw[:offset] and changed[offset+8:] == raw[offset+8:]
    assert struct.unpack_from(order+'Q', changed, offset)[0] == value
    assert changed != raw


@pytest.mark.parametrize('raw', [b'', bytes(343), bytes(344), b'invalid'])
def test_core_corruption_refuses_unknown_or_truncated_header(raw):
    from test_qemu_sb16_s16_recovery_native import corrupt_core2
    with pytest.raises(ValueError):
        corrupt_core2(base64.b64encode(raw).decode(), 'unsupported-width')


def test_new_native_matrix_bounds_describe_all_authored_cases_and_owner_caps():
    from test_qemu_sb16_s16_recovery_native import CORRUPTIONS, LEGACY_CASES, NATIVE_BOUNDS
    assert NATIVE_BOUNDS['cases'] == len(POSITIVE_CASES)+len(UNSAFE_CASES)+len(LEGACY_CASES)+len(CORRUPTIONS)+1 == 32
    assert NATIVE_BOUNDS['owners'] == 4*len(POSITIVE_CASES)+len(UNSAFE_CASES)+len(LEGACY_CASES)+2*len(CORRUPTIONS)+2 == 91
    assert NATIVE_BOUNDS['work_seconds'] == 600 and NATIVE_BOUNDS['future_ns'] == 600_000_000


def test_native_matrix_rejects_replaced_output_and_bounds_its_own_bytes(tmp_path):
    from test_qemu_sb16_s16_recovery_native import NATIVE_BOUNDS, Runtime
    output = tmp_path/'owned'
    output.mkdir(mode=0o700)
    info = output.stat()
    runtime = object.__new__(Runtime)
    runtime.config = {'output_identity': dict(device=info.st_dev, inode=info.st_ino)}
    runtime.output = output
    runtime.deadline = time.monotonic()+10
    assert runtime.resources()['logical'] == 0

    with (output/'sparse.bin').open('xb') as stream:
        stream.truncate(NATIVE_BOUNDS['output_bytes']+1)
    with pytest.raises(AssertionError, match="'logical'"):
        runtime.resources()

    output.rename(tmp_path/'original')
    output.mkdir(mode=0o700)
    with pytest.raises(AssertionError, match='directory or backing volume identity changed'):
        runtime.resources()


def test_resource_accounting_counts_root_and_fifo_without_opening_it(tmp_path):
    from test_qemu_sb16_s16_recovery_native import _usage
    root = tmp_path/'owned'
    root.mkdir()
    data = root/'bytes'
    data.write_bytes(b'authored bytes')
    fifo = root/'gdb.in'
    os.mkfifo(fifo)
    result = _usage(root)
    assert result['logical'] == len(b'authored bytes')
    assert result['allocated'] == sum(path.lstat().st_blocks*512 for path in (root, data, fifo))


def test_resource_accounting_refuses_an_escaping_symlink(tmp_path):
    from test_qemu_sb16_s16_recovery_native import _usage
    root = tmp_path/'owned'
    root.mkdir()
    outside = tmp_path/'outside'
    outside.write_bytes(b'unowned')
    (root/'escape').symlink_to(outside)
    with pytest.raises(AssertionError, match='escaped'):
        _usage(root)


def test_actual_project_store_mismatch_refuses_before_any_debugger_owner(tmp_path, monkeypatch):
    from fdisbull.project import Project
    from test_qemu_sb16_s16_recovery_native import Runtime, CaseRun
    selected = tmp_path/'selected-store'
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(selected))
    source = tmp_path/'CONTROL.COM'
    source.write_bytes(b'\x90\xc3')
    runtime = Runtime.__new__(Runtime)
    runtime.store = tmp_path/'required-owned-store'
    runtime.resources = lambda: None
    run = CaseRun.__new__(CaseRun)
    run.runtime = runtime
    calls = []
    def unexpected(*args, **kwargs):
        calls.append(True)
        raise AssertionError('Wrong store reached debugger construction')
    with Project.create(tmp_path/'control.fdb', source, image='com') as project:
        assert project.db.store.root.resolve() == selected.resolve()
        monkeypatch.setattr(project, 'debugger', unexpected)
        with pytest.raises(AssertionError, match='TargetStore escaped'):
            with run.launch(project):
                raise AssertionError('Wrong store created a live session')
    assert calls == []


def test_cold_completion_verifies_control_bytes_not_the_last_read_receipt(tmp_path, monkeypatch):
    from test_qemu_sb16_s16_recovery_native import _cold
    import test_qemu_sb16_s16_recovery_native as native
    source, disk, admission = (tmp_path/name for name in ('S16REC.COM', 'boot.img', 'admission.json'))
    source.write_bytes(b'\x90')
    disk.write_bytes(b'authored image placeholder; never executed')
    admission.write_text('{}')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    runtime = SimpleNamespace(owners=0, config_path=admission, config_sha=sha(admission),
        root=tmp_path, store=tmp_path/'target-store')
    expected = _state()
    actual = deepcopy(expected)
    actual['clock'].update(run='cold', epoch='cold-observation', sequence=1, host_monotonic_ns=200)
    actual['clock']['virtual_clock']['native']['epoch'] = 2
    actual['clock']['virtual_clock']['native']['budget-token'] = 'cold-budget'
    actual['audio']['window'] = 'cold-window'
    actual['audio']['native'].update(epoch=2, token='cold-window')
    run = SimpleNamespace(runtime=runtime, directory=tmp_path, db=tmp_path/'project.fdb',
        source=source, disk=dict(image=disk, prepared_sha256=sha(disk), source_sha256='original'),
        case=VoiceCase('host-control-identity'), offsets={}, deadline=1e20,
        remaining=lambda ceiling: ceiling, processes=[], report={'entry_clock': _clock()})
    control = dict(future=expected, hot_window='hot-window')
    def completed(command, **kwargs):
        control_path = tmp_path/'cold-control.json'
        assert command[-2] == str(control_path) and command[-1] == sha(control_path)
        receipt = dict(passed=True, leader_reaped=True, group_gone=True, cleanup_error=None)
        kwargs['receipt_path'].write_text(json.dumps(receipt))
        child = dict(passed=True, cold_python_pid=os.getpid()+1, full_future_exact=True,
            owners=[dict(pid=1234567, reaped=True, returncode=0),
                    dict(pid=1234568, reaped=True, returncode=0)],
            samples={'cold-future': actual})
        (tmp_path/'cold-native-s16.json').write_text(json.dumps(child))
        return subprocess.CompletedProcess(command, 0, stdout='', stderr=''), receipt
    monkeypatch.setattr(native, 'run_owned_cold', completed)
    _cold(run, control)
    assert runtime.owners == 2 and run.report['cold']['passed']
    assert run.report['cold_control_sha256'] == sha(tmp_path/'cold-control.json')
    assert sha(tmp_path/'cold-native-s16.json') != run.report['cold_control_sha256']


def _owned_logs(tmp_path, *, qemu=b'authored emulator stderr\n', boot=b'authored serial\n'):
    from pathlib import Path
    temporary = tempfile.TemporaryDirectory(prefix='owned-', dir=tmp_path)
    root = Path(temporary.name)
    for name, value in (('qemu.log', qemu), ('boot.log', boot)):
        if value is not None:
            (root/name).write_bytes(value)
    return temporary, root, tmp_path/'retained', {}


def test_complete_owned_logs_are_hashed_and_copied_before_idempotent_cleanup(tmp_path):
    from test_qemu_sb16_s16_recovery_native import preserve_owner_logs
    temporary, root, retained, owner = _owned_logs(tmp_path)
    preserve_owner_logs(temporary, retained, SimpleNamespace(poll=lambda: 0), owner)
    temporary.cleanup()
    receipt = owner['native_logs']
    assert receipt['process_reaped'] and receipt['complete'] and receipt['cleanup_succeeded']
    assert receipt['cleanup_attempted'] and receipt['errors'] == [] and not root.exists()
    for name in ('qemu.log', 'boot.log'):
        value = (retained/name).read_bytes()
        row = receipt['files'][name]
        assert row['status'] == 'complete' and row['source_bytes'] == row['retained_bytes'] == len(value)
        assert row['full_sha256'] == row['retained_sha256'] == hashlib.sha256(value).hexdigest()
        assert (retained/name).stat().st_mode & 0o777 == 0o600
    temporary.cleanup()
    assert owner['native_logs'] is receipt


def test_missing_owned_log_is_explicit_and_still_cleans_temporary(tmp_path):
    from test_qemu_sb16_s16_recovery_native import preserve_owner_logs
    temporary, root, retained, owner = _owned_logs(tmp_path, boot=None)
    preserve_owner_logs(temporary, retained, SimpleNamespace(poll=lambda: 0), owner)
    with pytest.raises(FileNotFoundError):
        temporary.cleanup()
    receipt = owner['native_logs']
    assert not root.exists() and receipt['cleanup_succeeded'] and not receipt['complete']
    assert receipt['files']['boot.log']['status'] == 'missing'
    assert receipt['files']['boot.log']['full_sha256'] is None
    assert receipt['files']['qemu.log']['status'] == 'complete'


def test_oversized_log_retains_only_bounded_prefix_and_never_claims_full_hash(tmp_path):
    from test_qemu_sb16_s16_recovery_native import LOG_MAX_BYTES, preserve_owner_logs
    temporary, root, retained, owner = _owned_logs(tmp_path, qemu=b'x'*(LOG_MAX_BYTES+17))
    preserve_owner_logs(temporary, retained, SimpleNamespace(poll=lambda: 0), owner)
    with pytest.raises(ValueError, match='256KiB'):
        temporary.cleanup()
    receipt = owner['native_logs']
    row = receipt['files']['qemu.log']
    assert row['status'] == 'truncated' and row['source_bytes'] == LOG_MAX_BYTES+17
    assert row['retained_bytes'] == LOG_MAX_BYTES and row['full_sha256'] is None
    assert (retained/'qemu.log').read_bytes() == b'x'*LOG_MAX_BYTES
    assert not root.exists() and receipt['cleanup_succeeded'] and not receipt['complete']


def test_log_copy_permission_failure_still_attempts_other_log_and_original_cleanup(tmp_path, monkeypatch):
    import test_qemu_sb16_s16_recovery_native as native
    temporary, root, retained, owner = _owned_logs(tmp_path)
    original = native._copy_owned_log
    def copy(source, destination):
        if source.name == 'qemu.log':
            raise PermissionError('authored log-copy permission refusal')
        return original(source, destination)
    monkeypatch.setattr(native, '_copy_owned_log', copy)
    native.preserve_owner_logs(temporary, retained, SimpleNamespace(poll=lambda: 0), owner)
    with pytest.raises(PermissionError, match='permission refusal'):
        temporary.cleanup()
    receipt = owner['native_logs']
    assert receipt['files']['qemu.log']['status'] == 'error'
    assert receipt['files']['boot.log']['status'] == 'complete'
    assert not root.exists() and receipt['cleanup_succeeded'] and not receipt['complete']


def test_log_preservation_failure_keeps_an_already_active_primary(tmp_path, monkeypatch):
    import test_qemu_sb16_s16_recovery_native as native
    temporary, root, retained, owner = _owned_logs(tmp_path)
    def fail(*args):
        raise OSError('authored retained-log write failure')
    monkeypatch.setattr(native, '_copy_owned_log', fail)
    native.preserve_owner_logs(temporary, retained, SimpleNamespace(poll=lambda: 0), owner)
    primary = RuntimeError('actual first failure')
    with pytest.raises(RuntimeError) as caught:
        try:
            raise primary
        except RuntimeError:
            temporary.cleanup()
            raise
    assert caught.value is primary and not root.exists()
    assert not owner['native_logs']['complete'] and owner['native_logs']['cleanup_succeeded']
    assert primary.log_retention_receipt is owner['native_logs']
    assert any('retained-log write failure' in note for note in primary.__notes__)


def test_original_temporary_cleanup_error_is_recorded_without_masking_body(tmp_path):
    from test_qemu_sb16_s16_recovery_native import preserve_owner_logs
    temporary, root, retained, owner = _owned_logs(tmp_path)
    original = temporary.cleanup
    def clean_then_fail():
        original()
        raise OSError('authored temporary cleanup failure')
    temporary.cleanup = clean_then_fail
    preserve_owner_logs(temporary, retained, SimpleNamespace(poll=lambda: 0), owner)
    primary = RuntimeError('first guest-stop failure')
    with pytest.raises(RuntimeError) as caught:
        try:
            raise primary
        except RuntimeError:
            temporary.cleanup()
            raise
    assert caught.value is primary and not root.exists()
    receipt = owner['native_logs']
    assert receipt['cleanup_attempted'] and not receipt['cleanup_succeeded'] and not receipt['complete']
    assert receipt['errors'][-1]['stage'] == 'temporary-cleanup'


@pytest.mark.parametrize('poll_error', [False, True], ids=['still-running', 'poll-error'])
def test_missing_reap_proof_never_skips_original_temporary_cleanup(tmp_path, poll_error):
    from test_qemu_sb16_s16_recovery_native import preserve_owner_logs
    temporary, root, retained, owner = _owned_logs(tmp_path)
    def poll():
        if poll_error:
            raise OSError('authored owner-observation failure')
        return None
    preserve_owner_logs(temporary, retained, SimpleNamespace(poll=poll), owner)
    with pytest.raises((OSError, RuntimeError)):
        temporary.cleanup()
    assert not root.exists() and not owner['native_logs']['complete']
    assert owner['native_logs']['cleanup_attempted'] and owner['native_logs']['cleanup_succeeded']


@pytest.mark.parametrize('body_fails', [False, True], ids=['cleanup-only', 'body-and-cleanup'])
def test_actual_launch_path_preserves_body_if_session_exit_raises(tmp_path, body_fails):
    from test_qemu_sb16_s16_recovery_native import CaseRun
    primary, cleanup = RuntimeError('first stop sentinel'), OSError('session close sentinel')
    exits = []
    class Session:
        def __enter__(self):
            return self
        def _set_deadline(self, value):
            assert value == run.deadline
        def __exit__(self, kind, error, traceback):
            exits.append(error)
            raise cleanup
    tools = {key: {'path': 'never-executed'} for key in ('candidate', 'mcopy', 'qemu_img')}
    runtime = SimpleNamespace(project=lambda project: None, config={'tools': tools, 'firmware': {'root': 'never-used'}})
    run = CaseRun.__new__(CaseRun)
    run.runtime, run.directory, run.disk = runtime, tmp_path, {'image': tmp_path/'unused.img'}
    run.case, run.deadline, run.remaining = VoiceCase('context-check'), time.monotonic()+10, lambda ceiling: ceiling
    run.report = {}
    project = SimpleNamespace(debugger=lambda *args, **kwargs: Session())
    with pytest.raises(RuntimeError if body_fails else OSError) as caught:
        with run.launch(project):
            if body_fails:
                raise primary
    assert caught.value is (primary if body_fails else cleanup)
    assert exits == [primary if body_fails else None]
    assert run.report['context_cleanup_faults'][0]['context'] == 'debug-session'
    if body_fails:
        assert any('session close sentinel' in note for note in primary.__notes__)


@pytest.mark.parametrize('body_fails', [False, True], ids=['cleanup-only', 'body-and-cleanup'])
def test_actual_project_context_closes_database_and_preserves_body(tmp_path, monkeypatch, body_fails):
    from fdisbull.project import Project
    from test_qemu_sb16_s16_recovery_native import CaseRun
    import sqlite3
    monkeypatch.setenv('FDISBULL_TARGET_STORE', str(tmp_path/'objects'))
    run = CaseRun.__new__(CaseRun)
    run.source, run.db, run.report = tmp_path/'CONTROL.COM', tmp_path/'project.fdb', {}
    run.source.write_bytes(b'\x90\xc3')
    run.runtime = SimpleNamespace(project=lambda project: None)
    primary, cleanup = RuntimeError('body before project close'), OSError('project close sentinel')
    original = Project.__exit__
    exits = []
    def close_then_fail(project, *args):
        original(project, *args)
        exits.append(project)
        raise cleanup
    monkeypatch.setattr(Project, '__exit__', close_then_fail)
    with pytest.raises(RuntimeError if body_fails else OSError) as caught:
        with run.project(create=True):
            if body_fails:
                raise primary
    assert caught.value is (primary if body_fails else cleanup) and len(exits) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        exits[0].db.execute('SELECT 1')
    assert run.report['context_cleanup_faults'][0]['context'] == 'project'
