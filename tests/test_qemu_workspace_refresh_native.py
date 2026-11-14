"""Native staged host refresh: old guest/checkpoint and cold-generation isolation."""
import hashlib
import pytest
from fdisbull.project import Project
from support.dos_workspace_fixture import workspace_probe
from test_qemu_dos_workspace_native import _inputs,_launch,_mz,_open,_runtime_base,_word


def _continue_to_done(debug,base,marker):
    finish=debug.breakpoint(base+marker['done'])
    assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
    assert _word(debug,base+marker['status'])==0xbeef
    value=debug.memory(base+marker['second_read'],length=2)['hex']
    debug.delete_breakpoint(finish['breakpoint_id'])
    return value


def _cold_probe(project,runtime,directory,generation,marker):
    with _launch(project,runtime,directory,generation=generation) as debug:
        base=_runtime_base(debug)
        result=_continue_to_done(debug,base,marker)
        assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
        return result


@pytest.mark.parametrize('kind',['com','mz'])
def test_refresh_is_staged_and_old_checkpoint_and_generations_survive(tmp_path,kind):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    com,marker=workspace_probe(build,runtime['NASM']);source=_mz(com) if kind=='mz' else com
    binary=directory/('PROBE.EXE' if kind=='mz' else 'PROBE.COM');binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    (directory/'DELETE.DAT').write_bytes(b'will be deleted')
    with Project.create(tmp_path/'project.fdb',binary,**({} if kind=='mz' else {'image':'com'})) as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            ready=debug.breakpoint(base+marker['open_ready'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            opened=[item for item in _open(debug)['handles'] if item['dos_name']=='EXIST.BIN']
            assert len(opened)==1 and opened[0]['position']==2
            saved=debug.save_state()
            history=debug.rewind_start(max_steps=4,timeout_ms=60000)
            current=debug.workspace_status()['generation']['artifact']
            assert debug.rewind_status()['cursor']==history['cursor']
            (directory/'EXIST.BIN').write_bytes(b'WXYZ')
            (directory/'DELETE.DAT').unlink()
            (directory/'ADDED.DAT').write_bytes(b'new host data')
            changed=debug.workspace_edit(current,'refresh',timeout_ms=60000)
            refreshed=changed['generation']['artifact']
            assert changed['active'] is False
            assert debug.workspace_status()['generation']['artifact']==current
            assert debug.rewind_status()['cursor']==history['cursor']
            opened=[item for item in _open(debug)['handles'] if item['dos_name']=='EXIST.BIN']
            assert len(opened)==1 and opened[0]['position']==2
            assert debug.workspace_read('EXIST.BIN',current)['data']==b'ABCD'
            assert debug.workspace_read('EXIST.BIN',refreshed)['data']==b'WXYZ'
            names={entry['dos_path'] for entry in debug.workspace_files(refreshed)['entries']}
            assert 'ADDED.DAT' in names and 'DELETE.DAT' not in names
            debug.delete_breakpoint(ready['breakpoint_id'])
            assert _continue_to_done(debug,base,marker)=='4344'
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            remapped=restored['controls']['breakpoints'][ready['breakpoint_id']]
            opened=[item for item in _open(debug)['handles'] if item['dos_name']=='EXIST.BIN']
            assert len(opened)==1 and opened[0]['position']==2
            debug.delete_breakpoint(remapped)
            assert _continue_to_done(debug,base,marker)=='4344'
        assert _cold_probe(project,runtime,directory,current,marker)=='4344'
        assert _cold_probe(project,runtime,directory,refreshed,marker)=='595a'
    assert binary.read_bytes()==source
    assert (directory/'EXIST.BIN').read_bytes()==b'WXYZ'
    assert (directory/'ADDED.DAT').read_bytes()==b'new host data'
    assert not (directory/'DELETE.DAT').exists()
    assert (directory/'GONE.BIN').read_bytes()==b'original'


def test_refresh_refusals_preserve_live_owner(tmp_path):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    source,marker=workspace_probe(build,runtime['NASM']);binary=directory/'PROBE.COM';binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);generation=debug.workspace_status()['generation']['artifact']
            private=debug.workspace_edit(generation,'write',path='EXIST.BIN',data=b'private',
                        expected_sha256=hashlib.sha256(b'ABCD').hexdigest())['generation']['artifact']
            with pytest.raises(ValueError,match='conflict'):
                debug.workspace_edit(private,'refresh')
            assert not debug.closed and debug.workspace_status()['generation']['artifact']==generation
            binary.write_bytes(source+b'changed')
            with pytest.raises(ValueError,match='source|executable|identity'):
                debug.workspace_edit(generation,'refresh')
            binary.write_bytes(source)
            assert not debug.closed and debug.workspace_status()['generation']['artifact']==generation
            directory.rename(tmp_path/'original-root');directory.mkdir();(directory/'PROBE.COM').write_bytes(source)
            with pytest.raises(ValueError,match='root|identity'):
                debug.workspace_edit(generation,'refresh')
            assert not debug.closed and debug.workspace_status()['generation']['artifact']==generation
            assert _continue_to_done(debug,base,marker)=='4344'
