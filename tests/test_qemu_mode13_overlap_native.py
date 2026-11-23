"""Same-byte DOSBox-X/QEMU BIOS reapply, with source-timer checkpoint replay."""
from base64 import b64decode
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from fdisbull.qemu_dos_checkpoint import _unarchive
from support.dos_process_fixture import digest
from test_paired_mode13_reapply_native import _dosbox_reapply_witness, _pre_post, _program
from test_paired_video_frame_native import _write_json
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, live_word, process_record, read_bytes
from test_qemu_mode13_paired_phase_native import (
    _advance_exact_window, _mode13_owner, _read_geometry, _verify_rows,
)


pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_MODE13_OVERLAP') != '1',
    reason='Select the exact paired producers for native Mode 13h overlap',
)
PROFILE = 'dosbox-mode13-overlap'
MODEL = 'qemu-vga-chain4-dosbox-mode13-overlap-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-7'
GUEST_SHA = '1742f5a2317b70365de38404732ad04128976543e862e0a913f38d3b02db2c9b'
REFERENCE_PRODUCER = '8eaf15b372b2cf34f22cc552241085e6ff56edcdba3be6f399b3ca2134ce2a49'
REFERENCE_TRACE = '125941baeb505861639429b7c5c0aedba467b5ed2be4c84202ea1c9615b87cd5'
# Rounded producer scheduler measurements from the causal witness. The
# matching input/output unit is a fraction of each producer's physical line.
REFERENCE_OFFSET = 17773
REFERENCE_LINE = 31778
HEIGHT = 200
PREFIX = 65
WITNESS_COLUMN = 73
LEGACY_VGA_MEMORY = 0xa0000


def _native(debug):
    return debug.video_frame_observe()['native']


def _logical(receipt):
    value = deepcopy(receipt)
    value.pop('token')
    value.pop('epoch')
    if 'frame' in value:
        value['frame'].pop('epoch')
    return value


def _reference(evidence):
    assert evidence['producer_sha256'] == REFERENCE_PRODUCER and evidence['fixture_sha256'] == GUEST_SHA
    assert evidence['raw_before'] == evidence['raw_after']
    assert evidence['post_phases'] == [1, 0, 1, 1, 1, 1, 1]
    frames = evidence['after_rasters']
    initial_id = evidence['before_warm']['frame_id']
    assert [frame['identity']['frame_id'] for frame in frames] == list(range(initial_id + 1, initial_id + 8))
    assert len({frame['identity']['mode_id'] for frame in frames}) == 1
    mixed = frames[0]['receipt']['source_timing']
    assert mixed['line_period_ns'] == REFERENCE_LINE
    assert mixed['rows'][0]['scheduled_ns'] - mixed['first_callback_scheduled_ns'] == REFERENCE_OFFSET
    assert mixed['transition_overflow'] is False
    by_id = {entry['sequence']: entry for entry in mixed['transition_events']}
    mixed_vertical = by_id[mixed['vertical_sequence']]
    setup = by_id[mixed_vertical['setup_sequence']]
    commit = by_id[setup['sequence'] + 1]
    assert setup['kind'] == 'setup-entry' and commit['kind'] == 'setup-commit'
    assert (setup['logical_rows_seen'], commit['logical_rows_seen'], mixed_vertical['logical_rows_seen']) == (27, 0, 198)
    assert setup['scheduled_ns'] == commit['scheduled_ns'] < mixed_vertical['scheduled_ns']
    assert setup['line_delay_ns'] == commit['line_delay_ns'] == mixed_vertical['line_delay_ns'] == REFERENCE_LINE
    assert not mixed_vertical['setup_in_progress']
    for index, frame in enumerate(frames):
        timing = frame['receipt']['source_timing']
        rows = timing['rows']
        scale = 1 if index == 0 else 2
        assert [row['physical_line'] for row in rows] == list(range(timing['physical_phase'], 400, 2))
        intervals = [right['scheduled_ns'] - left['scheduled_ns'] for left, right in zip(rows, rows[1:])]
        assert len(intervals) == HEIGHT - 1 and all(abs(gap - scale * REFERENCE_LINE) <= 2 for gap in intervals)
        assert all(row['line_delay_ns'] == REFERENCE_LINE for row in rows)
    return frames


def _reapply(debug, offsets, geometry, evidence):
    """Execute the unchanged fixture's BIOS edge and retain its guest timing."""
    period, line = geometry['period_ns'], geometry['line_ns']
    process = process_record(debug)
    addresses = {name: com_address(process, value) for name, value in offsets.items()}
    old = _native(debug)['mode-setup']
    evidence['prior_mode_setup'] = old
    assert not old.get('same-mode-reapply')
    now = debug.clock_observe()['virtual_ns']
    _advance_exact_window(debug, now + 2 * period)
    warm = debug.video_frame_start()['native']
    first_warm = (warm['virtual-ns'] // period + 1) * period
    _advance_exact_window(debug, first_warm + line // 4 + 399 * line + line // 2)
    baseline = _native(debug)['frame']
    _verify_rows(baseline, first_warm, 1, geometry)
    assert 'reapply-overlap' not in baseline

    debug.write_memory(addresses['go'], '01', expected_hex='00', space='physical')
    park(debug, addresses['bios13'])
    before = debug.clock_observe()['virtual_ns']
    assert live_word(debug.registers(), 'rax', 'eax', 'ax') == 0x13
    assert read_bytes(debug, addresses['bios13'], 2) == b'\xcd\x10'
    assert read_bytes(debug, addresses['returned'], 1) == b'\0'
    park(debug, addresses['held'])
    after = debug.clock_observe()['virtual_ns']
    assert read_bytes(debug, addresses['returned'], 1) == b'\x01'
    _pre_post(lambda address, length: read_bytes(debug, address, length), addresses, evidence)
    retired = _native(debug)
    evidence.update(before_bios_ns=before, returned_bios_ns=after, retired=retired)
    assert retired['state'] == 'invalidated' and retired['token'] == warm['token']
    setup = retired['mode-setup']
    assert setup['same-mode-reapply'] is True
    assert old['committed-ns'] < before <= setup['committed-ns'] <= after
    first = (setup['committed-ns'] // period + 1) * period
    evidence['first_mixed_start_ns'] = first
    assert after < first, evidence
    return setup, first


def _pending(debug, overlap, *, rows, next_new, next_retained):
    value = _native(debug)
    assert value['model'] == MODEL and value['state'] == 'observing'
    assert value['reapply-overlap'] == overlap and value['rows-sampled'] == rows
    assert not value.get('frame')
    assert value['overlap-next-new-ns'] == next_new
    assert value['overlap-next-retained-ns'] == next_retained
    assert value['next-deadline-ns'] == min(next_new, next_retained)
    assert value['virtual-ns'] < value['next-deadline-ns']
    return value


def _checkpoint(debug, project, name, observed, prefix_due):
    artifact = debug.save_state(name, max_bytes=96 * 1024 * 1024)
    box = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?', (artifact['artifact'],)).fetchone()
    payload = bytes(box['data'])
    assert sha256(payload).hexdigest() == box['sha256']
    _, bundle = _unarchive(payload, metadata_only=True)
    native = bundle['instrumentation']
    assert sha256(native['state'].encode()).hexdigest() == native['sha256']
    sidecar = json.loads(native['state'])
    assert sidecar['format'] == FORMAT
    video = sidecar['video-frame']
    assert video['info'] == observed
    assert video['timer-pending'] is True and video['timer-expire-ns'] == observed['next-deadline-ns']
    prefix = video['partial-rows']
    assert [row['row'] for row in prefix] == list(range(len(prefix_due)))
    assert [row['intended-ns'] for row in prefix] == prefix_due
    line = observed['reapply-overlap']['line-period-ns']
    assert all(0 <= row['actual-ns'] - due < line // 8 for row, due in zip(prefix, prefix_due, strict=True))
    rgb = b64decode(video['partial-rgb-base64'], validate=True)
    assert len(rgb) == len(prefix_due) * 320 * 3
    assert sha256(rgb).hexdigest() == video['partial-sha256']
    if len(prefix_due) == PREFIX:
        offset = ((PREFIX - 1) * 320 + WITNESS_COLUMN) * 3
        assert rgb[offset:offset + 3] == b'\0\0\0'
    return artifact['artifact'], dict(sidecar_sha256=native['sha256'], video=video)


def _reach_partial(debug, overlap):
    """Prove alternate timer consumption before taking a nonempty prefix."""
    new = overlap['new-first-ns']
    retained = overlap['retained-first-ns']
    line = overlap['line-period-ns']
    _advance_exact_window(debug, new + line // 8)
    _pending(debug, overlap, rows=0, next_new=new + line, next_retained=retained)
    _advance_exact_window(debug, retained + line // 8)
    _pending(debug, overlap, rows=1, next_new=new + line, next_retained=retained + line)
    _advance_exact_window(debug, retained + (PREFIX - 1) * line + line // 8)
    return _pending(debug, overlap, rows=PREFIX, next_new=new + PREFIX * line,
                    next_retained=retained + PREFIX * line)


def _complete_three(debug, overlap, first, geometry, sequence):
    line = geometry['line_ns']
    period = geometry['period_ns']
    retained = overlap['retained-first-ns']
    stages = ((1, first, retained + (HEIGHT - 1) * line),
              (0, first + period, first + period + line // 4 + 398 * line),
              (1, first + 2 * period, first + 2 * period + line // 4 + 399 * line))
    before_write = _native(debug)
    for row in (PREFIX - 1, PREFIX):
        address = LEGACY_VGA_MEMORY + row * 320 + WITNESS_COLUMN
        assert read_bytes(debug, address, 1) == b'\0'
        debug.write_memory(address, '0f', expected_hex='00', space='physical')
        assert read_bytes(debug, address, 1) == b'\x0f'
    assert _native(debug) == before_write

    complete = []
    witness = []
    for index, (phase, origin, last_due) in enumerate(stages):
        _advance_exact_window(debug, last_due + line // 2)
        result = _native(debug)
        frame = result['frame']
        assert not {'reapply-overlap', 'overlap-next-new-ns', 'overlap-next-retained-ns'}.intersection(result)
        assert frame['frame-id'] == result['frame-sequence'] == sequence + index + 1
        assert frame['stream-generation'] == result['stream-generation'] and frame['epoch'] == result['epoch']
        if index == 0:
            assert frame['source-phase'] == phase and frame['reapply-overlap'] == overlap
            assert frame['frame-start-ns'] == origin and frame['period-ns'] == period and frame['line-period-ns'] == line
            assert (frame['width'], frame['height'], frame['stride']) == (320, 200, 960)
            rows = frame['rows']
            assert [row['row'] for row in rows] == list(range(HEIGHT))
            due = [retained + row * line for row in range(HEIGHT)]
            assert [row['intended-ns'] for row in rows] == due
            assert all(0 <= row['actual-ns'] - intended < line // 8 for row, intended in zip(rows, due, strict=True))
            assert frame['first-sample-ns'] == rows[0]['actual-ns']
            assert frame['last-sample-ns'] == rows[-1]['actual-ns'] == frame['completed-ns']
        else:
            assert 'reapply-overlap' not in frame
            _verify_rows(frame, origin, phase, geometry)
        points = [[WITNESS_COLUMN, PREFIX - 1], [WITNESS_COLUMN, PREFIX]]
        probe = debug.video_frame_probe(points, stream=result['token'], frame_id=frame['frame-id'])
        assert probe['frame'] == frame and probe['native'] == result
        witness.append([sample['rgb'] for sample in probe['samples']])
        complete.append(_logical(result))
    old = [0, 0, 0]
    updated = witness[0][1]
    assert updated != old
    assert witness == [[old, updated], [updated, updated], [updated, updated]]
    return dict(frames=complete, live_row_witness=witness)


def _restore(debug, artifact, observed):
    previous = debug.vm.process
    receipt = debug.load_state(artifact, timeout_ms=60000)
    assert receipt['instrumentation']['format'] == FORMAT
    assert debug.vm.process is not previous and previous.poll() == 0
    restored = _native(debug)
    assert restored['token'] != observed['token'] and restored['epoch'] != observed['epoch']
    assert _logical(restored) == _logical(observed)


def test_native_mode13_reapply_overlap_matches_dosbox_and_restores(tmp_path, clock_runtime, clock_disk):
    assert os.environ.get('FDISBULL_REQUIRE_DOSBOX_CHAIN4_TIMING') == '1'
    assert os.environ['FDISBULL_DOSBOX_CHAIN4_TIMING_SHA256'] == REFERENCE_PRODUCER
    legacy_dir = tmp_path / 'dosbox-reference'
    legacy_dir.mkdir()
    legacy = _dosbox_reapply_witness(legacy_dir)
    legacy_frames = _reference(legacy)
    candidate_dir = tmp_path / 'qemu-candidate'
    candidate_dir.mkdir()
    code, offsets = _program(candidate_dir, clock_runtime['nasm'])
    assert sha256(code).hexdigest() == legacy['fixture_sha256'] == GUEST_SHA
    evidence = {'reference_causal_trace_sha256': REFERENCE_TRACE,
                'fresh_dosbox_receipt_sha256': digest(legacy_dir / 'dosbox-mode13-reapply.json')}
    try:
        with _mode13_owner(candidate_dir, clock_runtime, clock_disk, code, evidence,
                           profile=PROFILE) as (project, debug):
            process = process_record(debug)
            park(debug, com_address(process, offsets['warm']))
            prior, geometry = _read_geometry(debug)
            setup, first = _reapply(debug, offsets, geometry, evidence)
            returned, returned_geometry = _read_geometry(debug)
            assert prior['raw'] == returned['raw'] and returned_geometry == geometry
            assert evidence['raw_before'] == legacy['raw_before'] and evidence['raw_after'] == legacy['raw_after']
            line = geometry['line_ns']
            new = first + line // 4
            retained = new + line * REFERENCE_OFFSET // REFERENCE_LINE
            overlap = {'new-first-ns': new, 'retained-first-ns': retained, 'line-period-ns': line}
            evidence['independent_schedule'] = overlap
            started = debug.video_frame_start()['native']
            assert started['mode-setup'] == setup and started['start-ns'] < first
            sequence = started['frame-sequence']
            _advance_exact_window(debug, new - line // 8)
            early = _pending(debug, overlap, rows=0, next_new=new, next_retained=retained)
            early_id, evidence['early_checkpoint'] = _checkpoint(debug, project, 'overlap-early.qcow2', early, [])
            partial = _reach_partial(debug, overlap)
            prefix_due = [retained + row * line for row in range(PREFIX)]
            partial_id, evidence['partial_checkpoint'] = _checkpoint(debug, project, 'overlap-partial.qcow2', partial, prefix_due)
            expected = _complete_three(debug, overlap, first, geometry, sequence)
            evidence['baseline'] = expected
            assert [item['frame']['source-phase'] for item in expected['frames']] == [
                item['lattice']['physical_phase'] for item in legacy_frames[:3]]
            # A complete replay has exactly the same future, including every
            # actual callback, pixel digest, pending state and frame id.
            checkpoints = [('early', early_id, early), ('partial', partial_id, partial)]
            for name, artifact, state in checkpoints:
                _restore(debug, artifact, state)
                if name == 'early':
                    assert _logical(_reach_partial(debug, overlap)) == _logical(partial)
                replay = _complete_three(debug, overlap, first, geometry, sequence)
                assert replay == expected
                evidence[f'hot_{name}'] = replay
            database = project.path
            last_hot_owner = debug.vm.process
        assert last_hot_owner.poll() == 0

        tool = str(Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True))
        with Project(database) as project:
            with project.debugger(clock_runtime['executable'], candidate_dir,
                    **launch_options(clock_runtime, clock_disk, qemu_clock='virtual', qemu_retrace='precise',
                                     qemu_checkpoint_tool=tool, qemu_video_source_profile=PROFILE)) as cold:
                for name, artifact, state in checkpoints:
                    _restore(cold, artifact, state)
                    if name == 'early':
                        assert _logical(_reach_partial(cold, overlap)) == _logical(partial)
                    replay = _complete_three(cold, overlap, first, geometry, sequence)
                    assert replay == expected
                    evidence[f'cold_{name}'] = replay
                last_cold_owner = cold.vm.process
            assert last_cold_owner.poll() == 0
        assert (candidate_dir / 'PAIRVID.COM').read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
        evidence['all_owners_reaped'] = True
    finally:
        _write_json(tmp_path / 'paired-mode13-overlap-receipt.json', evidence)
