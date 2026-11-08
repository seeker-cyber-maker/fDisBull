"""Immutable whole-VM PE checkpoints in hash-bound private project sidecars."""
from __future__ import annotations

from contextlib import nullcontext
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from .dosbox_rpc import DebuggerError
from .external_files import _file_name
from .anchor_stones import AnchorStoneSessionMixin
from .wine_arch import register_names, ip_name, flags_name

FORMAT='fdisbull-qemu-native-1'
REGISTERS={'rax','rbx','rcx','rdx','rsi','rdi','rbp','rsp','r8','r9','r10','r11','r12','r13','r14','r15','rip','rflags'}


def file_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def sidecar(project):
    path=Path(str(project.path)+'.fdisbull-states')
    if path.is_symlink():raise ValueError('Native-state sidecar cannot be a symbolic link')
    path.mkdir(mode=0o700,exist_ok=True)
    return path


def get_state(project,artifact,version=None):
    row=project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(artifact,)).fetchone()
    if row is None or row['kind']!='state' or version is not None and row['version']!=version:
        raise ValueError('Native state must belong to the selected project version')
    raw=bytes(row['data'])
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Stored native state manifest hash mismatch')
    document=json.loads(raw)
    if document.get('format')!=FORMAT:raise ValueError('Expected a PE64 QEMU native state')
    digest=document['machine_sha256']
    if not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest):raise ValueError('Invalid native state identity')
    path=sidecar(project)/(digest+'.mig.gz')
    if path.is_symlink() or not path.is_file() or path.stat().st_size!=document['machine_size'] or file_hash(path)!=digest:
        raise ValueError('Native state sidecar is missing or its hash differs; preserve the project and sidecar together')
    if document['metadata']['source_sha256']!=project.meta['source_sha256'] or document['metadata']['version_sha256']!=project.version(row['version'])['sha256']:
        raise ValueError('Native state source/version mismatch')
    return row,document,path


def state_info(project,artifact):
    row,document,path=get_state(project,artifact)
    return {'artifact':artifact,'version':row['version'],'sha256':row['sha256'],'size':len(row['data']),
            'native_size':path.stat().st_size,'metadata':document['metadata'],
            'components':[{'name':'state.json','size':len(row['data'])},{'name':'machine.mig.gz','size':path.stat().st_size,'sha256':document['machine_sha256']}],
            'storage':'hash-bound external sidecar; required alongside the project'}


def export_state(project,artifact,destination):
    row,document,path=get_state(project,artifact)
    destination=Path(destination).expanduser().resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as raw,zipfile.ZipFile(raw,'w',compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('state.json',bytes(row['data']))
        archive.write(path,'machine.mig.gz')
    return {'artifact':artifact,'output':str(destination),'sha256':file_hash(destination),
            'artifact_sha256':row['sha256'],'size':destination.stat().st_size,'format':FORMAT}


def integer(value, bits=64):
    if isinstance(value,str) and re.fullmatch(r'0x[0-9a-fA-F]{1,16}',value):value=int(value,16)
    if type(value) is int and 0<=value<2**bits:return value
    raise ValueError('PE register values require unsigned 64-bit integers or explicit 0x strings')


def validate_edits(memory,registers, *, bits=64):
    from .debug_state import byte_string
    if not isinstance(memory,list) or len(memory)>64 or not isinstance(registers,dict):raise ValueError('Invalid PE state edit collection')
    total=0
    for edit in memory:
        if not isinstance(edit,dict) or set(edit)!={'address','expected_hex','data_hex'}:raise ValueError('PE state memory edit requires flat address and expected/data bytes')
        before=byte_string(edit['expected_hex']);after=byte_string(edit['data_hex'])
        if len(before)!=len(after):raise ValueError('Native state edits cannot resize memory')
        total+=len(after)
    if total>65536:raise ValueError('Native state memory edits exceed 64 KiB')
    for name,change in registers.items():
        if name not in register_names(bits) or not isinstance(change,dict) or set(change)!={'expected','value'}:raise ValueError('Invalid PE register edit')
        old=integer(change['expected'],bits);new=integer(change['value'],bits)
        if name in ('rflags','eflags') and (old^new)&~0xcd5:raise ValueError('PE flags editing supports arithmetic/direction flags; debugger control flags are reserved')


def checked_runtime_rip(debug,value):
    """Register values are runtime addresses, even when image ASLR changes its base."""
    project_address=debug.project_address(value)
    if project_address is None:raise ValueError('RIP edit is outside the observed main image')
    debug._address(project_address,executable=True)
    return value


def apply_edits(debug,memory,registers):
    validate_edits(memory,registers,bits=getattr(debug,'bits',64));debug._layer_setup()
    if debug._pending_exec:raise ValueError('Complete the execution-layer instruction before editing registers or state')
    ranges=[];plans=[];snapshot=debug.registers()
    for edit in memory:
        data=bytes.fromhex(edit['data_hex']);address=debug._address(edit['address'],len(data))
        if any(address<hi and low<address+len(data) for low,hi in ranges):raise ValueError('Native state memory edits overlap')
        ranges.append((address,address+len(data)))
        if any(address<=a<address+len(data) for a in set(debug._ram_applied)|set(debug._execution)|set(debug.breakpoints.values())):
            raise ValueError('Disable overlapping layers/breakpoints before native state editing')
        if debug.memory(address,length=len(data))['hex']!=edit['expected_hex'].lower():raise ValueError('Native state edit expected bytes mismatch')
        plans.append((address,edit))
    for name,change in registers.items():
        value=snapshot[name] if name in (ip_name(snapshot),flags_name(snapshot)) else snapshot['general'][name]
        if int(value,16)!=integer(change['expected']):raise ValueError('Native state register expected value mismatch: '+name)
        if name in ('rip','eip'):checked_runtime_rip(debug,integer(change['value']))
    evidence={'memory':[],'registers':[],'target_execution_during_edits':False,'guest_services_running':True}
    try:
        for address,edit in plans:evidence['memory'].append(debug.write_memory(address,edit['data_hex'],expected_hex=edit['expected_hex']))
        if registers:
            debug.call('setregs',{'values':{name:integer(change['value']) for name,change in registers.items()}})
            after=debug.registers()
            for name,change in registers.items():
                value=after[name] if name in (ip_name(after),flags_name(after)) else after['general'][name]
                if int(value,16)!=integer(change['value']):raise DebuggerError('Native register readback mismatch')
                evidence['registers'].append({'register':name,'before':hex(integer(change['expected'])),'after':value,'verified':True})
    except BaseException:
        debug.close();raise
    debug._event('state-edits',evidence);return evidence


class PEStateSessionMixin(AnchorStoneSessionMixin):
    def _state_host(self):
        self._layer_setup()
        return {'breakpoints':self.breakpoints,'watchpoints':self.watchpoints,'active':self._layers,
                'layer_hashes':{i:self.project.debug_layer_info(i)['sha256'] for i in self._layers},
                'generation':self._layer_generation,'scratch':self._scratch,
                **{name:{hex(a):b for a,b in getattr(self,name).items()} for name in ('_ram_base','_ram_applied','_execution','_execute_guards')}}

    def _load_state_host(self,host):
        self._layer_setup()
        for identifier,digest in host['layer_hashes'].items():
            if self.project.debug_layer_info(identifier)['sha256']!=digest:raise ValueError('Native state layer definition mismatch')
        self.breakpoints={k:int(v) for k,v in host['breakpoints'].items()};self.watchpoints=host['watchpoints']
        self._layers=host['active'];self._layer_generation=host['generation'];self._scratch=host['scratch'];self._pending_exec=None
        for name in ('_ram_base','_ram_applied','_execution','_execute_guards'):
            values=host[name]
            if not isinstance(values,dict) or len(values)>65536:raise ValueError('Invalid native layer state')
            setattr(self,name,{int(a,16):b for a,b in values.items()})
        self._layer_generations[self._layer_generation]=list(self._layers)

    def save_state(self,name='checkpoint.sav',*,max_bytes=None):
        lock=getattr(self,'_delta_lock',None) or getattr(self.rpc,'lock',None)
        with lock if lock is not None else nullcontext():
            guard=getattr(self,'_cpu_delta_before_call',None)
            if guard is not None:guard('state.save')
            return self._save_native_state(name,max_bytes=max_bytes)

    def _save_native_state(self,name='checkpoint.sav',*,max_bytes=None):
        if max_bytes is not None and (type(max_bytes) is not int or not 1<=max_bytes<=2*1024**3):
            raise ValueError('PE native state max_bytes must be 1..2 GiB including manifest and sidecar')
        _file_name(name);self._layer_setup()
        if self._pending_exec:raise ValueError('Finish the pending execution-layer instruction before native capture')
        from .qemu_input import require_released_machine_input
        require_released_machine_input(getattr(self.rpc,'vm',None))
        if self.rpc.capabilities.get('keyboard'):
            inputs=self.call('keyboard-state')
            if inputs.get('pending') or inputs.get('held') or getattr(self,'_keyboard_leases',{}):
                raise ValueError('Native checkpoint requires released keys and an empty input queue')
        directory=sidecar(self.project)
        if shutil.disk_usage(directory).free<2*1024**3:raise ValueError('Native VM capture requires at least 2 GiB of free space')
        if sum(p.stat().st_size for p in directory.glob('*.mig.gz'))>6*1024**3:raise ValueError('Project native checkpoints exceed 6 GiB budget')
        registers=self.registers();host=self._state_host()
        with tempfile.TemporaryDirectory(prefix='.capture-',dir=directory) as temporary:
            path=Path(temporary)/'machine.mig.gz';capture=self.rpc.capture(path)
            if not 0<path.stat().st_size<=2*1024**3:raise ValueError('Native checkpoint exceeds 2 GiB compressed budget')
            if sum(p.stat().st_size for p in directory.glob('*.mig.gz'))+path.stat().st_size>6*1024**3:
                raise ValueError('Project native checkpoint budget exceeds 6 GiB')
            expanded=0
            with gzip.open(path,'rb') as stream:
                while chunk:=stream.read(8*1024**2):
                    expanded+=len(chunk)
                    if expanded>8*1024**3:raise ValueError('Native checkpoint exceeds expanded budget')
            digest=file_hash(path);destination=directory/(digest+'.mig.gz')
            native_size=path.stat().st_size
            metadata={**self.metadata,'format':FORMAT,'registers':registers,'native_sha256':digest,
                      'native_size':native_size,'storage':'private-project-sidecar','capture':capture,
                      'target_paused':True,'host_files_restored':False}
            if hasattr(self,'_state_provenance'):metadata['derivation']=self._state_provenance
            document={'format':FORMAT,'machine_sha256':digest,'machine_size':native_size,'metadata':metadata,'host':host}
            data=json.dumps(document,sort_keys=True,separators=(',',':')).encode()
            if max_bytes is not None and native_size+len(data)>max_bytes:
                raise ValueError('PE native state manifest and sidecar exceed remaining delta byte budget')
            if destination.is_symlink():raise ValueError('Native sidecar file cannot be a symbolic link')
            if destination.exists():
                if file_hash(destination)!=digest:raise ValueError('Existing native sidecar hash mismatch')
            else:path.replace(destination);destination.chmod(0o400)
        result=self._artifact(name,'state',data,metadata)
        result['native_size']=destination.stat().st_size;return result

    def load_state(self,artifact):
        lock=getattr(self,'_delta_lock',None) or getattr(self.rpc,'lock',None)
        with lock if lock is not None else nullcontext():
            if getattr(self,'_cpu_delta_history',None) is None:
                return self._load_native_state(artifact)
            with self._cpu_delta_full_load():
                result=self._load_native_state(artifact)
                self._cpu_delta_loaded(self.metadata.get('delta_experiment'))
                return result

    def _load_native_state(self,artifact):
        row,document,path=get_state(self.project,artifact,self.version['id'])
        for name in ('qemu','kernel','initramfs'):
            if self.rpc.inputs[name]['sha256']!=document['metadata']['runtime_inputs'][name]['sha256']:
                raise ValueError('Native state backend identity mismatch: '+name)
            if file_hash(self.rpc.inputs[name]['path'])!=self.rpc.inputs[name]['sha256']:
                raise ValueError('Native state runtime file identity changed: '+name)
        if self.metadata['files']!=document['metadata']['files']:raise ValueError('Native state program inputs mismatch')
        if hasattr(self,'_disk_manifest') and self._disk_manifest()!=document['metadata']['files']:
            raise ValueError('Native state host program input identities changed')
        if self.metadata['runtime_profile']!=document['metadata']['runtime_profile']:raise ValueError('Native state runtime profile mismatch')
        from .wine_rpc import WineQemuRPC
        options=[self.rpc.inputs[n]['path'] for n in ('qemu','kernel','initramfs')]
        self.rpc.close()
        try:
            replacement=WineQemuRPC(*options,restore=path,memory_mib=document['metadata'].get('memory_mib',4096))
            try:
                if any(replacement.inputs[n]['sha256']!=document['metadata']['runtime_inputs'][n]['sha256']
                       for n in ('qemu','kernel','initramfs')):
                    raise ValueError('Native state runtime identity changed during VM replacement')
                if hasattr(self,'_cpu_delta_bind_rpc'):self._cpu_delta_bind_rpc(replacement)
            except BaseException:
                replacement.close();raise
            self.rpc=replacement
            self.runtime_base=int(document['metadata']['runtime_image_base'],16);self.delta=self.runtime_base-self.static_base
            self._expected={r.start:bytearray(r.data) for r in self.regions};self._relocate_expected()
            old_metadata=document['metadata']
            self.metadata={k:v for k,v in old_metadata.items() if k not in (
                'format','registers','native_sha256','native_size','storage','capture','target_paused','host_files_restored','derivation')}
            self.metadata.update(qemu_pid=self.rpc.process.pid,runtime_inputs=self.rpc.inputs,restored_from=artifact)
            self._load_state_host(document['host']);self._frame=None;self.mode_id+=1
            changed=getattr(self,'_windows_invalidate_input_leases',None) or getattr(self,'_windows_state_changed',None)
            if callable(changed):changed()
            registers=self.registers()
            for name in (ip_name(registers),flags_name(registers),'general','thread'):
                if registers[name]!=document['metadata']['registers'][name]:raise DebuggerError('Native restored registers differ: '+name)
            bits=getattr(self,'bits',64)
            self.rpc.capabilities.update(bits=bits,architecture='x86-32' if bits==32 else 'x86-64')
            self.metadata['capabilities']=self.rpc.capabilities
            result={'artifact':artifact,'sha256':row['sha256'],'registers':registers,'state':'stopped','native_size':document['machine_size']}
            with self.project.transaction(True):
                self.project.db.execute('UPDATE debug_runs SET metadata=? WHERE id=?',(json.dumps(self.metadata),self.run_id))
            self._event('load-state',result);return result
        except BaseException:self.close();raise

    def write_registers(self,registers):
        lock=getattr(self,'_delta_lock',None) or getattr(self.rpc,'lock',None)
        with lock if lock is not None else nullcontext():
            guard=getattr(self,'_cpu_delta_before_call',None)
            if guard is not None:guard('setregs')
            return apply_edits(self,[],registers)
