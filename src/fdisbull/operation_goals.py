"""Bounded operation definitions and backward recovery goals beside common UIL.

This companion describes known UDL blocks, authored composition and missing
knowledge. It does not execute an operation or prove its semantic labels.
Execution dependencies stay separate from dependencies of recovery work.
"""

from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import re

from .common_uil import canonical_bytes, digest, load_json


FORMAT = 'fdisbull-operation-goals-1'
PLAN_FORMAT = 'fdisbull-operation-goal-plan-1'
_ID = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,63}\Z')
_SCOPES = ('candidate', 'observed', 'bounded')


def operation_goal_schema():
    """Return the bundled structural JSON Schema without a runtime dependency."""
    return json.loads(files('fdisbull').joinpath('data/operation-goals-1.schema.json').read_text())


def _fields(value, required, optional=()):
    if (type(value) is not dict or not set(required) <= value.keys()
            or value.keys() - set(required) - set(optional)):
        raise ValueError('invalid operation-goal fields')


def _text(value, maximum=256):
    if type(value) is not str or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError('bounded nonempty text/reference required')
    return value


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError('ID must be an identifier of at most64 characters')
    return value


def _list(value, maximum, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError('operation-goal list exceeds its declared bounds')
    return value


def _ids(value, maximum=64):
    items = [_id(v) for v in _list(value, maximum)]
    if len(set(items)) != len(items):
        raise ValueError('duplicate operation-goal reference')
    return items


def _evidence(value):
    return [_text(v, 512) for v in _list(value, 16)]


def _scope(value):
    if value not in _SCOPES:
        raise ValueError('scope must be candidate, observed or bounded')


def _ports(value):
    ports = {}
    for port in _list(value, 64):
        _fields(port, ('id', 'type'))
        ident = _id(port['id'])
        if ident in ports:
            raise ValueError('duplicate port ID')
        ports[ident] = _text(port['type'], 128)
    return ports


def _index(items, maximum):
    result = {}
    for item in _list(items, maximum):
        if type(item) is not dict:
            raise ValueError('operation-goal declaration must be an object')
        ident = _id(item.get('id'))
        if ident in result:
            raise ValueError('duplicate declaration ID')
        result[ident] = item
    return result


def _acyclic(edges, label):
    done, active = set(), set()
    def visit(node):
        if node in active:
            raise ValueError(label + ' contains a cycle')
        if node in done:
            return
        active.add(node)
        for child in edges[node]:
            if child not in edges:
                raise ValueError(label + ' references an unknown node')
            visit(child)
        active.remove(node)
        done.add(node)
    for node in edges:
        visit(node)


def validate_operation_goals(document):
    """Validate syntax, identities, typed wiring and both dependency graphs.

Port types here are nominal references. Matching them is not admission to an
executable UIL profile. Opaque regions and unresolved signatures are explicit.
"""
    if len(canonical_bytes(document)) > 1024 * 1024:
        raise ValueError('operation-goal document exceeds1MiB')
    _fields(document, ('format', 'blocks', 'operations', 'knowledge', 'findings', 'correspondences'))
    if document['format'] != FORMAT:
        raise ValueError('unsupported operation-goal format')
    blocks = _index(document['blocks'], 128)
    operations = _index(document['operations'], 64)
    knowledge = _index(document['knowledge'], 128)
    for block in blocks.values():
        _fields(block, ('id', 'udl_ref', 'region_ref', 'signature', 'inputs', 'outputs',
                        'resolution', 'scope', 'evidence', 'needs'))
        _text(block['udl_ref']); _text(block['region_ref'])
        inputs, outputs = _ports(block['inputs']), _ports(block['outputs'])
        if block['signature'] not in ('unknown', 'declared'):
            raise ValueError('invalid block signature status')
        if block['resolution'] not in ('opaque', 'partial', 'resolved'):
            raise ValueError('invalid block resolution status')
        if block['signature'] == 'unknown' and (inputs or outputs or block['resolution'] == 'resolved'):
            raise ValueError('unknown signature cannot declare ports or resolved analysis')
        _scope(block['scope']); _evidence(block['evidence'])
        if set(_ids(block['needs'])) - knowledge.keys():
            raise ValueError('block references unknown knowledge')
    for item in knowledge.values():
        _fields(item, ('id', 'question', 'needs', 'scope', 'evidence'))
        _text(item['question'], 2048); _scope(item['scope']); _evidence(item['evidence'])
        _ids(item['needs'])
    _acyclic({k: set(v['needs']) for k, v in knowledge.items()}, 'knowledge dependency graph')
    operation_edges = {}
    for operation in operations.values():
        _fields(operation, ('id', 'inputs', 'outputs', 'steps', 'results', 'scope', 'evidence'))
        inputs, outputs = _ports(operation['inputs']), _ports(operation['outputs'])
        _scope(operation['scope']); _evidence(operation['evidence'])
        steps = _index(operation['steps'], 64)
        if not steps:
            raise ValueError('use an explicit block for an unresolved/opaque operation')
        signatures, execution_edges = {}, {}
        operation_edges[operation['id']] = set()
        for step in steps.values():
            _fields(step, ('id', 'kind', 'ref', 'inputs', 'after'))
            _id(step['ref'])
            if step['kind'] not in ('block', 'operation'):
                raise ValueError('step kind must be block or operation')
            pool = blocks if step['kind'] == 'block' else operations
            if step['ref'] not in pool:
                raise ValueError('step references an unknown definition')
            target = pool[step['ref']]
            signatures[step['id']] = (_ports(target['inputs']), _ports(target['outputs']))
            execution_edges[step['id']] = set(_ids(step['after']))
            if step['kind'] == 'operation':
                operation_edges[operation['id']].add(step['ref'])
        def reference_type(reference):
            _text(reference)
            parts = reference.split(':')
            if len(parts) == 2 and parts[0] == 'input' and parts[1] in inputs:
                return inputs[parts[1]], None
            if (len(parts) == 3 and parts[0] == 'step' and parts[1] in signatures
                    and parts[2] in signatures[parts[1]][1]):
                return signatures[parts[1]][1][parts[2]], parts[1]
            raise ValueError('invalid typed port reference')
        for step in steps.values():
            if type(step['inputs']) is not dict or set(step['inputs']) != set(signatures[step['id']][0]):
                raise ValueError('step input bindings do not match declared ports')
            for name, ref in step['inputs'].items():
                typ, producer = reference_type(ref)
                if typ != signatures[step['id']][0][name]:
                    raise ValueError('step input type mismatch')
                if producer:
                    execution_edges[step['id']].add(producer)
        if type(operation['results']) is not dict or set(operation['results']) != set(outputs):
            raise ValueError('operation output bindings incomplete')
        for name, reference in operation['results'].items():
            if reference_type(reference)[0] != outputs[name]:
                raise ValueError('operation output type mismatch')
        _acyclic(execution_edges, 'operation step graph')
    _acyclic(operation_edges, 'operation definition graph')
    seen_findings = set()
    for finding in _list(document['findings'], 256):
        _fields(finding, ('kind', 'ref', 'scope', 'evidence'))
        if finding['kind'] not in ('knowledge', 'block-result'):
            raise ValueError('unknown finding kind')
        pool = knowledge if finding['kind'] == 'knowledge' else blocks
        if finding['ref'] not in pool:
            raise ValueError('finding refers to unknown identity')
        key = (finding['kind'], finding['ref'])
        if key in seen_findings:
            raise ValueError('duplicate finding')
        seen_findings.add(key)
        _scope(finding['scope']); _evidence(finding['evidence'])
    for mapping in _index(document['correspondences'], 256).values():
        _fields(mapping, ('id', 'logical', 'stages', 'scope', 'evidence'))
        logical = mapping['logical']
        _fields(logical, ('operation', 'port', 'field', 'type'))
        if logical['operation'] not in operations:
            raise ValueError('correspondence refers to unknown operation')
        parts = _text(logical['port']).split(':')
        if len(parts) != 2 or parts[0] not in ('input', 'output'):
            raise ValueError('correspondence needs input/output port reference')
        if parts[1] not in _ports(operations[logical['operation']][parts[0] + 's']):
            raise ValueError('correspondence refers to unknown logical port')
        _text(logical['field']); _text(logical['type'], 128)
        _scope(mapping['scope']); _evidence(mapping['evidence'])
        for stage in _list(mapping['stages'], 16, 1):
            _fields(stage, ('kind', 'ref'), ('offset', 'length', 'encoding'))
            if stage['kind'] not in ('record', 'buffer', 'file-range', 'opaque-region'):
                raise ValueError('invalid correspondence stage kind')
            _text(stage['ref'])
            for name in ('offset', 'length'):
                if name in stage and (type(stage[name]) is not int or not 0 <= stage[name] <= 0xFFFFFFFF):
                    raise ValueError('correspondence ranges need bounded unsigned integers')
            if 'encoding' in stage:
                _text(stage['encoding'], 128)
    return deepcopy(document)


def load_operation_goals(path):
    return validate_operation_goals(load_json(path))


def _definition_digest(document):
    # Findings and analysis progress must not rename the operation or known UDL
    # blocks. A changed composition/signature/source reference does change it.
    core = deepcopy(document)
    core.pop('findings')
    for section in ('blocks', 'operations', 'knowledge', 'correspondences'):
        for item in core[section]:
            for key in ('resolution', 'scope', 'evidence'):
                item.pop(key, None)
    return digest(core)


def plan_operation(document, operation_id, available=()):
    """Backward-plan recovery work; never execute or synthesize missing blocks.

Available facts mean available information, including candidate findings. They
do not change the definition's resolution or assurance. Execution `after`/data
edges are preserved, while recovery only waits for declared knowledge needs.
"""
    _id(operation_id)
    document = validate_operation_goals(document)
    blocks = {b['id']: b for b in document['blocks']}
    operations = {o['id']: o for o in document['operations']}
    knowledge = {k['id']: k for k in document['knowledge']}
    if operation_id not in operations:
        raise ValueError('requested operation is unknown')
    definition = _definition_digest(document)
    knowledge_keys = {}
    def structural(item):
        return {key: deepcopy(value) for key, value in item.items()
                if key not in ('resolution', 'scope', 'evidence')}
    def knowledge_key(ref):
        if ref not in knowledge_keys:
            core = structural(knowledge[ref])
            core['needs'] = [knowledge_key(need) for need in core['needs']]
            knowledge_keys[ref] = 'opgoal.knowledge.' + ref + '.' + digest(core)[:16]
        return knowledge_keys[ref]
    block_keys = {}
    for ref, block in blocks.items():
        core = structural(block)
        core['needs'] = [knowledge_key(need) for need in core['needs']]
        block_keys[ref] = 'opgoal.analysis.' + ref + '.' + digest(core)[:16]
    def fact(kind, ref):
        return knowledge_key(ref) if kind == 'knowledge' else block_keys[ref]
    if not isinstance(available, (list, tuple, set, frozenset)) or len(available) > 4096:
        raise ValueError('available must be bounded fact keys')
    observed = {_text(key, 128) for key in available}
    facts, tasks, reached_ops, reached_blocks, reached_knowledge = {}, {}, set(), set(), set()
    for block in blocks.values():
        if block['resolution'] == 'resolved':
            key = fact('analysis', block['id'])
            facts[key] = {'key': key, 'value': {'kind': 'block-result', 'ref': block['id'],
                'resolution': 'resolved', 'scope': block['scope']},
                'evidence': {'definition': definition, 'references': block['evidence']}}
    for finding in document['findings']:
        kind = 'knowledge' if finding['kind'] == 'knowledge' else 'analysis'
        key = fact(kind, finding['ref'])
        facts[key] = {'key': key, 'value': deepcopy(finding),
                      'evidence': {'definition': definition, 'references': finding['evidence']}}
    observed.update(facts)
    def task(kind, ref, needs, question, source):
        key = fact('knowledge' if kind == 'resolve-knowledge' else 'analysis', ref)
        ident = 'goal.' + hashlib.sha256((kind + ':' + key).encode()).hexdigest()[:24]
        requires = [fact('knowledge', need) for need in needs]
        tasks[ident] = {'id': ident, 'kind': kind, 'ref': ref, 'question': question,
            'requires': requires, 'produces': [key], 'scope': source['scope'],
            'evidence': deepcopy(source['evidence']),
            'missing': [key for key in requires if key not in observed]}
    def visit_knowledge(ref):
        if ref in reached_knowledge:
            return
        reached_knowledge.add(ref)
        if fact('knowledge', ref) in observed:
            return
        item = knowledge[ref]
        for dependency in item['needs']:
            visit_knowledge(dependency)
        task('resolve-knowledge', ref, item['needs'], item['question'], item)
    def visit_block(ref):
        if ref in reached_blocks:
            return
        reached_blocks.add(ref)
        if fact('analysis', ref) in observed:
            return
        block = blocks[ref]
        for need in block['needs']:
            visit_knowledge(need)
        task('recover-block', ref, block['needs'], 'Recover the declared role/ports of known UDL block ' + block['udl_ref'], block)
    def visit_operation(ref):
        if ref in reached_ops:
            return
        reached_ops.add(ref)
        for step in operations[ref]['steps']:
            (visit_block if step['kind'] == 'block' else visit_operation)(step['ref'])
    visit_operation(operation_id)
    descendants = {}
    def descendant_blocks(ref):
        if ref in descendants:
            return descendants[ref]
        found = set()
        for step in operations[ref]['steps']:
            found.update({step['ref']} if step['kind'] == 'block' else descendant_blocks(step['ref']))
        descendants[ref] = found
        return found
    coverage = []
    for ref in sorted(reached_ops):
        children = descendant_blocks(ref)
        result_refs = sorted(b for b in children if fact('analysis', b) in observed)
        coverage.append({'operation': ref, 'known_blocks': sorted(children),
            'definition_resolved': sorted(b for b in children if blocks[b]['resolution'] == 'resolved'),
            'results_available': result_refs, 'missing_results': sorted(children - set(result_refs)),
            'all_component_results_available': len(result_refs) == len(children),
            'scope': operations[ref]['scope'], 'claim': 'Result availability is not semantic proof or execution qualification.'})
    relevant_facts = {fact('analysis', b) for b in reached_blocks} | {fact('knowledge', k) for k in reached_knowledge}
    ready = [deepcopy(t) for t in tasks.values() if not t['missing']]
    blocked = [deepcopy(t) for t in tasks.values() if t['missing']]
    return {'format': PLAN_FORMAT, 'goal': operation_id, 'definition_sha256': definition,
        'ready': sorted(ready, key=lambda t: t['id']), 'blocked': sorted(blocked, key=lambda t: t['id']),
        'facts': [facts[k] for k in sorted(relevant_facts & facts.keys())],
        'available_fact_keys': sorted(relevant_facts & observed), 'coverage': coverage,
        'known_blocks': [deepcopy(blocks[b]) for b in sorted(reached_blocks)],
        'unselected_blocks': sorted(blocks.keys() - reached_blocks),
        'operations': [deepcopy(operations[o]) for o in sorted(reached_ops)],
        'correspondences': [deepcopy(c) for c in document['correspondences']
                            if c['logical']['operation'] in reached_ops],
        'scope': 'Authored recovery-goal companion; no automatic execution, new UIL opcode or semantic proof.'}


def queue_frontier(plan):
    """Return add/publish-ready shapes for the single-owner dependency queue."""
    if type(plan) is not dict or plan.get('format') != PLAN_FORMAT:
        raise ValueError('expected an operation-goal plan')
    tasks = [{key: deepcopy(task[key]) for key in ('id', 'requires', 'produces')}
             | {'operation': None, 'priority': 0} for task in plan['ready'] + plan['blocked']]
    return {'facts': deepcopy(plan['facts']), 'tasks': tasks,
            'ready': [task['id'] for task in plan['ready']],
            'blocked': [{'id': task['id'], 'missing': task['missing']} for task in plan['blocked']],
            'definition_sha256': plan['definition_sha256'], 'execution': 'none; caller selects or delegates recovery work'}
