"""Optional original-game witness for QEMU named input routes.

Uses the existing hash-pinned ATTT fixture and explicit native DOS runtime.
No emulator is prepared, downloaded or substituted by this test.
"""
from copy import deepcopy
import json

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from test_qemu_dos_game_parity_native import game_runtime, _launch_qemu, _number, _read_qemu_image


def test_native_macro_public_input_wait_saved_script_and_cold_evidence(tmp_path, game_runtime):
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
            try:
                reply = respond(dict(method='debug-macro', params=dict(project=str(database), run=debug.run_id,
                    macro_set=saved['id'], name='move', timeout_ms=7000,
                    args=dict(key='q', board_address=hex(base + 3), expected=(b'x' + b' ' * 8).hex()))),
                    debugger=workspace)
            finally:
                workspace.sessions.clear()
            assert reply['ok'], reply
            result = reply['result']
            assert result['ok'] and result['outputs']['matched'], result
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
            owner = debug.vm.process
        assert owner.poll() is not None
    with Project(database) as project:
        assert project.debug_macro_info(saved['id'])['definition'] == definition
        export = tmp_path / 'macro-result-cold.json'
        project.debug_export(result['artifact'], export)
        assert export.read_bytes() == evidence
