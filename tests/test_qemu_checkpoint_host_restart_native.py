"""A saved DOS checkpoint crosses an actual Python process boundary.

The child reopens the same FDB and emits only a compact result object. Guest
inputs are authored except for the separately supplied private FreeDOS image.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

from fdisbull.project import Project
from support.dos_process_fixture import digest, prepare_dos_baseline
from test_qemu_dos_checkpoint_sessions_native import _fixture, _inputs, _number, _open_debug, _word


def _child(control_path):
    control = json.loads(Path(control_path).read_text())
    runtime = _inputs()
    disk = {'image': Path(control['disk']), 'prepared_sha256': control['disk_sha256']}
    witness = control['witness']
    static = control['static']
    with Project(control['database']) as project:
        assert project.debug_state_info(control['artifact'])['sha256'] == control['artifact_sha256']
        with _open_debug(project, runtime, Path(control['directory']), disk) as debug:
            fresh_process = debug.vm.process
            fresh_epoch = debug.dos_process_info()['capture_epoch']
            assert debug.run_id != control['origin_run']
            loaded = debug.load_state(control['artifact'])
            assert fresh_process.poll() is not None and debug.vm.process is not fresh_process
            process = debug.dos_process_info()
            assert loaded['source_binding_restored'] is True
            assert process['capture_epoch'] not in (control['origin_epoch'], fresh_epoch)
            base = _number(process['source_mapping']['runtime_base'])
            assert debug.registers()['linear_pc'] == control['saved_pc']
            assert _word(debug, base + witness['data_offset']) == witness['first']
            assert _word(debug, base + witness['ram_offset']) == 0x1234
            layers = loaded['controls']['layers']
            fetch, ram = layers[control['fetch']], layers[control['ram']]
            assert debug.layers()['active'] == [fetch, ram]
            assert debug.code(hex(static + witness['fetch_offset']), length=3,
                              space='source', view='ram')['hex'] == witness['before']
            assert debug.code(hex(static + witness['fetch_offset']), length=3,
                              space='source', view='execute')['hex'] == witness['after']
            hooks = debug.hooks()['hooks']
            assert len(hooks) == 1 and hooks[0]['hook'] == control['hook'] and hooks[0]['hits'] == 1
            result = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert result['outcome'] == 'hook' and result['hook_hits'][0]['hit'] == 2
            assert result['hook_hits'][0]['hook'] == control['hook']
            assert _word(debug, base + witness['data_offset']) == witness['second']
            debug.delete_hook(control['hook'])
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            output = _word(debug, base + witness['data_offset'])
            assert output == witness['final']
            debug.layers([])
            assert _word(debug, base + witness['ram_offset']) == 0
            done = debug.run(timeout_ms=5000)
            assert done['outcome'] == 'guest_exit' and done['process']['termination']['code'] == 42
    assert digest(disk['image']) == disk['prepared_sha256']
    print(json.dumps({'passed': True, 'pid': os.getpid(), 'output': output,
                      'hook_hit': 2, 'exit_code': 42, 'capture_epoch': process['capture_epoch']}))


def test_native_checkpoint_restores_after_python_host_restart(tmp_path):
    runtime = _inputs()
    boot = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot)
    disk = prepare_dos_baseline(boot, tmp_path / 'baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    code, witness = _fixture('com')
    source = tmp_path / witness['filename']
    source.write_bytes(code)
    db = tmp_path / 'host-restart.fdb'
    with Project.create(db, source, image='com') as project:
        static = project.regions(1)[0].start
        fetch = project.debug_layer('host-restart-fetch', kind='execute', patches=[{
            'address': hex(static + witness['fetch_offset']),
            'expected_hex': witness['before'], 'data_hex': witness['after'],
        }])['layer']
        ram = project.debug_layer('host-restart-ram', kind='ram', patches=[{
            'address': hex(static + witness['ram_offset']),
            'expected_hex': '0000', 'data_hex': '3412',
        }])['layer']
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            info = debug.dos_process_info()
            debug.layers([fetch, ram])
            hook = debug.hook(hex(static + witness['hook_offset']), space='source',
                              once=False, max_hits=3,
                              actions=[{'op': 'layers', 'layers': [fetch, ram]}])
            hit = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert hit['outcome'] == 'hook' and hit['hook_hits'][0]['hit'] == 1
            base = _number(info['source_mapping']['runtime_base'])
            assert _word(debug, base + witness['data_offset']) == witness['first']
            saved_pc = debug.registers()['linear_pc']
            saved = debug.save_state()
            control = dict(database=str(db), directory=str(tmp_path), disk=str(disk['image']),
                           disk_sha256=disk['prepared_sha256'], artifact=saved['artifact'],
                           artifact_sha256=saved['sha256'], witness=witness, static=static,
                           fetch=fetch, ram=ram, hook=hook['hook'], origin_run=debug.run_id,
                           origin_epoch=info['capture_epoch'], saved_pc=saved_pc)
            original_vm = debug.vm.process
        assert original_vm.poll() is not None
    control_path = tmp_path / 'child-control.json'
    control_path.write_text(json.dumps(control))
    environment = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / 'src')
    environment['PYTHONPATH'] = src + os.pathsep + environment.get('PYTHONPATH', '')
    completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(control_path)],
                               cwd=str(Path(__file__).resolve().parents[1]), env=environment,
                               capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stderr[-3000:]
    result = json.loads(completed.stdout)
    assert result['passed'] is True and result['pid'] != os.getpid()
    assert result['output'] == witness['final'] and result['hook_hit'] == 2 and result['exit_code'] == 42
    assert source.read_bytes() == code and digest(boot) == boot_hash


if __name__ == '__main__':
    _child(sys.argv[1])
