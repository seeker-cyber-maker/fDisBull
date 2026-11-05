"""Runtime support for already generated Python functions, not an IR interpreter.

Source-specific parser, object storage, text fallback, and save semantics are
explicit retained services. The game logic executes as Python functions.
"""
from __future__ import annotations
import copy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sys

from asset_package import Package, PackageError, canonical, exact, parse_json, sha
from state_services import StateServices, Word16Error, _integer, _u16, MAX_FRAMES, MAX_TEXT


class Globals:
    """240 typed slots alias the authoritative dynamic-memory bytes."""
    def __init__(self, machine): self.machine = machine
    def __len__(self): return 240
    def __getitem__(self,index):
        _integer(index,'global index',0,239)
        return self.machine._read(self.machine.layout['globals'] + 2*index,16)
    def __setitem__(self,index,value):
        _integer(index,'global index',0,239)
        self.machine._write(self.machine.layout['globals'] + 2*index,16,_u16(value))


class MemoryView:
    """Named, non-duplicated views for analysis; no invented semantic labels."""
    def __init__(self,machine):
        self.machine=machine
        self.globals=Globals(machine)
    @property
    def locals(self): return self.machine.frames[-1]['locals']
    @property
    def stack(self): return self.machine.stack
    def flag(self,obj,bit): return self.machine.attribute_test(obj,bit)
    def set_flag(self,obj,bit,value):
        if type(value) is not bool: raise Word16Error('Flag value must be boolean')
        (self.machine.attribute_set if value else self.machine.attribute_clear)(obj,bit)


class DirectGame(StateServices):
    """A continuation scheduler over native Python functions, with owned state."""
    def __init__(self, root, *, seed=12, strict_text=False, random_tape=None):
        self.root=Path(root).resolve()
        lock_data=(self.root/'product.json').read_bytes()
        lock=parse_json(lock_data)
        exact(lock,('format','files'),'product lock')
        if lock['format']!='fdisbull-z3-python-product-1' or not isinstance(lock['files'],dict):
            raise PackageError('Invalid product lock')
        if not 1 <= len(lock['files']) <= 1024: raise PackageError('Product file budget')
        total=0
        for name,digest in lock['files'].items():
            if (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_./-]+',name)
                    or name.startswith('/') or '..' in name or '//' in name):
                raise PackageError('Unsafe product path')
            path=self.root/name
            if path.is_symlink() or self.root not in path.resolve().parents:
                raise PackageError('External product file')
            total+=path.stat().st_size
            if total > 128*1024*1024: raise PackageError('Product byte budget')
            if sha(path.read_bytes())!=digest: raise PackageError('Product file digest mismatch: '+name)
        self.product_digest=sha(lock_data)
        spec=parse_json((self.root/'program.json').read_bytes())
        if spec['format']!='fdisbull-z3-python-code-1': raise PackageError('Wrong code format')
        self.spec=spec
        mp=Package.read(self.root/'media.zip')
        state=Package.read(self.root/'memory.zip')
        if mp.digest!=spec['media_sha256'] or state.digest!=spec['memory_sha256']:
            raise PackageError('Media/state identity mismatch')
        schema=parse_json(state.get('state.layout','layout'))
        if schema['format']!='fdisbull-z3-memory-layout-1': raise PackageError('Wrong memory layout')
        dynamic=state.get('state.dynamic','state-template')
        readonly=state.get('state.readonly','readonly-data')
        self.initial=dynamic+readonly
        self.writable_end=schema['writable_end']
        self.layout=schema['layout']
        if self.writable_end!=len(dynamic) or self.layout['declared_bytes']!=len(self.initial):
            raise PackageError('Invalid memory partition')
        self.program={'entry':spec['entry']}
        self.package_digest=spec['program_sha256']  # reference snapshot compatibility
        self.blocks=set(spec['block_ids'])
        self.functions={int(k):v for k,v in spec['functions'].items()}
        self.seed=_integer(seed,'seed',0,0xffffffff)
        self.random_tape=self._validate_tape(random_tape)
        self.executed_blocks=set()
        self._game_slot=None
        self._shards={}
        self._initialize()
        self.state=MemoryView(self)
        self.strict_text=strict_text
        self.asset_hits=self.codec_misses=self.codec_calls=self.changed_dependencies=0
        self.text_requests=set()
        index=parse_json(mp.get('text.index','binding'))
        if index['format']!='fdisbull-text-bindings-1': raise PackageError('Wrong text index')
        self._texts={}
        for key,entry in index['bindings'].items():
            text=mp.get(entry['asset'],'text').decode('utf-8')
            if len(text)>MAX_TEXT: raise PackageError('Text budget')
            end=-1
            for span in entry['reads']:
                if (len(span)!=2 or any(type(x) is not int for x in span)
                        or span[0]<0 or span[1]<=0 or span[0]+span[1]>len(self.initial)
                        or span[0]<end):
                    raise PackageError('Invalid text guard')
                end=span[0]+span[1]
            if not entry['reads']: raise PackageError('Missing text guard')
            self._texts[key]=(text,entry['reads'])

    def _resolve(self,pc):
        shard=pc >> self.spec['shard_bits']
        if shard not in self._shards:
            path=self.root/'game_code'/f'b{shard:03x}.py'
            # Load exact checked source. No IR evaluation and no dependency on cwd.
            name='_z3_'+self.product_digest[:16]+f'_{shard:03x}'
            spec=importlib.util.spec_from_file_location(name,path)
            module=importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            self._shards[shard]=module.BLOCKS
        try:return self._shards[shard][pc]
        except KeyError as exc:raise Word16Error(f'Missing generated continuation {pc:#x}') from exc

    def guard_code(self,pc,size):
        if self.memory[pc:pc+size]!=self.initial[pc:pc+size]:
            raise Word16Error(f'Unsupported self-modified code at {pc:#x}')

    def run(self,max_steps=2_000_000):
        _integer(max_steps,'step budget',1,100_000_000)
        if self.fault is not None:raise Word16Error('Execution is faulted; restore a qualified checkpoint')
        steps=0
        try:
            while not self.halted and self.pending_input is None and steps<max_steps:
                if self.pc not in self.blocks:raise Word16Error(f'Missing generated continuation {self.pc:#x}')
                block=self._resolve(self.pc)
                self.executed_blocks.add(self.pc)
                steps+=1
                block(self)
        except (Word16Error,IndexError,KeyError,TypeError,OverflowError,UnboundLocalError) as exc:
            self.fault=str(exc)
            raise Word16Error(f'Python execution failed at {self.pc:#x}: {exc}') from exc
        status='halted' if self.halted else 'input' if self.pending_input is not None else 'budget_exhausted'
        result={'status':status,'text':''.join(self._text),'steps':steps,'pc':self.pc,
                **self._score(),'events':self._events}
        if self.halt_reason is not None:result['halt_reason']=self.halt_reason
        self._text,self._events,self._text_size=[],[],0
        return result

    def call_function(self,target,args,store,resume):
        _integer(target,'call target',0,len(self.memory)-1)
        for v in args:_integer(v)
        if target==0:
            self._write_var(store,0);self._goto(resume);return
        if target not in self.functions:raise Word16Error(f'Missing lowered function target {target:#x}')
        f=self.functions[target]
        if self.memory[target:target+f['guard_bytes']]!=self.initial[target:target+f['guard_bytes']]:
            raise Word16Error('Unsupported self-modified function header')
        if len(self.frames)>=MAX_FRAMES:raise Word16Error('Call frame budget exceeded')
        local=list(f['locals'])
        for i,v in enumerate(args[:len(local)]):local[i]=_u16(v)
        self.frames.append({'locals':local,'base':len(self.stack),'resume':resume,'store':store})
        self._goto(f['entry'])

    def request_input(self,text,parse,resume):
        self._bounds(text,1,True)
        if parse:self._bounds(parse,2,True)
        self._host('status',[])
        self.pending_input={'text':text,'parse':parse,'resume':resume}
        self.pc=resume

    def save_path(self,callback,resume):
        if not callback():self._goto(resume)
        self._game_slot=self._state(include_slot=False,include_output=False)
        self._events.append({'type':'save','success':True})

    def restore_path(self,callback,resume):
        if self._game_slot is None:
            if not callback():self._goto(resume)
            self._events.append({'type':'restore','success':False})
        else:
            text,events,size=self._text,self._events,self._text_size
            flags=bytes(self.memory[16:18]);slot=self._game_slot
            self.restore(slot);self._game_slot=slot
            self.memory[16:18]=flags
            self.host['transcript']=bool(int.from_bytes(flags,'big')&1)
            self._text,self._events,self._text_size=text,events,size
            self._events.append({'type':'restore','success':True})

    def restart_game(self):
        text,events,size=self._text,self._events,self._text_size
        self._initialize(bytes(self.memory[16:18]))
        self._text,self._events,self._text_size=text,events,size
        self._events.append({'type':'restart'})

    def _decode_text(self,address,seen=(),limit=None):
        if not seen:self.text_requests.add((address,limit))
        key=str(address)+(':'+str(limit) if limit is not None else ':*')
        item=self._texts.get(key)
        if not seen and item is not None:
            text,guards=item
            if all(self.memory[a:a+n]==self.initial[a:a+n] for a,n in guards):
                self.asset_hits+=1;return text
            self.changed_dependencies+=1
        self.codec_calls+=1
        if not seen:self.codec_misses+=1
        if self.strict_text:raise Word16Error('Unresolved or changed media binding: '+key)
        return super()._decode_text(address,seen=seen,limit=limit)

    # Direct named support functions replace the generic layout-operation switch.
    def tree_parent(self,obj):return self._link(_integer(obj),4)
    def tree_sibling(self,obj):return self._link(_integer(obj),5)
    def tree_child(self,obj):return self._link(_integer(obj),6)
    def tree_detach(self,obj):return self._detach(obj)
    def tree_name(self,obj):
        table=self._read(self._object(obj)+7,16)
        words=self._read(table)
        return self._decode_text(table+1,limit=table+1+words*2) if words else ''
    def tree_insert(self,obj,destination):
        self._object(obj);dest=self._object(destination)
        ancestor,seen=destination,set()
        while ancestor:
            if ancestor==obj or ancestor in seen:raise Word16Error('Insertion would create an object cycle')
            seen.add(ancestor);ancestor=self._link(ancestor,4)
        self._detach(obj);record=self._object(obj);first=self._read(dest+6)
        self._write(record+4,8,destination);self._write(record+5,8,first);self._write(dest+6,8,obj)
    def _attribute(self,obj,bit):
        _integer(bit,'attribute bit',0,31)
        at=self._object(obj)+bit//8
        return at,128>>(bit%8),self._read(at)
    def attribute_test(self,obj,bit):
        _,mask,old=self._attribute(obj,bit);return bool(old&mask)
    def attribute_set(self,obj,bit):
        at,mask,old=self._attribute(obj,bit);self._write(at,8,old|mask)
    def attribute_clear(self,obj,bit):
        at,mask,old=self._attribute(obj,bit);self._write(at,8,old&~mask)
    def _property(self,obj,number,allow_zero=False):
        _integer(number,'property number',0 if allow_zero else 1,31)
        values=self._properties(obj)
        return values,next((r for r in values if r[0]==number),None)
    def property_get(self,obj,number):
        _,match=self._property(obj,number)
        if match is None:return self._read(self.layout['objects']+2*(number-1),16)
        _,at,size=match
        if size not in (1,2):raise Word16Error('Scalar property must occupy one or two bytes')
        return self._read(at,size*8)
    def property_address(self,obj,number):
        _,match=self._property(obj,number);return match[1] if match else 0
    def property_next(self,obj,number):
        values,match=self._property(obj,number,True)
        if number==0:return values[0][0] if values else 0
        if match is None:raise Word16Error('Requested property does not exist')
        index=values.index(match)+1
        return values[index][0] if index<len(values) else 0
    def property_length(self,address):
        _integer(address)
        return 0 if address==0 else (self._read(address-1)>>5)+1
    def property_put(self,obj,number,value):
        _,match=self._property(obj,number)
        if match is None:raise Word16Error('Requested property does not exist')
        _,at,size=match
        if size not in (1,2):raise Word16Error('Scalar property must occupy one or two bytes')
        self._write(at,size*8,value)
    def text_decode(self,address):return self._decode_text(address)
    def text_character(self,number):return self._character(number)
    def text_number(self,number):return str(_integer(number))

    def memory_container(self):
        """Export mutable storage and continuation without redundant global copies."""
        def split(state):
            out=copy.deepcopy(state)
            raw=bytes.fromhex(out.pop('memory'))
            out['dynamic_hex']=raw[:self.writable_end].hex()
            if out['game_slot'] is not None:out['game_slot']=split(out['game_slot'])
            return out
        return {'format':'fdisbull-z3-python-live-memory-1','product_sha256':self.product_digest,
                'media_sha256':self.spec['media_sha256'],'memory_sha256':self.spec['memory_sha256'],
                'state':split(self.snapshot())}

    def restore_memory_container(self,container):
        exact(container,('format','product_sha256','media_sha256','memory_sha256','state'),'live memory')
        if (container['format']!='fdisbull-z3-python-live-memory-1'
                or container['product_sha256']!=self.product_digest
                or container['media_sha256']!=self.spec['media_sha256']
                or container['memory_sha256']!=self.spec['memory_sha256']):
            raise PackageError('Live memory belongs to another product or asset set')
        def join(state,depth=0):
            if depth>1:raise PackageError('Nested save slots refused')
            out=copy.deepcopy(state)
            if 'memory' in out:raise PackageError('Duplicate memory backing')
            h=out.pop('dynamic_hex')
            if not isinstance(h,str) or len(h)!=self.writable_end*2 or not re.fullmatch('[0-9a-f]*',h):
                raise PackageError('Invalid dynamic memory')
            out['memory']=h+self.initial[self.writable_end:].hex()
            if out['game_slot'] is not None:out['game_slot']=join(out['game_slot'],depth+1)
            return out
        # Reference restore validates all fields before mutating the live instance.
        self.restore(join(container['state']))
