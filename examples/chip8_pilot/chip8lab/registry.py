"""Private read-only-after-creation evidence index for CHIP-8 observation candidates.

Do not confuse this with production UIL/UDC registry !57. A CHIP-8 instruction
family is not a qualified, cross-program semantic identity. CC0 provenance is
attached to every source; observations come only from the authored toy VM.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3


def build_index(report:dict, destination:Path):
    destination=Path(destination)
    if destination.exists():raise FileExistsError(destination)
    if any((parent/'.git').is_file() or (parent/'.git'/'HEAD').is_file()
           for parent in destination.resolve().parents):
        raise ValueError('local evidence database must stay outside Git')
    destination.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(destination)
    try:
        db.executescript('''
        CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE sources(sha256 TEXT PRIMARY KEY, title TEXT, platform TEXT, author TEXT,
                             origin_url TEXT, declared_license TEXT);
        CREATE TABLE block_candidates(
           source_sha TEXT NOT NULL REFERENCES sources(sha256),
           pc TEXT NOT NULL, word TEXT NOT NULL, family TEXT NOT NULL, proposed_intent TEXT NOT NULL,
           observed_count INTEGER NOT NULL CHECK(observed_count>0),
           evidence_status TEXT NOT NULL, PRIMARY KEY(source_sha,pc,word));
        CREATE INDEX block_by_family ON block_candidates(family,proposed_intent);
        CREATE TABLE observed_edges(source_sha TEXT NOT NULL REFERENCES sources(sha256),
           from_pc TEXT NOT NULL,to_pc TEXT NOT NULL,observed_count INTEGER NOT NULL,
           PRIMARY KEY(source_sha,from_pc,to_pc));
        ''')
        with db:
            db.execute('INSERT INTO metadata VALUES (?,?)',('format','fdisbull-chip8-observation-study-1'))
            db.execute('INSERT INTO metadata VALUES (?,?)',('source_report_sha256',report['receipt_sha256']))
            for item in report['corpus']['roms']:
                sha=item['sha256']
                db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?)',(
                    sha,item['title'],item['platform'],item['author'],
                    f"https://github.com/JohnEarnest/chip8Archive/blob/{report['source_commit']}/roms/{item['key']}.ch8",
                    'CC0-1.0 (archive claim)'))
                for b in item['dynamic'].get('block_candidates',[]):
                    db.execute('INSERT INTO block_candidates VALUES (?,?,?,?,?,?,?)',(
                        sha,b['source_address'],b['raw_word'],b['udl']['family'],
                        b['uil_intent_candidate'],b['observed_count'],b['behavioral_qualification']))
                for e in item['dynamic'].get('observed_edges',[]):
                    db.execute('INSERT INTO observed_edges VALUES (?,?,?,?)',(
                        sha,e['from'],e['to'],e['count']))
        db.close()
        return inspect_index(destination)
    except Exception:
        db.close()
        destination.unlink(missing_ok=True)
        raise


def inspect_index(path):
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True)
    try:
        meta=dict(db.execute('SELECT key,value FROM metadata ORDER BY key'))
        total=db.execute('SELECT count(*) FROM block_candidates').fetchone()[0]
        families=[{'family':x,'intent':y,'observations':n,'distinct_sources':s}
            for x,y,n,s in db.execute('''SELECT family,proposed_intent, count(*),count(DISTINCT source_sha)
                FROM block_candidates GROUP BY family,proposed_intent ORDER BY family''')]
        return {'metadata':meta,'sources':db.execute('SELECT count(*) FROM sources').fetchone()[0],
                'candidate_rows':total,'families':families,
                'edges':db.execute('SELECT count(*) FROM observed_edges').fetchone()[0],
                'boundary':'structurally stored observations; no original-runtime equivalence, cross-source semantic proof or execution grant'}
    finally:db.close()