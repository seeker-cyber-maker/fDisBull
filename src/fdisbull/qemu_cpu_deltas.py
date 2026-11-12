"""Freeze-only selected CPU/RAM histories for one owned native DOS process.

These are selected-state projections, not machine rewind or instruction-retirement
proof. Complete recovery always loads a separately validated full checkpoint.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import uuid

from .debug_cpu_deltas import validate_ranges, validate_policy, _fingerprint, _runs
from .qemu_dos_history import _history_operation

FORMAT = 'fdisbull-qemu-selected-cpu-ram-1'


def _encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _bounded(value,name,lo,hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{name} must be an integer in {lo}..{hi}')


def _ordinary(result):
    if (not isinstance(result,dict) or result.get('outcome') != 'step'
            or result.get('timed_out') is not False or result.get('hook_hits')
            or result.get('layer_conflict') or result.get('native_machine_stop')):
        return False
    state = result.get('session')
    stop = state.get('stop_reason') if isinstance(state,dict) else None
    if (not isinstance(state,dict) or state.get('state') != 'stopped'
            or not isinstance(stop,dict) or stop.get('kind') != 'step'
            or stop.get('breakpoint_ids')):
        return False
    process = result.get('process')
    return process is None or (isinstance(process,dict) and process.get('state') == 'active'
                               and not process.get('machine_closed'))


class QemuCpuDeltaMixin:
    """The stored projections are per live process and intentionally non-resumable."""

    @property
    def _delta_registers(self):
        from .qemu_cpu_undo_runtime import REGISTERS
        return REGISTERS

    @contextmanager
    def _qemu_delta_owned(self):
        if getattr(self,'_qemu_cpu_delta_busy',False):
            raise ValueError('Nested selected CPU delta operations are unsupported')
        self._qemu_cpu_delta_busy = True
        try: yield
        finally: self._qemu_cpu_delta_busy = False

    def _cpu_delta_before_operation(self, name, args=(), kwargs=None):
        from .qemu_cpu_undo_guard import before_operation
        return before_operation(self,name,args,kwargs or {})

    def _cpu_delta_full_restore_complete(self):
        history = getattr(self,'_qemu_cpu_delta_history',None)
        if history is not None:
            history.update(valid=False,frozen=False,invalid_reason='full native checkpoint restored')

    def _qemu_delta_identity(self):
        return dict(run=self.run_id,version=self.version['id'],epoch=self._runtime_epoch,
                    source_sha256=self.metadata['source_sha256'],version_sha256=self.metadata['version_sha256'],
                    project=self._history_identity())

    def _qemu_delta_require(self, *, valid=True):
        history = getattr(self,'_qemu_cpu_delta_history',None)
        if self.closed or history is None or (valid and not history['valid']):
            raise ValueError('No valid selected CPU delta history')
        if history['identity'] != self._qemu_delta_identity():
            history.update(valid=False,invalid_reason='live process identity changed')
            raise ValueError('Selected CPU delta belongs to a different live process epoch')
        return history

    def _qemu_delta_observe(self, history, *, check_binding=True):
        from .qemu_cpu_undo_runtime import observe
        value = observe(self,history['ranges'],history['registers'])
        if (not isinstance(value,dict) or not isinstance(value.get('cpu'),dict)
                or set(value['cpu']) != set(history['registers'])
                or any(type(v) is not int or v < 0 for v in value['cpu'].values())
                or not isinstance(value.get('ram'),list) or len(value['ram']) != len(history['ranges'])
                or any(not isinstance(data,bytes) or len(data) != row['length']
                       for data,row in zip(value['ram'],history['ranges']))
                or not isinstance(value.get('binding'),dict)):
            raise ValueError('Native selected CPU delta observation is invalid')
        if check_binding and history.get('binding') is not None and value['binding'] != history['binding']:
            history.update(valid=False,invalid_reason='native selected CPU delta context or ownership changed')
            raise ValueError('Native selected CPU delta context or ownership changed')
        return value

    def _qemu_delta_anchor_row(self, history):
        anchor = history['anchor']
        row = self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(anchor['artifact'],)).fetchone()
        if (row is None or row['kind'] != 'state' or row['run'] != self.run_id or row['version'] != self.version['id']
                or row['sha256'] != anchor['sha256'] or len(row['data']) != anchor['size']
                or _sha(bytes(row['data'])) != anchor['sha256']):
            raise ValueError('Selected CPU delta recovery anchor is missing or corrupt')
        from .qemu_dos_checkpoint import checkpoint_format, _unarchive, _compatibility, _json
        CHECKPOINT_FORMAT = checkpoint_format(self)
        metadata=json.loads(row['metadata'])
        if (not isinstance(metadata,dict) or metadata.get('format') != CHECKPOINT_FORMAT
                or metadata.get('source_sha256') != self.metadata['source_sha256']
                or metadata.get('version_sha256') != self.metadata['version_sha256']
                or metadata.get('host_files_restored') is not False):
            raise ValueError('Selected CPU delta recovery anchor identity differs')
        self._history_remaining_ms()
        _, bundle = _unarchive(bytes(row['data']))
        self._history_remaining_ms()
        expected=dict(format=CHECKPOINT_FORMAT,source_sha256=self.metadata['source_sha256'],
                      version_sha256=self.metadata['version_sha256'],version=self.version['id'],
                      runtime=_compatibility(self))
        if (metadata.get('sidecar_sha256') != _sha(_json(bundle))
                or any(bundle.get(key) != value for key,value in expected.items())):
            raise ValueError('Selected CPU delta anchor sidecar or runtime identity differs')
        return row

    def _qemu_delta_project_reserve(self, needed):
        used=int(self.project.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
        if used + needed > 256*1024**2:
            raise ValueError('Project artifact budget cannot reserve selected CPU delta evidence')

    def _qemu_delta_chain(self, history, target):
        cpu=deepcopy(history['initial_cpu']); ram=list(history['initial_ram'])
        selected=(deepcopy(cpu),list(ram)) if target == 0 else None
        parent=history['anchor']['sha256']
        for entry in history['entries'][:history['cursor']]:
            self._history_remaining_ms()
            row=self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(entry['artifact'],)).fetchone()
            if (row is None or row['kind'] != 'cpu-ram-delta' or row['run'] != self.run_id
                    or row['version'] != self.version['id'] or row['sha256'] != entry['sha256']
                    or len(row['data']) != entry['size'] or _sha(bytes(row['data'])) != entry['sha256']):
                raise ValueError('Selected CPU delta artifact is missing or corrupt')
            doc=json.loads(bytes(row['data']))
            if (doc.get('format') != FORMAT or doc.get('history') != history['id']
                    or doc.get('identity') != history['identity'] or doc.get('binding') != history['binding']
                    or doc.get('ranges') != history['ranges'] or doc.get('parent_sha256') != parent
                    or doc.get('index') != entry['index'] or doc.get('before') != _fingerprint(cpu,ram)):
                raise ValueError('Selected CPU delta history chain differs')
            for name, change in doc['registers'].items():
                if name not in cpu or cpu[name] != change['before'] or type(change['after']) is not int or change['after'] < 0:
                    raise ValueError('Selected CPU delta register chain differs')
                cpu[name]=change['after']
            for change in doc['memory']:
                n, offset = change['range'],change['offset']
                before, after = bytes.fromhex(change['before_hex']),bytes.fromhex(change['after_hex'])
                if (type(n) is not int or not 0 <= n < len(ram) or type(offset) is not int or offset < 0
                        or not before or len(before) != len(after) or offset+len(before)>len(ram[n])
                        or ram[n][offset:offset+len(before)] != before):
                    raise ValueError('Selected CPU delta memory chain differs')
                ram[n]=ram[n][:offset]+after+ram[n][offset+len(before):]
            if doc.get('after') != _fingerprint(cpu,ram):
                raise ValueError('Selected CPU delta after-state hash differs')
            if entry['index'] == target: selected=(deepcopy(cpu),list(ram))
            parent=entry['sha256']
        if selected is None: raise ValueError('Selected CPU delta target is unavailable')
        return (cpu,ram),selected

    @_history_operation
    def cpu_delta_start(self, ranges, *, registers=None, max_steps=16, max_bytes=67108864, timeout_ms=60000):
        from .qemu_cpu_undo_runtime import REGISTERS, normalize_ranges
        _bounded(max_steps,'max_steps',1,128); _bounded(max_bytes,'max_bytes',1,256*1024**2)
        validate_ranges(ranges)
        selected=sorted(REGISTERS) if registers is None else registers
        if (not isinstance(selected,list) or not selected or len(selected)>len(REGISTERS)
                or any(not isinstance(n,str) or n not in REGISTERS for n in selected)
                or len(set(selected)) != len(selected)):
            raise ValueError('Expected unique exposed native CPU delta registers')
        prior=getattr(self,'_qemu_cpu_delta_history',None)
        if prior and prior['frozen']: raise ValueError('Recover the frozen selected CPU delta state first')
        self._history_supported(); self._history_admission()
        normalized=normalize_ranges(self,ranges)
        history=dict(id=uuid.uuid4().hex,identity=self._qemu_delta_identity(),ranges=deepcopy(normalized),
                     registers=list(selected),binding=None,valid=True,frozen=False,invalid_reason=None,
                     cursor=0,entries=[],captures_used=0,delta_bytes_used=0,provenance_bytes_used=0,
                     max_steps=max_steps,max_bytes=max_bytes)
        with self._qemu_delta_owned():
            before=self._qemu_delta_observe(history)
            history['binding']=deepcopy(before['binding'])
            anchor=self.save_state('cpu-delta-anchor.qcow2',max_bytes=min(max_bytes,128*1024**2))
            history['anchor']={key:anchor[key] for key in ('artifact','sha256','size')}
            try:
                self._qemu_delta_anchor_row(history)
                after=self._qemu_delta_observe(history)
                if before['cpu'] != after['cpu'] or before['ram'] != after['ram']:
                    raise ValueError('Selected CPU/RAM changed during full anchor capture')
                history['initial_cpu']=deepcopy(after['cpu']);history['initial_ram']=list(after['ram'])
                history['per_step_reserve']=(128*sum(r['length'] for r in normalized)+16384
                    + 2*len(_encoded(dict(identity=history['identity'],binding=history['binding'],ranges=normalized))))
                self._qemu_cpu_delta_history=history
                self._event('qemu-cpu-delta-start',dict(format=FORMAT,history=history['id'],anchor=history['anchor'],
                    ranges=history['ranges'],registers=history['registers'],binding=history['binding']))
            except BaseException:
                self.close(); raise
        return self.cpu_delta_status()

    @_history_operation
    def cpu_delta_status(self):
        h=getattr(self,'_qemu_cpu_delta_history',None)
        if h is None: return dict(format=FORMAT,active=False,valid=False,frozen=False,execution_allowed=not self.closed)
        return dict(format=FORMAT,active=not self.closed,history=h['id'],valid=h['valid'],frozen=h['frozen'],
            invalid_reason=h['invalid_reason'],cursor=h['cursor'],captures_used=h['captures_used'],
            anchor=deepcopy(h['anchor']),ranges=deepcopy(h['ranges']),registers=list(h['registers']),
            anchor_bytes_used=h['anchor']['size'],delta_bytes_used=h['delta_bytes_used'],
            provenance_bytes_used=h['provenance_bytes_used'],
            total_bytes_used=h['anchor']['size']+h['delta_bytes_used']+h['provenance_bytes_used'],
            max_steps=h['max_steps'],max_bytes=h['max_bytes'],
            full_machine_restored=False,devices_restored=False,host_files_restored=False,
            unselected_ram='current',hidden_cpu='unknown',
            resume_safe=False,execution_allowed=not h['frozen'] and not self.closed,
            interval='observed native single-step stop',instruction_retirement='unknown')

    @_history_operation
    def cpu_delta_record(self, count=1, timeout_ms=10000):
        _bounded(count,'count',1,128); h=self._qemu_delta_require()
        if h['frozen']: raise ValueError('Selected CPU delta state is frozen')
        if h['captures_used']+count > h['max_steps']: raise ValueError('Selected CPU delta capture budget exhausted')
        if h['anchor']['size']+h['delta_bytes_used']+h['provenance_bytes_used']+count*h['per_step_reserve'] > h['max_bytes']:
            raise ValueError('Selected CPU delta byte budget cannot reserve requested intervals')
        self._qemu_delta_project_reserve(count*h['per_step_reserve'])
        self._qemu_delta_anchor_row(h)
        expected,_=self._qemu_delta_chain(h,h['cursor'])
        records=[]
        with self._qemu_delta_owned():
            for _ in range(count):
                try:
                    before=self._qemu_delta_observe(h)
                    if (before['cpu'],before['ram']) != expected:
                        h.update(valid=False,invalid_reason='selected CPU/RAM changed outside the recorded intervals')
                        raise ValueError('Selected CPU/RAM differs from recorded state')
                    if getattr(self,'_qemu_hook_pending',None) is not None:
                        raise ValueError('Resolve the pending hook before recording a native step')
                    pc=before.get('register_snapshot',{}).get('linear_pc')
                    hooks=getattr(self,'_qemu_hooks',{})
                    if hooks and pc is None:
                        raise ValueError('Native step cannot qualify the current hook location')
                    if pc is not None:
                        pc=int(pc,0) if isinstance(pc,str) else pc
                        if any(control.get('access','x') == 'x' and control.get('runtime_address') == pc
                               for control in hooks.values()):
                            raise ValueError('Native step starts at an active hook; dispatch it first')
                    execution_preflight=getattr(self,'_execution_preflight',None)
                    if execution_preflight is not None:
                        execution_preflight('s',self._history_remaining_ms())
                except ValueError as error:
                    if records:
                        error.result=dict(format=FORMAT,outcome='preflight_refused',requested_count=count,
                            recorded_count=len(records),records=deepcopy(records),
                            history=QemuCpuDeltaMixin.cpu_delta_status.__wrapped__(self))
                    raise
                self._event('qemu-cpu-delta-intent',dict(history=h['id'],kind='step',cursor=h['cursor']))
                try:
                    stop=self.step(timeout_ms=self._history_remaining_ms())
                    if not _ordinary(stop):
                        h.update(valid=False,invalid_reason='native step stopped before an ordinary interval')
                        self._event('qemu-cpu-delta-stop',dict(history=h['id'],stop=deepcopy(stop)))
                        return dict(format=FORMAT,outcome='interrupted',requested_count=count,
                                    recorded_count=len(records),records=records,stop=deepcopy(stop),history=self.cpu_delta_status())
                    after=self._qemu_delta_observe(h,check_binding=False)
                    if after['binding'] != h['binding']:
                        h.update(valid=False,invalid_reason='native step changed the selected process or control context')
                        self._event('qemu-cpu-delta-stop',dict(history=h['id'],stop=deepcopy(stop),
                            outcome='context_changed',binding=deepcopy(after['binding'])))
                        return dict(format=FORMAT,outcome='context_changed',requested_count=count,
                                    recorded_count=len(records),records=records,stop=deepcopy(stop),
                                    observed_binding=deepcopy(after['binding']),history=self.cpu_delta_status())
                    parent=h['entries'][h['cursor']-1]['sha256'] if h['cursor'] else h['anchor']['sha256']
                    doc=dict(format=FORMAT,history=h['id'],identity=h['identity'],binding=h['binding'],ranges=h['ranges'],
                        index=h['cursor']+1,parent_sha256=parent,before=_fingerprint(before['cpu'],before['ram']),
                        after=_fingerprint(after['cpu'],after['ram']),
                        registers={k:dict(before=before['cpu'][k],after=v) for k,v in after['cpu'].items() if v != before['cpu'][k]},
                        memory=_runs(before['ram'],after['ram']),stop=deepcopy(stop),instruction_retirement='unknown')
                    data=_encoded(doc)
                    if len(data)>h['per_step_reserve']: raise ValueError('Selected CPU delta exceeded reserved byte budget')
                    artifact=self._artifact('qemu-cpu-ram-delta.json','cpu-ram-delta',data,
                        dict(format=FORMAT,history=h['id'],index=doc['index'],parent_sha256=parent))
                    if artifact.get('sha256') != _sha(data) or artifact.get('size') != len(data):
                        raise ValueError('Selected CPU delta artifact receipt differs')
                    h['entries']=h['entries'][:h['cursor']]+[dict(index=doc['index'],artifact=artifact['artifact'],sha256=artifact['sha256'],size=artifact['size'])]
                    h['cursor']+=1;h['captures_used']+=1;h['delta_bytes_used']+=len(data)
                    records.append(deepcopy(h['entries'][-1]));expected=(after['cpu'],after['ram'])
                except BaseException:
                    h.update(valid=False,invalid_reason='selected CPU delta execution or journal failed')
                    self.close(); raise
        return dict(format=FORMAT,outcome='completed',requested_count=count,recorded_count=len(records),records=records,history=self.cpu_delta_status())

    @_history_operation
    def cpu_delta_rewind(self, count=1, *, policy=None, timeout_ms=60000):
        from .qemu_cpu_undo_runtime import prepare, apply
        _bounded(count,'count',1,128); h=self._qemu_delta_require()
        validate_policy(policy,registers=h['registers'])
        if policy and policy.get('allow_partial_resume',False):
            raise ValueError('Native selected CPU delta does not permit partial resume')
        if h['frozen'] or count > h['cursor']: raise ValueError('Selected CPU delta rewind is unavailable')
        reserve=262144+2*len(_encoded(dict(identity=h['identity'],binding=h['binding'],ranges=h['ranges'],policy=policy)))
        if h['anchor']['size']+h['delta_bytes_used']+h['provenance_bytes_used']+reserve > h['max_bytes']:
            raise ValueError('Selected CPU delta byte budget cannot reserve undo provenance')
        self._qemu_delta_project_reserve(reserve)
        self._qemu_delta_anchor_row(h)
        expected,selected=self._qemu_delta_chain(h,h['cursor']-count)
        with self._qemu_delta_owned():
            observed=self._qemu_delta_observe(h)
            if (observed['cpu'],observed['ram']) != expected:
                h.update(valid=False,invalid_reason='selected CPU/RAM preimage changed')
                raise ValueError('Selected CPU/RAM preimage differs from recorded state')
            cpu,ram=deepcopy(selected[0]),list(selected[1]); preserved=dict(registers={},memory=[])
            if policy:
                for name in policy.get('preserve_registers',[]):
                    cpu[name]=observed['cpu'][name];preserved['registers'][name]=cpu[name]
                from .qemu_cpu_undo_runtime import normalize_ranges
                ranges=normalize_ranges(self,policy.get('preserve_memory',[])) if policy.get('preserve_memory') else []
                for item in ranges:
                    address=int(item['linear'],0) if isinstance(item['linear'],str) else item['linear']
                    for n,region in enumerate(h['ranges']):
                        base=int(region['linear'],0) if isinstance(region['linear'],str) else region['linear']
                        offset=address-base
                        if 0<=offset and offset+item['length']<=region['length']:
                            value=observed['ram'][n][offset:offset+item['length']]
                            ram[n]=ram[n][:offset]+value+ram[n][offset+len(value):]
                            preserved['memory'].append(dict(range=deepcopy(item),sha256=_sha(value)))
                            break
                    else: raise ValueError('Preserved memory must fit an observed CPU delta range')
            plan=prepare(self,h['ranges'],observed,cpu,ram)
            self._event('qemu-cpu-delta-intent',dict(history=h['id'],kind='undo',cursor=h['cursor'],target=h['cursor']-count))
            h.update(frozen=True,valid=False,invalid_reason='selected CPU/RAM partial undo requires full checkpoint recovery')
            try:
                result=apply(self,plan)
                after=self._qemu_delta_observe(h,check_binding=False)
                applied = result.get('observation') if isinstance(result,dict) else None
                if (not isinstance(applied,dict) or applied.get('binding') != after['binding']
                        or applied.get('cpu') != after['cpu'] or applied.get('ram') != after['ram']
                        or after['cpu'] != cpu or after['ram'] != ram):
                    raise ValueError('Selected CPU/RAM undo readback differs')
                provenance=dict(format=FORMAT,history=h['id'],source_cursor=h['cursor'],target_cursor=h['cursor']-count,
                    anchor=deepcopy(h['anchor']),policy=deepcopy(policy),preserved=preserved,
                    observed=_fingerprint(observed['cpu'],observed['ram']),restored=_fingerprint(cpu,ram),
                    full_machine_restored=False,devices_restored=False,host_files_restored=False,
                    resume_safe=False,execution_allowed=False,
                    identity=deepcopy(h['identity']),binding=deepcopy(h['binding']),
                    ranges=deepcopy(h['ranges']),registers=list(h['registers']),
                    native_ram_transition=deepcopy(result.get('ram_transition')) if isinstance(result,dict) else None)
                data=_encoded(provenance)
                if len(data) > reserve:
                    raise ValueError('Selected CPU delta undo provenance exceeded its reservation')
                artifact=self._artifact('qemu-cpu-delta-undo.json','cpu-ram-delta-undo',data,dict(format=FORMAT,history=h['id']))
                if artifact.get('sha256') != _sha(data) or artifact.get('size') != len(data):
                    raise ValueError('Selected CPU delta provenance receipt differs')
                h['cursor']-=count
                h['provenance_bytes_used']+=len(data)
                self._event('qemu-cpu-delta-rewind',dict(artifact=artifact['artifact'],sha256=artifact['sha256'],**provenance))
            except BaseException:
                self.close(); raise
        return dict(format=FORMAT,partial_restored=True,full_machine_restored=False,devices_restored=False,host_files_restored=False,
                    resume_safe=False,execution_allowed=False,provenance=artifact,history=self.cpu_delta_status())

    @_history_operation
    def cpu_delta_recover(self, *, timeout_ms=60000):
        h=self._qemu_delta_require(valid=False)
        self._qemu_delta_anchor_row(h)
        with self._qemu_delta_owned():
            self._qemu_cpu_delta_full_load_depth=getattr(self,'_qemu_cpu_delta_full_load_depth',0)+1
            try:
                result=self.load_state(h['anchor']['artifact'],timeout_ms=self._history_remaining_ms())
                if not isinstance(result,dict) or result.get('source_binding_restored') is not True:
                    raise ValueError('Full native anchor recovery did not verify source binding')
                self._cpu_delta_full_restore_complete()
                self._event('qemu-cpu-delta-recover',dict(history=h['id'],anchor=h['anchor'],restore=result))
            except BaseException:
                self.close(); raise
            finally: self._qemu_cpu_delta_full_load_depth-=1
        return dict(format=FORMAT,full_native_anchor_loaded=True,restore=result,history=self.cpu_delta_status())
