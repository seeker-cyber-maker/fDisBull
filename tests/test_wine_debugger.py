"""PE adapter contracts plus an opt-in, real Wine/QEMU GUI acceptance test."""
import hashlib
import gzip
import json
import os
from pathlib import Path
import struct

import pytest

from fdisbull.project import Project
from fdisbull.wine_debugger import PEDebugSession
from fdisbull.wine_runtime import prepare
from fixtures_formats import pe64


def test_pe_launch_rejects_invalid_inputs_before_starting_vm(tmp_path):
    source=tmp_path/'test.exe';source.write_bytes(pe64())
    with Project.create(tmp_path/'test.fdb',source) as project:
        with pytest.raises(ValueError,match='requires kernel'):
            project.debugger('/missing-qemu',tmp_path)
        with pytest.raises(ValueError,match='source hash'):
            source.write_bytes(pe64()+b'changed')
            project.debugger('/missing-qemu',tmp_path,kernel='x',initramfs='y')
        source.write_bytes(pe64())
        with pytest.raises(ValueError,match='databases or saved states'):
            (tmp_path/'private.sav').write_bytes(b'private')
            project.debugger('/missing-qemu',tmp_path,kernel='x',initramfs='y',files=['test.exe','private.sav'])
        project.analyze()
        version=project.patch(project.meta['entry'],'90')['version']
        with pytest.raises(ValueError,match='original unpatched'):
            project.debugger('/missing-qemu',tmp_path,kernel='x',initramfs='y',version=version)


def test_pe_relocation_verification_changes_expected_view_only(tmp_path):
    data=bytearray(pe64())
    struct.pack_into('<II',data,0x98+112+5*8,0x11a0,12)
    struct.pack_into('<Q',data,0x380,0x140000123)
    struct.pack_into('<IIHH',data,0x3a0,0x1000,12,0xa180,0)
    source=tmp_path/'reloc.exe';source.write_bytes(data)
    with Project.create(tmp_path/'reloc.fdb',source) as project:
        session=PEDebugSession.__new__(PEDebugSession)
        session.project=project;session.version=project.version(1)
        session.static_base=0x140000000;session.delta=0x100000
        session.regions=project.regions(1)
        session._expected={r.start:bytearray(r.data) for r in session.regions}
        session._relocate_expected()
        assert struct.unpack_from('<Q',session._expected[0x140001000],0x180)[0]==0x140100123
        assert struct.unpack_from('<Q',next(r.data for r in project.regions(1) if r.start==0x140001000),0x180)[0]==0x140000123
        assert session.project_address('0x140101000')=='0x140001000'
        assert session.project_address('0x7fff00000000') is None
        with pytest.raises(ValueError,match='outside'):
            session._address(0x140000500)


def test_runtime_preparation_preserves_base_and_refuses_overwrite(tmp_path):
    base=tmp_path/'base'
    def member(name,data,index):
        name=name.encode()+b'\0'
        fields=(index,0o100644,0,0,1,0,len(data),0,0,0,0,len(name),0)
        header=b'070701'+b''.join(f'{v:08x}'.encode() for v in fields)
        return header+name+b'\0'*(-(110+len(name))%4)+data+b'\0'*(-len(data)%4)
    original=gzip.compress(member('usr/bin/keep',b'keep me',1)+member('opt/probes/old',b'old probe',2)+member('TRAILER!!!',b'',3))
    base.write_bytes(original)
    output=tmp_path/'runtime'
    result=prepare(base,output)
    assert base.read_bytes()==original
    expanded=gzip.decompress(output.read_bytes())
    assert b'usr/bin/keep' in expanded and b'opt/probes/old' not in expanded
    assert result['omitted_bytes']==len(b'old probe')
    assert result['resources']['opt/fdisbull/agent.c']
    with pytest.raises(FileExistsError):prepare(base,output)
    assert hashlib.sha256(output.read_bytes()).hexdigest()==result['runtime_sha256']


def test_pe_script_rejects_dos_operations_before_any_guest_edit():
    session=PEDebugSession.__new__(PEDebugSession)
    def unexpected(*args,**kwargs):
        pytest.fail('Unsupported script reached artifact storage or guest mutation')
    session._artifact=unexpected
    script={'format':'fdisbull-script-1','steps':[
        {'op':'write-memory','address':'0x140003000','data_hex':'01','expected_hex':'00'},
        {'op':'save-state','name':'unsupported.sav'}]}
    with pytest.raises(ValueError,match='Unsupported operations'):
        session.script(script)


def test_real_pe64_window_project_breakpoint_edit_trace_click_and_restart(tmp_path):
    names=('FDISBULL_PE_QEMU','FDISBULL_PE_KERNEL','FDISBULL_PE_INITRAMFS','FDISBULL_PE_FIXTURE')
    missing=[name for name in names if not os.environ.get(name)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_PE')=='1':pytest.fail('Missing real PE acceptance inputs: '+', '.join(missing))
        pytest.skip('Set FDISBULL_PE_* and FDISBULL_REQUIRE_PE=1 for real Wine/QEMU acceptance')
    qemu,kernel,runtime,fixture=[os.environ[name] for name in names]
    import lief
    from PIL import Image
    source=Path(fixture)
    binary=lief.PE.parse(str(source));base=binary.optional_header.imagebase
    exports={entry.name:base+entry.address for entry in binary.get_export().entries}
    checkpoint=exports['checkpoint'];counter=exports['counter']
    path=tmp_path/'oracle.fdb';evidence=Path(os.environ.get('FDISBULL_PE_EVIDENCE',tmp_path/'exports'))
    evidence.mkdir(parents=True,exist_ok=True)
    with Project.create(path,source) as project:
        project.analyze(start=checkpoint,max_instructions=64)
        static=project.disassembly(address=checkpoint,version=1,lines=4)['instructions']
        child=project.patch(checkpoint,'90')['version']
        with pytest.raises(ValueError,match='original unpatched'):
            project.debugger(qemu,source.parent,kernel=kernel,initramfs=runtime,version=child)
        with project.debugger(qemu,source.parent,kernel=kernel,initramfs=runtime,version=1) as debug:
            assert debug.registers()['project_address']==hex(project.meta['entry'])
            bp=debug.breakpoint(checkpoint)
            assert bp['bytes_verified'] and bp['project_address']==hex(checkpoint)
            arrived=debug.run(timeout_ms=60000)
            assert arrived['outcome']=='breakpoint',arrived
            assert debug.registers()['project_address']==hex(checkpoint)
            assert debug.memory(counter,length=4)['hex']=='07000000'
            frame=debug.screenshot('before.png',grid=True,grid_step=8)
            assert (frame['metadata']['width'],frame['metadata']['height'])==(320,200)
            with pytest.raises(ValueError,match='expected bytes'):
                debug.write_memory(counter,'29000000',expected_hex='08000000')
            edit=debug.write_memory(counter,'29000000',expected_hex='07000000')
            assert edit['after_hex']=='29000000'
            route=debug.script({'format':'fdisbull-script-1','steps':[
                {'op':'memory','address':hex(counter),'length':4,'as':'value'},
                {'op':'assert','value':'$value.hex','equals':'29000000'}]})
            assert route['ok'],route
            # Observe real instructions, including the displaced breakpoint instruction.
            trace=debug.trace('checkpoint.json',count=4,timeout_ms=20000)
            assert trace['metadata']['complete'],trace
            clicked=debug.click_frame(80,80,name='click.png',grid_step=8)
            assert clicked['click']['queued']
            arrived=debug.run(timeout_ms=30000)
            assert arrived['outcome']=='breakpoint',arrived
            assert debug.registers()['project_address']==hex(checkpoint)
            assert debug.memory(counter,length=4)['hex']=='2a000000' # 41 edited + one actual click
            after=debug.screenshot('after.png')
            assert after['sha256']!=frame['metadata']['coordinate_grid']['source_sha256']
            # A second click proves the breakpoint was rearmed after the first hit.
            debug.click(80,80,mode_id=after['metadata']['mode_id'])
            assert debug.run(timeout_ms=30000)['outcome']=='breakpoint'
            assert debug.memory(counter,length=4)['hex']=='2b000000'
            debug.delete_breakpoint(bp['breakpoint_id'])
            paused=debug.run(timeout_ms=100)
            assert paused['outcome']=='timeout' and paused['session']['state']=='stopped',paused
            run=debug.run_id
        assert debug.rpc.process.poll() is not None
        assert project.disassembly(address=checkpoint,version=1,lines=4)['instructions']==static
    # No emulator needed for image or trace export after project restart.
    with Project(path) as project:
        artifacts=project.debug_artifacts(version=1,run=run)['artifacts']
        for artifact in artifacts:
            project.debug_export(artifact['id'],evidence/artifact['name'])
        with Image.open(evidence/'after.png') as image:
            assert image.size==(320,200) and image.getpixel((40,56))==(32,192,96)
        recorded=json.loads((evidence/'checkpoint.json').read_text())
        assert recorded['complete'] and len(recorded['events'])==4
        assert recorded['events'][0]['project_address']==hex(checkpoint)
        assert recorded['events'][0]['instruction']['address']==int(recorded['events'][0]['address'],16)
        # A new VM through the foreground server restores original data and
        # exercises the public JSON routing used by agents.
        from fdisbull.debugger import DebugWorkspace
        from fdisbull.cli import respond
        workspace=DebugWorkspace()
        def request(method,**params):
            reply=respond({'id':'pe-acceptance','method':method,
                'params':{'project':str(path),**params}},debugger=workspace)
            assert reply['ok'],reply
            return reply['result']
        try:
            launched=request('debug-launch',executable=qemu,game_dir=str(source.parent),
                backend='wine-qemu',kernel=kernel,initramfs=runtime,version=1)
            second_run=launched['run']
            request('debug-breakpoint',run=second_run,address=hex(checkpoint))
            assert request('debug-run',run=second_run,timeout_ms=60000)['outcome']=='breakpoint'
            assert request('debug-memory',run=second_run,address=hex(counter),length=4)['hex']=='07000000'
            edited=request('debug-write-memory',run=second_run,address=hex(counter),
                           data_hex='29000000',expected_hex='07000000')
            assert edited['after_hex']=='29000000'
            assert request('debug-stop',run=second_run)['process_reaped']
        finally:
            workspace.close()
    (evidence/'acceptance.json').write_text(json.dumps({'result':'pass','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'checkpoint':hex(checkpoint),'counter':hex(counter),'artifacts':[{'name':a['name'],'sha256':a['sha256']} for a in artifacts]},indent=2)+'\n')
