"""Two prepared DOS named-action witnesses; no native execution is implied.

The unchanged authored COM owns IRQ1 and records actual scancodes separately
from its BIOS-tick-driven position. Only these two tests are admitted by the
finite gate; each owns one fresh VM and never restores or retries an action.
"""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import hashlib
import json
import time

from fdisbull.cli import public_addresses, respond
from fdisbull.debugger import DebugWorkspace
from fdisbull.output_limits import OutputPolicy, output_policy_context
from fdisbull.project import Project
from support.dos_process_fixture import digest
from support.observed_movement_fixture import movement_guest
from test_qemu_clock_budget_native import clock_disk, clock_runtime
from test_qemu_dos_process_native import com_address, launch_options, process_record


PRESS = dict(kind='press', key='a', modifiers=[], hold_ms=80, gap_ms=80)
GUEST_MS, SLICE_MS, ACTION_MS = 500, 25, 5000
WORK_SECONDS = 50  # The separate owner controller reserves ten more for cleanup.


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def write_json(directory, name, value):
    (directory / name).write_text(json.dumps(value, sort_keys=True, indent=2,
                                           allow_nan=False) + '\n')


def remaining(deadline, maximum_ms):
    value = int((deadline - time.monotonic()) * 1000)
    if value <= 0:
        raise TimeoutError('Authored native scene-action case exhausted its original work deadline')
    return min(value, maximum_ms)


def memory_predicate(offset, value):
    return {'runtime_memory': dict(binding='action-state', offset=offset,
                                   length=len(bytes.fromhex(value)), hex=value)}


def position_predicate(op, value):
    return {'compare': dict(left={'runtime_memory': dict(binding='action-state',
        offset=4, type='u16')}, op=op, right=value)}


def definition(*, blocked=False):
    context = dict(state='authored IRQ1 input and guest position',
                   triggers=['actual a make/break and guest BIOS-tick loop'])
    ready = (memory_predicate(8, '01') if blocked else {'all': [
        position_predicate('eq', 0), memory_predicate(8, '00'),
        memory_predicate(10, '000000')]})
    return dict(format='fdisbull-scene-3',
        observation_profile=dict(kind='runtime-memory', version=1),
        action_profile=dict(kind='qemu-virtual-keyboard', version=1),
        context=context, exclusive_group='blocked-action' if blocked else 'named-action',
        match=memory_predicate(0, b'MV01'.hex()), objects=[dict(
            name='actor', context=context, visible={'constant': True}, ready=ready,
            enabled={'constant': True}, action=deepcopy(PRESS), guest_ms=GUEST_MS,
            timeout_ms=ACTION_MS, outcome_phase='state', outcome={'all': [
                memory_predicate(10, '0101021e9e'), memory_predicate(8, '00'),
                position_predicate('gt', 0)]})])


def action_options(scene):
    return dict(scene=scene, object='actor', guest_ms=GUEST_MS,
                timeout_ms=ACTION_MS, slice_ms=SLICE_MS)


@contextmanager
def launch(directory, runtime, disk):
    deadline = time.monotonic() + WORK_SECONDS
    source, symbols = movement_guest(directory, runtime['nasm'])
    binary = directory / 'ACTION.COM'
    binary.write_bytes(source)
    database = directory / 'action.fdb'
    source_hash = hashlib.sha256(source).hexdigest()
    boot_hash = digest(runtime['boot_image'])
    options = launch_options(runtime, disk, qemu_clock='virtual', qemu_audio='off',
        qemu_retrace='standard', boot_timeout_ms=remaining(deadline, 15000))
    owner = None
    with Project.create(database, binary, image='com') as project:
        project.analyze(start=hex(project.regions(1)[0].start + symbols['ready'] - 0x100),
                        max_instructions=1)
        with project.debugger(runtime['executable'], directory, **options) as debug:
            owner = debug.vm
            previous = getattr(debug, '_rpc_deadline', None)
            debug._rpc_deadline = min(previous, deadline) if previous is not None else deadline
            try:
                process = process_record(debug)
                address = lambda name: com_address(process, symbols[name])
                point = debug.breakpoint(address('ready'))
                setup = debug.run(timeout_ms=remaining(deadline, 10000))
                assert setup['outcome'] == 'breakpoint', setup
                assert point['breakpoint_id'] in setup['session']['stop_reason']['breakpoint_ids']
                debug.delete_breakpoint(point['breakpoint_id'])
                bound = debug.bind_runtime_memory('action-state', address('state'), length=29,
                    expected_hex=b'MV01'.hex(), provenance=dict(
                        fixture='unchanged authored IRQ1 and BIOS-tick COM', sha256=source_hash),
                    space='physical')
                assert debug.capabilities['virtual_keyboard_press'] is True
                yield dict(project=project, debug=debug, bound=bound, address=address,
                    source=source, source_hash=source_hash, boot_hash=boot_hash,
                    baseline_hash=disk['prepared_sha256'], setup=setup,
                    owner=owner, deadline=deadline, case_deadline=deadline + 10,
                    database=database)
            finally:
                debug._rpc_deadline = previous
        assert owner.process.poll() == 0
        assert owner.qmp is None and owner.gdb is None
        assert owner.temporary is None and owner._qemu_image_proof is None
    assert binary.read_bytes() == source
    assert digest(runtime['boot_image']) == boot_hash
    assert digest(disk['image']) == disk['prepared_sha256']
    remaining(deadline + 10, 1)


def wire_value(value):
    """Retain actual wire bytes in JSON without changing the returned object."""
    if isinstance(value, bytes):
        return {'bytes_hex': value.hex()}
    if isinstance(value, (tuple, list)):
        return [wire_value(item) for item in value]
    if isinstance(value, dict):
        return {key: wire_value(item) for key, item in value.items()}
    return value


class Observer:
    """Wrap real bound methods; record results and boundaries without a read."""
    def __init__(self, debug, directory):
        self.debug, self.directory = debug, directory
        self.records = {name: [] for name in (
            'reads', 'executions', 'runs', 'presses', 'releases', 'cancels',
            'actions', 'scripts')}
        self.originals = []

    def wrap(self, owner, name, category):
        original = getattr(owner, name)
        self.originals.append((owner, name, original))

        @wraps(original)
        def observed(*args, **kwargs):
            record = dict(args=wire_value(args), kwargs=wire_value(kwargs))
            self.records[category].append(record)
            if category == 'runs':
                record['reads_before'] = len(self.records['reads'])
                record['executions_before'] = len(self.records['executions'])
            try:
                result = original(*args, **kwargs)
            except BaseException as error:
                record['error'] = dict(type=type(error).__name__, message=str(error))
                primary = getattr(error, 'result', None)
                if primary is not None:
                    record['error']['result'] = deepcopy(primary)
                prefix = getattr(error, 'scene_act_result', None)
                if prefix is not None and prefix is not primary:
                    record['error']['scene_act_result'] = deepcopy(prefix)
                raise
            else:
                record['result'] = deepcopy(wire_value(result) if category == 'executions' else result)
                return result
            finally:
                if category == 'runs':
                    record['reads_after'] = len(self.records['reads'])
                    record['executions_after'] = len(self.records['executions'])

        setattr(owner, name, observed)

    def __enter__(self):
        for name, category in (
            ('runtime_memory', 'reads'), ('_clock_advance_with_hooks', 'runs'),
            ('keyboard_press', 'presses'), ('keyboard_key_up', 'releases'),
            ('input_cancel_pending', 'cancels'), ('scene_act', 'actions'),
            ('script', 'scripts')):
            self.wrap(self.debug, name, category)
        self.wrap(self.debug.vm.gdb, 'execute', 'executions')
        return self

    def __exit__(self, *exception):
        for owner, name, original in reversed(self.originals):
            setattr(owner, name, original)
        write_json(self.directory, 'scene-act-observer.json', self.records)


def local_boundary(debug, project, observer):
    """Only cached state and local database reads; no QMP/GDB operation."""
    return dict(owner=id(debug.vm), process_object=id(debug.vm.process),
        run=debug.run_id, capture_epoch=debug._runtime_epoch,
        checkpoint_epoch=debug._checkpoint_epoch, process=deepcopy(debug._process),
        input=deepcopy(debug.input_state()), counts={
            name: len(records) for name, records in observer.records.items()},
        observations=project.db.execute('SELECT count(*) FROM debug_scene_observations').fetchone()[0],
        artifacts=project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0])


def invoke_json(debug, project, observer, directory, *, request_id, method,
                parameters, export_name, require_export):
    workspace = DebugWorkspace()
    workspace.sessions[debug.run_id] = debug
    try:
        with output_policy_context(OutputPolicy(max_inline_bytes=4096,
                artifact_dir=directory / 'bounded-outputs')):
            reply = respond(dict(id=request_id, method=method, params=dict(
                project=str(project.path), run=debug.run_id, **parameters)), debugger=workspace)
            write_json(directory, request_id + '-reply.json', reply)
            candidate = reply.get('result') if reply['ok'] else reply.get('output')
            marker = candidate if isinstance(candidate, dict) and candidate.get(
                'format') == 'fdisbull-output-ref-1' else None
            if marker is None:
                assert not require_export, reply
                return reply, None
            assert marker['complete'] is False and marker['retry_safe'] is False
            assert marker['execution']['returned'] is True
            assert marker['execution']['ok'] is reply['ok']
            before = local_boundary(debug, project, observer)
            output = directory / export_name
            exported = respond(dict(id=request_id + '-export', method='output-export',
                params=dict(artifact=marker['artifact']['id'], output=str(output))))
            assert exported['ok'], exported
            raw = output.read_bytes()
            assert len(raw) == marker['artifact']['bytes']
            assert hashlib.sha256(raw).hexdigest() == marker['artifact']['sha256']
            assert local_boundary(debug, project, observer) == before
            return json.loads(raw), dict(path=output.name, bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(), marker=marker, exported=exported)
    finally:
        workspace.sessions.clear()


def state(debug, bound):
    receipt = debug.runtime_memory(bound['id'], offset=0, length=29)
    raw = bytes.fromhex(receipt['hex'])
    assert raw[:4] == b'MV01' and len(raw) == 29
    return dict(receipt=receipt, position=int.from_bytes(raw[4:6], 'little'),
        ticks=int.from_bytes(raw[6:8], 'little'), held=raw[8], settled=raw[9],
        makes=raw[10], breaks=raw[11], count=raw[12], edges=raw[13:29].hex())


def stable_clock(value):
    return value['epoch'], value['virtual_ns'], value['counter']


def artifact(project, identifier):
    row = project.db.execute('SELECT * FROM debug_artifacts WHERE id=?', (identifier,)).fetchone()
    assert row is not None
    result = dict(row)
    result['data'] = bytes(result['data'])
    result['metadata'] = json.loads(result['metadata'])
    assert hashlib.sha256(result['data']).hexdigest() == result['sha256']
    return result


def stored_action(project, scene, result):
    info = project.debug_scene_info(scene['id'])
    assert info == scene
    assert hashlib.sha256(canonical_bytes(info['definition'])).hexdigest() == info['sha256']
    historical = project.debug_scene_observation(result['observation'])
    assert historical['historical'] is True and historical['live_state_verified'] is False
    assert historical['result'] == result
    row = project.db.execute('SELECT * FROM debug_scene_observations WHERE id=?',
                             (result['observation'],)).fetchone()
    document = row['document']
    assert json.loads(document) == {key: value for key, value in result.items() if key != 'observation'}
    raw = document.encode()
    assert len(raw) == result['action_wait']['evidence_bytes']
    assert len(raw) <= result['action_wait']['evidence_limit_bytes']
    return dict(scene=info, observation=historical, document_bytes=len(raw),
                document_sha256=hashlib.sha256(raw).hexdigest())


def stored_script(project, saved, declaration, result):
    raw = canonical_bytes(declaration)
    row = project.db.execute('SELECT * FROM debug_scripts WHERE id=?', (saved['script_id'],)).fetchone()
    assert row is not None and row['script'].encode() == raw
    assert row['sha256'] == saved['sha256'] == hashlib.sha256(raw).hexdigest()
    assert row['version'] == saved['version']
    route = artifact(project, result['script_artifact'])
    report = artifact(project, result['artifact'])
    assert route['kind'] == 'script' and route['data'] == raw
    assert route['sha256'] == result['script_sha256'] == saved['sha256']
    assert report['kind'] == 'script-result'
    assert json.loads(report['data']) == {key: value for key, value in result.items() if key != 'artifact'}
    return dict(saved=dict(row), route=dict(id=route['id'], sha256=route['sha256'], size=len(raw)),
        report=dict(id=report['id'], sha256=report['sha256'], size=len(report['data'])))


def common_result(debug, scene, result, action_call):
    assert result['format'] == 'fdisbull-scene-action-1'
    assert result['scene_revision'] == scene['id'] and result['manifest_sha256'] == scene['sha256']
    assert result['source_identity'] == scene['definition']['source_identity']
    obj = scene['definition']['objects'][0]
    assert result['object_id'] == obj['id'] and result['run'] == debug.run_id
    assert result['attempt_id'] == result['intention']['id']
    assert result['intention']['consumed'] is True and result['intention']['replay'] is False
    plan = result['plan']
    assert plan['format'] == 'fdisbull-scene-action-plan-1'
    for key in ('scene_revision', 'manifest_sha256', 'object_id', 'source_identity'):
        assert plan[key] == result[key]
    assert plan['press'] == PRESS
    assert plan['action_sha256'] == hashlib.sha256(canonical_bytes(PRESS)).hexdigest()
    assert obj['guest_ms'] == GUEST_MS and obj['timeout_ms'] == ACTION_MS
    resolved_timeout_ms = action_call['kwargs']['timeout_ms']
    assert type(resolved_timeout_ms) is int and 0 < resolved_timeout_ms <= ACTION_MS
    assert plan['guest_ms'] == GUEST_MS
    assert plan['timeout_ms'] == min(obj['timeout_ms'], resolved_timeout_ms)
    assert plan['sha256'] == hashlib.sha256(canonical_bytes(
        {key: value for key, value in plan.items() if key != 'sha256'})).hexdigest()
    assert result['input']['device_queue_accepted'] is None
    assert result['input']['guest_consumed'] is None
    assert result['effect']['phase'] == 'state'
    assert result['before']['capture_context_verified'] is True
    assert result['before']['observation_context']['capture_epoch'] == debug._runtime_epoch
    assert 'frame' not in result and 'frame' not in result['before']
    budget = result['action_wait']
    assert budget['clock_domain'] == 'QEMU_CLOCK_VIRTUAL'
    assert budget['requested_guest_ms'] == GUEST_MS
    assert budget['requested_virtual_ns'] == GUEST_MS * 1_000_000
    assert budget['guest_elapsed_ms'] == budget['guest_elapsed_ns'] / 1_000_000
    return budget


def delivered_press(arm, delivery, *, complete):
    assert arm['state'] == arm['native']['state'] == 'armed'
    assert arm['native']['press']['dispatched-count'] == 0
    assert arm['guest_consumed'] is arm['device_queue_accepted'] is None
    for key in ('token', 'run', 'epoch', 'session_id', 'start_ns', 'deadline_ns', 'sequences', 'edge_count'):
        assert delivery[key] == arm[key]
    assert delivery['guest_consumed'] is delivery['device_queue_accepted'] is None
    assert delivery['native']['epoch'] == arm['native']['epoch']
    expected_count = 2 if complete else 1
    assert delivery['state'] == delivery['native']['state'] == ('dispatched' if complete else 'cancelled')
    assert delivery['requires_resolution'] is (not complete)
    native = delivery['native']['press']
    assert native['key'] == 'a' and native['modifiers'] == []
    assert native['hold-ms'] == native['gap-ms'] == 80
    assert native['dispatched-count'] == expected_count and len(native['steps']) == 2
    make, release = native['steps']
    assert {key: make[key] for key in ('key', 'down', 'delay-ns')} == dict(
        key='a', down=True, **{'delay-ns': 2_000_000})
    assert {key: release[key] for key in ('key', 'down', 'delay-ns')} == dict(
        key='a', down=False, **{'delay-ns': 80_000_000})
    assert make['deadline-ns'] == arm['start_ns'] + 2_000_000
    assert make['dispatch-ns'] >= make['deadline-ns']
    assert release['deadline-ns'] == make['dispatch-ns'] + 80_000_000
    if complete:
        assert release['dispatch-ns'] >= release['deadline-ns']
        assert delivery['dispatch_ns'] == delivery['terminal_ns'] == release['dispatch-ns']
    else:
        assert 'dispatch-ns' not in release and delivery['dispatch_ns'] is None
        assert make['dispatch-ns'] <= delivery['terminal_ns'] < release['deadline-ns']
    return arm['press']['steps'][0]['lease']


def assert_public_run_addresses(canonical, projected):
    assert projected == public_addresses(canonical)
    assert canonical['action_wait']['runs']
    for original, public in zip(canonical['action_wait']['runs'],
                                projected['action_wait']['runs'], strict=True):
        for field in ('start', 'end'):
            address = original['process']['allocation'][field]
            assert type(address) is int
            assert public['process']['allocation'][field] == hex(address)
        headers = original['process']['drivers']['headers']
        assert headers
        for header, public_header in zip(headers, public['process']['drivers']['headers'], strict=True):
            assert type(header['address']) is int
            assert public_header['address'] == hex(header['address'])


def test_native_named_action_saved_script_consumption_and_effect(tmp_path, clock_runtime, clock_disk):
    with launch(tmp_path, clock_runtime, clock_disk) as fixture:
        project, debug = fixture['project'], fixture['debug']
        scene = project.debug_save_scene('named-action', definition())
        declaration = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
            dict(op='scene-act', **action_options(scene['id']), **{'as': 'acted'}),
            dict(op='assert', value='$acted.complete', equals=True),
            dict(op='assert', value='$acted.effect.matched', equals=True),
            dict(op='assert', value='$acted.input.completed', equals=True)])
        saved = project.debug_save_script('named-action.json', declaration)
        initial = state(debug, fixture['bound'])
        assert initial['position'] == initial['held'] == initial['makes'] == initial['breaks'] == initial['count'] == 0
        before_clock = debug.clock_observe()
        initial_owner, initial_epoch = debug.vm, debug._runtime_epoch
        with Observer(debug, tmp_path) as observed:
            document, exported = invoke_json(debug, project, observed, tmp_path,
                request_id='scene-act-script', method='debug-script', parameters=dict(
                    script_id=saved['script_id'], timeout_ms=remaining(fixture['deadline'], 7000)),
                export_name='script-public-export.json', require_export=True)
            assert len(observed.records['scripts']) == len(observed.records['actions']) == 1
            script = observed.records['scripts'][0]['result']
            result = observed.records['actions'][0]['result']
            write_json(tmp_path, 'canonical-script-result.json', script)
            write_json(tmp_path, 'canonical-action-result.json', result)
            assert document == dict(id='scene-act-script', ok=True, result=public_addresses(script))
            assert script['ok'] is True and script['error'] is None
            assert script['requested_steps'] == script['completed_steps'] == len(declaration['steps']) == 4
            assert len(script['steps']) == 4 and all(step['ok'] for step in script['steps'])
            assert script['steps'][0]['result'] == result
            assert_public_run_addresses(result, document['result']['steps'][0]['result'])
            budget = common_result(debug, scene, result, observed.records['actions'][0])
            assert result['status'] == 'matched' and result['complete'] is True
            assert result['before']['status'] == 'matched'
            assert result['before']['initial_outcome'] is False
            assert result['effect']['matched'] is True and result['effect']['observation'] is not None
            assert result['effect']['observation']['outcome'] is True
            assert result['effect']['observation']['capture_context_verified'] is True
            assert 'frame' not in result['effect']['observation']
            assert result['input']['attempted'] is result['input']['accepted'] is result['input']['completed'] is True
            assert len(observed.records['presses']) == 1
            arm = observed.records['presses'][0]['result']
            assert result['input']['arm'] == arm
            delivered_press(arm, result['input']['delivery'], complete=True)
            assert budget['runs'] == [entry['result'] for entry in observed.records['runs']]
            assert 1 <= len(budget['runs']) == len(observed.records['executions']) <= 20
            assert budget['polls'] and budget['stop'] is None
            assert budget['clock_progress_complete'] is True
            assert not observed.records['releases'] and not observed.records['cancels']
            after_clock = debug.clock_observe()
            assert after_clock['epoch'] == before_clock['epoch']
            assert 0 < budget['guest_elapsed_ns'] == after_clock['virtual_ns'] - before_clock['virtual_ns'] <= 500_000_000
            final = state(debug, fixture['bound'])
            assert final['position'] > 0 and final['held'] == 0
            assert final['makes'] == final['breaks'] == 1 and final['count'] == 2
            assert final['edges'] == '1e9e' + '00' * 14
            assert debug.input_state()['pending_edges'] == 0 and debug.input_state()['leases'] == {}
            assert debug.vm is initial_owner and debug._runtime_epoch == initial_epoch
            assert not debug.closed and initial_owner.process.poll() is None
            persisted = dict(action=stored_action(project, scene, result),
                             script=stored_script(project, saved, declaration, script))
            witness = dict(format='fdisbull-native-scene-action-witness-1', case='saved-script-success',
                source_sha256=fixture['source_hash'], boot_sha256=fixture['boot_hash'],
                baseline_sha256=fixture['baseline_hash'], run=debug.run_id,
                owner=dict(pid=initial_owner.process.pid, capture_epoch=initial_epoch),
                scene=scene, script=saved, initial=initial, final=final,
                before_clock=before_clock, after_clock=after_clock, exported=exported,
                action_observation=result['observation'], setup=fixture['setup'])
    with Project(tmp_path / 'action.fdb') as reopened:
        assert dict(action=stored_action(reopened, scene, result),
                    script=stored_script(reopened, saved, declaration, script)) == persisted
    remaining(fixture['case_deadline'], 1)
    witness['owner'].update(returncode=initial_owner.process.poll(), reaped=True)
    witness['cold_reopen_verified'] = True
    write_json(tmp_path, 'scene-act-persistence.json', persisted)
    write_json(tmp_path, 'scene-act-witness.json', witness)


def test_native_named_action_json_refusal_and_first_stop(tmp_path, clock_runtime, clock_disk):
    with launch(tmp_path, clock_runtime, clock_disk) as fixture:
        project, debug = fixture['project'], fixture['debug']
        blocked = project.debug_save_scene('not-ready', definition(blocked=True))
        scene = project.debug_save_scene('named-action', definition())
        initial = state(debug, fixture['bound'])
        assert initial['position'] == initial['held'] == initial['makes'] == initial['breaks'] == initial['count'] == 0
        owner, epoch = debug.vm, debug._runtime_epoch
        with Observer(debug, tmp_path) as observed:
            clock_before = debug.clock_observe()
            input_before, owned_before = deepcopy(debug.input_state()), deepcopy(debug._input_storage())
            process_before = deepcopy(debug._process)
            refusal, refusal_export = invoke_json(debug, project, observed, tmp_path,
                request_id='scene-act-not-ready', method='debug-scene-act',
                parameters=action_options(blocked['id']), export_name='readiness-refusal-export.json',
                require_export=False)
            assert len(observed.records['actions']) == 1
            refused_error = observed.records['actions'][0]['error']
            refused = refused_error['result']
            write_json(tmp_path, 'canonical-readiness-refusal.json', refused)
            assert refusal == dict(id='scene-act-not-ready', ok=False, error=refused_error)
            common_result(debug, blocked, refused, observed.records['actions'][0])
            assert not refused['complete'] and refused['before']['availability']['ready'] is False
            assert refused['input']['attempted'] is False and refused['input']['accepted'] is False
            assert refused['input']['arm'] is None and refused['input']['delivery'] is None
            assert refused['effect']['matched'] is None and refused['effect']['observation'] is None
            assert not refused['action_wait']['runs'] and refused['action_wait']['guest_elapsed_ns'] == 0
            assert not observed.records['presses'] and not observed.records['executions'] and not observed.records['runs']
            assert not observed.records['releases'] and not observed.records['cancels']
            assert stable_clock(debug.clock_observe()) == stable_clock(clock_before)
            assert debug.input_state() == input_before and debug._input_storage() == owned_before
            assert debug._process == process_before
            assert state(debug, fixture['bound'])['receipt']['hex'] == initial['receipt']['hex']
            refusal_persisted = stored_action(project, blocked, refused)

            point = debug.breakpoint(fixture['address']('irq_fence'))
            interrupted, stop_export = invoke_json(debug, project, observed, tmp_path,
                request_id='scene-act-first-stop', method='debug-scene-act',
                parameters=action_options(scene['id']), export_name='interrupted-action-export.json',
                require_export=True)
            assert len(observed.records['actions']) == 2
            stopped_error = observed.records['actions'][1]['error']
            result = stopped_error['result']
            write_json(tmp_path, 'canonical-interrupted-action.json', result)
            assert interrupted == dict(id='scene-act-first-stop', ok=False, error=stopped_error)
            budget = common_result(debug, scene, result, observed.records['actions'][1])
            assert result['attempt_id'] != refused['attempt_id']
            assert result['status'] == 'stopped' and result['complete'] is False
            assert result['before']['status'] == 'matched' and result['before']['initial_outcome'] is False
            assert result['input']['attempted'] is result['input']['accepted'] is True
            assert result['input']['completed'] is False
            assert result['effect']['matched'] is None and result['effect']['observation'] is None
            assert len(observed.records['presses']) == len(observed.records['runs']) == len(observed.records['executions']) == 1
            boundary = observed.records['runs'][0]
            assert budget['runs'] == [boundary['result']]
            assert budget['stop'] == boundary['result'] and budget['stop']['outcome'] == 'breakpoint'
            assert budget['clock_progress_complete'] is True
            assert 0 < budget['guest_elapsed_ns'] == budget['stop']['clock_budget']['elapsed_ns'] < 500_000_000
            assert point['breakpoint_id'] in budget['stop']['session']['stop_reason']['breakpoint_ids']
            assert int(budget['stop']['registers']['linear_pc'], 16) == fixture['address']('irq_fence')
            # Establish the action's no-post-stop-read claim before the separate
            # caller inspection below. Export and persistence reads are local.
            assert len(observed.records['reads']) == boundary['reads_after']
            assert not budget['polls']
            assert not observed.records['releases'] and not observed.records['cancels']
            assert result['input']['arm'] == observed.records['presses'][0]['result']
            assert result['input']['delivery'] == budget['stop']['input_delivery']
            lease = delivered_press(result['input']['arm'], result['input']['delivery'], complete=False)
            pending = deepcopy(debug.input_state())
            assert pending['pending_edges'] == 1 and len(pending['pending']) == 1
            assert pending['leases'][lease]['make'] == 'native_dispatched'
            assert pending['leases'][lease]['release'] == 'python_pending'
            assert pending['pending'][0]['sequence'] == result['input']['arm']['sequences'][1]
            assert debug.vm is owner and debug._runtime_epoch == epoch
            assert not debug.closed and owner.process.poll() is None
            caller_read = state(debug, fixture['bound'])
            assert caller_read['makes'] == caller_read['count'] == caller_read['held'] == 1
            assert caller_read['breaks'] == caller_read['position'] == 0
            assert caller_read['edges'] == '1e' + '00' * 15
            assert len(observed.records['executions']) == len(observed.records['runs']) == 1
            assert debug.input_state() == pending
            stopped_persisted = stored_action(project, scene, result)
            persisted = dict(refusal=refusal_persisted, stopped=stopped_persisted)
            witness = dict(format='fdisbull-native-scene-action-witness-1', case='json-refusal-and-first-stop',
                source_sha256=fixture['source_hash'], boot_sha256=fixture['boot_hash'],
                baseline_sha256=fixture['baseline_hash'], run=debug.run_id,
                owner=dict(pid=owner.process.pid, capture_epoch=epoch), initial=initial,
                blocked_scene=blocked, scene=scene, readiness_clock=clock_before,
                input_before_refusal=input_before, owned_before_refusal=owned_before,
                breakpoint=point, stop=budget['stop'], pending_after_stop=pending,
                caller_post_stop_read=caller_read, caller_read_is_action_effect=False,
                action_reads_at_stop=boundary['reads_after'],
                observations=[refused['observation'], result['observation']],
                refusal_export=refusal_export, stop_export=stop_export, setup=fixture['setup'])
    with Project(tmp_path / 'action.fdb') as reopened:
        assert dict(refusal=stored_action(reopened, blocked, refused),
                    stopped=stored_action(reopened, scene, result)) == persisted
    remaining(fixture['case_deadline'], 1)
    witness['owner'].update(returncode=owner.process.poll(), reaped=True)
    witness['cold_reopen_verified'] = True
    write_json(tmp_path, 'scene-act-persistence.json', persisted)
    write_json(tmp_path, 'scene-act-witness.json', witness)
