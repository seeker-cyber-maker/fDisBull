"""Stopped, atomic frame-owned CHIP-8 keypad edges."""
from copy import deepcopy
import uuid
from .dosbox_rpc import DebuggerError
from .qemu_dos_history import _history_operation

KEY_SUBSET='fdisbull-chip8-frame-keys-6'
KEY_ENV='fdisbull-chip8-display-keypad-timers-rng-layers-frames-keys-5'
KEY_MODEL='fdisbull-chip8-frame-keys-1'
KEYS='0123456789abcdef'


def _reference(value,allowed):
    return allowed and isinstance(value,str) and value.startswith('$')


def validate_edges(edges,*,allow_references=False):
    if _reference(edges,allow_references):return
    if not isinstance(edges,list) or len(edges)>16:raise ValueError('CHIP-8 frame input requires at most 16 edges')
    seen=set()
    for edge in edges:
        if _reference(edge,allow_references):continue
        if not isinstance(edge,dict) or set(edge)!={'key','pressed'}:raise ValueError('CHIP-8 frame edge requires key and pressed')
        key=edge['key']
        if not _reference(key,allow_references):
            if not isinstance(key,str) or len(key)!=1 or key not in KEYS:raise ValueError('CHIP-8 key must be lowercase hexadecimal')
            if key in seen:raise ValueError('Duplicate CHIP-8 frame input key')
            seen.add(key)
        if not _reference(edge['pressed'],allow_references) and type(edge['pressed']) is not bool:
            raise ValueError('CHIP-8 key pressed must be boolean')


def validate_schedule(inputs,frames,*,allow_references=False):
    if inputs is None or _reference(inputs,allow_references):return
    if not isinstance(inputs,list) or len(inputs)>128:raise ValueError('Invalid CHIP-8 frame input schedule')
    seen=set()
    for item in inputs:
        if _reference(item,allow_references):continue
        if not isinstance(item,dict) or set(item)!={'frame','edges'}:raise ValueError('CHIP-8 schedule requires frame and edges')
        frame=item['frame']
        if not _reference(frame,allow_references):
            if type(frame) is not int or not 0<=frame<128 or type(frames) is int and frame>=frames or frame in seen:
                raise ValueError('Invalid CHIP-8 scheduled frame')
            seen.add(frame)
        validate_edges(item['edges'],allow_references=allow_references)


def _edges(edges,held):
    validate_edges(edges);mask=held
    for edge in edges:
        bit=1<<int(edge['key'],16)
        if bool(mask&bit)==edge['pressed']:raise ValueError('CHIP-8 key is already in the requested state')
        mask=(mask|bit) if edge['pressed'] else (mask&~bit)
    return mask


def validate_key_snapshot(saved,environment):
    fields={'epoch','active','generation','accepted-edges','held-mask','key-mask','state-generation'}
    if not isinstance(saved,dict) or set(saved)!=fields or type(saved.get('active')) is not bool:
        raise ValueError('Invalid CHIP-8 key checkpoint proof')
    for key in fields-{'active'}:
        if type(saved.get(key)) is not int or not 0<=saved[key]<(1<<64):raise ValueError('Invalid CHIP-8 key checkpoint field')
    if (not saved['epoch'] or saved['held-mask']>0xffff or saved['key-mask']>0xffff or
            saved['active'] and (saved['held-mask']!=saved['key-mask'] or saved['generation'] in (0,(1<<64)-1) or saved['accepted-edges']==0) or not saved['active'] and saved['held-mask'] or
            not isinstance(environment,dict) or saved['key-mask']!=environment.get('key-mask') or
            saved['state-generation']!=environment.get('state-generation')):
        raise ValueError('CHIP-8 key checkpoint and environment differ')
    return deepcopy(saved)


class Chip8KeysMixin:
    def _chip8_keys_query(self,*,adoption=False):
        if self.identity.get('cpu_subset')!=KEY_SUBSET:raise ValueError('CHIP-8 frame key ownership requires v6')
        info=self.vm.qmp.call('query-chip8-frame-keys')
        if (not isinstance(info,dict) or info.get('model')!=KEY_MODEL or info.get('subset')!=KEY_SUBSET or
                info.get('environment-model')!=KEY_ENV):raise DebuggerError('Invalid CHIP-8 key owner identity')
        for key in ('active','valid','needs-adoption','repeat-supported'):
            if type(info.get(key)) is not bool:raise DebuggerError('Invalid CHIP-8 key owner '+key)
        for key in ('epoch','generation','accepted-edges','state-generation','held-mask','key-mask','edge-capacity'):
            if type(info.get(key)) is not int or not 0<=info[key]<(1<<64):raise DebuggerError('Invalid CHIP-8 key owner '+key)
        if (not info['epoch'] or not info['valid'] or info['repeat-supported'] or info['edge-capacity']!=16 or
                info['held-mask']>0xffff or info['key-mask']>0xffff or not isinstance(info.get('token'),str)):
            raise DebuggerError('Invalid CHIP-8 key owner state')
        held=[key for key in KEYS if info['held-mask']&(1<<int(key,16))]
        if info.get('held')!=held or info['active'] and info['held-mask']!=info['key-mask']:
            raise DebuggerError('CHIP-8 held key state differs')
        if info['needs-adoption']:
            if not adoption or not info['active'] or info['token']:raise DebuggerError('CHIP-8 key owner needs adoption')
        elif info['active']:
            if info['generation']<1 or info['accepted-edges']<1:raise DebuggerError('Invalid active CHIP-8 key generation or edge count')
            owner=getattr(self.vm,'_chip8_key_owner',None)
            if not info['token'] or owner!=(info['epoch'],info['token'],info['generation'],info['accepted-edges'],info['held-mask']):raise DebuggerError('CHIP-8 key ownership differs')
        elif info['held-mask'] or info['token'] or getattr(self.vm,'_chip8_key_owner',None) is not None:
            raise DebuggerError('Invalid inactive CHIP-8 key owner')
        return deepcopy(info)

    def _chip8_key_snapshot(self):
        info=self._chip8_keys_query()
        return {k:info[k] for k in ('epoch','active','generation','accepted-edges','held-mask','key-mask','state-generation')}

    def _chip8_key_adopt(self,saved):
        validate_key_snapshot(saved,{'key-mask':saved.get('key-mask') if isinstance(saved,dict) else None,
                                      'state-generation':saved.get('state-generation') if isinstance(saved,dict) else None})
        native=self._chip8_keys_query(adoption=True)
        if (native['epoch']==saved['epoch'] or any(native[k]!=saved[k] for k in ('active','generation','accepted-edges','held-mask','key-mask','state-generation')) or
                native['needs-adoption']!=saved['active']):raise ValueError('Restored CHIP-8 key ownership differs')
        if not native['active']:
            self.vm._chip8_key_owner=None;return native
        if native['generation']==(1<<64)-1:raise ValueError('CHIP-8 key adoption generation exhausted')
        token=uuid.uuid4().hex
        result=self.vm.qmp.call('x-chip8-adopt-frame-keys',{'token':token,'expected-generation':native['generation'],
                                  'expected-state-generation':native['state-generation'],'held-mask':native['held-mask']})
        self.vm._chip8_key_owner=(native['epoch'],token,native['generation']+1,native['accepted-edges'],native['held-mask'])
        after=self._chip8_keys_query()
        if result!=after or after['needs-adoption'] or (after['generation']!=native['generation']+1 or any(after[k]!=native[k] for k in ('accepted-edges','held-mask','key-mask','state-generation'))):
            raise DebuggerError('CHIP-8 key adoption differs')
        return after

    def _chip8_keys_prepare(self,edges):
        native=self._chip8_keys_query();mask=_edges(edges,native['held-mask'])
        if edges and not native['active'] and native['key-mask']:
            raise ValueError('Release manual CHIP-8 keys before frame ownership')
        if edges and (len(edges)>native['edge-capacity'] or native['generation']==(1<<64)-1 or native['state-generation']==(1<<64)-1 or native['accepted-edges']>(1<<64)-1-len(edges)):
            raise ValueError('CHIP-8 frame key capacity exhausted')
        return native,mask

    def _chip8_keys_apply(self,native,edges,mask):
        if not edges:return dict(native=native,edges=[],held=native['held'],guest_consumed=None,repeat_supported=False)
        token=native['token'] or uuid.uuid4().hex
        intent={'token':token,'expected-generation':native['generation'],'edges':deepcopy(edges)}
        self._event('frame-inputs-intent',intent)
        try:
            raw=self.vm.qmp.call('x-chip8-apply-frame-key-edges',{'token':token,'expected-generation':native['generation'],
                'expected-state-generation':native['state-generation'],'edges':deepcopy(edges)})
            self.vm._chip8_key_owner=(native['epoch'],token,native['generation']+1,native['accepted-edges']+len(edges),mask);after=self._chip8_keys_query()
            if (raw!=after or not after['active'] or after['generation']!=native['generation']+1 or
                    after['state-generation']!=native['state-generation']+1 or after['accepted-edges']!=native['accepted-edges']+len(edges) or
                    after['held-mask']!=mask or after['key-mask']!=mask):raise DebuggerError('CHIP-8 frame input receipt differs')
            result=dict(native=after,edges=deepcopy(edges),held=after['held'],guest_consumed=None,repeat_supported=False)
            self._event('frame-inputs',result);return result
        except BaseException as error:
            error.result=dict(intent=intent,native_receipt=deepcopy(raw) if 'raw' in locals() else None,
                              disposition='CHIP-8 frame input outcome uncertain; do not replay')
            try:self.close()
            except BaseException:pass
            raise

    def _chip8_key_before_manual(self):
        native=self._chip8_keys_query()
        if not native['active']:return
        if native['held-mask']:raise ValueError('Release frame-owned CHIP-8 keys before manual keypad input')
        if native['generation']==(1<<64)-1:raise ValueError('CHIP-8 key detach generation exhausted')
        try:
            result=self.vm.qmp.call('x-chip8-detach-frame-keys',{'token':native['token'],'expected-generation':native['generation']})
            self.vm._chip8_key_owner=None;after=self._chip8_keys_query()
            if (result!=after or after['active'] or after['generation']!=native['generation']+1 or
                    after['accepted-edges']!=native['accepted-edges'] or after['state-generation']!=native['state-generation']):
                raise DebuggerError('CHIP-8 key detach differs')
            return after
        except BaseException as error:
            if getattr(error,'result',None) is None:
                error.result=dict(detach_receipt=deepcopy(result) if 'result' in locals() else None,
                                  disposition='CHIP-8 key detach outcome uncertain; do not replay')
            self.close();raise

    @_history_operation
    def frame_inputs(self,edges,*,timeout_ms=1000):
        if self.project.db.in_transaction:raise ValueError('CHIP-8 frame input requires no caller transaction')
        self._stopped();self._chip8_frame_idle();native,mask=self._chip8_keys_prepare(edges)
        live=getattr(self,'_qemu_history_live',None);manifest=None
        if live and live.get('valid'):
            selected,_=self._history_latest(live['history'])
            if selected.get('history_kind')=='chip8-60hz-samples':
                manifest=selected;self._frame_current(manifest);self._key_journal_budget(manifest,int(bool(edges)))
            elif edges:live.update(valid=False,cursor=None,invalid_reason='unrecorded CHIP-8 frame input')
        with self._history_internal():
            if not edges:return self._chip8_keys_apply(native,edges,mask)
            last_history=manifest['_artifact_id'] if manifest is not None else None
            point=manifest['cursor'] if manifest is not None else None
            journal=last_history;result=None;stage='pending-intent'
            try:
                if manifest is not None:
                    self._history_pending(manifest,point,'chip8-frame-input',receipt={'edges':deepcopy(edges)})
                    journal=manifest['_artifact_id']
                stage='key-application';result=self._chip8_keys_apply(native,edges,mask)
                if manifest is not None:
                    manifest['input_journal'].append(deepcopy(result));manifest['pending_inputs'].append(deepcopy(result))
                    manifest['input_dirty']=True;stage='input-publication';manifest,_=self._history_new_revision(manifest)
                return result
            except BaseException as error:
                previous=getattr(error,'result',None)
                evidence=dict(phase=stage,receipt=deepcopy(result),last_committed_history=last_history,
                              last_committed_point=point,last_observed_journal=journal,do_not_replay=True,
                              uncertain=True,cause_result=previous)
                try:self.close()
                except BaseException as close_error:evidence['close_error']=str(close_error)
                evidence['owner_closed']=bool(self.closed);error.result=evidence
                raise

    def keyboard_state(self,*,timeout_ms=1000):
        import time
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid CHIP-8 keyboard timeout')
        with self._budget(self.vm,time.monotonic()+timeout_ms/1000):
            self._stopped();native=self._chip8_keys_query()
            return {'keyboard':{'frame_keys':native['held'],'native':native,'frame_edge_capacity':native['edge-capacity']}}
