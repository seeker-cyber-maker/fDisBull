#!/usr/bin/env python3
"""Offline, source-only census of the complete pinned DOSBox RPC server.

Replay just agent_server.cpp in memory. Verify the upstream member, complete
patch and resulting source against their manifests before inspecting the known
method filter and every parsed.method dispatch use. No compiler, emulator,
network, package import or external source checkout is needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MEMBER = 'src/agent/server/agent_server.cpp'
PROFILES = {'stable': 'experimental/dosbox-x', 'layers': 'experimental/dosbox-x/layers'}
_TOKEN = re.compile(r'(?P<comment>//[^\n]*|/\*.*?\*/)|'
                    r'(?P<string>"(?:\\.|[^"\\])*")|(?P<char>\'(?:\\.|[^\'\\])*\')|'
                    r'(?P<name>[A-Za-z_][A-Za-z_0-9]*)|(?P<number>[0-9]+)|'
                    r'(?P<op>==|!=|\|\||&&|::|[^\s])', re.S)
_METHOD = re.compile(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _read(path, maximum):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('Census input exceeds its byte bound: ' + str(path))
    return raw


def replay_member(original, patch, member=MEMBER):
    """Apply exact unified hunks for one member, with no fuzzy matching."""
    lines = patch.decode('utf-8').splitlines(keepends=True)
    header = f'diff --git a/{member} b/{member}\n'
    starts = [i for i, line in enumerate(lines) if line == header]
    if len(starts) != 1:
        raise ValueError('Expected exactly one native server diff')
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('diff --git ')), len(lines))
    block = lines[start:end]
    base = original.decode('utf-8').splitlines(keepends=True)
    result, cursor, index, hunks = [], 0, 0, 0
    while index < len(block):
        match = re.fullmatch(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n?', block[index])
        if not match:
            if block[index].startswith('@@'):
                raise ValueError('Malformed native server hunk header')
            index += 1
            continue
        old_size, new_size = int(match[2] or 1), int(match[4] or 1)
        offset = int(match[1]) - (1 if old_size else 0)
        if not cursor <= offset <= len(base):
            raise ValueError('Native server hunk is overlapping or outside its source')
        result.extend(base[cursor:offset])
        new_offset = int(match[3]) - (1 if new_size else 0)
        if len(result) != new_offset:
            raise ValueError('Native server new hunk offset differs')
        cursor, index, removed, added = offset, index + 1, 0, 0
        while index < len(block) and not block[index].startswith('@@ '):
            line = block[index]
            if not line or line[0] not in ' +-':
                raise ValueError('Unsupported native server hunk syntax')
            if line[0] in ' -':
                if cursor >= len(base) or base[cursor] != line[1:]:
                    raise ValueError('Native server hunk context differs')
                cursor += 1
                removed += 1
            if line[0] in ' +':
                result.append(line[1:])
                added += 1
            index += 1
        if (removed, added) != (old_size, new_size):
            raise ValueError('Native server hunk counts differ')
        hunks += 1
    if not hunks:
        raise ValueError('Native server patch has no hunks')
    result.extend(base[cursor:])
    return ''.join(result).encode('utf-8')


def _tokens(source):
    return [(m.lastgroup, m.group(), m.start()) for m in _TOKEN.finditer(source)
            if m.lastgroup != 'comment']


def _brace_end(tokens, start):
    depth = 0
    for index in range(start, len(tokens)):
        kind, value, _ = tokens[index]
        if kind != 'op':
            continue
        depth += value == '{'
        depth -= value == '}'
        if depth == 0:
            return index
    raise ValueError('Unclosed native dispatch block')


def _string(token, *, prefix=False):
    if token[0] != 'string':
        raise ValueError('RPC dispatch requires a literal method name')
    value = json.loads(token[1])
    if not _METHOD.fullmatch(value[:-1] + '.member' if prefix and value.endswith('.') else value):
        raise ValueError('Malformed RPC method name or prefix')
    if prefix and not value.endswith('.'):
        raise ValueError('RPC prefix must end at a namespace separator')
    return value


def server_methods(raw, prefix_fallbacks):
    """Recognize the reviewed literal filter/dispatch grammar, fail closed.

    This is an interface census, not a C++ behavior proof. Every parsed.method
    use must be an exact comparison, a bounded literal prefix comparison, or
    the leading rejecting IsKnownMethod guard. A prefix is never permission
    to silently classify a new declaration: fallback-only names need an
    explicit reviewed statement witness in the source provenance manifest.
    """
    text = raw.decode('utf-8')
    tokens = _tokens(text)
    values = [t[1] for t in tokens]
    definitions = [i for i in range(len(tokens) - 3) if values[i:i+3] == ['static', 'bool', 'IsKnownMethod']]
    if len(definitions) != 1:
        raise ValueError('Expected one complete IsKnownMethod definition')
    opening = values.index('{', definitions[0])
    closing = _brace_end(tokens, opening)
    body = tokens[opening+1:closing]
    if not body or body[0][1] != 'return' or body[-1][1] != ';':
        raise ValueError('Unsupported known-method filter grammar')
    declared, declared_lines = set(), {}
    expression = body[1:-1]
    while expression:
        if len(expression) < 3 or [t[1] for t in expression[:2]] != ['method', '==']:
            raise ValueError('Unsupported known-method filter grammar')
        method = _string(expression[2])
        if method in declared:
            raise ValueError('Duplicate known RPC method: ' + method)
        declared.add(method)
        declared_lines[method] = text.count('\n', 0, expression[2][2]) + 1
        expression = expression[3:]
        if expression:
            if expression[0][1] != '||' or len(expression) == 1:
                raise ValueError('Unsupported known-method filter grammar')
            expression = expression[1:]
    exact, compared, prefixes, guards, dispatch_lines = set(), set(), {}, [], {}
    uses = [i for i in range(len(tokens)-2) if values[i:i+3] == ['parsed', '.', 'method']
            and all(t[0] != 'string' for t in tokens[i:i+3])]
    for index in uses:
        tail = values[index+3:]
        if tail and tail[0] in ('==', '!='):
            method = _string(tokens[index+4])
            compared.add(method)
            if tail[0] == '==':
                exact.add(method)
                dispatch_lines.setdefault(method, []).append(text.count('\n', 0, tokens[index][2]) + 1)
        elif tail[:4] == ['.', 'compare', '(', '0']:
            if (tail[4:5] != [','] or tail[6:7] != [','] or tail[8:12] != [')', '==', '0', ')']
                    or not tail[5].isdigit()):
                raise ValueError('Unsupported RPC prefix dispatch grammar')
            prefix = _string(tokens[index+10], prefix=True)
            if int(tail[5]) != len(prefix) or prefix in prefixes:
                raise ValueError('Invalid or duplicate RPC prefix dispatch')
            group_start = values.index('{', index+3)
            group_end = _brace_end(tokens, group_start)
            prefixes[prefix] = tokens[group_start+1:group_end]
        elif values[max(0,index-5):index] == ['if', '(', '!', 'IsKnownMethod', '('] and tail[:3] == [')', ')', 'return']:
            guards.append(index)
        else:
            raise ValueError('Unclassified parsed.method use at line ' + str(text.count('\n', 0, tokens[index][2]) + 1))
    if len(guards) != 1 or not uses or guards[0] != uses[0]:
        raise ValueError('Missing leading rejecting known-method guard')
    if compared - declared:
        raise ValueError('Dispatch references undeclared RPC methods: ' + ', '.join(sorted(compared-declared)))
    missing = declared - exact
    if missing != set(prefix_fallbacks):
        raise ValueError('Known RPC methods lack reviewed dispatch: ' + ', '.join(sorted(missing ^ set(prefix_fallbacks))))
    for prefix, group in prefixes.items():
        if not any(name.startswith(prefix) for name in declared):
            raise ValueError('RPC prefix dispatch has no declared methods: ' + prefix)
    for method, witness in prefix_fallbacks.items():
        prefix = witness['prefix']
        if prefix not in prefixes or not method.startswith(prefix):
            raise ValueError('RPC fallback lacks its prefix dispatch: ' + method)
        expected = [t[:2] for t in _tokens(witness['required_statement'])]
        actual = [t[:2] for t in prefixes[prefix]]
        if not expected or not any(actual[i:i+len(expected)] == expected for i in range(len(actual))):
            raise ValueError('RPC fallback statement is missing: ' + method)
    return {'methods': sorted(declared), 'known_method_lines': declared_lines,
            'exact_dispatch_lines': dispatch_lines, 'prefix_dispatches': sorted(prefixes),
            'reviewed_prefix_fallbacks': prefix_fallbacks,
            'unclassified_dispatch_uses': 0}


def census(root=ROOT):
    root = Path(root)
    provenance_path = root / 'experimental/dosbox-x/census/upstream.json'
    provenance_raw = _read(provenance_path, 16384)
    provenance = json.loads(provenance_raw)
    if provenance.get('format') != 'fdisbull-dosbox-rpc-census-upstream-1' or provenance.get('member') != MEMBER:
        raise ValueError('Invalid native RPC census provenance')
    source = _read(provenance_path.with_name('agent_server.upstream.cpp'), 1024*1024)
    if digest(source) != provenance['member_sha256'] or len(source) != provenance['member_bytes']:
        raise ValueError('Upstream native server identity differs')
    profiles = {}
    for profile, directory in PROFILES.items():
        manifest_raw = _read(root / directory / 'source-manifest.json', 2*1024*1024)
        manifest = json.loads(manifest_raw)
        if manifest['baseline_commit'] != provenance['baseline_commit']:
            raise ValueError('Native source baseline differs')
        patch = _read(root / directory / 'headless-agent.patch', 8*1024*1024)
        if digest(patch) != manifest['patch_sha256']:
            raise ValueError('Native patch identity differs: ' + profile)
        expected = [item for item in manifest['source_files'] if item['path'] == MEMBER]
        if len(expected) != 1:
            raise ValueError('Native manifest requires exactly one server member')
        native = replay_member(source, patch)
        if digest(native) != expected[0]['sha256'] or len(native) != expected[0]['size']:
            raise ValueError('Reconstructed native server identity differs: ' + profile)
        profiles[profile] = dict(server_methods(native, provenance['prefix_fallbacks']),
            patch_sha256=digest(patch), source_sha256=digest(native), source_bytes=len(native),
            source_manifest_sha256=digest(manifest_raw))
    return {'format': 'fdisbull-dosbox-rpc-census-1', 'upstream': provenance,
            'provenance_sha256': digest(provenance_raw), 'profiles': profiles,
            'methods': sorted({name for p in profiles.values() for name in p['methods']}),
            'runtime_validation': 'not_run', 'scope': 'Complete pinned source interface census; no native behavior or parity qualification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Repository root with pinned census input, complete patches and manifests')
    args = parser.parse_args()
    result = census(args.root)
    ledger = json.loads(_read(args.root / 'src/fdisbull/data/dos-migration.json', 2*1024*1024))
    declared = [row['method'] for row in ledger['rpc_methods']]
    if len(set(declared)) != len(declared) or set(declared) != set(result['methods']):
        raise ValueError('Migration RPC inventory differs from the complete native census')
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
