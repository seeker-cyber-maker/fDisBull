#!/usr/bin/env python3
"""Measure and verify an AGI census; emit only identities and aggregate evidence.

Supply your own qualified private game directories. No game is executed and no
resource, script, message, vocabulary, inventory name or memory is exported.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / 'src').is_dir():
    sys.path.insert(0, str(ROOT / 'src'))

from fdisbull.agi import inspect_logic
from fdisbull.agi_resources import V2Resources
from fdisbull.agi_scenes import inspect_scenes


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True).encode()).hexdigest()


def source_identity(root):
    names = {'LOGDIR', 'PICDIR', 'VIEWDIR', 'SNDDIR', 'OBJECT', 'WORDS.TOK', 'AGI', 'AGIDATA.OVL'}
    return {p.name: {'size': p.stat().st_size, 'sha256': sha256(p.read_bytes()).hexdigest()}
            for p in sorted(root.iterdir()) if p.is_file() and
            (p.name.upper() in names or re.fullmatch(r'VOL\.\d+', p.name.upper()))}


def verify_game(root, runs):
    before = source_identity(root)
    stages, documents = {}, {}
    for stage in ('outline', 'resolve'):
        durations, hashes = [], []
        for _ in range(runs):
            start = time.perf_counter()
            doc = inspect_scenes(root, profile='2.917', stage=stage)
            durations.append((time.perf_counter() - start) * 1000)
            if doc['sha256'] != digest({k: v for k, v in doc.items() if k != 'sha256'}):
                raise ValueError('Census canonical digest mismatch')
            hashes.append(doc['sha256'])
        if len(set(hashes)) != 1:
            raise ValueError('Repeated scans were not deterministic')
        stages[stage] = {'samples_ms': durations, 'median_ms': statistics.median(durations),
                         'minimum_ms': min(durations), 'maximum_ms': max(durations),
                         'canonical_sha256': hashes[0], 'coverage': doc['coverage']}
        documents[stage] = doc
    full = inspect_scenes(root, profile='2.917', include_ir=True)
    store = V2Resources(root)
    payloads = {r['number']: r['payload'] for r in store.resources('logic') if r['status'] == 'ok'}
    logdir = next(p for p in root.iterdir() if p.name.upper() == 'LOGDIR')
    compared, rebuilt_bytes, rebuilt_instructions, legacy_unsupported = 0, 0, 0, 0
    reference_by_logic = {entry['logic']: entry for entry in documents['resolve']['logics']}
    outline_by_logic = {entry['logic']: entry for entry in documents['outline']['logics']}
    for logic in full['logics']:
        if logic['status'] != 'decoded':
            continue
        body = logic['ir']['instructions']
        if digest(body) != logic['ir']['sha256']:
            raise ValueError('Structural IR digest mismatch')
        reference = reference_by_logic[logic['logic']]
        outline = outline_by_logic[logic['logic']]
        if logic['ir']['sha256'] != reference['ir']['sha256'] or logic['ir']['sha256'] != outline['ir']['sha256']:
            raise ValueError('Outline, resolve and expanded IR changed the source representation')
        if logic['references'] != reference['references']:
            raise ValueError('Expanding IR changed recovered references')
        payload = payloads[logic['logic']]
        code = payload[2:2 + int.from_bytes(payload[:2], 'little')]
        rebuilt = b''.join(bytes([row['opcode']]) + bytes(row['operands']) for row in body)
        if rebuilt != code or body[0]['offset'] != 2 or body[-1]['end_offset'] != 2 + len(code):
            raise ValueError('Structural IR did not preserve the complete bytecode')
        if any(a['end_offset'] != b['offset'] for a, b in zip(body, body[1:])):
            raise ValueError('Structural IR has a source gap or overlap')
        rebuilt_bytes += len(code)
        rebuilt_instructions += len(body)
        by_offset = {row['offset']: row for row in body}
        old = inspect_logic(logdir, root, logic['logic'], profile='2.917', max_instructions=10000)
        for row in old['instructions']:
            if row['mnemonic'] == 'unsupported':
                legacy_unsupported += 1
                continue
            new = by_offset.get(row['offset'] + 2)
            if new is None or new['opcode'] != row['opcode'] or new['end_offset'] - new['offset'] != row['size']:
                raise ValueError('Disagreement with preserved partial inspector')
            if (bytes([new['opcode']]) + bytes(new['operands'])).hex() != row['bytes']:
                raise ValueError('Partial inspector source bytes differ')
            compared += 1
    after = source_identity(root)
    if before != after:
        raise ValueError('Input identity changed during verification')
    return {'profile': '2.917', 'source_files': before, 'source_files_unchanged': True,
            'stages': stages, 'source_read_counts_per_scan': full['source']['read_counts'],
            'backing_checks': {'ir_roundtrip_equal': True, 'ir_code_bytes': rebuilt_bytes,
                               'ir_instructions': rebuilt_instructions,
                               'all_stages_ir_identity_equal': True,
                               'expanded_references_equal': True,
                               'legacy_subset_instructions_compared': compared,
                               'legacy_unsupported_frontier_instructions': legacy_unsupported,
                               'legacy_scope': 'source bytes and widths of the preserved partial inspector; not an execution oracle'},
            'resource_issues': full['resource_issues'],
            'native_execution': False, 'accepted_uil_interactions': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', action='append', required=True, metavar='NAME=DIRECTORY')
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error('--runs must be 1..10')
    games = {}
    for item in args.game:
        name, separator, directory = item.partition('=')
        if not separator or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name) or name in games:
            parser.error('--game needs a unique short NAME=DIRECTORY')
        games[name] = Path(directory)
    report = {'format': 'fdisbull-agi-census-verification-1',
              'python': platform.python_version(), 'runs_per_stage': args.runs,
              'timing_scope': 'warm repeated in-process scan including fresh reads, hashing, parsing, stage analysis and canonical digest; excludes process startup, report serialization, source backing checks, setup and research',
              'speedup_comparison': None, 'games': {name: verify_game(root, args.runs) for name, root in games.items()},
              'implementation_sha256': {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                                        for path in [ROOT / 'src/fdisbull/agi_resources.py', ROOT / 'src/fdisbull/agi_scenes.py',
                                                     ROOT / 'src/fdisbull/agi_layout.py', ROOT / 'src/fdisbull/cli.py']}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'ok': True, 'games': {name: game['stages']['resolve']['coverage']
                                          for name, game in report['games'].items()}}, sort_keys=True))


if __name__ == '__main__':
    main()
