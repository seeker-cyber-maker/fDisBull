"""A bounded, declarative JSON language for repeatable debugger routes."""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import time

from .debugger import bounded

OPERATIONS = {
    'run':'run', 'click':'click', 'screenshot':'screenshot', 'trace':'trace',
    'breakpoint':'breakpoint', 'delete-breakpoint':'delete_breakpoint',
    'save-state':'save_state', 'load-state':'load_state',
    'registers':'registers', 'memory':'memory', 'status':'status',
}


def validate_script(script):
    from .debugger import DebugSession
    if not isinstance(script,dict) or set(script) != {'format','steps'} or script['format'] != 'fdisbull-script-1':
        raise ValueError('Script requires format=fdisbull-script-1 and steps')
    if len(json.dumps(script,allow_nan=False).encode()) > 1024*1024:
        raise ValueError('Script exceeds 1 MiB')
    expanded = []

    def visit(steps, depth=0):
        if not isinstance(steps,list) or not steps or depth>8:
            raise ValueError('Script steps must be lists with nesting at most eight')
        for step in steps:
            if not isinstance(step,dict) or not isinstance(step.get('op'),str):
                raise ValueError('Every step requires an op')
            op = step['op']
            if 'expect' in step and (op!='run' or step['expect'] not in ('breakpoint','guest_time','timeout','exited','pause')):
                raise ValueError('expect is a run outcome: breakpoint, guest_time, timeout, exited, or pause')
            if op=='repeat':
                if set(step) != {'op','count','steps'}:
                    raise ValueError('repeat requires count and steps')
                bounded(step['count'],'repeat count',1,1000)
                for _ in range(step['count']):
                    visit(step['steps'],depth+1)
            else:
                alias = step.get('as')
                if alias is not None and (not isinstance(alias,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',alias)):
                    raise ValueError('Step alias must be a simple identifier')
                params = {k:v for k,v in step.items() if k not in ('op','as','expect')}
                if op=='assert':
                    if set(params) != {'value','equals'}:
                        raise ValueError('assert requires value and equals')
                elif op in OPERATIONS:
                    signature = inspect.signature(getattr(DebugSession,OPERATIONS[op]))
                    signature.bind(None,**params)
                else:
                    raise ValueError('Unknown script operation: '+op)
                expanded.append(step)
                if len(expanded)>1000:
                    raise ValueError('Script exceeds 1000 expanded steps')
    visit(script['steps'])
    if not expanded:
        raise ValueError('Script must contain at least one operation')
    return expanded


def execute_script(session, script, *, timeout_ms=60000):
    bounded(timeout_ms,'timeout_ms',1,600000)
    steps = validate_script(script) # Reject malformed later steps before any guest mutation.
    encoded = json.dumps(script,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    source = session._artifact('route.fdisbull.json','script',encoded,{'format':script['format']})
    started = time.monotonic(); deadline = started+timeout_ms/1000
    results = {}; records = []; failure = None

    def resolve(value):
        if isinstance(value,str) and value.startswith('$'):
            parts = value[1:].split('.')
            current = results[parts[0]]
            for part in parts[1:]:
                current = current[int(part)] if isinstance(current,list) else current[part]
            return current
        if isinstance(value,list):
            return [resolve(item) for item in value]
        if isinstance(value,dict):
            return {k:resolve(v) for k,v in value.items()}
        return value

    for index, step in enumerate(steps):
        record = {'index':index,'op':step['op']}
        try:
            remaining = int((deadline-time.monotonic())*1000)
            if remaining <= 0:
                raise TimeoutError('Script host-time budget expired')
            params = resolve({k:v for k,v in step.items() if k not in ('op','as','expect')})
            if step['op'] in ('run','trace'):
                params['timeout_ms'] = min(params.get('timeout_ms',remaining),remaining)
            if step['op']=='assert':
                if params['value'] != params['equals']:
                    raise ValueError(f"Assertion failed: {params['value']!r} != {params['equals']!r}")
                result = {'matched':True}
            else:
                result = getattr(session,OPERATIONS[step['op']])(**params)
            record['result'] = result
            if step['op']=='run':
                expected = step.get('expect','guest_time' if 'guest_ms' in params else 'breakpoint')
                if result['outcome'] != expected:
                    raise ValueError(f"Run expected {expected}, observed {result['outcome']}")
            if step['op']=='trace' and not result['metadata']['complete']:
                raise ValueError('Trace stopped before the requested event count')
            if 'as' in step:
                results[step['as']] = result
            record.update(ok=True,result=result)
        except Exception as error:
            failure = {'index':index,'op':step['op'],'type':type(error).__name__,'message':str(error)}
            record.update(ok=False,error=failure)
        records.append(record)
        if failure:
            break
    report = {'format':'fdisbull-script-result-1','script_artifact':source['artifact'],
              'script_sha256':hashlib.sha256(encoded).hexdigest(),'run':session.run_id,
              'ok':failure is None,'error':failure,'completed_steps':sum(r['ok'] for r in records),
              'requested_steps':len(steps),'host_elapsed_ms':round((time.monotonic()-started)*1000,3),
              'steps':records}
    evidence = session._artifact('route-result.json','script-result',json.dumps(report,indent=2).encode(),
                                 {'ok':report['ok'],'completed_steps':report['completed_steps']})
    return {**report,'artifact':evidence['artifact']}
