"""Passive, build-qualified DESQview identity and lifecycle observation.

This provider reads the original manager's state and its natural XDI callouts.
It never invokes a guest interrupt, changes a vector, writes code or assigns a
task generation.  The session tracker must own continuous event observation;
attaching to an existing task does not recover its earlier lifetime.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import hashlib
import struct

from .memory_search_runtime import _paused, _read


DV_SHA256 = '3377cc1b59b45b6cc9a4211d84bb5ed75599113ec6672af439c727b020517966'
DV_SIZE = 146459
MZ_HEADER = 0x1c00
INT15_IP = 0x177b
XDI_IP = 0x1a63
# These original-code spans have no MZ relocation words.  Bytes are obtained
# from the caller's hash-verified vendor member, never shipped in the tool.
FINGERPRINTS = ((0x1a40, 44), (0x1cf5, 29), (0x1d12, 12),
                (0x1d23, 10), (0x9e35, 83), (0xaf53, 12))
CURRENT_POINTER = 0x15f8
CURRENT_HANDLE = 0x15f2
CURRENT_MAPPING = 0x15f4
TASK_MAPPING = 0x12
TASK_PROCESS = 0x109
MAPPING_PROCESS = 0x2c
EVENTS = {3: 'dv-end', 4: 'process-create', 5: 'process-end', 6: 'create',
          7: 'end', 8: 'save', 9: 'restore', 0x0c: 'swap-out',
          0x0d: 'swap-in', 0x10: 'free'}
MAX_CHAIN = 8


class DesqviewProviderError(ValueError):
    """A previously selected manager could not be qualified at this stop."""


def _require(value, message):
    if not value:
        raise DesqviewProviderError(message)


def _number(value):
    result = int(value, 0) if isinstance(value, str) else value
    _require(type(result) is int and 0 <= result <= 0xffffffff, 'Invalid native register')
    return result


def _register(registers, name):
    values = registers.get('registers', {})
    for key in (name, name.lower(), name.upper()):
        if key in values:
            return _number(values[key])
    raise DesqviewProviderError('Missing native register ' + name)


def _cpu(observed):
    state = observed['address_state']
    registers = observed['registers']
    _require(state.get('register_context_match') is True and state.get('machine_vcpus') == 1,
             'DESQview needs one coherent stopped CPU')
    _require(state.get('cpu_mode') in ('real', 'v86') and state.get('code_bits') == 16,
             'DESQview manager needs an observed real/V86 16-bit context')
    cs = state.get('segments', {}).get('cs', {})
    selector = _number(cs.get('selector'))
    base = _number(cs.get('base'))
    ip = _register(registers, 'eip')
    _require(selector <= 0xffff and ip <= 0xffff and base == selector * 16,
             'DESQview CPU segment cache is inconsistent')
    return dict(cs=selector, cs_base=base, ip=ip, linear=base + ip)


def _same_stop(before, after):
    _require(before['address_state'] == after['address_state'] and
             before['registers'] == after['registers'], 'DESQview observation changed CPU stop')


def _gate(session):
    return session.vm.lock if hasattr(session, 'vm') else nullcontext()


def _source(session):
    """Obtain only the explicitly selected original FAT member."""
    profile = getattr(session, 'guest_profile', None)
    if not isinstance(profile, dict) or profile.get('profile') != 'desqview-386-v1':
        return None
    members = [row for row in profile.get('members', []) if row.get('role') == 'program']
    if len(members) != 1 or members[0].get('sha256') != DV_SHA256:
        return None
    from .qemm_runtime import _FATVolume, _file, MAX_IMAGE
    image = profile.get('boot_image', {})
    _, carrier = _file(image.get('path'), MAX_IMAGE, 'DESQview provider boot image')
    _require(hashlib.sha256(carrier).hexdigest() == image.get('sha256'),
             'DESQview provider boot carrier changed')
    raw = _FATVolume(carrier).read(members[0]['guest_path'], maximum=DV_SIZE)
    _require(len(raw) == DV_SIZE and hashlib.sha256(raw).hexdigest() == DV_SHA256,
             'DESQview provider original member changed')
    _require(raw[:2] == b'MZ' and struct.unpack_from('<H', raw, 8)[0] * 16 == MZ_HEADER,
             'DESQview provider original MZ layout changed')
    identity = dict(provider='desqview-2.8-passive-v2', member_path=members[0]['guest_path'],
                    source_sha256=DV_SHA256, size=DV_SIZE, boot_image_sha256=image['sha256'],
                    mz_header_bytes=MZ_HEADER)
    return raw, identity


def _far(raw):
    offset, segment = struct.unpack('<HH', raw)
    return segment, offset


def _entry_candidates(session, observed, *, include_pc=True):
    """Follow only understood native vector-chain jumps, never a RAM scan."""
    segment, offset = _far(_read(session, 0x15 * 4, 4, 'linear'))
    result, visited = [], set()
    for _ in range(MAX_CHAIN):
        key = (segment, offset)
        if key in visited:
            break
        visited.add(key)
        result.append(dict(segment=segment, offset=offset, origin='INT15-vector-chain'))
        address = segment * 16 + offset
        code = _read(session, address, 7, 'linear')
        if code[0] == 0xea:
            segment, offset = _far(code[1:5])
        elif code[0] == 0xe9:
            offset = (offset + 3 + int.from_bytes(code[1:3], 'little', signed=True)) & 0xffff
        elif code[0] == 0xeb:
            offset = (offset + 2 + int.from_bytes(code[1:2], 'little', signed=True)) & 0xffff
        elif code[:3] == b'\x2e\xff\x2e':
            pointer = segment * 16 + int.from_bytes(code[3:5], 'little')
            segment, offset = _far(_read(session, pointer, 4, 'linear'))
        else:
            break
    if not include_pc:
        return result
    cpu = _cpu(observed)
    # An observed original-manager path can qualify discovery even when a
    # memory-manager vector wrapper is unsupported. Arbitrary matching RAM is
    # insufficient: the stopped CPU must be inside one of these known paths.
    if (INT15_IP <= cpu['ip'] < 0x1824 or 0x1a40 <= cpu['ip'] < 0x1a6c or
            0x1cf5 <= cpu['ip'] < 0x1d1e):
        result.append(dict(segment=cpu['cs'], offset=INT15_IP, origin='observed-manager-PC'))
    return result


class DesqviewProvider:
    """A qualified original manager; host tracker owns epochs and task reuse."""

    def __init__(self, session, source, identity, segment, origin):
        self.session = session
        self._source = source
        self._run = session.run_id
        self.segment = segment
        self.base = segment * 16
        self.hook_address = self.base + XDI_IP
        self.source_identity = deepcopy(identity)
        self.catalog = dict(resident_segment=segment, discovery=origin,
                            current_pointer_offset=CURRENT_POINTER,
                            current_handle_offset=CURRENT_HANDLE,
                            current_mapping_offset=CURRENT_MAPPING,
                            task_mapping_offset=TASK_MAPPING,
                            task_process_far_pointer_offset=TASK_PROCESS,
                            mapping_process_far_pointer_offset=MAPPING_PROCESS,
                            task_handle_resolver_offset=0x9e35,
                            containment_schema='original-dv2.8-process-membership-1',
                            xdi_hook_offset=XDI_IP,
                            fingerprints=[dict(file_offset=MZ_HEADER + start,
                                               resident_offset=start, length=size,
                                               sha256=hashlib.sha256(source[MZ_HEADER+start:MZ_HEADER+start+size]).hexdigest())
                                          for start, size in FINGERPRINTS],
                            lifetime='Creation before attachment is unknown; continuous tracker events are required.')

    def _validate(self):
        _require(self.session.run_id == self._run, 'DESQview provider belongs to another run')
        for start, size in FINGERPRINTS:
            _require(_read(self.session, self.base + start, size, 'linear') ==
                     self._source[MZ_HEADER + start:MZ_HEADER + start + size],
                     'DESQview original manager fingerprint changed')

    def _identity(self):
        segment, offset = _far(_read(self.session, self.base + CURRENT_POINTER, 4, 'linear'))
        _require(segment != 0 and offset <= 0xffe7, 'Invalid DESQview current-task pointer')
        record = _read(self.session, segment * 16 + offset, 24, 'linear')
        handle = int.from_bytes(record[10:12], 'little')
        globals_ = _read(self.session, self.base + CURRENT_HANDLE, 8, 'linear')
        global_handle, mapping, data_segment, global_offset = struct.unpack('<4H', globals_)
        # Both original dispatch LDS and setter stores independently link the
        # manager's task record, mapping token and public internal-stack handle.
        linked_mapping, linked_task = struct.unpack('<HH', _read(self.session, segment * 16 + 0xa04, 4, 'linear'))
        _require(handle != 0 and handle == global_handle and segment == data_segment and
                 offset == global_offset and offset == linked_task and mapping == linked_mapping,
                 'DESQview current-task record/handle linkage disagrees')
        membership = self._task_membership(handle, mapping)
        _require(membership['task_record'] == dict(segment=segment, offset=offset,
                                                   linear=segment * 16 + offset),
                 'DESQview current task differs from its original public handle')
        return dict(handle=handle, handle_offset=0, handle_text=f'{handle:04x}:0000',
                    record=dict(segment=segment, offset=offset, linear=segment * 16 + offset),
                    mapping_context=mapping, process_identity=membership['process_identity'],
                    process_membership=membership['relation'], source_identity=deepcopy(self.source_identity),
                    qualification='Original manager record/handle linkage at this stopped observation; no earlier creation inferred.')

    def _process_for_mapping(self, mapping):
        """Read the original GET-process route, never a PSP/physical heuristic.

        Resident CS:1D23 follows current mapping+2C. The XDI emitter's BX is
        the native active mapping token, including its temporary swap context.
        This reusable native key needs the tracker's process generation.
        """
        _require(type(mapping) is int and 0 <= mapping <= 0xffd0,
                 'Invalid DESQview owner mapping extent')
        data_segment = int.from_bytes(_read(self.session, self.base + CURRENT_POINTER + 2, 2, 'linear'), 'little')
        _require(data_segment != 0, 'Missing DESQview manager data segment')
        raw = _read(self.session, data_segment * 16 + mapping + MAPPING_PROCESS, 4, 'linear')
        segment, offset = _far(raw)
        _require(segment != 0, 'Missing DESQview process record')
        linear = segment * 16 + offset
        return dict(key=f'desqview-process:{mapping:04x}:{linear:08x}',
                    record=dict(segment=segment, offset=offset, linear=linear),
                    mapping_context=mapping,
                    qualification='Original manager process pointer in its native mapping record; virtual/far identity is reusable and requires a tracked process generation, never a physical address.')

    def _task_membership(self, handle, mapping):
        """Resolve an actual target handle using the original object contract.

        CS:9E35 validates an external task's FEDC marker and manager segment,
        then follows its canonical far backpointer at+0C. Do not assume that
        the external paragraph alias is the canonical manager record address.
        """
        _require(type(handle) is int and 1 <= handle <= 0xffff,
                 'Invalid DESQview target task handle')
        data_segment = int.from_bytes(_read(self.session, self.base + CURRENT_POINTER + 2, 2, 'linear'), 'little')
        alias = _read(self.session, handle * 16, 16, 'linear')
        segment, offset = _far(alias[12:16])
        _require(int.from_bytes(alias[4:6], 'little') == 0xfedc and segment == data_segment and
                 segment != 0 and offset + TASK_PROCESS + 4 <= 0x10000,
                 'DESQview target handle marker/backpointer is unqualified')
        address = segment * 16 + offset
        task = _read(self.session, address, 24, 'linear')
        _require(int.from_bytes(task[10:12], 'little') == handle and
                 _far(task[12:16]) == (segment, offset) and
                 int.from_bytes(task[TASK_MAPPING:TASK_MAPPING+2], 'little') == mapping,
                 'DESQview target task owner/backpointer disagrees')
        process = self._process_for_mapping(mapping)
        task_process = _far(_read(self.session, address + TASK_PROCESS, 4, 'linear'))
        owner = process['record']
        _require(task_process == (owner['segment'], owner['offset']),
                 'DESQview task/process ownership routes disagree')
        record = dict(segment=segment, offset=offset, linear=address)
        relation = dict(qualified=True, kind='task-process-membership', task_handle=handle,
                        task_record=record, owner_mapping_context=mapping,
                        owner_process_record=deepcopy(owner),
                        method='original-dv2.8-task-owner-crosscheck')
        return dict(task_record=record, process_identity=process, relation=relation)

    def current_identity(self):
        with _gate(self.session):
            before = _paused(self.session)
            _cpu(before)
            self._validate()
            result = self._identity()
            _same_stop(before, _paused(self.session))
            return result

    def validate_coverage(self):
        """Validate the resident hook during a DOS or supervisor-mode stop.

        QEMM can own CS/SS while serving a DOS task. Its protected handler is
        not an application context, and does not itself end that lifetime.
        """
        with _gate(self.session):
            before = _paused(self.session)
            state = before['address_state']
            _require(state.get('register_context_match') is True and state.get('machine_vcpus') == 1,
                     'DESQview coverage requires one coherent stopped CPU')
            self._validate()
            entries = _entry_candidates(self.session, before, include_pc=False)
            _require(any(row['segment'] == self.segment and row['offset'] == INT15_IP for row in entries),
                     'Original DESQview manager no longer owns the observed INT15 chain')
            _same_stop(before, _paused(self.session))
            return dict(source_identity=deepcopy(self.source_identity), hook_address=self.hook_address,
                        qualification='Resident lifecycle hook; no application identity inferred from supervisor CS/SS')

    def interpret_event(self, registers):
        """Read a naturally reached original XDI call; never dispatch it."""
        with _gate(self.session):
            before = _paused(self.session)
            _require(registers == before['registers'], 'Stale DESQview lifecycle registers')
            cpu = _cpu(before)
            _require(cpu['linear'] == self.hook_address and cpu['cs'] == self.segment,
                     'CPU is not at the original DESQview XDI callout')
            self._validate()
            ax, bx, dx, bp = (_register(registers, name) & 0xffff for name in ('eax', 'ebx', 'edx', 'ebp'))
            event = ax & 0xff
            multiplex = _read(self.session, self.base + 0x19f8, 1, 'linear')[0]
            _require(event <= 0x10 and bp == event * 4 and ax >> 8 == multiplex,
                     'DESQview lifecycle dispatch arguments disagree')
            # The emitter's current context and affected process are different
            # facts. In particular swap notifications temporarily select BX's
            # process mapping while DX may still denote the manager task.
            identity_error = None
            try:
                identity = self._identity()
            except DesqviewProviderError as error:
                identity = None
                identity_error = str(error)
            emitted_handle = int.from_bytes(_read(self.session, self.base + CURRENT_HANDLE, 2, 'linear'), 'little')
            if event != 0x0a:
                _require(dx == emitted_handle, 'DESQview lifecycle handle differs from original emitter state')
            process = None
            try:
                if event in (0x0c, 0x0d):
                    process = self._process_for_mapping(bx)
                    relation = dict(qualified=True, kind='process-mapping', owner_mapping_context=bx,
                                    owner_process_record=deepcopy(process['record']),
                                    method='original-dv2.8-process-mapping-crosscheck')
                else:
                    target = self._task_membership(dx, bx)
                    process, relation = target['process_identity'], target['relation']
            except DesqviewProviderError as error:
                relation = dict(qualified=False, kind='unqualified', task_handle=dx,
                                owner_mapping_context=bx, reason=str(error))
            result = dict(kind=EVENTS.get(event, 'other'), event=event, handle=dx,
                          mapping_context=bx, current_identity=identity,
                          current_identity_error=identity_error,
                          process_identity=process, target_relation=relation,
                          containment_qualified=relation['qualified'],
                          hook_address=self.hook_address, source_identity=deepcopy(self.source_identity),
                          qualification='Passive original XDI callout; tracker owns lifetime generations and observation gaps.')
            _same_stop(before, _paused(self.session))
            return result


def discover(session):
    """Discover one qualified original manager or return None, without guessing.

    None means unsupported/not observed at this stop, never manager absence.
    A recognized source/carrier mismatch raises instead of publishing identity.
    """
    if not hasattr(session, 'vm'):
        return None
    selected = _source(session)
    if selected is None:
        return None
    source, identity = selected
    with _gate(session):
        before = _paused(session)
        try:
            _cpu(before)
        except DesqviewProviderError:
            return None
        found = {}
        for candidate in _entry_candidates(session, before):
            if candidate['offset'] != INT15_IP or candidate['segment'] == 0:
                continue
            provider = DesqviewProvider(session, source, identity, candidate['segment'], candidate['origin'])
            try:
                provider._validate()
                _require(_read(session, provider.base + INT15_IP - 8, 8, 'linear') == b'DESQview',
                         'Original DESQview interrupt signature missing')
                provider._identity()
            except DesqviewProviderError:
                continue
            found[provider.base] = provider
        _same_stop(before, _paused(session))
        _require(len(found) <= 1, 'Ambiguous original DESQview manager candidates')
        return next(iter(found.values()), None)
