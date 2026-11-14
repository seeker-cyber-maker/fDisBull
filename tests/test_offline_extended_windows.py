"""Contract tests only; native execution is a separately admitted qualification."""
import importlib.util
from pathlib import Path

import pytest
from offline_windows_oracles import win16_profile
from test_offline_windows_oracles import sample_ne

SPEC = importlib.util.spec_from_file_location('offline_extended_verify', Path(__file__).parents[1] / 'scripts/verify_chat_offline_kit.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def test_profile_and_roles_fail_closed(tmp_path):
    fixture = tmp_path / 'oracle.exe'; fixture.write_bytes(sample_ne())
    profile = win16_profile(sample_ne())
    assert verify.validate_win16_profile(fixture, profile)['counter'] == 'ne:2:0x25'
    forged = dict(profile, counter='ne:2:0x26')
    with pytest.raises(ValueError, match='differs'):
        verify.validate_win16_profile(fixture, forged)
    fixture.write_bytes(sample_ne() + b'x')
    with pytest.raises(ValueError, match='identity'):
        verify.validate_win16_profile(fixture, profile)
    roles = {name: [tmp_path / name] for name in ('pe32_fixture', 'win16_fixture', 'win16_profile')}
    assert verify.extended_windows_roles({'profile': 'shared', 'windows_acceptance': 'pe64-pe32-win16'}, roles)
    with pytest.raises(ValueError, match='without acceptance'):
        verify.extended_windows_roles({'profile': 'shared'}, roles)
    with pytest.raises(ValueError, match='Exactly one'):
        verify.extended_windows_roles({'profile': 'shared', 'windows_acceptance': 'pe64-pe32-win16'}, {**roles, 'win16_profile': []})
    with pytest.raises(ValueError, match='incompatible'):
        verify.extended_windows_roles({'profile': 'prebuilt', 'windows_acceptance': 'pe64-pe32-win16'}, roles)


def test_public_api_sequence_restores_then_rebinds(monkeypatch, tmp_path):
    """A scripted boundary checks orchestration, not guest behavior."""
    import fdisbull.project
    calls = []
    class Debug:
        def __init__(self, restored):
            self.value = 7; self.key = False
            self.metadata = {'original_entry_verified': True}
            calls.append(('launch', restored))
        def __enter__(self): return self
        def __exit__(self, *args): calls.append(('close',))
        def breakpoint(self, address): calls.append(('breakpoint', address)); return {'bytes_verified': True}
        def run(self, **kwargs):
            if self.key: self.value = 8; self.key = False
            return {'outcome': 'breakpoint'}
        def memory(self, address, **kwargs): return {'hex': f'{self.value:02x}'}
        def screenshot(self, name, **kwargs): return {'sha256': 'a'*64, 'metadata': {'width': 320, 'height': 200}}
        def frame_probe(self, points): return {'samples': [{'rgb': [224,160,32] if self.value == 7 else [32,192,96]}]}
        def trace(self, *args, **kwargs): return {'metadata': {'complete': True, 'event_count': 1}}
        def save_state(self, *args): calls.append(('save',)); return {'artifact': 'saved'}
        def write_memory(self, address, value, **kwargs):
            assert kwargs['expected_hex'] == f'{self.value:02x}'
            self.value = int(value, 16); calls.append(('edit', self.value))
        def load_state(self, artifact):
            assert artifact == 'saved'; self.value = 7; calls.append(('restore',)); return {'state': 'stopped'}
        def keyboard_press(self, key, **kwargs): assert key == 'right'; self.key = True; calls.append(('input',)); return {'queued': 2}
    class Project:
        def __init__(self, path): pass
        @classmethod
        def create(cls, path, fixture, **kwargs): return cls(path)
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def analyze(self, **kwargs): pass
        def debugger(self, *args, **kwargs): return Debug(kwargs.get('state'))
    monkeypatch.setattr(fdisbull.project, 'Project', Project)
    fixture = tmp_path / 'ORACLE.EXE'; fixture.write_bytes(sample_ne())
    result = verify.verify_win16_authored(tmp_path / 'private.fdb', fixture, 'qemu', 'kernel', 'initramfs', win16_profile(sample_ne()))
    assert result['status'] == 'passed'
    assert calls == [('launch', None), ('breakpoint', 'ne:1:0x10'), ('save',), ('edit', 8), ('restore',), ('input',), ('close',), ('launch', 'saved'), ('input',), ('close',)]
