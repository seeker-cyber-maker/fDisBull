#!/usr/bin/env python3
"""Create a private, verifiable SQLite FDB snapshot and external-object closure."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
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


def _hash_file(path,end,maximum):
    digest=hashlib.sha256();size=0
    with open(path,'rb') as stream:
        while True:
            _deadline(end);part=stream.read(1024*1024)
            if not part: break
            size+=len(part)
            if size>maximum: raise ValueError('FDB backup file exceeds its size bound')
            digest.update(part)
    return size,digest.hexdigest()


def capture_fdb(path, objects_roots, output_newdir, timeout_seconds):
    """Snapshot one FDB and all recursively referenced objects, without fake data.

    A missing or corrupt object leaves an incomplete directory without a
    manifest. The source connection uses SQLite online backup, including WAL.
    """
    if (isinstance(timeout_seconds,bool) or not isinstance(timeout_seconds,(int,float))
            or not 0<timeout_seconds<=86400): raise ValueError('Invalid backup timeout')
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
        snapshot=output/'project.fdb'
        source_db=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=min(timeout_seconds,1))
        dest_db=sqlite3.connect(str(snapshot),timeout=min(timeout_seconds,1))
        try:
            dest_db.set_progress_handler(lambda: int(time.monotonic()>=end),10000)
            page_size=source_db.execute('PRAGMA page_size').fetchone()[0]
            def progress(status,remaining,total):
                _deadline(end)
                if total*page_size>MAX_DATABASE: raise ValueError('FDB snapshot exceeds size bound')
            source_db.backup(dest_db,pages=256,progress=progress,sleep=0.01)
            _deadline(end)
            if dest_db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                raise ValueError('FDB snapshot integrity check failed')
            refs={};pending=[];scanned_text=set();total_objects=0
            def collect(ref):
                digest=ref['sha256'];old=refs.get(digest)
                if old is not None and old['size']!=ref['size']:
                    raise ValueError('Conflicting size for external object hash')
                if old is None:
                    refs[digest]={'size':ref['size'],'encodings':set()}
                if ref['encoding'] not in refs[digest]['encodings']:
                    refs[digest]['encodings'].add(ref['encoding']);pending.append((digest,ref['encoding']))
            tables=dest_db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            for (name,) in tables:
                _deadline(end)
                if not isinstance(name,str) or '\0' in name: raise ValueError('Invalid SQLite table name')
                quoted='"'+name.replace('"','""')+'"'
                for row in dest_db.execute('SELECT * FROM '+quoted):
                    for value in row: _references(value,collect,end)
            rootfds=None
            while pending:
                _deadline(end);digest,encoding=pending.pop();record=refs[digest]
                existing=output/'objects'/digest
                if not existing.exists():
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
                    try: text=existing.read_bytes().decode('utf-8')
                    except UnicodeDecodeError as error: raise ValueError('External text object is not UTF-8') from error
                    _references(text,collect,end)
            dest_db.close();dest_db=None
            size,digest=_hash_file(snapshot,end,MAX_DATABASE)
            with open(snapshot,'rb') as stream: os.fsync(stream.fileno())
            os.fsync(objectsfd)
            manifest={'format':FORMAT,'database':{'path':'project.fdb','size':size,'sha256':digest},
                      'objects':[{'path':'objects/'+key,'size':refs[key]['size'],'sha256':key,
                                  'encodings':sorted(refs[key]['encodings'])} for key in sorted(refs)],
                      'objects_total_bytes':total_objects,
                      'scope':'SQLite snapshot and referenced target objects only; other external files, runtimes and backend dependencies are not inventoried.'}
            encoded=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode('utf-8')
            _deadline(end)
            fd=os.open('.manifest.partial',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=outfd)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(encoded);stream.flush();os.fsync(stream.fileno())
                _deadline(end)
                os.rename('.manifest.partial','manifest.json',src_dir_fd=outfd,dst_dir_fd=outfd)
                os.fsync(outfd)
            except BaseException:
                # A manifest that could not be durably published is not a completion receipt.
                for name in ('.manifest.partial','manifest.json'):
                    try: os.unlink(name,dir_fd=outfd)
                    except FileNotFoundError: pass
                raise
            return manifest
        finally:
            source_db.close()
            if dest_db is not None: dest_db.close()
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
