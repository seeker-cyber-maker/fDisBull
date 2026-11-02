"""Live, bounded full-state frame history; durable Anchor Stones stay separate."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from functools import wraps
import base64
import hashlib
import io
import json
import threading
import time
import uuid

from .debug_rewind import READ_ONLY, _bounded
from .operation_budget import rpc_budget
from . import frame_state_codec as state_codec


FORMAT = 'fdisbull-frame-timeline-1'
_SETUP_LOCK = threading.Lock()
_READ_ONLY = READ_ONLY | {'input.keyboard.state', 'input.mouse.state'}


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _require_released_mouse(mouse):
    # Native saves retain hardware button bits, but have no agent ownership
    # sidecar for releasing them after a load. Admit only released input.
    if not isinstance(mouse, dict) or any(mouse.get(key) for key in
            ('buttons', 'owned_buttons', 'pending_release_buttons', 'release_pending')):
        raise ValueError('Native checkpoints require released mouse buttons and no pending mouse input')


def _receipt(result):
    """Keep durable operation evidence compact; the full point list stays live."""
    result = dict(result)
    if isinstance(result.get('timeline'), dict):
        result['timeline'] = {k: v for k, v in result['timeline'].items() if k not in ('points', 'experiment')}
    return result


def _reference(value, allowed):
    return allowed and isinstance(value, str) and value.startswith('$')


def _address(value):
    if type(value) is int and 0 <= value < 0xa0000:
        return value
    if isinstance(value, str) and value.startswith('0x'):
        try:
            number = int(value, 16)
        except ValueError:
            pass
        else:
            if 0 <= number < 0xa0000:
                return number
    raise ValueError('Timeline preservation requires explicit conventional runtime linear RAM addresses')


def validate_edges(edges, *, allow_references=False):
    from .keyboard_input import KEYS
    if _reference(edges, allow_references):
        return
    if not isinstance(edges, list) or len(edges) > 32:
        raise ValueError('Frame input requires at most 32 explicit key edges')
    seen = set()
    for edge in edges:
        if _reference(edge, allow_references):
            continue
        if not isinstance(edge, dict) or set(edge) != {'key', 'pressed'}:
            raise ValueError('A frame edge requires key and pressed')
        key = edge['key']
        if not _reference(key, allow_references):
            if not isinstance(key, str) or key not in KEYS:
                raise ValueError('Unknown frame input key')
            key = 'escape' if key == 'esc' else key
            if key in seen:
                raise ValueError('Duplicate frame input key')
            seen.add(key)
        if not _reference(edge['pressed'], allow_references) and type(edge['pressed']) is not bool:
            raise ValueError('Frame edge pressed must be boolean')


def validate_schedule(inputs, frames, *, allow_references=False):
    if inputs is None or _reference(inputs, allow_references):
        return
    if not isinstance(inputs, list) or len(inputs) > 128:
        raise ValueError('Frame schedule requires at most 128 entries')
    seen = set()
    for item in inputs:
        if _reference(item, allow_references):
            continue
        if not isinstance(item, dict) or set(item) != {'frame', 'edges'}:
            raise ValueError('Frame schedule entry requires frame and edges')
        frame = item['frame']
        if not _reference(frame, allow_references):
            _bounded(frame, 'scheduled frame', 0, 127)
            if type(frames) is int and frame >= frames:
                raise ValueError('Scheduled frame exceeds requested advancement')
            if frame in seen:
                raise ValueError('Duplicate scheduled frame')
            seen.add(frame)
        validate_edges(item['edges'], allow_references=allow_references)


def validate_timeline_policy(policy, *, allow_references=False):
    if policy is None or _reference(policy, allow_references):
        return
    if not isinstance(policy, dict) or set(policy) - {'name', 'preserve_memory', 'allow_partial_resume'}:
        raise ValueError('Timeline policy supports name, preserve_memory and allow_partial_resume')
    name = policy.get('name', 'preserve-current-ram')
    if not _reference(name, allow_references) and (not isinstance(name, str) or not 1 <= len(name) <= 128):
        raise ValueError('Timeline policy name must contain 1..128 characters')
    resume = policy.get('allow_partial_resume', False)
    if not _reference(resume, allow_references) and type(resume) is not bool:
        raise ValueError('allow_partial_resume must be boolean')
    ranges = policy.get('preserve_memory', [])
    if _reference(ranges, allow_references):
        return
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 64:
        raise ValueError('Timeline preservation requires 1..64 RAM ranges')
    total, intervals = 0, []
    for item in ranges:
        if _reference(item, allow_references):
            continue
        if not isinstance(item, dict) or set(item) != {'address', 'length'}:
            raise ValueError('Preserved runtime RAM requires address and length')
        length = item['length']
        if not _reference(length, allow_references):
            _bounded(length, 'preserved length', 1, 65536)
            total += length
        address = item['address']
        if not _reference(address, allow_references):
            address = _address(address)
            if type(length) is int:
                end = address + length
                if end > 0xa0000 or any(address < hi and low < end for low, hi in intervals):
                    raise ValueError('Preserved RAM ranges overlap or leave conventional RAM')
                intervals.append((address, end))
    if total > 65536:
        raise ValueError('Preserved RAM exceeds 64 KiB')


def validate_storage(storage_mode='full', keyframe_interval=8, *, allow_references=False):
    if not _reference(storage_mode, allow_references) and storage_mode not in ('full', 'delta'):
        raise ValueError('Timeline storage_mode must be full or delta')
    if not _reference(keyframe_interval, allow_references):
        _bounded(keyframe_interval, 'keyframe_interval', 1, 128)


def timeline_locked(function):
    @wraps(function)
    def locked(self, *args, **kwargs):
        # Some tests/backends borrow individual DebugSession methods.
        with FrameTimelineSessionMixin._timeline_gate(self):
            return function(self, *args, **kwargs)
    return locked


class FrameTimelineSessionMixin:
    def _timeline_gate(self):
        # Borrowed DOS helpers also serve Wine/QEMU. Reuse that backend's
        # stable reentrant lock rather than introducing a second lock order.
        stable = getattr(self, '_delta_lock', None)
        if stable is not None:
            return stable
        rpc = getattr(self, 'rpc', None)
        if getattr(rpc, 'vm', None) is not None:
            return rpc.lock
        backend = getattr(self, 'backend_name', None) or getattr(self, 'metadata', {}).get('backend')
        if rpc is None and backend in ('wine-qemu', 'ida-wine-qemu', 'dosbox-qemu'):
            return nullcontext()
        with _SETUP_LOCK:
            if getattr(self, '_timeline_lock', None) is None:
                self._timeline_lock = threading.RLock()
        return self._timeline_lock

    @contextmanager
    def _timeline_owned(self):
        self._timeline_depth = getattr(self, '_timeline_depth', 0) + 1
        try:
            yield
        finally:
            self._timeline_depth -= 1

    def _timeline_before_call(self, method, params=None):
        if getattr(self, '_timeline_depth', 0) or getattr(self, '_timeline_load_depth', 0):
            return
        history = getattr(self, '_frame_timeline', None)
        if history is not None and history['mixed_frozen'] and method not in {
                'session.status', 'state.get_registers', 'memory.read', 'input.keyboard.state',
                'input.mouse.state', 'agent.capabilities', 'session.close', 'session.stop'}:
            raise ValueError('Timeline mixed state is frozen; restore a complete point before execution or capture')
        if method not in _READ_ONLY:
            self._timeline_invalidate('unrecorded RPC: ' + str(method))

    def _timeline_invalidate(self, reason):
        history = getattr(self, '_frame_timeline', None)
        if history is not None and history['valid']:
            history['valid'] = False
            history['invalid_reason'] = reason
            history['current_dirty'] = True
            self._event('timeline-invalidated', dict(timeline=history['id'], reason=reason))

    @contextmanager
    def _timeline_full_load(self):
        if not getattr(self, '_timeline_depth', 0):
            FrameTimelineSessionMixin._timeline_invalidate(self, 'full native restore attempted')
        self._timeline_load_depth = getattr(self, '_timeline_load_depth', 0) + 1
        try:
            yield
        finally:
            self._timeline_load_depth -= 1

    def _timeline_loaded(self):
        history = getattr(self, '_frame_timeline', None)
        if history is not None:
            history['mixed_frozen'] = False

    def _timeline_fail(self, reason, *, close=False):
        try:
            self._timeline_invalidate(reason)
        except BaseException:
            pass  # Invalidation sets safety flags before attempting its receipt.
        finally:
            if close:
                try:
                    self.close()
                except BaseException:
                    pass

    def _timeline_native(self):
        if self.closed or not self.rpc.capabilities.get('frame_timeline'):
            raise ValueError('Frame timeline requires a live compatible native frame_timeline backend')

    def _timeline_identity(self):
        return dict(run=self.run_id, version=self.version['id'], **{
            key: self.metadata.get(key) for key in ('backend', 'source_sha256', 'version_sha256',
                'emulator_sha256', 'runtime_profile', 'runtime_load_segment', 'game_dir')})

    def _timeline_require(self):
        self._timeline_native()
        history = getattr(self, '_frame_timeline', None)
        if history is None or not history['valid']:
            raise ValueError('No valid live frame timeline; explicitly start a new timeline')
        if history['identity'] != self._timeline_identity() or history['manifest'] != self._disk_manifest():
            self._timeline_invalidate('session or mounted-file identity changed')
            raise ValueError('Frame timeline session or mounted-file identity changed')
        return history

    def _timeline_admit(self):
        if self.call('session.status').get('state') != 'stopped':
            raise ValueError('Frame timeline requires a stopped target')
        layers = self._layer_state()
        if layers.get('active') or layers.get('ram_applied') or getattr(self, '_hooks', {}):
            raise ValueError('Frame timeline requires no active layers or hooks')
        if getattr(self, '_spatial_guard_active', False) or getattr(self, '_spatial_guard_failed', False):
            raise ValueError('Frame timeline cannot use a temporary or failed spatial guard')
        if (getattr(self, '_cpu_delta_history', None) or {}).get('frozen'):
            raise ValueError('Recover the frozen CPU delta state before starting a frame timeline')
        keyboard = self.call('input.keyboard.state').get('keyboard', {})
        if keyboard.get('pending_events') or keyboard.get('owned_keys'):
            raise ValueError('Frame timeline cannot mix legacy queued or leased keyboard input')
        _require_released_mouse(self.call('input.mouse.state').get('mouse', {}))

    def _timeline_bytes(self, history):
        return sum(p['bytes'] for p in history['points']) + sum(len(_encoded(i)) for i in history['inputs'])

    def _timeline_raw_size(self, point):
        return point['checkpoint']['size'] if 'delta' in point else len(point['checkpoint']['data'])

    def _timeline_state_payload_size(self, point):
        return len(point['delta']['payload']) if 'delta' in point else len(point['checkpoint']['data'])

    def _timeline_descriptor_size(self, point):
        return len(_encoded(state_codec.descriptor(point['delta']))) if 'delta' in point else 0

    def _timeline_point_bytes(self, point):
        return (self._timeline_state_payload_size(point) + self._timeline_descriptor_size(point)
                + len(_encoded(point['checkpoint']['metadata'])) + (len(point['image']) if point['image'] else 0)
                + len(_encoded(point['image_metadata'])))

    def _timeline_codec_deadline(self):
        deadline = getattr(self, '_rpc_deadline', None)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('Frame timeline codec exceeded the shared operation deadline')

    def _timeline_materialize(self, history, point):
        """Verify the bounded dependency chain before returning ordinary native bytes."""
        begun = time.perf_counter_ns()
        stats = history['codec_stats']
        stats['materialize_count'] += 1
        try:
            self._timeline_codec_deadline()
            index = next((i for i, item in enumerate(history['points']) if item is point), None)
            if index is None:
                raise ValueError('Native delta point is not owned by this timeline')
            chain = []
            while True:
                current = history['points'][index]
                self._timeline_check_point(current, history)
                if 'delta' not in current:
                    data = current['checkpoint']['data']
                    break
                if index == 0 or len(chain) >= history['keyframe_interval'] - 1:
                    raise ValueError('Native delta base is missing or chain exceeds its bound')
                parent = history['points'][index - 1]
                delta = current['delta']
                if (delta['base_point'] != parent['id'] or delta['base_sha256'] != parent['checkpoint']['sha256']
                        or delta['base_size'] != self._timeline_raw_size(parent)
                        or delta['depth'] != parent.get('delta', {}).get('depth', 0) + 1):
                    raise ValueError('Native delta dependency identity mismatch')
                chain.append(current)
                index -= 1
            for current in reversed(chain):
                self._timeline_codec_deadline()
                data = state_codec.decode(data, current['delta'], max_bytes=history['max_state_bytes'],
                                          max_depth=history['keyframe_interval'] - 1)
                stats['delta_decode_count'] += 1
            self._timeline_codec_deadline()
            return dict(data=data, sha256=point['checkpoint']['sha256'],
                        metadata=deepcopy(point['checkpoint']['metadata']))
        finally:
            stats['decode_elapsed_ns'] += time.perf_counter_ns() - begun

    def _timeline_rebase_first(self, history):
        """Promote a successor before evicting its base; never edit a shared point."""
        successor = history['points'][1]
        if 'delta' in successor:
            promoted = dict(successor, checkpoint=self._timeline_materialize(history, successor))
            del promoted['delta']
            promoted['bytes'] = self._timeline_point_bytes(promoted)
            history['points'][1] = promoted
            # Descriptors bind their actual retained dependency depth. Replace
            # descendants too, so a speculative preflight never edits shared
            # points and the selected state's existing envelope remains stable.
            depth = 0
            for index in range(2, len(history['points'])):
                descendant = history['points'][index]
                if 'delta' not in descendant:
                    break
                self._timeline_check_point(descendant, history)
                depth += 1
                updated = dict(descendant, delta=state_codec.rebase_depth(descendant['delta'], depth))
                updated['bytes'] = self._timeline_point_bytes(updated)
                history['points'][index] = updated

    def _timeline_branch(self, history):
        if history['needs_branch'] or history['cursor'] + 1 < len(history['points']):
            point = history['points'][history['cursor']]
            history['points'] = history['points'][:history['cursor'] + 1]
            history['inputs'] = [i for i in history['inputs'] if i['frame'] < point['frame']]
            history['branch'] = uuid.uuid4().hex
            history['needs_branch'] = False
            history['next_frame'] = point['frame'] + 1

    def _timeline_reserve(self, history, extra=0):
        reserve = history['max_state_bytes'] + history['max_image_bytes'] + extra
        if history['captures_used'] >= history['max_captures']:
            raise ValueError('Frame timeline cumulative capture budget exhausted')
        while (len(history['points']) >= history['max_frames'] + 1
               or self._timeline_bytes(history) + reserve > history['max_bytes']):
            if history['cursor'] == 0:
                raise ValueError('Frame timeline cannot reserve the next capture within its byte budget')
            self._timeline_rebase_first(history)
            del history['points'][0]
            history['cursor'] -= 1
            retained = {p['id'] for p in history['points']}
            history['inputs'] = [i for i in history['inputs'] if i['point'] in retained]

    def _timeline_prepare_forward(self, history, extra=0):
        # Branch/eviction preflight changes only this owned cache. A refusal
        # before native mutation must retain the old future and rewind depth.
        if history['storage_mode'] == 'delta':
            self._timeline_materialize(history, history['points'][history['cursor']])
        saved = {key: history[key] for key in ('points', 'inputs', 'cursor', 'branch', 'needs_branch', 'next_frame')}
        history['points'], history['inputs'] = list(history['points']), list(history['inputs'])
        try:
            self._timeline_branch(history)
            self._timeline_reserve(history, extra)
        except BaseException:
            history.update(saved)
            raise

    def _timeline_envelope(self, point):
        return dict(id=point['id'], frame=point['frame'], kind=point['kind'],
                    checkpoint_sha256=point['checkpoint']['sha256'],
                    checkpoint_size=self._timeline_raw_size(point), metadata=point['checkpoint']['metadata'],
                    image_sha256=_sha(point['image']) if point['image'] is not None else None,
                    image_metadata=point['image_metadata'])

    def _timeline_check_point(self, point, history=None):
        if 'delta' in point:
            if 'data' in point['checkpoint']:
                raise ValueError('Delta point unexpectedly retains a full payload')
            state_codec.validate(point['delta'], result_sha256=point['checkpoint']['sha256'],
                result_size=point['checkpoint']['size'], max_bytes=history['max_state_bytes'] if history else 256 * 1024**2,
                max_depth=history['keyframe_interval'] - 1 if history else 127)
        elif _sha(point['checkpoint']['data']) != point['checkpoint']['sha256']:
            raise ValueError('Frame timeline cached checkpoint hash mismatch')
        if _sha(_encoded(self._timeline_envelope(point))) != point['envelope_sha256']:
            raise ValueError('Frame timeline cached checkpoint/image envelope hash mismatch')

    def _timeline_capture(self, history, *, boundary=None):
        checkpoint = deepcopy(self._capture_native_checkpoint(max_bytes=history['max_state_bytes']))
        data = checkpoint.get('data')
        if not isinstance(data, bytes) or not data or _sha(data) != checkpoint.get('sha256'):
            raise ValueError('Frame timeline native checkpoint receipt hash mismatch')
        if len(data) + len(_encoded(checkpoint['metadata'])) > history['max_state_bytes']:
            raise ValueError('Frame timeline native checkpoint exceeds its state budget')
        if checkpoint['metadata'].get('disk_manifest') != history['manifest']:
            raise ValueError('Frame timeline checkpoint mounted-file identity mismatch')
        image, image_metadata = None, {}
        try:
            result = self.call('video.screenshot')
        except ValueError as error:
            if boundary is not None or not ('No complete framebuffer' in str(error) or 'FRAMEBUFFER_UNAVAILABLE' in str(error)):
                raise
        else:
            image = base64.b64decode(result['png_base64'], validate=True)
            image_metadata = {k: v for k, v in result.items() if k != 'png_base64'}
            if not image.startswith(b'\x89PNG\r\n\x1a\n') or result.get('sha256') != _sha(image):
                raise ValueError('Frame timeline stored PNG identity mismatch')
            if len(image) + len(_encoded(image_metadata)) > history['max_image_bytes']:
                raise ValueError('Frame timeline stored image exceeds its byte budget')
            width, height = result.get('width'), result.get('height')
            if type(width) is not int or type(height) is not int or not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height * 4 > 16 * 1024**2:
                raise ValueError('Frame timeline stored image dimensions exceed native bounds')
            from PIL import Image
            with Image.open(io.BytesIO(image)) as decoded:
                if decoded.format != 'PNG' or decoded.size != (width, height):
                    raise ValueError('Frame timeline stored image dimensions differ from its receipt')
                decoded.load()
            if boundary is not None and result.get('frame_id') != boundary['frame_id']:
                raise ValueError('Frame timeline screenshot differs from completed frame boundary')
        if self._disk_manifest() != history['manifest']:
            raise ValueError('Mounted files changed during frame timeline capture')
        if boundary is None and type(image_metadata.get('frame_id')) is int:
            history['last_native_frame_id'] = image_metadata['frame_id']
        point = dict(id=uuid.uuid4().hex, frame=history['next_frame'],
                     kind='initial-paused' if boundary is None else 'completed-frame',
                     checkpoint=checkpoint, image=image, image_metadata=image_metadata)
        point['envelope_sha256'] = _sha(_encoded(self._timeline_envelope(point)))
        if history['storage_mode'] == 'delta' and history['points']:
            parent = history['points'][history['cursor']]
            depth = parent.get('delta', {}).get('depth', 0) + 1
            if depth < history['keyframe_interval']:
                base = self._timeline_materialize(history, parent)
                begun = time.perf_counter_ns()
                try:
                    self._timeline_codec_deadline()
                    delta = state_codec.encode(base['data'], data, base_point=parent['id'], depth=depth)
                    self._timeline_codec_deadline()
                finally:
                    history['codec_stats']['encode_count'] += 1
                    history['codec_stats']['encode_elapsed_ns'] += time.perf_counter_ns() - begun
                if delta is not None:
                    point['delta'] = delta
                    point['checkpoint'] = dict(sha256=checkpoint['sha256'], size=len(data), metadata=checkpoint['metadata'])
        point['bytes'] = self._timeline_point_bytes(point)
        history['captures_used'] += 1
        history['next_frame'] += 1
        return point

    @timeline_locked
    def timeline_start(self, max_frames=120, max_bytes=64 * 1024**2, max_state_bytes=8 * 1024**2,
                       max_image_bytes=2 * 1024**2, max_captures=4096, storage_mode='full', keyframe_interval=8):
        validate_storage(storage_mode, keyframe_interval)
        for name, value, hi in (('max_frames', max_frames, 4096), ('max_bytes', max_bytes, 256 * 1024**2),
                ('max_state_bytes', max_state_bytes, 256 * 1024**2), ('max_image_bytes', max_image_bytes, 16 * 1024**2),
                ('max_captures', max_captures, 65536)):
            _bounded(value, name, 1, hi)
        if max_state_bytes + max_image_bytes > max_bytes:
            raise ValueError('Frame timeline byte budget cannot reserve one state and image')
        self._timeline_native()
        if (getattr(self, '_frame_timeline', None) or {}).get('mixed_frozen'):
            raise ValueError('Recover the frozen timeline mixed state before starting a new timeline')
        with self._timeline_owned():
            self._timeline_admit()
            self._timeline_invalidate('new frame timeline started')
            for name in ('_cpu_delta_invalidate', '_rewind_invalidate'):
                if hasattr(self, name):
                    getattr(self, name)('frame timeline started')
            history = dict(id=uuid.uuid4().hex, branch=uuid.uuid4().hex, identity=self._timeline_identity(),
                manifest=deepcopy(self._disk_manifest()), valid=True, invalid_reason=None, points=[], inputs=[],
                cursor=0, current_dirty=False, needs_branch=False, next_frame=0, captures_used=0, input_events_used=0,
                last_native_frame_id=None, max_frames=max_frames, max_bytes=max_bytes, max_state_bytes=max_state_bytes,
                max_image_bytes=max_image_bytes, max_captures=max_captures, mixed_frozen=False,
                storage_mode=storage_mode, keyframe_interval=keyframe_interval,
                codec_stats=dict(encode_count=0, encode_elapsed_ns=0, materialize_count=0,
                                 decode_elapsed_ns=0, delta_decode_count=0))
            history['points'].append(self._timeline_capture(history))
            self._frame_timeline = history
        result = self.timeline_status()
        self._event('timeline-start', result)
        return result

    @timeline_locked
    def timeline_status(self):
        history = getattr(self, '_frame_timeline', None)
        result = dict(format=FORMAT, run=self.run_id, survives_live_session=False,
                      storage='bounded live RAM cache; no per-frame durable state artifacts',
                      unit='completed renderer frame followed by the next safe CPU boundary')
        if history is None:
            return dict(result, active=False, valid=False, cursor=None, retained_points=0, bytes_used=0,
                        current_dirty=False, current_cached=False, available_back=0)
        point = history['points'][history['cursor']]
        experiment = self.metadata.get('timeline_experiment') or self.metadata.get('delta_experiment')
        return dict(result, timeline=history['id'], branch=history['branch'], active=not self.closed,
            storage_mode=history['storage_mode'], keyframe_interval=history['keyframe_interval'],
            full_state_points=sum('delta' not in p for p in history['points']),
            delta_state_points=sum('delta' in p for p in history['points']),
            retained_encoded_state_payload_bytes=sum(self._timeline_state_payload_size(p) for p in history['points']),
            reconstructed_state_payload_bytes=sum(self._timeline_raw_size(p) for p in history['points']),
            retained_delta_descriptor_bytes=sum(self._timeline_descriptor_size(p) for p in history['points']),
            raw_checkpoint_limit_bytes=history['max_state_bytes'],
            codec_transient_bound_bytes=(6 * history['max_state_bytes'] + 8 * 1024**2 + 4 * state_codec.BLOCK) if history['storage_mode'] == 'delta' else 0,
            codec_stats=deepcopy(history['codec_stats']),
            capture_contract='Complete native state capture at every point; delta encoding changes retention only',
            cache_budget_excludes='Codec transient workspace, native serialization/emulator RAM and Python allocator overhead',
            valid=history['valid'] and not self.closed, invalid_reason=history['invalid_reason'], cursor=point['frame'],
            retained_points=len(history['points']), available_back=history['cursor'] if history['valid'] and not self.closed else 0,
            current_dirty=history['current_dirty'], current_cached=not history['current_dirty'] and history['valid'],
            point=point['id'], point_kind=point['kind'], checkpoint_sha256=point['checkpoint']['sha256'],
            bytes_used=self._timeline_bytes(history), captures_used=history['captures_used'], input_events_used=history['input_events_used'],
            max_frames=history['max_frames'], max_bytes=history['max_bytes'], max_captures=history['max_captures'],
            max_state_bytes=history['max_state_bytes'], max_image_bytes=history['max_image_bytes'],
            state_bytes_used=sum(self._timeline_state_payload_size(p) + self._timeline_descriptor_size(p) + len(_encoded(p['checkpoint']['metadata'])) for p in history['points']),
            image_bytes_used=sum((len(p['image']) if p['image'] else 0) + len(_encoded(p['image_metadata'])) for p in history['points']),
            state_payload_bytes=sum(self._timeline_state_payload_size(p) for p in history['points']),
            image_payload_bytes=sum(len(p['image']) if p['image'] else 0 for p in history['points']),
            input_bytes_used=sum(len(_encoded(i)) for i in history['inputs']),
            experiment=deepcopy(experiment), resume_safe=not bool(experiment) and not history['mixed_frozen'] and not self.closed,
            points=[dict(point=p['id'], frame=p['frame'], kind=p['kind'], checkpoint_sha256=p['checkpoint']['sha256'],
                         state_bytes=self._timeline_state_payload_size(p) + self._timeline_descriptor_size(p) + len(_encoded(p['checkpoint']['metadata'])),
                         image_bytes=(len(p['image']) if p['image'] else 0) + len(_encoded(p['image_metadata'])),
                         checkpoint_size=self._timeline_raw_size(p), image_size=len(p['image']) if p['image'] else 0,
                         encoded_state_size=self._timeline_state_payload_size(p),
                         storage_kind='delta' if 'delta' in p else 'full', delta_depth=p.get('delta', {}).get('depth', 0),
                         image_sha256=_sha(p['image']) if p['image'] is not None else None,
                         envelope_sha256=p['envelope_sha256']) for p in history['points']],
            execution_allowed=not history['mixed_frozen'] and not self.closed)

    def _timeline_input_reservation(self, edges):
        normalized = [dict(key='escape' if e['key'] == 'esc' else e['key'], pressed=e['pressed']) for e in edges]
        return len(_encoded(normalized)) + 256 if edges else 0

    def _timeline_edges(self, edges, history=None, *, reserved=False, input_state=None):
        validate_edges(edges)
        normalized = [dict(key='escape' if e['key'] == 'esc' else e['key'], pressed=e['pressed']) for e in edges]
        held, capacity = input_state if input_state is not None else self._timeline_input_state()
        self._timeline_edge_ownership(normalized, held)
        self._timeline_edge_capacity(edges, capacity)
        if history is not None:
            if history['mixed_frozen']:
                raise ValueError('Timeline preservation policy requires explicit partial resume approval')
            if history['input_events_used'] + len(edges) > 4096:
                raise ValueError('Frame timeline cumulative input budget exhausted')
            if edges and not reserved:
                self._timeline_prepare_forward(history, self._timeline_input_reservation(edges))
        try:
            result = self.call('input.keyboard.frame_edges', dict(edges=normalized))
        except BaseException:
            self._timeline_fail('native frame input delivery failed', close=bool(edges))
            raise
        if history is not None and edges:
            history['current_dirty'] = True
            history['input_events_used'] += len(edges)
            history['inputs'].append(dict(point=history['points'][history['cursor']]['id'],
                frame=history['points'][history['cursor']]['frame'], edges=deepcopy(normalized)))
        return result

    def _timeline_input_state(self):
        keyboard = self.call('input.keyboard.state').get('keyboard', {})
        held = keyboard.get('frame_keys', [])
        if not isinstance(held, list) or any(not isinstance(key, str) for key in held):
            raise ValueError('Native frame input ownership is unavailable')
        return {'escape' if key == 'esc' else key for key in held}, keyboard.get('frame_edge_capacity')

    def _timeline_edge_capacity(self, edges, capacity):
        if edges and (type(capacity) is not int or not 0 <= capacity <= 32):
            raise ValueError('Native frame input FIFO capacity is unavailable')
        if edges and len(edges) > capacity:
            raise ValueError('Native keyboard FIFO cannot reserve this complete frame input batch')

    def _timeline_edge_ownership(self, edges, held):
        held = set(held)
        for edge in edges:
            key = 'escape' if edge['key'] == 'esc' else edge['key']
            if (key in held) == edge['pressed']:
                raise ValueError('Frame input key is already in the requested held/released state')
            (held.add if edge['pressed'] else held.remove)(key)
        return held

    @timeline_locked
    def frame_inputs(self, edges):
        validate_edges(edges)
        self._timeline_native()
        history = getattr(self, '_frame_timeline', None)
        if history is not None and history['mixed_frozen']:
            raise ValueError('Timeline mixed state is frozen')
        history = self._timeline_require() if history is not None and history['valid'] else None
        accepted = False
        with self._timeline_owned():
            self._timeline_admit()
            try:
                result = self._timeline_edges(edges, history)
                accepted = bool(edges)
                if edges:
                    self._event('frame-inputs', dict(edges=deepcopy(edges), timeline=history['id'] if history else None))
            except BaseException:
                # Shape/ownership validation precedes native delivery. Once a
                # delivery was accepted, a missing receipt is an uncertain edit.
                if accepted:
                    self._timeline_fail('frame input receipt failed', close=True)
                raise
        return dict(result, timeline=self.timeline_status())

    def _timeline_step(self, history=None):
        result = dict(self.call('frame.step', {}))
        if 'state' not in result:
            revision = result.get('state_revision')
            if type(revision) is not int or revision < 0:
                raise ValueError('Native frame boundary lacks a verifiable state revision')
            stopped = self.call('session.status')
            if stopped.get('state') != 'stopped' or stopped.get('state_revision') != revision:
                raise ValueError('Native frame boundary stopped-state revision readback mismatch')
            result['state'] = 'stopped'
            result['boundary_verified_by'] = 'matching stopped session.status revision'
        frame = result.get('frame_id')
        if (type(frame) is not int or frame < 1 or result.get('state') != 'stopped'
                or result.get('completed') is not True or result.get('stop_reason', {}).get('kind') != 'frame'):
            raise ValueError('Native frame step did not return a completed frame and stopped CPU boundary')
        if history is not None:
            if history['last_native_frame_id'] is not None and frame <= history['last_native_frame_id']:
                raise ValueError('Native completed frame identity did not advance')
            history['last_native_frame_id'] = frame
        return result

    @timeline_locked
    @rpc_budget
    def advance_frames(self, frames=1, timeout_ms=10000):
        _bounded(frames, 'frames', 1, 128)
        self._timeline_native()
        if (getattr(self, '_frame_timeline', None) or {}).get('mixed_frozen'):
            raise ValueError('Timeline mixed state is frozen')
        self._timeline_invalidate('unrecorded frame advancement')
        records = []
        with self._timeline_owned():
            self._timeline_admit()
            try:
                for _ in range(frames):
                    records.append(self._timeline_step())
            except BaseException:
                self._timeline_fail('unrecorded frame advance failed', close=True)
                raise
        return dict(format=FORMAT, run=self.run_id, completed_frames=len(records), frames=records)

    @timeline_locked
    @rpc_budget
    def timeline_advance(self, frames=1, inputs=None, timeout_ms=10000):
        _bounded(frames, 'frames', 1, 128)
        validate_schedule(inputs, frames)
        history = self._timeline_require()
        if history['mixed_frozen']:
            raise ValueError('Timeline preservation policy requires explicit partial resume approval')
        if history['captures_used'] + frames > history['max_captures']:
            raise ValueError('Frame timeline cumulative capture budget exhausted')
        schedule = {item['frame']: item['edges'] for item in inputs or []}
        if history['input_events_used'] + sum(len(e) for e in schedule.values()) > 4096:
            raise ValueError('Frame timeline cumulative input budget exhausted')
        # Check the first complete transition, including its input journal,
        # without changing the cache or issuing even an observation RPC.
        probe = dict(history, points=list(history['points']), inputs=list(history['inputs']))
        self._timeline_prepare_forward(probe, self._timeline_input_reservation(schedule.get(0, [])))
        completed = []
        attempted = False
        with self._timeline_owned():
            try:
                self._timeline_admit()
                held, _ = self._timeline_input_state()
                for offset in sorted(schedule):
                    held = self._timeline_edge_ownership(schedule[offset], held)
                for offset in range(frames):
                    attempted = False
                    input_state = None
                    if schedule.get(offset):
                        input_state = self._timeline_input_state()
                        self._timeline_edge_ownership(schedule[offset], input_state[0])
                        self._timeline_edge_capacity(schedule[offset], input_state[1])
                    self._timeline_prepare_forward(history, self._timeline_input_reservation(schedule.get(offset, [])))
                    if offset in schedule:
                        attempted = True
                        self._timeline_edges(schedule[offset], history, reserved=True, input_state=input_state)
                    attempted = True
                    boundary = self._timeline_step(history)
                    point = self._timeline_capture(history, boundary=boundary)
                    history['points'].append(point)
                    history['cursor'] = len(history['points']) - 1
                    history['current_dirty'] = False
                    completed.append(dict(point=point['id'], frame=point['frame'], native_frame=deepcopy(boundary),
                                          checkpoint_sha256=point['checkpoint']['sha256']))
                    self._timeline_require()
                    attempted = False
            except BaseException:
                if attempted:
                    self._timeline_fail('frame advancement or capture failed', close=True)
                raise
        result = dict(format=FORMAT, run=self.run_id, completed_frames=len(completed), frames=completed,
                      timeline=self.timeline_status())
        try:
            self._event('timeline-advance', _receipt(result))
        except BaseException:
            self._timeline_fail('frame receipt failed', close=True)
            raise
        return result

    def _timeline_runtime_read(self, address, length):
        result = self.call('memory.read', dict(address=dict(space='linear', offset=f'0x{address:08X}'), length=length))
        data = base64.b64decode(result['data_base64'], validate=True)
        if len(data) != length or result.get('sha256') != _sha(data):
            raise ValueError('Timeline preserved RAM readback identity mismatch')
        return data

    @timeline_locked
    @rpc_budget
    def timeline_rewind(self, frames=1, policy=None, timeout_ms=10000):
        _bounded(frames, 'frames', 0, 4096)
        validate_timeline_policy(policy)
        history = self._timeline_require()
        if frames > history['cursor'] or (frames == 0 and not history['current_dirty']):
            raise ValueError('Timeline rewind exceeds available frames or requires a dirty current point for zero')
        target_index = history['cursor'] - frames
        point = history['points'][target_index]
        checkpoint = self._timeline_materialize(history, point)
        attempted = False
        with self._timeline_owned():
            try:
                self._timeline_admit()
                preserved = []
                source_point = history['points'][history['cursor']]
                source = dict(point=source_point['id'], frame=source_point['frame'], branch=history['branch'],
                              current_dirty=history['current_dirty'])
                prior_experiment = deepcopy(self.metadata.get('timeline_experiment'))
                for item in (policy or {}).get('preserve_memory', []):
                    address = _address(item['address'])
                    preserved.append((address, self._timeline_runtime_read(address, item['length'])))
                attempted = True
                restored = self._restore_native_checkpoint(checkpoint)
                plans = [(address, self._timeline_runtime_read(address, len(data)), data) for address, data in preserved]
                for address, old, new in plans:
                    if old != new:
                        self.call('memory.write', dict(address=dict(space='linear', offset=f'0x{address:08X}'),
                            expected_sha256=_sha(old), data_base64=base64.b64encode(new).decode()))
                if any(self._timeline_runtime_read(address, len(new)) != new for address, _, new in plans):
                    raise ValueError('Timeline preservation overlay readback mismatch')
                history['cursor'] = target_index
                history['current_dirty'] = bool(policy)
                history['mixed_frozen'] = bool(policy and not policy.get('allow_partial_resume', False))
                history['needs_branch'] = True
                if policy:
                    self._timeline_branch(history)
                    experiment = dict(format='fdisbull-timeline-experiment-1', policy=deepcopy(policy),
                        timeline=history['id'], branch=history['branch'], base_point=point['id'],
                        source=source,
                        base_checkpoint_sha256=point['checkpoint']['sha256'],
                        preserved=[dict(address=hex(a), length=len(data), sha256=_sha(data)) for a, data in preserved],
                        full_machine_restored=False, resume_safe=False)
                    if prior_experiment is not None:
                        experiment['parent_sha256'] = _sha(_encoded(prior_experiment))
                    self.metadata['timeline_experiment'] = experiment
                self._timeline_require()
                experiment = self.metadata.get('timeline_experiment') or self.metadata.get('delta_experiment')
                result = dict(format=FORMAT, run=self.run_id, rewound_frames=frames, restored=restored,
                    full_native_state_loaded=True, full_machine_restored=not bool(experiment),
                    execution_allowed=not history['mixed_frozen'], resume_safe=not bool(experiment),
                    experiment=deepcopy(experiment), timeline=self.timeline_status())
                self._event('timeline-rewind', _receipt(result))
            except BaseException:
                self._timeline_fail('timeline native restore or overlay failed', close=attempted)
                raise
        return result

    @timeline_locked
    def timeline_pin(self, name='anchor-stone.sav'):
        history = self._timeline_require()
        if history['current_dirty']:
            raise ValueError('Current timeline point is dirty; complete a fresh frame before pinning')
        point = history['points'][history['cursor']]
        checkpoint = self._timeline_materialize(history, point)
        return self._artifact(name, 'state', checkpoint['data'], deepcopy(checkpoint['metadata']))

    @timeline_locked
    def timeline_image(self, name='timeline-frame.png'):
        history = self._timeline_require()
        point = history['points'][history['cursor']]
        self._timeline_check_point(point)
        if point['image'] is None:
            raise ValueError('The initial paused timeline point has no completed stored frame')
        metadata = dict(deepcopy(point['image_metadata']), timeline=history['id'], point=point['id'],
            checkpoint_sha256=point['checkpoint']['sha256'], stored_frame=True,
            historical_reference=history['current_dirty'], current_machine=not history['current_dirty'])
        return self._artifact(name, 'screenshot', point['image'], metadata)

    @timeline_locked
    def timeline_stop(self):
        if (getattr(self, '_frame_timeline', None) or {}).get('mixed_frozen'):
            raise ValueError('Restore the frozen timeline point before stopping its guard')
        result = self.timeline_status()
        self._frame_timeline = None
        return dict(format=FORMAT, run=self.run_id, stopped=True, released_bytes=result['bytes_used'],
                    target_executed=False, input_state_changed=False)
