"""Optional original-game witness for QEMU named input routes.

Uses the existing hash-pinned ATTT fixture and explicit native DOS runtime.
No emulator is prepared, downloaded or substituted by this test.
"""
from copy import deepcopy
import json

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from test_qemu_dos_game_parity_native import game_runtime, _launch_qemu, _number, _read_qemu_image
from test_qemu_timing_native import native_executions


def test_native_macro_public_input_wait_saved_script_and_cold_evidence(tmp_path, game_runtime, monkeypatch):
    database = tmp_path / 'native-macro.fdb'
    with Project.create(database, game_runtime['source'], image='com') as project:
        with _launch_qemu(project, tmp_path, game_runtime) as debug:
            assert debug.capabilities['input_macros'] is True
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            definition = dict(format='fdisbull-macro-set-1', name='attt-native-input', macros={
                'move': dict(parameters={
                    'key': dict(type='string', enum=['q', '4']),
                    'board_address': dict(type='string'), 'expected': dict(type='string')},
                    steps=[dict(op='keyboard.press', key='$args.key', hold_ms=80, gap_ms=80),
                           dict(op='wait', observations={'board': dict(kind='memory', address='$args.board_address',
                                length=9, space='physical')}, until=dict(observation='board', equals='$args.expected'),
                                guest_ms=750, slice_ms=50, timeout_ms=5000,
                                timeout_screenshot=None, **{'as': 'ready'})],
                    outputs=dict(matched='$ready.matched', elapsed_ns='$ready.guest_elapsed_ns')),
                'invalid': dict(steps=[dict(op='keyboard.key-down', key='a'),
                                      dict(op='memory', address=0, length=0)]),
                'observe': dict(steps=[dict(op='status')]),
            })
            saved = project.debug_define_macros(definition)
            caller_lease = debug.keyboard_key_down('ctrl')['lease']
            before = deepcopy(debug.input_state())
            clock = debug.clock_observe()['virtual_ns']
            with pytest.raises(ValueError, match='memory'):
                debug.macro(saved['id'], 'invalid')
            assert debug.input_state() == before and caller_lease in before['leases']
            assert debug.clock_observe()['virtual_ns'] == clock
            cancelled = debug.input_cancel_pending()
            assert caller_lease in cancelled['cancelled_leases']

            workspace = DebugWorkspace()
            workspace.sessions[debug.run_id] = debug
            calls = native_executions(debug, monkeypatch)
            policy = OutputPolicy(artifact_dir=tmp_path / 'outputs')
            try:
                with output_policy_context(policy):
                    reply = respond(dict(method='debug-macro', params=dict(project=str(database), run=debug.run_id,
                        macro_set=saved['id'], name='move', timeout_ms=7000,
                        args=dict(key='q', board_address=hex(base + 3), expected=(b'x' + b' ' * 8).hex()))),
                        debugger=workspace)
                    assert reply['ok'], reply
                    # Native wait evidence exceeds the normal 64-KiB wire
                    # budget. Recover its exact response; never rerun input.
                    reference = reply['result']
                    assert reference['format'] == 'fdisbull-output-ref-1', reference
                    assert reference['status'] == 'artifact_required'
                    assert reference['complete'] is False and reference['retry_safe'] is False
                    assert reference['execution']['ok'] is True
                    executed_calls = len(calls)
                    for pointer, expected in (('/ok', True), ('/result/ok', True),
                                              ('/result/outputs/matched', True)):
                        selected = respond(dict(method='output-select', params=dict(
                            artifact=reference['artifact']['id'], pointer=pointer)))
                        assert selected['ok'] and selected['result']['complete'], selected
                        assert selected['result']['value'] is expected
                    exported = tmp_path / 'public-macro-response.json'
                    delivered = respond(dict(method='output-export', params=dict(
                        artifact=reference['artifact']['id'], output=str(exported))))
                    assert delivered['ok'], delivered
                    recovered = json.loads(exported.read_bytes())
                    assert recovered['ok'] is True and recovered['id'] == reply['id']
                    result = recovered['result']
                    assert len(calls) == executed_calls > 0
            finally:
                workspace.sessions.clear()
            assert result['ok'] and result['outputs']['matched'], result
            assert result['execution']['ok'] and result['execution']['completed_steps'] == 2
            assert result['outputs']['elapsed_ns'] > 0
            assert _read_qemu_image(debug, 12)[3:12] == b'x' + b' ' * 8
            assert not debug.input_state()['leases'] and debug.input_state()['pending_edges'] == 0

            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='macro', macro_set=saved['id'], name='move', timeout_ms=7000,
                     args=dict(key='4', board_address=hex(base + 3), expected=b'x  o     '.hex()),
                     **{'as': 'move'}),
                dict(op='assert', value='$move.ok', equals=True)])
            route = project.debug_save_script('named-second-move.json', script)
            executed = debug.script(script_id=route['script_id'], timeout_ms=8000)
            assert executed['ok'], executed
            assert _read_qemu_image(debug, 12)[3:12] == b'x  o     '
            assert not debug.input_state()['leases'] and debug.input_state()['pending_edges'] == 0
            export = tmp_path / 'macro-result.json'
            project.debug_export(result['artifact'], export)
            evidence = export.read_bytes()
            assert json.loads(evidence)['outputs']['matched'] is True
            # An outer failure after an observation-only macro must preserve
            # the caller's pending lease and must not run its later suffix.
            caller_lease = debug.keyboard_key_down('ctrl')['lease']
            before = deepcopy(debug.input_state())
            clock, executed_calls = debug.clock_observe()['virtual_ns'], len(calls)
            preserving = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='macro', macro_set=saved['id'], name='observe'),
                dict(op='assert', value=1, equals=2), dict(op='run', timeout_ms=5000)])
            route = project.debug_save_script('preserve-caller-input.json', preserving)
            stopped = debug.script(script_id=route['script_id'], timeout_ms=7000)
            assert not stopped['ok'] and stopped['input_cleanup'] is None
            assert len(stopped['steps']) == 2 and stopped['steps'][0]['result']['ok']
            assert not debug.closed and debug.input_state() == before
            assert caller_lease in before['leases'] and len(calls) == executed_calls
            assert debug.clock_observe()['virtual_ns'] == clock
            assert caller_lease in debug.input_cancel_pending()['cancelled_leases']
            owner = debug.vm.process
        assert owner.poll() is not None
    with Project(database) as project:
        assert project.debug_macro_info(saved['id'])['definition'] == definition
        export = tmp_path / 'macro-result-cold.json'
        project.debug_export(result['artifact'], export)
        assert export.read_bytes() == evidence


def test_native_macro_partial_input_stops_once_and_retains_native_receipt(tmp_path, game_runtime, monkeypatch):
    with Project.create(tmp_path / 'native-macro-partial.fdb', game_runtime['source'], image='com') as project:
        with _launch_qemu(project, tmp_path, game_runtime) as debug:
            # Let the original game reach its input loop before arming a long
            # chord. Its board write then stops the machine between make/break.
            ready = debug.clock_advance(750_000_000, timeout_ms=5000)
            assert ready['clock_budget']['deadline_reached']
            assert _read_qemu_image(debug, 12)[3:12] == b' ' * 9
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            point = debug.breakpoint(base + 3, access='w', length=1)
            definition = dict(format='fdisbull-macro-set-1', name='attt-native-partial', macros={
                'interrupted': dict(steps=[
                    dict(op='keyboard.press', key='q', hold_ms=1000, gap_ms=80),
                    dict(op='run', timeout_ms=5000),
                    dict(op='keyboard.press', key='4', hold_ms=80, gap_ms=80),
                    dict(op='run', timeout_ms=5000)])})
            saved = project.debug_define_macros(definition)
            calls = native_executions(debug, monkeypatch)
            qmp, native_calls = debug.vm.qmp.call, []
            def observe_qmp(command, *args, **kwargs):
                native_calls.append(command)
                return qmp(command, *args, **kwargs)
            monkeypatch.setattr(debug.vm.qmp, 'call', observe_qmp)
            owner = debug.vm.process
            result = debug.macro(saved['id'], 'interrupted', timeout_ms=7000)
            assert not result['ok'] and debug.closed and owner.poll() is not None
            assert len(result['execution']['steps']) == 2 and len(calls) == 1
            stop = result['execution']['steps'][-1]['result']
            assert stop['outcome'] == 'watchpoint', stop
            assert point['breakpoint_id'] in stop['session']['stop_reason']['breakpoint_ids']
            assert stop['session']['stop_reason']['native_reply'] == calls[0]['reply'][0].decode('ascii')
            delivery = stop['input_delivery']
            assert delivery['state'] == 'cancelled' and delivery['requires_resolution'] is True
            assert delivery['press']['dispatched_count'] == 1
            assert delivery['press']['undispatched_count'] == 1
            assert delivery['guest_consumed'] is None
            edges = delivery['native']['press']['steps']
            assert edges[0]['dispatch-ns'] <= delivery['terminal_ns'] < edges[1]['deadline-ns']
            assert native_calls.count('x-fdisbull-arm-keyboard-press') == 1
            assert 'input-send-event' not in native_calls
            assert result['execution']['input_cleanup']['closed']
            assert not debug._input_storage()['leases']
