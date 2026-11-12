"""Host-only journal tests; synthetic receipts do not assert guest provenance."""
import hashlib
import json
import os
import pytest

from test_qemu_workspace import session
from test_qemu_workspace_edits import prepared_host
from fdisbull.dos_file_layers import WorkspaceStore
from fdisbull.dos_keep_policy import KeepPolicyStore, PROVENANCE, PROVENANCE_KIND


def setup(session, tmp_path):
    debug, source = prepared_host(session, tmp_path)
    destination = tmp_path / 'kept'; destination.mkdir()
    base = debug._dos_workspace['generation']['artifact']
    store = KeepPolicyStore(debug)
    policy = store.create('D:\\SAVE.DAT', destination, 'observer-token', base)['artifact']
    return debug, store, policy, base, destination


def proof(debug, base, data, *, path='SAVE.DAT'):
    ws = WorkspaceStore(debug)
    generation = ws.create_file(base, path, data)['artifact']
    def event(sequence, function, handle=5, ax=0, requested=0, accepted=0):
        return dict(sequence=sequence,function=function,handle=handle,ax=ax,requested=requested,
                    accepted=accepted,carry=False,**{'caller-pc':0x1000,'return-pc':0x1002})
    events=[event(1,0x5b,ax=5)]
    if data: events.append(event(len(events)+1,0x40,ax=len(data),requested=len(data),accepted=len(data)))
    events.extend([event(len(events)+1,0x3e),event(len(events)+2,0x0d)])
    native={'api-version':1,'model':'qemu-pc-dos-save-witness-v1','active':True,'valid':True,
            'epoch':1,'generation':1,'event-count':len(events),'write-count':int(bool(data)),
            'bytes-written':len(data),'child-psp':0x100,'created-handle':5,'events':events,
            'payload-hex':data.hex(),'token':'observer-token','dos-path':'D:\\'+path,
            'source-ranges':[{'start':0x1000,'size':0x100}],'phase':'ready','pending':False,'create-seen':True,
            'close-seen':True,'flush-seen':True,'commit-seen':False}
    doc = dict(format=PROVENANCE, path=path, source_sha256=debug.metadata['source_sha256'],
               version=debug.version['id'], base_generation=base, generation=generation,
               payload_sha256=hashlib.sha256(data).hexdigest(), size=len(data),
               observer_token='observer-token', native=native)
    ref = debug._artifact('proof.json', PROVENANCE_KIND, json.dumps(doc).encode(), {})
    return generation, dict(artifact=ref['artifact'], sha256=ref['sha256'])


def test_policy_versions_deduplicate_and_survive_new_store(session, tmp_path):
    debug, store, policy, base, dest = setup(session, tmp_path)
    g1, p1 = proof(debug, base, b'first')
    result = store.apply(policy, g1, p1)
    assert result['outcome'] == 'kept' and (dest/'00000001.SAV').read_bytes() == b'first'
    assert KeepPolicyStore(debug).apply(policy, g1, p1)['outcome'] == 'already-kept'
    g2, p2 = proof(debug, base, b'second')
    assert store.apply(policy, g2, p2)['outcome'] == 'kept'
    assert (dest/'00000002.SAV').read_bytes() == b'second'
    assert store.status(policy)['completed'] == 2
    store.set_enabled(policy, False)
    with pytest.raises(ValueError, match='disabled'): store.apply(policy, g1, p1)
    store.set_enabled(policy, True)
    assert store.apply(policy, g1, p1)['outcome'] == 'already-kept'


def test_journal_survives_new_run_and_checkpoint_cursor_change(session,tmp_path):
    from test_qemu_dos_history import Harness
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'checkpointed')
    store.apply(policy, gen, ref)
    # A different run represents the host after a checkpoint restore; the
    # policy journal is not an in-guest checkpoint or a native restore test.
    restored = Harness(debug.project, run_id='restored-run')
    restored._artifact = lambda *args: restored.project._debug_artifact(restored.run_id,*args)
    fresh = KeepPolicyStore(restored)
    assert fresh.status(policy)['completed'] == 1
    assert fresh.apply(policy, gen, ref)['outcome'] == 'already-kept'
    assert (dest/'00000001.SAV').read_bytes() == b'checkpointed'


def test_wrong_provenance_or_corrupted_output_refuses(session, tmp_path):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'bytes')
    with pytest.raises(ValueError, match='provenance'):
        store.apply(policy, gen, dict(ref, sha256='0'*64))
    store.apply(policy, gen, ref)
    (dest/'00000001.SAV').write_bytes(b'wrong')
    with pytest.raises(ValueError, match='differ'): store.apply(policy, gen, ref)
    (dest/'00000001.SAV').unlink()
    with pytest.raises(FileNotFoundError): store.apply(policy, gen, ref)


def test_failure_keeps_pending_and_never_replays(session, tmp_path, monkeypatch):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'bytes')
    calls=[]
    def fail(*args, **kwargs):
        calls.append(1); raise OSError('unknown publication')
    monkeypatch.setattr(store.workspace, 'export_file', fail)
    with pytest.raises(OSError) as error: store.apply(policy, gen, ref)
    assert error.value.result['outcome'] == 'needs-reconciliation'
    assert KeepPolicyStore(debug).apply(policy, gen, ref)['outcome'] == 'needs-reconciliation'
    assert len(calls) == 1 and not list(dest.iterdir())


def test_replaced_directory_and_symlink_refuse(session, tmp_path):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'bytes')
    renamed = dest.with_name('moved'); dest.rename(renamed); dest.mkdir()
    with pytest.raises(ValueError, match='identity'): store.apply(policy, gen, ref)
    dest.rmdir(); dest.symlink_to(renamed, target_is_directory=True)
    with pytest.raises(OSError): store.apply(policy, gen, ref)
    assert not list(renamed.iterdir())


def test_preexisting_collision_remains_pending(session, tmp_path):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'bytes')
    (dest/'00000001.SAV').write_bytes(b'original')
    with pytest.raises(FileExistsError): store.apply(policy, gen, ref)
    assert (dest/'00000001.SAV').read_bytes() == b'original'
    assert store.apply(policy, gen, ref)['outcome'] == 'needs-reconciliation'


def test_completion_receipt_failure_leaves_published_bytes_and_no_replay(session, tmp_path, monkeypatch):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'published')
    original = store._put
    def fail_complete(kind, doc):
        if doc.get('action') == 'complete': raise OSError('journal unavailable')
        return original(kind, doc)
    monkeypatch.setattr(store, '_put', fail_complete)
    with pytest.raises(OSError) as error: store.apply(policy, gen, ref)
    assert error.value.result['outcome'] == 'needs-reconciliation'
    assert error.value.result['export']['durable'] is True
    assert error.value.result['export']['sha256'] == hashlib.sha256(b'published').hexdigest()
    assert (dest/'00000001.SAV').read_bytes() == b'published'
    assert KeepPolicyStore(debug).apply(policy, gen, ref)['outcome'] == 'needs-reconciliation'
    assert len(list(dest.iterdir())) == 1


def test_caller_transaction_refused_before_reservation(session, tmp_path):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'data')
    with debug.project.transaction(True):
        with pytest.raises(ValueError, match='transaction'): store.apply(policy, gen, ref)
    assert store.status(policy)['reservations'] == 0 and not list(dest.iterdir())


def test_forged_provenance_field_rejected(session, tmp_path):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'data')
    row = debug.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(ref['artifact'],)).fetchone()
    doc = json.loads(bytes(row['data'])); doc['observer_token'] = 'different'
    bad = debug._artifact('bad.json', PROVENANCE_KIND, json.dumps(doc).encode(), {})
    with pytest.raises(ValueError, match='provenance|Provenance|misbound'):
        store.apply(policy, gen, dict(artifact=bad['artifact'], sha256=bad['sha256']))
    assert store.status(policy)['reservations'] == 0 and not list(dest.iterdir())


@pytest.mark.parametrize('change', ['invalid', 'missing_flush', 'payload', 'order', 'short_write'])
def test_synthetic_native_proof_tampering_refuses_before_reservation(session,tmp_path,change):
    debug, store, policy, base, dest = setup(session, tmp_path)
    gen, ref = proof(debug, base, b'data')
    row = debug.project.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(ref['artifact'],)).fetchone()
    doc = json.loads(bytes(row['data'])); native=doc['native']
    if change == 'invalid': native['valid']=False
    elif change == 'missing_flush': native['flush-seen']=False
    elif change == 'payload': native['payload-hex']=b'fake'.hex()
    elif change == 'order': native['events'][1]['function']=0x3e
    else: native['events'][1]['accepted']=1
    bad=debug._artifact('bad-native.json',PROVENANCE_KIND,json.dumps(doc).encode(),{})
    with pytest.raises(ValueError): store.apply(policy,gen,dict(artifact=bad['artifact'],sha256=bad['sha256']))
    assert store.status(policy)['reservations']==0 and not list(dest.iterdir())


def test_directory_swap_between_check_and_export_refuses(session,tmp_path,monkeypatch):
    debug, store, policy, base, dest = setup(session,tmp_path)
    gen, ref = proof(debug,base,b'data')
    original = store.workspace.export_file
    moved = dest.with_name('original-directory')
    def swap_then_export(*args,**kwargs):
        dest.rename(moved)
        dest.mkdir()
        return original(*args,**kwargs)
    monkeypatch.setattr(store.workspace,'export_file',swap_then_export)
    with pytest.raises(ValueError,match='identity') as error:
        store.apply(policy,gen,ref)
    assert error.value.result['outcome']=='needs-reconciliation'
    assert not list(dest.iterdir()) and not list(moved.iterdir())
    assert store.status(policy)['pending']==1
