"""Regressions at the real guest broker/native command boundary.

Load only broker functions: importing the guest script would open its serial
device. Native program acceptance is tested separately.
"""
import ast
import io
import json
import os
from pathlib import Path
import select
import subprocess
from types import SimpleNamespace
import time

import pytest

from fdisbull.windows_ui import _events


def broker_functions():
    source=Path(__file__).parents[1]/'src/fdisbull/wine_guest/broker.py'
    parsed=ast.parse(source.read_text())
    functions=ast.Module(body=[node for node in parsed.body if isinstance(node,ast.FunctionDef)],type_ignores=[])
    scope={'os':os,'json':json,'select':select,'time':time}
    exec(compile(functions,str(source),'exec'),scope)
    return scope


@pytest.mark.parametrize('boot_times_out',[False,True])
def test_session_start_bounds_cold_wine_setup_and_never_launches_after_timeout(tmp_path,boot_times_out):
    scope=broker_functions();calls=[]
    scope.update(process=None,Path=lambda *parts:tmp_path.joinpath(*parts[1:]),
                 open=lambda *args,**kwargs:open(tmp_path/'wine.log',*args[1:],**kwargs),
                 stage_files=lambda params:(tmp_path,'oracle.exe'))
    def run(command,**options):
        calls.append(('wineboot',options['timeout']))
        assert command==['wineboot','-u'] and options['check'] is True
        assert options['timeout']==300
        if boot_times_out:raise subprocess.TimeoutExpired(command,options['timeout'])
    def launch(command,**options):
        calls.append(('launch',command))
        return SimpleNamespace()
    scope['subprocess']=SimpleNamespace(run=run,Popen=launch,DEVNULL=subprocess.DEVNULL,PIPE=subprocess.PIPE)
    scope['response']=lambda seconds:calls.append(('response',seconds)) or {'started':True}
    params={'target':'oracle.exe','entry_rva':0x1000}
    if boot_times_out:
        with pytest.raises(subprocess.TimeoutExpired):scope['invoke']('session.start',params)
        assert calls==[('wineboot',300)] and scope['process'] is None
    else:
        assert scope['invoke']('session.start',params)=={'started':True}
        assert [item[0] for item in calls]==['wineboot','launch','response']
        assert calls[-1]==('response',90)


@pytest.mark.parametrize('params',[
    {'events':_events(text='Ab!'),'duration_ms':240},
    {'events':_events(key='a',modifiers=('ctrl','alt')),'duration_ms':80},
    {'events':_events(text='a'*64,hold_ms=100,gap_ms=100),'duration_ms':12800},
])
def test_keyboard_offsets_reach_native_queue_unchanged(params):
    scope=broker_functions();stream=io.BytesIO();scope['process']=SimpleNamespace(stdin=stream)
    observed=[]
    scope['response']=lambda *args,**kwargs:observed.append(kwargs) or {'queued':len(params['events'])}
    result=scope['invoke']('keyboard',params)
    fields=stream.getvalue().decode().split()
    assert fields[:3]==['keyboard',str(len(params['events'])),str(params['duration_ms'])]
    assert [int(fields[i]) for i in range(5,len(fields),3)]==[e['delay_ms'] for e in params['events']]
    assert result['queued']==len(params['events']) and observed==[{'unavailable_capture':False}]


def test_unordered_keyboard_batch_refuses_before_native_write():
    scope=broker_functions();stream=io.BytesIO();scope['process']=SimpleNamespace(stdin=stream)
    events=_events(text='ab');events[-1]['delay_ms']=0
    with pytest.raises(ValueError,match='nondecreasing'):
        scope['invoke']('keyboard',{'events':events,'duration_ms':160})
    assert stream.getvalue()==b''


@pytest.mark.parametrize('params,command',[
    ({},b'context-diagnostics\n'),
    ({'record_setters':True},b'context-diagnostics record 1\n'),
    ({'record_setters':False},b'context-diagnostics record 0\n'),
])
def test_context_diagnostics_is_a_single_readonly_native_request(params,command):
    scope=broker_functions();stream=io.BytesIO();scope['process']=SimpleNamespace(stdin=stream)
    reply={'pending_event':{'thread':420},'setters':[]}
    scope['response']=lambda *args,**kwargs:reply
    assert scope['invoke']('context-diagnostics',params) is reply
    assert stream.getvalue()==command


@pytest.mark.parametrize('params',[{'record_setters':1},{'record_setters':'true'},
    {'record_setters':None},{'resume':True}])
def test_context_diagnostics_invalid_options_refuse_before_native_request(params):
    scope=broker_functions();stream=io.BytesIO();scope['process']=SimpleNamespace(stdin=stream)
    with pytest.raises(ValueError,match='optional Boolean'):
        scope['invoke']('context-diagnostics',params)
    assert stream.getvalue()==b''


@pytest.mark.parametrize('error',['no-visible-client-window','capture-failed','write-failed'])
@pytest.mark.parametrize('screenshot',[False,True])
def test_only_known_readonly_capture_unavailability_is_recoverable(error,screenshot):
    scope=broker_functions();read,write=os.pipe()
    try:
        os.write(write,(json.dumps({'error':error})+'\n').encode())
        scope['process']=SimpleNamespace(stdout=os.fdopen(read,'rb',closefd=False))
        if screenshot and error!='write-failed':
            assert scope['response'](unavailable_capture=True)=={'available':False,'reason':error}
        else:
            with pytest.raises(RuntimeError,match=error):scope['response'](unavailable_capture=screenshot)
    finally:
        os.close(read);os.close(write)
