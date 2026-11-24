"""Host contract checks for stopped QEMU code observations."""
import threading
from types import SimpleNamespace

import pytest

from fdisbull.dos_views import DOSViewsMixin
from fdisbull.qemu_layers import QemuLayerSessionMixin


class CodeSession(QemuLayerSessionMixin):
    def __init__(self):
        self.vm = SimpleNamespace(lock=threading.RLock(), gdb=None, qmp=None)
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
