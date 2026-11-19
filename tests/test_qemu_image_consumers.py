"""Cold Wine and DOS bridge callers retain executing-image admission gates."""
from copy import deepcopy
import hashlib
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from fdisbull import qemu_image
from fdisbull.project import Project
from fdisbull.wine_rpc import WineQemuRPC
from test_wine_pe32 import pe32_relocated


def load_snapshot(stem):
    return __import__('fdisbull.' + stem, fromlist=[stem])


class PassedIdentityBoundary(Exception):
    pass


class ReachedGuestWithoutAdmission(Exception):
    pass


@pytest.mark.parametrize('qemu_transport', [True, False])
def test_wine_cold_session_forwards_saved_executed_image_before_transport(tmp_path, monkeypatch, qemu_transport):
    wine = load_snapshot('wine_debugger')
    game = tmp_path / 'game'
    game.mkdir()
    source = game / 'authored.exe'
    source.write_bytes(pe32_relocated())
    inputs = {}
    for key in ('qemu', 'kernel', 'initramfs'):
        path = tmp_path / key
        path.write_bytes(('authored ' + key).encode())
        inputs[key] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    inputs['qemu_image'] = dict(format=qemu_image.FORMAT, path='/private/qualified-image',
        sha256='a' * 64, size=123, version='10.0.13')
    uploads = [dict(path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest())]
    saved = dict(metadata=dict(runtime_inputs=deepcopy(inputs), files=uploads, memory_mib=4096))
    native = tmp_path / 'private-native-state'
    native.write_bytes(b'authored checkpoint boundary only')
    monkeypatch.setattr('fdisbull.guest_assets.uploads', lambda *a, **kw: deepcopy(uploads))
    monkeypatch.setattr(wine, 'get_state', lambda *a: ({}, saved, native))
    calls = []
    class QualifiedTransport(WineQemuRPC if qemu_transport else object):
        def __init__(self, *args, restore=None, **kwargs):
            expected_runtime_inputs = kwargs.get('expected_runtime_inputs')
            calls.append(dict(expected=expected_runtime_inputs, restore=restore))
            # Exercise exactly the newly required transport admission, without
            # substituting an accepting factory or starting a native owner.
            if qemu_transport:
                qemu_image.require_record(expected_runtime_inputs)
                assert expected_runtime_inputs == inputs
            else:
                assert 'expected_runtime_inputs' not in kwargs
            assert restore == native
            raise PassedIdentityBoundary('qualified producer reached cold transport')
    class Session(wine.PEDebugSession):
        rpc_type = QualifiedTransport
    with Project.create(tmp_path / 'project.fdb', source) as project:
        with pytest.raises(PassedIdentityBoundary):
            Session(project, inputs['qemu']['path'], game, kernel=inputs['kernel']['path'],
                    initramfs=inputs['initramfs']['path'], state='qualified-state')
    assert len(calls) == 1


def bridge_session():
    module = load_snapshot('dos_qemu')
    session = module.DOSQemuSession.__new__(module.DOSQemuSession)
    inputs = dict(qemu=dict(sha256='b' * 64, version='QEMU emulator version 10.0.13'),
        qemu_image=dict(format=qemu_image.FORMAT, path='/private/qualified-image',
                        size=123, sha256='a' * 64, version='10.0.13'))
    session.rpc = SimpleNamespace(vm=SimpleNamespace(inputs=inputs), inputs=inputs,
        lock=threading.RLock(), capabilities=dict(save_states=True, frame_timeline=True))
    session.metadata = dict(runtime_inputs=deepcopy(inputs))
    session.closed = False
    session._disk_manifest = lambda: []
    session.close = lambda: setattr(session, 'closed', True)
    calls = []
    def call(method, *args, **kwargs):
        calls.append(method)
        raise ReachedGuestWithoutAdmission(method)
    session.call = call
    return session, calls


def checkpoint(session, *, legacy=False):
    data = b'authored cached native payload'
    metadata = dict(session.metadata, disk_manifest=[], registers=dict(cpu_mode='real'), code_layers={})
    if legacy:
        metadata.pop('runtime_inputs')
    return dict(data=data, sha256=hashlib.sha256(data).hexdigest(), metadata=metadata)


@pytest.mark.parametrize('operation', ['capture', 'restore', 'public-save', 'public-load'])
def test_dos_in_qemu_timeline_native_boundary_verifies_live_image(monkeypatch, operation):
    session, calls = bridge_session()
    def refused(vm, *args):
        assert vm is session.rpc.vm
        raise PassedIdentityBoundary('live image refusal before native call')
    monkeypatch.setattr(qemu_image, 'verify', refused)
    with pytest.raises(PassedIdentityBoundary):
        if operation == 'capture':
            session._capture_native_checkpoint()
        elif operation == 'restore':
            session._restore_native_checkpoint(checkpoint(session))
        elif operation == 'public-save':
            session.save_state()
        else:
            import json
            item=checkpoint(session)
            row=dict(kind='state',version=1,data=item['data'],sha256=item['sha256'],
                     metadata=json.dumps(item['metadata']))
            session.version={'id':1}
            session.project=SimpleNamespace(db=SimpleNamespace(execute=lambda *a:
                SimpleNamespace(fetchone=lambda:row)))
            session.load_state('authored-state')
    assert calls == []


def test_dos_in_qemu_timeline_legacy_payload_refuses_before_guest_import(monkeypatch):
    session, calls = bridge_session()
    monkeypatch.setattr(qemu_image, 'verify', lambda *args: None)
    with pytest.raises(qemu_image.ProducerMismatch, match='legacy producer is unqualified'):
        session._restore_native_checkpoint(checkpoint(session, legacy=True))
    assert calls == []


def test_dos_bridge_timeline_identity_pins_current_portable_producer():
    session,calls=bridge_session()
    session.run_id='authored-run';session.version={'id':1}
    before=session._timeline_identity()
    session.rpc.inputs['qemu_image']['sha256']='c'*64
    after=session._timeline_identity()
    assert before['runtime_inputs']['qemu_image']['sha256']=='a'*64
    assert before != after and calls==[]
    assert 'path' not in after['runtime_inputs']['qemu_image']


def test_dos_bridge_changed_saved_producer_refuses_without_guest_or_owner_loss(monkeypatch):
    session,calls=bridge_session()
    payload=checkpoint(session)
    payload['metadata']=deepcopy(payload['metadata'])
    payload['metadata']['runtime_inputs']['qemu_image']['sha256']='c'*64
    monkeypatch.setattr(qemu_image,'verify',lambda *args:None)
    with pytest.raises(qemu_image.ProducerMismatch,match='producer identity differs'):
        session._restore_native_checkpoint(payload)
    assert calls==[] and not session.closed


def test_ordinary_dosbox_capture_keeps_its_existing_native_admission(monkeypatch):
    from fdisbull.debugger import DebugSession
    bridge,calls=bridge_session()
    session=DebugSession.__new__(DebugSession)
    session.__dict__.update(vars(bridge))
    monkeypatch.setattr(qemu_image,'verify',lambda *a:pytest.fail('QEMU admission on ordinary DOSBox'))
    with pytest.raises(ReachedGuestWithoutAdmission,match='input.mouse.state'):
        session._capture_native_checkpoint()
    assert calls==['input.mouse.state']
