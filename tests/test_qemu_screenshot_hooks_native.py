"""Authored COM witness for passive stopped-surface hooks and exact cleanup.

Uses the explicit QEMU clock lane, original caller-owned FreeDOS and the
ordinary layer/surface primitives. No game or new native command is required.
"""
from copy import deepcopy

import pytest

from fdisbull.screenshot_hooks import ScreenshotHookError
from support.dos_process_fixture import digest
from test_qemu_clock_budget_native import clock_runtime, clock_disk, park
from test_qemu_dos_process_native import create_project, launch_options, process_record, com_address
from test_qemu_timing_native import native_executions


def test_native_stopped_surface_hooks_restore_layers_without_guest_advance(
        tmp_path, clock_runtime, clock_disk, monkeypatch):
    # Set mode 13h and pixel zero to palette entry four, then loop. The word
    # at COM offset 20h is ordinary data and is never read by this guest.
    prefix = bytes.fromhex('b81300cd10b800a08ec026c606000004')
    code = (prefix + bytes.fromhex('ebfe')).ljust(0x20, b'\0') + bytes.fromhex('3412')
    binary, project = create_project(tmp_path, code, filename='SURFACE.COM')
    debug = None
    try:
        with project:
            with project.debugger(clock_runtime['executable'], tmp_path,
                    **launch_options(clock_runtime, clock_disk, qemu_clock='virtual')) as debug:
                info = process_record(debug)
                park(debug, com_address(info, 0x100 + len(prefix)))
                runtime_word = com_address(info, 0x120)
                layer = debug.layer_patch('stopped-data', runtime_word, expected_hex='3412',
                    data_hex='efbe', kind='ram', activate=True, space='physical')['layer']
                assert debug.memory(runtime_word, length=2)['hex'] == 'efbe'
                calls = native_executions(debug, monkeypatch)
                caller_lease = debug.keyboard_key_down('ctrl')['lease']
                input_before = deepcopy(debug.input_state())
                before_cpu = debug.registers()
                before_clock = debug.clock_observe()
                # Project storage is shared with legacy DOSBox. An incompatible
                # policy must be rejected by QEMU before any layer/capture work.
                project.debug_screenshot_hooks(dict(suspend_layers=[layer], require_fresh_frame=True))
                generation = debug.layers()['generation']
                with pytest.raises(ValueError, match='require_fresh_frame=false'):
                    debug.screenshot()
                assert debug.layers()['generation'] == generation
                assert debug.input_state() == input_before and calls == []

                policy = dict(require_fresh_frame=False, suspend_layers=[layer],
                    pre=[dict(op='memory', address=runtime_word, length=2, **{'as': 'data'}),
                         dict(op='assert', value='$data.hex', equals='3412')],
                    post=[dict(op='memory', address=runtime_word, length=2, **{'as': 'data'}),
                          dict(op='assert', value='$data.hex', equals='3412')])
                saved = debug.screenshot_hooks(policy)
                result = debug.screenshot('stopped-hooks.png')
                report, metadata = result['screenshot_hooks'], result['metadata']
                assert report['ok'] and report['pre']['ok'] and report['post']['ok'], report
                assert report['restore'] == dict(ok=True, active=[layer])
                assert metadata['screenshot_hooks']['policy_sha256'] == saved['sha256']
                assert metadata['screenshot_hooks']['capture_layers'] == []
                assert metadata['completed_guest_frame'] is None and metadata['guest_frame_id'] is None
                assert metadata['capture_id'] and metadata['selected_cpu_unchanged']
                assert metadata['clocks']['before']['virtual_ns'] == metadata['clocks']['after']['virtual_ns']
                assert debug.memory(runtime_word, length=2)['hex'] == 'efbe'
                assert debug.registers() == before_cpu
                after_clock = debug.clock_observe()
                assert after_clock['virtual_ns'] == before_clock['virtual_ns']
                assert after_clock['counter'] == before_clock['counter']
                assert debug.input_state() == input_before and caller_lease in input_before['leases']
                assert calls == []

                # The first failed assertion prevents the later control, keeps
                # the exact failed prefix and restores without a cleanup run.
                debug.screenshot_hooks(dict(policy, pre=[dict(op='assert', value=1, equals=2),
                                                         dict(op='layer-enable', layer=layer)]))
                with pytest.raises(ScreenshotHookError) as failed:
                    debug.screenshot('not-captured.png')
                failed_report = failed.value.result
                assert failed_report['capture'] is None and len(failed_report['pre']['steps']) == 1
                assert failed_report['post']['ok'] and failed_report['restore']['ok']
                assert debug.layers()['active'] == [layer]
                assert debug.memory(runtime_word, length=2)['hex'] == 'efbe'
                assert debug.input_state() == input_before and calls == []
                assert debug.clock_observe()['virtual_ns'] == before_clock['virtual_ns']
                raw = debug.capture_surface('direct-surface.png')
                assert 'screenshot_hooks' not in raw['metadata']
                assert raw['metadata']['completed_guest_frame'] is None and calls == []
                assert caller_lease in debug.input_cancel_pending()['cancelled_leases']
    finally:
        if debug is not None:
            assert debug.vm.process.poll() is not None
        assert binary.read_bytes() == code
        assert digest(clock_disk['image']) == clock_disk['prepared_sha256']
