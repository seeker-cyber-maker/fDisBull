"""Explicit, hash-bound uploads for disposable DOS and Windows guests."""
import base64
import hashlib
from pathlib import Path


def uploads(project,directory,target,files=None):
    directory=Path(directory).expanduser().resolve(strict=True)
    names=[target] if files is None else files
    if not isinstance(names,list) or not 1<=len(names)<=1024 or any(not isinstance(n,str) for n in names) or target not in names or len(set(names))!=len(names):
        raise ValueError('files must explicitly include the target and at most 1024 unique relative assets')
    result=[];total=0;seen=set()
    for name in names:
        if not name or '\\' in name or ':' in name or '\x00' in name or Path(name).is_absolute() or '..' in Path(name).parts or Path(name).as_posix()!=name:
            raise ValueError('Asset paths must be local relative paths')
        if name.casefold() in seen:raise ValueError('Guest filenames must be unique ignoring case')
        seen.add(name.casefold());path=directory/name
        if any(p.is_symlink() for p in [path,*path.parents] if p!=directory.parent) or not path.is_file() or not path.resolve().is_relative_to(directory):
            raise ValueError('Assets must be regular files without symbolic links')
        structured_mz_target = name==target and project.meta['format'] in ('MZ', 'COM')
        if path.resolve() in (project.path,Path(str(project.path)+'-wal'),Path(str(project.path)+'-shm')) or (path.suffix.lower() in ('.fdb','.db','.sqlite','.sqlite3','.sav','.state') and not structured_mz_target):
            raise ValueError('Do not upload project databases or saved states as game assets')
        total+=path.stat().st_size
        if total>64*1024*1024:raise ValueError('Explicit guest upload exceeds 64 MiB')
        data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if name==target and digest!=project.meta['source_sha256']:raise ValueError('Executable differs from the project source hash')
        result.append(dict(path=name,sha256=digest,data_base64=base64.b64encode(data).decode()))
    return result
