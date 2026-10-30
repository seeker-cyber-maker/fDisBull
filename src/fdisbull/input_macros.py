"""Immutable game-control vocabularies above unchanged physical primitives."""
from copy import deepcopy
import hashlib
import json
import re
import time
from .operation_budget import rpc_budget

MACRO_DDL = '''
CREATE TABLE IF NOT EXISTS debug_macro_sets(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 parent TEXT REFERENCES debug_macro_sets(id), created TEXT NOT NULL,
 author TEXT NOT NULL, sha256 TEXT NOT NULL, document TEXT NOT NULL);
'''
AUTHORITIES = {'player-input','authoring','diagnostic'}
PRIMITIVES = {'keyboard.press','keyboard.type','keyboard.state','keyboard.key-down','keyboard.key-up',
              'run','wait','assert','scene-check','scene-assert','scene-click','scene-act','scene-wait',
              'frame-probe','registers','memory','status','screenshot'}

# Only guaranteed fields are eligible for result references. More complex or
# backend-specific structures require an explicitly reviewed schema addition.
_RESULT_PATHS = {
    'keyboard.key-down': {'lease','key','run','claim','accepted','delivery','session_id','state_revision',
                          'keyboard.pending_events','keyboard.owned_keys','keyboard.queued_guest_ms'},
    'keyboard.key-up': {'lease','key','consumed','claim','accepted','delivery','session_id','state_revision',
                        'keyboard.pending_events','keyboard.owned_keys','keyboard.queued_guest_ms'},
    'keyboard.press': {'accepted','delivery','session_id','state_revision','keyboard.pending_events','keyboard.owned_keys','keyboard.queued_guest_ms'},
    'keyboard.type': {'accepted','delivery','session_id','state_revision','keyboard.pending_events','keyboard.owned_keys','keyboard.queued_guest_ms'},
    'keyboard.state': {'session_id','state_revision','keyboard.pending_events','keyboard.owned_keys','keyboard.queued_guest_ms'},
    'memory': {'hex','project_address','data_base64','session_id','state_revision'},
    'status': {'run','version','live','session_id','state','state_revision'},
    'registers': {'cs','ip','project_address','session_id','state_revision','instruction_pointer','flags','cpu_mode',
                  *('general.'+r for r in ('eax','ebx','ecx','edx','esi','edi','esp','ebp')),
                  *('segments.'+r for r in ('cs','ds','es','ss','fs','gs'))},
    'frame-probe': {'session_id','state_revision','format','frame_id','width','height','samples'},
    'run': {'run','outcome','timed_out','guest_elapsed_ms','host_elapsed_ms','fast_forward','hook_hits'},
    'assert': {'matched'},
}


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def _portable(value):
    """Reject host-absolute paths; other text is untrusted and never executed."""
    if isinstance(value,str):
        if value.startswith(('/', '~', '\\\\')) or re.match(r'^[A-Za-z]:[\\/]',value):
            raise ValueError('Portable macro metadata cannot contain host absolute paths')
    elif isinstance(value,list):
        for child in value:_portable(child)
    elif isinstance(value,dict):
        for key,child in value.items():_portable(key);_portable(child)


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}',value):
        raise ValueError('Invalid macro identifier')
    return value


def _parameter(spec,value, *, symbolic=False):
    if not isinstance(spec,dict) or set(spec)-{'type','enum','default'}:raise ValueError('Invalid macro parameter')
    kind=spec.get('type','string' if 'enum' in spec else None)
    if kind not in ('string','integer','boolean','input-lease'):raise ValueError('Unsupported macro parameter type')
    if kind=='input-lease':
        if not isinstance(value,str) or not (re.fullmatch(r'[a-f0-9]{32}',value) or symbolic and re.fullmatch(r'\$[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)+',value)):
            raise ValueError('Input lease must be an owned token or a typed result reference')
    elif (kind=='string' and (not isinstance(value,str) or len(value)>4096)) or (kind=='integer' and (type(value) is not int or not -(1<<63)<=value<(1<<63))) or (kind=='boolean' and type(value) is not bool):
        raise ValueError('Macro argument type mismatch')
    if 'enum' in spec:
        choices=spec['enum']
        if not isinstance(choices,list) or not 1<=len(choices)<=64 or not any(type(value) is type(choice) and value==choice for choice in choices):raise ValueError('Macro argument not in enum')


def _declaration(spec):
    if not isinstance(spec,dict) or set(spec)-{'type','enum','default'}:raise ValueError('Invalid macro parameter')
    kind=spec.get('type','string' if 'enum' in spec else None)
    if kind not in ('string','integer','boolean','input-lease'):raise ValueError('Unsupported parameter type')
    if 'enum' in spec:
        choices=spec['enum']
        if not isinstance(choices,list) or not 1<=len(choices)<=64:raise ValueError('Invalid macro enum')
        for choice in choices:_parameter({'type':kind},choice)
    if 'default' in spec:_parameter(spec,spec['default'])


def validate_macro_set(definition):
    if not isinstance(definition,dict) or set(definition)-{'format','name','macros','provenance'} or definition.get('format')!='fdisbull-macro-set-1':
        raise ValueError('Expected fdisbull-macro-set-1')
    identifier(definition.get('name'))
    if len(encode(definition).encode())>1024*1024:raise ValueError('Macro set exceeds 1 MiB')
    macros=definition.get('macros')
    if not isinstance(macros,dict) or not 1<=len(macros)<=128:raise ValueError('Expected 1..128 macros')
    edges={}
    for name,macro in macros.items():
        identifier(name)
        if not isinstance(macro,dict) or set(macro)-{'parameters','authority','steps','outputs','context','evidence'}:raise ValueError('Invalid macro declaration')
        if macro.get('authority','player-input') not in AUTHORITIES:raise ValueError('Unknown macro authority')
        parameters=macro.get('parameters',{})
        if not isinstance(parameters,dict) or len(parameters)>16:raise ValueError('Invalid macro parameters')
        for key,spec in parameters.items():
            identifier(key)
            _declaration(spec)
        steps=macro.get('steps')
        if not isinstance(steps,list) or not 1<=len(steps)<=1000:raise ValueError('Macro requires bounded steps')
        aliases=set();edges[name]=[]
        for step in steps:
            if not isinstance(step,dict) or step.get('op') not in PRIMITIVES|{'macro'}:raise ValueError('Unsupported macro operation')
            if 'as' in step:
                if not isinstance(step['as'],str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',step['as']) or step['as'] in aliases:raise ValueError('Invalid or duplicate macro binding')
                aliases.add(step['as'])
            if step['op']=='macro':
                if set(step)-{'op','name','args','as'} or step.get('name') not in macros:raise ValueError('Unknown nested macro')
                edges[name].append(step['name'])
        outputs=macro.get('outputs',{})
        if not isinstance(outputs,dict) or len(outputs)>16:raise ValueError('Invalid macro outputs')
        for key in outputs:identifier(key)
    active=set();memo={}
    def visit(name):
        if name in active:raise ValueError('Recursive macro set')
        if name in memo:return memo[name]
        active.add(name); depth=1; count=0
        for step in macros[name]['steps']:
            if step['op']=='macro':
                child_depth,child_count=visit(step['name']);depth=max(depth,child_depth+1);count+=child_count
            else:count+=1
            if depth>8 or count>1000:raise ValueError('Macro nesting or expanded operations exceed limit')
        active.remove(name);memo[name]=(depth,count)
        return memo[name]
    for name in macros:visit(name)
    return deepcopy(definition)


def expand_macro(definition,name,args=None, *, allowed_authorities=('player-input',)):
    definition=validate_macro_set(definition)
    allowed=set(allowed_authorities)
    if not allowed<=AUTHORITIES:raise ValueError('Unknown allowed authority')
    steps=[];lineage=[];counter=0
    def expand(name,args,path):
        nonlocal counter
        if name not in definition['macros']:raise ValueError('Unknown macro')
        macro=definition['macros'][name];authority=macro.get('authority','player-input')
        if authority not in allowed:raise ValueError('Macro authority is not allowed: '+authority)
        parameters=macro.get('parameters',{})
        if not isinstance(args,dict) or set(args)-set(parameters):raise ValueError('Unknown macro argument')
        bound={}
        for key,spec in parameters.items():
            if key not in args and 'default' not in spec:raise ValueError('Missing macro argument: '+key)
            value=args.get(key,spec.get('default'));_parameter(spec,value,symbolic=True);bound[key]=deepcopy(value)
        prefix='m'+str(counter)+'a';counter+=1
        aliases={}
        alias_operations={}
        nested_outputs={}
        def replace(value):
            if isinstance(value,str) and value.startswith('$args.'):
                key=value[6:]
                if key not in bound:raise ValueError('Unknown macro parameter reference')
                return bound[key]
            if isinstance(value,str) and value.startswith('$'):
                if not re.fullmatch(r'\$[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_0-9]+)*',value):raise ValueError('Invalid macro result reference')
                first,*rest=value[1:].split('.')
                if first in nested_outputs:
                    current=nested_outputs[first]
                    for part in rest:
                        if not isinstance(current,dict) or part not in current:raise ValueError('Invalid nested macro output')
                        current=current[part]
                    return current
                if first not in aliases:raise ValueError('Macro reference is not an earlier local binding: '+value)
                known=_RESULT_PATHS.get(alias_operations[first],set())
                if not rest or '.'.join(rest) not in known:
                    raise ValueError('Unknown or unverifiable result field: '+value)
                return '$'+'.'.join([aliases[first],*rest])
            if isinstance(value,list):return [replace(v) for v in value]
            if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
            return value
        for item in macro['steps']:
            if item['op']=='macro':
                output=expand(item['name'],replace(item.get('args',{})),path+[name])
                if 'as' in item:nested_outputs[item['as']]={'outputs':output}
                continue
            step=replace({k:v for k,v in item.items() if k!='as'})
            if step['op']=='run':
                if step.get('stop_on_hook',True) is not True:raise ValueError('Macro run must preserve hook stops')
                step['stop_on_hook']=True
            if 'as' in item:
                aliases[item['as']]=prefix+str(len(aliases))
                alias_operations[item['as']]=item['op']
                step['as']=aliases[item['as']]
            steps.append(step);lineage.append({'macro':name,'path':path,'authority':authority,'parameters':bound})
            if len(steps)>1000:raise ValueError('Macro exceeds 1000 expanded operations')
        return replace(macro.get('outputs',{}))
    outputs=expand(name,{} if args is None else args,[])
    from .debug_script import validate_script
    script={'format':'fdisbull-script-1','steps':steps};validate_script(script)
    for step in steps:
        if step['op']=='keyboard.key-up':
            lease=step['lease']
            if not isinstance(lease,str) or not (re.fullmatch(r'[a-f0-9]{32}',lease) or re.fullmatch(r'\$[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_0-9]+)+',lease)):
                raise ValueError('Invalid input lease reference')
        if step['op']=='run':
            for field,maximum in (('guest_ms',3600000),('timeout_ms',600000)):
                if field in step and not (isinstance(step[field],str) and step[field].startswith('$')):
                    if type(step[field]) is not int or not 1<=step[field]<=maximum:raise ValueError('Invalid run '+field)
            for field in ('fast_forward','stop_on_hook'):
                if field in step and type(step[field]) is not bool:raise ValueError('Invalid run '+field)
    return {'script':script,'outputs':outputs,'lineage':lineage}


class MacroProjectMixin:
    def debug_define_macros(self,definition, *, version=None,author='agent',parent=None):
        definition=validate_macro_set(definition)
        if not isinstance(author,str) or not 1<=len(author)<=256:raise ValueError('Invalid macro author')
        v=self.version(version)
        if parent is not None:self.debug_macro_info(parent,version=v['id'])
        doc={'definition':definition,'binding':{'version':v['id'],'version_sha256':v['sha256'],'source_sha256':self.source_sha256(v['id'])},'author':author,'parent':parent}
        text=encode(doc);sha=hashlib.sha256(text.encode()).hexdigest()
        from .project import now
        with self.transaction(True):
            self.db.execute('INSERT OR IGNORE INTO debug_macro_sets VALUES (?,?,?,?,?,?,?)',(sha,v['id'],parent,now(),author,sha,text))
        return self.debug_macro_info(sha,version=v['id'])

    def debug_macro_info(self,macro_set, *, version=None):
        v=self.version(version);row=self.db.execute('SELECT * FROM debug_macro_sets WHERE id=? AND version=?',(macro_set,v['id'])).fetchone()
        if row is None:raise ValueError('Unknown macro set for selected byte version')
        text=row['document'];doc=json.loads(text)
        if hashlib.sha256(encode(doc).encode()).hexdigest()!=row['sha256'] or row['id']!=row['sha256']:raise ValueError('Macro manifest hash mismatch')
        if not isinstance(doc,dict) or set(doc)!={'definition','binding','author','parent'} or row['author']!=doc['author'] or row['parent']!=doc['parent']:
            raise ValueError('Macro record metadata mismatch')
        if doc['binding']!={'version':v['id'],'version_sha256':v['sha256'],'source_sha256':self.source_sha256(v['id'])}:raise ValueError('Macro source binding mismatch')
        validate_macro_set(doc['definition'])
        return {k:row[k] for k in ('id','version','parent','author','sha256','created')}|doc

    def debug_macro_sets(self, *, version=None):
        v=self.version(version)['id'];return {'version':v,'macro_sets':[self.debug_macro_info(r['id'],version=v) for r in self.db.execute('SELECT id FROM debug_macro_sets WHERE version=? ORDER BY rowid',(v,))]}

    def debug_export_macros(self,macro_set, *, version=None):
        """Return a hash-bound JSON metadata envelope; no host files are read."""
        info=self.debug_macro_info(macro_set,version=version)
        _portable(info['definition'])
        envelope={'format':'fdisbull-macro-export-1',
                  'binding':{'version_sha256':info['binding']['version_sha256'],
                             'source_sha256':info['binding']['source_sha256']},
                  'definition':info['definition']}
        return {**envelope,'sha256':hashlib.sha256(encode(envelope).encode()).hexdigest()}

    def debug_import_macros(self,envelope, *, version=None,author='agent'):
        """Import an envelope only into a project with the exact source/version hashes."""
        if not isinstance(envelope,dict) or set(envelope)!={'format','binding','definition','sha256'} or envelope['format']!='fdisbull-macro-export-1':
            raise ValueError('Invalid macro export envelope')
        encoded=encode({key:value for key,value in envelope.items() if key!='sha256'})
        if len(encoded.encode())>1024*1024 or not isinstance(envelope['sha256'],str) or hashlib.sha256(encoded.encode()).hexdigest()!=envelope['sha256']:
            raise ValueError('Macro export hash mismatch or excessive size')
        v=self.version(version)
        if envelope['binding']!={'version_sha256':v['sha256'],'source_sha256':self.source_sha256(v['id'])}:
            raise ValueError('Macro export source or version mismatch')
        _portable(envelope['definition'])
        return self.debug_define_macros(envelope['definition'],version=v['id'],author=author)


def _output(value,bindings):
    if isinstance(value,str) and value.startswith('$'):
        current=bindings
        for part in value[1:].split('.'):current=current[int(part)] if isinstance(current,list) else current[part]
        return current
    if isinstance(value,dict):return {k:_output(v,bindings) for k,v in value.items()}
    if isinstance(value,list):return [_output(v,bindings) for v in value]
    return value


class MacroSessionMixin:
    def _macro_plan(self,macro_set,name,args=None,allowed_authorities=('player-input',)):
        info=self.project.debug_macro_info(macro_set,version=self.version['id'])
        plan=expand_macro(info['definition'],name,args,allowed_authorities=allowed_authorities)
        unsupported={s['op'] for s in plan['script']['steps']}-set(self.script_operations)
        if unsupported:raise ValueError('Unsupported macro primitives: '+', '.join(sorted(unsupported)))
        if any(s['op'] in ('keyboard.key-down','keyboard.key-up') for s in plan['script']['steps']) and not self.rpc.capabilities.get('input',{}).get('keyboard_held_leases'):
            raise ValueError('Backend does not support held-key leases')
        for step in plan['script']['steps']:
            if step['op']=='keyboard.key-up' and not step['lease'].startswith('$') and step['lease'] not in getattr(self,'_keyboard_leases',{}):
                raise ValueError('Unknown, consumed or unrelated input lease')
        return info,plan

    @rpc_budget
    def macro(self,macro_set,name, *, args=None,allowed_authorities=('player-input',),timeout_ms=10000):
        if type(timeout_ms) is not int or not 1<=timeout_ms<=600000:raise ValueError('Invalid macro timeout_ms')
        info,plan=self._macro_plan(macro_set,name,args,allowed_authorities)
        from .debug_script import execute_script
        before=set(getattr(self,'_keyboard_leases',{}));started=time.monotonic();bindings={}
        def input_state():
            if getattr(self,'closed',False):return {'available':False,'reason':'session_closed'}
            try:return {'available':True,'keyboard':self.keyboard_state()['keyboard'],
                        'host_owned_keys':sorted(getattr(self,'_keyboard_leases',{}).values())}
            except Exception as failure:return {'available':False,'reason':str(failure)}
        input_before=input_state()
        remaining=timeout_ms-int((time.monotonic()-started)*1000)
        if remaining<=0:raise TimeoutError('Macro host-time budget expired before execution')
        report=execute_script(self,plan['script'],timeout_ms=remaining,_bindings_out=bindings)
        outputs={};error=None
        try:
            if report['ok']:outputs=_output(plan['outputs'],bindings)
        except Exception as failure:error=str(failure)
        def tokens(value):
            if isinstance(value,str):return {value}
            if isinstance(value,dict):return set().union(set(),*(tokens(v) for v in value.values()))
            if isinstance(value,list):return set().union(set(),*(tokens(v) for v in value))
            return set()
        active=set(getattr(self,'_keyboard_leases',{}))
        retained=tokens(outputs) & active if report['ok'] and error is None else set()
        acquired={item['result']['lease'] for item in report['steps']
                  if item.get('ok') and item.get('op')=='keyboard.key-down' and 'lease' in item.get('result',{})}
        abandoned=(acquired-before) & active-retained
        cleanup=[]
        if report.get('input_cleanup') is not None:cleanup.append(report['input_cleanup'])
        if abandoned and not getattr(self,'closed',False):
            # Closing avoids resuming through a breakpoint or hook merely to
            # deliver a queued break. Backend session stop resets all input.
            self.close()
            cleanup.append({'closed':True,'reason':'New input lease not returned; session closed without resuming guest'})
            error='Macro did not return an active lease; session closed'
        input_after=input_state() if time.monotonic()-started<timeout_ms/1000 or getattr(self,'closed',False) else {'available':False,'reason':'host_time_budget_expired'}
        result={'format':'fdisbull-macro-result-1','macro_set':info['id'],'macro_sha256':info['sha256'],'name':name,'args':args or {},
                'ok':report['ok'] and error is None,'outputs':outputs,'expanded_steps':plan['script']['steps'],'lineage':plan['lineage'],
                'execution':report,'cleanup':cleanup,'error':error,'run':self.run_id,'input_before':input_before,'input_after':input_after,'host_elapsed_ms':round((time.monotonic()-started)*1000,3),
                'claim':'Expanded input delivery is not target-level action completion.'}
        self._event('macro',result)
        artifact=self._artifact('macro-result.json','macro-result',json.dumps(result,indent=2).encode(),{'ok':result['ok'],'macro_set':info['id']})
        return {**result,'artifact':artifact['artifact']}
