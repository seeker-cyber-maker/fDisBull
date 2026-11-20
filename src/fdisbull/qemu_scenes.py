"""Passive runtime-scene reads under one native owner, epoch and host deadline."""
from copy import deepcopy
import time

from .qemu_runtime_memory import _scope
from .runtime_scenes import validate_parameters, select, companions, observation_result, evaluate, store
from .scene_values import compact_result


def _admit(session):
    from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
    session._runtime_admit()
    if (session.vm.machine_configuration.get('clock_profile', {}).get('profile') != 'virtual'
            or not VIRTUAL_CLOCK_COMMANDS <= session.vm.qmp_commands):
        raise ValueError('Passive QEMU scene checks require the explicit native virtual clock')


def preflight(session, scene, *, object=None, compact=False, allow_references=False):
    validate_parameters(scene, object=object, compact=compact, allow_references=allow_references)
    _admit(session)
    if not (allow_references and scene.startswith('$')):
        target = None if allow_references and isinstance(object, str) and object.startswith('$') else object
        info, _ = select(session.project, scene, session.version['id'], target)
        companions(session.project, info, session.version['id'])


def _identity(session):
    return (id(session.vm), id(getattr(session.vm,'process',None)), id(session.project), session.run_id, session._runtime_epoch,
            deepcopy(session.version), session.metadata.get('source_sha256'), session.metadata.get('version_sha256'),
            deepcopy(session._runtime_lifetime()))


def _observe(session, scene, *, object=None, compact=False, asserting=False, _publish=True):
    from .scenes import SceneError
    validate_parameters(scene, object=object, compact=compact)
    seed = _identity(session)
    result = None
    name = 'scene_assert' if asserting else 'scene_check'
    with _scope(session, name, (scene,), dict(object=object, compact=compact)) as deadline:
        def stable():
            if time.monotonic() >= deadline: raise TimeoutError('Passive scene observation host deadline expired')
            if _identity(session) != seed: raise ValueError('Passive scene owner or restore epoch changed')
            _admit(session)
        try:
            stable()
            info, selected = select(session.project, scene, session.version['id'], object)
            others = companions(session.project, info, session.version['id'])
            result = observation_result(session,info,selected)
            stable()
            cpu = session._runtime_paused()
            stable()
            before = session.clock_observe()
            stable()
            result = evaluate(session, info, selected, others, result, deadline=deadline, owner_guard=stable)
            after = None
            if not result.get('evaluation_stopped'):
                stable()
                after = session.clock_observe()
                stable()
                if (before['epoch'] != after['epoch'] or before['virtual_ns'] != after['virtual_ns']
                        or before.get('counter') != after.get('counter')
                        or session._runtime_paused() != cpu):
                    raise ValueError('Passive scene observations span different stopped CPU/clock contexts')
            stable()
            fresh, _ = select(session.project, scene, session.version['id'], object)
            refreshed = companions(session.project, fresh, session.version['id'])
            pins = lambda items: [(item['id'], item['sha256']) for item in items]
            if pins([fresh, *refreshed]) != pins([info, *others]): raise ValueError('Scene manifest changed during observation')
            result['observation_context'] = dict(run=session.run_id, version=session.version['id'],
                capture_epoch=session._runtime_epoch, source_sha256=session.metadata['source_sha256'],
                version_sha256=session.metadata['version_sha256'], cpu_mode=cpu['observation_cpu_mode'],
                address_context=deepcopy(cpu['observation_address_context']),
                clock=dict(domain='QEMU_CLOCK_VIRTUAL', epoch=before['epoch'], virtual_ns=before['virtual_ns'],
                           before=before, after=after))
            result['capture_context_verified'] = after is not None
            if _publish:
                result = store(session, result)
            stable()
            if compact: result = compact_result(result)
            if asserting and result['status'] != 'matched': raise SceneError(result)
            return result
        except BaseException as error:
            if result is not None and 'observation' not in result:
                result.update(status='unavailable', complete=False, capture_context_verified=False)
                result.setdefault('error_type',type(error).__name__);result.setdefault('error',str(error))
            if result is not None and getattr(error, 'result', None) is None: error.result = result
            elif result is not None and error.result is not result:error.scene_result=result
            raise


class QemuSceneObservationMixin:
    def scene_check(self, scene, *, object=None, compact=False):
        return _observe(self, scene, object=object, compact=compact)

    def scene_assert(self, scene, *, object=None, compact=False):
        return _observe(self, scene, object=object, compact=compact, asserting=True)

    def scene_wait(self, scene, *, object=None, guest_ms=5000, timeout_ms=5000, slice_ms=100, compact=False):
        from .qemu_scene_wait import wait
        return wait(self, scene, object=object, guest_ms=guest_ms, timeout_ms=timeout_ms,
                    slice_ms=slice_ms, compact=compact)
