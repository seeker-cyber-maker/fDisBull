"""Portable scene definitions and clean reference PNGs; never executable state."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import uuid
import zipfile


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def identity(project,version):
    return {k:project.meta[k] for k in ('source_sha256','format','arch','bits')}|{
        'mapped_sha256':project.version(version)['sha256']}


class SceneBundleMixin:
    def debug_export_scenes(self, scenes, output, *, version=None):
        if not isinstance(scenes,list) or not 1<=len(scenes)<=64:raise ValueError('Export requires 1..64 scenes')
        v=self.version(version)['id'];items=[];snapshots={};payloads={};roots=set()
        for selected in scenes:
            info=self.debug_scene_info(selected,version=v)
            if info['scene'] in roots:raise ValueError('Export at most one revision of each scene')
            roots.add(info['scene']);items.append(info)
            doc=info['definition']
            refs={doc['reference']}|{a for obj in doc['objects'] for a in obj['evidence']}
            for artifact in sorted(refs):
                row,metadata=self._scene_snapshot(artifact,v)
                path='snapshots/'+row['sha256']+'.png'
                snapshots[artifact]=dict(path=path,sha256=row['sha256'],metadata=metadata)
                payloads[path]=bytes(row['data'])
        manifest=dict(format='fdisbull-scene-bundle-1',compatibility=identity(self,v),scenes=items,snapshots=snapshots)
        data=encoded(manifest)
        if len(snapshots)>1024 or len(data)>4*1024*1024 or sum(map(len,payloads.values()))>64*1024*1024-len(data):
            raise ValueError('Scene bundle exceeds size budget')
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',data)
            for path,payload in sorted(payloads.items()):archive.writestr(path,payload)
        result=buffer.getvalue();destination=Path(output)
        if len(result)>64*1024*1024:raise ValueError('Compressed scene bundle exceeds budget')
        with destination.open('xb') as stream:stream.write(result)
        return dict(output=str(destination),sha256=hashlib.sha256(result).hexdigest(),size=len(result),
                    scenes=len(items),snapshots=len(payloads),snapshot_hashes=sorted({s['sha256'] for s in snapshots.values()}))

    def debug_import_scenes(self, bundle, *, version=None):
        try:return self._import_scene_bundle(bundle,version=version)
        except (zipfile.BadZipFile,zipfile.LargeZipFile,EOFError) as error:
            raise ValueError('Invalid scene bundle archive: '+str(error)) from error

    def _import_scene_bundle(self, bundle, *, version=None):
        v=self.version(version)['id'];source=Path(bundle)
        if not source.is_file() or source.stat().st_size>64*1024*1024:raise ValueError('Scene bundle exceeds size budget')
        with source.open('rb') as stream:raw=stream.read(64*1024*1024+1)
        if len(raw)>64*1024*1024:raise ValueError('Scene bundle exceeds size budget')
        bundle_sha=hashlib.sha256(raw).hexdigest()
        payloads={}
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members=archive.infolist();names=[i.filename for i in members]
            if len(names)>1025 or len(set(names))!=len(names) or 'manifest.json' not in names:
                raise ValueError('Invalid scene bundle members')
            if sum(i.file_size for i in members)>64*1024*1024:raise ValueError('Scene bundle expands beyond budget')
            for item in members:
                if item.filename!='manifest.json' and not re.fullmatch(r'snapshots/[0-9a-f]{64}\.png',item.filename):
                    raise ValueError('Unexpected scene bundle member')
                if stat.S_ISLNK(item.external_attr>>16) or item.flag_bits&1 or item.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) or item.file_size>(4 if item.filename=='manifest.json' else 16)*1024*1024:
                    raise ValueError('Invalid scene bundle entry')
                payloads[item.filename]=archive.read(item)
        manifest=json.loads(payloads['manifest.json'])
        if not isinstance(manifest,dict) or set(manifest)!={'format','compatibility','scenes','snapshots'} or manifest['format']!='fdisbull-scene-bundle-1':
            raise ValueError('Expected fdisbull-scene-bundle-1')
        if manifest['compatibility']!=identity(self,v):raise ValueError('Scene bundle is not compatible with this source and mapped byte version')
        items=manifest['scenes'];snapshots=manifest['snapshots']
        if not isinstance(items,list) or not 1<=len(items)<=64 or not isinstance(snapshots,dict) or not 1<=len(snapshots)<=1024:
            raise ValueError('Invalid scene bundle counts')
        from PIL import Image
        for entry in snapshots.values():
            if not isinstance(entry,dict) or set(entry)!={'path','sha256','metadata'}:raise ValueError('Invalid snapshot record')
            data=payloads.get(entry['path']);meta=entry['metadata']
            if data is None or entry['path']!='snapshots/'+entry['sha256']+'.png' or hashlib.sha256(data).hexdigest()!=entry['sha256']:
                raise ValueError('Scene snapshot hash mismatch')
            with Image.open(io.BytesIO(data)) as image:
                if image.format!='PNG' or image.size!=(meta['width'],meta['height']):raise ValueError('Expected clean PNG snapshot dimensions')
                image.verify()
        if set(payloads)!={'manifest.json',*(entry['path'] for entry in snapshots.values())}:raise ValueError('Unreferenced bundle payload')
        names=set();revisions=set();references=set()
        for item in items:
            if not isinstance(item,dict) or set(item)!={'id','scene','version','name','parent','created','author','sha256','definition'}:
                raise ValueError('Invalid scene bundle record')
            if item['name'] in names or item['id'] in revisions:raise ValueError('Duplicate bundle scene')
            names.add(item['name']);revisions.add(item['id'])
            if self.db.execute('SELECT 1 FROM debug_scenes WHERE version=? AND name=?',(v,item['name'])).fetchone():
                raise ValueError('Scene name already exists: '+item['name'])
            doc=item['definition']
            if hashlib.sha256(encoded(doc)).hexdigest()!=item['sha256']:raise ValueError('Scene manifest hash mismatch')
            references.add(doc['reference'])
            references.update(a for obj in doc['objects'] for a in obj['evidence'])
        if references!=set(snapshots):raise ValueError('Missing or unused snapshot references')
        # A savepoint also makes this operation atomic inside a caller's outer
        # transaction. Regular project transactions intentionally nest without one.
        from .project import now
        artifact_map={};object_map={};scene_map={};run=uuid.uuid4().hex
        with self.transaction(True):
            self.db.execute('SAVEPOINT scene_bundle')
            try:
                self.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (run,v,now(),now(),'imported',encoded(dict(backend='scene-bundle-import',historical_only=True,bundle_sha256=bundle_sha)).decode()))
                for old,entry in snapshots.items():
                    metadata=dict(entry['metadata'],bundle_origin=dict(bundle_sha256=bundle_sha,artifact=old),historical_only=True)
                    artifact_map[old]=self._debug_artifact(run,entry['path'].split('/')[-1],'screenshot',payloads[entry['path']],metadata)['artifact']
                for item in items:
                    doc=deepcopy(item['definition']);doc['reference']=artifact_map[doc['reference']]
                    origin={k:item[k] for k in ('id','scene','author','sha256','created')};origin['bundle_sha256']=bundle_sha
                    doc['context']['bundle_origin']=origin
                    old_ids=[]
                    for obj in doc['objects']:
                        old_ids.append(obj.pop('id'))
                        obj['evidence']=[artifact_map[a] for a in obj['evidence']]
                    saved=self.debug_save_scene(item['name'],doc,version=v,author='scene bundle import')
                    scene_map[item['id']]=saved['id']
                    for old,obj in zip(old_ids,saved['definition']['objects'],strict=True):
                        if old in object_map:raise ValueError('Duplicate source object id')
                        object_map[old]=obj['id']
                self.db.execute('RELEASE scene_bundle')
            except BaseException:
                self.db.execute('ROLLBACK TO scene_bundle');self.db.execute('RELEASE scene_bundle')
                raise
        return dict(format='fdisbull-scene-import-1',bundle_sha256=bundle_sha,version=v,run=run,
                    scene_map=scene_map,object_map=object_map,artifact_map=artifact_map,historical_only=True,live_state_verified=False)
