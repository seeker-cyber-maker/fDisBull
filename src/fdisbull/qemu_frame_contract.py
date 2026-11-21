"""Legacy-shaped pixel consumers for explicitly retained QEMU source rasters.

The native producer remains RGB888 at its declared scanline phase. Encoding is
performed by this host adapter. Neither shape compatibility nor an unchanged
session-control revision establishes application drawing completion, DOSBox
sampling-phase equivalence, or atomic CPU/frame state.
"""
import base64
from copy import deepcopy
import hashlib
import io

from .dosbox_rpc import DebuggerError
from .qemu_session_revision import session_revision
from .qemu_video_frame import (_failed, _probe_points_snapshot, _remaining,
                               validate_video_frame_parameters, validate_video_frame_probe)
from .screenshot_codecs import ENCODINGS, decode_frame_rgba, validate_encoding


FRAME_SOURCE = 'qemu_completed_source_raster'
FRAME_PROFILE = 'qemu-vga-chain4-scanline-v1'
FRAME_CLOCK = 'QEMU_CLOCK_VIRTUAL_milliseconds'


def configure_frame_contract(session):
    """Advertise the available host codecs separately from native transport."""
    from .qemu_observation_authority import ObservationAuthority
    available = (bool(session.capabilities.get('video_frame_capture'))
                 and isinstance(getattr(session.vm, 'observation_authority', None), ObservationAuthority))
    encodings = ['png', 'png-indexed'] if available else []
    if available:
        try:
            import zstandard  # noqa: F401
        except ImportError:
            pass
        else:
            encodings.append('rgba-zstd')
    video = dict(pixel_probe=available, screenshot_encodings=encodings,
        source=FRAME_SOURCE, frame_profile=FRAME_PROFILE, codec_origin='host-adapter',
        source_bpp=24, captured_ticks_clock=FRAME_CLOCK,
        requires_retained_source_raster=True, stopped_only=True,
        native_transport='RGB888/P6', completed_guest_frames=False)
    session.capabilities.update(frame_contract=available, frame_probe=available,
        frame_rgba=available, frame_contract_profile=FRAME_PROFILE, video=video)
    # Existing frame consumers discover codecs through rpc.capabilities.
    # QEMU's machine object is the DOS session's RPC owner, not a DOSBox agent.
    capabilities = dict(getattr(session.vm, 'capabilities', {}))
    capabilities['video'] = deepcopy(video)
    session.vm.capabilities = capabilities


def validate_frame_rgba_parameters(*, encoding='rgba-zstd', timeout_ms=1000):
    if type(encoding) is not str or encoding not in ENCODINGS:
        raise ValueError('Screenshot encoding must be png, png-indexed or rgba-zstd')
    validate_video_frame_parameters(timeout_ms=timeout_ms)


def frame_contract_metadata(session, native, clock, revision=None):
    """Keep native identity explicit while projecting a legacy integer mode."""
    authority = session_revision(session.vm)
    revision = authority.snapshot() if revision is None else revision
    frame = native['frame']
    identity = dict(owner_lifetime=revision['session_id'], native_epoch=native['epoch'],
        clock_epoch=clock['epoch'], stream=native['token'],
        stream_generation=native['stream-generation'],
        configuration_generation=frame['configuration-generation'],
        timing_generation=frame['timing-generation'], frame_id=frame['frame-id'],
        runtime_epoch=getattr(session, '_runtime_epoch', None),
        checkpoint_epoch=getattr(session, '_checkpoint_epoch', None))
    mode = tuple((key, value) for key, value in identity.items() if key != 'frame_id')
    return dict(**revision, source=FRAME_SOURCE, frame_profile=FRAME_PROFILE,
        frame_identity=identity, mode_id=authority.mode(mode), frame_id=frame['frame-id'],
        width=frame['width'], height=frame['height'], source_bpp=24,
        double_width=False, double_height=False, captured_ns=frame['completed-ns'],
        captured_ticks=frame['completed-ns'] // 1_000_000, captured_ticks_clock=FRAME_CLOCK,
        atomic=False, frame_state_equivalence=None, application_frame_complete=None,
        legacy_phase_equivalence=None, completed_source_raster=True)


def _encode(frame, encoding):
    """Produce the actual requested transport, with exact indexed fallback."""
    from PIL import Image
    metadata = deepcopy(frame.metadata)
    metadata['native_transport'] = metadata.pop('transport')
    metadata.update(codec_origin='host-adapter', requested_encoding=encoding)
    if encoding == 'rgba-zstd':
        import zstandard
        payload = zstandard.ZstdCompressor(level=1, write_content_size=True).compress(frame.pixels)
        metadata.update(format='rgba-zstd', encoding=encoding, pixel_format='RGBA8',
            stride=frame.stride, uncompressed_bytes=len(frame.pixels), raw_sha256=frame.sha256)
        field = 'data_base64'
    else:
        palette = {}
        indices = bytearray()
        if encoding == 'png-indexed':
            for offset in range(0, len(frame.pixels), 4):
                color = frame.pixels[offset:offset + 3]
                if color not in palette:
                    if len(palette) == 256:
                        break
                    palette[color] = len(palette)
                indices.append(palette[color])
        indexed = encoding == 'png-indexed' and len(indices) == frame.width * frame.height
        output = io.BytesIO()
        if indexed:
            with Image.frombytes('P', (frame.width, frame.height), bytes(indices)) as image:
                image.putpalette(b''.join(palette).ljust(768, b'\0'))
                image.save(output, format='PNG', compress_level=1)
            metadata['palette_colors'] = len(palette)
        else:
            with Image.frombytes('RGBA', (frame.width, frame.height), frame.pixels) as image:
                image.save(output, format='PNG', compress_level=1)
            if encoding == 'png-indexed':
                metadata['fallback_reason'] = 'more_than_256_colors'
        payload = output.getvalue()
        for key in ('pixel_format', 'stride', 'uncompressed_bytes', 'raw_sha256'):
            metadata.pop(key, None)
        metadata.update(format='png', encoding='png-indexed' if indexed else 'png')
        field = 'png_base64'
    metadata.update(sha256=hashlib.sha256(payload).hexdigest())
    metadata[field] = base64.b64encode(payload).decode('ascii')
    return metadata


class QemuFrameContractMixin:
    def _frame_contract_begin(self):
        from .qemu_observation_authority import ObservationAuthority
        vm = self.vm
        authority = getattr(vm, 'observation_authority', None)
        if not self.capabilities.get('frame_contract') or not isinstance(authority, ObservationAuthority):
            raise ValueError('Frame consumers require the owned source-raster extension and explicit virtual/precise profiles')
        authority._current_client(vm.qmp, 'qmp')
        revision = session_revision(vm)
        identity = (authority, revision, vm.lock, vm.qmp, vm.qmp.socket,
            getattr(self, '_runtime_epoch', None), getattr(self, '_checkpoint_epoch', None),
            revision.snapshot())
        return vm, identity

    def _frame_contract_check(self, vm, identity):
        authority, revision, lock, qmp, channel, runtime, checkpoint, before = identity
        _remaining(vm)
        if (self.vm is not vm or getattr(vm, 'closed', False)
                or vm.observation_authority is not authority or session_revision(vm) is not revision
                or vm.lock is not lock or vm.qmp is not qmp or qmp.socket is not channel
                or getattr(self, '_runtime_epoch', None) != runtime
                or getattr(self, '_checkpoint_epoch', None) != checkpoint
                or revision.snapshot() != before):
            raise DebuggerError('Session control or owner changed across the retained-frame read')
        authority._current_client(qmp, 'qmp')

    def frame_probe(self, points, *, timeout_ms=1000):
        points = _probe_points_snapshot(points)
        validate_video_frame_probe(points, timeout_ms=timeout_ms)
        vm, identity = self._frame_contract_begin()
        before = self._video_frame_context(cpu_context=False)
        prior = self._video_frame_select(vm, before, None, None)
        result = None
        raw, chunks = None, []
        try:
            result, raw, chunks = self._video_frame_selected_probe(vm, before, prior, points)
            result.update(frame_contract_metadata(self, prior, before, identity[-1]))
            result['format'] = 'rgb-samples'
            self._frame_contract_check(vm, identity)
            self._video_frame_publish(vm, 'frame-probe', result)
            self._frame_contract_check(vm, identity)
            return result
        except BaseException as error:
            _failed(vm, error, 'frame-probe', clock=before, native=raw, result=result, probe_chunks=chunks)
            raise

    def _frame_contract_read(self, encoding, *, decode):
        # Negotiate before native I/O. A requested codec is never silently
        # ignored, and Zstandard availability is a host-adapter capability.
        validate_encoding(encoding, self.capabilities)
        vm, identity = self._frame_contract_begin()
        before = self._video_frame_context(cpu_context=False)
        prior = self._video_frame_select(vm, before, None, None)
        result = None
        try:
            frame = self._video_frame_selected_rgba(vm, before, prior)
            frame.metadata.update(frame_contract_metadata(self, prior, before, identity[-1]))
            self._frame_contract_check(vm, identity)
            result = _encode(frame, encoding)
            if decode:
                result = decode_frame_rgba(result)
            self._frame_contract_check(vm, identity)
            return result
        except BaseException as error:
            _failed(vm, error, 'frame-rgba' if decode else 'frame-screenshot',
                    clock=before, native=prior, result=getattr(result, 'metadata', result))
            raise

    def frame_rgba(self, *, encoding='rgba-zstd', timeout_ms=1000):
        """Consume one retained raster through a real host codec, without artifacts."""
        return self._frame_contract_read(encoding, decode=True)

    def _frame_screenshot(self, *, encoding='png', timeout_ms=1000):
        return self._frame_contract_read(encoding, decode=False)

    def call(self, method, params=None):
        """Small local SDK facade; it does not forward arbitrary DOSBox RPCs."""
        if params is not None and type(params) is not dict:
            raise ValueError('Frame RPC parameters must be an object')
        params = dict(params or {})
        if params.pop('session_id', self.session_id) != self.session_id:
            raise ValueError('Frame RPC belongs to another session lifetime')
        if method == 'session.status' and not params:
            return self.status()
        if method == 'video.probe' and set(params) <= {'points', 'timeout_ms'} and 'points' in params:
            return self.frame_probe(**params)
        if method == 'video.screenshot' and set(params) <= {'encoding', 'timeout_ms'}:
            return self._frame_screenshot(**params)
        raise ValueError('Unsupported QEMU frame RPC method or parameters: ' + str(method))
