"""Restored native observer owners retain their ordinary migration blockers."""
from pathlib import Path

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project
from fdisbull.qemu_checkpoint import snapshot_job
from support.dos_process_fixture import BASELINE_CONFIG, prepare_dos_baseline
from test_qemu_dos_checkpoint_sessions_native import _inputs


@pytest.mark.parametrize('owner', ['audio', 'display'])
def test_restored_observer_blocks_ordinary_snapshot_without_other_owners(tmp_path, owner):
    runtime = _inputs()
    disk = prepare_dos_baseline(
        Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']), tmp_path / 'baseline.img',
        runtime['FDISBULL_QEMU_DOS_MCOPY'], config=b'SWITCHES=/F\r\n' + BASELINE_CONFIG)
    # A source-authored self-loop; the session starts stopped at its entry.
    source = tmp_path / 'GUARD.COM'
    source.write_bytes(bytes.fromhex('ebfe'))
    with Project.create(tmp_path / 'guard.fdb', source, image='com') as project:
        with project.debugger(
            runtime['FDISBULL_QEMU_LAYERS'], tmp_path, backend='qemu-dos',
            dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
            dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
            qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
            qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], boot_timeout_ms=30000,
            qemu_clock='virtual', qemu_audio='pc-speaker' if owner == 'audio' else 'off',
            qemu_retrace='standard') as debug:
            native = debug.clock_observe()['virtual_clock']['native']
            assert native['budget-state'] == 'idle' and not native.get('budget-token')
            started = (debug.audio_start(max_frames=32000) if owner == 'audio'
                       else debug.display_start(period_ns=20_000_000))
            assert started['state'] == ('capturing' if owner == 'audio' else 'observing')
            saved = debug.save_state()
            restored = debug.load_state(saved['artifact'])
            rebound = restored['instrumentation']['windows'][owner]
            assert rebound['old'] == started['window'] and rebound['new'] != rebound['old']
            observed = debug.audio_observe() if owner == 'audio' else debug.display_observe()
            assert observed['window'] == rebound['new'] and observed['state'] == started['state']
            native = debug.clock_observe()['virtual_clock']['native']
            assert native['budget-state'] == 'idle' and not native.get('budget-token')
            assert debug.save_state('restored-checkpoint.fdbstate')['artifact'] != saved['artifact']
            expected = ('fDisBull audio capture windows do not support generic migration'
                        if owner == 'audio' else 'fDisBull retained display does not support migration')
            with pytest.raises(DebuggerError, match=expected):
                snapshot_job(debug.vm, 'save', tag='ordinary-refused', vmstate='disk0', devices=['disk0'])
            assert debug.vm.process.poll() is not None and debug.vm.qmp is None
