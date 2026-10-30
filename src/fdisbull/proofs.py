"""Bounded equivalence of explicitly supplied finite-width models.

This module does not parse C, lift instructions, or establish model fidelity.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid


PROOF_DDL = '''
CREATE TABLE IF NOT EXISTS bounded_proofs(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 version_sha256 TEXT NOT NULL, source_sha256 TEXT NOT NULL, created TEXT NOT NULL,
 author TEXT NOT NULL, evidence TEXT NOT NULL, spec TEXT NOT NULL, result TEXT NOT NULL,
 sha256 TEXT NOT NULL);
'''


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError('Expected finite JSON data') from error


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _load_z3():
    try:
        import z3
    except ImportError:
        return None
    return z3


def _validate(spec):
    text = _json(spec)
    if len(text.encode()) > 65536:
        raise ValueError('Proof specification exceeds 64 KiB')
    required = {'format', 'scope', 'variables', 'assumptions', 'left', 'right'}
    if not isinstance(spec, dict) or not required <= set(spec) or set(spec) - required - {'provenance'}:
        raise ValueError('Proof requires format, scope, variables, assumptions, left and right')
    if spec['format'] != 'fdisbull-proof-1' or not isinstance(spec['scope'], str) or not 1 <= len(spec['scope']) <= 1024:
        raise ValueError('Invalid proof format or model scope')
    if 'provenance' in spec:
        source = spec['provenance']
        if (not isinstance(source, dict) or set(source) != {'kind', 'sha256', 'node'} or
                not isinstance(source['kind'], str) or not 1 <= len(source['kind']) <= 128 or
                not isinstance(source['node'], str) or not 1 <= len(source['node']) <= 512 or
                not isinstance(source['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', source['sha256'])):
            raise ValueError('provenance requires kind, lowercase SHA-256 and node')
    variables = spec['variables']
    if not isinstance(variables, dict) or len(variables) > 64:
        raise ValueError('variables must be an object with at most 64 entries')
    for name, width in variables.items():
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}', name) or type(width) is not int or not 1 <= width <= 256:
            raise ValueError('Invalid variable name or bit width')
    if not isinstance(spec['assumptions'], list) or len(spec['assumptions']) > 64:
        raise ValueError('assumptions must be a list with at most 64 entries')
    nodes = 0

    def visit(node, depth=0):
        nonlocal nodes
        nodes += 1
        if nodes > 1024 or depth > 32 or not isinstance(node, dict):
            raise ValueError('Invalid or excessive expression')
        if set(node) == {'var'}:
            name = node['var']
            if not isinstance(name, str) or name not in variables:
                raise ValueError('Unknown variable')
            return ('bv', variables[name])
        if set(node) == {'const', 'width'}:
            value, width = node['const'], node['width']
            if type(width) is not int or not 1 <= width <= 256 or type(value) is not int or not 0 <= value < 2**width:
                raise ValueError('Invalid bit-vector constant')
            return ('bv', width)
        if set(node) == {'bool'} and type(node['bool']) is bool:
            return ('bool', None)
        if set(node) != {'op', 'args'} or not isinstance(node['op'], str) or not isinstance(node['args'], list):
            raise ValueError('Invalid expression node')
        op, args = node['op'], node['args']
        arities = {'add':2, 'sub':2, 'mul':2, 'band':2, 'bor':2, 'bxor':2,
                   'bnot':1, 'eq':2, 'ult':2, 'ule':2, 'slt':2, 'sle':2,
                   'and':2, 'or':2, 'not':1, 'ite':3}
        if op not in arities or len(args) != arities[op]:
            raise ValueError('Unsupported operation or arity: ' + op)
        types = [visit(arg, depth + 1) for arg in args]
        if op in ('and', 'or', 'not'):
            if any(t[0] != 'bool' for t in types): raise ValueError('Boolean operands required')
            return ('bool', None)
        if op == 'ite':
            if types[0][0] != 'bool' or types[1] != types[2]: raise ValueError('Invalid conditional types')
            return types[1]
        if op == 'eq':
            if types[0] != types[1]: raise ValueError('Equality operands must have matching types')
            return ('bool', None)
        if any(t[0] != 'bv' for t in types) or any(t != types[0] for t in types):
            raise ValueError('Matching bit-vector operands required')
        return ('bool', None) if op in ('ult', 'ule', 'slt', 'sle') else types[0]

    for assumption in spec['assumptions']:
        if visit(assumption)[0] != 'bool': raise ValueError('Assumptions must be Boolean')
    if visit(spec['left']) != visit(spec['right']): raise ValueError('Compared expressions must have matching types')
    return text


def _model(variables, left, right, scope, assumptions, provenance=None):
    if assumptions is None: assumptions = []
    if not isinstance(assumptions, list): raise ValueError('assumptions must be a list')
    spec = {'format':'fdisbull-proof-1', 'scope':scope, 'variables':variables,
            'assumptions':list(assumptions), 'left':left, 'right':right}
    if provenance is not None: spec['provenance'] = provenance
    _validate(spec)
    return spec


def arithmetic_model(variables, left, right, *, scope, assumptions=None, semantics='bitvector_modular'):
    """Build an explicitly modular arithmetic comparison, not a C parser."""
    if semantics != 'bitvector_modular':
        raise ValueError('Unsupported arithmetic semantics; C undefined behavior is not modeled automatically')
    return _model(variables, left, right, scope, assumptions)


def readiness_model(variables, ready, requirement, *, scope, assumptions=None):
    """Check whether a satisfiable readiness condition implies a requirement."""
    if assumptions is not None and not isinstance(assumptions, list): raise ValueError('assumptions must be a list')
    return _model(variables, requirement, {'bool':True}, scope, (assumptions or []) + [ready])


def guarded_transition_model(variables, guard, left, right, *, scope, source, assumptions=None):
    """Compare one guarded transition under a caller-asserted source identity."""
    if assumptions is not None and not isinstance(assumptions, list): raise ValueError('assumptions must be a list')
    if source is None: raise ValueError('A source provenance claim is required')
    return _model(variables, left, right, scope, (assumptions or []) + [guard], source)


def check_equivalence(spec, timeout_ms=1000):
    """Compare two models under satisfiable assumptions; never infer source semantics."""
    encoded = _validate(spec)
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 60000:
        raise ValueError('timeout_ms must be an integer in 1..60000')
    result = {'format':'fdisbull-proof-result-1', 'spec_sha256':_digest(encoded),
              'scope':spec['scope'], 'timeout_ms':timeout_ms,
              'semantics':'explicit fixed-width modular bit vectors; no implied C/C++ definedness or model fidelity'}
    if 'provenance' in spec:
        result['provenance'] = spec['provenance']
        result['provenance_status'] = 'caller_asserted_not_independently_verified'
    z3 = _load_z3()
    if z3 is None:
        return {**result, 'status':'unavailable', 'reason':'z3-solver is not installed', 'solver':None}
    result['solver'] = 'Z3 ' + z3.get_version_string()
    variables = {name:z3.BitVec(name, width) for name, width in spec['variables'].items()}

    def build(node):
        if 'var' in node: return variables[node['var']]
        if 'const' in node: return z3.BitVecVal(node['const'], node['width'])
        if 'bool' in node: return z3.BoolVal(node['bool'])
        op = node['op']; a = [build(item) for item in node['args']]
        if op == 'add': return a[0] + a[1]
        if op == 'sub': return a[0] - a[1]
        if op == 'mul': return a[0] * a[1]
        if op == 'band': return a[0] & a[1]
        if op == 'bor': return a[0] | a[1]
        if op == 'bxor': return a[0] ^ a[1]
        if op == 'bnot': return ~a[0]
        if op == 'eq': return a[0] == a[1]
        if op == 'ult': return z3.ULT(a[0], a[1])
        if op == 'ule': return z3.ULE(a[0], a[1])
        if op == 'slt': return a[0] < a[1]
        if op == 'sle': return a[0] <= a[1]
        if op == 'and': return z3.And(*a)
        if op == 'or': return z3.Or(*a)
        if op == 'not': return z3.Not(a[0])
        return z3.If(*a)

    deadline = time.monotonic() + timeout_ms / 1000
    solver = z3.Solver()
    solver.add(*[build(item) for item in spec['assumptions']])
    def run():
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0: return None
        solver.set(timeout=remaining)
        return solver.check()
    feasible = run()
    if feasible is None: return {**result, 'status':'unknown', 'reason':'time budget expired before assumption check'}
    if feasible == z3.unknown: return {**result, 'status':'unknown', 'reason':solver.reason_unknown()}
    if feasible == z3.unsat: return {**result, 'status':'vacuous', 'reason':'assumptions are unsatisfiable'}
    solver.add(build(spec['left']) != build(spec['right']))
    verdict = run()
    if verdict is None: return {**result, 'status':'unknown', 'reason':'time budget expired before equivalence check'}
    if verdict == z3.unknown: return {**result, 'status':'unknown', 'reason':solver.reason_unknown()}
    if verdict == z3.unsat: return {**result, 'status':'equivalent_under_assumptions'}
    model = solver.model()
    values = {name:{'width':spec['variables'][name], 'unsigned':model.eval(value, model_completion=True).as_long()}
              for name, value in variables.items()}
    return {**result, 'status':'counterexample', 'inputs':values}


class ProofProjectMixin:
    def proof_check(self, spec, version=None, timeout_ms=1000, author='agent', evidence=None):
        if not isinstance(author, str) or not 1 <= len(author) <= 256:
            raise ValueError('author must be a nonempty string of at most 256 characters')
        if evidence is None: evidence = []
        if not isinstance(evidence, list) or len(_json(evidence).encode()) > 65536:
            raise ValueError('evidence must be a JSON list within 64 KiB')
        result = check_equivalence(spec, timeout_ms=timeout_ms)
        from .project import now
        identifier = uuid.uuid4().hex
        with self.transaction(True):
            v = self.version(version)
            record = {'id':identifier, 'version':v['id'], 'version_sha256':v['sha256'],
                      'source_sha256':self.source_binding_sha256(v['id']), 'created':now(), 'author':author,
                      'evidence':evidence, 'spec':spec, 'result':result}
            digest = _digest(_json(record))
            self.db.execute('INSERT INTO bounded_proofs VALUES (?,?,?,?,?,?,?,?,?,?)',
                            (identifier, v['id'], v['sha256'], self.source_binding_sha256(v['id']), record['created'],
                             author, _json(evidence), _json(spec), _json(result), digest))
        return {**record, 'sha256':digest}

    def proof_info(self, proof, version=None):
        v = self.version(version)
        row = self.db.execute('SELECT * FROM bounded_proofs WHERE id=? AND version=?', (proof, v['id'])).fetchone()
        if row is None: raise ValueError('Unknown proof for selected version')
        record = dict(row); digest = record.pop('sha256')
        for field in ('evidence', 'spec', 'result'):
            try: record[field] = json.loads(record[field])
            except (ValueError, TypeError) as error: raise ValueError('Corrupt proof record') from error
        if _digest(_json(record)) != digest or record['version_sha256'] != v['sha256'] or record['source_sha256'] != self.source_binding_sha256(v['id']):
            raise ValueError('Proof record or version hash mismatch')
        return {**record, 'sha256':digest}

    def proofs(self, version=None):
        v = self.version(version)['id']
        rows = self.db.execute('SELECT id FROM bounded_proofs WHERE version=? ORDER BY rowid', (v,)).fetchall()
        return {'version':v, 'proofs':[self.proof_info(row['id'], version=v) for row in rows]}
