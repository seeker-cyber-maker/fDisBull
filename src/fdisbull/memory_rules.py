"""Bounded host-assisted conditional memory edits over owned search candidates.

Rules are immutable private artifacts. Each tick observes the original task and
mapping again, then creates a fresh scalar snapshot and one-shot guarded edit.
No guest TSR, timer hook, injected search loop or background worker is installed.
Durable pending records prevent a lost acknowledgment from becoming a retry.
"""
from __future__ import annotations

from copy import deepcopy
from functools import wraps
import json
import time
import uuid

from .memory_search import plan_edit, snapshot_metadata, start_search
from .memory_search_runtime import _artifact, _brief, _capture, _json, _locked, _search
from .operation_budget import rpc_budget


MAX_TICKS = 4096
MAX_APPLICATIONS = 4096
_TERMINAL = frozenset(('exhausted', 'disabled', 'uncertain'))
_RULE_KEYS = frozenset(('format', 'name', 'created_at', 'origin_search_artifact',
    'origin_snapshot_artifact', 'origin_context', 'origin_state_sha256',
    'origin_snapshot_sha256', 'spec', 'offset', 'action', 'max_applications', 'max_ticks'))


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def _stamp():
    from .debugger import stamp
    return stamp()


def _name(value):
    if (type(value) is not str or not value.strip() or len(value) > 128
            or any(ord(character) < 32 for character in value)):
        raise ValueError('Rule name must contain 1..128 printable characters')
    return value


def _rule(project, identifier):
    row, raw, _ = _artifact(project, identifier, 'memory-rule')
    if len(raw) > 256 * 1024:
        raise ValueError('Memory rule exceeds its metadata budget')
    rule = json.loads(raw)
    if (type(rule) is not dict or rule.keys() != _RULE_KEYS
            or rule['format'] != 'fdisbull-memory-rule-1'):
        raise ValueError('Unsupported memory rule format')
    _name(rule['name'])
    _integer(rule['max_applications'], 'max_applications', 1, MAX_APPLICATIONS)
    _integer(rule['max_ticks'], 'max_ticks', 1, MAX_TICKS)
    origin_row, origin, data, metadata = _search(project, rule['origin_search_artifact'])
    if row['run'] != origin_row['run']:
        raise ValueError('Memory rule and original search belong to different runs')
    if (rule['origin_snapshot_artifact'] != origin['snapshot_artifact']
            or rule['origin_state_sha256'] != origin['state']['state_sha256']
            or rule['origin_snapshot_sha256'] != metadata['snapshot']['snapshot_sha256']
            or _json(rule['origin_context']) != _json(metadata['snapshot']['context'])
            or _json(rule['spec']) != _json(origin['state']['spec'])):
        raise ValueError('Memory rule differs from its original candidate identity')
    action = rule['action']
    if type(action) is not dict or set(action) != {'value', 'condition', 'compare_value'}:
        raise ValueError('Unsupported memory rule action')
    # Recheck candidate membership and scalar/condition bounds, including the
    # implicit equality value normalized when this rule was created.
    plan_edit(origin['state'], data, metadata['snapshot'], offset=rule['offset'], **action)
    return row, rule


def _progress(project, identifier, rule, run):
    row = project.db.execute(
        "SELECT id FROM debug_artifacts WHERE run=? AND kind='memory-rule-progress' "
        "AND json_extract(metadata,'$.rule_artifact')=? ORDER BY rowid DESC LIMIT 1",
        (run, identifier)).fetchone()
    if row is None:
        raise ValueError('Memory rule has no retained progress record')
    artifact, raw, _ = _artifact(project, row['id'], 'memory-rule-progress')
    progress = json.loads(raw)
    if (type(progress) is not dict or progress.get('format') != 'fdisbull-memory-rule-progress-1'
            or progress.get('rule_artifact') != identifier or artifact['run'] != run
            or progress.get('run_id') != run or progress.get('status') not in {'active', 'pending', *_TERMINAL}
            or type(progress.get('last')) is not dict):
        raise ValueError('Invalid retained memory rule progress')
    ticks = _integer(progress.get('ticks'), 'retained ticks', 0, rule['max_ticks'])
    attempts = _integer(progress.get('attempts'), 'retained attempts', 0, min(ticks, rule['max_applications']))
    _integer(progress.get('applications'), 'retained applications', 0, attempts)
    _integer(progress.get('sequence'), 'progress sequence', 0, MAX_TICKS * 8 + 16)
    return row['id'], progress


def _save(project, identifier, run, previous_id, progress, *, session=None):
    progress = deepcopy(progress)
    progress['previous_progress_artifact'] = previous_id
    progress['updated_at'] = _stamp()
    artifact = project._debug_artifact(run, 'memory-rule-progress.json', 'memory-rule-progress',
        _json(progress), dict(rule_artifact=identifier, sequence=progress['sequence']))
    if session is not None:
        # The artifact and its ordinary artifact event already committed in one
        # Project transaction. This named event is supplementary, not the sole
        # record of an attempted action.
        try:
            session._event('memory-rule-progress', dict(rule_artifact=identifier,
                progress_artifact=artifact['artifact'], status=progress['status'],
                phase=progress['phase'], ticks=progress['ticks'], attempts=progress['attempts'],
                applications=progress['applications']))
        except Exception:
            pass
    return artifact['artifact'], progress


def _next(progress, **changes):
    return dict(deepcopy(progress), sequence=progress['sequence'] + 1, **changes)


def _response(identifier, progress_id, progress, *, fresh=False):
    last = progress['last']
    result = dict(rule_artifact=identifier, progress_artifact=progress_id,
        status=progress['status'], reason=progress.get('reason'), ticks=progress['ticks'],
        attempts=progress['attempts'], applications=progress['applications'],
        tick_executed=fresh, applied=bool(fresh and last.get('applied')), assisted=True,
        progress_persisted=True)
    for key in ('observed_value', 'plan_artifact', 'snapshot_artifact', 'search_artifact',
                'dispatch_outcome', 'error_type', 'error', 'close_error'):
        if key in last:
            result[key] = last[key]
    return result


def _task(context):
    return None if context['task_evidence'].startswith('physical address') else context['task_id']


def _selected_mapping(original_capture, scalar_capture, address, width):
    """The fresh scalar must retain the observed subset of the original map.

    A context hash for a smaller region is necessarily different. Comparing
    actual masked PDE/PTE observations, rather than accepting that new hash,
    prevents a remap between the whole-region and selected-scalar captures
    from being adopted as a new candidate. Page activity was normalized by the
    capture adapter; permissions and physical frames remain significant.
    """
    original, current = original_capture['mapping'], scalar_capture['mapping']
    if original['kind'] == 'physical-addresses':
        if original != current or original_capture['pages'] or scalar_capture['pages']:
            raise ValueError('Selected scalar physical address domain changed')
        return
    low, high = address & ~4095, (address + width - 1) & ~4095
    expected = [page for page in original_capture['pages'] if low <= int(page['linear'], 0) <= high]
    if (len(expected) != (high - low) // 4096 + 1 or expected != scalar_capture['pages']
            or {key: value for key, value in original.items() if key not in ('pages_sha256', 'page_count')}
            != {key: value for key, value in current.items() if key not in ('pages_sha256', 'page_count')}):
        raise ValueError('Selected scalar mapping changed after the original context check')


def _finish(session, identifier, rule, progress_id, progress, *, phase, reason, last):
    status = 'active'
    if progress['attempts'] >= rule['max_applications']:
        status, reason = 'exhausted', 'application_budget'
    elif progress['ticks'] >= rule['max_ticks']:
        status, reason = 'exhausted', 'tick_budget'
    updated = _next(progress, status=status, phase=phase, reason=reason, last=last)
    progress_id, updated = _save(session.project, identifier, session.run_id, progress_id, updated, session=session)
    return _response(identifier, progress_id, updated, fresh=True)


def _failure(session, identifier, progress_id, progress, error, *, uncertain, fresh=True):
    last = dict(progress['last'], applied=False, error_type=type(error).__name__, error=str(error)[:2048],
                dispatch_outcome='unknown' if uncertain else 'not_dispatched')
    if uncertain:
        try:
            close = getattr(session, 'close', None)
            if close is None:
                close = session.vm.close
            close()
        except Exception as close_error:
            last['close_error'] = str(close_error)[:2048]
    updated = _next(progress, status='uncertain' if uncertain else 'disabled', phase='failed',
                    reason='uncertain_dispatch' if uncertain else 'context_or_guard_failure', last=last)
    try:
        final_id, updated = _save(session.project, identifier, session.run_id, progress_id, updated, session=session)
        return _response(identifier, final_id, updated, fresh=fresh)
    except Exception as journal_error:
        # The last durable record remains pending. Even if this process ends,
        # another tick will refuse to replay it. Keep a live terminal guard too.
        blocked = getattr(session, '_memory_rule_blocked', None)
        if blocked is None:
            blocked = session._memory_rule_blocked = {}
        result = _response(identifier, progress_id, updated, fresh=fresh)
        result.update(progress_persisted=False, journal_error=str(journal_error)[:2048])
        blocked[identifier] = result
        return result


class MemoryRuleProjectMixin:
    """Create/read rules and their history without launching or resuming a VM."""

    def memory_rule_create(self, search, *, offset, value, condition='always', compare_value=None,
                           max_applications=128, max_ticks=4096, name='memory-rule'):
        _name(name)
        _integer(max_applications, 'max_applications', 1, MAX_APPLICATIONS)
        _integer(max_ticks, 'max_ticks', 1, MAX_TICKS)
        row, envelope, data, metadata = _search(self, search)
        original = plan_edit(envelope['state'], data, metadata['snapshot'], offset=offset, value=value,
                             condition=condition, compare_value=compare_value)
        rule = dict(format='fdisbull-memory-rule-1', name=name, created_at=_stamp(),
            origin_search_artifact=search, origin_snapshot_artifact=envelope['snapshot_artifact'],
            origin_context=metadata['snapshot']['context'], origin_state_sha256=envelope['state']['state_sha256'],
            origin_snapshot_sha256=metadata['snapshot']['snapshot_sha256'], spec=envelope['state']['spec'],
            offset=offset, action=dict(value=value, condition=condition,
                                      compare_value=original['condition']['compare_value']),
            max_applications=max_applications, max_ticks=max_ticks)
        artifact = self._debug_artifact(row['run'], 'memory-rule.json', 'memory-rule', _json(rule),
            dict(format=rule['format'], origin_search_artifact=search))
        identifier = artifact['artifact']
        initial = dict(format='fdisbull-memory-rule-progress-1', rule_artifact=identifier, run_id=row['run'],
            sequence=0, status='active', phase='created', reason=None, ticks=0, attempts=0, applications=0, last={})
        progress_id, initial = _save(self, identifier, row['run'], None, initial)
        return _brief(artifact, rule=rule, progress_artifact=progress_id, progress=initial,
                      execution='not_run', assistance='host snapshot, conditional plan and guarded write')

    def memory_rule_info(self, rule):
        row, configuration = _rule(self, rule)
        progress_id, progress = _progress(self, rule, configuration, row['run'])
        return dict(artifact=rule, run=row['run'], rule=configuration,
                    progress_artifact=progress_id, progress=progress)


def _rule_run_operation(function):
    """Acquire the native machine under the same outer deadline as its RPCs."""
    @wraps(function)
    def invoke(self, *args, **kwargs):
        if hasattr(self, 'vm'):
            from .qemu_machine import machine_trace_operation
            @wraps(function)
            def native_bound(session, *inner_args, **inner_kwargs):
                previous = getattr(session, '_rpc_deadline', None)
                session._rpc_deadline = min(previous, session._deadline) if previous is not None else session._deadline
                try:
                    return function(session, *inner_args, **inner_kwargs)
                finally:
                    session._rpc_deadline = previous
            return machine_trace_operation(native_bound, label='Periodic memory rule')(self, *args, **kwargs)
        return _locked(rpc_budget(function))(self, *args, **kwargs)
    return invoke


class MemoryRuleSessionMixin:
    """Explicit ticks; every possible write has a new one-shot expected-byte plan."""

    @_locked
    def memory_rule_tick(self, rule):
        row, configuration = _rule(self.project, rule)
        if row['run'] != self.run_id:
            raise ValueError('Memory rule belongs to a different live run')
        blocked = getattr(self, '_memory_rule_blocked', {}).get(rule)
        if blocked is not None:
            return dict(deepcopy(blocked), applied=False, tick_executed=False)
        progress_id, progress = _progress(self.project, rule, configuration, self.run_id)
        if progress['status'] in _TERMINAL:
            return _response(rule, progress_id, progress)
        if progress['status'] == 'pending':
            return _failure(self, rule, progress_id, progress,
                ValueError('Previous rule operation lacks a completion receipt; replay refused'), uncertain=True, fresh=False)
        pending = _next(progress, status='pending', phase='tick-started', reason=None,
                        ticks=progress['ticks'] + 1, last=dict(applied=False, origin_search_artifact=configuration['origin_search_artifact']))
        progress_id, pending = _save(self.project, rule, self.run_id, progress_id, pending, session=self)
        plan_id, dispatched = None, False
        try:
            original = configuration['origin_context']
            region = original['region']
            # Qualify the original complete region's mapping. Do not store a
            # multi-MiB duplicate per tick: only the selected scalar is retained
            # if an edit is actually required.
            _, identity, original_capture = _capture(self, region['start'], region['length'],
                                                     original['address_space'], _task(original))
            if _json(identity) != _json(original):
                raise ValueError('Original memory rule task, mapping or epoch changed')
            address, width = region['start'] + configuration['offset'], configuration['spec']['width']
            raw, context, capture = _capture(self, address, width, original['address_space'], _task(original))
            _selected_mapping(original_capture, capture, address, width)
            if ({key: value for key, value in context.items() if key not in ('region', 'mapping_id')}
                    != {key: value for key, value in original.items() if key not in ('region', 'mapping_id')}):
                raise ValueError('Selected scalar left its original task or epoch')
            snapshot = snapshot_metadata(raw, context=context, capture_id=uuid.uuid4().hex, captured_at=_stamp())
            spec = configuration['spec']
            options = dict(width=spec['width'], signed=spec['signed'], byteorder=spec['byteorder'],
                           bias=spec['bias'], stride=1, mode='unknown')
            selected = start_search(raw, snapshot, **options)
            planned = plan_edit(selected, raw, snapshot, offset=0, **configuration['action'])
            last = dict(pending['last'], observed_value=planned['condition']['observed_value'],
                        predicate=planned['condition'], dispatch_outcome='not_dispatched',
                        observation_sha256=snapshot['snapshot_sha256'])
            if not planned['eligible']:
                return _finish(self, rule, configuration, progress_id, pending,
                               phase='observed', reason='condition_not_satisfied', last=last)
            if planned['expected_hex'] == planned['replacement_hex']:
                return _finish(self, rule, configuration, progress_id, pending,
                               phase='observed', reason='already_value', last=last)
            scalar = self._artifact('memory-rule-scalar.bin', 'memory-snapshot', raw,
                dict(snapshot=snapshot, capture=capture, rule_origin=dict(rule_artifact=rule,
                     search_artifact=configuration['origin_search_artifact'], offset=configuration['offset'])))
            searched = self.project.memory_search_start(scalar['artifact'], **options)
            edit = self.project.memory_edit_plan(searched['artifact'], offset=0, **configuration['action'])
            if edit['plan'] != planned:
                raise ValueError('Retained one-shot plan differs from the observed scalar plan')
            plan_id = edit['artifact']
            last.update(snapshot_artifact=scalar['artifact'], search_artifact=searched['artifact'], plan_artifact=plan_id)
            pending = _next(pending, attempts=pending['attempts'] + 1, phase='write-pending', last=last)
            progress_id, pending = _save(self.project, rule, self.run_id, progress_id, pending, session=self)
            receipt = self.memory_apply(plan_id)
            dispatched = True
            if receipt.get('applied') is not True or receipt.get('verified') is not True:
                raise ValueError('Fresh conditional memory write did not return verified success')
            pending['applications'] += 1
            last.update(applied=True, dispatch_outcome=receipt['dispatch_outcome'], write_receipt=receipt)
            return _finish(self, rule, configuration, progress_id, pending,
                           phase='write-complete', reason='applied', last=last)
        except Exception as error:
            uncertain = dispatched or (plan_id is not None and plan_id in getattr(self, '_applied_memory_plans', set()))
            return _failure(self, rule, progress_id, pending, error, uncertain=uncertain)

    @_rule_run_operation
    def memory_rule_run(self, rule, *, ticks, interval_ms=100, timeout_ms=10000):
        """Run a finite guest-time sequence, first tick immediately.

        Subsequent ticks follow DOSBox guest-time slices or the explicitly
        selected QEMU virtual clock, not a guaranteed wall-clock frequency.
        A nonordinary native stop or host timeout ends this invocation without
        an extra edit.
        """
        _integer(ticks, 'ticks', 1, MAX_TICKS)
        _integer(interval_ms, 'interval_ms', 1, 60000)
        _integer(timeout_ms, 'timeout_ms', 1, 60000)
        backend = getattr(self, 'backend_name', None) or self.metadata.get('backend')
        # The ordinary DOSBox DebugSession predates an explicit backend_name.
        # Native QEMU contexts use a separately admitted virtual-clock contract.
        qemu = hasattr(self, 'vm')
        if not qemu and backend not in (None, 'dosbox', 'dosbox-qemu'):
            raise ValueError('Periodic guest-time memory rules require the DOSBox backend')
        if qemu:
            from .qemu_memory_rules import admit_native_rule_run
            admit_native_rule_run(self)
        row, configuration = _rule(self.project, rule)
        if row['run'] != self.run_id:
            raise ValueError('Memory rule belongs to a different live run')
        if qemu:
            from .qemu_memory_rules import preflight
            preflight(self, configuration)
        # rpc_budget intersects this allowance with any outer operation. All
        # nested snapshot/read/edit RPCs share it; time is never renewed per tick.
        deadline = self._rpc_deadline
        completed, recent, outcome = 0, [], 'host_timeout'
        last = None
        clock_stop = None
        while completed < ticks:
            if time.monotonic() >= deadline:
                break
            last = self.memory_rule_tick(rule)
            if last['tick_executed']:
                completed += 1
                recent.append(dict(progress_artifact=last['progress_artifact'], applied=last['applied']))
                recent = recent[-16:]
            if last['status'] != 'active':
                outcome = 'rule_' + last['status'] if last['status'] != 'uncertain' else 'uncertain'
                break
            if completed == ticks:
                outcome = 'tick_budget_complete'
                break
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining < 1:
                break
            progress_id, progress = _progress(self.project, rule, configuration, self.run_id)
            waiting = _next(progress, status='pending', phase='execution-pending', reason=None)
            progress_id, waiting = _save(self.project, rule, self.run_id, progress_id, waiting, session=self)
            try:
                if qemu:
                    from .qemu_clock import clock_timer_stop_is_ordinary
                    elapsed = self.clock_advance(interval_ms * 1_000_000, timeout_ms=max(1, remaining))
                    ordinary = clock_timer_stop_is_ordinary(elapsed)
                    native_outcome = elapsed.get('outcome') if isinstance(elapsed, dict) else None
                    if not isinstance(native_outcome, str):
                        raise ValueError('Virtual clock slice returned no qualified outcome')
                    outcome = 'guest_time' if ordinary else 'clock_interrupted'
                    if not ordinary:
                        clock_stop = deepcopy(elapsed)
                    terminal = native_outcome in ('guest_exit', 'guest_tsr') or (
                        isinstance(elapsed.get('process'), dict) and
                        elapsed['process'].get('state') in ('guest_exit', 'guest_tsr', 'exited'))
                    guest_slice = dict(outcome=native_outcome, requested_virtual_ns=interval_ms * 1_000_000,
                                       clock_stop=deepcopy(elapsed))
                else:
                    elapsed = self.run(guest_ms=interval_ms, timeout_ms=max(1, remaining),
                                       fast_forward=False, stop_on_hook=True)
                    if type(elapsed) is not dict or type(elapsed.get('outcome')) is not str:
                        raise ValueError('Guest slice returned no qualified outcome')
                    outcome = elapsed['outcome']
                    if outcome == 'guest_time':
                        if (elapsed.get('session', {}).get('state') != 'stopped'
                                or type(elapsed.get('guest_elapsed_ms')) not in (int, float)
                                or not elapsed['guest_elapsed_ms'] >= interval_ms):
                            raise ValueError('Guest slice did not establish its time budget and paused endpoint')
                    terminal = outcome in ('guest_exit', 'guest_tsr')
                    guest_slice = dict(outcome=outcome, guest_elapsed_ms=elapsed.get('guest_elapsed_ms'),
                                       requested_guest_ms=interval_ms)
                status = 'disabled' if terminal else 'active'
                resumed = _next(waiting, status=status, phase='execution-complete' if outcome == 'guest_time' else 'interrupted',
                                reason=None if outcome == 'guest_time' else outcome,
                                last=dict(waiting['last'], guest_slice=guest_slice))
                progress_id, resumed = _save(self.project, rule, self.run_id, progress_id, resumed, session=self)
                if outcome != 'guest_time':
                    break
            except Exception as error:
                last = _failure(self, rule, progress_id, waiting, error, uncertain=True, fresh=False)
                outcome = 'uncertain'
                break
        progress_id, progress = _progress(self.project, rule, configuration, self.run_id)
        result = dict(rule_artifact=rule, progress_artifact=progress_id, outcome=outcome,
                    complete=completed == ticks and outcome in ('tick_budget_complete', 'rule_exhausted'),
                    requested_ticks=ticks, completed_ticks=completed, interval_ms=interval_ms,
                    timeout_ms=timeout_ms, recent_ticks=recent, progress=progress,
                    assistance='bounded host snapshot/edit sequence; not an installed timer or original Game Wizard code')
        if qemu:
            result['clock_domain'] = 'qemu-virtual-ns'
        if clock_stop is not None:
            result['clock_stop'] = clock_stop
        return result
