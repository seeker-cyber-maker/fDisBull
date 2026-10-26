"""Immutable, project-local experiments and bounded baseline/layer trials.

Native states remain private artifacts. Restoring an experiment replaces owned
debugger controls; ordinary load_state deliberately retains its older semantics.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import time

from .external_files import _file_name


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def validate_observations(observations):
    if not isinstance(observations, list) or len(observations) > 64:
        raise ValueError('Observations require at most 64 explicit memory ranges')
    total = 0
    for item in observations:
        if not isinstance(item, dict) or set(item) not in (
                {'address', 'length'}, {'address', 'length', 'cs'}):
            raise ValueError('Observation requires address, length and optional cs')
        length = item['length']
        if type(length) is not int or not 1 <= length <= 65536:
            raise ValueError('Observation length must be 1..65536')
        total += length
    if total > 65536:
        raise ValueError('Observations exceed 64 KiB per trial')
    encoded(observations)
    return deepcopy(observations)


def _register_values(value, prefix=''):
    result = {}
    for name, item in value.items():
        path = prefix + name
        if isinstance(item, dict):
            result.update(_register_values(item, path + '.'))
        elif name not in ('run', 'version', 'state_revision'):
            result[path] = item
    return result


def _stop_value(run):
    stop = run.get('session', {}).get('stop_reason', {})
    # Native IDs change on every rearm. Preserve their full receipts in the script report.
    def without_ids(value):
        if isinstance(value, dict):
            return {k: without_ids(v) for k, v in value.items()
                    if k not in ('breakpoint_id', 'breakpoint_ids', 'session_id', 'state_revision')}
        if isinstance(value, list):
            return [without_ids(v) for v in value]
        return value
    return {'outcome': run['outcome'], 'stop_reason': without_ids(stop)}


def _trace_event(event):
    # Runtime mappings and host/layer generations are provenance, not CPU changes.
    result = {key: event[key] for key in (
        'project_address', 'project_segmented_address', 'address', 'instruction',
        'bytes', 'ram_bytes', 'execution_bytes', 'registers', 'register_changes', 'completed') if key in event}
    if isinstance(event.get('address'), dict) and event.get('execution_bytes'):
        from iced_x86 import Decoder
        raw = bytes.fromhex(event['execution_bytes'])
        instruction = Decoder(16, raw, ip=int(event['address']['offset'], 16)).decode()
        if not instruction.is_invalid:
            # DOS records a 15-byte lookahead. Later instructions are not part of this fetch.
            for name in ('ram_bytes', 'execution_bytes'):
                if name in result:
                    result[name] = result[name][:instruction.len * 2]
    return result


def compare_trials(baseline, layer):
    """Compare captured observations only; an incomplete run cannot prove equality."""
    # Pair only captures of the same operation/range. zip alone silently loses
    # unmatched evidence and can turn malformed trial records into false equality.
    for field in ('memory','traces','screenshots','observations'):
        left_items=baseline.get(field,[]);right_items=layer.get(field,[])
        if not isinstance(left_items,list) or not isinstance(right_items,list) or len(left_items)!=len(right_items):
            raise ValueError('Experiment capture alignment mismatch: '+field+' count')
        seen=set()
        for index,(a,b) in enumerate(zip(left_items,right_items,strict=True)):
            if field=='memory':
                same=(a['project_address']==b['project_address'] and len(bytes.fromhex(a['hex']))==len(bytes.fromhex(b['hex']))
                      and a.get('context')==b.get('context') and a.get('project_cs')==b.get('project_cs'))
            else:
                same=a['step']==b['step'] and a['step'] not in seen
                seen.add(a['step'])
                if field=='traces':same= same and a['semantics']==b['semantics']
                if field=='observations':
                    same= same and a['op']==b['op']
                    if a['op']=='memory':same= same and a['value']['address']==b['value']['address']
            if not same:raise ValueError(f'Experiment capture alignment mismatch: {field} identity at {index}')
    complete = baseline['ok'] and layer['ok']
    left = _register_values(baseline['registers'])
    right = _register_values(layer['registers'])
    registers = [{'field': key, 'baseline': left.get(key), 'layer': right.get(key)}
                 for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)]
    memory = [{'observation': index, 'address': a['project_address'],
               'baseline_hex': a['hex'], 'layer_hex': b['hex']}
              for index, (a, b) in enumerate(zip(baseline['memory'], layer['memory'])) if a['hex'] != b['hex']]
    traces = []
    for a, b in zip(baseline['traces'], layer['traces']):
        difference = None
        for index, (before, after) in enumerate(zip(a['events'], b['events'])):
            x, y = _trace_event(before), _trace_event(after)
            if x != y:
                difference = {'index': index, 'fields': sorted(k for k in x.keys() | y.keys() if x.get(k) != y.get(k)),
                              'baseline': before, 'layer': after}
                break
        traces.append({'step': a['step'], 'baseline_artifact': a['artifact'], 'layer_artifact': b['artifact'],
                       'baseline_count': len(a['events']), 'layer_count': len(b['events']),
                       'count_differs': len(a['events']) != len(b['events']),
                       'first_observed_difference': difference,
                       'semantics': a['semantics']})
    screenshots = [{'step': a['step'], 'baseline_artifact': a['artifact'], 'layer_artifact': b['artifact'],
                    'different': a['sha256'] != b['sha256']}
                   for a, b in zip(baseline['screenshots'], layer['screenshots'])]
    steps = [{'step': a['step'], 'op': a['op'], 'baseline': a['value'], 'layer': b['value']}
             for a, b in zip(baseline.get('observations', []), layer.get('observations', [])) if a['value'] != b['value']]
    different = bool(registers or memory or any(t['first_observed_difference'] or t['count_differs'] for t in traces)
                     or any(s['different'] for s in screenshots) or steps)
    return {'complete': bool(complete), 'observed_difference': different if complete else None,
            'registers': registers, 'memory': memory, 'traces': traces, 'screenshots': screenshots, 'steps': steps,
            'scope': 'Captured observations and positional trace prefixes; no claim of deterministic replay or full coverage'}


class ExperimentProjectMixin:
    def _experiment_document(self, artifact, version=None):
        row = self.db.execute('''SELECT a.*,r.version FROM debug_artifacts a
            JOIN debug_runs r ON r.id=a.run WHERE a.id=?''', (artifact,)).fetchone()
        if row is None or row['kind'] != 'experiment' or version is not None and row['version'] != version:
            raise ValueError('Unknown experiment for the selected project version')
        data = bytes(row['data'])
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Stored experiment hash mismatch')
        document = json.loads(data)
        if document['format'] != 'fdisbull-experiment-1' or document['version'] != row['version']:
            raise ValueError('Invalid experiment identity')
        state = self.debug_state_info(document['checkpoint']['artifact'])
        if state['sha256'] != document['checkpoint']['sha256'] or state['version'] != row['version']:
            raise ValueError('Experiment checkpoint identity mismatch')
        if hashlib.sha256(encoded(document['script'])).hexdigest() != document['script_sha256']:
            raise ValueError('Experiment script hash mismatch')
        for identifier, digest in document['layer_hashes'].items():
            info = self.debug_layer_info(identifier)
            if info['sha256'] != digest or info['version'] != row['version']:
                raise ValueError('Experiment layer identity mismatch')
        return document

    def debug_experiment_info(self, artifact):
        return {'artifact': artifact, **self._experiment_document(artifact)}

    def debug_experiments(self, version=None):
        version = self.version(version)['id']
        return {'version': version, 'experiments': [a for a in self.debug_artifacts(version)['artifacts']
                                                   if a['kind'] == 'experiment']}


class ExperimentSessionMixin:
    def _remember_breakpoints(self, params, result):
        if not hasattr(self, '_experiment_breakpoints'):
            self._experiment_breakpoints = {}
        for item in result.get('breakpoints', [result]):
            spec = deepcopy(params)
            if params.get('access', 'x') == 'x' and item.get('project_cs') is not None:
                spec.update(address=item['project_address'], cs=item['project_cs'])
            if params.get('access', 'x') != 'x' and 'breakpoints' in result:
                spec.update(address=item['project_address'], cs=None, length=1)
            self._experiment_breakpoints[item['breakpoint_id']] = spec
        return result

    def _forget_breakpoint(self, identifier):
        getattr(self, '_experiment_breakpoints', {}).pop(identifier, None)

    def _experiment_supported(self):
        if self.closed:
            raise ValueError('Debugger session is closed')
        backend = getattr(self, 'backend_name', None)
        if backend is not None and backend != 'wine-qemu':
            raise ValueError('Experiments require native DOSBox, DOSBox/QEMU or the custom Wine/QEMU backend')
        if backend is None and not self.rpc.capabilities.get('code_layers'):
            raise ValueError('DOS experiments require the layers-capable backend')

    def _native_control_ids(self):
        if getattr(self, 'backend_name', None) == 'wine-qemu':
            return set(self.breakpoints) | set(self.watchpoints)
        return {b['breakpoint_id'] for b in self.call('breakpoints.list')['breakpoints']}

    def controls(self):
        self._experiment_supported()
        self._layer_setup()
        if getattr(self, 'backend_name', None) == 'wine-qemu':
            # PE native states include controller-owned breakpoint registries.
            self._experiment_breakpoints = {
                **{k: {'address': hex(v), 'access': 'x', 'view': 'static', 'length': 1, 'cs': None}
                   for k, v in self.breakpoints.items()},
                **{k: {**v, 'cs': None, 'view': 'static'} for k, v in self.watchpoints.items()}}
        actual = self._native_control_ids()
        registry = getattr(self, '_experiment_breakpoints', {})
        if actual != set(registry):
            raise ValueError('Untracked or externally changed debugger controls; experiment capture refused')
        hooks = list({h['hook']: h for h in self._hooks.values()}.values())
        for hook in hooks:
            if 'definition' not in hook or len(hook['breakpoints']) != hook['native_count']:
                raise ValueError('Partially deleted hook cannot be captured as an experiment')
        hooked = set(self._hooks)
        return deepcopy({'breakpoints': [{'key': k, 'params': v} for k, v in registry.items() if k not in hooked],
                         'hooks': [{'key': h['hook'], 'params': h['definition'], 'hits': h['hits']} for h in hooks]})

    def _clear_experiment_controls(self):
        self._layer_setup()
        for identifier in sorted(self._native_control_ids()):
            self.delete_breakpoint(identifier)
        self._hooks.clear()
        self._experiment_breakpoints = {}

    def _checkpoint_controls(self, document):
        """PE whole-VM states preserve pending breakpoint displacement and guards.

        Deleting/reinstalling an INT3 at the saved PC loses that displacement
        state and causes a duplicate stop. Verify and bind the restored registry.
        """
        current = self.controls()
        expected = document['controls']
        for kind in ('breakpoints', 'hooks'):
            if {i['key']: i['params'] for i in current[kind]} != {i['key']: i['params'] for i in expected[kind]}:
                raise ValueError('Native checkpoint control registry differs from the experiment')
        restored = {'breakpoints': {}, 'hooks': {}}
        for item in current['breakpoints']:
            params = item['params']
            address = int(params['address'], 16) if isinstance(params['address'], str) else params['address']
            restored['breakpoints'][item['key']] = {
                **params, 'breakpoint_id': item['key'], 'run': self.run_id, 'version': self.version['id'],
                'project_address': hex(address), 'runtime_address': hex(address + self.delta),
                'native_checkpoint_restored': True}
        return restored

    def _validate_experiment_script(self, script):
        from .debug_script import validate_script
        steps = validate_script(script)
        unsupported = {s['op'] for s in steps} - self.script_operations
        if unsupported:
            raise ValueError('Unsupported experiment operations: ' + ', '.join(sorted(unsupported)))
        if any(s.get('as') == 'controls' for s in steps):
            raise ValueError('controls is reserved for restored experiment bindings')

    def save_experiment(self, name, *, script=None, script_id=None, observations=None):
        self._experiment_supported()
        _file_name(name)
        if (script is None) == (script_id is None):
            raise ValueError('Supply exactly one of script or script_id')
        if script_id is not None:
            row = self.project.db.execute('SELECT * FROM debug_scripts WHERE id=? AND version=?',
                                          (script_id, self.version['id'])).fetchone()
            if row is None or hashlib.sha256(row['script'].encode()).hexdigest() != row['sha256']:
                raise ValueError('Unknown or corrupt experiment script')
            script = json.loads(row['script'])
        self._validate_experiment_script(script)
        observations = validate_observations([] if observations is None else observations)
        for item in observations:
            self.memory(**item)  # Validate mapped ranges before any state capture.
        controls = self.controls()
        active = self.layers()['active']
        layer_ids = set(active)
        for hook in controls['hooks']:
            for action in hook['params']['actions']:
                if action['op'] == 'layers':
                    layer_ids.update(action['layers'])
        state = self.save_state('experiment-checkpoint.sav')
        document = {'format': 'fdisbull-experiment-1', 'name': name, 'version': self.version['id'],
                    'checkpoint': {'artifact': state['artifact'], 'sha256': state['sha256']},
                    'controls': controls, 'active_layers': active,
                    'layer_hashes': {i: self.project.debug_layer_info(i)['sha256'] for i in sorted(layer_ids)},
                    'script': script, 'script_sha256': hashlib.sha256(encoded(script)).hexdigest(),
                    'observations': observations,
                    'trace_semantics': 'completed_steps' if getattr(self, 'backend_name', None) else 'pre_execution_fetch_last_pending'}
        return self._artifact(name, 'experiment', encoded(document),
                              {'format': document['format'], 'checkpoint': state['artifact'], 'script_sha256': document['script_sha256']})

    def restore_experiment(self, experiment):
        self._experiment_supported()
        document = self.project._experiment_document(experiment, self.version['id'])
        self._validate_experiment_script(document['script'])
        # Refuse unknown live controls before replacing anything.
        self.controls()
        try:
            self._clear_experiment_controls()
            state = self.load_state(document['checkpoint']['artifact'])
            if self.layers()['active'] != document['active_layers']:
                raise ValueError('Restored experiment layer stack differs from its saved definition')
            if getattr(self, 'backend_name', None) == 'wine-qemu':
                restored = self._checkpoint_controls(document)
            else:
                self._clear_experiment_controls()
                restored = {'breakpoints': {}, 'hooks': {}}
                for item in document['controls']['breakpoints']:
                    created = self.breakpoint(**item['params'])
                    # DOS watches are captured per native byte, including partially deleted groups.
                    restored['breakpoints'][item['key']] = created['breakpoints'][0] if 'breakpoints' in created else created
                for item in document['controls']['hooks']:
                    hook = self.hook(**item['params'])
                    for control in self._hooks.values():
                        if control['hook'] == hook['hook']:
                            control['hits'] = item['hits']
                    hook['hits'] = item['hits']
                    restored['hooks'][item['key']] = hook
            result = {'experiment': experiment, 'checkpoint': state, 'controls': restored,
                      'active_layers': self.layers()['active'], 'hit_counts_restored': True}
            self._event('restore-experiment', result)
            return result
        except BaseException:
            self.close()  # A partial control restore is not a usable trial starting point.
            raise

    def _experiment_trial(self, document, restored, deadline, active):
        from .debug_script import execute_script
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            raise TimeoutError('Comparison dispatch budget expired')
        self.layers(active)
        report = execute_script(self, document['script'], timeout_ms=remaining,
                                bindings={'controls': restored['controls']})
        trial = {'ok': report['ok'], 'script_report': report['artifact'], 'script_error': report['error'],
                 'active_layers_at_start': active, 'registers': {}, 'memory': [], 'traces': [], 'screenshots': [], 'observations': []}
        if not self.closed:
            trial['registers'] = self.registers()
            trial['memory'] = [self.memory(**item) for item in document['observations']]
        for record in report['steps']:
            result = record.get('result', {})
            if record['op'] in ('registers', 'memory', 'run', 'wait') and result:
                if record['op'] == 'wait':
                    value = {k: result[k] for k in ('complete', 'matched', 'outcome', 'last_observation')}
                    value['polls'] = [poll['values'] for poll in result['polls']]
                elif record['op'] == 'run':
                    value = _stop_value(result)
                elif record['op'] == 'registers':
                    value = _register_values(result)
                else:
                    value = {'address': result['project_address'], 'hex': result['hex']}
                trial['observations'].append({'step': record['index'], 'op': record['op'], 'value': value})
            if record['op'] == 'trace' and 'artifact' in result:
                row = self.project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?', (result['artifact'],)).fetchone()
                data = bytes(row['data'])
                if hashlib.sha256(data).hexdigest() != row['sha256']:
                    raise ValueError('Stored trace hash mismatch')
                trial['traces'].append({'step': record['index'], 'artifact': result['artifact'],
                                        'events': json.loads(data)['events'], 'semantics': document['trace_semantics']})
            if record['op'] in ('screenshot', 'click-frame') and result:
                frame = result['frame'] if record['op'] == 'click-frame' else result
                trial['screenshots'].append({'step': record['index'], 'artifact': frame['artifact'], 'sha256': frame['sha256']})
        return trial

    def compare_experiment(self, experiment, *, layers, timeout_ms=60000):
        self._experiment_supported()
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
            raise ValueError('timeout_ms must be 1..600000')
        if not isinstance(layers, list) or len(layers) > 64 or len(set(layers)) != len(layers):
            raise ValueError('Comparison requires an explicit ordered layer stack')
        document = self.project._experiment_document(experiment, self.version['id'])
        self._validate_experiment_script(document['script'])
        for identifier in layers:
            if self.project.debug_layer_info(identifier)['version'] != self.version['id']:
                raise ValueError('Comparison layer version mismatch')
        deadline = time.monotonic() + timeout_ms / 1000
        result = {'format': 'fdisbull-experiment-comparison-1', 'experiment': experiment,
                  'checkpoint': document['checkpoint'], 'script_sha256': document['script_sha256'],
                  'layer_hashes': {i: self.project.debug_layer_info(i)['sha256']
                                   for i in sorted(set(document['active_layers']) | set(layers))},
                  'run': self.run_id, 'baseline': None, 'layer': None, 'comparison': None,
                  'ok': False, 'error': None, 'baseline_restored': False}
        try:
            for name, active in (('baseline', document['active_layers']), ('layer', layers)):
                restored = self.restore_experiment(experiment)
                result[name] = self._experiment_trial(document, restored, deadline, active)
                if not result[name]['ok']:
                    result['error'] = {'type': 'ScriptFailure', 'trial': name, 'step': result[name]['script_error']}
                    break
            if result['baseline'] is not None and result['layer'] is not None:
                result['comparison'] = compare_trials(result['baseline'], result['layer'])
                result['ok'] = result['comparison']['complete']
        except Exception as error:
            result['error'] = {'type': type(error).__name__, 'message': str(error)}
        finally:
            if not self.closed:
                try:
                    result['restored_controls'] = self.restore_experiment(experiment)['controls']
                    result['baseline_restored'] = True
                except Exception as error:
                    result['error'] = {'type': type(error).__name__, 'message': 'Final restore: ' + str(error)}
            if not result['baseline_restored']:
                result['ok'] = False
        # Trace bodies stay in their original artifacts; reports contain references and the first difference.
        for name in ('baseline', 'layer'):
            if result[name]:
                for trace in result[name]['traces']:
                    trace.pop('events')
        artifact = self._artifact('experiment-comparison.json', 'experiment-comparison', encoded(result),
                                  {'experiment': experiment, 'ok': result['ok'], 'baseline_restored': result['baseline_restored']})
        return {**result, 'artifact': artifact['artifact']}
