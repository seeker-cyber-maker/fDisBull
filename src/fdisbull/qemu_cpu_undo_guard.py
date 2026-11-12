"""Freeze selected native undo until a verified full process restore succeeds."""
from functools import wraps


CPU_OPERATIONS = frozenset({'cpu_delta_start','cpu_delta_status','cpu_delta_record',
                            'cpu_delta_rewind','cpu_delta_recover'})
READ_ONLY = frozenset({'cpu_delta_status','status','registers','memory','memory_translation','code',
    'dos_process_info','dos_task_observe','dos_task_context','dos_task_scheduler_observe',
    'dos_task_memory','hooks','layer_stack','clock_observe','audio_observe',
    'display_observe','retrace_observe','input_state','keyboard_state',
    'rewind_status','timeline_status','timeline_image','controls','close',
    'workspace_status','workspace_files','workspace_read'})
FULL_RECOVERY = frozenset({'cpu_delta_recover','rewind','timeline_rewind','restore_experiment'})


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
    @wraps(function)
    def load(session,*args,**kwargs):
        previous = getattr(session,'_qemu_cpu_delta_full_load_depth',0)
        session._qemu_cpu_delta_full_load_depth = previous + 1
        try:
            result = function(session,*args,**kwargs)
        finally:
            session._qemu_cpu_delta_full_load_depth = previous
        complete = getattr(session,'_cpu_delta_full_restore_complete',None)
        if (complete is not None and isinstance(result,dict)
                and result.get('source_binding_restored') is True):
            complete()
        return result
    return load
