"""JSON workspace routing and captured startup directory contracts."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fdisbull.debugger import DebugWorkspace
from test_qemu_workspace import session


def _workspace(tmp_path):
    workspace=DebugWorkspace();calls=[]
    fake=SimpleNamespace(run_id='run',project=SimpleNamespace(path=(tmp_path/'project.fdb').resolve()),metadata={'backend':'qemu-dos'})
    fake.workspace_read=lambda **kw:dict(generation='g',data=b'\x00\xff',size=2)
    fake.workspace_edit=lambda **kw:(calls.append(kw) or {'active':False})
    workspace.sessions['run']=fake
    return workspace,calls,fake.project.path


def test_json_read_and_edit_hex(tmp_path):
    workspace,calls,path=_workspace(tmp_path)
    result=workspace.invoke('debug-workspace-read',str(path),{'run':'run','path':'A.DAT'})
    assert result['data_hex']=='00ff' and 'data' not in result
    assert json.loads(json.dumps(result))['data_hex']=='00ff'
    params={'run':'run','generation':'g','operation':'write','path':'A.DAT',
            'data_hex':'00ff','expected_sha256':'a'*64}
    assert workspace.invoke('debug-workspace-edit',str(path),params)=={'active':False}
    assert calls==[{'generation':'g','operation':'write','path':'A.DAT','data':b'\x00\xff','expected_sha256':'a'*64}]


@pytest.mark.parametrize('options',[{'data_hex':'0'}, {'data_hex':'gg'}, {'data_hex':3}, {'data_hex':'00','data':'00'}])
def test_json_edit_bad_hex_rejected_before_dispatch(tmp_path,options):
    workspace,calls,path=_workspace(tmp_path)
    with pytest.raises(ValueError):
        workspace.invoke('debug-workspace-edit',str(path),{'run':'run','generation':'g','operation':'create','path':'A',**options})
    assert calls==[]


def test_omitted_game_dir_uses_captured_startup_workspace(tmp_path,monkeypatch):
    import fdisbull.project
    initial=tmp_path/'initial';initial.mkdir();other=tmp_path/'later';other.mkdir()
    monkeypatch.chdir(initial);workspace=DebugWorkspace();monkeypatch.chdir(other)
    calls=[]
    class FakeProject:
        def __init__(self,path): self.path=Path(path).resolve()
        def debugger(self,**params):
            calls.append(params)
            return SimpleNamespace(run_id=str(len(calls)),status=lambda:{'ok':True})
        def __exit__(self,*args): pass
    monkeypatch.setattr(fdisbull.project,'Project',FakeProject)
    assert workspace.invoke('debug-launch','db',{'backend':'qemu-dos','executable':'qemu'})=={'ok':True}
    workspace.invoke('debug-launch','db',{'backend':'qemu-dos','executable':'qemu','game_dir':'explicit'})
    assert calls[0]['game_dir']==str(initial.resolve()) and calls[1]['game_dir']=='explicit'


def test_legacy_process_state_info_does_not_claim_workspace(session,monkeypatch):
    import fdisbull.qemu_dos_checkpoint as checkpoint
    bundle={'format':checkpoint.FORMAT,'fixture':'old'}
    sidecar=checkpoint._sha(checkpoint._json(bundle))
    artifact=session.project._debug_artifact(session.run_id,'legacy.qcow2','state',b'legacy',
                    {'format':checkpoint.FORMAT,'sidecar_sha256':sidecar})
    monkeypatch.setattr(checkpoint,'_unarchive',lambda data:(b'machine',bundle))
    info=session.project.debug_state_info(artifact['artifact'])
    assert info['metadata']['format']==checkpoint.FORMAT
    assert 'workspace' not in info['metadata']
    assert info['scope']=='stopped DOS process, private disk, layers and debugger controls'
