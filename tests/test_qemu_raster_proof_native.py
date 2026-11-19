"""Actual typed raster evidence, deliberately without frame/cadence claims.

The exact candidate ELF is selected by FDISBULL_QEMU_CLOCK. An explicit test
launcher hook adds the opt-in native property; no public frame API is added.
Existing fixed-period renderer publications drive attempts and remain sampling.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import time

from PIL import Image
import pytest

from fdisbull import qemu_machine
from fdisbull.dosbox_rpc import DebuggerError
from support.dos_process_fixture import digest
from support.qemu_raster_proof_fixture import COMMANDS, oracle, raster_program
from test_qemu_clock_budget_native import budget_receipt, clock_disk, clock_runtime, park
from test_qemu_display_native import pixels
from test_qemu_dos_le_checkpoint_native import _checkpoint_tool
from test_qemu_dos_process_native import com_address, create_project, launch_options, process_record


COMMAND = 'x-fdisbull-query-raster-proof'
PERIOD_NS = 50_000_000


@pytest.fixture
def raster_witness(tmp_path, clock_runtime, clock_disk, monkeypatch, record_property):
    original = qemu_machine.machine_retrace_arguments
    selected = {'enabled': True}

    def arguments(profile):
        args = original(profile)
        return args + (['-global', 'VGA.x-fdisbull-raster-proof=on']
                       if selected['enabled'] else [])

    monkeypatch.setattr(qemu_machine, 'machine_retrace_arguments', arguments)
    serial = 0

    @contextmanager
    def launch(*, enabled=True, checkpoints=False):
        nonlocal serial
        serial += 1
        selected['enabled'] = enabled
        directory = tmp_path / str(serial)
        directory.mkdir()
        code, offsets = raster_program(directory, clock_runtime['nasm'])
        binary, project = create_project(directory, code)
        record_property('authored_com_sha256', hashlib.sha256(code).hexdigest())
        record_property('producer_semantics', 'existing fixed-period synchronous renderer; no video-frame cadence claim')
        debug = None
        owners = []
        extra = {'qemu_checkpoint_tool': str(_checkpoint_tool())} if checkpoints else {}
        try:
            with project:
                try:
                    with project.debugger(clock_runtime['executable'], directory,
                            **launch_options(clock_runtime, clock_disk,
                                             qemu_clock='virtual', qemu_retrace='precise', **extra)) as debug:
                        owners.append(debug.vm.process)
                        assert COMMAND in debug.vm.qmp_commands
                        assert ('VGA.x-fdisbull-raster-proof=on' in debug.vm.command) is enabled
                        info = process_record(debug)
                        symbols = {key: com_address(info, value) for key, value in offsets.items()}
                        park(debug, symbols['ready'])
                        yield project, debug, symbols, owners
                finally:
                    if debug is not None:
                        owners.append(debug.vm.process)
                        assert all(owner.poll() is not None for owner in owners)
                        record_property('owners_reaped', len({id(owner) for owner in owners}))
        finally:
            assert binary.read_bytes() == code
            assert digest(clock_disk['image']) == clock_disk['prepared_sha256']

    return launch


def passive(project, debug):
    before, regs = debug.clock_observe(), debug.registers()
    files = {str(p) for p in Path(debug.vm.temporary.name).rglob('*') if p.is_file()}
    artifacts = project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    first = debug.vm.qmp.call(COMMAND)
    assert debug.vm.qmp.call(COMMAND) == first
    after = debug.clock_observe()
    assert all(before[k] == after[k] for k in ('run', 'epoch', 'virtual_ns', 'counter'))
    assert debug.registers() == regs
    assert artifacts == project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    assert files == {str(p) for p in Path(debug.vm.temporary.name).rglob('*') if p.is_file()}
    assert first['api-version'] == 1 and first['model'] == 'qemu-vga-raster-proof-v1'
    assert first['device-type'] == 'VGA' and first['console'] == first['head'] == 0
    assert first['virtual-ns'] == before['virtual_ns']
    assert not {'frame-id', 'mode-id', 'state-revision', 'update-id'} & first.keys()
    assert not debug.capabilities['completed_guest_frames']
    return first


def publish(debug, *, first=False):
    delta = PERIOD_NS * 3 // 2 if first else PERIOD_NS
    budget_receipt(debug.clock_advance(delta, timeout_ms=5000), delta)
    return debug.display_observe()


def command(debug, symbols, name):
    number, fence = COMMANDS[name]
    debug.write_memory(symbols['command'], bytes([number]).hex(), expected_hex='00')
    return park(debug, symbols[fence])


def unavailable(proof, *, attempted=None):
    assert proof['outcome'] == 'unavailable' and proof['reason']
    assert not {'source', 'producing-configuration'} & proof.keys()
    assert proof['current-configuration-matches'] is False
    if attempted is not None:
        assert proof['attempted'] is attempted


def verify(project, debug, proof, *, palette=False, vram=False):
    assert proof['outcome'] in ('updated', 'valid-unchanged')
    assert proof['attempted'] and 'reason' not in proof
    source = proof['source']
    assert source['profile'] == 'qemu-vga-chain4-320x200-raster-v1'
    assert (source['width'], source['height'], source['source-bpp']) == (320, 200, 8)
    assert (source['surface-width'], source['surface-height']) == (640, 400)
    assert source['column-duplication'] == source['row-duplication'] == 2
    assert source['start-address'] == 0 and source['line-offset'] == 320
    assert source['draw-handler'] == 'vga_draw_line8d2' and not source['dac-8bit']
    assert source['rows-considered'] == 400 and 0 <= source['rows-redrawn'] <= 400
    assert (source['rows-redrawn'] == 0) is (proof['outcome'] == 'valid-unchanged')
    configuration = proof['producing-configuration']
    assert configuration['epoch'] == proof['epoch']
    assert configuration['virtual-ns'] == proof['attempt-ns'] <= proof['virtual-ns']
    assert proof['current-configuration-matches'] is True
    expected_indices, expected_palette, expected_rgb = oracle(
        changed_palette=palette, changed_vram=vram)
    assert source['source-index-sha256'] == hashlib.sha256(expected_indices).hexdigest()
    assert source['palette-rgb-sha256'] == hashlib.sha256(expected_palette).hexdigest()
    assert source['source-rgb-sha256'] == hashlib.sha256(expected_rgb).hexdigest()
    retained = debug.capture_display()
    with pixels(project, retained) as image:
        assert image.size == (640, 400)
        actual = image.convert('RGB').tobytes()
        assert hashlib.sha256(actual).hexdigest() == source['surface-rgb-sha256']
        source_image = image.resize((320, 200), resample=Image.Resampling.NEAREST)
        assert source_image.tobytes() == expected_rgb
        assert source_image.resize((640, 400), resample=Image.Resampling.NEAREST).tobytes() == actual
    assert passive(project, debug) == proof
    return source


def test_native_owned_source_palette_unchanged_and_last_row(raster_witness):
    with raster_witness() as (project, debug, symbols, _):
        unavailable(passive(project, debug))
        debug.display_start(period_ns=PERIOD_NS)
        publish(debug, first=True)
        first = passive(project, debug)
        assert first['outcome'] == 'updated'
        first_source = verify(project, debug, first)
        # A full-update path does not consume DIRTY_MEMORY_VGA. One following
        # attempt may redraw the same setup bytes while clearing that bitmap;
        # verify it, then demand cache reuse on the next declared attempt.
        publish(debug)
        drained = passive(project, debug)
        assert verify(project, debug, drained)['source-rgb-sha256'] == first_source['source-rgb-sha256']
        publish(debug)
        repeated = passive(project, debug)
        assert repeated['outcome'] == 'valid-unchanged'
        assert verify(project, debug, repeated)['source-rgb-sha256'] == first_source['source-rgb-sha256']
        command(debug, symbols, 'palette')
        stale = passive(project, debug)
        assert stale['current-configuration-matches'] is True
        assert stale['source'] == repeated['source']  # palette is not configuration identity
        publish(debug)
        changed = passive(project, debug)
        assert changed['outcome'] == 'updated'
        changed_source = verify(project, debug, changed, palette=True)
        assert changed_source['source-index-sha256'] == first_source['source-index-sha256']
        assert changed_source['source-rgb-sha256'] != first_source['source-rgb-sha256']
        publish(debug)
        unchanged = passive(project, debug)
        assert unchanged['outcome'] == 'valid-unchanged'
        verify(project, debug, unchanged, palette=True)
        command(debug, symbols, 'vram')
        publish(debug)
        last_row = passive(project, debug)
        assert last_row['outcome'] == 'updated'
        verify(project, debug, last_row, palette=True, vram=True)


def test_native_invalid_mode_blank_panning_and_aba(raster_witness):
    with raster_witness() as (project, debug, symbols, _):
        debug.display_start(period_ns=PERIOD_NS)
        old_display = publish(debug, first=True)
        first = passive(project, debug)
        verify(project, debug, first)
        command(debug, symbols, 'invalid_text')
        assert passive(project, debug)['current-configuration-matches'] is False
        invalid_display = publish(debug)
        unavailable(passive(project, debug), attempted=True)
        assert invalid_display['update_id'] > old_display['update_id']
        with pixels(project, debug.capture_display()) as image:
            assert hashlib.sha256(image.tobytes()).hexdigest() == first['source']['surface-rgb-sha256']
        command(debug, symbols, 'restore')
        publish(debug)
        verify(project, debug, passive(project, debug))
        command(debug, symbols, 'blank')
        publish(debug)
        unavailable(passive(project, debug), attempted=True)
        command(debug, symbols, 'enable')
        publish(debug)
        verify(project, debug, passive(project, debug))
        command(debug, symbols, 'panning')
        publish(debug)
        unavailable(passive(project, debug), attempted=True)
        command(debug, symbols, 'unpan')
        publish(debug)
        before = passive(project, debug)
        verify(project, debug, before)
        command(debug, symbols, 'page_aba')
        after = passive(project, debug)
        assert after['source'] == before['source']
        assert after['producing-configuration'] == before['producing-configuration']
        assert after['current-configuration-matches'] is False
        current = debug.vga_configuration_observe()['current']
        assert current['raw'] == before['producing-configuration']['raw']
        assert current['configuration_generation'] > before['producing-configuration']['configuration-generation']
        publish(debug)
        fresh = passive(project, debug)
        assert fresh['outcome'] == 'updated'
        verify(project, debug, fresh)


def test_native_hot_load_clears_proof_but_keeps_retained_display_history(raster_witness):
    with raster_witness(checkpoints=True) as (project, debug, _, owners):
        debug.display_start(period_ns=PERIOD_NS)
        publish(debug, first=True)
        first = passive(project, debug)
        verify(project, debug, first)
        saved = debug.save_machine_state()
        old_owner = debug.vm
        restored = debug.load_machine_state(saved['artifact'])
        owners.append(debug.vm.process)
        assert debug.vm is not old_owner and old_owner.process.poll() is not None
        assert restored['machine_state_restored']
        empty = passive(project, debug)
        unavailable(empty, attempted=False)
        assert empty['reason'] == 'native-load' and empty['epoch'] != first['epoch']
        with pixels(project, debug.capture_display()) as image:
            assert hashlib.sha256(image.tobytes()).hexdigest() == first['source']['surface-rgb-sha256']
        unavailable(passive(project, debug), attempted=False)
        publish(debug)
        fresh = passive(project, debug)
        assert fresh['outcome'] == 'updated'
        verify(project, debug, fresh)


def test_native_profile_opt_in_and_reset_refuse_old_proof(raster_witness):
    with raster_witness(enabled=False) as (_, debug, _, _):
        with pytest.raises(DebuggerError, match='raster-proof'):
            debug.vm.qmp.call(COMMAND)
        debug.display_start(period_ns=PERIOD_NS)
        assert publish(debug, first=True)['update_id'] > 0
    with raster_witness() as (project, debug, _, _):
        debug.display_start(period_ns=PERIOD_NS)
        publish(debug, first=True)
        before = passive(project, debug)
        verify(project, debug, before)
        # The production launch exits on reboot. Explicitly select surviving
        # reset for this negative hook probe, then observe its asynchronous
        # epoch transition using passive queries only; never execute the guest.
        debug.vm.qmp.call('set-action', {'reboot': 'reset'})
        debug.vm.qmp.call('system_reset')
        deadline = time.monotonic() + 2
        while True:
            reset = debug.vm.qmp.call('x-fdisbull-query-clock', timeout_ms=1000)
            if reset['epoch'] != before['epoch']:
                break
            assert time.monotonic() < deadline, reset
        assert reset['budget-state'] == 'invalidated' and not reset['budget-supported']
        assert not reset['running'] and reset['virtual-ns'] == before['virtual-ns']
        with pytest.raises(DebuggerError, match='epoch|invalidated|reset'):
            debug.vm.qmp.call(COMMAND)
