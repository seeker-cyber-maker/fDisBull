"""Authored stopped-boundary peer; no native guest or Keen qualification."""
import base64
from copy import deepcopy
import hashlib
import importlib.util
import io
from pathlib import Path
import struct

from PIL import Image
import pytest


SPEC = importlib.util.spec_from_file_location(
    'keen_loop', Path(__file__).resolve().parents[1] / 'scripts/experiments/keen_loop.py')
loop = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loop)

SOURCE = hashlib.sha256(b'authored DOS fixture').hexdigest()
PROFILE = {'source_sha256': SOURCE, 'address': 0x20000, 'length': 4,
           'qualification': 'Authored peer counter; no game address claim'}
CAPS = {'execution': {'bounded_frame_step': {'schema': 'dotbox-bounded-frame-step-1',
         'max_frames': 10000, 'max_guest_ms': 30000}},
        'input': {'cooperative_control': 'dotbox-input-control-1'},
        'timing': {'fast_forward': True}, 'limits': {'max_memory_read_bytes': 65536}}
_png = io.BytesIO()
Image.new('RGB', (2, 1), (23, 45, 67)).save(_png, format='PNG')
PNG = _png.getvalue()


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class Peer:
    def __init__(self, clock):
        self.clock = clock
        self.binding = {'run_id': 'run-1', 'session_id': 'ses-1', 'generation': 0,
                        'timeline': 'timeline-1', 'state_revision': 1}
        self.metadata = {'source_sha256': SOURCE}
        self.calls = []
        self.revision, self.ticks, self.frame = 1, 1000, 70
        self.generation, self.fast = 0, False
        self.keys = set()
        self.stop = {'kind': 'pause'}
        self.scenario = None
        self.step_count = 0
        self.delay = 0.0001
        self.screenshot_changes = {}

    def __call__(self, method, params, *, timeout_ms):
        self.calls.append((method, deepcopy(params), timeout_ms, self.clock()))
        self.clock.now += self.delay
        if self.scenario == ('uncertain', method):
            raise TimeoutError('Acknowledgement lost after dispatch')
        if method == 'session.status':
            result = {'state': 'stopped', 'last_stop': deepcopy(self.stop)}
        elif method == 'input.control':
            result = {'owner': 'agent', 'generation': self.generation}
        elif method == 'input.keyboard.state':
            result = {'keyboard': self.keyboard()}
        elif method == 'execution.timing':
            if 'fast_forward' in params and self.fast != params['fast_forward']:
                self.fast = params['fast_forward']
                self.revision += 1
            result = {'fast_forward': self.fast, 'guest_ticks': self.ticks}
        elif method == 'input.keyboard.frame_edges':
            assert params['control_generation'] == self.generation
            for edge in params['edges']:
                if edge['pressed']:
                    assert edge['key'] not in self.keys
                    self.keys.add(edge['key'])
                else:
                    self.keys.remove(edge['key'])
            self.revision += 1
            result = {'accepted': True, 'delivery': 'hardware_edges_at_paused_boundary',
                      'keyboard': self.keyboard()}
        elif method == 'frame.step':
            self.step_count += 1
            before = self.ticks
            elapsed = min(params['max_guest_ms'], params['max_frames'] * 14)
            frames = min(params['max_frames'], elapsed // 14)
            self.ticks = (self.ticks + elapsed) % (1 << 32)
            self.frame += frames
            self.revision += 1
            frame_limit = frames == params['max_frames']
            cause = 'frame_limit' if frame_limit else 'guest_time_limit'
            self.stop = {'kind': 'frame' if frame_limit else 'budget'}
            if self.scenario in ('breakpoint', 'own_hook'):
                cause = 'breakpoint'
                self.stop = {'kind': 'breakpoint', 'breakpoint_id': 'qualified' if self.scenario == 'own_hook' else 'foreign'}
            if self.scenario == 'frame_named_budget':
                self.stop = {'kind': 'budget'}
            result = {'completed': frame_limit and cause != 'breakpoint', 'stop_reason': deepcopy(self.stop),
                      'boundary': 'bounded_execution_then_safe_fetch',
                      'frame_available': True, 'frame_id': self.frame,
                      'mode_id': 1, 'guest_ticks': self.ticks,
                      'registers': {'session_id': 'ses-1', 'state_revision': self.revision},
                      'bounded': {'max_frames': params['max_frames'],
                                  'max_guest_ms': params['max_guest_ms'],
                                  'frames_completed': frames, 'guest_elapsed_ms': elapsed,
                                  'guest_ticks_before': before, 'guest_ticks_after': self.ticks,
                                  'guest_tick_bits': 32, 'stop_cause': cause}}
            if self.scenario == 'bad_accounting':
                result['bounded']['guest_elapsed_ms'] += 1
            if self.scenario == 'rebound':
                self.binding['timeline'] = 'timeline-2'
        elif method == 'memory.read':
            assert params['address'] == {'space': 'linear', 'offset': '0x00020000'}
            assert params['length'] == 4
            raw = struct.pack('<I', self.step_count)
            result = {'data_base64': base64.b64encode(raw).decode(), 'byte_count': 4,
                      'address': params['address'], 'sha256': hashlib.sha256(raw).hexdigest()}
            if self.scenario == 'bad_read':
                result['data_base64'] = 'not base64'
        elif method == 'video.screenshot':
            assert params['encoding'] == 'png'
            result = {'png_base64': base64.b64encode(PNG).decode(), 'format': 'png',
                      'width': 2, 'height': 1, 'sha256': hashlib.sha256(PNG).hexdigest(),
                      'frame_id': self.frame - 1, 'mode_id': 1, 'captured_ticks': self.ticks - 1,
                      'source': 'last_completed_guest_frame', **self.screenshot_changes}
        else:
            raise AssertionError('Unexpected RPC: ' + method)
        return {'session_id': 'ses-1', 'state_revision': self.revision, **result}

    def keyboard(self):
        return {'frame_keys': sorted(self.keys), 'pending_events': 0, 'owned_keys': 0,
                'frame_edge_capacity': 32, 'queued_guest_ms': 0}


def make(policy=None, decoder=None, **options):
    clock = Clock()
    peer = Peer(clock)
    controller = loop.KeenLoop(peer, profile=deepcopy(PROFILE), binding=peer.binding,
        capabilities=deepcopy(CAPS), decoder=decoder or (lambda raw: {'counter': struct.unpack('<I', raw)[0]}),
        policy=policy or loop.neutral_policy, clock=clock, sleep=clock.sleep, **options)
    return peer, controller, clock


def run(controller, **options):
    return controller.run(max_cycles=3, total_guest_ms=100, host_timeout_ms=1000, **options)


def test_neutral_loop_observes_without_input_and_reports_latency():
    peer, controller, _ = make()
    result = run(controller)
    assert result['outcome'] == 'cycle_limit'
    assert [row['state']['counter'] for row in result['samples']] == [1, 2, 3]
    assert result['metrics']['feedback_guest_ms'] == 42
    assert result['metrics']['cycle_latency_ms']['max'] > 0
    assert result['metrics']['guest_host_ratio'] > 0
    assert not any(name == 'input.keyboard.frame_edges' for name, *_ in peer.calls)
    assert result['cleanup']['status'] == 'neutral'
    assert result['observation_valid'] is False
    with pytest.raises(ValueError, match='one-shot'):
        run(controller)


def test_chord_only_changes_edges_then_releases_and_drains():
    peer, controller, _ = make(policy=lambda observation: {'right', 'ctrl'})
    result = run(controller)
    edges = [params['edges'] for name, params, *_ in peer.calls if name == 'input.keyboard.frame_edges']
    assert edges == [[{'key': 'ctrl', 'pressed': True}, {'key': 'right', 'pressed': True}],
                     [{'key': 'ctrl', 'pressed': False}, {'key': 'right', 'pressed': False}]]
    assert result['cleanup']['status'] == 'released_and_drained'
    assert result['cleanup']['game_consumption_verified'] is False
    assert result['metrics']['total_guest_ms'] <= 100
    assert not peer.keys
    assert peer.step_count == 4


@pytest.mark.parametrize('method', ['frame.step', 'input.keyboard.frame_edges', 'memory.read'])
def test_transport_uncertainty_never_issues_another_rpc(method):
    peer, controller, _ = make(policy=lambda observation: {'right'})
    peer.scenario = ('uncertain', method)
    result = run(controller)
    assert result['outcome'] == 'transport_uncertain'
    assert peer.calls[-1][0] == method
    assert result['cleanup']['status'] == 'preserved'
    assert result['metrics']['guest_accounting_complete'] is (method != 'frame.step')


@pytest.mark.parametrize('scenario', ['breakpoint', 'bad_accounting', 'rebound'])
def test_unexpected_boundary_never_reads_releases_or_resumes(scenario):
    peer, controller, _ = make(policy=lambda observation: {'right'})
    peer.scenario = scenario
    result = run(controller)
    assert result['outcome'] in ('unexpected_stop', 'invalidated')
    assert peer.calls[-1][0] == 'frame.step'
    assert result['cleanup']['status'] == 'preserved'


def test_generation_change_after_policy_declines_without_input():
    peer, controller, _ = make()
    def policy(observation):
        peer.generation += 1
        return {'right'}
    controller.policy = policy
    result = run(controller)
    assert result['outcome'] == 'invalidated'
    assert not any(name in ('frame.step', 'input.keyboard.frame_edges') for name, *_ in peer.calls)


def test_explicit_invalidation_in_policy_declines_without_input():
    peer, controller, _ = make()
    def policy(observation):
        controller.invalidate('External rewind')
        return {'right'}
    controller.policy = policy
    result = run(controller)
    assert result['outcome'] == 'invalidated'
    assert not any(name in ('frame.step', 'input.keyboard.frame_edges') for name, *_ in peer.calls)


def test_source_mismatch_refuses_before_rpc():
    peer, controller, _ = make()
    peer.metadata['source_sha256'] = '0' * 64
    result = run(controller)
    assert result['outcome'] == 'invalidated'
    assert peer.calls == []


def test_stale_initial_revision_refuses_before_input():
    peer, controller, _ = make()
    peer.revision += 1
    result = run(controller)
    assert result['outcome'] == 'invalidated'
    assert [name for name, *_ in peer.calls] == ['session.status']


def test_fast_forward_is_explicit_and_restored_on_safe_completion():
    peer, controller, _ = make()
    result = run(controller, fast_forward=True)
    timing = [params for name, params, *_ in peer.calls if name == 'execution.timing']
    assert [row['fast_forward'] for row in timing if 'fast_forward' in row] == [True, False]
    assert peer.fast is False
    assert result['timing']['selected_fast_forward'] is True


def test_pacing_uses_one_schedule_and_reports_misses():
    peer, controller, clock = make()
    result = run(controller, pace_hz=20)
    assert clock.sleeps
    assert result['metrics']['missed_paced_deadlines'] == 0
    peer, controller, clock = make()
    peer.delay = 0.01
    result = run(controller, pace_hz=100)
    assert result['metrics']['missed_paced_deadlines'] > 0


def test_clock_wrap_is_validated_with_native_width():
    peer, controller, _ = make()
    peer.ticks = (1 << 32) - 5
    result = run(controller)
    assert result['outcome'] == 'cycle_limit'
    assert result['metrics']['feedback_guest_ms'] == 42


def test_bad_memory_payload_halts_without_more_native_calls():
    peer, controller, _ = make()
    peer.scenario = 'bad_read'
    result = run(controller)
    assert result['outcome'] == 'unexpected_stop'
    assert peer.calls[-1][0] == 'memory.read'


@pytest.mark.parametrize('options', [{'max_frames': 3}, {'max_guest_ms': 41}, {'pace_hz': 0},
                                    {'fast_forward': 1}, {'max_cycles': True}])
def test_bad_limits_refuse_before_rpc(options):
    peer, controller, _ = make()
    kwargs = {'max_cycles': 3, 'total_guest_ms': 100, 'host_timeout_ms': 1000, **options}
    with pytest.raises(ValueError):
        controller.run(**kwargs)
    assert peer.calls == []


def test_frame_limit_can_have_outer_budget_stop_kind():
    peer, controller, _ = make()
    peer.scenario = 'frame_named_budget'
    result = run(controller)
    assert result['outcome'] == 'cycle_limit'
    assert result['metrics']['cycles'] == 3


def hook_controller(**options):
    peer, _, clock = make()
    profile = {**PROFILE, 'boundary': {'breakpoint_id': 'qualified', 'max_frames': 8,
                                     'max_guest_ms': 120}}
    peer.stop = {'kind': 'breakpoint', 'breakpoint_id': 'qualified'}
    controller = loop.KeenLoop(peer, profile=profile, binding=peer.binding,
                              capabilities=CAPS, decoder=lambda raw: {'counter': struct.unpack('<I', raw)[0]},
                              clock=clock, sleep=clock.sleep, **options)
    return peer, controller, clock


def test_qualified_hook_is_the_only_coherent_boundary():
    peer, controller, _ = hook_controller()
    peer.scenario = 'own_hook'
    result = controller.run(max_cycles=3, total_guest_ms=500, host_timeout_ms=1000,
                            max_frames=8, max_guest_ms=120)
    assert result['outcome'] == 'cycle_limit'
    assert all(row['coherence'] == 'qualified_hook' for row in result['samples'])


@pytest.mark.parametrize('scenario, expected', [(None, 'coherence_miss'), ('breakpoint', 'unexpected_stop')])
def test_hook_budget_miss_or_foreign_hook_preserves_stop(scenario, expected):
    peer, controller, _ = hook_controller()
    peer.scenario = scenario
    result = run(controller)
    assert result['outcome'] == expected
    assert peer.calls[-1][0] == 'frame.step'
    assert result['samples'] == []
    assert result['metrics']['total_guest_ms'] == 14
    assert result['metrics']['guest_accounting_complete'] is True


def test_policy_completion_releases_owned_keys_and_drains():
    def policy(observation):
        return {'right'} if observation['sequence'] < 1 else None
    peer, controller, _ = make(policy=policy)
    result = run(controller)
    assert result['outcome'] == 'policy_stop'
    assert len(result['samples']) == 1
    assert result['cleanup']['status'] == 'released_and_drained'
    assert peer.keys == set()


def test_decoder_failure_at_known_stop_cleans_up_without_replaying_action():
    def decoder(raw):
        value = struct.unpack('<I', raw)[0]
        if value:
            raise ValueError('State does not satisfy the qualified schema')
        return {'counter': value}
    peer, controller, _ = make(policy=lambda observation: {'right'}, decoder=decoder)
    result = run(controller)
    assert result['outcome'] == 'callback_error'
    assert result['cleanup']['status'] == 'released_and_drained'
    assert peer.step_count == 2  # One attempted action plus the explicit release drain.


def test_host_budget_has_one_deadline_with_reserved_cleanup():
    peer, controller, clock = make(policy=lambda observation: {'right'})
    peer.delay = .01
    result = controller.run(max_cycles=100, total_guest_ms=10000, host_timeout_ms=500)
    assert result['outcome'] == 'host_budget'
    assert result['cleanup']['status'] == 'released_and_drained'
    assert not peer.keys
    assert clock() <= .5
    assert all(start + timeout / 1000 <= .500001 for _, _, timeout, start in peer.calls)


def test_guest_budget_includes_release_drain():
    peer, controller, _ = make(policy=lambda observation: {'right'})
    result = controller.run(max_cycles=100, total_guest_ms=65, host_timeout_ms=1000)
    assert result['outcome'] == 'guest_limit'
    assert result['metrics']['feedback_guest_ms'] == 45
    assert result['metrics']['total_guest_ms'] <= 65
    assert result['cleanup']['status'] == 'released_and_drained'


def test_coalesced_profile_accepts_native_maximum_and_rejects_overflow():
    peer, _, clock = make()
    for length in (30710, 65536):
        loop.KeenLoop(peer, profile={**PROFILE, 'length': length}, binding=peer.binding,
                      capabilities=CAPS, decoder=lambda raw: {}, clock=clock, sleep=clock.sleep)
    with pytest.raises(ValueError, match='bounded region length'):
        loop.KeenLoop(peer, profile={**PROFILE, 'length': 65537}, binding=peer.binding,
                      capabilities=CAPS, decoder=lambda raw: {})
    assert peer.calls == []


def test_zero_progress_hook_is_not_counted_as_a_completed_iteration():
    peer, controller, _ = hook_controller()
    peer.scenario = 'own_hook'
    original = controller.target
    def no_progress(method, params, *, timeout_ms):
        before, frame = peer.ticks, peer.frame
        result = original(method, params, timeout_ms=timeout_ms)
        if method == 'frame.step':
            peer.ticks, peer.frame = before, frame
            result['guest_ticks'], result['frame_id'] = before, frame
            result['bounded'].update(frames_completed=0, guest_elapsed_ms=0,
                                     guest_ticks_after=before)
        return result
    controller.target = no_progress
    result = run(controller)
    assert result['outcome'] == 'unexpected_stop'
    assert result['samples'] == []
    assert result['metrics']['total_guest_ms'] == 0
    assert peer.calls[-1][0] == 'frame.step'


def test_presentation_is_disabled_by_default_without_screenshot_calls():
    peer, controller, _ = make()
    result = run(controller)
    assert not any(method == 'video.screenshot' for method, *_ in peer.calls)
    assert result['presentation']['enabled'] is False
    assert result['presentation']['attempted'] == result['presentation']['published'] == 0
    assert result['presentation']['total_ms'] == 0


@pytest.mark.parametrize('frame_every, sequences', [(1, list(range(10))), (4, [0, 4, 8])])
def test_presentation_cadence_preserves_exact_pixels_and_distinct_frame_identity(frame_every, sequences):
    delivered = []
    def sink(png_bytes, metadata):
        delivered.append((png_bytes, deepcopy(metadata)))
        metadata.clear()  # A sink cannot mutate the retained receipt or state sample.
    peer, controller, _ = hook_controller(frame_sink=sink, frame_every=frame_every)
    peer.scenario = 'own_hook'
    result = controller.run(max_cycles=9, total_guest_ms=500, host_timeout_ms=1000)
    assert result['outcome'] == 'cycle_limit'
    assert [metadata['state_observation']['sequence'] for _, metadata in delivered] == sequences
    assert all(png == PNG and metadata['width'] == 2 and metadata['height'] == 1
               for png, metadata in delivered)
    assert all(metadata['phase_synchronized'] is False
               and metadata['captured_ticks'] != metadata['state_observation']['guest_ticks']
               for _, metadata in delivered)
    assert [sample['state']['counter'] for sample in result['samples']] == list(range(1, 10))
    assert result['presentation']['published'] == len(sequences)
    assert result['presentation']['captured'] == len(sequences)
    assert [event['sequence'] for event in result['presentation']['events']] == sequences
    assert all(event['frame']['sha256'] == hashlib.sha256(PNG).hexdigest()
               for event in result['presentation']['events'])
    assert sum(method == 'video.screenshot' for method, *_ in peer.calls) == len(sequences)
    assert peer.step_count == 9


@pytest.mark.parametrize('changes', [
    {'png_base64': 'not base64'}, {'sha256': '0' * 64}, {'width': 3},
    {'png_base64': base64.b64encode(b'not png').decode(), 'sha256': hashlib.sha256(b'not png').hexdigest()},
    {'frame_id': True}, {'mode_id': -1}, {'captured_ticks': '1000'},
    {'source': 'current_game_state'}, {'session_id': 'different'}, {'state_revision': 999},
])
def test_invalid_presentation_receipt_preserves_without_release_or_resume(changes):
    def policy(observation):
        peer.screenshot_changes = changes
        return {'right'}
    peer, controller, _ = hook_controller(frame_sink=lambda *_: None, frame_every=1, policy=policy)
    peer.scenario = 'own_hook'
    result = run(controller)
    assert result['outcome'] in ('unexpected_stop', 'invalidated')
    assert result['cleanup']['status'] == 'preserved'
    assert peer.calls[-1][0] == 'video.screenshot'
    assert peer.keys == {'right'}
    assert result['presentation']['published'] == 1
    assert result['presentation']['errors'] == 1
    assert len(result['samples']) == 1  # The coherent update preceded the display failure.


def test_screenshot_transport_uncertainty_never_issues_another_rpc():
    def policy(observation):
        peer.scenario = ('uncertain', 'video.screenshot')
        return {'right'}
    peer, controller, _ = make(frame_sink=lambda *_: None, frame_every=1, policy=policy)
    result = run(controller)
    assert result['outcome'] == 'transport_uncertain'
    assert result['cleanup']['status'] == 'preserved'
    assert peer.calls[-1][0] == 'video.screenshot'
    assert result['metrics']['guest_accounting_complete'] is True
    assert result['presentation']['events'][-1]['error']['outcome'] == 'transport_uncertain'


def test_interrupted_sink_releases_only_after_fresh_stopped_owner_fence():
    def sink(png_bytes, metadata):
        if metadata['state_observation']['sequence']:
            clock.now += .007
            raise InterruptedError('Owner stop request')
    peer, controller, clock = make(frame_sink=sink, frame_every=1, policy=lambda _: {'right'})
    result = run(controller)
    assert result['outcome'] == 'callback_error'
    assert result['cleanup']['status'] == 'released_and_drained'
    assert not peer.keys
    assert peer.step_count == 2
    last_capture = max(i for i, (method, *_) in enumerate(peer.calls) if method == 'video.screenshot')
    assert [method for method, *_ in peer.calls[last_capture + 1:]] == [
        'session.status', 'input.control', 'input.keyboard.frame_edges', 'frame.step', 'input.keyboard.state']
    assert result['presentation']['errors'] == 1
    assert result['presentation']['sink_ms'] == pytest.approx(7)
    assert result['presentation']['events'][-1]['error']['type'] == 'InterruptedError'


def test_sink_failure_with_changed_owner_refuses_cleanup_input():
    def sink(png_bytes, metadata):
        if metadata['state_observation']['sequence']:
            peer.generation += 1
            raise InterruptedError('Owner changed')
    peer, controller, _ = make(frame_sink=sink, frame_every=1, policy=lambda _: {'right'})
    result = run(controller)
    assert result['outcome'] == 'invalidated'
    assert result['cleanup']['status'] == 'incomplete'
    assert peer.calls[-1][0] == 'input.control'
    assert peer.keys == {'right'}


def test_presentation_callback_cost_is_in_cycle_host_and_pacing_metrics():
    def sink(png_bytes, metadata):
        clock.now += .04
    peer, controller, clock = make(frame_sink=sink, frame_every=1)
    result = run(controller, pace_hz=35)
    assert result['metrics']['cycle_latency_ms']['p50'] == pytest.approx(40.5)
    assert result['metrics']['missed_paced_deadlines'] == 3
    assert result['presentation']['sink_ms'] == pytest.approx(160)
    assert result['presentation']['rpc_ms'] == pytest.approx(.4)
    assert result['presentation']['total_ms'] == pytest.approx(160.4)
    assert result['metrics']['host_ms'] >= result['presentation']['total_ms']
    assert [row['rpc_count'] for row in result['samples']] == [5, 5, 5]


def test_coherence_miss_does_not_publish_an_unqualified_update():
    peer, controller, _ = hook_controller(frame_sink=lambda *_: None, frame_every=1)
    result = run(controller)
    assert result['outcome'] == 'coherence_miss'
    assert result['presentation']['published'] == 1
    assert [event['sequence'] for event in result['presentation']['events']] == [0]


@pytest.mark.parametrize('kind', ['coroutine', 'generator', 'async_generator'])
def test_deferred_sink_is_not_reported_as_successful_delivery(kind):
    async def asynchronous_sink(*args):
        pass
    def generator_sink(*args):
        yield None
    async def asynchronous_generator_sink(*args):
        yield None
    sink = {'coroutine': asynchronous_sink, 'generator': generator_sink,
            'async_generator': asynchronous_generator_sink}[kind]
    with pytest.raises(TypeError, match='synchronous'):
        make(frame_sink=sink)
    peer, controller, _ = make(frame_sink=lambda *args: sink(*args))
    result = run(controller)
    assert result['outcome'] == 'callback_error'
    assert result['cleanup']['status'] == 'neutral'
    assert result['presentation']['captured'] == 1
    assert result['presentation']['published'] == 0


def test_sink_overrun_is_measured_without_claiming_a_hard_callback_deadline():
    def sink(*args):
        clock.now += 1.1
    peer, controller, clock = make(frame_sink=sink)
    result = run(controller)
    assert result['outcome'] == 'host_budget'
    assert result['metrics']['host_ms'] > 1000
    assert result['presentation']['sink_ms'] == pytest.approx(1100)
    assert result['samples'] == []
    assert not any(method in ('input.keyboard.frame_edges', 'frame.step') for method, *_ in peer.calls)


@pytest.mark.parametrize('options', [{'frame_sink': False}, {'frame_every': 0}, {'frame_every': -1},
                                    {'frame_every': True}, {'frame_every': 1.5}])
def test_invalid_presentation_options_refuse_before_rpc(options):
    with pytest.raises((TypeError, ValueError)):
        make(**options)
