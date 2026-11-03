"""Immutable common-UIL packages in a project, with original versions retained."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import sqlite3
import uuid

from .common_uil import (canonical_bytes, digest, validate_program,
                        validate_presentation, validate_orchestration, validate_realization)

PACKAGE = 'fdisbull-common-uil-package-1'


def validate_package(package):
    if type(package) is not dict or set(package) != {'format','program','presentation','catalog','orchestration'} or package['format'] != PACKAGE:
        raise ValueError('invalid common UIL package')
    canonical_bytes(package)
    validate_program(package['program'])
    validate_presentation(package['program'],package['presentation'])
    validate_realization(package['program'],package['presentation'],package['catalog'],package['orchestration'])
    return True


@contextmanager
def _savepoint(db):
    name = 'common_uil_' + uuid.uuid4().hex
    db.execute('SAVEPOINT ' + name)
    try:
        yield
    except BaseException:
        db.execute('ROLLBACK TO ' + name); db.execute('RELEASE ' + name)
        raise
    else:
        db.execute('RELEASE ' + name)


class CommonUILMixin:
    def store_uil_package(self, name, package, *, version=None, parent=None, author='agent'):
        validate_package(package)
        for label,value in (('name',name),('author',author)):
            if type(value) is not str or not 1 <= len(value) <= 128 or any(ord(c)<32 for c in value):
                raise ValueError('invalid common UIL '+label)
        source = self.version(version)
        with _savepoint(self.db):
            self.db.execute('''CREATE TABLE IF NOT EXISTS common_uil_packages (
                id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
                name TEXT NOT NULL, parent TEXT REFERENCES common_uil_packages(id),
                sha256 TEXT NOT NULL, author TEXT NOT NULL, document TEXT NOT NULL)''')
            previous = self.db.execute('SELECT id FROM common_uil_packages WHERE version=? AND name=? ORDER BY rowid DESC LIMIT 1',
                                       (source['id'],name)).fetchone()
            if previous is not None and parent != previous['id']:
                raise ValueError('updating UIL requires the current immutable parent')
            if previous is None and parent is not None:
                raise ValueError('first UIL package cannot have a parent')
            record = {'format':'fdisbull-common-uil-record-1','name':name,'author':author,
                      'parent':parent,'version':source['id'],'source_version_sha256':source['sha256'],
                      'package':deepcopy(package)}
            sha = digest(record); ident = 'uil:' + sha
            encoded = canonical_bytes(record).decode()
            found = self.db.execute('SELECT document FROM common_uil_packages WHERE id=?',(ident,)).fetchone()
            if found is not None and found['document'] != encoded:
                raise ValueError('common UIL identity collision')
            if found is None:
                self.db.execute('INSERT INTO common_uil_packages VALUES (?,?,?,?,?,?,?)',
                                (ident,source['id'],name,parent,sha,author,encoded))
        return self.uil_package_info(ident)

    def uil_package_info(self, revision, *, full=False):
        if type(full) is not bool:
            raise ValueError('full must be boolean')
        try:
            row = self.db.execute('SELECT * FROM common_uil_packages WHERE id=?',(revision,)).fetchone()
        except sqlite3.OperationalError as exc:
            raise ValueError('no stored common UIL packages') from exc
        if row is None:
            raise ValueError('unknown common UIL package')
        record = json.loads(row['document'])
        if (type(record) is not dict or set(record) != {'format','name','author','parent','version','source_version_sha256','package'}
                or record['format'] != 'fdisbull-common-uil-record-1'
                or canonical_bytes(record).decode() != row['document']):
            raise ValueError('noncanonical/corrupt stored common UIL record')
        validate_package(record['package'])
        if digest(record) != row['sha256'] or row['id'] != 'uil:'+row['sha256']:
            raise ValueError('stored common UIL digest mismatch')
        if any(record[k] != row[k] for k in ('name','author','parent','version')):
            raise ValueError('stored common UIL metadata mismatch')
        if self.version(record['version'])['sha256'] != record['source_version_sha256']:
            raise ValueError('stored common UIL source-version binding mismatch')
        package = record['package']
        result = {k:row[k] for k in ('id','version','name','parent','sha256','author')}
        result.update(program_sha256=digest(package['program']),
                      catalog_sha256=digest(package['catalog']),
                      presentation_sha256=digest(package['presentation']),
                      orchestration_sha256=digest(package['orchestration']),
                      source_binding='version-identity-only; source correspondence remains separately qualified')
        if full: result['document'] = deepcopy(record)
        return result

    def uil_packages(self, *, limit=100, offset=0):
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValueError('invalid common UIL pagination')
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='common_uil_packages'").fetchone() is None:
            return []
        rows = self.db.execute('SELECT id FROM common_uil_packages ORDER BY rowid LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        return [self.uil_package_info(r['id']) for r in rows]
