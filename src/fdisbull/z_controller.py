"""One retained Project/DebugSession with reloadable, trusted Python Z actions.

The explicitly selected action file is arbitrary trusted Python, not a sandbox.
It exports ACTIONS = {'look': {'handler': look, 'description': 'Observe',
'entry': 'known scene', 'next_state': 'same scene'}}. Handlers take (ctx, **params).
Metadata describes the contract; handlers must check their actual entry state.
Keep target mutable state in ctx.state; the project/session also survive reloads,
while action-module globals do not. Compose with ctx.invoke('verb', **params).

JSON-lines requests use {"id": ..., "verb": ..., "params": {...}}. Reserved verbs
are list, call, run, frame and close. Raw call deliberately returns the complete
backend reply; action authors can consume it and return compact witnesses. Target
Python may have arbitrary side effects or block: its execution is not preempted,
and failed actions are never automatically rolled back or retried.
"""

from contextlib import contextmanager, redirect_stdout
from collections import Counter
import base64
import inspect
import json
import math
from pathlib import Path
import sys
import threading
import time
from types import ModuleType
import uuid


BUILTINS = {
    'list': 'List freshly loaded action contracts',
    'call': 'Explicit raw backend call through the owned session',
    'run': 'Run with an explicit guest-time budget and host deadline',
    'frame': 'Capture a retained frame; optionally export it',
    'expect-frame': 'Compare a stable rectangle of the stored guest frame with a reference; stop on mismatch',
    'serializer-candidates': 'Extract bounded candidate state bindings from identified x86-32 serializer callers',
    'serializer-discovery': 'Find loaded filename anchors, caller ranges and register ABI candidates without a source mapping',
    'invoke-native': 'Call a signature-checked original flat32 near-return routine at a caller-qualified boundary',
    'capture-native-call': 'Observe an original near call, its actual inputs, return and bounded continuation',
    'invoke-captured-call': 'Replay an observed original call in its live runtime without Save/Load UI input',
    'native-capture-watch': 'Keep owned candidate callsite breakpoints armed across separate UI actions; explicitly finish a hit',
    'work-queue': 'Add small dependent tasks, publish facts and inspect ready work',
    'run-work': 'Execute one explicitly selected ready operation; never automatically retry effects',
    'operation-goal': 'Validate a formal UIL operation goal, propagate required UDL recovery work backward and optionally feed the queue',
    'record-frontier': 'Inventory labeled files and surface independent repeating-record work beside runtime blockers',
    'record-rows': 'Read bounded raw-preserving rows from one explicitly identified file',
    'sample-contexts': 'Sample short normal-speed execution contexts while preserving debugger stops',
    'capture-action': 'Retain a named recipe of existing verbs; optionally execute once with before/after frames',
    'observe-state': 'Record an explicit scene/state observation; never inferred from a successful click',
    'close': 'Close the owned debugger and project',
}
MAX_REQUEST_BYTES = 1024 * 1024


class FrameExpectationError(ValueError):
    """A failed comparison with retained, JSON-ready observation evidence."""

    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(f"frame expectation failed: {diagnostic['reason']}; "
                         f"mean_error={diagnostic['mean_error']}; "
                         f"frame={diagnostic['frame']['path']}")


def _parameter_contract(function, *, skip=(), skip_first=False):
    """Expose accepted keyword names so discovery does not require source reading."""
    required, optional = [], {}
    try:
        parameters = list(inspect.signature(function).parameters.items())
    except (TypeError, ValueError):
        return {'unavailable': 'callable has no inspectable signature'}
    for name, parameter in parameters[1:] if skip_first else parameters:
        if name in skip or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.default is parameter.empty:
            required.append(name)
        else:
            try:
                json.dumps(parameter.default, allow_nan=False)
                optional[name] = parameter.default
            except (TypeError, ValueError):
                optional[name] = {'default_repr': repr(parameter.default)}
    return {'required': required, 'optional': optional}


def _bounded(value, label, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f'{label} must be an integer in 1..{maximum}')


def _record_frontier_summary(result):
    """Bound previews, not the retained analysis or its unknown observations."""
    def counts(rows):
        return dict(Counter(row['kind'] for row in rows))

    def omitted(total, shown):
        return {'total': total, 'returned': shown, 'omitted': max(0, total - shown)}

    changes = [row for row in result['changes'] if row['kind'] != 'same_bytes']
    change_preview = []
    for row in changes[:12]:
        source = row['after'] or row['before']
        change_preview.append({'source_label': source['label'], 'path': source['path'],
                               'relative_path': row['relative_path'], 'kind': row['kind'],
                               'before_size': row['before']['size'] if row['before'] else None,
                               'after_size': row['after']['size'] if row['after'] else None})
    shared = sorted(result['shared_record_counts'], key=lambda row: (
        -sum(file['name_supported'] for file in row['files']),
        -len(row['files']), -row['record_count']))
    shared_preview = []
    for row in shared[:4]:
        files = sorted(row['files'], key=lambda file: not file['name_supported'])
        shared_preview.append({key: row[key] for key in
                               ('source_label', 'source_root', 'record_count', 'basis')} | {
            'files': files[:6], 'file_preview': omitted(len(files), min(6, len(files)))})
    tasks = []
    for row in result['ready_tasks'][:8]:
        task = {key: value for key, value in row.items() if key not in ('candidate', 'also_sources')}
        candidate = row['candidate']
        task['candidate'] = ({key: value for key, value in candidate.items() if key != 'examples'} | {
            'examples': candidate['examples'][:2],
            'examples_omitted': max(0, len(candidate['examples']) - 2)}) if candidate else None
        if row.get('also_sources'):
            task['also_sources'] = row['also_sources'][:4]
            task['also_sources_omitted'] = max(0, len(row['also_sources']) - 4)
        tasks.append(task)
    return {'format': 'fdisbull-record-frontier-summary-1', 'status': result['status'],
            'sources': [{'label': source['label'], 'root': source['path'],
                         'files': len(source['files']), 'files_truncated': source['files_truncated'],
                         'errors': len(source['errors'])} for source in result['sources']],
            'change_counts': counts(result['changes']), 'changes': change_preview,
            'source_comparisons': [{'before_label': row['before_label'], 'after_label': row['after_label'],
                                   'change_counts': counts(row['files'])}
                                  for row in result['source_comparisons']],
            'shared_record_counts': shared_preview, 'ready_tasks': tasks,
            'blocked_tasks': result['blocked_tasks'], 'errors': result['errors'][:8],
            'limits': result['limits'],
            'previews': {'non_same_changes': omitted(len(changes), len(change_preview)),
                         'shared_record_counts': omitted(len(shared), len(shared_preview)),
                         'ready_tasks': omitted(result['limits']['ready_tasks_total'], len(tasks)),
                         'errors': omitted(len(result['errors']), min(8, len(result['errors'])))},
            'claim': 'Bounded previews; omitted rows remain in the raw artifact. Layouts and shared counts are candidates.'}


@contextmanager
def _action_import_path(path):
    # Only this explicitly trusted source directory, never automatic game discovery.
    entry = str(path)
    sys.path.insert(0, entry)
    try:
        yield
    finally:
        if entry in sys.path:
            sys.path.remove(entry)


class ZContext:
    """Persistent target state and existing owned runtime operations."""

    def __init__(self, controller, project, session, root):
        self._controller = controller
        self.p = project
        self.d = session
        self.root = root
        self.state = {}
        self.request_started_ns = None

    def invoke(self, verb, **params):
        """Compose an action using this request's already loaded generation."""
        return self._controller._invoke(verb, params)

    def call(self, method, params=None):
        if not isinstance(method, str) or not method.strip():
            raise ValueError('method must be a nonempty backend method name')
        if params is not None and not isinstance(params, dict):
            raise ValueError('raw call params must be an object')
        if params and 'session_id' in params:
            raise ValueError('the controller supplies its owned session_id')
        return self.d.call(method, params)

    def run(self, *, guest_ms, timeout_ms=10000, fast_forward=True, stop_on_hook=False):
        """Guest time is required; host time and input hold are separate limits."""
        _bounded(guest_ms, 'guest_ms', 3600000)
        _bounded(timeout_ms, 'timeout_ms', 600000)
        if type(fast_forward) is not bool or type(stop_on_hook) is not bool:
            raise ValueError('fast_forward and stop_on_hook must be boolean')
        result = self.d.run(guest_ms=guest_ms, timeout_ms=timeout_ms,
                            fast_forward=fast_forward, stop_on_hook=stop_on_hook)
        keys = ('outcome', 'timed_out', 'requested_guest_ms', 'guest_elapsed_ms',
                'host_elapsed_ms', 'fast_forward', 'stop', 'hook_hits')
        return {key: result[key] for key in keys if key in result}

    def frame(self, name=None, *, output=None, grid=None, boxes=None):
        if grid is not None and (type(grid) is not int or not 10 <= grid <= 512):
            raise ValueError('grid must be a pixel spacing in 10..512')
        name = name or f'z-frame-{time.monotonic_ns()}.png'
        result = self.d.screenshot(name)
        frame = {key: result[key] for key in ('artifact', 'name', 'sha256') if key in result}
        metadata = result.get('metadata', {})
        frame.update({key: metadata[key] for key in
                      ('width', 'height', 'frame_id', 'mode_id', 'captured_ticks')
                      if key in metadata})
        if output is not None or grid is not None:
            output = output or f'evidence/{name}'
            destination = Path(output)
            if not destination.is_absolute():
                destination = self.root / destination
            self.p.debug_export(result['artifact'], destination)
            frame['path'] = str(destination)
            if grid is not None:
                from .z_capture import coordinate_grid
                frame['grid'] = coordinate_grid(destination, destination.with_name(destination.stem + '-grid.png'),
                                                spacing=grid, boxes=boxes or ())
        return frame

    def dos_click(self, x, y, **options):
        """Use the shared DOS helper without copying its target-input mechanics."""
        from .z_dos import click_at_dos_mouse_poll
        return click_at_dos_mouse_poll(self.d, x, y, **options)

    def expect_frame(self, reference, box, *, max_mean_error=0):
        """Check a caller-chosen stable region; do not run, input or infer a scene."""
        from PIL import Image, ImageChops, ImageStat

        if (not isinstance(box, (list, tuple)) or len(box) != 4
                or any(type(value) is not int for value in box)
                or not 0 <= box[0] < box[2] or not 0 <= box[1] < box[3]):
            raise ValueError('box must be integer [left, top, right, bottom] with positive area')
        if (type(max_mean_error) not in (int, float) or not math.isfinite(max_mean_error)
                or not 0 <= max_mean_error <= 255):
            raise ValueError('max_mean_error must be a finite number in 0..255')
        reference = Path(reference)
        if not reference.is_absolute():
            reference = self.root / reference
        with Image.open(reference) as expected:
            reference_size = expected.size
            if box[2] > expected.width or box[3] > expected.height:
                raise ValueError('box extends outside the reference image')
            expected_crop = expected.convert('RGB').crop(box)
        stem = f'expect-frame-{time.monotonic_ns()}'
        frame = self.frame(stem + '.png', output=f'evidence/{stem}.png')
        result = {'matched': False, 'reference': str(reference), 'box': list(box),
                  'metric': 'mean absolute RGB channel error, 0..255',
                  'mean_error': None, 'max_mean_error': max_mean_error,
                  'reference_size': list(reference_size), 'frame': frame,
                  'claim': 'Stored frame rectangle comparison only; no semantic scene label is inferred.'}
        with Image.open(frame['path']) as actual:
            result['frame_size'] = list(actual.size)
            if actual.size != reference_size:
                result['reason'] = 'image_size_mismatch'
            else:
                difference = ImageChops.difference(actual.convert('RGB').crop(box), expected_crop)
                result['mean_error'] = sum(ImageStat.Stat(difference).mean) / 3
                result['matched'] = result['mean_error'] <= max_mean_error
                result['reason'] = 'within_threshold' if result['matched'] else 'mean_error_exceeded'
        path = self._retain_analysis('frame_expectation', result, f'evidence/{stem}.json')
        result = result | {'path': path}
        if not result['matched']:
            raise FrameExpectationError(result)
        return result

    def _retain_analysis(self, key, result, output):
        self.state[key] = result
        if output is None:
            return None
        destination = Path(output)
        if not destination.is_absolute():
            destination = self.root / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2) + '\n')
        return str(destination)

    def serializer_candidates(self, *, summary=False, output=None, **options):
        """Analyze explicit native code ranges and known serializer register ABIs."""
        from .serializer_candidates import extract_serializer_candidates, summarize_serializer_candidates
        from .z_dos import read_linear

        if type(summary) is not bool:
            raise ValueError('summary must be boolean')

        def read_bytes(address, size):
            result = read_linear(self.d, address, size)
            return base64.b64decode(result['data_base64'], validate=True)

        result = extract_serializer_candidates(read_bytes, **options)
        path = self._retain_analysis('serializer_candidates', result, output)
        reply = summarize_serializer_candidates(result) if summary else result
        return reply | {'path': path} if path is not None else reply

    def observe_state(self, state, observation):
        if not isinstance(state, dict) or not state or not isinstance(observation, (str, dict)) or not observation:
            raise ValueError('state needs explicit values and a nonempty observation or evidence reference')
        self.state.update(state)
        return {'state': state, 'observation': observation, 'source': 'caller observation'}

    def serializer_discovery(self, *, summary=True, output='evidence/serializer-discovery.json', **options):
        from .serializer_discovery import discover_serializer_calls
        from .z_dos import read_linear
        def read_bytes(address, size):
            return base64.b64decode(read_linear(self.d, address, size)['data_base64'], validate=True)
        if type(summary) is not bool:
            raise ValueError('summary must be boolean')
        result = discover_serializer_calls(read_bytes, **options)
        self.state['serializer_discovery'] = result
        destination = Path(output)
        if not destination.is_absolute():
            destination = self.root / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2) + '\n')
        if not summary:
            return {**result, 'path': str(destination)}
        compact = {key: result[key] for key in ('format', 'address_space', 'status', 'anchors', 'callers',
                                               'serializer_targets', 'issues', 'next_step', 'scope')}
        return compact | {'path': str(destination), 'reference_count': len(result['references']),
                          'call_count': len(result['calls'])}

    def invoke_native(self, **options):
        from .z_native import invoke_native
        return invoke_native(self, **options)

    def _work_queue(self):
        from .z_queue import DependencyQueue
        return DependencyQueue.load(self.root / 'work.z.json')

    def native_capture_watch(self, op='status', **options):
        from .z_capture_watch import native_capture_watch
        return native_capture_watch(self, op=op, **options)

    def operation_goal(self, document, goal, *, available=None, enqueue=False, output=None):
        from .operation_goals import load_operation_goals, plan_operation, queue_frontier
        if type(enqueue) is not bool:
            raise ValueError('enqueue must be boolean')
        if isinstance(document, str):
            path = Path(document)
            document = load_operation_goals(path if path.is_absolute() else self.root / path)
        queue = self._work_queue()
        facts = queue.snapshot()['facts']
        if available is None:
            available = list(facts)
        plan = plan_operation(document, goal, available=available)
        frontier = queue_frontier(plan)
        if enqueue:
            # The frontier is data only: validate the whole merge in memory
            # before atomically replacing the retained queue.
            destination = queue.path
            staged = type(queue)()
            staged._state = queue.snapshot()
            queue = staged
            # Add declared producers before publishing their result facts.
            existing = queue.snapshot()['tasks']
            for task in frontier['tasks']:
                if task['id'] in existing:
                    previous = existing[task['id']]
                    if any(previous[key] != task[key] for key in ('requires', 'produces')):
                        raise ValueError('existing queue task has a different operation-goal definition')
                else:
                    queue.add_task(**task)
            for fact in frontier['facts']:
                queue.publish(**fact)
            queue.save(destination)
        output = output or f'evidence/operation-goal-{time.monotonic_ns()}.json'
        path = self._retain_analysis('operation_goal', plan, output)
        return {'format': plan['format'], 'goal': goal, 'definition_sha256': plan['definition_sha256'],
                'path': path, 'ready': plan['ready'][:16], 'blocked': plan['blocked'][:16],
                'ready_total': len(plan['ready']), 'blocked_total': len(plan['blocked']),
                'known_block_count': len(plan['known_blocks']), 'coverage': plan['coverage'],
                'enqueued': enqueue, 'queue': queue.summary() if enqueue else None,
                'scope': plan['scope']}

    def work_queue(self, op='status', **options):
        queue = self._work_queue()
        methods = {'add': 'add_task', 'publish': 'publish', 'claim': 'claim',
                   'complete': 'complete', 'fail': 'fail', 'retry': 'retry'}
        if op in ('status', 'ready'):
            if options:
                raise ValueError('status and ready take no extra parameters')
            return queue.summary() if op == 'status' else {'ready': queue.ready()}
        if op not in methods:
            raise ValueError('op must be add, publish, claim, complete, fail, retry, ready or status')
        result = getattr(queue, methods[op])(**options)
        return {'result': result, 'queue': queue.summary()}

    def _publish_native_contract(self, name, contract, path):
        queue = self._work_queue()
        # Only observed outputs release dependents. A decoded target is not a
        # successful return, and an observed return is not scene initialization.
        if contract.get('entry_conditions', {}).get('registers'):
            queue.publish('native-entry:' + name, {'path': path}, evidence=path)
        if contract.get('return_registers'):
            queue.publish('native-call:' + name, {'path': path}, evidence=path)
        if any(row.get('after_registers') for row in contract.get('continuation', [])):
            queue.publish('native-continuation:' + name, {'path': path}, evidence=path)
        changes = contract.get('argument_changes', {})
        if changes.get('bytes_changed', 0):
            queue.publish('native-buffer-change:' + name,
                {'path': path, 'sampled_bytes_changed': changes['bytes_changed']}, evidence=path)

    def capture_native_call(self, name, callsite, code_selector, *, trigger=None,
                            summary=True, output=None, **options):
        from .z_call_contract import capture_native_call
        from .z_argument_changes import summarize_argument_changes
        if type(summary) is not bool:
            raise ValueError('summary must be boolean')
        if trigger is not None:
            if (not isinstance(trigger, dict) or set(trigger) - {'verb', 'params'}
                    or not isinstance(trigger.get('verb'), str)
                    or not isinstance(trigger.get('params', {}), dict)):
                raise ValueError('trigger needs verb and optional params')
            action = lambda: self.invoke(trigger['verb'], **trigger.get('params', {}))
        else:
            action = None
        try:
            contract = capture_native_call(self, name, callsite, code_selector, trigger=action, **options)
        except Exception:
            partial = self.state.get('native_capture_pending')
            if partial and partial.get('name') == name:
                partial['argument_changes'] = summarize_argument_changes(partial)
                path = self._retain_analysis('native_contract_partial', partial,
                    output or f'evidence/native-contract-partial-{time.monotonic_ns()}.json')
                self._publish_native_contract(name, partial, path)
            raise
        contract['argument_changes'] = summarize_argument_changes(contract)
        output = output or f'evidence/native-contract-{time.monotonic_ns()}.json'
        path = self._retain_analysis('native_contract', contract, output)
        self._publish_native_contract(name, contract, path)
        if not summary:
            return contract | {'path': path}
        entry = contract.get('entry_conditions', {})
        return {key: value for key, value in contract.items() if key not in (
            'entry_conditions', 'arguments', 'post_arguments', 'continuation', 'return_registers')} | {
            'path': path, 'entry_conditions': {key: value for key, value in entry.items()
                                               if key not in ('registers', 'stack')},
            'arguments': [{'register': row['register'], 'value': row['value'],
                           'c_string': (row.get('pointer_hypothesis') or {}).get('c_string'),
                           'pointer_read_error': row.get('pointer_read_error')}
                          for row in contract.get('arguments', [])],
            'continuation': [row['instruction'] for row in contract.get('continuation', [])],
            'returned_eax': contract.get('return_registers', {}).get('general', {}).get('eax')}

    def invoke_captured_call(self, name=None, *, contract=None, output=None, **options):
        from .z_call_contract import invoke_captured_call
        if contract is None:
            contract = self.state.get('native_call_contracts', {}).get(name)
            if contract is None:
                raise ValueError('unknown captured name; pass an existing contract path or capture in this owner')
        elif isinstance(contract, str):
            source = Path(contract)
            contract = json.loads((source if source.is_absolute() else self.root / source).read_text())
        result = invoke_captured_call(self, contract, **options)
        output = output or f'evidence/native-replay-{time.monotonic_ns()}.json'
        path = self._retain_analysis('native_replay', result, output)
        key = name or contract['name']
        self._work_queue().publish('native-replay:' + key, {'path': path}, evidence=path)
        return result | {'path': path}

    def run_work(self, id=None):
        queue = self._work_queue()
        ready = queue.ready()
        if id is None:
            if not ready:
                return {'status': 'no_ready_work', 'queue': queue.summary()}
            id = ready[0]['id']
        task = queue.claim(id)
        operation = task.get('operation')
        if operation and operation['verb'] in ('run-work', 'close'):
            queue.fail(id, 'queue operations cannot recursively run work or close the owner')
            raise ValueError('recursive run-work and close are not queue operations')
        if not operation:
            queue.fail(id, 'task has no executable operation; use explicit claim/complete for manual work')
            raise ValueError('selected task has no operation')
        try:
            result = self.invoke(operation['verb'], **operation.get('params', {}))
            json.dumps(result, allow_nan=False)
        except Exception as error:
            # Reload: the operation may have published useful partial outputs.
            queue = self._work_queue()
            if queue.snapshot()['tasks'][id]['status'] == 'running':
                queue.fail(id, str(error))
            raise
        queue = self._work_queue()
        try:
            queue.complete(id)
            status = 'completed'
        except ValueError as error:
            # Successful effects are never repeated merely to fill an output.
            current = queue.snapshot()['tasks'][id]
            if current['status'] == 'running':
                status = 'awaiting_outputs'
            else:
                if current['status'] != 'failed':
                    queue.claim(id)
                    queue.fail(id, 'operation completed after its inputs changed; review before retry: ' + str(error))
                status = 'needs_review'
        return {'id': id, 'status': status, 'result': result, 'queue': queue.summary()}

    def record_frontier(self, *, summary=True, output=None, **options):
        from .record_candidates import record_frontier
        if type(summary) is not bool:
            raise ValueError('summary must be boolean')
        previous = options.get('previous')
        if isinstance(previous, str):
            source = Path(previous)
            options['previous'] = json.loads((source if source.is_absolute() else self.root / source).read_text())
        result = record_frontier(**options)
        if output is None:
            output = f'evidence/record-frontier-{time.monotonic_ns()}.json'
        path = self._retain_analysis('record_frontier', result, output)
        if not summary:
            return {**result, 'path': path}
        return _record_frontier_summary(result) | {'path': path}

    def record_rows(self, *, summary=False, output=None, **options):
        from .record_candidates import read_record_rows
        if type(summary) is not bool:
            raise ValueError('summary must be boolean')
        result = read_record_rows(**options)
        path = self._retain_analysis('record_rows', result, output)
        if summary:
            rows = result['rows']
            named = [row for row in rows if row.get('name')]

            def preview(row, *, raw=False):
                item = {key: row[key] for key in ('index', 'offset')}
                if row.get('name') is not None:
                    item.update(name=row['name'][:80], name_truncated=len(row['name']) > 80)
                if raw:
                    item.update(raw_prefix_hex=row['raw_hex'][:64],
                                raw_prefix_truncated=len(row['raw_hex']) > 64)
                return item

            reply = {key: result[key] for key in ('source', 'stride', 'record_count',
                                                 'start', 'next_row', 'complete', 'claim')}
            reply.update(format='fdisbull-record-rows-summary-1', returned_rows=len(rows),
                         named_rows_in_returned_range=len(named),
                         named_rows=[preview(row) for row in named[:16]],
                         named_rows_truncated=len(named) > 16,
                         example_rows=[preview(row, raw=True) for row in rows[:4]],
                         trailing_offset=result['trailing_offset'],
                         trailing_bytes=len(result['trailing_hex']) // 2)
        else:
            reply = result
        return reply | {'path': path} if path is not None else reply

    def sample_contexts(self, **options):
        from .z_dos import sample_execution_contexts
        return sample_execution_contexts(self.d, **options)


class ZController:
    """Own one dedicated project and debugger until close or stream termination.

    A failed action can leave intentional or partial guest/state changes. The next
    request retains that context for inspection and recovery. Sibling Python
    imports follow normal Python caching; the selected action file itself is
    compiled from its current bytes on every action/list request, without pycache.
    """

    def __init__(self, project, session, actions_path, *, root=None):
        self.actions_path = Path(actions_path).expanduser().resolve()
        self.ctx = ZContext(self, project, session,
                            Path(root).expanduser().resolve() if root is not None
                            else self.actions_path.parent)
        self.closed = False
        self.started_ns = time.monotonic_ns()
        self._module_name = '_fdisbull_z_actions_' + uuid.uuid4().hex
        self._active_actions = None
        self._depth = 0
        self._lock = threading.Lock()
        self.recipes_path = self.actions_path.with_suffix('.z.json')
        self._recipe_progress = []
        self._capture_progress = None

    @classmethod
    def open(cls, project_path, executable, game_dir, actions_path, *, root=None,
             debugger_options=None, project_factory=None):
        if project_factory is None:
            from .project import Project
            project_factory = Project
        project = project_factory(project_path)
        try:
            session = project.debugger(executable, game_dir, **(debugger_options or {}))
            try:
                return cls(project, session, actions_path, root=root)
            except BaseException:
                session.close()
                raise
        except BaseException:
            project.__exit__(*sys.exc_info())
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _load_actions(self):
        source = self.actions_path.read_bytes()
        code = compile(source, str(self.actions_path), 'exec', dont_inherit=True)
        module = ModuleType(self._module_name)
        module.__file__ = str(self.actions_path)
        sys.modules[self._module_name] = module
        exec(code, module.__dict__)
        declared = getattr(module, 'ACTIONS', None)
        if not isinstance(declared, dict):
            raise ValueError('trusted action module must export an ACTIONS object')
        actions = {}
        for name, spec in declared.items():
            if not isinstance(name, str) or not name.strip() or name in BUILTINS:
                raise ValueError(f'invalid or reserved action name: {name!r}')
            if not isinstance(spec, dict) or not callable(spec.get('handler')):
                raise ValueError(f'action {name!r} needs a callable handler')
            metadata = {key: spec.get(key, '') for key in ('description', 'entry', 'next_state')}
            if any(not isinstance(value, str) for value in metadata.values()):
                raise ValueError(f'action {name!r} metadata must be strings')
            actions[name] = {'handler': spec['handler'], **metadata,
                             'parameters': _parameter_contract(spec['handler'], skip_first=True)}
        from .z_capture import read_recipes, recipe_handler, validate_recipe
        for name, recipe in read_recipes(self.recipes_path).items():
            validated = validate_recipe(name, reserved=BUILTINS, **recipe)
            if name in actions:
                # Promoting a recipe to a target-specific Python operation retains
                # its input fallback on disk without shadowing the new handler.
                continue
            actions[name] = {'handler': recipe_handler(name, validated),
                             'description': 'Captured input/operation recipe',
                             'entry': recipe['entry'], 'next_state': recipe['next_state'],
                             'capture': recipe}
        return actions

    def _builtin_parameters(self):
        from .serializer_discovery import discover_serializer_calls
        from .serializer_candidates import extract_serializer_candidates
        from .record_candidates import record_frontier, read_record_rows
        from .z_native import invoke_native
        from .z_dos import sample_execution_contexts
        from .z_call_contract import capture_native_call, invoke_captured_call
        from .z_capture_watch import native_capture_watch
        handlers = {'call': self.ctx.call, 'run': self.ctx.run, 'frame': self.ctx.frame,
                    'expect-frame': self.ctx.expect_frame,
                    'capture-action': self._capture_action, 'observe-state': self.ctx.observe_state,
                    'serializer-discovery': discover_serializer_calls,
                    'serializer-candidates': extract_serializer_candidates,
                    'invoke-native': invoke_native, 'record-frontier': record_frontier,
                    'record-rows': read_record_rows, 'sample-contexts': sample_execution_contexts,
                    'capture-native-call': capture_native_call, 'invoke-captured-call': invoke_captured_call,
                    'work-queue': self.ctx.work_queue, 'run-work': self.ctx.run_work,
                    'native-capture-watch': native_capture_watch, 'operation-goal': self.ctx.operation_goal}
        result = {name: _parameter_contract(handler, skip=('ctx', 'read_bytes', 'session'))
                  for name, handler in handlers.items()}
        for verb in ('serializer-discovery', 'serializer-candidates', 'record-frontier'):
            result[verb]['optional'].update(_parameter_contract(getattr(self.ctx, verb.replace('-', '_')))['optional'])
        for verb, handler in (('serializer-candidates', self._serializer_candidates_reply),
                              ('record-rows', self._record_rows_reply),
                              ('record-frontier', self.ctx.record_frontier)):
            result[verb]['optional'].update(_parameter_contract(handler)['optional'])
            result[verb]['generated_defaults'] = {'output': f'evidence/{verb}-{{monotonic_ns}}.json'}
        result.update({name: {'required': [], 'optional': {}} for name in ('list', 'close')})
        for verb in ('capture-native-call', 'invoke-captured-call'):
            wrapper = _parameter_contract(getattr(self.ctx, verb.replace('-', '_')))
            result[verb]['optional'].update(wrapper['optional'])
            result[verb]['required'] = wrapper['required']
        from .z_queue import DependencyQueue
        result['work-queue']['operations'] = {op: _parameter_contract(getattr(DependencyQueue, method), skip_first=True)
            for op, method in {'add': 'add_task', 'publish': 'publish', 'claim': 'claim',
                               'complete': 'complete', 'fail': 'fail', 'retry': 'retry'}.items()}
        return result

    def _serializer_candidates_reply(self, *, summary=True, output=None, **options):
        if output is None:
            output = f'evidence/serializer-candidates-{time.monotonic_ns()}.json'
        return self.ctx.serializer_candidates(summary=summary, output=output, **options)

    def _record_rows_reply(self, *, summary=True, output=None, **options):
        if output is None:
            output = f'evidence/record-rows-{time.monotonic_ns()}.json'
        return self.ctx.record_rows(summary=summary, output=output, **options)

    def _invoke(self, verb, params):
        if self._active_actions is None:
            raise RuntimeError('ctx.invoke is available inside a loaded action request')
        if verb in ('call', 'run', 'frame', 'expect-frame'):
            return getattr(self.ctx, verb.replace('-', '_'))(**params)
        if verb in ('serializer-candidates', 'record-rows'):
            return getattr(self, '_' + verb.replace('-', '_') + '_reply')(**params)
        if verb in ('serializer-discovery', 'invoke-native', 'record-frontier', 'sample-contexts',
                    'capture-native-call', 'invoke-captured-call', 'work-queue', 'run-work',
                    'native-capture-watch', 'operation-goal'):
            return getattr(self.ctx, verb.replace('-', '_'))(**params)
        if verb not in self._active_actions:
            raise ValueError(f'unknown action: {verb!r}')
        if self._depth >= 32:
            raise ValueError('composed action depth exceeds 32')
        self._depth += 1
        try:
            return self._active_actions[verb]['handler'](self.ctx, **params)
        finally:
            self._depth -= 1

    def _capture_action(self, *, name, steps, entry='', next_state='', observation=None,
                        requires=None, execute=False, replace=False):
        from .z_capture import save_recipe, validate_recipe, recipe_handler
        if type(execute) is not bool or type(replace) is not bool:
            raise ValueError('execute and replace must be boolean')
        recipe = validate_recipe(name, steps, reserved=BUILTINS, entry=entry,
                                 next_state=next_state, observation=observation, requires=requires)
        for step in recipe['steps']:
            if step['verb'] not in self._active_actions and step['verb'] not in (
                    'call', 'run', 'frame', 'expect-frame', 'serializer-candidates', 'serializer-discovery',
                    'invoke-native', 'record-frontier', 'record-rows', 'sample-contexts',
                    'capture-native-call', 'invoke-captured-call', 'work-queue', 'run-work',
                    'native-capture-watch', 'operation-goal'):
                raise ValueError(f'capture references unknown verb: {step["verb"]!r}')
        if name in self._active_actions and 'capture' not in self._active_actions[name]:
            raise ValueError('an authored Python action already uses that name')
        save_recipe(self.recipes_path, name, recipe, replace=replace)
        self._active_actions[name] = {'handler': recipe_handler(name, recipe),
                                      'description': 'Captured input/operation recipe',
                                      'entry': entry, 'next_state': next_state, 'capture': recipe}
        result = {'name': name, 'path': str(self.recipes_path), 'recipe': recipe,
                  'status': 'captured; observation is an authored claim'}
        self._capture_progress = result
        if execute:
            # Capture before invoking so an interruption still leaves a reusable
            # recipe; never replay automatically after a partial failure.
            result['before'] = self.ctx.frame(output=f'evidence/capture-before-{time.monotonic_ns()}.png')
            result['execution'] = self._invoke(name, {})
            result['after'] = self.ctx.frame(output=f'evidence/capture-after-{time.monotonic_ns()}.png')
        return result

    def _dispatch(self, verb, params):
        if verb == 'close':
            if params:
                raise ValueError('close takes no params')
            self.close()
            return {'closed': True}
        if self.closed or getattr(self.ctx.d, 'closed', False):
            raise RuntimeError('controller debugger is closed')
        if verb in ('call', 'run', 'frame', 'expect-frame'):
            return getattr(self.ctx, verb.replace('-', '_'))(**params)
        if verb in ('serializer-candidates', 'record-rows'):
            return getattr(self, '_' + verb.replace('-', '_') + '_reply')(**params)
        if verb in ('serializer-discovery', 'invoke-native', 'record-frontier', 'sample-contexts',
                    'invoke-captured-call', 'work-queue', 'native-capture-watch', 'operation-goal'):
            return getattr(self.ctx, verb.replace('-', '_'))(**params)
        if verb == 'observe-state':
            return self.ctx.observe_state(**params)
        with _action_import_path(self.actions_path.parent):
            try:
                self._active_actions = self._load_actions()
                if verb == 'list':
                    if params:
                        raise ValueError('list takes no params')
                    return {'actions': [dict(name=name, **{k: v for k, v in spec.items()
                                             if k != 'handler'})
                                        for name, spec in self._active_actions.items()],
                            'builtins': BUILTINS.copy(), 'builtin_parameters': self._builtin_parameters(),
                            'metadata_is_descriptive': True}
                if verb == 'capture-action':
                    return self._capture_action(**params)
                return self._invoke(verb, params)
            finally:
                self._active_actions = None
                sys.modules.pop(self._module_name, None)

    def handle(self, request):
        """Return one JSON-compatible response; request/action errors keep the guest."""
        with self._lock:
            started = time.monotonic_ns()
            self.ctx.request_started_ns = started
            self._recipe_progress = []
            self._capture_progress = None
            response = {'id': None, 'verb': None}
            try:
                if not isinstance(request, dict):
                    raise ValueError('request must be an object')
                json.dumps(request, allow_nan=False)
                response.update(id=request.get('id'), verb=request.get('verb'))
                if set(request) - {'id', 'verb', 'params'}:
                    raise ValueError('request accepts only id, verb and params')
                verb, params = request.get('verb'), request.get('params', {})
                if not isinstance(verb, str) or not verb:
                    raise ValueError('verb must be a nonempty string')
                if not isinstance(params, dict):
                    raise ValueError('params must be an object')
                result = self._dispatch(verb, params)
                json.dumps(result, allow_nan=False)
                response.update(ok=True, result=result)
            except (Exception, SystemExit) as error:
                response.update(ok=False, error={'type': type(error).__name__, 'message': str(error)},
                                effects='not rolled back; inspect current state before retrying')
                if isinstance(error, FrameExpectationError):
                    response['frame_expectation'] = error.diagnostic
                if self._recipe_progress:
                    response['recipe_progress'] = self._recipe_progress
                if self._capture_progress:
                    response['capture_progress'] = self._capture_progress
            ended = time.monotonic_ns()
            response['timing'] = {'start_monotonic_ns': started, 'end_monotonic_ns': ended,
                                  'elapsed_ms': round((ended - started) / 1000000, 3)}
            return response

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.ctx.d.close()
        finally:
            self._active_actions = None
            sys.modules.pop(self._module_name, None)
            self.ctx.p.__exit__(None, None, None)


def _reject_constant(value):
    raise ValueError(f'non-JSON numeric constant: {value}')


def serve_controller(controller, input_stream, output_stream, *, error_stream=None):
    """Serve one response per request; keep request failures local, close on EOF.

    Diagnostics from trusted Python go to error_stream, preserving JSON stdout.
    Oversized lines are drained as one bad request so later lines still work.
    Transport failures and interrupts leave through finally and close ownership.
    """
    error_stream = error_stream if error_stream is not None else sys.stderr

    def emit(value):
        output_stream.write(json.dumps(value, allow_nan=False, separators=(',', ':')) + '\n')
        output_stream.flush()

    try:
        emit({'event': 'ready', 'protocol': 'fdisbull-z-controller-1',
              'actions_path': str(controller.actions_path),
              'trust': 'explicit local action file executes arbitrary trusted Python',
              'controller_started_monotonic_ns': controller.started_ns,
              'ready_monotonic_ns': time.monotonic_ns()})
        while not controller.closed:
            line = input_stream.readline(MAX_REQUEST_BYTES + 1)
            if not line:
                return 0
            try:
                encoded = line if isinstance(line, bytes) else line.encode('utf-8')
                if len(encoded) > MAX_REQUEST_BYTES:
                    newline = b'\n' if isinstance(line, bytes) else '\n'
                    while line and not line.endswith(newline):
                        line = input_stream.readline(MAX_REQUEST_BYTES + 1)
                    raise ValueError('request exceeds 1 MiB')
                request = json.loads(encoded, parse_constant=_reject_constant)
            except (ValueError, UnicodeError, RecursionError) as error:
                emit({'id': None, 'ok': False,
                      'error': {'type': 'InvalidJSON', 'message': str(error)}})
                continue
            with redirect_stdout(error_stream):
                response = controller.handle(request)
            emit(response)
        return 0
    finally:
        with redirect_stdout(error_stream):
            controller.close()


def serve(project_path, executable, game_dir, actions_path, *, root=None,
          debugger_options=None, input_stream=None, output_stream=None,
          error_stream=None, project_factory=None):
    """CLI seam: open one owner, run JSONL, and close it on every exit path."""
    input_stream = input_stream if input_stream is not None else sys.stdin
    output_stream = output_stream if output_stream is not None else sys.stdout
    error_stream = error_stream if error_stream is not None else sys.stderr
    started = time.monotonic_ns()
    with redirect_stdout(error_stream):
        controller = ZController.open(project_path, executable, game_dir, actions_path,
                                      root=root, debugger_options=debugger_options,
                                      project_factory=project_factory)
    controller.started_ns = started
    return serve_controller(controller, input_stream, output_stream, error_stream=error_stream)
