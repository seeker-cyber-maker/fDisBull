"""Retarget the qualified private Snake capsule to native macOS ARM64.

Keeps the original project/delivery read-only. The native compiler consumes the
same source model, cuts, region contracts and input/drawing plan after resolving
all immutable endpoints again in a private project copy.
"""
from pathlib import Path
import hashlib
import json
import sqlite3
import zipfile

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull.udc_memory_macos import build_memory_macos_shell


def prepare(previous,output,*,with_app=True):
    previous=Path(previous).resolve();output=Path(output).absolute()
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('choose a new private native study outside Git')
    package=json.loads((previous/'browser-package.json').read_text())
    if type(package.get('file')) is not str or Path(package['file']).name!=package['file']:
        raise ValueError('source capsule must be a local package filename')
    archive=previous/package['file'];source_db=previous/'build-03/snake.fdb'
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    before={'package':sha(archive),'database':sha(source_db)}
    if before['package']!=package['sha256']:raise ValueError('source browser capsule changed')
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:raise ValueError('source browser capsule failed CRC')
        raw=zipped.read('memory-shell.json');manifest=json.loads(raw)
        initial_raw=zipped.read('initial.json')
        if hashlib.sha256(initial_raw).hexdigest()!=manifest['artifacts']['initial.json']:
            raise ValueError('source initial arena changed')
        initial=json.loads(initial_raw)
    build=json.loads((previous/'build-03/build.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=build['manifest_sha256']:raise ValueError('source manifest changed')
    if digest(manifest['program'])!=build['module_uil_sha256']:raise ValueError('source UIL changed')
    if build['module_uil_sha256']!='a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720':
        raise ValueError('select the qualified Snake fixture')
    output.mkdir(parents=True,mode=0o700)
    database=output/'snake-native.fdb'
    with sqlite3.connect(source_db.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(database) as target:
        source.backup(target)
    with Project(database) as project:
        native=build_memory_macos_shell(project,build['selections'],manifest['plan'],initial,output/'native',
            cuts=manifest['source_cut_document'],regions=manifest['regions']['document'],with_app=with_app)
    with Project(database) as project:
        assert project.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for selection in build['selections'].values():
            assert project.udl_selection_info(selection,full=True)['document']['program']==manifest['program']
    assert sha(archive)==before['package'] and sha(source_db)==before['database']
    result={'format':'fdisbull-snake-native-macos-build-1','original_sha256':build['original_sha256'],
        'module_uil_sha256':native['module_uil_sha256'],'udl_sha256':build['udl_sha256'],
        'source_package_sha256':before['package'],'source_database_sha256':before['database'],
        'source_unchanged':True,'database':str(database),'database_reopened':True,'native':str(output/'native'),
        'native_manifest_sha256':sha(output/'native/native-shell.json'),'native_execution':False,
        'scope':'source-identical retargeting; native execution and AppKit adapter checks are separate'}
    (output/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--without-app',action='store_true',help='Build only the native core for isolated qualification')
    args=parser.parse_args();print(json.dumps(prepare(args.previous,args.output,with_app=not args.without_app)))
