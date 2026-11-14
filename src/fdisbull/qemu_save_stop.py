"""Owned native post-flush stops and outer-public-run save keep service.

Native stopping, durable acknowledgement and host publication are distinct.
No ready-state polling, hidden continue, or publication from internal execution.
"""
from copy import deepcopy
from functools import wraps
import time

MODEL='qemu-pc-dos-save-stop-v1'
QUERY='x-fdisbull-query-dos-save-stop'
SET='x-fdisbull-set-dos-save-stop'
ACK='x-fdisbull-ack-dos-save-stop'
COMMANDS=frozenset((QUERY,SET,ACK))


def safe_stop_enabled(session):
    binding=getattr(session,'_dos_save_witness',None) or {}
    return bool(binding.get('safe_stop') and not binding.get('safe_stop_disarmed'))


def validate(info):
    if not isinstance(info,dict) or info.get('api-version')!=1 or info.get('model')!=MODEL:
        raise ValueError('Unsupported native DOS save-stop receipt')
    for key in ('enabled','acknowledged','pending'):
        if type(info.get(key)) is not bool:raise ValueError('Invalid save-stop '+key)
    for key in ('epoch','generation','observer-generation','sequence','witness-generation',
                'event-count','return-pc','return-cs','return-ss','return-sp'):
        value=info.get(key)
        maximum=0xffff if key in ('return-cs','return-ss','return-sp') else 0xfffff if key=='return-pc' else 256 if key=='event-count' else (1<<64)-1
        if type(value) is not int or not 0<=value<=maximum:
            raise ValueError('Invalid save-stop '+key)
    if not info['epoch'] or not info['generation']:
        raise ValueError('Save-stop owner counters are missing')
    if not isinstance(info.get('observer-token'),str) or not isinstance(info.get('reason'),str):
        raise ValueError('Save-stop owner or reason is malformed')
    state=info.get('state')
    if (state not in ('idle','pending','consumed','preempted','invalid')
            or info['pending']!=(state=='pending')
            or state=='idle' and (info['sequence'] or not info['acknowledged'])
            or state in ('pending','consumed','preempted') and not info['sequence']
            or state=='pending' and info['acknowledged']):
        raise ValueError('Inconsistent save-stop attempt state')
    return deepcopy(info)


def query(vm):
    if not COMMANDS<=getattr(vm,'qmp_commands',set()):
        raise ValueError('Automatic save stops require the native N24 extension')
    return validate(vm.qmp.call(QUERY))


def bound(session,info,native=None):
    from .qemu_dos_provenance import query as witness_query, _bound
    native=witness_query(session.vm) if native is None else native
    binding=_bound(session,native)
    if (not binding.get('safe_stop') or binding.get('mode')!='save' or not binding.get('policy_id')
            or info['observer-token']!=binding['observer_token']
            or info['observer-generation']!=native['generation']):
        raise ValueError('Save-stop receipt does not bind the owned save policy')
    return binding,native


def checkpoint_record(session,native):
    info=query(session.vm);bound(session,info,native)
    if info['pending'] or info['state']=='invalid':
        raise ValueError('Resolve the native save-stop handoff before checkpointing')
    return info


def validate_checkpoint_record(record,native,binding):
    info=validate(record)
    if (info['pending'] or info['state']=='invalid'
            or info['observer-token']!=binding['observer_token']
            or info['observer-generation']!=native['generation']):
        raise ValueError('Invalid checkpointed save-stop ownership')


def verify_loaded(vm,record,native):
    actual=query(vm)
    expected=deepcopy(record);left=deepcopy(actual)
    for key in ('epoch','generation','observer-generation'):
        expected.pop(key,None);left.pop(key,None)
    if (left!=expected or actual['epoch']<=record['epoch']
            or actual['generation']<=record['generation']
            or actual['observer-generation']!=native['generation']):
        raise ValueError('Restored native save-stop state differs from checkpoint')
    return actual


def _alive(session):
    return (not getattr(session,'closed',False)
            and not (getattr(session,'_process',None) or {}).get('machine_closed',False)
            and getattr(session.vm,'qmp',None) is not None)


def _close_preserving(session,error):
    try:
        session.close()
    except BaseException as closing:
        prior=getattr(error,'result',None)
        error.result=dict(previous=prior,closing_error=str(closing))


def _remaining(session):
    limits=[v for v in (getattr(session,'_rpc_deadline',None),getattr(session.vm,'operation_deadline',None)) if v is not None]
    if limits and time.monotonic()>=min(limits):raise TimeoutError('Save keep outer run deadline expired')


def _ack(session,info,reason):
    if info['pending'] or info['state']=='invalid':raise ValueError('Unresolved native save-stop attempt')
    if info['acknowledged']:return info,None
    from .qemu_dos_provenance import _json,_sha
    data=_json(dict(format=MODEL,reason=reason,native=info))
    ref=session._artifact('dos-save-stop.json','workspace-save-stop-record',data,dict(format=MODEL))
    if ref['sha256']!=_sha(data):raise ValueError('Save-stop acknowledgement receipt differs')
    try:
        _remaining(session)
        after=validate(session.vm.qmp.call(ACK,{'token':info['observer-token'],'epoch':info['epoch'],
            'expected-generation':info['generation'],'sequence':info['sequence']}))
    except BaseException as error:
        error.result=dict(save_stop=info,acknowledgement_record=ref,disposition='uncertain ACK; do not replay')
        raise
    if (not after['acknowledged'] or after['pending'] or after['sequence']!=info['sequence']
            or after['state']!=info['state'] or after['epoch']!=info['epoch']
            or after['generation']<=info['generation']):
        error=ValueError('Native save-stop acknowledgement did not match')
        error.result=dict(save_stop=info,observed=after,acknowledgement_record=ref,disposition='uncertain ACK; do not replay')
        raise error
    return after,ref


def _set(session,info,enabled):
    if info['enabled']==enabled:return info
    _remaining(session)
    after=validate(session.vm.qmp.call(SET,{'token':info['observer-token'],'epoch':info['epoch'],
        'expected-generation':info['generation'],'enabled':enabled}))
    if (after['enabled']!=enabled or after['epoch']!=info['epoch']
            or after['generation']<=info['generation'] or after['sequence']!=info['sequence']
            or after['state']!=info['state'] or after['acknowledged']!=info['acknowledged']):
        raise ValueError('Native save-stop policy configuration did not match')
    return after


def before_execute(session,command):
    if not safe_stop_enabled(session):return None
    from .qemu_dos_provenance import query as witness_query
    from .dos_keep_policy import KeepPolicyStore
    from .qemu_workspace_output import _context
    try:
        native=witness_query(session.vm)
        if not native or not native['active']:
            raise ValueError('Expected active native save-stop owner is missing')
        info=query(session.vm);binding,_=bound(session,info,native)
    except BaseException as error:
        error.result=dict(disposition='unverified save-stop owner before execution; do not replay')
        _close_preserving(session,error);raise
    scope=getattr(session,'_save_stop_run_scope',None)
    desired=bool(scope is not None and scope.owns and native['valid']
                 and not binding.get('host_fault')
                 and KeepPolicyStore(session).status(binding['policy_id'])['enabled'])
    if desired:_context(session) # Reject inadmissible owned execution before dispatch.
    try:
        info,ref=_ack(session,info,'reconcile prior attempt before explicit execution; no publication')
        if ref and scope is not None:scope.reconciled.append(ref)
        configured=_set(session,info,desired)
        if ref:configured['_prior_acknowledgement']=ref
        return configured
    except BaseException as error:
        error.result=dict(save_stop=info,control_effects=getattr(error,'result',None),
                          disposition='uncertain control state; do not replay')
        _close_preserving(session,error);raise


def _number(value):
    return int(value,0) if isinstance(value,str) else value


def after_execute(session,result,before):
    if before is None:return result
    from .qemu_dos_provenance import query as witness_query
    try:
        info=query(session.vm);native=witness_query(session.vm);bound(session,info,native)
        if before.get('_prior_acknowledgement'):
            result['save_stop_prior_acknowledgements']=[deepcopy(before['_prior_acknowledgement'])]
        if info['epoch']!=before['epoch'] or info['sequence']<before['sequence']:
            raise ValueError('Save-stop owner changed during execution')
        if info['sequence']==before['sequence']:return result
        if info['sequence']!=before['sequence']+1 or info['pending'] or info['acknowledged'] or info['state'] not in ('consumed','preempted'):
            raise ValueError('Save-stop attempt did not settle exactly once')
        result['save_stop']=deepcopy(info)
        reason=result.get('session',{}).get('stop_reason',{})
        regs=result.get('registers') or {};values=regs.get('registers',{})
        pc=_number(regs.get('linear_pc'))
        sp=values.get('rsp',values.get('esp',values.get('sp')))
        exact=(pc==info['return-pc'] and _number(values.get('cs'))==info['return-cs']
               and _number(values.get('ss'))==info['return-ss'] and type(_number(sp)) is int
               and _number(sp)&0xffff==info['return-sp'])
        reply=reason.get('native_reply','')
        fields={f.split(':',1)[0] for f in reply[3:].split(';') if f}
        last=native['events'][-1] if native['events'] else {}
        pure=(last.get('function')==0x0d and last.get('return-pc')==info['return-pc']
              and info['state']=='consumed' and info['witness-generation']==native['generation']
              and info['event-count']==native['event-count'] and native['valid'] and native['phase']=='ready'
              and native['pending'] is False and not native['hardware-interrupt-depth']
              and result.get('outcome')=='stopped' and result.get('timed_out') is False
              and reason.get('breakpoint_ids')==[] and reply[:3] in ('T02','S02')
              and not fields&{'watch','rwatch','awatch','swbreak','hwbreak'}
              and not any(k in result for k in ('layer_conflict','clock_budget','frame','guest_exit','guest_tsr'))
              and exact)
        deferred=[key for key,bp in getattr(session,'breakpoints',{}).items()
                  if bp.get('access')=='x' and bp.get('address')==pc]
        if deferred:result['save_stop_deferred_controls']=deferred;pure=False
        if pure:
            result['native_save_machine_stop']=deepcopy(reason)
            result['outcome']='save_boundary'
            result['session']['stop_reason']=dict(reason,kind='save_boundary')
            if isinstance(result.get('stop'),dict):result['stop']=dict(result['stop'],trigger='save_boundary',native_kind='save_boundary')
        else:result['save_boundary_conflict']=True
        return result
    except BaseException as error:
        error.result=dict(execution=deepcopy(result),save_stop=getattr(error,'result',None),
                          disposition='unverified native stop; do not replay')
        _close_preserving(session,error);raise


class SaveRunScope:
    def __init__(self,session):
        self.session=session;self.result=None;self.reconciled=[];self.entered=False

    def __enter__(self):
        s=self.session;self.previous=getattr(s,'_save_stop_run_scope',None)
        self.owns=bool(self.previous is None and not getattr(s,'_history_busy',False)
                      and not getattr(s,'_save_keep_suppressed_depth',0))
        self.old_deadline=getattr(s,'_deadline',None);self.old_rpc=getattr(s,'_rpc_deadline',None)
        limits=[v for v in (self.old_deadline,self.old_rpc,getattr(s.vm,'operation_deadline',None)) if v is not None]
        if not limits:raise ValueError('Automatic save run requires an outer deadline')
        s._deadline=s._rpc_deadline=min(limits);s._save_stop_run_scope=self;self.entered=True
        return self

    def finish(self,result):
        self.result=result
        if self.reconciled:result['save_stop_prior_acknowledgements']=deepcopy(self.reconciled)
        if not self.owns or result.get('outcome')!='save_boundary' or result.get('save_boundary_conflict'):
            return result
        from .qemu_dos_provenance import service_policy
        from .qemu_workspace import _seal_workspace
        kept=None
        try:
            _remaining(self.session)
            sealed=_seal_workspace(self.session)
            result['save_keep']=dict(checkpoint=sealed['checkpoint'],workspace=deepcopy(sealed['workspace']))
            kept=service_policy(self.session,sealed)
            result['save_keep']['policy']=kept
            if kept is None or kept.get('outcome') not in ('kept','already-kept','needs-reconciliation'):
                raise ValueError('Owned save boundary did not yield an admitted keep policy')
            _remaining(self.session)
            return result
        except BaseException as error:
            error.result=dict(execution=deepcopy(result),keep_effects=getattr(error,'result',None),
                              disposition='do not replay automatic keep')
            _close_preserving(self.session,error);raise

    def __exit__(self,kind,error,traceback):
        s=self.session
        try:
            if self.entered and _alive(s):
                info=query(s.vm);bound(s,info)
                info,ref=_ack(s,info,'settled explicit public run' if self.owns else 'internal execution; no automatic publication')
                final=_set(s,info,bool(self.previous is not None and self.previous.owns))
                if isinstance(self.result,dict):
                    self.result['save_stop_cleanup']=dict(native=final,acknowledgement=ref)
                _remaining(s)
        except BaseException as cleanup:
            _close_preserving(s,cleanup)
            effects=dict(execution=deepcopy(self.result),cleanup_error=str(cleanup),
                         control_effects=getattr(cleanup,'result',None),
                         disposition='uncertain save-stop cleanup; do not replay')
            if error is not None:
                error.result=dict(previous=getattr(error,'result',None),cleanup=effects)
            else:
                cleanup.result=effects
                raise cleanup

        finally:
            if self.entered:
                s._save_stop_run_scope=self.previous;s._deadline=self.old_deadline;s._rpc_deadline=self.old_rpc
        return False


def no_automatic_keeps(function):
    @wraps(function)
    def invoke(session,*args,**kwargs):
        if not safe_stop_enabled(session):return function(session,*args,**kwargs)
        previous=getattr(session,'_save_keep_suppressed_depth',0)
        session._save_keep_suppressed_depth=previous+1
        try:return function(session,*args,**kwargs)
        finally:session._save_keep_suppressed_depth=previous
    return invoke
