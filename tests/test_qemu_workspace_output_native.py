"""Native caller-attested output export, without guest-create provenance."""
import pytest
from fdisbull.project import Project
from support.dos_workspace_fixture import workspace_probe
from test_qemu_dos_workspace_native import (
    _dirty_search_probe, _inputs, _launch, _mz, _open, _runtime_base, _word,
)


def _count_states(project):
    return project.db.execute("SELECT count(*) FROM debug_artifacts WHERE kind='state'").fetchone()[0]


@pytest.mark.parametrize('kind',['com','mz'])
def test_attested_output_preserves_checkpoint_and_imports_cold(tmp_path,kind):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    com,marker=workspace_probe(build,runtime['NASM']);source=_mz(com) if kind=='mz' else com
    binary=directory/('PROBE.EXE' if kind=='mz' else 'PROBE.COM');binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    destination=tmp_path/'export.dat'; database=tmp_path/'project.fdb'
    with Project.create(database,binary,**({} if kind=='mz' else {'image':'com'})) as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);ready=debug.breakpoint(base+marker['open_ready'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            opened=[row for row in _open(debug)['handles'] if row['dos_name']=='EXIST.BIN']
            assert len(opened)==1 and opened[0]['position']==2
            saved=debug.save_state(); history=debug.rewind_start(max_steps=4,timeout_ms=60000)
            states_before=_count_states(project);pc_before=debug.registers()['linear_pc']
            with pytest.raises(ValueError):
                debug.workspace_save_output('RENAMED.DAT',destination)
            with pytest.raises(ValueError):
                debug.workspace_save_output('RENAMED.DAT',destination,closed_and_flushed=True)
            assert not destination.exists() and not debug.closed
            assert debug.registers()['linear_pc']==pc_before and _count_states(project)==states_before
            assert debug.rewind_status()['cursor']==history['cursor']
            debug.delete_breakpoint(ready['breakpoint_id'])
            done=debug.breakpoint(base+marker['done'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            assert _word(debug,base+marker['status'])==0xbeef
            debug.delete_breakpoint(done['breakpoint_id'])
            # A protected original path and an existing export destination must
            # refuse without overwriting either file.
            existing=tmp_path/'occupied.dat';existing.write_bytes(b'leave this alone')
            with pytest.raises((ValueError,FileExistsError)):
                debug.workspace_save_output('EXIST.BIN',tmp_path/'original-copy.dat',closed_and_flushed=True)
            with pytest.raises((ValueError,FileExistsError)):
                debug.workspace_save_output('RENAMED.DAT',existing,closed_and_flushed=True)
            assert existing.read_bytes()==b'leave this alone' and not debug.closed
            result=debug.workspace_save_output('RENAMED.DAT',destination,closed_and_flushed=True,timeout_ms=60000)
            assert result['format']=='fdisbull-qemu-workspace-output-1'
            assert result['provenance']=='caller-attested' and result['guest_create_provenance'] is False
            assert result['checkpoint']['artifact'] and result['generation']['artifact'] and result['artifact']
            assert result['export']['durable'] and destination.read_bytes()==bytes.fromhex('1000ff41')
            for observation in (result['file_state_before'],result['file_state_after']):
                assert observation['ordinary_open_count']==0 and observation['dirty_buffer_count']==0
            generation=result['generation']['artifact']
            with pytest.raises(ValueError,match='witnessed new'):
                debug.workspace_keep('RENAMED.DAT',tmp_path/'not-proven.dat',generation)
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            assert destination.read_bytes()==bytes.fromhex('1000ff41')
            names={entry['dos_path'] for entry in debug.workspace_files()['entries']}
            assert 'RENAMED.DAT' not in names
            debug.delete_breakpoint(restored['controls']['breakpoints'][ready['breakpoint_id']])
            old=debug.workspace_status()['generation']['artifact']
            staged=debug.workspace_edit(old,'import',path='IMPORT.DAT',data=destination.read_bytes())
            imported=staged['generation']['artifact']
            assert staged['active'] is False
        with _launch(project,runtime,directory,generation=imported) as cold:
            assert cold.workspace_read('IMPORT.DAT')['data']==bytes.fromhex('1000ff41')
            assert cold.workspace_status()['generation']['artifact']==imported
    assert binary.read_bytes()==source
    assert (directory/'EXIST.BIN').read_bytes()==b'ABCD'
    assert (directory/'GONE.BIN').read_bytes()==b'original'
    assert not (directory/'RENAMED.DAT').exists()


def test_attested_output_refuses_dirty_open_handle_without_closing_owner(tmp_path):
    runtime=_inputs();build=tmp_path/'build';build.mkdir();directory=tmp_path/'input';directory.mkdir()
    source,marker=_dirty_search_probe(build,runtime['NASM']);binary=directory/'PROBE.COM';binary.write_bytes(source)
    (directory/'EXIST.BIN').write_bytes(b'ABCD');(directory/'GONE.BIN').write_bytes(b'original')
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);ready=debug.breakpoint(base+marker['ready'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            state=_open(debug)
            assert state['ordinary_open_count']>0 and state['dirty_buffer_count']>0
            pc=debug.registers()['linear_pc'];count=_count_states(project)
            with pytest.raises(ValueError):
                debug.workspace_save_output('RENAMED.DAT',tmp_path/'never.dat',closed_and_flushed=True)
            assert not debug.closed and debug.registers()['linear_pc']==pc and _count_states(project)==count
            assert not (tmp_path/'never.dat').exists()
            debug.delete_breakpoint(ready['breakpoint_id'])
            done=debug.breakpoint(base+marker['done'])
            assert debug.run(timeout_ms=20000)['outcome']=='breakpoint'
            assert _word(debug,base+marker['status'])==0xbeef
            debug.delete_breakpoint(done['breakpoint_id'])
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert (directory/'EXIST.BIN').read_bytes()==b'ABCD'
