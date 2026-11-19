"""Bounded stopped-surface preparation, without a completed-frame claim."""
from copy import deepcopy
from contextlib import contextmanager
import time
import uuid

from .operation_budget import request_deadline
from .qemu_macros import _referenced, _literal_preflight
from .screenshot_hooks import READ_AND_LAYERS, ScreenshotHookError, validate_configuration


@contextmanager
def _scope(session, identity, deadline):
    """Recheck the same owner and inherited bounds after queued admission."""
    owner = identity[0]
    lock = identity[3]
    def limits():
        return [deadline, getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
                getattr(owner, 'operation_deadline', None), *(getattr(channel, 'operation_deadline', None)
                    for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None)]
    deadline = min(value for value in limits() if value is not None)
    allowance = min(10, deadline - time.monotonic())
    if allowance <= 0 or not lock.acquire(timeout=allowance):
        raise TimeoutError('Screenshot hook could not acquire its owner before the deadline')
    saved = None
    try:
        deadline = min(value for value in limits() if value is not None)
        _check(session, identity, deadline, {})
        channels = [(channel, getattr(channel, 'operation_deadline', None)) for channel in
                    (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None]
        saved = (getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
                 getattr(owner, 'operation_deadline', None), channels)
        session._rpc_deadline = session._deadline = owner.operation_deadline = deadline
        for channel, _ in channels:
            channel.operation_deadline = deadline
        yield deadline
    except BaseException as error:
        if any(channel is not None and hasattr(channel, 'socket') and channel.socket is None
               for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None))):
            try:
                owner.close()
            except BaseException as cleanup_error:
                error.screenshot_cleanup_error = type(cleanup_error).__name__
        raise
    finally:
        if saved is not None:
            session._rpc_deadline, session._deadline, owner.operation_deadline, channels = saved
            for channel, bound in channels:
                channel.operation_deadline = bound
            for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)):
                if channel is not None and not any(channel is old for old, _ in channels):
                    channel.operation_deadline = saved[2]
        lock.release()


def _stack(value):
    if (not isinstance(value, list) or len(value) > 64
            or any(type(item) is not str or item.startswith('$') for item in value)
            or len(set(value)) != len(value)):
        raise ValueError('Screenshot hooks require a literal, ordered stack of unique layer IDs')
    return list(value)


def validate_native_configuration(configuration, *, session=None):
    """Reject unsupported phases before persistence or native effects."""
    if not isinstance(configuration, dict) or configuration.get('require_fresh_frame') is not False:
        raise ValueError('QEMU screenshot hooks require explicit require_fresh_frame=false; completed frames are unqualified')
    config = validate_configuration(configuration)
    _stack(config['suspend_layers'])
    from .debug_script import validate_script
    for phase in ('pre', 'post'):
        for step in config[phase]:
            if step['op'] not in READ_AND_LAYERS:
                raise ValueError('QEMU screenshot hooks admit only passive reads and layer controls; run/wait are unqualified')
            params = {key: value for key, value in step.items() if key not in ('op', 'as')}
            if step['op'] != 'assert' and _referenced(params):
                raise ValueError('QEMU screenshot hook primitive parameters and layer destinations must be literal')
            if step['op'] == 'layer-stack':
                if params.get('active') is not None:
                    _stack(params['active'])
                if params.get('conflict', 'stop') != 'stop':
                    raise ValueError('Screenshot hooks require conflict=stop for exact layer restoration')
            elif step['op'] == 'layer-enable':
                _stack([params['layer']])
                if type(params.get('enabled', True)) is not bool:
                    raise ValueError('Screenshot hook layer enabled must be boolean')
            elif step['op'] == 'memory':
                _literal_preflight(session, step)
            elif step['op'] == 'code':
                if (type(params.get('length', 32)) is not int or not 1 <= params.get('length', 32) <= 65536
                        or params.get('view', 'execute') not in ('ram', 'execute')):
                    raise ValueError('Invalid screenshot hook code length or view')
        if config[phase]:
            validate_script(dict(format='fdisbull-script-1', backend='qemu-dos', steps=config[phase]), session=session)
    if session is not None:
        _definitions(session, config, [])
    return config


def _definitions(session, config, original):
    ids = set(original) | set(config['suspend_layers'])
    for step in config['pre'] + config['post']:
        if step['op'] == 'layer-stack':
            ids.update(step.get('active') or [])
        elif step['op'] == 'layer-enable':
            ids.add(step['layer'])
    result = {}
    for identifier in ids:
        info = session.project.debug_layer_info(identifier)
        if info['version'] != session.version['id'] or info['id'] != identifier:
            raise ValueError('Screenshot hook layer belongs to another immutable version')
        result[identifier] = deepcopy(info)
    return result


def validate_hook_script(steps, *, session=None):
    """Follow prospective literal setters, including setters before captures."""
    if not any(step['op'] in ('screenshot-hooks', 'screenshot') for step in steps):
        return
    policy = None
    known = False
    for step in steps:
        if step['op'] == 'screenshot-hooks' and step.get('configuration') is not None:
            policy = validate_native_configuration(step['configuration'], session=session)
            known = True
        elif step['op'] == 'screenshot' and step.get('hooks', True) is not False:
            if not known and session is not None:
                stored = session.project.debug_screenshot_hooks(version=session.version['id'])
                policy = stored['configuration'] if stored['configured'] else None
                known = True
            if policy is not None:
                validate_native_configuration(policy, session=session)


def _identity(session):
    owner = getattr(session, 'vm', None)
    lock = getattr(owner, 'lock', None)
    if (owner is None or getattr(session, 'closed', True) or getattr(owner, 'qmp', None) is None
            or not callable(getattr(lock, 'acquire', None)) or not callable(getattr(lock, 'release', None))):
        raise ValueError('Screenshot hooks require a live owned machine and its owner lock')
    return (owner, getattr(owner, 'process', None), session.project,
            lock, getattr(session, '_process', None),
            deepcopy(session.version), deepcopy(session._runtime_lifetime()),
            deepcopy((getattr(session, '_process', None) or {}).get('source_mapping')),
            deepcopy(getattr(session, '_dos_task_binding', None)))


def _check(session, identity, deadline, definitions):
    if time.monotonic() >= deadline:
        raise TimeoutError('Screenshot hook host deadline expired')
    current = _identity(session)
    if (any(left is not right for left, right in zip(identity[:5], current[:5]))
            or identity[5:] != current[5:] or session.closed or session.vm.qmp is None):
        raise ValueError('Screenshot hook owner, source, task or lifetime changed')
    from .qemu_spatial_policy import _context
    _context(session)
    for identifier, expected in definitions.items():
        if session.project.debug_layer_info(identifier) != expected:
            raise ValueError('Screenshot hook immutable layer definition changed')


def _preflight_stacks(session, config, original, definitions, deadline):
    """Check known destinations and backing before the first transition."""
    if sum(len(definition['patches']) for definition in definitions.values()) > 256:
        raise ValueError('Screenshot hook plan exceeds 256 total layer patches')
    if sum(len(bytes.fromhex(patch['data_hex'])) for definition in definitions.values()
           for patch in definition['patches']) > 65536:
        raise ValueError('Screenshot hook plan exceeds 64 KiB of total layer bytes')
    positions = {}
    for identifier, definition in definitions.items():
        if time.monotonic() >= deadline:
            raise TimeoutError('Screenshot hook layer preflight deadline expired')
        positions[identifier] = []
        for patch in definition['patches']:
            addresses = session._layer_positions(definition, patch)
            before, after = bytes.fromhex(patch['expected_hex']), bytes.fromhex(patch['data_hex'])
            if len(addresses) != len(before) or len(before) != len(after):
                raise ValueError('Screenshot layer definition differs from its backing extent')
            positions[identifier].append((addresses, before))
    def transition(stack, step):
        if step['op'] == 'layer-stack' and step.get('active') is not None:
            stack = list(step['active'])
        elif step['op'] == 'layer-enable':
            stack = [item for item in stack if item != step['layer']]
            if step.get('enabled', True):
                stack.append(step['layer'])
        return stack
    stack = [item for item in original if item not in config['suspend_layers']]
    prefixes = [original, stack]
    for step in config['pre']:
        stack = transition(stack, step)
        prefixes.append(list(stack))
    # Post is also cleanup after an earlier failed prefix. Admit all possible
    # literal starting stacks; never assume the whole pre route succeeded.
    stacks = {tuple(stack) for stack in prefixes}
    for prefix in prefixes:
        stack = prefix
        for step in config['post']:
            stack = transition(stack, step)
            stacks.add(tuple(stack))
            if len(stacks) > 256:
                raise ValueError('Screenshot hook plan exceeds 256 possible cleanup stacks')
    for step in config['pre'] + config['post']:
        if step['op'] == 'code':
            session._layer_spans(step['address'], step.get('length', 32), 'source', step.get('cs'))
    for stack in stacks:
        if time.monotonic() >= deadline:
            raise TimeoutError('Screenshot hook layer preflight deadline expired')
        stack = list(stack)
        _stack(stack)
        if stack and getattr(session, '_dos_task_monitor', None):
            raise ValueError('Screenshot hooks cannot change task-private layer stacks')
        if sum(len(positions[item]) for item in stack) > 256:
            raise ValueError('Screenshot hook stack exceeds 256 patches')
        expected = {}
        for item in stack:
            for addresses, before in positions[item]:
                for address, byte in zip(addresses, before):
                    if expected.setdefault(address, byte) != byte:
                        raise ValueError('Screenshot hook layers disagree about base bytes')
        if len(set(expected) | set(getattr(session, '_layer_ram_applied', {}))) > 65536:
            raise ValueError('Screenshot hook transition exceeds 64 KiB')


class _SurfaceEvidence:
    def __init__(self, session, identity, deadline, definitions, evidence):
        self.identity, self.deadline, self.definitions = identity, deadline, definitions
        self.session, self.evidence = session, deepcopy(evidence)
        self.capture = None


def surface_hook_evidence(session):
    """Return nested provenance only; never merge core surface claims."""
    token = getattr(session, '_qemu_surface_hook_evidence', None)
    if token is None:
        return None
    if type(token) is not _SurfaceEvidence or token.session is not session:
        raise ValueError('Invalid stopped-surface screenshot hook provenance')
    _check(session, token.identity, token.deadline, token.definitions)
    return deepcopy(token.evidence)


def retain_surface_hook_capture(session, artifact):
    """Retain an already-published receipt even if its outer deadline expires.

    This private result channel changes no artifact metadata or capture claim.
    Raw capture without an active hook context remains a no-op here.
    """
    token = getattr(session, '_qemu_surface_hook_evidence', None)
    if type(token) is _SurfaceEvidence and token.session is session:
        token.capture = deepcopy(artifact)


class QemuScreenshotHookMixin:
    def screenshot_hooks(self, configuration=None):
        if getattr(self, '_screenshot_hooks_running', False):
            raise ValueError('Cannot reconfigure hooks during screenshot capture')
        identity = _identity(self)
        with _scope(self, identity, request_deadline(self, 10000)) as deadline:
            _check(self, identity, deadline, {})
            if self.project.db.in_transaction:
                raise ValueError('Screenshot hooks require a project outside a caller-owned transaction')
            if configuration is not None:
                validate_native_configuration(configuration, session=self)
            _check(self, identity, deadline, {})
            result = self.project.debug_screenshot_hooks(configuration, version=self.version['id'])
            try:
                _check(self, identity, deadline, {})
            except BaseException as error:
                error.result = result
                raise
            return result

    def screenshot(self, name='machine.png', *, grid=False, grid_step=8, hooks=True):
        from .debug_script import execute_script
        from .external_files import _file_name
        from .qemu_machine import _machine_operation_guard
        from .screenshot_grid import validate_step
        _file_name(name)
        if type(hooks) is not bool or type(grid) is not bool:
            raise ValueError('hooks and grid must be boolean')
        if grid:
            validate_step(grid_step)
        if not hooks:
            return super().screenshot(name, grid=grid, grid_step=grid_step)
        if getattr(self, '_screenshot_hooks_running', False):
            raise ValueError('Nested QEMU screenshot hook capture is unsupported')
        started = time.monotonic()
        identity = _identity(self)
        policy = self.project.debug_screenshot_hooks(version=self.version['id'])
        if not policy['configured']:
            return super().screenshot(name, grid=grid, grid_step=grid_step)
        config = validate_native_configuration(policy['configuration'], session=self)
        with _scope(self, identity, started + config['timeout_ms'] / 1000) as deadline:
            _check(self, identity, deadline, {})
            if self.project.db.in_transaction:
                raise ValueError('Screenshot hooks require a project outside a caller-owned transaction')
            if self.project.debug_screenshot_hooks(version=self.version['id']) != policy:
                raise ValueError('Screenshot hook policy changed during lock admission')
            original = _stack(self.layers()['active'])
            definitions = _definitions(self, config, original)
            _preflight_stacks(self, config, original, definitions, deadline)
            _check(self, identity, deadline, definitions)
            _machine_operation_guard(self.vm, 'screenshot', (name,), dict(grid=grid, grid_step=grid_step))
            report = dict(attempt=uuid.uuid4().hex, policy=policy['id'], policy_sha256=policy['sha256'],
                original_layers=original, layer_identities={key: {field: value[field] for field in ('id','version','sha256')}
                    for key, value in definitions.items()}, require_fresh_frame=False,
                completed_guest_frame=None, pre=None, post=None, capture=None, restore=None, errors=[], ok=False)
            modified = False
            self._screenshot_hooks_running = True

            def check():
                _check(self, identity, deadline, definitions)

            def phase(which):
                nonlocal modified
                if not config[which]:
                    return
                check()
                modified |= any(step['op'] == 'layer-enable' or step['op'] == 'layer-stack'
                                and step.get('active') is not None for step in config[which])
                allowance = int((deadline - time.monotonic()) * 1000)
                if allowance < 1:
                    raise TimeoutError('Screenshot hook phase deadline expired')
                report[which] = execute_script(self,
                    dict(format='fdisbull-script-1', backend='qemu-dos', steps=config[which]),
                    timeout_ms=allowance, bindings={'capture': dict(original_layers=original,
                        suspended_layers=config['suspend_layers'])}, _after_step=lambda step, result: check())
                if not report[which]['ok']:
                    raise ValueError('Screenshot ' + which + ' hook failed')

            def failure(which, error):
                report['errors'].append(dict(phase=which, type=type(error).__name__, message=str(error)))

            try:
                wanted = [item for item in original if item not in config['suspend_layers']]
                if wanted != original:
                    modified = True
                    self.layers(wanted)
                phase('pre')
                check()
                report['capture_layers'] = _stack(self.layers()['active'])
                evidence = {key: report[key] for key in ('attempt','policy','policy_sha256','original_layers',
                    'capture_layers','layer_identities','require_fresh_frame','completed_guest_frame')}
                token = _SurfaceEvidence(self, identity, deadline, definitions, evidence)
                self._qemu_surface_hook_evidence = token
                try:
                    report['capture'] = super().screenshot(name, grid=False, grid_step=grid_step)
                finally:
                    if report['capture'] is None and token.capture is not None:
                        report['capture'] = token.capture
                    self._qemu_surface_hook_evidence = None
                if grid:
                    check()
                    report['capture'] = self.project.debug_grid(report['capture']['artifact'],
                        name=name+'.grid.png', step=grid_step)
                check()
            except Exception as error:
                failure('pre-or-capture', error)
            finally:
                try:
                    phase('post')
                except Exception as error:
                    failure('post', error)
                try:
                    check()
                    if modified and _stack(self.layers()['active']) != original:
                        self.layers(original)
                    if _stack(self.layers()['active']) != original:
                        raise ValueError('Screenshot hook original stack was not restored exactly')
                    check()
                    report['restore'] = dict(ok=True, active=list(original))
                except Exception as error:
                    failure('restore', error)
                    report['restore'] = dict(ok=False)
                    if modified or self.vm is not identity[0]:
                        identity[0]._fdisbull_control_quarantine = 'uncertain screenshot hook restoration'
                        try:
                            if self.vm is identity[0]:
                                self.close()
                            else:
                                identity[0].close()
                        except BaseException as cleanup_error:
                            failure('close', cleanup_error)
                finally:
                    self._screenshot_hooks_running = False
                    self._qemu_surface_hook_evidence = None
            report['ok'] = not report['errors']
            try:
                self._event('screenshot-hooks', report)
            except Exception as error:
                failure('evidence', error)
                report['ok'] = False
            if report['ok']:
                try:
                    check()
                except Exception as error:
                    failure('completion', error)
                    report['ok'] = False
            if not report['ok']:
                raise ScreenshotHookError(report)
            return dict(report['capture'], screenshot_hooks=report)
