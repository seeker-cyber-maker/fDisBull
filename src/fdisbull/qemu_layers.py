"""Stopped QEMU layer transitions keyed by physical RAM backing."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import struct

from .code_layers import branch_replacement, groups
from .debug_state import byte_string
from .dos_memory import translate_386_page
from .dosbox_rpc import DebuggerError
from .memory_search_runtime import _locked


LAYER_COMMANDS = frozenset(('x-fdisbull-layer-configure', 'x-fdisbull-layer-observe'))
MAX_BYTES = 65536


def _chunks(before, after):
    return [
        {'address': span[0], 'before': bytes(before[a] for a in span).hex(),
         'after': bytes(after[a] for a in span).hex()}
        for span in groups(after)
    ]


class QemuLayerSessionMixin:
    def _reset_native_layers(self):
        self._layer_active = []
        self._layer_generation = 0
        self._layer_ram_base = {}
        self._layer_ram_applied = {}
        self._layer_exec_base = {}
        self._layer_exec = {}

    def _layer_epoch(self):
        return getattr(self, '_runtime_epoch', self.run_id)

    def _layer_preflight(self):
        if self.project is None or not self.capabilities.get('code_layers'):
            raise ValueError('QEMU layers require a project and a native one-vCPU layer backend')
        if self.project.db.in_transaction:
            raise ValueError('QEMU layers require a project outside a caller-owned transaction')
        self._stopped()
        if not hasattr(self, '_layer_active'):
            self._reset_native_layers()

    def _layer_source_address(self, address, length, state, cs):
        from .qemu_dos_trace import _ownership

        if not getattr(self, '_process', None):
            raise ValueError('Source layer addresses require an active COM/MZ process')
        from .qemu_dos_tasks import require_task
        require_task(self)
        if state['cpu_mode'] == 'real':
            if (state['paging'] is not False or state['code_bits'] != 16
                    or state['register_context_match'] is not True):
                raise ValueError('Source layers require an observed real-mode DOS process')
            _ownership(self, {'capture_epoch': self._layer_epoch()})
        else:
            from .qemu_dos_checkpoint import _origin, _verify_process
            _verify_process(self, self._process, _origin(self))
            _ownership(self, {'capture_epoch': self._layer_epoch()})
        static, _ = self.project._dos_parse_address(address, cs)
        for extent in self._process['source_mapping']['live_ranges']:
            offset = static - extent['project_address']
            if 0 <= offset and offset + length <= extent['length']:
                return extent['runtime_address'] + offset, static
        raise ValueError('Source layer extent is outside the verified DOS module')

    def _layer_ram_extent(self, address, length):
        ram_end = min(self.vm.machine_configuration['memory_mib'] << 20, 0xc0000000)
        end = address + length
        if not (0 <= address < end <= 0xa0000 or 0x100000 <= address < end <= ram_end):
            raise ValueError('Layer backing must be conventional or extended PC RAM')

    def _layer_spans(self, address, length, space, cs=None):
        if type(length) is not int or not 1 <= length <= MAX_BYTES:
            raise ValueError('Layer length must be 1..65536')
        if cs is not None and space != 'source':
            raise ValueError('CS requires a source address')
        if space not in ('source', 'linear', 'physical'):
            raise ValueError('Layer space must be source, linear, or physical')
        remote = self._stopped()
        state = self.registers()['address_state']
        static = None
        if space == 'source':
            linear, static = self._layer_source_address(address, length, state, cs)
        else:
            linear = int(address, 0) if isinstance(address, str) else address
        if type(linear) is not int or not 0 <= linear <= 0x100000000 - length:
            raise ValueError('Layer extent must fit a 32-bit address space')
        if space == 'physical':
            self._layer_ram_extent(linear, length)
            spans = []
            start = linear
            while start < linear + length:
                count = min(4096 - (start & 4095), linear + length - start)
                spans.append((start, count))
                start += count
            return linear, static, spans, state
        if state['register_context_match'] is not True or state['machine_vcpus'] != 1:
            raise ValueError('Layer binding requires one observed stopped CPU context')

        def read_table(location, count):
            self._layer_ram_extent(location, count)
            return remote.memory(location, count, space='physical')

        spans = []
        start = linear
        while start < linear + length:
            count = min(4096 - (start & 4095), linear + length - start)
            mapping = translate_386_page(start, state, read_table)
            if mapping['status'] != 'mapped':
                raise ValueError('Layer requires an observed RAM mapping: ' + mapping['status'])
            backing = int(mapping['physical_address'], 16)
            self._layer_ram_extent(backing, count)
            if remote.memory(start, count, space='virtual') != remote.memory(backing, count, space='physical'):
                raise DebuggerError('Native virtual read differs from the selected layer backing')
            spans.append((backing, count))
            start += count
        return linear, static, spans, state

    def _layer_native_observe(self, **extent):
        result = self.vm.qmp.call('x-fdisbull-layer-observe', extent or None)
        valid_fault = isinstance(result, dict) and isinstance(result.get('fault'), str) and result['fault']
        expected_count = 0 if valid_fault else len(self._layer_exec)
        if (not isinstance(result, dict) or type(result.get('generation')) is not int
                or type(result.get('execution-bytes')) is not int
                or result['generation'] != self._layer_generation
                or result['execution-bytes'] != expected_count
                or valid_fault and not self._layer_exec):
            self.close()
            raise DebuggerError('QEMU layer state differs from the owned layer stack')
        return result

    def _layer_before_execution(self):
        if getattr(self, '_dos_task_monitor', None):
            from .qemu_dos_task_views import before_task_execution
            before_task_execution(self)
        if getattr(self, '_layer_exec', None):
            state = self._layer_native_observe()
            if state.get('fault'):
                raise DebuggerError('Execution layer is faulted. Clear the layer stack before running.')
            # Debugger-side writes do not pass through the guest CPU's
            # write tracking. Check their backing before any continuation.
            remote = self._stopped()
            for span in groups(self._layer_exec_base):
                original = bytes(self._layer_exec_base[address] for address in span)
                if remote.memory(span[0], len(span), space='physical') != original:
                    raise DebuggerError('Execution layer backing changed. Clear the layer stack before running.')

    def _layer_positions(self, definition, patch):
        data = bytes.fromhex(patch['data_hex'])
        binding = definition.get('native_binding')
        if binding is None:
            _, _, spans, _ = self._layer_spans(patch['address'], len(data), 'source')
        else:
            if binding.get('scope') == 'task-private':
                raise ValueError('Task-private definitions require dos_task_layers')
            if binding['run'] != self.run_id or binding['epoch'] != self._layer_epoch():
                raise ValueError('Layer backing belongs to a different QEMU run or epoch')
            if binding.get('task_identity') is not None:
                from .qemu_dos_tasks import task_key
                if task_key(binding['task_identity']) != task_key(getattr(self, '_dos_task_binding', None)):
                    raise ValueError('Layer backing belongs to a different native DOS task lifetime')
            spans = binding['spans']
        return [a for start, count in spans for a in range(start, start + count)]

    @_locked
    def layers(self, active=None, *, conflict='stop'):
        self._layer_preflight()
        if conflict not in ('stop', 'keep_changed') or (conflict != 'stop' and active != []):
            raise ValueError('conflict=keep_changed is only valid when clearing all layers')
        native = self._layer_native_observe()
        if active is None:
            return dict(run=self.run_id, active=list(self._layer_active),
                        generation=self._layer_generation, native=native,
                        layers=[self.project.debug_layer_info(i) for i in self._layer_active])
        if (not isinstance(active, list) or len(active) > 64
                or any(not isinstance(i, str) for i in active) or len(set(active)) != len(active)):
            raise ValueError('Active stack requires at most 64 unique layer IDs')
        if active and getattr(self, '_dos_task_monitor', None):
            raise ValueError('Use task-private stacks while native task switching is enabled')
        if active and getattr(self, '_dos_task_binding', None) is not None:
            from .qemu_dos_tasks import require_task
            require_task(self)
        definitions = [self.project.debug_layer_info(i) for i in active]
        if any(d['version'] != self.version['id'] for d in definitions):
            raise ValueError('Layer belongs to a different static version')
        if sum(len(d['patches']) for d in definitions) > 256:
            raise ValueError('Active layers exceed 256 patches')
        expected, ram, execute = {}, {}, {}
        for definition in definitions:
            for patch in definition['patches']:
                addresses = self._layer_positions(definition, patch)
                before = bytes.fromhex(patch['expected_hex'])
                after = bytes.fromhex(patch['data_hex'])
                if len(addresses) != len(before) or len(before) != len(after):
                    raise ValueError('Layer definition differs from its backing extent')
                output = ram if definition['kind'] == 'ram' else execute
                for address, old, new in zip(addresses, before, after):
                    if expected.setdefault(address, old) != old:
                        raise ValueError('Overlapping layer definitions disagree about their base bytes')
                    output[address] = new
                if len(expected) > MAX_BYTES:
                    raise ValueError('Active transition exceeds 64 KiB')
        touched = set(expected) | self._layer_ram_applied.keys()
        if len(touched) > MAX_BYTES:
            raise ValueError('Active transition exceeds 64 KiB')
        remote = self._stopped()
        current = {}
        for span in groups(touched):
            current.update(zip(span, remote.memory(span[0], len(span), space='physical')))
        base = dict(current)
        preserved = []
        for address, applied in self._layer_ram_applied.items():
            observed = current[address]
            if observed == applied:
                base[address] = self._layer_ram_base[address]
            elif conflict == 'keep_changed':
                preserved.append(dict(address=hex(address), layer_byte=applied, observed_byte=observed))
            else:
                raise ValueError('Active RAM layer conflicts with changed memory at ' + hex(address))
        for address, byte in expected.items():
            if base[address] != byte:
                raise ValueError('Layer expected base bytes mismatch at ' + hex(address))
        post_ram = base | ram
        writes = {a: post_ram[a] for a in self._layer_ram_applied.keys() | ram.keys()}
        args = {'generation': self._layer_generation,
                'ram': _chunks(current, writes), 'execute': _chunks(post_ram, execute)}
        previous = list(self._layer_active)
        from .qemu_machine import _before_machine_execution, _tracking
        _before_machine_execution(self,'machine-layer-write')
        self._automatic_internal_pending=None
        try:
            result = self.vm.qmp.call('x-fdisbull-layer-configure', args)
        except DebuggerError as error:
            if 'FDISBULL_LAYER_PRECONDITION' not in str(error):
                self.close()
            raise
        except BaseException:
            self.close()
            raise
        try:
            generation = self._layer_generation + 1
            for key, expected_value in (('generation', generation), ('ram-bytes', len(writes)),
                                        ('execution-bytes', len(execute))):
                if not isinstance(result, dict) or type(result.get(key)) is not int or result[key] != expected_value:
                    raise DebuggerError('QEMU returned an invalid layer transition receipt')
            evidence = dict(run=self.run_id, active_before=previous, active=list(active),
                            generation=generation, ram_bytes=len(ram), execution_bytes=len(execute),
                            guest_instructions_during_transition=0, preserved_changed_bytes=preserved,
                            backend=result)
            self._event('layer-transition', evidence)
        except BaseException:
            self.close()
            raise
        self._layer_active = list(active)
        self._layer_generation = generation
        self._layer_ram_base = {a: base[a] for a in ram}
        self._layer_ram_applied = ram
        self._layer_exec_base = {a: post_ram[a] for a in execute}
        self._layer_exec = execute
        _tracking(self,'after_stop','machine-layer-transition')
        return evidence

    @_locked
    def layer_enable(self, layer, *, enabled=True):
        self._layer_preflight()
        if type(enabled) is not bool:
            raise ValueError('enabled must be boolean')
        if self.project.debug_layer_info(layer)['version'] != self.version['id']:
            raise ValueError('Layer belongs to a different static version')
        active = [i for i in self._layer_active if i != layer]
        return self.layers(active + [layer] if enabled else active)

    @_locked
    def layer_patch(self, name, address, *, expected_hex, data_hex, kind='ram', activate=True, space=None):
        self._layer_preflight()
        if getattr(self, '_dos_task_binding', None) is not None:
            from .qemu_dos_tasks import require_task
            require_task(self)
        if type(activate) is not bool or kind not in ('ram', 'execute'):
            raise ValueError('Layer requires kind=ram or execute and boolean activate')
        before, after = byte_string(expected_hex), byte_string(data_hex)
        if len(before) != len(after):
            raise ValueError('A layer cannot resize memory')
        if space is None:
            space = 'source' if hasattr(self, '_process') else 'linear'
        linear, static, spans, _ = self._layer_spans(address, len(before), space)
        patch = dict(address=hex(linear if static is None else static), expected_hex=before.hex(), data_hex=after.hex())
        if space == 'source':
            result = self.project.debug_layer(name, kind=kind, patches=[patch], version=self.version['id'])
        else:
            # This definition owns the selected backing, even when the same
            # guest linear window subsequently selects a different page.
            binding = dict(run=self.run_id, epoch=self._layer_epoch(), space=space, spans=spans)
            if getattr(self, '_dos_task_binding', None) is not None:
                binding['task_identity'] = deepcopy(self._dos_task_binding)
            result = self.project._store_debug_layer(name, self.version['id'],
                                                     dict(kind=kind, patches=[patch], native_binding=binding))
        if activate:
            result['activation'] = self.layer_enable(result['layer'])
        return result

    @_locked
    def code(self, address, *, cs=None, length=32, view='execute', space=None):
        from iced_x86 import Decoder, Formatter, FormatterSyntax

        self._layer_preflight()
        self._layer_native_observe()
        if view not in ('ram', 'execute'):
            raise ValueError('view must be ram or execute')
        if space is None:
            space = 'source' if hasattr(self, '_process') else 'linear'
        linear, static, spans, state = self._layer_spans(address, length, space, cs)
        remote = self._stopped()
        observed = bytearray()
        task_view = None
        if getattr(self, '_dos_task_monitor', None) and space != 'physical':
            from .qemu_dos_task_views import selected_view
            task_view = selected_view(self)
        for start, count in spans:
            if task_view is not None:
                from .qemu_dos_task_views import _read
                data, _ = _read(self, task_view, start, count, view)
                observed.extend(data)
                continue
            ram = remote.memory(start, count, space='physical')
            if view == 'ram':
                observed.extend(ram)
                continue
            expected = bytearray(ram)
            for offset, byte in enumerate(ram):
                location = start + offset
                if location in self._layer_exec:
                    if byte != self._layer_exec_base[location]:
                        raise DebuggerError('Instruction layer backing changed at ' + hex(location))
                    expected[offset] = self._layer_exec[location]
            native = self._layer_native_observe(address=start, length=count)
            if native.get('fault') or native.get('data-hex') != expected.hex():
                raise DebuggerError('QEMU did not verify the effective instruction fetch view')
            observed.extend(expected)
        bits = state['code_bits']
        instructions = []
        runtime_cs = project_cs = None
        ip = linear
        if bits in (16, 32, 64):
            formatter = Formatter(FormatterSyntax.NASM)
            if bits == 16:
                segment = state['segments'].get('cs') or {}
                segment_base = int(segment.get('base') or '0x0', 16)
                if static is not None:
                    _, selector = self.project._dos_parse_address(address, cs)
                    if selector is not None:
                        segment_base = (selector << 4) + linear - static
                if not 0 <= linear - segment_base < 0x10000:
                    segment_base = linear & ~0xf
                ip = linear - segment_base
                if ip + length > 0x10000:
                    raise ValueError('Code view crosses a 16-bit segment boundary')
                if state['cpu_mode'] == 'real':
                    runtime_cs = hex(segment_base >> 4)
                    if static is not None:
                        project_cs = hex((segment_base - linear + static) >> 4)
            for instruction in Decoder(bits, bytes(observed), ip=ip):
                if instruction.is_invalid:
                    break
                offset = (instruction.ip - ip) & ((1 << bits) - 1)
                instructions.append(dict(runtime_address=hex(linear + offset),
                    project_address=hex(static + offset) if static is not None else None,
                    ip=hex(instruction.ip), size=instruction.len,
                    bytes=bytes(observed[offset:offset + instruction.len]).hex(),
                    instruction=formatter.format(instruction)))
        return dict(hex=observed.hex(), sha256=hashlib.sha256(observed).hexdigest(), length=length,
                    view=view, space=space, runtime_address=hex(linear),
                    project_address=hex(static) if static is not None else None, instructions=instructions,
                    runtime_cs=runtime_cs, project_cs=project_cs, instruction_pointer=hex(ip),
                    generation=self._layer_generation if task_view is None else task_view['generation'],
                    active_layers=list(self._layer_active if task_view is None else task_view['active']),
                    backing=[dict(physical_address=hex(a), length=n) for a, n in spans],
                    evidence='stopped native backing bytes and guarded instruction overlay')

    @_locked
    def capture_code(self, address, *, cs=None, length=64, view='execute', space=None, name='code-view.json'):
        result = self.code(address, cs=cs, length=length, view=view, space=space)
        metadata = {key: result[key] for key in ('view', 'space', 'project_address', 'generation', 'active_layers')}
        metadata['static_promotion'] = 'unqualified'
        return self._artifact(name, 'qemu-code-snapshot', json.dumps(result, indent=2).encode(), metadata)

    def _layer_base_bytes(self, address, length):
        _, _, spans, _ = self._layer_spans(address, length, 'source')
        remote = self._stopped()
        original = bytearray()
        for start, count in spans:
            for location, observed in enumerate(remote.memory(start, count, space='physical'), start):
                if location in self._layer_ram_applied and observed != self._layer_ram_applied[location]:
                    raise ValueError('Active RAM layer conflicts with changed memory at ' + hex(location))
                original.append(self._layer_ram_base.get(location, observed))
        return original.hex()

    @_locked
    def branch(self, name, address, *, mode='invert', activate=True):
        view = self.code(address, length=8, space='source')
        if not view['instructions']:
            raise ValueError('No decoded runtime branch')
        raw = bytes.fromhex(view['instructions'][0]['bytes'])
        replacement = branch_replacement(raw, mode)
        return self.layer_patch(name, address, expected_hex=self._layer_base_bytes(address, len(raw)),
                                data_hex=replacement.hex(), kind='execute', activate=activate, space='source')

    @_locked
    def cave(self, name, *, address, code_hex, return_to, activate=False):
        self._layer_preflight()
        body = byte_string(code_hex)
        target, _, _, _ = self._layer_spans(return_to, 1, 'source')
        if target >= 0x100000:
            raise ValueError('Virtual cave return requires an unwrapped real-mode far address')
        jump = b'\xea' + struct.pack('<HH', target & 15, target >> 4)
        data = body + jump
        result = self.layer_patch(name, address, expected_hex=self._layer_base_bytes(address, len(data)),
                                  data_hex=data.hex(), kind='execute', activate=activate, space='source')
        return result | dict(return_runtime_linear=hex(target), far_jump_hex=jump.hex(),
                             guest_ram_bytes_written=0)
