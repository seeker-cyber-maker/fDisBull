#!/usr/bin/env python3
"""Private one-way intake copies and consistent FDB version backups.

FSEvents is advisory: every invocation reconciles admitted local roots. Remote
deletions are never requested. Only a verified transfer advances local state.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import time
import uuid

from fdb_backup import capture_fdb

FORMAT = 'fdisbull-drive-sync-1'


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n'


def _write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex)
    _write_new(temp, _json(value).encode())
    os.replace(temp, path)


def _root(path):
    path = Path(path).expanduser().absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Admitted source roots cannot have symlink ancestry')
    if not path.is_dir():
        raise ValueError('Admitted source root is unavailable: ' + str(path))
    return path


def _identity(path):
    s = path.stat()
    return {'device': s.st_dev, 'inode': s.st_ino}


def _member(root, relative):
    path = Path(relative)
    if not path.parts or path.is_absolute() or any(p in ('', '.', '..') for p in path.parts):
        raise ValueError('Source selection must be a relative path')
    target = root / path
    for parent in target.parents:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError('Source selection traverses a symlink')
    return target


def scan_library(library):
    """Inventory only explicit selections; retain links as metadata, not bytes."""
    root = _root(library['root'])
    expected = library.get('identity')
    if expected and _identity(root) != expected:
        raise ValueError('Library root identity changed; no transfer attempted')
    result = {}
    def visit(path):
        s = path.lstat()
        relative = path.relative_to(root).as_posix()
        if any(c in relative for c in ('\n', '\r', '\x00')):
            raise ValueError('Source name cannot be represented safely in a transfer list')
        common = dict(path=str(path), size=s.st_size, mtime_ns=s.st_mtime_ns,
                      ctime_ns=s.st_ctime_ns, inode=s.st_ino, device=s.st_dev)
        if stat.S_ISLNK(s.st_mode):
            result[relative] = dict(common, kind='symlink', target=os.readlink(path))
        elif stat.S_ISDIR(s.st_mode):
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(s.st_mode):
            result[relative] = dict(common, kind='file')
        else:
            raise ValueError('Special library entry is unsupported: ' + relative)
    for relative in library.get('include_dirs', []):
        selected = _member(root, relative)
        if not selected.is_dir() or selected.is_symlink():
            raise ValueError('Admitted library directory is missing or aliased: ' + relative)
        visit(selected)
    for relative in library.get('include_files', []):
        selected = _member(root, relative)
        if not selected.exists() and not selected.is_symlink():
            raise ValueError('Admitted library metadata is missing: ' + relative)
        visit(selected)
    return result


def stable_copy(source, destination):
    """Capture bytes with a no-follow descriptor and compare-before/after guard."""
    source, destination = Path(source), Path(destination)
    for parent in source.parents:
        if parent.is_symlink():
            raise ValueError('Cannot capture through symlink ancestry')
    before = source.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Stable capture requires a regular file')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as reader:
        observed = os.fstat(reader.fileno())
        def key(s):
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns
        if key(observed) != key(before):
            raise ValueError('Source changed before capture')
        with destination.open('xb') as writer:
            for block in iter(lambda: reader.read(1024 * 1024), b''):
                writer.write(block); sha.update(block); md5.update(block)
            writer.flush(); os.fsync(writer.fileno())
        if key(os.fstat(reader.fileno())) != key(before) or key(source.lstat()) != key(before):
            raise ValueError('Source changed during capture; staged bytes are not published')
    if destination.stat().st_size != before.st_size:
        raise ValueError('Captured length differs')
    return dict(sha256=sha.hexdigest(), md5=md5.hexdigest(), size=before.st_size)


class RcloneTransport:
    """Pinned private Drive root, retained overwritten versions, exact MD5 readback."""
    def __init__(self, config):
        self.config = config
        self.executable = config.get('executable', '/opt/homebrew/bin/rclone')
        self.remote = config['remote']
        if not self.remote.endswith(':') or '/' in self.remote:
            raise ValueError('Use a named rclone remote with a separately pinned root ID')
        if not config.get('root_id'):
            raise ValueError('Drive root folder ID is required before activation')

    def command(self, *args):
        command = [self.executable, *args, '--config', self.config['config'],
                   '--ask-password=false', '--drive-root-folder-id', self.config['root_id']]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=self.config.get('timeout_seconds', 480))
        if result.returncode:
            # Token/config contents and provider diagnostics never enter receipts.
            raise RuntimeError('rclone transfer/verification failed; exit=' + str(result.returncode))
        return result.stdout

    def put_tree(self, source_dir, remote_path, backup_suffix):
        source_dir = Path(source_dir)
        files = {p.relative_to(source_dir).as_posix(): p for p in source_dir.rglob('*') if p.is_file()}
        if any(p.is_symlink() for p in source_dir.rglob('*')):
            raise ValueError('Staged transfer trees cannot contain symlinks')
        if not files:
            return {'verified': True, 'files': 0}
        destination = self.remote + remote_path
        self.command('copy', str(source_dir), destination, '--checksum', '--fast-list',
                     '--backup-dir', self.remote + 'history/' + backup_suffix + '/' + remote_path,
                     '--transfers', '8', '--checkers', '8', '--tpslimit', '8', '--retries', '3', '--low-level-retries', '5')
        # Google Drive ordinary files expose MD5. Never treat a size-only check
        # as verification. Only this exact submitted set must match.
        expected={}
        for relative,path in files.items():
            md5=hashlib.md5()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):md5.update(block)
            expected[relative]={'size':path.stat().st_size,'md5':md5.hexdigest()}
        self.verify_files(remote_path,expected)
        return {'verified': True, 'files': len(files), 'verification': 'Drive MD5 and size',
                'expected':expected}

    def verify_files(self,remote_path,expected):
        if not expected:return {'verified':True,'files':0}
        response = json.loads(self.command('lsjson', self.remote+remote_path, '--recursive', '--files-only', '--fast-list',
                                          '--hash', '--hash-type', 'MD5'))
        actual = {}
        for row in response:
            path = row.get('Path')
            if path in actual:
                raise ValueError('Duplicate remote path is ambiguous')
            actual[path] = row
        for relative,proof in expected.items():
            row = actual.get(relative, {})
            hashes = {key.lower(): value for key, value in row.get('Hashes', {}).items()}
            if row.get('Size') != proof['size'] or hashes.get('md5') != proof['md5']:
                raise ValueError('Cloud size/MD5 readback differs or is unavailable: ' + relative)
        return {'verified': True, 'files': len(expected), 'verification': 'Drive MD5 and size'}


def _proofs(directory):
    result={}
    for p in Path(directory).rglob('*'):
        if p.is_file():
            h=hashlib.md5()
            with p.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            result[p.relative_to(directory).as_posix()]={'size':p.stat().st_size,'md5':h.hexdigest()}
    return result


@contextmanager
def _lock(state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (state / 'worker.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A sync worker already owns this repository') from None
        yield


def _state(path):
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, signature TEXT, receipt TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS projects(path TEXT PRIMARY KEY, signature TEXT, generation TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS metadata(name TEXT PRIMARY KEY, value TEXT)')
    db.commit()
    return db


def _signature(entry):
    return json.dumps({key: entry.get(key) for key in ('kind','size','mtime_ns','ctime_ns','inode','device','target')}, sort_keys=True)


def _fdb_inputs(repository):
    root = _root(repository['root'])
    if repository.get('identity') and _identity(root) != repository['identity']:
        raise ValueError('FDB repository identity changed')
    projects = root / 'projects'
    if not projects.is_dir() or projects.is_symlink():
        raise ValueError('FDB projects directory is unavailable')
    result = []
    for base, dirs, files in os.walk(projects, followlinks=False):
        if any((Path(base) / name).is_symlink() for name in dirs):
            raise ValueError('FDB project directory symlinks must be registered explicitly')
        for name in sorted(files):
            if name.lower().endswith('.fdb'):
                path = Path(base) / name
                if path.is_symlink():
                    raise ValueError('FDB project symlinks must be registered explicitly')
                result.append((str(path), repository.get('objects_roots', [])))
    registrations = root / 'registrations'
    if registrations.exists():
        for path in sorted(registrations.glob('*.json')):
            if path.is_symlink():
                raise ValueError('FDB registration must be a regular local file')
            entry = json.loads(path.read_text())
            result.append((entry['path'], entry.get('objects_roots', repository.get('objects_roots', []))))
    unique = {}
    for path, roots in result:
        if path in unique and unique[path] != roots:
            raise ValueError('Conflicting object-store registrations for FDB')
        unique[path] = roots
    return sorted(unique.items())


def _db_signature(path):
    result = []
    for suffix in ('', '-wal'):
        selected = Path(str(path) + suffix)
        if selected.is_symlink():
            raise ValueError('FDB/WAL symlink is unsupported')
        if selected.exists():
            s = selected.stat()
            result.append((suffix, s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns))
    if not result or result[0][0] != '':
        raise ValueError('Registered FDB is unavailable')
    return json.dumps(result)


def plan(config):
    entries = scan_library(config['library'])
    return dict(format=FORMAT, library_files=sum(x['kind']=='file' for x in entries.values()),
                library_bytes=sum(x['size'] for x in entries.values() if x['kind']=='file'),
                symlinks_recorded=sum(x['kind']=='symlink' for x in entries.values()),
                fdb_inputs=len(_fdb_inputs(config['fdb_repository'])),
                deletion_policy='retain remote files and all overwritten versions',
                external_links='metadata only; linked sources are not silently followed')


def _sync_library_phase(config, db, directory, run, result, transport):
    entries = scan_library(config['library'])
    library = directory / 'library'
    objects = directory / 'library-objects'
    pending = []
    for relative, entry in entries.items():
        signature = _signature(entry)
        previous = db.execute('SELECT signature FROM files WHERE path=?', (relative,)).fetchone()
        if previous and previous[0] == signature:
            continue
        if entry['kind'] == 'symlink':
            receipt = dict(kind='symlink', target=entry['target'], bytes_uploaded=False)
        else:
            captured = library / relative
            receipt = stable_copy(entry['path'], captured)
            objects.mkdir(exist_ok=True)
            object_path = objects / receipt['sha256']
            if not object_path.exists():
                os.link(captured, object_path)
            receipt['remote_path'] = 'library/objects/' + receipt['sha256']
        pending.append((relative, signature, receipt))
    result['phase']='uploading_library'
    result['staged_files']=len(pending)
    _atomic_json(Path(config['state_dir'])/'status.json',result)
    transferred = transport.put_tree(objects, 'library/objects', run)
    if transferred.get('verified') is not True:
        raise ValueError('Transport did not certify the submitted library set')
    result['uploaded_files'] += transferred.get('files', 0)
    # Namespace manifests retain deletion/link observations. They do not
    # remove any remote payload and appear only after that set verifies.
    content={row[0]:json.loads(row[1]) for row in db.execute('SELECT path,receipt FROM files')}
    content.update({row[0]:row[2] for row in pending})
    groups = {}
    for path, entry in entries.items():
        if entry['kind'] != 'file':
            continue
        # Old completed installations may reference the original latest path.
        # It is read-only under this layout; new payloads always use SHA-256.
        proof = content[path]
        remote_path = proof.get('remote_path', 'library/files/' + path)
        if remote_path == 'library/objects/' + proof['sha256']:
            prefix, relative = 'library/objects', proof['sha256']
        elif remote_path == 'library/files/' + path:
            prefix, relative = 'library/files', path
        else:
            raise ValueError('Cached library payload identity is invalid')
        proof['remote_path'] = remote_path
        groups.setdefault(prefix, {})[relative] = proof
    for prefix, expected in groups.items():
        if transport.verify_files(prefix, expected).get('verified') is not True:
            raise ValueError('Current library remote verification failed')
    if scan_library(config['library'])!=entries:
        raise ValueError('Library changed during transfer; namespace was not published')
    summary = {path:dict(**{k:v for k,v in entry.items() if k!='path'},content=content[path])
               for path,entry in entries.items()}
    namespace_hash=hashlib.sha256(_json(summary).encode()).hexdigest()
    prior_namespace=db.execute('SELECT value FROM metadata WHERE name=?',('namespace',)).fetchone()
    if pending or not prior_namespace or prior_namespace[0]!=namespace_hash:
        metadata = directory / 'library-manifest'
        _write_new(metadata/'manifest.json', _json(dict(format=FORMAT, run=run, entries=summary,
                  source_root=str(_root(config['library']['root'])),
                  source_identity=_identity(_root(config['library']['root'])),
                  external_links='recorded only', payload_layout='sha256-objects-v1', complete_transfer_set=True)).encode())
        complete = transport.put_tree(metadata, 'library/manifests/'+run, run)
        if complete.get('verified') is not True:
            raise ValueError('Library manifest remote verification failed')
        db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('library_manifest',
                   _json({'remote_path':'library/manifests/'+run,'expected':_proofs(metadata)})))
    else:
        prior=db.execute('SELECT value FROM metadata WHERE name=?',('library_manifest',)).fetchone()
        if not prior:raise ValueError('Library completion manifest reference is missing')
        prior=json.loads(prior[0])
        if transport.verify_files(prior['remote_path'],prior['expected']).get('verified') is not True:
            raise ValueError('Stored library manifest remote verification failed')
    for relative, signature, receipt in pending:
        db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?)', (relative, signature, _json(receipt)))
    db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('namespace',namespace_hash))
    db.commit()


def _sync_fdb_phase(config, db, directory, run, result, transport):
    for source, roots in _fdb_inputs(config['fdb_repository']):
        try:
            result['phase']='capturing_and_uploading_fdb'
            _atomic_json(Path(config['state_dir'])/'status.json',result)
            signature = _db_signature(source)+json.dumps(sorted(str(Path(p).absolute()) for p in roots))
            previous = db.execute('SELECT signature,generation FROM projects WHERE path=?',(source,)).fetchone()
            if previous and previous[0] == signature:
                prior=db.execute('SELECT value FROM metadata WHERE name=?',('project:'+source,)).fetchone()
                if not prior:raise ValueError('FDB remote manifest reference is missing')
                proof=json.loads(prior[0])
                if transport.verify_files(proof['remote_path'],proof['expected']).get('verified') is not True:
                    raise ValueError('Existing FDB generation remote verification failed')
                continue
            identifier = hashlib.sha256(str(Path(source).absolute()).encode()).hexdigest()[:20]
            output = directory / ('fdb-'+identifier)
            manifest = capture_fdb(source, roots, output, config.get('snapshot_timeout_seconds',120))
            # Keep every complete project version independently
            # restorable, including its exact private object subset.
            generation = run
            payload=directory/('fdb-payload-'+identifier)
            commit=directory/('fdb-commit-'+identifier)
            payload.mkdir();commit.mkdir()
            for selected in output.rglob('*'):
                if selected.is_file():
                    relative=selected.relative_to(output)
                    destination=(commit if relative.as_posix()=='manifest.json' else payload)/relative
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    os.link(selected,destination)
            remote_generation='fdb/projects/'+identifier+'/'+generation
            uploaded = transport.put_tree(payload, remote_generation, run)
            if uploaded.get('verified') is not True:
                raise ValueError('FDB generation transfer was not verified')
            committed=transport.put_tree(commit,remote_generation,run)
            if committed.get('verified') is not True:
                raise ValueError('FDB completion manifest transfer was not verified')
            # If commits occurred during the backup, the current source
            # signature is deliberately not marked as captured.
            if _db_signature(source)+json.dumps(sorted(str(Path(p).absolute()) for p in roots)) == signature:
                db.execute('INSERT OR REPLACE INTO projects VALUES (?,?,?)',(source,signature,generation))
                db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('project:'+source,
                           _json({'remote_path':remote_generation,'expected':_proofs(output)})))
                db.commit()
            result['uploaded_files'] += uploaded.get('files',0)
            result['projects'].append(dict(path=source, id=identifier, generation=generation,
                                           manifest=manifest, verified=True))
        except Exception as error:
            result['errors'].append(dict(source=source, type=type(error).__name__, message=str(error)))


def run_once(config, transport=None):
    if config.get('format') != FORMAT:
        raise ValueError('Unsupported sync configuration')
    if not config.get('enabled', False):
        return dict(format=FORMAT, status='disabled', uploaded_files=0)
    state = Path(config['state_dir']).expanduser().absolute()
    with _lock(state):
        run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
        directory = state / 'runs' / run
        directory.mkdir(parents=True, mode=0o700)
        result = dict(format=FORMAT, run=run, status='running', phase='preflight', pid=os.getpid(), uploaded_files=0,
                      projects=[], errors=[], deletions_propagated=False)
        _atomic_json(state/'status.json',result)
        transport = transport or RcloneTransport(config['transport'])
        db = _state(state / 'state.sqlite')
        try:
            binding = json.dumps(dict(library=config['library'],
                library_observed_identity=_identity(_root(config['library']['root'])),
                repository=config['fdb_repository'],
                repository_observed_identity=_identity(_root(config['fdb_repository']['root'])),
                transport={key:config.get('transport',{}).get(key) for key in
                           ('remote','root_id','config','account_permission_id')}),sort_keys=True)
            previous_binding=db.execute('SELECT value FROM metadata WHERE name=?',('binding',)).fetchone()
            if previous_binding and previous_binding[0]!=binding:
                raise ValueError('Sync source/destination changed; use a new state directory')
            db.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',('binding',binding));db.commit()
            # FDBs are independent inputs and run before the potentially large
            # intake copy. A failure in either phase cannot skip the other.
            for phase, operation in (('fdb', _sync_fdb_phase), ('library', _sync_library_phase)):
                result['phase'] = phase
                _atomic_json(state/'status.json', result)
                try:
                    operation(config, db, directory, run, result, transport)
                except Exception as error:
                    db.rollback()
                    result['errors'].append(dict(phase=phase, type=type(error).__name__, message=str(error)))
            result['status'] = 'complete' if not result['errors'] else 'partial'
            result['phase']='finished'
            return result
        except Exception as error:
            result['status']='failed'
            result['errors'].append(dict(type=type(error).__name__, message=str(error)))
            raise
        finally:
            db.close()
            _atomic_json(directory/'receipt.json', result)
            _atomic_json(state/'status.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['plan','run','status','register'])
    parser.add_argument('--config', required=True)
    parser.add_argument('--path')
    parser.add_argument('--objects-root', action='append', default=[])
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if args.operation == 'plan':
        result = plan(config)
    elif args.operation == 'status':
        path = Path(config['state_dir'])/'status.json'
        result = json.loads(path.read_text()) if path.exists() else {'status':'not_run'}
    elif args.operation == 'register':
        if not args.path:
            parser.error('register requires --path')
        source = Path(args.path).expanduser().resolve(strict=True)
        identifier = hashlib.sha256(str(source).encode()).hexdigest()[:20]
        selected = Path(config['fdb_repository']['root'])/'registrations'/(identifier+'.json')
        _write_new(selected, _json(dict(path=str(source),objects_roots=args.objects_root or
                    config['fdb_repository'].get('objects_roots',[]))).encode())
        result = {'registered':str(source),'registration':str(selected)}
    else:
        result = run_once(config)
    print(_json(result), end='')
    if result.get('status') in ('partial', 'incomplete', 'failed'):
        sys.exit(2)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(_json(dict(status='failed',type=type(error).__name__,message=str(error))),file=sys.stderr,end='')
        sys.exit(1)
