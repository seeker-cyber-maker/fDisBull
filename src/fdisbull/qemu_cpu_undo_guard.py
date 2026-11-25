"""Freeze selected native undo until a verified full native restore succeeds."""
from copy import deepcopy
from functools import wraps
import inspect
import json
import math
import time


CPU_OPERATIONS = frozenset({'cpu_delta_start','cpu_delta_status','cpu_delta_record',
                            'cpu_delta_rewind','cpu_delta_recover'})
READ_ONLY = frozenset({'cpu_delta_status','status','registers','memory','memory_translation','code',
    'frame_probe','frame_rgba','_frame_screenshot',
    'bind_runtime_memory','runtime_memory','scene_check','scene_assert',
    'dos_process_info','dos_source_admit','dos_source_bind','dos_source_binding','dos_source_unbind','_le_source_refresh','tracking_status','dos_task_observe','dos_task_context','dos_task_scheduler_observe',
    'dos_task_memory','hooks','layer_stack','clock_observe','audio_observe', 'mixer_observe',
    'display_observe','retrace_observe','input_state','keyboard_state','observe_int33_mouse',
    'rewind_status','timeline_status','timeline_image','controls','close',
    'workspace_status','workspace_files','workspace_read','workspace_provenance_status',
    'breakpoints_list'})
FULL_RECOVERY = frozenset({'cpu_delta_recover','rewind','timeline_rewind','restore_experiment'})
_MACHINE_SCOPE = '_qemu_cpu_delta_machine_restore_scope'


def _deadline_values(session, vm):
    return (getattr(session,'_deadline',None),getattr(session,'_rpc_deadline',None),
            getattr(vm,'operation_deadline',None),
            *(getattr(channel,'operation_deadline',None) for channel in
              (getattr(vm,'qmp',None),getattr(vm,'gdb',None)) if channel is not None))


class _MachineRestoreScope:
    """An unexported invocation identity; JSON receipts cannot issue it."""
    def __init__(self, session):
        self.session=session
        self.vm=getattr(session,'vm',None)
        self.lock=getattr(self.vm,'lock',None)
        self.project=getattr(session,'project',None)
        self.run=getattr(session,'run_id',None)
        self.version=deepcopy(getattr(session,'version',None))
        metadata=getattr(session,'metadata',{})
        self.source=(metadata.get('source_sha256'),metadata.get('version_sha256'))
        self.epoch=getattr(session,'_runtime_epoch',self.run)
        self.checkpoint=getattr(session,'_checkpoint_epoch',None)
        self.deadlines=_deadline_values(session,self.vm)
        self.attestation=None


def _machine_deadline(scope, session, retained=None):
    bounds=[value for value in (*scope.deadlines,*_deadline_values(session,session.vm),retained)
            if value is not None]
    if not bounds or any(type(value) not in (int,float) or not math.isfinite(value) for value in bounds):
        raise ValueError('Machine restore attestation requires a finite full loader deadline')
    deadline=min(bounds)
    if time.monotonic() >= deadline:
        raise TimeoutError('Machine restore full loader deadline expired')
    return deadline


def _machine_transition(scope, session):
    vm=getattr(session,'vm',None)
    epoch=getattr(session,'_runtime_epoch',getattr(session,'run_id',None))
    checkpoint=getattr(session,'_checkpoint_epoch',None)
    metadata=getattr(session,'metadata',{})
    if (scope.session is not session or scope.vm is None or vm is None or vm is scope.vm
            or scope.lock is None or getattr(vm,'lock',None) is not scope.lock
            or scope.project is None or session.project is not scope.project
            or type(scope.run) is not str or not scope.run or session.run_id != scope.run
            or scope.version is None or session.version != scope.version
            or (metadata.get('source_sha256'),metadata.get('version_sha256')) != scope.source
            or type(epoch) is not str or not epoch or epoch == scope.epoch
            or type(scope.checkpoint) is not int or type(checkpoint) is not int
            or checkpoint <= scope.checkpoint or getattr(session,'closed',True)
            or getattr(vm,'qmp',None) is None
            or getattr(vm,'_fdisbull_control_quarantine',None)
            or not callable(getattr(getattr(vm,'process',None),'poll',None))
            or vm.process.poll() is not None):
        raise ValueError('Machine restore full loader owner or epoch identity differs')
    for channel in (vm.qmp,getattr(vm,'gdb',None)):
        if channel is not None and hasattr(channel,'socket') and channel.socket is None:
            raise ValueError('Machine restore full loader transport is closed')
    return vm,epoch,checkpoint


def _machine_receipt(result, epoch, checkpoint):
    if (not isinstance(result,dict) or result.get('machine_state_restored') is not True
            or result.get('source_binding_restored') is not False
            or type(result.get('artifact')) is not str or not result['artifact']
            or type(result.get('sha256')) is not str or len(result['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in result['sha256'])
            or result.get('capture_epoch') != epoch
            or type(result.get('checkpoint_epoch')) is not int
            or result['checkpoint_epoch'] != checkpoint):
        raise ValueError('Machine restore full loader receipt differs')
    try:
        return json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    except (TypeError,ValueError) as error:
        raise ValueError('Machine restore full loader receipt must be JSON') from error


def attest_machine_restore(session, result):
    """Attest only at a trusted full loader's final verified publication point.

    This private signal stays outside the public JSON receipt. It does not
    establish source ownership or make a selected projection valid again.
    """
    scope=getattr(session,_MACHINE_SCOPE,None)
    if not isinstance(scope,_MachineRestoreScope) or scope.session is not session:
        raise ValueError('Machine restore attestation requires an active full loader')
    if scope.attestation is not None:
        raise ValueError('Machine restore full loader already issued its attestation')
    deadline=_machine_deadline(scope,session)
    vm,epoch,checkpoint=_machine_transition(scope,session)
    encoded=_machine_receipt(result,epoch,checkpoint)
    _machine_deadline(scope,session,deadline)
    scope.attestation=(result,encoded,vm,vm.process,epoch,checkpoint,deadline)


def _verify_machine_attestation(scope, session, result, proof):
    original,encoded,vm,process,epoch,checkpoint,deadline=proof
    _machine_deadline(scope,session,deadline)
    current,current_epoch,current_checkpoint=_machine_transition(scope,session)
    if (result is not original or current is not vm or current.process is not process
            or (current_epoch,current_checkpoint) != (epoch,checkpoint)
            or _machine_receipt(result,epoch,checkpoint) != encoded):
        raise ValueError('Machine restore full loader attestation changed before return')
    _machine_deadline(scope,session,deadline)


def _quarantine_machine_restore(session, error):
    """A post-return proof failure is outside the core loader's cleanup scope."""
    vm=getattr(session,'vm',None)
    if vm is not None:
        try:
            vm._fdisbull_control_quarantine=(getattr(vm,'_fdisbull_control_quarantine',None)
                                           or 'failed full machine restore attestation')
        except BaseException as cleanup:
            error.machine_restore_quarantine_error=type(cleanup).__name__
    close=getattr(session,'close',None) or getattr(vm,'close',None)
    if close is not None:
        try:close()
        except BaseException as cleanup:
            error.machine_restore_cleanup_error=type(cleanup).__name__


def before_operation(session, name, args=(), kwargs=None):
    kwargs = kwargs or {}
    if (getattr(session,'_qemu_cpu_delta_busy',False)
            or getattr(session,'_qemu_cpu_delta_full_load_depth',0)):
        return
    readonly = name in READ_ONLY
    if name in ('layers','dos_task_layers'):
        readonly = kwargs.get('active',args[0] if args else None) is None
    history = getattr(session,'_qemu_cpu_delta_history',None)
    if history is not None:
        if history.get('frozen') and not readonly and name not in FULL_RECOVERY:
            raise ValueError('Selected CPU/RAM partial state is frozen; load a full process checkpoint before mutation or capture')
        if history.get('valid') and not readonly and name not in CPU_OPERATIONS:
            history.update(valid=False,invalid_reason='unrecorded operation: '+str(name))
            session._event('cpu-delta-invalidated',dict(history=history['id'],reason=history['invalid_reason']))
    if name in CPU_OPERATIONS - {'cpu_delta_status'}:
        live = getattr(session,'_qemu_history_live',None)
        if live and live.get('valid'):
            live.update(valid=False,cursor=None,invalid_reason='selected CPU/RAM operation: '+str(name))


def full_load(function):
    """Bypass the freeze only inside the existing fully validated loader."""
    signature=inspect.signature(function)
    def finish_load(session,*args,**kwargs):
        previous = getattr(session,'_qemu_cpu_delta_full_load_depth',0)
        had_scope=hasattr(session,_MACHINE_SCOPE)
        previous_scope=getattr(session,_MACHINE_SCOPE,None)
        scope=_MachineRestoreScope(session)
        setattr(session,_MACHINE_SCOPE,scope)
        session._qemu_cpu_delta_full_load_depth = previous + 1
        try:
            result = function(session,*args,**kwargs)
        finally:
            proof=scope.attestation
            scope.attestation=None
            if had_scope:setattr(session,_MACHINE_SCOPE,previous_scope)
            else:delattr(session,_MACHINE_SCOPE)
            session._qemu_cpu_delta_full_load_depth = previous
        complete = getattr(session,'_cpu_delta_full_restore_complete',None)
        if proof is not None:
            try:_verify_machine_attestation(scope,session,result,proof)
            except BaseException as error:
                _quarantine_machine_restore(session,error)
                raise
            if complete is not None:complete()
        elif (complete is not None and isinstance(result,dict)
                and result.get('source_binding_restored') is True):
            complete()
        return result

    @wraps(function)
    def load(session,*args,**kwargs):
        owner=getattr(session,'vm',None)
        lock=getattr(owner,'lock',None)
        if lock is None:
            return finish_load(session,*args,**kwargs)
        from .operation_budget import request_deadline
        arguments=signature.bind(session,*args,**kwargs)
        arguments.apply_defaults()
        deadline=request_deadline(session,arguments.arguments.get('timeout_ms',60000))
        def bounded_deadline():
            values=[value for value in (deadline,*_deadline_values(session,owner)) if value is not None]
            if any(type(value) not in (int,float) or not math.isfinite(value) for value in values):
                raise ValueError('Full restore requires a finite loader deadline')
            return min(values)
        deadline=bounded_deadline()
        wait=min(10.,deadline-time.monotonic())
        if wait<=0 or not lock.acquire(timeout=wait):
            raise TimeoutError('Full restore deadline expired waiting for the machine')
        try:
            if session.vm is not owner or getattr(owner,'lock',None) is not lock:
                raise ValueError('Machine owner changed before full restore admission')
            deadline=bounded_deadline()
            if time.monotonic()>=deadline:
                raise TimeoutError('Full restore deadline expired before admission')
            # Read the prior value only after acquiring the lock: a queued
            # loader must not restore another call's temporary RPC deadline.
            had_rpc=hasattr(session,'_rpc_deadline')
            previous_rpc=getattr(session,'_rpc_deadline',None)
            session._rpc_deadline=deadline
            try:return finish_load(session,*args,**kwargs)
            finally:
                if had_rpc:session._rpc_deadline=previous_rpc
                else:delattr(session,'_rpc_deadline')
        finally:lock.release()
    return load
