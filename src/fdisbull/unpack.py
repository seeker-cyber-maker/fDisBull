"""Non-executing, layered installer intake. Run with ``python -m fdisbull.unpack``.

Providers are trusted Python integrations, never discovered from target content.
An image filesystem is a derived subset, not a preservation-equivalent disc.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Callable

from .archive_layers import safe_name, zip_segments, zip_payload
from .image_intake import file_identity, hash_file, disc_plan, disc_payload
from .exepack import unpack_exepack, rebuild_mz, mz_info


@dataclass(frozen=True)
class Limits:
    max_input: int = 256 * 1024 * 1024
    max_member: int = 128 * 1024 * 1024
    max_total: int = 1024 * 1024 * 1024
    max_files: int = 10000
    max_depth: int = 4
    max_seconds: int = 180

    def __post_init__(self):
        bounds = {'max_input':(1,512*1024*1024), 'max_member':(1,256*1024*1024),
                  'max_total':(1,4*1024*1024*1024), 'max_files':(1,100000),
                  'max_depth':(0,16), 'max_seconds':(1,3600)}
        for key,(low,high) in bounds.items():
            v = getattr(self,key)
            if type(v) is not int or not low <= v <= high:
                raise ValueError('invalid limit: '+key)


@dataclass(frozen=True)
class Provider:
    """Explicit trusted extension, e.g. the separately qualified floppy reader.

    inspect(path, limits) -> JSON metadata containing entries with name/size.
    read(path, metadata, entry, limit) -> bytes. Neither callback may run targets.
    The dispatcher enforces names and budgets around callbacks. Python plugins
    are trusted code, not a security sandbox.
    """
    name: str
    inspect: Callable
    read: Callable


_PROVIDERS: dict[str, Provider] = {}


def register_provider(provider: Provider):
    if (not isinstance(provider, Provider) or not provider.name.isidentifier() or
            provider.name in _PROVIDERS or provider.name in ('zip','disc','inno','exepack')):
        raise ValueError('invalid or duplicate trusted provider')
    _PROVIDERS[provider.name] = provider


def catalog():
    return {'format':'fdisbull-unpack-catalog-1', 'executes_targets':False,
            'providers':['zip','disc','inno','exepack', *sorted(_PROVIDERS)],
            'native_profiles':['ZIP stored/deflate, concatenated/SFX with opaque prefix',
                'CUE/INS + Mode1/2048 or Mode1/2352 + primary ISO9660',
                'installed native Inno reader profiles', 'classic EXEPACK 16/18, skip=1, Ultima wrapper'],
            'unsupported':['ZIP64/spanned/encrypted ZIP','UDF/Mode2 filesystems',
                'NRG/MDS/MDF/CCD/SUB/VCD proprietary layouts without explicit provider',
                'floppy layouts require the separately qualified reader via explicit trusted provider'],
            'generic_dynamic_unpacking':'python -m fdisbull.installer_probe; explicit owned DOSBox execution'}


def _bytes(path: Path, limits: Limits) -> bytes:
    before = file_identity(path)
    if before['size'] > limits.max_input:
        raise ValueError('source byte limit exceeded')
    with path.open('rb') as f:
        data = f.read(limits.max_input+1)
    if len(data) != before['size'] or before != file_identity(path):
        raise ValueError('source changed while reading')
    return data


def _probe(path: Path, prefix: bytes) -> str | None:
    # Magic/profile evidence takes precedence over suffix. Exotics never fall
    # through to a raw ISO guess merely because their byte length is convenient.
    if prefix[:2] == b'MZ' and b'rDlPtS' in prefix:
        return 'inno'
    if path.suffix.lower() in ('.nrg','.mds','.mdf','.ccd','.sub','.vcd','.vc4'):
        return 'unsupported-disc'
    if path.suffix.lower() in ('.cue','.ins'):
        return 'disc' if b'FILE' in prefix.upper() and b'TRACK' in prefix.upper() else 'unknown'
    if prefix[:12] == b'\x00'+b'\xff'*10+b'\x00':
        return 'disc'
    if any(prefix[i*2048:i*2048+7] == b'\x01CD001\x01' for i in range(16,32)):
        return 'disc'
    if path.suffix.lower() in ('.img','.ima','.vfd','.dsk','.ipf','.dmk','.imd','.hfe'):
        return 'unsupported-disc'
    if prefix[:2] == b'MZ':
        return 'exepack-or-executable'
    if prefix[:4] in (b'PK\x03\x04',b'PK\x05\x06'):
        return 'zip'
    return None


def inspect_path(path, *, provider=None, track=None, limits=None) -> dict:
    limits = limits or Limits()
    path = Path(path).absolute()
    before = file_identity(path)
    if before['size'] > limits.max_input:
        raise ValueError('source byte limit exceeded')
    with path.open('rb') as f:
        prefix = f.read(min(limits.max_input, 1024*1024))
    selected = provider or _probe(path,prefix)
    source = {'path':str(path), 'bytes':before['size'], 'sha256':hash_file(path)}
    result = {'format':'fdisbull-layer-inspection-1', 'source':source,
              'source_identity':before, 'provider':selected, 'status':'supported',
              'executes_targets':False, 'entries':[], 'metadata':{}}
    if selected in _PROVIDERS:
        result['metadata'] = _PROVIDERS[selected].inspect(path,limits)
        result['entries'] = result['metadata']['entries']
    elif selected == 'disc':
        plan = disc_plan(path,track_number=track,max_entries=limits.max_files)
        result['metadata'] = plan
        result['entries'] = [dict(name=e['output_name'],size=e['size'],directory=e['kind']=='directory',
                                  reference=e) for e in plan['filesystem']['entries']]
    elif selected == 'inno':
        try:
            from .native_inno import NativeInno
        except ImportError as exc:
            raise ValueError('native Inno provider missing from installed package') from exc
        n = NativeInno.open(path,deadline=time.monotonic()+limits.max_seconds)
        result['metadata'] = n.describe()
        result['entries'] = [dict(name=e['path'],size=e['size'],directory=False) for e in n.inventory]
    else:
        data = _bytes(path,limits)
        if selected in ('exepack','exepack-or-executable'):
            try:
                image,report = unpack_exepack(data,max_output=min(limits.max_member,16*1024*1024))
                result['metadata'] = report
                result['provider'] = 'exepack'
                result['entries'] = [dict(name='image.bin',size=len(image),directory=False),
                    dict(name='analysis.exe',size=len(rebuild_mz(image,report)),directory=False)]
            except ValueError as exc:
                if selected == 'exepack':
                    raise
                result.update(status='opaque-executable', provider=None,
                    metadata={'static_refusal':str(exc), 'next':'explicit owned installer_probe; not an OEP guess'})
                try: result['metadata']['mz'] = mz_info(data)
                except ValueError: pass
                # A DOS/Windows self-extracting ZIP is still an archive. Never
                # run its stub just because EXEPACK is the wrong profile.
                if b'PK\x05\x06' in data:
                    try:
                        z = zip_segments(data,max_entries=limits.max_files)
                        result.update(provider='zip',metadata=z,status='partial')
                        result['entries'] = [dict(name=f'archive-{i:03d}/'+e['name'],size=e['size'],
                            directory=e['directory'],segment=i,reference=e)
                            for i,s in enumerate(z['segments']) for e in s['entries']]
                    except ValueError as zip_error:
                        result['metadata']['zip_refusal'] = str(zip_error)
        elif selected == 'unsupported-disc':
            result.update(status='unsupported',metadata={'reason':'explicit image provider required'})
        elif selected in ('zip',None):
            if selected == 'zip' or b'PK\x05\x06' in data:
                z = zip_segments(data,max_entries=limits.max_files)
                result.update(provider='zip',metadata=z)
                result['entries'] = [dict(name=f'archive-{i:03d}/'+e['name'], size=e['size'],
                    directory=e['directory'], segment=i, reference=e)
                    for i,s in enumerate(z['segments']) for e in s['entries']]
                if not z['complete_byte_accounting']:
                    result['status'] = 'partial'
            else:
                result.update(status='leaf',provider=None)
        elif selected == 'unknown':
            result.update(status='unsupported',metadata={'reason':'descriptor suffix without admitted structure'})
        else:
            raise ValueError('unknown provider: '+str(selected))
    _preflight(result['entries'],limits)
    if before != file_identity(path):
        raise ValueError('source changed during inspection')
    return result


def _preflight(entries, limits):
    if not isinstance(entries,list) or len(entries) > limits.max_files:
        raise ValueError('entry count limit')
    seen, files, total = set(),set(),0
    for e in entries:
        name = safe_name(e['name']); key = name.casefold()
        if key in seen or type(e.get('size')) is not int or e['size'] < 0:
            raise ValueError('duplicate or malformed entry')
        if e['size'] > limits.max_member:
            raise ValueError('member byte limit: '+name)
        if not e.get('directory',False): files.add(key)
        total += e['size']; seen.add(key)
    if total > limits.max_total:
        raise ValueError('total expansion limit')
    for key in seen:
        parts = key.split('/')
        if any('/'.join(parts[:i]) in files for i in range(1,len(parts))):
            raise ValueError('file/directory prefix collision')


def unpack_layers(path, output, *, recursive=False, provider=None, track=None, limits=None) -> dict:
    """Extract into an exclusively created private directory; never overwrite.

    The source is not deleted. Unsupported leaves are retained and reported.
    A failed operation removes only the directory this call created.
    """
    if type(recursive) is not bool:
        raise ValueError('recursive must be boolean')
    limits = limits or Limits()
    source = Path(path).absolute(); output = Path(output).absolute()
    file_identity(source)
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError('output parent must be an existing nonsymlink directory')
    output.mkdir(mode=0o700)  # exclusive; existing paths/symlinks refuse
    deadline = time.monotonic()+limits.max_seconds
    manifest = {'format':'fdisbull-layer-extraction-1','complete':True,'executes_targets':False,
                'limits':asdict(limits),'layers':[],'files':[],'bytes_written':0,
                'preservation_equivalent':False, 'originals_retained':True}
    visited = set(); pending = [(source,None,0,provider,track)]

    def check():
        if time.monotonic() > deadline:
            raise ValueError('cooperative extraction deadline exceeded')

    try:
        while pending:
            check()
            current,parent,depth,forced,selected_track = pending.pop(0)
            key = str(current.resolve())
            if key in visited: continue
            visited.add(key)
            if depth > limits.max_depth:
                manifest['complete'] = False
                manifest['layers'].append({'source_path':key,'parent':parent,'depth':depth,'status':'depth-limit'})
                continue
            report = inspect_path(current,provider=forced,track=selected_track,limits=limits)
            check()
            lid = len(manifest['layers'])
            report.update(id=lid,parent=parent,depth=depth)
            manifest['layers'].append(report)
            if report['status'] in ('partial','unsupported','opaque-executable'):
                manifest['complete'] = False
            if report['provider'] == 'disc':
                for src in report['metadata']['sources']: visited.add(str(Path(src['path']).resolve()))
                if report['metadata']['omissions']: manifest['complete']=False
            if not report['entries']: continue
            folder = output / f'layer-{lid:04d}'
            files = [e for e in report['entries'] if not e.get('directory',False)]
            if len(manifest['files'])+len(files) > limits.max_files:
                raise ValueError('global extracted-file budget')
            if manifest['bytes_written']+sum(e['size'] for e in files) > limits.max_total:
                raise ValueError('global expanded-byte budget')
            if report['provider'] == 'inno':
                from .native_inno import NativeInno
                n = NativeInno.open(current,deadline=deadline)
                if n.source_sha256 != report['source']['sha256']:
                    raise ValueError('Inno source changed')
                n.extract_selected(folder,[e['name'] for e in files],emit_manifest=False,deadline=deadline)
            else:
                folder.mkdir(mode=0o700)
                data = _bytes(current,limits) if report['provider'] in ('zip','exepack') else None
                if data is not None and hashlib.sha256(data).hexdigest() != report['source']['sha256']:
                    raise ValueError('source changed before extraction')
                unpacked = unpack_exepack(data,max_output=min(limits.max_member,16*1024*1024)) if report['provider']=='exepack' else None
                for e in report['entries']:
                    check(); destination = folder / safe_name(e['name'])
                    if e.get('directory',False):
                        destination.mkdir(parents=True,exist_ok=True); continue
                    if report['provider'] == 'zip':
                        payload = zip_payload(data,report['metadata']['segments'][e['segment']],e['reference'],limit=limits.max_member)
                    elif report['provider'] == 'disc':
                        payload = disc_payload(report['metadata'],e['reference'],limit=min(limits.max_member,64*1024*1024))
                    elif unpacked is not None:
                        payload = unpacked[0] if e['name']=='image.bin' else rebuild_mz(*unpacked)
                    else:
                        payload = _PROVIDERS[report['provider']].read(current,report['metadata'],e,limits.max_member)
                    if not isinstance(payload,bytes) or len(payload) != e['size']:
                        raise ValueError('provider output length mismatch')
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    with destination.open('xb') as f: f.write(payload)
            children = []
            for e in files:
                check(); p=folder/safe_name(e['name'])
                if p.stat().st_size != e['size']: raise ValueError('extracted size mismatch')
                manifest['files'].append(dict(layer=lid,member=e['name'],output=str(p.relative_to(output)),
                    bytes=e['size'],sha256=hash_file(p)))
                manifest['bytes_written'] += e['size']
                # Rebuilt analysis executables must never be recursively called
                # an additional unpacking layer or automatically executed.
                if recursive and report['provider'] != 'exepack':
                    children.append((p,lid,depth+1,None,None))
            if report['source_identity'] != file_identity(current):
                raise ValueError('source changed during extraction')
            if report['provider']=='disc':
                for s in report['metadata']['sources']:
                    if s['identity'] != file_identity(Path(s['path'])): raise ValueError('disc companion changed')
            # Inspect descriptors before their binary companions, and only after
            # every sibling has been materialized.
            children.sort(key=lambda item:(item[0].suffix.lower() not in ('.cue','.ins'),str(item[0])))
            pending.extend(children)
        check()
        with (output/'layers.json').open('x',encoding='utf-8') as f:
            json.dump(manifest,f,indent=2,allow_nan=False); f.write('\n')
        return manifest
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    sub.add_parser('catalog')
    for op in ('inspect','extract'):
        p=sub.add_parser(op); p.add_argument('path'); p.add_argument('--provider'); p.add_argument('--track',type=int)
        if op=='extract': p.add_argument('output'); p.add_argument('--recursive',action='store_true')
        for field in Limits.__dataclass_fields__:
            p.add_argument('--'+field.replace('_','-'),type=int,default=getattr(Limits(),field))
    args=vars(parser.parse_args()); operation=args.pop('operation')
    try:
        if operation=='catalog': result=catalog()
        else:
            limits=Limits(**{k:args.pop(k) for k in Limits.__dataclass_fields__})
            result=inspect_path(**args,limits=limits) if operation=='inspect' else unpack_layers(**args,limits=limits)
        print(json.dumps(result,allow_nan=False)); return 0
    except (ValueError,OSError,KeyError) as exc:
        print(json.dumps({'status':'refused','error':str(exc),'executes_targets':False})); return 2


if __name__=='__main__':
    raise SystemExit(main())
