"""Native N24 automatic save boundaries on explicit outer public runs."""
import os
import struct
import pytest
from fdisbull.project import Project
from fdisbull.debug_script import execute_script
from test_qemu_dos_workspace_native import _inputs,_launch,_runtime_base,_word
from test_qemu_dos_save_operations_native import _setup,_initial_file_generation


def _runtime():
    runtime=_inputs();binary=os.environ.get('FDISBULL_QEMU_SAVE_STOP')
    if not binary:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS')=='1':pytest.fail('FDISBULL_QEMU_SAVE_STOP is required')
        pytest.skip('Supply FDISBULL_QEMU_SAVE_STOP')
    runtime['qemu']=binary
    return runtime


def _number(value):return int(value,0) if isinstance(value,str) else value


def _policy_receipt(result):
    assert result['outcome']=='save_boundary' and result.get('save_keep')
    keep=result['save_keep']
    assert keep['checkpoint'] and keep['workspace'] and keep['policy']
    return keep['policy']


@pytest.mark.parametrize('kind',['com','mz'])
def test_outer_run_stops_before_next_instruction_and_keeps_two_versions(tmp_path,kind):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,kind=kind)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,**({} if kind=='mz' else {'image':'com'})) as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug)
            debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            first=debug.run(timeout_ms=30000)
            assert _policy_receipt(first)['outcome']=='kept'
            assert _number(debug.registers()['linear_pc'])==base+marker['first']-6
            assert _word(debug,base+marker['status'])==0
            assert sorted(p.read_bytes() for p in keeps.iterdir())==[b'AXZ']
            second=debug.run(timeout_ms=30000)
            assert _policy_receipt(second)['outcome']=='kept'
            assert _word(debug,base+marker['status'])==0xa11a
            assert sorted(p.read_bytes() for p in keeps.iterdir())==[b'AX!',b'AXZ']
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'
    assert not (directory/'SAVE.DAT').exists()


def test_temp_rename_auto_boundary_only_after_final_flush(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant='replace')
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        generation=_initial_file_generation(project,runtime,directory)
        with _launch(project,runtime,directory,generation=generation) as debug:
            debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',temporary_path='TEMP.DAT',safe_stop=True)
            result=debug.run(timeout_ms=30000)
            assert _policy_receipt(result)['outcome']=='kept'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'NEW']
            assert debug.run(timeout_ms=10000)['outcome']=='guest_exit'
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


def test_checkpoint_and_project_reopen_dedup_and_disabled_policy(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir();database=tmp_path/'project.fdb'
    with Project.create(database,binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            policy=debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)['policy']['artifact']
            armed=debug.save_state()
            assert _policy_receipt(debug.run(timeout_ms=30000))['outcome']=='kept'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AXZ']
    with Project(database) as project:
        with _launch(project,runtime,directory) as debug:
            debug.load_state(armed['artifact'],timeout_ms=60000)
            assert _policy_receipt(debug.run(timeout_ms=30000))['outcome']=='already-kept'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AXZ']
            debug.workspace_keep_policy_enabled(policy,False)
            debug.load_state(armed['artifact'],timeout_ms=60000)
            assert debug.run(timeout_ms=30000)['outcome']=='guest_exit'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AXZ']
    assert binary.read_bytes()==source and (directory/'ORIG.DAT').read_bytes()==b'original'


def test_user_breakpoint_before_flush_wins_without_automatic_keep(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            point=debug.breakpoint(base+marker['seek'])
            first=debug.run(timeout_ms=30000)
            assert first['outcome']=='breakpoint' and not first.get('save_keep')
            assert list(keeps.iterdir())==[]
            debug.delete_breakpoint(point['breakpoint_id'])
            assert _policy_receipt(debug.run(timeout_ms=30000))['outcome']=='kept'
    assert binary.read_bytes()==source


def test_checkpoint_during_flush_yields_one_boundary_after_restore(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            offset,segment=struct.unpack_from('<HH',debug._vectors_before,0x21*4)
            vector=segment*16+offset;point=debug.breakpoint(vector)
            for _ in range(32):
                result=debug.run(timeout_ms=30000)
                assert result['outcome']=='breakpoint' and not result.get('save_keep')
                state=debug.workspace_provenance_status()['native']
                assert state['pending']
                if state['pending-function']==0x0d:
                    break
                debug.delete_breakpoint(point['breakpoint_id'])
                assert debug.step(timeout_ms=10000)['outcome']=='step'
                point=debug.breakpoint(vector)
            else:pytest.fail('DOS flush entry was not observed within the bounded calls')
            saved=debug.save_state()
            debug.delete_breakpoint(point['breakpoint_id'])
            assert _policy_receipt(debug.run(timeout_ms=30000))['outcome']=='kept'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AXZ']
            restored=debug.load_state(saved['artifact'],timeout_ms=60000)
            assert debug.workspace_provenance_status()['native']['pending-function']==0x0d
            debug.delete_breakpoint(restored['controls']['breakpoints'][point['breakpoint_id']])
            assert _policy_receipt(debug.run(timeout_ms=30000))['outcome']=='already-kept'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AXZ']
    assert binary.read_bytes()==source


def test_breakpoint_at_return_site_never_fabricates_boundary_or_keep(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            point=debug.breakpoint(base+marker['first']-6)
            result=debug.run(timeout_ms=30000)
            assert result['outcome']=='breakpoint' and not result.get('save_keep')
            assert point['breakpoint_id'] in result['session']['stop_reason']['breakpoint_ids']
            assert list(keeps.iterdir())==[]
            debug.delete_breakpoint(point['breakpoint_id'])
            assert _policy_receipt(debug.run(timeout_ms=30000))['outcome']=='kept'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AX!']
    assert binary.read_bytes()==source


def test_hook_at_return_site_keeps_real_hook_cause_and_no_autokeep(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            hook=debug.hook(base+marker['first']-6,space='linear',once=False,max_hits=2,
                            actions=[{'op':'layers','layers':[]}])['hook']
            result=debug.run(timeout_ms=30000,stop_on_hook=True)
            assert result['outcome']=='hook' and not result.get('save_keep')
            assert len(result['hook_hits'])==1 and result['hook_hits'][0]['hook']==hook
            assert list(keeps.iterdir())==[]
            debug.delete_hook(hook)
    assert binary.read_bytes()==source


def test_script_run_suppresses_automatic_keeps(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            script={'format':'fdisbull-script-1','backend':'qemu-dos',
                    'steps':[{'op':'run','expect':'guest_exit','timeout_ms':30000}]}
            result=execute_script(debug,script,timeout_ms=60000)
            assert result['ok'] and list(keeps.iterdir())==[]
    assert binary.read_bytes()==source


def test_comparative_trial_does_not_publish_automatic_keeps(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            base=_runtime_base(debug);debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            debug.breakpoint(base+marker['done'])
            route={'format':'fdisbull-script-1','backend':'qemu-dos',
                   'steps':[{'op':'run','expect':'breakpoint','timeout_ms':30000}]}
            saved=debug.save_experiment('trial.json',script=route)
            compared=debug.compare_experiment(saved['artifact'],layers=[],timeout_ms=60000)
            assert compared['ok'] and compared['baseline_restored']
            assert not list(keeps.iterdir())
            assert _policy_receipt(debug.run(timeout_ms=30000))['outcome']=='kept'
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AXZ']
    assert binary.read_bytes()==source


def test_invalid_save_does_not_trigger_automatic_keep(tmp_path):
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime,variant='gap')
    keeps=tmp_path/'keeps';keeps.mkdir()
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            result=debug.run(timeout_ms=30000)
            assert result['outcome']=='guest_exit' and not result.get('save_keep')
            assert list(keeps.iterdir())==[]
    assert binary.read_bytes()==source


def test_keep_journal_failure_after_export_closes_without_replay(tmp_path,monkeypatch):
    from fdisbull.dos_keep_policy import KeepPolicyStore
    runtime=_runtime();directory,binary,source,marker=_setup(tmp_path,runtime)
    keeps=tmp_path/'keeps';keeps.mkdir();original=KeepPolicyStore._put
    def fail_completion(owner,kind,document):
        if document.get('action')=='complete':raise OSError('injected keep journal failure')
        return original(owner,kind,document)
    monkeypatch.setattr(KeepPolicyStore,'_put',fail_completion)
    with Project.create(tmp_path/'project.fdb',binary,image='com') as project:
        with _launch(project,runtime,directory) as debug:
            debug.workspace_keep_policy('SAVE.DAT',keeps,mode='save',safe_stop=True)
            with pytest.raises(OSError,match='injected keep journal failure') as raised:
                debug.run(timeout_ms=30000)
            effects=raised.value.result
            assert effects['execution']['outcome']=='save_boundary'
            assert effects['keep_effects']['outcome']=='needs-reconciliation'
            assert effects['keep_effects']['export']['durable']
            assert 'do not replay' in effects['disposition']
            assert debug.closed
            assert [p.read_bytes() for p in keeps.iterdir()]==[b'AXZ']
    assert binary.read_bytes()==source
