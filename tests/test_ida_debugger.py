"""Public PE adapter preflight and a real, optional IDA/Wine/QEMU gate."""
import json
import os
from pathlib import Path
import time

import pytest

from fdisbull.project import Project
from fixtures_formats import pe64


def test_batch_trace_decodes_actual_instruction_lengths_and_keeps_layer_identity():
    from fdisbull.ida_debugger import IDAPEDebugSession
    debug=IDAPEDebugSession.__new__(IDAPEDebugSession)
    debug._layer_setup=lambda:None
    debug._execution={};debug._pending_exec=None;debug.watchpoints={}
    debug._layers=['layer-1'];debug._layer_generation=3
    raw=['9090ebfc','90ebfc','ebfc']
    events=[dict(address=hex(0x1000+i),bytes=data,registers={'rip':hex(0x1000+i)}) for i,data in enumerate(raw)]
    calls=[]
    def call(method,params,**options):
        calls.append(method)
        return dict(events=events,complete=True,session={'state':'stopped'})
    debug.call=call
    result=debug._trace_native(3,time.monotonic()+1)
    assert calls==['trace-batch']
    assert [event['bytes'] for event in result['events']]==['90','90','ebfc']
    assert all(event['ram_bytes']==event['execution_bytes']==event['bytes'] and
               event['active_layers']==['layer-1'] and event['layer_generation']==3 for event in result['events'])


def test_already_expired_host_budget_never_starts_a_guest_step():
    from fdisbull.ida_debugger import IDAPEDebugSession
    debug=IDAPEDebugSession.__new__(IDAPEDebugSession)
    debug._layer_setup=lambda:None
    debug._execution={};debug._pending_exec=None;debug.watchpoints={}
    debug.call=lambda method:dict(state='stopped',stop_reason={'kind':'step'}) if method=='status' else pytest.fail(method)
    result=debug._trace_native(3,time.monotonic()-1)
    assert result['events']==[] and not result['complete'] and result['session']['stop_reason']['kind']=='timeout'


def test_ida_launch_requires_an_explicit_server_and_matching_runtime(tmp_path):
    source=tmp_path/'test.exe';source.write_bytes(pe64())
    with Project.create(tmp_path/'test.fdb',source) as project:
        with pytest.raises(ValueError,match='remote_server'):
            project.debugger('missing',tmp_path,backend='ida-wine-qemu')
        with pytest.raises(ValueError,match='requires backend'):
            project.debugger('missing',tmp_path,remote_server='missing')
        server=tmp_path/'server.exe';server.write_text('not a PE')
        with pytest.raises(ValueError,match='Windows IDA'):
            project.debugger('missing',tmp_path,backend='ida-wine-qemu',remote_server=server,kernel='k',initramfs='i')
        with pytest.raises(ValueError,match='state reconnection'):
            project.debugger('missing',tmp_path,backend='ida-wine-qemu',remote_server=server,kernel='k',initramfs='i',state='old')
        assert project.debug_runs()['runs']==[]


def test_real_ida_pe64_patchless_breakpoint_memory_registers_ram_layer_trace_click_and_export(tmp_path):
    names=('FDISBULL_PE_QEMU','FDISBULL_PE_KERNEL','FDISBULL_IDA_INITRAMFS','FDISBULL_PE_FIXTURE','FDISBULL_IDA_SERVER')
    missing=[name for name in names if not os.environ.get(name)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_IDA')=='1':pytest.fail('Missing IDA acceptance inputs: '+', '.join(missing))
        pytest.skip('Supply FDISBULL_IDA_* and FDISBULL_PE_* for real remote-server acceptance')
    qemu,kernel,runtime,fixture,server=[os.environ[name] for name in names]
    import lief
    from PIL import Image
    source=Path(fixture);binary=lief.PE.parse(str(source));base=binary.optional_header.imagebase
    exports={e.name:base+e.address for e in binary.get_export().entries}
    checkpoint,counter=exports['checkpoint'],exports['counter']
    path=tmp_path/'remote.fdb';evidence=Path(os.environ.get('FDISBULL_IDA_EVIDENCE',tmp_path/'evidence'))
    evidence.mkdir(parents=True,exist_ok=True)
    with Project.create(path,source) as project:
        project.analyze(start=checkpoint,max_instructions=64)
        original=project.disassembly(address=checkpoint,lines=4)['instructions']
        with project.debugger(qemu,source.parent,backend='ida-wine-qemu',remote_server=server,
                              kernel=kernel,initramfs=runtime) as debug:
            bp=debug.breakpoint(checkpoint)
            assert bp['mechanism']=='page' and bp['guest_code_modified'] is False
            hit=debug.run(timeout_ms=60000)
            assert hit['outcome']=='breakpoint',hit
            assert debug.registers()['project_address']==hex(checkpoint)
            assert debug.memory(counter,length=4)['hex']=='07000000'
            edit=debug.write_memory(counter,'29000000',expected_hex='07000000')
            assert edit['after_hex']=='29000000'
            rax=debug.registers()['general']['rax']
            debug.write_registers({'rax':{'expected':rax,'value':'0x123456789abcdef0'}})
            assert debug.registers()['general']['rax']=='0x123456789abcdef0'
            debug.write_registers({'rax':{'expected':'0x123456789abcdef0','value':rax}})
            before=debug.screenshot('ida-before.png',grid=True,grid_step=8)
            trace=debug.trace('ida-trace.json',count=4,timeout_ms=30000)
            assert trace['metadata']['complete']
            clicked=debug.click_frame(80,80,name='ida-click-grid8.png',grid_step=8)
            assert clicked['click']['queued']
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert debug.memory(counter,length=4)['hex']=='2a000000'
            debug.delete_breakpoint(bp['breakpoint_id'])
            layer=debug.layer_patch('paused data edit',counter,expected_hex='2a000000',data_hex='2b000000',kind='ram')
            assert debug.memory(counter,length=4)['hex']=='2b000000'
            debug.layers([])
            assert debug.memory(counter,length=4)['hex']=='2a000000'
            with pytest.raises(ValueError,match='RAM layers only'):
                debug.layer_patch('unsupported',checkpoint,expected_hex='55',data_hex='90',kind='execute')
            paused=debug.run(timeout_ms=1000)
            assert paused['outcome']=='timeout' and paused['session']['state']=='stopped'
            after=debug.screenshot('ida-after.png')
            run=debug.run_id
        assert debug.rpc.process.poll() is not None
        assert project.disassembly(address=checkpoint,version=1,lines=4)['instructions']==original
        child=project.patch(checkpoint,'90')['version']
        assert project.debug_artifacts(version=child)['artifacts']==[]
    with Project(path) as project:
        for artifact in project.debug_artifacts(version=1,run=run)['artifacts']:
            project.debug_export(artifact['id'],evidence/artifact['name'])
        assert json.loads((evidence/'ida-trace.json').read_text())['complete']
        with Image.open(evidence/'ida-after.png') as image:assert image.size==(320,200)
