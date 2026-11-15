#!/usr/bin/env python3
"""Create a private, verifiable SQLite FDB snapshot and external-object closure."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import stat
import time

PREFIX='fdisbull-external-object-1:'
JSON_KEY='$fdisbull_external_object_1'
FORMAT='fdisbull-private-backup-1'
MAX_DATABASE=2*1024**3
MAX_OBJECT=128*1024**2
MAX_OBJECTS_TOTAL=1024**3


def _deadline(end):
    if time.monotonic() >= end:
        raise TimeoutError('FDB backup deadline expired')


def _directory(path):
    """Open an existing directory with no symlink traversal."""
    path=Path(path).expanduser().absolute()
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in ('.','..'): raise ValueError('Unsafe directory component')
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        return fd
    except BaseException:
        os.close(fd);raise


def _identity(ref):
    if (not isinstance(ref,dict) or set(ref)!={'size','sha256','encoding'}
            or type(ref['size']) is not int or not 0<=ref['size']<=MAX_OBJECT
            or not isinstance(ref['sha256'],str) or len(ref['sha256'])!=64
            or any(c not in '0123456789abcdef' for c in ref['sha256'])
            or ref['encoding'] not in ('bytes','text')):
        raise ValueError('Invalid external object identity')
    return ref


def _references(value, collect, end):
    """Recognize nested references in structured JSON and referenced text."""
    stack=[value];nodes=0
    while stack:
        _deadline(end);current=stack.pop();nodes+=1
        if nodes>1_000_000: raise ValueError('External reference structure exceeds bound')
        if isinstance(current,bytes):
            if not current.startswith((PREFIX.encode(),b'{',b'[')): continue
            try: current=current.decode('utf-8')
            except UnicodeDecodeError: continue
        if isinstance(current,str):
            if current.startswith(PREFIX):
                try: ref=json.loads(current[len(PREFIX):])
                except (ValueError,RecursionError) as error: raise ValueError('Malformed external object reference') from error
                collect(_identity(ref));continue
            if not current.startswith(('{','[')): continue
            try: current=json.loads(current)
            except (ValueError,RecursionError) as error:
                if JSON_KEY in current: raise ValueError('Malformed external object envelope') from error
                continue
        if isinstance(current,dict):
            if JSON_KEY in current: collect(_identity(current[JSON_KEY]))
            stack.extend(v for k,v in current.items() if k!=JSON_KEY)
        elif isinstance(current,list): stack.extend(current)


def source_identity(path):
    """Keep the original project name recoverable from an opaque generation."""
    source=Path(path).expanduser().absolute()
    return {'path':str(source),'name':source.name,
            'project_id':hashlib.sha256(str(source).encode()).hexdigest()[:20]}


def _same_inode(first, second):
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _require_directory(path, descriptor):
    current = _directory(path)
    try:
        if not _same_inode(os.fstat(current), os.fstat(descriptor)):
            raise ValueError('Backup directory identity changed')
    finally:
        os.close(current)


def _sqlite_backup(source, staging, sourcefd, snapshotfd, referencesfd, end, source_parentfd):
    """Use a fresh, site-disabled child with no SQLite descriptor cache/threads."""
    _deadline(end)
    helper = Path(__file__).resolve().with_name('fdb_backup_sqlite.py')
    command = [sys.executable, '-I', '-S', '-B', str(helper),
               '--source', str(source), '--snapshot', str(staging/'snapshot.sqlite'),
               '--source-fd', str(sourcefd), '--source-parent-fd', str(source_parentfd),
               '--snapshot-fd', str(snapshotfd),
               '--references-fd', str(referencesfd), '--deadline', str(end),
               '--max-database', str(MAX_DATABASE)]
    for operation in ('backup', 'scan'):
        try:
            result = subprocess.run(command + ['--operation', operation], pass_fds=(sourcefd, snapshotfd, referencesfd, source_parentfd),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=max(.001, end-time.monotonic()), check=False)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError('FDB SQLite worker deadline expired') from error
        if len(result.stdout) > 8192 or len(result.stderr) > 8192:
            raise ValueError('Invalid SQLite worker response')
        try:
            reply = json.loads(result.stdout)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError('SQLite worker failed without a completion receipt') from error
        if result.returncode or reply.get('status') != 'completed':
            if reply.get('error_type') == 'TimeoutError':
                raise TimeoutError('FDB SQLite worker deadline expired')
            raise ValueError('SQLite worker refused: ' + str(reply.get('error', 'unknown failure')))
        expected = {'source': list(_inode(os.fstat(sourcefd))),
                    'snapshot': list(_inode(os.fstat(snapshotfd)))}
        if operation == 'scan':
            expected.pop('source')
        if (reply.get('format') != 'fdisbull-private-sqlite-backup-1'
                or reply.get('bound_inodes') != expected):
            raise ValueError('SQLite worker database identity receipt differs')

def _inode(value):
    return value.st_dev, value.st_ino


def _require_name(parentfd, name, descriptor):
    current = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parentfd)
    try:
        if (not stat.S_ISREG(os.fstat(current).st_mode)
                or not _same_inode(os.fstat(current), os.fstat(descriptor))):
            raise ValueError('Published backup file identity changed')
    finally:
        os.close(current)


def _publish(source_parent, source_name, destination_parent, destination_name,
             descriptor, size, digest, end, maximum):
    """Never replace a destination; bind the published inode and its bytes."""
    os.link(source_name, destination_name, src_dir_fd=source_parent,
            dst_dir_fd=destination_parent, follow_symlinks=False)
    published = os.open(destination_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=destination_parent)
    try:
        if (not stat.S_ISREG(os.fstat(published).st_mode)
                or not _same_inode(os.fstat(published), os.fstat(descriptor))):
            raise ValueError('Published backup file identity changed')
        actual_size, actual_digest = _hash_descriptor(published, end, maximum)
        if (actual_size, actual_digest) != (size, digest):
            raise ValueError('Published backup file bytes changed')
    finally:
        os.close(published)


def _hash_descriptor(descriptor, end, maximum):
    digest = hashlib.sha256(); size = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        _deadline(end)
        part = os.read(descriptor, 1024 * 1024)
        if not part:
            return size, digest.hexdigest()
        size += len(part)
        if size > maximum:
            raise ValueError('FDB backup file exceeds its size bound')
        digest.update(part)


def capture_fdb(path, objects_roots, output_newdir, timeout_seconds, *, expected_source_identity=None):
    """Snapshot one FDB and all recursively referenced objects, without fake data.

    A missing or corrupt object leaves an incomplete directory without a
    manifest. The source connection uses SQLite online backup, including WAL.
    Writable SQLite staging is private and disk-backed; publication into the
    pinned output directory is exclusive. Failed staging is retained rather
    than deleting names that may have been replaced by another operation.
    Callers with an earlier admission may bind source and parent inode identity.
    Successful private stages are retained; hard-linked payloads are not copied.
    """
    if (isinstance(timeout_seconds,bool) or not isinstance(timeout_seconds,(int,float))
            or not 0<timeout_seconds<=86400): raise ValueError('Invalid backup timeout')
    identity_fields={'device','inode','parent_device','parent_inode'}
    if expected_source_identity is not None and (
            not isinstance(expected_source_identity,dict)
            or set(expected_source_identity)!=identity_fields
            or any(type(value) is not int or value<0 for value in expected_source_identity.values())):
        raise ValueError('Invalid admitted source identity')
    end=time.monotonic()+timeout_seconds
    source=Path(path).expanduser().absolute(); output=Path(output_newdir).expanduser().absolute()
    if not isinstance(objects_roots,list):
        raise ValueError('Object roots must be a list')
    roots=[Path(root).expanduser().absolute() for root in objects_roots]
    if source.is_symlink() or not source.is_file(): raise ValueError('FDB must be an existing regular file')
    paths=[source.parent,output.parent]
    descriptors=[]
    try:
        for directory in paths:
            descriptors.append(_directory(directory))
            for parent in (directory,*directory.parents):
                if (parent/'.git').exists() or (parent/'.git').is_symlink():
                    raise ValueError('Private backup paths must be outside Git')
        for root in [source.parent,*roots]:
            if output == root or root in output.parents:
                raise ValueError('Backup output cannot be inside source or object stores')
        for root in roots:
            if any(parent.is_symlink() for parent in (root,*root.parents)):
                raise ValueError('Object store paths cannot contain symlinks')
        os.mkdir(output.name,0o700,dir_fd=descriptors[-1])
        outfd=_directory(output); descriptors.append(outfd)
        os.mkdir('objects',0o700,dir_fd=outfd)
        objectsfd=os.open('objects',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=outfd)
        descriptors.append(objectsfd)
        sourcefd=os.open(source.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=descriptors[0])
        descriptors.append(sourcefd)
        if not stat.S_ISREG(os.fstat(sourcefd).st_mode):
            raise ValueError('FDB source is not a regular file')
        source_stat=os.fstat(sourcefd); parent_stat=os.fstat(descriptors[0])
        captured_identity={'device':source_stat.st_dev,'inode':source_stat.st_ino,
                           'parent_device':parent_stat.st_dev,'parent_inode':parent_stat.st_ino}
        if expected_source_identity is not None and captured_identity!=expected_source_identity:
            raise ValueError('Admitted source identity changed')
        # SQLite writes only in a new private sibling, never at a mutable public
        # snapshot pathname. Failed staging is retained for explicit recovery.
        staging_name='.fdb-stage-'+secrets.token_hex(16)
        parentfd=descriptors[1]
        os.mkdir(staging_name,0o700,dir_fd=parentfd)
        stagingfd=os.open(staging_name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parentfd)
        descriptors.append(stagingfd)
        staging=output.parent/staging_name
        _require_directory(staging,stagingfd)
        snapshotfd=os.open('snapshot.sqlite',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=stagingfd)
        descriptors.append(snapshotfd)
        _require_directory(source.parent,descriptors[0])
        referencesfd=os.open('references.jsonl',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=stagingfd)
        descriptors.append(referencesfd)
        _sqlite_backup(source,staging,sourcefd,snapshotfd,referencesfd,end,descriptors[0])
        refs={};pending=[];scanned_text=set();total_objects=0
        def collect(ref):
            digest=ref['sha256'];old=refs.get(digest)
            if old is not None and old['size']!=ref['size']:
                raise ValueError('Conflicting size for external object hash')
            if old is None:
                refs[digest]={'size':ref['size'],'encodings':set()}
            if ref['encoding'] not in refs[digest]['encodings']:
                refs[digest]['encodings'].add(ref['encoding']);pending.append((digest,ref['encoding']))
        os.lseek(referencesfd,0,os.SEEK_SET)
        with os.fdopen(os.dup(referencesfd),'rb') as records:
            while True:
                _deadline(end);line=records.readline(512)
                if not line:break
                if not line.endswith(b'\n'):raise ValueError('Invalid SQLite reference record')
                collect(_identity(json.loads(line)))
        rootfds=None
        while pending:
            _deadline(end);digest,encoding=pending.pop();record=refs[digest]
            try:
                existing=os.stat(digest,dir_fd=objectsfd,follow_symlinks=False)
                if not stat.S_ISREG(existing.st_mode):
                    raise ValueError('Snapshot object is not a regular file')
            except FileNotFoundError:
                existing=None
            if existing is None:
                if rootfds is None:
                    rootfds=[]
                    for root in roots:
                        for parent in (root,*root.parents):
                            if (parent/'.git').exists() or (parent/'.git').is_symlink():
                                raise ValueError('Private object stores must be outside Git')
                        try: rootfd=_directory(root)
                        except FileNotFoundError: continue
                        descriptors.append(rootfd);rootfds.append(rootfd)
                opened=None
                for rootfd in rootfds:
                    try: opened=os.open(digest,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=rootfd)
                    except FileNotFoundError: continue
                    break
                if opened is None: raise ValueError('External object missing: '+digest)
                try:
                    if not stat.S_ISREG(os.fstat(opened).st_mode): raise ValueError('External object is not a regular file')
                    out=os.open(digest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=objectsfd)
                    try:
                        actual=0;hasher=hashlib.sha256()
                        while True:
                            _deadline(end);chunk=os.read(opened,1024*1024)
                            if not chunk: break
                            actual+=len(chunk)
                            if actual>record['size'] or total_objects+actual>MAX_OBJECTS_TOTAL:
                                raise ValueError('External object exceeds declared or aggregate bound')
                            hasher.update(chunk);view=memoryview(chunk)
                            while view:
                                count=os.write(out,view)
                                if count<=0: raise OSError('Object write made no progress')
                                view=view[count:]
                        if actual!=record['size'] or hasher.hexdigest()!=digest:
                            raise ValueError('External object size or SHA-256 differs: '+digest)
                        os.fsync(out);total_objects+=actual
                    finally: os.close(out)
                finally: os.close(opened)
            if encoding=='text' and digest not in scanned_text:
                scanned_text.add(digest)
                objectfd=os.open(digest,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=objectsfd)
                try:
                    size,actual_digest=_hash_descriptor(objectfd,end,MAX_OBJECT)
                    if size!=record['size'] or actual_digest!=digest:
                        raise ValueError('Snapshot text object differs from its identity')
                    os.lseek(objectfd,0,os.SEEK_SET)
                    chunks=[]
                    while True:
                        _deadline(end); chunk=os.read(objectfd,1024*1024)
                        if not chunk: break
                        chunks.append(chunk)
                    text=b''.join(chunks).decode('utf-8')
                except UnicodeDecodeError as error: raise ValueError('External text object is not UTF-8') from error
                finally: os.close(objectfd)
                _references(text,collect,end)
        size,digest=_hash_descriptor(snapshotfd,end,MAX_DATABASE)
        for key,record in refs.items():
            objectfd=os.open(key,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=objectsfd)
            try:
                object_size,object_digest=_hash_descriptor(objectfd,end,MAX_OBJECT)
                if object_size!=record['size'] or object_digest!=key:
                    raise ValueError('Snapshot object differs from its identity')
            finally:
                os.close(objectfd)
        _require_directory(source.parent,descriptors[0])
        _require_directory(output.parent,parentfd)
        _require_directory(output,outfd)
        _require_name(descriptors[0],source.name,sourcefd)
        _publish(stagingfd,'snapshot.sqlite',outfd,'project.fdb',snapshotfd,size,digest,end,MAX_DATABASE)
        os.fsync(snapshotfd)
        os.fsync(objectsfd)
        manifest={'format':FORMAT,'source':source_identity(source),'database':{'path':'project.fdb','size':size,'sha256':digest},
                  'objects':[{'path':'objects/'+key,'size':refs[key]['size'],'sha256':key,
                              'encodings':sorted(refs[key]['encodings'])} for key in sorted(refs)],
                  'objects_total_bytes':total_objects,
                  'scope':'SQLite snapshot and referenced target objects only; other external files, runtimes and backend dependencies are not inventoried.'}
        encoded=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode('utf-8')
        _deadline(end)
        fd=os.open('.manifest.partial',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=outfd)
        descriptors.append(fd)
        view=memoryview(encoded)
        while view:
            _deadline(end);count=os.write(fd,view)
            if count<=0:raise OSError('Manifest write made no progress')
            view=view[count:]
        os.fsync(fd)
        _require_directory(output,outfd)
        _publish(outfd,'.manifest.partial',outfd,'manifest.json',fd,len(encoded),
                 hashlib.sha256(encoded).hexdigest(),end,len(encoded))
        os.fsync(outfd)
        _require_directory(output,outfd)
        # Retain private staging and partial names. Successful DB/manifest links
        # share their inodes; there is no conditional pathname deletion race.
        return manifest
    finally:
        for fd in reversed(descriptors): os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path');parser.add_argument('output_newdir')
    parser.add_argument('--objects-root',action='append',default=[])
    parser.add_argument('--timeout-seconds',type=float,default=600)
    args=parser.parse_args()
    print(json.dumps(capture_fdb(args.path,args.objects_root,args.output_newdir,args.timeout_seconds),sort_keys=True))


if __name__=='__main__': main()
