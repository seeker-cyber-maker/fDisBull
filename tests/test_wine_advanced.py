"""PE64 native watches, layers and whole-VM checkpoints use authored inputs only."""
import base64
import json
import os
import hashlib
import time
from pathlib import Path

import pytest

from fdisbull.project import Project
from fdisbull.wine_watch import access_facts


def test_access_facts_distinguish_load_store_and_read_modify_write():
    regs={'rip':'0x140001000','general':{'rax':'0x140003000'}}
    load=access_facts(bytes.fromhex('8b00'),regs,0x140003000,0)
    store=access_facts(bytes.fromhex('8900'),regs,0x140003000,1)
    both=access_facts(bytes.fromhex('830001'),regs,0x140003000,1)
    assert load['ranges']==[dict(address=0x140003000,length=4,read=True,write=False)]
    assert store['ranges']==[dict(address=0x140003000,length=4,read=False,write=True)]
    assert both['ranges']==[dict(address=0x140003000,length=4,read=True,write=True)]


def test_guard_watch_rejects_ambiguous_and_shared_fetch_page_access():
    from fdisbull.wine_watch import check_fetch_watch_alias
    regs={'rip':'0x140001000','general':{'rax':'0x140001080','rsi':'0x140001080','rdi':'0x140001100','rcx':'0x4'}}
    with pytest.raises(ValueError,match='non-repeated scalar'):
        access_facts(bytes.fromhex('f3a4'),regs,0x140001080,0)
    with pytest.raises(ValueError,match='shares the fetched guard page'):
        check_fetch_watch_alias(bytes.fromhex('8b00'),regs,0x140001000,[(0x140001080,0x140001084)])
    check_fetch_watch_alias(bytes.fromhex('8b00'),regs,0x140001000,[(0x140003000,0x140003004)])


def native_inputs():
    names=('FDISBULL_PE_QEMU','FDISBULL_PE_KERNEL','FDISBULL_PE_INITRAMFS','FDISBULL_PE_FIXTURE')
    missing=[n for n in names if not os.environ.get(n)]
    if missing:
        if os.environ.get('FDISBULL_REQUIRE_PE')=='1':pytest.fail('Missing native PE inputs: '+', '.join(missing))
        pytest.skip('Set FDISBULL_PE_* for real Wine/QEMU acceptance')
    return [os.environ[n] for n in names]


def test_real_pe_guard_write_and_read_watches(tmp_path):
    import lief
    qemu,kernel,runtime,fixture=native_inputs()
    source=Path(fixture);binary=lief.PE.parse(str(source));base=binary.optional_header.imagebase
    exports={e.name:base+e.address for e in binary.get_export().entries}
    with Project.create(tmp_path/'watches.fdb',source) as project:
        project.analyze(start=exports['checkpoint'],max_instructions=32)
        with project.debugger(qemu,source.parent,kernel=kernel,initramfs=runtime,version=1) as debug:
            bp=debug.breakpoint(exports['checkpoint'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            write=debug.breakpoint(exports['counter']+1,access='w',length=1)
            frame=debug.screenshot()
            debug.click(80,80,mode_id=frame['metadata']['mode_id'])
            stopped=debug.run(timeout_ms=60000)
            assert stopped['outcome']=='watchpoint',stopped
            assert write['breakpoint_id'] in stopped['session']['stop_reason']['breakpoint_ids']
            assert stopped['session']['stop_reason']['before_access']
            assert debug.memory(exports['counter'],length=4)['hex']=='07000000'
            debug.delete_breakpoint(write['breakpoint_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert debug.memory(exports['counter'],length=4)['hex']=='08000000'
            read=debug.breakpoint(exports['counter'],access='r',length=4)
            debug.click(80,80,mode_id=frame['metadata']['mode_id'])
            stopped=debug.run(timeout_ms=60000)
            assert stopped['outcome']=='watchpoint',stopped
            assert read['breakpoint_id'] in stopped['session']['stop_reason']['breakpoint_ids']
            assert any(r['read'] for r in stopped['session']['stop_reason']['access_facts']['ranges'])
            debug.delete_breakpoint(read['breakpoint_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert debug.memory(exports['counter'],length=4)['hex']=='09000000'
            # A read-only watch must not report a pure store as a read.
            read=debug.breakpoint(exports['counter'],access='r',length=4)
            debug.click(80,80,button='right',mode_id=frame['metadata']['mode_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert debug.memory(exports['counter'],length=4)['hex']=='11000000'
            debug.click(80,80,mode_id=frame['metadata']['mode_id'])
            stopped=debug.run(timeout_ms=60000)
            assert stopped['outcome']=='watchpoint'
            assert any(r['read'] and r['write'] for r in stopped['session']['stop_reason']['access_facts']['ranges'])
            debug.delete_breakpoint(read['breakpoint_id'])


def test_pe_register_edit_widths_and_reserved_control_flags():
    from fdisbull.wine_state import validate_edits
    validate_edits([],{'rax':{'expected':'0x0','value':'0x123456789abcdef0'}})
    with pytest.raises(ValueError,match='control flags'):
        validate_edits([],{'rflags':{'expected':'0x202','value':'0x302'}})
    with pytest.raises(ValueError,match='64-bit'):
        validate_edits([],{'rax':{'expected':0,'value':2**64}})


def test_rip_edit_validates_observed_runtime_image_after_rebasing(tmp_path):
    from fixtures_formats import pe64
    from fdisbull.wine_debugger import PEDebugSession
    from fdisbull.wine_state import checked_runtime_rip
    source=tmp_path/'synthetic.exe';source.write_bytes(pe64())
    with Project.create(tmp_path/'synthetic.fdb',source) as project:
        # Exercise the real address mapper without claiming a live rebased VM.
        debug=PEDebugSession.__new__(PEDebugSession)
        debug.project=project;debug.regions=project.regions(1);debug.delta=0x10000000
        assert checked_runtime_rip(debug,0x150001000)==0x150001000
        with pytest.raises(ValueError,match='outside the observed'):
            checked_runtime_rip(debug,0x140001000)


def test_qmp_handles_fragmented_replies_and_async_stop_event():
    import socket,threading
    from fdisbull.qemu_control import QemuControl
    left,right=socket.socketpair();qmp=QemuControl.__new__(QemuControl)
    qmp.socket=left;qmp.buffer=bytearray();qmp.sequence=0;qmp.lock=threading.Lock()
    def peer():
        try:
            request=json.loads(right.recv(4096));assert request['execute']=='query-status'
            data=(json.dumps({'event':'STOP'})+'\n'+json.dumps({'return':{'running':False,'status':'paused'},'id':request['id']})+'\n').encode()
            right.sendall(data[:9]);right.sendall(data[9:])
        finally:right.close()
    worker=threading.Thread(target=peer);worker.start()
    try:assert qmp.call('query-status')=={'running':False,'status':'paused'}
    finally:qmp.close();worker.join(timeout=1)


def test_real_pe_layers_crc_native_state_edit_and_restart(tmp_path):
    import lief,shutil
    qemu,kernel,runtime,fixture=native_inputs();source=Path(fixture)
    binary=lief.PE.parse(str(source));base=binary.optional_header.imagebase
    exports={e.name:base+e.address for e in binary.get_export().entries}
    image_hash=hashlib.sha256(source.read_bytes()).hexdigest();path=tmp_path/'advanced.fdb'
    evidence=Path(os.environ.get('FDISBULL_PE_EVIDENCE',tmp_path/'exports'));evidence.mkdir(parents=True,exist_ok=True)
    inputs=tmp_path/'program';inputs.mkdir()
    shutil.copy2(source,inputs/source.name)
    (inputs/'fixture-asset.txt').write_text('Authored state-fork asset; never a game file.\n')
    options=dict(executable=qemu,game_dir=str(inputs),kernel=kernel,initramfs=runtime,version=1,
                 files=[source.name,'fixture-asset.txt'])
    witness={};started=time.monotonic()
    with Project.create(path,source) as project:
        for name in ('checkpoint','experiment_value','before_experiment','after_experiment','branch_value'):
            project.analyze(start=exports[name],max_instructions=4096)
        static=project.disassembly(address=exports['experiment_value'],lines=2,version=1)['instructions']
        child_version=project.patch(exports['experiment_value']+1,'09')['version']
        project.analyze(start=exports['experiment_value'],version=child_version,max_instructions=64)
        with project.debugger(**options) as debug:
            bp=debug.breakpoint(exports['checkpoint']);assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            def value(name):return int.from_bytes(bytes.fromhex(debug.memory(exports[name],length=4)['hex']),'little')
            def click(button='left'):
                frame=debug.screenshot();debug.click(80,80,button=button,mode_id=frame['metadata']['mode_id'])
                result=debug.run(timeout_ms=60000);assert result['outcome']=='breakpoint',result
            compute=exports['experiment_value']
            assert debug.memory(compute,length=6)['hex']=='b801000000c3'
            ram=debug.layer_patch('ram-two',hex(compute+1),expected_hex='01000000',data_hex='02000000',kind='ram')
            click();assert value('counter')==9 and value('integrity')==0
            witness['ram']={'counter':value('counter'),'crc_matches':value('integrity')}
            debug.layer_enable(ram['layer'],enabled=False)
            execute=debug.layer_patch('execute-three',hex(compute+1),expected_hex='01000000',data_hex='03000000',kind='execute')
            assert debug.code(compute,length=6)['hex']=='b803000000c3'
            assert debug.memory(compute,length=6)['hex']=='b801000000c3'
            before=debug.breakpoint(exports['before_experiment']);after=debug.breakpoint(exports['after_experiment'])
            frame=debug.screenshot();debug.click(80,80,mode_id=frame['metadata']['mode_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            trace=debug.trace('layer-execution.json',count=128,timeout_ms=60000)
            trace_data=json.loads(bytes(project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(trace['artifact'],)).fetchone()[0]))
            moved=[e for e in trace_data['events'] if e.get('native_address')]
            assert moved and moved[0]['ram_bytes']=='b801000000' and moved[0]['execution_bytes']=='b803000000',trace_data
            debug.delete_breakpoint(before['breakpoint_id']);debug.delete_breakpoint(after['breakpoint_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert value('counter')==12 and value('integrity')==1
            assert value('last_crc')==value('original_crc')
            witness['execute']={'counter':value('counter'),'crc_matches':value('integrity'),'crc32':hex(value('last_crc'))}
            debug.layer_enable(execute['layer'],enabled=False);click();assert value('counter')==13
            branch=debug.branch('invert-pe-jcc',exports['branch_value']+2)
            click('middle');assert value('counter')==15
            debug.layer_enable(branch['layer'],enabled=False);click('middle');assert value('counter')==16
            witness['branch']={'inverted_increment':2,'restored_increment':1}
            # The alternate instruction itself reads its original source byte.
            # A RAM-patched implementation would read B6, not the original 01.
            self_read=debug.layer_patch('read-original-code',compute,expected_hex='b801000000',data_hex='0fb6009090',kind='execute')
            before=debug.breakpoint(exports['before_experiment'])
            frame=debug.screenshot();debug.click(80,80,mode_id=frame['metadata']['mode_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            regs=debug.registers()
            debug.write_registers({'rax':{'expected':regs['general']['rax'],'value':hex(compute+1)}})
            code_watch=debug.breakpoint(compute+1,access='r',length=1)
            stopped=debug.run(timeout_ms=60000)
            assert stopped['outcome']=='watchpoint' and stopped['session']['stop_reason'].get('native_address'),stopped
            assert debug.memory(compute+1,length=1)['hex']=='01'
            with pytest.raises(ValueError,match='pending execution-layer'):
                debug.save_state('incomplete.sav')
            debug.delete_breakpoint(code_watch['breakpoint_id']);debug.delete_breakpoint(before['breakpoint_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert value('counter')==17 and value('integrity')==1
            debug.layer_enable(self_read['layer'],enabled=False)
            witness['alternate_reads_original']={'counter':17,'source_byte':'01','data_watch_inside_layer':True}
            debug.layer_enable(execute['layer'])
            watch=debug.breakpoint(exports['counter'],access='rw',length=4)
            from fdisbull.wine_state import apply_edits
            original=debug.registers()
            with pytest.raises(ValueError,match='expected value mismatch'):
                apply_edits(debug,[{'address':hex(exports['counter']),'expected_hex':'11000000','data_hex':'63000000'}],
                            {'rax':{'expected':int(original['general']['rax'],16)^1,'value':0}})
            assert value('counter')==17 and debug.registers()['general']==original['general']
            parent=debug.save_state('parent.sav');original_regs=debug.registers()
            witness['parent_artifact']=parent['artifact']
            debug.write_memory(exports['counter'],'29000000',expected_hex='11000000')
            debug.load_state(parent['artifact'])
            assert value('counter')==17 and debug.registers()['general']==original_regs['general']
            assert debug.layers()['active']==[execute['layer']]
            frame=debug.screenshot();debug.click(80,80,mode_id=frame['metadata']['mode_id'])
            stopped=debug.run(timeout_ms=60000);assert stopped['outcome']=='watchpoint',stopped
            assert value('counter')==17
            debug.delete_breakpoint(watch['breakpoint_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert value('counter')==20
        info=project.debug_state_info(parent['artifact']);assert info['native_size']>0
        derived=project.debug_fork_state(parent['artifact'],qemu,str(inputs),kernel=kernel,initramfs=runtime,
            memory=[{'address':hex(exports['counter']),'expected_hex':'11000000','data_hex':'33000000'}],
            registers={'rax':{'expected':original_regs['general']['rax'],'value':'0x123456789abcdef0'}})
        assert project.debug_state_info(parent['artifact'])['sha256']==parent['sha256']
        assert project.debug_state_info(derived['artifact'])['metadata']['derivation']['parent_artifact']==parent['artifact']
        assert [item['path'] for item in project.debug_state_info(derived['artifact'])['metadata']['files']]==[source.name,'fixture-asset.txt']
        witness['derived_artifact']=derived['artifact']
    with Project(path) as project:
        with project.debugger(**options,state=derived['artifact']) as debug:
            assert debug.memory(exports['counter'],length=4)['hex']=='33000000'
            assert debug.registers()['general']['rax']=='0x123456789abcdef0'
            assert debug.layers()['active']==[execute['layer']]
            debug.delete_breakpoint(watch['breakpoint_id'])
            frame=debug.click_frame(80,80,name='restored-click.png',grid_step=8)
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert debug.memory(exports['counter'],length=4)['hex']=='36000000'
            assert debug.memory(exports['integrity'],length=4)['hex']=='01000000'
            after=debug.screenshot('restored-after.png')
            trace=debug.trace('restored-trace.json',count=4,timeout_ms=20000)
            debug.layer_enable(execute['layer'],enabled=False)
            current=debug.screenshot();debug.click(80,80,mode_id=current['metadata']['mode_id'])
            assert debug.run(timeout_ms=60000)['outcome']=='breakpoint'
            assert debug.memory(exports['counter'],length=4)['hex']=='37000000'
            debug.load_state(parent['artifact'])
            assert debug.memory(exports['counter'],length=4)['hex']=='11000000'
            assert debug.registers()['general']==original_regs['general']
            run=debug.run_id
        assert project.disassembly(address=exports['experiment_value'],lines=2,version=1)['instructions']==static
        assert project.disassembly(address=exports['experiment_value'],lines=1,version=child_version)['instructions'][0]['bytes']=='b809000000'
        for artifact in project.debug_artifacts(version=1)['artifacts']:
            if artifact['kind']=='state':continue
            destination=evidence/(artifact['id']+'-'+artifact['name'])
            project.debug_export(artifact['id'],destination)
        exported=project.debug_export(derived['artifact'],tmp_path/'private-derived.sav')
        import zipfile
        with zipfile.ZipFile(exported['output']) as archive:
            assert set(archive.namelist())=={'state.json','machine.mig.gz'} and archive.testzip() is None
        witness.update(result='pass',elapsed_seconds=time.monotonic()-started,original_source_unchanged=hashlib.sha256(source.read_bytes()).hexdigest()==image_hash,
                       parent_memory=17,derived_memory=51,derived_rax='0x123456789abcdef0',resumed_with_layer=54,resumed_without_layer=55)
        assert witness['original_source_unchanged']
        (evidence/'advanced-verification.json').write_text(json.dumps(witness,indent=2)+'\n')
