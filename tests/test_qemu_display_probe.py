"""Sparse publication evidence through the production QMP envelope and bounds."""
from copy import deepcopy
import json

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.debug_script import execute_script
from fdisbull.qemu_display import DISPLAY_PROBE_COMMANDS
from test_qemu_display import DisplayWire
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation


class ProbeWire(DisplayWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.mutate_probe = lambda value: value
        self.after_probe = lambda: None

    def publish(self):
        update = self.display['updates'] + 1
        self.display.update(updates=update, width=3, height=2,
                            **{'update-id': update, 'published-ns': self.receipt['virtual-ns']})
        self.pixels = bytes((255, 0, 0, 0, 255, 0, 0, 0, 255,
                             1, 2, 3, 4, 5, 6, 7, 8, 9))

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command == 'x-fdisbull-start-display':
            self.display = {'api-version': 1, 'epoch': 1, 'state': 'idle',
                            'virtual-ns': self.receipt['virtual-ns'], 'period-ns': 0, 'updates': 0}
        if command != 'x-fdisbull-probe-display':
            return super().sendall(data)
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        self.display['virtual-ns'] = self.receipt['virtual-ns']
        samples = []
        for point in args['points']:
            offset = (point['y'] * self.display['width'] + point['x']) * 3
            r, g, b = self.pixels[offset:offset + 3]
            samples.append(dict(point, r=r, g=g, b=b))
        response = self.mutate_probe(dict(display=deepcopy(self.display), samples=samples))
        self.buffer.extend(json.dumps({'id': request['id'], 'return': response}).encode() + b'\n')
        self.delay = self.latency
        self.after_probe()


@pytest.fixture
def probe(audio):
    o = audio
    wire = ProbeWire(o.clock)
    o.qmp.socket = o.wire = wire
    from fdisbull.qemu_display import DISPLAY_COMMANDS
    o.vm.qmp_commands |= DISPLAY_COMMANDS | DISPLAY_PROBE_COMMANDS
    o.session.capabilities.update(renderer_capture=True, renderer_probe=True)
    o.session.display_start()
    wire.publish()
    wire.calls.clear()
    wire.budgets.clear()
    return o


def probe_calls(o):
    return [args for command, args in o.wire.calls if command == 'x-fdisbull-probe-display']


def test_probe_reads_ordered_duplicate_pixels_without_image_export_or_execution(probe):
    o = probe
    result = o.session.display_probe([[2, 1], [0, 0], (2, 1), [1, 0]])
    assert result['format'] == 'fdisbull-renderer-probe-1'
    assert result['points'] == [[2, 1], [0, 0], [2, 1], [1, 0]]
    assert result['pixels'] == [dict(x=2, y=1, rgb=[7, 8, 9]), dict(x=0, y=0, rgb=[255, 0, 0]),
                                dict(x=2, y=1, rgb=[7, 8, 9]), dict(x=1, y=0, rgb=[0, 255, 0])]
    assert result['coordinate_domain'] == 'retained_renderer_pixels' and result['pixel_format'] == 'RGB24'
    assert result['completed_renderer_update'] is True and result['completed_guest_frame'] is None
    assert result['guest_frame_id'] is None
    assert not {'mode_id', 'frame_id', 'state_revision', 'pixel_sha256'} & result.keys()
    assert result['clocks']['before']['counter'] == result['clocks']['after']['counter']
    assert result['clocks']['before']['virtual_ns'] == result['clocks']['after']['virtual_ns']
    assert probe_calls(o) == [dict(token=result['window'], **{'update-id': 1},
                                  points=[dict(x=x, y=y) for x, y in result['points']])]
    assert not {'screendump', 'x-fdisbull-export-display', 'cont', 'human-monitor-command'} & {
        command for command, _ in o.wire.calls}
    assert not list(o.directory.glob('*.ppm'))
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('count', [0, 256])
def test_probe_empty_and_maximum_point_lists(probe, count):
    o = probe
    result = o.session.display_probe([[0, 0]] * count)
    assert len(result['pixels']) == count and result['update_id'] == 1
    assert len(o.vm._display_probe_samples['samples']) <= 256


@pytest.mark.parametrize('options', [
    dict(points=None), dict(points=()), dict(points='00'), dict(points={}),
    dict(points=[[0, 0]] * 257), dict(points=[0]), dict(points=[[]]),
    dict(points=[[0]]), dict(points=[[0, 0, 0]]), dict(points=[dict(x=0, y=0)]),
    dict(points=[[True, 0]]), dict(points=[[0, False]]), dict(points=[[0.0, 0]]),
    dict(points=[[0, '0']]), dict(points=[[-1, 0]]), dict(points=[[8192, 0]]),
    dict(points=[[0, 8192]]), dict(points=[], window='w'), dict(points=[], update_id=1),
    dict(points=[], window='', update_id=1), dict(points=[], window='w\0', update_id=1),
    dict(points=[], window='w' * 129, update_id=1), dict(points=[], window=True, update_id=1),
    dict(points=[], window='w', update_id=True), dict(points=[], window='w', update_id=0),
    dict(points=[], window='w', update_id=1 << 64), dict(points=[], window='w', update_id=1.0),
    dict(points=[], timeout_ms=True), dict(points=[], timeout_ms=None),
    dict(points=[], timeout_ms=0), dict(points=[], timeout_ms=600001),
])
def test_invalid_probe_values_refuse_before_any_native_io(probe, options):
    o = probe
    with pytest.raises(ValueError):
        o.session.display_probe(**options)
    assert not o.wire.calls and not o.vm.closed


@pytest.mark.parametrize('reason', ['empty', 'window', 'old-update', 'future-update', 'width', 'height'])
def test_valid_but_unavailable_publication_or_point_refuses_without_probe(probe, reason):
    o = probe
    args = dict(points=[[0, 0]])
    if reason == 'empty':
        o.wire.display['updates'] = 0
        for key in ('update-id', 'published-ns', 'width', 'height'):
            o.wire.display.pop(key)
    elif reason in ('window', 'old-update', 'future-update'):
        args.update(window=o.wire.display['token'], update_id=1)
        if reason == 'window':
            args['window'] = 'foreign'
        elif reason == 'old-update':
            o.wire.publish()
        else:
            args['update_id'] = 2
    else:
        args['points'] = [[3, 0] if reason == 'width' else [0, 2]]
    with pytest.raises(ValueError):
        o.session.display_probe(**args)
    assert not probe_calls(o) and not o.vm.closed


def test_expected_identity_is_exact_and_window_scoped(probe):
    o = probe
    first = o.session.display_probe([])
    o.session.display_stop()
    second = o.session.display_start()
    o.wire.publish()
    assert first['window'] != second['window']
    with pytest.raises(ValueError, match='different retained'):
        o.session.display_probe([], window=first['window'], update_id=1)
    result = o.session.display_probe([], window=second['window'], update_id=1)
    assert result['update_id'] == 1 and result['window'] == second['window'] and not o.vm.closed


@pytest.mark.parametrize('mutation', [
    lambda value: None,
    lambda value: dict(value, png_base64='unexpected'),
    lambda value: {'display': value['display']},
    lambda value: dict(value, samples=None),
    lambda value: dict(value, samples=[]),
    lambda value: dict(value, samples=value['samples'] * 2),
    lambda value: dict(value, samples=list(reversed(value['samples']))),
    lambda value: dict(value, samples=[dict(value['samples'][0], r=True), value['samples'][1]]),
    lambda value: dict(value, samples=[dict(value['samples'][0], x=False), value['samples'][1]]),
    lambda value: dict(value, samples=[dict(value['samples'][0], g=-1), value['samples'][1]]),
    lambda value: dict(value, samples=[dict(value['samples'][0], b=256), value['samples'][1]]),
    lambda value: dict(value, samples=[dict(value['samples'][0], r=1.0), value['samples'][1]]),
    lambda value: dict(value, samples=[dict(value['samples'][0], extra=1), value['samples'][1]]),
    lambda value: dict(value, samples=[{k: v for k, v in value['samples'][0].items() if k != 'b'}, value['samples'][1]]),
])
def test_malformed_samples_close_without_artifact_or_retry(probe, mutation):
    o = probe
    o.wire.mutate_probe = mutation
    with pytest.raises(DebuggerError) as caught:
        o.session.display_probe([[0, 0], [1, 1]])
    assert o.vm.closed and len(probe_calls(o)) == 1
    assert caught.value.result['native_received'] is True
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0


@pytest.mark.parametrize('change', [
    {'epoch': 2}, {'token': 'wrong'}, {'update-id': 2}, {'updates': 2, 'update-id': 2},
    {'width': 2}, {'height': 1}, {'virtual-ns': 1001}, {'published-ns': 999},
    {'period-ns': 1_000_000}, {'state': 'stopped', 'stop-ns': 1000},
])
def test_probe_must_return_exact_queried_publication(probe, change):
    o = probe
    o.wire.mutate_probe = lambda value: dict(value, display=dict(value['display'], **change))
    with pytest.raises(DebuggerError) as caught:
        o.session.display_probe([[0, 0]])
    assert o.vm.closed and caught.value.result['native']['display'].items() >= change.items()


@pytest.mark.parametrize('between_calls', [False, True])
def test_duplicate_or_previous_probe_overlap_cannot_contradict_rgb(probe, between_calls):
    o = probe
    if between_calls:
        o.session.display_probe([[1, 0], [0, 0]])
    def mutate(value):
        value['samples'][-1]['r'] = 0
        return value
    o.wire.mutate_probe = mutate
    with pytest.raises(DebuggerError, match='pixels changed'):
        o.session.display_probe([[0, 0]] if between_calls else [[0, 0], [0, 0]])
    assert o.vm.closed


def test_sample_consistency_memory_is_one_previous_probe_and_changes_with_publication(probe):
    o = probe
    o.session.display_probe([[0, 0], [1, 0]])
    o.session.display_probe([[1, 0], [2, 0]])
    assert set(o.vm._display_probe_samples['samples']) == {(1, 0), (2, 0)}
    o.wire.publish()
    o.wire.pixels = bytes(18)
    value = o.session.display_probe([[1, 0]])
    assert value['update_id'] == 2 and value['pixels'][0]['rgb'] == [0, 0, 0]


@pytest.mark.parametrize('clock_field', ['epoch', 'virtual-ns', 'counter'])
def test_clock_change_across_sparse_read_closes_owner(probe, clock_field):
    o = probe
    def change():
        if clock_field == 'counter':
            o.wire.counter += 1
        else:
            o.wire.receipt[clock_field] += 1
    o.wire.after_probe = change
    with pytest.raises(DebuggerError):
        o.session.display_probe([[0, 0]])
    assert o.vm.closed and len(probe_calls(o)) == 1


@pytest.mark.parametrize('event', ['machine-clock-observe', 'machine-display-probe'])
def test_initial_or_final_journal_failure_closes_without_retry(probe, event):
    o = probe
    original = o.session._event
    def fail(name, payload):
        if name == event:
            raise OSError('authored storage failure')
        original(name, payload)
    o.session._event = fail
    with pytest.raises(OSError) as caught:
        o.session.display_probe([[0, 0]])
    assert o.vm.closed
    if event == 'machine-display-probe':
        assert caught.value.result['format'] == 'fdisbull-renderer-probe-1'
        assert len(probe_calls(o)) == 1
    else:
        assert not probe_calls(o)


@pytest.mark.parametrize('reply', [None, {'api-version': 99}])
def test_malformed_prequery_retains_raw_evidence_and_closes(probe, reply):
    o = probe
    o.wire.mutate_display = lambda value: reply
    with pytest.raises(DebuggerError) as caught:
        o.session.display_probe([])
    assert o.vm.closed and not probe_calls(o)
    assert caught.value.result['stage'] == 'publication-query'
    assert caught.value.result['native_received'] is True and caught.value.result['native'] == reply


def test_completed_prequery_error_with_healthy_channel_closes(probe):
    o = probe
    original = o.qmp.call
    def failed(command, arguments=None):
        if command == 'x-fdisbull-query-display':
            raise DebuggerError('authored completed QMP refusal')
        return original(command, arguments)
    o.qmp.call = failed
    with pytest.raises(DebuggerError) as caught:
        o.session.display_probe([])
    assert o.vm.closed and not probe_calls(o)
    assert caught.value.result['native_received'] is False


def test_late_committed_probe_keeps_evidence_and_closes(probe):
    o = probe
    original = o.session._event
    def late(name, payload):
        original(name, payload)
        if name == 'machine-display-probe':
            o.clock.now += 1.01
    o.session._event = late
    with pytest.raises(TimeoutError) as caught:
        o.session.display_probe([[0, 0]])
    assert o.vm.closed and caught.value.result['pixels'][0]['rgb'] == [255, 0, 0]
    assert o.project.db.execute("SELECT count(*) FROM debug_events WHERE operation='machine-display-probe'").fetchone()[0] == 1


def test_direct_probe_has_one_host_deadline_through_actual_qmp_io(probe):
    o = probe
    o.wire.latency = .15
    with pytest.raises(TimeoutError):
        o.session.display_probe([[0, 0]])
    assert o.clock.now == pytest.approx(101.0)
    assert o.vm.closed and o.wire.socket_closed
    assert o.wire.budgets == pytest.approx([1.0, .85, .70, .55, .40, .25, .10])
    assert len(probe_calls(o)) == 1


def test_tighter_incoming_deadlines_are_preserved_and_restored(probe):
    o = probe
    o.session._rpc_deadline, o.session._deadline = 100.6, 100.5
    o.vm.operation_deadline, o.qmp.operation_deadline, o.gdb.operation_deadline = 100.4, 100.3, 100.2
    o.session.display_probe([[0, 0]], timeout_ms=5000)
    assert o.wire.budgets and all(value == pytest.approx(.2) for value in o.wire.budgets)
    assert o.session._rpc_deadline == 100.6 and o.session._deadline == 100.5
    assert o.vm.operation_deadline == 100.4 and o.qmp.operation_deadline == 100.3
    assert o.gdb.operation_deadline == 100.2 and not o.vm.closed


def test_script_probe_shares_the_route_deadline_at_the_qmp_transport(probe):
    o = probe
    o.wire.latency = .02
    route = dict(format='fdisbull-script-1', backend='qemu-machine',
                 steps=[dict(op='display-probe', points=[[0, 0]])])
    report = execute_script(o.session, route, timeout_ms=50)
    assert not report['ok'] and report['error']['type'] == 'TimeoutError'
    # The script floors its remaining allowance to integer milliseconds.
    first = o.wire.budgets[0]
    assert .049 <= first <= .05 + 1e-12
    assert o.wire.budgets == pytest.approx([first, first - .02, first - .04])
    assert not probe_calls(o) and o.vm.closed and o.wire.socket_closed
