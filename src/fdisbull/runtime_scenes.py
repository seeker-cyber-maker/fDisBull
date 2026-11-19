"""Explicit passive scene models over witnessed runtime RAM.

Scene-1 remains a screenshot/frame contract. This separate profile cannot grant
pixel geometry, action, source-symbol, allocation or completed-frame authority.
"""
from copy import deepcopy
import hashlib
import json
import re
import time
import uuid

from .scene_values import ObservationReads, scalar_type


FORMAT = 'fdisbull-scene-2'
PROFILE = {'kind': 'runtime-memory', 'version': 1}
_TOP = {'format', 'observation_profile', 'source_identity', 'context', 'match',
        'content', 'exclusive_group', 'objects'}
_OBJECT = {'id', 'name', 'aliases', 'context', 'visible', 'ready', 'enabled', 'outcome', 'exclusive_group'}


def is_runtime_scene(value):
    return isinstance(value, dict) and value.get('format') == FORMAT


def require_frame_scene(info):
    if info['definition'].get('format') != 'fdisbull-scene-1':
        raise ValueError('This consumer requires a frame-backed scene-1 profile; passive runtime scenes grant no frame or action authority')
    return info


def source_identity(project, version):
    selected = project.version(version)
    return dict(source_sha256=project.meta['source_sha256'], version=selected['id'],
                version_sha256=selected['sha256'])


def validate_definition(definition, *, identity=None, stored=False):
    """Finite concrete schema; stored binding names never create live bindings."""
    from .scenes import encoded, name, context, predicate
    if not isinstance(definition, dict) or set(definition) - _TOP:
        raise ValueError('Invalid passive runtime scene fields')
    doc = deepcopy(definition)
    required = {'format', 'observation_profile', 'context', 'match', 'objects'}
    if not required <= set(doc) or doc['format'] != FORMAT or doc['observation_profile'] != PROFILE:
        raise ValueError('Expected scene-2 with observation_profile runtime-memory version 1')
    if type(doc['observation_profile']['version']) is not int:
        raise ValueError('Runtime observation profile version must be integer 1')
    if 'source_identity' in doc:
        source = doc['source_identity']
        if (not isinstance(source, dict) or set(source) != {'source_sha256', 'version', 'version_sha256'}
                or type(source['version']) is not int or source['version'] < 1
                or any(not isinstance(source[key], str) or not re.fullmatch('[0-9a-f]{64}', source[key])
                       for key in ('source_sha256', 'version_sha256'))):
            raise ValueError('Invalid runtime scene source/version identity')
    if len(encoded(doc)) > 1024 * 1024: raise ValueError('Runtime scene exceeds 1 MiB')
    if identity is not None:
        if 'source_identity' in doc and doc['source_identity'] != identity:
            raise ValueError('Runtime scene source or selected byte version differs')
        if stored and doc.get('source_identity') != identity:
            raise ValueError('Stored runtime scene lacks its source/version identity')
        doc['source_identity'] = deepcopy(identity)
    context(doc['context'])
    doc.setdefault('exclusive_group', 'main'); name(doc['exclusive_group'])
    objects = doc['objects']
    if not isinstance(objects, list) or not 1 <= len(objects) <= 64:
        raise ValueError('Runtime scene requires 1..64 passive objects')
    budget, refs = [0], set()

    def count(depth):
        budget[0] += 1
        if depth > 8 or budget[0] > 4096: raise ValueError('Runtime scene exceeds its finite predicate budget')

    def binding(ref, width):
        token, offset = ref.get('binding'), ref.get('offset', 0)
        if (not isinstance(token, str) or not 1 <= len(token) <= 128 or token.startswith('$')
                or type(offset) is not int or not 0 <= offset <= 65535 or offset + width > 65536):
            raise ValueError('Runtime scene requires a literal binding and bounded byte extent')
        refs.add((token, offset, width))
        if sum(item[2] for item in refs) > 65536: raise ValueError('Runtime scene observations exceed 64 KiB')

    def expression(value, depth=0):
        count(depth)
        if type(value) is int: return
        if not isinstance(value, dict) or len(value) != 1: raise ValueError('Invalid runtime scene scalar expression')
        op, item = next(iter(value.items()))
        if op == 'runtime_memory': binding(item, scalar_type(item['type'])[0])
        elif op in ('add', 'sub'):
            for child in item: expression(child, depth+1)
        elif op == 'wrap': expression(item['value'], depth+1)
        else: raise ValueError('Runtime scene expressions permit witnessed RAM only; source, engine and before state are unsupported')

    def walk(value, depth=0):
        count(depth)
        op, item = next(iter(value.items()))
        if op == 'constant': return
        if op in ('all', 'any'):
            for child in item: walk(child, depth+1)
        elif op == 'not': walk(item, depth+1)
        elif op == 'runtime_memory': binding(item, item['length'])
        elif op == 'compare':
            expression(item['left'], depth+1); expression(item['right'], depth+1)
        else: raise ValueError('Runtime scene predicates do not support pixels, source memory or action baselines')

    def check(value):
        # The established predicate grammar validates shape, widths, values and
        # arity before this profile walks every child, including false branches.
        predicate(value, 1, 1, allow_before=False)
        walk(value)

    check(doc['match'])
    if 'content' in doc:
        if not isinstance(doc['content'], dict) or set(doc['content']) != {'requested', 'displayed', 'ready'}:
            raise ValueError('Content requires requested, displayed and ready predicates')
        for value in doc['content'].values(): check(value)
    names, ids = set(), set()
    for obj in objects:
        if (not isinstance(obj, dict) or set(obj) - _OBJECT or
                not {'name', 'context', 'visible', 'ready', 'enabled', 'outcome'} <= set(obj)):
            raise ValueError('Runtime scene objects contain passive predicates, never actions or pixel geometry')
        context(obj['context']); name(obj['name'])
        aliases = obj.setdefault('aliases', [])
        if not isinstance(aliases, list) or len(aliases) > 32: raise ValueError('Invalid object aliases')
        for label in [obj['name'], *aliases]:
            name(label)
            if label in names: raise ValueError('Duplicate scene object name or alias')
            names.add(label)
        if 'id' in obj:
            identifier = obj['id']
            if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier) or identifier in ids:
                raise ValueError('Invalid or duplicate passive object identity')
            ids.add(identifier)
        elif stored: raise ValueError('Stored passive object lacks its identity')
        if 'exclusive_group' in obj: name(obj['exclusive_group'])
        for field in ('visible', 'ready', 'enabled', 'outcome'): check(obj[field])
    if not refs: raise ValueError('A runtime-memory scene requires at least one explicit RAM observation')
    if stored and doc != definition: raise ValueError('Stored runtime scene is missing canonical fields')
    return doc


def save_scene(project, scene_name, definition, *, parent=None, version=None, author='agent'):
    from .scenes import encoded, name
    from .project import now
    name(scene_name)
    if not isinstance(author, str) or not 1 <= len(author) <= 256: raise ValueError('Scene author required')
    identity = source_identity(project, version); version = identity['version']
    doc = validate_definition(definition, identity=identity)
    root = project.db.execute('SELECT id FROM debug_scenes WHERE version=? AND name=?', (version, scene_name)).fetchone()
    root_id = root['id'] if root else uuid.uuid4().hex
    previous = project.db.execute('SELECT id FROM debug_scene_revisions WHERE scene=? ORDER BY rowid DESC LIMIT 1', (root_id,)).fetchone()
    if (previous['id'] if previous else None) != parent: raise ValueError('Scene parent must be the current revision')
    prior = project.debug_scene_info(parent, version=version)['definition'] if parent else None
    if prior is not None and not is_runtime_scene(prior): raise ValueError('Scene revisions cannot change observation profile')
    old_names = {obj['name']: obj for obj in prior['objects']} if prior else {}
    old_ids = {obj['id']: obj for obj in prior['objects']} if prior else {}
    for obj in doc['objects']:
        if 'id' in obj and obj['id'] not in old_ids: raise ValueError('Unknown persistent object id')
        obj['id'] = obj.get('id', old_names.get(obj['name'], {}).get('id', uuid.uuid4().hex))
        if obj['id'] in old_ids and obj['name'] != old_ids[obj['id']]['name']:
            obj['aliases'] = list(dict.fromkeys([a for a in obj['aliases'] if a != obj['name']] + [old_ids[obj['id']]['name']]))
    doc = validate_definition(doc, identity=identity, stored=True)
    digest, revision = hashlib.sha256(encoded(doc)).hexdigest(), uuid.uuid4().hex
    with project.transaction(True):
        current = project.db.execute('SELECT id FROM debug_scene_revisions WHERE scene=? ORDER BY rowid DESC LIMIT 1', (root_id,)).fetchone()
        if (current['id'] if current else None) != parent: raise ValueError('Scene revision changed during save')
        if not root: project.db.execute('INSERT INTO debug_scenes VALUES (?,?,?)', (root_id, version, scene_name))
        for obj in doc['objects']:
            project.db.execute('INSERT OR IGNORE INTO debug_scene_objects VALUES (?,?)', (obj['id'], root_id))
        project.db.execute('INSERT INTO debug_scene_revisions VALUES (?,?,?,?,?,?,?)',
            (revision, root_id, parent, now(), author, digest, encoded(doc).decode()))
    return project.debug_scene_info(revision, version=version)


def validate_stored(project, info, document):
    validated = validate_definition(document, identity=source_identity(project, info['version']), stored=True)
    for obj in validated['objects']:
        row = project.db.execute('SELECT scene FROM debug_scene_objects WHERE id=?', (obj['id'],)).fetchone()
        if row is None or row['scene'] != info['scene']: raise ValueError('Passive object belongs to another scene')
    if project.db.execute('SELECT 1 FROM debug_scene_evidence WHERE revision=?', (info['id'],)).fetchone():
        raise ValueError('Passive runtime scene cannot carry implicit frame evidence')


def validate_parameters(scene, *, object=None, compact=False, allow_references=False):
    # Only scalar script result references may defer their own unknown value.
    for name, value in (('scene', scene), ('object', object)):
        if name == 'object' and value is None: continue
        if not isinstance(value, str) or not 1 <= len(value) <= 256: raise ValueError('Invalid scene/object reference')
        if value.startswith('$') and not allow_references: raise ValueError('Scene reference must be resolved before observation')
    if not (allow_references and isinstance(compact, str) and compact.startswith('$')) and type(compact) is not bool:
        raise ValueError('compact must be boolean')


def select(project, scene, version, target=None):
    info = project.debug_scene_info(scene, version=version)
    if not is_runtime_scene(info['definition']):
        raise ValueError('QEMU passive scene checks require explicit scene-2 runtime-memory profile')
    selected = None
    if target is not None:
        found = [obj for obj in info['definition']['objects'] if target in (obj['id'], obj['name'], *obj['aliases'])]
        if len(found) != 1: raise ValueError('Unknown scene object')
        selected = found[0]
    return info, selected


def companions(project, info, version):
    # Bound catalog admission and combined bytes before the first native read.
    count = project.db.execute('SELECT count(*) FROM debug_scenes WHERE version=?', (version,)).fetchone()[0]
    if count > 256: raise ValueError('Passive scene catalog exceeds the 256-scene admission budget')
    others = [other for other in project.debug_scenes(version=version)['scenes']
              if other['scene'] != info['scene'] and is_runtime_scene(other['definition'])
              and other['definition']['exclusive_group'] == info['definition']['exclusive_group']]
    if len(others) > 63: raise ValueError('Passive scene group exceeds 64 candidate scenes')
    def expression_cost(value):
        if type(value) is int:return 1
        op,child=next(iter(value.items()))
        if op in ('add','sub'):return 1+sum(expression_cost(item) for item in child)
        if op=='wrap':return 1+expression_cost(child['value'])
        return 1
    def predicate_cost(value):
        op,child=next(iter(value.items()))
        if op in ('all','any'):return 1+sum(predicate_cost(item) for item in child)
        if op=='not':return 1+predicate_cost(child)
        if op=='compare':return 1+expression_cost(child['left'])+expression_cost(child['right'])
        return 1
    from .scenes import _predicates
    specs=[*_predicates(info['definition']),*(other['definition']['match'] for other in others)]
    if sum(predicate_cost(spec) for spec in specs)>4096:
        raise ValueError('Combined scene predicate/expression work exceeds 4096 nodes')
    refs = set()
    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'runtime_memory':
                    width = child['length'] if 'length' in child else scalar_type(child['type'])[0]
                    refs.add((child['binding'], child.get('offset', 0), width))
                else: collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
    collect(info['definition'])
    for other in others: collect(other['definition']['match'])
    if sum(ref[2] for ref in refs) > 65536: raise ValueError('Combined scene observations exceed 64 KiB')
    return others


class _EvaluationStopped(ValueError):
    pass


class _EvaluationBudget:
    def __init__(self, deadline, evidence, owner_guard):
        self.deadline,self.evidence=deadline,evidence
        self.owner_guard,self.primary_error=owner_guard,None
        self.nodes,self.evidence_count,self.evidence_bytes,self.capture_bytes=0,0,0,0
        self.failure=None

    def fail(self, reason):
        if self.failure is None:self.failure=str(reason)[:1024]
        raise _EvaluationStopped(self.failure)

    def check(self):
        if self.failure is not None:raise _EvaluationStopped(self.failure)
        if time.monotonic()>=self.deadline:self.fail('Passive scene evaluation host deadline expired')
        try:self.owner_guard()
        except BaseException as error:
            self.primary_error=error
            self.fail(f'{type(error).__name__}: {error}')
        from .scenes import encoded
        for entry in self.evidence[self.evidence_count:]:
            size=len(encoded(entry))
            if self.evidence_bytes+size>1024*1024:
                del self.evidence[self.evidence_count:]
                self.fail('Passive scene predicate evidence exceeds 1 MiB')
            self.evidence_bytes+=size;self.evidence_count+=1

    def guard(self):
        self.check();self.nodes+=1
        if self.nodes>4096:self.fail('Passive scene evaluation exceeds 4096 predicate nodes')

    def finish_failure_evidence(self):
        # The shared evaluator may append one error after a read guard refused.
        # Retain the first failure without letting that final entry exceed its cap.
        from .scenes import encoded
        for entry in self.evidence[self.evidence_count:]:
            size=len(encoded(entry))
            if self.evidence_bytes+size>1024*1024:
                del self.evidence[self.evidence_count:]
                break
            self.evidence_bytes+=size;self.evidence_count+=1


class _BudgetedReads(ObservationReads):
    def __init__(self, session, budget):
        super().__init__(session);self.budget=budget

    def read_runtime(self, binding, offset, length):
        self.budget.check()
        key=f'runtime/{binding}/{offset}/{length}'
        fresh=key not in self.captures
        if fresh and len(self.captures)>=256:self.budget.fail('Passive scene exceeds 256 unique capture receipts')
        try:
            result=super().read_runtime(binding,offset,length)
        except Exception as error:
            self.captures.pop(key,None)
            self.budget.fail(f'{type(error).__name__}: {error}')
        if fresh:
            from .scenes import encoded
            size=len(encoded(self.captures[key]))
            if self.budget.capture_bytes+size>4*1024*1024:
                del self.captures[key]
                self.budget.fail('Passive scene capture receipts exceed 4 MiB')
            self.budget.capture_bytes+=size
        self.budget.check()
        return result


def observation_result(session, info, selected):
    doc = info['definition']
    return dict(format='fdisbull-scene-observation-2', observation_profile=deepcopy(PROFILE),
        completion_scope='declared-runtime-predicates', scene_revision=info['id'], manifest_sha256=info['sha256'],
        source_identity=deepcopy(doc['source_identity']), object_id=selected['id'] if selected else None,
        status='unavailable', complete=False, scene_matched=None, content={}, objects={}, availability={}, evidence=[], conflicts=[], handlers=[], run=session.run_id,
        claim='Stopped caller-witnessed RAM predicates only; no pixel, frame, action or source/allocation lifetime authority.')


def evaluate(session, info, selected, others, result, *, deadline, owner_guard):
    """Use the shared conservative predicate evaluator and scalar captures."""
    from .scenes import _evaluate
    doc=info['definition']
    budget=_EvaluationBudget(deadline,result['evidence'],owner_guard);reads=_BudgetedReads(session,budget)
    def check(value):
        result=_evaluate(value,session,{},budget.evidence,reads,guard=budget.guard)
        budget.check()
        return result
    try:
        _evaluate_scene(doc,selected,others,result,check)
        budget.check()
    except _EvaluationStopped:
        budget.finish_failure_evidence()
        result.update(status='unavailable',complete=False,evaluation_stopped=True,error=budget.failure)
    result['read_statistics'],result['memory_captures']=reads.stats(),list(reads.captures.values())
    result['evaluation_budget']=dict(predicate_nodes=budget.nodes,predicate_evidence_bytes=budget.evidence_bytes,
        capture_receipt_bytes=budget.capture_bytes,stopped=budget.failure is not None)
    result['candidate_manifests']=[dict(scene_revision=other['id'],manifest_sha256=other['sha256']) for other in others]
    if budget.primary_error is not None:
        error=budget.primary_error
        if getattr(error,'result',None) is None:error.result=result
        else:error.scene_result=result
        raise error
    return result


def _evaluate_scene(doc, selected, others, result, check):
    matched = check(doc['match']); result['scene_matched'] = matched
    result['content'] = {key: check(value) for key, value in doc.get('content', {}).items()}
    unknown = False
    for other in others:
        other_doc = other['definition']
        value = check(other_doc['match']); unknown |= value is None
        if value is True and matched is True:
            result['conflicts'].append(dict(kind='scene-recognition', scene_revision=other['id']))
    available, groups = {}, {}
    for obj in doc['objects']:
        available[obj['id']] = {field: check(obj[field]) for field in ('visible', 'ready', 'enabled')}
        unknown |= None in available[obj['id']].values()
        if obj.get('exclusive_group') and available[obj['id']]['visible'] is True:
            groups.setdefault(obj['exclusive_group'], []).append(obj['id'])
    result['objects'] = available
    for group, identifiers in groups.items():
        if len(identifiers) > 1: result['conflicts'].append(dict(kind='object-recognition', group=group, object_ids=identifiers))
    if selected:
        result['availability'] = available[selected['id']]
        result['initial_outcome'] = check(selected['outcome']); unknown |= result['initial_outcome'] is None
    required = [matched, *result['content'].values(), *result['availability'].values()]
    if result['conflicts']: result['status'] = 'ambiguous'
    elif unknown or None in required: result['status'] = 'unavailable'
    else: result['status'] = 'matched' if all(required) else 'mismatch'
    result['complete'] = result['status'] in ('matched', 'mismatch')


def store(session, result):
    from .project import now
    from .scenes import encoded
    identifier = uuid.uuid4().hex
    with session.project.transaction(True):
        session.project.db.execute('INSERT INTO debug_scene_observations VALUES (?,?,?,?,?,?)',
            (identifier, result['scene_revision'], session.run_id, now(), result['status'], encoded(result).decode()))
    return dict(result, observation=identifier)
