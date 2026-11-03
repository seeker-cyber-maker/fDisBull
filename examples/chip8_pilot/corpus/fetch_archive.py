"""Explicit, pinned CC0 archive fetch into a private folder outside Git.

Requires network access, and never sends files to a remote registry.
No game binaries are stored in the fDisBull repository source branch.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import urllib.request

HERE=Path(__file__).resolve().parent

def verify(raw, entry):
    size=len(raw)
    sha=hashlib.sha256(raw).hexdigest()
    blob=hashlib.sha1(b'blob '+str(size).encode()+b'\0'+raw).hexdigest()
    if size!=entry['size'] or sha!=entry['sha256'] or blob!=entry['git_blob_sha']:
        raise ValueError('source identity mismatch: '+entry['key'])

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dest',required=True,type=Path,help='Existing private folder outside Git checkout')
    a=ap.parse_args(argv)
    dest=a.dest.resolve()
    if not dest.is_dir():ap.error('destination folder must already exist')
    if any((p/'.git').is_file() or (p/'.git'/'HEAD').is_file() for p in dest.parents):
        ap.error('no ROMs inside a Git checkout')
    manifest=json.loads((HERE/'manifest.json').read_text())
    for entry in manifest['programs']:
        path=dest/(entry['key']+'.ch8')
        if path.exists():
            verify(path.read_bytes(),entry)
            print('existing/verified',path.name)
            continue
        url=f"https://raw.githubusercontent.com/JohnEarnest/chip8Archive/{manifest['source_commit']}/roms/{entry['key']}.ch8"
        with urllib.request.urlopen(url, timeout=20) as response:
            raw=response.read(65537)
        verify(raw,entry)
        with path.open('xb') as out:out.write(raw)
        print('fetched/verified',path.name)

if __name__=='__main__':main()