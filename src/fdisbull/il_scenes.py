"""A small scene backing for Z: shared IL executes actions; the player renders.

This is a projection envelope, not another rule language or native interpreter.
Only pure fdisbull-il-1 state/text effects execute. Source claims stay private.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading

from fdisbull.interaction_il import execute_il, validate_il

LIMIT = 1024 * 1024


def _fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) <= set(required) | set(optional):
        raise ValueError('Invalid scene fields')


def _text(value):
    if not isinstance(value, str) or not value:
        raise ValueError('Expected scene text')


def _read(path):
    with Path(path).open('rb') as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('Scene input exceeds limit')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=unique)


class ILSceneBackend:
    """One authoritative typed IL state, exposed through the existing Z protocol.

    Checkpoints are deliberately in-memory, for bounded tests. Native effects,
    autonomous time, durable saves and general UDC compilation are not supplied.
    """
    def __init__(self, definition, *, project=None, version=None, state=None):
        try:
            encoded = json.dumps(definition, allow_nan=False).encode()
            if len(encoded) > LIMIT:
                raise ValueError('Scene definition exceeds limit')
            self.definition = deepcopy(definition)
            doc = self.definition
            _fields(doc, ('format', 'programs', 'contexts', 'objects', 'partial'))
            if doc['format'] != 'fdisbull-il-scene-1' or type(doc['partial']) is not bool:
                raise ValueError('Invalid scene format')
            if not isinstance(doc['programs'], dict) or not 1 <= len(doc['programs']) <= 32:
                raise ValueError('Invalid scene programs')
            self.programs, self.sources = {}, {}
            for name, program in doc['programs'].items():
                _text(name)
                if isinstance(program, dict) and set(program) == {'revision'}:
                    _text(program['revision'])
                    if project is None:
                        raise ValueError('Stored IL requires its source project')
                    from fdisbull.il_recovery import load_il
                    loaded = load_il(project, program['revision'], version=version)
                    self.sources[name] = {k: loaded[k] for k in ('id', 'version', 'sha256', 'author')}
                    program = loaded['document']
                validate_il(program)
                def text_bytes(body):
                    total = 0
                    for block in body:
                        if block['op'] == 'text':
                            total += len(program['resources'][block['resource']]['text'].encode('utf-8'))
                        elif block['op'] == 'if':
                            total += text_bytes(block['then']) + text_bytes(block['else'])
                    return total
                if text_bytes(program['body']) > 32768:
                    raise ValueError('Action text exceeds the Z output budget')
                self.programs[name] = deepcopy(program)
            first = next(iter(self.programs.values()))
            self.variables = deepcopy(first['variables'])
            if any(p['variables'] != self.variables for p in self.programs.values()):
                raise ValueError('Scene programs must share typed declarations')
            self.template = {'format': 'fdisbull-il-1', 'role': 'uil',
                             'variables': self.variables, 'resources': {}, 'body': []}
            initial = execute_il(self.template, state=state)
            if not initial['complete']:
                raise ValueError('Invalid scene initial state')
            self.state = initial['state']
            contexts, objects = doc['contexts'], doc['objects']
            if not isinstance(contexts, list) or not 1 <= len(contexts) <= 64:
                raise ValueError('Invalid contexts')
            if not isinstance(objects, list) or len(objects) > 256:
                raise ValueError('Invalid objects')
            context_ids = set()
            for context in contexts:
                _fields(context, ('id', 'title', 'description', 'when'))
                for key in ('id', 'title', 'description'):
                    _text(context[key])
                if context['id'] in context_ids:
                    raise ValueError('Duplicate context')
                context_ids.add(context['id'])
                self._check_condition(context['when'])
            ids = set()
            for obj in objects:
                _fields(obj, ('id', 'context', 'label', 'aliases', 'description', 'bindings'),
                        ('visible_when', 'inventory_when'))
                for key in ('id', 'context', 'label', 'description'):
                    _text(obj[key])
                if obj['id'] in ids or obj['context'] not in context_ids:
                    raise ValueError('Invalid object identity or context')
                ids.add(obj['id'])
                if not isinstance(obj['aliases'], list) or not all(isinstance(a, str) and a for a in obj['aliases']):
                    raise ValueError('Invalid aliases')
                for field in ('visible_when', 'inventory_when'):
                    if field in obj:
                        self._check_condition(obj[field])
                if not isinstance(obj['bindings'], list) or len(obj['bindings']) > 64:
                    raise ValueError('Invalid bindings')
                bindings = set()
                for binding in obj['bindings']:
                    _fields(binding, ('verb', 'program'), ('item',))
                    _text(binding['verb']); _text(binding['program'])
                    item = binding.get('item')
                    if item is not None:
                        _text(item)
                    key = (binding['verb'], item)
                    if key in bindings or binding['program'] not in self.programs:
                        raise ValueError('Duplicate or unresolved binding')
                    bindings.add(key)
            for obj in objects:
                if any(b.get('item') is not None and b['item'] not in ids for b in obj['bindings']):
                    raise ValueError('Unknown item binding')
        except (TypeError, KeyError, RecursionError) as exc:
            raise ValueError('Invalid scene definition') from exc
        self.lock = threading.RLock()
        self.revision = 0
        self.epoch = secrets.token_hex(32)
        self.checkpoints = {}

    def _predicate(self, condition):
        program = deepcopy(self.template)
        program['body'] = [{'id': 'scene-condition', 'op': 'require', 'condition': condition}]
        return program

    def _check_condition(self, condition):
        validate_il(self._predicate(condition))

    def _holds(self, condition):
        return execute_il(self._predicate(condition), self.state)['complete']

    def _token(self):
        return hashlib.sha256((self.epoch + ':' + str(self.revision)).encode()).hexdigest()

    def observe(self):
        with self.lock:
            contexts = [c for c in self.definition['contexts'] if self._holds(c['when'])]
            if len(contexts) != 1:
                return {'complete': False}
            context = contexts[0]
            observation = {'complete': True, 'session_token': self.epoch,
                'context': {k: context[k] for k in ('id', 'title', 'description')},
                'objects': [], 'inventory': [], 'coverage': {'partial': self.definition['partial']}}
            observation['context']['token'] = self._token()
            for obj in self.definition['objects']:
                carried = 'inventory_when' in obj and self._holds(obj['inventory_when'])
                visible = obj['context'] == context['id'] and ('visible_when' not in obj or self._holds(obj['visible_when']))
                if not carried and not visible:
                    continue
                public = {k: deepcopy(obj[k]) for k in ('id', 'label', 'aliases', 'description')}
                public['verbs'] = list(dict.fromkeys(b['verb'] for b in obj['bindings']))
                observation['inventory' if carried else 'objects'].append(public)
            return observation

    def act(self, request):
        with self.lock:
            def result(status, complete, message):
                return {'status': status, 'complete': complete, 'message': message}
            if (not isinstance(request, dict) or set(request) != {'verb', 'target', 'item', 'context_token'}
                    or not all(isinstance(request[k], str) for k in ('verb', 'target', 'context_token'))
                    or request['item'] is not None and not isinstance(request['item'], str)):
                return result('incomplete', False, 'Invalid action request.')
            observation = self.observe()
            if not observation['complete']:
                return result('incomplete', False, 'Observation incomplete.')
            if request['context_token'] != observation['context']['token']:
                return result('rejected', True, 'Context changed.')
            visible = {o['id'] for o in observation['objects'] + observation['inventory']}
            if request['target'] not in visible or request['item'] is not None and request['item'] not in visible:
                return result('rejected', True, 'Action unavailable.')
            obj = next(o for o in self.definition['objects'] if o['id'] == request['target'])
            bindings = [b for b in obj['bindings'] if b['verb'] == request['verb'] and b.get('item') == request['item']]
            if len(bindings) != 1:
                return result('rejected', True, 'Action unavailable.')
            outcome = execute_il(self.programs[bindings[0]['program']], self.state)
            if not outcome['complete']:
                if outcome.get('error') == 'qualification condition not met':
                    return result('rejected', True, 'Action refused.')
                return result('incomplete', False, 'Action unsupported or incomplete.')
            self.state = outcome['state']
            self.revision += 1
            text = ''.join(e['resource_data']['text'] for e in outcome['events'] if e['op'] == 'text')
            # A confirmed pure-IL commit stays confirmed if the next scene is outside coverage.
            return result('success', True, text or 'Action completed.')

    def save(self, slot='live'):
        with self.lock:
            if not isinstance(slot, str) or not 1 <= len(slot) <= 64:
                return {'complete': False, 'status': 'incomplete'}
            if slot not in self.checkpoints and len(self.checkpoints) >= 64:
                return {'complete': False, 'status': 'incomplete'}
            self.checkpoints[slot] = deepcopy(self.state)
            return {'complete': True, 'status': 'saved', 'checkpoint': slot, 'replay_safe': True}

    def load(self, checkpoint='live'):
        with self.lock:
            if not isinstance(checkpoint, str) or not 1 <= len(checkpoint) <= 64:
                return {'complete': False, 'status': 'incomplete'}
            if checkpoint not in self.checkpoints:
                return {'complete': True, 'status': 'missing', 'checkpoint': checkpoint}
            self.state = deepcopy(self.checkpoints[checkpoint])
            self.revision += 1
            return {'complete': True, 'status': 'restored', 'checkpoint': checkpoint, 'replay_safe': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Serve shared IL scenes to a Z text player without a debugger')
    parser.add_argument('scene')
    parser.add_argument('--project', help='project for source-verified immutable IL revision references')
    parser.add_argument('--version', type=int)
    parser.add_argument('--state', help='private typed starting-state JSON')
    args = parser.parse_args(argv)
    try:
        from contextlib import nullcontext
        from fdisbull.project import Project
        from fdisbull.text_projection import serve_stream
        with Project(args.project) if args.project else nullcontext() as project:
            backend = ILSceneBackend(_read(args.scene), project=project, version=args.version,
                                     state=_read(args.state) if args.state else None)
        serve_stream(backend, sys.stdin, sys.stdout)
        return 0
    except (ValueError, OSError, RecursionError) as exc:
        print(json.dumps({'complete': False, 'status': 'stopped', 'error': type(exc).__name__}), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
