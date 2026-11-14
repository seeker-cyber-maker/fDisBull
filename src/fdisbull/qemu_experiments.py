"""Full-checkpoint paired experiments for native QEMU DOS processes.

Each arm starts from the same verified whole-machine checkpoint. This module
does not provide replay or promise deterministic execution.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import time

from .dosbox_rpc import DebuggerError
from .qemu_dos_history import _history_operation

FORMAT = 'fdisbull-qemu-experiment-1'
KIND = 'experiment'
_ALLOWED_SCRIPT_OPS = frozenset({
    'step', 'run', 'registers', 'memory', 'trace', 'screenshot', 'capture-surface', 'assert',
    'delete-breakpoint', 'delete-hook',
})
_MAX_STEPS = 128
_MAX_TRACE_EVENTS = 1024
_MAX_SCREENSHOTS = 4
_MAX_SCRIPT_MEMORY = 65536
_PROJECT_ARTIFACT_BUDGET = 256 * 1024 * 1024
_STATE_ARTIFACT_MAX = 128 * 1024 * 1024
_REPORT_ARTIFACT_MAX = 16 * 1024 * 1024


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _artifact_row(project, artifact):
    row = project.db.execute('''SELECT a.*,r.version FROM debug_artifacts a
        JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (artifact,)).fetchone()
    if row is None:
        raise ValueError('Experiment references a missing artifact')
    data = bytes(row['data'])
    if _sha(data) != row['sha256']:
        raise ValueError('Experiment referenced artifact hash mismatch')
    return row, data, json.loads(row['metadata'])


def _require_project_capacity(project, reserve):
    used = int(project.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
    if type(reserve) is not int or reserve < 0 or used + reserve > _PROJECT_ARTIFACT_BUDGET:
        raise ValueError('Native experiment cannot reserve its bounded checkpoint and trial artifacts')
    return used


def _same_endpoint(left, right):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return all(left.get(key) == right.get(key) for key in ('identity', 'registers', 'memory'))


def _validate_script(session, script):
    from .debug_script import validate_script
    raw = _json(script)
    if len(raw) > 1024 * 1024:
        raise ValueError('Native experiment script exceeds 1 MiB')

    def count_steps(rows, depth=0):
        if not isinstance(rows, list) or depth > 8:
            raise ValueError('Native experiment script has invalid nesting')
        total = 0
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Native experiment script step must be an object')
            if row.get('op') == 'repeat':
                count = row.get('count')
                if type(count) is not int or not 1 <= count <= 1000:
                    raise ValueError('Native experiment repeat count must be a literal integer 1..1000')
                total += count * count_steps(row.get('steps'), depth + 1)
            else:
                total += 1
            if total > _MAX_STEPS:
                raise ValueError('Native experiment script exceeds 128 expanded steps')
        return total

    count_steps(script.get('steps') if isinstance(script, dict) else None)
    expanded = validate_script(script, session=session)
    if len(expanded) > _MAX_STEPS:
        raise ValueError('Native experiment script exceeds 128 expanded steps')
    unsupported = sorted({item['op'] for item in expanded} - _ALLOWED_SCRIPT_OPS)
    if unsupported:
        raise ValueError('Unsupported native experiment operations: ' + ', '.join(unsupported))
    memory_bytes = trace_events = screenshots = 0
    for item in expanded:
        op = item['op']
        if op == 'memory':
            if item.get('space', 'physical') not in ('physical', 'virtual'):
                raise ValueError('Native experiment script memory requires physical or virtual space')
            length = item.get('length', 16)
            if type(length) is not int or not 1 <= length <= _MAX_SCRIPT_MEMORY:
                raise ValueError('Native experiment memory observations must use literal lengths 1..65536')
            if item.get('space') not in ('physical', 'virtual', 'linear'):
                raise ValueError('Native experiment memory reads require an explicit runtime address space')
            memory_bytes += length
        elif op == 'trace':
            count = item.get('count', 128)
            if type(count) is not int or count < 1:
                raise ValueError('Native experiment trace counts must be positive literal integers')
            trace_events += count
        elif op in ('screenshot', 'capture-surface'):
            screenshots += 1
            if item.get('grid', False) is not False:
                raise ValueError('Native experiment screenshots must be ungridded')
    if memory_bytes > _MAX_SCRIPT_MEMORY:
        raise ValueError('Native experiment script memory observations exceed 64 KiB')
    if trace_events > _MAX_TRACE_EVENTS:
        raise ValueError('Native experiment trace budget exceeds 1024 events')
    if screenshots > _MAX_SCREENSHOTS:
        raise ValueError('Native experiment screenshot budget exceeds four images')
    return expanded


def _validate_control_references(steps, control_ids):
    for step in steps:
        if step['op'] == 'delete-breakpoint':
            value = step.get('breakpoint_id')
            prefix, suffix = '$controls.breakpoints.', '.breakpoint_id'
            if (not isinstance(value, str) or not value.startswith(prefix) or not value.endswith(suffix)
                    or value[len(prefix):-len(suffix)] not in control_ids.get('breakpoints', {})):
                raise ValueError('Native experiment may delete only a captured breakpoint through controls')
        elif step['op'] == 'delete-hook':
            value = step.get('hook')
            prefix, suffix = '$controls.hooks.', '.hook'
            if (not isinstance(value, str) or not value.startswith(prefix) or not value.endswith(suffix)
                    or value[len(prefix):-len(suffix)] not in control_ids.get('hooks', {})):
                raise ValueError('Native experiment may delete only a captured hook through controls')


def _layer_hashes(project, version, layer_ids):
    hashes = {}
    for identifier in sorted(set(layer_ids)):
        info = project.debug_layer_info(identifier)
        if info['version'] != version:
            raise ValueError('Experiment layer belongs to a different static version')
        hashes[identifier] = _logical_layer_hash(info)
    return hashes


def _logical_layer_hash(info):
    """Hash immutable layer content, excluding fresh-owner binding fields."""
    value = deepcopy(info)
    value.pop('sha256', None)
    value.pop('id', None)
    value.pop('run', None)
    value.pop('created', None)
    binding = value.get('native_binding')
    if isinstance(binding, dict):
        binding.pop('run', None)
        binding.pop('epoch', None)
    return _sha(_json(value))


def _layer_stacks(session):
    global_stack = list(session.layers()['active'])
    private = {}
    bindings, pages = {}, {}
    for task_id, row in sorted(getattr(session, '_dos_task_views', {}).items()):
        private[task_id] = list(row['active'])
        bindings[task_id] = deepcopy(row['binding'])
        pages[task_id] = list(row['pages'])
    selected = None
    binding = getattr(session, '_dos_task_binding', None)
    if binding is not None:
        selected = binding['task_id']
    return global_stack, private, selected, bindings, pages


def _control_view(raw, project=None, version=None):
    """Return logical control definitions while omitting disposable native IDs."""
    breakpoints = []
    for item in raw.get('breakpoints', []):
        row = {key: deepcopy(value) for key, value in item.items() if key not in ('id', 'breakpoint_id', 'run', 'epoch')}
        breakpoints.append(row)
    hooks = []
    for item in raw.get('hooks', []):
        row = {key: deepcopy(value) for key, value in item.items()
               if key not in ('breakpoint_id', 'run', 'epoch')}
        if project is not None:
            for action in row.get('actions', []):
                if action.get('op') in ('layers', 'task-layers'):
                    action['layer_hashes'] = [_logical_layer_hash(project.debug_layer_info(identifier))
                                              for identifier in action.pop('layers', [])]
        hooks.append(row)
    return dict(breakpoints=breakpoints, hooks=hooks,
                pending_hook=raw.get('pending_hook'),
                pending_task=raw.get('pending_task'))


def project_document(project, artifact, version=None):
    """Read and validate a native experiment artifact without a live machine."""
    row, data, _metadata = _artifact_row(project, artifact)
    if (row['kind'] != KIND or version is not None and row['version'] != version):
        raise ValueError('Unknown native experiment for the selected project version')
    document = json.loads(data)
    if (not isinstance(document, dict) or document.get('format') != FORMAT
            or document.get('version') != row['version']):
        raise ValueError('Invalid native experiment identity')
    if (not isinstance(document.get('identity'), dict)
            or not isinstance(document.get('controls'), dict)
            or not isinstance(document.get('source_sha256'), str)
            or not isinstance(document.get('version_sha256'), str)
            or not isinstance(document.get('runtime'), dict)):
        raise ValueError('Incomplete native experiment metadata')
    checkpoint = document.get('checkpoint')
    if not isinstance(checkpoint, dict) or set(checkpoint) != {'artifact', 'sha256'}:
        raise ValueError('Invalid native experiment checkpoint reference')
    state, state_data, state_metadata = _artifact_row(project, checkpoint['artifact'])
    if (state['kind'] != 'state' or state['version'] != row['version']
            or state['sha256'] != checkpoint['sha256']
            or state_metadata.get('source_sha256') != document.get('source_sha256')):
        raise ValueError('Native experiment checkpoint identity mismatch')
    from .qemu_dos_checkpoint import PROCESS_FORMATS, _unarchive, _sha as checkpoint_sha
    CHECKPOINT_FORMAT = state_metadata.get('format')
    if CHECKPOINT_FORMAT not in PROCESS_FORMATS:
        raise ValueError('Native experiment requires a full process checkpoint')
    _machine, bundle = _unarchive(state_data)
    if (bundle.get('format') != CHECKPOINT_FORMAT
            or bundle.get('source_sha256') != document.get('source_sha256')
            or bundle.get('version') != row['version']
            or bundle.get('version_sha256') != document.get('version_sha256')
            or bundle.get('runtime') != document.get('runtime')
            or state_metadata.get('sidecar_sha256') != checkpoint_sha(_json(bundle))):
        raise ValueError('Native experiment checkpoint sidecar differs from its source/runtime identity')
    from .qemu_dos_checkpoint import WORKSPACE_FORMAT
    if CHECKPOINT_FORMAT == WORKSPACE_FORMAT:
        from .qemu_workspace import validate_workspace
        if state_metadata.get('workspace') != bundle.get('workspace'):
            raise ValueError('Native experiment workspace metadata differs')
        validate_workspace(project, bundle.get('workspace'), row['version'])
    origin_run = document.get('origin_run')
    capture_epoch = document.get('capture_epoch')
    if (not isinstance(origin_run, str) or not origin_run
            or not isinstance(capture_epoch, str) or not capture_epoch
            or origin_run != state_metadata.get('origin_run')
            or capture_epoch != bundle.get('process', {}).get('capture_epoch')):
        raise ValueError('Native experiment capture origin differs from its full process checkpoint')
    script = document.get('script')
    if (not isinstance(script, dict) or _sha(_json(script)) != document.get('script_sha256')):
        raise ValueError('Native experiment script hash mismatch')
    observations = document.get('observations')
    from .qemu_trial_observations import validate_observations
    validate_observations(observations)
    hashes = document.get('layer_hashes')
    if not isinstance(hashes, dict) or len(hashes) > 256:
        raise ValueError('Invalid native experiment layer hashes')
    for identifier, digest in hashes.items():
        if _layer_hashes(project, row['version'], [identifier]).get(identifier) != digest:
            raise ValueError('Stored native experiment layer hash mismatch')
    if not isinstance(document.get('identity'), dict) or not isinstance(document.get('controls'), dict):
        raise ValueError('Incomplete native experiment metadata')
    control_ids = document.get('control_ids')
    if (not isinstance(control_ids, dict)
            or not isinstance(control_ids.get('breakpoints'), dict)
            or not isinstance(control_ids.get('hooks'), dict)):
        raise ValueError('Invalid native experiment control bindings')
    _validate_control_references(script.get('steps', []), control_ids)
    return deepcopy(document)


class QemuExperimentMixin:
    """Paired runs from one private full-process checkpoint."""

    def _qemu_experiment_supported(self):
        if getattr(self, 'closed', True) or getattr(self, 'metadata', {}).get('backend') != 'qemu-dos':
            raise ValueError('Native experiments require an open QEMU DOS process')
        if self.project.db.in_transaction:
            raise ValueError('Native experiments require a project outside a caller-owned transaction')
        self._history_supported()

    def _qemu_experiment_controls(self):
        from .qemu_checkpoint_controls import capture_controls
        raw = capture_controls(self)
        return dict(logical=_control_view(raw, self.project, self.version['id']), raw_sha256=_sha(_json(raw)))

    @_history_operation
    def controls(self):
        self._qemu_experiment_supported()
        value = self._qemu_experiment_controls()
        return {'run': self.run_id, **value['logical'], 'sha256': value['raw_sha256']}

    def _qemu_experiment_layer_snapshot(self):
        global_stack, task_stacks, selected, task_bindings, task_pages = _layer_stacks(self)
        ids = set(global_stack)
        for stack in task_stacks.values():
            ids.update(stack)
        from .qemu_checkpoint_controls import capture_controls
        controls = capture_controls(self)
        for hook in controls.get('hooks', []):
            for action in hook.get('actions', []):
                if action.get('op') in ('layers', 'task-layers'):
                    ids.update(action.get('layers', []))
        hashes = _layer_hashes(self.project, self.version['id'], ids)
        return dict(global_layers=global_stack, tasks=task_stacks, selected_task=selected,
                    task_bindings=task_bindings, task_pages=task_pages,
                    hashes=hashes)

    def _qemu_experiment_candidate(self, layers, document):
        if not isinstance(layers, list) or len(layers) > 64 or any(not isinstance(i, str) for i in layers) or len(set(layers)) != len(layers):
            raise ValueError('Comparison requires an explicit ordered layer stack')
        task_id = document['layer_stacks'].get('selected_task')
        private = task_id is not None
        expected_kind = 'tasks' if private else 'global'
        saved_binding = document['layer_stacks'].get('task_bindings', {}).get(task_id) if private else None
        saved_pages = set(document['layer_stacks'].get('task_pages', {}).get(task_id, [])) if private else set()
        if private and (not isinstance(saved_binding, dict) or not saved_pages):
            raise ValueError('Native experiment lacks its selected task page ownership')
        layer_hashes = {}
        expected_bytes = {}
        total_patches = 0
        total_bytes = 0
        from .qemu_dos_tasks import task_key
        for identifier in layers:
            info = self.project.debug_layer_info(identifier)
            if info['version'] != self.version['id'] or info.get('kind') not in ('ram', 'execute'):
                raise ValueError('Comparison layer has incompatible version or kind')
            binding = info.get('native_binding')
            if binding is not None:
                if not isinstance(binding, dict):
                    raise ValueError('Comparison layer has an unsupported native binding')
                # The original global-layer format predates the explicit
                # scope field. A missing scope is its established global form.
                scope = binding.get('scope', 'global')
                if scope not in ('global', 'task-private'):
                    raise ValueError('Comparison layer has an unsupported native binding')
                if (binding.get('run') != document.get('origin_run')
                        or binding.get('epoch') != document.get('capture_epoch')):
                    raise ValueError('Comparison layer belongs to a different captured run or epoch')
                if private:
                    owner = binding.get('task_identity')
                    if scope == 'task-private':
                        if owner is None or task_key(owner) != task_key(saved_binding):
                            raise ValueError('Comparison layer belongs to a different native task lifetime')
                    else:
                        raise ValueError('Global comparison layer cannot be activated in a task-private trial')
                elif scope == 'task-private' or binding.get('task_identity') is not None:
                    raise ValueError('Task-private comparison layer requires its registered task view')
            for patch in info.get('patches', []):
                before, after = bytes.fromhex(patch['expected_hex']), bytes.fromhex(patch['data_hex'])
                if not before or len(before) != len(after):
                    raise ValueError('Comparison layer has an invalid patch extent')
                total_patches += 1
                total_bytes += len(before)
                if binding is not None:
                    allowed_pages = saved_pages
                    addresses = []
                    spans = binding.get('spans', [])
                    for span in spans:
                        if (not isinstance(span, (list, tuple)) or len(span) != 2
                                or type(span[0]) is not int or type(span[1]) is not int
                                or span[1] <= 0 or span[1] > 4096
                                or private and any((page * 4096) not in allowed_pages
                                                   for page in range(span[0] // 4096,
                                                       (span[0] + span[1] - 1) // 4096 + 1))):
                            raise ValueError('Native comparison layer extent is outside registered RAM')
                        self._layer_ram_extent(span[0], span[1])
                        addresses.extend(range(span[0], span[0] + span[1]))
                else:
                    # Qualify the static source extent before a checkpoint
                    # restore; runtime page ownership is checked on activation.
                    static, _ = self.project._dos_parse_address(patch['address'])
                    ranges = document.get('endpoint', {}).get('identity', {}).get('source_mapping', {}).get('live_ranges', [])
                    if not any(0 <= static - extent.get('project_address', -1)
                               and static - extent.get('project_address', -1) + len(before) <= extent.get('length', 0)
                               for extent in ranges):
                        raise ValueError('Comparison layer is outside the verified source module')
                    _, _, spans, _ = self._layer_spans(patch['address'], len(before), 'source')
                    addresses = [address for start, count in spans for address in range(start, start + count)]
                    if private and any((address // 4096) * 4096 not in saved_pages for address in addresses):
                        raise ValueError('Source comparison layer is outside the saved task-private pages')
                if len(addresses) != len(before) or len(set(addresses)) != len(addresses):
                    raise ValueError('Comparison layer spans differ from patch bytes')
                for address, old in zip(addresses, before):
                    if expected_bytes.setdefault(address, old) != old:
                        raise ValueError('Comparison layer stack has conflicting expected bytes')
            layer_hashes[identifier] = info['sha256']
        if total_patches > 256 or total_bytes > 65536 or len(expected_bytes) > 65536:
            raise ValueError('Comparison layer stack exceeds native transition bounds')
        return dict(private=private, task_id=task_id, layer_ids=list(layers),
                    layer_hashes=layer_hashes, kind=expected_kind)

    def _qemu_experiment_activate(self, candidate):
        layers = candidate['layer_ids']
        if candidate['private']:
            active = self.dos_task_layers(layers, task=candidate['task_id'])
        else:
            active = self.layers(layers)
        return active

    def _qemu_experiment_rebind_candidate(self, candidate):
        """Clone epoch-bound definitions; immutable original artifacts are untouched."""
        row = self._dos_task_views[candidate['task_id']] if candidate['private'] else None
        result = deepcopy(candidate)
        ids = []
        for identifier in candidate['layer_ids']:
            definition = self.project.debug_layer_info(identifier)
            binding = definition.get('native_binding')
            if binding is None:
                ids.append(identifier)
                continue
            current = deepcopy(binding)
            current['run'] = self.run_id
            current['epoch'] = self._layer_epoch()
            if row is not None:
                current['task_identity'] = deepcopy(row['binding'])
            clone = dict(kind=definition['kind'], patches=deepcopy(definition['patches']),
                         native_binding=current)
            stored = self.project._store_debug_layer(definition['name'], self.version['id'], clone)
            ids.append(stored['layer'])
        result['layer_ids'] = ids
        return result

    def _qemu_experiment_identity(self):
        return deepcopy(self._history_identity())

    @_history_operation
    def save_experiment(self, name, *, script=None, script_id=None, observations=None, timeout_ms=60000):
        from .external_files import _file_name
        from .qemu_trial_observations import validate_observations
        self._qemu_experiment_supported()
        _file_name(name)
        if (script is None) == (script_id is None):
            raise ValueError('Supply exactly one of script or script_id')
        if script_id is not None:
            row = self.project.db.execute('SELECT script,sha256,version FROM debug_scripts WHERE id=?',
                                          (script_id,)).fetchone()
            if row is None or row['version'] != self.version['id'] or _sha(row['script'].encode()) != row['sha256']:
                raise ValueError('Unknown or corrupt native experiment script')
            script = json.loads(row['script'])
        expanded = _validate_script(self, script)
        raw_script_hash = _sha(_json(script))
        script = dict(format='fdisbull-script-1', backend='qemu-dos', steps=deepcopy(expanded))
        observations = validate_observations([] if observations is None else observations)
        endpoint_memory = sum(item['length'] for item in observations)
        script_memory = sum(item.get('length', 16) for item in expanded if item['op'] == 'memory')
        if endpoint_memory + script_memory > _MAX_SCRIPT_MEMORY:
            raise ValueError('Native experiment total memory observation budget exceeds 64 KiB')
        if any(step.get('as') == 'controls' for step in expanded):
            raise ValueError('controls is reserved for restored native experiment controls')
        # Validate exact source mappings without reading through the legacy
        # machine-memory API, whose default domain is physical RAM.
        from .qemu_cpu_undo_runtime import normalize_ranges
        for item in observations:
            normalize_ranges(self, [item])
        _require_project_capacity(self.project, _STATE_ARTIFACT_MAX + _REPORT_ARTIFACT_MAX)
        controls = self._qemu_experiment_controls()
        from .qemu_checkpoint_controls import capture_controls
        raw_controls = capture_controls(self)
        control_ids = dict(
            breakpoints={item['id']: {k: deepcopy(v) for k, v in item.items() if k != 'id'}
                         for item in raw_controls.get('breakpoints', [])},
            hooks={item['hook']: {k: deepcopy(v) for k, v in item.items() if k != 'breakpoint_id'}
                   for item in raw_controls.get('hooks', [])})
        _validate_control_references(expanded, control_ids)
        stacks = self._qemu_experiment_layer_snapshot()
        layer_hashes = stacks['hashes']
        from .qemu_trial_observations import capture_state
        endpoint = capture_state(self, observations)
        state = self.save_state('qemu-experiment-checkpoint.qcow2')
        after_save = capture_state(self, observations)
        if not _same_endpoint(endpoint, after_save):
            self.close()
            raise DebuggerError('Native experiment endpoint changed while its full checkpoint was captured')
        identity = self._qemu_experiment_identity()
        document = dict(format=FORMAT, name=name, version=self.version['id'],
            source_sha256=self.metadata['source_sha256'], version_sha256=self.metadata['version_sha256'],
            runtime=identity['runtime'], identity=identity, endpoint=endpoint,
            origin_run=self.run_id, capture_epoch=self._process['capture_epoch'],
            checkpoint={'artifact': state['artifact'], 'sha256': state['sha256']},
            controls=controls['logical'], control_ids=control_ids,
            layer_stacks=stacks, layer_hashes=layer_hashes,
            script=deepcopy(script), script_sha256=_sha(_json(script)),
            script_origin_sha256=raw_script_hash, observations=observations,
            evidence_scope='paired bounded observations from repeated full native checkpoints; no deterministic replay claim')
        artifact = self._artifact(name, KIND, _json(document),
            dict(format=FORMAT, checkpoint=state['artifact'], script_sha256=document['script_sha256']))
        return {**artifact, 'format': FORMAT, 'checkpoint': document['checkpoint'],
                'controls': controls['logical'], 'active_layers': stacks['global_layers'],
                'task_layers': stacks['tasks'], 'observations': observations}

    def _qemu_experiment_document(self, experiment):
        document = project_document(self.project, experiment, self.version['id'])
        if document['identity'] != self._qemu_experiment_identity():
            raise ValueError('Native experiment source/runtime identity differs from this process')
        _validate_script(self, document['script'])
        _validate_control_references(document['script']['steps'], document['control_ids'])
        return document

    @_history_operation
    def restore_experiment(self, experiment, *, timeout_ms=60000):
        self._qemu_experiment_supported()
        document = self._qemu_experiment_document(experiment)
        self._history_admission()
        try:
            checkpoint = self.load_state(document['checkpoint']['artifact'], timeout_ms=self._history_remaining_ms())
            from .qemu_trial_observations import capture_state
            endpoint = capture_state(self, document['observations'])
            if not _same_endpoint(endpoint, document.get('endpoint')):
                raise DebuggerError('Restored native experiment endpoint differs from its full checkpoint')
            restored_controls = self._qemu_experiment_controls()
            if restored_controls['logical'] != document['controls']:
                raise DebuggerError('Restored native experiment controls differ from the saved checkpoint')
            stacks = self._qemu_experiment_layer_snapshot()
            expected_global = [document['layer_stacks']['hashes'][i]
                               for i in document['layer_stacks']['global_layers']]
            actual_global = [stacks['hashes'][i] for i in stacks['global_layers']]
            expected_tasks = {task: [document['layer_stacks']['hashes'][i] for i in ids]
                              for task, ids in document['layer_stacks']['tasks'].items()}
            actual_tasks = {task: [stacks['hashes'][i] for i in ids]
                            for task, ids in stacks['tasks'].items()}
            if (actual_global != expected_global or actual_tasks != expected_tasks
                    or stacks['selected_task'] != document['layer_stacks']['selected_task']):
                raise DebuggerError('Restored native experiment layer stacks differ')
            controls = self._qemu_experiment_control_bindings(document, checkpoint.get('controls', {}))
            return dict(experiment=experiment, checkpoint=checkpoint,
                controls=controls, active_layers=stacks['global_layers'], task_layers=stacks['tasks'],
                source_binding_restored=True)
        except BaseException:
            self.close()
            raise

    def _qemu_experiment_control_bindings(self, document, rebound):
        points = rebound.get('breakpoints', {}) if isinstance(rebound, dict) else {}
        hooks = rebound.get('hooks', {}) if isinstance(rebound, dict) else {}
        controls = {'breakpoints': {}, 'hooks': {}}
        for identifier in document.get('control_ids', {}).get('breakpoints', {}):
            fresh = points.get(identifier)
            if not isinstance(fresh, str):
                raise DebuggerError('Restored experiment breakpoint binding is incomplete')
            controls['breakpoints'][identifier] = {'breakpoint_id': fresh}
        for identifier in document.get('control_ids', {}).get('hooks', {}):
            fresh = hooks.get(identifier)
            if not isinstance(fresh, str):
                raise DebuggerError('Restored experiment hook binding is incomplete')
            controls['hooks'][identifier] = {'hook': fresh}
        controls['hook_registry'] = deepcopy(list(getattr(self, '_qemu_hooks', {}).values()))
        return controls

    def _qemu_experiment_trial(self, document, report, controls):
        from .qemu_trial_observations import capture_trial
        return capture_trial(self, document, report, controls)

    def _qemu_experiment_publish_comparison(self, result):
        try:
            artifact = self._artifact('qemu-experiment-comparison.json', 'experiment-comparison',
                                      _json(result), dict(experiment=result['experiment'], ok=result['ok'],
                                      baseline_restored=result['baseline_restored']))
        except BaseException as error:
            # The comparison may already contain completed trials and a final
            # restore receipt. Preserve that evidence on the raised error, and
            # close because durable publication is now uncertain.
            try:
                error.result = deepcopy(result)
            except BaseException:
                pass
            self.close()
            raise
        return {**result, 'artifact': artifact['artifact']}

    @_history_operation
    def compare_experiment(self, experiment, *, layers, timeout_ms=60000):
        from .debug_script import execute_script
        from .qemu_trial_observations import compare_trials
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
            raise ValueError('timeout_ms must be 1..600000')
        self._qemu_experiment_supported()
        document = self._qemu_experiment_document(experiment)
        candidate = self._qemu_experiment_candidate(layers, document)
        expanded = _validate_script(self, document['script'])
        traces = sum(1 for item in expanded if item['op'] == 'trace')
        screenshots = sum(1 for item in expanded if item['op'] in ('screenshot', 'capture-surface'))
        clone_size = lambda definition: sum(len(bytes.fromhex(patch['data_hex'])) + 4096
                                            for patch in definition.get('patches', []))
        baseline_clone_bytes = 0
        for identifier in document['layer_hashes']:
            definition = self.project.debug_layer_info(identifier)
            if definition.get('native_binding') is not None:
                baseline_clone_bytes += clone_size(definition)
        cloned_bytes = baseline_clone_bytes * 3
        for identifier in candidate['layer_ids']:
            definition = self.project.debug_layer_info(identifier)
            if definition.get('native_binding') is not None:
                cloned_bytes += clone_size(definition)
        output_reserve = (2 * _REPORT_ARTIFACT_MAX * (1 + traces + screenshots)
                          + _REPORT_ARTIFACT_MAX + 2 * 1024 * 1024 + cloned_bytes)
        _require_project_capacity(self.project, output_reserve)
        deadline = min(self._deadline, time.monotonic() + timeout_ms / 1000)
        result = dict(format='fdisbull-qemu-experiment-comparison-1', experiment=experiment,
            checkpoint=deepcopy(document['checkpoint']), script_sha256=document['script_sha256'],
            layer_hashes=candidate['layer_hashes'], baseline=None, layer=None,
            comparison=None, ok=False, error=None, baseline_restored=False)
        dispatch_started = False
        try:
            for arm, requested_stack in (('baseline', None), ('layer', candidate)):
                restored = self.restore_experiment(experiment, timeout_ms=self._remaining_deadline_ms(deadline))
                active = document['layer_stacks']['global_layers'] if requested_stack is None else requested_stack['layer_ids']
                if requested_stack is not None:
                    rebound = self._qemu_experiment_rebind_candidate(requested_stack)
                    self._qemu_experiment_activate(rebound)
                    active = rebound['layer_ids']
                remaining = self._remaining_deadline_ms(deadline)
                bindings = {'controls': restored['controls']}
                dispatch_started = True
                report = execute_script(self, document['script'], timeout_ms=remaining, bindings=bindings)
                trial = self._qemu_experiment_trial(document, report, restored['controls'])
                dispatch_started = False
                result[arm] = trial
                if not trial.get('ok') or not trial.get('complete'):
                    result['error'] = {'type': 'ScriptFailure', 'trial': arm,
                                       'step': trial.get('script_error')}
                    break
            if result['baseline'] is not None and result['layer'] is not None:
                result['comparison'] = compare_trials(result['baseline'], result['layer'])
                result['ok'] = bool(result['comparison'].get('complete'))
        except BaseException as error:
            result['error'] = {'type': type(error).__name__, 'message': str(error)}
            if dispatch_started and not self.closed:
                self.close()
            if self.closed:
                result['baseline_restored'] = False
        finally:
            if not self.closed and time.monotonic() < deadline:
                try:
                    self.restore_experiment(experiment, timeout_ms=self._remaining_deadline_ms(deadline))
                    result['baseline_restored'] = True
                except BaseException as error:
                    result['error'] = {'type': type(error).__name__, 'message': 'Final full restore: ' + str(error)}
                    self.close()
            elif not self.closed:
                self.close()
            if not result['baseline_restored']:
                result['ok'] = False
        for arm in ('baseline', 'layer'):
            trial = result.get(arm)
            if trial:
                for trace in trial.get('traces', []):
                    trace.pop('events', None)
        return self._qemu_experiment_publish_comparison(result)

    def _remaining_deadline_ms(self, deadline):
        value = int((deadline - time.monotonic()) * 1000)
        if value <= 0:
            self.close()
            raise TimeoutError('Native experiment operation deadline expired')
        return value
