"""Same non-wrapping Bx/Cx guest on DOSBox-X and QEMU; documented count gate.

Uses the paired-tone native prerequisites. Frozen QEMU is expected to fail
the stereo count assertions; preserve its reports as baseline evidence.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import time

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.qemu_sb16_count_fixture import DMA_UNITS, expected_progress, parse_report, sb16_count
from test_qemu_paired_tone_native import paired_tone_runtime
from test_qemu_clock_budget_native import park
from test_qemu_dos_process_native import assert_completion, com_address


def _qemu(directory, source, code, offsets, runtime, result):
    owner = None
    try:
        with Project.create(directory / 'count.fdb', source, image='com') as project:
            with project.debugger(runtime['qemu'], directory, backend='qemu-dos',
                dos_boot_image=str(runtime['disk']['image']), dos_mcopy=str(runtime['mcopy']),
                qemu_firmware=str(runtime['firmware']), qemu_transport='pipe',
                qemu_checkpoint_tool=str(runtime['qemu_img']), qemu_clock='virtual',
                qemu_audio='sb16', boot_timeout_ms=30000) as debug:
                owner = debug.vm.process
                result['owner_pid'] = owner.pid
                process = debug.dos_process_info()
                symbols = {key: com_address(process, value) for key, value in offsets.items() if key != 'report_size'}
                def read(address, length):
                    return bytes.fromhex(debug.memory(address, length=length, space='physical')['hex'])
                original_vector = read(0x3c, 4)
                result['ready_stop'] = park(debug, symbols['ready'])
                result['ready'] = parse_report(read(symbols['report'], offsets['report_size']))
                result['audio_start'] = debug.audio_start(max_frames=100000)
                result['started_stop'] = park(debug, symbols['started'])
                result['started_device'] = debug.vm.qmp.call('x-fdisbull-query-sb16')
                if result['ready']['bits'] == 16:
                    before_cpu, before_clock = debug.registers(), debug.clock_observe()
                    with pytest.raises(ValueError, match='SB16 checkpoint supports U8 mono/stereo') as refused:
                        debug.save_state('s16-deliberately-unsupported.state')
                    result['s16_checkpoint_refusal'] = str(refused.value)
                    assert debug.vm.process is owner and owner.poll() is None
                    assert debug.registers() == before_cpu
                    assert debug.clock_observe()['virtual_ns'] == before_clock['virtual_ns']
                    assert debug.vm.qmp.call('x-fdisbull-query-sb16') == result['started_device']
                result['done_stop'] = park(debug, symbols['done'])
                result['done'] = parse_report(read(symbols['report'], offsets['report_size']))
                result['done_device'] = debug.vm.qmp.call('x-fdisbull-query-sb16')
                assert read(0x3c, 4) == original_vector
                result['irq_vector_restored'] = True
                result['exit'] = debug.run(timeout_ms=5000)
                assert_completion(debug, result['exit'], exit_code=42)
                result['audio_stop'] = debug.audio_stop()
                artifact = debug.capture_audio('count.wav')
                project.debug_export(artifact['artifact'], directory / 'audio.wav')
                result['audio'] = debug.audio_observe()
                assert result['audio']['dropped_frames'] == 0
    finally:
        if owner is not None:
            result.update(reaped=owner.poll() is not None, native_returncode=owner.returncode)
    assert result['reaped'] and result['native_returncode'] == 0
    assert source.read_bytes() == code


def _dosbox(directory, source, code, offsets, runtime, result):
    rpc = None
    deadline = time.monotonic() + 45
    try:
        rpc = DOSBoxRPC(runtime['dosbox'], directory)
        result['owner_pid'] = rpc.process.pid
        result['start'] = rpc.call('session.start', dict(target=dict(command=source.name, arguments=[]),
            mounts=[dict(drive='C', host_path=str(directory))], break_at='entry'))
        sid = result['start']['session_id']
        def call(method, parameters=None):
            assert time.monotonic() < deadline, 'Finite DOSBox count phase expired'
            return rpc.call(method, dict(session_id=sid, **(parameters or {})))
        regs = call('state.get_registers')
        cs = int(regs['segments']['cs'], 16)
        assert regs['cpu_mode'] == 'real' and int(regs['instruction_pointer'], 16) == 0x100
        def read(address, length):
            value = call('memory.read', dict(address=dict(space='linear', offset=f'0x{address:08x}'), length=length))
            return base64.b64decode(value['data_base64'], validate=True)
        assert read(cs * 16 + 0x100, len(code)) == code
        original_vector = read(0x3c, 4)
        call('execution.timing', dict(fast_forward=True))
        def continue_once():
            op = call('execution.continue')
            while True:
                state = call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=250))
                if not state.get('running', False):
                    return state
        def run_to(name):
            point = call('breakpoints.create', dict(kind='execution', once=True,
                address=dict(space='segmented', segment=f'0x{cs:04x}', offset=f'0x{offsets[name]:08x}')))
            state = continue_once()
            assert state['state'] == 'stopped' and state['stop_reason']['kind'] == 'breakpoint', state
            assert state['stop_reason']['breakpoint_id'] == point['breakpoint_id']
            return state
        for name in ('ready', 'started', 'done'):
            result[name + '_stop'] = run_to(name)
            result[name] = parse_report(read(cs * 16 + offsets['report'], offsets['report_size']))
        assert read(0x3c, 4) == original_vector
        result['irq_vector_restored'] = True
        result['exit'] = continue_once()
        ended = result['exit']['stop_reason']['guest_exit']
        assert result['exit']['state'] == 'exited' and ended['requested_exit_code'] == 42
        assert ended['resident'] is False and ended['stage'] == 'after-process-cleanup'
    finally:
        if rpc is not None:
            log = Path(rpc.temporary.name) / 'emulator.log'
            if log.exists():
                shutil.copy2(log, directory / 'emulator.log')
            rpc.close()
            result.update(native_returncode=rpc.process.returncode, reaped=rpc.process.poll() is not None)
    assert result['reaped'] and result['native_returncode'] == 0
    assert source.read_bytes() == code


def _completed(result, *, bits, channels, fifo):
    before, after = result['ready'], result['done']
    assert (before['bits'], before['channels'], before['fifo'], before['phase']) == (bits, channels, int(fifo), 1)
    assert before['reset_byte'] == 0xaa and before['major'] == 4 and before['failure'] == 0
    assert before['initial_address'] == (before['buffer_physical'] >> (bits == 16)) & 0xffff
    assert before['buffer_physical'] % 8192 == 0
    assert before['initial_count'] == DMA_UNITS - 1
    assert after['phase'] == 3 and after['failure'] == 0
    # Register82h defines IRQ sources in bits0..2; upper bits are reserved.
    assert after['irq_count'] == 1 and after['irq_status'] & 7 == (1 if bits == 8 else 2)
    assert after['old_mask'] == after['restored_mask']
    assert after['final_address'] == after['irq_address']
    assert after['final_count'] == after['irq_dma_count']
    assert result['irq_vector_restored'] and result['reaped']
    expected = expected_progress(before)
    result['documented_expected'] = expected
    result['observed_progress'] = dict(units=after['final_address'] - before['initial_address'],
        bytes=(after['final_address'] - before['initial_address']) * (bits // 8),
        remaining_units=after['final_count'] + 1)
    assert result['observed_progress']['units'] + result['observed_progress']['remaining_units'] == DMA_UNITS


@pytest.mark.parametrize('bits', [8, 16], ids=['u8', 's16'])
@pytest.mark.parametrize('channels', [1, 2], ids=['mono', 'stereo'])
@pytest.mark.parametrize('fifo', [False, True], ids=['fifo-off', 'fifo-on'])
def test_native_documented_sb16_count_without_dma_wrap(tmp_path, paired_tone_runtime, bits, channels, fifo):
    runtime = paired_tone_runtime
    code, offsets = sb16_count(tmp_path, runtime['nasm'], bits=bits, channels=channels, fifo=fifo)
    result = dict(format='fdisbull-sb16-documented-count-1', success=False,
        bits=bits, channels=channels, fifo=fifo, offsets=offsets, backends={},
        identical_guest_bytes_per_backend=True, no_host_guest_state_writes=True,
        no_cross_engine_pcm_or_timing_equality_claim=True)
    try:
        for engine, controller in [('dosbox', _dosbox), ('qemu', _qemu)]:
            directory = tmp_path / engine
            directory.mkdir()
            source = directory / 'COUNT.COM'
            source.write_bytes(code)
            backend = result['backends'][engine] = dict(source=dict(bytes=len(code), sha256=digest(source)))
            controller(directory, source, code, offsets, runtime, backend)
            _completed(backend, bits=bits, channels=channels, fifo=fifo)
        for engine, backend in result['backends'].items():
            expected, after = backend['documented_expected'], backend['done']
            assert (after['final_address'], after['final_count']) == (expected['address'], expected['count']), (engine, backend['observed_progress'], expected)
        result['success'] = True
    finally:
        result['original_boot_unchanged'] = digest(runtime['boot']) == runtime['boot_sha256']
        (tmp_path / 'sb16-count-result.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    assert result['original_boot_unchanged']
