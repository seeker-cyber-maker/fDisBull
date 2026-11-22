"""Source-raster timeline over real history artifacts and authored native receipts."""
from base64 import b64decode, b64encode
from copy import deepcopy
from hashlib import sha256
import io
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from fdisbull.cli import respond
from fdisbull.debug_script import execute_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_dos_checkpoint import FORMAT as CHECKPOINT_FORMAT, _archive, _unarchive
from fdisbull.qemu_frame_contract import FRAME_SOURCE
from fdisbull.qemu_frame_keys import adopt_frame_keys
from fdisbull.qemu_instrumented_checkpoint import COMMANDS
from fdisbull.qemu_source_timeline import source_raster_record
from fdisbull.qemu_video_control import FORMAT as ADVANCE_FORMAT
from fdisbull.screenshot_codecs import RGBAFrame
from test_qemu_dos_frames import frames
from test_qemu_dos_history import project, session
from test_qemu_frame_keys import keys
from test_qemu_observation_cleanup import Process
from test_qemu_video_checkpoint import envelope, make_state, rebind, source_record


IMPORT = 'x-fdisbull-instrumented-checkpoint-import'
SOURCE_OPTIONS = dict(frame_source='source-raster', max_frames=8, max_bytes=8*1024**2,
                      max_state_bytes=1024**2, max_image_bytes=4096)


def _successor(record):
    """Finish the pending authored raster and retain the next partial prefix."""
    value = deepcopy(record)
    info = value['info']
    frame = info['frame']
    period = frame['period-ns']
    info['frame-sequence'] += 1
    frame['frame-id'] += 1
    for field in ('virtual-ns', 'next-deadline-ns'):
        info[field] += period
    for field in ('frame-start-ns', 'first-sample-ns', 'last-sample-ns', 'completed-ns'):
        frame[field] += period
    for row in (*frame['rows'], *value['partial-rows']):
        row['intended-ns'] += period
        row['actual-ns'] += period
    value['frame-start-ns'] += period
    value['timer-expire-ns'] += period
    prefix = b64decode(record['partial-rgb-base64'])
    rgb = prefix + bytes([35, 48, 62]) * (320 * 200 - len(prefix) // 3)
    value['rgb-base64'] = b64encode(rgb).decode()
    frame['pixel-sha256'] = sha256(rgb).hexdigest()
    return value


def _authored_raster(**options):
    record = source_record(**options)
    info = record['info']
    frame = info.get('frame', {})
    # Keep the exact relative row/deadline timing of the fixture at a native
    # timeline cadence of 16 ms, within the persisted delta schema's bounds.
    for fields in (record, info, frame, *frame.get('rows', []), *record['partial-rows']):
        for name, value in fields.items():
            if name.endswith('-ns') and value >= 0:
                fields[name] = value * 5000
    return record


@pytest.fixture
def source_timeline(keys, monkeypatch):
    debug = keys
    debug.capabilities = {'frame_step': True, 'rewind': True, 'source_raster_timeline': True}
    debug.vm.qmp_commands |= COMMANDS | {'query-qmp-schema', 'x-fdisbull-query-video-frame'}
    debug.vm.machine_configuration['retrace_profile'] = {'profile': 'precise'}
    debug.source = _authored_raster()
    debug.source_calls = []
    debug.source_schema = True
    debug.source_interrupted = False
    debug.alter_restore = lambda source: None
    qmp_call = debug.vm.qmp.call

    def call(command, arguments=None, **kwargs):
        if command == 'query-qmp-schema':
            debug.source_calls.append(('schema',))
            members = [{'name': 'video-frame-generation'}]
            if debug.source_schema:
                members.append({'name': 'video-frame-token'})
            return [
                {'name': IMPORT, 'meta-type': 'command', 'ret-type': 'format3-result'},
                {'name': 'format3-result', 'meta-type': 'object', 'members': members},
            ]
        if command == 'x-fdisbull-apply-frame-key-edges':
            debug.source_calls.append(('apply', deepcopy(arguments['edges'])))
        return qmp_call(command, arguments, **kwargs)

    def observe(*, timeout_ms=1000):
        debug.source_calls.append(('observe',))
        info = deepcopy(debug.source['info'])
        frame = info.get('frame')
        return dict(native=info, frame=frame, stream=info.get('token'), epoch=info['epoch'],
                    state=info['state'], frame_id=frame['frame-id'] if frame else None,
                    completed_source_raster=frame is not None)

    def advance(*, timeout_ms=5000, stop_on_hook=True):
        assert stop_on_hook is True
        before = deepcopy(debug.source['info'])
        debug.source_calls.append(('advance', before['token'], before['rows-sampled']))
        if not debug.source_interrupted:
            debug.source = _successor(debug.source)
            debug.pc += 1
        after = deepcopy(debug.source['info'])
        kind = 'breakpoint' if debug.source_interrupted else 'stopped'
        result = dict(outcome='hook' if debug.source_interrupted else 'stopped',
                      timed_out=False, hook_hits=[{'hook': 'h'}] if debug.source_interrupted else [],
                      session=dict(state='stopped', stop_reason=dict(kind=kind, breakpoint_ids=[],
                          native_reply='T05' if debug.source_interrupted else 'T02')))
        fence = {'state': 'cancelled' if debug.source_interrupted else 'completed'}
        return dict(format=ADVANCE_FORMAT, advance_completed=not debug.source_interrupted,
                    native_result=result, owner_exited=False,
                    completed_source_raster=not debug.source_interrupted,
                    stop_consumed=not debug.source_interrupted,
                    source=dict(before=before, after=after),
                    clocks=dict(before=dict(virtual_ns=before['virtual-ns']),
                                after=dict(virtual_ns=after['virtual-ns'])),
                    fence=dict(arm={'baseline-rows-sampled': before['rows-sampled']},
                               observed=fence, released=fence),
                    frame=None if debug.source_interrupted else after['frame'])

    def selected(stream, frame_id):
        info = deepcopy(debug.source['info'])
        frame = info['frame']
        if stream is not None:
            assert stream == info['token']
        if frame_id is not None:
            assert frame_id == frame['frame-id']
        rgb = b64decode(debug.source['rgb-base64'])
        assert sha256(rgb).hexdigest() == frame['pixel-sha256']
        return rgb, dict(source=FRAME_SOURCE, stream=info['token'], epoch=info['epoch'],
                         frame_id=frame['frame-id'], native=info, frame=frame,
                         pixel_sha256=frame['pixel-sha256'], width=320, height=200)

    def capture(name, *, stream=None, frame_id=None, timeout_ms=1000, max_bytes=None):
        debug.source_calls.append(('capture',))
        rgb, metadata = selected(stream, frame_id)
        output = io.BytesIO()
        Image.frombytes('RGB', (320, 200), rgb).save(output, format='PNG')
        data = output.getvalue()
        if max_bytes is not None and len(data) > max_bytes:
            raise ValueError('PNG exceeds image byte budget')
        return debug._artifact(name, 'screenshot', data, metadata)

    def rgba(*, encoding, timeout_ms=1000):
        assert encoding == 'png'
        debug.source_calls.append(('readback',))
        rgb, metadata = selected(None, None)
        with Image.frombytes('RGB', (320, 200), rgb) as image:
            data = image.convert('RGBA').tobytes()
        return RGBAFrame(320, 200, data, sha256(data).hexdigest(), metadata)

    def capture_state(owner, name, max_bytes):
        assert owner is debug
        info = debug.source['info']
        state = make_state(debug.source)
        rebind(state, epoch=info['epoch'])
        state['video-frame'] = deepcopy(debug.source)
        key_state = state['frame-keys']
        key_state.update({key: deepcopy(debug.key_state[key])
                          for key in key_state.keys() - {'source-epoch'}})
        bundle = dict(format=CHECKPOINT_FORMAT, instrumentation=envelope(state))
        machine = json.dumps(dict(pc=debug.pc, keys=debug.key_state)).encode()
        payload = _archive(machine, bundle)
        assert len(payload) <= max_bytes
        metadata = dict(format=CHECKPOINT_FORMAT, host_files_restored=False,
                        source_sha256=debug.metadata['source_sha256'],
                        version_sha256=debug.metadata['version_sha256'],
                        sidecar_sha256=sha256(json.dumps(bundle, sort_keys=True,
                            separators=(',', ':'), allow_nan=False).encode('ascii')).hexdigest())
        if info.get('frame') and info['state'] == 'observing':
            metadata['source_raster'] = source_raster_record(info)
        debug.source_calls.append(('save', info['frame-sequence']))
        return dict(name=name, kind='state', data=payload, metadata=metadata,
                    size=len(payload), sha256=sha256(payload).hexdigest())

    def save(name, *, max_bytes=None):
        record = capture_state(debug, name, max_bytes)
        return debug._artifact(name, 'state', record['data'], record['metadata'])

    def load_data(data, artifact):
        debug.source_calls.append(('load', artifact))
        machine, bundle = _unarchive(data)
        saved = json.loads(machine)
        debug.pc = saved['pc']
        debug.key_state.clear()
        debug.key_state.update(saved['keys'])
        debug.source = json.loads(bundle['instrumentation']['state'])['video-frame']
        info = debug.source['info']
        info['token'] = 'new-source-owner'
        info['epoch'] += 1
        info['frame']['epoch'] = info['epoch']
        debug.key_state['epoch'] = info['epoch']
        if debug.key_state['active']:
            debug.key_state['token'] = 'new-key-owner'
        previous = debug.vm
        debug.vm = SimpleNamespace(**vars(previous))
        debug.vm.process = SimpleNamespace(poll=lambda: None)
        previous.process.poll = lambda: 0
        debug.vm.history_operation_guard = None
        debug.vm.__dict__.pop('session_revision', None)
        debug._history_bind()
        adopt_frame_keys(debug.vm, debug.key_state)
        debug.alter_restore(debug.source)
        return {'source_binding_restored': True}

    def load(artifact, *, timeout_ms=60000):
        data = debug.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                        (artifact,)).fetchone()['data']
        return load_data(bytes(data), artifact)

    debug.vm.qmp.call = call
    debug.video_frame_observe = observe
    debug.video_frame_advance = advance
    debug.capture_video_frame = capture
    debug.frame_rgba = rgba
    debug.save_state = save
    debug.load_state = load
    debug._history_load_prepared = lambda prepared, **kwargs: load_data(prepared['data'], prepared['artifact'])
    monkeypatch.setattr('fdisbull.qemu_dos_checkpoint.capture_process_state', capture_state)
    return debug


def start(debug, **options):
    return debug.timeline_start(**SOURCE_OPTIONS, **options)


def _artifact_count(debug, kind):
    return debug.project.db.execute('SELECT count(*) FROM debug_artifacts WHERE kind=?',
                                    (kind,)).fetchone()[0]


@pytest.mark.parametrize('storage', ['full', 'delta'])
def test_partial_sampling_replays_from_fresh_owner_with_exact_persisted_raster(source_timeline, storage):
    debug = source_timeline
    root = start(debug, storage_mode=storage)
    root_point = root['point']
    historical = root['nodes'][0]['frame']['source_raster']
    assert historical['pixel_sha256'] == sha256(bytes([4, 85, 170]) * (320 * 200)).hexdigest()
    assert (historical['frame_id'], historical['epoch'], historical['stream']) == (23, 1, 'saved-source-owner')
    root_image = debug.timeline_image(point=root_point)
    assert root_image['source_raster'] == historical

    make = dict(frame=0, edges=[dict(key='a', pressed=True)])
    first = debug.timeline_advance(inputs=[make])
    assert first['completed_frames'] == 1 and first['completed_guest_frame'] is None
    first_point = first['point']
    first_frame = first['nodes'][-1]['frame']
    assert first_frame['keys'] == ['a'] and first_frame['kind'] == 'source-raster'
    old_image = debug.timeline_image(point=first_point)
    accepted = debug.key_state['accepted-edges']
    assert accepted == 1
    next_frame = debug.timeline_advance()
    assert next_frame['completed_frames'] == 1
    image_count = _artifact_count(debug, 'screenshot')

    previous = debug.vm
    restored = debug.timeline_rewind(point=first_point)
    assert debug.vm is not previous and previous.process.poll() == 0
    assert restored['point'] == first_point
    # Source continuity is read from the live restored owner, not the cached PNG.
    readback = restored['restore']['frame_readback']
    assert readback['historical'] == first_frame['source_raster']
    assert readback['live']['stream'] == 'new-source-owner'
    assert readback['live']['epoch'] == 2
    assert readback['live']['logical_sha256'] == readback['historical']['logical_sha256']
    assert debug.key_state['accepted-edges'] == accepted and debug.key_state['held'] == ['a']
    assert debug.key_state['token'] == 'new-key-owner'
    assert _artifact_count(debug, 'screenshot') == image_count
    assert debug.timeline_image(point=first_point) == old_image

    replay = debug.timeline_advance()
    assert replay['completed_frames'] == 1 and replay['point'] != next_frame['point']
    assert replay['nodes'][-1]['parent'] == first_point
    record = replay['nodes'][-1]['frame']['source_raster']
    recorded = next_frame['nodes'][-1]['frame']['source_raster']
    assert record['logical_sha256'] == recorded['logical_sha256']
    assert record['pixel_sha256'] == recorded['pixel_sha256']
    assert record['epoch'] != recorded['epoch'] and record['stream'] != recorded['stream']
    assert [call for call in debug.source_calls if call[0] == 'apply'] == [
        ('apply', [dict(key='a', pressed=True)]),
    ]
    assert all(call[2] == 3 for call in debug.source_calls if call[0] == 'advance')
    assert debug.vm.qmp.calls == []  # No renderer fence or fallback.


def test_source_start_requires_format3_and_existing_completed_raster(source_timeline):
    debug = source_timeline
    debug.source_schema = False
    with pytest.raises(ValueError, match='format-3'):
        start(debug)
    assert debug.source_calls == [('schema',)]
    debug.source_schema = True
    debug.source = _authored_raster(complete=False)
    with pytest.raises(ValueError, match='retained raster'):
        start(debug)
    assert _artifact_count(debug, 'rewind-history') == 0 and not debug.closed
    assert {call[0] for call in debug.source_calls} <= {'schema', 'observe'}


def test_replaced_vm_during_source_root_capture_closes_only_captured_owner(source_timeline, monkeypatch):
    debug = source_timeline
    original = debug.vm
    original.process = Process()
    replacement = SimpleNamespace(process=Process())
    capture = debug.capture_video_frame

    def replace_after_capture(*args, **kwargs):
        result = capture(*args, **kwargs)
        debug.vm = replacement
        return result

    monkeypatch.setattr(debug, 'capture_video_frame', replace_after_capture)
    with pytest.raises(DebuggerError, match='original owner') as caught:
        start(debug)

    assert caught.value.frame_input_owner['owner_changed']
    assert debug.vm is replacement and not debug.closed
    assert original.process.terminates == original.process.waits == 1
    assert original.process.stdin.closes == original.process.stdout.closes == 1
    assert replacement.process.terminates == replacement.process.waits == 0
    assert replacement.process.stdin.closes == replacement.process.stdout.closes == 0
    manifest = debug.project.db.execute(
        "SELECT data FROM debug_artifacts WHERE kind='rewind-history' ORDER BY rowid DESC LIMIT 1",
    ).fetchone()
    stored = json.loads(bytes(manifest['data']))
    assert stored['nodes'] == [] and stored['pending']['kind'] == 'source-raster-root'


def test_tampered_png_is_refused_before_source_timeline_restore(source_timeline):
    debug = source_timeline
    root = start(debug)
    image = debug.timeline_image(point=root['point'])
    with debug.project.transaction(True):
        debug.project.db.execute('UPDATE debug_artifacts SET data=? WHERE id=?',
                                 (b'bad image', image['artifact']))
    before = list(debug.source_calls)
    with pytest.raises(ValueError, match='image is missing or corrupt'):
        debug.timeline_rewind(point=root['point'])
    assert not debug.closed
    assert not any(call[0] == 'load' for call in debug.source_calls[len(before):])


@pytest.mark.parametrize(('field', 'message'), [
    ('source_raster', 'checkpoint and source raster identity differ'),
    ('sidecar_sha256', 'checkpoint sidecar hash differs'),
])
def test_checkpoint_with_inconsistent_source_provenance_is_refused_before_restore(
        source_timeline, field, message):
    debug = source_timeline
    root = start(debug)
    node = root['nodes'][0]
    checkpoint = node['checkpoint']['artifact']
    row = debug.project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',
                                   (checkpoint,)).fetchone()
    metadata = json.loads(row['metadata'])
    if field == 'source_raster':
        metadata[field]['logical_sha256'] = '9' * 64
    else:
        metadata[field] = '9' * 64
    with debug.project.transaction(True):
        debug.project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',
                                 (json.dumps(metadata), checkpoint))
    prior = list(debug.source_calls)
    with pytest.raises(ValueError, match=message):
        debug.timeline_rewind(point=root['point'])
    assert debug.source_calls == prior and not debug.closed
    assert debug.timeline_status()['point'] == root['point']


def test_source_timeline_attachment_infers_stored_backend_without_capturing(source_timeline):
    debug = source_timeline
    root = start(debug)
    debug.timeline_stop()
    before = list(debug.source_calls)
    with pytest.raises(ValueError, match='differs from the stored timeline'):
        debug.timeline_start(timeline=root['timeline'], frame_source='renderer')
    attached = debug.timeline_start(timeline=root['timeline'])
    assert attached['frame_source'] == 'source-raster'
    assert not attached['valid'] and attached['point'] is None
    assert not any(call[0] in ('advance', 'save', 'capture', 'apply')
                   for call in debug.source_calls[len(before):])
    assert debug.timeline_image(point=root['point'])['stored_frame']


def test_live_phase_drift_refuses_before_input_or_history_intent(source_timeline):
    debug = source_timeline
    root = start(debug)
    debug.source['info']['next-deadline-ns'] += 1
    before = list(debug.source_calls)
    manifests = _artifact_count(debug, 'rewind-history')
    make = dict(frame=0, edges=[dict(key='a', pressed=True)])
    with pytest.raises(ValueError, match='does not match the timeline cursor'):
        debug.timeline_advance(inputs=[make])
    assert debug.source_calls[len(before):] == [('observe',)]
    assert _artifact_count(debug, 'rewind-history') == manifests
    assert debug.key_state['held'] == [] and not debug.closed
    assert debug.timeline_status()['point'] == root['point']


def test_changed_restored_sampling_phase_cannot_publish_a_successful_cursor(source_timeline):
    debug = source_timeline
    root = start(debug)
    first = debug.timeline_advance()
    def alter_phase(value):
        value['info']['next-deadline-ns'] += 1
    debug.alter_restore = alter_phase
    with pytest.raises((DebuggerError, ValueError), match='[Ss]ource|[Rr]aster'):
        debug.timeline_rewind(point=root['point'])
    assert debug.closed
    assert len([call for call in debug.source_calls if call[0] == 'load']) == 1
    persisted = debug._frame_manifest(first['timeline'])
    assert persisted['pending']['kind'] == 'restore' and persisted['cursor'] == first['point']


def test_source_timeline_hook_stop_retains_existing_history_and_creates_no_node(source_timeline):
    debug = source_timeline
    root = start(debug)
    debug.source_interrupted = True
    result = debug.timeline_advance(frames=2)
    assert result['outcome'] == 'interrupted' and result['completed_frames'] == 0
    assert result['retained_nodes'] == 1 and result['nodes'][0]['id'] == root['point']
    assert not result['valid'] and not debug.closed
    assert result['stop']['outcome'] == 'hook'
    assert _artifact_count(debug, 'screenshot') == 1


def test_public_json_and_saved_script_replay_source_only_profile(source_timeline):
    debug = source_timeline
    workspace = DebugWorkspace()
    workspace.sessions[debug.run_id] = debug
    params = dict(project=str(debug.project.path), run=debug.run_id)
    reply = respond(dict(method='debug-timeline-start', params=dict(params, **SOURCE_OPTIONS)),
                    debugger=workspace)
    assert reply['ok'], reply
    point = reply['result']['point']
    assert reply['result']['frame_source'] == 'source-raster'
    script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=[
        {'op': 'timeline-start', 'timeline': reply['result']['timeline'],
         'frame_source': 'source-raster', 'as': 'root'},
        {'op': 'timeline-advance', 'frames': 1},
        {'op': 'timeline-rewind', 'timeline': '$root.timeline', 'point': '$root.point'},
    ])
    report = execute_script(debug, script, timeout_ms=10000)
    assert report['ok'] and report['completed_steps'] == 3, report
    restored = report['steps'][-1]['result']
    assert restored['point'] == point and restored['restore']['frame_readback']['live']['epoch'] == 2
    image = respond(dict(method='debug-timeline-image', params=dict(params, point=point)), debugger=workspace)
    assert image['ok'] and image['result']['source_raster']['epoch'] == 1, image
