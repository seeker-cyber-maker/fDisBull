"""DOS namespace aliases; executable eligibility comes from the parsed image."""
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile


def guest_name(filename, source_sha256):
    if re.fullmatch(r'[A-Za-z0-9_-]{1,8}\.(?:exe|com)', filename, re.IGNORECASE):
        return filename
    return 'FB' + source_sha256[:6].upper() + '.EXE'


class LaunchAlias:
    """Own one disposable copy, never rename or overwrite an input file."""
    def __init__(self, directory, name, data):
        self.path = Path(directory)/name
        self.sha256 = hashlib.sha256(data).hexdigest()
        if any(p.name.casefold() == name.casefold() for p in Path(directory).iterdir()):
            raise ValueError('DOS launch alias collides with an existing file: ' + name)
        # Exclusive creation also rejects a same-name race or dangling symlink.
        with self.path.open('xb') as stream:
            stat = os.fstat(stream.fileno())
            self.identity = (stat.st_dev, stat.st_ino)
            try:
                os.fchmod(stream.fileno(),0o600)
                stream.write(data)
                stream.flush()
            except BaseException:
                self.close() # Preserve a changed/replaced file, including partial output.
                raise

    def _unchanged(self,path):
        info=path.lstat()
        return (stat.S_ISREG(info.st_mode) and (info.st_dev,info.st_ino)==self.identity and
                info.st_size<=64*1024*1024 and hashlib.sha256(path.read_bytes()).hexdigest()==self.sha256)

    def close(self):
        try:
            unchanged=self._unchanged(self.path)
        except FileNotFoundError:
            return dict(status='absent', path=str(self.path))
        except OSError as error:
            return dict(status='retained_changed',path=str(self.path),error=str(error))
        # Preserve an externally replaced or guest-modified file as evidence.
        if not unchanged:
            return dict(status='retained_changed', path=str(self.path))
        # Atomically take the pathname out of circulation, then verify the moved
        # inode. A replacement between the first check and rename is preserved.
        try:directory=Path(tempfile.mkdtemp(prefix='.fdisbull-alias-',dir=self.path.parent))
        except OSError as error:
            return dict(status='retained_changed',path=str(self.path),error=str(error))
        parked=directory/self.path.name
        try:self.path.rename(parked)
        except FileNotFoundError:
            directory.rmdir()
            return dict(status='absent',path=str(self.path))
        except OSError as error:
            directory.rmdir()
            return dict(status='retained_changed',path=str(self.path),error=str(error))
        try:
            if self._unchanged(parked):
                parked.unlink();directory.rmdir()
                return dict(status='removed',path=str(self.path))
            # Restore without overwriting a newly created file at the old name.
            os.link(parked,self.path,follow_symlinks=False)
            parked.unlink();directory.rmdir()
            return dict(status='retained_changed',path=str(self.path))
        except OSError as error:
            return dict(status='retained_changed',path=str(parked),original_alias=str(self.path),error=str(error))
