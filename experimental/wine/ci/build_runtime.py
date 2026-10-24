"""Convert this CI's trusted Docker export without extracting it onto the host.

The normal installed-package preparer supplies all production guest resources.
The temporary base, rootfs and compiled fixture are CI inputs, never packages.
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

from fdisbull.wine_runtime import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs-tar', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.base.exists() or args.output.exists():
        raise SystemExit('Refusing to overwrite a runtime input or output')
    inode = 1
    with args.base.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, compresslevel=1) as output:
        def emit(name, mode, size=0, stream=None, uid=0, gid=0, major=0, minor=0):
            nonlocal inode
            encoded = name.encode() + b'\0'
            fields = (inode, mode, uid, gid, 1, 0, size, 0, 0, major, minor, len(encoded), 0)
            output.write(b'070701' + b''.join(f'{v:08x}'.encode() for v in fields) + encoded)
            output.write(b'\0' * (-(110 + len(encoded)) % 4))
            remaining = size
            while remaining:
                chunk = stream.read(min(8 * 1024**2, remaining))
                if not chunk:
                    raise ValueError(f'Truncated runtime member: {name}')
                output.write(chunk)
                remaining -= len(chunk)
            output.write(b'\0' * (-size % 4))
            inode += 1

        with tarfile.open(args.rootfs_tar) as archive:
            for member in archive:
                name = member.name.removeprefix('./').rstrip('/')
                if not name or name == '.':
                    continue
                if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
                    raise ValueError('Non-local runtime path')
                if name in {'dev/console', 'dev/null'} or any(
                    name == prefix or name.startswith(prefix + '/')
                    for prefix in ('opt/ci', 'usr/share/doc', 'usr/share/man', 'var/lib/apt/lists', 'var/cache/apt')
                ):
                    continue
                permissions = member.mode & 0o7777
                if member.isdir():
                    emit(name, stat.S_IFDIR | permissions, uid=member.uid, gid=member.gid)
                elif member.issym():
                    data = member.linkname.encode()
                    emit(name, stat.S_IFLNK | permissions, len(data), io.BytesIO(data), member.uid, member.gid)
                elif member.isfile() or member.islnk():
                    # Resolve trusted tar hard links into independent CPIO files.
                    with archive.extractfile(member) as stream:
                        size = stream.seek(0, 2)
                        stream.seek(0)
                        emit(name, stat.S_IFREG | permissions, size, stream, member.uid, member.gid)
                elif member.ischr() or member.isblk():
                    kind = stat.S_IFCHR if member.ischr() else stat.S_IFBLK
                    emit(name, kind | permissions, uid=member.uid, gid=member.gid,
                         major=member.devmajor, minor=member.devminor)
                elif member.isfifo():
                    emit(name, stat.S_IFIFO | permissions, uid=member.uid, gid=member.gid)
                else:
                    raise ValueError(f'Unsupported runtime member: {name}')
        emit('dev/console', stat.S_IFCHR | 0o600, major=5, minor=1)
        emit('dev/null', stat.S_IFCHR | 0o666, major=1, minor=3)
        emit('TRAILER!!!', 0)
    receipt = prepare(args.base, args.output)
    with args.rootfs_tar.open('rb') as stream:
        receipt['rootfs_tar_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
