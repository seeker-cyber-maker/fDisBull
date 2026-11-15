"""Owned LE source recipes with fresh stopped relations, never task lifetimes."""
from copy import deepcopy
from functools import partial
import hashlib
import json
from pathlib import Path
import time
import uuid

from .qemu_machine import machine_trace_operation
from .qemu_dos_source_admission import _parameters, _source, _context, _gdt


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _producer():
    root = Path(__file__).parent
    return {name: _sha((root/name).read_bytes()) for name in
            ('le.py', 'qemu_dos_le_match.py', 'qemu_dos_source_admission.py',
             'qemu_dos_le_identity.py', 'qemu_dos_le_binding.py', 'qemu_machine.py')}


class QemuDOSLEBindingMixin:
    def _le_source_execution_bound(self):
        state = getattr(self, '_le_source', None)
        return state is not None and state['state']!='retired'

    def _le_source_owner_valid(self, binding):
        process = self._process
        return (not self.closed and self.vm is binding['owner']
            and self.vm.process is binding['process'] and self.vm.process is not None
            and self.vm.process.poll() is None and self.vm.qmp is not None
            and not getattr(self.vm, '_fdisbull_control_quarantine', None)
            and process['state']=='active' and not process.get('machine_closed')
            and self._runtime_epoch==binding['recipe']['capture_epoch']
            and process['capture_epoch']==self._runtime_epoch)

    def _le_source_bound(self):
        """Handle selection only; no guest observation or implicit admission."""
        return getattr(self, '_le_source', None) is not None

    def _le_source_summary(self):
        state = getattr(self, '_le_source', None)
        if state is None:
            return dict(source_view='embedded-le', state='unbound', live=False)
        recipe = state['recipe']
        return dict(source_view='embedded-le', binding_id=recipe['binding_id'],
            run=recipe['run'], capture_epoch=recipe['capture_epoch'],
            source_sha256=recipe['source_sha256'], version=recipe['version'],
            version_sha256=recipe['version_sha256'], state=state['state'],
            live=state['state']=='qualified-stopped', generation=state['generation'],
            observations=state['observations'], reason=state.get('reason'),
            artifact=deepcopy(state.get('binding_artifact')),
            last_observation=deepcopy(state.get('last_observation')),
            continuity='source recipe and owned stop sequence; not OS/task/allocation lifetime',
            execution_coverage=state.get('execution_coverage', 'stopped-only'),
            checkpoint_binding_restored=False)

    def _le_source_retire(self, reason, *, persist=False):
        state = getattr(self, '_le_source', None)
        if state is None or state['state']=='retired':
            return
        state.update(state='retired', reason=reason, generation=state['generation']+1)
        if persist:
            self._event('dos-source-binding-state', self._le_source_summary())

    def _le_source_lifecycle(self, operation, reason):
        state = getattr(self, '_le_source', None)
        if state is None or state['state']=='retired' or getattr(self, '_le_source_observing', False):
            return
        if operation=='close':
            self._le_source_retire(reason)
        elif operation=='before_execution':
            if reason not in ('machine-gdb-step', 'machine-gdb-run'):
                self._le_source_retire(reason, persist=True)
                return
            # Current authority ends before dispatch. A normal run has an
            # unobserved interval; its later endpoint starts a new generation.
            try:
                _source(self, state['recipe']['source_sha256'])
                if _producer()!=state['producer'] or not self._le_source_owner_valid(state):
                    raise ValueError('Protected source owner/producer identity changed before execution')
            except ValueError:
                self._le_source_retire('source/owner identity changed before execution', persist=True)
                raise
            if reason=='machine-gdb-run':
                state['generation']+=1
            state.update(state='pending-owned-execution', reason=reason,
                execution_coverage='stopped-endpoints' if reason=='machine-gdb-run' else 'stepped-boundaries')
            self._event('dos-source-binding-state', self._le_source_summary())
        elif operation=='after_stop':
            limits = [getattr(self, '_deadline', None), getattr(self, '_rpc_deadline', None),
                      getattr(self, '_le_source_execution_deadline', None),
                      getattr(self.vm, 'operation_deadline', None),
                      *[getattr(c, 'operation_deadline', None) for c in
                        (getattr(self.vm, 'gdb', None), getattr(self.vm, 'qmp', None)) if c is not None]]
            limits = [v for v in limits if v is not None]
            remaining = int((min(limits)-time.monotonic())*1000) if limits else 10000
            if remaining<1:
                state.update(state='out-of-scope', reason='operation budget expired before source revalidation')
                self._event('dos-source-binding-state', self._le_source_summary())
                return
            timeout = min(10000, remaining)
            state['observation_io_started'] = False
            previous_deadline = getattr(self, '_deadline', None)
            try:
                # Preserve the absolute limit across wrapper/admission delay;
                # a rounded relative allowance must not widen this request.
                if limits:
                    self._deadline = min(limits)
                self._le_source_refresh(timeout_ms=timeout)
            except TimeoutError:
                if state['observation_io_started']:
                    raise
                state.update(state='out-of-scope', reason='operation budget expired before source observation I/O')
            finally:
                self._deadline = previous_deadline
            self._event('dos-source-binding-state', self._le_source_summary())

    @machine_trace_operation
    def _le_source_refresh(self, *, timeout_ms=10000):
        state = getattr(self, '_le_source', None)
        if state is not None and state['state']!='retired':
            return self._le_source_observe(state, state['observations']+1)

    def _le_source_operation_guard(self, name, args, kwargs):
        state = getattr(self, '_le_source', None)
        if state is None or state['state']=='retired':
            return
        # Some native recovery paths deliberately bypass ordinary history
        # guards. Retire source authority before those operations as well.
        mutating = {'load_state', 'load_anchor_stone', 'rewind', 'timeline_rewind',
                    'restore_experiment', 'cpu_delta_rewind', 'cpu_delta_recover',
                    'write_registers', 'write_memory', 'write_engine_state'}
        task_read = {'dos_task_observe', 'dos_task_context', 'dos_task_scheduler_observe', 'dos_task_memory'}
        if name in mutating or name.startswith('dos_task_') and name not in task_read and name!='dos_task_layers':
            self._le_source_retire('operation: '+name, persist=True)

    @partial(machine_trace_operation, label='Protected source binding', parameter_validator=_parameters)
    def dos_source_bind(self, *, name='le-source-binding.json', max_compare_bytes=524288,
                        max_scan_bytes=16777216, timeout_ms=10000, expected_source_sha256=None):
        from .le import load_runtime_le_carrier
        from .qemu_dos_le_identity import make_recipe, BINDING_FORMAT
        self._le_source_retire('replaced by explicit binding', persist=True)
        admission = self.dos_source_admit(name='le-source-seed.json',
            max_compare_bytes=max_compare_bytes, max_scan_bytes=max_scan_bytes,
            timeout_ms=self._remaining(), expected_source_sha256=expected_source_sha256)
        if admission['status']!='admitted':
            raise ValueError('Protected source binding requires an admitted current LE source')
        row = self.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',
                                      (admission['artifact'],)).fetchone()
        document = json.loads(bytes(row['data']))
        raw, _ = _source(self, expected_source_sha256)
        image = load_runtime_le_carrier(raw)
        recipe = make_recipe(image, document, binding_id=uuid.uuid4().hex)
        state = dict(source_view='embedded-le', recipe=recipe, image=image,
            capture_epoch=self._runtime_epoch, owner=self.vm, process=self.vm.process,
            producer=_producer(), material={}, state='preparing', generation=1,
            observations=0, reason=None, execution_coverage='stopped-only')
        event, stopped = self._le_source_observe(state, 1)
        if not event['source_qualification']['qualified']:
            raise ValueError('Protected source binding has no fully qualified current instruction: '+
                             str(event['source_qualification'].get('reason')))
        seed = {key: admission[key] for key in ('artifact', 'sha256', 'size')}
        payload = dict(format=BINDING_FORMAT, recipe=recipe, admission=seed,
                       gdt_hex=state['material']['gdt_hex'], producer=state['producer'])
        data = _encoded(payload)
        if len(data)>4*1024*1024:
            raise ValueError('Protected source binding exceeds its private artifact budget')
        self._remaining()
        with self.project.transaction(True):
            if (not self._le_source_owner_valid(state) or _producer()!=state['producer']
                    or _source(self, expected_source_sha256, internal_transaction=True)[1]['version_sha256']!=recipe['version_sha256']
                    or self.registers()!=stopped['registers'] or not self._le_source_owner_valid(state)
                    or _producer()!=state['producer']):
                raise ValueError('Protected source changed before binding publication')
            artifact = self._artifact(name, 'dos-source-binding', data,
                dict(format=BINDING_FORMAT, binding_id=recipe['binding_id'], source_view='embedded-le',
                     source_sha256=recipe['source_sha256'], capture_epoch=recipe['capture_epoch']))
            self._event('dos-source-bind', dict(artifact=artifact['artifact'], sha256=artifact['sha256'],
                binding_id=recipe['binding_id'], capture_epoch=recipe['capture_epoch'], admission=seed))
            self._remaining()
        state['binding_artifact'] = artifact
        self._le_source = state
        return self._le_source_summary()

    @machine_trace_operation
    def dos_source_binding(self, *, refresh=False, timeout_ms=10000):
        if type(refresh) is not bool:
            raise ValueError('Protected source refresh must be boolean')
        state = getattr(self, '_le_source', None)
        if refresh and state is not None and state['state']!='retired':
            self._le_source_observe(state, state['observations']+1)
        return self._le_source_summary()

    @machine_trace_operation
    def dos_source_unbind(self, *, timeout_ms=10000):
        self._le_source_retire('explicit unbind', persist=True)
        previous = self._le_source_summary()
        self._le_source = None
        return dict(source_view='embedded-le', state='unbound', live=False, previous=previous)

    def _le_source_trace_binding(self):
        state = getattr(self, '_le_source', None)
        if state is None or state['state']=='retired':
            raise ValueError('Call dos_source_bind before tracing the embedded LE source')
        self._le_source_observe(state, state['observations']+1)
        return state

    def _le_source_observe(self, binding, sequence, *, clocked=False):
        from .qemu_dos_le_identity import qualify_instruction
        from .qemu_dos_trace import _clock_sample, _clock_bracket
        if binding['state']=='retired':
            raise ValueError('Protected source recipe is retired; bind again explicitly')
        binding.update(state='observing', reason='fresh stopped validation pending')
        binding['observation_io_started'] = False
        self._remaining()
        recipe = binding['recipe']
        if not self._le_source_owner_valid(binding):
            binding.update(state='retired', reason='owner or capture epoch changed')
            self._le_source_retire('owner or capture epoch changed')
            raise ValueError('Protected source binding owner/epoch is no longer active')
        previous = getattr(self, '_le_source_observing', False)
        self._le_source_observing = True
        before_clock = None
        registers = None; cpu = None; reads = {}; gdt = None
        qualification = None
        try:
            before_clock = _clock_sample(self) if clocked else None
            try:
                raw, identity = _source(self, recipe['source_sha256'])
            except ValueError:
                binding.update(state='retired', reason='source/version identity changed')
                raise
            if (identity['version']!=recipe['version'] or identity['version_sha256']!=recipe['version_sha256']
                    or _sha(raw)!=recipe['source_sha256'] or _producer()!=binding['producer']):
                binding.update(state='retired', reason='source/version/producer changed')
                raise ValueError('Protected source recipe identity changed')
            self._remaining()
            binding['observation_io_started'] = True
            remote = self._stopped()
            registers = self.registers()
            if getattr(self, '_layer_active', None) or getattr(self, '_dos_task_monitor', None):
                raise ValueError('Protected LE source requires an unlayered current machine view')
            cpu = _context(registers); table = _gdt(self)
            seed_table = recipe['initial_admission']['gdt']
            if any(table[k]!=seed_table[k] for k in ('base','limit')):
                raise ValueError('Protected LE GDT placement changed')
            cpu.update(gdtr_base=table['base'], gdtr_limit=table['limit'])
            ram_end = min(self.vm.machine_configuration['memory_mib']<<20, 0xc0000000)
            def read(address, length):
                self._remaining()
                if (type(address) is not int or type(length) is not int or not 1<=length<=65536
                        or not (0<=address<address+length<=0xa0000 or 0x100000<=address<address+length<=ram_end)):
                    raise ValueError('Protected LE source read exceeds physical RAM')
                key = (address,length)
                if key not in reads:
                    if sum(n for _,n in reads)+length>524288:
                        raise ValueError('Protected LE source observation exceeds its read budget')
                    physical = remote.memory(address,length,space='physical',timeout_ms=self._remaining())
                    virtual = remote.memory(address,length,space='virtual',timeout_ms=self._remaining())
                    if len(physical)!=length or physical!=virtual:
                        raise ValueError('Protected LE physical and linear readbacks differ')
                    reads[key] = physical
                return reads[key]
            gdt = read(table['base'],table['limit']+1)
            qualification = qualify_instruction(binding['image'],recipe,cpu,gdt,read)
            for (address,length), value in list(reads.items()):
                if (remote.memory(address,length,space='physical',timeout_ms=self._remaining())!=value
                        or remote.memory(address,length,space='virtual',timeout_ms=self._remaining())!=value):
                    raise ValueError('Protected LE source bytes changed during observation')
            if (self.registers()!=registers or _gdt(self)!=table or not self._le_source_owner_valid(binding)
                    or _source(self,recipe['source_sha256'])[1]!=identity or _producer()!=binding['producer']):
                if not self._le_source_owner_valid(binding):
                    binding.update(state='retired', reason='owner or capture epoch changed during observation')
                raise ValueError('Protected LE stopped source/context changed during observation')
            binding['material'] = dict(gdt_hex=gdt.hex())
        except ValueError as error:
            if binding['state']=='retired':
                raise
            qualification = dict(qualified=False,reason=str(error),instruction_size=None,
                execution_bytes='',source_instruction_sha256=None,source_location=None,context=None)
            if registers is None:
                raise
        except BaseException as error:
            if binding['state']!='retired':
                binding.update(state='out-of-scope', reason=type(error).__name__+': '+str(error)[:1024])
            raise
        finally:
            self._le_source_observing = previous
        state = registers.get('address_state', {})
        cs = state.get('segments', {}).get('cs', {})
        address = dict(space='segmented',segment=hex(int(registers['registers']['cs'],0)),
                       offset=registers['instruction_pointer'])
        context = dict(cpu_mode=registers['cpu_mode'], code_bits=state.get('code_bits'),
            paging_enabled=state.get('paging'), a20=state.get('a20'), cs=deepcopy(cs),
            source_generation=binding['generation'],
            **{k.lower():v for k,v in state.get('control',{}).items()})
        code = qualification.get('execution_bytes','')
        identity = dict(source_version=self.version['id'],runtime_address=address,project_address=None,
            source_location=deepcopy(qualification.get('source_location')),
            context=qualification.get('context'),
            source_instruction_sha256=qualification.get('source_instruction_sha256'))
        raw_event = dict(sequence=sequence,address=registers.get('linear_pc'),segmented_address=address,
            bytes=code,execution_bytes=code,registers=deepcopy(registers['registers']),
            cpu_mode=registers['cpu_mode'],code_bits=state.get('code_bits'),address_context=context,
            task_id=None,mapping_id=recipe['binding_id'],project_address=None,identity=identity,
            source_qualification=deepcopy(qualification),active_layers=[],
            le_source_witness=dict(cpu=cpu,gdt_sha256=_sha(gdt) if gdt is not None else None,
                readback=[dict(address=a,length=n,hex=b.hex()) for (a,n),b in reads.items()
                          if gdt is None or (a,n)!=(cpu['gdtr_base'],cpu['gdtr_limit']+1)]),
            observation=dict(registers_stage='before-instruction',instruction_completed=False,
                flags_materialized=True,evidence='revalidated owned LE stopped boundary; no retirement/task lifetime claim'))
        stopped = dict(registers=registers,address=address,source_qualification=deepcopy(qualification))
        if clocked:
            raw_event['clock'] = _clock_bracket(self,before_clock,_clock_sample(self))
            stopped['clock'] = deepcopy(raw_event['clock'])
        from .execution_trace import MAX_BOUNDARY_BYTES
        if len(_encoded(raw_event))>MAX_BOUNDARY_BYTES:
            raise ValueError('Protected LE stopped boundary exceeds its 8 KiB budget')
        self._remaining()
        if not self._le_source_owner_valid(binding):
            binding.update(state='retired', reason='owner changed before observation publication')
            raise ValueError('Protected source owner changed before observation publication')
        binding['observations']+=1
        binding.update(state='qualified-stopped' if qualification['qualified'] else 'out-of-scope',
            reason=qualification.get('reason'), last_observation=dict(sequence=binding['observations'],
                qualified=qualification['qualified'], source_location=deepcopy(qualification.get('source_location')),
                instruction_sha256=qualification.get('source_instruction_sha256'),
                linear_pc=registers.get('linear_pc')))
        return raw_event, stopped
