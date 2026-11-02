"""Transport/CLI checks use no GUI, target or native permission changes."""
import json
from pathlib import Path
import subprocess

import pytest

from fdisbull import macos_capture as module
from fdisbull.cli import main, respond


def backend(monkeypatch):
    monkeypatch.setattr(module, 'prepare_helper', lambda **kwargs:Path(__file__))
    return module.NativeCapture()


def test_native_refusal_is_preserved_even_when_helper_exits_nonzero(monkeypatch):
    native = backend(monkeypatch)
    monkeypatch.setattr(module, '_run', lambda *args, **kwargs:
        b'{"ok":false,"error":{"message":"menu state unknown"}}')
    with pytest.raises(ValueError, match='menu state unknown'):
        native('snapshot', bundle_id='test.fixture')


@pytest.mark.parametrize('response', [b'not JSON', b'[]', b'{"ok":true}', b'{"ok":true,"result":[]}'])
def test_malformed_native_replies_are_refused(monkeypatch, response):
    native = backend(monkeypatch)
    monkeypatch.setattr(module, '_run', lambda *args, **kwargs:response)
    with pytest.raises(ValueError):
        native('snapshot', bundle_id='test.fixture')


def test_transport_reaps_child_before_interrupt_propagates(monkeypatch):
    class Process:
        returncode = None
        calls = []
        def communicate(self, *args, **kwargs):
            self.calls.append('communicate')
            if len(self.calls) == 1:
                raise KeyboardInterrupt()
            return b'', b''
        def kill(self):
            self.calls.append('kill')
    process = Process()
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs:process)
    with pytest.raises(KeyboardInterrupt):
        module._run(['fixture'])
    assert process.calls == ['communicate','kill','communicate']


def test_snapshot_is_projectless_and_cli_routes_same_request(monkeypatch, capsys):
    calls = []
    def native(operation, **kwargs):
        calls.append((operation,kwargs))
        return {'target':{'running':False}, 'menu':{'open':False}}
    monkeypatch.setattr(module, 'NativeCapture', lambda:native)
    reply = respond({'method':'macos-snapshot','params':{'bundle_id':'test.fixture'}},
                    default_project='/must/not/be/opened')
    assert reply['ok']
    assert main(['macos-snapshot','test.fixture']) == 0
    assert json.loads(capsys.readouterr().out)['result'] == reply['result']
    assert calls == [('snapshot',{'bundle_id':'test.fixture'})] * 2


def test_no_tool_preparation_on_non_macos(monkeypatch):
    monkeypatch.setattr(module.platform, 'system', lambda:'Linux')
    monkeypatch.setattr(module, '_run', lambda *args, **kwargs:pytest.fail('tool launched'))
    with pytest.raises(ValueError, match='macOS'):
        module.prepare_helper()
