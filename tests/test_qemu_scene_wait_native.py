"""Finite scene-2 wait acceptance on an independently authored DOS IRQ1 guest.

Ten cases own at most eleven VM lifetimes: three public routes, initial-match
and invalid-script admission, timeout, two first stops, one two-owner restore,
and real DOS exit/TSR. These tests are prepared requirements, not a claim of execution.
See docs/QEMU_SCENE_WAIT_GATE.md for inputs, bounds and admission.
"""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import hashlib
import json
import struct
import time

import pytest

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from fdisbull.scenes import SceneError
from support.dos_process_fixture import com_exit, resident_com
from support.qemu_scene_wait_assertions import initial_match_preserves_arm
from test_qemu_clock_budget_native import clock_runtime, clock_disk
from test_qemu_dos_process_native import com_address, process_record, launch_options
from test_qemu_dos_le_checkpoint_native import _checkpoint_tool
from test_qemu_scenes_native import definition, launch as launch_scene, passive


@contextmanager
def body_deadline(debug, seconds=30):
    previous = getattr(debug, '_rpc_deadline', None)
    deadline = time.monotonic() + seconds
    debug._rpc_deadline = min(previous, deadline) if previous is not None else deadline
    try:yield
    finally:debug._rpc_deadline = previous


@contextmanager
def launch(tmp_path, runtime, disk, *, body_timeout=30):
    with launch_scene(tmp_path, runtime, disk) as state, body_deadline(state[1], body_timeout):
        yield state


def wait_options(scene='edges', **changes):
    return dict(dict(scene=scene, object='actor', guest_ms=500, slice_ms=25,
                     timeout_ms=5000), **changes)


def save_edges(project, *, make_only=False):
    doc = definition()
    # "Released" and "an edge occurred" describe independent facts, not
    # mutually exclusive scene identities. Keep their recognition groups apart.
    doc['exclusive_group'] = 'input-ledger'
    doc['context']['state'] = 'authored IRQ1 make' if make_only else 'authored IRQ1 make and break'
    doc['match'] = {'runtime_memory': dict(binding='scene-state', offset=10,
        length=1 if make_only else 5, hex='01' if make_only else '0101021e9e')}
    return project.debug_save_scene('edges', doc)


def instrument(debug):
    """Count actual native execution and public RAM probes; do not replace them."""
    calls, reads, boundaries = [], [], []
    execute, read, advance = debug.vm.gdb.execute, debug.runtime_memory, debug._clock_advance_with_hooks
    def tracked_execute(*args, **kwargs):
        calls.append(args)
        return execute(*args, **kwargs)
    def tracked_read(*args, **kwargs):
        reads.append(args)
        return read(*args, **kwargs)
    def tracked_advance(*args, **kwargs):
        result = advance(*args, **kwargs)
        boundaries.append(dict(result=result, reads=len(reads), executions=len(calls)))
        return result
    debug.vm.gdb.execute = tracked_execute
    debug.runtime_memory = tracked_read
    debug._clock_advance_with_hooks = tracked_advance
    return calls, reads, boundaries


@pytest.mark.parametrize('route', ['python', 'json', 'script'])
def test_native_scene_wait_public_routes(tmp_path, clock_runtime, clock_disk, route):
    database = tmp_path / 'scene.fdb'
    with launch(tmp_path, clock_runtime, clock_disk) as (project, debug, bind, bound, released):
        assert debug.capabilities['runtime_scene_wait']
        save_edges(project)
        assert debug.runtime_memory(bound['id'], offset=10, length=5)['hex'] == '0000000000'
        debug.keyboard_press('a', hold_ms=80, gap_ms=80)
        calls, reads, boundaries = instrument(debug)
        if route == 'python':
            canonical = result = debug.scene_wait(**wait_options())
        elif route == 'script':
            script = project.debug_save_script('scene-wait.json', dict(
                format='fdisbull-script-1', backend='qemu-dos', steps=[
                    dict(op='scene-wait', **wait_options(), **{'as': 'ready'}),
                    dict(op='assert', value='$ready.status', equals='matched')]))
            scripted = debug.script(script_id=script['script_id'], timeout_ms=7000)
            assert scripted['ok'] and scripted['completed_steps'] == 2, scripted
            canonical = result = scripted['steps'][0]['result']
        else:
            observed_waits = []
            original_wait = debug.scene_wait
            @wraps(original_wait)
            def capture_wait(*args, **kwargs):
                result = original_wait(*args, **kwargs)
                observed_waits.append(deepcopy(result))
                return result
            debug.scene_wait = capture_wait
            workspace = DebugWorkspace()
            workspace.sessions[debug.run_id] = debug
            try:
                with output_policy_context(OutputPolicy(max_inline_bytes=4096,
                        artifact_dir=tmp_path / 'bounded-outputs')):
                    reply = respond(dict(method='debug-scene-wait', params=dict(
                        project=str(database), run=debug.run_id, **wait_options())), debugger=workspace)
                    assert reply['ok'], reply
                    marker = reply['result']
                    assert marker['format'] == 'fdisbull-output-ref-1' and not marker['complete']
                    assert marker['execution']['complete'] is True and marker['retry_safe'] is False
                    before_clock = debug.clock_observe()['virtual_ns']
                    before = (len(calls), len(boundaries), len(project.debug_scene_observations()['observations']))
                    output = tmp_path / 'completed-scene-wait.json'
                    exported = respond(dict(method='output-export', params=dict(
                        artifact=marker['artifact']['id'], output=str(output))))
                    assert exported['ok'], exported
                    raw = output.read_bytes()
                    assert len(raw) == marker['artifact']['bytes']
                    assert hashlib.sha256(raw).hexdigest() == marker['artifact']['sha256']
                    result = json.loads(raw)['result']
                    assert debug.clock_observe()['virtual_ns'] == before_clock
                    assert before == (len(calls), len(boundaries), len(project.debug_scene_observations()['observations']))
                    assert len(observed_waits) == 1
                    canonical = observed_waits[0]
                    assert result == public_addresses(canonical)
                    for original, projected in zip(canonical['wait']['runs'], result['wait']['runs'], strict=True):
                        for field in ('start', 'end'):
                            address = original['process']['allocation'][field]
                            assert type(address) is int
                            assert projected['process']['allocation'][field] == hex(address)
                        headers = original['process']['drivers']['headers']
                        public_headers = projected['process']['drivers']['headers']
                        assert headers
                        for header, public_header in zip(headers, public_headers, strict=True):
                            assert type(header['address']) is int
                            assert public_header['address'] == hex(header['address'])
            finally:
                workspace.sessions.clear()
                debug.scene_wait = original_wait
        assert result['status'] == 'matched' and result['complete'], result
        assert result['completion_scope'] == 'declared-runtime-predicates' and 'frame' not in result
        wait = result['wait']
        assert wait['outcome'] == 'predicate' and wait['clock_progress_complete']
        assert wait['clock_domain'] == 'QEMU_CLOCK_VIRTUAL' and 0 < wait['guest_elapsed_ns'] <= 500_000_000
        assert wait['guest_elapsed_ns'] == wait['final_clock']['virtual_ns'] - wait['initial_clock']['virtual_ns']
        assert wait['guest_elapsed_ms'] == wait['guest_elapsed_ns'] / 1_000_000
        assert wait['polls'][0]['status'] == 'mismatch' and wait['polls'][-1]['status'] == 'matched'
        assert wait['input_plan']['first_slice_attempted'] and not wait['input_plan']['release']
        assert len(calls) == len(boundaries) == len(wait['runs'])
        assert canonical['wait']['runs'] == [boundary['result'] for boundary in boundaries]
        ledger = debug.runtime_memory(bound['id'], offset=10, length=5)['hex']
        assert ledger == '0101021e9e' and not debug._input_pending()
        assert not debug.input_state()['leases']
        assert project.debug_scene_observation(canonical['observation'])['result'] == canonical
    with Project(database) as reopened:
        historical = reopened.debug_scene_observation(canonical['observation'])
        assert historical['result'] == canonical and historical['historical'] and not historical['live_state_verified']


def test_native_initial_match_preserves_fixed_arm_and_invalid_script(tmp_path, clock_runtime, clock_disk):
    with launch(tmp_path, clock_runtime, clock_disk) as (project, debug, bind, bound, scene):
        debug.keyboard_press('a', hold_ms=80, gap_ms=80)
        inputs = deepcopy(debug.input_state())
        calls, reads, boundaries = instrument(debug)
        invalid = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
            dict(op='write-runtime-memory', binding='scene-state', offset=8, data_hex='01', expected_hex='00'),
            dict(op='scene-wait', scene='released', timeout_ms=True)])
        with pytest.raises(ValueError, match='integer'):debug.script(invalid)
        assert not calls and not reads and not boundaries and debug.input_state() == inputs
        result = initial_match_preserves_arm(debug, lambda: debug.scene_wait(**wait_options('released')))
        assert result['complete'] and result['wait']['guest_elapsed_ns'] == 0
        assert len(result['wait']['polls']) == 1 and not result['wait']['runs']
        assert not result['wait']['input_plan']['first_slice_attempted']
        assert not calls and not boundaries
        assert debug.runtime_memory(bound['id'], offset=8, length=7)['hex'] == '00010000000000'


def test_native_false_scene_wait_measures_budget_timeout(tmp_path, clock_runtime, clock_disk):
    with launch(tmp_path, clock_runtime, clock_disk) as (project, debug, bind, bound, scene):
        doc = definition()
        doc['match'] = {'runtime_memory': dict(binding='scene-state', offset=10, length=1, hex='ff')}
        project.debug_save_scene('never', doc)
        calls, reads, boundaries = instrument(debug)
        with pytest.raises(SceneError) as error:
            debug.scene_wait(**dict(wait_options('never'), guest_ms=20, slice_ms=5))
        result = error.value.result
        wait = result['wait']
        assert result['status'] == 'timeout' and not result['complete'] and wait['outcome'] == 'guest_budget'
        assert wait['requested_virtual_ns'] == 20_000_000 and wait['clock_progress_complete']
        assert wait['guest_elapsed_ns'] >= wait['requested_virtual_ns']
        assert wait['guest_elapsed_ns'] == wait['final_clock']['virtual_ns'] - wait['initial_clock']['virtual_ns']
        assert wait['guest_budget_overshoot_ms'] == wait['guest_elapsed_ns'] / 1_000_000 - 20
        assert 1 <= len(calls) == len(boundaries) == len(wait['runs']) <= 4
        limit = wait['initial_clock']['virtual_ns'] + wait['requested_virtual_ns']
        assert all(run['clock_budget']['start_ns'] < limit for run in wait['runs'])
        assert all(run['clock_budget']['stopped_ns'] < limit for run in wait['runs'][:-1])
        assert project.debug_scene_observation(result['observation'])['result'] == result
        assert not debug.closed and not debug._input_pending()


@pytest.mark.parametrize('stop_kind', ['breakpoint', 'watchpoint'])
def test_native_scene_wait_keeps_first_native_stop(tmp_path, clock_runtime, clock_disk, stop_kind):
    with launch(tmp_path, clock_runtime, clock_disk) as (project, debug, bind, bound, scene):
        save_edges(project, make_only=True)
        code = (tmp_path / 'SCENE.COM').read_bytes()
        _, irq_fence, state, *_ = struct.unpack_from('<11H', code, len(code) - 22)
        info = process_record(debug)
        point = debug.breakpoint(com_address(info, irq_fence) if stop_kind == 'breakpoint'
            else com_address(info, state + 8), access='x' if stop_kind == 'breakpoint' else 'w')
        debug.keyboard_press('a', hold_ms=80, gap_ms=80)
        calls, reads, boundaries = instrument(debug)
        with pytest.raises(SceneError) as error:debug.scene_wait(**wait_options())
        result = error.value.result
        wait = result['wait']
        assert result['status'] == 'stopped' and not result['complete']
        assert wait['outcome'] == stop_kind and wait['stop'] is boundaries[0]['result']
        assert point['breakpoint_id'] in wait['stop']['session']['stop_reason']['breakpoint_ids']
        assert len(wait['polls']) == len(wait['runs']) == len(calls) == len(boundaries) == 1
        assert len(reads) == boundaries[0]['reads'] and result['scene_matched'] is False
        assert not debug.closed and debug.input_state()['leases']
        assert wait['stop']['input_delivery']['requires_resolution'] is True
        # The native write precedes the IRQ fence and the held-byte store. This
        # separate caller read proves the predicate is now true; the wait did
        # not read or continue after the higher-priority native stop.
        assert debug.runtime_memory(bound['id'], offset=10, length=1)['hex'] == '01'
        assert len(calls) == 1


def test_native_restore_requires_new_scene_wait_witness(tmp_path, clock_runtime, clock_disk):
    with launch(tmp_path, clock_runtime, clock_disk, body_timeout=60) as (project, debug, bind, bound, scene):
        before = debug.scene_wait(**wait_options('released'))
        saved = debug.save_machine_state()
        owner, epoch = debug.vm, debug._runtime_epoch
        restored = debug.load_machine_state(saved['artifact'], timeout_ms=30000)
        assert debug.vm is not owner and owner.process.poll() is not None and debug._runtime_epoch != epoch
        assert restored['machine_state_restored'] and not restored['source_binding_restored']
        calls, reads, boundaries = instrument(debug)
        with pytest.raises(SceneError) as error:debug.scene_wait(**wait_options('released'))
        stale = error.value.result
        assert stale['status'] == 'unavailable' and not stale['complete']
        assert not calls and not boundaries and not debug._runtime_bindings
        assert project.debug_scene_observation(before['observation'])['result'] == before
        fresh = bind()
        assert fresh['id'] != bound['id']
        after = passive(debug, lambda: debug.scene_wait(**wait_options('released')))
        assert after['status'] == 'matched' and after['wait']['guest_elapsed_ns'] == 0
        assert after['observation_context']['capture_epoch'] != before['observation_context']['capture_epoch']
        assert not calls and not boundaries and not debug._process['source_mapping']['live']


@pytest.mark.parametrize('outcome', ['guest_exit', 'guest_tsr'])
def test_native_scene_wait_records_dos_return(tmp_path, clock_runtime, clock_disk, outcome):
    code = com_exit(37) if outcome == 'guest_exit' else resident_com(exit_code=37)[0]
    binary = tmp_path / ('SCNEXIT.COM' if outcome == 'guest_exit' else 'SCNTSR.COM')
    binary.write_bytes(code)
    database = tmp_path / 'terminal.fdb'
    selected = launch_options(clock_runtime, clock_disk, qemu_clock='virtual',
                              qemu_checkpoint_tool=str(_checkpoint_tool()))
    with Project.create(database, binary, image='com') as project:
        project.analyze(max_instructions=1)
        with project.debugger(clock_runtime['executable'], tmp_path, **selected) as debug:
            with body_deadline(debug):
                info = process_record(debug)
                debug.bind_runtime_memory('terminal-state', com_address(info, 0x100), length=1,
                    expected_hex='90', provenance=dict(fixture=outcome, sha256=hashlib.sha256(code).hexdigest()),
                    space='physical')
                doc = definition()
                doc['context']['state'] = 'false predicate before authored DOS return'
                doc['match'] = {'runtime_memory': dict(binding='terminal-state', length=1, hex='ff')}
                project.debug_save_scene('before-return', doc)
                owner, epoch = debug.vm, debug._runtime_epoch
                calls, reads, boundaries = instrument(debug)
                if outcome == 'guest_exit':
                    workspace = DebugWorkspace()
                    workspace.sessions[debug.run_id] = debug
                    try:
                        with output_policy_context(OutputPolicy(max_inline_bytes=1048576)):
                            reply = respond(dict(method='debug-scene-wait', params=dict(
                                project=str(database), run=debug.run_id, **wait_options('before-return'))),
                                debugger=workspace)
                    finally:workspace.sessions.clear()
                    assert not reply['ok'] and reply['error']['type'] == 'SceneError', reply
                    result = reply['error']['result']
                else:
                    script = project.debug_save_script('terminal-wait.json', dict(
                        format='fdisbull-script-1', backend='qemu-dos', steps=[
                            dict(op='scene-wait', **wait_options('before-return')),
                            dict(op='assert', value=True, equals=True)]))
                    scripted = debug.script(script_id=script['script_id'], timeout_ms=7000)
                    assert not scripted['ok'] and scripted['completed_steps'] == 0
                    assert len(scripted['steps']) == 1 and scripted['steps'][0]['error']['type'] == 'SceneError'
                    result = scripted['steps'][0]['result']
                wait, terminal = result['wait'], result['wait']['stop']
                assert result['status'] == 'stopped' and not result['complete'] and result['scene_matched'] is False
                assert wait['outcome'] == terminal['outcome'] == outcome
                assert terminal == boundaries[-1]['result'] and terminal['session']['stop_reason']['kind'] == outcome
                assert terminal['process']['termination']['code'] == 37
                assert terminal['process']['termination']['resident'] is (outcome == 'guest_tsr')
                assert terminal['process'] == debug._process and debug.vm is owner
                assert terminal['process']['capture_epoch'] == debug._runtime_epoch != epoch
                assert terminal['native_machine_stop']['kind'] == 'breakpoint'
                assert len(calls) == len(boundaries) == len(wait['runs'])
                assert len(wait['polls']) == len(wait['runs'])
                assert len(reads) == boundaries[-1]['reads']
                assert wait['clock_progress_complete'] and wait['guest_elapsed_ns'] > 0
                assert project.debug_scene_observation(result['observation'])['result'] == result
                assert not debug.closed and owner.process.poll() is None
            native = debug.vm.process
        assert native.poll() is not None
    with Project(database) as reopened:
        historical = reopened.debug_scene_observation(result['observation'])
        assert historical['result'] == result and historical['historical'] and not historical['live_state_verified']
