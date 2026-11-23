"""Persistent stopped QEMU renderer-publication histories.

A renderer publication is not proof of a completed guest drawing frame, VGA
vertical retrace, physical scanout, or input consumption.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from functools import wraps
import io
import json
from pathlib import Path
import time
import uuid

from .qemu_dos_history import (FORMAT, MAX_NODES, MAX_STATE, QemuDOSHistoryMixin, _history_operation,
                               _json, _positive_int, _sha)
from .dosbox_rpc import DebuggerError
from .qemu_frame_step import source_frame_advance_route
from .qemu_source_timeline import (SOURCE_RASTER, SOURCE_UNIT, require_source_checkpoint_schema,
    source_raster_record, source_timeline_capable, validate_source_raster)
from .qemu_frame_key_batch import (INPUT_RECEIPT_RESERVE, InputReceiptBudgetError, VerifiedBatchRefusal,
    batch_capability, frame_input_operation, input_owner, plan_batch)

FRAME_COMMANDS = frozenset({'x-fdisbull-arm-display-frame',
    'x-fdisbull-query-display-frame', 'x-fdisbull-cancel-display-frame'})
KIND = 'renderer-frames'


def _source_record_match(saved, current):
    return (current['logical_sha256'] == saved['logical_sha256']
            and current['pixel_sha256'] == saved['pixel_sha256']
            and current['frame_id'] == saved['frame_id'])


def _verify_source_checkpoint(metadata, expected):
    if metadata.get('source_raster') != expected:
        raise ValueError('Native checkpoint and source raster identity differ')


def _timeline_start_operation(function):
    renderer = _history_operation(function)
    source = frame_input_operation(function)

    @wraps(function)
    def invoke(self, *args, **kwargs):
        if kwargs.get('frame_source') == SOURCE_RASTER and kwargs.get('timeline') is None:
            return source(self, *args, **kwargs)
        return renderer(self, *args, **kwargs)
    return invoke


def _ordinary_stop(result):
    if (not isinstance(result, dict) or result.get('outcome') != 'stopped'
            or result.get('timed_out') is not False or result.get('hook_hits')
            or any(key in result for key in ('native_machine_stop','guest_exit','guest_tsr'))):
        return False
    process = result.get('process')
    if process is not None and (not isinstance(process, dict) or process.get('state') != 'active'
                                or process.get('termination') is not None
                                or process.get('machine_closed', False) is not False):
        return False
    session = result.get('session')
    if not isinstance(session,dict) or session.get('state') != 'stopped': return False
    stop = session.get('stop_reason')
    if (not isinstance(stop,dict) or stop.get('kind') != 'stopped'
            or stop.get('breakpoint_ids') != [] or stop.get('classification_complete',True) is not True):
        return False
    reply = stop.get('native_reply')
    if not isinstance(reply,str) or reply[:3] not in ('T02','S02'): return False
    if reply.startswith('S') and len(reply) != 3: return False
    fields = {item.split(':',1)[0] for item in reply[3:].split(';') if item}
    return not fields.intersection({'watch','rwatch','awatch','swbreak','hwbreak'})


def _frame_receipt(raw, *, token, display_token, baseline, epoch=None):
    if (not isinstance(raw,dict) or type(raw.get('api-version')) is not int or raw['api-version'] != 1
            or type(raw.get('epoch')) is not int or raw['epoch'] < 1
            or epoch is not None and raw['epoch'] != epoch
            or raw.get('state') not in ('armed','completed','cancelled')
            or raw.get('token') != token or raw.get('display-token') != display_token
            or type(raw.get('baseline-update-id')) is not int or raw['baseline-update-id'] != baseline
            or type(raw.get('updates')) is not int or raw['updates'] < baseline
            or type(raw.get('stop-pending')) is not bool or type(raw.get('stop-consumed')) is not bool):
        raise DebuggerError('Invalid native renderer frame-fence receipt')
    if raw['state'] == 'completed':
        if (type(raw.get('completed-update-id')) is not int
                or raw['completed-update-id'] != baseline + 1 or raw['updates'] != baseline + 1
                or type(raw.get('published-ns')) is not int or raw['published-ns'] < 0):
            raise DebuggerError('Native renderer fence did not retain its next publication')
    elif 'completed-update-id' in raw or 'published-ns' in raw:
        raise DebuggerError('Incomplete renderer fence unexpectedly names a publication')
    return deepcopy(raw)


def _image_row(session, image):
    row = session.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(image.get('artifact'),)).fetchone()
    if (row is None or row['version'] != session.version['id'] or row['kind'] != 'screenshot' or row['sha256'] != image.get('sha256')
            or len(row['data']) != image.get('size') or _sha(bytes(row['data'])) != row['sha256']):
        raise ValueError('Stored timeline image is missing or corrupt')
    return row


class QemuDOSFramesMixin:
    """Renderer-update points backed by complete, immutable process states."""

    @staticmethod
    def _validate_manifest(manifest):
        from .qemu_frame_storage import FORMAT as DELTA_FORMAT, validate_manifest
        if isinstance(manifest,dict) and manifest.get('format') == DELTA_FORMAT:
            validate_manifest(manifest)
        else:
            QemuDOSHistoryMixin._validate_manifest(manifest)
        if manifest.get('history_kind') == KIND:
            config = manifest.get('frame_config')
            if not isinstance(config, dict) or config.get('frame_source') not in (None, SOURCE_RASTER):
                raise ValueError('Unknown stored timeline frame source')
            source = config.get('frame_source')
            for node in manifest['nodes']:
                frame = node.get('frame')
                if not isinstance(frame, dict) or (frame.get('kind') == SOURCE_RASTER) != (source == SOURCE_RASTER):
                    raise ValueError('Timeline frame source differs from its point')
                if source == SOURCE_RASTER:
                    validate_source_raster(frame.get('source_raster'))

    def _frame_delta(self, manifest):
        from .qemu_frame_storage import FORMAT as DELTA_FORMAT
        return manifest.get('format') == DELTA_FORMAT

    def _frame_state_bytes(self, manifest):
        from .qemu_frame_storage import stored_size
        return sum(stored_size(n['checkpoint']) if self._frame_delta(manifest)
                   else n['checkpoint']['size'] for n in manifest['nodes'])

    def _frame_bytes_used(self, manifest):
        return (self._frame_state_bytes(manifest)
                + sum(n['frame']['image']['size'] for n in manifest['nodes'])
                + len(json.dumps(manifest.get('input_journal',[]),sort_keys=True,separators=(',',':')).encode()))

    def _history_prepare_restore(self, manifest, target):
        prepared = None
        if self._frame_delta(manifest):
            from .qemu_frame_storage import materialize
            prepared = materialize(self,manifest,target)
        source = target.get('frame', {}).get('source_raster')
        if source is not None:
            if prepared is None:
                row = self._history_state_artifact(target['checkpoint'])
                data, metadata = bytes(row['data']), json.loads(row['metadata'])
            else:
                data, metadata = prepared['data'], prepared['metadata']
            _verify_source_checkpoint(metadata, source)
            from .qemu_dos_checkpoint import _unarchive
            from .qemu_instrumented_checkpoint import validate
            _, bundle = _unarchive(data, metadata_only=True)
            if _sha(_json(bundle)) != metadata.get('sidecar_sha256'):
                raise ValueError('Source raster checkpoint sidecar hash differs')
            state = validate(self.vm, bundle.get('instrumentation'))
            _verify_source_checkpoint({'source_raster': source_raster_record(
                state.get('video-frame', {}).get('info') if state is not None else None)}, source)
        return prepared

    def _frame_capture_delta(self, manifest, node_id, parent, name, image_capture, *, source=None):
        from .qemu_dos_checkpoint import capture_process_state
        from .qemu_frame_storage import store
        config = manifest['frame_config']
        before = self._history_disk_bytes()
        captured = capture_process_state(self,name,config['max_state_bytes'])
        after = self._history_disk_bytes()
        if source is not None:
            _verify_source_checkpoint(captured['metadata'], source)
        image = self._frame_image(image_capture(max_bytes=config['max_image_bytes']),config['max_image_bytes'])
        checkpoint = store(self,manifest,node_id,parent,captured,reserve_bytes=image['size'])
        checkpoint.update(live_disk_bytes_before=before,live_disk_bytes_after=after,
                          live_disk_bytes_growth=None if before is None or after is None else max(0,after-before))
        return checkpoint,image

    def _frame_capability(self, source=None):
        if source == SOURCE_RASTER:
            self._history_supported()
            if not source_timeline_capable(self):
                raise ValueError('Source raster timeline requires native frame stepping and instrumented checkpoints')
            return
        from .qemu_display import DISPLAY_COMMANDS
        from .qemu_clock import VIRTUAL_CLOCK_COMMANDS
        self._history_supported()
        if not (FRAME_COMMANDS | DISPLAY_COMMANDS | VIRTUAL_CLOCK_COMMANDS) <= self.vm.qmp_commands:
            raise ValueError('Renderer frame history requires the native frame fence, display and virtual clock')
        if self.vm.machine_configuration.get('clock_profile',{}).get('profile') != 'virtual':
            raise ValueError('Renderer frame history requires an explicit virtual clock')

    def _frame_stop_after_step(self):
        if getattr(self.vm, '_active_frame_fence', None) is None:
            return False
        context = getattr(self, '_frame_fence_context', None)
        if not context or context['token'] != self.vm._active_frame_fence:
            raise DebuggerError('Renderer frame fence ownership is uncertain')
        receipt = _frame_receipt(self.vm.qmp.call('x-fdisbull-query-display-frame',
            {'token':context['token']}), **context)
        return receipt['state'] != 'armed'

    def _frame_manifest(self, selected=None):
        live = getattr(self,'_qemu_history_live',None)
        selected = selected or (live.get('history') if live else None)
        if selected is None: raise ValueError('Start or attach a renderer timeline first')
        manifest,_ = self._history_latest(selected)
        if manifest.get('history_kind') != KIND:
            raise ValueError('Selected history is not a renderer frame timeline')
        return manifest

    def _frame_summary(self, manifest, artifact=None):
        result = self._history_summary(manifest,artifact)
        delta = self._frame_delta(manifest)
        full_points = sum(n['checkpoint'].get('storage',{}).get('kind','full') == 'full' for n in manifest['nodes'])
        source = manifest['frame_config'].get('frame_source')
        unit = SOURCE_UNIT if source == SOURCE_RASTER else 'completed synchronous renderer update'
        result.update(format=manifest['format'],unit=unit, completed_guest_frame=None,
            timeline=result['history'], point=result['cursor'],
            storage_mode=manifest['frame_config'].get('storage_mode','full'),
            keyframe_interval=manifest['frame_config'].get('keyframe_interval',8),
            frame_config=deepcopy(manifest['frame_config']),
            full_state_points=full_points,delta_state_points=len(manifest['nodes'])-full_points,
            retained_encoded_state_payload_bytes=sum(n['checkpoint']['storage']['payload_size'] if delta
                else n['checkpoint']['size'] for n in manifest['nodes']),
            reconstructed_state_payload_bytes=sum(n['checkpoint']['size'] for n in manifest['nodes']),
            retained_state_metadata_bytes=sum(n['checkpoint']['storage']['metadata_size'] for n in manifest['nodes']) if delta else 0,
            state_bytes_used=self._frame_state_bytes(manifest),storage_bytes_used=self._frame_bytes_used(manifest),
            input_bytes_used=len(json.dumps(manifest.get('input_journal',[]),sort_keys=True,separators=(',',':')).encode()),
            codec_transient_bound_bytes=6*manifest['frame_config']['max_state_bytes']+8*1024**2 if delta else 0,
            image_bytes_used=sum(n['frame']['image']['size'] for n in manifest['nodes']),
            nodes=[dict(id=n['id'],parent=n['parent'],edge=deepcopy(n['edge']),
                        checkpoint=deepcopy(n['checkpoint']),frame=deepcopy(n['frame'])) for n in manifest['nodes']])
        if source == SOURCE_RASTER:
            result['frame_source'] = SOURCE_RASTER
        result['current_dirty'] = bool(manifest.get('input_dirty',False))
        live = getattr(self,'_qemu_history_live',None)
        valid = bool(live and not self.closed and live.get('valid')
            and live.get('history') == manifest.get('_artifact_id')
            and live.get('fingerprint') == self._history_live_fingerprint())
        result['valid'] = valid
        result['cursor'] = result['point'] = live.get('cursor') if valid else None
        return result

    def _frame_budget(self, manifest, parent, count=1, input_reserve=0):
        config = manifest['frame_config']
        if len(manifest['nodes']) + count > min(config['max_frames'], config['max_captures'], MAX_NODES):
            raise ValueError('Renderer timeline capture budget exhausted')
        used = self._frame_bytes_used(manifest)
        remaining = config['max_bytes'] - used
        state_reserve = max(4096, min(MAX_STATE, max(parent['checkpoint']['size'],self._history_disk_bytes() or 0)))
        reserve = count * (state_reserve + config['max_image_bytes']) + input_reserve
        project_used = int(self.project.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
        if remaining < reserve or 256*1024*1024 - project_used < reserve:
            raise ValueError('Renderer timeline cannot reserve checkpoint and image budget')
        return used

    def _frame_image(self, artifact, limit):
        if (not isinstance(artifact,dict) or not isinstance(artifact.get('artifact'),str)
                or not isinstance(artifact.get('sha256'),str) or type(artifact.get('size')) is not int
                or not 1 <= artifact['size'] <= limit):
            raise ValueError('Renderer timeline image receipt exceeds its budget')
        image = {key:artifact[key] for key in ('artifact','sha256','size')}
        _image_row(self,image)
        return image

    def _frame_current(self, manifest):
        live = getattr(self,'_qemu_history_live',None)
        if (not live or not live.get('valid') or live.get('history') != manifest.get('_artifact_id')
                or live.get('cursor') != manifest.get('cursor')
                or live.get('fingerprint') != self._history_live_fingerprint()):
            raise ValueError('Renderer timeline live cursor is invalid; restore an explicit point')
        if manifest.get('pending') is not None:
            raise ValueError('Renderer timeline has an unresolved operation')
        return self._node(manifest,live['cursor'])

    def _history_validate_node_before_restore(self, target):
        frame = target.get('frame')
        if frame is None: return
        if not isinstance(frame,dict) or not isinstance(frame.get('image'),dict):
            raise ValueError('Renderer timeline point lacks its image identity')
        if frame.get('kind') not in ('initial-paused','renderer-update',SOURCE_RASTER) or frame.get('completed_guest_frame') is not None:
            raise ValueError('Renderer timeline point has an invalid publication scope')
        if frame['kind'] == 'renderer-update':
            digest = frame.get('pixel_sha256')
            if (type(frame.get('width')) is not int or type(frame.get('height')) is not int
                    or not 1 <= frame['width'] <= 8192 or not 1 <= frame['height'] <= 8192
                    or frame['width'] * frame['height'] * 3 > 16 * 1024**2
                    or type(frame.get('update_id')) is not int or frame['update_id'] < 1
                    or type(frame.get('published_ns')) is not int or frame['published_ns'] < 0
                    or not isinstance(digest,str) or len(digest) != 64
                    or any(c not in '0123456789abcdef' for c in digest)):
                raise ValueError('Renderer timeline publication identity is invalid')
        row = _image_row(self,frame['image'])
        raster = frame.get('source_raster')
        if frame['kind'] == SOURCE_RASTER:
            validate_source_raster(raster)
            metadata = json.loads(row['metadata'])
            if source_raster_record(metadata.get('native')) != raster:
                raise ValueError('Stored source raster image provenance differs from its timeline point')
        try:
            from PIL import Image
            with Image.open(io.BytesIO(bytes(row['data']))) as image:
                width, height = image.size
                if (image.format != 'PNG' or not 1 <= width <= 8192 or not 1 <= height <= 8192
                        or width * height * 3 > 16 * 1024**2):
                    raise ValueError('Stored timeline image has invalid dimensions or format')
                if frame['kind'] in ('renderer-update', SOURCE_RASTER):
                    expected = raster if frame['kind'] == SOURCE_RASTER else frame
                    if (width,height) != (expected['width'],expected['height']):
                        raise ValueError('Stored timeline image dimensions differ from publication')
                    if hashlib.sha256(image.convert('RGB').tobytes()).hexdigest() != expected['pixel_sha256']:
                        raise ValueError('Stored timeline image pixels differ from publication')
                else:
                    image.verify()
        except ValueError:
            raise
        except Exception as error:
            raise ValueError('Stored timeline image cannot be decoded') from error

    def _history_restore_node_check(self, target):
        frame = target.get('frame')
        if frame is not None:
            from .qemu_frame_keys import FRAME_KEY_COMMANDS
            if FRAME_KEY_COMMANDS <= self.vm.qmp_commands:
                actual = self._frame_keys_query()['held']
                if actual != frame.get('keys',[]):
                    raise DebuggerError('Restored frame key ownership differs from timeline point')
            elif frame.get('keys',[]):
                raise DebuggerError('Restored timeline requires native frame key ownership')
        if frame is None or frame.get('kind') == 'initial-paused': return
        if frame.get('kind') == SOURCE_RASTER:
            historical = frame['source_raster']
            readback = self.frame_rgba(encoding='png', timeout_ms=self._history_remaining_ms())
            live = source_raster_record(readback.metadata['native'])
            if (not _source_record_match(historical, live)
                    or live['stream'] == historical['stream'] or live['epoch'] == historical['epoch']):
                raise DebuggerError('Restored source raster pixels, sampling phase or fresh owner differ')
            return dict(historical=deepcopy(historical), live=live)
        if frame.get('kind') != 'renderer-update':
            raise ValueError('Unknown renderer timeline point kind')
        publication = self.display_observe()
        for key,field in (('update_id','update_id'),('published_ns','published_ns'),('width','width'),('height','height')):
            if publication.get(key) != frame.get(field):
                raise DebuggerError('Restored renderer publication differs: '+field)
        # Export the retained pixels into a private transient file; do not create
        # a new project artifact or re-render while verifying restoration.
        native = publication['native']
        path = Path(self.vm.temporary.name) / ('history-display-'+uuid.uuid4().hex+'.ppm')
        try:
            result = self.vm.qmp.call('x-fdisbull-export-display',{'token':native['token'],'filename':str(path)})
            if result != native:
                raise DebuggerError('Restored renderer changed during pixel readback')
            if not path.is_file() or path.stat().st_size > 16*1024**2 + 128:
                raise DebuggerError('Restored renderer export exceeds its byte budget')
            raw = path.read_bytes()
            header = f"P6\n{frame['width']} {frame['height']}\n255\n".encode('ascii')
            if (not raw.startswith(header) or len(raw) != len(header)+frame['width']*frame['height']*3
                    or hashlib.sha256(raw[len(header):]).hexdigest() != frame['pixel_sha256']):
                raise DebuggerError('Restored renderer pixels differ from timeline point')
        finally:
            path.unlink(missing_ok=True)

    def _frame_execute(self, publication, token):
        owner = getattr(self, '_frame_input_owner', None)
        vm = owner.check().vm if owner is not None else self.vm
        def call(name, *args, **kwargs):
            return owner.call(name, *args, **kwargs) if owner is not None else getattr(self, name)(*args, **kwargs)
        def qmp(command, arguments):
            return owner.qmp(command, arguments, mutating=command != 'x-fdisbull-query-display-frame') if owner is not None else vm.qmp.call(command, arguments)
        from .qemu_video_control import require_no_video_frame_fence
        from .qemu_step_over import require_no_step_over
        if owner is not None:
            owner.invoke(owner.preflights[0], vm, 'renderer-frame advance')
            owner.invoke(owner.preflights[1], vm, 'renderer-frame advance')
        else:
            require_no_video_frame_fence(vm, 'renderer-frame advance')
            require_no_step_over(vm, 'renderer-frame advance')
        native = publication['native']
        display_token, baseline = native['token'], native['updates']
        vm._active_frame_fence = token
        result = None
        try:
            armed = _frame_receipt(qmp('x-fdisbull-arm-display-frame',
                {'token':token,'display-token':display_token}),token=token,display_token=display_token,
                baseline=baseline,epoch=native['epoch'])
            if (armed['state'] != 'armed' or armed['updates'] != baseline
                    or armed['stop-pending'] or armed['stop-consumed']):
                raise DebuggerError('Renderer frame fence was not cleanly armed')
            self._frame_fence_context = dict(token=token,display_token=display_token,
                                             baseline=baseline,epoch=armed['epoch'])
            result = call('_run_with_hooks', timeout_ms=call('_history_remaining_ms'),stop_on_hook=True)
            observed = _frame_receipt(qmp('x-fdisbull-query-display-frame',{'token':token}),
                token=token,display_token=display_token,baseline=baseline,epoch=armed['epoch'])
            final = _frame_receipt(qmp('x-fdisbull-cancel-display-frame',{'token':token}),
                token=token,display_token=display_token,baseline=baseline,epoch=armed['epoch'])
            if observed['state'] != 'completed' and final['state'] != 'cancelled':
                raise DebuggerError('Renderer fence did not cancel its incomplete arm')
            if (observed['state'] == 'completed' and (final['state'] != 'completed'
                    or any(final.get(k) != observed.get(k) for k in
                           ('completed-update-id','published-ns','stop-consumed','stop-pending')))):
                raise DebuggerError('Renderer fence cleanup changed its completed publication')
            if owner is not None: owner.check()
            vm._active_frame_fence = None
            self._frame_fence_context = None
            ordinary = (_ordinary_stop(result) and observed['state'] == 'completed'
                        and observed['stop-pending'] is False and observed['stop-consumed'] is True)
            return result, observed, final, ordinary
        except BaseException as error:
            if result is not None and getattr(error, 'result', None) is None:
                error.result = result
            if owner is None: self.close()
            raise

    def _frame_capture_source(self, manifest, node_id, parent, name, source):
        owner = getattr(self, '_frame_input_owner', None)

        def call(method, *args, **kwargs):
            if owner is not None:
                return owner.call(method, *args, **kwargs)
            return getattr(self, method)(*args, **kwargs)

        config = manifest['frame_config']
        used = call('_frame_bytes_used', manifest)

        def capture_image(*, max_bytes):
            artifact = call('capture_video_frame', 'timeline-source.png', stream=source['stream'],
                frame_id=source['frame_id'], max_bytes=max_bytes, timeout_ms=call('_history_remaining_ms'))
            if source_raster_record(artifact['metadata'].get('native')) != source:
                raise DebuggerError('Captured source raster differs from the selected timeline point')
            return artifact

        if call('_frame_delta', manifest):
            return call('_frame_capture_delta',manifest,node_id,parent,name,capture_image,source=source)
        checkpoint = call('_history_checkpoint',
            remaining_bytes=min(config['max_state_bytes'],config['max_bytes']-used),node_name=name)
        row = call('_history_state_artifact', checkpoint)
        _verify_source_checkpoint(json.loads(row['metadata']), source)
        image_limit = min(config['max_image_bytes'],config['max_bytes']-used-checkpoint['size'])
        if image_limit < 1:
            raise ValueError('Source raster timeline image budget exhausted')
        return checkpoint,call('_frame_image',capture_image(max_bytes=image_limit),image_limit)

    @_timeline_start_operation
    def timeline_start(self, max_frames=16, max_bytes=536870912, max_state_bytes=134217728,
                       max_image_bytes=2097152, max_captures=128, storage_mode='full',
                       keyframe_interval=8, period_ns=16666667, *, timeline=None, frame_source=None, timeout_ms=60000):
        from .qemu_display import validate_display_period
        for value,name,maximum in ((max_frames,'max_frames',MAX_NODES),(max_captures,'max_captures',MAX_NODES),
                (max_bytes,'max_bytes',1024**3),(max_state_bytes,'max_state_bytes',MAX_STATE),
                (max_image_bytes,'max_image_bytes',16*1024**2),(keyframe_interval,'keyframe_interval',128)):
            _positive_int(value,name,1,maximum)
        validate_display_period(period_ns)
        from .debug_timeline import validate_storage
        validate_storage(storage_mode,keyframe_interval)
        if max_state_bytes + max_image_bytes > max_bytes:
            raise ValueError('Renderer timeline byte budget cannot reserve one state and image')
        if frame_source not in (None, 'renderer', SOURCE_RASTER):
            raise ValueError('frame_source must be renderer or source-raster')
        if timeline is not None:
            manifest = self._frame_manifest(timeline)
            stored_source = manifest['frame_config'].get('frame_source', 'renderer')
            if frame_source is not None and frame_source != stored_source:
                raise ValueError('Requested frame_source differs from the stored timeline')
            self._frame_capability(stored_source)
            live = getattr(self,'_qemu_history_live',None)
            if not live or live.get('history_id') != manifest['id']:
                self._qemu_history_live = dict(history=manifest['_artifact_id'],history_id=manifest['id'],
                    cursor=None,valid=False,invalid_reason='attached timeline is not bound to this machine',fingerprint=None)
            return self._frame_summary(manifest)
        owner = input_owner(self) if frame_source == SOURCE_RASTER else None
        source = None
        if owner is not None:
            if period_ns != 16666667:
                raise ValueError('Source raster timing uses the native stream period')
            owner.call('_frame_capability', frame_source)
            owner.call('_history_admission')
            owner.invoke(require_source_checkpoint_schema, owner.vm)
            observed = owner.call('video_frame_observe', timeout_ms=owner.call('_history_remaining_ms'))
            source = source_raster_record(observed.get('native'))
            period_ns = observed['native']['frame']['period-ns']
        else:
            self._frame_capability()
            self._history_admission()
        project_used = int(self.project.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
        if 256*1024*1024 - project_used < max_state_bytes + max_image_bytes:
            raise ValueError('Project artifact budget cannot reserve a frame checkpoint and image')
        initial = self.display_observe() if source is None else None
        history_id = uuid.uuid4().hex
        config = dict(max_frames=max_frames,max_bytes=max_bytes,max_state_bytes=max_state_bytes,
            max_image_bytes=max_image_bytes,max_captures=max_captures,period_ns=period_ns,
            storage_mode=storage_mode,keyframe_interval=keyframe_interval)
        if source is not None:
            config['frame_source'] = SOURCE_RASTER
        from .qemu_frame_storage import FORMAT as DELTA_FORMAT
        identity = owner.call('_history_identity') if owner else self._history_identity()
        manifest = dict(format=DELTA_FORMAT if storage_mode == 'delta' else FORMAT,id=history_id,revision=0,parent_manifest=None,
            identity=identity,max_steps=min(max_frames,max_captures,MAX_NODES),
            max_bytes=max_bytes,nodes=[],head=None,cursor=None,live_cursor_valid=False,
            invalid_reason=None,pending=dict(kind='source-raster-root' if source else 'renderer-root',started=time.time_ns()),
            history_kind=KIND,frame_config=config)
        if owner is not None:
            owner.intent_written = True
            manifest,_ = owner.call('_history_new_revision', manifest,pending=manifest['pending'])
        else:
            manifest,_ = self._history_new_revision(manifest,pending=manifest['pending'])
        try:
            with self._history_internal():
                node_id = uuid.uuid4().hex
                if source is not None:
                    checkpoint,image = owner.call('_frame_capture_source',manifest,node_id,None,
                        f'frame-{history_id[:8]}-root.qcow2',source)
                else:
                    if initial.get('state') != 'observing':
                        self.display_start(period_ns=period_ns)
                    else:
                        config['period_ns'] = initial['observation_period_ns']
                        manifest['frame_config'] = deepcopy(config)
                if source is None and self._frame_delta(manifest):
                    checkpoint,image = self._frame_capture_delta(manifest,node_id,None,
                        f'frame-{history_id[:8]}-root.qcow2',lambda **kw:self.capture_surface('frame-root.png',**kw))
                elif source is None:
                    checkpoint = self._history_checkpoint(remaining_bytes=max_state_bytes,
                        node_name=f'frame-{history_id[:8]}-root.qcow2')
                    image = self._frame_image(self.capture_surface('frame-root.png',max_bytes=max_image_bytes),max_image_bytes)
                keys = owner.call('_timeline_frame_keys') if owner else self._timeline_frame_keys()
                registers = owner.call('registers') if owner else self.registers()
                frame = dict(kind=SOURCE_RASTER if source is not None else 'initial-paused',
                    image=image,keys=keys,completed_guest_frame=None)
                if source is not None:
                    frame['source_raster'] = source
                manifest['nodes'].append(dict(id=node_id,parent=None,checkpoint=checkpoint,
                    edge=dict(kind='root',completed_instruction=False),registers=registers,created=time.time_ns(),
                    frame=frame))
                manifest.update(head=node_id,cursor=node_id,live_cursor_valid=True,pending=None)
                if owner is not None:
                    new,artifact = owner.call('_history_new_revision', manifest)
                    owner.intent_written = False
                    return owner.call('_frame_summary', new, artifact['artifact'])
                new,artifact = self._history_new_revision(manifest)
                return self._frame_summary(new,artifact['artifact'])
        except BaseException:
            if owner is None:
                self.close()
            raise

    @_history_operation
    def timeline_status(self, *, timeline=None):
        live = getattr(self,'_qemu_history_live',None)
        if timeline is None and not live:
            return dict(format=FORMAT,timeline=None,valid=False,cursor=None,retained_nodes=0,
                        unit='completed synchronous renderer update',completed_guest_frame=None)
        return self._frame_summary(self._frame_manifest(timeline))

    @frame_input_operation
    def timeline_advance(self, frames=1, inputs=None, timeout_ms=60000):
        owner = input_owner(self)
        _positive_int(frames,'frames',1,MAX_NODES)
        from .debug_timeline import validate_schedule
        from .qemu_frame_keys import _edges, _input_journal_budget, resolve_batch_intent
        validate_schedule(inputs,frames)
        schedule = {item['frame']:item['edges'] for item in (inputs or [])}
        manifest = owner.call('_frame_manifest', )
        source_timeline = manifest['frame_config'].get('frame_source') == SOURCE_RASTER
        if source_timeline:
            owner.call('_frame_capability', SOURCE_RASTER)
        else:
            owner.call('_frame_capability')
        parent = owner.call('_frame_current', manifest)
        if owner.call('_frame_delta', manifest):
            from .qemu_frame_storage import materialize
            owner.invoke(materialize,self,manifest,parent)
            owner.call('_history_validate_node_before_restore', parent)
        owner.call('_frame_budget', manifest,parent,frames,
                           input_reserve=INPUT_RECEIPT_RESERVE * sum(bool(v) for v in schedule.values()))
        owner.call('_history_admission', )
        if schedule:
            if not hasattr(self,'_frame_keys_query'):
                raise ValueError('Native frame key ownership is unavailable')
            native = owner.call('_frame_keys_query', )
            simulated = native['held']
            for index in range(frames):
                _, simulated = _edges(schedule.get(index,[]),simulated)
            owner.invoke(_input_journal_budget,self,manifest,sum(bool(v) for v in schedule.values()))
        records = []
        def input_refused(reason):
            output = owner.call('_frame_summary', manifest)
            output.update(outcome='input_refused',
                pending_inputs=deepcopy(manifest.get('pending_inputs',[])),
                completed_frames=len(records), recorded_frames=len(records),
                frames=deepcopy(records), reason=reason)
            return output
        for index in range(frames):
            owner.call('_history_admission', )
            edge_list = schedule.get(index,[])
            key_receipt = planned = None
            if edge_list:
                native, converted, next_held = owner.call('_frame_keys_prepare', edge_list)
                if not batch_capability(owner.vm) and len(converted) > native['edge-capacity']:
                    return input_refused('Native frame key edge capacity is unavailable')
                try:
                    planned = plan_batch(self, native, converted, next_held)
                except (VerifiedBatchRefusal, InputReceiptBudgetError) as refusal:
                    return input_refused(str(refusal))
            if source_timeline:
                publication = owner.call('video_frame_observe', timeout_ms=owner.call('_history_remaining_ms'))
                current = source_raster_record(publication.get('native'))
                if not _source_record_match(parent['frame']['source_raster'], current):
                    raise ValueError('Live source raster does not match the timeline cursor')
                baseline = current['frame_id']
            else:
                publication = owner.call('display_observe')
                if publication.get('state') != 'observing':
                    raise ValueError('Renderer observation window is not active')
                baseline = publication['native']['updates']
            token = uuid.uuid4().hex
            kind = SOURCE_RASTER if source_timeline else 'renderer-frame'
            owner.intent_written = True
            owner.call('_history_pending', manifest,parent['id'],kind,receipt=dict(token=token,baseline=baseline))
            pending = deepcopy(manifest['pending'])
            try:
                if edge_list:
                    key_receipt = owner.call('_frame_keys_apply', native,converted,next_held,planned=planned)
                    manifest.setdefault('input_journal',[]).append(deepcopy(key_receipt))
                    manifest.setdefault('pending_inputs',[]).append(deepcopy(key_receipt))
                    manifest['input_dirty'] = True
                    owner.call('_history_pending', manifest,parent['id'],kind,receipt=dict(
                        token=token,baseline=baseline,input=deepcopy(key_receipt)))
                if source_timeline:
                    advance = owner.call('video_frame_advance',
                        timeout_ms=owner.call('_history_remaining_ms'),stop_on_hook=True)
                    result, final, ordinary = advance['native_result'], advance['fence'], advance['advance_completed']
                else:
                    result, observed, final, ordinary = owner.call('_frame_execute', publication,token)
                if not ordinary:
                    result = deepcopy(result)
                    if source_timeline:
                        result['source_raster_fence'] = deepcopy(final)
                    else:
                        result['renderer_frame_fence'] = dict(
                            observed=deepcopy(observed), final=deepcopy(final),
                            publication_completed=observed['state'] == 'completed',
                            ordinary_stop=False)
                    stopped = owner.call('_history_resolve_known_stop', result,f'{kind} publication interrupted',
                        records=records,requested_count=frames)
                    output = owner.call('_frame_summary', owner.call('_frame_manifest', stopped['history']))
                    output.update(pending_inputs=deepcopy(manifest.get('pending_inputs',[])),completed_frames=len(records),recorded_frames=len(records),
                                  frames=records,stop=deepcopy(result),
                                  outcome='interrupted')
                    return output
                node_id = uuid.uuid4().hex
                name = f"frame-{manifest['id'][:8]}-{len(manifest['nodes'])+1:04d}.qcow2"
                if source_timeline:
                    after = advance['source']['after']
                    source = source_raster_record(after)
                    if (source['stream'] != current['stream'] or source['epoch'] != current['epoch']
                            or source['frame_id'] != baseline + 1 or after['frame'] != advance['frame']
                            or advance['stop_consumed'] is not True):
                        raise DebuggerError('Source raster differs from its completed timeline fence')
                    checkpoint,image = owner.call('_frame_capture_source', manifest,node_id,parent,name,source)
                    frame = dict(kind=SOURCE_RASTER,image=image,source_raster=source)
                else:
                    after = owner.call('display_observe')
                    if (after.get('update_id') != observed['completed-update-id']
                            or after.get('published_ns') != observed['published-ns']):
                        raise DebuggerError('Renderer publication differs from frame fence')
                    checkpoint,image,metadata = self._frame_capture_renderer(owner,manifest,node_id,parent,name)
                    frame = dict(kind='renderer-update',image=image,update_id=after['update_id'],
                        published_ns=after['published_ns'],width=after['width'],height=after['height'],
                        pixel_sha256=metadata['pixel_sha256'])
                frame.update(keys=owner.call('_timeline_frame_keys'),input=deepcopy(key_receipt),
                             completed_guest_frame=None)
                manifest['nodes'].append(dict(id=node_id,parent=parent['id'],checkpoint=checkpoint,
                    edge=dict(kind=frame['kind'],stop=deepcopy(result),fence=final,completed_instruction=None),
                    registers=owner.call('registers'),created=time.time_ns(),frame=frame))
                manifest.update(head=node_id,cursor=node_id,live_cursor_valid=True,pending=None,
                                invalid_reason=None,input_dirty=False,pending_inputs=[])
                manifest,artifact = owner.call('_history_new_revision', manifest)
                owner.intent_written = False
                records.append(dict(point=node_id,parent=parent['id'],frame=deepcopy(frame),history=artifact['artifact']))
                parent = manifest['nodes'][-1]
            except VerifiedBatchRefusal as refusal:
                resolve_batch_intent(self, manifest, pending)
                return input_refused(str(refusal))
            except BaseException as error:
                if key_receipt is not None and getattr(error, 'result', None) is None:
                    error.result = deepcopy(key_receipt)
                raise
        output = owner.call('_frame_summary', manifest)
        output.update(outcome='completed',completed_frames=len(records),frames=records)
        return output

    def _frame_capture_renderer(self, owner, manifest, node_id, parent, name):
        config = manifest['frame_config']
        used = owner.call('_frame_bytes_used', manifest)
        if owner.call('_frame_delta', manifest):
            checkpoint,image = owner.call('_frame_capture_delta', manifest,node_id,parent,name,
                lambda **kw:owner.call('capture_display','timeline-frame.png',**kw))
            return checkpoint,image,json.loads(_image_row(self,image)['metadata'])
        checkpoint = owner.call('_history_checkpoint',
            remaining_bytes=min(config['max_state_bytes'],config['max_bytes']-used),node_name=name)
        image_limit = min(config['max_image_bytes'],config['max_bytes']-used-checkpoint['size'])
        if image_limit < 1:
            raise ValueError('Renderer timeline image budget exhausted')
        captured = owner.call('capture_display', 'timeline-frame.png',max_bytes=image_limit)
        return checkpoint,owner.call('_frame_image', captured,image_limit),captured['metadata']

    @_history_operation
    def timeline_rewind(self, frames=1, policy=None, *, timeline=None, point=None, timeout_ms=60000):
        if policy not in (None,{}): raise ValueError('Renderer timeline partial-state preservation is unsupported')
        if type(frames) is not int or not 0 <= frames <= MAX_NODES:
            raise ValueError('frames must be an integer in 0..128')
        manifest = self._frame_manifest(timeline)
        if point is not None:
            target = self._node(manifest,point)
            if target is None: raise ValueError('Unknown renderer timeline point')
        else:
            current = self._frame_current(manifest)
            chain = self._ancestors(manifest,current['id'])
            if frames >= len(chain): raise ValueError('Renderer timeline rewind exceeds available points')
            target = chain[frames]
        self._history_validate_node_before_restore(target)
        restored = self.rewind(history=manifest['_artifact_id'],node=target['id'],timeout_ms=self._history_remaining_ms())
        updated = self._frame_manifest(restored['history'])
        result = self._frame_summary(updated)
        result.update(rewound_frames=frames,restore=restored,completed_guest_frame=None)
        return result

    @_history_operation
    def timeline_image(self, name='frame.png', *, timeline=None, point=None):
        from .external_files import _file_name
        _file_name(name)
        manifest = self._frame_manifest(timeline)
        node = self._node(manifest,point or manifest.get('cursor'))
        if node is None: raise ValueError('Unknown renderer timeline point')
        frame = node['frame']
        row = _image_row(self,frame['image'])
        result = dict(artifact=row['id'],sha256=row['sha256'],size=len(row['data']),
                      point=node['id'],stored_frame=True,completed_guest_frame=None)
        if frame['kind'] == SOURCE_RASTER:
            self._history_validate_node_before_restore(node)
            result['source_raster'] = deepcopy(frame['source_raster'])
        return result

    @_history_operation
    def timeline_pin(self, name='frame.qcow2'):
        from .external_files import _file_name
        _file_name(name)
        manifest = self._frame_manifest()
        if manifest.get('input_dirty'): raise ValueError('Restore or capture dirty frame input before pinning')
        node = self._frame_current(manifest)
        if self._frame_delta(manifest):
            checkpoint = self._history_prepare_restore(manifest,node)
            self._history_validate_node_before_restore(node)
            return self._artifact(name,'state',checkpoint['data'],checkpoint['metadata'])
        row = self._history_state_artifact(node['checkpoint'])
        metadata = json.loads(row['metadata'])
        if node['frame']['kind'] == SOURCE_RASTER:
            _verify_source_checkpoint(metadata, node['frame']['source_raster'])
            self._history_validate_node_before_restore(node)
        return self._artifact(name,'state',bytes(row['data']),metadata)

    def _timeline_frame_keys(self):
        from .qemu_frame_keys import FRAME_KEY_COMMANDS
        if FRAME_KEY_COMMANDS <= self.vm.qmp_commands:
            return list(self._frame_keys_query()['held'])
        return []

    def _history_restore_manifest_updates(self, target, manifest):
        if target.get('frame') is not None:
            manifest['input_dirty'] = False
            manifest['pending_inputs'] = []

    @_history_operation
    def timeline_stop(self):
        manifest = self._frame_manifest()
        result = self._frame_summary(manifest)
        self._qemu_history_live = None
        return dict(result,stopped=True,target_executed=False,input_state_changed=False)

    @source_frame_advance_route
    @_history_operation
    def advance_frames(self, frames=1, timeout_ms=60000):
        _positive_int(frames,'frames',1,MAX_NODES)
        self._frame_capability()
        self._history_admission()
        initial = self.display_observe()
        live = getattr(self,'_qemu_history_live',None)
        if live and live.get('valid'):
            live.update(valid=False,cursor=None,invalid_reason='unrecorded renderer advancement')
        records = []
        with self._history_internal():
            if initial.get('state') != 'observing':
                self.display_start(period_ns=16666667)
            for _ in range(frames):
                publication = self.display_observe()
                if publication.get('state') != 'observing':
                    raise ValueError('Renderer observation window is not active')
                result, observed, final, ordinary = self._frame_execute(publication,uuid.uuid4().hex)
                receipt = dict(stop=deepcopy(result),fence=deepcopy(final),ordinary=ordinary)
                try:
                    self._event('machine-frame-advance',receipt)
                except BaseException as error:
                    error.result = receipt
                    self.close()
                    raise
                if not ordinary:
                    return dict(format=FORMAT,outcome='interrupted',completed_frames=len(records),
                                frames=records,stop=deepcopy(result),completed_guest_frame=None)
                records.append(dict(update_id=observed['completed-update-id'],
                    published_ns=observed['published-ns'],fence=final))
        return dict(format=FORMAT,outcome='completed',completed_frames=len(records),frames=records,
                    unit='completed synchronous renderer update',completed_guest_frame=None)
