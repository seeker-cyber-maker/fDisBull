"""Full native checkpoint histories for the bounded CHIP-8 v4 machine."""
from copy import deepcopy
from functools import wraps
import json
import inspect
import time

from .qemu_dos_history import QemuDOSHistoryMixin, MAX_STATE, _sha

FORMAT='fdisbull-qemu-chip8-history-v1'
SUBSET='fdisbull-chip8-layers-hooks-4'
STATE_FORMAT='fdisbull-qemu-chip8-state-4'


class Chip8HistoryMixin(QemuDOSHistoryMixin):
    HISTORY_FORMAT=FORMAT

    @classmethod
    def _validate_manifest(cls,manifest):
        super()._validate_manifest(manifest)
        def ident(value):
            return isinstance(value,str) and len(value)==32 and all(c in '0123456789abcdef' for c in value)
        revision=manifest.get('revision');parent=manifest.get('parent_manifest')
        if (not ident(manifest.get('id')) or type(revision) is not int or revision<1 or
                (revision==1 and parent is not None) or (revision>1 and not ident(parent))):
            raise ValueError('Invalid CHIP-8 history revision identity')
        for node in manifest['nodes']:
            cp=node['checkpoint'];digest=cp.get('metadata_sha256')
            if (not ident(node['id']) or not ident(cp.get('artifact')) or
                    not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest)):
                raise ValueError('Invalid CHIP-8 history node identity or metadata hash')

    def _history_supported(self):
        if (self.closed or self.identity.get('cpu_subset')!=SUBSET or
                self._checkpoint_tool is None or self.vm.checkpoint_disk is None):
            raise ValueError('CHIP-8 history requires the v4 native full checkpoint backend')
        if self.project.db.in_transaction:
            raise ValueError('History operations require a project outside a caller-owned transaction')

    def _history_identity(self):
        return dict(schema=1,version=self.version['id'],runtime=deepcopy(self.identity))

    def _history_admission(self):
        self._checkpoint_admit()

    def _history_require_live(self):
        self._history_supported();self._stopped()

    def _history_verify_restored(self,restored):
        if self.closed or not isinstance(restored,dict) or restored.get('host_files_restored') is not False:
            raise ValueError('CHIP-8 full checkpoint restore was not verified')

    def _history_live_fingerprint(self):
        return dict(run=self.run_id,epoch=self.vm.history_epoch)

    def _history_base_response(self):
        return dict(format=FORMAT,active=not self.closed,
                    implementation='immutable full native CHIP-8 checkpoints; no deterministic replay',
                    checkpoint_scope='CPU, RAM, device/RNG, layers and hook controls',host_files_restored=False,
                    storage_budget_scope='cumulative state artifact payloads; project 256 MiB runtime-artifact cap also applies',
                    private_disk_budget_scope='live private QCOW2 growth is measured separately and is not quota-managed',
                    live_private_disk_bytes=self._history_disk_bytes())

    def _history_latest(self,history):
        manifest,row=super()._history_latest(history)
        # Validate every indexed node at attach/read, without repeatedly hashing
        # up to the full retained checkpoint budget. The selected restore does
        # the full content hash in _history_state_artifact before dispatch.
        for node in manifest['nodes']:
            checkpoint=node['checkpoint']
            item=self.project.db.execute(
                'SELECT a.kind,a.sha256,a.metadata,fdb_length(a.data) AS size,r.version '
                'FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                (checkpoint['artifact'],)).fetchone()
            if (item is None or item['kind']!='state' or item['version']!=self.version['id'] or
                    item['sha256']!=checkpoint['sha256'] or item['size']!=checkpoint['size']):
                raise ValueError('CHIP-8 history checkpoint index is missing or inconsistent')
            if _sha(item['metadata'].encode())!=checkpoint['metadata_sha256']:
                raise ValueError('CHIP-8 history checkpoint metadata hash differs')
            try:meta=json.loads(item['metadata'])
            except (TypeError,ValueError):raise ValueError('Invalid CHIP-8 checkpoint metadata') from None
            if (meta.get('format')!=STATE_FORMAT or meta.get('identity')!=self.identity or
                    meta.get('host_files_restored') is not False):
                raise ValueError('CHIP-8 history checkpoint identity differs')
        return manifest,row

    def _history_state_artifact(self,checkpoint):
        row=self.project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
                                    (checkpoint['artifact'],)).fetchone()
        if (row is None or row['kind']!='state' or row['version']!=self.version['id'] or
                row['sha256']!=checkpoint['sha256'] or len(row['data'])!=checkpoint['size'] or
                _sha(bytes(row['data']))!=checkpoint['sha256']):
            raise ValueError('CHIP-8 history checkpoint artifact is missing or corrupt')
        if _sha(row['metadata'].encode())!=checkpoint['metadata_sha256']:
            raise ValueError('CHIP-8 history checkpoint metadata hash differs')
        try:meta=json.loads(row['metadata'])
        except (TypeError,ValueError):raise ValueError('Invalid CHIP-8 checkpoint metadata') from None
        if (meta.get('format')!=STATE_FORMAT or meta.get('identity')!=self.identity or
                meta.get('host_files_restored') is not False):
            raise ValueError('CHIP-8 history checkpoint identity differs')
        return row

    def _history_checkpoint(self,*,remaining_bytes,node_name):
        limit=min(MAX_STATE,max(1,remaining_bytes));before=self._history_disk_bytes()
        result=self.save_state(node_name,max_bytes=limit,timeout_ms=self._history_remaining_ms())
        after=self._history_disk_bytes()
        if (not isinstance(result,dict) or not isinstance(result.get('artifact'),str) or
                not isinstance(result.get('sha256'),str) or type(result.get('size')) is not int or
                not 1<=result['size']<=limit):
            raise ValueError('Invalid CHIP-8 checkpoint receipt')
        row=self.project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',(result['artifact'],)).fetchone()
        if row is None or not isinstance(row['metadata'],str):raise ValueError('Missing CHIP-8 checkpoint metadata')
        checkpoint=dict(artifact=result['artifact'],sha256=result['sha256'],size=result['size'],
                        metadata_sha256=_sha(row['metadata'].encode()))
        self._history_state_artifact(checkpoint)
        return dict(**checkpoint,
                    live_disk_bytes_before=before,live_disk_bytes_after=after,
                    live_disk_bytes_growth=None if before is None or after is None else max(0,after-before))


def bind_history_mutations(cls):
    """Invalidate under the same bounded owner lock as each public mutation."""
    for name in ('step','run','write_memory','write_registers','breakpoint','delete_breakpoint',
                 'chip8_keypad','chip8_tick','chip8_seed_rng','layers','layer_enable','layer_patch',
                 'hook','delete_hook','save_state','load_state'):
        original=getattr(cls,name)
        def wrap(function,operation):
            signature=inspect.signature(function)
            has_timeout='timeout_ms' in signature.parameters
            @wraps(function)
            def invoke(self,*args,**kwargs):
                owner=self.vm
                bound=signature.bind(self,*args,**kwargs);bound.apply_defaults()
                timeout=bound.arguments.get('timeout_ms',10000)
                if type(timeout) is not int or not 1<=timeout<=600000:
                    return function(self,*args,**kwargs)
                deadline=time.monotonic()+timeout/1000
                prior=getattr(self,'_rpc_deadline',None)
                if prior is not None:deadline=min(deadline,prior)
                wait=min(10.0,max(0,deadline-time.monotonic()))
                if not wait or not owner.lock.acquire(timeout=wait):raise TimeoutError('CHIP-8 history mutation lock deadline expired')
                old_deadline=getattr(self,'_rpc_deadline',None)
                channels=[channel for channel in (getattr(owner,'qmp',None),getattr(owner,'gdb',None)) if channel is not None]
                old_channels=[getattr(channel,'operation_deadline',None) for channel in channels]
                try:
                    if self.vm is not owner:raise ValueError('CHIP-8 machine owner changed')
                    if time.monotonic()>=deadline:raise TimeoutError('CHIP-8 mutation deadline expired')
                    self._rpc_deadline=deadline
                    for channel,prior_channel in zip(channels,old_channels):
                        channel.operation_deadline=min(deadline,prior_channel) if prior_channel is not None else deadline
                    self._history_before_operation(operation,args,kwargs)
                    if has_timeout:
                        remaining=int((deadline-time.monotonic())*1000)
                        if remaining<1:raise TimeoutError('CHIP-8 mutation deadline expired')
                        kwargs=dict(kwargs,timeout_ms=remaining)
                    result=function(self,*args,**kwargs)
                    if time.monotonic()>=deadline:
                        error=TimeoutError('CHIP-8 mutation exceeded its outer deadline');error.result=result
                        try:self.close()
                        except Exception:pass
                        raise error
                    return result
                finally:
                    self._rpc_deadline=old_deadline
                    for channel,prior_channel in zip(channels,old_channels):channel.operation_deadline=prior_channel
                    if self.vm is not owner:
                        for name in ('qmp','gdb'):
                            channel=getattr(self.vm,name,None)
                            if channel is not None:channel.operation_deadline=old_deadline
                    owner.lock.release()
            return invoke
        setattr(cls,name,wrap(original,name))
    return cls
