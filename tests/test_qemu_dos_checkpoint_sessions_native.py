"""Mid-program DOS checkpoint across sessions with live layers and hooks.

All executable bytes below are authored for this test. Native QEMU, firmware,
qemu-img, mcopy and a caller-owned FreeDOS boot image are separate inputs.
This test deliberately requires a reopened project and a different run.
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import digest, mz_exit, prepare_dos_baseline


def _inputs():
    keys = ('FDISBULL_QEMU_LAYERS', 'FDISBULL_QEMU_DOS_BOOT_IMAGE',
            'FDISBULL_QEMU_DOS_MCOPY', 'FDISBULL_QEMU_DOS_FIRMWARE',
            'FDISBULL_QEMU_IMG')
    values = {key: os.environ.get(key) for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('Missing cross-session checkpoint inputs: ' + ', '.join(missing))
        pytest.skip('Supply cross-session checkpoint inputs: ' + ', '.join(missing))
    for key, value in values.items():
        path = Path(value).expanduser()
        assert path.is_dir() if key == 'FDISBULL_QEMU_DOS_FIRMWARE' else path.is_file(), key
    return values


def _fixture(case):
    if case == 'com':
        # MOV CX,2; MOV AX,1111; MOV [0120],AX; INC word [0120];
        # LOOP back to INC; MOV AX,4c2a; INT 21. Data at 0120 and 0124.
        source = bytes.fromhex('b90200b81111a32001ff062001e2fab82a4ccd21').ljust(0x26, b'\0')
        return source, dict(filename='CHECK.COM', image='com', fetch_offset=3,
                            before='b81111', after='b82222', hook_offset=9,
                            data_offset=0x20, ram_offset=0x24,
                            first=0x2222, second=0x2223, final=0x2224)
    source, fixture = mz_exit()
    source = bytearray(source)
    # Retain both genuine MZ relocation entries, including the immediate in
    # MOV AX,7. DS then addresses module offset 70h after DOS relocation.
    instructions = bytes.fromhex(
        '90b807008ed8b90200c7060000efbeff060000e2fab82a4ccd21')
    source[64 + 0x20:64 + 0x20 + len(instructions)] = instructions
    return bytes(source), dict(filename='CHECK.EXE', image=None,
                               fetch_offset=0x29, before='c7060000efbe',
                               after='c7060000feca', hook_offset=0x2f,
                               data_offset=0x70, ram_offset=0x74,
                               first=0xcafe, second=0xcaff, final=0xcb00,
                               relative_cs=fixture['relative_cs'])


def _word(debug, address):
    raw = debug.memory(address, length=2, space='physical')['hex']
    return int.from_bytes(bytes.fromhex(raw), 'little')


def _number(value):
    return int(value, 0) if isinstance(value, str) else value


def _open_debug(project, runtime, directory, disk):
    return project.debugger(
        runtime['FDISBULL_QEMU_LAYERS'], directory, backend='qemu-dos',
        dos_boot_image=str(disk['image']), dos_mcopy=runtime['FDISBULL_QEMU_DOS_MCOPY'],
        dos_startup_batch='FDAUTO.BAT', qemu_transport='pipe',
        qemu_firmware=runtime['FDISBULL_QEMU_DOS_FIRMWARE'],
        qemu_checkpoint_tool=runtime['FDISBULL_QEMU_IMG'], boot_timeout_ms=30000)


@pytest.mark.parametrize('case', ['com', 'mz'])
@pytest.mark.parametrize('binding', ['source', 'backing'])
def test_native_midprogram_cross_session_checkpoint_layers_and_hook(tmp_path, case, binding):
    runtime = _inputs()
    boot_source = Path(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'])
    boot_hash = digest(boot_source)
    disk = prepare_dos_baseline(boot_source, tmp_path / 'baseline.img',
                                runtime['FDISBULL_QEMU_DOS_MCOPY'])
    source_bytes, witness = _fixture(case)
    source = tmp_path / witness['filename']
    source.write_bytes(source_bytes)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    db = tmp_path / 'checkpoint.fdb'
    options = {'image': witness['image']} if witness['image'] else {}

    with Project.create(db, source, **options) as project:
        static = project.regions(1)[0].start
        if binding == 'source':
            fetch = project.debug_layer('checkpoint-fetch', kind='execute', patches=[{
                'address': hex(static + witness['fetch_offset']),
                'expected_hex': witness['before'], 'data_hex': witness['after'],
            }])['layer']
            ram = project.debug_layer('checkpoint-ram', kind='ram', patches=[{
                'address': hex(static + witness['ram_offset']),
                'expected_hex': '0000', 'data_hex': '3412',
            }])['layer']
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            process = debug.dos_process_info()
            runtime_base = _number(process['source_mapping']['runtime_base'])
            if case == 'mz':
                assert _number(process['entry']['cs']) == _number(process['source_mapping']['load_segment']) + witness['relative_cs']
            if binding == 'backing':
                fetch = debug.layer_patch('checkpoint-fetch-backing', runtime_base + witness['fetch_offset'],
                                          expected_hex=witness['before'], data_hex=witness['after'],
                                          kind='execute', space='physical', activate=False)['layer']
                ram = debug.layer_patch('checkpoint-ram-backing', runtime_base + witness['ram_offset'],
                                        expected_hex='0000', data_hex='3412',
                                        kind='ram', space='physical', activate=False)['layer']
            original_fetch, original_ram = fetch, ram
            debug.layers([fetch, ram])
            hook = debug.hook(hex(static + witness['hook_offset']), space='source',
                              once=False, max_hits=3,
                              actions=[{'op': 'layers', 'layers': [fetch, ram]}])
            first = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert first['outcome'] == 'hook' and first['hook_hits'][0]['hit'] == 1
            assert _word(debug, runtime_base + witness['data_offset']) == witness['first']
            assert _word(debug, runtime_base + witness['ram_offset']) == 0x1234
            assert debug.code(hex(static + witness['fetch_offset']), length=len(bytes.fromhex(witness['before'])),
                              space='source', view='ram')['hex'] == witness['before']
            assert debug.code(hex(static + witness['fetch_offset']), length=len(bytes.fromhex(witness['after'])),
                              space='source', view='execute')['hex'] == witness['after']
            saved_epoch = process['capture_epoch']
            saved_run = debug.run_id
            saved_pc = debug.registers()['linear_pc']
            saved = debug.save_state()
            artifact = saved['artifact']
            original_vm = debug.vm.process
        assert original_vm.poll() is not None

    # Reopen from the persisted project; this is deliberately not a second
    # load operation in the same live debugger session.
    with Project(db) as project:
        assert project.debug_state_info(artifact)['sha256'] == saved['sha256']
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            new_run = debug.run_id
            fresh_vm = debug.vm.process
            fresh_epoch = debug.dos_process_info()['capture_epoch']
            assert new_run != saved_run and fresh_vm is not original_vm
            restored = debug.load_state(artifact)
            fetch = restored['controls']['layers'][original_fetch]
            ram = restored['controls']['layers'][original_ram]
            if binding == 'backing':
                assert fetch != original_fetch and ram != original_ram
            else:
                assert (fetch, ram) == (original_fetch, original_ram)
            assert fresh_vm.poll() is not None
            assert debug.vm.process is not fresh_vm and debug.vm.process is not original_vm
            info = debug.dos_process_info()
            assert restored['source_binding_restored'] is True and info['state'] == 'active'
            assert info['capture_epoch'] not in (saved_epoch, fresh_epoch)
            assert debug.registers()['linear_pc'] == saved_pc
            runtime_base = _number(info['source_mapping']['runtime_base'])
            assert _word(debug, runtime_base + witness['data_offset']) == witness['first']
            assert _word(debug, runtime_base + witness['ram_offset']) == 0x1234
            assert debug.layers()['active'] == [fetch, ram]
            assert debug.code(hex(static + witness['fetch_offset']), length=len(bytes.fromhex(witness['before'])),
                              space='source', view='ram')['hex'] == witness['before']
            assert debug.code(hex(static + witness['fetch_offset']), length=len(bytes.fromhex(witness['after'])),
                              space='source', view='execute')['hex'] == witness['after']
            controls = debug.hooks()['hooks']
            assert len(controls) == 1 and controls[0]['hook'] == hook['hook'] and controls[0]['hits'] == 1
            assert controls[0]['actions'] == [{'op': 'layers', 'layers': [fetch, ram]}]
            second = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert second['outcome'] == 'hook' and second['hook_hits'][0]['hit'] == 2
            assert second['hook_hits'][0]['hook'] == hook['hook']
            assert _word(debug, runtime_base + witness['data_offset']) == witness['second']
            # Reloading the unchanged original artifact must rewind CPU, RAM,
            # control counts and the pending hook step-over consistently.
            previous_vm = debug.vm.process
            previous_epoch = info['capture_epoch']
            repeated = debug.load_state(artifact)
            first_fetch, first_ram = fetch, ram
            fetch = repeated['controls']['layers'][original_fetch]
            ram = repeated['controls']['layers'][original_ram]
            if binding == 'backing':
                assert fetch not in (original_fetch, first_fetch) and ram not in (original_ram, first_ram)
            else:
                assert (fetch, ram) == (original_fetch, original_ram)
            assert previous_vm.poll() is not None and debug.vm.process is not previous_vm
            info = debug.dos_process_info()
            assert repeated['source_binding_restored'] is True
            assert info['capture_epoch'] != previous_epoch
            runtime_base = _number(info['source_mapping']['runtime_base'])
            assert _word(debug, runtime_base + witness['data_offset']) == witness['first']
            assert debug.layers()['active'] == [fetch, ram]
            controls = debug.hooks()['hooks']
            assert len(controls) == 1 and controls[0]['hook'] == hook['hook'] and controls[0]['hits'] == 1
            assert controls[0]['actions'] == [{'op': 'layers', 'layers': [fetch, ram]}]
            second = debug.run(timeout_ms=15000, stop_on_hook=True)
            assert second['outcome'] == 'hook' and second['hook_hits'][0]['hit'] == 2
            assert _word(debug, runtime_base + witness['data_offset']) == witness['second']
            debug.delete_hook(hook['hook'])
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert _word(debug, runtime_base + witness['data_offset']) == witness['final']
            debug.layers([])
            assert _word(debug, runtime_base + witness['ram_offset']) == 0
            done = debug.run(timeout_ms=5000)
            assert done['outcome'] == 'guest_exit' and done['process']['termination']['code'] == 42
    assert source.read_bytes() == source_bytes and hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert digest(boot_source) == boot_hash and digest(disk['image']) == disk['prepared_sha256']


def test_native_checkpoint_preserves_guest_modified_ram_layer_and_user_breakpoint(tmp_path):
    runtime = _inputs()
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'],
                                tmp_path / 'modified-baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    # INC word [0120h]; NOP; JMP $. The initial source word is zero.
    code = bytes.fromhex('ff06200190ebfe').ljust(0x22, b'\0')
    source = tmp_path / 'MODIFY.COM'
    source.write_bytes(code)
    db = tmp_path / 'modified.fdb'
    with Project.create(db, source, image='com') as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            layer = debug.layer_patch('guest-modified-data', base + 0x20,
                                      expected_hex='0000', data_hex='0500',
                                      kind='ram', space='physical')['layer']
            assert _word(debug, base + 0x20) == 5
            assert debug.step(timeout_ms=5000)['outcome'] == 'step'
            assert _word(debug, base + 0x20) == 6
            # A distinct ordinary breakpoint is also a host-owned control and
            # must be rebound; it is not the hook or the DOS return trap.
            point = debug.breakpoint(base + 5)
            saved = debug.save_state()
            old_vm = debug.vm.process
        assert old_vm.poll() is not None
    with Project(db) as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            fresh_vm = debug.vm.process
            restored = debug.load_state(saved['artifact'])
            assert fresh_vm.poll() is not None and debug.vm.process is not fresh_vm
            rebound = restored['controls']['layers'][layer]
            assert rebound != layer and debug.layers()['active'] == [rebound]
            new_point = restored['controls']['breakpoints'][point['breakpoint_id']]
            assert new_point in debug.breakpoints
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            assert debug.breakpoints[new_point]['address'] == base + 5
            assert _word(debug, base + 0x20) == 6
            with pytest.raises(ValueError, match='(?i)conflict|changed'):
                debug.layers([])
            assert _word(debug, base + 0x20) == 6 and debug.layers()['active'] == [rebound]
            debug.layers([], conflict='keep_changed')
            assert _word(debug, base + 0x20) == 6 and debug.layers()['active'] == []
            debug.delete_breakpoint(new_point)
    assert source.read_bytes() == code and digest(disk['image']) == disk['prepared_sha256']


@pytest.mark.parametrize('mode', ['queued', 'held'])
def test_native_checkpoint_refuses_pending_or_held_physical_input(tmp_path, mode):
    runtime = _inputs()
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'],
                                tmp_path / 'input-baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    source = tmp_path / 'WAIT.COM'
    source.write_bytes(bytes.fromhex('ebfe'))
    with Project.create(tmp_path / 'input.fdb', source, image='com') as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            before = debug.vm.process
            lease = debug.keyboard_key_down('a')['lease']
            if mode == 'held':
                result = debug.run(timeout_ms=100)
                assert result['outcome'] == 'timeout'
                state = debug.input_state()
                assert state['pending_edges'] == 0 and lease in state['leases']
                assert state['leases'][lease]['make'] != 'python_pending'
            else:
                assert debug.input_state()['pending_edges'] == 1
            with pytest.raises(ValueError, match='(?i)input|lease|held|pending'):
                debug.save_state()
            assert debug.vm.process is before and before.poll() is None
            assert debug.status()['state'] == 'stopped'
            assert lease in debug.input_state()['leases']
            if mode == 'queued':
                debug.input_cancel_pending()
                assert not debug.input_state()['leases']
            else:
                debug.keyboard_key_up(lease)
                assert debug.run(timeout_ms=100)['outcome'] == 'timeout'
                assert not debug.input_state()['leases']


@pytest.mark.parametrize('tamper', ['sha256', 'source_sha256', 'version_sha256'])
def test_native_checkpoint_preflight_rejects_corrupt_or_mismatched_identity_without_destroying_owner(tmp_path, tamper):
    runtime = _inputs()
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'],
                                tmp_path / 'preflight-baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    source_bytes, witness = _fixture('com')
    source = tmp_path / witness['filename']
    source.write_bytes(source_bytes)
    with Project.create(tmp_path / 'preflight.fdb', source, image='com') as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            saved = debug.save_state()
            artifact = saved['artifact']
            assert saved['metadata']['format'] == 'fdisbull-qemu-dos-process-qcow2-v2'
            row = project.db.execute('SELECT sha256, metadata FROM debug_artifacts WHERE id=?', (artifact,)).fetchone()
            old_sha, old_metadata = row['sha256'], row['metadata']
            changed = json.loads(old_metadata)
            if tamper != 'sha256':
                changed[tamper] = '0' * 64
            with project.transaction(True):
                project.db.execute('UPDATE debug_artifacts SET sha256=?, metadata=? WHERE id=?',
                                   ('0' * 64 if tamper == 'sha256' else old_sha,
                                    json.dumps(changed), artifact))
            current_vm = debug.vm.process
            old_pc = debug.registers()['linear_pc']
            try:
                with pytest.raises(ValueError, match='(?i)hash|identity|source|version|mismatch'):
                    debug.load_state(artifact)
                assert debug.vm.process is current_vm and current_vm.poll() is None
                assert debug.status()['state'] == 'stopped' and debug.registers()['linear_pc'] == old_pc
            finally:
                with project.transaction(True):
                    project.db.execute('UPDATE debug_artifacts SET sha256=?, metadata=? WHERE id=?',
                                       (old_sha, old_metadata, artifact))
            # Refusal is non-destructive: the same real guest still executes
            # both loop iterations and reaches its original output boundary.
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + 15)
            result = debug.run(timeout_ms=15000)
            assert result['outcome'] == 'breakpoint', result
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            debug.delete_breakpoint(point['breakpoint_id'])
            assert _word(debug, base + witness['data_offset']) == 0x1113
            done = debug.run(timeout_ms=5000)
            assert done['outcome'] == 'guest_exit' and done['process']['termination']['code'] == 42
    assert source.read_bytes() == source_bytes


def test_native_checkpoint_refuses_changed_helper_report_code(tmp_path):
    from fdisbull.dos_process_helper import _LOADER_TEMPLATE

    runtime = _inputs()
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'],
                                tmp_path / 'helper-baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    source_bytes, witness = _fixture('com')
    source = tmp_path / witness['filename']
    source.write_bytes(source_bytes)
    prefix = bytes.fromhex('505152561e0e1ffc')
    assert _LOADER_TEMPLATE.count(prefix) == 1
    offset = _LOADER_TEMPLATE.index(prefix)
    with Project.create(tmp_path / 'helper-check.fdb', source, image='com') as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            address = debug._ready['helper_segment'] * 16 + 0x100 + offset
            debug.write_memory(address, '90', expected_hex='50')
            owner = debug.vm.process
            with pytest.raises(ValueError, match='helper.*code'):
                debug.save_state()
            assert debug.vm.process is owner and owner.poll() is None
            debug.write_memory(address, '50', expected_hex='90')
            done = debug.run(timeout_ms=5000)
            assert done['outcome'] == 'guest_exit' and done['process']['termination']['code'] == 42


def test_native_cross_session_checkpoint_preserves_open_guest_file(tmp_path):
    from struct import unpack_from
    from support.dos_process_fixture import assemble

    runtime = _inputs()
    nasm = os.environ.get('NASM')
    if not nasm:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_LAYERS') == '1':
            pytest.fail('NASM required for the guest file checkpoint witness')
        pytest.skip('Supply NASM for the guest file checkpoint witness')
    disk = prepare_dos_baseline(runtime['FDISBULL_QEMU_DOS_BOOT_IMAGE'],
                                tmp_path / 'file-baseline.img', runtime['FDISBULL_QEMU_DOS_MCOPY'])
    program = assemble(tmp_path, 'open-file-checkpoint', r'''
bits 16
org 0x100
    jmp near start
    dw save_marker, verify_marker, output
start:
    mov dx,filename
    xor cx,cx
    mov ah,0x3c
    int 0x21
    jc failed
    mov bx,ax
    mov dx,first_byte
    mov cx,1
    mov ah,0x40
    int 0x21
    jc failed
    cmp ax,1
    jne failed
save_marker:
    nop
    mov dx,second_byte
    mov cx,1
    mov ah,0x40
    int 0x21
    jc failed
    cmp ax,1
    jne failed
    mov ax,0x4200
    xor cx,cx
    xor dx,dx
    int 0x21
    jc failed
    mov dx,output
    mov cx,2
    mov ah,0x3f
    int 0x21
    jc failed
    cmp ax,2
    jne failed
verify_marker:
    nop
    mov ah,0x3e
    int 0x21
    jc failed
    mov ax,0x4c2a
    int 0x21
failed:
    mov ax,0x4c01
    int 0x21
filename: db 'FDCHECK.DAT',0
first_byte: db 'A'
second_byte: db 'B'
output: dw 0
''', nasm)
    save_ip, verify_ip, output_ip = unpack_from('<HHH', program, 3)
    source = tmp_path / 'FILE.COM'
    source.write_bytes(program)
    database = tmp_path / 'open-file.fdb'
    with Project.create(database, source, image='com') as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            psp = debug.dos_process_info()['psp_segment']
            point = debug.breakpoint(psp * 16 + save_ip)
            assert debug.run(timeout_ms=15000)['outcome'] == 'breakpoint'
            artifact = debug.save_state()['artifact']
    with Project(database) as project:
        with _open_debug(project, runtime, tmp_path, disk) as debug:
            restored = debug.load_state(artifact)
            debug.delete_breakpoint(restored['controls']['breakpoints'][point['breakpoint_id']])
            psp = debug.dos_process_info()['psp_segment']
            finish = debug.breakpoint(psp * 16 + verify_ip)
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'breakpoint', result
            assert debug.memory(psp * 16 + output_ip, length=2)['hex'] == '4142'
            debug.delete_breakpoint(finish['breakpoint_id'])
            result = debug.run(timeout_ms=5000)
            assert result['outcome'] == 'guest_exit' and result['process']['termination']['code'] == 42
    assert source.read_bytes() == program
    assert digest(disk['image']) == disk['prepared_sha256']
