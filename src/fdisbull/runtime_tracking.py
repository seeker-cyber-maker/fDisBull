"""Automatic, bounded, stopped-state runtime bindings for ordinary sessions.

Source identity, physical translation and OS task lifetime are separate facts.
An unmonitored execution gap closes a lifetime rather than guessing that a
recycled PSP, descriptor, CR3 or DESQview handle denotes the earlier task.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import uuid


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class AutomaticRuntimeTracker:
    """Owned by one session; callbacks run under that session's normal gate."""

    def __init__(self, session):
        self.session = session
        self.project = session.project
        self.tasks = {}
        self.active_bindings = {}
        self.provider = None
        self.internal_breakpoints = set()
        self.generations = {}
        self.observed_creations = set()
        self.owned_dos = bool(getattr(session, 'session_id', None) and
            session.metadata.get('capabilities', {}).get('lifecycle', {}).get('dos_guest_exit') is True)
        self.closed = False
        self.busy = False
        self.sequence = 0
        self.last = dict(state='initializing', enabled=True, current_bindings=0,
                         lifetime_qualification='unqualified')

    def status(self):
        return deepcopy(dict(self.last, closed=self.closed, observations=self.sequence,
                             task_incarnations=list(self.tasks.values()),
                             internal_breakpoints=sorted(self.internal_breakpoints)))

    def _record(self, kind, document):
        data = _json(dict(format='fdisbull-automatic-runtime-tracking-1', kind=kind, document=document))
        artifact = self.session._artifact('runtime-tracking.json', 'runtime-tracking', data,
                                          dict(kind=kind, automatic=True))
        return dict(kind='recorded', reference='local-runtime-tracking:' + artifact['artifact'],
                    sha256=hashlib.sha256(data).hexdigest())

    def _invalidate(self, reason):
        if not any(self.active_bindings.values()):
            return
        evidence = self._record('invalidate', dict(reason=reason, bindings=self.active_bindings))
        # A journal failure propagates before execution. Never dispatch with a
        # source-qualified relation still advertised as current.
        with self.project.transaction(True):
            for task, bindings in self.active_bindings.items():
                if bindings:
                    self.project.runtime_unmap(task, bindings, evidence)
        self.active_bindings = {}
        self.last.update(state='invalidated-before-execution', current_bindings=0)

    def _end(self, reason, keys=None):
        selected = list(self.tasks) if keys is None else list(keys)
        if not selected:
            return
        evidence = self._record('lifetime-end', dict(reason=reason, identities=selected))
        with self.project.transaction(True):
            for key in selected:
                task = self.tasks.get(key)
                if task:
                    self.project.runtime_task_end(task, evidence)
        for key in selected:
            task = self.tasks.pop(key, None)
            self.active_bindings.pop(task, None)

    def before_execution(self, reason):
        if self.closed or self.busy:
            return
        self._invalidate(reason)
        if self.provider is not None:
            try:
                points = self.session.breakpoints
                for identifier in self.internal_breakpoints:
                    point = points[identifier]
                    if point.get('address') not in (self.provider.hook_address, hex(self.provider.hook_address)) or point.get('access') != 'x' or point.get('length') != 1:
                        raise ValueError('native lifecycle hook was replaced')
                if not self.internal_breakpoints:
                    raise ValueError('native lifecycle hook was removed')
                self.provider.validate_coverage()
            except Exception:
                self._end('native lifecycle coverage could not be verified before execution')
                self.generations.clear()
                self.observed_creations.clear()
                self._drop_provider()
        # QMP asynchronous running, restored history and writes are not covered
        # by our passive lifecycle breakpoint. Do not join across those gaps.
        if any(word in reason for word in ('resume', 'state.load', 'restore', 'write', 'reset', 'parent')):
            self._end('observation coverage gap: ' + reason)
            self.generations.clear()
            self.observed_creations.clear()
            self._drop_provider()
        elif self.provider is None and not self.owned_dos:
            # A source match alone supports one stop, never a continuing task.
            self._end('source-only observation ended before execution')

    def _drop_provider(self):
        for identifier in list(self.internal_breakpoints):
            if identifier in self.session.breakpoints:
                self.session.delete_breakpoint(identifier)
        self.internal_breakpoints.clear()
        self.provider = None

    def _provider(self):
        if not hasattr(self.session, 'vm'):
            return
        if self.provider is None:
            from .runtime_desqview import discover
            provider = discover(self.session)
            if provider is None:
                return
            point = self.session.breakpoint(provider.hook_address)
            self.internal_breakpoints.add(point['breakpoint_id'])
            self.provider = provider
            evidence = self._record('native-provider-attach', dict(
                source_identity=provider.source_identity, catalog=provider.catalog,
                current_identity=provider.current_identity(),
                earlier_creation='unknown', executable_modified=False))
            self.last['provider_evidence'] = evidence

    def internal_stop(self, event):
        """Consume only our breakpoint; a colliding user breakpoint stays visible."""
        ids = set(event.get('breakpoints', event.get('breakpoint_ids', event.get('stop', {}).get('breakpoint_ids', []))))
        if not ids.intersection(self.internal_breakpoints) or self.provider is None:
            return False
        native = self.provider.interpret_event(self.session.registers())
        evidence = self._record('native-lifecycle', native)
        kind, handle = native.get('kind'), native.get('handle')
        if kind in ('create', 'end', 'free'):
            prefix = 'desqview:' + str(handle) + ':'
            self._end('observed native ' + str(kind), [key for key in self.tasks if key.startswith(prefix)])
            self.generations[handle] = self.generations.get(handle, 0) + 1
            self.observed_creations.discard(handle)
            if kind == 'create':
                self.observed_creations.add(handle)
        elif kind in ('process-end', 'dv-end'):
            # Process containment is deliberately conservative until a native
            # process->task relation has been established for every child.
            self._end('observed native ' + str(kind))
            self.observed_creations.clear()
            if kind == 'dv-end':
                self._drop_provider()
        self.last.update(last_native_event=native, lifecycle_evidence=evidence)
        return ids <= self.internal_breakpoints

    def _identity(self, match):
        source = hashlib.sha256(_json(match['source_identity'])).hexdigest()
        if self.provider is not None:
            native = self.provider.current_identity()
            handle = native['handle']
            generation = self.generations.setdefault(handle, 0)
            return (f'desqview:{handle}:{generation}:{source[:16]}',
                    dict(provider='source-qualified-desqview', native=native,
                         generation=generation, creation_observed=handle in self.observed_creations,
                         qualification='native lifecycle monitored since attach; earlier creation unknown'))
        if self.owned_dos:
            return ('dos-launch:' + self.session.session_id,
                    dict(provider='owned-dos-launch', native_session_id=self.session.session_id,
                         source_sha256=self.session.metadata['source_sha256'],
                         capability='lifecycle.dos_guest_exit',
                         qualification='owned original launch; native target PSP termination observed by backend; child allocation ownership unqualified'))
        return ('observation:' + uuid.uuid4().hex,
                dict(provider='stopped-source-observation', source=match['identity_evidence'],
                     qualification='one stopped observation; OS lifetime and continuity unqualified'))

    def _publish(self, match):
        key, native = self._identity(match)
        evidence = self._record('source-observation', dict(source=match, identity=native))
        task = self.tasks.get(key)
        if task is None:
            # Existing runtime-state initialization supplies the exact epoch
            # used by memory_snapshot, including checkpoint invalidation.
            state = getattr(self.session, '_runtime_state', None)
            if callable(state):
                state()
            epoch = getattr(self.session, '_runtime_epoch', self.session.run_id)
            task = self.project.runtime_task_start(self.session.run_id, key, evidence,
                version=self.session.version['id'], capture_epoch=epoch)['task']
            self.tasks[key] = task
            with self.project.transaction(True):
                row = self.project._mapping_task(task)
                row['automatic_tracking'] = dict(identity=native, source=match['source_identity'])
                # started/ended are SQL interval fields, not document identity.
                row.pop('started', None); row.pop('ended', None)
                self.project.db.execute('UPDATE runtime_mapping_tasks SET document=? WHERE id=?',
                                        (_json(row).decode(), task))
        bindings = []
        for span in match['source_spans']:
            snapshot = self.session.memory_snapshot(span['address'], length=span['length'],
                task_id=key, name='automatic-' + span['name'] + '.bin')
            fragments = span.get('fragments') or [dict(snapshot_offset=0,
                object_offset=span['object_offset'], length=span['length'])]
            for fragment in fragments:
                offset = fragment['snapshot_offset']
                end = offset + fragment['length']
                while offset < end:
                    # Split at observed linear pages so each binding retains
                    # its exact physical relation even across discontinuities.
                    count = min(end - offset, 4096 - ((span['address'] + offset) & 4095))
                    mapped = self.project.runtime_map_snapshot(task, snapshot['artifact'], span['object_id'],
                        fragment['object_offset'] + offset - fragment['snapshot_offset'], count,
                        snapshot_offset=offset)
                    bindings.append(mapped['binding'])
                    # Track incrementally so an enrichment failure can close
                    # every already-published relation before returning.
                    self.active_bindings[task] = list(bindings)
                    offset += count
        return dict(task=task, identity=native, source=match['source_identity'],
                    binding_count=len(bindings), bindings=bindings)

    def after_stop(self, reason):
        if self.closed or self.busy:
            return
        self.busy = True
        try:
            self._invalidate('new stopped observation')
            self._provider()
            from .runtime_source_matching import discover
            matches = discover(self.session)
            published = [self._publish(match) for match in matches]
            self.sequence += 1
            self.last.update(state='qualified-stopped-bindings' if published else 'no-source-match',
                reason=reason, current_bindings=sum(row['binding_count'] for row in published),
                sources=published, lifetime_qualification=('native-lifecycle-since-attach' if self.provider else
                    'owned-dos-launch' if self.owned_dos else 'one-stop-only'),
                executables_modified=False)
            self.last.pop('error_type', None)
            self.last.pop('error', None)
        except Exception as error:
            self._invalidate('incomplete stopped observation')
            self._end('incomplete stopped observation; lifetime continuity retired')
            self.generations.clear()
            self.observed_creations.clear()
            if self.provider is not None:
                self._drop_provider()
            self.last.update(state='unqualified', reason=reason, current_bindings=0,
                error_type=type(error).__name__, error=str(error), executables_modified=False)
            # Detection is enrichment, never a reason to replay a completed
            # action. Fail closed for facts while preserving debugger usability.
        finally:
            self.busy = False

    def close(self, reason):
        if self.closed:
            return
        self._end(reason)
        self.active_bindings = {}
        self.closed = True
        self.last.update(state='closed', reason=reason, current_bindings=0)
