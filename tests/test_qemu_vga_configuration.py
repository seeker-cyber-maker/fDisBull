"""Configuration identity and history through the production QMP boundary."""
from copy import deepcopy
import hashlib
import json

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_clock import VIRTUAL_CLOCK_COMMANDS, machine_clock_configuration
from fdisbull.qemu_display import DISPLAY_COMMANDS
from fdisbull.qemu_retrace import RETRACE_COMMANDS, machine_retrace_configuration
from fdisbull.qemu_vga_configuration import VGA_CONFIGURATION_COMMANDS, VGA_CONFIGURATION_MODEL
from test_qemu_display import DisplayWire
from test_qemu_audio import audio
from test_qemu_io_deadlines import observation


class ConfigurationWire(DisplayWire):
    def __init__(self, clock):
        super().__init__(clock)
        self.configuration = {'api-version': 1, 'model': VGA_CONFIGURATION_MODEL,
            'epoch': 1, 'virtual-ns': 1000, 'device': '/machine/unattached/device[0]',
            'device-type': 'VGA', 'console': 0, 'head': 0, 'configuration-generation': 5,
            'raw': {'sequencer': [0] * 8, 'sequencer-vbe': [0] * 8,
                'graphics': [0] * 16, 'crtc': [0] * 256, 'attribute-controls': [0] * 5,
                'misc-output': 1, 'feature-control': 0, 'display-enabled': True,
                'vbe': [0xb0c5] + [0] * 9, 'vbe-start-address': 0,
                'vbe-line-offset': 0, 'vbe-bank-mask': 255, 'bank-offset': 0,
                'dac-8bit': False, 'big-endian-framebuffer': False,
                'vram-size': 16777216, 'vbe-size': 16777216, 'vbe-size-mask': 16777215}}
        self.published = None
        self.mutate_configuration = lambda value: value
        self.after_configuration = lambda: None
        self.reject_configuration = False
        self.refuse_command = None
        self.mutate_envelope = lambda value: value
        self.last_configuration_reply = None

    def current(self):
        value = deepcopy(self.configuration)
        value['virtual-ns'] = self.receipt['virtual-ns']
        return value

    def publish(self):
        update = self.display['updates'] + 1
        self.display.update(updates=update, width=320, height=200,
            **{'update-id': update, 'published-ns': self.receipt['virtual-ns']})
        self.published = self.current()

    def sendall(self, data):
        request = json.loads(data)
        command, args = request['execute'], request.get('arguments', {})
        if command == self.refuse_command:
            self.calls.append((command, args))
            self.budgets.append(self.timeout)
            self.buffer.extend(json.dumps({'id': request['id'], 'error': {
                'class': 'GenericError', 'desc': 'authored clock refusal'}}).encode() + b'\n')
            self.delay = self.latency
            return
        if command == 'x-fdisbull-start-display':
            self.display = {'api-version': 1, 'epoch': 1, 'state': 'idle',
                'virtual-ns': self.receipt['virtual-ns'], 'period-ns': 0, 'updates': 0}
            self.published = None
        if command != 'x-fdisbull-query-vga-configuration':
            return super().sendall(data)
        assert args == {}
        self.calls.append((command, args))
        self.budgets.append(self.timeout)
        self.display['virtual-ns'] = self.receipt['virtual-ns']
        value = dict(display=deepcopy(self.display), current=self.current())
        if self.published is not None:
            value['published'] = deepcopy(self.published)
        value = self.mutate_configuration(value)
        self.last_configuration_reply = deepcopy(value)
        answer = ({'error': {'class': 'GenericError', 'desc': 'authored native refusal'}}
                  if self.reject_configuration else {'return': value})
        envelope = self.mutate_envelope(dict(id=request['id'], **answer))
        self.buffer.extend(json.dumps(envelope).encode() + b'\n')
        self.delay = self.latency
        self.after_configuration()


@pytest.fixture
def vga(audio):
    o = audio
    o.wire = ConfigurationWire(o.clock)
    o.qmp.socket = o.wire
    o.vm.qmp_commands |= DISPLAY_COMMANDS | RETRACE_COMMANDS | VGA_CONFIGURATION_COMMANDS
    o.vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('precise', 'virtual')
    o.vm.native_retrace_admission = {key: deepcopy(o.wire.configuration[key])
        for key in ('epoch', 'device', 'device-type', 'console', 'head')}
    o.session.capabilities.update(vga_configuration=True, renderer_capture=True,
                                  retrace_observation=True)
    return o


def publish(o):
    if o.wire.display['state'] == 'idle':
        o.session.display_start()
    o.wire.publish()
    o.wire.calls.clear()
    o.wire.budgets.clear()


def configuration_calls(o):
    return [args for command, args in o.wire.calls
            if command == 'x-fdisbull-query-vga-configuration']


def configuration_events(o):
    return [json.loads(row[0]) for row in o.project.db.execute(
        "SELECT evidence FROM debug_events WHERE operation='machine-vga-configuration-observe'")]


def replace(value, path, replacement):
    target = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return value


@pytest.mark.parametrize('empty_window', [False, True])
def test_later_publication_cannot_contradict_last_actual_stamp(vga, empty_window):
    o = vga
    publish(o)
    o.session.vga_configuration_observe()
    if empty_window:
        o.session.display_stop()
        o.session.display_start()
        assert o.session.vga_configuration_observe()['published'] is None
    o.wire.configuration['configuration-generation'] = 7
    o.wire.configuration['raw']['crtc'][0x0d] = 8
    o.wire.receipt['virtual-ns'] += 1
    o.wire.publish()
    o.wire.published['configuration-generation'] = 4 if empty_window else 5
    o.wire.published['raw']['crtc'][0x0d] = 9
    with pytest.raises(DebuggerError, match='configuration'):
        o.session.vga_configuration_observe()
    assert o.vm.closed


def test_published_stamp_cannot_contradict_previously_observed_current_generation(vga):
    o = vga
    publish(o)
    o.wire.configuration['configuration-generation'] = 6
    o.wire.configuration['raw']['crtc'][0x0d] = 6
    o.session.vga_configuration_observe()
    o.wire.configuration['configuration-generation'] = 7
    o.wire.configuration['raw']['crtc'][0x0d] = 7
    o.wire.publish()
    o.wire.published['configuration-generation'] = 6
    o.wire.published['raw']['crtc'][0x0d] = 9
    with pytest.raises(DebuggerError, match='configuration'):
        o.session.vga_configuration_observe()
    assert o.vm.closed


def test_clock_conflict_keeps_both_completed_brackets(vga):
    o = vga
    o.wire.after_configuration = lambda: setattr(o.wire, 'counter', o.wire.counter + 1)
    with pytest.raises(DebuggerError, match='clock changed') as caught:
        o.session.vga_configuration_observe()
    clocks = caught.value.result['clocks']
    assert clocks['before']['counter']['value'] + 1 == clocks['after']['counter']['value']
    assert o.vm.closed and caught.value.result['native_received'] is True


@pytest.mark.parametrize('empty_window', [False, True])
def test_passive_observation_without_pixels_needs_no_renderer_or_execution(vga, empty_window):
    o = vga
    if empty_window:
        o.session.display_start()
        o.wire.calls.clear()
    result = o.session.vga_configuration_observe()
    assert result['format'] == 'fdisbull-vga-configuration-1'
    assert result['run'] == o.session.run_id and result['context'] == 'machine'
    assert result['published'] is result['configuration_matches'] is None
    assert result['display']['state'] == ('observing' if empty_window else 'idle')
    assert result['display']['updates'] == 0 and result['display']['width'] is None
    assert result['publication_configuration_semantics'] == 'configuration_observed_at_publication'
    for field in ('raster_coherence', 'cursor_mapping', 'completed_guest_frame', 'guest_frame_id'):
        assert result[field] is None
    assert not {'mode_id', 'frame_id', 'state_revision'} & result.keys()
    assert [command for command, _ in o.wire.calls] == [
        'query-status', 'query-replay', 'x-fdisbull-query-clock',
        'x-fdisbull-query-vga-configuration',
        'query-status', 'query-replay', 'x-fdisbull-query-clock']
    before, after = result['clocks']['before'], result['clocks']['after']
    assert before['counter'] == after['counter'] and before['virtual_ns'] == after['virtual_ns'] == 1000
    assert before['epoch'] == after['epoch'] == result['epoch']
    assert before['sequence'] < after['sequence']
    assert configuration_events(o) == [result]
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
    assert not list(o.directory.glob('*.ppm')) and not list(o.directory.glob('*.png'))
    assert not o.vm.closed


def test_raw_fingerprint_is_canonical_values_not_generation_or_renderer_identity(vga):
    o = vga
    publish(o)
    first = o.session.vga_configuration_observe()
    expected = hashlib.sha256(json.dumps(first['native']['current']['raw'],
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
    assert first['current']['configuration_sha256'] == expected
    assert first['configuration_matches'] is True
    # An unobserved A -> B -> A restores the values, not the native identity.
    o.wire.configuration['configuration-generation'] += 2
    o.wire.configuration['raw'] = dict(reversed(list(o.wire.configuration['raw'].items())))
    restored = o.session.vga_configuration_observe()
    assert restored['current']['configuration_sha256'] == expected
    assert restored['current']['configuration_generation'] == first['current']['configuration_generation'] + 2
    assert restored['configuration_matches'] is False
    assert restored['published'] == first['published']
    assert restored['display']['update_id'] == first['display']['update_id']
    assert not o.vm.closed


def test_returned_and_journaled_values_do_not_mutate_owned_frontiers(vga):
    o = vga
    publish(o)
    first = o.session.vga_configuration_observe()
    retained = deepcopy(first)
    first['current']['raw']['crtc'][13] = 99
    first['published']['raw']['crtc'][13] = 88
    first['native']['current']['raw']['crtc'][13] = 77
    second = o.session.vga_configuration_observe()
    assert second['current'] == retained['current'] and second['published'] == retained['published']
    assert configuration_events(o)[0] == retained
    assert o.vm._vga_configuration_last['raw']['crtc'][13] == 0
    assert o.vm._vga_publication_last['snapshot']['raw']['crtc'][13] == 0


def test_stopped_publication_keeps_its_stamp_when_current_configuration_changes(vga):
    o = vga
    publish(o)
    first = o.session.vga_configuration_observe()
    stopped = o.session.display_stop()
    o.wire.configuration['configuration-generation'] += 1
    o.wire.configuration['raw']['crtc'][13] = 4
    o.wire.receipt['virtual-ns'] += 100
    observed = o.session.vga_configuration_observe()
    assert observed['published'] == first['published']
    assert observed['display']['state'] == 'stopped'
    assert observed['display']['stop_ns'] == stopped['stop_ns']
    assert observed['display']['age_ns'] == 100
    assert observed['display']['width'] == 320 and observed['display']['height'] == 200
    assert observed['configuration_matches'] is False
    assert observed['current']['observed_ns'] == 1100
    assert not {'width', 'height', 'mode_id'} & observed['current'].keys()
    assert not o.vm.closed


def test_same_virtual_time_allows_a_stopped_configuration_change(vga):
    o = vga
    publish(o)
    first = o.session.vga_configuration_observe()
    o.wire.configuration['configuration-generation'] += 1
    o.wire.configuration['raw']['big-endian-framebuffer'] = True
    second = o.session.vga_configuration_observe()
    assert second['current']['observed_ns'] == second['published']['observed_ns'] == first['current']['observed_ns']
    assert second['current']['configuration_generation'] > second['published']['configuration_generation']
    assert second['published'] == first['published'] and second['configuration_matches'] is False
    assert first['clocks']['after']['counter'] == second['clocks']['before']['counter']
    assert not o.vm.closed


def test_empty_replacement_window_preserves_device_generation_then_accepts_new_publication(vga):
    o = vga
    publish(o)
    first = o.session.vga_configuration_observe()
    o.session.display_stop()
    o.session.display_start()
    empty = o.session.vga_configuration_observe()
    assert empty['published'] is None and empty['configuration_matches'] is None
    assert empty['display']['window'] != first['display']['window']
    assert empty['current']['configuration_generation'] == first['current']['configuration_generation']
    o.wire.receipt['virtual-ns'] += 1
    o.wire.publish()
    new = o.session.vga_configuration_observe()
    assert new['display']['update_id'] == 1 and new['configuration_matches'] is True
    assert new['display']['window'] == empty['display']['window']
    assert new['current']['configuration_generation'] == first['current']['configuration_generation']
    assert not o.vm.closed


@pytest.mark.parametrize('reply', [None, [], {}, {'display': {}}, {'current': {}}, False])
def test_missing_or_wrong_envelope_payload_preserves_the_received_value(vga, reply):
    o = vga
    o.wire.mutate_configuration = lambda value: reply
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    evidence = caught.value.result
    assert evidence['native_received'] is True and evidence['native'] == reply
    assert evidence['stage'] == 'configuration-query'
    assert o.vm.closed and configuration_calls(o) == [{}] and not configuration_events(o)


@pytest.mark.parametrize('location', ['envelope', 'current', 'raw', 'display'])
def test_unknown_native_fields_are_not_silently_discarded(vga, location):
    o = vga
    def add(value):
        target = {'envelope': value, 'current': value['current'],
                  'raw': value['current']['raw'], 'display': value['display']}[location]
        target['unversioned-extra'] = 7
        return value
    o.wire.mutate_configuration = add
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert caught.value.result['native'] == o.wire.last_configuration_reply
    assert o.vm.closed and not configuration_events(o)


@pytest.mark.parametrize('path', [
    ('current', 'model'), ('current', 'configuration-generation'), ('current', 'raw'),
    ('current', 'raw', 'crtc'), ('current', 'raw', 'bank-offset'), ('display', 'updates'),
])
def test_missing_required_native_fields_fail_with_unmodified_evidence(vga, path):
    o = vga
    def remove(value):
        target = value
        for key in path[:-1]:
            target = target[key]
        target.pop(path[-1])
        return value
    o.wire.mutate_configuration = remove
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert o.vm.closed and caught.value.result['native'] == o.wire.last_configuration_reply


@pytest.mark.parametrize('field,value', [
    ('api-version', True), ('api-version', 2), ('model', 'qemu-vga-configuration-fdisbull-v2'),
    ('epoch', False), ('epoch', 0), ('epoch', 2), ('epoch', 1 << 64),
    ('virtual-ns', True), ('virtual-ns', -1), ('virtual-ns', 1001),
    ('device', 'relative'), ('device', '/'), ('device', '/foreign'), ('device', '/bad\0path'),
    ('device-type', 'secondary-vga'), ('console', False), ('console', 1),
    ('head', True), ('head', 1), ('configuration-generation', True),
    ('configuration-generation', 0), ('configuration-generation', 1 << 64),
    ('raw', None), ('raw', []),
])
def test_snapshot_identity_types_and_bounds_are_exact(vga, field, value):
    o = vga
    o.wire.mutate_configuration = lambda reply: replace(reply, ('current', field), value)
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert caught.value.result['native']['current'][field] == value
    assert o.vm.closed and configuration_calls(o) == [{}] and not configuration_events(o)


@pytest.mark.parametrize('field,length,maximum', [
    ('sequencer', 8, 255), ('sequencer-vbe', 8, 255), ('graphics', 16, 255),
    ('crtc', 256, 255), ('attribute-controls', 5, 255), ('vbe', 10, 65535),
])
@pytest.mark.parametrize('defect', ['short', 'long', 'boolean', 'negative', 'overflow'])
def test_register_arrays_are_bounded_native_vectors(vga, field, length, maximum, defect):
    o = vga
    values = [0] * length
    if defect == 'short':
        values.pop()
    elif defect == 'long':
        values.append(0)
    else:
        values[-1] = {'boolean': True, 'negative': -1, 'overflow': maximum + 1}[defect]
    o.wire.mutate_configuration = lambda reply: replace(reply, ('current', 'raw', field), values)
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert caught.value.result['native']['current']['raw'][field] == values
    assert o.vm.closed and not configuration_events(o)


@pytest.mark.parametrize('field,value', [
    ('sequencer', None), ('graphics', {'0': 0}), ('vbe', 'ten words'),
    ('crtc', [0.0] * 256), ('attribute-controls', ['0'] * 5),
    ('misc-output', True), ('misc-output', -1), ('misc-output', 256),
    ('feature-control', 1.0), ('feature-control', 256),
    ('vbe-start-address', -1), ('vbe-line-offset', 1 << 32),
    ('vbe-bank-mask', True), ('vram-size', 1 << 32),
    ('vbe-size', -1), ('vbe-size-mask', 1.0),
    ('bank-offset', True), ('bank-offset', -(1 << 31) - 1), ('bank-offset', 1 << 31),
    ('display-enabled', 1), ('dac-8bit', 0), ('big-endian-framebuffer', 'false'),
])
def test_native_scalar_domains_and_array_types_do_not_coerce(vga, field, value):
    o = vga
    o.wire.mutate_configuration = lambda reply: replace(reply, ('current', 'raw', field), value)
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert caught.value.result['native']['current']['raw'][field] == value
    assert o.vm.closed and not configuration_events(o)


@pytest.mark.parametrize('bank_offset', [-(1 << 31), (1 << 31) - 1])
def test_declared_integer_endpoints_are_preserved_without_guessed_mode_constraints(vga, bank_offset):
    o = vga
    o.wire.configuration['configuration-generation'] = (1 << 64) - 1
    raw = o.wire.configuration['raw']
    raw['sequencer'] = [255] * 8
    raw['vbe'] = [65535] * 10
    raw['vbe-start-address'] = (1 << 32) - 1
    raw['bank-offset'] = bank_offset
    result = o.session.vga_configuration_observe()
    assert result['current']['raw'] == raw
    assert result['current']['configuration_generation'] == (1 << 64) - 1
    assert result['cursor_mapping'] is None and not o.vm.closed


@pytest.mark.parametrize('change', [
    {'configuration-generation': 4}, {'device': '/another/device'}, {'epoch': 2},
])
def test_current_identity_cannot_regress_or_change_owner(vga, change):
    o = vga
    o.session.vga_configuration_observe()
    o.wire.configuration.update(change)
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert o.vm.closed and len(configuration_events(o)) == 1
    assert caught.value.result['native']['current'].items() >= change.items()


def test_current_raw_cannot_change_without_advancing_generation(vga):
    o = vga
    o.session.vga_configuration_observe()
    o.wire.configuration['raw']['crtc'][13] = 8
    with pytest.raises(DebuggerError, match='one generation') as caught:
        o.session.vga_configuration_observe()
    assert caught.value.result['native']['current']['raw']['crtc'][13] == 8
    assert o.vm.closed and len(configuration_events(o)) == 1


@pytest.mark.parametrize('defect', ['missing', 'null', 'ahead', 'wrong-time', 'wrong-device', 'extra'])
def test_existing_publication_requires_its_exact_historical_snapshot(vga, defect):
    o = vga
    publish(o)
    def corrupt(value):
        if defect == 'missing':
            value.pop('published')
        elif defect == 'null':
            value['published'] = None
        else:
            field, changed = {'ahead': ('configuration-generation', 6),
                'wrong-time': ('virtual-ns', 999), 'wrong-device': ('device', '/other'),
                'extra': ('invented', True)}[defect]
            value['published'][field] = changed
        return value
    o.wire.mutate_configuration = corrupt
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert caught.value.result['native'] == o.wire.last_configuration_reply
    assert o.vm.closed and not configuration_events(o)


def test_publication_stamp_is_not_invented_before_the_first_renderer_update(vga):
    o = vga
    o.wire.mutate_configuration = lambda value: dict(value, published=deepcopy(value['current']))
    with pytest.raises(DebuggerError, match='invented'):
        o.session.vga_configuration_observe()
    assert o.vm.closed and not configuration_events(o)


def test_equal_current_and_publication_generation_must_have_equal_raw(vga):
    o = vga
    publish(o)
    o.wire.published['raw']['big-endian-framebuffer'] = True
    with pytest.raises(DebuggerError, match='current generation'):
        o.session.vga_configuration_observe()
    assert o.vm.closed


def test_same_publication_cannot_acquire_a_new_configuration_generation(vga):
    o = vga
    publish(o)
    o.session.vga_configuration_observe()
    o.wire.configuration['configuration-generation'] = 7
    o.wire.published['configuration-generation'] = 6
    with pytest.raises(DebuggerError, match='stamp changed'):
        o.session.vga_configuration_observe()
    assert o.vm.closed and len(configuration_events(o)) == 1


@pytest.mark.parametrize('publication_time,publication_generation', [(1001, 5), (999, 7)])
def test_historical_time_and_generation_cannot_reverse_known_current_order(
        vga, publication_time, publication_generation):
    o = vga
    o.wire.receipt['virtual-ns'] = 900
    o.session.display_start()
    o.wire.receipt['virtual-ns'] = 1000
    o.wire.configuration['configuration-generation'] = 6
    o.session.vga_configuration_observe()
    o.wire.receipt['virtual-ns'] = 1002
    o.wire.configuration['configuration-generation'] = 8
    o.wire.publish()
    o.wire.display['published-ns'] = publication_time
    o.wire.published['virtual-ns'] = publication_time
    o.wire.published['configuration-generation'] = publication_generation
    with pytest.raises(DebuggerError, match='time order'):
        o.session.vga_configuration_observe()
    assert o.vm.closed


@pytest.mark.parametrize('change', [
    {'token': 'unowned'}, {'width': 0}, {'width': 8193}, {'updates': True},
    {'epoch': 2}, {'virtual-ns': 1001}, {'state': 'invalidated'},
])
def test_atomic_display_receipt_retains_existing_ownership_and_bounds(vga, change):
    o = vga
    publish(o)
    o.wire.mutate_configuration = lambda value: dict(value, display=dict(value['display'], **change))
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert o.vm.closed and caught.value.result['native']['display'].items() >= change.items()


@pytest.mark.parametrize('timeout', [None, True, False, 0, -1, 600001, 1.0, '1000', [], {}])
def test_invalid_timeout_refuses_before_deadline_creation_lock_and_io(vga, monkeypatch, timeout):
    o = vga
    class ForbiddenLock:
        def acquire(self, **kwargs):
            pytest.fail('Invalid timeout reached machine lock admission')
    def forbidden_deadline(*args, **kwargs):
        pytest.fail('Invalid timeout reached deadline creation')
    original_lock = o.vm.lock
    o.vm.lock = ForbiddenLock()
    monkeypatch.setattr('fdisbull.operation_budget.request_deadline', forbidden_deadline)
    try:
        with pytest.raises(ValueError):
            o.session.vga_configuration_observe(timeout_ms=timeout)
    finally:
        o.vm.lock = original_lock
    assert not o.wire.calls and not o.vm.closed and not configuration_events(o)


@pytest.mark.parametrize('args,kwargs', [((1000,), {}), ((), {'mode_id': 1}),
                                       ((), {'allow_references': True})])
def test_complete_signature_refuses_before_admission(vga, monkeypatch, args, kwargs):
    o = vga
    def forbidden_deadline(*args, **kwargs):
        pytest.fail('Invalid signature reached deadline creation')
    monkeypatch.setattr('fdisbull.operation_budget.request_deadline', forbidden_deadline)
    with pytest.raises(TypeError):
        o.session.vga_configuration_observe(*args, **kwargs)
    assert not o.wire.calls and not o.vm.closed


@pytest.mark.parametrize('missing', [VGA_CONFIGURATION_COMMANDS, DISPLAY_COMMANDS,
                                    RETRACE_COMMANDS, VIRTUAL_CLOCK_COMMANDS])
def test_missing_native_dependency_refuses_before_io_and_preserves_owner(vga, missing):
    o = vga
    o.vm.qmp_commands -= missing
    with pytest.raises(ValueError, match='extension'):
        o.session.vga_configuration_observe()
    assert not o.wire.calls and not o.vm.closed


def test_caller_transaction_and_absent_project_refuse_before_io(vga):
    o = vga
    with o.project.transaction(True):
        with pytest.raises(ValueError, match='transaction'):
            o.session.vga_configuration_observe()
    o.session.project = None
    try:
        with pytest.raises(ValueError, match='project'):
            o.session.vga_configuration_observe()
    finally:
        o.session.project = o.project
    assert not o.wire.calls and not o.vm.closed


def test_unselected_precise_profile_is_a_nonterminal_capability_refusal(vga):
    o = vga
    o.vm.machine_configuration['retrace_profile'] = machine_retrace_configuration('standard', 'virtual')
    o.vm.native_retrace_admission = None
    with pytest.raises(ValueError, match='precise'):
        o.session.vga_configuration_observe()
    assert not o.wire.calls and not o.vm.closed


@pytest.mark.parametrize('defect', ['profile-lost', 'clock-lost', 'cpu-changed', 'admission-missing'])
def test_loss_of_admitted_profile_or_owner_is_terminal_without_native_dispatch(vga, defect):
    o = vga
    if defect == 'profile-lost':
        o.vm.machine_configuration['retrace_profile'] = {'profile': 'standard'}
    elif defect == 'clock-lost':
        o.vm.machine_configuration['clock_profile'] = machine_clock_configuration('instruction', 1)
    elif defect == 'cpu-changed':
        o.vm.machine_configuration['cpus'] = True
    else:
        o.vm.native_retrace_admission = None
    with pytest.raises(DebuggerError):
        o.session.vga_configuration_observe()
    assert o.vm.closed and not o.wire.calls


@pytest.mark.parametrize('defect', ['pending-stop', 'running', 'armed-budget', 'fired-budget'])
def test_nonpassive_native_clock_refuses_before_configuration_query(vga, defect):
    o = vga
    if defect == 'pending-stop':
        o.wire.receipt['pending-stop'] = True
    elif defect == 'running':
        o.wire.receipt.update(running=True, status='running')
    else:
        o.wire.receipt.update({'budget-state': 'armed' if defect == 'armed-budget' else 'fired',
            'budget-token': 'outstanding', 'budget-start-ns': 900, 'budget-deadline-ns': 950})
        if defect == 'fired-budget':
            o.wire.receipt['budget-fired-ns'] = 950
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert o.vm.closed and not configuration_calls(o)
    assert caught.value.result['stage'] == 'before-clock'
    assert caught.value.result['native_received'] is False


def test_completed_native_refusal_closes_a_healthy_transport_without_retry(vga):
    o = vga
    o.wire.reject_configuration = True
    with pytest.raises(DebuggerError, match='authored native refusal') as caught:
        o.session.vga_configuration_observe()
    assert o.vm.closed and o.wire.socket_closed and configuration_calls(o) == [{}]
    assert caught.value.result['native_received'] is False
    assert caught.value.result['native'] is None and not configuration_events(o)


@pytest.mark.parametrize('mutation', [
    lambda value: dict(value, id=value['id'] + 1),
    lambda value: {'id': value['id']},
    lambda value: dict(value, error={'class': 'GenericError', 'desc': 'both outcomes'}),
    lambda value: [],
])
def test_uncertain_qmp_envelopes_close_without_consuming_a_later_reply(vga, mutation):
    o = vga
    o.wire.mutate_envelope = mutation
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    assert o.vm.closed and o.wire.socket_closed and configuration_calls(o) == [{}]
    assert caught.value.result['native_received'] is False and not configuration_events(o)


@pytest.mark.parametrize('stage', ['before', 'after'])
def test_native_clock_refusal_preserves_available_configuration_and_bracket(vga, stage):
    o = vga
    if stage == 'before':
        o.wire.refuse_command = 'query-replay'
    else:
        o.wire.after_configuration = lambda: setattr(o.wire, 'refuse_command', 'query-replay')
    with pytest.raises(DebuggerError, match='authored clock refusal') as caught:
        o.session.vga_configuration_observe()
    evidence = caught.value.result
    assert o.vm.closed and not configuration_events(o)
    assert evidence['stage'] == stage + '-clock'
    assert evidence['clocks']['after'] is None
    if stage == 'before':
        assert evidence['clocks']['before'] is None and evidence['native_received'] is False
        assert not configuration_calls(o)
    else:
        assert evidence['clocks']['before']['virtual_ns'] == 1000
        assert evidence['native_received'] is True and evidence['native'] == o.wire.last_configuration_reply


@pytest.mark.parametrize('field', ['virtual-ns', 'epoch'])
def test_clock_drift_never_persists_a_qualified_configuration(vga, field):
    o = vga
    def drift():
        o.wire.receipt[field] += 1
    o.wire.after_configuration = drift
    with pytest.raises(DebuggerError) as caught:
        o.session.vga_configuration_observe()
    evidence = caught.value.result
    assert o.vm.closed and not configuration_events(o) and evidence['native_received'] is True
    assert evidence['native'] == o.wire.last_configuration_reply
    if field == 'virtual-ns':
        assert evidence['clocks']['after']['virtual_ns'] == evidence['clocks']['before']['virtual_ns'] + 1


@pytest.mark.parametrize('kind', ['failure', 'late'])
def test_journal_failure_or_late_commit_keeps_complete_result_and_closes(vga, kind):
    o = vga
    original = o.session._event
    def persist(name, result):
        if name != 'machine-vga-configuration-observe':
            return original(name, result)
        if kind == 'failure':
            raise OSError('authored configuration journal failure')
        original(name, result)
        o.clock.now += .2
    o.session._event = persist
    with pytest.raises(OSError if kind == 'failure' else TimeoutError) as caught:
        o.session.vga_configuration_observe(timeout_ms=100)
    result = caught.value.result
    assert result['format'] == 'fdisbull-vga-configuration-1'
    assert result['native'] == o.wire.last_configuration_reply
    assert result['clocks']['before']['counter'] == result['clocks']['after']['counter']
    assert o.vm.closed and configuration_calls(o) == [{}]
    assert len(configuration_events(o)) == (1 if kind == 'late' else 0)


def test_existing_exception_result_is_not_overwritten(vga):
    o = vga
    failure = OSError('authored result-bearing persistence failure')
    retained = {'format': 'authored-error-evidence', 'reason': 'original evidence'}
    failure.result = retained
    def fail(name, value):
        raise failure
    o.session._event = fail
    with pytest.raises(OSError) as caught:
        o.session.vga_configuration_observe()
    assert caught.value.result is retained and o.vm.closed


def test_direct_observation_shrinks_one_deadline_through_all_native_reads(vga):
    o = vga
    o.wire.latency = .01
    o.session.vga_configuration_observe(timeout_ms=100)
    assert o.wire.budgets == pytest.approx([.10, .09, .08, .07, .06, .05, .04])
    assert o.clock.now == pytest.approx(100.07)
    assert o.vm.operation_deadline is o.qmp.operation_deadline is o.gdb.operation_deadline is None
    assert o.session._deadline is None and not o.vm.closed


def test_timeout_during_final_clock_closes_and_preserves_received_native_value(vga):
    o = vga
    o.wire.latency = .15
    with pytest.raises(TimeoutError) as caught:
        o.session.vga_configuration_observe()
    assert o.clock.now == pytest.approx(101.0)
    assert o.wire.budgets == pytest.approx([1.0, .85, .70, .55, .40, .25, .10])
    assert caught.value.result['native_received'] is True
    assert caught.value.result['native'] == o.wire.last_configuration_reply
    assert caught.value.result['clocks']['after'] is None
    assert o.vm.closed and o.wire.socket_closed and not configuration_events(o)


def test_incoming_deadlines_are_intersected_and_restored(vga):
    o = vga
    o.session._rpc_deadline, o.session._deadline = 100.6, 100.5
    o.vm.operation_deadline, o.qmp.operation_deadline, o.gdb.operation_deadline = 100.4, 100.3, 100.2
    o.session.vga_configuration_observe(timeout_ms=5000)
    assert o.wire.budgets and all(value == pytest.approx(.2) for value in o.wire.budgets)
    assert o.session._rpc_deadline == 100.6 and o.session._deadline == 100.5
    assert o.vm.operation_deadline == 100.4 and o.qmp.operation_deadline == 100.3
    assert o.gdb.operation_deadline == 100.2 and not o.vm.closed


def test_preexpired_deadline_never_attempts_lock_or_io(vga):
    o = vga
    class ForbiddenLock:
        def acquire(self, **kwargs):
            pytest.fail('Expired operation reached lock admission')
    original_lock = o.vm.lock
    o.vm.lock = ForbiddenLock()
    o.session._rpc_deadline = o.clock.now
    try:
        with pytest.raises(TimeoutError):
            o.session.vga_configuration_observe()
    finally:
        o.vm.lock = original_lock
        o.session._rpc_deadline = None
    assert not o.wire.calls and not o.vm.closed


def test_lock_wait_consumes_only_remaining_allowance_without_native_dispatch(vga):
    o = vga
    waits = []
    class BusyLock:
        def acquire(self, *, timeout):
            waits.append(timeout)
            o.clock.now += timeout
            return False
    original_lock = o.vm.lock
    o.vm.lock = BusyLock()
    try:
        with pytest.raises(TimeoutError, match='busy'):
            o.session.vga_configuration_observe(timeout_ms=50)
    finally:
        o.vm.lock = original_lock
    assert waits == pytest.approx([.05]) and o.clock.now == pytest.approx(100.05)
    assert not o.wire.calls and not o.vm.closed


def test_outer_wrapper_expiry_after_last_internal_check_still_closes(vga, monkeypatch):
    from fdisbull import qemu_vga_configuration
    o = vga
    original = qemu_vga_configuration._remaining
    def yield_after_check(owner, *, label):
        original(owner, label=label)
        if configuration_events(o):
            # Simulate host work after the method's final successful check.
            o.clock.now += .2
    monkeypatch.setattr(qemu_vga_configuration, '_remaining', yield_after_check)
    with pytest.raises(TimeoutError) as caught:
        o.session.vga_configuration_observe(timeout_ms=100)
    assert caught.value.result['format'] == 'fdisbull-vga-configuration-1'
    assert o.vm.closed and len(configuration_events(o)) == 1 and configuration_calls(o) == [{}]
