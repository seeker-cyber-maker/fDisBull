"""Adapter contracts at the fDisBull/native boundary; no GUI qualification."""
import base64
from contextlib import nullcontext
import hashlib
import threading
from types import SimpleNamespace

import pytest

from dotbox import backend


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


class Session:
    run_id = 'retained-run'
    session_id = 'native-session'

    def __init__(self):
        self.rpc = SimpleNamespace(capabilities={'input': {'cooperative_control': 'dotbox-input-control-1'}})
        self.calls = []
        self.state = 'stopped'
        self.owner = 'agent'
        self.generation = 0
        self.closed = False
        self.pause_race = False
        self.wait_running = False
        self.last_stop = {'kind': 'startup'}

    def call(self, method, params=None):
        params = params or {}
        self.calls.append((method, params))
        if method == 'session.status':
            return {'state': self.state, 'state_revision': 1, 'last_stop': self.last_stop}
        if method == 'input.control':
            if params:
                assert params['expected_generation'] == self.generation
                self.owner = params['owner']
                self.generation += 1
            return {'state': self.state, 'owner': self.owner, 'generation': self.generation}
        if method == 'execution.continue':
            self.state = 'running'
            return {'state': self.state, 'operation_id': 'continue-1'}
        if method == 'execution.pause':
            if self.pause_race:
                self.state = 'stopped'
                raise ValueError('Target is not running (TARGET_NOT_RUNNING)')
            return {'operation_id': 'pause-1'}
        if method == 'execution.wait':
            if self.wait_running:
                return {'state': 'running', 'running': True}
            self.state = 'stopped'
            self.last_stop = {'kind': 'breakpoint' if self.pause_race else 'pause'}
            return {'state': self.state, 'running': False,
                    'stop_reason': self.last_stop}
        if method == 'video.screenshot':
            return {'format': 'png', 'png_base64': base64.b64encode(PNG).decode(),
                    'width': 1, 'height': 1, 'sha256': hashlib.sha256(PNG).hexdigest(),
                    'frame_id': 12, 'mode_id': 4, 'state_revision': 1}
        if method.startswith('input.'):
            assert params['control_generation'] == self.generation
            assert self.owner == 'agent'
            return {'accepted': True, 'delivery': 'queued'}
        raise AssertionError(method)

    def close(self):
        self.closed = True


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    session = Session()
    projects = []

    class Store:
        def __init__(self, path, program=None):
            self.path = path
            self.closed = False
            self.meta = {'filename': 'GAME.EXE', 'source_sha256': hashlib.sha256(b'game').hexdigest()}
            projects.append(self)
            if program is not None:
                path.touch()
                self.created = program

        def __exit__(self, *args):
            self.closed = True

    def native_session(executable, game_dir, program, **options):
        projects[-1].launch = (executable, game_dir, program, options)
        return session

    def validate_keyboard(**params):
        if 'text' in params:
            if not isinstance(params['text'], str) or not params['text']:
                raise ValueError('invalid test text')
        elif params.get('key') not in ('enter', 'up'):
            raise ValueError('invalid test key')

    def decode_screenshot(reply):
        raw = base64.b64decode(reply['png_base64'], validate=True)
        assert raw == PNG
        return raw, {key: value for key, value in reply.items() if key != 'png_base64'}

    monkeypatch.setattr(backend, '_load_runtime', lambda: (
        Store, native_session, validate_keyboard, decode_screenshot, lambda *args, **kwargs: nullcontext()))
    game_dir = tmp_path / 'game'
    game_dir.mkdir()
    program = game_dir / 'GAME.EXE'
    program.write_bytes(b'game')
    executable = tmp_path / 'dosbox-agent'
    executable.write_text('test-only')
    executable.chmod(0o700)
    config = {'project': str(tmp_path / 'game.fdb'), 'program': str(program),
              'game_dir': str(game_dir), 'executable': str(executable)}
    return config, session, projects


def test_visible_original_backend_reused_and_control_query_has_no_effect(adapter):
    config, native, projects = adapter
    b = backend.FDisBullBackend(config)
    try:
        assert projects[0].launch[3] == {'window': True, 'source_sha256': hashlib.sha256(b'game').hexdigest()}
        assert projects[0].launch[2].name == 'GAME.EXE'
        first, second = b.status(), b.status()
        assert first == second
        assert first['run_id'] == 'retained-run'
        assert first['native_control'] == {'owner': 'agent', 'generation': 0}
        assert native.generation == 0 and native.state == 'stopped'
    finally:
        b.close()
    assert native.closed and projects[0].closed


@pytest.mark.parametrize('window_scale', [None, 2, 3, 4, 5])
def test_visible_backend_passes_only_explicit_window_scale(adapter, window_scale):
    config, native, projects = adapter
    config['window_scale'] = window_scale
    b = backend.DOSBoxBackend(config)
    try:
        expected = {'window': True, 'source_sha256': hashlib.sha256(b'game').hexdigest()}
        if window_scale is not None:
            expected['window_scale'] = window_scale
        assert projects[0].launch[3] == expected
    finally:
        b.close()
    assert native.closed and projects[0].closed


def test_spectator_only_binary_refused_and_owned_resources_closed(adapter):
    config, native, projects = adapter
    native.rpc.capabilities = {'input': {}}
    with pytest.raises(backend.BackendUnavailable, match='cooperative'):
        backend.FDisBullBackend(config)
    assert native.closed and projects[0].closed


def test_explicit_image_format_mismatch_refused_before_native_launch(adapter):
    config, native, stores = adapter
    config['image'] = 'mz'
    with pytest.raises(ValueError, match='image format'):
        backend.DOSBoxBackend(config)
    assert stores[0].closed and not hasattr(stores[0], 'launch')
    assert not native.calls


def test_transfer_is_native_atomic_and_stale_input_never_dispatched(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        b.play()
        control = b.transfer('host', expected_generation=0)
        assert control == {'owner': 'host', 'generation': 1}
        assert native.state == 'running'
        with pytest.raises(ValueError, match='generation'):
            b.key({'key': 'enter'}, generation=0)
        with pytest.raises(ValueError, match='agent'):
            b.key({'key': 'enter'}, generation=1)
        assert not any(method == 'input.keyboard.press' for method, _ in native.calls)
        b.transfer('agent', expected_generation=1)
        reply = b.key({'key': 'enter', 'modifiers': ['ctrl']}, generation=2)
        assert reply['delivery'] == 'queued'
        assert native.calls[-1] == ('input.keyboard.press', {
            'key': 'enter', 'modifiers': 'ctrl', 'hold_ms': 40, 'gap_ms': 40,
            'control_generation': 2})
    finally:
        b.close()


@pytest.mark.parametrize('change', ['breakpoint', 'generation'])
def test_handoff_resume_reobserves_stop_and_ownership(adapter, monkeypatch, change):
    config, native, _ = adapter
    b = backend.DOSBoxBackend(config)
    b.transfer('host', 0)
    original = native.call

    def changed(method, params=None):
        if method == 'session.status':
            if change == 'breakpoint':
                native.last_stop = {'kind': 'breakpoint'}
            else:
                native.generation += 1
        return original(method, params)

    monkeypatch.setattr(native, 'call', changed)
    try:
        if change == 'generation':
            with pytest.raises(ValueError, match='Ownership changed'):
                b.resume_after_handoff('host', 1)
        else:
            assert b.resume_after_handoff('host', 1)['stop_reason']['kind'] == 'breakpoint'
        assert not any(method == 'execution.continue' for method, _ in native.calls)
    finally:
        b.close()


def test_text_and_click_include_authoritative_generation_and_frame_guard(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        b.type({'text': 'look\n'}, generation=0)
        assert native.calls[-1][1]['control_generation'] == 0
        b.click({'x': 20, 'y': 30, 'mode_id': 4, 'frame_id': 12}, generation=0)
        assert native.calls[-1] == ('input.mouse.click', {
            'x': 20, 'y': 30, 'button': 'left', 'hold_ms': 80,
            'mode_id': 4, 'frame_id': 12, 'control_generation': 0})
    finally:
        b.close()


def test_named_control_rechecks_generation_between_steps_and_preserves_partial_progress(adapter, monkeypatch):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    revision = 'a' * 64
    plan = {'revision': revision, 'name': 'confirm', 'queued_guest_ms': 160,
            'steps': [{'op': 'key', 'params': {'key': 'enter'}},
                      {'op': 'key', 'params': {'key': 'up'}}]}
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: plan))
    original = native.call

    def drift(method, params=None):
        result = original(method, params)
        if method == 'input.keyboard.press':
            native.generation += 1  # Another native controller wins after step one.
        return result

    try:
        b.play()
        monkeypatch.setattr(native, 'call', drift)
        with pytest.raises(ActionInterrupted) as failure:
            b.act({'revision': revision, 'name': 'confirm'}, generation=0)
        progress = failure.value.progress
        assert progress['active_step'] == 1
        assert len(progress['completed_steps']) == 1
        assert progress['completed_steps'][0]['result']['accepted'] is True
        delivered = [params for method, params in native.calls if method == 'input.keyboard.press']
        assert len(delivered) == 1 and delivered[0]['control_generation'] == 0
        assert not native.closed and native.state == 'running'
    finally:
        b.close()


def test_named_control_does_not_queue_input_for_a_stopped_guest(adapter, monkeypatch):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: {
        'revision': 'a' * 64, 'name': 'confirm', 'queued_guest_ms': 80,
        'steps': [{'op': 'key', 'params': {'key': 'enter'}}]}))
    try:
        with pytest.raises(ValueError, match='running guest'):
            b.act({'revision': 'a' * 64, 'name': 'confirm'}, generation=0)
        assert not any(method == 'input.keyboard.press' for method, _ in native.calls)
        assert not native.closed
    finally:
        b.close()


def test_named_control_stops_queuing_after_breakpoint_between_steps(adapter, monkeypatch):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    revision = 'a' * 64
    plan = {'revision': revision, 'name': 'two_inputs', 'queued_guest_ms': 160,
            'steps': [{'op': 'key', 'params': {'key': 'enter'}},
                      {'op': 'key', 'params': {'key': 'up'}}]}
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: plan))
    original = native.call

    def breakpoint_after_input(method, params=None):
        result = original(method, params)
        if method == 'input.keyboard.press':
            native.state = 'stopped'
            native.last_stop = {'kind': 'breakpoint'}
        return result

    try:
        b.play()
        before = len(native.calls)
        monkeypatch.setattr(native, 'call', breakpoint_after_input)
        with pytest.raises(ActionInterrupted) as failure:
            b.act({'revision': revision, 'name': 'two_inputs'}, generation=0)
        progress = failure.value.progress
        assert progress['active_step'] == 1
        assert len(progress['completed_steps']) == 1
        assert progress['completed_steps'][0]['result']['accepted'] is True
        dispatched = [(method, params) for method, params in native.calls[before:]
                      if method == 'input.keyboard.press']
        assert len(dispatched) == 1 and dispatched[0][1]['key'] == 'enter'
        assert not any(method == 'execution.continue' for method, _ in native.calls[before:])
        assert not native.closed and native.state == 'stopped'
        assert native.last_stop == {'kind': 'breakpoint'}
    finally:
        b.close()


def test_authoring_controls_during_human_play_has_no_native_effect(adapter, monkeypatch):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    saved = []
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(
        save=lambda definition, **options: saved.append((definition, options)) or {'revision': 'a' * 64}))
    try:
        b.play()
        b.transfer('host', 0)
        before = list(native.calls)
        assert b.harness_save({'definition': {'test': 'authored'}})['revision'] == 'a' * 64
        assert saved == [({'test': 'authored'}, {'parent': None})]
        assert native.calls == before and native.state == 'running' and native.owner == 'host'
    finally:
        b.close()


@pytest.mark.parametrize('method,params', [
    ('key', {'key': 'enter', 'method': 'memory.write'}),
    ('key', {'key': 'enter', 'hold_ms': True}),
    ('type', {'text': 'hello', 'output': '/tmp/arbitrary'}),
    ('click', {'x': True, 'y': 0, 'mode_id': 4, 'frame_id': 12}),
    ('click', {'x': -1, 'y': 0, 'mode_id': 4, 'frame_id': 12}),
    ('click', {'x': 0, 'y': 0, 'button': 'unknown', 'mode_id': 4, 'frame_id': 12}),
    ('click', {'x': 20, 'y': 30}),
    ('click', {'x': 20, 'y': 30, 'mode_id': 4}),
    ('click', {'x': 20, 'y': 30, 'frame_id': 12}),
])
def test_bad_input_does_not_reach_mutating_rpc_or_close_guest(adapter, method, params):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        with pytest.raises(ValueError):
            getattr(b, method)(params, generation=0)
        assert not native.closed
        assert not any(m in ('input.keyboard.press', 'input.keyboard.type', 'input.mouse.click') for m, _ in native.calls)
    finally:
        b.close()


def test_pause_preserves_breakpoint_winning_the_pause_race(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        b.play()
        native.pause_race = True
        result = b.pause()
        assert result['stop_reason']['kind'] == 'breakpoint'
        assert [method for method, _ in native.calls].count('execution.continue') == 1
    finally:
        b.close()


def test_pause_deadline_closes_owned_guest_without_automatic_resume(adapter):
    config, native, projects = adapter
    b = backend.FDisBullBackend(config)
    b.play()
    native.wait_running = True
    with pytest.raises(TimeoutError, match='pause'):
        b.pause()
    assert native.closed and projects[0].closed


def test_completed_frame_has_no_server_path_or_persistent_artifact_effect(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        b.play()
        reply = b.frame()
        assert base64.b64decode(reply['png_base64']) == PNG
        assert reply['frame_id'] == 12 and reply['mode_id'] == 4
        assert native.state == 'running'
        assert native.calls[-1] == ('video.screenshot', {'encoding': 'png'})
    finally:
        b.close()


def test_existing_project_does_not_reimport_or_launch_a_different_program(adapter):
    config, native, projects = adapter
    from pathlib import Path
    Path(config['project']).touch()
    other = Path(config['game_dir']) / 'OTHER.EXE'
    other.write_bytes(b'other')
    config['program'] = str(other)
    with pytest.raises(ValueError, match='program'):
        backend.FDisBullBackend(config)
    assert projects[0].closed and not hasattr(projects[0], 'created')
    assert not hasattr(projects[0], 'launch')


def test_cross_thread_access_refused_before_backend_call(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    errors = []
    before = list(native.calls)
    def other_thread():
        try:
            b.status()
        except Exception as error:
            errors.append(error)
    worker = threading.Thread(target=other_thread)
    worker.start()
    worker.join(2)
    assert errors and isinstance(errors[0], RuntimeError)
    assert native.calls == before
    b.close()


def test_stale_transfer_has_no_input_reset_or_execution_effect(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        b.play()
        with pytest.raises(ValueError, match='generation'):
            b.transfer('host', expected_generation=1)
        assert native.owner == 'agent' and native.generation == 0
        assert native.state == 'running'
        assert not any(method == 'input.control' and params for method, params in native.calls)
    finally:
        b.close()


def test_exited_guest_is_not_automatically_restarted(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        native.state = 'exited'
        with pytest.raises(ValueError, match='exited'):
            b.play()
        assert b.pause()['state'] == 'exited'
        assert not any(method == 'execution.continue' for method, _ in native.calls)
    finally:
        b.close()


def test_missing_project_requires_explicit_program_before_dependency_loading(adapter, monkeypatch):
    config, _, projects = adapter
    config.pop('program')
    monkeypatch.setattr(backend, '_load_runtime', lambda: pytest.fail('must not load runtime'))
    with pytest.raises(ValueError, match='program'):
        backend.FDisBullBackend(config)
    assert not projects


def test_close_always_closes_project_and_stays_idempotent_after_session_error(adapter):
    config, native, projects = adapter
    b = backend.FDisBullBackend(config)
    calls = []
    def failed_cleanup():
        calls.append('close')
        raise RuntimeError('native cleanup failed')
    native.close = failed_cleanup
    with pytest.raises(RuntimeError, match='cleanup failed'):
        b.close()
    assert projects[0].closed
    b.close()
    assert calls == ['close']


def test_native_last_stop_schema_preserves_breakpoint_across_handoff(adapter):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    try:
        assert b.status()['stop_reason'] == {'kind': 'startup'}
        b.play()
        native.state = 'stopped'
        native.last_stop = {'kind': 'breakpoint', 'breakpoint_id': 'bp-1'}
        assert b.status()['stop_reason'] == native.last_stop
        b.transfer('host', expected_generation=0)
        assert b.status()['stop_reason'] == native.last_stop
        assert b.pause()['stop_reason'] == native.last_stop
        assert [method for method, _ in native.calls].count('execution.continue') == 1
    finally:
        b.close()


def mouse_plan():
    return {'revision': 'a' * 64, 'name': 'choose', 'queued_guest_ms': 80,
            'steps': [{'op': 'click', 'params': {
                'x': 0, 'y': 0, 'width': 1, 'height': 1, 'button': 'left', 'hold_ms': 80}}]}


def test_named_absolute_mouse_pauses_uses_fresh_frame_and_resumes_once(adapter, monkeypatch):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    try:
        b.play()
        before = len(native.calls)
        reply = b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        methods = [m for m, _ in native.calls[before:]]
        assert methods.count('execution.pause') == 1
        assert methods.count('execution.wait') == 1
        assert methods.count('video.screenshot') == 1
        assert methods.count('input.mouse.click') == 1
        assert methods.count('execution.continue') == 1
        assert methods.index('execution.wait') < methods.index('video.screenshot') < methods.index('input.mouse.click') < methods.index('execution.continue')
        assert next(p for m, p in native.calls[before:] if m == 'input.mouse.click') == {
            'x': 0, 'y': 0, 'button': 'left', 'hold_ms': 80,
            'frame_id': 12, 'mode_id': 4, 'control_generation': 0}
        coordination = reply['coordination']
        assert coordination['resume_acknowledged'] is True
        assert coordination['resume_observed'] is False
        assert coordination['status'] == 'resume_acknowledged'
        assert [event['stage'] for event in coordination['events']] == [
            'started', 'pause_requested', 'stopped', 'frame_captured', 'click_acknowledged', 'resume_requested', 'resume_acknowledged']
        times = [event['monotonic_ns'] for event in coordination['events']]
        assert times == sorted(times)
        assert reply['transition_verified'] is False and native.state == 'running'
    finally:
        b.close()


@pytest.mark.parametrize('change', [
    {'width': 2}, {'height': 2},
])
def test_named_mouse_size_mismatch_leaves_paused_without_input_or_resume(adapter, monkeypatch, change):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    plan = mouse_plan()
    plan['steps'][0]['params'].update(change)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: plan))
    try:
        b.play()
        before = len(native.calls)
        with pytest.raises(ActionInterrupted, match='dimensions') as failure:
            b.act({'revision': plan['revision'], 'name': plan['name']}, generation=0)
        assert failure.value.progress['completed_steps'] == []
        assert failure.value.progress['coordination']['resume_acknowledged'] is False
        assert native.state == 'stopped' and not native.closed
        assert not any(m in ('input.mouse.click', 'execution.continue') for m, _ in native.calls[before:])
    finally:
        b.close()


@pytest.mark.parametrize('owner,generation', [('host', 0), ('agent', 1)])
def test_named_mouse_requires_current_agent_before_any_pause_or_input(adapter, monkeypatch, owner, generation):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    try:
        b.play()
        native.owner = owner
        before = len(native.calls)
        with pytest.raises(ValueError):
            b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=generation)
        assert native.state == 'running'
        assert not any(m in ('execution.pause', 'execution.continue', 'input.mouse.click') for m, _ in native.calls[before:])
    finally:
        b.close()


@pytest.mark.parametrize('mutation', ['breakpoint', 'exited', 'ownership'])
@pytest.mark.parametrize('after_method', ['execution.wait', 'video.screenshot', 'input.mouse.click'])
def test_named_mouse_preserves_unexpected_stop_or_ownership_without_resume(adapter, monkeypatch, mutation, after_method):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    original = native.call

    def changed(method, params=None):
        result = original(method, params)
        if method == after_method:
            if mutation == 'ownership':
                native.owner = 'host'
                native.generation += 1
            else:
                native.state = 'stopped' if mutation == 'breakpoint' else 'exited'
                native.last_stop = {'kind': mutation}
        return result

    try:
        b.play()
        before = len(native.calls)
        monkeypatch.setattr(native, 'call', changed)
        with pytest.raises(ActionInterrupted) as failure:
            b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        progress = failure.value.progress
        click_count = sum(m == 'input.mouse.click' for m, _ in native.calls[before:])
        assert click_count == (1 if after_method == 'input.mouse.click' else 0)
        assert len(progress['completed_steps']) == click_count
        assert progress['coordination']['resume_acknowledged'] is False
        assert not any(m == 'execution.continue' for m, _ in native.calls[before:])
        assert not native.closed
        if mutation == 'ownership':
            assert native.owner == 'host'
        else:
            assert native.last_stop == {'kind': mutation}
    finally:
        b.close()


def test_named_mouse_breakpoint_winning_pause_is_preserved(adapter, monkeypatch):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    try:
        b.play()
        native.pause_race = True
        before = len(native.calls)
        with pytest.raises(ActionInterrupted, match='Breakpoint or exit'):
            b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        assert native.last_stop == {'kind': 'breakpoint'}
        assert not any(m in ('video.screenshot', 'input.mouse.click', 'execution.continue') for m, _ in native.calls[before:])
    finally:
        b.close()


@pytest.mark.parametrize('failure_method', ['input.mouse.click', 'execution.continue'])
def test_named_mouse_ambiguous_rpc_is_not_replayed_or_resumed(adapter, monkeypatch, failure_method):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    original = native.call

    def lost_ack(method, params=None):
        result = original(method, params)
        if method == failure_method:
            raise TimeoutError('transport lost after dispatch')
        return result

    try:
        b.play()
        before = len(native.calls)
        monkeypatch.setattr(native, 'call', lost_ack)
        with pytest.raises(ActionInterrupted, match='transport lost') as failure:
            b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        progress = failure.value.progress
        assert 'unknown' in progress['outcome']
        assert len(progress['completed_steps']) == (1 if failure_method == 'execution.continue' else 0)
        assert progress['coordination']['resume_acknowledged'] is False
        assert sum(m == 'input.mouse.click' for m, _ in native.calls[before:]) == 1
        assert sum(m == 'execution.continue' for m, _ in native.calls[before:]) == (1 if failure_method == 'execution.continue' else 0)
        assert not native.closed
    finally:
        b.close()


def test_named_mouse_uses_new_ids_each_time_without_changing_absolute_position(adapter, monkeypatch):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    plan = mouse_plan()
    plan['steps'][0]['params'].update(x=159, y=88, width=320, height=200)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: plan))
    original = native.call
    frame_id = 12

    def fresh(method, params=None):
        nonlocal frame_id
        result = original(method, params)
        if method == 'video.screenshot':
            assert native.state == 'stopped'
            frame_id += 7
            result.update(width=320, height=200, frame_id=frame_id, mode_id=frame_id + 100)
        if method == 'input.mouse.click':
            assert native.state == 'stopped'
            assert params['frame_id'] == frame_id and params['mode_id'] == frame_id + 100
        return result

    try:
        b.play()
        monkeypatch.setattr(native, 'call', fresh)
        for _ in range(2):
            b.act({'revision': plan['revision'], 'name': plan['name']}, generation=0)
        delivered = [p for m, p in native.calls if m == 'input.mouse.click']
        assert [(p['x'], p['y']) for p in delivered] == [(159, 88), (159, 88)]
        assert [p['frame_id'] for p in delivered] == [19, 26]
        assert all('width' not in p and 'height' not in p for p in delivered)
    finally:
        b.close()


@pytest.mark.parametrize('field,value', [('frame_id', None), ('mode_id', True), ('frame_id', 1.5)])
def test_named_mouse_invalid_live_ids_never_reach_input_or_resume(adapter, monkeypatch, field, value):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    original = native.call

    def bad_frame(method, params=None):
        result = original(method, params)
        if method == 'video.screenshot':
            result[field] = value
        return result

    try:
        b.play()
        before = len(native.calls)
        monkeypatch.setattr(native, 'call', bad_frame)
        with pytest.raises(ActionInterrupted):
            b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        assert native.state == 'stopped'
        assert not any(m in ('input.mouse.click', 'execution.continue') for m, _ in native.calls[before:])
    finally:
        b.close()


def test_named_mouse_failed_acceptance_leaves_paused_without_replay_or_resume(adapter, monkeypatch):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    original = native.call

    def declined(method, params=None):
        result = original(method, params)
        if method == 'input.mouse.click':
            result['accepted'] = False
        return result

    try:
        b.play()
        before = len(native.calls)
        monkeypatch.setattr(native, 'call', declined)
        with pytest.raises(ActionInterrupted, match='acceptance') as failure:
            b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        assert not failure.value.progress['completed_steps']
        assert native.state == 'stopped' and not native.closed
        assert sum(m == 'input.mouse.click' for m, _ in native.calls[before:]) == 1
        assert not any(m == 'execution.continue' for m, _ in native.calls[before:])
    finally:
        b.close()


def test_named_mouse_state_revision_change_without_receipt_boundary_is_preserved(adapter, monkeypatch):
    from dotbox.harness import ActionInterrupted
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    original = native.call
    clicked = False

    def changed(method, params=None):
        nonlocal clicked
        result = original(method, params)
        if method == 'input.mouse.click':
            clicked = True
        if method == 'session.status' and clicked:
            result['state_revision'] = 2
        return result

    try:
        b.play()
        before = len(native.calls)
        monkeypatch.setattr(native, 'call', changed)
        with pytest.raises(ActionInterrupted, match='state changed') as failure:
            b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        assert len(failure.value.progress['completed_steps']) == 1
        assert native.state == 'stopped'
        assert not any(m == 'execution.continue' for m, _ in native.calls[before:])
    finally:
        b.close()


def test_named_mouse_honors_a_new_state_revision_in_the_click_receipt(adapter, monkeypatch):
    config, native, _ = adapter
    b = backend.FDisBullBackend(config)
    monkeypatch.setattr(b, '_harness', lambda: SimpleNamespace(plan=lambda *_: mouse_plan()))
    original = native.call
    clicked = False

    def advanced(method, params=None):
        nonlocal clicked
        result = original(method, params)
        if method == 'input.mouse.click':
            clicked = True
            result['state_revision'] = 2
        if method == 'session.status' and clicked:
            result['state_revision'] = 2
        return result

    try:
        b.play()
        monkeypatch.setattr(native, 'call', advanced)
        result = b.act({'revision': 'a' * 64, 'name': 'choose'}, generation=0)
        assert result['coordination']['resume_acknowledged'] is True
        assert native.state == 'running'
    finally:
        b.close()
