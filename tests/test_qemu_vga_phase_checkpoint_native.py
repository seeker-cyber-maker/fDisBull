"""Public hot/cold checkpoint of a native initial and steady Mode 13h raster."""

from copy import deepcopy
import os
from pathlib import Path
import struct

import pytest

from fdisbull.project import Project
from fdisbull.qemu_instrumented_checkpoint import VIDEO_PHASE_FORMAT
from fdisbull.qemu_video_checkpoint import MODEL
from support.dos_process_fixture import assemble, digest
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_vga_mode_setup_native import BODY, VGA_BIOS


pytestmark = pytest.mark.skipif(
    os.environ.get('FDISBULL_REQUIRE_QEMU_VGA_PHASE') != '1',
    reason='Select the pinned native Mode 13h phase checkpoint witness',
)
# Exact authored standard Mode 13h geometry, as measured by the existing
# independent physical-line oracle for this VGA ROM and precise PC profile.
LINE_NS = 31_700
PERIOD_NS = 449 * LINE_NS


def _observe(debug):
    return debug.video_frame_observe()['native']


def _logical(info):
    logical = deepcopy(info)
    logical.pop('token')
    logical.pop('epoch')
    if 'frame' in logical:
        logical['frame'].pop('epoch')
    return logical


def _reach(debug, target):
    now = debug.clock_observe()['virtual_ns']
    assert target > now
    budget = debug.clock_advance(target - now, timeout_ms=10000)['clock_budget']
    assert budget['deadline_reached'] and budget['deadline_ns'] == target


def _future(debug, first):
    observed = []
    for phase, start in enumerate((first, first + PERIOD_NS)):
        _reach(debug, start + 400 * LINE_NS)
        result = _observe(debug)
        frame = result['frame']
        assert frame['frame-start-ns'] == start
        assert (frame['source-phase'], frame['line-period-ns'], frame['period-ns']) == (
            phase, LINE_NS, PERIOD_NS)
        assert [row['intended-ns'] for row in frame['rows']] == [
            start + LINE_NS // 4 + (2 * row + phase) * LINE_NS for row in range(200)]
        observed.append(_logical(result))
    return observed


def _restore(debug, artifact, saved):
    previous = debug.vm.process
    result = debug.load_state(artifact, timeout_ms=60000)
    assert result['instrumentation']['format'] == VIDEO_PHASE_FORMAT
    assert previous.poll() == 0 and debug.vm.process is not previous
    current = _observe(debug)
    assert current['token'] != saved['token'] and current['epoch'] != saved['epoch']
    assert _logical(current) == _logical(saved)


def test_mode13_phase_checkpoint_replays_initial_and_steady_rows(
        tmp_path, clock_runtime, clock_disk, record_property):
    qemu_sha = os.environ['FDISBULL_QEMU_VGA_PHASE_SHA256']
    assert digest(clock_runtime['executable']) == qemu_sha
    assert digest(Path(clock_runtime['firmware']) / 'vgabios-stdvga.bin') == VGA_BIOS
    tool = Path(os.environ['FDISBULL_QEMU_IMG'])
    assert digest(tool) == os.environ['FDISBULL_QEMU_VGA_PHASE_IMG_SHA256']
    record_property('native_producer_sha256', qemu_sha)

    # BIOS function 00h with the preserve-display bit keeps the full mode
    # transaction and reaches our stop before the first raster boundary.
    code = assemble(tmp_path, 'vga-phase-replay', BODY.replace('mov ax,13h', 'mov ax,93h'),
                    clock_runtime['nasm'])
    assert code[-14:-10] == b'VGA1'
    ready, first_guest_stop, *_ = struct.unpack('<5H', code[-10:])
    source = tmp_path / 'CHANGEM.COM'
    source.write_bytes(code)
    database = tmp_path / 'phase.fdb'

    def launch(project, *, phased=True):
        return project.debugger(clock_runtime['executable'], tmp_path,
            **launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                qemu_retrace='precise', qemu_video_source_profile='dosbox-mode13' if phased else None,
                qemu_checkpoint_tool=str(tool)))

    with Project.create(database, source, image='com') as project:
        with launch(project) as debug:
            info = process_record(debug)
            park(debug, com_address(info, ready))
            park(debug, com_address(info, first_guest_stop))
            initial = debug.video_frame_start()['native']
            committed = initial['mode-setup']['committed-ns']
            first = (committed // PERIOD_NS + 1) * PERIOD_NS
            assert initial['virtual-ns'] < first and initial['rows-sampled'] == 0
            assert initial['next-deadline-ns'] == first + LINE_NS // 4
            before = debug.save_state('phase-before-first.qcow2')
            _reach(debug, first + 130 * LINE_NS)
            partial = _observe(debug)
            assert partial['rows-sampled'] == 65
            assert partial['next-deadline-ns'] == first + 130 * LINE_NS + LINE_NS // 4
            saved = debug.save_state('phase-partial.qcow2')
            expected = _future(debug, first)
            _restore(debug, before['artifact'], initial)
            assert _future(debug, first) == expected
            owner = debug.vm.process
        assert owner.poll() == 0

    with Project(database) as project:
        with launch(project, phased=False) as default:
            owner = default.vm.process
            before = default.registers()
            assert _observe(default)['model'] == MODEL
            with pytest.raises(ValueError, match='Process checkpoint sidecar or runtime identity differs'):
                default.load_state(saved['artifact'], timeout_ms=60000)
            assert default.vm.process is owner and owner.poll() is None
            assert default.registers() == before
        assert owner.poll() == 0
        with launch(project) as debug:
            _restore(debug, saved['artifact'], partial)
            assert _future(debug, first) == expected
            owner = debug.vm.process
        assert owner.poll() == 0
    assert source.read_bytes() == code
    assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
