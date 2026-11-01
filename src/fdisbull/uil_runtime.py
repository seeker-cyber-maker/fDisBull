"""Reference execution of indexed UIL and explicit typed call shims.

All mutable values are owned copies. Effects are plans; this evaluator never
opens a resource, sends input, plays audio or retries a failed invocation.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from .common_uil import (digest, validate_program, validate_presentation,
                         validate_orchestration, validate_realization, presentation_value,
                         default_value, typed, wrap, RESOURCE_KINDS)


class _Return(Exception):
    pass


TRACE_LIMITS = {'calls':1024,'events':256,'cells':65536,'event_bytes':1048576,
                'array_inline':64,'text_inline_bytes':256}


def trace_values(values):
    result = []; cells = 0
    for value in values:
        if type(value) is list and len(value) > TRACE_LIMITS['array_inline']:
            raw = json.dumps(value,separators=(',',':')).encode()
            result.append({'kind':'array-summary','length':len(value),
                           'sha256':hashlib.sha256(raw).hexdigest()}); cells += 4
        elif type(value) is str and len(value.encode()) > TRACE_LIMITS['text_inline_bytes']:
            raw = value.encode()
            result.append({'kind':'text-summary','bytes':len(raw),
                           'sha256':hashlib.sha256(raw).hexdigest()}); cells += 4
        else:
            result.append(deepcopy(value))
            cells += max(1,len(value)) if type(value) is list else 1
    return result,cells


def execute_program(program, presentation, orchestration=None, catalog=None,
                    inputs=None, max_steps=4000000):
    program = deepcopy(program); presentation = deepcopy(presentation)
    orchestration = deepcopy(orchestration); catalog = deepcopy(catalog)
    inputs = deepcopy(inputs)
    validate_program(program); validate_presentation(program, presentation)
    if type(max_steps) is not int or not 1 <= max_steps <= 4000000:
        raise ValueError('invalid aggregate execution budget')
    if orchestration is None:
        orchestration = {'format':'fdisbull-uil-orchestration-1',
                         'program_sha256':digest(program),'bindings':[],
                         'ownership':'copy-in-copy-out','max_call_depth':32}
    if catalog is None:
        catalog = {'format':'fdisbull-uil-catalog-1','groups':[],'rejected':[]}
    resolved = validate_realization(program, presentation, catalog, orchestration)
    entry = program['functions'][program['entry']]
    entry_bindings = presentation['functions'][program['entry']]
    original = [presentation_value(v,d) for v,d in zip(entry_bindings['initial'],entry['variables'])]
    if inputs is not None:
        if type(inputs) is not list or len(inputs) != len(entry['inputs']):
            raise ValueError('entry input ports are incomplete')
        for value, slot in zip(inputs, entry['inputs']):
            if not typed(value, entry['variables'][slot]):
                raise ValueError('entry input type mismatch')
            original[slot] = deepcopy(value)
    arguments = [deepcopy(original[i]) for i in entry['inputs']]
    events = []; calls = []; frames = []; steps = [0]; trace_cells = [0]; event_bytes = [0]
    identities = {'program_sha256':digest(program),'presentation_sha256':digest(presentation),
                  'orchestration_sha256':digest(orchestration),'catalog_sha256':digest(catalog)}

    def charge():
        steps[0] += 1
        if steps[0] > max_steps: raise ValueError('aggregate step budget exhausted')
        for frame in frames:
            frame['steps'] += 1
            if frame['steps'] > frame['function']['max_steps']:
                raise ValueError('function step budget exhausted')

    def evaluate(expr, fn, state, constants):
        if 'var' in expr: return deepcopy(state[expr['var']])
        if 'const' in expr: return deepcopy(constants[expr['const']])
        op = expr['op']
        if op == 'load':
            index = evaluate(expr['index'],fn,state,constants); array = state[expr['array']]
            if not 0 <= index < len(array): raise ValueError('array load out of bounds')
            return array[index]
        args = [evaluate(x,fn,state,constants) for x in expr['args']]
        typ = expr['type']
        if op == 'cast': return bool(args[0]) if typ == 'bool' else wrap(args[0], typ)
        if op == 'select': return deepcopy(args[1] if args[0] else args[2])
        if op == 'not': return not args[0]
        if op == 'parity_even': return (int(args[0]) & 255).bit_count() % 2 == 0
        a, b = args
        if op == 'eq': return a == b
        if op == 'ne': return a != b
        if op == 'lt': return a < b
        if op == 'le': return a <= b
        if op == 'gt': return a > b
        if op == 'ge': return a >= b
        if op in ('div','mod'):
            if b == 0: raise ValueError('integer division by zero')
            q = abs(a) // abs(b)
            if (a < 0) != (b < 0): q = -q
            return wrap(q if op == 'div' else a-q*b,typ)
        if op in ('shl','shr'):
            if not 0 <= b < int(typ[1:]): raise ValueError('invalid shift count')
            return wrap(a << b if op == 'shl' else a >> b,typ)
        values = {'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,
                  'and':lambda:a&b,'or':lambda:a|b,'xor':lambda:a^b}
        return wrap(values[op](),typ)

    def run_function(fn, values, constants, initial=None):
        if len(frames) >= orchestration['max_call_depth']:
            raise ValueError('orchestration call depth exhausted')
        if len(values) != len(fn['inputs']): raise ValueError('callee input arity differs')
        state = deepcopy(initial) if initial is not None else [default_value(d) for d in fn['variables']]
        for value, slot in zip(values,fn['inputs']):
            if not typed(value,fn['variables'][slot]): raise ValueError('callee input type differs')
            state[slot] = deepcopy(value)
        frame = {'function':fn,'steps':0}; frames.append(frame)
        def expr(v): return evaluate(v,fn,state,constants)
        def body(nodes):
            for node in nodes:
                op = node['op']
                if op == 'group': body(node['body']); continue
                charge()
                if op == 'set': state[node['dst']] = expr(node['value'])
                elif op == 'store':
                    index = expr(node['index']); value = expr(node['value']); array = state[node['array']]
                    if not 0 <= index < len(array): raise ValueError('array store out of bounds')
                    array[index] = value
                elif op == 'if': body(node['then'] if expr(node['condition']) else node['else'])
                elif op == 'while':
                    iterations = 0
                    while True:
                        charge()
                        if not expr(node['condition']): break
                        if iterations >= node['limit']: raise ValueError('loop bound exhausted')
                        iterations += 1; body(node['body'])
                elif op in ('call','invoke'):
                    values = [expr(x) for x in node['inputs']]
                    if op == 'call':
                        child = program['functions'][node['function']]
                        binding = presentation['functions'][node['function']]
                        cs = [presentation_value(v,d) for v,d in zip(binding['constants'],child['constants'])]
                        init = [presentation_value(v,d) for v,d in zip(binding['initial'],child['variables'])]
                        outputs, _ = run_function(child,values,cs,init)
                    else:
                        impl = resolved['resolved'][node['block']]; child = impl['function']
                        cs = [presentation_value(v,d) for v,d in zip(impl['constants'],child['constants'])]
                        logged_inputs, cells = trace_values(values)
                        if len(calls) >= TRACE_LIMITS['calls'] or trace_cells[0]+cells+1 > TRACE_LIMITS['cells']:
                            raise ValueError('invocation trace budget exhausted')
                        trace_cells[0] += cells + 1
                        call = {'block':node['block'],'semantic_id':program['imports'][node['block']]['semantic_id'],
                                'implementation':impl['id'],'language':impl['language'],
                                'inputs':logged_inputs,'outputs':[],'status':'entered'}
                        calls.append(call)
                        try:
                            outputs, _ = run_function(child,values,cs)
                            logged_outputs, cells = trace_values(outputs)
                            if trace_cells[0]+cells > TRACE_LIMITS['cells']:
                                raise ValueError('invocation trace budget exhausted')
                            trace_cells[0] += cells
                        except ValueError as exc:
                            call.update(status='refused',error=str(exc)); raise
                        call.update(status='complete',outputs=logged_outputs)
                    for slot, value in zip(node['outputs'],outputs): state[slot] = deepcopy(value)
                elif op == 'require':
                    if not expr(node['condition']): raise ValueError('required condition failed')
                elif op == 'effect':
                    values = [expr(x) for x in node['inputs']]; index = values[0]
                    if not 0 <= index < len(presentation['resources']):
                        raise ValueError('effect resource is unavailable')
                    resource = presentation['resources'][index]
                    if resource['kind'] != RESOURCE_KINDS[node['service']]:
                        raise ValueError('effect resource kind differs')
                    event = {'service':node['service'],'inputs':deepcopy(values),'resource':deepcopy(resource)}
                    size = len(json.dumps(event,ensure_ascii=False,separators=(',',':')).encode())
                    if len(events) >= TRACE_LIMITS['events'] or event_bytes[0]+size > TRACE_LIMITS['event_bytes']:
                        raise ValueError('effect event budget exhausted')
                    event_bytes[0] += size; events.append(event)
                elif op == 'return': raise _Return()
        try:
            try: body(fn['body'])
            except _Return: pass
            if any(not typed(v,d) for v,d in zip(state,fn['variables'])):
                raise ValueError('function output state violates declared types')
            return [deepcopy(state[i]) for i in fn['outputs']], state
        finally:
            frames.pop()
    try:
        constants = [presentation_value(v,d) for v,d in zip(entry_bindings['constants'],entry['constants'])]
        outputs, state = run_function(entry,arguments,constants,original)
    except ValueError as exc:
        return {'status':'refused','outputs':[],'state':original,'events':[],
                'calls':calls,'steps':steps[0],'error':str(exc),**identities}
    if events:
        return {'status':'pending_host','outputs':[],'state':original,
                'proposed_state':state,'events':events,'calls':calls,'steps':steps[0],**identities}
    return {'status':'complete','outputs':outputs,'state':state,'events':[],
            'calls':calls,'steps':steps[0],**identities}


class ExecutionTicket:
    """Owned pure result awaiting an application's context check, consumed once."""
    __slots__ = ('_result','_context','_consumed')

    def __init__(self, result, context):
        self._result = deepcopy(result); self._context = deepcopy(context); self._consumed = False


def prepare_execution(program, presentation, orchestration, catalog, **kwargs):
    owned = deepcopy(orchestration)
    if type(owned) is not dict or 'context' not in owned:
        raise ValueError('guarded execution requires explicit context epochs')
    context = deepcopy(owned['context'])
    return ExecutionTicket(execute_program(program,presentation,owned,catalog,**kwargs),context)


def finish_execution(ticket, context):
    if not isinstance(ticket,ExecutionTicket): raise ValueError('invalid execution ticket')
    if ticket._consumed: raise ValueError('execution ticket already consumed')
    ticket._consumed = True
    keys = ('session','generation','revision','selection_epoch','provider_epoch')
    if type(context) is not dict or set(context) != set(keys) or any(type(v) is not int or not 0 <= v < (1 << 53) for v in context.values()):
        raise ValueError('invalid execution context epochs')
    if context != ticket._context:
        return {'status':'refused','outputs':[],'events':[],
                'error':'stale execution context; no retry or fallback',
                'context':deepcopy(context)}
    return deepcopy(ticket._result)
