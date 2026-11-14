"""N21 lossless opaque checkpoint deltas with full renderer PNG artifacts."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import BASELINE_CONFIG, digest, prepare_dos_baseline
from test_qemu_dos_modes_checkpoint_native import _inputs, _launch
from test_qemu_dos_frames_native import _source, _image, _assert_mode13_pixels


def _artifact(project,identifier):
    row = project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',(identifier,)).fetchone()
    assert row is not None
    data = bytes(row['data'])
    assert hashlib.sha256(data).hexdigest() == row['sha256']
    return data


def _state_count(project):
    return project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0]


def _cold(control):
    runtime = _inputs()
    with Project(control['db']) as project:
        with _launch(project,runtime,control['dir'],{'image':control['disk']},clock_profile='virtual') as debug:
            fresh = debug.vm.process
            epoch = debug.dos_process_info()['capture_epoch']
            result = debug.timeline_rewind(timeline=control['timeline'],point=control['point'],timeout_ms=60000)
            assert fresh.poll() is not None and debug.dos_process_info()['capture_epoch'] != epoch
            assert result['point'] == control['point'] and result['completed_guest_frame'] is None
            pin = debug.timeline_pin('cold-delta.qcow2')
            assert _artifact(project,pin['artifact']) == Path(control['oracle']).read_bytes()
            image = debug.timeline_image('cold-delta.png',timeline=control['timeline'],point=control['point'])
            assert hashlib.sha256(_artifact(project,image['artifact'])).hexdigest() == control['png_sha']
            assert debug.registers()['registers'] == control['registers']
            assert debug.clock_observe()['virtual_ns'] == control['clock_ns']
            assert debug.timeline_advance(frames=1,timeout_ms=60000)['completed_frames'] == 1
    return {'passed':True}


def test_native_lossless_checkpoint_delta_branch_pin_and_cold_restore(tmp_path,monkeypatch):
    import fdisbull.qemu_dos_checkpoint as checkpoints
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); boot_sha = digest(boot)
    disk = prepare_dos_baseline(boot,tmp_path / 'baseline.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data, marker = _source(tmp_path,runtime['NASM'])
    source = tmp_path / 'DELTA.COM'; source.write_bytes(data)
    db = tmp_path / 'delta.fdb'
    captured = []
    original_capture = checkpoints.capture_process_state
    def capture(session,name,max_bytes):
        result = original_capture(session,name,max_bytes)
        assert hashlib.sha256(result['data']).hexdigest() == result['sha256']
        captured.append(bytes(result['data']))
        return result
    monkeypatch.setattr(checkpoints,'capture_process_state',capture)
    with Project.create(db,source,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            point = debug.breakpoint(base + marker['ready'])
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            full_rows_before = _state_count(project)
            root = debug.timeline_start(storage_mode='delta',keyframe_interval=2,period_ns=20_000_000,timeout_ms=60000)
            root_node = next(n for n in root['nodes'] if n['id'] == root['point'])
            assert root_node['checkpoint']['storage']['kind'] == 'full'
            assert _state_count(project) == full_rows_before + 1 and len(captured) == 1
            assert root['storage_mode'] == 'delta'
            points = [root['point']]; oracle = {root['point']:captured[-1]}
            pins, images, states = {}, {}, {}
            for index in range(3):
                before_capture, before_rows = len(captured), _state_count(project)
                next_frame = debug.timeline_advance(frames=1,timeout_ms=60000)
                assert next_frame['completed_frames'] == 1 and next_frame['completed_guest_frame'] is None
                assert len(captured) == before_capture + 1
                point_id = next_frame['point']; points.append(point_id); oracle[point_id] = captured[-1]
                cp = next(n['checkpoint'] for n in next_frame['nodes'] if n['id'] == point_id)
                assert _state_count(project) == before_rows + int(cp['storage']['kind'] == 'full')
                before_pin, before_pc = len(captured), debug.registers()['registers']
                pin = debug.timeline_pin('oracle-%d.qcow2' % index)
                assert len(captured) == before_pin and debug.registers()['registers'] == before_pc
                assert _artifact(project,pin['artifact']) == oracle[point_id]
                pins[point_id] = pin['sha256']
                image = debug.timeline_image('image-%d.png' % index,point=point_id)
                frame = next(n['frame'] for n in next_frame['nodes'] if n['id'] == point_id)
                _assert_mode13_pixels(project,debug,image,frame)
                images[point_id] = _artifact(project,image['artifact'])
                states[point_id] = dict(registers=debug.registers()['registers'],clock_ns=debug.clock_observe()['virtual_ns'])
            status = debug.timeline_status()
            nodes = {node['id']:node for node in status['nodes']}
            assert status['full_state_points'] >= 1 and status['delta_state_points'] >= 1
            assert status['reconstructed_state_payload_bytes'] == sum(len(oracle[n]) for n in points)
            actual_payload, actual_metadata, actual_images = 0, 0, 0
            for point_id in points:
                cp = nodes[point_id]['checkpoint']; storage = cp['storage']
                assert cp['sha256'] == hashlib.sha256(oracle[point_id]).hexdigest()
                assert cp['size'] == len(oracle[point_id]) and storage['kind'] in ('full','delta')
                assert 0 <= storage['depth'] < 2 and storage['payload_size'] > 0
                row = project.db.execute('SELECT kind,data,metadata FROM debug_artifacts WHERE id=?',
                                         (cp['artifact'],)).fetchone()
                assert row is not None
                payload = bytes(row['data'])
                metadata = json.dumps(json.loads(row['metadata']),sort_keys=True,separators=(',',':'),
                                      allow_nan=False).encode()
                assert row['kind'] == ('state' if storage['kind'] == 'full' else 'qemu-frame-state-delta')
                assert len(payload) == storage['payload_size']
                assert hashlib.sha256(payload).hexdigest() == storage['payload_sha256']
                assert len(metadata) == storage['metadata_size']
                assert hashlib.sha256(metadata).hexdigest() == storage['metadata_sha256']
                image = nodes[point_id]['frame']['image']
                image_payload = _artifact(project,image['artifact'])
                assert len(image_payload) == image['size']
                actual_payload += len(payload); actual_metadata += len(metadata); actual_images += len(image_payload)
            assert status['retained_encoded_state_payload_bytes'] == actual_payload
            assert status['retained_state_metadata_bytes'] == actual_metadata
            assert status['image_bytes_used'] == actual_images
            assert status['state_bytes_used'] == actual_payload + actual_metadata
            assert status['storage_bytes_used'] == actual_payload + actual_metadata + actual_images + status['input_bytes_used']
            assert actual_payload < status['reconstructed_state_payload_bytes']  # This observed fixture produced deltas.
            delta_point = next(p for p in points[1:] if nodes[p]['checkpoint']['storage']['kind'] == 'delta')
            # Rewind to first child, then create a distinct sibling and retain old future.
            debug.timeline_rewind(point=points[1],timeout_ms=60000)
            branch = debug.timeline_advance(frames=1,timeout_ms=60000)
            new_nodes = {node['id']:node for node in branch['nodes']}
            assert new_nodes[branch['point']]['parent'] == points[1]
            assert new_nodes[points[2]]['parent'] == points[1] and branch['point'] != points[2]
            assert _artifact(project,debug.timeline_image('retained.png',point=points[2])['artifact']) == images[points[2]]
            debug.timeline_rewind(point=delta_point,timeout_ms=60000)
            oracle_path = tmp_path / 'checkpoint-oracle.bin'; oracle_path.write_bytes(oracle[delta_point])
            control = dict(db=str(db),dir=str(tmp_path),disk=str(disk['image']),timeline=debug.timeline_status()['timeline'],
                point=delta_point,oracle=str(oracle_path),png_sha=hashlib.sha256(images[delta_point]).hexdigest(),
                **states[delta_point])
    with Project(db) as offline:
        out = tmp_path / 'offline.png'
        # Existing immutable PNG artifact remains independently exportable without a VM.
        row = offline.db.execute("SELECT id FROM debug_artifacts WHERE sha256=?",(control['png_sha'],)).fetchone()
        assert row is not None
        offline.debug_export(row['id'],out)
        assert out.read_bytes() == images[delta_point]
    control_path = tmp_path / 'delta-control.json'; control_path.write_text(json.dumps(control))
    child = subprocess.run([sys.executable,str(Path(__file__).resolve()),str(control_path)],
        capture_output=True,text=True,env=os.environ.copy(),timeout=240)
    assert child.returncode == 0, child.stderr[-6000:]
    assert json.loads(child.stdout)['passed'] is True
    assert source.read_bytes() == data and digest(boot) == boot_sha


if __name__ == '__main__':
    print(json.dumps(_cold(json.loads(Path(sys.argv[1]).read_text()))))


def test_native_corrupt_delta_base_refuses_before_replacing_live_owner(tmp_path):
    from test_qemu_memory_rules_native import _case
    with _case(tmp_path) as (project,debug,_,_,_,_):
        root = debug.timeline_start(storage_mode='delta',keyframe_interval=3,period_ns=20_000_000,timeout_ms=60000)
        child = debug.timeline_advance(frames=1,timeout_ms=60000)
        assert child['completed_frames'] == 1
        nodes = {node['id']:node for node in child['nodes']}
        assert nodes[child['point']]['checkpoint']['storage']['kind'] == 'delta'
        base_artifact = nodes[root['point']]['checkpoint']['artifact']
        old_process = debug.vm.process
        before_regs, before_clock = debug.registers()['registers'],debug.clock_observe()['virtual_ns']
        before_keys = debug.keyboard_state()
        with project.transaction(True):
            project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',(b'corrupt-authored-fixture',base_artifact))
        with pytest.raises(ValueError,match='corrupt|hash|missing|integrity'):
            debug.timeline_rewind(point=child['point'],timeout_ms=60000)
        assert debug.vm.process is old_process and old_process.poll() is None and not debug.closed
        assert debug.registers()['registers'] == before_regs and debug.clock_observe()['virtual_ns'] == before_clock
        assert debug.keyboard_state() == before_keys


def test_native_delta_held_keys_restore_without_reinject(tmp_path):
    from support.qemu_io_fixture import bios_keyboard_display
    from test_qemu_frame_keys_native import MAKE, _consume, _proof, _release
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE']); boot_sha = digest(boot)
    disk = prepare_dos_baseline(boot,tmp_path / 'baseline.img',runtime['FDISBULL_QEMU_DOS_MCOPY'],
        config=b'SWITCHES=/F\r\n'+BASELINE_CONFIG)
    data, offsets = bios_keyboard_display(tmp_path,runtime['NASM'])
    source = tmp_path / 'BIOS.COM'; source.write_bytes(data)
    with Project.create(tmp_path / 'held-delta.fdb',source,image='com') as project:
        with _launch(project,runtime,tmp_path,disk,clock_profile='virtual') as debug:
            base = debug.dos_process_info()['source_mapping']['runtime_base']
            symbols = {key:base + value - 0x100 for key,value in offsets.items() if key.endswith('_ip')}
            ready = debug.breakpoint(symbols['ready_ip'])
            assert debug.run(timeout_ms=30000)['outcome'] == 'breakpoint'
            debug.delete_breakpoint(ready['breakpoint_id'])
            debug.timeline_start(storage_mode='delta',keyframe_interval=3,period_ns=20_000_000,timeout_ms=60000)
            first = debug.timeline_advance(frames=1,inputs=[dict(frame=0,edges=MAKE)],timeout_ms=60000)
            assert first['completed_frames'] == 1
            point = first['point']
            node = next(n for n in first['nodes'] if n['id'] == point)
            assert node['checkpoint']['storage']['kind'] == 'delta'
            keys = debug.keyboard_state()['keyboard']['native']
            assert keys['active'] and not keys['repeat-supported'] and keys['accepted-edges'] == 2
            saved = _proof(keys)
            assert debug.timeline_advance(frames=1,timeout_ms=60000)['completed_frames'] == 1
            old = debug.vm.process
            debug.timeline_rewind(point=point,timeout_ms=60000)
            assert old.poll() is not None
            restored = debug.keyboard_state()['keyboard']['native']
            assert restored['epoch'] != keys['epoch'] and restored['token'] != keys['token']
            assert _proof(restored) == saved and restored['accepted-edges'] == 2
            # The saved node already advanced a frame and consumed one BIOS A.
            count = int.from_bytes(bytes.fromhex(debug.memory(symbols['key_count_ip'],length=2)['hex']),'little')
            assert count == 1
            assert debug.advance_frames(frames=3,timeout_ms=60000)['completed_frames'] == 3
            assert int.from_bytes(bytes.fromhex(debug.memory(symbols['key_count_ip'],length=2)['hex']),'little') == 1
            _release(debug,symbols,'bios')
    assert source.read_bytes() == data and digest(boot) == boot_sha


def test_native_delta_restores_task_private_irq_layers_and_hooks(tmp_path,monkeypatch):
    from fdisbull.qemu_dos_process import QemuDOSProcessSession
    from test_qemu_dos_frames_native import test_native_renderer_timeline_rewind_preserves_private_irq_state
    start, advance = QemuDOSProcessSession.timeline_start, QemuDOSProcessSession.timeline_advance
    seen = []
    def delta_start(self,*args,**kwargs):
        kwargs.update(storage_mode='delta',keyframe_interval=3)
        return start(self,*args,**kwargs)
    def capture_advance(self,*args,**kwargs):
        result = advance(self,*args,**kwargs)
        seen.extend(result.get('nodes',[]))
        return result
    monkeypatch.setattr(QemuDOSProcessSession,'timeline_start',delta_start)
    monkeypatch.setattr(QemuDOSProcessSession,'timeline_advance',capture_advance)
    test_native_renderer_timeline_rewind_preserves_private_irq_state(tmp_path)
    assert any(node['checkpoint']['storage']['kind'] == 'delta' for node in seen)
