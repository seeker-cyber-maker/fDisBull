"""PE32 state-replacement metadata at the stopped RPC boundary, without a VM."""
from copy import deepcopy
import hashlib
import json
import threading
from types import SimpleNamespace

from fdisbull.project import Project
from fdisbull.wine_debugger import PEDebugSession
from fdisbull import wine_rpc, wine_state
from test_wine_pe32 import context32, pe32_relocated


def test_pe32_state_replacement_rebinds_actual_profile_and_persisted_capabilities(tmp_path, monkeypatch):
    source = tmp_path / 'authored.exe'
    source.write_bytes(pe32_relocated())
    inputs = {}
    for name in ('qemu', 'kernel', 'initramfs'):
        path = tmp_path / name
        data = ('authored input ' + name).encode()
        path.write_bytes(data)
        inputs[name] = dict(path=str(path), sha256=hashlib.sha256(data).hexdigest())
    context = dict(context32(), architecture='x86-32', bits=32, cs='0x23')
    replacements = []

    class StoppedRPC:
        """Replace only machine restoration; retain real host readback/mapping."""
        def __init__(self, *paths, restore=None, memory_mib=4096):
            self.inputs = deepcopy(inputs)
            # A fresh transport has no selected-process profile yet.
            self.capabilities = dict(architecture='x86-64', bits=64, keyboard=True)
            self.lock = threading.RLock()
            self.vm = None
            self.process = SimpleNamespace(pid=2468)
            self.closed = False
            self.restore = restore
            self.memory_mib = memory_mib
            if restore is not None:
                replacements.append(self)

        def call(self, method, params=None, timeout_ms=30000):
            assert method == 'registers'
            return deepcopy(context)

        def close(self):
            self.closed = True

    with Project.create(tmp_path / 'project.fdb', source) as project:
        session = PEDebugSession.__new__(PEDebugSession)
        session.project = project
        session.version = project.version(1)
        session.bits = 32
        session.closed = False
        session.run_id = 'pe32-state-replacement'
        session.game_dir = tmp_path
        session.static_base = session.runtime_base = 0x400000
        session.delta = 0
        session.regions = project.regions(1)
        session.mode_id = 0
        session._frame = None
        session.rpc = original = StoppedRPC()
        original.capabilities.update(architecture='x86-32', bits=32)
        session.metadata = dict(runtime_profile='pe32-win32-debug-1', bits=32,
            memory_mib=8192, runtime_inputs=deepcopy(inputs), files=[],
            source_sha256=project.meta['source_sha256'],
            version_sha256=session.version['sha256'], runtime_image_base='0x400000',
            capabilities=original.capabilities)
        session._windows_ui_initialize(window=False)
        host = dict(breakpoints={}, watchpoints={}, active=[], layer_hashes={},
            generation=0, scratch=None, _ram_base={}, _ram_applied={},
            _execution={}, _execute_guards={})
        document = dict(machine_size=123, metadata={**deepcopy(session.metadata),
            'registers': deepcopy(context)}, host=host)
        checkpoint = tmp_path / 'stopped.mig.gz'
        checkpoint.write_bytes(b'restore edge substituted by StoppedRPC')
        monkeypatch.setattr(wine_state, 'get_state',
            lambda *args: ({'sha256': 'a' * 64}, document, checkpoint))
        monkeypatch.setattr(wine_rpc, 'WineQemuRPC', StoppedRPC)
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (session.run_id, 1, 'now', None, 'stopped', json.dumps(session.metadata)))

        result = session.load_state('saved-pe32')

        assert original.closed and len(replacements) == 1
        assert session.rpc is replacements[0]
        assert session.rpc.restore == checkpoint and session.rpc.memory_mib == 8192
        assert session.rpc.capabilities['architecture'] == 'x86-32'
        assert session.rpc.capabilities['bits'] == 32
        assert session.metadata['capabilities'] is session.rpc.capabilities
        assert session.metadata['runtime_profile'] == 'pe32-win32-debug-1'
        persisted = json.loads(project.db.execute(
            'SELECT metadata FROM debug_runs WHERE id=?', (session.run_id,)).fetchone()[0])
        assert persisted['capabilities']['architecture'] == 'x86-32'
        assert persisted['capabilities']['bits'] == 32
        assert result['registers']['cpu_mode'] == 'protected32'
        assert result['registers']['eip'] == context['eip']
        assert 'rip' not in result['registers']
