"""Actual native owner replacement cannot rewind a host fair-play latch."""
import hashlib
import json
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import com_exit
from test_qemu_dos_process_native import launch_options, process_runtime, process_disk
from test_qemu_dos_le_checkpoint_native import _checkpoint_tool


@pytest.mark.parametrize('kind', ['owned-machine', 'source-process'])
def test_native_older_checkpoint_preserves_newer_fair_play_policy(tmp_path, process_runtime, process_disk, kind):
    runtime, tool = process_runtime, _checkpoint_tool()
    source = tmp_path / 'POLICY.COM'
    source.write_bytes(com_exit(0))
    originals = {str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest()
                 for path in (source, runtime['boot_image'], runtime['executable'], tool)}
    database = tmp_path / 'policy.fdb'
    with Project.create(database, source, image='com') as project:
        with project.debugger(runtime['executable'], tmp_path,
                **launch_options(runtime, process_disk, qemu_checkpoint_tool=str(tool), spatial_mode='story')) as debug:
            assert debug.capabilities['spatial_policy'] is True
            original = debug.registers()
            state = debug.spatial_policy()
            assert state == dict(spatial_mode='story', fair_play=False, assisted_travel=False, voluntary=True)
            assert debug.registers() == original
            saved = debug.save_machine_state() if kind == 'owned-machine' else debug.save_state()
            locked = debug.spatial_policy('physical', fair_play=True)
            owner, epoch = debug.vm, debug._runtime_epoch
            if kind == 'owned-machine': debug.load_machine_state(saved['artifact'])
            else: debug.load_state(saved['artifact'])
            assert debug.vm is not owner and owner.process.poll() is not None
            assert debug._runtime_epoch != epoch
            assert debug.spatial_policy() == locked
            with pytest.raises(ValueError, match='Fair play'):
                debug.spatial_policy('assisted', fair_play=False)
            assert debug.spatial_policy() == locked
            assert not hasattr(debug, 'assisted_travel') and not hasattr(debug, 'frame_probe')
            evidence = [dict(row) for row in project.db.execute(
                "SELECT operation,evidence FROM debug_events WHERE run=? AND operation='spatial-policy' ORDER BY sequence",
                (debug.run_id,))]
            run, native = debug.run_id, debug.vm.process
        assert native.poll() is not None
    with Project(database) as reopened:
        assert [dict(row) for row in reopened.db.execute(
            "SELECT operation,evidence FROM debug_events WHERE run=? AND operation='spatial-policy' ORDER BY sequence",
            (run,))] == evidence
        assert all(json.loads(row['evidence'])['fair_play'] for row in evidence[1:])
    assert {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in originals} == originals
