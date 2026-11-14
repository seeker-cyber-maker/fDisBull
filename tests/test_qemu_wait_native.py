"""Original-game input to observed readiness through public native wait routes.

Uses the same admitted original ATTT fixture as the paired workload. Native
virtual time is explicit; a matched board does not imply all queued key edges
have finished, so the caller separately drains its owned input before saving.
"""
import json
import hashlib
import os

import pytest

from fdisbull.cli import respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from fdisbull.output_limits import OutputPolicy, output_policy_context
from test_qemu_dos_game_parity_native import game_runtime, _launch_qemu, _number, _read_qemu_image


def test_original_game_json_wait_saved_script_and_cold_evidence(tmp_path, game_runtime):
    tool = os.environ.get('FDISBULL_QEMU_IMG')
    if not tool:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail('Native wait acceptance requires FDISBULL_QEMU_IMG')
        pytest.skip('Set FDISBULL_QEMU_IMG for original-game wait acceptance')
    database = tmp_path/'observed-input.fdb'
    with Project.create(database, game_runtime['source'], image='com') as project:
        with _launch_qemu(project, tmp_path, game_runtime, checkpoint_tool=tool) as debug:
            base = _number(debug.dos_process_info()['source_mapping']['runtime_base'])
            observations = {'board':dict(kind='memory', address=hex(base+3), length=9, space='physical')}
            params = dict(observations=observations, guest_ms=750, slice_ms=50,
                          timeout_ms=5000, timeout_screenshot=None)
            debug.keyboard_press('q', hold_ms=80, gap_ms=80)
            workspace = DebugWorkspace()
            workspace.sessions[debug.run_id] = debug
            try:
                with output_policy_context(OutputPolicy(max_inline_bytes=4096,
                        artifact_dir=tmp_path/'bounded-outputs')):
                    reply = respond(dict(method='debug-wait', params=dict(project=str(database), run=debug.run_id,
                        until=dict(observation='board', equals=(b'x'+b' '*8).hex()), **params)), debugger=workspace)
                    assert reply['ok'], reply
                    marker=reply['result']
                    assert marker['format']=='fdisbull-output-ref-1' and marker['complete'] is False
                    assert marker['execution']['complete'] is True and marker['retry_safe'] is False
                    before_clock=debug.clock_observe()['virtual_ns']
                    before_events=project.db.execute("SELECT count(*) FROM debug_events WHERE operation='wait'").fetchone()[0]
                    recovered_path=tmp_path/'completed-wait-response.json'
                    exported=respond(dict(method='output-export',params=dict(
                        artifact=marker['artifact']['id'],output=str(recovered_path))))
                    assert exported['ok'],exported
                    recovered=recovered_path.read_bytes()
                    assert len(recovered)==marker['artifact']['bytes']
                    assert hashlib.sha256(recovered).hexdigest()==marker['artifact']['sha256']
                    reply=json.loads(recovered)
                    assert debug.clock_observe()['virtual_ns']==before_clock
                    assert project.db.execute("SELECT count(*) FROM debug_events WHERE operation='wait'").fetchone()[0]==before_events==1
            finally:
                workspace.sessions.clear()
            assert reply['ok'], reply
            observed = reply['result']
            assert observed['complete'] and observed['matched'] and observed['outcome']=='predicate'
            assert observed['clock_domain']=='QEMU_CLOCK_VIRTUAL'
            assert observed['guest_elapsed_ns']>0
            assert observed['guest_elapsed_ms']==observed['guest_elapsed_ns']/1_000_000
            assert _read_qemu_image(debug, 12)[3:12]==b'x'+b' '*8
            # The board proves this input's effect. It does not certify the
            # scheduled key-up; finish that bounded native input interval.
            debug.clock_advance(200_000_000, timeout_ms=5000)
            assert debug.input_state()['pending_edges']==0
            script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
                dict(op='wait', until=dict(observation='board',equals=b'x  o     '.hex()),
                     **params, **{'as':'ready'}),
                dict(op='assert',value='$ready.matched',equals=True)])
            saved_script=project.debug_save_script('wait-for-second-move.json',script)
            debug.keyboard_press('4',hold_ms=80,gap_ms=80)
            scripted=debug.script(script_id=saved_script['script_id'],timeout_ms=7000)
            assert scripted['ok'] and scripted['completed_steps']==2,scripted
            assert scripted['steps'][0]['result']['guest_elapsed_ns']>0
            assert _read_qemu_image(debug,12)[3:12]==b'x  o     '
            debug.clock_advance(200_000_000,timeout_ms=5000)
            checkpoint=debug.save_state()
            route_path=tmp_path/'route-result.json'
            project.debug_export(scripted['artifact'],route_path)
            route_bytes=route_path.read_bytes()
            assert json.loads(route_bytes)['steps'][0]['result']['clock_domain']=='QEMU_CLOCK_VIRTUAL'
            original_owner=debug.vm.process
        assert original_owner.poll() is not None
    with Project(database) as project:
        assert any(x['id']==saved_script['script_id'] for x in project.debug_scripts()['scripts'])
        export=tmp_path/'route-result-cold.json'
        project.debug_export(scripted['artifact'],export)
        assert export.read_bytes()==route_bytes
        with _launch_qemu(project,tmp_path,game_runtime,checkpoint_tool=tool) as debug:
            assert debug.load_state(checkpoint['artifact'])['source_binding_restored']
            base=_number(debug.dos_process_info()['source_mapping']['runtime_base'])
            immediate=debug.wait({'board':dict(kind='memory',address=hex(base+3),length=9)},
                dict(observation='board',equals=b'x  o     '.hex()),guest_ms=100,
                timeout_ms=3000,timeout_screenshot=None)
            assert immediate['matched'] and immediate['guest_elapsed_ns']==0
            debug.keyboard_press('escape',hold_ms=80,gap_ms=80)
            exited=debug.run(timeout_ms=5000)
            assert exited['outcome']=='guest_exit' and exited['process']['termination']['code']==0
