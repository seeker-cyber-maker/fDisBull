"""Local, immutable, deliberately narrow UDC rule index for the CHIP-8 PoC.

The agent swedes a new Python template in swedes.py (manual review), then uses
this index to register its identity. The compiler accepts only exact templates
in the trusted source module. SQLite metadata NEVER becomes executable code.
This is NOT production registry !57 and does not import arbitrary plugins.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from .swedes import SWEDES

FORMAT='chip8-python-udc-rule-study-1'

def template_digest(family:str):
    return hashlib.sha256(SWEDES[family].encode('utf-8')).hexdigest()

class RuleCatalog:
    def __init__(self,path,*,create=False):
        self.path=Path(path).resolve()
        if any((parent/'.git').is_file() or (parent/'.git'/'HEAD').is_file()
               for parent in (self.path, *self.path.parents)):
            raise ValueError('rule catalog must live outside a Git checkout')
        if create:
            with self.path.open('xb'): pass
        elif not self.path.exists():
            raise FileNotFoundError(self.path)
        self.db=sqlite3.connect(self.path)
        try:
            if create:
                self.db.executescript('''
                  CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                  CREATE TABLE rules(family TEXT PRIMARY KEY, template_sha256 TEXT NOT NULL,
                       provenance TEXT NOT NULL, status TEXT NOT NULL);
                ''')
                self.db.execute('INSERT INTO metadata VALUES (?,?)',('format',FORMAT))
                self.db.commit()
            if self.db.execute('SELECT value FROM metadata WHERE key="format"').fetchone()!=(FORMAT,):
                raise ValueError('unsupported registry format')
        except Exception:
            self.db.close()
            raise

    def __enter__(self):return self
    def __exit__(self,*_):self.db.close()

    def register(self,family,*,provenance='agent-authored Python rule'):
        if family not in SWEDES:raise ValueError('manual swede rule must exist in trusted swedes.py before registration')
        dig=template_digest(family)
        row=self.db.execute('SELECT template_sha256 FROM rules WHERE family=?',(family,)).fetchone()
        if row is not None and row[0]!=dig:
            raise ValueError('old template revision must not be overwritten; create a new registry revision')
        if row is not None:return False
        with self.db:
            self.db.execute('INSERT INTO rules VALUES (?,?,?,?)',(family,dig,provenance,'declared-author-template'))
        return True

    def available(self):
        rows=self.db.execute('SELECT family,template_sha256 FROM rules ORDER BY family').fetchall()
        for fam,dig in rows:
            if fam not in SWEDES or template_digest(fam)!=dig:
                raise ValueError('untrusted/mismatched swede template identity: '+fam)
        return {fam for fam,_ in rows}

    def summary(self):
        families=sorted(self.available())
        raw=json.dumps([(f,template_digest(f)) for f in families],separators=(',',':')).encode()
        return {'format':FORMAT,'status':'declarative; no execution authority',
                'registered_families':families,'registered_count':len(families),
                'catalog_sha256':hashlib.sha256(raw).hexdigest(),
                'remaining_available_agent_templates':sorted(set(SWEDES)-set(families))}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('init','register','summary'))
    parser.add_argument('database',type=Path)
    parser.add_argument('families',nargs='*')
    parser.add_argument('--omit',nargs='*',default=[])
    a=parser.parse_args()
    with RuleCatalog(a.database,create=a.command=='init') as db:
        if a.command=='init':
            for name in sorted(SWEDES):
                if name not in a.omit: db.register(name)
        elif a.command=='register':
            if not a.families:raise SystemExit('supply one or more reviewed family names')
            for name in a.families: db.register(name)
        print(json.dumps(db.summary(),indent=2,sort_keys=True))

if __name__=='__main__':main()