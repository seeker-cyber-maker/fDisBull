#!/usr/bin/env python3
"""Bounded real-BLA region campaign; no CJS target execution or target copies.

The target repository remains external. This runner qualifies two narrow
claims: source-matched u32 predicate reductions and identity of stateless Wasm
function regions. These are distinct from PE trace equivalence and full-app
equivalence. Reports contain hashes, source offsets and compact receipts.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys


LIMIT = 16 * 1024 * 1024
SUPPORTED_COMMIT = '0269b5b0f4f2941e53070c9b3ffbda88d5348437'
SUPPORTED_L1 = 'b5afb315e193bb6f3f98ef0c4be0e86f4b36ceb32c1b6f14d76d3ffbea7f1892'
PATHS = {
    'js': 'challenge/archive/v6-tiered-protect/artifacts/L1.cjs',
    'clean_js': 'challenge/archive/v6-tiered-protect/clean/target.template.cjs',
    'clean_wasm': 'challenge/v6/src/core.wasm',
    'hardened_wasm': 'challenge/v6/hardened/core.wasm.gz',
    'license': 'LICENSE',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def read(path, limit=2 * 1024 * 1024):
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f'Missing or oversized selected artifact: {path.name}')
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError('Selected artifact grew during read')
    return raw


def uleb(raw, at):
    value = 0
    for index in range(5):
        if at >= len(raw):
            raise ValueError('Truncated Wasm integer')
        byte = raw[at]
        at += 1
        value |= (byte & 127) << (index * 7)
        if byte < 128:
            if value >= 1 << 32:
                raise ValueError('Oversized Wasm u32')
            return value, at
    raise ValueError('Oversized Wasm integer')


def sleb(raw, at):
    value = shift = 0
    for _ in range(5):
        if at >= len(raw):
            raise ValueError('Truncated Wasm signed integer')
        byte = raw[at]
        at += 1
        value |= (byte & 127) << shift
        shift += 7
        if byte < 128:
            if byte & 64:
                value -= 1 << shift
            if not -(1 << 31) <= value < 1 << 31:
                raise ValueError('Wasm constant exceeds i32')
            return value & 0xffffffff, at
    raise ValueError('Oversized Wasm signed integer')


def wasm(raw):
    if raw[:8] != b'\0asm\1\0\0\0' or len(raw) > LIMIT:
        raise ValueError('Expected bounded Wasm v1 module')
    at = 8
    sections, customs = {}, []
    last = 0
    while at < len(raw):
        kind = raw[at]
        size, start = uleb(raw, at + 1)
        end = start + size
        if end > len(raw):
            raise ValueError('Wasm section exceeds module')
        payload = raw[start:end]
        if kind == 0:
            customs.append({'bytes': size, 'sha256': digest(payload)})
        else:
            if kind <= last or kind not in (1, 3, 7, 10):
                raise ValueError('Unexpected import/state/start/other Wasm section')
            sections[kind] = payload
            last = kind
        at = end
    if set(sections) != {1, 3, 7, 10}:
        raise ValueError('Missing required pure-function sections')
    # This campaign admits exactly the public BLA mix/seal signatures.
    if sections[1] != bytes.fromhex('0260027f7f017f60017f017f') or sections[3] != b'\x02\x00\x01':
        raise ValueError('Function signatures or indexing differ from the admitted pair')
    payload = sections[7]
    count, cursor = uleb(payload, 0)
    if count > 1024:
        raise ValueError('Too many export aliases')
    exports, selected = set(), {}
    for _ in range(count):
        length, cursor = uleb(payload, cursor)
        end = cursor + length
        if length > 1024 * 1024 or end >= len(payload):
            raise ValueError('Malformed export name')
        name = payload[cursor:end]
        name.decode('utf8')
        if name in exports:
            raise ValueError('Duplicate Wasm export')
        exports.add(name)
        kind = payload[end]
        index, cursor = uleb(payload, end + 1)
        if kind != 0 or index not in (0, 1):
            raise ValueError('Export refers outside the admitted pure functions')
        if name in (b'mix', b'seal'):
            selected[name.decode()] = index
    if cursor != len(payload) or selected != {'mix': 0, 'seal': 1}:
        raise ValueError('Selected export identity differs')
    payload = sections[10]
    count_code, cursor = uleb(payload, 0)
    if count_code != 2:
        raise ValueError('Unexpected function count')
    functions = []
    for index in range(count_code):
        length, cursor = uleb(payload, cursor)
        end = cursor + length
        body = payload[cursor:end]
        if len(body) != length or length > 256 or not body or body[0] != 0:
            raise ValueError('Unexpected locals or function extent')
        operations, position = [], 1
        while position < len(body):
            op = body[position]
            position += 1
            if op == 0x20:
                argument, position = uleb(body, position)
                if argument >= (2 if index == 0 else 1):
                    raise ValueError('Unknown local argument')
                operations.append(('arg', argument))
            elif op == 0x41:
                constant, position = sleb(body, position)
                operations.append(('const', constant))
            elif op in (0x6a, 0x6c, 0x73, 0x77):
                operations.append(({0x6a: 'add', 0x6c: 'mul', 0x73: 'xor', 0x77: 'rotl'}[op],))
            elif op == 0x10:
                callee, position = uleb(body, position)
                if index != 1 or callee != 0:
                    raise ValueError('Unexpected call or recursive dependency')
                operations.append(('call_mix',))
            elif op == 0x0b and position == len(body):
                operations.append(('end',))
            else:
                raise ValueError('Instruction outside pure i32 function profile')
        if not operations or operations[-1] != ('end',):
            raise ValueError('Missing function terminator')
        functions.append({'bytes': length, 'sha256': digest(body), 'operations': operations})
        cursor = end
    if cursor != len(payload):
        raise ValueError('Trailing function data')
    return {'sections': sections, 'customs': customs, 'exports': selected,
            'export_count': count, 'functions': functions}


def interpret(functions, index, args):
    stack = []
    for op in functions[index]['operations']:
        if op[0] == 'arg':
            stack.append(args[op[1]] & 0xffffffff)
        elif op[0] == 'const':
            stack.append(op[1])
        elif op[0] == 'end':
            if len(stack) != 1:
                raise ValueError('Wasm stack/type contract does not return one i32')
            return stack[0]
        else:
            if len(stack) < 2:
                raise ValueError('Wasm expression stack underflow')
            right, left = stack.pop(), stack.pop()
            if op[0] == 'call_mix':
                value = interpret(functions, 0, (left, right))
            elif op[0] == 'add':
                value = left + right
            elif op[0] == 'mul':
                value = left * right
            elif op[0] == 'xor':
                value = left ^ right
            elif op[0] == 'rotl':
                distance = right & 31
                value = (left << distance) | (left >> ((32 - distance) & 31))
            else:
                raise ValueError('Unknown reduced operation')
            stack.append(value & 0xffffffff)
    raise ValueError('Function did not terminate')


def predicates(source):
    import z3 as z
    seed = re.search(r'const (runtimeSeed\w+) = ([^\n]+);', source)
    invariant_shape = re.compile(r'.+ & 0x7fffc \| \(typeof ([_$a-zA-Z]\w*) === "function" && '
                                 r'\1\(0\) === 4129934667 \? 1 : 0\)')
    if not seed or not invariant_shape.fullmatch(seed[2]):
        raise ValueError('Seed construction differs from reviewed invariant')
    name = re.escape(seed[1])
    square = re.compile(r'\(Math\.imul\(' + name + r' \^ (\d+), ' + name + r' \^ (\d+)\) & 7\) === 1')
    selected = []
    for constant in (24, 28):
        match = next((m for m in square.finditer(source) if int(m[1]) == int(m[2]) == constant), None)
        if match is None:
            raise ValueError('Selected original BLA square guard was not found exactly')
        selected.append(('square', constant, match))
    consecutive = re.compile(r'\(Math\.imul\(' + name + r' \| 21, \(' + name + r' \| 21\) \+ 1\) & 1\) === 0')
    match = consecutive.search(source)
    if match is None:
        raise ValueError('Selected original BLA consecutive-product guard was not found exactly')
    selected.append(('consecutive', 21, match))
    s = z.BitVec('seed', 32)
    rows, runtime = [], []
    rng = random.Random(20261112)
    seeds = [0, 1, 4, 5, 0x7fffc, 0x7fffd, 0x80000000, 0xffffffff]
    seeds += [rng.getrandbits(32) for _ in range(128)]
    seeds += [(rng.getrandbits(17) << 2) | 1 for _ in range(128)]
    for kind, constant, match in selected:
        solver = z.Solver()
        solver.set(timeout=1000)
        if kind == 'square':
            expression = (((s ^ constant) * (s ^ constant)) & 7) == 1
            solver.add((s & 3) == 1)
            expected = [(((v ^ constant) * (v ^ constant)) & 7) == 1 for v in seeds]
        else:
            value = s | constant
            expression = ((value * (value + 1)) & 1) == 0
            expected = [(((v | constant) * ((v | constant) + 1)) & 1) == 0 for v in seeds]
        solver.add(z.Not(expression))
        proof = str(solver.check())
        if proof != 'unsat':
            raise ValueError('BLA predicate counterquery did not prove unsatisfiable')
        region = source[match.start():match.end()]
        rows.append({'operation': kind, 'constant': constant, 'source_offsets': [match.start(), match.end()],
                     'source_region_sha256': digest(region.encode()), 'reduced_value': True,
                     'assumptions': ['Standard intrinsic Math.imul and u32 seed input'] +
                                    (['seed & 3 == 1; intact corpus digest branch'] if kind == 'square' else []),
                     'counterquery': proof, 'solver': {'name': 'z3', 'version': z.get_version_string(),
                                                        'timeout_ms': 1000},
                     'scope': 'Pure matched JavaScript u32 predicate only; no surrounding calls or mutable state'})
        runtime.append({'expression': region.replace(seed[1], 's'), 'seeds': seeds, 'expected': expected})
    return rows, runtime


NODE = r'''
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const zlib = require('node:zlib');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const hash = x => crypto.createHash('sha256').update(x).digest('hex');
const predicates = input.predicates.map(item => {
  const script = new vm.Script('(' + item.expression + ')');
  const context = vm.createContext({s: 0, Math: Object.freeze({imul: Math.imul})});
  const outputs = item.seeds.map(s => {context.s = s; return script.runInContext(context, {timeout: 25});});
  assert.deepEqual(outputs, item.expected);
  const outside = item.seeds.findIndex((s, i) => (s & 3) !== 1 && outputs[i] !== true);
  return {cases: outputs.length, outputs_sha256: hash(JSON.stringify(outputs)),
          invariant_cases: item.seeds.filter(s => (s & 3) === 1).length,
          outside_invariant_counterexample: outside < 0 ? null : {seed: item.seeds[outside], result: outputs[outside]}};
});
const modules = input.wasm.map(item => {
  const original = fs.readFileSync(item.path);
  assert.equal(hash(original), item.file_sha256);
  const bytes = item.gzip ? zlib.gunzipSync(original, {maxOutputLength: 16 * 1024 * 1024}) : original;
  assert.equal(hash(bytes), item.module_sha256);
  assert.equal(WebAssembly.validate(bytes), true);
  const module = new WebAssembly.Module(bytes);
  assert.equal(WebAssembly.Module.imports(module).length, 0);
  return new WebAssembly.Instance(module, {}).exports;
});
const outputs = input.vectors.map(([a,b], index) => {
  const oldMix = modules[0].mix(a,b) >>> 0, newMix = modules[1].mix(a,b) >>> 0;
  const oldSeal = modules[0].seal(a) >>> 0, newSeal = modules[1].seal(a) >>> 0;
  assert.equal(oldMix, newMix); assert.equal(oldSeal, newSeal);
  assert.equal(oldMix, input.expected[index][0]); assert.equal(oldSeal, input.expected[index][1]);
  return [oldMix, oldSeal];
});
console.log(JSON.stringify({node: process.version, predicates,
  wasm: {mix_cases: outputs.length, seal_cases: outputs.length,
    outputs_sha256: hash(JSON.stringify(outputs)), vectors_sha256: hash(JSON.stringify(input.vectors)),
    actual_modules_validated: true, clean_hardened_and_independent_interpreter_agree: true}}));
'''


def campaign(root):
    root = root.resolve(strict=True)
    files = {name: read(root / relative) for name, relative in PATHS.items()}
    commit = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True,
                            capture_output=True, text=True, timeout=10).stdout.strip()
    if commit != SUPPORTED_COMMIT or digest(files['js']) != SUPPORTED_L1:
        raise ValueError('BLA revision or source differs from this reviewed campaign')
    remote = subprocess.run(['git', '-C', str(root), 'config', '--get', 'remote.origin.url'],
                            check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if remote.rstrip('/').removesuffix('.git') != 'https://github.com/qybaihe/bla':
        raise ValueError('Selected checkout does not identify the expected BLA upstream')
    selected_status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain', '--', *PATHS.values()],
                                     check=True, capture_output=True, text=True, timeout=10).stdout
    if selected_status:
        raise ValueError('Selected BLA artifacts differ from the owning checkout')
    if b'MIT License' not in files['license']:
        raise ValueError('Expected provenance/license notice missing')
    source = files['js'].decode('utf8')
    predicate_rows, runtime_predicates = predicates(source)
    with gzip.GzipFile(fileobj=io.BytesIO(files['hardened_wasm'])) as stream:
        hardened = stream.read(LIMIT + 1)
    if len(hardened) > LIMIT:
        raise ValueError('Decoded hardened module exceeds bound')
    modules = [files['clean_wasm'], hardened]
    parsed = [wasm(raw) for raw in modules]
    for kind in (1, 3, 10):
        if parsed[0]['sections'][kind] != parsed[1]['sections'][kind]:
            raise ValueError('BLA type/function/code regions differ; identity claim refused')
    rng = random.Random(73017)
    vectors = [[a,b] for a in (0, 1, 0xffffffff, 0x80000000) for b in (0, 1, 0xffffffff, 0x80000000)]
    vectors += [[rng.getrandbits(32), rng.getrandbits(32)] for _ in range(128)]
    expected = [[interpret(parsed[0]['functions'], 0, pair),
                 interpret(parsed[0]['functions'], 1, pair[:1])] for pair in vectors]
    runtime_input = {'predicates': runtime_predicates, 'vectors': vectors, 'expected': expected,
                     'wasm': [{'path': str(root / PATHS[key]), 'file_sha256': digest(files[key]),
                               'module_sha256': digest(raw), 'gzip': key == 'hardened_wasm'}
                              for key, raw in zip(('clean_wasm', 'hardened_wasm'), modules, strict=True)]}
    node = shutil.which('node')
    if node is None:
        raise ValueError('Node is required for independent runtime checks')
    result = subprocess.run([node, '--max-old-space-size=128', '-e', NODE], input=encoded(runtime_input),
                            capture_output=True, timeout=30,
                            env={key: value for key, value in os.environ.items()
                                 if key not in ('NODE_OPTIONS', 'NODE_PATH')})
    if result.returncode:
        raise ValueError('Bounded Node validation failed: ' + result.stderr.decode(errors='replace')[:1000])
    runtime = json.loads(result.stdout)
    report = {'format': 'fdisbull-bla-region-campaign-1', 'status': 'verified_bounded_regions',
              'runner_sha256': digest(Path(__file__).read_bytes()),
              'source': {'repository': remote, 'commit': commit,
                         'selected_sources_match_checkout': True,
                         'files': {key: {'path': PATHS[key], 'bytes': len(raw), 'sha256': digest(raw)}
                                   for key, raw in files.items()}},
              'predicate_regions': [row | {'runtime': evidence} for row, evidence in
                                    zip(predicate_rows, runtime['predicates'], strict=True)],
              'wasm_regions': {'claim': 'Exact stateless selected-function code-region identity',
                  'selected_exports': parsed[0]['exports'],
                  'imports_memory_tables_globals_start_elements_data': 'Absent in both admitted modules',
                  'module_sha256': {'clean': digest(modules[0]), 'hardened': digest(modules[1])},
                  'module_bytes': {'clean': len(modules[0]), 'hardened': len(modules[1])},
                  'export_count': {'clean': parsed[0]['export_count'], 'hardened': parsed[1]['export_count']},
                  'equal_sections': {str(kind): {'bytes': len(parsed[0]['sections'][kind]),
                                                'sha256': digest(parsed[0]['sections'][kind])} for kind in (1,3,10)},
                  'functions': [{'index': index, 'bytes': item['bytes'], 'sha256': item['sha256']}
                                for index, item in enumerate(parsed[0]['functions'])],
                  'runtime': runtime['wasm']},
              'runtime': {'node': runtime['node'], 'max_old_space_mib': 128, 'timeout_seconds': 30},
              'limitations': ['PE trace regional equivalence does not admit these original JS/Wasm artifacts.',
                  'Predicate proofs cover exactly matched pure u32 regions, conditional on stated seed invariant.',
                  'The corpus digest condition and surrounding JS calls/shadow-heap effects are not proved.',
                  'Wasm selected function code is identical; this is not normalization of different instruction bodies.',
                  'Wasm export/custom surfaces differ; whole-module and complete challenge equivalence are not claimed.',
                  'Finite runtime agreement is not a universal runtime proof.',
                  'No full CJS challenge execution, authorization-key recovery or FLAG output was performed.']}
    report['report_sha256'] = digest(encoded(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Existing external BLA checkout')
    parser.add_argument('--output', type=Path, required=True, help='New sanitized JSON receipt outside checkout')
    args = parser.parse_args()
    report = campaign(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'output': str(args.output),
                      'report_sha256': report['report_sha256'], 'predicate_regions': len(report['predicate_regions']),
                      'wasm_runtime_cases': report['wasm_regions']['runtime']['mix_cases']}))


if __name__ == '__main__':
    try:
        main()
    except (ImportError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'BLA campaign failed: {error}', file=sys.stderr)
        raise SystemExit(2)
