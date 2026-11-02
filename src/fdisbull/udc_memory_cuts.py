"""Hash-bound suspension points in an unchanged bounded-memory UIL document.

A cut substitutes a separately selected canonical function for an exactly equal
inlined statement range.  Lowering is deliberately limited to regions with no
local inputs or continuation inputs and no enclosing loop.  It does not infer
equivalence, invent calls in the recovered document, or enlarge its word arena.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from .udc_web_memory import MAX_STEPS, digest, validate_memory_uil


CUT_FORMAT = 'fdisbull-memory-cuts-1'
LOWERING_FORMAT = 'fdisbull-memory-cut-lowering-1'
MAX_CUTS = 32
MAX_CALL_DEPTH = 16
_SATURATED = MAX_STEPS + 1


@dataclass
class _Location:
    nodes: list
    index: int
    ancestors: tuple
    tails: tuple


def _children(node):
    if node['op'] == 'if':
        return (node['then'], node['else'])
    if node['op'] == 'while':
        return (node['body'],)
    return ()


def _statements(nodes):
    for node in nodes:
        yield node
        for child in _children(node):
            yield from _statements(child)


def _without_annotations(value):
    if isinstance(value, dict):
        return {k: _without_annotations(v) for k, v in value.items()
                if k not in ('id', 'evidence')}
    if isinstance(value, list):
        return [_without_annotations(v) for v in value]
    return value


def _reads(expression):
    if not isinstance(expression, dict):
        return set()
    if 'var' in expression:
        return {expression['var']}
    result = set()
    for value in expression.values():
        result |= _reads(value)
    return result


def _flow(nodes, defined=()):
    """Return definite fallthrough definitions and reads before definition.

    A loop may execute zero times.  A returning branch contributes reads but
    does not constrain definitions on paths that can reach the next statement.
    Initial local values intentionally do not count as transferred definitions.
    """
    defined, needed, falls = set(defined), set(), True
    for node in nodes:
        if not falls:
            break
        op = node['op']
        if op == 'set':
            needed |= _reads(node['value']) - defined
            defined.add(node['var'])
        elif op == 'store':
            needed |= (_reads(node['index']) | _reads(node['value'])) - defined
        elif op == 'if':
            needed |= _reads(node['condition']) - defined
            yes, yr, yf = _flow(node['then'], defined)
            no, nr, nf = _flow(node['else'], defined)
            needed |= yr | nr
            if yf and nf:
                defined = yes & no
            elif yf:
                defined = yes
            elif nf:
                defined = no
            else:
                falls = False
        elif op == 'while':
            needed |= _reads(node['condition']) - defined
            _, body_reads, _ = _flow(node['body'], defined)
            needed |= body_reads
        else:  # The whole program validator admitted only return here.
            falls = False
    return defined, needed, falls


def _plus(a, b):
    return min(_SATURATED, a + b)


def _times(a, b):
    return min(_SATURATED, a * b)


def _maximum(*values):
    available = [value for value in values if value is not None]
    return max(available) if available else None


def _offset(value, amount):
    return None if value is None else _plus(value, amount)


def _bound_paths(nodes):
    """Bound fallthrough and returned paths, with saturating arithmetic.

    Each statement costs one.  While additionally charges every condition,
    including the final false condition or the limit-refusal condition.
    """
    fall, returned = 0, None
    for node in nodes:
        if fall is None:
            break
        op = node['op']
        if op in ('set', 'store'):
            nf, nr = 1, None
        elif op == 'return':
            nf, nr = None, 1
        elif op == 'if':
            yf, yr = _bound_paths(node['then'])
            nf_, nr_ = _bound_paths(node['else'])
            nf = _offset(_maximum(yf, nf_), 1)
            nr = _offset(_maximum(yr, nr_), 1)
        else:
            bf, br = _bound_paths(node['body'])
            limit = node['limit']
            # Zero iterations is a possible fallthrough even if every body
            # path returns.  Otherwise allow all declared iterations.
            nf = 2 if bf is None else _plus(1, _plus(limit + 1, _times(limit, bf)))
            nr = None
            if br is not None:
                previous = 0 if bf is None else _times(limit - 1, _plus(bf, 1))
                nr = _plus(2, _plus(previous, br))
        if nr is not None:
            returned = _maximum(returned, _plus(fall, nr))
        fall = None if nf is None else _plus(fall, nf)
    return fall, returned


def _graph_depth(graph):
    memo = {}

    def visit(name, active):
        if name in active:
            raise ValueError('recursive bounded-memory cuts')
        if name in memo:
            return memo[name]
        depth = 1 + max((visit(child, active | {name})
                         for child in graph[name]), default=0)
        if depth > MAX_CALL_DEPTH:
            raise ValueError('bounded-memory cut call depth exceeds 16')
        memo[name] = depth
        return depth

    for name in graph:
        visit(name, set())


def lower_memory_cuts(program, document):
    """Validate exact inlined cuts and derive independently compilable phases.

    Yield tokens are captured compiler locals, never extra arena words.  The
    caller's original budget is returned for aggregate runtime enforcement;
    phases use the global compiler cap so the two suspension adapter statements
    cannot spuriously consume that source budget.  A phase's static execution
    bound, including those adapters, must still fit that global cap.
    """
    canonical = validate_memory_uil(program)
    if canonical['role'] != 'uil':
        raise ValueError('bounded-memory cuts require UIL')
    if type(document) is not dict or set(document) != {'format', 'module_uil_sha256', 'cuts'}:
        raise ValueError('invalid bounded-memory cut document fields')
    module_digest = digest(canonical)
    if document['format'] != CUT_FORMAT or document['module_uil_sha256'] != module_digest:
        raise ValueError('bounded-memory cut module identity mismatch')
    cuts = document['cuts']
    if type(cuts) is not list or not 1 <= len(cuts) <= MAX_CUTS:
        raise ValueError('bounded-memory cuts require 1 through 32 entries')

    locations, seen_ids = {}, set()
    for function, spec in canonical['functions'].items():
        locations[function] = {}

        def discover(nodes, ancestors=(), tails=()):
            for index, node in enumerate(nodes):
                ident = node.get('id')
                if ident is not None:
                    if ident in seen_ids:
                        raise ValueError('duplicate bounded-memory cut node id')
                    seen_ids.add(ident)
                    locations[function][ident] = _Location(nodes, index, ancestors, tails)
                for child in _children(node):
                    discover(child, (*ancestors, node), (nodes[index + 1:], *tails))

        discover(spec['body'])

    grouped = {}
    occupied = {}
    graph = {name: set() for name in canonical['functions']}
    for cut in cuts:
        if type(cut) is not dict or set(cut) != {'caller', 'entry', 'callee'}:
            raise ValueError('invalid bounded-memory cut entry fields')
        caller, entry, callee = cut['caller'], cut['entry'], cut['callee']
        if (type(caller) is not str or caller not in canonical['functions'] or
                type(callee) is not str or callee not in canonical['functions'] or
                type(entry) is not str or entry not in locations[caller]):
            raise ValueError('unknown bounded-memory cut endpoint')
        location = locations[caller][entry]
        body = canonical['functions'][callee]['body']
        region = location.nodes[location.index:location.index + len(body)]
        if not body or _without_annotations(region) != _without_annotations(body):
            raise ValueError('bounded-memory cut is not the exact callee body')
        nodes = list(_statements(region))
        if any(node['op'] == 'return' for node in nodes):
            raise ValueError('return inside bounded-memory cut region')
        callee_budget = canonical['functions'][callee]['max_steps']
        caller_budget = canonical['functions'][caller]['max_steps']
        if (callee_budget < caller_budget and
                _maximum(*_bound_paths(body)) > callee_budget):
            raise ValueError('callee budget could narrow source')
        if any(node['op'] == 'while' for node in location.ancestors):
            raise ValueError('bounded-memory cut has a loop ancestor')
        identities = {id(node) for node in nodes}
        used = occupied.setdefault(caller, set())
        if used & identities:
            raise ValueError('overlapping bounded-memory cut regions')
        used |= identities
        if _flow(region)[1]:
            raise ValueError('bounded-memory cut has incoming local reads')
        continuation = list(location.nodes[location.index + len(body):])
        for tail in location.tails:
            continuation.extend(tail)
        if _flow(continuation)[1]:
            raise ValueError('bounded-memory cut continuation has incoming local reads')
        grouped.setdefault(caller, []).append((cut, len(body), continuation))
        graph[caller].add(callee)
    _graph_depth(graph)

    token = '$__fdisbull_cut_token'
    suffix = 0
    while token in canonical['variables']:
        suffix += 1
        token = '$__fdisbull_cut_token_' + str(suffix)
    if len(canonical['variables']) == 256:
        raise ValueError('bounded-memory cut token needs one free local')

    functions = {}
    for caller, entries in grouped.items():
        # Tokens are stable within this caller and follow the explicit document
        # order.  A continuation can encounter subsequent sibling/ancestor cuts.
        by_entry = {cut['entry']: (number, count)
                    for number, (cut, count, _) in enumerate(entries, 1)}

        def replace(nodes):
            result, index = [], 0
            while index < len(nodes):
                node = nodes[index]
                selected = by_entry.get(node.get('id'))
                if selected is not None:
                    number, count = selected
                    result.extend([{'op': 'set', 'var': token, 'value': number},
                                   {'op': 'return'}])
                    index += count
                    continue
                clone = deepcopy(node)
                if clone['op'] == 'if':
                    clone['then'] = replace(node['then'])
                    clone['else'] = replace(node['else'])
                elif clone['op'] == 'while':
                    clone['body'] = replace(node['body'])
                result.append(clone)
                index += 1
            return result

        def phase(nodes):
            body = replace(nodes)
            bound = _maximum(*_bound_paths(body))
            if bound > MAX_STEPS:
                raise ValueError('bounded-memory cut phase static bound exceeds 4000000')
            derived = deepcopy(canonical)
            derived['variables'][token] = {'type': 'u32', 'initial': 0}
            derived['functions'] = {caller: {'body': body, 'max_steps': MAX_STEPS}}
            derived = validate_memory_uil(derived)
            return {'program': derived, 'function': caller, 'max_steps_bound': bound}

        phases = {'entry': phase(canonical['functions'][caller]['body'])}
        yields = {}
        for number, (cut, _, continuation) in enumerate(entries, 1):
            resume = 'resume_' + str(number)
            phases[resume] = phase(continuation)
            yields[str(number)] = {'callee': cut['callee'], 'resume': resume,
                                   'adapter_steps': 2}
        functions[caller] = {'max_steps': canonical['functions'][caller]['max_steps'],
                             'token_local': token, 'phases': phases, 'yields': yields}

    return deepcopy({'format': LOWERING_FORMAT, 'module_uil_sha256': module_digest,
                     'cut_plan_sha256': digest(document), 'document': document,
                     'functions': functions})
