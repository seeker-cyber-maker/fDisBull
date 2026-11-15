"""Disposable checks of staged activation reporting; no installation performed."""
import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('check_local_install_test',ROOT/'scripts/check_local_install.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


def selected(tmp_path,status):
    base=tmp_path/'base';prefix=base/'releases/candidate';(prefix/'share').mkdir(parents=True)
    (base/'current').symlink_to('releases/candidate')
    (prefix/'RUNTIME.json').write_text(json.dumps({'version':'0.35.0','source_commit':'a'*40}))
    attempt='1'*32;directory=prefix/'share/activations'/attempt;directory.mkdir(parents=True)
    intent={'schema':'fdisbull-install-activation-2','attempt':attempt,'source_commit':'a'*40,'version':'0.35.0',
            'previous_selector':None,'new_selector':'releases/candidate','staged_receipt_sha256':'c'*64}
    path=directory/'intent.json';path.write_text(json.dumps(intent));intent_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    (prefix/'INSTALLATION.json').write_text(json.dumps({'status':status,'version':'0.35.0','source_commit':'a'*40,
         'activation_attempt':attempt,'activation_intent':{'path':f'share/activations/{attempt}/intent.json','sha256':intent_sha}}))
    (prefix/'PAYLOAD.json').write_text('{}')
    (prefix/'share/verify-system.py').write_text('# stub')
    return base,prefix


def test_selected_activating_is_never_normal_pass(tmp_path,monkeypatch,capsys):
    import sys
    base,_=selected(tmp_path,'activating')
    monkeypatch.setattr(sys,'argv',['check','--base',str(base),'--json'])
    monkeypatch.setattr(checker.subprocess,'run',lambda *a,**k:pytest.fail('public check must fail before verifier'))
    assert checker.main()==1
    assert json.loads(capsys.readouterr().out)['status']=='failed'


def test_explicit_precheck_is_selected_but_not_active(tmp_path,monkeypatch,capsys):
    import sys
    base,_=selected(tmp_path,'activating');calls=[]
    proof={'status':'prechecked','selected_default':True,'active_default':False,'version':'0.35.0','source_commit':'a'*40}
    def run(command,**kwargs):calls.append(command);return SimpleNamespace(returncode=0,stdout=json.dumps(proof),stderr='')
    monkeypatch.setattr(checker.subprocess,'run',run)
    monkeypatch.setattr(sys,'argv',['check','--base',str(base),'--json','--activation-precheck'])
    assert checker.main()==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='prechecked' and result['selected_default'] is True and result['active_default'] is False
    assert result['version']=='0.35.0' and result['source_commit']=='a'*40
    assert '--activation-precheck' in calls[0]


def test_precheck_rejects_false_active_claim(tmp_path,monkeypatch,capsys):
    import sys
    base,_=selected(tmp_path,'activating')
    proof={'status':'passed','selected_default':True,'active_default':True,'version':'0.35.0','source_commit':'a'*40}
    monkeypatch.setattr(checker.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(proof),stderr=''))
    monkeypatch.setattr(sys,'argv',['check','--base',str(base),'--json','--activation-precheck'])
    assert checker.main()==1
    assert json.loads(capsys.readouterr().out)['status']=='failed'


def test_public_checker_refuses_missing_completion_before_trusting_verifier(tmp_path,monkeypatch,capsys):
    import sys
    base,_=selected(tmp_path,'active_verified')
    monkeypatch.setattr(sys,'argv',['check','--base',str(base),'--json'])
    monkeypatch.setattr(checker.subprocess,'run',lambda *a,**k:pytest.fail('missing completion must fail independently'))
    assert checker.main()==1
    assert json.loads(capsys.readouterr().out)['status']=='failed'


def test_precheck_refuses_tampered_intent_before_verifier(tmp_path,monkeypatch,capsys):
    import sys
    base,prefix=selected(tmp_path,'activating')
    path=prefix/'share/activations'/('1'*32)/'intent.json';path.write_text('{}')
    monkeypatch.setattr(sys,'argv',['check','--base',str(base),'--json','--activation-precheck'])
    monkeypatch.setattr(checker.subprocess,'run',lambda *a,**k:pytest.fail('hash mismatch must fail independently'))
    assert checker.main()==1
    assert json.loads(capsys.readouterr().out)['status']=='failed'


def test_public_checker_requires_and_independently_rehashes_completion(tmp_path,monkeypatch,capsys):
    import sys
    base,prefix=selected(tmp_path,'active_verified');attempt='1'*32
    receipt=json.loads((prefix/'INSTALLATION.json').read_text());intent_sha=receipt['activation_intent']['sha256']
    complete={'schema':'fdisbull-install-activation-complete-2','attempt':attempt,'source_commit':'a'*40,'version':'0.35.0',
              'previous_selector':None,'new_selector':'releases/candidate','intent_sha256':intent_sha,
              'precheck_result':{'status':'prechecked','selected_default':True,'active_default':False,'version':'0.35.0','source_commit':'a'*40},
              'command_resolution':{'prefix':str(prefix),'version':'0.35.0','caller_path':'/usr/local/bin/fdisbull',
                  'wrapper':'/usr/local/bin/fdisbull','wrapper_sha256':'a'*64,
                  'native_commands':{'dosbox':'/dosbox','qemu':'/qemu','targets':['dosbox-layers','dosbox-x','qemu-system-x86_64']}}}
    path=prefix/'share/activations'/attempt/'complete.json';path.write_text(json.dumps(complete))
    receipt['activation_complete']={'path':f'share/activations/{attempt}/complete.json','sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (prefix/'INSTALLATION.json').write_text(json.dumps(receipt))
    proof={'status':'passed','selected_default':True,'active_default':True,'version':'0.35.0','source_commit':'a'*40}
    calls=[]
    monkeypatch.setattr(checker.subprocess,'run',lambda *a,**k:calls.append(a) or SimpleNamespace(returncode=0,stdout=json.dumps(proof),stderr=''))
    monkeypatch.setattr(sys,'argv',['check','--base',str(base),'--json'])
    assert checker.main()==0
    assert json.loads(capsys.readouterr().out)['status']=='passed' and len(calls)==1
    path.write_text(json.dumps({**complete,'source_commit':'b'*40}))
    assert checker.main()==1
    assert json.loads(capsys.readouterr().out)['status']=='failed' and len(calls)==1
