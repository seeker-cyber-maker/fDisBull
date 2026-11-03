"""Read-only bound survey for schema-8, x86-32, version-1 private projects.

No source instructions/bytes are written to the report. Bound results remain
conditional on traversing the modeled slice; table integrity is separate.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from switch_guard import qualify

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; choose a new evidence filename')
    uri = args.project.resolve().as_uri() + '?mode=ro'
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        meta = dict(conn.execute('SELECT key, value FROM metadata'))
        if int(meta['schema']) != 8 or json.loads(meta['arch']) != 'x86' or int(meta['bits']) != 32:
            parser.error('this research reader only supports schema 8 x86-32 version-1 projects')
        records = qualify(conn)
    fields = ('dispatch', 'status', 'slice_start', 'guard', 'escape', 'table',
              'entry_count', 'bound', 'verdict', 'guard_feasible', 'claim')
    payload = {'scope': 'Local source-bound slice models, not runtime reachability or table integrity.',
               'records': [{k:r[k] for k in fields if k in r} for r in records]}
    args.output.write_text(json.dumps(payload, indent=2) + '\n')
    print('Wrote', len(records), 'conditional site records to', args.output)

if __name__ == '__main__':
    main()
