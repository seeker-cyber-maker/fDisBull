"""Display readbacks must not manufacture frame or clock qualifications."""
from copy import deepcopy
from types import SimpleNamespace

from PIL import Image
import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_surface import QemuSurfaceMixin


class Capture(QemuSurfaceMixin):
    def __init__(self, directory, *, change_cpu=False, change_clock=False):
        self.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
        self.run_id = 'owned-run'
        self.events, self.artifacts, self.calls = [], [], []
        self.cpus = [dict(linear_pc='0x1234'), dict(linear_pc='0x1235' if change_cpu else '0x1234')]
        self.clocks = [dict(epoch='clock-epoch', counter=dict(state='observed', value=count))
                       for count in (10, 11 if change_clock else 10)]
        self.closed = False
        self.vm = SimpleNamespace(temporary=SimpleNamespace(name=str(directory)),
            qmp_commands={'screendump'}, qmp=SimpleNamespace(call=self.call), close=self.close)

    def close(self):
        self.closed = True

    def call(self, method, args):
        self.calls.append(method)
        Image.new('RGB', (2, 2), (1, 2, 3)).save(args['filename'], format='PPM')
        return {}

    def _stopped(self):
        return None

    def clock_observe(self):
        return self.clocks.pop(0)

    def registers(self):
        return self.cpus.pop(0)

    def _artifact(self, name, kind, data, metadata):
        result = dict(artifact=1, metadata=deepcopy(metadata), data=data)
        self.artifacts.append(result)
        return result

    def _event(self, operation, evidence):
        self.events.append((operation, evidence))


@pytest.mark.parametrize('change', ['change_cpu', 'change_clock'])
def test_changed_stopped_bracket_cannot_return_a_surface_and_closes_owner(tmp_path, change):
    capture = Capture(tmp_path, **{change: True})
    with pytest.raises(DebuggerError, match='changed'):
        capture.capture_surface()
    assert capture.closed and capture.artifacts == []
    assert capture.calls == ['screendump']
    assert list(tmp_path.iterdir()) == []


def test_surface_receipt_has_no_completed_frame_and_cannot_fake_supported_clock(tmp_path):
    capture = Capture(tmp_path)
    capture.clocks = [dict(epoch='standard-clock', counter=dict(state='unsupported', value=None))
                      for _ in range(2)]
    result = capture.capture_surface('visible.png')
    metadata = result['metadata']
    assert metadata['source'] == 'qemu_display_surface'
    assert metadata['completed_guest_frame'] is None and metadata['guest_frame_id'] is None
    assert metadata['clock_stability'] == 'not_observable'
    assert metadata['selected_cpu_unchanged'] is True and metadata['stopped'] is True
    assert result['data'].startswith(b'\x89PNG\r\n\x1a\n')
    assert not capture.closed and list(tmp_path.iterdir()) == []


def test_surface_transaction_refusal_precedes_native_requests(tmp_path):
    capture = Capture(tmp_path)
    capture.project.db.in_transaction = True
    with pytest.raises(ValueError, match='caller-owned transaction'):
        capture.capture_surface()
    assert capture.calls == capture.artifacts == [] and not capture.closed


def test_virtual_time_change_refuses_capture_even_when_instruction_count_is_unchanged(tmp_path):
    capture = Capture(tmp_path)
    for clock, virtual_ns in zip(capture.clocks, (10, 11)):
        clock['virtual_ns'] = virtual_ns
    with pytest.raises(DebuggerError, match='clock changed'):
        capture.capture_surface()
    assert capture.closed and capture.artifacts == []


def test_virtual_surface_keeps_both_stopped_clock_domains(tmp_path):
    capture = Capture(tmp_path)
    for clock in capture.clocks:
        clock['virtual_ns'] = 19
    result = capture.capture_surface()
    assert result['metadata']['clock_stability'] == 'virtual_clock_and_instruction_counter_unchanged'
    assert result['metadata']['completed_guest_frame'] is None


def test_surface_image_budget_refuses_before_artifact_publication(tmp_path):
    capture = Capture(tmp_path)
    with pytest.raises(ValueError, match='image byte budget'):
        capture.capture_surface(max_bytes=1)
    assert capture.calls == ['screendump'] and capture.artifacts == []
    assert not capture.closed and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('limit', [0, True, 16*1024**2+1])
def test_surface_invalid_image_budget_precedes_native_capture(tmp_path, limit):
    capture = Capture(tmp_path)
    with pytest.raises(ValueError, match='max_bytes'):
        capture.capture_surface(max_bytes=limit)
    assert capture.calls == capture.artifacts == []
