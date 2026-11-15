"""Fresh stopped embedded-LE evidence, separate from the MZ launch binding."""
from copy import deepcopy
from functools import partial
import hashlib
import json
import re

from .qemu_machine import machine_trace_operation

FORMAT = 'fdisbull-qemu-dos-le-admission-1'


def _sha(data):return hashlib.sha256(data).hexdigest()


def _integer(value):
    if isinstance(value,str):
        try:value=int(value,0)
        except ValueError:raise ValueError('Invalid protected source address context') from None
    if type(value) is not int or not 0 <= value < 2**32:
        raise ValueError('Invalid protected source address context')
    return value


def _parameters(*,name,max_compare_bytes,max_scan_bytes,timeout_ms,expected_source_sha256):
    from .external_files import _file_name
    _file_name(name)
    for value,upper,label in ((max_compare_bytes,524288,'comparison'),(max_scan_bytes,16777216,'scan'),(timeout_ms,600000,'timeout')):
        if type(value) is not int or not 1 <= value <= upper:
            raise ValueError('Invalid protected source '+label+' budget')
    if expected_source_sha256 is not None and (not isinstance(expected_source_sha256,str) or
            re.fullmatch('[0-9a-f]{64}',expected_source_sha256) is None):
        raise ValueError('Expected an exact lowercase source SHA-256')


def _source(session, expected, *, internal_transaction=False):
    project=session.project;version=project.version(session.version['id'])
    if (project.db.in_transaction and not internal_transaction) or version['parent'] is not None:
        raise ValueError('Protected source admission requires an original project outside a caller transaction')
    if project.meta['arch']!='x86' or project.meta['format'] not in ('MZ','LE'):
        raise ValueError('Protected source admission requires an original x86 LE carrier')
    pin=project.meta['source_sha256']
    if expected is not None and expected!=pin:
        raise ValueError('Protected source caller pin differs')
    if session.metadata['source_sha256']!=pin or session.metadata['version_sha256']!=version['sha256']:
        raise ValueError('Protected source session identity differs')
    row=project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',(version['id'],)).fetchone()
    if row is None:raise ValueError('Retained protected source unavailable')
    raw=bytes(row[0])
    if not 0 < len(raw) <= 64*1024*1024 or _sha(raw)!=pin or project.digest(project.regions(version['id']))!=version['sha256']:
        raise ValueError('Retained protected source or mapped version differs')
    return raw,dict(source_sha256=pin,version=version['id'],version_sha256=version['sha256'])


def _context(registers):
    state=registers.get('address_state',{})
    if (registers.get('cpu_mode')!='protected' or state.get('code_bits')!=32
            or state.get('machine_vcpus')!=1 or state.get('register_context_match') is not True
            or state.get('paging') is not False or state.get('a20') is not True):
        raise ValueError('Protected source admission requires one observed unpaged protected32 CPU with A20 enabled')
    cs=state.get('segments',{}).get('cs',{})
    selector=_integer(cs.get('selector'))
    if _integer(registers.get('registers',{}).get('cs'))!=selector:
        raise ValueError('Protected CS register and cache differ')
    cpu=dict(mode='protected',bits=32,cs=selector,ip=_integer(registers.get('instruction_pointer')),
             cs_base=_integer(cs.get('base')),cs_limit=_integer(cs.get('limit')),
             cs_attributes=_integer(cs.get('attributes')))
    if _integer(registers.get('linear_pc'))!=cpu['cs_base']+cpu['ip']:
        raise ValueError('Protected source PC differs from observed CS cache')
    return cpu


def _gdt(session):
    value=session.vm.qmp.call('human-monitor-command',{'command-line':'info registers'},timeout_ms=session._remaining())
    match=re.search(r'\bGDT\s*=\s*([0-9a-fA-F]+)\s+([0-9a-fA-F]+)',value) if isinstance(value,str) else None
    if not match:raise ValueError('Protected source admission requires observed GDT base and limit')
    base,limit=(int(v,16) for v in match.groups())
    if limit>65535 or not 0 <= base < base+limit+1 <= 2**32:
        raise ValueError('Protected source GDT exceeds its bounded extent')
    return dict(base=base,limit=limit)


def _producer():
    from pathlib import Path
    root=Path(__file__).parent
    return {p:_sha((root/p).read_bytes()) for p in ('qemu_dos_source_admission.py','qemu_dos_le_match.py','le.py')}


def _public_observation(result):
    if result is None:return None
    summary=deepcopy(result)
    evidence=summary['identity_evidence']
    evidence['excluded_loader_fixup_count']=len(evidence.pop('excluded_loader_fixups'))
    summary['full_observation_in_artifact']=True
    if len(json.dumps(summary,sort_keys=True,separators=(',',':')).encode())<=32768:
        return summary
    spans=result['source_spans']
    return dict(format=result['format'],status=result['status'],source=result['source'],
        full_observation_in_artifact=True,reply_truncated=True,source_span_count=len(spans),
        object_ids=sorted({s['object_id'] for s in spans}),
        identity_evidence={k:evidence[k] for k in ('kind','lifetime_qualified','cpu','gdt_sha256',
            'code_object','runtime_code_base','stable_code_extent','excluded_loader_fixup_count')},
        source_spans=[{k:s[k] for k in ('name','kind','address','length','object_id','object_index',
            'object_offset','compared_bytes','comparable_sha256')} for s in spans[:16]],
        budget=result['budget'],limitations=result['limitations'])


class QemuDOSSourceAdmissionMixin:
    @partial(machine_trace_operation,label='Protected source admission',parameter_validator=_parameters)
    def dos_source_admit(self, *,name='protected-source-admission.json',max_compare_bytes=524288,
                         max_scan_bytes=16777216,timeout_ms=10000,expected_source_sha256=None):
        """Record bounded stopped original-LE matches; never install a live map."""
        from .le import load_runtime_le_carrier
        from .qemu_dos_le_match import match
        self._remaining();remote=self._stopped()
        process=self._process
        if (self.closed or self.vm.process is None or self.vm.process.poll() is not None
                or process is None or process['state']!='active' or process.get('machine_closed')
                or process['capture_epoch']!=self._runtime_epoch):
            raise ValueError('Protected source admission requires the active owned DOS process epoch')
        if getattr(self,'_layer_active',None) or getattr(self,'_dos_task_monitor',None):
            raise ValueError('Protected source admission requires an unlayered current machine view')
        original_mapping=deepcopy(process);epoch=self._runtime_epoch
        raw,identity=_source(self,expected_source_sha256);producer=_producer()
        image=load_runtime_le_carrier(raw)
        before=self.registers();cpu=_context(before);table=_gdt(self)
        reads={};ram_end=min(self.vm.machine_configuration['memory_mib']<<20,0xc0000000)
        def read_linear(address,length):
            self._remaining()
            if (type(address) is not int or type(length) is not int or not 1<=length<=524288
                    or not (0<=address<address+length<=0xa0000 or 0x100000<=address<address+length<=ram_end)):
                raise ValueError('Protected source comparison requires conventional or extended physical RAM')
            key=(address,length)
            if key in reads:return reads[key]
            chunks=[]
            for offset in range(0,length,65536):
                count=min(length-offset,65536)
                physical=remote.memory(address+offset,count,space='physical',timeout_ms=self._remaining())
                virtual=remote.memory(address+offset,count,space='virtual',timeout_ms=self._remaining())
                if len(physical)!=count or physical!=virtual:
                    raise ValueError('Protected source physical and linear bytes differ')
                chunks.append(physical)
            reads[key]=b''.join(chunks)
            return reads[key]
        gdt_bytes=read_linear(table['base'],table['limit']+1)
        result=match(image,cpu,gdt_bytes,read_linear,max_compare_bytes=max_compare_bytes,max_scan_bytes=max_scan_bytes)
        if result is not None and result['source']['source_sha256']!=identity['source_sha256']:
            raise ValueError('Protected source match identifies a different carrier')
        self._remaining()
        if self.registers()!=before or _gdt(self)!=table:
            raise ValueError('Protected source CPU or GDT context changed during admission')
        # Verify all bytes used for the candidate, including fixup pointer sites.
        for (address,length),expected in list(reads.items()):
            for offset in range(0,length,65536):
                count=min(length-offset,65536);part=expected[offset:offset+count]
                if (remote.memory(address+offset,count,space='physical',timeout_ms=self._remaining())!=part
                        or remote.memory(address+offset,count,space='virtual',timeout_ms=self._remaining())!=part):
                    raise ValueError('Protected source memory changed during admission')
        if (self.registers()!=before or _gdt(self)!=table or self._runtime_epoch!=epoch
                or self._process!=original_mapping or _source(self,expected_source_sha256)[1]!=identity
                or _producer()!=producer):
            raise ValueError('Protected source identity or stopped context changed before publication')
        document=dict(format=FORMAT,backend='qemu-dos',run=self.run_id,capture_epoch=epoch,
            **identity,producer=producer,status='admitted' if result is not None else 'unmatched',
            source_view='embedded-le',qualification='bounded-stopped-original-source-byte-match' if result is not None else 'no-source-match',
            lifetime_qualified=False,live_mapping_installed=False,initial_mz_mapping_changed=False,
            observed_cpu=cpu,gdt=dict(**table,sha256=_sha(gdt_bytes)),
            address_scope='unpaged A20-enabled physical/linear RAM readback',
            readback=[dict(address=a,length=n,sha256=_sha(b)) for (a,n),b in reads.items()],
            options=dict(max_compare_bytes=max_compare_bytes,max_scan_bytes=max_scan_bytes),
            observation=result,revalidation='historical stopped evidence; call again after execution, mutation, restore or owner replacement')
        data=json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if len(data)>4*1024*1024:raise ValueError('Protected source artifact exceeds its private budget')
        self._remaining()
        with self.project.transaction(True):
            if (_source(self,expected_source_sha256,internal_transaction=True)[1]!=identity
                    or self._runtime_epoch!=epoch or self._process!=original_mapping or _producer()!=producer):
                raise ValueError('Protected source changed during publication')
            artifact=self._artifact(name,'dos-source-admission',data,dict(format=FORMAT,**identity,
                capture_epoch=epoch,status=document['status'],source_view='embedded-le',lifetime_qualified=False))
            self._event('dos-source-admission',dict(artifact=artifact['artifact'],sha256=artifact['sha256'],status=document['status']))
            self._remaining()
        # The byte-bearing document stays in the private artifact. Public replies
        # expose its identity and bounded summary, not commercial instruction bytes.
        reply=dict(format=FORMAT,**identity,run=self.run_id,capture_epoch=epoch,status=document['status'],
            artifact=artifact['artifact'],sha256=artifact['sha256'],size=artifact['size'],
            source_view='embedded-le',lifetime_qualified=False,live_mapping_installed=False,
            qualification=document['qualification'],observation=_public_observation(result))
        return reply
