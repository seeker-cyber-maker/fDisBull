#!/usr/bin/env python3
"""Archive pinned upstream DOSBox source plus the verified patched-file overlay."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile
import tomllib


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def build(source,manifest,source_commit,output,version=None):
    if version is None:
        version=tomllib.loads((Path(__file__).resolve().parents[1]/'pyproject.toml').read_text())['project']['version']
    source=Path(source).resolve();manifest=json.loads(Path(manifest).read_text());output=Path(output)
    baseline=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if baseline!=manifest['baseline_commit']:raise ValueError('Wrong upstream baseline')
    paths=[]
    for item in manifest['source_files']:
        rel=PurePosixPath(item['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid source path')
        path=source/rel
        if path.is_symlink() or not path.is_file() or source not in path.resolve().parents:raise ValueError('Source must be a regular in-tree file')
        if digest(path)!=item['sha256']:raise ValueError('Patched source hash mismatch: '+str(rel))
        paths.append((path,rel))
    if output.exists():raise ValueError('Companion output already exists')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        upstream=root/'upstream.tar.xz'
        # git archive reads only tracked bytes at the pinned baseline, including
        # the upstream license; no build products or private working files enter.
        with upstream.open('wb') as raw,lzma.LZMAFile(raw,'w') as compressed:
            process=subprocess.Popen(['git','-C',str(source),'archive','--format=tar',baseline],stdout=subprocess.PIPE)
            try:
                for block in iter(lambda:process.stdout.read(1024*1024),b''):compressed.write(block)
                if process.wait():raise ValueError('Upstream source archive failed')
            finally:process.stdout.close()
        overlay=root/'overlay.tar.gz'
        with tarfile.open(overlay,'w:gz') as archive:
            for path,relative in paths:
                info=archive.gettarinfo(str(path),'overlay/'+relative.as_posix());info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
                with path.open('rb') as stream:archive.addfile(info,stream)
        (root/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (root/'README.txt').write_text(
            f'DOSBox-X corresponding source for fDisBull {version}\n\n'
            f'fDisBull commit: {source_commit}\nUpstream: https://github.com/joncampbell123/dosbox-x\n'
            f'Pinned upstream commit: {baseline}\nPatch SHA-256: {manifest["patch_sha256"]}\n'
            f'All {len(paths)} patched source files matched source-manifest.json before archiving.\n'
            'Extract upstream.tar.xz, then overlay the contents of overlay/ from overlay.tar.gz.\n'
            'The upstream source includes COPYING and other component notices.\n'
            './autogen.sh\n./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent '
            '--disable-avcodec --disable-libslirp --disable-libfluidsynth\nmake -j2\n'
            'Requires compiler/autotools, SDL2/SDL2_net, ncurses, PNG, zlib and FreeType development packages.\n'
            'Source identity is verified; byte-reproducible binaries are not claimed. No user games, states or databases are included.\n')
        (root/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(root.iterdir())))
        with tarfile.open(output,'w') as archive:
            for path in sorted(root.iterdir()):archive.add(path,arcname='source-companion/'+path.name,recursive=False)
    return {'source_commit':source_commit,'upstream_commit':baseline,'verified_source_files':len(paths),'sha256':digest(output)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','manifest','source-commit','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();print(json.dumps(build(args.source,args.manifest,args.source_commit,args.output),indent=2))
