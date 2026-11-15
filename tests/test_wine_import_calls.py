"""Mapped PE export parsing and observation orchestration, without a VM.

The boundary peer is deliberately a fake RPC collaborator. Native execution is
qualified separately by the real Wine acceptance test.
"""
from copy import deepcopy
import base64
import hashlib
import json
import struct

import pytest

from fdisbull.project import Project
from fdisbull.debug_semantics import normalize_trace
from fdisbull.wine_arch import register_names
from fdisbull.wine_import_calls import observe_import_call, resolve_loaded_export
from fixtures_formats import pe64


def _image(exports):
    raw = bytearray(0x3000)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 60, 0x80)
    raw[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HH', raw, 0x84, 0x8664, 2)
    struct.pack_into('<H', raw, 0x94, 240)
    struct.pack_into('<H', raw, 0x98, 0x20b)
    struct.pack_into('<I', raw, 0x98 + 56, len(raw))
    struct.pack_into('<I', raw, 0x98 + 108, 16)
    struct.pack_into('<II', raw, 0x98 + 112, 0x1000, 0x400)
    for index, (rva, flags) in enumerate(((0x1000, 0x40000040), (0x2000, 0x60000020))):
        offset = 0x188 + 40 * index
        struct.pack_into('<III', raw, offset + 8, 0x1000, rva, 0x1000)
        struct.pack_into('<I', raw, offset + 36, flags)
    names = sorted(exports)
    struct.pack_into('<IIIIII', raw, 0x1010, 1, len(names), len(names), 0x1040, 0x1080, 0x10c0)
    offset, addresses = 0x1100, {}
    for index, name in enumerate(names):
        encoded = name.encode() + b'\0'
        raw[offset:offset + len(encoded)] = encoded
        struct.pack_into('<I', raw, 0x1080 + 4 * index, offset)
        struct.pack_into('<H', raw, 0x10c0 + 2 * index, index)
        offset += len(encoded)
        value = exports[name]
        if isinstance(value, str):
            rva = 0x1200 + index * 64
            raw[rva:rva + len(value) + 1] = value.encode() + b'\0'
        else:
            rva = 0x2000 + index * 32
            raw[rva:rva + 16] = b'\x90' * 15 + b'\xc3'
        struct.pack_into('<I', raw, 0x1040 + 4 * index, rva)
        addresses[name] = rva
    return bytes(raw), addresses


def _modules(images):
    state = {'module_revision': len(images), 'state_revision': 1, 'modules': [
        {'name': name, 'base': hex(base), 'size': len(raw), 'bits': 64, 'generation': i + 1}
        for i, (base, name, raw) in enumerate(images)]}
    def read(address, length):
        for base, _, raw in images:
            if base <= address and address + length <= base + len(raw):
                return raw[address - base:address - base + length]
        raise ValueError('Unmapped authored module read')
    return state, read


def test_loaded_named_export_and_its_exact_read_evidence():
    raw, offsets = _image({'GetLastError': None})
    state, read = _modules([(0x100000, 'kernel32.dll', raw)])
    result = resolve_loaded_export(state, 'KERNEL32.dll', 'GetLastError', read)
    assert result['target'] == hex(0x100000 + offsets['GetLastError'])
    assert result['chain'][0]['generation'] == 1
    assert all(hashlib.sha256(bytes.fromhex(r['hex'])).hexdigest() == r['sha256'] for r in result['reads'])


def test_forwarder_follows_the_actually_loaded_export_including_ordinal():
    kernel, _ = _image({'SetLastError': 'NTDLL.#1'})
    ntdll, offsets = _image({'RtlSetLastWin32Error': None})
    state, read = _modules([(0x100000, 'kernel32.dll', kernel), (0x200000, 'ntdll.dll', ntdll)])
    result = resolve_loaded_export(state, 'kernel32', 'SetLastError', read)
    assert result['target'] == hex(0x200000 + offsets['RtlSetLastWin32Error'])
    assert result['chain'][0]['forwarder'] == 'NTDLL.#1'
    assert result['chain'][1]['symbol'] == '#1'


@pytest.mark.parametrize('problem', ['forwarder_cycle', 'missing_module', 'wrong_arch',
    'outside_table', 'nonexecutable', 'ambiguous_name', 'short_read'])
def test_unproved_loaded_exports_fail_closed(problem):
    raw, _ = _image({'GetLastError': 'KERNEL32.GetLastError' if problem == 'forwarder_cycle' else None})
    raw = bytearray(raw)
    if problem == 'wrong_arch':
        struct.pack_into('<H', raw, 0x84, 0x14c)
    elif problem == 'outside_table':
        struct.pack_into('<I', raw, 0x101c, 0x2fff)
    elif problem == 'nonexecutable':
        struct.pack_into('<I', raw, 0x188 + 40 + 36, 0x40000040)
    images = [(0x100000, 'kernel32.dll', bytes(raw))]
    if problem == 'ambiguous_name':
        images.append((0x200000, 'KERNEL32.DLL', bytes(raw)))
    state, read = _modules(images)
    if problem == 'short_read':
        original = read
        read = lambda address, length: original(address, length)[:-1]
    with pytest.raises(ValueError):
        resolve_loaded_export(state, 'absent' if problem == 'missing_module' else 'kernel32', 'GetLastError', read)


class BoundaryPeer:
    """A finite RPC fake; it never substitutes for the native acceptance lane."""
    def __init__(self, project, api, *, failure=None):
        self.project, self.api, self.failure = project, api, failure
        self.version, self.delta, self.bits, self.closed = project.version(1), 0, 64, False
        self.run_id, self.site, self.stack, self.slot = 'authored-import-rpc-peer', 0x140001010, 0x8000, 0x140001080
        self.deleted, self.stage, self.state = [], 'before', 'stopped'
        image, offsets = _image({n: None for n in ('GetLastError', 'SetLastError', 'ExitProcess')})
        self.modules, self.module_read = _modules([(0x70000000, 'kernel32.dll', image)])
        self.target = 0x70000000 + offsets[api]
        instruction = b'\xff\x15' + (self.slot - self.site - 6).to_bytes(4, 'little', signed=True)
        self.memory = {self.site + k: b for k, b in enumerate(instruction)}
        self.memory.update({self.slot + k: b for k, b in enumerate((self.target + (1 if failure == 'iat' else 0)).to_bytes(8, 'little'))})
        self.memory.update({self.stack - 8 + k: 0 for k in range(48)})
        self.general = {n: hex(0x80 + i) for i, n in enumerate(sorted(register_names(64) - {'rip', 'rflags'}))}
        self.general.update(rsp=hex(self.stack), rcx='0x12345678')
        project._document = lambda _: {'imports': [{'name': api, 'module': 'KERNEL32.dll', 'kind': 'iat', 'address': self.slot}]}

    def project_address(self, address):
        address = int(address, 16) if isinstance(address, str) else address
        return hex(address) if 0x140001000 <= address < 0x140002000 else None

    def _registers(self):
        values = deepcopy(self.general)
        rip = self.site
        if self.stage == 'entry':
            values['rsp'] = hex(self.stack - 8)
            rip = self.target + (1 if self.failure == 'entry' else 0)
        elif self.stage == 'return':
            rip += 6
            values['rax'] = '0xfeedcafe12345678'
            values['rcx'] = '0xdeadbeef'
            if self.failure == 'nonvolatile':
                values['rbx'] = '0x0'
        return {'rip': hex(rip), 'rflags': '0x202', 'general': values, 'thread': 17}

    def registers(self):
        raw = self._registers()
        return raw | {'project_address': self.project_address(raw['rip']), 'cpu_mode': 'long64'}

    def call(self, method, params=None, **_):
        if method == 'status':
            return {'state': self.state}
        if method == 'registers':
            return self._registers()
        if method == 'modules':
            result = deepcopy(self.modules)
            if self.failure == 'module_revision' and self.stage == 'return':
                result['module_revision'] += 1
            return result
        assert method == 'read'
        address, length = params['address'], params['length']
        if 0x70000000 <= address < 0x70003000:
            raw = self.module_read(address, length)
        else:
            raw = bytes(self.memory[address + k] for k in range(length))
        return {'data_base64': base64.b64encode(raw).decode()}

    def _artifact(self, name, kind, raw, metadata):
        return self.project._debug_artifact(self.run_id, name, kind, raw, metadata)

    def trace(self, name, *, count, timeout_ms):
        assert count == 1 and timeout_ms > 0
        before = self._registers()
        event = {'address': hex(self.site), 'project_address': hex(self.site), 'registers': before,
            'execution_bytes': bytes(self.memory[self.site + k] for k in range(6)).hex(), 'active_layers': []}
        event['bytes'] = event['ram_bytes'] = event['execution_bytes']
        normalize_trace('wine-qemu', [event], version=1)
        doc = {'run': self.run_id, 'version': 1, 'complete': True,
            'mapping': {'source_sha256': self.project.meta['source_sha256'], 'version_sha256': self.version['sha256']},
            'events': [event]}
        if self.failure == 'trace_run':
            doc['run'] = 'foreign-run'
        self.memory.update({self.stack - 8 + k: b for k, b in enumerate((self.site + 6).to_bytes(8, 'little'))})
        self.stage = 'entry'
        return self._artifact(name, 'trace', json.dumps(doc).encode(), {})

    def breakpoint(self, address):
        assert address == self.site + 6
        return {'breakpoint_id': 'bp-1'}

    def delete_breakpoint(self, identifier):
        self.deleted.append(identifier)
        return {'deleted': True}

    def run(self, *, timeout_ms):
        assert timeout_ms > 0
        if self.failure == 'timeout':
            return {'outcome': 'timeout', 'session': {'state': 'stopped'}}
        if self.api == 'ExitProcess':
            self.state = 'exited'
            return {'outcome': 'exited', 'session': {'state': 'exited',
                'exit_code': 0 if self.failure == 'exit_code' else int(self.general['rcx'], 16)}}
        self.stage = 'return'
        self.memory[self.stack] = 0x99  # Volatile home-space bytes need not survive.
        return {'outcome': 'breakpoint', 'session': {'state': 'stopped'}}


@pytest.fixture
def project(tmp_path):
    source = tmp_path / 'peer.exe'
    source.write_bytes(pe64())
    with Project.create(tmp_path / 'peer.fdb', source) as p:
        p.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
            ('authored-import-rpc-peer', 1, 'authored', None, 'stopped', '{}'))
        p.db.commit()
        yield p


def _observe(project, api='GetLastError', failure=None):
    peer = BoundaryPeer(project, api, failure=failure)
    receipt = observe_import_call(peer, memory_ranges=[{'address': hex(peer.stack), 'length': 32}],
        code_ranges=[{'address': hex(peer.site), 'length': 6}])
    row = project.db.execute('SELECT data FROM debug_artifacts WHERE id=?', (receipt['artifact'],)).fetchone()
    return peer, json.loads(bytes(row['data']))


@pytest.mark.parametrize('api', ['SetLastError', 'GetLastError', 'ExitProcess'])
def test_import_observer_preserves_real_boundary_shapes_and_cleanup(project, api):
    peer, doc = _observe(project, api)
    assert doc['status'] == 'complete', doc
    assert doc['import']['name'] == api
    assert doc['contexts']['entry']['rip'] == hex(peer.target)
    assert doc['entry_instruction']['project_address'] is None
    assert doc['entry_instruction']['observation']['instruction_completed'] is False
    assert hashlib.sha256(bytes.fromhex(doc['entry_instruction']['read']['hex'])).hexdigest() == doc['entry_instruction']['read']['sha256']
    if api == 'ExitProcess':
        assert doc['terminal']['exit_code'] == 0x12345678 and not peer.deleted
        assert 'return' not in doc['contexts']
    else:
        assert doc['contexts']['return']['general']['rax'] == '0xfeedcafe12345678'
        assert doc['shadow_store']['return_hex'] != doc['shadow_store']['before_hex']
        assert peer.deleted == ['bp-1']


@pytest.mark.parametrize('failure', ['iat', 'entry', 'nonvolatile', 'timeout', 'module_revision', 'trace_run'])
def test_failed_observation_keeps_partial_evidence_and_removes_owned_breakpoint(project, failure):
    peer, doc = _observe(project, failure=failure)
    assert doc['status'] == 'partial' and doc['error']
    if failure in ('nonvolatile', 'timeout', 'module_revision'):
        assert peer.deleted == ['bp-1']


def test_exit_requires_the_actual_terminal_argument_code(project):
    _, doc = _observe(project, api='ExitProcess', failure='exit_code')
    assert doc['status'] == 'partial' and 'exit code' in doc['error']['message']


def test_invalid_range_schema_is_rejected_before_guest_execution(project):
    peer = BoundaryPeer(project, 'GetLastError')
    with pytest.raises(ValueError):
        observe_import_call(peer, memory_ranges=[{'address': '0xffffffffffffffff', 'length': 8}])
    assert peer.stage == 'before'
