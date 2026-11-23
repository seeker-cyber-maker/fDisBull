"""Actual DOS VBE status-port reads paired with format-9 timed scanout."""

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from support.paired_vbe_status import (
    EDGE_LIMIT,
    PIT_HZ,
    RECORD_BYTES,
    read_edges,
    source_with_status_probe,
    status_lattice,
    symbols,
)
from test_qemu_clock_budget_native import clock_runtime, clock_disk, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vga_640_checkpoint_native import DOSBOX_RGB, expected_pixels, logical, source, verify_export
from test_qemu_vga_phase_checkpoint_native import _reach

PROFILE = 'vga-640x480-sync'
MODEL = 'qemu-vga-640x480-sync-v1'
FORMAT = 'fdisbull-instrumented-qemu-state-9'
LAYOUT = 'vbe-banked-101'
LINE = 27_208
PERIOD = 525 * LINE
HBLANK_START = 80 * LINE // 100
HBLANK_END = 98 * LINE // 100
HEIGHT = 480
DOSBOX_STATUS_REFERENCE = 'fdc97b510fce3b1a76013cc37bdc0abfd047089e0d1f95a4c9f75303d5dd4b38'

pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VBE_RETRACE') != '1',
    reason='Select the exact paired VBE status-port witness and QEMU sync producer',
)


def expected_status(timestamp):
    phase = timestamp % PERIOD
    line, offset = divmod(phase, LINE)
    vertical = 490 * LINE <= phase <= 492 * LINE
    blank = line >= HEIGHT or HBLANK_START <= offset <= HBLANK_END
    return (8 if vertical else 0) | (1 if blank else 0)


def retrace(debug):
    receipt = debug.retrace_observe()
    native = receipt['native']
    assert native['phase-supported'] and native['raw']['vbe-enable'] & 1, native
    model = native['vbe101-timing']
    expected = dict(
        **{
            'line-period-ns': LINE,
            'chars-per-line': 100,
            'lines-per-frame': 525,
            'hblank-start-ns': HBLANK_START,
            'hblank-end-ns': HBLANK_END,
            'vblank-start-line': HEIGHT,
            'vsync-start-line': 490,
            'vsync-end-line': 492,
        }
    )
    assert {key: model[key] for key in expected} == expected
    phase = native['phase']
    assert (phase['period-ns'], phase['phase-ns']) == (PERIOD, native['virtual-ns'] % PERIOD)
    assert phase['line'] == phase['phase-ns'] // LINE
    assert phase['status1-timing-bits'] == expected_status(native['virtual-ns'])
    return {
        key: deepcopy(native[key])
        for key in ('virtual-ns', 'raw', 'timing', 'timing-generation', 'phase', 'vbe101-timing')
    }


def register(receipt, name):
    values = receipt['registers']
    return int(values.get('r' + name, values.get('e' + name)), 0)


def guest_status(debug, site, successor, *, target=None, expected=None):
    if target is not None:
        _reach(debug, target)
    park(debug, site)
    old_cpu = debug.registers()
    assert register(old_cpu, 'dx') & 0xFFFF == 0x03DA
    assert debug.memory(site, length=1, space='virtual')['hex'] == 'ec'
    before = retrace(debug)
    executed = debug.step(count=1, timeout_ms=5000)
    assert executed['outcome'] == 'step' and not executed['timed_out'], executed
    cpu = debug.registers()
    assert int(cpu['linear_pc'], 0) == successor == site + 1
    value = register(cpu, 'ax') & 0xFF
    after = retrace(debug)
    assert 0 < after['virtual-ns'] - before['virtual-ns'] < LINE // 8
    first, last = (part['phase']['status1-timing-bits'] for part in (before, after))
    assert (value & 9) in (first, last), dict(value=value, before=before, after=after)
    if target is not None:
        assert target <= before['virtual-ns'] < target + LINE // 3
    if expected is not None:
        assert first == last == (value & 9) == expected, dict(value=value, before=before, after=after)
    return dict(
        guest_value=value,
        instruction_pc=old_cpu['linear_pc'],
        successor=cpu['linear_pc'],
        requested_virtual_ns=target,
        native_before=before,
        native_after=after,
    )


def guest_hblank(debug, sites, frame_start, samples):
    first_line, last_line = 11, 18
    _reach(debug, frame_start + first_line * LINE + HBLANK_START)
    for _ in range(64):
        sample = guest_status(debug, *sites)
        samples.append(sample)
        before, after = (sample[key]['phase'] for key in ('native_before', 'native_after'))
        if before['line'] > last_line:
            break
        if (
            first_line <= before['line'] == after['line'] <= last_line
            and before['status1-timing-bits'] == after['status1-timing-bits'] == 1
        ):
            # The virtual-time bracket selects the read. The observed guest
            # byte already had to match the independently tested phase.
            return
    pytest.fail(f'No guest IN within horizontal blank on rows {first_line}..{last_line}')


def checked_frame(debug, first_deadline):
    result = debug.video_frame_advance(timeout_ms=8000)
    assert result['advance_completed'], result
    state = source(debug)
    assert state['model'] == MODEL and state['state'] == 'observing'
    frame = state['frame']
    assert frame['scanout-layout'] == state['scanout-layout'] == LAYOUT
    assert (frame['width'], frame['height'], frame['stride'], frame['pixel-format']) == (
        640,
        480,
        1920,
        'RGB888',
    )
    assert (frame['line-period-ns'], frame['period-ns']) == (LINE, PERIOD)
    start = frame['frame-start-ns']
    assert start % PERIOD == 0 and first_deadline == start + LINE // 4
    assert len(frame['rows']) == HEIGHT
    for number, row in enumerate(frame['rows']):
        intended = first_deadline + number * LINE
        assert row['row'] == number and row['intended-ns'] == intended
        # The original callback can slip less than one whole physical line.
        assert intended <= row['actual-ns'] < intended + LINE
        assert row['actual-ns'] < start + HEIGHT * LINE
    assert frame['first-sample-ns'] == frame['rows'][0]['actual-ns']
    assert frame['completed-ns'] == frame['last-sample-ns'] == frame['rows'][-1]['actual-ns']
    assert frame['pixel-sha256'] == DOSBOX_RGB[LAYOUT]
    verify_export(debug, state, expected_pixels('banked'))
    return logical(state)


def restore(debug, checkpoint, saved, saved_phase):
    prior = debug.vm.process
    selected = debug.load_state(checkpoint, timeout_ms=60_000)
    assert selected['instrumentation']['format'] == FORMAT
    new = debug.vm.process
    assert new is not prior and prior.poll() == 0
    observed = source(debug)
    assert observed['token'] != saved['token'] and observed['epoch'] != saved['epoch']
    assert logical(observed) == logical(saved)
    assert retrace(debug) == saved_phase
    verify_export(debug, observed, expected_pixels('banked'))
    return new


def journal(debug, labels):
    count = int.from_bytes(memory(debug, labels['edge_count'], 2), 'little')
    assert 0 < count <= EDGE_LIMIT
    raw = memory(debug, labels['edge_journal'], count * RECORD_BYTES)
    return raw, read_edges(raw)


def memory(debug, address, length):
    return bytes.fromhex(debug.memory(address, length=length, space='virtual')['hex'])


def follow(debug, labels, prefix, first_deadline):
    assert journal(debug, labels)[0] == prefix
    frame = checked_frame(debug, first_deadline)
    this_start = frame['frame']['frame-start-ns']
    inside = guest_status(
        debug,
        labels['status_in'],
        labels['status_out'],
        target=this_start + 490 * LINE + LINE // 2,
        expected=9,
    )
    outside = guest_status(
        debug,
        labels['status_in'],
        labels['status_out'],
        target=this_start + 493 * LINE + LINE // 2,
        expected=1,
    )
    park(debug, labels['timing_done'])
    assert memory(debug, labels['timing_result'], 1) == b'\x01'
    raw, records = journal(debug, labels)
    assert raw.startswith(prefix) and len(raw) > len(prefix)
    cadence = status_lattice(records, line=Fraction(LINE * PIT_HZ, 10**9))
    final = retrace(debug)
    # The last transition that the actual guest journal records is the fourth
    # vertical fall. It then exits polling in the same vblank.
    assert (records[-1]['old'], records[-1]['new']) == (9, 1)
    assert final['phase']['status1-timing-bits'] == 1
    assert 492 * LINE < final['phase']['phase-ns'] < PERIOD
    latest = source(debug)
    assert latest['frame']['frame-id'] > frame['frame']['frame-id']
    assert latest['frame']['pixel-sha256'] == DOSBOX_RGB[LAYOUT]
    return dict(
        timed_frame=frame,
        journal_hex=raw.hex(),
        journal_sha256=sha256(raw).hexdigest(),
        cadence=cadence,
        guest_status=[inside, outside],
        final_phase=final,
        final_raster=logical(latest),
    )


def launch(project, executable, directory, runtime, disk, tool):
    return project.debugger(
        executable,
        directory,
        **launch_options(
            runtime,
            disk,
            qemu_clock='virtual',
            qemu_retrace='precise',
            qemu_video_source_profile=PROFILE,
            qemu_checkpoint_tool=str(tool),
        ),
    )


def cold_replay(spec_path):
    directory = spec_path.parent
    spec = json.loads(spec_path.read_text())
    executable = Path(spec['runtime']['executable'])
    tool = Path(spec['tool'])
    assert digest(executable) == spec['qemu_sha256'] and digest(tool) == spec['qemu_img_sha256']
    with Project(directory / 'vbe-status.fdb') as project:
        with launch(project, executable, directory, spec['runtime'], spec['disk'], tool) as debug:
            initial = debug.vm.process
            resumed = restore(debug, spec['checkpoint'], spec['saved_source'], spec['saved_phase'])
            result = follow(debug, spec['labels'], bytes.fromhex(spec['prefix_hex']), spec['first_deadline'])
    assert initial is not resumed and initial.poll() == resumed.poll() == 0
    return dict(
        host_pid=os.getpid(),
        result=result,
        owners=dict(
            cold_entry=dict(pid=initial.pid, returncode=initial.poll()),
            cold_restored=dict(pid=resumed.pid, returncode=resumed.poll()),
        ),
    )


def test_native_paired_vbe_status_and_raster_restore(tmp_path, clock_runtime, clock_disk):
    from test_qemu_dosbox_vga_modes_native import _SOURCE, _DAC

    executable = clock_runtime['executable']
    tool = Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True)
    actual_hash = digest(executable)
    helper_hash = digest(tool)
    assert actual_hash == os.environ['FDISBULL_QEMU_VBE_RETRACE_SHA256']
    assert helper_hash == os.environ['FDISBULL_QEMU_VBE_RETRACE_IMG_SHA256']
    code = assemble(
        tmp_path,
        'vbe-retrace',
        source_with_status_probe(_SOURCE)
        + '\ncolors: db '
        + ','.join(str(value) for color in _DAC for value in color),
        clock_runtime['nasm'],
    )
    authored_hash = sha256(code).hexdigest()
    assert authored_hash == os.environ['FDISBULL_PAIRED_VBE_RETRACE_COM_SHA256']
    page_labels, symbols_static = symbols(code)
    first, planar, banked, _, mode_command = page_labels
    binary = tmp_path / 'VBE.COM'
    binary.write_bytes(code)
    database = tmp_path / 'vbe-status.fdb'
    receipt = dict(
        com_sha256=authored_hash,
        qemu_sha256=actual_hash,
        qemu_img_sha256=helper_hash,
        profile=PROFILE,
        dosbox_status_reference_sha256=DOSBOX_STATUS_REFERENCE,
        completed=False,
    )
    owners, cold_owners = {}, {}

    def write():
        (tmp_path / 'vbe-guest-retrace.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')

    try:
        with Project.create(database, binary, image='com') as project:
            with launch(project, executable, tmp_path, clock_runtime, clock_disk, tool) as debug:
                owners['start'] = debug.vm.process
                process = process_record(debug)
                first, planar, banked, mode_command = (
                    com_address(process, at) for at in (first, planar, banked, mode_command)
                )
                labels = {name: com_address(process, at) for name, at in symbols_static.items()}
                park(debug, first)
                debug.write_memory(mode_command, '01', expected_hex='00')
                park(debug, planar)
                debug.write_memory(mode_command, '02', expected_hex='01')
                park(debug, banked)
                census = debug.vga_configuration_observe()['current']['raw']
                assert census['vbe'][1:6] == [640, 480, 8, 1, 4]
                assert census['vbe-start-address'] == 0 and census['vbe-line-offset'] == 640
                receipt['held_phase'] = retrace(debug)
                armed = debug.video_frame_start()['native']
                assert armed['model'] == MODEL and armed['scanout-layout'] == LAYOUT
                first_deadline = armed['next-deadline-ns']
                intact = receipt['intact'] = checked_frame(debug, first_deadline)
                start = intact['frame']['frame-start-ns']
                write()

                debug.write_memory(labels['timing_go'], '01', expected_hex='00')
                incoming = (labels['status_in'], labels['status_out'])
                samples = receipt['pre_checkpoint_guest_status'] = [guest_status(debug, *incoming)]
                for point, want in (
                    (start + 480 * LINE + LINE // 2, 1),
                    (start + 490 * LINE + LINE // 2, 9),
                    (start + 493 * LINE + LINE // 2, 1),
                    (start + PERIOD + 10 * LINE + LINE // 2, 0),
                ):
                    samples.append(guest_status(debug, *incoming, target=point, expected=want))
                    write()
                receipt['hblank_sweep'] = []
                guest_hblank(debug, incoming, start + PERIOD, receipt['hblank_sweep'])
                write()
                first_deadline += PERIOD
                _reach(debug, first_deadline + 180 * LINE + LINE // 2)
                partial = source(debug)
                saved_phase = retrace(debug)
                assert partial['rows-sampled'] == 181 and saved_phase['phase']['line'] == 180
                assert partial['next-deadline-ns'] == first_deadline + 181 * LINE
                assert logical(partial)['frame'] == intact['frame']
                prefix, prefix_records = journal(debug, labels)
                assert any(item['old'] == 9 and item['new'] == 1 for item in prefix_records)
                assert memory(debug, labels['timing_result'], 1) == b'\0'
                receipt['checkpoint_frontier'] = dict(
                    source=logical(partial),
                    phase=saved_phase,
                    journal_sha256=sha256(prefix).hexdigest(),
                    journal_count=len(prefix_records),
                )
                saved = debug.save_state('vbe-guest-status-and-partial')
                receipt['checkpoint'] = saved['sha256']
                write()
                receipt['forward'] = follow(debug, labels, prefix, first_deadline)
                write()
                owners['hot'] = restore(debug, saved['artifact'], partial, saved_phase)
                receipt['hot'] = follow(debug, labels, prefix, first_deadline)
                assert receipt['hot'] == receipt['forward']
            assert all(proc.poll() == 0 for proc in owners.values())
        spec = tmp_path / 'cold-spec.json'
        spec.write_text(
            json.dumps(
                dict(
                    labels=labels,
                    first_deadline=first_deadline,
                    checkpoint=saved['artifact'],
                    saved_source=partial,
                    saved_phase=saved_phase,
                    prefix_hex=prefix.hex(),
                    qemu_sha256=actual_hash,
                    qemu_img_sha256=helper_hash,
                    tool=str(tool),
                    disk={'image': str(clock_disk['image'])},
                    runtime={k: str(v) if isinstance(v, Path) else v for k, v in clock_runtime.items()},
                )
            )
        )
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), str(spec)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        (tmp_path / 'cold.log').write_text(completed.stdout + completed.stderr)
        assert completed.returncode == 0, completed.stderr
        cold = json.loads(completed.stdout)
        assert cold['host_pid'] != os.getpid()
        receipt['cold_host_pid'] = cold['host_pid']
        cold_owners = cold['owners']
        assert not {proc.pid for proc in owners.values()} & {item['pid'] for item in cold_owners.values()}
        receipt['cold'] = cold['result']
        assert receipt['cold'] == receipt['forward']
        receipt['completed'] = True
    finally:
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        receipt['owners'] = {
            **{stage: dict(pid=proc.pid, returncode=proc.poll()) for stage, proc in owners.items()},
            **cold_owners,
        }
        write()


if __name__ == '__main__':
    print(json.dumps(cold_replay(Path(sys.argv[1]))))
