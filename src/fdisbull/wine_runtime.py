"""Prepare an offline Wine/QEMU runtime from a trusted Linux initramfs.

The base must contain Wine64, Xvfb, Python3 and x86_64-w64-mingw32-gcc.
The supplied base is preserved. No games or project files enter the runtime.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
from pathlib import PurePosixPath

# The qualification base also contains an old Python environment, tests and DOSBox
# build. Initramfs files occupy guest RAM: retaining those can starve Wine startup.
OMIT=('opt/venv','opt/tests','opt/probes','opt/dosbox-x',
      'usr/share/doc','usr/share/man','var/lib/apt/lists','var/cache/apt')


def compact_base(base, output):
    """Stream trusted gzip/newc files into a new archive; never extract on host."""
    omitted=0;retained=0
    with gzip.open(base,'rb') as source:
        while True:
            first=source.read(1)
            while first==b'\0':first=source.read(1) # conventional cpio block padding
            if not first:break
            header=first+source.read(109)
            if len(header)!=110 or header[:6]!=b'070701':
                raise ValueError('Wine base must be a gzip-compressed newc initramfs')
            fields=[int(header[6+i*8:14+i*8],16) for i in range(13)]
            mode,nlink,size,namesize=fields[1],fields[4],fields[6],fields[11]
            if not 1<=namesize<=4096 or size>1024*1024*1024:
                raise ValueError('CPIO member exceeds runtime preparation budget')
            encoded=source.read(namesize);padding=source.read(-(110+namesize)%4)
            if len(encoded)!=namesize or not encoded.endswith(b'\0'):
                raise ValueError('Truncated CPIO member name')
            name=encoded[:-1].decode().removeprefix('./')
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                raise ValueError('Non-local CPIO runtime path')
            if nlink>1 and not stat.S_ISDIR(mode):
                raise ValueError('Expand CPIO hard links before preparing the Wine runtime')
            keep=not any(name==prefix or name.startswith(prefix+'/') for prefix in OMIT)
            if keep:output.write(header+encoded+padding);retained+=size
            else:omitted+=size
            remaining=size
            while remaining:
                chunk=source.read(min(8*1024*1024,remaining))
                if not chunk:raise ValueError('Truncated CPIO runtime data')
                if keep:output.write(chunk)
                remaining-=len(chunk)
            padding=source.read(-size%4)
            if keep:output.write(padding)
    return {'retained_base_bytes':retained,'omitted_bytes':omitted,'omitted_prefixes':OMIT}


def resources():
    root = Path(__file__).with_name('wine_guest')
    return {'init':root/'init.sh', 'opt/fdisbull/agent.c':root/'agent.c',
            'opt/fdisbull/broker.py':root/'broker.py'}


def prepare(base, output):
    base = Path(base).expanduser().resolve(strict=True)
    output = Path(output).expanduser().resolve()
    records = {}
    try:
        with output.open('xb') as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=1,mtime=0) as stream:
                compaction=compact_base(base,stream)
            # Linux supports concatenated compressed newc archives. New /init replaces
            # the probe launcher, leaving the sealed base image unchanged.
            with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as stream:
                def emit(name, data, mode, inode):
                    encoded=name.encode()+b'\0'
                    fields=(inode,mode,0,0,1,0,len(data),0,0,0,0,len(encoded),0)
                    stream.write(b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)+encoded)
                    stream.write(b'\0'*(-(110+len(encoded))%4));stream.write(data)
                    stream.write(b'\0'*(-len(data)%4))
                emit('opt/fdisbull',b'',stat.S_IFDIR|0o755,1)
                for i,(name,path) in enumerate(resources().items(),2):
                    data=path.read_bytes();records[name]=hashlib.sha256(data).hexdigest()
                    emit(name,data,stat.S_IFREG|0o755,i)
                emit('TRAILER!!!',b'',0,10)
    except FileExistsError:
        raise
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    with base.open('rb') as stream:base_hash=hashlib.file_digest(stream,'sha256').hexdigest()
    with output.open('rb') as stream:output_hash=hashlib.file_digest(stream,'sha256').hexdigest()
    result={'base_sha256':base_hash,'runtime_sha256':output_hash,'resources':records,**compaction}
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-initramfs',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(prepare(args.base_initramfs,args.output),indent=2))

if __name__=='__main__':main()
