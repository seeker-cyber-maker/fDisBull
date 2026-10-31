"""Versioned structural types over physical data identity, independent of ISA/container."""
from __future__ import annotations
import json
import re
from .type_catalog import TypeCatalogMixin

TYPE_DDL = """
CREATE TABLE IF NOT EXISTS type_definitions(version INTEGER NOT NULL,name TEXT NOT NULL,document TEXT NOT NULL,author TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(version,name));
CREATE TABLE IF NOT EXISTS type_catalog_origins(version INTEGER NOT NULL,name TEXT NOT NULL,definition_sha256 TEXT NOT NULL,author TEXT NOT NULL,document TEXT NOT NULL,PRIMARY KEY(version,name));
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


def _rich_value(layout,value):
    if 'bit_range' in layout:
        field=layout['bit_range'];width=field['width']
        value=(value>>field['lsb'])&((1<<width)-1)
        if field['signed'] and value&(1<<(width-1)):value-=1<<width
        return dict(value=value,bit_range=dict(field))
    if layout['kind']=='enum':
        matches=[name for name,number in layout['members'].items() if number==value]
        if not layout['flags']:return dict(symbols=matches)
        if matches:return dict(symbols=matches,unknown_bits=0)
        selected=[];known=0
        for name,number in layout['members'].items():
            if number and number&value==number:
                selected.append(name);known|=number
        return dict(symbols=selected,unknown_bits=value&~known)
    return {}


def type_layout(name, registry, active=(), _budget=None):
    """Validate a named layout. Pointer recursion does not recurse by value."""
    if _budget is None:_budget=[65536,4096]
    _budget[0]-=1
    if _budget[0]<0:raise ValueError('type expansion exceeds 65536 nodes/members')
    if name in active or len(active)>32:
        raise ValueError('recursive by-value type or nesting exceeds 32 levels')
    raw=registry.get(name,_BUILTINS.get(name))
    if not isinstance(raw,dict):
        raise ValueError(f'unknown type: {name}')
    kind=raw.get('kind')
    if kind=='typedef':
        target=type_layout(_name(raw.get('target')),registry,active+(name,),_budget)
        return dict(name=name,kind=kind,size=target['size'],target=target)
    if kind=='enum':
        size=_int(raw.get('size'),'enum size',1,8)
        signed=raw.get('signed',False);flags=raw.get('flags',False)
        if type(signed) is not bool or type(flags) is not bool or flags and signed:
            raise ValueError('enum signed/flags must be booleans; flags are unsigned')
        members=raw.get('members')
        if not isinstance(members,dict) or not 1<=len(members)<=1024:
            raise ValueError('enum requires 1..1024 named members')
        _budget[0]-=len(members)
        if _budget[0]<0:raise ValueError('type expansion exceeds 65536 nodes/members')
        low=-(1<<(size*8-1)) if signed else 0
        high=(1<<(size*8-int(signed)))-1
        for member,value in members.items():
            _name(member);_int(value,'enum value',low,high)
        return dict(name=name,kind=kind,size=size,signed=signed,flags=flags,members=dict(members))
    if kind=='bitfield':
        size=_int(raw.get('size'),'bitfield storage size',1,8)
        fields=raw.get('fields')
        if not isinstance(fields,list) or not 1<=len(fields)<=64:
            raise ValueError('bitfield requires 1..64 fields')
        _budget[0]-=len(fields)
        if _budget[0]<0:raise ValueError('type expansion exceeds 65536 nodes/members')
        names=set();occupied=0;result=[]
        for field in fields:
            field_name=_name(field.get('name'))
            lsb=_int(field.get('lsb'),'lsb',0,size*8-1)
            width=_int(field.get('width'),'width',1,size*8)
            signed=field.get('signed',False)
            mask=((1<<width)-1)<<lsb
            if field_name in names or lsb+width>size*8 or mask&occupied or type(signed) is not bool:
                raise ValueError('duplicate, overlapping or out-of-range bitfield')
            names.add(field_name);occupied|=mask
            result.append(dict(name=field_name,lsb=lsb,width=width,signed=signed))
        return dict(name=name,kind=kind,size=size,fields=result)
    if kind=='function':
        from .frames import ABI_PROFILES
        abi=raw.get('abi');arguments=raw.get('arguments');variadic=raw.get('variadic',False)
        if abi not in ABI_PROFILES or type(variadic) is not bool:
            raise ValueError('function requires a known ABI and boolean variadic')
        if not isinstance(arguments,list) or len(arguments)>64:
            raise ValueError('function requires at most 64 named arguments')
        if variadic and ABI_PROFILES[abi].get('argument_order')=='left_to_right':
            raise ValueError('Pascal variadic argument placement is unsupported')
        returns=type_layout(_name(raw['returns']),registry,active+(name,),_budget) if raw.get('returns') is not None else None
        if returns is not None and not returns['size']:raise ValueError('return type must have storage')
        names=set();args=[]
        for argument in arguments:
            argname=_name(argument.get('name'))
            argtype=type_layout(_name(argument.get('type')),registry,active+(name,),_budget)
            if argname in names or not argtype['size']:raise ValueError('argument requires unique name and storage type')
            names.add(argname);args.append(dict(name=argname,type=argtype))
        return dict(name=name,kind=kind,size=0,returns=returns,arguments=args,abi=abi,variadic=variadic)
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
        layout=type_layout(element,registry,active+(name,),_budget);size=count*layout['size']
        if size>1<<20 or not size:raise ValueError('array requires storage and must not exceed 1 MiB')
        return dict(name=name,kind=kind,size=size,element=layout,count=count)
    if kind in ('struct','union'):
        if kind=='union':
            _budget[1]-=1
            if _budget[1]<0:raise ValueError('union expansion exceeds 4096 instances')
        size=_int(raw.get('size'),'structure size',1)
        fields=raw.get('fields')
        if not isinstance(fields,list) or len(fields)>1024:raise ValueError('fields must be a list of at most 1024 entries')
        result=[];names=set()
        for field in fields:
            if not isinstance(field,dict):raise ValueError('field must be an object')
            field_name=_name(field.get('name'))
            if field_name in names:raise ValueError('duplicate field name')
            names.add(field_name)
            offset=_int(field.get('offset',0) if kind=='union' else field.get('offset'),'field offset')
            if kind=='union' and offset!=0:raise ValueError('union members must start at offset zero')
            layout=type_layout(_name(field.get('type')),registry,active+(name,),_budget)
            if not layout['size']:raise ValueError('field type requires storage')
            if offset+layout['size']>size:raise ValueError('field exceeds structure size')
            if kind=='struct' and any(offset<previous['offset']+previous['type']['size'] and offset+layout['size']>previous['offset'] for previous in result):
                raise ValueError('overlapping structure fields require a separately defined representation')
            result.append(dict(name=field_name,offset=offset,type=layout))
        return dict(name=name,kind=kind,size=size,fields=sorted(result,key=lambda f:f['offset']))
    raise ValueError('unsupported type kind')


def _field_at(layout,offset,path=''):
    if layout['kind']=='typedef':return _field_at(layout['target'],offset,path)
    if layout['kind'] in ('union','bitfield'):
        return dict(path=path+(f'+0x{offset:x}' if offset else ''),byte_offset=offset,
                    type_name=layout['name'],kind=layout['kind'],size=layout['size'],
                    alternatives=[path+'.'+f['name'] for f in layout['fields']],active_member=None)
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


class TypeSystemMixin(TypeCatalogMixin):
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
                if not size:raise ValueError('bound data type must retain storage')
                if region is None or address+size>region.start+len(region.data):raise ValueError('updated type binding exceeds its mapped region')
                if address<previous_end:raise ValueError('updated type bindings would overlap')
                previous_end=address+size
            if hasattr(self,'_validate_file_types'):self._validate_file_types(v,registry)
            self._forget_type_origin(v,name,definition,author)
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

    def set_function_type(self,address,type_name,version=None,cs=None,author='agent'):
        """Freeze an authored prototype into the existing versioned summary seam."""
        from copy import deepcopy
        from .frames import ABI_PROFILES
        with self.transaction(True):
            v,context,a=self._advanced_identity(address,cs,version)
            layout=type_layout(_name(type_name),self._type_registry(v))
            while layout['kind']=='typedef':layout=layout['target']
            if layout['kind']!='function':raise ValueError('set-function-type requires a function type')
            abi=deepcopy(ABI_PROFILES[layout['abi']])
            if abi['arch']!=self.arch or abi['bits']!=self.bits:raise ValueError('function ABI does not match project architecture')
            # Only the DOS stack conventions have typed placement here. Other
            # ABIs retain their existing register/stack candidate model.
            if self.arch=='x86' and self.bits==16:
                offset=0;placements=[]
                indices=list(range(len(layout['arguments'])))
                if abi.get('argument_order')=='left_to_right':indices.reverse()
                for index in indices:
                    arg=layout['arguments'][index];width=arg['type']['size']
                    placements.append(dict(index=index,name=arg['name'],offset=offset,width=width))
                    offset+=(width+1)//2*2
                abi['parameter_layout']=sorted(placements,key=lambda item:item['index'])
                if abi.get('argument_order')=='left_to_right':abi['callee_cleanup']=offset
            prototype=dict(arguments=[dict(name=arg['name'],type=arg['type']['name']) for arg in layout['arguments']],
                           declared_function_type=type_name,layout_snapshot=layout)
            label=self._dos_label(v,a,context) if self.meta['format'] in ('MZ', 'COM') else self._label(v,a)
            return self.set_summary(address,label,version=v,cs=cs,prototype=prototype,abi=abi,author=author)

    def apply_type(self,address,type_name,name=None,version=None,author='agent'):
        from .project import key
        type_name=_name(type_name)
        if name is not None:_name(name)
        if not isinstance(author,str) or not 1<=len(author)<=256:raise ValueError('author must contain 1..256 characters')
        with self.transaction(True):
            v=self.version(version)['id'];a=self._address(address);layout=type_layout(type_name,self._type_registry(v));size=layout['size']
            if not size:raise ValueError('function types have no data storage; bind a pointer or set a function prototype')
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
                if t['kind']=='typedef':
                    visit(dict(t['target'],name=t['name']),offset,path)
                elif t['kind'] in ('struct','union'):
                    for f in t['fields']:visit(f['type'],offset+f['offset'],path+'.'+f['name'])
                elif t['kind']=='bitfield':
                    for field in t['fields']:
                        visit(dict(name=t['name'],kind='scalar',size=t['size'],bit_range=field),offset,path+'.'+field['name'])
                elif t['kind']=='array':
                    for index in range(t['count']):
                        if len(items)>=max_items:truncated=True;break
                        visit(t['element'],offset+index*t['element']['size'],path+f'[{index}]')
                else:
                    raw=region.data[a-region.start+offset:a-region.start+offset+t['size']]
                    value=int.from_bytes(raw,'little',signed=t.get('signed',False));item=dict(address=hex(a+offset),path=path,type=t['name'],size=t['size'],bytes=raw.hex(),value=value)
                    item.update(_rich_value(t,value))
                    if t['kind']=='pointer':
                        target=(int.from_bytes(raw[2:],'little')*16+int.from_bytes(raw[:2],'little') if t['address_space']=='far16' else t['segment']*16+value if t['address_space']=='near' and t['segment'] is not None else value if t['address_space']=='flat' else None)
                        item.update(target=hex(target) if target is not None else None,target_type=t['target'],target_mapped=bool(target is not None and self._mapping(v,target)),target_name=self._label(v,target) if target is not None else None,assumption='retained snapshot pointer value; not runtime memory')
                        if self.meta['format'] == 'NE':
                            # Win16 selectors/near offsets are not DOS paragraph
                            # bases or packed logical segment-index keys.
                            item.update(target=None, target_mapped=False, target_name=None,
                                        assumption='encoded NE pointer value only; runtime selector/segment binding is unknown')
                            if t['address_space'] == 'far16':
                                item.update(encoded_offset=int.from_bytes(raw[:2], 'little'),
                                            encoded_selector=int.from_bytes(raw[2:], 'little'))
                        target_type=type_layout(t['target'],self._type_registry(v))
                        while target_type['kind']=='typedef':target_type=target_type['target']
                        if target_type['kind']=='function':item['prototype']=target_type
                    item['name']=self._label(v,a+offset)
                    items.append(item)
            visit(layout,0,self._type_location(v,a)['binding_name'])
            return dict(version=v,address=hex(a),layout=layout,items=items,truncated=truncated,source='immutable mapped bytes; user-assigned structural interpretation')
