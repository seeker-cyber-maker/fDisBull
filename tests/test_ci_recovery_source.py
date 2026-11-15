import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_source', root / 'scripts/ci/recovery_source.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
OLD, NEW = 'a' * 40, 'b' * 40
REF = 'codex/repair'


class Runner:
    def __init__(self, repo):
        self.repo = repo
        self.calls = []
        self.sha = OLD
        self.changed = False
        self.staged = False
        self.worker_mode = 'pass'
        self.bad_remote = False
    def __call__(self, argv, *, cwd, env, input_bytes, timeout):
        self.calls.append(argv)
        code, out = 0, ''
        if argv[0] == 'git':
            args = argv[1:]
            if args == ['rev-parse', 'HEAD']: out = self.sha
            elif args == ['branch', '--show-current']: out = REF
            elif args == ['status', '--porcelain', '--untracked-files=all']: out = ' M ' + module.ALLOWED if self.changed else ''
            elif args[:2] == ['remote', 'get-url']:
                out = 'unexpected' if self.bad_remote else module.REMOTES[args[-1]]
            elif args == ['diff', '--cached', '--name-only']: out = module.ALLOWED if self.staged else ''
            elif args[0] == 'add': self.staged = True
            elif args[0] == 'commit': self.sha = NEW; self.changed = self.staged = False
            elif args[0] == 'ls-remote': out = self.sha + '\trefs/heads/' + REF
            elif args[0] != 'push': raise AssertionError(args)
        elif argv[0] == module.CODEX:
            assert timeout == 300
            assert 'OPENAI_API_KEY' not in env
            self.changed = True
            (self.repo / module.ALLOWED).write_text('fixed source\n')
            Path(argv[argv.index('--output-last-message') + 1]).write_text('{"summary":"repaired"}')
            out = json.dumps({'type': 'turn.completed', 'command': 'printenv', 'token': 'secret-value'}) + '\n' if self.worker_mode != 'no_turn' else '{}\n'
            if self.worker_mode == 'timeout':
                return {'returncode': -9, 'stdout': out.encode(), 'stderr': b'bounded', 'timed_out': True, 'overflow': False}
            if self.worker_mode == 'probe_changed': (self.repo / module.PROBE).write_text('changed test')
        else:
            assert argv[1:] == [module.PROBE, '--source-check']
            passed = self.changed
            out = json.dumps({'reason': 'incomplete_capture_accepted', 'passed': passed})
            code = 0 if passed else 1
        return {'returncode': code, 'stdout': out.encode(), 'stderr': b'', 'timed_out': False, 'overflow': False}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    (repo / 'scripts/ci').mkdir(parents=True)
    (repo / module.PROBE).write_text('frozen source check\n')
    (repo / module.ALLOWED).write_text('broken source\n')
    monkeypatch.setenv('OPENAI_API_KEY', 'secret-value')
    runner = Runner(repo)
    worker = module.SourceRepair(repo, tmp_path / 'private', REF, runner=runner)
    backend = SimpleNamespace(_action_receipt=lambda key, value: '/var/lib/fdisbull-ci/control/recovery/x/receipt.json')
    payload = {'target': {'source_sha': OLD}}
    return worker, runner, backend, payload


def test_worker_proves_repair_commits_pushes_and_reconciles(setup):
    worker, runner, backend, payload = setup
    result = worker('incident:source', payload, backend)
    assert result['source_sha'] == NEW and result['status'] == 'completed'
    assert worker.reconcile('incident:source', payload, backend) == result
    assert sum(call[0] == module.CODEX for call in runner.calls) == 1
    pushes = [call for call in runner.calls if call[:2] == ['git', 'push']]
    assert pushes == [['git', 'push', 'local-hub', 'HEAD:refs/heads/' + REF],
                      ['git', 'push', '--push-option=ci.skip', 'gitlab', 'HEAD:refs/heads/' + REF]]
    directory = worker._directory('incident:source')
    assert json.loads((directory / 'exit.json').read_text())['returncode'] == 0
    assert (directory / 'stdout.jsonl').is_file() and (directory / 'before.json').is_file()
    assert 'secret-value' not in (directory / 'stdout.jsonl').read_text()
    assert 'printenv' not in (directory / 'stdout.jsonl').read_text()


@pytest.mark.parametrize('mode', ['timeout', 'no_turn', 'probe_changed'])
def test_worker_failures_never_commit_or_push_and_do_not_relaunch(setup, mode):
    worker, runner, backend, payload = setup
    runner.worker_mode = mode
    with pytest.raises(RuntimeError): worker('incident:source', payload, backend)
    assert worker.reconcile('incident:source', payload, backend) is None
    with pytest.raises(FileExistsError): worker('incident:source', payload, backend)
    assert not any(call[:2] in (['git', 'commit'], ['git', 'push']) for call in runner.calls)
    assert sum(call[0] == module.CODEX for call in runner.calls) == 1
    if mode == 'timeout':
        exit_receipt = json.loads((worker._directory('incident:source') / 'exit.json').read_text())
        assert exit_receipt['timed_out'] is True
        assert json.loads((worker._directory('incident:source') / 'stderr.json').read_text())['bytes'] == 7


def test_remote_mismatch_stops_before_worker(setup):
    worker, runner, backend, payload = setup
    runner.bad_remote = True
    with pytest.raises(RuntimeError): worker('incident:source', payload, backend)
    assert not any(call[0] == module.CODEX for call in runner.calls)


def test_reconcile_rejects_changed_remote_readback(setup):
    worker, runner, backend, payload = setup
    worker('incident:source', payload, backend)
    runner.bad_remote = True
    assert worker.reconcile('incident:source', payload, backend) is None
    assert sum(call[0] == module.CODEX for call in runner.calls) == 1
