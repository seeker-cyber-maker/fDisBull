"""Repack our trusted runtime export as a disposable Linux initramfs.

This does not extract the image onto the host. Only DOSBox build/source files
are omitted; its tested executable and all runtime libraries are retained.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs-tar',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():
        raise SystemExit('Output already exists')
    own=Path(__file__).resolve().parent
    replacements={
        'init':own/'probes/tcg-init.sh',
        'opt/probes/probe.sh':own/'probes/probe.sh',
        'opt/probes/controller64.c':own/'probes/controller64.c',
    }
    records=[]
    inode=1
    with args.output.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as output:
        def emit(name,mode,size=0,stream=None,uid=0,gid=0,rmajor=0,rminor=0):
            nonlocal inode
            encoded=name.encode()+b'\0'
            fields=(inode,mode,uid,gid,1,0,size,0,0,rmajor,rminor,len(encoded),0)
            header=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)
            assert len(header)==110
            output.write(header+encoded)
            output.write(b'\0'*((-(110+len(encoded)))%4))
            digest=hashlib.sha256()
            remaining=size
            while remaining:
                chunk=stream.read(min(8*1024**2,remaining))
                if not chunk:raise ValueError(f'Short image member: {name}')
                output.write(chunk);digest.update(chunk);remaining-=len(chunk)
            output.write(b'\0'*((-size)%4))
            records.append({'name':name,'size':size,'sha256':digest.hexdigest()})
            inode+=1

        with tarfile.open(args.rootfs_tar) as source:
            for member in source:
                name=member.name.removeprefix('./').rstrip('/')
                if not name or name=='.':continue
                if name.startswith('/') or '..' in PurePosixPath(name).parts:
                    raise ValueError('Non-local image path')
                if name in replacements or name in {'dev/console','dev/null'}:continue
                if name.startswith('opt/dosbox-x/') and name not in {
                    'opt/dosbox-x/src','opt/dosbox-x/src/dosbox-x'}:continue
                permissions=member.mode & 0o7777
                if member.isdir():emit(name,stat.S_IFDIR|permissions,uid=member.uid,gid=member.gid)
                elif member.issym():
                    data=member.linkname.encode()
                    emit(name,stat.S_IFLNK|permissions,len(data),io.BytesIO(data),member.uid,member.gid)
                elif member.isfile() or member.islnk():
                    stream=source.extractfile(member)
                    size=stream.seek(0,2);stream.seek(0)
                    emit(name,stat.S_IFREG|permissions,size,stream,member.uid,member.gid)
                elif member.ischr() or member.isblk():
                    kind=stat.S_IFCHR if member.ischr() else stat.S_IFBLK
                    emit(name,kind|permissions,uid=member.uid,gid=member.gid,rmajor=member.devmajor,rminor=member.devminor)
                elif member.isfifo():emit(name,stat.S_IFIFO|permissions,uid=member.uid,gid=member.gid)
                else:raise ValueError(f'Unsupported image entry: {name}')
        for name,path in replacements.items():
            with path.open('rb') as stream:
                emit(name,stat.S_IFREG|0o755,path.stat().st_size,stream)
        emit('dev/console',stat.S_IFCHR|0o600,rmajor=5,rminor=1)
        emit('dev/null',stat.S_IFCHR|0o666,rmajor=1,rminor=3)
        emit('TRAILER!!!',0)
    receipt={'rootfs_tar':str(args.rootfs_tar),'initramfs':str(args.output),
             'omitted':'DOSBox sources/build files, preserving opt/dosbox-x/src/dosbox-x',
             'entries':records}
    args.output.with_suffix(args.output.suffix+'.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(f'Created {args.output} with {len(records)} entries')


if __name__=='__main__':main()
