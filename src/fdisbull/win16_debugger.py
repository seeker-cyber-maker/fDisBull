"""Original NE debugging through observed Wine16 selectors in an owned guest.

The 32-bit winevdm carrier is bootstrap code, never the original NE entry.
Wine's register callback is stopped before the original entry executes; its
prepared CS:IP and DS, live LDT descriptors, and retained source bytes establish
the first mappings. Logical segment indices are never DOS paragraphs.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import struct
import time
import uuid

from .debugger import DebugSession, bounded, stamp
from .dosbox_rpc import DebuggerError
from .external_files import _file_name
from .ne import load_ne, parse_address
from .windows_ui import WindowsUIMixin
from .wine_rpc import WineQemuRPC


def _integer(value, name='integer'):
    if isinstance(value, str):
        try:value=int(value, 0)
        except ValueError:raise ValueError('Invalid '+name) from None
    if type(value) is not int or not 0 <= value <= 0xffffffffffffffff:
        raise ValueError('Invalid '+name)
    return value


def _descriptor_signature(value):
    """Only actual descriptor fields define an address binding, not a stop count."""
    return tuple(value[k] for k in ('selector','base','limit','present','default_big','type','dpl'))


class RemotePEExports:
    """Bounded observed PE export lookup used only for the Wine loader seam."""
    def __init__(self, read, modules):
        self.read=read
        self.modules=[m for m in modules if m.get('bits') == 32]

    def _read(self, module, rva, length):
        size=_integer(module['size'],'module size')
        if not 0 <= rva <= size or not 0 <= length <= size-rva:
            raise DebuggerError('Loader export exceeds the observed module')
        base=_integer(module['base'],'module base')
        return b''.join(self.read(base+start,min(32768,rva+length-start))
                        for start in range(rva,rva+length,32768))

    def _string(self, module, rva):
        size=_integer(module['size'])
        data=self._read(module,rva,min(256,size-rva))
        if b'\0' not in data:raise DebuggerError('Unterminated loader export name')
        try:return data.split(b'\0',1)[0].decode('ascii')
        except UnicodeError:raise DebuggerError('Non-ASCII loader export name') from None

    @staticmethod
    def _name(module):
        return str(module.get('name','')).replace('\\','/').rsplit('/',1)[-1].casefold()

    def resolve(self, module, symbol, seen=()):
        identity=(_integer(module['base']),str(symbol))
        if identity in seen or len(seen)>=8:raise DebuggerError('Loader export forwarding cycle')
        dos=self._read(module,0,64)
        pe=struct.unpack_from('<I',dos,60)[0]
        if dos[:2]!=b'MZ' or not 64<=pe<=1048576:
            raise DebuggerError('Loader module lacks a bounded PE header')
        header=self._read(module,pe,128)
        if header[:4]!=b'PE\0\0' or struct.unpack_from('<HH',header,4)[0]!=0x14c or struct.unpack_from('<H',header,24)[0]!=0x10b:
            raise DebuggerError('Expected an observed I386 loader module')
        er,es=struct.unpack_from('<II',header,24+96)
        if not er or es<40:return None
        fields=struct.unpack('<IIHHIIIIIII',self._read(module,er,40))
        ordinal_base,functions,names,fa,na,oa=fields[5:]
        if not 0<functions<=65536 or names>functions:
            raise DebuggerError('Loader export table exceeds its budget')
        if isinstance(symbol,int):index=symbol-ordinal_base
        else:
            # PE named exports are sorted; never transfer or scan a whole DLL.
            low,high=0,names;index=-1
            while low<high:
                mid=(low+high)//2
                nr=struct.unpack('<I',self._read(module,na+mid*4,4))[0]
                text=self._string(module,nr)
                if text<symbol:low=mid+1
                elif text>symbol:high=mid
                else:
                    index=struct.unpack('<H',self._read(module,oa+mid*2,2))[0];break
        if not 0<=index<functions:return None
        address=struct.unpack('<I',self._read(module,fa+index*4,4))[0]
        if not address:return None
        if er<=address<er+es:
            forward=self._string(module,address)
            library,separator,target=forward.rpartition('.')
            if not separator:raise DebuggerError('Invalid loader export forwarder')
            selected=[m for m in self.modules if self._name(m) in (library.casefold(),library.casefold()+'.dll')]
            if len(selected)!=1:raise DebuggerError('Forwarded loader module is not uniquely observed')
            return self.resolve(selected[0],int(target[1:]) if target.startswith('#') else target,seen+(identity,))
        self._read(module,address,1)
        return dict(address=_integer(module['base'])+address,module=module['name'],
                    module_base=module['base'],module_generation=module['generation'],symbol=str(symbol))

    def callback(self):
        candidates=[m for m in self.modules if self._name(m) in ('krnl386.exe16','wow32.dll','kernel32.dll')]
        for preferred in ('krnl386.exe16','wow32.dll','kernel32.dll'):
            for module in candidates:
                if self._name(module)!=preferred:continue
                for symbol in ('K32WOWCallback16Ex','WOWCallback16Ex'):
                    result=self.resolve(module,symbol)
                    if result:return result
        raise DebuggerError('Wine16 register callback is not loaded at the observed carrier entry')


class Win16DebugSession(WindowsUIMixin):
    rpc_type=WineQemuRPC
    backend_name='wine-ne-qemu'
    register_edits_available=False
    register_context_contract=('verified live 16-bit LDT: GetThreadContext low32 projection; '
        'ordinary 32-bit stops: Wow64GetThreadContext; context_source identifies the observed API view')
    native_hooks_available=False
    script_operations={'run','step','trace','breakpoint','delete-breakpoint','registers','write-registers','memory',
        'write-memory','status','assert','click','click-frame','screenshot',
        'keyboard.press','keyboard.type','keyboard.state','keyboard.key-down','keyboard.key-up','frame-probe','scene-check','scene-assert',
        'scene-click','scene-act','scene-wait','wait'}
    _artifact=DebugSession._artifact
    script=DebugSession.script
    click_frame=DebugSession.click_frame
    __enter__=DebugSession.__enter__
    __exit__=DebugSession.__exit__
    machine=DebugSession.machine
    contexts=DebugSession.contexts
    context=DebugSession.context

    def __init__(self, project, executable, game_dir, *, kernel, initramfs,
                 version=None, files=None, boot_timeout_ms=240000,state=None,window=False,memory_mib=4096):
        self.project=project;self.rpc=None;self.closed=False;self.run_id=uuid.uuid4().hex
        self.bits=16
        self.version=project.version(version)
        if project.meta['format']!='NE' or project.meta['arch']!='x86' or project.bits!=16 or self.version['parent'] is not None:
            raise ValueError('Win16 launch requires the original unpatched Windows NE version')
        if state is not None:raise ValueError('Win16 native checkpoint restoration requires separate selector requalification')
        if type(window) is not bool:raise ValueError('window must be boolean')
        if memory_mib is None:memory_mib=4096
        bounded(boot_timeout_ms,'boot_timeout_ms',1000,600000)
        self.game_dir=Path(game_dir).expanduser().resolve(strict=True)
        self.target=project.meta['filename']
        from .guest_assets import uploads
        staged=uploads(project,self.game_dir,self.target,files)
        self.source=next(base64.b64decode(item['data_base64']) for item in staged if item['path']==self.target)
        self.ne=load_ne(self.source).metadata['ne']
        self.bindings={};self.breakpoints={};self.watchpoints={};self._binding_epoch=0
        self._recording=False;self._startup_receipts=[];self._edits={};self.mode_id=0;self._frame=None
        self._segments={s['index']:s for s in self.ne['segments']}
        self.metadata={'backend':self.backend_name,'runtime_profile':'wine11-ne-selector-1',
            'source_sha256':project.meta['source_sha256'],'version_sha256':self.version['sha256'],
            'files':[{'path':item['path'],'sha256':item['sha256']} for item in staged],
            'original_entry_verified':False,'address_mapping':'observed source segment + live LDT selector/offset; no DOS paragraph arithmetic',
            'watch_coverage':'qualified single scalar operands; unresolved selectors or widths refuse',
            'native_hooks_available':False,'native_checkpoints':False,'execution_layers':False,
            'general_register_writes':False,
            'general_register_write_limit':'six checked non-stack GPRs only when the paired native/WOW integer setter is available',
            'register_context_contract':self.register_context_contract}
        try:
            self.rpc=self.rpc_type(executable,kernel,initramfs,boot_timeout_ms=boot_timeout_ms,memory_mib=memory_mib)
            launched=self.call('session.start',{'target':self.target,'profile':'ne','files':staged},timeout_ms=300000)
            if launched.get('bits')!=32 or launched.get('launch_profile')!='win16-ne-carrier':
                raise DebuggerError('Runtime did not expose the actual Win16 carrier bootstrap')
            self.register_edits_available=self.rpc.capabilities.get('win16_integer_pair') is True
            self.rpc.capabilities.update(backend=self.backend_name,architecture='x86',bits=16,carrier_bits=32,
                source_bound_ne_selectors=True,save_states=False,code_layers=False,native_hooks=False,
                register_edit=self.register_edits_available,
                register_context=self.register_context_contract)
            self.metadata['general_register_writes']=self.register_edits_available
            self.metadata.update(runtime_inputs=self.rpc.inputs,guest_runtime=self.rpc.hello,
                target_pid=launched['pid'],carrier_image_base=launched['image_base'],qemu_pid=self.rpc.process.pid)
            self._bootstrap_ne(min(boot_timeout_ms,180000))
            self._windows_ui_initialize(window=window)
            with project.transaction(True):
                project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                    (self.run_id,self.version['id'],stamp(),None,'stopped',json.dumps(self.metadata)))
            self._recording=True
            for operation,evidence in self._startup_receipts:DebugSession._event(self,operation,evidence)
            self._startup_receipts.clear();self._event('launch',launched)
            project._live_debuggers.append(self)
        except BaseException:
            self._windows_ui_close()
            if self.rpc:self.rpc.close()
            self.closed=True
            raise

    def _event(self, operation, evidence):
        if self._recording:DebugSession._event(self,operation,evidence)
        else:self._startup_receipts.append((operation,evidence))

    def call(self, method, params=None, *, timeout_ms=30000):
        if self.closed:raise DebuggerError('Win16 debugger session is closed')
        deadline=getattr(self,'_rpc_deadline',None)
        if deadline is not None:
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:raise TimeoutError('Shared debugger host-time budget expired')
            timeout_ms=min(timeout_ms,remaining)
        return self.rpc.call(method,params or {},timeout_ms=timeout_ms)

    def _read_runtime(self, address, length):
        bounded(length,'length',1,65536)
        result=self.call('read',{'address':address,'length':length})
        raw=base64.b64decode(result['data_base64'],validate=True)
        if len(raw)!=length:raise DebuggerError('Incomplete stopped Win16 memory observation')
        return raw

    def _selector(self, selector):
        selector=_integer(selector,'selector')
        if not 0<selector<=65535 or not selector&4:raise ValueError('Win16 requires an observed LDT selector')
        result=dict(self.call('selector',{'selector':selector}))
        if _integer(result.get('selector'))!=selector or result.get('present') is not True or result.get('default_big') is not False:
            raise DebuggerError('Selector is not an observed present 16-bit descriptor')
        base=_integer(result.get('base'));limit=_integer(result.get('limit'))
        if base+limit>0xffffffff or limit>65535 or result.get('dpl')!=3:
            raise DebuggerError('Win16 descriptor exceeds its source address profile')
        result.update(selector=selector,base=base,limit=limit)
        return result

    def _source_mask(self, index):
        segment=self._segments[index];mask=bytearray(b'\xff'*segment['file_size'])
        for fixup in self.ne['fixups']:
            if fixup['source_segment_index']==index:
                for site in fixup['sources']:
                    for offset in range(site['offset'],site['offset']+fixup['source_width']):mask[offset]=0
        # Windows owns the documented INSTANCEDATA words at the start of DGROUP.
        if index==self.ne['automatic_data_segment_index']:
            mask[:min(16,len(mask))]=b'\0'*min(16,len(mask))
        return mask

    def _source_expected(self,index):
        """Verify the declared Win16 export-prolog ABI with exact expected bytes.

        The loader may replace the compiler's three-byte DS setup at an entry
        table export. This is a specified transform of a recognized original
        prolog, not permission to ignore unexplained code differences.
        """
        segment=self._segments[index]
        original=self.source[segment['file_offset']:segment['file_offset']+segment['file_size']]
        expected=bytearray(original);changes=[]
        if self.ne['automatic_data_segment_index'] and segment['executable']:
            for entry in self.ne['entries']:
                if entry.get('segment_index')!=index:continue
                offset=entry['offset'];before=original[offset:offset+3]
                if before not in (b'\x1e\x58\x90',b'\x8c\xd8\x90'):continue
                after=b'\x8c\xd8\x90'
                if entry['flags']&2:
                    selector=getattr(self,'_loader_ds_selector',None)
                    if selector is None:raise DebuggerError('NE public-data export prolog needs an observed automatic data selector')
                    after=b'\xb8'+struct.pack('<H',selector)
                elif self.ne['module_flags']&2 and entry['flags']&1:after=b'\x90\x90\x90'
                if after!=before:
                    expected[offset:offset+3]=after
                    changes.append(dict(ordinal=entry['ordinal'],offset=offset,source_hex=before.hex(),expected_hex=after.hex()))
        return bytes(expected),changes

    def _bind(self, index, selector, *, reason):
        descriptor=self._selector(selector);segment=self._segments[index]
        if descriptor['limit']+1<segment['allocation_size']:
            raise DebuggerError('Live selector is smaller than its declared NE segment')
        if bool(descriptor['type']&8)!=segment['executable']:
            raise DebuggerError('Live selector code/data type differs from its source segment')
        size=segment['file_size']
        if not size:raise DebuggerError('Allocation-only NE segments require a separately observed loader binding')
        original=self.source[segment['file_offset']:segment['file_offset']+size]
        expected,prologs=self._source_expected(index)
        observed=self._read_runtime(descriptor['base'],size);mask=self._source_mask(index)
        differences=[offset for offset,(a,b,m) in enumerate(zip(expected,observed,mask,strict=True)) if (a^b)&m]
        if sum(bool(x) for x in mask)<16 or differences:
            detail=(', first offset '+hex(differences[0])+' expected '+expected[differences[0]:differences[0]+8].hex()+
                    ' observed '+observed[differences[0]:differences[0]+8].hex()) if differences else ', insufficient unmasked source bytes'
            raise DebuggerError('Loaded NE segment bytes differ outside declared relocation/instance slots'+detail)
        existing=self.bindings.get(index)
        if existing is not None and _descriptor_signature(existing['descriptor'])!=_descriptor_signature(descriptor):
            raise DebuggerError('NE logical segment already has a different live selector binding')
        if any(k!=index and value['selector']==selector for k,value in self.bindings.items()):
            raise DebuggerError('A live selector cannot identify two different logical segments')
        self._binding_epoch+=1
        binding={'segment_index':index,'selector':selector,'base':descriptor['base'],'limit':descriptor['limit'],
            'descriptor':descriptor,'generation':self._binding_epoch,'source_sha256':self.metadata['source_sha256'],
            'source_segment_sha256':hashlib.sha256(original).hexdigest(),
            'verified_loader_export_prologs':prologs,
            'loaded_segment_sha256':hashlib.sha256(observed).hexdigest(),
            'unrelocated_bytes_verified':sum(bool(x) for x in mask),'masked_fixup_or_instance_bytes':sum(not x for x in mask),
            'reason':reason,'task_thread':descriptor['thread'],
            'task_epoch':self.metadata.get('task_identity',{}).get('epoch')}
        self.bindings[index]=binding;self._event('ne-bind-segment',binding)
        return binding

    def _bootstrap_ne(self, timeout_ms):
        started=time.monotonic();deadline=started+timeout_ms/1000
        modules=self.call('modules');exports=RemotePEExports(self._read_runtime,modules['modules'])
        callback=exports.callback();hook=self.call('bp',{'address':callback['address']})
        hook_id=hook['breakpoint_id'];entry_hook=None;prepared=None
        try:
            for _ in range(256):
                remaining=int((deadline-time.monotonic())*1000)
                if remaining<=0:raise TimeoutError('Win16 loader-entry observation budget expired')
                state=self.call('run',{'timeout_ms':remaining},timeout_ms=remaining+15000)
                stop=state['stop_reason']
                if stop['kind']=='exited':raise DebuggerError('Win16 carrier exited before the original entry was observed')
                if stop['kind']!='breakpoint':
                    if stop['kind']=='exception':continue
                    raise DebuggerError('Win16 loader callback was not reached within its declared budget')
                if _integer(stop['address'])!=callback['address']:
                    raise DebuggerError('Unexpected breakpoint during Win16 loader initialization')
                registers=self.call('registers');stack=_integer(registers['general']['esp'])
                fn,flags,length,args,ret=struct.unpack('<IIIII',self._read_runtime(stack+4,20))
                if (fn,flags,length,args)!=(0,2,0,0) or not ret:continue
                context=self._read_runtime(ret,204)
                # I386/WOW64 CONTEXT: segment fields 140..152, EIP/CS 184/188.
                cs,ip=struct.unpack_from('<I',context,188)[0],struct.unpack_from('<I',context,184)[0]
                ds=struct.unpack_from('<I',context,152)[0]
                source_entry=self.ne['logical_entry'];index=source_entry['segment_index']
                if ip!=source_entry['offset']:continue
                # The executable task entry has the declared stack/heap sizes
                # and zero BP. A DLL initializer uses a different register ABI.
                if struct.unpack_from('<I',context,180)[0] or struct.unpack_from('<I',context,164)[0]!=self.ne['stack_size'] or struct.unpack_from('<I',context,172)[0]!=self.ne['heap_size']:
                    continue
                self._loader_ds_selector=ds
                code=self._bind(index,cs,reason='observed Wine register callback before original NE entry')
                data_index=self.ne['automatic_data_segment_index']
                if data_index:
                    self._bind(data_index,ds,reason='observed initial NE automatic data selector before original entry')
                psp=struct.unpack_from('<I',context,148)[0]
                observed_modules=self.call('modules')
                if not any(m['bits']==32 and _integer(m['base'])==_integer(callback['module_base']) and m['generation']==callback['module_generation'] for m in observed_modules['modules']):
                    raise DebuggerError('Wine16 loader module changed during original task qualification')
                self.metadata['task_identity']={'epoch':uuid.uuid4().hex,'thread':registers['thread'],
                    'current_instance_handle':hex(struct.unpack_from('<I',context,156)[0]),
                    'previous_instance_handle':hex(struct.unpack_from('<I',context,160)[0]),
                    'psp_selector':psp,'psp_descriptor':self._selector(psp),
                    'loader_module_base':callback['module_base'],'loader_module_generation':callback['module_generation'],
                    'validated_module_revision':observed_modules['module_revision']}
                for binding in self.bindings.values():binding['task_epoch']=self.metadata['task_identity']['epoch']
                prepared={'callback':callback,'prepared_context_address':hex(ret),'cs':hex(cs),'ip':hex(ip),'ds':hex(ds),
                          'module_revision':modules['module_revision'],'original_entry':source_entry,
                          'source_segment_binding':code,'original_execution_before_entry_hook':False}
                entry_hook=self.call('bp',{'address':code['base']+ip})
                self.call('del',{'id':int(hook_id[3:])});hook_id=None
                break
            else:raise DebuggerError('Win16 loader callback limit reached before a source-bound original entry')
            remaining=max(1,int((deadline-time.monotonic())*1000))
            state=self.call('run',{'timeout_ms':remaining},timeout_ms=remaining+15000)
            regs=self.call('registers')
            if state['stop_reason']['kind']!='breakpoint' or _integer(regs.get('cs'))!=cs or _integer(regs['eip'])!=ip:
                raise DebuggerError('Original NE entry breakpoint did not match its prepared context')
            self.call('del',{'id':int(entry_hook['breakpoint_id'][3:])});entry_hook=None
            self.metadata.update(original_entry_verified=True,original_entry=source_entry,
                selector_bindings=list(self.bindings.values()),loader_entry_observation=prepared)
            self._event('ne-original-entry',prepared)
        finally:
            if hook_id is not None:
                try:self.call('del',{'id':int(hook_id[3:])})
                except Exception:pass
            if entry_hook is not None:
                try:self.call('del',{'id':int(entry_hook['breakpoint_id'][3:])})
                except Exception:pass

    def _binding(self, index):
        value=self.bindings.get(index)
        if value is None:raise ValueError('NE logical segment has no observed runtime selector binding')
        task=self.metadata.get('task_identity')
        if task is not None:
            current=self._selector(task['psp_selector'])
            if _descriptor_signature(current)!=_descriptor_signature(task['psp_descriptor']):
                raise DebuggerError('Stale Win16 task: PSP descriptor changed after original entry binding')
            if current['module_revision']!=task['validated_module_revision']:
                observed=self.call('modules')
                if not any(m['bits']==32 and _integer(m['base'])==_integer(task['loader_module_base']) and m['generation']==task['loader_module_generation'] for m in observed['modules']):
                    raise DebuggerError('Stale Win16 loader module generation')
                task['validated_module_revision']=observed['module_revision']
        descriptor=self._selector(value['selector'])
        if _descriptor_signature(descriptor)!=_descriptor_signature(value['descriptor']):
            raise DebuggerError('Stale Win16 selector: descriptor changed after source binding')
        return value

    def _resolve(self, address, length=1, cs=None, *, executable=False):
        if cs is not None:raise ValueError('NE uses ne:SEGMENT:OFFSET source addresses, not DOS CS paragraphs')
        bounded(length,'length',1,65536);key=parse_address(address);index,offset=key>>16,key&65535
        segment=self._segments.get(index)
        if segment is None or offset+length>segment['allocation_size'] or executable and not segment['executable']:
            raise ValueError('NE address exceeds its declared source segment')
        binding=self._binding(index)
        if offset+length>binding['limit']+1:raise DebuggerError('NE observation crosses the live selector limit')
        return key,binding,binding['base']+offset

    def scene_memory_key(self,address,length,cs=None):
        key,binding,_=self._resolve(address,length,cs)
        task=self.metadata.get('task_identity',{}).get('epoch','unqualified-task')
        return f'ne/{self.run_id}/{self.version["id"]}/{key:x}/{length}/{binding["selector"]:x}/{binding["generation"]}/{task}'

    def scene_memory_address(self,address,length,cs=None):
        key,_,_=self._resolve(address,length,cs)
        return f'ne:{key>>16}:{key&65535:#06x}'

    def project_address(self, runtime, *, selector=None):
        value=_integer(runtime)
        matches=[]
        for index,binding in self.bindings.items():
            if selector is not None:
                if binding['selector']==_integer(selector) and value<=binding['limit']:
                    self._binding(index);matches.append(index<<16|value)
            elif binding['base']<=value<=binding['base']+binding['limit']:
                self._binding(index);matches.append(index<<16|(value-binding['base']))
        if len(matches)!=1:return None
        key=matches[0];return f'ne:{key>>16}:{key&65535:#06x}'

    def _scene_slice(self,slice_ms,timeout_ms=None):
        """Shared UI slices retain source checks and exact watch classification."""
        if timeout_ms is None:timeout_ms=slice_ms
        bounded(slice_ms,'slice_ms',1,10000)
        bounded(timeout_ms,'timeout_ms',1,600000)
        deadline=time.monotonic()+min(slice_ms,timeout_ms)/1000
        while True:
            self._validate_controls()
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:
                state=self.call('status')
                state['stop_reason'].update(native_kind=state['stop_reason']['kind'],kind='timeout',native_budget_pause=False)
                return state
            state=self.call('slice',{'timeout_ms':remaining},timeout_ms=timeout_ms)
            if state['stop_reason']['kind']!='memory-access' or self._watch_stop(state):return state

    def status(self):
        return {'run':self.run_id,'version':self.version['id'],'live':not self.closed,
            **self.call('status'),'mapping':self.metadata,'native_hooks_available':False,
            'semantics':{'address_context':'source NE segment + observed live selector/offset',
                'watchpoint_stage':'before access; scalar classification required','timing':'host milliseconds',
                'native_hooks_available':False},'dot_mode':self.dot_mode()}

    def registers(self):
        result=dict(self.call('registers'));selector=_integer(result['cs']);ip=_integer(result['eip'])
        if selector&4:
            descriptor=self._selector(selector)
            if result.get('context_source')!='native-ldt-low32':
                raise DebuggerError('Win16 LDT register observations require the native-qualified context reader; prepare the current runtime')
            result.update(cpu_mode='protected16',ip=hex(ip&65535),flags=hex(_integer(result['eflags'])&65535),
                linear_ip=hex(descriptor['base']+(ip&65535)),selector_descriptor=descriptor)
            mapped=[b for b in self.bindings.values() if b['selector']==selector]
            if mapped and _descriptor_signature(mapped[0]['descriptor'])!=_descriptor_signature(descriptor):
                raise DebuggerError('Stale Win16 code selector: current descriptor differs from its source binding')
            if not mapped:
                self._bind_observed_code(selector,descriptor)
        else:result.update(cpu_mode='protected32-carrier',linear_ip=result['eip'])
        result['project_address']=self.project_address(ip,selector=selector)
        return result

    def _bind_observed_code(self,selector,descriptor):
        """A later far transfer may reveal another original segment, or a DLL.

        Only a unique retained source match qualifies. Observing a Wine DLL or
        an ambiguous duplicate leaves project_address unknown.
        """
        candidates=[s for i,s in self._segments.items() if i not in self.bindings
            and s['executable'] and 16<=s['file_size']<=descriptor['limit']+1
            and 0<=descriptor['limit']+1-s['allocation_size']<32]
        if not candidates:return
        observed=self._read_runtime(descriptor['base'],max(s['file_size'] for s in candidates))
        matches=[]
        for segment in candidates:
            size=segment['file_size'];mask=self._source_mask(segment['index'])
            source,_=self._source_expected(segment['index'])
            if sum(bool(x) for x in mask)>=16 and not any((a^b)&m for a,b,m in zip(source,observed[:size],mask,strict=True)):
                matches.append(segment['index'])
        if len(matches)==1:self._bind(matches[0],selector,reason='unique retained source match at an observed 16-bit CS stop')

    def _operand_ranges(self,raw,registers):
        """Translate one scalar operand through its actual observed selector."""
        from iced_x86 import Decoder,InstructionInfoFactory,MemorySizeExt,OpAccess,Register,RegisterExt,CodeSize
        bits=16 if registers['cpu_mode']=='protected16' else 32
        instruction=Decoder(bits,raw,ip=_integer(registers['eip'])).decode()
        if instruction.is_invalid or instruction.has_rep_prefix or instruction.has_repne_prefix:
            raise ValueError('Win16 watch requires a decoded non-repeated scalar instruction; stopped before access')
        operands=list(InstructionInfoFactory().info(instruction).used_memory())
        if len(operands)>1:raise ValueError('Win16 watch requires one scalar memory operand; stopped before access')
        names={value:name.lower() for name,value in vars(Register).items() if name.isupper() and isinstance(value,int)}
        ranges=[]
        for operand in operands:
            size=MemorySizeExt.info(operand.memory_size).size
            if not size or operand.vsib_size:raise ValueError('Win16 watch has an unresolved scalar operand width')
            offset=operand.displacement
            for register,scale in ((operand.base,1),(operand.index,operand.scale)):
                if register==Register.NONE:continue
                full=names.get(RegisterExt.full_register(register),'')
                if full.startswith('r'):full='e'+full[1:]
                if full not in registers['general']:raise ValueError('Win16 watch has an unresolved address register')
                value=_integer(registers['general'][full])
                width=RegisterExt.size(register)*8
                offset+=(value&((1<<width)-1))*scale
            offset&=(0xffff if operand.address_size==CodeSize.CODE16 else 0xffffffff)
            segment=names.get(operand.segment)
            if segment not in registers:raise ValueError('Win16 watch has an unresolved segment register')
            selector=_integer(registers[segment]);descriptor=self.call('selector',{'selector':selector})
            base=_integer(descriptor.get('base'));limit=_integer(descriptor.get('limit'))
            if descriptor.get('present') is not True or _integer(descriptor.get('selector'))!=selector or offset+size>limit+1 or base+offset+size>0x100000000:
                raise ValueError('Win16 watch operand exceeds its observed descriptor')
            ranges.append(dict(address=base+offset,length=size,selector=hex(selector),offset=hex(offset),
                read=operand.access in (OpAccess.READ,OpAccess.COND_READ,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE),
                write=operand.access in (OpAccess.WRITE,OpAccess.COND_WRITE,OpAccess.READ_WRITE,OpAccess.READ_COND_WRITE)))
        return {'instruction':str(instruction),'ranges':ranges}

    def _watch_stop(self,state):
        try:return self._classify_watch_stop(state)
        except Exception:
            # Native guard_pending would otherwise step this rejected access on
            # the next continuation. Closing preserves the refusal across calls.
            try:self.close()
            finally:raise

    def _classify_watch_stop(self,state):
        stop=state['stop_reason']
        if stop['kind']!='memory-access':return False
        registers=self.registers();runtime=_integer(registers['linear_ip'])
        length=min(15,registers['selector_descriptor']['limit']-(_integer(registers['eip'])&65535)+1) if registers['cpu_mode']=='protected16' else 15
        facts=self._operand_ranges(self._read_runtime(runtime,length),registers)
        fault=_integer(stop['access_address']);code=stop['access_code']
        if code==8:
            page=fault&~4095
            if any(w['runtime_address']<page+4096 and page<w['runtime_address']+w['length'] for w in self.watchpoints.values()):
                if any(r['address']<page+4096 and page<r['address']+r['length'] for r in facts['ranges']):
                    raise ValueError('Win16 data operand shares its fetched guard page; remove this watch before continuing')
            return False
        ranges=[r for r in facts['ranges'] if r['address']<=fault<r['address']+r['length']
                and (code==0 and r['read'] or code==1 and r['write'])]
        if not ranges:raise ValueError('Win16 guard access cannot be classified exactly; stopped before access')
        # The native write bit decides conditional writes; retain operand facts.
        if code==0:ranges=[dict(r,write=False) for r in ranges]
        matches=[identifier for identifier,w in self.watchpoints.items()
            if any(r['address']<w['runtime_address']+w['length'] and w['runtime_address']<r['address']+r['length']
                and (r['read'] and 'r' in w['access'] or r['write'] and 'w' in w['access']) for r in ranges)]
        if not matches:return False
        stop.update(kind='watchpoint',breakpoint_ids=matches,access_facts=dict(facts,ranges=ranges),registers=registers)
        return True

    def _refresh_spectator_after_stop(self,evidence):
        try:
            result=self._windows_refresh_spectator()
            if result is not None:evidence['spectator']=result
        except Exception as error:evidence['spectator_capture_error']={'type':type(error).__name__,'message':str(error)}
        return evidence

    def memory(self,address,*,cs=None,length=16):
        key,binding,runtime=self._resolve(address,length,cs)
        data=self._read_runtime(runtime,length)
        return {'run':self.run_id,'version':self.version['id'],'project_address':self.scene_memory_address(address,length,cs),
            'runtime_address':hex(runtime),'selector':hex(binding['selector']),'offset':hex(key&65535),
            'binding_generation':binding['generation'],'source_sha256':self.metadata['source_sha256'],
            'hex':data.hex(),'view':'observed live selector memory; owned INT3 bytes restored'}

    def write_memory(self,address,data_hex,*,expected_hex):
        data=bytes.fromhex(data_hex);expected=bytes.fromhex(expected_hex)
        if not 1<=len(data)<=65536 or len(data)!=len(expected):raise ValueError('NE edits require equal bounded expected/data bytes')
        key,binding,runtime=self._resolve(address,len(data))
        if any(runtime<=v['runtime_address']<runtime+len(data) for v in self.breakpoints.values()):
            raise ValueError('Delete overlapping NE breakpoints before editing code')
        before=self.memory(address,length=len(data))
        if before['hex']!=expected.hex():raise ValueError('NE edit expected bytes differ; mutation refused')
        try:
            result=self.call('write',{'address':runtime,'data_hex':data.hex()})
            after=self.memory(address,length=len(data))
        except BaseException:
            try:self.close()
            finally:raise
        if after['hex']!=data.hex():self.close();raise DebuggerError('NE write readback mismatch')
        for index,value in enumerate(data):self._edits[key+index]=value
        self._windows_state_changed();result.update(before_hex=expected.hex(),after_hex=data.hex(),
            project_address=before['project_address'],selector=hex(binding['selector']),assistance='diagnostic memory edit',static_version_unchanged=True)
        self._event('write-memory',result);return result

    def breakpoint(self,address,*,cs=None,access='x',length=1,view='static'):
        if access not in ('x','r','w','rw') or view!='static':raise ValueError('Unsupported NE breakpoint kind/view')
        key,binding,runtime=self._resolve(address,length,cs,executable=access=='x')
        if access!='x':
            result=self.call('watch',{'address':runtime,'length':length,'access':access})
            self.watchpoints[result['breakpoint_id']]={'address':key,'runtime_address':runtime,'length':length,'access':access,'binding_generation':binding['generation']}
        else:
            if length!=1:raise ValueError('NE execution breakpoints use one instruction boundary')
            code=self.project.disassembly(address=key,version=self.version['id'],lines=1)['instructions']
            if not code or parse_address(code[0]['address'])!=key:raise ValueError('Analyze the original NE instruction before adding its breakpoint')
            size=code[0]['size'];_,_,_=self._resolve(key,size,executable=True)
            observed=self._read_runtime(runtime,size);segment=self._segments[key>>16]
            offset=key&65535;expected=self._source_expected(key>>16)[0][offset:offset+size]
            mask=self._source_mask(key>>16)[offset:offset+size]
            for n in range(size):
                if key+n in self._edits:expected=expected[:n]+bytes([self._edits[key+n]])+expected[n+1:]
            if len(expected)!=size or any((a^b)&m for a,b,m in zip(expected,observed,mask,strict=True)):
                raise DebuggerError('NE instruction bytes differ from source outside declared fixups')
            from .decoder import decode
            native_instruction=decode(observed,key&65535,'x86',16)
            if not native_instruction or native_instruction['size']!=size:
                raise DebuggerError('Loaded NE instruction no longer has the analyzed source boundary')
            result=self.call('bp',{'address':runtime})
            self.breakpoints[result['breakpoint_id']]={'address':key,'runtime_address':runtime,'binding_generation':binding['generation']}
            result.update(bytes_verified=True,runtime_bytes=observed.hex(),source_fixup_mask=bytes(mask).hex(),runtime_instruction=native_instruction)
        result.update(run=self.run_id,project_address=self.scene_memory_address(key,length),runtime_address=hex(runtime),selector=hex(binding['selector']),binding_generation=binding['generation'])
        self._event('breakpoint',result);return result

    def delete_breakpoint(self,breakpoint_id):
        if breakpoint_id in self.watchpoints:
            result=self.call('unwatch',{'id':int(breakpoint_id[3:])});del self.watchpoints[breakpoint_id]
        elif breakpoint_id in self.breakpoints:
            result=self.call('del',{'id':int(breakpoint_id[3:])});del self.breakpoints[breakpoint_id]
        else:raise ValueError('Unknown owned NE breakpoint')
        self._event('delete-breakpoint',result);return result

    def _validate_controls(self):
        for control in (*self.breakpoints.values(),*self.watchpoints.values()):
            binding=self._binding(control['address']>>16)
            if control['binding_generation']!=binding['generation']:
                raise DebuggerError('Stored NE control has a stale source/selector generation')

    def run(self,*,timeout_ms=10000,guest_ms=None,fast_forward=False,stop_on_hook=False):
        bounded(timeout_ms,'timeout_ms',1,600000)
        if guest_ms is not None or fast_forward or stop_on_hook:
            raise ValueError('Win16 uses host-time execution; DOS guest time, fast-forward and hooks are unavailable')
        self._validate_controls();started=time.monotonic();deadline=started+timeout_ms/1000
        while True:
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:
                state=self.call('status');state['stop_reason'].update(native_kind=state['stop_reason']['kind'],kind='timeout');break
            state=self.call('run',{'timeout_ms':remaining},timeout_ms=remaining+15000)
            if state['stop_reason']['kind']!='memory-access' or self._watch_stop(state):break
        stop=state['stop_reason'];stop['project_address']=None if stop['kind']=='exited' else self.project_address(stop['address'])
        result={'run':self.run_id,'outcome':stop['kind'],'session':state,
            'host_elapsed_ms':(time.monotonic()-started)*1000,'instruction_completed':None}
        self._windows_state_changed();self._refresh_spectator_after_stop(result);self._event('run',result);return result

    def step(self,count=1,*,timeout_ms=10000):
        bounded(count,'count',1,10000);bounded(timeout_ms,'timeout_ms',1,600000)
        self._validate_controls();deadline=time.monotonic()+timeout_ms/1000;events=[]
        state=self.call('status')
        for _ in range(count):
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<=0:break
            before=self.registers();runtime=_integer(before['linear_ip'])
            raw=self._read_runtime(runtime, min(15,before['selector_descriptor']['limit']-(_integer(before['eip'])&65535)+1) if before['cpu_mode']=='protected16' else 15)
            while True:
                remaining=int((deadline-time.monotonic())*1000)
                if remaining<=0:
                    state=self.call('status');state['stop_reason'].update(native_kind=state['stop_reason']['kind'],kind='timeout');break
                state=self.call('step',{'timeout_ms':remaining},timeout_ms=remaining+15000)
                if state['stop_reason']['kind']!='memory-access' or self._watch_stop(state):break
            if state['stop_reason']['kind']!='step':break
            from .decoder import decode
            decoded=decode(raw,_integer(before['eip']),'x86',16 if before['cpu_mode']=='protected16' else 32)
            if not decoded:raise DebuggerError('Completed Win16 instruction could not be decoded')
            events.append({'address':before['eip'],'linear_address':hex(runtime),'project_address':before['project_address'],
                'selector':before['cs'],'cpu_mode':before['cpu_mode'],'bytes':raw[:decoded['size']].hex(),
                'registers':before,'instruction':decoded,'completed':True})
        self._windows_state_changed();result={'run':self.run_id,'requested':count,'executed':len(events),
            'completed':len(events)==count,'outcome':'step' if len(events)==count else state['stop_reason']['kind'],
            'events':events,'session':state}
        self._refresh_spectator_after_stop(result);self._event('step',result);return result

    def trace(self,name='trace.json',*,count=512,timeout_ms=10000,fast_forward=False):
        _file_name(name)
        if fast_forward:raise ValueError('Win16 has no DOS fast-forward')
        result=self.step(count=count,timeout_ms=timeout_ms)
        result.update(complete=result['completed'],requested_count=count,
            semantics='completed original/runtime instructions with actual selector context; uncompleted exceptions remain explicit')
        return self._artifact(name,'trace',json.dumps(result,indent=2).encode(),
            {'event_count':len(result['events']),'complete':result['completed']})

    def write_registers(self,registers):
        if not self.register_edits_available:
            raise ValueError('Win16 general-register writes require the paired native/WOW integer runtime')
        allowed={'eax','ebx','ecx','edx','esi','edi'}
        if not isinstance(registers,dict) or not registers or set(registers)-allowed:
            raise ValueError('Win16 register edits accept only six checked non-stack general registers')
        for change in registers.values():
            if not isinstance(change,dict) or set(change)!={'expected','value'}:
                raise ValueError('Win16 register edits require expected and value for every register')
        before=self.registers()
        if before.get('context_source')!='native-ldt-low32' or before.get('cpu_mode')!='protected16':
            raise ValueError('Win16 register edits require a stopped native 16-bit LDT context')
        values={}
        for name,change in registers.items():
            expected=_integer(change['expected']);value=_integer(change['value'])
            if expected!=_integer(before['general'][name]):
                raise ValueError('Win16 register expected value differs: '+name)
            if value<0 or value>0xffffffff:
                raise ValueError('Win16 register value exceeds the observed 32-bit carrier width')
            values[name]=value
        try:
            self.call('setregs',{'values':values})
            after=self.registers()
            for field in ('context_source','cpu_mode','eip','eflags','cs','ds','ss','es','fs','gs','project_address'):
                if after.get(field)!=before.get(field):
                    raise DebuggerError('Win16 register edit changed control or selector context: '+field)
            for name,original in before['general'].items():
                if _integer(after['general'][name])!=values.get(name,_integer(original)):
                    raise DebuggerError('Win16 register edit readback mismatch: '+name)
        except BaseException:
            try:self.close()
            finally:raise
        self._windows_state_changed()
        result={'before':before,'after':after,'assistance':'checked native Win16 integer edit'}
        self._event('write-registers',result)
        return result

    def save_state(self,*args,**kwargs):
        raise ValueError('Win16 native checkpoints require separately qualified source/selector restoration')

    def load_state(self,*args,**kwargs):
        raise ValueError('Win16 native checkpoints require separately qualified source/selector restoration')

    def close(self):
        if self.closed:return
        self._windows_ui_close()
        if self.rpc:self.rpc.close()
        self.closed=True
        if self._recording:
            with self.project.transaction(True):
                self.project.db.execute('UPDATE debug_runs SET ended=?,state=? WHERE id=?',(stamp(),'closed',self.run_id))
        if self in self.project._live_debuggers:self.project._live_debuggers.remove(self)
