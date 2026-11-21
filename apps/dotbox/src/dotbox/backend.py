"""Standalone visible-DOSBox adapter reusing the extracted native runtime.

The service owns this object on one thread. It never interprets desktop takeover
state; it only exposes the backend's acknowledged native input ownership.
"""
from collections.abc import Mapping
import base64
import hashlib
from pathlib import Path
import threading
import time


COOPERATIVE_CONTROL = 'dotbox-input-control-1'
_MAX_INTEGER = (1 << 53) - 1
_RPC_TIMEOUT_MS = 2000
_PAUSE_WAIT_MS = 1000


class BackendUnavailable(RuntimeError):
    """The selected core or binary cannot provide this playable slice."""


def _load_runtime():
    from .store import ControlStore
    from .native_session import NativeSession
    from .keyboard_input import validate_keyboard
    from .screenshot_codecs import decode_screenshot
    from .operation_budget import deadline_scope
    return ControlStore, NativeSession, validate_keyboard, decode_screenshot, deadline_scope


def _integer(value, name, low=0, high=_MAX_INTEGER):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _parameters(params, allowed, required=()):
    if not isinstance(params, Mapping):
        raise ValueError('input parameters must be an object')
    if set(params) - set(allowed):
        raise ValueError('unsupported input parameters')
    if set(required) - set(params):
        raise ValueError('required input parameters are missing')
    return dict(params)


def _control(result):
    owner, generation = result.get('owner'), result.get('generation')
    if owner not in ('agent', 'host'):
        raise RuntimeError('Backend returned invalid cooperative input ownership')
    _integer(generation, 'native control generation')
    return {'owner': owner, 'generation': generation}


def _stop_metadata(result):
    """Normalize native status's last_stop and execution.wait's stop_reason."""
    result = dict(result)
    if result.get('stop_reason') is None and 'last_stop' in result:
        result['stop_reason'] = result['last_stop']
    return result


class DOSBoxBackend:
    """Own one visible original-game session through the extracted DOSBox transport."""

    def __init__(self, config):
        self._thread = threading.get_ident()
        self._closed = False
        self._project = None
        self._session = None
        self._operation = None
        if not isinstance(config, Mapping):
            raise ValueError('backend configuration must be an object')
        missing = {'project', 'game_dir', 'executable'} - set(config)
        if missing:
            raise ValueError('backend configuration is missing ' + ', '.join(sorted(missing)))
        image = config.get('image')
        if image not in (None, 'auto', 'mz', 'com'):
            raise ValueError('image must be auto, mz or com')
        project_path = Path(config['project']).expanduser().resolve()
        game_dir = Path(config['game_dir']).expanduser().resolve(strict=True)
        executable = Path(config['executable']).expanduser().resolve(strict=True)
        if not game_dir.is_dir() or not executable.is_file():
            raise ValueError('expected a game directory and DOSBox executable')
        program = None
        if config.get('program') is not None:
            program = Path(config['program']).expanduser().resolve(strict=True)
            if (program.parent != game_dir or not program.is_file()
                    or not 0 < program.stat().st_size <= 64 * 1024 * 1024):
                raise ValueError('program must be a regular file directly inside game_dir, at most 64 MiB')
        if not project_path.exists() and program is None:
            raise ValueError('program is required to create a missing analysis project')

        Store, NativeSession, self._validate_keyboard, self._decode_screenshot, self._deadline_scope = _load_runtime()
        try:
            if project_path.exists():
                self._project = Store(project_path)
                if program is not None:
                    if (self._project.meta['filename'] != program.name
                            or self._project.meta['source_sha256'] != hashlib.sha256(program.read_bytes()).hexdigest()):
                        raise ValueError('program does not match the existing project source')
            else:
                self._project = Store(project_path, program=program)
            selected_program = (game_dir / self._project.meta['filename']).resolve(strict=True)
            if selected_program.parent != game_dir:
                raise ValueError('Stored program must be directly inside game_dir')
            if image not in (None, 'auto'):
                with selected_program.open('rb') as source:
                    actual_image = 'mz' if source.read(2) == b'MZ' else 'com'
                if actual_image != image:
                    raise ValueError('Declared image format does not match the original program')
            presentation = {} if config.get('window_scale') is None else {'window_scale': config['window_scale']}
            self._session = NativeSession(
                executable, game_dir, selected_program, window=True,
                source_sha256=self._project.meta['source_sha256'], **presentation)
            capabilities = self._session.rpc.capabilities
            if capabilities.get('input', {}).get('cooperative_control') != COOPERATIVE_CONTROL:
                raise BackendUnavailable(
                    'DOSBox backend lacks cooperative input control; use a DotBox-compatible backend')
            _control(self._call('input.control'))
        except BaseException:
            try:
                self.close()
            except BaseException:
                pass  # Preserve the launch/admission error after attempting owned cleanup.
            raise

    def _check_thread(self):
        if threading.get_ident() != self._thread:
            raise RuntimeError('The backend must be used on its owning service thread')

    def _call(self, method, params=None):
        self._check_thread()
        if self._closed:
            raise RuntimeError('Backend is closed')
        with self._deadline_scope(
                self._session, time.monotonic() + _RPC_TIMEOUT_MS / 1000,
                rpc_ms=_RPC_TIMEOUT_MS, admission_ms=0, cleanup_ms=1000):
            result = self._session.call(method, params or {})
        if not isinstance(result, dict):
            raise RuntimeError('Backend returned an invalid response')
        return result

    def status(self):
        native = _stop_metadata(self._call('session.status'))
        result = {'run_id': self._session.run_id,
                  'native_session_id': self._session.session_id,
                  'state': native.get('state'),
                  'native_control': _control(self._call('input.control'))}
        for field in ('state_revision', 'frame_id', 'mode_id', 'stop_reason'):
            if field in native:
                result[field] = native[field]
        return result

    def transfer(self, owner, expected_generation):
        if owner not in ('agent', 'host'):
            raise ValueError('owner must be agent or host')
        _integer(expected_generation, 'expected_generation', high=_MAX_INTEGER - 1)
        current = _control(self._call('input.control'))
        if current['generation'] != expected_generation:
            raise ValueError('native control generation changed')
        result = _control(self._call('input.control', {
            'owner': owner, 'expected_generation': expected_generation}))
        if result != {'owner': owner, 'generation': expected_generation + 1}:
            raise RuntimeError('Backend did not acknowledge the requested ownership generation')
        return result

    def play(self):
        current = self._call('session.status')
        if current.get('state') == 'running':
            return current
        if current.get('state') != 'stopped':
            raise ValueError('Cannot play an exited or unavailable guest')
        return self._continue()

    def resume_after_handoff(self, owner, generation):
        """Reobserve the owned startup/pause boundary before automatic resume.

        The service is the sole native controller. Execution RPCs themselves do
        not carry an atomic ownership guard; no foreign stop is adopted here.
        """
        if owner not in ('host', 'agent'):
            raise ValueError('Invalid resume owner')
        _integer(generation, 'generation')
        observed = self.status()
        if observed['native_control'] != {'owner': owner, 'generation': generation}:
            raise ValueError('Ownership changed before handoff resume')
        reason = observed.get('stop_reason') or {}
        kind = reason.get('kind') if isinstance(reason, dict) else reason
        if observed['state'] == 'stopped' and kind in ('startup', 'pause'):
            return self._continue()
        return observed

    def _continue(self):
        result = self._call('execution.continue')
        operation = result.get('operation_id')
        if not isinstance(operation, str) or not operation:
            raise RuntimeError('Backend did not identify the continuing operation')
        self._operation = operation
        return result

    def pause(self):
        current = _stop_metadata(self._call('session.status'))
        if current.get('state') != 'running':
            return current
        try:
            operation = self._call('execution.pause')['operation_id']
        except Exception as error:
            if not str(error).endswith('(TARGET_NOT_RUNNING)'):
                raise
            # A breakpoint/exit can win this race. Observe the original operation;
            # never resume it just to produce a pause receipt.
            operation = self._operation
            if operation is None:
                observed = _stop_metadata(self._call('session.status'))
                if observed.get('state') in ('stopped', 'exited'):
                    return observed
                raise RuntimeError('Pause race did not establish a stopped guest') from error
        result = _stop_metadata(self._call('execution.wait', {
            'operation_id': operation, 'timeout_ms': _PAUSE_WAIT_MS}))
        if result.get('running') is True or result.get('state') not in ('stopped', 'exited'):
            try:
                self.close()
            finally:
                raise TimeoutError('Backend did not pause within its bounded wait')
        self._operation = None
        return result

    def _require_agent(self, generation):
        _integer(generation, 'generation')
        current = _control(self._call('input.control'))
        if current['generation'] != generation:
            raise ValueError('native control generation changed')
        if current['owner'] != 'agent':
            raise ValueError('Agent input requires agent ownership')

    def key(self, params, generation):
        data = _parameters(params, ('key', 'modifiers', 'hold_ms', 'gap_ms'), ('key',))
        data.setdefault('modifiers', [])
        data.setdefault('hold_ms', 40)
        data.setdefault('gap_ms', 40)
        _integer(data['hold_ms'], 'hold_ms', 1, 1000)
        _integer(data['gap_ms'], 'gap_ms', 1, 1000)
        self._validate_keyboard(**data)
        self._require_agent(generation)
        data['modifiers'] = ','.join(data['modifiers'])
        return self._call('input.keyboard.press', {**data, 'control_generation': generation})

    def type(self, params, generation):
        data = _parameters(params, ('text', 'hold_ms', 'gap_ms'), ('text',))
        data.setdefault('hold_ms', 40)
        data.setdefault('gap_ms', 40)
        _integer(data['hold_ms'], 'hold_ms', 1, 1000)
        _integer(data['gap_ms'], 'gap_ms', 1, 1000)
        self._validate_keyboard(**data)
        self._require_agent(generation)
        return self._call('input.keyboard.type', {**data, 'control_generation': generation})

    def click(self, params, generation):
        data = _parameters(params, ('x', 'y', 'button', 'hold_ms', 'mode_id', 'frame_id'),
                           ('x', 'y', 'mode_id', 'frame_id'))
        _integer(data['x'], 'x', 0, 4095)
        _integer(data['y'], 'y', 0, 4095)
        data.setdefault('button', 'left')
        data.setdefault('hold_ms', 80)
        if data['button'] not in ('left', 'right', 'middle'):
            raise ValueError('button must be left, right or middle')
        _integer(data['hold_ms'], 'hold_ms', 1, 1000)
        for field in ('mode_id', 'frame_id'):
            if field in data:
                _integer(data[field], field)
        self._require_agent(generation)
        return self._call('input.mouse.click', {**data, 'control_generation': generation})

    def frame(self):
        reply = self._call('video.screenshot', {'encoding': 'png'})
        payload, metadata = self._decode_screenshot(reply)
        return {**metadata, 'format': 'png', 'png_base64': base64.b64encode(payload).decode('ascii')}

    def _harness(self):
        self._check_thread()
        if self._closed:
            raise RuntimeError('Backend is closed')
        from .harness import HarnessLibrary
        return HarnessLibrary(self._project, version=1, validate_keyboard=self._validate_keyboard)

    def harness_list(self):
        return self._harness().list()

    def harness_info(self, params):
        data = _parameters(params, ('revision',), ('revision',))
        return self._harness().info(data['revision'])

    def harness_save(self, params):
        data = _parameters(params, ('definition', 'parent'), ('definition',))
        # Only project metadata changes. No pause/input/scene operation is
        # needed, including while the human is playing the original game.
        return self._harness().save(data['definition'], parent=data.get('parent'))

    def act(self, params, generation):
        from .harness import ActionInterrupted
        data = _parameters(params, ('revision', 'name'), ('revision', 'name'))
        plan = self._harness().plan(data['revision'], data['name'])
        if any(step['op'] == 'click' for step in plan['steps']):
            return self._act_mouse(plan, generation)
        completed = []
        with self._deadline_scope(self._session, time.monotonic() + 1,
                                  rpc_ms=1000, admission_ms=0, cleanup_ms=0):
            self._require_agent(generation)
            if self._call('session.status').get('state') != 'running':
                raise ValueError('Named controls require a running guest; play explicitly first')
            for index, step in enumerate(plan['steps']):
                try:
                    if self._call('session.status').get('state') != 'running':
                        raise RuntimeError('Guest stopped during the control; inspect it before continuing')
                    # Each primitive rechecks native generation, and includes
                    # it in the actual input RPC. Never use core.macro(),
                    # whose general debug scripts do not carry this lease.
                    result = getattr(self, step['op'])(step['params'], generation)
                    if result.get('accepted') is not True:
                        raise RuntimeError('Backend did not acknowledge input acceptance')
                    completed.append({'index': index, 'op': step['op'], 'result': result})
                except Exception as error:
                    raise ActionInterrupted(plan['revision'], plan['name'], completed, index, error) from error
        return {'revision': plan['revision'], 'name': plan['name'],
                'queued_guest_ms': plan['queued_guest_ms'], 'steps': completed,
                'claim': 'Input accepted/queued; observe a new frame to verify the game outcome',
                'transition_verified': False}

    def _act_mouse(self, plan, generation):
        """Bind one persisted absolute click to a fresh stopped guest frame.

        This is one serialized service operation with a bounded RPC deadline.
        A failed or ambiguous RPC never triggers a replay or automatic resume.
        """
        from .harness import ActionInterrupted
        if len(plan['steps']) != 1 or plan['steps'][0]['op'] != 'click':
            raise ValueError('Mouse controls require exactly one click')
        params = _parameters(plan['steps'][0]['params'],
                             ('x', 'y', 'width', 'height', 'button', 'hold_ms'),
                             ('x', 'y', 'width', 'height'))
        for field in ('width', 'height'):
            _integer(params[field], field, 1, 4096)
        _integer(params['x'], 'x', 0, params['width'] - 1)
        _integer(params['y'], 'y', 0, params['height'] - 1)
        params.setdefault('button', 'left')
        params.setdefault('hold_ms', 80)
        if params['button'] not in ('left', 'right', 'middle'):
            raise ValueError('button must be left, right or middle')
        _integer(params['hold_ms'], 'hold_ms', 1, 1000)
        coordination = {'status': 'started', 'resume_acknowledged': False,
                        'resume_observed': False, 'events': []}

        def stamp(stage, **metadata):
            coordination['status'] = stage
            coordination['events'].append({'stage': stage, 'monotonic_ns': time.monotonic_ns(), **metadata})

        def stopped_boundary(expected_revision=None):
            status = _stop_metadata(self._call('session.status'))
            reason = status.get('stop_reason')
            kind = reason.get('kind') if isinstance(reason, dict) else reason
            if status.get('state') != 'stopped' or kind != 'pause':
                raise RuntimeError('Guest left the coordinated pause boundary; inspect before continuing')
            if expected_revision is not None and status.get('state_revision') != expected_revision:
                raise RuntimeError('Guest state changed at the coordinated pause boundary')
            return status

        completed = []
        stamp('started')
        with self._deadline_scope(self._session, time.monotonic() + 4,
                                  rpc_ms=1000, admission_ms=0, cleanup_ms=0):
            # All definition validation and initial admission precede pause or
            # input. Host ownership never causes even an execution mutation.
            self._require_agent(generation)
            if self._call('session.status').get('state') != 'running':
                raise ValueError('Named controls require a running guest; play explicitly first')
            try:
                stamp('pause_requested')
                paused = self.pause()
                reason = paused.get('stop_reason')
                kind = reason.get('kind') if isinstance(reason, dict) else reason
                if paused.get('state') != 'stopped' or kind != 'pause':
                    raise RuntimeError('Breakpoint or exit won the pause; guest preserved without click or resume')
                self._require_agent(generation)
                boundary = stopped_boundary(paused.get('state_revision'))
                stamp('stopped', state_revision=boundary.get('state_revision'), stop_reason=reason)
                frame = self.frame()
                stamp('frame_captured', frame_id=frame.get('frame_id'), mode_id=frame.get('mode_id'),
                      width=frame.get('width'), height=frame.get('height'))
                if (type(frame.get('width')) is not int or type(frame.get('height')) is not int
                        or (frame['width'], frame['height']) != (params['width'], params['height'])):
                    raise ValueError('Original guest frame dimensions differ from the selected control')
                stopped_boundary(boundary.get('state_revision'))
                click = {key: params[key] for key in ('x', 'y', 'button', 'hold_ms')}
                click.update(frame_id=frame.get('frame_id'), mode_id=frame.get('mode_id'))
                result = self.click(click, generation)
                if result.get('accepted') is not True:
                    raise RuntimeError('Backend did not acknowledge input acceptance')
                completed.append({'index': 0, 'op': 'click', 'result': result})
                stamp('click_acknowledged')
                self._require_agent(generation)
                # An accepted click can advance the backend's state revision;
                # its receipt supplies that boundary when present. Stop kind
                # and ownership must still match before our sole continue.
                stopped_boundary(result.get('state_revision', boundary.get('state_revision')))
                self._require_agent(generation)
                stamp('resume_requested')
                # Do not call play(), which permits explicit resumption from
                # any stopped reason. Only our just-validated pause qualifies.
                resumed = self._continue()
                coordination['resume_acknowledged'] = True
                stamp('resume_acknowledged', operation_id=resumed.get('operation_id'))
            except Exception as error:
                coordination['status'] = 'interrupted'
                coordination['events'].append({'stage': 'interrupted', 'monotonic_ns': time.monotonic_ns()})
                raise ActionInterrupted(plan['revision'], plan['name'], completed, 0, error,
                                        coordination=coordination) from error
        return {'revision': plan['revision'], 'name': plan['name'],
                'queued_guest_ms': plan['queued_guest_ms'], 'steps': completed,
                'coordination': coordination,
                'claim': 'Click accepted/queued and continue acknowledged; observe a fresh frame for game outcome and resumption',
                'transition_verified': False}

    def close(self):
        if self._closed:
            return
        self._check_thread()
        self._closed = True
        failure = None
        if self._session is not None:
            try:
                self._session.close()
            except BaseException as error:
                failure = error
        if self._project is not None:
            try:
                self._project.__exit__(None, None, None)
            except BaseException as error:
                if failure is None:
                    failure = error
        if failure is not None:
            raise failure


# Compatibility for callers of the dependent prototype; this class imports no fDisBull.
FDisBullBackend = DOSBoxBackend
