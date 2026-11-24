"""Host contract checks for stopped QEMU code observations."""
import threading
from types import SimpleNamespace

import pytest

from fdisbull.dos_views import DOSViewsMixin
from fdisbull.qemu_layers import QemuLayerSessionMixin, _UnsupportedLayerMapping


class CodeSession(QemuLayerSessionMixin):
    def __init__(self):
        self.vm = SimpleNamespace(lock=threading.RLock(), gdb=None, qmp=None, inputs={})
        self.project = DOSViewsMixin()
        self._process = True
        self._layer_active = ['overlay']
        self._layer_generation = 4
        self._layer_exec = {0x20101: 0x34}
        self._layer_exec_base = {0x20101: 0x78}
        self.state = {'cpu_mode': 'real', 'code_bits': 16,
                      'segments': {'cs': {'base': '0x20000'}}}
        self.artifacts = []

    def _layer_preflight(self): pass
    def _layer_spans(self, address, length, space, cs=None):
        static, _ = self.project._dos_parse_address(address, cs)
        return static + 0x10000, static, [(static + 0x10000, length)], self.state
    def _stopped(self): return self
    def memory(self, start, count, *, space): return bytes.fromhex('b87856')[:count]
    def _layer_native_observe(self, **extent):
        return {'data-hex': 'b83456'} if extent else {}
    def _artifact(self, name, kind, data, metadata):
        self.artifacts.append((name, kind, data, metadata))
        return self.artifacts[-1]


def test_source_alias_reports_runtime_cs_for_each_instruction():
    session = CodeSession()
    result = session.code('0fff:0110', length=3)
    assert result['runtime_address'] == '0x20100'
    assert result['project_address'] == '0x10100'
    assert result['runtime_cs'] == '0x1fff'
    assert result['project_cs'] == '0xfff'
    assert result['instructions'][0]['cs'] == '0x1fff'
    assert result['instructions'][0]['ip'] == '0x110'
    assert result['instructions'][0]['bytes'] == 'b83456'
    assert session.code('0fff:0110', length=3, view='ram')['hex'] == 'b87856'


def test_code_capture_failure_does_not_create_artifact():
    session = CodeSession()
    with pytest.raises(ValueError, match='segment boundary'):
        session.capture_code('0001:ffff', length=3, view='ram')
    assert session.artifacts == []


def test_observed_protected_width_controls_decoding():
    session = CodeSession()
    session.state = {'cpu_mode': 'protected', 'code_bits': 32, 'segments': {}}
    result = session.code('0fff:0110', length=3, view='ram')
    # B8 requires a four-byte immediate in 32-bit mode, so this truncated
    # sequence is not the valid 16-bit MOV AX, 5678h instruction.
    assert result['instructions'] == []
    assert result['runtime_cs'] is None


def test_unrepresentable_real_segment_refuses_without_capture():
    session = CodeSession()
    session._layer_spans = lambda *args: (0x110000, None, [(0x110000, 3)], session.state)
    with pytest.raises(ValueError, match='representable 16-bit real-mode CS'):
        session.capture_code(0x110000, length=3, view='ram', space='physical')
    assert session.artifacts == []


def test_hma_selects_representable_real_mode_alias():
    session = CodeSession()
    session._layer_spans = lambda *args: (0x100010, None, [(0x100010, 3)], session.state)
    result = session.code(0x100010, length=3, view='ram', space='physical')
    assert result['runtime_cs'] == '0xffff'
    assert result['instruction_pointer'] == '0x20'
    assert result['instructions'][0]['cs'] == '0xffff'


def test_first_unrepresentable_hma_address_refuses():
    session = CodeSession()
    session._layer_spans = lambda *args: (0x10fff0, None, [(0x10fff0, 1)], session.state)
    with pytest.raises(ValueError, match='representable 16-bit real-mode CS'):
        session.code(0x10fff0, length=1, view='ram', space='physical')


def test_hma_source_alias_keeps_project_selector_representable():
    session = CodeSession()
    session._layer_spans = lambda *args: (0x100010, 0xf0010, [(0x100010, 3)], session.state)
    result = session.code('0xf0010', length=3, view='ram')
    assert (result['runtime_cs'], result['project_cs'], result['instruction_pointer']) == (
        '0xffff', '0xefff', '0x20')


class HighPAESession(CodeSession):
    """Sparse stopped transport with two PAE pages in the high RAM bank."""
    backend_id = 'qemu-dos'
    _layer_spans = QemuLayerSessionMixin._layer_spans
    _layer_native_observe = QemuLayerSessionMixin._layer_native_observe

    def __init__(self, fault=None):
        super().__init__()
        self._process = None
        self._layer_active = []
        self._layer_exec = {}
        self._layer_exec_base = {}
        self.fault = fault
        self.table_reads = 0
        self.native_calls = []
        self.physical = {}
        self.put(0x1008, (0x2001).to_bytes(8, 'little'))
        self.put(0x2000, (0x3003).to_bytes(8, 'little'))
        self.put(0x3000, (0x100001003).to_bytes(8, 'little'))
        self.put(0x3008, (0x100003003).to_bytes(8, 'little'))
        self.put(0x100001ffe, b'\x90\x90')
        self.put(0x100003000, b'\x90\xc3')
        # Deliberately different low aliases detect a truncated physical address.
        self.put(0x1ffe, b'XX')
        self.put(0x3000, (0x100001003).to_bytes(8, 'little'))
        config = dict(memory_mib=64, max_ram_below_4g_mib=32, cpu='max')
        self.vm.machine_configuration = config.copy()
        self.vm.qmp = SimpleNamespace(call=self.qmp_call)
        from fdisbull.qemu_le_translation import QEMU_TCG_QUALIFIED_IMAGE
        self.metadata = dict(machine_configuration=config.copy(),
                             runtime_inputs={'qemu_image': {'sha256': QEMU_TCG_QUALIFIED_IMAGE}})
        self.vm.inputs = self.metadata['runtime_inputs'].copy()
        controls = dict(CR0=0x80000001, CR3=0x1000, CR4=0x20, EFER=0)
        self.regs = dict(cpu_mode='protected', instruction_pointer='0x40000ffe',
            linear_pc='0x40000ffe', registers=dict(cs='0x8'),
            address_state=dict(cpu_mode='protected', code_bits=32, machine_vcpus=1,
                register_context_match=True, paging=True, a20=True, control=controls,
                segments=dict(cs=dict(selector='0x8', base='0x0', limit=0xffffffff,
                                      attributes=0x9a))))

    def put(self, address, data):
        self.physical.update({address + i: byte for i, byte in enumerate(data)})

    def registers(self):
        from copy import deepcopy
        return deepcopy(self.regs)

    def memory(self, address, length, *, space):
        if space == 'virtual':
            data = b'\x90\x90\x90\xc3'
            if self.fault == 'alias':
                data = b'XX\x90\xc3'
            return data[address - 0x40000ffe:address - 0x40000ffe + length]
        if address == 0x2000:
            self.table_reads += 1
            if self.fault == 'table' and self.table_reads > 1:
                return (0x3001).to_bytes(8, 'little')
        return bytes(self.physical.get(address + i, 0) for i in range(length))

    def qmp_call(self, command, extent=None):
        if command == 'human-monitor-command':
            return ('CR0=80000001 CR3=00001000 CR4=00000020 EFER=00000000\n'
                    'GDT=00004000 000000ff\nLDT=0000 00000000 00000000 00000000\n')
        assert command == 'x-fdisbull-layer-observe'
        self.native_calls.append(extent)
        status = {'generation': self._layer_generation, 'execution-bytes': len(self._layer_exec)}
        if self.fault == 'native-changing' and len(self.native_calls) > 1:
            status['generation'] += 1
        if self.fault == 'native-nonempty':
            status['execution-bytes'] = 1
        if self.fault == 'native-fault':
            status['fault'] = 'injected fault'
        if extent:
            assert extent['address'] <= 0xffffffff
            status['data-hex'] = self.memory(extent['address'], extent['length'], space='physical').hex()
        return status


def test_high_pae_cross_page_capture_is_read_only():
    import json
    session = HighPAESession()
    result = session.capture_code(0x40000ffe, length=4, space='linear')
    payload = json.loads(result[2])
    assert payload['hex'] == '909090c3'
    assert payload['backing'] == [
        {'physical_address': '0x100001ffe', 'length': 2},
        {'physical_address': '0x100003000', 'length': 2}]
    assert result[3]['static_promotion'] == 'unqualified'
    assert payload['execute_view_witness'] == {
        'method': 'native-empty-execution-overlay', 'generation': 4, 'execution_bytes': 0}
    assert len(session.native_calls) >= 2 and all(call is None for call in session.native_calls)
    with pytest.raises(ValueError, match='unsupported'):
        session.code(0x40000ffe, length=4, space='linear')
    with pytest.raises(ValueError, match='unsupported'):
        session.layer_patch('forbidden', 0x40000ffe, expected_hex='909090c3',
                            data_hex='cccccccc', kind='ram', activate=False, space='linear')
    assert len(session.artifacts) == 1


@pytest.mark.parametrize('fault', ['table', 'alias'])
def test_high_pae_changed_walk_or_alias_never_publishes(fault):
    session = HighPAESession(fault)
    with pytest.raises(ValueError):
        session.capture_code(0x40000ffe, length=4, space='linear')
    assert session.artifacts == []


@pytest.mark.parametrize('failure', ['mapping', 'native', 'verify', 'ram'])
def test_capture_fallback_failure_never_publishes(failure):
    from fdisbull.dosbox_rpc import DebuggerError

    session = CodeSession()
    session.backend_id = 'qemu-dos'
    session._layer_spans = lambda *args: (_ for _ in ()).throw(
        _UnsupportedLayerMapping('Layer requires an observed RAM mapping: unsupported'))
    def fail():
        raise ValueError('changed witness')
    def fallback(address, length, cs):
        if failure == 'mapping':
            fail()
        return (address, None, [(0x100000100, length)],
                {'cpu_mode': 'protected', 'code_bits': 32, 'segments': {}},
                fail if failure == 'verify' else lambda: None, bytes.fromhex('b87856'))
    session._capture_linear_spans = fallback
    session._layer_exec = {}
    if failure == 'ram':
        session.memory = lambda *args, **kwargs: b'\x00\x00\x00'
    session._layer_native_observe = lambda **kw: {'data-hex': '000000' if failure == 'native' else 'b87856'} if kw else {}
    with pytest.raises((ValueError, DebuggerError)):
        session.capture_code(0x1000, length=3, space='linear')
    assert session.artifacts == []


def test_capture_does_not_fallback_on_other_mapping_failures():
    session = CodeSession()
    session._layer_spans = lambda *args: (_ for _ in ()).throw(ValueError('mapping changed'))
    session._capture_linear_spans = lambda *args: pytest.fail('unexpected fallback')
    with pytest.raises(ValueError, match='mapping changed'):
        session.capture_code(0x1000, length=3, space='linear')
    assert session.artifacts == []


def test_extended_capture_refuses_other_backends():
    session = CodeSession()
    session.backend_id = 'other'
    session._layer_spans = lambda *args: (_ for _ in ()).throw(
        _UnsupportedLayerMapping('unsupported'))
    session._capture_linear_spans = lambda *args: pytest.fail('unexpected fallback')
    with pytest.raises(ValueError, match='unsupported'):
        session.capture_code(0x1000, length=3, space='linear')
    assert session.artifacts == []


@pytest.mark.parametrize('fault', ['native-nonempty', 'native-fault', 'native-changing'])
def test_high_execute_rejects_untrusted_native_status(fault):
    session = HighPAESession(fault)
    from fdisbull.dosbox_rpc import DebuggerError
    with pytest.raises((ValueError, DebuggerError)):
        session.capture_code(0x40000ffe, length=4, space='linear', view='execute')
    assert session.artifacts == []


def test_high_execute_refuses_active_overlays_but_ram_view_remains_available():
    session = HighPAESession()
    session._layer_exec = {0x1234: 0xcc}
    session._layer_exec_base = {0x1234: 0x90}
    with pytest.raises(ValueError):
        session.capture_code(0x40000ffe, length=4, space='linear', view='execute')
    assert session.artifacts == []
    session.capture_code(0x40000ffe, length=4, space='linear', view='ram')
    assert len(session.artifacts) == 1


def test_low_execute_still_observes_each_native_extent():
    session = CodeSession()
    calls = []
    def observe(**extent):
        calls.append(extent)
        return {'data-hex': 'b83456'} if extent else {}
    session._layer_native_observe = observe
    session.capture_code('0fff:0110', length=3, view='execute')
    assert calls == [{}, {'address': 0x20100, 'length': 3}]


def test_high_execute_reads_native_overlay_with_active_low_and_high_bytes():
    import json
    session = HighPAESession()
    session.vm.qmp_commands = {'x-fdisbull-layer-observe-physical64'}
    session._layer_exec = {0x1234: 0xcc, 0x100001fff: 0xcc}
    session._layer_exec_base = {0x1234: 0x90, 0x100001fff: 0x90}
    original = session.qmp_call
    def qmp(command, extent=None):
        if command != 'x-fdisbull-layer-observe-physical64':
            return original(command, extent)
        data = bytearray(session.memory(extent['address'], extent['length'], space='physical'))
        for i in range(len(data)):
            data[i] = session._layer_exec.get(extent['address'] + i, data[i])
        return {'generation': 4, 'execution-bytes': 2, 'data-hex': data.hex()}
    session.vm.qmp.call = qmp
    result = session.capture_code(0x40000ffe, length=4, space='linear')
    payload = json.loads(result[2])
    assert payload['hex'] == '90cc90c3'
    assert payload['execute_view_witness'] == {
        'method': 'native-physical64-execution-overlay', 'generation': 4,
        'execution_bytes': 2, 'qemu_image_sha256': session.vm.inputs['qemu_image']['sha256']}
    session.vm.qmp.call = lambda command, extent=None: (
        {'generation': 4, 'execution-bytes': 2, 'data-hex': '9090'}
        if command == 'x-fdisbull-layer-observe-physical64' else original(command, extent))
    from fdisbull.dosbox_rpc import DebuggerError
    with pytest.raises(DebuggerError, match='effective instruction fetch'):
        session.capture_code(0x40000ffe, length=4, space='linear')
    assert len(session.artifacts) == 1


def test_high_execute_observes_with_only_low_overlay_active():
    import json
    session = HighPAESession()
    session.vm.qmp_commands = {'x-fdisbull-layer-observe-physical64'}
    session._layer_exec = {0x1234: 0xcc}
    session._layer_exec_base = {0x1234: 0x90}
    original = session.qmp_call
    def qmp(command, extent=None):
        if command == 'x-fdisbull-layer-observe-physical64':
            return {'generation': 4, 'execution-bytes': 1,
                    'data-hex': session.memory(extent['address'], extent['length'], space='physical').hex()}
        return original(command, extent)
    session.vm.qmp.call = qmp
    assert json.loads(session.capture_code(0x40000ffe, length=4, space='linear')[2])['hex'] == '909090c3'


def test_high_translated_execute_patch_binds_checked_physical_spans():
    session = HighPAESession()
    session.vm.qmp_commands = {'x-fdisbull-layer-observe-physical64'}
    session.run_id = 'run'
    session.version = {'id': 'version'}
    session.project._store_debug_layer = lambda name, version, definition: definition
    definition = session.layer_patch('high', 0x40000ffe, expected_hex='909090c3',
                                     data_hex='90cc90c3', kind='execute', activate=False, space='linear')
    assert definition['native_binding']['spans'] == [(0x100001ffe, 2), (0x100003000, 2)]
    with pytest.raises(ValueError, match='unsupported'):
        session.layer_patch('high', 0x40000ffe, expected_hex='909090c3',
                            data_hex='90cc90c3', kind='ram', activate=False, space='linear')
