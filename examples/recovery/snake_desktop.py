"""Emit the unchanged private Snake source model for native Win64 or Linux x64.

Compile its explicit recipe in the selected native/cross environment, then seal
with udc_memory_desktop.seal_memory_desktop_shell. Execution remains separate.
"""
from pathlib import Path
import hashlib
import json
import sqlite3
import zipfile

from fdisbull.project import Project
from fdisbull.udc_memory_desktop import emit_memory_desktop_shell


def prepare(previous,output,*,target):
    previous=Path(previous).resolve();output=Path(output).absolute()
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('choose a new private desktop study outside Git')
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    package=json.loads((previous/'browser-package.json').read_text())
    if type(package.get('file')) is not str or Path(package['file']).name!=package['file']:
        raise ValueError('source capsule must be a local filename')
    archive=previous/package['file'];database=previous/'build-03/snake.fdb'
    source_hashes={'package':sha(archive),'database':sha(database)}
    if source_hashes['package']!=package['sha256']:raise ValueError('source capsule changed')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('source capsule CRC failed')
        raw=z.read('memory-shell.json');manifest=json.loads(raw)
        initial_raw=z.read('initial.json');initial=json.loads(initial_raw)
        if hashlib.sha256(initial_raw).hexdigest()!=manifest['artifacts']['initial.json']:raise ValueError('initial arena changed')
    build=json.loads((previous/'build-03/build.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=build['manifest_sha256']:raise ValueError('source manifest changed')
    if build['module_uil_sha256']!='a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720':
        raise ValueError('select the qualified Snake fixture')
    output.mkdir(parents=True,mode=0o700);copy=output/'snake-native.fdb'
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(copy) as dest:source.backup(dest)
    with Project(copy) as project:
        native=emit_memory_desktop_shell(project,build['selections'],manifest['plan'],initial,output/'native',target=target,
            cuts=manifest['source_cut_document'],regions=manifest['regions']['document'])
    with Project(copy) as project:
        assert project.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for selection in build['selections'].values():
            assert project.udl_selection_info(selection,full=True)['document']['program']==native['program']
    assert source_hashes=={'package':sha(archive),'database':sha(database)}
    result={'format':'fdisbull-snake-native-desktop-build-1','stage':'source-only','target':target,
        'original_sha256':build['original_sha256'],'module_uil_sha256':native['module_uil_sha256'],
        'udl_sha256':build['udl_sha256'],'source_hashes':source_hashes,'prior_delivery_unchanged':True,
        'database_reopened':True,'native_manifest_sha256':sha(output/'native/native-shell.json'),
        'native_execution':False,'scope':'source-identical retargeting; compilation/execution/adapters qualified separately'}
    (output/'build.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--target',required=True,choices=['windows-x64','linux-x64'])
    args=parser.parse_args();print(json.dumps(prepare(args.previous,args.output,target=args.target)))
