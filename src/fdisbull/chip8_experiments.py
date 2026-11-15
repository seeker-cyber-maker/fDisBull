"""Bounded comparative trials from one verified CHIP-8 full checkpoint."""
from copy import deepcopy
import hashlib
import json
import time

from .qemu_dos_history import _history_operation
from .chip8_cpu_undo_runtime import validate_ranges
from .chip8_layers import _address
from .debug_state import byte_string
from .dosbox_rpc import DebuggerError

FORMAT='fdisbull-chip8-experiment-1'
COMPARISON_FORMAT='fdisbull-chip8-experiment-comparison-1'
KEY_SUBSET='fdisbull-chip8-frame-keys-6'
_ALLOWED={'step','run','registers','memory','screenshot','assert','delete-hook'}


def _json(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def _sha(data):return hashlib.sha256(data).hexdigest()


def _row(project,identifier,kind,version=None):
    index=project.db.execute('SELECT a.kind,r.version,fdb_length(a.data) AS size FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(identifier,)).fetchone()
    limit=(128 if kind=='state' else 16)*1024*1024
    if (index is None or index['kind']!=kind or version is not None and index['version']!=version or
            type(index['size']) is not int or not 0<index['size']<=limit):
        raise ValueError('CHIP-8 experiment artifact is missing or exceeds its bound')
    row=project.db.execute('SELECT a.*,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',(identifier,)).fetchone()
    if row is None or row['kind']!=kind or version is not None and row['version']!=version:
        raise ValueError('CHIP-8 experiment artifact identity differs')
    data=bytes(row['data'])
    if not data or _sha(data)!=row['sha256']:raise ValueError('CHIP-8 experiment artifact hash differs')
    try:metadata=json.loads(row['metadata'])
    except (ValueError,TypeError):raise ValueError('Malformed CHIP-8 experiment metadata') from None
    return row,data,metadata


def _script(script,session=None):
    from .debug_script import validate_script
    raw=_json(script)
    if len(raw)>1024*1024:raise ValueError('CHIP-8 trial script exceeds 1 MiB')
    steps=validate_script(script,session=session)
    if len(steps)>128 or any(step['op'] not in _ALLOWED for step in steps):
        raise ValueError('Unsupported or excessive CHIP-8 trial operations')
    if any(step.get('as')=='controls' for step in steps):raise ValueError('controls is reserved')
    screenshots=0;memory=0
    for step in steps:
        if step['op']=='memory':
            length=step.get('length',16)
            if type(length) is not int or not 1<=length<=4096 or step.get('space','physical') not in ('physical','virtual'):
                raise ValueError('CHIP-8 trial memory must use bounded flat RAM')
            address=step.get('address')
            if isinstance(address,str) and address.startswith('$'):raise ValueError('CHIP-8 trial memory address must be literal')
            _address(address,length);memory+=length
        if step['op']=='screenshot':
            screenshots+=1
            if step.get('grid',False) is not False:raise ValueError('CHIP-8 trial screenshot must be ungridded')
    if screenshots>4 or memory>65536:raise ValueError('CHIP-8 trial capture budget exceeded')
    return steps,memory


def _hooks_validate(steps,hooks):
    for step in steps:
        if step['op']=='delete-hook':
            value=step.get('hook');prefix='$controls.hooks.';suffix='.hook'
            if not isinstance(value,str) or not value.startswith(prefix) or not value.endswith(suffix) or value[len(prefix):-len(suffix)] not in hooks:
                raise ValueError('CHIP-8 trial may delete only a captured hook by reference')


def _report_budget(project,version,steps,hooks):
    runs=[step for step in steps if step['op']=='run']
    if hooks and any(step.get('stop_on_hook') is not True for step in runs):
        raise ValueError('CHIP-8 trials with hooks require stop_on_hook=True on every run')
    largest=0
    for hook in hooks:
        size=0
        for action in hook['actions']:
            size+=65536
            if action['op']=='layers':
                size+=sum(2*len(_json(item)) for item in _layer_definitions(project,version,action['layers']))
        largest=max(largest,size)
    # Each run can dispatch at most one bounded hook, and each stopped step
    # has a conservative allowance for native register, display and fetch data.
    estimate=len(_json(steps))+131072*len(steps)+len(runs)*largest
    if estimate>4*1024*1024:raise ValueError('CHIP-8 trial report plan exceeds 4 MiB per arm')
    return estimate


def _layer_definitions(project,version,ids):
    if not isinstance(ids,list) or len(ids)>64 or any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('Expected a bounded ordered CHIP-8 layer stack')
    definitions=[];count=0
    for identifier in ids:
        item=project.debug_layer_info(identifier)
        if (item.get('version')!=version or item.get('address_model')!='chip8-flat-4k' or
                item.get('chip8_profile')!='chip8-classic-pilot-default-v1' or item.get('kind') not in ('ram','execute')):
            raise ValueError('CHIP-8 experiment layer identity differs')
        count+=len(item['patches'])
        if count>256:raise ValueError('CHIP-8 experiment layer patch budget exceeded')
        definitions.append(item)
    return definitions


def _candidate(project,version,ids,snapshot):
    definitions=_layer_definitions(project,version,ids)
    hashes={item['id']:item['sha256'] for item in definitions}
    if ids==snapshot['layers']['active']:return hashes
    current=bytearray.fromhex(snapshot['ram_hex']);base=bytearray(current)
    state=snapshot['layers']
    for key,applied in state['ram_applied'].items():
        address=int(key)
        if current[address]!=applied:raise ValueError('Active CHIP-8 RAM layer has changed backing')
        base[address]=state['ram_base'][key]
    expected={}
    for definition in definitions:
        for patch in definition['patches']:
            before=byte_string(patch['expected_hex']);after=byte_string(patch['data_hex'])
            if len(before)!=len(after):raise ValueError('CHIP-8 layer cannot resize memory')
            address=_address(patch['address'],len(before))
            for offset,old in enumerate(before):
                loc=address+offset
                if expected.setdefault(loc,old)!=old:raise ValueError('CHIP-8 candidate layer guards disagree')
    if any(base[a]!=value for a,value in expected.items()):raise ValueError('CHIP-8 candidate expected base differs')
    return hashes


def _project_document(project,artifact,version=None):
    row,data,experiment_metadata=_row(project,artifact,'experiment',version)
    try:document=json.loads(data)
    except (ValueError,TypeError):raise ValueError('Malformed CHIP-8 experiment') from None
    if not isinstance(document,dict) or document.get('format')!=FORMAT or document.get('version')!=row['version']:
        raise ValueError('Invalid CHIP-8 experiment identity')
    if (project.meta.get('source_sha256')!=document.get('source_sha256') or
            project.version(row['version']).get('sha256')!=document.get('version_sha256')):
        raise ValueError('CHIP-8 experiment project source/version differs')
    if experiment_metadata != dict(format=FORMAT,checkpoint=document.get('checkpoint',{}).get('artifact'),
                                    script_sha256=document.get('script_sha256')):
        raise ValueError('CHIP-8 experiment artifact metadata differs')
    checkpoint=document.get('checkpoint')
    if not isinstance(checkpoint,dict) or set(checkpoint)!={'artifact','sha256','size','metadata_sha256'}:
        raise ValueError('Invalid CHIP-8 experiment checkpoint')
    state,payload,metadata=_row(project,checkpoint['artifact'],'state',row['version'])
    runtime=document.get('runtime')
    if (not isinstance(runtime,dict) or runtime.get('cpu_subset')!=KEY_SUBSET or
            runtime.get('profile')!='chip8-classic-pilot-default-v1' or
            not isinstance(document.get('origin_run'),str) or document['origin_run']!=row['run'] or state['run']!=row['run']):
        raise ValueError('CHIP-8 experiment native profile or origin run differs')
    if (state['sha256']!=checkpoint['sha256'] or len(payload)!=checkpoint['size'] or
            _sha(state['metadata'].encode())!=checkpoint['metadata_sha256'] or
            metadata.get('format')!='fdisbull-qemu-chip8-state-6' or metadata.get('identity')!=document.get('runtime') or
            metadata.get('host_files_restored') is not False):
        raise ValueError('CHIP-8 experiment full checkpoint differs')
    from .qemu_checkpoint import validate_qcow_header
    validate_qcow_header(payload[:104],1024*1024)
    if document.get('source_sha256')!=document.get('runtime',{}).get('source_sha256') or document.get('version_sha256')!=document.get('runtime',{}).get('version_sha256'):
        raise ValueError('CHIP-8 experiment source identity differs')
    script=document.get('script')
    if not isinstance(script,dict) or script.get('backend')!='qemu-chip8':raise ValueError('CHIP-8 experiment script backend differs')
    if _sha(_json(script))!=document.get('script_sha256'):raise ValueError('CHIP-8 experiment script hash differs')
    steps,_=_script(script);hooks=document.get('control_ids',{}).get('hooks')
    if not isinstance(hooks,dict):raise ValueError('CHIP-8 experiment controls missing')
    _hooks_validate(steps,hooks)
    observations=document.get('observations')
    if not isinstance(observations,list) or len(observations)>64:
        raise ValueError('Invalid CHIP-8 experiment observations')
    if observations:validate_ranges(observations)
    snapshot=document.get('snapshot')
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('ram_hex'),str) or snapshot.get('identity')!=document['runtime']:
        raise ValueError('CHIP-8 experiment snapshot identity missing or differs')
    try:ram=bytes.fromhex(snapshot['ram_hex'])
    except ValueError:raise ValueError('Invalid CHIP-8 experiment RAM') from None
    if len(ram)!=4096 or _sha(ram)!=metadata.get('ram_sha256') or snapshot.get('registers')!=metadata.get('registers'):
        raise ValueError('CHIP-8 experiment endpoint differs from checkpoint')
    if (snapshot.get('environment')!=metadata.get('environment') or snapshot.get('fault')!=metadata.get('fault') or
            snapshot.get('layers')!=metadata.get('layer_state') or snapshot.get('hooks')!=metadata.get('hook_state') or
            snapshot.get('layer_native')!=metadata.get('layer_native')):
        raise ValueError('CHIP-8 experiment checkpoint controls differ')
    key_state=metadata.get('key_state');raw_keys=snapshot.get('key_native')
    fields=('epoch','active','generation','accepted-edges','held-mask','key-mask','state-generation')
    if not isinstance(key_state,dict) or not isinstance(raw_keys,dict) or any(key_state.get(k)!=raw_keys.get(k) for k in fields):
        raise ValueError('CHIP-8 experiment checkpoint key ownership differs')
    logical={k:raw_keys[k] for k in ('active','held-mask','key-mask','accepted-edges')}
    if snapshot.get('keys')!=logical or document.get('controls',{}).get('keys')!=logical:
        raise ValueError('CHIP-8 experiment logical keys differ')
    if (document.get('controls',{}).get('hooks')!=snapshot['hooks'] or document.get('controls',{}).get('layers')!=snapshot['layers'] or
            document.get('controls',{}).get('key_native')!=raw_keys):
        raise ValueError('CHIP-8 experiment logical controls differ')
    try:cpu={k:int(v,16) for k,v in snapshot['registers']['registers'].items()}
    except (KeyError,TypeError,ValueError):raise ValueError('Malformed CHIP-8 experiment CPU') from None
    if cpu!=snapshot.get('cpu'):raise ValueError('CHIP-8 experiment CPU normalization differs')
    if len(snapshot.get('memory',[]))!=len(observations):raise ValueError('CHIP-8 experiment observation count differs')
    for item,actual_memory in zip(observations,snapshot['memory']):
        address=int(item['address'],0);chunk=ram[address:address+item['length']]
        expected_memory=dict(address=item['address'],length=len(chunk),hex=chunk.hex(),sha256=_sha(chunk))
        if expected_memory != actual_memory:raise ValueError('CHIP-8 experiment RAM observation differs')

    expected=document.get('layer_hashes')
    if not isinstance(expected,dict):raise ValueError('CHIP-8 experiment layer hashes missing')
    for item in _layer_definitions(project,row['version'],list(expected)):
        if expected.get(item['id'])!=item['sha256']:raise ValueError('CHIP-8 experiment layer hash differs')
    required=set(snapshot['layers']['active'])
    for hook in snapshot['hooks']['hooks']:
        for action in hook['actions']:
            if action['op']=='layers':required.update(action['layers'])
    if required!=set(expected):raise ValueError('CHIP-8 experiment layer hashes differ from controls')
    captured={h['hook']:deepcopy(h) for h in snapshot['hooks']['hooks']}
    if hooks!=captured:raise ValueError('CHIP-8 experiment hook bindings differ')
    _report_budget(project,row['version'],steps,snapshot['hooks']['hooks'])
    from .chip8_trial_observations import SEMANTIC
    try:
        expected_semantic={**{k:snapshot['environment'][k] for k in SEMANTIC},
                           'accepted-edges':logical['accepted-edges'],'held-mask':logical['held-mask'],
                           'fault':deepcopy(snapshot['fault'])}
    except (KeyError,TypeError):raise ValueError('CHIP-8 experiment semantic fields missing') from None
    if snapshot.get('semantic')!=expected_semantic:raise ValueError('CHIP-8 experiment semantic state differs')
    from .chip8_keys import validate_key_snapshot
    from .qemu_chip8 import _validate_environment, _fault_receipt
    from .chip8_layers import Chip8LayerMixin
    from types import SimpleNamespace
    _validate_environment(metadata['environment']);validate_key_snapshot(key_state,metadata['environment'])
    qmp=SimpleNamespace(call=lambda name:deepcopy(snapshot['fault'] if name=='query-chip8-fault' else snapshot['layer_native']))
    _fault_receipt(qmp,KEY_SUBSET)
    proxy=SimpleNamespace(vm=SimpleNamespace(qmp=qmp),project=project,version={'id':row['version']})
    layer=Chip8LayerMixin._chip8_layer_query(proxy)
    Chip8LayerMixin._chip8_layer_state_validate(proxy,snapshot['layers'],layer)
    if metadata['environment']['layer-generation']!=layer['generation']:
        raise ValueError('CHIP-8 experiment layer generation differs')
    return deepcopy(document)


def project_document(project,artifact,version=None):
    try:return _project_document(project,artifact,version)
    except (KeyError,TypeError,AttributeError,OverflowError,IndexError,DebuggerError) as error:
        raise ValueError('Malformed CHIP-8 experiment evidence') from error


class Chip8ExperimentMixin:
    def _history_before_operation(self,name,args=(),kwargs=None):
        # A rejected experiment preflight must not invalidate a retained live edge.
        # The actual effect boundary explicitly invalidates it below.
        if name in ('save_experiment','restore_experiment','compare_experiment'):
            history=getattr(self,'_qemu_cpu_delta_history',None)
            if history and history.get('frozen') and name!='restore_experiment':
                raise ValueError('Selected CHIP-8 partial state is frozen until full checkpoint recovery')
            return
        return super()._history_before_operation(name,args,kwargs)

    def _chip8_experiment_invalidate(self,name):
        history=getattr(self,'_qemu_cpu_delta_history',None)
        if history and history.get('valid'):
            history.update(valid=False,invalid_reason='unrecorded operation: '+name)
        live=getattr(self,'_qemu_history_live',None)
        if live and live.get('valid'):
            live.update(valid=False,cursor=None,invalid_reason='unrecorded operation: '+name)

    def _chip8_experiment_supported(self):
        if self.closed or self.identity.get('cpu_subset')!=KEY_SUBSET or self._checkpoint_tool is None:
            raise ValueError('CHIP-8 experiments require the v6 checkpoint backend')
        if self.project.db.in_transaction:raise ValueError('CHIP-8 experiments require no caller transaction')
        self._checkpoint_admit()

    def _chip8_experiment_snapshot(self,observations):
        from .chip8_trial_observations import SEMANTIC
        self._stopped();self._chip8_frame_idle();keys=self._chip8_keys_query()
        registers=self.registers();ram=self._memory(0,4096);environment=self.chip8_environment()
        native=self._chip8_layer_query();layers=self._chip8_layer_state();hooks=self._chip8_hook_state()
        from .qemu_chip8 import _fault_receipt
        fault=_fault_receipt(self.vm.qmp,self.identity['cpu_subset'])
        if (native['generation']!=layers['generation'] or environment['layer-generation']!=native['generation'] or
                keys['state-generation']!=environment['state-generation'] or keys['key-mask']!=environment['key-mask']):
            raise DebuggerError('CHIP-8 experiment control generations differ')
        if self.registers()!=registers or self.chip8_environment()!=environment:
            raise DebuggerError('CHIP-8 experiment changed during stopped observation')
        memory=[dict(address=r['address'],length=r['length'],hex=ram[int(r['address'],0):int(r['address'],0)+r['length']].hex(),
                     sha256=_sha(ram[int(r['address'],0):int(r['address'],0)+r['length']])) for r in observations]
        return dict(identity=deepcopy(self.identity),registers=registers,cpu={k:int(v,16) for k,v in registers['registers'].items()},ram_hex=ram.hex(),memory=memory,
                    environment=environment,semantic={**{k:environment[k] for k in SEMANTIC},'accepted-edges':keys['accepted-edges'],
                    'held-mask':keys['held-mask'],'fault':deepcopy(fault)},fault=fault,layers=layers,layer_native=native,hooks=hooks,
                    keys={k:keys[k] for k in ('active','held-mask','key-mask','accepted-edges')},key_native=keys)

    def _chip8_experiment_controls(self):
        hooks=self._chip8_hook_state();keys=self._chip8_keys_query()
        return dict(hooks=deepcopy(hooks),keys={k:keys[k] for k in ('active','held-mask','key-mask','accepted-edges')},
                    key_native=deepcopy(keys),layers=deepcopy(self._chip8_layer_state()))

    @_history_operation
    def controls(self):
        self._chip8_experiment_supported();return dict(run=self.run_id,**self._chip8_experiment_controls())

    @_history_operation
    def save_experiment(self,name,*,script=None,script_id=None,observations=None,timeout_ms=60000):
        from .external_files import _file_name
        _file_name(name);self._chip8_experiment_supported()
        if (script is None)==(script_id is None):raise ValueError('Supply exactly one experiment script')
        if script_id is not None:
            row=self.project.db.execute('SELECT script,sha256,version FROM debug_scripts WHERE id=?',(script_id,)).fetchone()
            if row is None or row['version']!=self.version['id'] or _sha(row['script'].encode())!=row['sha256']:
                raise ValueError('Unknown or corrupt CHIP-8 experiment script')
            script=json.loads(row['script'])
        steps,script_memory=_script(script,self)
        expanded=dict(format='fdisbull-script-1',backend='qemu-chip8',steps=deepcopy(steps))
        if observations is None:observations=[]
        if not isinstance(observations,list):raise ValueError('CHIP-8 experiment observations must be a list')
        obs=validate_ranges(observations) if observations else []
        obs=[{'address':r['address'],'length':r['length']} for r in obs]
        if script_memory+sum(r['length'] for r in obs)>65536:raise ValueError('CHIP-8 trial memory budget exceeded')
        before=self._chip8_experiment_snapshot(obs);hooks={h['hook']:deepcopy(h) for h in before['hooks']['hooks']}
        _hooks_validate(steps,hooks)
        ids=set(before['layers']['active'])
        for hook in before['hooks']['hooks']:
            for action in hook['actions']:
                if action['op']=='layers':ids.update(action['layers'])
        defs=_layer_definitions(self.project,self.version['id'],sorted(ids));hashes={d['id']:d['sha256'] for d in defs}
        _report_budget(self.project,self.version['id'],steps,before['hooks']['hooks'])
        from .qemu_experiments import _require_project_capacity
        _require_project_capacity(self.project,128*1024*1024+16*1024*1024)
        self._chip8_experiment_invalidate('save_experiment')
        state=self.save_state('chip8-experiment.qcow2',timeout_ms=self._history_remaining_ms())
        after=self._chip8_experiment_snapshot(obs)
        if before!=after:self.close();raise DebuggerError('CHIP-8 experiment changed during checkpoint capture')
        state_row=self.project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',(state['artifact'],)).fetchone()
        if state_row is None:self.close();raise ValueError('Missing CHIP-8 checkpoint metadata')
        checkpoint=dict(artifact=state['artifact'],sha256=state['sha256'],size=state['size'],metadata_sha256=_sha(state_row['metadata'].encode()))
        doc=dict(format=FORMAT,name=name,version=self.version['id'],source_sha256=self.metadata['source_sha256'],
            version_sha256=self.metadata['version_sha256'],runtime=deepcopy(self.identity),origin_run=self.run_id,
            checkpoint=checkpoint,snapshot=before,controls=self._chip8_experiment_controls(),control_ids={'hooks':hooks},
            layer_hashes=hashes,script=expanded,script_sha256=_sha(_json(expanded)),observations=obs)
        try:
            artifact=self._artifact(name,'experiment',_json(doc),dict(format=FORMAT,checkpoint=checkpoint['artifact'],script_sha256=doc['script_sha256']))
            project_document(self.project,artifact['artifact'],self.version['id'])
        except BaseException as error:
            error.result=dict(checkpoint=checkpoint,disposition='experiment publication uncertain; do not replay')
            self.close();raise
        return {**artifact,'format':FORMAT,'checkpoint':checkpoint,'controls':doc['controls'],
                'active_layers':before['layers']['active'],'observations':obs}

    @_history_operation
    def restore_experiment(self,experiment,*,timeout_ms=60000):
        self._chip8_experiment_supported();doc=project_document(self.project,experiment,self.version['id'])
        if doc['runtime']!=self.identity:raise ValueError('CHIP-8 experiment runtime differs')
        self._chip8_experiment_invalidate('restore_experiment')
        restored=self.load_state(doc['checkpoint']['artifact'],timeout_ms=self._history_remaining_ms())
        try:
            actual=self._chip8_experiment_snapshot(doc['observations']);expected=doc['snapshot']
            for key in ('registers','ram_hex','fault','layers','hooks','keys'):
                if actual[key]!=expected[key]:raise DebuggerError('Restored CHIP-8 experiment '+key+' differs')
            native_before=dict(expected['layer_native']);native_after=dict(actual['layer_native'])
            native_before.pop('stop-owned');native_after.pop('stop-owned')
            if native_before!=native_after or actual['layer_native']['stop-owned']:
                raise DebuggerError('Restored CHIP-8 experiment native layers differ')
            before=dict(expected['environment']);after=dict(actual['environment'])
            before.pop('key-wait-stop-owned');after.pop('key-wait-stop-owned')
            if before!=after or actual['environment']['key-wait-stop-owned']:
                raise DebuggerError('Restored CHIP-8 experiment environment differs')
            controls={'hooks':{h['hook']:{'hook':h['hook']} for h in actual['hooks']['hooks']},'breakpoints':{}}
            return dict(experiment=experiment,checkpoint=restored,controls=controls,active_layers=actual['layers']['active'],task_layers={})
        except BaseException:self.close();raise

    @_history_operation
    def compare_experiment(self,experiment,*,layers,timeout_ms=60000):
        from .debug_script import execute_script
        from .chip8_trial_observations import capture_trial,compare_trials
        from .qemu_experiments import _require_project_capacity
        self._chip8_experiment_supported();doc=project_document(self.project,experiment,self.version['id'])
        if doc['runtime']!=self.identity:raise ValueError('CHIP-8 experiment runtime differs')
        steps,_=_script(doc['script'],self)
        _report_budget(self.project,self.version['id'],steps,doc['snapshot']['hooks']['hooks'])
        hashes=_candidate(self.project,self.version['id'],layers,doc['snapshot'])
        _require_project_capacity(self.project,3*16*1024*1024+10*1024*1024)
        self._chip8_experiment_invalidate('compare_experiment')
        deadline=min(self._deadline,time.monotonic()+timeout_ms/1000)
        result=dict(format=COMPARISON_FORMAT,experiment=experiment,checkpoint=deepcopy(doc['checkpoint']),
            script_sha256=doc['script_sha256'],layer_hashes=hashes,baseline=None,layer=None,comparison=None,
            ok=False,error=None,baseline_restored=False)
        dispatched=False;arm=None
        try:
            for arm in ('baseline','layer'):
                remaining=int((deadline-time.monotonic())*1000)
                if remaining<1:raise TimeoutError('CHIP-8 trial deadline expired')
                restored=self.restore_experiment(experiment,timeout_ms=remaining)
                if arm=='layer':
                    if _candidate(self.project,self.version['id'],layers,doc['snapshot'])!=hashes:
                        raise ValueError('CHIP-8 candidate layer definition changed')
                    if layers!=doc['snapshot']['layers']['active']:self.layers(layers)
                remaining=int((deadline-time.monotonic())*1000)
                if remaining<1:raise TimeoutError('CHIP-8 trial deadline expired')
                reserve=min(10000,max(50,remaining//4))
                if remaining<=reserve:raise TimeoutError('CHIP-8 trial cannot reserve final restore budget')
                dispatched=True
                report=execute_script(self,doc['script'],timeout_ms=remaining-reserve,bindings={'controls':restored['controls']})
                result[arm]=dict(format='fdisbull-chip8-trial-observations-1',ok=False,complete=False,
                                 incomplete_reasons=['evidence_pending'],script_report=report.get('artifact'),
                                 raw_report=deepcopy(report))
                if len(_json(report))>4*1024*1024:raise ValueError('CHIP-8 trial report exceeded its bound')
                trial=capture_trial(self,doc,report)
                if len(_json(trial))>4*1024*1024:raise ValueError('CHIP-8 trial evidence exceeded its bound')
                result[arm]=trial;dispatched=False
                if not trial['ok'] or not trial['complete']:
                    result['error']=dict(type='ScriptFailure',trial=arm,error=trial.get('incomplete_reasons'));break
            if result['baseline'] is not None and result['layer'] is not None:
                result['comparison']=compare_trials(result['baseline'],result['layer']);result['ok']=result['comparison']['complete']
        except BaseException as error:
            result['error']=dict(type=type(error).__name__,message=str(error),cause_result=deepcopy(getattr(error,'result',None)))
            if dispatched and arm is not None and result[arm] is None:
                result[arm]=dict(format='fdisbull-chip8-trial-observations-1',ok=False,complete=False,
                                 incomplete_reasons=['dispatch_uncertain'],cause_result=deepcopy(getattr(error,'result',None)))
            if dispatched or self.closed:
                result['error'].update(uncertain=True,do_not_replay=True)
                if not self.closed:self.close()
                result['error']['owner_closed']=bool(self.closed)
        finally:
            if not self.closed and time.monotonic()<deadline:
                try:
                    self.restore_experiment(experiment,timeout_ms=max(1,int((deadline-time.monotonic())*1000)))
                    result['baseline_restored']=True
                except BaseException as error:
                    result['error']=dict(type=type(error).__name__,message='Final full restore: '+str(error),
                                         cause_result=deepcopy(getattr(error,'result',None)),uncertain=True,do_not_replay=True)
                    self.close();result['error']['owner_closed']=bool(self.closed)
            elif not self.closed:
                self.close()
                if result['error'] is None:result['error']=dict(type='TimeoutError',message='Final full restore deadline expired')
                result['error'].update(uncertain=True,do_not_replay=True,owner_closed=bool(self.closed))
            if not result['baseline_restored']:result['ok']=False
        try:
            encoded=_json(result)
            if len(encoded)>16*1024*1024:raise ValueError('CHIP-8 comparison report exceeded its bound')
            artifact=self._artifact('chip8-experiment-comparison.json','experiment-comparison',encoded,
                dict(format=COMPARISON_FORMAT,experiment=experiment,baseline_restored=result['baseline_restored']))
            return {**result,'artifact':artifact['artifact']}
        except BaseException as error:
            error.result=deepcopy(result);self.close();raise
