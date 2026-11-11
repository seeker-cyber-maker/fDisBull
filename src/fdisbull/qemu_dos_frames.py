"""Persistent stopped QEMU renderer-publication histories.

A renderer publication is not proof of a completed guest drawing frame, VGA
vertical retrace, physical scanout, or input consumption.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import time
import uuid

from .qemu_dos_history import (FORMAT, MAX_NODES, MAX_STATE, _history_operation,
                               _positive_int, _sha)
from .dosbox_rpc import DebuggerError

FRAME_COMMANDS = frozenset({'x-fdisbull-arm-display-frame',
    'x-fdisbull-query-display-frame', 'x-fdisbull-cancel-display-frame'})
KIND = 'renderer-frames'


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

    def _frame_capability(self):
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
        result.update(unit='completed synchronous renderer update', completed_guest_frame=None,
            timeline=result['history'], point=result['cursor'],
            storage_mode='full', frame_config=deepcopy(manifest['frame_config']),
            image_bytes_used=sum(n['frame']['image']['size'] for n in manifest['nodes']),
            nodes=[dict(id=n['id'],parent=n['parent'],edge=deepcopy(n['edge']),
                        checkpoint=deepcopy(n['checkpoint']),frame=deepcopy(n['frame'])) for n in manifest['nodes']])
        live = getattr(self,'_qemu_history_live',None)
        valid = bool(live and not self.closed and live.get('valid')
            and live.get('history') == manifest.get('_artifact_id')
            and live.get('fingerprint') == self._history_live_fingerprint())
        result['valid'] = valid
        result['cursor'] = result['point'] = live.get('cursor') if valid else None
        return result

    def _frame_budget(self, manifest, parent, count=1):
        config = manifest['frame_config']
        if len(manifest['nodes']) + count > min(config['max_frames'], config['max_captures'], MAX_NODES):
            raise ValueError('Renderer timeline capture budget exhausted')
        used = sum(n['checkpoint']['size'] + n['frame']['image']['size'] for n in manifest['nodes'])
        remaining = config['max_bytes'] - used
        state_reserve = max(4096, min(MAX_STATE, max(parent['checkpoint']['size'],self._history_disk_bytes() or 0)))
        reserve = count * (state_reserve + config['max_image_bytes'])
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
        if frame.get('kind') not in ('initial-paused','renderer-update') or frame.get('completed_guest_frame') is not None:
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
        try:
            from PIL import Image
            with Image.open(io.BytesIO(bytes(row['data']))) as image:
                width, height = image.size
                if (image.format != 'PNG' or not 1 <= width <= 8192 or not 1 <= height <= 8192
                        or width * height * 3 > 16 * 1024**2):
                    raise ValueError('Stored timeline image has invalid dimensions or format')
                if frame['kind'] == 'renderer-update':
                    if (width,height) != (frame['width'],frame['height']):
                        raise ValueError('Stored timeline image dimensions differ from publication')
                    if hashlib.sha256(image.convert('RGB').tobytes()).hexdigest() != frame['pixel_sha256']:
                        raise ValueError('Stored timeline image pixels differ from publication')
                else:
                    image.verify()
        except ValueError:
            raise
        except Exception as error:
            raise ValueError('Stored timeline image cannot be decoded') from error

    def _history_restore_node_check(self, target):
        frame = target.get('frame')
        if frame is None or frame.get('kind') == 'initial-paused': return
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
        native = publication['native']
        display_token, baseline = native['token'], native['updates']
        self.vm._active_frame_fence = token
        result = None
        try:
            armed = _frame_receipt(self.vm.qmp.call('x-fdisbull-arm-display-frame',
                {'token':token,'display-token':display_token}),token=token,display_token=display_token,
                baseline=baseline,epoch=native['epoch'])
            if (armed['state'] != 'armed' or armed['updates'] != baseline
                    or armed['stop-pending'] or armed['stop-consumed']):
                raise DebuggerError('Renderer frame fence was not cleanly armed')
            self._frame_fence_context = dict(token=token,display_token=display_token,
                                             baseline=baseline,epoch=armed['epoch'])
            result = self._run_with_hooks(timeout_ms=self._history_remaining_ms(),stop_on_hook=True)
            observed = _frame_receipt(self.vm.qmp.call('x-fdisbull-query-display-frame',{'token':token}),
                token=token,display_token=display_token,baseline=baseline,epoch=armed['epoch'])
            final = _frame_receipt(self.vm.qmp.call('x-fdisbull-cancel-display-frame',{'token':token}),
                token=token,display_token=display_token,baseline=baseline,epoch=armed['epoch'])
            if observed['state'] != 'completed' and final['state'] != 'cancelled':
                raise DebuggerError('Renderer fence did not cancel its incomplete arm')
            if (observed['state'] == 'completed' and (final['state'] != 'completed'
                    or any(final.get(k) != observed.get(k) for k in
                           ('completed-update-id','published-ns','stop-consumed','stop-pending')))):
                raise DebuggerError('Renderer fence cleanup changed its completed publication')
            self.vm._active_frame_fence = None
            self._frame_fence_context = None
            ordinary = (_ordinary_stop(result) and observed['state'] == 'completed'
                        and observed['stop-pending'] is False and observed['stop-consumed'] is True)
            return result, observed, final, ordinary
        except BaseException as error:
            if result is not None and getattr(error, 'result', None) is None:
                error.result = result
            self.close()
            raise

    @_history_operation
    def timeline_start(self, max_frames=16, max_bytes=536870912, max_state_bytes=134217728,
                       max_image_bytes=2097152, max_captures=128, storage_mode='full',
                       keyframe_interval=8, period_ns=16666667, *, timeline=None, timeout_ms=60000):
        from .qemu_display import validate_display_period
        for value,name,maximum in ((max_frames,'max_frames',MAX_NODES),(max_captures,'max_captures',MAX_NODES),
                (max_bytes,'max_bytes',1024**3),(max_state_bytes,'max_state_bytes',MAX_STATE),
                (max_image_bytes,'max_image_bytes',16*1024**2),(keyframe_interval,'keyframe_interval',128)):
            _positive_int(value,name,1,maximum)
        validate_display_period(period_ns)
        if storage_mode != 'full': raise ValueError('Renderer timeline supports full checkpoints only')
        if max_state_bytes + max_image_bytes > max_bytes:
            raise ValueError('Renderer timeline byte budget cannot reserve one state and image')
        self._frame_capability()
        if timeline is not None:
            manifest = self._frame_manifest(timeline)
            live = getattr(self,'_qemu_history_live',None)
            if not live or live.get('history_id') != manifest['id']:
                self._qemu_history_live = dict(history=manifest['_artifact_id'],history_id=manifest['id'],
                    cursor=None,valid=False,invalid_reason='attached timeline is not bound to this machine',fingerprint=None)
            return self._frame_summary(manifest)
        self._history_admission()
        project_used = int(self.project.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
        if 256*1024*1024 - project_used < max_state_bytes + max_image_bytes:
            raise ValueError('Project artifact budget cannot reserve a frame checkpoint and image')
        initial = self.display_observe()
        history_id = uuid.uuid4().hex
        config = dict(max_frames=max_frames,max_bytes=max_bytes,max_state_bytes=max_state_bytes,
            max_image_bytes=max_image_bytes,max_captures=max_captures,period_ns=period_ns)
        manifest = dict(format=FORMAT,id=history_id,revision=0,parent_manifest=None,
            identity=self._history_identity(),max_steps=min(max_frames,max_captures,MAX_NODES),
            max_bytes=max_bytes,nodes=[],head=None,cursor=None,live_cursor_valid=False,
            invalid_reason=None,pending=dict(kind='renderer-root',started=time.time_ns()),
            history_kind=KIND,frame_config=config)
        manifest,_ = self._history_new_revision(manifest,pending=manifest['pending'])
        try:
            with self._history_internal():
                if initial.get('state') != 'observing':
                    publication = self.display_start(period_ns=period_ns)
                else:
                    publication = initial
                    config['period_ns'] = publication['observation_period_ns']
                    manifest['frame_config'] = deepcopy(config)
                checkpoint = self._history_checkpoint(remaining_bytes=max_state_bytes,
                    node_name=f'frame-{history_id[:8]}-root.qcow2')
                image = self._frame_image(self.capture_surface('frame-root.png',max_bytes=max_image_bytes),max_image_bytes)
                node_id = uuid.uuid4().hex
                manifest['nodes'].append(dict(id=node_id,parent=None,checkpoint=checkpoint,
                    edge=dict(kind='root',completed_instruction=False),registers=self.registers(),created=time.time_ns(),
                    frame=dict(kind='initial-paused',image=image,completed_guest_frame=None)))
                manifest.update(head=node_id,cursor=node_id,live_cursor_valid=True,pending=None)
                new,artifact = self._history_new_revision(manifest)
                return self._frame_summary(new,artifact['artifact'])
        except BaseException:
            self.close(); raise

    @_history_operation
    def timeline_status(self, *, timeline=None):
        live = getattr(self,'_qemu_history_live',None)
        if timeline is None and not live:
            return dict(format=FORMAT,timeline=None,valid=False,cursor=None,retained_nodes=0,
                        unit='completed synchronous renderer update',completed_guest_frame=None)
        return self._frame_summary(self._frame_manifest(timeline))

    @_history_operation
    def timeline_advance(self, frames=1, inputs=None, timeout_ms=60000):
        _positive_int(frames,'frames',1,MAX_NODES)
        if inputs not in (None,[]): raise ValueError('Renderer timeline does not support frame input edges')
        self._frame_capability()
        manifest = self._frame_manifest()
        parent = self._frame_current(manifest)
        self._frame_budget(manifest,parent,frames)
        self._history_admission()
        records = []
        with self._history_internal():
            for _ in range(frames):
                self._history_admission()
                publication = self.display_observe()
                if publication.get('state') != 'observing': raise ValueError('Renderer observation window is not active')
                token = uuid.uuid4().hex
                baseline = publication['native']['updates']
                self._history_pending(manifest,parent['id'],'renderer-frame',receipt=dict(token=token,baseline=baseline))
                try:
                    result, observed, final, ordinary = self._frame_execute(publication,token)
                    if not ordinary:
                        result = deepcopy(result)
                        result['renderer_frame_fence'] = dict(
                            observed=deepcopy(observed), final=deepcopy(final),
                            publication_completed=observed['state'] == 'completed',
                            ordinary_stop=False)
                        stopped = self._history_resolve_known_stop(result,'renderer publication interrupted',
                            records=records,requested_count=frames)
                        output = self._frame_summary(self._frame_manifest(stopped['history']))
                        output.update(completed_frames=len(records),recorded_frames=len(records),
                                      frames=records,stop=deepcopy(result),
                                      outcome='interrupted')
                        return output
                    after = self.display_observe()
                    if (after.get('update_id') != observed['completed-update-id']
                            or after.get('published_ns') != observed['published-ns']):
                        raise DebuggerError('Renderer publication differs from frame fence')
                    config = manifest['frame_config']
                    used = sum(n['checkpoint']['size']+n['frame']['image']['size'] for n in manifest['nodes'])
                    checkpoint = self._history_checkpoint(remaining_bytes=min(config['max_state_bytes'],config['max_bytes']-used),
                        node_name=f"frame-{manifest['id'][:8]}-{len(manifest['nodes'])+1:04d}.qcow2")
                    image_limit = min(config['max_image_bytes'],config['max_bytes']-used-checkpoint['size'])
                    if image_limit < 1: raise ValueError('Renderer timeline image budget exhausted')
                    captured = self.capture_display('timeline-frame.png',max_bytes=image_limit)
                    image = self._frame_image(captured,image_limit)
                    metadata = captured['metadata']
                    frame = dict(kind='renderer-update',image=image,update_id=after['update_id'],
                        published_ns=after['published_ns'],width=after['width'],height=after['height'],
                        pixel_sha256=metadata['pixel_sha256'],completed_guest_frame=None)
                    node_id = uuid.uuid4().hex
                    manifest['nodes'].append(dict(id=node_id,parent=parent['id'],checkpoint=checkpoint,
                        edge=dict(kind='renderer-update',stop=deepcopy(result),fence=final,completed_instruction=None),
                        registers=self.registers(),created=time.time_ns(),frame=frame))
                    manifest.update(head=node_id,cursor=node_id,live_cursor_valid=True,pending=None,invalid_reason=None)
                    manifest,artifact = self._history_new_revision(manifest)
                    records.append(dict(point=node_id,parent=parent['id'],frame=deepcopy(frame),history=artifact['artifact']))
                    parent = manifest['nodes'][-1]
                except BaseException:
                    self.close(); raise
        output = self._frame_summary(manifest)
        output.update(completed_frames=len(records),frames=records)
        return output

    @_history_operation
    def timeline_rewind(self, frames=1, policy=None, *, timeline=None, point=None, timeout_ms=60000):
        if policy not in (None,{}): raise ValueError('Renderer timeline partial-state preservation is unsupported')
        _positive_int(frames,'frames',1,MAX_NODES)
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
        row = _image_row(self,node['frame']['image'])
        return dict(artifact=row['id'],sha256=row['sha256'],size=len(row['data']),
                    point=node['id'],stored_frame=True,completed_guest_frame=None)

    @_history_operation
    def timeline_pin(self, name='frame.qcow2'):
        from .external_files import _file_name
        _file_name(name)
        manifest = self._frame_manifest()
        node = self._frame_current(manifest)
        row = self._history_state_artifact(node['checkpoint'])
        return self._artifact(name,'state',bytes(row['data']),json.loads(row['metadata']))

    @_history_operation
    def timeline_stop(self):
        manifest = self._frame_manifest()
        result = self._frame_summary(manifest)
        self._qemu_history_live = None
        return dict(result,stopped=True,target_executed=False,input_state_changed=False)

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
