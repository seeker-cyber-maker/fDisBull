"""Full-checkpoint CHIP-8 histories at owned native 60 Hz sample stops."""
from copy import deepcopy
import hashlib
import io
import json
import time
import uuid
from PIL import Image

from .chip8_history import Chip8HistoryMixin, FRAME_SUBSET
from .chip8_keys import KEY_SUBSET,KEY_ENV,validate_schedule,_edges
from .qemu_dos_history import _history_operation, _positive_int, _sha, MAX_NODES, MAX_STATE
from .dosbox_rpc import DebuggerError

FORMAT='fdisbull-qemu-chip8-frames-v1'
KEY_FORMAT='fdisbull-qemu-chip8-frames-v2'
from .chip8_frame_storage import FORMAT as DELTA_FORMAT
KIND='chip8-60hz-samples'
MODEL='fdisbull-chip8-native-frame-sample-1'
ENV='fdisbull-chip8-display-keypad-timers-rng-layers-frames-4'
PERIOD=16666667


class Chip8FramesMixin:
    @classmethod
    def _validate_manifest(cls,manifest):
        if isinstance(manifest,dict) and manifest.get('format')==DELTA_FORMAT:
            from .chip8_frame_storage import validate_manifest
            return validate_manifest(manifest)
        if not isinstance(manifest,dict) or manifest.get('format') not in (FORMAT,KEY_FORMAT):
            return Chip8HistoryMixin._validate_manifest(manifest)
        copied=dict(manifest,format=Chip8HistoryMixin.HISTORY_FORMAT)
        Chip8HistoryMixin._validate_manifest(copied)
        runtime=manifest.get('identity',{}).get('runtime',{})
        expected_format=KEY_FORMAT if runtime.get('cpu_subset')==KEY_SUBSET else FORMAT if runtime.get('cpu_subset')==FRAME_SUBSET else None
        if manifest['format']!=expected_format:raise ValueError('CHIP-8 frame format and runtime differ')
        config=manifest.get('frame_config')
        if manifest.get('history_kind')!=KIND or not isinstance(config,dict):raise ValueError('Invalid CHIP-8 frame timeline')
        for key,maximum in (('max_frames',MAX_NODES),('max_captures',MAX_NODES),('max_bytes',1024**3),
                            ('max_state_bytes',MAX_STATE),('max_image_bytes',16*1024**2)):
            _positive_int(config.get(key),key,1,maximum)
        if config.get('storage_mode')!='full' or config.get('period_ns')!=PERIOD:raise ValueError('Invalid CHIP-8 frame configuration')
        if manifest['max_steps']!=min(config['max_frames'],config['max_captures']) or manifest['max_bytes']!=config['max_bytes']:
            raise ValueError('CHIP-8 timeline configuration differs from budget')
        if len(manifest['nodes'])>min(config['max_frames'],config['max_captures']):raise ValueError('CHIP-8 timeline capture budget exceeded')
        used=0
        if manifest['format']==KEY_FORMAT:
            if (not isinstance(manifest.get('input_journal'),list) or len(manifest['input_journal'])>1024 or
                    not isinstance(manifest.get('pending_inputs'),list) or type(manifest.get('input_dirty')) is not bool):
                raise ValueError('Invalid CHIP-8 frame input journal')
            pending=manifest['pending_inputs'];journal=manifest['input_journal']
            if len(pending)>len(journal) or pending and pending!=journal[-len(pending):] or manifest['input_dirty']!=bool(pending):
                raise ValueError('Invalid CHIP-8 pending input journal')
            used+=len(json.dumps(journal,sort_keys=True,separators=(',',':')).encode())
        for index,node in enumerate(manifest['nodes']):
            frame=node.get('frame')
            if (not isinstance(frame,dict) or frame.get('kind')!=('initial-paused' if index==0 else 'native-60hz-sample')
                    or frame.get('completed_guest_frame') is not None or not isinstance(frame.get('image'),dict)):
                raise ValueError('Invalid CHIP-8 frame point')
            if manifest['format']==KEY_FORMAT:
                keys=frame.get('keys')
                if not isinstance(keys,list) or any(not isinstance(k,str) or len(k)!=1 or k not in '0123456789abcdef' for k in keys) or keys!=sorted(set(keys)):
                    raise ValueError('Invalid CHIP-8 frame owned keys')
            image=frame['image'];cp=node['checkpoint']
            if (type(image.get('size')) is not int or not 1<=image['size']<=config['max_image_bytes'] or
                    cp['size']>config['max_state_bytes']):raise ValueError('CHIP-8 timeline point exceeds its budget')
            used+=cp['size']+image['size']
            if index:
                for key in ('virtual_ticks','sampled_ns','stopped_ns','phase_numerator','next_deadline_ns','state_generation','frame_generation','baseline_deadline_ns','baseline_phase'):
                    if type(frame.get(key)) is not int or not 0<=frame[key]<2**64:raise ValueError('Invalid CHIP-8 sample '+key)
                if (frame['phase_numerator']>=60 or frame['baseline_phase']>=60 or frame['virtual_ticks']<1 or
                        frame['stopped_ns']<frame['sampled_ns'] or frame['sampled_ns']<frame['baseline_deadline_ns']):
                    raise ValueError('Invalid CHIP-8 sample timing')
                phase=frame['baseline_phase'];next_phase=phase-20 if phase>=20 else phase+40
                interval=16666667 if phase>=20 else 16666666
                if frame['phase_numerator']!=next_phase or frame['next_deadline_ns']!=frame['baseline_deadline_ns']+interval:
                    raise ValueError('Invalid CHIP-8 sample recurrence')
        if used>config['max_bytes']:raise ValueError('CHIP-8 timeline exceeds its byte budget')

    def _history_summary(self,manifest,artifact=None):
        result=super()._history_summary(manifest,artifact)
        result['format']=manifest['format']
        if manifest['format']==DELTA_FORMAT:
            result['state_bytes_used']=sum(self._frame_state_size(node,manifest) for node in manifest['nodes'])
            result['reconstructed_state_bytes']=sum(node['checkpoint']['size'] for node in manifest['nodes'])
        return result

    def _frame_capability(self):
        self._history_supported()
        if self.identity.get('cpu_subset') not in (FRAME_SUBSET,KEY_SUBSET) or not self.capabilities.get('frame_timeline'):
            raise ValueError('CHIP-8 frame timeline requires v5 and a checkpoint tool')

    def _chip8_frame_query(self,token=None):
        args={} if token is None else {'token':token}
        info=self.vm.qmp.call('query-chip8-frame',args)
        if (not isinstance(info,dict) or info.get('model')!=MODEL or info.get('subset')!=self.identity['cpu_subset']
                or info.get('environment-model')!=(KEY_ENV if self.identity['cpu_subset']==KEY_SUBSET else ENV) or info.get('state') not in ('idle','armed','completed')):
            raise DebuggerError('Invalid CHIP-8 frame receipt identity')
        for key in ('stop-pending','stop-owned','stop-consumed','faulted','key-wait','layer-conflict'):
            if type(info.get(key)) is not bool:raise DebuggerError('Invalid CHIP-8 frame receipt '+key)
        for key in ('control-generation','state-generation','baseline-virtual-ticks','baseline-deadline-ns',
                    'completed-virtual-ticks','completed-deadline-ns','sampled-virtual-now-ns','frame-generation','phase-numerator'):
            if type(info.get(key)) is not int or not 0<=info[key]<=((59 if key=='phase-numerator' else (1<<64)-1)):
                raise DebuggerError('Invalid CHIP-8 frame receipt '+key)
        if not isinstance(info.get('token'),str) or token is not None and info['token']!=token:
            raise DebuggerError('CHIP-8 frame token differs')
        pixels=info.get('pixels-hex');digest=info.get('pixels-sha256')
        if not isinstance(pixels,str) or not isinstance(digest,str):raise DebuggerError('Invalid CHIP-8 frame pixels')
        has_sample=info['state']=='completed' or info['stop-pending']
        if has_sample:
            try:data=bytes.fromhex(pixels)
            except ValueError:raise DebuggerError('Invalid CHIP-8 frame pixels') from None
            if len(pixels)!=4096 or len(data)!=2048 or any(x not in (0,1) for x in data) or _sha(data)!=digest:
                raise DebuggerError('CHIP-8 sampled pixels differ')
            if (info['completed-virtual-ticks']!=info['baseline-virtual-ticks']+1 or
                    info['completed-deadline-ns']!=info['baseline-deadline-ns'] or
                    info['sampled-virtual-now-ns']<info['baseline-deadline-ns']):
                raise DebuggerError('CHIP-8 frame did not sample the next tick')
        elif pixels or digest or any(info[k] for k in ('completed-virtual-ticks','completed-deadline-ns','sampled-virtual-now-ns')):
            raise DebuggerError('Unexpected unsampled CHIP-8 frame payload')
        if info['state']=='idle' and (info['token'] or info['stop-pending'] or info['stop-owned'] or info['stop-consumed']):
            raise DebuggerError('Invalid idle CHIP-8 frame receipt')
        if info['state']=='completed' and (not info['stop-owned'] or not info['stop-consumed'] or info['stop-pending']):
            raise DebuggerError('Invalid completed CHIP-8 frame ownership')
        if info['state']=='armed' and (info['stop-owned'] or info['stop-consumed']):
            raise DebuggerError('Invalid armed CHIP-8 frame ownership')
        return deepcopy(info)

    def _chip8_frame_idle(self):
        if self._chip8_frame_query()['state']!='idle':raise ValueError('CHIP-8 frame fence is active')

    def _chip8_frame_on_stop(self,reply,timed_out):
        context=getattr(self,'_chip8_frame_context',None)
        if context is None:return None
        token=context['token'];observed=self._chip8_frame_query(token)
        if (observed['baseline-virtual-ticks']!=context['ticks'] or
                observed['baseline-deadline-ns']!=context['deadline']):
            raise DebuggerError('CHIP-8 frame baseline differs')
        if observed['state']=='completed' or observed['stop-pending']:
            phase=context['phase'];expected_phase=phase-20 if phase>=20 else phase+40
            if observed['phase-numerator']!=expected_phase:
                raise DebuggerError('CHIP-8 sample phase differs')
        owned=(not timed_out and reply[:3] in ('T05','S05') and observed['state']=='completed'
               and observed['stop-owned'] and observed['stop-consumed'] and not observed['stop-pending']
               and not observed['faulted'] and not observed['key-wait'] and not observed['layer-conflict'])
        live_generation=self.chip8_environment()['state-generation']
        final=self.vm.qmp.call('x-chip8-cancel-frame',{'token':token,'expected-control-generation':observed['control-generation']})
        idle=self._chip8_frame_query()
        if (final!=idle or idle['state']!='idle' or idle['control-generation']!=observed['control-generation']+1
                or idle['state-generation']!=live_generation):
            raise DebuggerError('CHIP-8 frame cancellation differs')
        self._chip8_frame_context=None
        return dict(owned=owned,observed=observed,cancelled=idle,baseline_phase=context['phase'])

    def _frame_manifest(self,timeline=None):
        live=getattr(self,'_qemu_history_live',None);selected=timeline or (live.get('history') if live else None)
        if selected is None:raise ValueError('Start or attach a CHIP-8 timeline first')
        manifest,_=self._history_latest(selected)
        if manifest.get('format') not in ((KEY_FORMAT,DELTA_FORMAT) if self.identity['cpu_subset']==KEY_SUBSET else (FORMAT,)):raise ValueError('Selected history is not a CHIP-8 frame timeline')
        for node in manifest['nodes']:self._image_row(node['frame']['image'])
        return manifest

    def _image_row(self,image):
        if not isinstance(image,dict):raise ValueError('Invalid CHIP-8 frame image')
        row=self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(image.get('artifact'),)).fetchone()
        if (row is None or row['version']!=self.version['id'] or row['kind']!='screenshot' or row['sha256']!=image.get('sha256')
                or len(row['data'])!=image.get('size') or _sha(bytes(row['data']))!=row['sha256']):
            raise ValueError('CHIP-8 timeline image is missing or corrupt')
        try:
            with Image.open(io.BytesIO(bytes(row['data']))) as decoded:
                if decoded.size!=(64,32) or hashlib.sha256(decoded.convert('RGBA').tobytes()).hexdigest()!=image.get('pixel_sha256'):
                    raise ValueError('CHIP-8 timeline pixels differ')
        except (OSError,ValueError) as error:raise ValueError('Invalid CHIP-8 timeline PNG') from error
        return row

    def _frame_delta(self,manifest):
        return manifest.get('format')==DELTA_FORMAT

    def _frame_state_size(self,node,manifest):
        if self._frame_delta(manifest):
            from .chip8_frame_storage import stored_size
            return stored_size(node['checkpoint'])
        return node['checkpoint']['size']

    def _history_prepare_restore(self,manifest,target):
        if not self._frame_delta(manifest):return None
        from .chip8_frame_storage import materialize
        prepared=materialize(self,manifest,target)
        self._chip8_prepared_frame=(target['id'],prepared)
        return prepared

    def _history_validate_node_before_restore(self,target,*,manifest=None):
        frame=target.get('frame')
        cached=getattr(self,'_chip8_prepared_frame',None)
        self._chip8_prepared_frame=None
        if frame is None:return
        self._image_row(frame['image'])
        if manifest is not None and self._frame_delta(manifest):
            from .chip8_frame_storage import materialize
            metadata=materialize(self,manifest,target)['metadata']
        elif cached and cached[0]==target['id']:
            metadata=cached[1]['metadata']
        else:
            row=self._history_state_artifact(target['checkpoint']);metadata=json.loads(row['metadata'])
        environment=metadata.get('environment')
        if not isinstance(environment,dict):raise ValueError('CHIP-8 checkpoint lacks frame environment')
        try:pixels=bytes.fromhex(environment['pixels-hex'])
        except (KeyError,TypeError,ValueError):raise ValueError('Invalid saved CHIP-8 pixels') from None
        if len(pixels)!=2048 or any(pixel not in (0,1) for pixel in pixels):raise ValueError('Invalid saved CHIP-8 pixels')
        rgba=b''.join(b'\xff\xff\xff\xff' if pixel else b'\x00\x00\x00\xff' for pixel in pixels)
        if (_sha(pixels)!=environment.get('pixels-sha256') or _sha(rgba)!=frame['image'].get('pixel_sha256')):
            raise ValueError('CHIP-8 image and checkpoint state differ')
        if 'keys' in frame:
            from .chip8_keys import validate_key_snapshot
            keys=validate_key_snapshot(metadata.get('key_state'),environment)
            if frame['keys']!=[k for k in '0123456789abcdef' if keys['held-mask']&(1<<int(k,16))]:
                raise ValueError('CHIP-8 frame keys and checkpoint state differ')
        if frame['kind']=='native-60hz-sample':
            for field,key in (('virtual_ticks','virtual-ticks'),('phase_numerator','phase-numerator'),
                              ('next_deadline_ns','next-deadline-ns'),('state_generation','state-generation'),
                              ('frame_generation','frame-generation'),('stopped_ns','virtual-now-ns'),('pixels_sha256','pixels-sha256')):
                if frame.get(field)!=environment.get(key):raise ValueError('CHIP-8 sample and checkpoint state differ')

    def _history_restore_node_check(self,target):
        frame=target.get('frame')
        if frame is None:return
        actual=self.frame_rgba(timeout_ms=self._history_remaining_ms())
        if 'keys' in frame and self._chip8_keys_query()['held']!=frame['keys']:
            raise DebuggerError('Restored CHIP-8 frame keys differ')
        if actual['sha256']!=frame['image']['pixel_sha256']:
            raise DebuggerError('Restored CHIP-8 timeline pixels differ')
        if frame['kind']=='native-60hz-sample':
            env=actual['environment']
            for field,key in (('virtual_ticks','virtual-ticks'),('phase_numerator','phase-numerator'),
                              ('next_deadline_ns','next-deadline-ns'),('state_generation','state-generation'),
                              ('frame_generation','frame-generation'),('stopped_ns','virtual-now-ns'),('pixels_sha256','pixels-sha256')):
                if frame[field]!=env.get(key):raise DebuggerError('Restored CHIP-8 sample state differs')

    def _frame_image(self,limit):
        frame=self.frame_rgba(timeout_ms=self._history_remaining_ms())
        out=io.BytesIO();Image.frombytes('RGBA',(64,32),frame['rgba']).save(out,format='PNG')
        data=out.getvalue()
        if len(data)>limit:raise ValueError('CHIP-8 timeline image budget exceeded')
        metadata=dict(format='chip8-frame-png-1',width=64,height=32,pixel_sha256=frame['sha256'],
                      environment=frame['environment'],identity=self.identity)
        captured=self._artifact('chip8-timeline.png','screenshot',data,metadata)
        if captured['sha256']!=_sha(data) or captured['size']!=len(data):raise DebuggerError('CHIP-8 timeline image publication differs')
        image=dict(artifact=captured['artifact'],sha256=captured['sha256'],size=captured['size'],pixel_sha256=frame['sha256'])
        self._image_row(image)
        return image,frame['environment']

    def _frame_summary(self,manifest):
        output=self._history_summary(manifest,manifest.get('_artifact_id'))
        live=getattr(self,'_qemu_history_live',None)
        valid=bool(live and live.get('valid') and not self.closed and live.get('history')==manifest.get('_artifact_id')
                   and live.get('fingerprint')==self._history_live_fingerprint())
        output.update(format=manifest['format'],timeline=manifest.get('_artifact_id'),point=live.get('cursor') if valid else None,
                      cursor=live.get('cursor') if valid else None,valid=valid,unit='native 60 Hz sample',completed_guest_frame=None,
                      frame_config=deepcopy(manifest['frame_config']),nodes=deepcopy(manifest['nodes']),
                      input_dirty=manifest.get('input_dirty',False),pending_inputs=deepcopy(manifest.get('pending_inputs',[])),
                      storage_mode=manifest['frame_config']['storage_mode'],keyframe_interval=manifest['frame_config']['keyframe_interval'],
                      state_bytes_used=sum(self._frame_state_size(n,manifest) for n in manifest['nodes']),
                      image_bytes_used=sum(n['frame']['image']['size'] for n in manifest['nodes']),
                      input_bytes_used=(len(json.dumps(manifest['input_journal'],sort_keys=True,separators=(',',':')).encode()) if manifest['format'] in (KEY_FORMAT,DELTA_FORMAT) else 0),
                      storage_bytes_used=(sum(self._frame_state_size(n,manifest)+n['frame']['image']['size'] for n in manifest['nodes'])+
                          (len(json.dumps(manifest['input_journal'],sort_keys=True,separators=(',',':')).encode()) if manifest['format'] in (KEY_FORMAT,DELTA_FORMAT) else 0)))
        if self._frame_delta(manifest):
            output.update(full_state_points=sum(n['checkpoint']['storage']['kind']=='full' for n in manifest['nodes']),
                          delta_state_points=sum(n['checkpoint']['storage']['kind']=='delta' for n in manifest['nodes']),
                          retained_encoded_state_payload_bytes=sum(n['checkpoint']['storage']['payload_size'] for n in manifest['nodes']),
                          reconstructed_state_payload_bytes=sum(n['checkpoint']['size'] for n in manifest['nodes']),
                          retained_state_metadata_bytes=sum(n['checkpoint']['storage']['metadata_size'] for n in manifest['nodes']))
        return output

    def _frame_current(self,manifest):
        live=getattr(self,'_qemu_history_live',None)
        if not live or not live.get('valid') or live.get('history')!=manifest.get('_artifact_id') or live.get('fingerprint')!=self._history_live_fingerprint():
            raise ValueError('CHIP-8 timeline has no valid live point; restore a point first')
        node=self._node(manifest,live['cursor'])
        if node is None:raise ValueError('CHIP-8 timeline point is missing')
        return node

    def _frame_budget(self,manifest,count=1,input_reserve=0):
        config=manifest['frame_config'];nodes=manifest['nodes']
        if len(nodes)+count>min(config['max_frames'],config['max_captures']):raise ValueError('CHIP-8 timeline capture budget exhausted')
        used=sum(self._frame_state_size(n,manifest)+n['frame']['image']['size'] for n in nodes)
        if manifest.get('format') in (KEY_FORMAT,DELTA_FORMAT):used+=len(json.dumps(manifest['input_journal'],sort_keys=True,separators=(',',':')).encode())
        if nodes:
            previous=self._node(manifest,manifest.get('cursor')) or nodes[-1]
            state_reserve=min(config['max_state_bytes'],max(4096,previous['checkpoint']['size'],self._history_disk_bytes() or 0))
        else:state_reserve=config['max_state_bytes']
        reserve=count*(state_reserve+config['max_image_bytes'])+input_reserve
        if used+reserve>config['max_bytes']:raise ValueError('CHIP-8 timeline byte budget cannot reserve requested captures')
        project_used=int(self.project.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
        if project_used+reserve>256*1024*1024:raise ValueError('Project artifact budget cannot reserve requested captures')

    def _key_journal_budget(self,manifest,count):
        journal=manifest.get('input_journal',[])
        if not isinstance(journal,list) or len(journal)+count>1024:raise ValueError('CHIP-8 input journal budget exhausted')
        used=sum(self._frame_state_size(n,manifest)+n['frame']['image']['size'] for n in manifest['nodes'])
        used+=len(json.dumps(journal,sort_keys=True,separators=(',',':')).encode())
        if used+count*8192>manifest['max_bytes']:raise ValueError('CHIP-8 input journal byte budget exhausted')
        project_used=int(self.project.db.execute('SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
        if project_used+2*(len(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode())+count*8192)>256*1024*1024:raise ValueError('Project input journal budget exhausted')

    @_history_operation
    def timeline_start(self,max_frames=16,max_bytes=536870912,max_state_bytes=134217728,max_image_bytes=2097152,
                       max_captures=128,storage_mode='full',keyframe_interval=8,period_ns=PERIOD,*,timeline=None,timeout_ms=60000):
        for value,name,maximum in ((max_frames,'max_frames',MAX_NODES),(max_captures,'max_captures',MAX_NODES),
                (max_bytes,'max_bytes',1024**3),(max_state_bytes,'max_state_bytes',MAX_STATE),(max_image_bytes,'max_image_bytes',16*1024**2),
                (keyframe_interval,'keyframe_interval',128)):_positive_int(value,name,1,maximum)
        if storage_mode not in ('full','delta') or type(period_ns) is not int or period_ns!=PERIOD:raise ValueError('CHIP-8 timeline requires full or delta storage and native 60 Hz')
        if storage_mode=='delta' and (self.identity.get('cpu_subset')!=KEY_SUBSET or not self.capabilities.get('frame_delta_storage')):
            raise ValueError('CHIP-8 delta frame storage requires v6 and a checkpoint tool')
        self._frame_capability()
        if timeline is not None:
            manifest=self._frame_manifest(timeline);live=getattr(self,'_qemu_history_live',None)
            if not live or live.get('history_id')!=manifest['id']:
                self._qemu_history_live=dict(history=manifest['_artifact_id'],history_id=manifest['id'],cursor=None,valid=False,
                    invalid_reason='attached timeline is not bound to this machine',fingerprint=None)
            return self._frame_summary(manifest)
        self._history_admission();self._chip8_frame_idle()
        config=dict(max_frames=max_frames,max_bytes=max_bytes,max_state_bytes=max_state_bytes,max_image_bytes=max_image_bytes,
                    max_captures=max_captures,storage_mode=storage_mode,keyframe_interval=keyframe_interval,period_ns=period_ns)
        ident=uuid.uuid4().hex
        manifest=dict(format=(DELTA_FORMAT if storage_mode=='delta' else KEY_FORMAT if self.identity['cpu_subset']==KEY_SUBSET else FORMAT),id=ident,revision=0,parent_manifest=None,identity=self._history_identity(),
                      max_steps=min(max_frames,max_captures),max_bytes=max_bytes,nodes=[],head=None,cursor=None,
                      live_cursor_valid=False,invalid_reason=None,pending=dict(kind='frame-root',started=time.time_ns()),
                      history_kind=KIND,frame_config=config)
        if self.identity['cpu_subset']==KEY_SUBSET:manifest.update(input_journal=[],pending_inputs=[],input_dirty=False)
        self._frame_budget(manifest);manifest,_=self._history_new_revision(manifest,pending=manifest['pending'])
        try:
            with self._history_internal():
                node=uuid.uuid4().hex
                if self._frame_delta(manifest):
                    from .chip8_frame_storage import store
                    captured=self._capture_state('chip8-frame-root.qcow2',max_bytes=max_state_bytes,timeout_ms=self._history_remaining_ms())
                    image,env=self._frame_image(max_image_bytes);saved=captured['metadata']
                    checkpoint=store(self,manifest,node,None,captured,reserve_bytes=image['size'])
                else:
                    checkpoint=self._history_checkpoint(remaining_bytes=max_state_bytes,node_name='chip8-frame-root.qcow2')
                    image,env=self._frame_image(max_image_bytes)
                    saved=json.loads(self._history_state_artifact(checkpoint)['metadata'])
                if env!=saved.get('environment') or env!=self.chip8_environment():raise DebuggerError('CHIP-8 root image environment changed')
                frame=dict(kind='initial-paused',image=image,completed_guest_frame=None)
                if self.identity['cpu_subset']==KEY_SUBSET:frame['keys']=self._chip8_keys_query()['held']
                manifest['nodes'].append(dict(id=node,parent=None,checkpoint=checkpoint,
                    edge=dict(kind='root',completed_instruction=False),registers=self.registers(),created=time.time_ns(),frame=frame))
                manifest.update(head=node,cursor=node,live_cursor_valid=True,pending=None)
                manifest,_=self._history_new_revision(manifest)
                return self._frame_summary(manifest)
        except BaseException:self.close();raise

    @_history_operation
    def timeline_status(self,*,timeline=None):
        if timeline is None and not getattr(self,'_qemu_history_live',None):
            return dict(format=(KEY_FORMAT if self.identity.get('cpu_subset')==KEY_SUBSET else FORMAT),timeline=None,valid=False,cursor=None,point=None,retained_nodes=0,unit='native 60 Hz sample',completed_guest_frame=None)
        return self._frame_summary(self._frame_manifest(timeline))

    def _frame_admit(self,*,future_mask=None,will_apply=False):
        if self._chip8_hook_pending is not None:raise ValueError('Resolve pending CHIP-8 hook before frame advance')
        self._stopped();fence=self._chip8_frame_query()
        if fence['state']!='idle':raise ValueError('CHIP-8 frame fence is active')
        from .qemu_chip8 import _fault_receipt
        fault=_fault_receipt(self.vm.qmp,self.identity['cpu_subset']);layer=self._chip8_layer_query();env=self.chip8_environment()
        if layer['generation']!=self._layer_generation or env['layer-generation']!=layer['generation']:
            raise DebuggerError('CHIP-8 layer generations differ')
        if self.identity['cpu_subset']==KEY_SUBSET:
            keys=self._chip8_keys_query()
            if keys['key-mask']!=env['key-mask'] or keys['state-generation']!=env['state-generation']:
                raise DebuggerError('CHIP-8 key and environment state differs')
        mask=env['key-mask'] if future_mask is None else future_mask
        waiting_blocked=env['key-wait'] and not (self.identity['cpu_subset']==KEY_SUBSET and mask and
                            (will_apply or not env['key-wait-stop-owned']))
        if fault.get('faulted') or waiting_blocked or layer['faulted'] or not layer['backing-valid']:
            raise ValueError('CHIP-8 fault, key wait or layer conflict prevents frame advance')
        if (env['state-generation']==(1<<64)-1 or env['virtual-ticks']==(1<<64)-1 or
                fence['control-generation']>=(1<<64)-2):raise ValueError('CHIP-8 frame generation exhausted')
        return fence,env

    def _frame_run(self):
        before,env=self._frame_admit();token=uuid.uuid4().hex
        args={'token':token,'expected-state-generation':env['state-generation'],
              'expected-virtual-ticks':env['virtual-ticks'],'expected-deadline-ns':env['next-deadline-ns']}
        try:
            armed=self.vm.qmp.call('x-chip8-arm-frame',args);read=self._chip8_frame_query(token)
            if (armed!=read or read['state']!='armed' or read['stop-pending'] or
                    read['control-generation']!=before['control-generation']+1 or
                    read['state-generation']!=env['state-generation']):
                raise DebuggerError('CHIP-8 frame fence did not arm')
            self._chip8_frame_context=dict(token=token,ticks=env['virtual-ticks'],deadline=env['next-deadline-ns'],phase=env['phase-numerator'])
            self._chip8_frame_driving=True
            try:return self.run(timeout_ms=self._history_remaining_ms(),stop_on_hook=True)
            finally:self._chip8_frame_driving=False
        except BaseException:
            self.close();raise

    @_history_operation
    def timeline_advance(self,frames=1,inputs=None,timeout_ms=60000):
        _positive_int(frames,'frames',1,MAX_NODES)
        self._frame_capability();manifest=self._frame_manifest();parent=self._frame_current(manifest)
        schedule={}
        if self.identity['cpu_subset']==KEY_SUBSET:
            validate_schedule(inputs,frames);schedule={item['frame']:item['edges'] for item in (inputs or [])}
            native=self._chip8_keys_query();mask=native['held-mask'];active=native['active']
            first_mask=mask if active else native['key-mask']
            for index in range(frames):
                edges=schedule.get(index,[])
                if edges and not active and native['key-mask']:raise ValueError('Release manual CHIP-8 keys before frame ownership')
                mask=_edges(edges,mask)
                if edges:active=True
                if index==0 and edges:first_mask=mask
            batches=sum(bool(edges) for edges in schedule.values());total=sum(len(edges) for edges in schedule.values())
            if native['generation']>(1<<64)-1-batches or native['state-generation']>(1<<64)-1-batches or native['accepted-edges']>(1<<64)-1-total:
                raise ValueError('CHIP-8 frame key schedule counters exhausted')
            self._key_journal_budget(manifest,batches)
        elif inputs not in (None,[]):raise ValueError('CHIP-8 frame input schedules require v6')
        if self._frame_delta(manifest):self._history_validate_node_before_restore(parent,manifest=manifest)
        self._history_admission()
        if self.identity['cpu_subset']==KEY_SUBSET:self._frame_admit(future_mask=first_mask,will_apply=bool(schedule.get(0)))
        else:self._frame_admit()
        self._frame_budget(manifest,frames,input_reserve=8192*sum(bool(edges) for edges in schedule.values()));records=[];input_receipts=[]
        committed_history=manifest['_artifact_id'];committed_point=parent['id'];last_journal=committed_history
        with self._history_internal():
            for index in range(frames):
                stage='pending-intent';checkpoint=None;image=None;result=None;key_receipt=None
                try:
                    edges=schedule.get(index,[])
                    self._history_pending(manifest,parent['id'],'chip8-frame',receipt={'edges':deepcopy(edges)} if edges else None)
                    last_journal=manifest['_artifact_id']
                    if edges:
                        stage='key-application';native,mask=self._chip8_keys_prepare(edges)
                        key_receipt=self._chip8_keys_apply(native,edges,mask);input_receipts.append(deepcopy(key_receipt))
                        manifest['input_journal'].append(deepcopy(key_receipt));manifest['pending_inputs'].append(deepcopy(key_receipt));manifest['input_dirty']=True
                        stage='input-publication';manifest,_=self._history_new_revision(manifest,pending=manifest['pending'])
                        last_journal=manifest['_artifact_id']
                    stage='native-sample'
                    result=self._frame_run()
                    if result.get('outcome')!='frame':
                        stopped=self._history_resolve_known_stop(result,'CHIP-8 sample interrupted',records=records,requested_count=frames)
                        output=self._frame_summary(self._frame_manifest(stopped['history']))
                        output.update(outcome='interrupted',completed_frames=len(records),frames=records,stop=result,input_receipts=deepcopy(input_receipts))
                        return output
                    fence=result['frame_fence'];proof=fence['observed'];config=manifest['frame_config']
                    stopped=self.chip8_environment();phase=fence['baseline_phase']
                    interval=16666667 if phase>=20 else 16666666
                    expected_next=proof['baseline-deadline-ns']+interval
                    for field,key in (('virtual-ticks','completed-virtual-ticks'),('phase-numerator','phase-numerator'),
                                      ('frame-generation','frame-generation'),('state-generation','state-generation'),('pixels-sha256','pixels-sha256')):
                        if stopped[field]!=proof[key]:raise DebuggerError('CHIP-8 sample stopped state differs')
                    if (stopped['state-generation']==(1<<64)-1 or stopped['next-deadline-ns']!=expected_next or
                            stopped['virtual-now-ns']<proof['sampled-virtual-now-ns']):
                        raise DebuggerError('CHIP-8 sample stopped timing differs')
                    stage='checkpoint-capture';node=uuid.uuid4().hex
                    if self._frame_delta(manifest):
                        from .chip8_frame_storage import store
                        captured=self._capture_state('chip8-frame.qcow2',max_bytes=config['max_state_bytes'],timeout_ms=self._history_remaining_ms())
                        stage='image-capture';image,env=self._frame_image(config['max_image_bytes']);saved=captured['metadata']
                        stage='delta-publication';checkpoint=store(self,manifest,node,parent,captured,reserve_bytes=image['size'])
                    else:
                        checkpoint=self._history_checkpoint(remaining_bytes=config['max_state_bytes'],node_name='chip8-frame.qcow2')
                        stage='image-capture';image,env=self._frame_image(config['max_image_bytes'])
                        saved=json.loads(self._history_state_artifact(checkpoint)['metadata'])
                    if (env!=stopped or env!=saved.get('environment') or env['virtual-ticks']!=proof['completed-virtual-ticks'] or env['pixels-sha256']!=proof['pixels-sha256']
                            or env['frame-generation']!=proof['frame-generation'] or env!=self.chip8_environment()):
                        raise DebuggerError('CHIP-8 sampled image and stopped state differ')
                    used=sum(self._frame_state_size(n,manifest)+n['frame']['image']['size'] for n in manifest['nodes'])
                    if manifest['format'] in (KEY_FORMAT,DELTA_FORMAT):used+=len(json.dumps(manifest['input_journal'],sort_keys=True,separators=(',',':')).encode())
                    if used+(self._frame_state_size({'checkpoint':checkpoint},manifest))+image['size']>config['max_bytes']:
                        raise ValueError('CHIP-8 timeline byte budget exceeded')
                    frame=dict(kind='native-60hz-sample',image=image,virtual_ticks=proof['completed-virtual-ticks'],
                               sampled_ns=proof['sampled-virtual-now-ns'],stopped_ns=env['virtual-now-ns'],
                               phase_numerator=env['phase-numerator'],next_deadline_ns=env['next-deadline-ns'],
                               baseline_deadline_ns=proof['baseline-deadline-ns'],baseline_phase=phase,state_generation=env['state-generation'],
                               frame_generation=env['frame-generation'],pixels_sha256=env['pixels-sha256'],completed_guest_frame=None)
                    if manifest['format'] in (KEY_FORMAT,DELTA_FORMAT):frame.update(keys=self._chip8_keys_query()['held'],input=deepcopy(key_receipt))
                    manifest['nodes'].append(dict(id=node,parent=parent['id'],checkpoint=checkpoint,
                        edge=dict(kind='native-60hz-sample',completed_instruction=None,stop=deepcopy(result)),
                        registers=self.registers(),created=time.time_ns(),frame=frame))
                    manifest.update(head=node,cursor=node,live_cursor_valid=True,pending=None,invalid_reason=None)
                    if manifest['format'] in (KEY_FORMAT,DELTA_FORMAT):manifest.update(input_dirty=False,pending_inputs=[])
                    stage='node-publication'
                    manifest,_=self._history_new_revision(manifest);records.append(dict(point=node,parent=parent['id'],frame=deepcopy(frame)))
                    parent=manifest['nodes'][-1];committed_history=manifest['_artifact_id'];committed_point=node;last_journal=committed_history
                except BaseException as error:
                    previous=getattr(error,'result',None)
                    receipt=dict(requested_count=frames,completed_frames=len(records),frames=deepcopy(records),
                        last_committed_history=committed_history,last_committed_point=committed_point,
                        last_observed_journal=last_journal,phase=stage,uncertain=True,do_not_replay=True,
                        checkpoint=deepcopy(checkpoint),image=deepcopy(image),stop=deepcopy(result),
                        input_receipts=deepcopy(input_receipts),cause_result=previous)
                    try:self.close()
                    except BaseException as close_error:receipt['close_error']=str(close_error)
                    receipt['owner_closed']=bool(self.closed);error.result=receipt
                    raise
        output=self._frame_summary(manifest);output.update(outcome='completed',completed_frames=len(records),frames=records,input_receipts=deepcopy(input_receipts))
        return output

    @_history_operation
    def timeline_rewind(self,frames=1,policy=None,*,timeline=None,point=None,timeout_ms=60000):
        if policy not in (None,{}):raise ValueError('CHIP-8 partial frame restore is unsupported')
        if type(frames) is not int or not 0<=frames<=MAX_NODES:raise ValueError('Invalid CHIP-8 rewind frame count')
        manifest=self._frame_manifest(timeline)
        if point is None:
            chain=self._ancestors(manifest,self._frame_current(manifest)['id'])
            if frames>=len(chain):raise ValueError('CHIP-8 rewind exceeds retained points')
            target=chain[frames]
        else:
            target=self._node(manifest,point)
            if target is None:raise ValueError('Unknown CHIP-8 timeline point')
        self._history_validate_node_before_restore(target,manifest=manifest)
        restored=self.rewind(history=manifest['_artifact_id'],node=target['id'],timeout_ms=self._history_remaining_ms())
        result=self._frame_summary(self._frame_manifest(restored['history']))
        result.update(rewound_frames=frames,restore=restored,completed_guest_frame=None)
        return result

    @_history_operation
    def timeline_image(self,name='frame.png',*,timeline=None,point=None):
        from .external_files import _file_name
        _file_name(name);manifest=self._frame_manifest(timeline);node=self._node(manifest,point or manifest.get('cursor'))
        if node is None:raise ValueError('Unknown CHIP-8 timeline point')
        row=self._image_row(node['frame']['image'])
        return dict(artifact=row['id'],sha256=row['sha256'],size=len(row['data']),point=node['id'],stored_frame=True,completed_guest_frame=None)

    @_history_operation
    def timeline_pin(self,name='frame.qcow2'):
        from .external_files import _file_name
        _file_name(name);manifest=self._frame_manifest();node=self._frame_current(manifest)
        if manifest.get('input_dirty'):raise ValueError('Restore or capture dirty CHIP-8 frame input before pinning')
        if self._frame_delta(manifest):
            self._history_validate_node_before_restore(node,manifest=manifest)
            from .chip8_frame_storage import materialize
            prepared=materialize(self,manifest,node)
            return self._artifact(name,'state',prepared['data'],prepared['metadata'])
        row=self._history_state_artifact(node['checkpoint']);return self._artifact(name,'state',bytes(row['data']),json.loads(row['metadata']))

    def _history_restore_manifest_updates(self,target,manifest):
        if manifest.get('format') in (KEY_FORMAT,DELTA_FORMAT):
            manifest['input_dirty']=False;manifest['pending_inputs']=[]

    @_history_operation
    def timeline_stop(self):
        manifest=self._frame_manifest();result=self._frame_summary(manifest);self._qemu_history_live=None
        return dict(result,stopped=True,target_executed=False,input_state_changed=False)

    @_history_operation
    def advance_frames(self,frames=1,timeout_ms=60000):
        _positive_int(frames,'frames',1,MAX_NODES);self._frame_capability();self._frame_admit()
        live=getattr(self,'_qemu_history_live',None)
        if live and live.get('valid'):live.update(valid=False,cursor=None,invalid_reason='unrecorded CHIP-8 frame advance')
        records=[]
        with self._history_internal():
            for _ in range(frames):
                try:
                    result=self._frame_run()
                    if result.get('outcome')!='frame':return dict(format=(KEY_FORMAT if self.identity['cpu_subset']==KEY_SUBSET else FORMAT),outcome='interrupted',completed_frames=len(records),frames=records,stop=result,completed_guest_frame=None)
                    records.append(result['frame_fence']['observed'])
                except BaseException as error:
                    previous=getattr(error,'result',None)
                    receipt=dict(requested_count=frames,completed_frames=len(records),frames=deepcopy(records),
                                 uncertain=True,do_not_replay=True,cause_result=previous)
                    try:self.close()
                    except BaseException as close_error:receipt['close_error']=str(close_error)
                    receipt['owner_closed']=bool(self.closed);error.result=receipt
                    raise
        return dict(format=(KEY_FORMAT if self.identity['cpu_subset']==KEY_SUBSET else FORMAT),outcome='completed',completed_frames=len(records),frames=records,unit='native 60 Hz sample',completed_guest_frame=None)
