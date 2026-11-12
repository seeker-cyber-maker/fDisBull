"""Private, immutable, content-addressed DOS workspace generations.

Two-pass host capture detects observed changes; it is not an atomic host snapshot
and cannot rule out ABA writes by non-cooperating external writers.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import uuid

FORMAT='fdisbull-dos-workspace-generation-1'
CHUNK_KIND='workspace-file-chunk'
GENERATION_KIND='workspace-generation'
CHUNK_SIZE=65536
MAX_ENTRIES=512
MAX_BYTES=16*1024*1024
MAX_DEPTH=16
_ALLOWED=set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~")
_DEVICES={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}


def _hash(data): return hashlib.sha256(data).hexdigest()
def _json(value): return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()


def _number(value,name,lo,hi):
    if type(value) is not int or not lo <= value <= hi: raise ValueError(f'{name} must be {lo}..{hi}')
    return value


def _dos_time(st):
    dt=datetime.fromtimestamp(st.st_mtime,tz=timezone.utc)
    year=min(2107,max(1980,dt.year))
    return ((year-1980)<<9)|(dt.month<<5)|dt.day, (dt.hour<<11)|(dt.minute<<5)|(dt.second//2)


def _parts(name):
    text=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().upper()
    base,sep,ext=text.rpartition('.')
    if not sep or not base: base,ext=text,''
    return ''.join(c if c in _ALLOWED else '_' for c in base), ''.join(c if c in _ALLOWED else '_' for c in ext)


def _aliases(names):
    ordered=sorted(names,key=lambda x:(x.casefold(),x.encode('utf-8')))
    result={}; used=set()
    # Reserve valid names before generated aliases, preventing an alias from
    # stealing another member's authentic short name.
    for name in ordered:
        base,ext=_parts(name)
        direct=(name.isascii() and name.upper() == (base + ('.'+ext if ext else ''))
                and 1<=len(base)<=8 and len(ext)<=3 and base not in _DEVICES)
        alias=base+('.'+ext if ext else '')
        if direct and alias not in used:
            result[name]=alias;used.add(alias)
    for name in ordered:
        if name in result: continue
        base,ext=_parts(name); base=(base or '_');ext=ext[:3]
        for n in range(1,1000000):
            suffix='~'+str(n)
            alias=base[:8-len(suffix)]+suffix+('.'+ext if ext else '')
            if alias not in used and len(alias.split('.')[0])<=8:
                result[name]=alias;used.add(alias);break
        else: raise ValueError('DOS short-name alias space exhausted')
    return result


def _stat_identity(s):
    return (s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def _scan(rootfd, *, max_entries,max_bytes,max_depth):
    entries=[]; total=0
    def visit(fd,host_prefix,dos_prefix,depth):
        nonlocal total
        if depth>max_depth: raise ValueError('Workspace directory depth exceeds its bound')
        before=os.fstat(fd)
        names=os.listdir(fd)
        for name in names:
            try: name.encode('utf-8')
            except UnicodeEncodeError: raise ValueError('Workspace filename is not valid UTF-8') from None
            if not name or name in ('.','..') or any(ord(c)<32 for c in name):
                raise ValueError('Workspace filename contains unsupported characters')
        aliases=_aliases(names)
        for name in sorted(names,key=lambda x:(x.casefold(),x.encode('utf-8'))):
            if len(entries)>=max_entries: raise ValueError('Workspace entry count exceeds its bound')
            st=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                raise ValueError('Workspace symlinks and special entries are unsupported')
            host=host_prefix+[name]; dos=dos_prefix+[aliases[name]]
            date,tm=_dos_time(st)
            item=dict(path='/'.join(host),dos_path='\\'.join(dos),
                      type='directory' if stat.S_ISDIR(st.st_mode) else 'file',
                      attributes=0x10 if stat.S_ISDIR(st.st_mode) else 0x20,dos_date=date,dos_time=tm)
            flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)
            if stat.S_ISDIR(st.st_mode): flags |= os.O_DIRECTORY
            handle=os.open(name,flags,dir_fd=fd)
            try:
                if _stat_identity(os.fstat(handle)) != _stat_identity(st):
                    raise ValueError('Workspace member changed during capture')
                if item['type']=='directory':
                    entries.append(item);visit(handle,host,dos,depth+1)
                else:
                    if st.st_size<0 or total+st.st_size>max_bytes:
                        raise ValueError('Workspace file bytes exceed the capture bound')
                    chunks=[]; remaining=st.st_size
                    while remaining:
                        part=os.read(handle,min(CHUNK_SIZE,remaining))
                        if not part: raise ValueError('Workspace file was truncated during capture')
                        chunks.append(part);remaining-=len(part)
                    if os.read(handle,1) or _stat_identity(os.fstat(handle)) != _stat_identity(st):
                        raise ValueError('Workspace file changed during capture')
                    item['data']=b''.join(chunks);total+=len(item['data']);entries.append(item)
            finally: os.close(handle)
        if _stat_identity(os.fstat(fd)) != _stat_identity(before):
            raise ValueError('Workspace directory changed during capture')
    visit(rootfd,[],[],0)
    return entries,total


def capture_directory(root, *, max_entries=MAX_ENTRIES,max_bytes=MAX_BYTES,max_depth=MAX_DEPTH):
    _number(max_entries,'max_entries',1,MAX_ENTRIES);_number(max_bytes,'max_bytes',0,MAX_BYTES)
    _number(max_depth,'max_depth',1,MAX_DEPTH)
    if not hasattr(os,'O_NOFOLLOW'): raise ValueError('Workspace capture requires no-follow directory access')
    path=Path(root).expanduser().resolve(strict=True)
    fd=os.open(str(path),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        initial=os.fstat(fd)
        first,total=_scan(fd,max_entries=max_entries,max_bytes=max_bytes,max_depth=max_depth)
        second,total2=_scan(fd,max_entries=max_entries,max_bytes=max_bytes,max_depth=max_depth)
        if first!=second or total!=total2 or _stat_identity(os.fstat(fd)) != _stat_identity(initial):
            raise ValueError('Workspace changed between the two inventory passes')
    finally: os.close(fd)
    return dict(root=str(path),root_identity=dict(device=initial.st_dev,inode=initial.st_ino),entries=first,total_bytes=total,
                consistency='two stable no-follow passes; noncooperating ABA writes are not excluded')


def _validate_entries(entries):
    if not isinstance(entries,list) or len(entries)>MAX_ENTRIES: raise ValueError('Invalid workspace entries')
    seen=set(); total=0
    directories={item.get('dos_path') for item in entries if isinstance(item,dict) and item.get('type')=='directory'}
    for item in entries:
        if not isinstance(item,dict) or item.get('type') not in ('file','directory'):
            raise ValueError('Invalid workspace entry')
        path=item.get('dos_path');host=item.get('path')
        if (not isinstance(path,str) or not path or not isinstance(host,str) or not host
                or path != path.upper() or '/' in path or len(path.split('\\'))>MAX_DEPTH+1
                or any(not p or p in ('.','..') or not re.fullmatch(r"[A-Z0-9!#$%&'()@^_`{}~-]{1,8}(?:\.[A-Z0-9!#$%&'()@^_`{}~-]{1,3})?",p)
                       for p in path.split('\\'))
                or host.startswith('/') or any(p in ('','.','..') for p in host.split('/'))
                or path in seen):
            raise ValueError('Invalid or duplicate DOS workspace path')
        parent=path.rpartition('\\')[0]
        if parent and parent not in directories: raise ValueError('Workspace parent directory is missing')
        seen.add(path)
        for key in ('attributes','dos_date','dos_time'): _number(item.get(key),key,0,65535 if key!='attributes' else 255)
        if item['type']=='directory':
            if not item['attributes'] & 0x10 or 'data' in item: raise ValueError('Invalid directory entry')
        else:
            if item['attributes'] & 0x10 or not isinstance(item.get('data'),bytes): raise ValueError('Invalid file entry')
            total+=len(item['data'])
    if total>MAX_BYTES: raise ValueError('Workspace file bytes exceed the generation bound')
    return total


class WorkspaceStore:
    """Immutable manifests plus deduplicated 64 KiB private artifacts."""
    def __init__(self,session):
        self.session=session;self.project=session.project;self.version=session.version['id'];self.run=session.run_id

    def _row(self,identifier,kind):
        row=self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(identifier,)).fetchone()
        if row is None or row['version'] != self.version or row['kind'] != kind:
            raise ValueError('Workspace artifact is missing or belongs to another source version')
        data=bytes(row['data'])
        if _hash(data) != row['sha256']: raise ValueError('Workspace artifact hash mismatch')
        return row,data

    def _chunk(self,data):
        digest=_hash(data)
        rows=self.project.db.execute('SELECT a.id FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.kind=? AND a.sha256=? AND r.version=?',(CHUNK_KIND,digest,self.version)).fetchall()
        for row in rows:
            _,existing=self._row(row['id'],CHUNK_KIND)
            if existing==data: return dict(artifact=row['id'],sha256=digest,size=len(data))
        receipt=self.session._artifact('workspace-chunk.bin',CHUNK_KIND,data,dict(format=FORMAT,sha256=digest))
        if receipt['sha256']!=digest or receipt['size']!=len(data): raise ValueError('Workspace chunk receipt differs')
        return dict(artifact=receipt['artifact'],sha256=digest,size=len(data))

    def _manifest(self,identifier):
        row,data=self._row(identifier,GENERATION_KIND)
        if len(data)>16*1024**2: raise ValueError('Workspace manifest exceeds its byte bound')
        try: doc=json.loads(data)
        except (TypeError,ValueError) as error: raise ValueError('Workspace manifest is malformed') from error
        if (not isinstance(doc,dict) or doc.get('format')!=FORMAT or doc.get('version')!=self.version
                or not isinstance(doc.get('entries'),list) or len(doc['entries'])>MAX_ENTRIES
                or not isinstance(doc.get('original_paths'),list) or not isinstance(doc.get('original_dos_paths'),list)
                or any(not isinstance(v,str) or not v for v in doc.get('original_paths',[])+doc.get('original_dos_paths',[]))
                or not isinstance(doc.get('protected_paths'),list) or not isinstance(doc.get('protected_dos_paths'),list)
                or any(not isinstance(v,str) or not v for v in doc.get('protected_paths',[])+doc.get('protected_dos_paths',[]))
                or doc.get('mode') not in ('checkpointed','live')
                or not isinstance(doc.get('source_root'),(str,type(None)))
                or not isinstance(doc.get('source_identity'),(dict,type(None)))
                or not isinstance(doc.get('parent'),(str,type(None))) or not isinstance(doc.get('base'),(str,type(None)))):
            raise ValueError('Workspace generation identity is malformed')
        return doc

    def load(self,generation):
        doc=self._manifest(generation);entries=[];total=0
        seen={generation};current=doc
        for _ in range(4096):
            parent=current['parent']
            if parent is None:
                if current['base'] is not None: raise ValueError('Workspace root has an invalid base')
                root=next(iter(seen)) if len(seen)==1 else parent_id
                break
            if parent in seen: raise ValueError('Workspace generation lineage contains a cycle')
            seen.add(parent);parent_id=parent
            prior=self._manifest(parent)
            for key in ('version','original_paths','original_dos_paths','source_root','source_identity','mode'):
                if current.get(key)!=prior.get(key): raise ValueError('Workspace lineage identity changed')
            if (not set(prior['protected_paths']) <= set(current['protected_paths'])
                    or not set(prior['protected_dos_paths']) <= set(current['protected_dos_paths'])):
                raise ValueError('Workspace protected host paths regressed')
            current=prior
        else: raise ValueError('Workspace generation lineage exceeds its bound')
        if doc['parent'] is not None and doc['base'] != root:
            raise ValueError('Workspace generation base differs from its lineage')
        for item in doc['entries']:
            if not isinstance(item,dict): raise ValueError('Invalid workspace generation entry')
            row=deepcopy(item); refs=row.pop('chunks',None)
            if row.get('origin') not in ('original','new','unproven'):
                raise ValueError('Invalid workspace file origin')
            if row.get('type')=='file':
                size=row.get('size')
                if (type(size) is not int or size<0 or total+size>MAX_BYTES
                        or not isinstance(refs,list) or len(refs)!=(size+CHUNK_SIZE-1)//CHUNK_SIZE):
                    raise ValueError('Workspace file chunk list or size is invalid')
                total+=size
                parts=[]
                for ref in refs:
                    if not isinstance(ref,dict) or set(ref)!={'artifact','sha256','size'}:
                        raise ValueError('Invalid workspace chunk reference')
                    _,data=self._row(ref['artifact'],CHUNK_KIND)
                    if len(data)!=ref['size'] or len(data)>CHUNK_SIZE or _hash(data)!=ref['sha256']:
                        raise ValueError('Workspace chunk identity differs')
                    parts.append(data)
                row['data']=b''.join(parts)
                if row.get('size')!=len(row['data']) or row.get('sha256')!=_hash(row['data']):
                    raise ValueError('Workspace file identity differs')
            elif refs is not None: raise ValueError('Workspace directory carries file chunks')
            entries.append(row)
        _validate_entries(entries)
        if doc['parent'] is None:
            if (doc['original_paths'] != sorted(item['path'].casefold() for item in entries)
                    or doc['original_dos_paths'] != sorted(item['dos_path'] for item in entries)
                    or doc['protected_paths'] != sorted(set(doc['original_paths']))
                    or doc['protected_dos_paths'] != sorted(set(doc['original_dos_paths']))
                    or any(item['origin']!='original' for item in entries)):
                raise ValueError('Workspace root inventory identity differs')
        else:
            # A child is usable only while its immutable admission base is
            # reconstructible, including originals no longer in this branch.
            self.load(root)
        return dict(artifact=generation,manifest=doc,entries=entries)

    def seal(self, entries, *, parent=None, base=None, reason='capture', source_root=None, source_identity=None, mode='checkpointed', _created=(), _renamed=None, _modified=(), _host_refresh=False):
        _validate_entries(entries)
        if mode not in ('checkpointed','live') or not isinstance(reason,str) or not 1<=len(reason)<=128:
            raise ValueError('Invalid workspace generation mode or reason')
        old=self.load(parent) if parent is not None else None
        if old is None and base is not None: raise ValueError('A workspace base cannot precede its root generation')
        if old is not None:
            root=old['manifest']['base'] or parent
            if base is not None and base!=root: raise ValueError('Workspace base identity differs from parent')
            origin_paths=old['manifest']['original_paths']; origin_dos=old['manifest']['original_dos_paths']
            protected_paths=old['manifest']['protected_paths']; protected_dos=old['manifest']['protected_dos_paths']
            root_path=old['manifest'].get('source_root');mode=old['manifest']['mode']
            root_identity=old['manifest'].get('source_identity')
            if ((source_root is not None and str(Path(source_root).expanduser().resolve(strict=True)) != root_path)
                    or (source_identity is not None and source_identity != root_identity)):
                raise ValueError('Workspace source identity differs from parent')
            previous={item['dos_path']:item for item in old['entries']}
        else:
            root=None;root_path=str(Path(source_root).expanduser().resolve(strict=True)) if source_root is not None else None
            root_identity=deepcopy(source_identity)
            if root_path is not None:
                if (not isinstance(root_identity,dict) or set(root_identity)!={'device','inode'}
                        or any(type(root_identity[k]) is not int or root_identity[k]<0 for k in root_identity)):
                    raise ValueError('Workspace source root requires its captured device/inode identity')
                fd=os.open(root_path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    observed=os.fstat(fd)
                    if (observed.st_dev,observed.st_ino)!=(root_identity['device'],root_identity['inode']):
                        raise ValueError('Workspace source root changed after inventory')
                finally: os.close(fd)
            elif root_identity is not None:
                raise ValueError('Workspace root identity has no source root')
            origin_paths=sorted(item['path'].casefold() for item in entries)
            origin_dos=sorted(item['dos_path'] for item in entries)
            protected_paths=sorted(set(origin_paths));protected_dos=sorted(set(origin_dos))
            previous={}
        if _host_refresh:
            if old is None: raise ValueError('Host refresh requires an existing workspace generation')
            protected_paths=sorted(set(protected_paths)|{item['path'].casefold() for item in entries})
            protected_dos=sorted(set(protected_dos)|{item['dos_path'] for item in entries})
        created=set(_created)
        if any(path in previous or path in protected_dos for path in created):
            raise ValueError('Workspace create collides with an existing or original name')
        if any(item['dos_path'] in created and item['path'].casefold() in protected_paths for item in entries):
            raise ValueError('Workspace create collides with an original host path')
        renamed=dict(_renamed or {})
        modified=set(_modified)
        if any(path not in previous or previous[path]['type'] != 'file' for path in modified):
            raise ValueError('Workspace write requires an existing file')
        if any(source not in previous or destination in previous or destination in protected_dos
               for destination,source in renamed.items()):
            raise ValueError('Workspace rename conflicts with an existing or original name')
        if any(item['dos_path'] in renamed and item['path'].casefold() in protected_paths for item in entries):
            raise ValueError('Workspace rename conflicts with an original host path')
        packed=[]
        for item in entries:
            value=deepcopy(item);data=value.pop('data',None)
            prior=previous.get(value['dos_path'])
            # A raw FAT inventory cannot prove rename/create identity. Never
            # grant keep rights to a newly observed pathname on that basis.
            value['origin']='original' if old is None or value['dos_path'] in protected_dos or value['path'].casefold() in protected_paths else 'unproven'
            if value['dos_path'] in created: value['origin']='new'
            if value['dos_path'] in modified and prior['origin']=='new': value['origin']='new'
            if value['dos_path'] in renamed:
                original=previous[renamed[value['dos_path']]]
                if original.get('data')!=data or original['type'] != value['type']:
                    raise ValueError('Workspace rename changed the source identity')
                value['origin']=original['origin']
            if (not _host_refresh and value['dos_path'] not in protected_dos
                    and value['path'].casefold() not in protected_paths and prior
                    and prior.get('origin')=='new' and prior.get('data')==data and prior.get('path')==value['path']):
                value['origin']='new'
            if value['type']=='file':
                value['size']=len(data);value['sha256']=_hash(data)
                value['chunks']=[self._chunk(data[i:i+CHUNK_SIZE]) for i in range(0,len(data),CHUNK_SIZE)]
            packed.append(value)
        tombstones=sorted(set(previous)-{item['dos_path'] for item in entries})
        doc=dict(format=FORMAT,version=self.version,parent=parent,base=root,mode=mode,reason=reason,tombstones=tombstones,
                 source_root=root_path,source_identity=root_identity,original_paths=origin_paths,original_dos_paths=origin_dos,
                 protected_paths=protected_paths,protected_dos_paths=protected_dos,entries=packed)
        data=_json(doc)
        receipt=self.session._artifact('workspace-generation.json',GENERATION_KIND,data,
                                       dict(format=FORMAT,parent=parent,base=root,sha256=_hash(data)))
        if receipt['sha256']!=_hash(data) or receipt['size']!=len(data): raise ValueError('Workspace generation receipt differs')
        return dict(artifact=receipt['artifact'],sha256=receipt['sha256'],manifest=doc)

    def inspect(self,generation, *, base=None):
        current=self.load(generation);root=base or current['manifest']['base'] or generation
        original=self.load(root)
        a={x['dos_path']:x for x in original['entries']};b={x['dos_path']:x for x in current['entries']}
        def summary(item):
            return {k:deepcopy(v) for k,v in item.items() if k!='data'}
        changes=[]
        for path in sorted(set(a)|set(b)):
            before=summary(a[path]) if path in a else None;after=summary(b[path]) if path in b else None
            if before!=after: changes.append(dict(dos_path=path,before=before,after=after))
        return dict(base=root,generation=generation,base_entries=[summary(x) for x in original['entries']],
                    effective=[summary(x) for x in current['entries']],difference=changes)

    def import_file(self,generation,dos_path,data, *, path=None,attributes=0x20,dos_date=0x0021,dos_time=0):
        if not isinstance(data,bytes): raise ValueError('Imported workspace data must be bytes')
        current=self.load(generation); entries=current['entries']
        if any(item['dos_path']==dos_path for item in entries): raise ValueError('Workspace import collides with an existing path')
        item=dict(path=path or dos_path.replace('\\','/'),dos_path=dos_path,type='file',data=data,
                  attributes=attributes,dos_date=dos_date,dos_time=dos_time)
        _validate_entries(entries+[item])
        result=self.seal(entries+[item],parent=generation,reason='explicit-import')
        return result

    def refresh(self,generation, *, source_dospath=None, expected_source_sha256=None):
        """Stage a two-pass host revision if private edits and source identity allow it."""
        if (source_dospath is None) != (expected_source_sha256 is None):
            raise ValueError('Workspace refresh source path and SHA-256 must be supplied together')
        if source_dospath is not None and (
                not isinstance(source_dospath,str) or not source_dospath
                or source_dospath != source_dospath.upper() or '/' in source_dospath
                or not isinstance(expected_source_sha256,str)
                or not re.fullmatch(r'[0-9a-f]{64}',expected_source_sha256)):
            raise ValueError('Workspace refresh source identity is malformed')
        current=self.load(generation)
        if not current['manifest'].get('source_root'):
            raise ValueError('Controlled host refresh requires an admitted source root')
        host_reference=current
        while host_reference['manifest']['parent'] is not None and host_reference['manifest']['reason'] != 'controlled-refresh':
            host_reference=self.load(host_reference['manifest']['parent'])
        keys=('path','dos_path','type','attributes','dos_date','dos_time','data')
        def projection(entries):
            return sorted((item['dos_path'],tuple(item.get(key) for key in keys))
                          for item in entries)
        if projection(current['entries']) != projection(host_reference['entries']):
            raise ValueError('Private workspace edits conflict with host refresh; reconcile explicitly')
        source=None
        if source_dospath is not None:
            base_id=current['manifest']['base'] or generation
            base=self.load(base_id)
            if base['manifest']['parent'] is not None:
                raise ValueError('Workspace refresh source is not bound to an immutable base')
            source=next((item for item in base['entries']
                         if item['dos_path']==source_dospath),None)
            if (source is None or source['type']!='file' or source.get('origin')!='original'
                    or source.get('sha256')!=expected_source_sha256):
                raise ValueError('Workspace refresh source differs from the immutable base')
        captured=capture_directory(current['manifest']['source_root'])
        if (captured['root'] != current['manifest']['source_root']
                or captured['root_identity'] != current['manifest']['source_identity']):
            raise ValueError('Controlled workspace host root identity changed')

        if source_dospath is not None:
            observed=next((item for item in captured['entries']
                           if item['path']==source['path']
                           and item['dos_path']==source_dospath),None)
            if (observed is None or observed['type']!='file'
                    or _hash(observed['data'])!=expected_source_sha256):
                raise ValueError('Workspace refresh source changed, disappeared or lost its DOS alias')
        result=self.seal(captured['entries'],parent=generation,reason='controlled-refresh',_host_refresh=True)
        result['capture_consistency']=captured['consistency']
        return result

    def create_file(self,generation,dos_path,data, *, path=None,attributes=0x20,dos_date=0x0021,dos_time=0):
        """Apply an explicitly witnessed create to a new private generation.

        Call only for a verified create operation; a directory diff alone cannot
        establish that an observed file is new rather than a renamed original.
        """
        if not isinstance(data,bytes): raise ValueError('Created workspace data must be bytes')
        current=self.load(generation);entries=current['entries']
        item=dict(path=path or dos_path.replace('\\','/'),dos_path=dos_path,type='file',data=data,
                  attributes=attributes,dos_date=dos_date,dos_time=dos_time)
        _validate_entries(entries+[item])
        return self.seal(entries+[item],parent=generation,reason='witnessed-create',_created=(dos_path,))

    def rename_file(self,generation,source,destination, *, path=None):
        current=self.load(generation);entries=current['entries']
        found=next((item for item in entries if item['dos_path']==source),None)
        if found is None or found['type']!='file': raise ValueError('Workspace rename requires an existing file')
        if any(item['dos_path']==destination for item in entries): raise ValueError('Workspace rename destination exists')
        replacement=deepcopy(found);replacement.update(dos_path=destination,path=path or destination.replace('\\','/'))
        replaced=[replacement if item is found else item for item in entries]
        _validate_entries(replaced)
        return self.seal(replaced,parent=generation,reason='witnessed-rename',_renamed={destination:source})

    def write_file(self,generation,dos_path,data, *, expected_sha256):
        """Apply a witnessed full-file replacement with a compare-before-write guard."""
        if not isinstance(data,bytes): raise ValueError('Workspace replacement must be bytes')
        current=self.load(generation); entries=current['entries']
        found=next((item for item in entries if item['dos_path']==dos_path),None)
        if found is None or found['type']!='file': raise ValueError('Workspace write requires an existing file')
        if not isinstance(expected_sha256,str) or _hash(found['data'])!=expected_sha256:
            raise ValueError('Workspace file changed before write')
        replacement=deepcopy(found);replacement['data']=data
        return self.seal([replacement if item is found else item for item in entries],parent=generation,
                         reason='witnessed-write',_modified=(dos_path,))

    def write_range(self,generation,dos_path,offset,data, *, expected_sha256):
        if type(offset) is not int or offset<0 or offset>MAX_BYTES or not isinstance(data,bytes) or offset+len(data)>MAX_BYTES:
            raise ValueError('Workspace write range exceeds its bound')
        current=self.load(generation)
        found=next((item for item in current['entries'] if item['dos_path']==dos_path),None)
        if found is None or found['type']!='file': raise ValueError('Workspace write requires an existing file')
        old=found['data']; new=old[:offset]+bytes(max(0,offset-len(old)))+data+old[offset+len(data):]
        return self.write_file(generation,dos_path,new,expected_sha256=expected_sha256)

    def resize_file(self,generation,dos_path,size, *, expected_sha256):
        if type(size) is not int or not 0<=size<=MAX_BYTES: raise ValueError('Workspace file size exceeds its bound')
        current=self.load(generation)
        found=next((item for item in current['entries'] if item['dos_path']==dos_path),None)
        if found is None or found['type']!='file': raise ValueError('Workspace resize requires an existing file')
        old=found['data'];new=old[:size]+bytes(max(0,size-len(old)))
        return self.write_file(generation,dos_path,new,expected_sha256=expected_sha256)

    def delete_file(self,generation,dos_path):
        current=self.load(generation);entries=current['entries']
        found=next((item for item in entries if item['dos_path']==dos_path),None)
        if found is None or found['type']!='file': raise ValueError('Workspace deletion requires an existing file')
        return self.seal([item for item in entries if item is not found],parent=generation,reason='witnessed-delete')

    def keep(self,generation,dos_path,destination):
        """Export an explicitly created staged file to a new host path.

        Explicit authored creates qualify; they do not prove that the guest
        created the file. Original and previously admitted host paths remain
        protected, and raw FAT inventory differences do not qualify.
        """
        return self._export_file(generation,dos_path,destination,require_new=True)

    def export_file(self,generation,dos_path,destination):
        """Export a coherently admitted generation file to a new destination.

        The caller owns guest-close and flush qualification; this function
        validates stored bytes and exclusive host publication only.
        """
        return self._export_file(generation,dos_path,destination,require_new=False)

    def _export_file(self,generation,dos_path,destination, *, require_new):
        current=self.load(generation)
        entry=next((item for item in current['entries'] if item['dos_path']==dos_path),None)
        if entry is None or entry['type']!='file':
            raise ValueError('Workspace export requires an existing file')
        if require_new and entry.get('origin')!='new':
            raise ValueError('Keep requires a coherently captured, witnessed new file')
        root=current['manifest'].get('source_root')
        target=Path(destination).expanduser()
        if not target.is_absolute(): target=Path.cwd()/target
        if any(part in ('.','..') for part in target.parts) or not target.name:
            raise ValueError('Invalid workspace export destination')
        if root:
            try: relative=target.relative_to(Path(root))
            except ValueError: relative=None
            if relative is not None:
                rel='/'.join(relative.parts).casefold()
                guest='\\'.join(relative.parts).upper()
                if rel in current['manifest']['protected_paths'] or guest in current['manifest']['protected_dos_paths']:
                    raise ValueError('Workspace export cannot replace an original path or DOS alias')
        if not hasattr(os,'O_NOFOLLOW'): raise ValueError('Workspace export requires no-follow directory access')
        parent=target.parent
        parent_fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        fd=None
        temporary_name=None
        durable=False
        try:
            for component in parent.parts[1:]:
                next_fd=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent_fd)
                os.close(parent_fd);parent_fd=next_fd

            requested=_aliases([target.name])[target.name]
            def check_destination_free(exclude_temporary=False):
                names=os.listdir(parent_fd)
                if exclude_temporary and temporary_name is not None:
                    names=[name for name in names if name!=temporary_name]
                aliases=_aliases(names)
                if any(name.casefold()==target.name.casefold() for name in names):
                    raise FileExistsError('Workspace export destination already exists')
                if requested in aliases.values():
                    raise FileExistsError('Workspace export DOS alias collides')

            check_destination_free()
            temporary_name='.fdisbull-export-'+uuid.uuid4().hex+'.tmp'
            fd=os.open(temporary_name,os.O_CREAT|os.O_EXCL|os.O_RDWR|os.O_NOFOLLOW,
                       0o600,dir_fd=parent_fd)
            staged_stat=os.fstat(fd)

            def is_staged_inode(name):
                try:
                    named_stat=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
                except FileNotFoundError:
                    return False
                opened_stat=os.fstat(fd)
                return (stat.S_ISREG(named_stat.st_mode)
                        and (named_stat.st_dev,named_stat.st_ino)==(staged_stat.st_dev,staged_stat.st_ino)
                        and (opened_stat.st_dev,opened_stat.st_ino)==(staged_stat.st_dev,staged_stat.st_ino))

            data=entry['data'];offset=0
            while offset<len(data):
                written=os.write(fd,data[offset:])
                if written<=0: raise OSError('Workspace export write made no progress')
                offset+=written
            os.fsync(fd);os.lseek(fd,0,os.SEEK_SET)
            check=bytearray()
            while True:
                part=os.read(fd,CHUNK_SIZE)
                if not part: break
                check.extend(part)
            if len(check)!=len(data) or _hash(check)!=entry['sha256']:
                raise OSError('Workspace export readback differs')

            # Recheck DOS aliases after staging. The final hard-link itself is
            # exclusive against an exact-name race; external case/alias races
            # between this scan and link remain filesystem-dependent.
            check_destination_free(exclude_temporary=True)
            if not is_staged_inode(temporary_name):
                raise OSError('Workspace export staging file changed before publication')
            os.link(temporary_name,target.name,src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,follow_symlinks=False)
            if not is_staged_inode(target.name):
                raise OSError('Workspace export final link differs from the verified staging file')
            if is_staged_inode(temporary_name):
                os.unlink(temporary_name,dir_fd=parent_fd)
            temporary_name=None
            os.fsync(parent_fd)
            durable=True
            evidence=dict(format=FORMAT,generation=generation,dos_path=dos_path,
                destination=str(target),size=len(data),sha256=entry['sha256'],durable=True)
            encoded=_json(evidence)
            try:
                receipt=self.session._artifact('workspace-export.json','workspace-export-receipt',encoded,
                    dict(format=FORMAT,generation=generation,sha256=_hash(encoded)))
            except BaseException as error:
                error.result=dict(**deepcopy(evidence),receipt_persisted=False,
                                  publication='uncertain; do not replay')
                raise
            if receipt.get('sha256')!=_hash(encoded):
                error=ValueError('Workspace export receipt differs from its persisted bytes')
                error.result=dict(**deepcopy(evidence),receipt_persisted=True,
                                  publication='uncertain; do not replay')
                raise error
            return dict(**evidence,artifact=receipt['artifact'])
        except BaseException as error:
            if fd is not None and getattr(error,'result',None) is None:
                error.result=dict(format=FORMAT,generation=generation,dos_path=dos_path,
                                  destination=str(target),durable=bool(durable),
                                  publication='uncertain; do not replay')
            raise
        finally:
            if temporary_name is not None:
                try:
                    named_stat=os.stat(temporary_name,dir_fd=parent_fd,follow_symlinks=False)
                    opened_stat=os.fstat(fd) if fd is not None else None
                    if (opened_stat is not None and stat.S_ISREG(named_stat.st_mode)
                            and (named_stat.st_dev,named_stat.st_ino)==(opened_stat.st_dev,opened_stat.st_ino)):
                        os.unlink(temporary_name,dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            if fd is not None: os.close(fd)
            os.close(parent_fd)
