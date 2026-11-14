"""Disabled-by-default, finite source-repair bridge for an authenticated VPS.

Authority for closed/canonical CI evidence is the authenticated root VPS
verifier; hashes below bind transferred bytes and do not prove closure. The
Mac separately validates immutable source Git objects and a local reproducer.
No raw provider trace is accepted or sent to the model. No branch publication
is available without an explicitly installed, readback-verifying publisher.
"""
import ast
import base64
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
from pathlib import Path, PurePosixPath
import re
import signal
import sys
import xml.etree.ElementTree as ET


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(path))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


identity = _load('production_source_identity', 'recovery_production.py')
source = _load('production_source_worker', 'recovery_source_production.py')
legacy = _load('production_source_runner', 'recovery_source.py')
provider = _load('production_source_provider', 'production_transport.py')

REPO = Path('/Volumes/CODEX/Codex_Projects/fDisBull')
WORKTREES = Path('/Volumes/CACHE/fdisbull-ci-builds/source-repair-worktrees')
CACHE_UUID = 'DB098A4B-7968-418F-8B20-61597F42392A'
STATE = Path('/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-source-state')
HELPER = '/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge/production_source_transport.py'
ACTIVATION = Path('/Volumes/CODEX/Codex_Projects/fDisBull-targets-private/production-ci-bridge/source-activation.json')
STORAGE = '/Users/tiga/.codex/bin/storage_admit.py'
SOURCE_PYTHON = '/Users/tiga/miniconda/bin/python3'
SOURCE_PYTHON_VERSION = '3.13.13'
SOURCE_PYTHON_SHA256 = '0f5374bca527c5a5e958ee94e03e55816a368533286e6315b8bf013da622fc61'
PINNED_INTERPRETER = {'path': SOURCE_PYTHON, 'version': SOURCE_PYTHON_VERSION, 'sha256': SOURCE_PYTHON_SHA256}
JUNIT = 'artifacts/ordinary/tests.xml'
MAX_JUNIT = 16 * 1024 * 1024
MAX_INVENTORY = 1024 * 1024
MAX_DOC = 32 * 1024 * 1024
MAX_BLOB = 2 * 1024 * 1024


def _raw(value, maximum):
    if not isinstance(value, str) or len(value) > 4 * ((maximum + 2) // 3): raise ValueError('encoded evidence exceeds bound')
    try: data = base64.b64decode(value, validate=True)
    except (ValueError, TypeError): raise ValueError('invalid encoded evidence') from None
    if not data or len(data) > maximum: raise ValueError('evidence size invalid')
    return data


def _json(data):
    value = json.loads(data)
    if not isinstance(value, dict): raise ValueError('evidence object required')
    return value


def _hash(data): return hashlib.sha256(data).hexdigest()


def _clean_env(env):
    markers = ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTH', 'PROXY')
    cleaned = {k: v for k, v in env.items() if not any(x in k.upper() for x in markers)
               and not k.startswith(('GIT_', 'GH_', 'GLAB_', 'SSL_', 'CURL_'))
               and k not in ('SSH_ASKPASS', 'GH_CONFIG_DIR', 'GLAB_CONFIG_DIR', 'REQUESTS_CA_BUNDLE')}
    cleaned.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                   GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='core.hooksPath', GIT_CONFIG_VALUE_0='/dev/null',
                   GIT_CONFIG_KEY_1='core.fsmonitor', GIT_CONFIG_VALUE_1='false')
    return cleaned


def current_source_interpreter():
    """Bind source qualification to the already-installed Python environment."""
    executable = Path(SOURCE_PYTHON).resolve(strict=True)
    if Path(sys.executable).resolve(strict=True) != executable or platform.python_version() != SOURCE_PYTHON_VERSION:
        raise RuntimeError('source interpreter identity mismatch')
    with executable.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != SOURCE_PYTHON_SHA256:
        raise RuntimeError('source interpreter hash mismatch')
    for module in ('pytest', 'capstone', 'iced_x86', 'lief'):
        if importlib.util.find_spec(module) is None:
            raise RuntimeError('source interpreter dependency unavailable')
    return dict(PINNED_INTERPRETER)


def validate_bundle(bundle):
    keys = {'target', 'evidence_receipt_path', 'evidence_receipt_sha256', 'evidence_receipt_base64',
            'job_base64', 'inventory_base64', 'junit_path', 'junit_base64'}
    if not isinstance(bundle, dict) or set(bundle) != keys: raise ValueError('invalid source evidence bundle')
    target = identity.target(bundle['target'])
    if target['provider'] not in ('github', 'gitlab') or target['job_name'] not in ('qualification', 'test-and-package'):
        raise ValueError('only ordinary hosted failure supported')
    if (target['provider'], target['job_name']) not in (('github', 'qualification'), ('gitlab', 'test-and-package')):
        raise ValueError('ordinary job identity mismatch')
    raw_path = bundle['evidence_receipt_path']
    if (not isinstance(raw_path, str) or not raw_path.startswith('/var/lib/fdisbull-ci/')
            or '..' in PurePosixPath(raw_path).parts or str(PurePosixPath(raw_path)) != raw_path):
        raise ValueError('invalid private evidence receipt path')
    receipt_bytes = _raw(bundle['evidence_receipt_base64'], 65536)
    if not isinstance(bundle['evidence_receipt_sha256'], str) or _hash(receipt_bytes) != bundle['evidence_receipt_sha256']:
        raise ValueError('evidence receipt hash mismatch')
    receipt = _json(receipt_bytes)
    if (receipt.get('schema') != 'fdisbull-production-evidence-1' or receipt.get('target') != target
            or receipt.get('job_status') != 'failed'):
        raise ValueError('canonical failed evidence mismatch')
    job_bytes = _raw(bundle['job_base64'], 65536)
    inventory_bytes = _raw(bundle['inventory_base64'], MAX_INVENTORY)
    junit = _raw(bundle['junit_base64'], MAX_JUNIT)
    if (_hash(job_bytes) != receipt.get('export_job_sha256') or _hash(inventory_bytes) != receipt.get('inventory_sha256')
            or bundle['junit_path'] != JUNIT):
        raise ValueError('closed evidence binding mismatch')
    job = _json(job_bytes)
    if target['provider'] == 'github':
        if (job.get('schema') != 'fdisbull-production-job-export-1' or job.get('job_status') != 'failed'
                or any(str(job.get(k)) != str(v) for k, v in target.items() if k != 'provider')):
            raise ValueError('job evidence identity mismatch')
    else:
        if (job.get('schema') != 'fdisbull-ovh-result-export-v1' or job.get('job_status') != 'failed'
                or str(job.get('pipeline_id')) != target['pipeline_id'] or str(job.get('job_id')) != target['job_id']
                or job.get('job_name') != target['job_name'] or job.get('source_commit') != target['source_sha']):
            raise ValueError('job evidence identity mismatch')
    if job.get('export_success') is not True: raise ValueError('unclosed job export')
    inventory = json.loads(inventory_bytes)
    if not isinstance(inventory, list) or len(inventory) > 4096: raise ValueError('invalid inventory')
    matches = [x for x in inventory if isinstance(x, dict) and x.get('path') == JUNIT]
    if (len(matches) != 1 or matches[0].get('sha256') != _hash(junit)
            or matches[0].get('size') != len(junit)):
        raise ValueError('JUnit not bound to closed inventory')
    event = _hash(json.dumps({'target': target, 'receipt_sha256': _hash(receipt_bytes),
                              'junit_sha256': _hash(junit)}, sort_keys=True, separators=(',', ':')).encode())
    return target, junit, event


def select_node(junit, tracked_tests):
    if b'<!DOCTYPE' in junit.upper() or b'<!ENTITY' in junit.upper(): raise ValueError('XML declarations refused')
    root = ET.fromstring(junit)
    if root.tag not in ('testsuites', 'testsuite'): raise ValueError('invalid JUnit')
    suites = [root] if root.tag == 'testsuite' else root.findall('testsuite')
    if len(suites) != 1 or suites[0].findall('.//testsuite'):
        raise ValueError('unsupported JUnit suite layout')
    suite = suites[0]
    cases = suite.findall('testcase')
    counts = {key: suite.get(key) for key in ('tests', 'failures', 'errors')}
    if (not cases or len(cases) > 200000 or any(not isinstance(x, str) or not x.isascii() or not x.isdecimal() for x in counts.values())
            or int(counts['tests']) != len(cases) or int(counts['failures']) != 1
            or int(counts['errors']) != 0 or root.findall('.//error')):
        raise ValueError('unsupported JUnit result')
    failed = [case for case in cases if case.findall('failure')]
    if len(failed) != 1 or len(failed[0].findall('failure')) != 1: raise ValueError('exactly one failed test required')
    case = failed[0]
    if case.findall('skipped'): raise ValueError('conflicting test outcome')
    name, classname = case.get('name'), case.get('classname')
    if (not isinstance(name, str) or not re.fullmatch(r'test_[A-Za-z0-9_]+', name)
            or not isinstance(classname, str) or len(classname) > 500):
        raise ValueError('parameterized or unsupported test node')
    candidates = []
    for path in tracked_tests:
        if not re.fullmatch(r'tests/[A-Za-z0-9_/-]+\.py', path): continue
        module = path[:-3].replace('/', '.')
        for prefix in (module, module.removeprefix('tests.')):
            if classname == prefix: candidates.append((path, None))
            elif classname.startswith(prefix + '.'):
                suffix = classname[len(prefix) + 1:]
                if re.fullmatch(r'Test[A-Za-z0-9_]+', suffix): candidates.append((path, suffix))
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) != 1: raise ValueError('test module mapping ambiguous')
    path, cls = candidates[0]
    return path + ('::' + cls if cls else '') + '::' + name


def direct_modules(test_source, tracked_sources):
    tree = ast.parse(test_source)
    paths = set(tracked_sources); selected = set()
    def add(module):
        if not module.startswith('fdisbull.'): return
        path = 'src/' + module.replace('.', '/') + '.py'
        if path in paths: selected.add(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names: add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module == 'fdisbull':
                for alias in node.names: add('fdisbull.' + alias.name)
            elif isinstance(node.module, str): add(node.module)
    result = sorted(selected)
    if not 1 <= len(result) <= 3: raise ValueError('direct source mapping unsupported')
    return result


def _cache_volume_ok(worktrees, *, root=Path('/Volumes/CACHE'), runner=None):
    """Read-only volume admission; the repair-worktree parent must pre-exist."""
    root,worktrees=Path(root),Path(worktrees)
    try:
        if (not os.path.ismount(root) or root.is_symlink() or not worktrees.is_dir()
                or root not in worktrees.parents or any(p.is_symlink() for p in (worktrees,*worktrees.parents))
                or worktrees.stat().st_dev!=root.stat().st_dev):return False
        result=(runner or legacy.run_command)(['/usr/sbin/diskutil','info','-plist',str(root)],cwd='/',timeout=12)
        if (not isinstance(result,dict) or result.get('returncode')!=0 or result.get('timed_out') is not False
                or result.get('overflow') is not False or not isinstance(result.get('stdout'),bytes)
                or len(result['stdout'])>65536):return False
        info=plistlib.loads(result['stdout'])
        return info.get('VolumeUUID')==CACHE_UUID and info.get('MountPoint')==str(root) and info.get('Internal') is False
    except (OSError,ValueError,TypeError,KeyError):return False


class SourceServer:
    def __init__(self, *, repo=REPO, worktrees=WORKTREES, state=STATE, runner=None,
                 guard=None, selection_policy_approved=False, publisher=None, worker_class=source.ProductionSourceRepair,
                 interpreter_check=current_source_interpreter):
        self.repo, self.worktrees, self.state = Path(repo), Path(worktrees), Path(state)
        self._runner = runner or legacy.run_command
        self.guard = guard or self._guard
        self.approved = selection_policy_approved is True
        self.publisher, self.worker_class = publisher, worker_class
        self.interpreter_check = interpreter_check

    def runner(self, argv, *, cwd, env=None, input_bytes=None, timeout=30):
        base = os.environ if env is None else env
        return self._runner(argv, cwd=cwd, env=_clean_env(base), input_bytes=input_bytes, timeout=timeout)

    def _guard(self):
        # Reuse the installed bridge's exact UUID/state/anchor validation.
        if platform.system() != 'Darwin': raise RuntimeError('Mac source host required')
        provider.ProviderBridge(provider.STATE_DIR)._ensure()
        for path in (self.repo, self.state):
            if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_dir(): raise RuntimeError('source root unavailable')
            if path.stat().st_dev != Path('/Volumes/CODEX').stat().st_dev: raise RuntimeError('source root off CODEX')
        if not _cache_volume_ok(self.worktrees):raise RuntimeError('pinned CACHE worktree parent unavailable')
        if self.state.stat().st_uid != os.getuid() or self.state.stat().st_mode & 0o077:
            raise RuntimeError('private source state unavailable')

    def _run(self, args, cwd, timeout=30):
        r = self.runner(args, cwd=str(cwd), env=source._credential_free_environment(), input_bytes=None, timeout=timeout)
        if (not isinstance(r, dict) or r.get('timed_out') is not False or r.get('overflow') is not False
                or r.get('returncode') != 0 or not isinstance(r.get('stdout'), bytes)
                or len(r['stdout']) > MAX_BLOB or not isinstance(r.get('stderr'), bytes)):
            raise RuntimeError('bounded command unavailable')
        return r['stdout']

    def _directory(self, event):
        if not isinstance(event, str) or not re.fullmatch(r'[0-9a-f]{64}', event): raise ValueError('invalid event')
        return self.state / event

    def _git(self, *args): return self._run(['git', *args], self.repo)
    def _blob(self, sha, path): return self._git('show', sha + ':' + path)

    def prepare(self, target, bundle):
        if not self.approved: raise RuntimeError('source selection policy not approved')
        self.guard()
        if self.interpreter_check() != PINNED_INTERPRETER: raise RuntimeError('source interpreter unavailable')
        validated, junit, event = validate_bundle(bundle)
        if identity.target(target) != validated: raise ValueError('target mismatch')
        directory = self._directory(event)
        directory.mkdir(mode=0o700, exist_ok=False)
        legacy._json(directory/'intent.json', {'target': validated, 'event_key': event,
                                              'evidence_receipt_sha256': bundle['evidence_receipt_sha256']})
        sha = validated['source_sha']
        self._git('cat-file', '-e', sha + '^{commit}')
        tracked = self._git('ls-tree', '-r', '--name-only', sha).decode('utf-8', 'strict').splitlines()
        node = select_node(junit, [x for x in tracked if x.startswith('tests/')])
        test = node.split('::')[0]; test_bytes = self._blob(sha, test)
        allowed = direct_modules(test_bytes, [x for x in tracked if x.startswith('src/fdisbull/')])
        branch = 'codex/ci-repair-' + event
        worktree = self.worktrees / ('ci-repair-' + event)
        required_verifiers = ('scripts/check_ci_qualification.py', 'scripts/ci/execution_identity.py', 'pyproject.toml')
        if not set(required_verifiers) <= set(tracked): raise ValueError('required verifier source missing')
        protected = [*required_verifiers, *(['tests/conftest.py'] if 'tests/conftest.py' in tracked else [])]
        verifiers = {p: _hash(self._blob(sha, p)) for p in protected}
        policy = {'source_sha': sha, 'candidate_ref': branch, 'allowed_paths': allowed,
                  'source_hashes': {p: _hash(self._blob(sha, p)) for p in allowed},
                  'test_hashes': {test: _hash(test_bytes)}, 'verifier_hashes': verifiers,
                  'reproducer_argv': ['python', '-m', 'pytest', '-q', node], 'max_diff_bytes': 65536}
        # Storage and mount gates occur immediately before the new worktree.
        self.guard()
        self._run(['/usr/bin/python3', STORAGE, '--path', str(self.worktrees), '--expected-bytes', '200000000'], self.repo)
        if worktree.exists() or worktree.is_symlink(): raise RuntimeError('worktree already exists; reconcile only')
        self._git('-c', 'core.hooksPath=/dev/null', 'worktree', 'add', '-b', branch, str(worktree), sha)
        worker = self.worker_class(worktree, directory, policy, runner=self.runner, admission=lambda repo, p: True)
        worker._identity(sha); worker._tests()
        if worker._check() != 1: raise RuntimeError('local baseline did not reproduce')
        record = {'schema': 'fdisbull-source-reproducer-1', 'selection_profile': 'single-failure-direct-imports-1',
                  'status': 'verified_reproducer', 'event_key': event, 'target': validated,
                  'policy': policy, 'worktree': str(worktree), 'node': node,
                  'baseline': 'failed', 'baseline_platform': platform.system(), 'baseline_interpreter': dict(PINNED_INTERPRETER),
                  'linux_parity': False, 'requires_linux_requalification': True}
        legacy._json(directory/'prepared.json', record)
        return {**record, 'receipt_path': str(directory/'prepared.json')}

    def reconcile_prepare(self, target, bundle):
        if not self.approved: return None
        self.guard()
        if self.interpreter_check() != PINNED_INTERPRETER: return None
        validated, _, event = validate_bundle(bundle)
        if identity.target(target) != validated: return None
        try:
            directory, record = self._validated_record(event, validated)
            worker = self.worker_class(record['worktree'], directory, record['policy'], runner=self.runner,
                                       admission=lambda repo, p: True)
            worker._identity(validated['source_sha']); worker._tests()
            return {**record, 'receipt_path': str(directory/'prepared.json')}
        except (OSError, ValueError, KeyError, RuntimeError): return None

    def _validated_record(self, event, target):
        directory = self._directory(event)
        if any(p.is_symlink() for p in (directory, *directory.parents)):
            raise ValueError('unsafe source state')
        intent = _json((directory/'intent.json').read_bytes())
        record = _json((directory/'prepared.json').read_bytes())
        policy = record.get('policy')
        if (intent.get('event_key') != event or intent.get('target') != target
                or record.get('schema') != 'fdisbull-source-reproducer-1'
                or record.get('selection_profile') != 'single-failure-direct-imports-1'
                or record.get('status') != 'verified_reproducer' or record.get('event_key') != event
                or record.get('baseline_interpreter') != PINNED_INTERPRETER
                or record.get('target') != target or not isinstance(policy, dict)
                or policy.get('source_sha') != target['source_sha']
                or policy.get('candidate_ref') != 'codex/ci-repair-' + event
                or record.get('worktree') != str(self.worktrees / ('ci-repair-' + event))
                or policy.get('max_diff_bytes') != 65536
                or policy.get('reproducer_argv') != ['python', '-m', 'pytest', '-q', record.get('node')]):
            raise ValueError('preparation mismatch')
        allowed = policy.get('allowed_paths'); sources = policy.get('source_hashes')
        if (not isinstance(allowed, list) or not 1 <= len(allowed) <= 3 or not isinstance(sources, dict)
                or set(allowed) != set(sources) or len(allowed) != len(sources)):
            raise ValueError('prepared source binding mismatch')
        for group in (sources, policy.get('test_hashes'), policy.get('verifier_hashes')):
            if not isinstance(group, dict) or not group: raise ValueError('protected hashes missing')
            for name, digest in group.items():
                if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', name)
                        or name.startswith('/') or '..' in name.split('/') or not isinstance(digest, str)
                        or not re.fullmatch(r'[0-9a-f]{64}', digest) or _hash(self._blob(target['source_sha'], name)) != digest):
                    raise ValueError('protected Git blob mismatch')
        return directory, record

    def _prepared(self, payload):
        if not isinstance(payload, dict) or not isinstance(payload.get('source_prepare'), dict): raise ValueError('preparation required')
        event = payload['source_prepare'].get('event_key')
        return self._validated_record(event, identity.target(payload['target']))

    def _publisher(self, key, local):
        if self.publisher is None or not callable(self.publisher) or not callable(getattr(self.publisher, 'readback', None)):
            raise RuntimeError('reviewed dual-provider publisher unavailable')
        published = self.publisher(key, local)
        readback = self.publisher.readback(key, local)
        for result in (published, readback):
            if (not isinstance(result, dict) or result.get('verified') is not True
                    or result.get('source_sha') != local['source_sha'] or result.get('candidate_ref') != local['candidate_ref']
                    or not isinstance(result.get('receipt_path'), str) or not result['receipt_path']
                    or any(not isinstance(result.get(name), dict) or result[name].get('verified') is not True
                           or result[name].get('source_sha') != local['source_sha']
                           or result[name].get('candidate_ref') != local['candidate_ref'] for name in ('github', 'gitlab'))):
                raise RuntimeError('dual-provider publication readback unavailable')
        return readback

    def repair(self, key, payload):
        self.guard()
        if self.interpreter_check() != PINNED_INTERPRETER: raise RuntimeError('source interpreter unavailable')
        if not self.approved or not callable(self.publisher) or not callable(getattr(self.publisher, 'readback', None)):
            raise RuntimeError('source worker or dual-provider publisher unavailable')
        if not callable(getattr(self.publisher, 'admit', None)) or self.publisher.admit() is not True:
            raise RuntimeError('shared provider status unavailable')
        directory, record = self._prepared(payload)
        worker = self.worker_class(record['worktree'], directory, record['policy'], runner=self.runner,
                    admission=lambda repo, p: str(repo) == record['worktree'] and p == record['policy'], publisher=self._publisher)
        result = worker(key, payload)
        return result

    def reconcile(self, key, payload):
        self.guard()
        if self.interpreter_check() != PINNED_INTERPRETER: return None
        if not self.approved or not callable(self.publisher) or not callable(getattr(self.publisher, 'readback', None)): return None
        try:
            directory, record = self._prepared(payload)
            worker = self.worker_class(record['worktree'], directory, record['policy'], runner=self.runner,
                    admission=lambda repo, p: True, publisher=self._publisher)
            result = worker.reconcile(key, payload)
            if result and isinstance(result.get('publication'), dict):
                self._publisher_readback_only(key, result)
                return result
            # A commit may exist when publication response was lost. Never
            # publish again: independently verify the immutable local commit
            # and read both existing remote refs before writing final proof.
            action_dir = worker._directory(key)
            local = _json((action_dir/'local.json').read_bytes())
            if (local.get('status') != 'completed' or local.get('base_sha') != record['policy']['source_sha']
                    or local.get('candidate_ref') != record['policy']['candidate_ref']
                    or not re.fullmatch(r'[0-9a-f]{40}', str(local.get('source_sha', '')))
                    or local['source_sha'] == local['base_sha']): return None
            worker._identity(local['source_sha']); worker._tests()
            if (worker._git('rev-parse', local['source_sha']+'^') != local['base_sha']
                    or ('Recovery-Action-Key: '+key) not in worker._git('log','-1','--format=%B').splitlines()):
                return None
            changed = set(worker._git('diff-tree','--no-commit-id','--name-only','-r',local['source_sha']).splitlines())
            if not changed or not changed <= set(record['policy']['allowed_paths']): return None
            local['publication'] = self._publisher_readback_only(key, local)
            final = action_dir/'final.json'
            if final.exists() or final.is_symlink(): return None
            legacy._json(final, local)
            return local
        except (OSError, ValueError, KeyError, RuntimeError): return None

    def _publisher_readback_only(self, key, result):
        readback = self.publisher.readback(key, result)
        if (not isinstance(readback, dict) or readback.get('verified') is not True
                or readback.get('source_sha') != result['source_sha'] or readback.get('candidate_ref') != result['candidate_ref']
                or not isinstance(readback.get('receipt_path'), str) or not readback['receipt_path']
                or any(not isinstance(readback.get(name), dict) or readback[name].get('verified') is not True
                       or readback[name].get('source_sha') != result['source_sha']
                       or readback[name].get('candidate_ref') != result['candidate_ref'] for name in ('github', 'gitlab'))):
            raise RuntimeError('dual-provider readback unavailable')
        return readback


def handle(server, doc):
    """Only structured source operations; callers cannot provide command or paths."""
    if not isinstance(doc, dict): raise ValueError('invalid request')
    operation = doc.get('operation')
    if operation in ('prepare', 'reconcile_prepare') and set(doc) == {'operation', 'target', 'evidence'}:
        return getattr(server, operation)(doc['target'], doc['evidence'])
    if operation in ('repair', 'reconcile') and set(doc) == {'operation', 'key', 'payload'}:
        payload = doc['payload']
        if (not isinstance(doc['key'], str) or not 1 <= len(doc['key']) <= 500
                or any(ord(c) < 32 for c in doc['key']) or not isinstance(payload, dict)
                or set(payload) != {'target', 'source_prepare'}
                or not isinstance(payload['source_prepare'], dict)
                or set(payload['source_prepare']) != {'event_key'}):
            raise ValueError('invalid source action')
        return getattr(server, operation)(doc['key'], payload)
    raise ValueError('unsupported source operation')


class SSHSourceTransport:
    """Fixed private SSH route; no arbitrary command, helper path or credentials."""
    def __init__(self, *, runner=None):
        self.runner = runner or legacy.run_command

    def _call(self, doc):
        data = json.dumps(doc, separators=(',', ':')).encode()
        if len(data) > MAX_DOC: raise ValueError('source request exceeds bound')
        argv = ['/usr/bin/tailscale', 'ssh', 'tiga@100.76.103.43', SOURCE_PYTHON, HELPER]
        result = self.runner(argv, cwd='/', env=_clean_env(os.environ), input_bytes=data, timeout=600)
        if (not isinstance(result, dict) or result.get('returncode') != 0 or result.get('timed_out') is not False
                or result.get('overflow') is not False or not isinstance(result.get('stdout'), bytes)
                or len(result['stdout']) > 65536):
            raise RuntimeError('source bridge outcome unknown')
        try: envelope = json.loads(result['stdout'])
        except (ValueError, UnicodeError): raise RuntimeError('source bridge outcome unknown') from None
        if not isinstance(envelope, dict) or set(envelope) != {'result'}:
            raise RuntimeError('source bridge outcome unknown')
        return envelope['result']

    def prepare(self, target, evidence):
        validated, _, _ = validate_bundle(evidence)
        if identity.target(target) != validated: raise ValueError('target mismatch')
        return self._call({'operation': 'prepare', 'target': target, 'evidence': evidence})

    def reconcile_prepare(self, target, evidence):
        validated, _, _ = validate_bundle(evidence)
        if identity.target(target) != validated: raise ValueError('target mismatch')
        return self._call({'operation': 'reconcile_prepare', 'target': target, 'evidence': evidence})

    def repair(self, key, payload):
        return self._call({'operation': 'repair', 'key': key, 'payload': payload})

    def reconcile(self, key, payload):
        return self._call({'operation': 'reconcile', 'key': key, 'payload': payload})


ACTIVATION_MODULES = ('production_source_transport.py', 'production_source_publish.py',
                      'recovery_production.py', 'recovery_source_production.py', 'recovery_source.py',
                      'production_transport.py', 'ci_status.py')


def server_factory(*, config_path=ACTIVATION, module_root=None, bridge_guard=None, publisher_factory=None,
                   interpreter_probe=current_source_interpreter):
    """Enable only an operator-approved private config with exact installed bytes."""
    config_path = Path(config_path)
    module_root = Path(__file__).parent if module_root is None else Path(module_root)
    disabled = SourceServer()
    try:
        if (any(p.is_symlink() for p in (config_path, *config_path.parents))
                or not config_path.is_file() or config_path.stat().st_size > 16384
                or config_path.stat().st_uid != os.getuid() or config_path.stat().st_mode & 0o077
                or config_path.parent.stat().st_uid != os.getuid() or config_path.parent.stat().st_mode & 0o077):
            return disabled
        config = _json(config_path.read_bytes())
        if (set(config) != {'schema', 'approved', 'selection_profile', 'publisher', 'module_sha256', 'source_interpreter'}
                or config['schema'] != 'fdisbull-source-activation-1' or config['approved'] is not True
                or config['selection_profile'] != 'single-failure-direct-imports-1'
                or config['publisher'] != 'candidate-ref-v1' or config['source_interpreter'] != PINNED_INTERPRETER
                or not isinstance(config['module_sha256'], dict)
                or set(config['module_sha256']) != set(ACTIVATION_MODULES)):
            return disabled
        if interpreter_probe() != PINNED_INTERPRETER: return disabled
        if bridge_guard is None:
            provider.ProviderBridge(provider.STATE_DIR)._ensure()
            volume = Path('/Volumes/CODEX').stat().st_dev
            if config_path.stat().st_dev != volume or module_root.stat().st_dev != volume:
                return disabled
        else:
            bridge_guard()
        for name in ACTIVATION_MODULES:
            path = module_root/name; expected = config['module_sha256'][name]
            if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()
                    or path.stat().st_size > MAX_BLOB or not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected)
                    or _hash(path.read_bytes()) != expected):
                return disabled
        server = SourceServer(selection_policy_approved=True)
        if publisher_factory is None:
            publisher_module = _load('activated_source_publisher', 'production_source_publish.py')
            bridge = provider.ProviderBridge(provider.STATE_DIR)
            def shared_admit(name):
                bridge._ensure()
                host, repo, _, scope = bridge._scope_state(name)
                with bridge.status_api._locked(scope) as acquired:
                    if not acquired: return False
                    state = bridge.status_api._load_state(scope/'state.json', host.lower(), repo.lower())
                    return state.get('owner') == provider.OWNER and state.get('provider_stop') is None
            def shared_stop(name, reason):
                bridge._ensure()
                host, repo, directory, _ = bridge._scope_state(name)
                result = bridge.status_api.record_provider_stop(repo=repo, host=host, owner=provider.OWNER,
                                                                reason=reason, state_dir=directory)
                return result.get('recorded') is True or result.get('reason') == 'provider_stopped'
            server.publisher = publisher_module.CandidateRefPublisher(WORKTREES, STATE, guard=server._guard,
                                                                       provider_admit=shared_admit, provider_stop=shared_stop)
        else:
            server.publisher = publisher_factory(server)
        if (not callable(server.publisher) or not callable(getattr(server.publisher, 'readback', None))
                or not callable(getattr(server.publisher, 'admit', None))):
            return disabled
        return server
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return disabled


class OwnedCancel(BaseException):
    """Interrupt owned subprocess supervision without selector retry."""


def _interrupt_owned(signum, frame):
    # selectors may swallow InterruptedError; a dedicated BaseException must
    # reach bounded.run_command's owned process-group cleanup.
    raise OwnedCancel()


def main():
    signals = [signal.SIGTERM]
    if hasattr(signal, 'SIGHUP'): signals.append(signal.SIGHUP)
    previous = {}
    try:
        for signum in signals:
            previous[signum] = signal.signal(signum, _interrupt_owned)
        data = sys.stdin.buffer.read(MAX_DOC + 1)
        if len(data) > MAX_DOC: raise ValueError('source request exceeds bound')
        doc = json.loads(data)
        result = handle(server_factory(), doc)
        print(json.dumps({'result': result}, separators=(',', ':')))
        return 0
    except (Exception, OwnedCancel):
        print('{"error":"source_operation_unavailable"}')
        return 1
    finally:
        for signum, handler in previous.items(): signal.signal(signum, handler)


if __name__ == '__main__': raise SystemExit(main())
