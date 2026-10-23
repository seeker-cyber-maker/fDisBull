"""Versioned structural types over physical data identity, independent of ISA/container."""
from __future__ import annotations
import json
import re

TYPE_DDL = """
CREATE TABLE IF NOT EXISTS type_definitions(version INTEGER NOT NULL,name TEXT NOT NULL,document TEXT NOT NULL,author TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(version,name));
CREATE TABLE IF NOT EXISTS type_bindings(version INTEGER NOT NULL,address TEXT NOT NULL,name TEXT NOT NULL,type_name TEXT NOT NULL,size INTEGER NOT NULL,author TEXT NOT NULL,PRIMARY KEY(version,address));
"""
_BUILTINS = {f'{prefix}{bits}':dict(kind='scalar',size=bits//8,signed=prefix=='i') for prefix in ('u','i') for bits in (8,16,32,64)}
_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')


def _name(value):
    if not isinstance(value,str) or not _NAME.fullmatch(value):
        raise ValueError('type and field names must be identifiers of 1..128 characters')
    return value


def _int(value,label,low=0,high=1<<20):
    if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def type_layout(name, registry, active=()):
    """Validate a named layout. Pointer recursion does not recurse by value."""
    if name in active or len(active)>32:
        raise ValueError('recursive by-value type or nesting exceeds 32 levels')
    raw=registry.get(name,_BUILTINS.get(name))
    if not isinstance(raw,dict):
        raise ValueError(f'unknown type: {name}')
    kind=raw.get('kind')
    if kind=='scalar':
        size=_int(raw.get('size'),'scalar size',1,16)
        if not isinstance(raw.get('signed',False),bool):raise ValueError('signed must be boolean')
        return dict(name=name,kind=kind,size=size,signed=raw.get('signed',False))
    if kind=='pointer':
        size=_int(raw.get('size'),'pointer size',1,8)
        if size not in (2,4,8):raise ValueError('pointer size must be 2, 4 or 8 bytes')
        target=_name(raw.get('target'))
        if target not in registry and target not in _BUILTINS:raise ValueError(f'unknown pointer target: {target}')
        space=raw.get('address_space','flat')
        if space not in ('flat','near','far16'):raise ValueError('pointer address_space must be flat, near or far16')
        segment=raw.get('segment')
        if space=='far16' and size!=4:raise ValueError('far16 pointers occupy four bytes')
        if segment is not None:_int(segment,'near segment',0,65535)
        return dict(name=name,kind=kind,size=size,target=target,address_space=space,segment=segment)
    if kind=='array':
        element=_name(raw.get('element'));count=_int(raw.get('count'),'array count',1,65536)
        layout=type_layout(element,registry,active+(name,));size=count*layout['size']
        if size>1<<20:raise ValueError('type exceeds 1 MiB')
        return dict(name=name,kind=kind,size=size,element=layout,count=count)
    if kind=='struct':
        size=_int(raw.get('size'),'structure size',1)
        fields=raw.get('fields')
        if not isinstance(fields,list) or len(fields)>1024:raise ValueError('fields must be a list of at most 1024 entries')
        result=[];names=set()
        for field in fields:
            if not isinstance(field,dict):raise ValueError('field must be an object')
            field_name=_name(field.get('name'))
            if field_name in names:raise ValueError('duplicate field name')
            names.add(field_name)
            offset=_int(field.get('offset'),'field offset')
            layout=type_layout(_name(field.get('type')),registry,active+(name,))
            if offset+layout['size']>size:raise ValueError('field exceeds structure size')
            if any(offset<previous['offset']+previous['type']['size'] and offset+layout['size']>previous['offset'] for previous in result):
                raise ValueError('overlapping structure fields require a separately defined representation')
            result.append(dict(name=field_name,offset=offset,type=layout))
        return dict(name=name,kind=kind,size=size,fields=sorted(result,key=lambda f:f['offset']))
    raise ValueError('type kind must be scalar, pointer, array or struct')


def _field_at(layout,offset,path=''):
    if layout['kind']=='array':
        width=layout['element']['size'];index,inside=divmod(offset,width)
        return _field_at(layout['element'],inside,path+f'[{index}]')
    if layout['kind']=='struct':
        for field in layout['fields']:
            width=field['type']['size']
            if field['offset']<=offset<field['offset']+width:
                return _field_at(field['type'],offset-field['offset'],path+'.'+field['name'])
        return dict(path=path+(f'+0x{offset:x}' if offset else ''),byte_offset=offset,type_name=layout['name'],kind='padding',size=1)
    return dict(path=path+(f'+0x{offset:x}' if offset else ''),byte_offset=offset,type_name=layout['name'],kind=layout['kind'],size=layout['size'])


class TypeSystemMixin:
    def _type_registry(self,v):
        return {r['name']:json.loads(r['document']) for r in self.db.execute('SELECT name,document FROM type_definitions WHERE version=?',(v,))}

    def define_type(self,name,definition,version=None,author='agent'):
        name=_name(name)
        if name in _BUILTINS:raise ValueError('built-in scalar types cannot be redefined')
        if not isinstance(definition,dict):raise ValueError('definition must be an object')
        if not isinstance(author,str) or not 1<=len(author)<=256:raise ValueError('author must contain 1..256 characters')
        if len(json.dumps(definition))>65536:raise ValueError('type definition exceeds 64 KiB')
        with self.transaction(True):
            v=self.version(version)['id'];registry=self._type_registry(v);old_registry=dict(registry);registry[name]=definition
            layouts={n:type_layout(n,registry) for n in registry}
            bindings=self.db.execute('SELECT * FROM type_bindings WHERE version=? ORDER BY address',(v,)).fetchall()
            previous_end=-1
            for binding in bindings:
                address=int(binding['address'],16);size=type_layout(binding['type_name'],registry)['size'];region=self._mapping(v,address)
                if region is None or address+size>region.start+len(region.data):raise ValueError('updated type binding exceeds its mapped region')
                if address<previous_end:raise ValueError('updated type bindings would overlap')
                previous_end=address+size
            if hasattr(self,'_validate_file_types'):self._validate_file_types(v,registry)
            self.db.execute('INSERT INTO type_definitions VALUES (?,?,?,?,1) ON CONFLICT(version,name) DO UPDATE SET document=excluded.document,author=excluded.author,revision=revision+1',(v,name,json.dumps(definition,sort_keys=True),author))
            if hasattr(self,'_update_file_type_sizes'):self._update_file_type_sizes(v,registry)
            invalidated=[]
            for binding in bindings:
                size=type_layout(binding['type_name'],registry)['size']
                self.db.execute('UPDATE type_bindings SET size=? WHERE version=? AND address=?',(size,v,binding['address']))
                old_layout=type_layout(binding['type_name'],old_registry)
                if old_layout!=type_layout(binding['type_name'],registry) and hasattr(self,'_invalidate_derived'):
                    invalidated+=self._invalidate_derived(v,int(binding['address'],16),max(size,binding['size']),'type definition changed')
            return dict(version=v,name=name,layout=layouts[name],invalidated_tasks=sorted(set(invalidated)))

    def types(self,version=None):
        with self.transaction():
            v=self.version(version)['id'];registry=self._type_registry(v)
            return dict(version=v,types=[dict(layout=type_layout(name,registry),source='built-in' if name in _BUILTINS else 'user') for name in sorted(set(registry)|set(_BUILTINS))],bindings=[dict(address=hex(int(r['address'],16)),name=r['name'],type=r['type_name'],size=r['size'],author=r['author']) for r in self.db.execute('SELECT * FROM type_bindings WHERE version=? ORDER BY address',(v,))])

    def apply_type(self,address,type_name,name=None,version=None,author='agent'):
        from .project import key
        type_name=_name(type_name)
        if name is not None:_name(name)
        if not isinstance(author,str) or not 1<=len(author)<=256:raise ValueError('author must contain 1..256 characters')
        with self.transaction(True):
            v=self.version(version)['id'];a=self._address(address);layout=type_layout(type_name,self._type_registry(v));size=layout['size']
            region=self._mapping(v,a)
            if region is None or a+size>region.start+len(region.data):raise ValueError('type binding must fit in one mapped region')
            for r in self.db.execute('SELECT address,size FROM type_bindings WHERE version=? AND address!=?',(v,key(a))):
                b=int(r['address'],16)
                if a<b+r['size'] and a+size>b:raise ValueError('type bindings overlap')
            old=self.db.execute('SELECT size FROM type_bindings WHERE version=? AND address=?',(v,key(a))).fetchone()
            self.db.execute('INSERT OR REPLACE INTO type_bindings VALUES (?,?,?,?,?,?)',(v,key(a),name or f'data_{a:x}',type_name,size,author))
            invalidated=self._invalidate_derived(v,a,max(size,old[0] if old else 0),'type binding changed') if hasattr(self,'_invalidate_derived') else []
            return dict(version=v,address=hex(a),type=layout,name=name or f'data_{a:x}',invalidated_tasks=invalidated)

    def _raw_type_location(self,v,a):
        from .project import key
        row=self.db.execute('SELECT * FROM type_bindings WHERE version=? AND address<=? ORDER BY address DESC LIMIT 1',(v,key(a))).fetchone()
        if row is None:return None
        base=int(row['address'],16)
        if a>=base+row['size']:return None
        layout=type_layout(row['type_name'],self._type_registry(v));field=_field_at(layout,a-base)
        annotation=self.db.execute("SELECT text FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'",(v,self.context,row['address'])).fetchone()
        # A linked first field is distinct from its enclosing structural root.
        shared_root=hasattr(self,'_native_is_shared') and self._native_is_shared(v,base)
        root_name=annotation[0] if annotation and not shared_root else row['name']
        return dict(binding_address=hex(base),binding_name=root_name,binding_type=row['type_name'],name=root_name+field['path'],**field)

    def _type_location(self,v,a):
        return self._raw_type_location(v,a)

    def _typed_label(self,v,a,original):
        from .project import key
        if self.db.execute("SELECT 1 FROM annotations WHERE version=? AND context=? AND address=? AND kind='name'",(v,self.context,key(a))).fetchone():return original
        location=self._type_location(v,a)
        return location['name'] if location else original

    def _label(self,v,a):return self._typed_label(v,a,super()._label(v,a))
    def _dos_label(self,v,a,context=None):return self._typed_label(v,a,super()._dos_label(v,a,context))

    def _presentation(self,v,a):
        shown=super()._presentation(v,a);location=self._type_location(v,a)
        if location:shown={**shown,'name':self._typed_label(v,a,shown['name']),'type':location}
        return shown

    def _dos_presentation(self,v,a,context=None):
        shown=super()._dos_presentation(v,a,context);location=self._type_location(v,a)
        if location:shown={**shown,'name':self._typed_label(v,a,shown['name']),'type':location}
        return shown

    def locate(self,address,version=None,cs=None):
        result=super().locate(address,version,cs)
        a=self._address(address);v=result['version']
        if self._type_location(v,a):
            result['presentation']=self._boundary_presentation(v,a,result.get('requested_context'))
        return result

    def typed_data(self,address,version=None,max_items=256):
        from .project import integer,key
        max_items=integer(max_items,'max_items',1,4096)
        with self.transaction():
            v=self.version(version)['id'];a=self._address(address)
            row=self.db.execute('SELECT * FROM type_bindings WHERE version=? AND address=?',(v,key(a))).fetchone()
            if row is None:raise ValueError('typed-data requires an exact type binding address')
            layout=type_layout(row['type_name'],self._type_registry(v));region=self._mapping(v,a);items=[];truncated=False
            def visit(t,offset,path):
                nonlocal truncated
                if len(items)>=max_items:truncated=True;return
                if t['kind']=='struct':
                    for f in t['fields']:visit(f['type'],offset+f['offset'],path+'.'+f['name'])
                elif t['kind']=='array':
                    for index in range(t['count']):
                        if len(items)>=max_items:truncated=True;break
                        visit(t['element'],offset+index*t['element']['size'],path+f'[{index}]')
                else:
                    raw=region.data[a-region.start+offset:a-region.start+offset+t['size']]
                    value=int.from_bytes(raw,'little',signed=t.get('signed',False));item=dict(address=hex(a+offset),path=path,type=t['name'],size=t['size'],bytes=raw.hex(),value=value)
                    if t['kind']=='pointer':
                        target=(int.from_bytes(raw[2:],'little')*16+int.from_bytes(raw[:2],'little') if t['address_space']=='far16' else t['segment']*16+value if t['address_space']=='near' and t['segment'] is not None else value if t['address_space']=='flat' else None)
                        item.update(target=hex(target) if target is not None else None,target_type=t['target'],target_mapped=bool(target is not None and self._mapping(v,target)),target_name=self._label(v,target) if target is not None else None,assumption='retained snapshot pointer value; not runtime memory')
                    item['name']=self._label(v,a+offset)
                    items.append(item)
            visit(layout,0,self._type_location(v,a)['binding_name'])
            return dict(version=v,address=hex(a),layout=layout,items=items,truncated=truncated,source='immutable mapped bytes; user-assigned structural interpretation')
