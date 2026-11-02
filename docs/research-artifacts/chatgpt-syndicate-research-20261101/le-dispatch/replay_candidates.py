"""Replay the retained candidate seed plan on a NEW private FDB copy.

This uses a pinned research-only private queue seam in fDisBull 0.26.0.
It neither changes source bytes nor inserts resolved indirect edges.
Do not put inputs, databases, outputs, or their raw logs in Git.
"""
import argparse
import hashlib
import importlib.metadata
import json
import sqlite3
from pathlib import Path
from fdisbull.project import Project

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--plan', type=Path, default=Path(__file__).with_name('replay-plan.json'))
    parser.add_argument('--max-attempts', type=int, default=100000)
    args = parser.parse_args()
    if importlib.metadata.version('fdisbull') != '0.26.0':
        parser.error('requires the research-pinned fDisBull 0.26.0')
    if args.destination.exists() or args.baseline.resolve() == args.destination.resolve():
        parser.error('destination must be a new file; originals are never overwritten')
    for parent in (args.destination.parent.resolve(), *args.destination.parent.resolve().parents):
        if (parent / '.git').exists():
            parser.error('destination must be outside Git')
    if args.max_attempts <= 0:
        parser.error('max-attempts must be positive')
    plan = json.loads(args.plan.read_text())
    with sqlite3.connect(args.baseline.resolve().as_uri() + '?mode=ro', uri=True) as source:
        meta = dict(source.execute('SELECT key,value FROM metadata'))
        if json.loads(meta['source_sha256']) != plan['source_sha256']:
            parser.error('source identity differs from the retained research plan')
        if source.execute('SELECT COUNT(*) FROM instructions WHERE version=1').fetchone()[0] != plan['baseline_instructions']:
            parser.error('expected the original 22,910-instruction checkpoint')
        with sqlite3.connect(args.destination) as out:
            source.backup(out)
    remaining = args.max_attempts
    runs = []
    with Project(args.destination) as project:
        if project.digest(project.regions(1)) != plan['mapped_sha256']:
            raise ValueError('mapped image differs; no candidate seeds applied')
        for stage in plan['stages']:
            entries = [int(a,16) for a in stage['entries']]
            if remaining <= 0:
                break
            if stage['recorded_using_function_seed_API']:
                for address in entries:
                    if remaining <= 0: break
                    result = project.analyze(start=address, max_instructions=min(8000,remaining))
                    remaining -= result['attempted']
                    runs.append({'stage':stage['name'], 'entry':hex(address), 'result':result})
            else:
                with project.transaction(True):
                    for address in entries:
                        project._queue_code(1,address,'research conditional candidate replay: '+stage['name'])
                while remaining > 0:
                    result = project.analyze(max_instructions=min(15000,remaining))
                    remaining -= result['attempted']
                    runs.append({'stage':stage['name'], 'result':result})
                    if result['stable'] or result['attempted'] == 0: break
        result = {'runs':runs, 'remaining_attempt_budget':remaining,
                  'instructions':project.db.execute('SELECT COUNT(*) FROM instructions WHERE version=1').fetchone()[0],
                  'integrity':project.db.execute('PRAGMA integrity_check').fetchone()[0],
                  'source_bytes_changed':False, 'native_execution':False,
                  'qualification':'Conditional candidate replay, not proved reachability.'}
        assert project.digest(project.regions(1)) == plan['mapped_sha256']
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
