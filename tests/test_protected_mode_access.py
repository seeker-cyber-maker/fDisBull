"""A DOS watch records the access mode before the later debugger stop."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from fdisbull.dosbox_rpc import DOSBoxRPC
from test_protected_mode_native import assemble_fixture


def test_real_watch_access_modes_survive_the_programs_real_to_protected_transition(tmp_path):
    backend = os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        pytest.skip('Set FDISBULL_DOSBOX for native access-mode acceptance')
    binary = assemble_fixture(tmp_path)
    report = {'fixture_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'accesses': []}
    rpc = None
    try:
        rpc = DOSBoxRPC(backend, tmp_path)
        started = rpc.call('session.start', {
            'target': {'command': binary.name, 'arguments': []},
            'mounts': [{'drive': 'C', 'host_path': str(tmp_path)}], 'break_at': 'entry'})
        sid = started['session_id']

        def call(method, params=None):
            return rpc.call(method, {'session_id': sid, **(params or {})})

        entry = call('state.get_registers')
        assert entry['cpu_mode'] == 'real'
        base = int(entry['segments']['cs'], 16) * 16
        # The program writes its GDT pointer in real mode, then its stage byte
        # after enabling 32-bit protected mode and paging. Both watches are
        # declared at the qualified real-mode entry before either write.
        watches = []
        for offset in (0x52A, 0x600):
            watches.append(call('breakpoints.create', {'kind': 'w', 'once': False,
                'address': {'space': 'linear', 'offset': f'0x{base + offset:08X}'}}))
        for index, (mode, width) in enumerate((('real', 4), ('protected', 1))):
            operation = call('execution.continue')
            stop = call('execution.wait', {'operation_id': operation['operation_id'], 'timeout_ms': 3000})
            assert not stop.get('running') and stop['stop_reason']['kind'] == 'breakpoint'
            assert stop['stop_reason']['breakpoint_id'] == watches[index]['breakpoint_id']
            access = stop['stop_reason']['data_access']
            assert access['cpu_mode'] == mode and access['access'] == 'w'
            assert access['length'] == width
            assert access['stop_timing'] == 'after_access_before_next_instruction'
            assert call('state.get_registers')['cpu_mode'] == mode
            assert 'address_context' not in access  # No reconstructed paging provenance.
            report['accesses'].append(access)
            call('breakpoints.delete', {'breakpoint_id': watches[index]['breakpoint_id']})
        assert report['accesses'][0]['instruction']['segment'] == entry['segments']['cs']
        assert report['accesses'][1]['instruction']['segment'] == '0x0008'
        report['passed'] = True
    finally:
        if rpc is not None:
            rpc.close()
            report['reaped'] = rpc.process.poll() is not None
        (tmp_path / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
