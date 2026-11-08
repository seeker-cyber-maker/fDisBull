"""Bounded read-only input snapshots for discovery. Never execute/extract members."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile
import io
import os
import stat


def snapshot_inputs(root, *, max_files, max_file_bytes, max_total_bytes):
    root=Path(root)
    if root.is_symlink() or not root.exists():raise ValueError('regular input file or extracted directory required')
    root=root.resolve(); paths=[]; skipped=[]; limited=False
    if root.is_dir():
        for directory,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=sorted(d for d in dirs if d!='.git' and not (Path(directory)/d).is_symlink())
            for name in sorted(files):
                p=Path(directory)/name
                if p.is_symlink():
                    skipped.append({'path':str(p.relative_to(root)),'reason':'symlink'});continue
                if not stat.S_ISREG(p.stat().st_mode):
                    skipped.append({'path':str(p.relative_to(root)),'reason':'not a regular file'});continue
                if len(paths)>=max_files:limited=True;break
                paths.append(p)
            if limited:break
    elif stat.S_ISREG(root.stat().st_mode):paths=[root]
    else:raise ValueError('regular file or directory required')
    snapshots={};manifest=[];originals=[];total=0;member_work=0
    for p in sorted(paths):
        rel=p.relative_to(root).as_posix() if root.is_dir() else p.name
        size=p.stat().st_size
        if size>max_file_bytes or total+size>max_total_bytes:
            skipped.append({'path':rel,'reason':'byte budget','size':size});continue
        with p.open('rb') as stream:data=stream.read(max_file_bytes+1)
        if len(data)!=size:raise ValueError('source changed during read: '+rel)
        total+=size;digest=sha256(data).hexdigest();originals.append((p,size,digest))
        if data.startswith(b'PK\x03\x04'):
            try:z=ZipFile(io.BytesIO(data))
            except BadZipFile as exc:raise ValueError('invalid ZIP') from exc
            entries=z.infolist()
            if len(entries)>max_files:raise ValueError('ZIP member count exceeds budget')
            names=set()
            for entry in entries:
                name=entry.filename;parts=PurePosixPath(name).parts
                if name in names or not name or '\\' in name or name.startswith('/') or '..' in parts or ':' in name or '\x00' in name:
                    raise ValueError('unsafe or duplicate ZIP member name')
                names.add(name)
                mode=entry.external_attr>>16
                if stat.S_ISLNK(mode) or entry.flag_bits&1:raise ValueError('encrypted/symlink ZIP member refused')
            # Single archive layer. Only content-identified console ROMs are
            # admitted; native installers/AGI resources use existing extraction.
            for entry in sorted(entries,key=lambda e:e.filename):
                if entry.is_dir():continue
                member_work+=1
                if member_work>max_files:limited=True;break
                name=rel+'!'+entry.filename
                if entry.file_size>max_file_bytes or total+entry.file_size>max_total_bytes:
                    skipped.append({'path':name,'reason':'expanded byte budget'});continue
                try:
                    with z.open(entry) as stream:member=stream.read(max_file_bytes+1)
                except (BadZipFile,RuntimeError,NotImplementedError) as exc:raise ValueError('ZIP member decode refused') from exc
                if len(member)!=entry.file_size:raise ValueError('ZIP member size mismatch')
                total+=len(member)
                from .rom_nes import parse_nes
                from .rom_snes import parse_snes
                from .rom_sega import parse_genesis
                if not (parse_nes(member) or parse_genesis(member) or parse_snes(member)):
                    skipped.append({'path':name,'reason':'archive fast path admits only content-identified console ROMs'});continue
                snapshots[name]=member
                manifest.append({'path':name,'bytes':len(member),'sha256':sha256(member).hexdigest(),
                                 'container_sha256':digest,'member':entry.filename})
            z.close()
        else:
            snapshots[rel]=data;manifest.append({'path':rel,'bytes':size,'sha256':digest})
    return root,snapshots,manifest,originals,skipped,limited,total,len(paths)


def verify_snapshots(originals):
    for p,size,digest in originals:
        if p.is_symlink() or not p.is_file() or p.stat().st_size!=size:raise ValueError('source changed during scan')
        with p.open('rb') as stream:data=stream.read(size+1)
        if len(data)!=size or sha256(data).hexdigest()!=digest:raise ValueError('source changed during scan')
