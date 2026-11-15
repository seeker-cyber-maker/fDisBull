"""Exercise established deep native contracts on the composite FreeDOS disk."""
from contextlib import contextmanager
import importlib
import os

import pytest


@pytest.mark.parametrize('module,case', [
    ('test_qemu_experiments_native',
     'test_native_experiment_restores_private_irq_and_held_keys'),
    ('test_qemu_cpu_deltas_native',
     'test_native_cpu_projection_preserves_held_keys_private_irq_and_recovers'),
    ('test_qemu_frame_deltas_native',
     'test_native_delta_restores_task_private_irq_layers_and_hooks'),
])
def test_workspace_preserves_native_contracts(tmp_path, monkeypatch, module, case):
    component = os.environ.get('FDISBULL_FREEDOS_RUNTIME')
    if not component:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail('Native workspace preservation requires FDISBULL_FREEDOS_RUNTIME')
        pytest.skip('Supply FDISBULL_FREEDOS_RUNTIME')
    launches = []

    @contextmanager
    def launch(project, runtime, directory, disk, *, clock_profile='standard', **extra):
        # Existing scenarios keep their build/FDB beside the authored source.
        # Admit only that source and a sentinel into this private workspace.
        game = directory / 'workspace-input'
        game.mkdir(exist_ok=True)
        source = directory / project.meta['filename']
        target = game / source.name
        if not target.exists():
            target.write_bytes(source.read_bytes())
            (game / 'SENTINEL.DAT').write_bytes(b'unchanged host original')
        before = {p.name: p.read_bytes() for p in game.iterdir()}
        with project.debugger(runtime.get('FDISBULL_QEMU_DOS', runtime.get('FDISBULL_QEMU_LAYERS')), game, backend='qemu-dos',
                freedos_runtime=component, dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
                qemu_transport='pipe', qemu_firmware=runtime.get('FDISBULL_QEMU_DOS_FIRMWARE', runtime.get('FDISBULL_QEMU_LAYERS_FIRMWARE')),
                qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'],
                qemu_clock=clock_profile, boot_timeout_ms=60000, **extra) as debug:
            assert debug.workspace_read('SENTINEL.DAT')['data'] == before['SENTINEL.DAT']
            launches.append(debug.run_id)
            yield debug
        assert {p.name: p.read_bytes() for p in game.iterdir()} == before

    # These scenarios intentionally reuse the same deeply qualified contracts.
    # Replace only their launch adapter, leaving all state assertions intact.
    for name in ('test_qemu_experiments_native', 'test_qemu_cpu_deltas_native',
                 'test_qemu_dos_frames_native', 'test_qemu_dos_modes_checkpoint_native'):
        monkeypatch.setattr(importlib.import_module(name), '_launch', launch)
    function = getattr(importlib.import_module(module), case)
    if module == 'test_qemu_frame_deltas_native':
        function(tmp_path, monkeypatch)
    else:
        function(tmp_path)
    assert launches
