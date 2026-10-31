"""Bounded exchange of unbound, explicitly authored type interpretations."""
from __future__ import annotations

import hashlib
import json
import re
from collections import deque

_FORMAT='fdisbull-types-1'
_SOURCE_KEYS={'source_sha256','version_sha256','version','arch','bits','endian'}
_STATUSES={'declared_interpretation','imported_interpretation','changed_local_interpretation'}
_DEFINITION_KEYS={
    'scalar':{'kind','size','signed'}, 'typedef':{'kind','target'},
    'pointer':{'kind','size','target','address_space','segment'},
    'array':{'kind','element','count'}, 'struct':{'kind','size','fields'},
    'union':{'kind','size','fields'}, 'bitfield':{'kind','size','fields'},
    'enum':{'kind','size','signed','flags','members'},
    'function':{'kind','returns','arguments','abi','variadic'},
}


def _json(value):
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError,OverflowError,RecursionError) as error:
        raise ValueError('Type catalog requires finite JSON values') from error


def _digest(value):return hashlib.sha256(_json(value).encode()).hexdigest()


def _author(value):
    if not isinstance(value,str) or not 1<=len(value)<=256:raise ValueError('author must contain 1..256 characters')
    return value


def _keys(value,required,optional=()):
    if not isinstance(value,dict) or not required<=value.keys() or set(value)-required-set(optional):
        raise ValueError('Type catalog object has missing or unsupported fields')


def _source(value):
    from .typesystem import _int
    _keys(value,_SOURCE_KEYS)
    for key in ('source_sha256','version_sha256'):
        if not isinstance(value[key],str) or not re.fullmatch('[0-9a-f]{64}',value[key]):
            raise ValueError('Type catalog source requires lowercase SHA-256 identities')
    _int(value['version'],'source version',1,(1<<63)-1)
    _int(value['bits'],'source bits',1,128)
    if not isinstance(value['arch'],str) or not 1<=len(value['arch'])<=128:
        raise ValueError('Type catalog source architecture must contain 1..128 characters')
    if value['endian'] not in ('little','big'):raise ValueError('Unknown source byte order')


def _definition(value):
    if not isinstance(value,dict):raise ValueError('type definition must be an object')
    if len(_json(value).encode())>65536:raise ValueError('type definition exceeds 64 KiB')
    kind=value.get('kind')
    if not isinstance(kind,str) or kind not in _DEFINITION_KEYS or set(value)-_DEFINITION_KEYS[kind]:
        raise ValueError('Unsupported portable type definition fields or kind')
    if kind=='pointer' and value.get('segment') is not None:
        raise ValueError('Fixed pointer segments are context-bound; define a context-free layout')
    nested='fields' if kind in ('struct','union','bitfield') else 'arguments' if kind=='function' else None
    if nested and isinstance(value.get(nested),list):
        permitted={'name','lsb','width','signed'} if kind=='bitfield' else {'name','type'} if kind=='function' else {'name','offset','type'}
        for field in value[nested]:
            if not isinstance(field,dict) or set(field)-permitted:
                raise ValueError('Unsupported portable field or argument metadata')


def _catalog(document):
    from .typesystem import _name,_BUILTINS
    encoded=_json(document)
    if len(encoded.encode())>4*1024*1024:raise ValueError('Type catalog exceeds 4 MiB')
    document=json.loads(encoded)
    _keys(document,{'format','source','types'})
    if document['format']!=_FORMAT:raise ValueError('Expected fdisbull-types-1 catalog')
    _source(document['source'])
    rows=document['types']
    if not isinstance(rows,list) or len(rows)>4096:raise ValueError('Type catalog requires at most 4096 rows')
    names=set()
    for row in rows:
        _keys(row,{'name','definition','author','origin'})
        name=_name(row['name'])
        if name in names:raise ValueError('Duplicate type names in catalog')
        if name in _BUILTINS:raise ValueError('Catalog cannot redefine built-in scalar types')
        names.add(name);_definition(row['definition']);_author(row['author'])
        origin=row['origin'];_keys(origin,{'status','source','author'},{'imported_by'})
        if not isinstance(origin['status'],str) or origin['status'] not in _STATUSES:raise ValueError('Unknown type origin status')
        _source(origin['source']);_author(origin['author'])
        if origin['author']!=row['author']:raise ValueError('Type author and declared origin author disagree')
        if 'imported_by' in origin:_author(origin['imported_by'])
    return document


def _graph(registry,names):
    from .typesystem import type_layout
    try:
        # Share a budget across catalog layouts, including repeated dependency
        # expansion. Pointer recursion does not expand its target by value.
        budget=[65536,4096]
        for name in names:type_layout(name,registry,_budget=budget)
    except (TypeError,AttributeError,KeyError,RecursionError) as error:
        raise ValueError('Malformed type dependency graph') from error


def _dependencies(definition):
    kind=definition['kind']
    if kind in ('pointer','typedef'):return [definition.get('target')]
    if kind=='array':return [definition.get('element')]
    if kind in ('struct','union'):
        fields=definition.get('fields')
        if not isinstance(fields,list):raise ValueError('Type fields must be a list')
        return [field.get('type') for field in fields]
    if kind=='function':
        arguments=definition.get('arguments')
        if not isinstance(arguments,list):raise ValueError('Function arguments must be a list')
        return ([definition['returns']] if definition.get('returns') is not None else [])+[field.get('type') for field in arguments]
    return []


def _selected_rows(db,v,names):
    from .typesystem import _name,_BUILTINS
    if names is None:
        count,size=db.execute('SELECT count(*),COALESCE(sum(length(document)),0) FROM type_definitions WHERE version=?',(v,)).fetchone()
        if count>4096:raise ValueError('Type catalog requires at most 4096 rows')
        if size>4*1024*1024:raise ValueError('Type catalog exceeds 4 MiB')
        names=[row[0] for row in db.execute('SELECT name FROM type_definitions WHERE version=? ORDER BY name',(v,))]
    if not isinstance(names,list) or len(names)>4096:raise ValueError('Select at most 4096 type names as a list')
    requested=[_name(name) for name in names]
    if len(set(requested))!=len(requested):raise ValueError('Duplicate selected type names')
    if any(name in _BUILTINS for name in requested):raise ValueError('Select custom types, not built-in scalar types')
    queue=deque(requested);selected={};size=0
    while queue:
        name=queue.popleft()
        if name in selected:continue
        if len(selected)>=4096:raise ValueError('Type catalog requires at most 4096 rows')
        length=db.execute('SELECT length(document) FROM type_definitions WHERE version=? AND name=?',(v,name)).fetchone()
        if length is None:raise ValueError('Unknown selected type or dependency: '+name)
        if length[0]>65536:raise ValueError('type definition exceeds 64 KiB')
        row=db.execute('SELECT name,document,author FROM type_definitions WHERE version=? AND name=?',(v,name)).fetchone()
        definition=json.loads(row['document']);_definition(definition)
        size+=len(row['document'].encode())
        if size>4*1024*1024:raise ValueError('Type catalog exceeds 4 MiB')
        selected[name]=dict(row,definition=definition)
        for dependency in _dependencies(definition):
            dependency=_name(dependency)
            if dependency not in _BUILTINS and dependency not in selected:queue.append(dependency)
    return [selected[name] for name in sorted(selected)]


class TypeCatalogMixin:
    def _type_catalog_source(self,v):
        return dict(source_sha256=self.meta.get('source_sha256'),version_sha256=self.version(v)['sha256'],
                    version=v,arch=self.arch,bits=self.bits,endian=self.meta.get('endian','little'))

    def _forget_type_origin(self,v,name,definition,author):
        row=self.db.execute('SELECT definition_sha256,author FROM type_catalog_origins WHERE version=? AND name=?',(v,name)).fetchone()
        if row and (row['definition_sha256']!=_digest(definition) or row['author']!=author):
            self.db.execute('DELETE FROM type_catalog_origins WHERE version=? AND name=?',(v,name))

    def export_types(self,version=None,names=None):
        """Export declarations only. Source/origin identities are assertions, not proof."""
        with self.transaction():
            v=self.version(version)['id'];source=self._type_catalog_source(v);_source(source)
            rows=[]
            for row in _selected_rows(self.db,v,names):
                definition=row['definition']
                prior=self.db.execute('SELECT * FROM type_catalog_origins WHERE version=? AND name=?',(v,row['name'])).fetchone()
                if prior and prior['definition_sha256']==_digest(definition) and prior['author']==row['author']:
                    origin=json.loads(prior['document'])
                else:
                    # Old installed writers can edit schema-8 definitions without
                    # maintaining our optional provenance table. Never reuse it.
                    origin=dict(status='changed_local_interpretation' if prior else 'declared_interpretation',source=source,author=row['author'])
                rows.append(dict(name=row['name'],definition=definition,author=row['author'],origin=origin))
            _graph({row['name']:row['definition'] for row in rows},[row['name'] for row in rows])
            return _catalog(dict(format=_FORMAT,source=source,types=rows))

    def import_types(self,catalog,version=None,author='agent'):
        """Validate the complete graph, then add nonconflicting unbound definitions."""
        document=_catalog(catalog);_author(author)
        with self.transaction(True):
            v=self.version(version)['id'];registry=self._type_registry(v);incoming={r['name']:r['definition'] for r in document['types']}
            for name,definition in incoming.items():
                if name in registry and registry[name]!=definition:raise ValueError('Destination type conflict: '+name)
            combined={**registry,**incoming}
            _graph(combined,incoming)
            imported=[];skipped=[]
            for row in document['types']:
                name=row['name']
                if name in registry:skipped.append(name);continue
                definition=row['definition'];origin={**row['origin'],'status':'imported_interpretation','imported_by':author}
                self.db.execute('INSERT INTO type_definitions VALUES (?,?,?,?,1)',(v,name,_json(definition),row['author']))
                self.db.execute('INSERT INTO type_catalog_origins VALUES (?,?,?,?,?)',(v,name,_digest(definition),row['author'],_json(origin)))
                imported.append(name)
            return dict(version=v,imported=len(imported),skipped=len(skipped),imported_names=imported,skipped_names=skipped,
                        author=author,source=document['source'],bindings_imported=0,invalidated_tasks=[])
