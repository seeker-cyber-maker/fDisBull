"""Bounded execution of shared-continuation interaction programs."""
from copy import deepcopy
import json

from .interaction_il import ILInvalid, _CAP, _fields, _require, _typed, _validate_v1


def validate_flow(document):
    try:
        return _validate_flow(document)
    except (TypeError, KeyError, RecursionError) as exc:
        raise ILInvalid('invalid graph') from exc


def _validate_flow(document):
    try:
        raw = json.dumps(document, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as exc:
        raise ILInvalid('document must be finite JSON') from exc
    _require(len(raw) <= 65536, 'document size budget exceeded')
    _fields(document, ('format', 'role', 'variables', 'resources', 'entry', 'continuations'), ('evidence',))
    _require(document['format'] == 'fdisbull-il-2', 'invalid format')
    continuations = document['continuations']
    _require(isinstance(continuations, dict) and bool(continuations), 'invalid continuations')
    _require(all(isinstance(k, str) and bool(k) for k in continuations), 'invalid continuation id')
    _require(isinstance(document['entry'], str) and document['entry'] in continuations, 'invalid entry')
    bodies, conditions = [], []
    for continuation in continuations.values():
        _fields(continuation, ('body', 'transfer'))
        _require(isinstance(continuation['body'], list), 'body must be a list')
        bodies.extend(continuation['body'])
        transfer = continuation['transfer']
        _require(isinstance(transfer, dict), 'invalid transfer')
        op = transfer.get('op')
        if op == 'goto':
            _fields(transfer, ('op', 'target')); targets = [transfer['target']]
        elif op == 'if':
            _fields(transfer, ('op', 'condition', 'then', 'else'))
            conditions.append(transfer['condition']); targets = [transfer['then'], transfer['else']]
        elif op == 'call':
            _fields(transfer, ('op', 'target', 'resume'))
            targets = [transfer['target']]
            if transfer['resume'] is not None: targets.append(transfer['resume'])
        elif op in ('return', 'stop'):
            _fields(transfer, ('op',)); targets = []
        else:
            raise ILInvalid('unknown transfer')
        _require(all(isinstance(t, str) and t in continuations for t in targets), 'invalid continuation target')
    synthetic = {k: deepcopy(v) for k, v in document.items() if k not in ('entry', 'continuations')}
    synthetic.update(format='fdisbull-il-1', body=bodies)
    return _validate_v1(synthetic, graph_ids=continuations, graph_conditions=conditions, graph_mode=True)


def execute_flow(document, state=None, capabilities=(), max_steps=1024, max_call_depth=8, *,
                 effect_context=None, checkpoint=None, host_result=None):
    # The effect runner owns suspension/resumption; the original scalar path
    # retains its existing result and atomic execution contract.
    def contains_effect(body):
        return any(b.get('op')=='effect' or b.get('op')=='if' and
                   (contains_effect(b.get('then',[])) or contains_effect(b.get('else',[])))
                   for b in body if isinstance(b,dict))
    if (any(x is not None for x in (effect_context,checkpoint,host_result)) or
            isinstance(document,dict) and isinstance(document.get('continuations'),dict) and
            any(isinstance(c,dict) and isinstance(c.get('body'),list) and contains_effect(c['body'])
                for c in document['continuations'].values())):
        from .interaction_effects import execute_effect_flow
        return execute_effect_flow(document,state,capabilities,max_steps,max_call_depth,
                                   effect_context,checkpoint,host_result)
    from .interaction_il import execute_il
    original = deepcopy(state)
    try:
        validate_flow(document)
        _require(type(max_steps) is int and max_steps >= 0, 'invalid step budget')
        _require(type(max_call_depth) is int and 1 <= max_call_depth <= 64, 'invalid call depth')
        _require(isinstance(capabilities, (list, tuple, set, frozenset)) and all(isinstance(x, str) for x in capabilities), 'invalid capabilities')
        _require(set(capabilities) <= set(_CAP.values()), 'unknown capability')
        declarations = document['variables']
        if state is None:
            state = {k: v['initial'] for k, v in declarations.items()}
        _require(isinstance(state, dict) and state.keys() == declarations.keys(), 'invalid state keys')
        _require(all(_typed(state[k], v['type']) for k, v in declarations.items()), 'invalid state value')
        original = deepcopy(state)
        def preflight(body):
            for b in body:
                _require(b['op'] != 'opaque', 'opaque block cannot execute')
                if b['op'] in _CAP:
                    _require(_CAP[b['op']] in capabilities, 'missing capability: ' + _CAP[b['op']])
                if b['op'] == 'if':
                    preflight(b['then']); preflight(b['else'])
        for continuation in document['continuations'].values():
            preflight(continuation['body'])
        work, events, visited, trace, stack = deepcopy(state), [], [], [], []
        def val(v): return work[v['var']] if isinstance(v, dict) else v
        def cond(c):
            op = c['op']
            if op == 'eq': return val(c['left']) == val(c['right'])
            if op == 'lt': return val(c['left']) < val(c['right'])
            if op == 'bit_test': return bool(val(c['value']) & (1 << c['bit']))
            if op == 'not': return not cond(c['condition'])
            return all(cond(x) for x in c['conditions'])
        current = document['entry']
        while True:
            _require(len(visited) < max_steps, 'step budget exceeded')
            visited.append(current)
            trace.append({'continuation': current, 'call_stack': list(stack)})
            continuation = document['continuations'][current]
            sub = {k: deepcopy(v) for k, v in document.items() if k not in ('entry', 'continuations')}
            sub.update(format='fdisbull-il-1', body=continuation['body'])
            result = execute_il(sub, work, capabilities, max_steps - len(visited))
            _require(result['status'] != 'refused', result.get('error', 'execution refused'))
            work = result['proposed_state']; events.extend(result['events']); visited.extend(result['visited'])
            transfer = continuation['transfer']; op = transfer['op']
            if op == 'goto': current = transfer['target']
            elif op == 'if': current = transfer['then'] if cond(transfer['condition']) else transfer['else']
            elif op == 'call':
                _require(len(stack) < max_call_depth, 'call depth exceeded')
                stack.append(transfer['resume']); current = transfer['target']
            elif op == 'return' and stack:
                current = stack.pop()
                _require(current is not None, 'unexpected return without continuation')
            else:
                break
        pending = any(e['op'] in _CAP for e in events)
        return {'complete': not pending, 'status': 'pending_host' if pending else 'complete',
                'state': original if pending else work, 'proposed_state': work, 'events': events,
                'visited': visited, 'evidence': deepcopy(document.get('evidence', {})),
                'control_trace': trace, 'control': {'continuation': current, 'call_stack': list(stack), 'stop': op}}
    except (ILInvalid, TypeError, KeyError, RecursionError) as exc:
        return {'complete': False, 'status': 'refused', 'error': str(exc), 'state': original, 'events': [], 'visited': []}
