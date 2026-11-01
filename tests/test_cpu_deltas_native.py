"""Selected CPU/RAM delta contracts on an explicitly selected native backend."""
import base64

import pytest

from fdisbull.cli import METHODS
from fdisbull.debug_script import validate_script
from fdisbull.debugger import DebugWorkspace
from test_rewind_native import native, observed


def test_delta_routes_and_script_limits_are_explicit():
    for method in ('debug-delta-start','debug-delta-record','debug-delta-status',
                   'debug-delta-rewind','debug-delta-recover'):
        assert method in METHODS
    validate_script({'format':'fdisbull-script-1','steps':[
        {'op':'delta-start','ranges':[{'address':'1000:0000','length':512}]},
        {'op':'delta-record','count':3}, {'op':'delta-rewind','count':2},
        {'op':'delta-status'}, {'op':'delta-recover'}]})
    with pytest.raises(ValueError):
        validate_script({'format':'fdisbull-script-1','steps':[
            {'op':'delta-record','count':True}]})


def test_real_delta_projection_freezes_until_native_recovery(native):
    project,debug,_=native
    workspace=DebugWorkspace();workspace.sessions[debug.run_id]=debug
    def invoke(method,**params):
        return workspace.invoke(method,project.path,{'run':debug.run_id,**params})
    initial=observed(debug)
    started=invoke('debug-delta-start',ranges=[{'address':'1000:0000','length':512}],max_steps=12)
    assert started['anchor']['artifact']
    states=[]
    for _ in range(6):
        states.append(observed(debug))
        invoke('debug-delta-record')
    artifacts=project.debug_artifacts()['artifacts']
    assert len([a for a in artifacts if a['kind']=='state'])==1
    result=invoke('debug-delta-rewind',count=2)
    assert result['full_machine_restored'] is False
    assert result['partial_restored'] is True
    assert observed(debug)==states[4]
    before=observed(debug)
    for operation in (
        lambda: debug.run(guest_ms=1), lambda: debug.trace(count=2),
        lambda: debug.save_state(), lambda: debug.screenshot(),
        lambda: debug.cpu_delta_start([{'address':'1000:0000','length':512}]),
        lambda: debug.cpu_delta_record()):
        with pytest.raises(ValueError): operation()
        assert observed(debug)==before
    invoke('debug-delta-rewind')
    assert observed(debug)==states[3]
    invoke('debug-delta-recover')
    assert observed(debug)==initial
    assert not invoke('debug-delta-status')['frozen']
    debug.trace(count=2,fast_forward=True)
    assert int(debug.registers()['instruction_pointer'],16)==1


def test_real_whole_selected_range_guard_detects_unchanged_byte_tamper(native):
    _,debug,_=native
    debug.cpu_delta_start([{'address':'1000:0000','length':512}])
    debug.cpu_delta_record(count=2)
    # Deliberately bypass the public invalidation hook to test full-range guards.
    value=debug.memory('1000:0104',length=1)
    debug.rpc.call('memory.write',{'session_id':debug.session_id,'address':value['address'],
        'expected_sha256':value['sha256'],'data_base64':base64.b64encode(b'\xa5').decode()})
    before=observed(debug)
    with pytest.raises(ValueError): debug.cpu_delta_rewind()
    assert observed(debug)==before
    debug.cpu_delta_recover()
    assert not debug.cpu_delta_status()['frozen']


def test_real_successful_direct_native_load_clears_partial_guard(native):
    _,debug,_=native
    initial=observed(debug)
    started=debug.cpu_delta_start([{'address':'1000:0000','length':512}])
    debug.cpu_delta_record(count=3)
    debug.cpu_delta_rewind()
    assert debug.cpu_delta_status()['frozen']
    debug.load_state(started['anchor']['artifact'])
    assert observed(debug)==initial
    assert not debug.cpu_delta_status()['frozen']
    debug.trace(count=2,fast_forward=True)


def test_real_delta_script_and_no_automatic_resume(native):
    _,debug,_=native
    initial=observed(debug)
    result=debug.script({'format':'fdisbull-script-1','steps':[
        {'op':'delta-start','ranges':[{'address':'1000:0000','length':512}]},
        {'op':'delta-record','count':4}, {'op':'delta-rewind','count':2},
        {'op':'delta-recover'}]},timeout_ms=20000)
    assert result['ok'],result
    assert observed(debug)==initial
