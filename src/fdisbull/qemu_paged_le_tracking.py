"""Opt-in, independently witnessed LE observations at owned stopped boundaries."""

from copy import deepcopy
import json
import hashlib
from pathlib import Path
import uuid

from .qemu_machine import machine_trace_operation
from .dosbox_rpc import DebuggerError
from .qemu_dos_source_admission import _parameters, _source
from .qemu_dos_le_binding import _producer


def _paged_producer():
    from .qemu_paged_le_capture import _producer as capture_producer

    root = Path(__file__).parent
    names = ('qemu_paged_le_observation.py', 'qemu_paged_le_tracking.py')
    return {
        **_producer(),
        **capture_producer(),
        **{name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
    }


class QemuPagedLETrackingMixin:
    @machine_trace_operation
    def dos_source_bind(
        self,
        *,
        name='le-source-binding.json',
        max_compare_bytes=524288,
        max_scan_bytes=16777216,
        timeout_ms=10000,
        expected_source_sha256=None,
        tracking=None,
    ):
        if tracking is None:
            return super().dos_source_bind(
                name=name,
                max_compare_bytes=max_compare_bytes,
                max_scan_bytes=max_scan_bytes,
                timeout_ms=timeout_ms,
                expected_source_sha256=expected_source_sha256,
            )
        _parameters(
            name=name,
            max_compare_bytes=max_compare_bytes,
            max_scan_bytes=max_scan_bytes,
            timeout_ms=timeout_ms,
            expected_source_sha256=expected_source_sha256,
        )
        if tracking != 'paged':
            raise ValueError('Protected source tracking must be paged or omitted')
        if (max_compare_bytes, max_scan_bytes) != (524288, 16777216):
            raise ValueError('Paged LE tracking supports only the default comparison and scan budgets')
        from .le import load_runtime_le_carrier

        self._le_source_retire('replaced by explicit binding', persist=True)
        raw, identity = _source(self, expected_source_sha256)
        recipe = dict(
            binding_id=uuid.uuid4().hex, run=self.run_id, capture_epoch=self._runtime_epoch, **identity
        )
        from .qemu_runtime_capture import _qemu_input_hashes

        from .qemu_paged_le_capture import _ram_limits
        _, high_end = _ram_limits(self.vm.machine_configuration)
        if high_end is not None:
            recipe['high_ram_end'] = high_end
        inputs = _qemu_input_hashes(self.metadata.get('runtime_inputs', {}))
        if hasattr(self.vm, 'inputs') and _qemu_input_hashes(self.vm.inputs) != inputs:
            raise ValueError('Paged LE native input identity differs')
        state = dict(
            source_view='embedded-le',
            tracking='paged',
            recipe=recipe,
            native_inputs=inputs,
            image=load_runtime_le_carrier(raw),
            owner=self.vm,
            process=self.vm.process,
            producer=_producer(),
            paged_producer=_paged_producer(),
            material={},
            state='preparing',
            generation=1,
            observations=0,
            reason=None,
            execution_coverage='stopped-only',
        )
        event, _ = self._paged_observe(state, 1)
        if not event['qualification']['qualified']:
            raise ValueError(
                'Paged LE tracking requires a qualified current instruction: '
                + str(event['qualification']['reason'])
            )
        data = json.dumps(
            dict(format='fdisbull-paged-le-tracking-binding-1', recipe=recipe),
            sort_keys=True,
            separators=(',', ':'),
        ).encode()
        state['binding_artifact'] = self._artifact(
            name,
            'dos-source-binding',
            data,
            dict(format='fdisbull-paged-le-tracking-binding-1', binding_id=recipe['binding_id']),
        )
        self._le_source = state
        self._event('dos-source-bind', self._le_source_summary())
        return self._le_source_summary()

    def _le_source_observe(self, binding, sequence, *, clocked=False):
        if binding.get('tracking') != 'paged':
            return super()._le_source_observe(binding, sequence, clocked=clocked)
        return self._paged_observe(binding, sequence, clocked=clocked)

    def _paged_observe(self, binding, sequence, *, clocked=False):
        from .qemu_paged_le_capture import _cpu, _ram_limits, _ram_extent, _pse36
        from .qemu_le_translation import parse_hmp
        from .qemu_paged_le_observation import observe, _unknown
        from .qemu_dos_trace import _clock_sample, _clock_bracket

        if binding['state'] == 'retired' or not self._le_source_owner_valid(binding):
            binding.update(state='retired', reason='owner or capture epoch changed')
            raise ValueError('Paged LE tracking owner/epoch is no longer active')
        binding.update(
            state='observing',
            reason='fresh stopped validation pending',
            observation_io_started=False,
            current_mapping=None,
        )
        registers = None
        before = _clock_sample(self) if clocked else None
        previous = getattr(self, '_le_source_observing', False)
        self._le_source_observing = True
        try:
            _, identity = _source(self, binding['recipe']['source_sha256'])
            if (
                any(identity[k] != binding['recipe'][k] for k in identity)
                or _producer() != binding['producer']
                or _paged_producer() != binding['paged_producer']
            ):
                binding.update(state='retired', reason='source or producer changed')
                raise ValueError('Paged LE source identity changed')
            registers = self.registers()
            binding['observation_io_started'] = True

            def context():
                return parse_hmp(
                    self.vm.qmp.call(
                        'human-monitor-command',
                        {'command-line': 'info registers'},
                        timeout_ms=self._remaining(),
                    )
                )

            ctx = context()
            cpu = _cpu(registers, ctx)
            if (
                getattr(self, '_layer_active', None)
                or getattr(self, '_dos_task_monitor', None)
                or getattr(self, '_dos_task_binding', None)
            ):
                raise ValueError('Paged LE tracking requires an unlayered machine view')
            memory_mib = self.vm.machine_configuration['memory_mib']
            if self.metadata['machine_configuration']['memory_mib'] != memory_mib:
                raise ValueError('Guest RAM configuration changed')
            end, high_end = _ram_limits(self.vm.machine_configuration)
            if (binding['recipe'].get('high_ram_end') != high_end or
                    _ram_limits(self.metadata['machine_configuration']) != (end, high_end)):
                raise ValueError('Guest RAM topology changed')
            remote = self._stopped()

            def physical(a, n):
                if not _ram_extent(a, n, end, high_end):
                    raise ValueError('Paged LE witness is outside RAM')
                return remote.memory(a, n, space='physical', timeout_ms=self._remaining())

            def virtual(a, n):
                return remote.memory(a, n, space='virtual', timeout_ms=self._remaining())

            from .qemu_le_translation import QEMU_TCG_PAE_ACCESSED_IMAGE
            options = {}
            if binding['native_inputs'].get('qemu_image') == QEMU_TCG_PAE_ACCESSED_IMAGE:
                options['qemu_image_sha256'] = QEMU_TCG_PAE_ACCESSED_IMAGE
            if high_end is not None:
                options['high_ram_end'] = high_end
            if _pse36(self.vm.machine_configuration, binding['native_inputs'].get('qemu_image')):
                options['pse36'] = True
            result = observe(binding['image'], identity['version'], cpu, ctx, physical, virtual, **options)
            from .qemu_runtime_capture import _qemu_input_hashes

            if (
                _ram_limits(self.vm.machine_configuration) != (end, high_end)
                or _ram_limits(self.metadata['machine_configuration']) != (end, high_end)
                or self.registers() != registers
                or context() != ctx
                or not self._le_source_owner_valid(binding)
                or _source(self, identity['source_sha256'])[1] != identity
                or _producer() != binding['producer']
                or _paged_producer() != binding['paged_producer']
                or _qemu_input_hashes(self.metadata.get('runtime_inputs', {}))
                != binding['native_inputs']
                or hasattr(self.vm, 'inputs')
                and _qemu_input_hashes(self.vm.inputs) != binding['native_inputs']
            ):
                raise DebuggerError('Paged LE stopped context changed during observation')
        except DebuggerError as error:
            binding.update(state='out-of-scope', reason=str(error), current_mapping=None)
            raise
        except ValueError as error:
            if binding['state'] == 'retired':
                raise
            result = _unknown(error)
            if registers is None:
                binding.update(state='out-of-scope', reason=str(error))
                raise
        except BaseException as error:
            binding.update(state='out-of-scope', reason=type(error).__name__ + ': ' + str(error)[:1024])
            raise
        finally:
            self._le_source_observing = previous
        binding['observations'] += 1
        q = result['qualification']
        binding.update(
            state='qualified-stopped' if q['qualified'] else 'out-of-scope',
            reason=q['reason'],
            current_mapping=deepcopy(result['mapping_identity']) if q['qualified'] else None,
            last_observation=dict(
                sequence=binding['observations'],
                qualified=q['qualified'],
                source_location=deepcopy(q['source_location']),
                instruction_sha256=q['source_instruction_sha256'],
                linear_pc=registers.get('linear_pc'),
            ),
        )
        event = dict(sequence=sequence, registers=deepcopy(registers), **result)
        if clocked:
            event['clock'] = _clock_bracket(self, before, _clock_sample(self))
        return event, dict(registers=registers, source_qualification=deepcopy(q))

    @machine_trace_operation
    def trace(
        self, name='machine-trace.json', *, count=128, timeout_ms=10000, bits=None, source_view=None
    ):
        state = getattr(self, '_le_source', None)
        if not state or state.get('tracking') != 'paged' or source_view == 'initial-dos':
            return super().trace(
                name=name, count=count, timeout_ms=timeout_ms, bits=bits, source_view=source_view
            )
        from .external_files import _file_name

        _file_name(name)
        if (
            type(count) is not int
            or not 1 <= count <= 10000
            or (bits is not None and (type(bits) is not int or bits != 32))
            or source_view not in (None, 'embedded-le')
        ):
            raise ValueError('Invalid paged LE trace parameters')
        from .qemu_step_policy import observe_step_policy

        policy = observe_step_policy(self._stopped(), timeout_ms=self._remaining())
        if (
            policy['status'] != 'observed'
            or policy['enabled'] is not True
            or policy['unknown_mask'] != 0
        ):
            raise ValueError('Paged LE trace requires an observed, enabled QEMU step policy')
        from .execution_trace import ExecutionTraceError

        events, event_bytes = [], 0
        outcome, current_stop, error = 'count', None, None
        interrupted = None
        attempted = 0
        try:
            for index in range(count):
                event, current_stop = self._paged_observe(state, index + 1)
                encoded = json.dumps(event, sort_keys=True, separators=(',', ':')).encode()
                if event_bytes + len(encoded) + 1 > 15 * 1024 * 1024:
                    outcome = 'artifact_budget'
                    break
                events.append(event)
                event_bytes += len(encoded) + 1
                pc = int(event['registers']['linear_pc'], 0)
                points = [
                    identifier
                    for identifier, point in self.breakpoints.items()
                    if identifier != self._return_breakpoint
                    and point['access'] == 'x'
                    and point['address'] == pc
                ]
                if points:
                    outcome = 'foreign_stop'
                    current_stop = dict(
                        kind='armed_execution_breakpoint_boundary',
                        breakpoint_ids=points,
                        registers=deepcopy(event['registers']),
                    )
                    break
                attempted += 1
                current_stop = None
                native = self.step(timeout_ms=self._remaining())
                current_stop = native
                if native['outcome'] != 'step':
                    outcome = (
                        native['outcome']
                        if native['outcome'] in ('guest_exit', 'guest_tsr', 'exited', 'timeout')
                        else 'foreign_stop'
                    )
                    break
        except BaseException as exc:
            if current_stop is None and isinstance(getattr(exc, 'result', None), dict):
                current_stop = deepcopy(exc.result)
            interrupted = exc if not isinstance(exc, Exception) else None
            outcome = (
                'cancelled'
                if interrupted is not None
                else 'timeout'
                if isinstance(exc, TimeoutError)
                else 'error'
            )
            error = dict(type=type(exc).__name__, message=str(exc))
            gdb, qmp = self.vm.gdb, self.vm.qmp
            if qmp is not None and (
                not self.vm.machine_stopped
                or getattr(qmp, 'socket', True) is None
                or gdb is not None
                and gdb.socket is None
            ):
                self.vm.close()
        document = dict(
            format='fdisbull-paged-le-trace-1',
            binding=deepcopy(state['recipe']),
            binding_artifact=deepcopy(state['binding_artifact']),
            events=events,
            outcome=outcome,
            attempted_steps=attempted,
            current_stop=current_stop,
            error=error,
            step_policy=policy,
            producer=deepcopy(state['paged_producer']),
            native_inputs=deepcopy(state['native_inputs']),
            scope='independently witnessed stopped boundaries; no task lifetime or retirement claim',
        )
        try:
            data = json.dumps(document, sort_keys=True, separators=(',', ':')).encode()
            if len(data) > 16 * 1024 * 1024:
                raise ValueError('Paged LE trace exceeds its artifact budget')
            artifact = self._artifact(
                name,
                'trace',
                data,
                dict(format=document['format'], event_count=len(events), outcome=outcome),
            )
        except Exception as exc:
            result = dict(
                outcome=outcome,
                attempted_steps=attempted,
                current_stop=current_stop,
                error=error,
                observation_count=len(events),
            )
            if interrupted is not None:
                interrupted.result = result
                raise interrupted from exc
            raise ExecutionTraceError(result, exc) from exc
        if interrupted is not None:
            interrupted.result = dict(trace=artifact, outcome=outcome, current_stop=current_stop)
            raise interrupted
        return artifact

    def _le_source_summary(self):
        value = super()._le_source_summary()
        state = getattr(self, '_le_source', None)
        if state is not None and state.get('tracking') == 'paged':
            value['tracking'] = 'paged'
            value['mapping_identity'] = (
                deepcopy(state.get('current_mapping')) if state['state'] == 'qualified-stopped' else None
            )
            value['continuity'] = 'independent stopped observations; not OS/task/allocation lifetime'
        return value

    @machine_trace_operation
    def trace_until(
        self,
        until,
        *,
        regions=None,
        max_steps=1000,
        timeout_ms=10000,
        name='trace-until.json',
        action=None,
        label='trial',
        source_view=None,
    ):
        state = getattr(self, '_le_source', None)
        if state and state.get('tracking') == 'paged' and source_view != 'initial-dos':
            raise ValueError('Paged LE tracking does not support predicate traces')
        return super().trace_until(
            until,
            regions=regions,
            max_steps=max_steps,
            timeout_ms=timeout_ms,
            name=name,
            action=action,
            label=label,
            source_view=source_view,
        )
