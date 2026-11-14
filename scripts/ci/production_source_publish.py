"""Candidate-only dual-provider branch publication with durable no-replay intents.

Tokens exist only in the invoking process and per-command environment. This
module never mutates main, merges, tags, releases, or installs software.
"""
import base64
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import re
import sys


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


legacy = _load('publisher_bounded_runner', 'recovery_source.py')
provider = _load('publisher_provider_boundary', 'production_transport.py')
GIT_BIN = '/usr/bin/git'
GH_BIN = '/opt/homebrew/bin/gh'
GLAB_BIN = '/opt/homebrew/bin/glab'
REMOTES = {'github': 'https://github.com/seeker-cyber-maker/fDisBull.git',
           'gitlab': 'https://gitlab.com/brewster-jennings-group/fdisbull.git'}
SHA = re.compile(r'[0-9a-f]{40}\Z')
REF = re.compile(r'codex/ci-repair-([0-9a-f]{64})\Z')
PINNED_INTERPRETER = {'path': '/Users/tiga/miniconda/bin/python3', 'version': '3.13.13',
                      'sha256': '0f5374bca527c5a5e958ee94e03e55816a368533286e6315b8bf013da622fc61'}


def _env():
    forbidden = ('TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL', 'AUTH', 'API_KEY', 'PROXY')
    result = {k: v for k, v in os.environ.items() if not any(x in k.upper() for x in forbidden)
              and not k.startswith(('GIT_', 'GH_', 'GLAB_', 'SSL_', 'CURL_'))
              and k not in ('SSH_ASKPASS', 'GITLAB_HOST', 'REQUESTS_CA_BUNDLE')}
    result.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                  GIT_CONFIG_COUNT='2', GIT_CONFIG_KEY_0='core.hooksPath', GIT_CONFIG_VALUE_0='/dev/null',
                  GIT_CONFIG_KEY_1='core.fsmonitor', GIT_CONFIG_VALUE_1='false')
    return result


def _write(path, value):
    data = (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    dfd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(dfd)
    finally: os.close(dfd)
    return str(path)


def _read(path):
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('publication proof unavailable')
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict): raise ValueError('publication proof invalid')
    return value


def _digest(path):
    if path.is_symlink() or not path.is_file(): raise ValueError('protected source missing')
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CandidateRefPublisher:
    def __init__(self, worktrees, state, *, guard, provider_admit=None, provider_stop=None, runner=None):
        self.worktrees, self.state = Path(worktrees), Path(state)
        self.guard, self.runner = guard, runner or legacy.run_command
        self.provider_admit, self.provider_stop = provider_admit, provider_stop
        if not callable(guard): raise ValueError('source guard required')

    def admit(self):
        self.guard()
        if not callable(self.provider_admit) or not callable(self.provider_stop):
            raise RuntimeError('shared provider status unavailable')
        if any(self.provider_admit(name) is not True for name in REMOTES):
            raise RuntimeError('shared provider status stopped or unavailable')
        return True

    def _stop(self, name, reason):
        if not callable(self.provider_stop) or self.provider_stop(name, reason) is not True:
            raise RuntimeError('shared provider stop could not be persisted')
        raise RuntimeError('publisher account mismatch' if reason == 'provider_account_mismatch'
                           else 'publisher provider stopped')

    def _classify_failure(self, name, result):
        # Inspect only in memory; persist a compact vocabulary, never raw text.
        raw = result.get('stderr', b'') if isinstance(result, dict) else b''
        text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else ''
        match = re.search(r'(?i)(?:HTTP|error|status|returned)\D{0,20}(401|403|429)\b', text)
        if match: self._stop(name, 'provider_http_' + match.group(1))
        if provider._status._restricted(text): self._stop(name, 'provider_restriction')
        if re.search(r'(?i)authentication failed|could not read username|access denied', text):
            self._stop(name, 'provider_authentication_required')

    def _run(self, argv, *, cwd, env, timeout=30):
        r = self.runner(argv, cwd=str(cwd), env=env, input_bytes=None, timeout=timeout)
        if (not isinstance(r, dict) or type(r.get('returncode')) is not int
                or r.get('timed_out') is not False or r.get('overflow') is not False
                or not isinstance(r.get('stdout'), bytes) or not isinstance(r.get('stderr'), bytes)
                or len(r['stdout']) > legacy.LIMIT or len(r['stderr']) > legacy.LIMIT):
            raise RuntimeError('publisher command outcome unknown')
        return r

    def _local_git(self, worktree, *args):
        result = self._run([GIT_BIN, '-C', str(worktree), *args], cwd=worktree, env=_env())
        if result['returncode'] != 0: raise RuntimeError('local Git proof unavailable')
        return result['stdout']

    def _proof(self, key, local):
        self.guard()
        if (not isinstance(key, str) or not 1 <= len(key) <= 500 or any(ord(c) < 32 for c in key)
                or not isinstance(local, dict) or local.get('status') != 'completed'):
            raise ValueError('invalid publication action')
        ref, new, base = local.get('candidate_ref'), local.get('source_sha'), local.get('base_sha')
        match = REF.fullmatch(ref) if isinstance(ref, str) else None
        if not match or not isinstance(new, str) or not SHA.fullmatch(new) or not isinstance(base, str) or not SHA.fullmatch(base) or new == base:
            raise ValueError('invalid candidate identity')
        event = match.group(1); directory = self.state / event
        prepared = _read(directory/'prepared.json'); policy = prepared.get('policy')
        worktree = self.worktrees / ('ci-repair-' + event)
        if (not isinstance(policy, dict) or prepared.get('event_key') != event
                or prepared.get('schema') != 'fdisbull-source-reproducer-1'
                or prepared.get('selection_profile') != 'single-failure-direct-imports-1'
                or prepared.get('status') != 'verified_reproducer' or prepared.get('worktree') != str(worktree)
                or prepared.get('baseline_interpreter') != PINNED_INTERPRETER
                or not isinstance(prepared.get('target'), dict) or prepared['target'].get('source_sha') != base
                or not isinstance(prepared.get('node'), str)
                or policy.get('reproducer_argv') != ['python', '-m', 'pytest', '-q', prepared['node']]
                or policy.get('candidate_ref') != ref or policy.get('source_sha') != base
                or policy.get('max_diff_bytes') != 65536 or local.get('receipt_path') is None):
            raise ValueError('prepared policy mismatch')
        if any(p.is_symlink() for p in (worktree, *worktree.parents)) or not worktree.is_dir():
            raise ValueError('candidate worktree unavailable')
        action = directory / ('source-' + hashlib.sha256(key.encode()).hexdigest())
        intent, baseline, worker, saved_local = (_read(action/name) for name in ('intent.json', 'baseline.json', 'worker.json', 'local.json'))
        if (intent != {'key': key, 'source_sha': base, 'candidate_ref': ref}
                or baseline.get('exit_code') != 1 or baseline.get('test_hashes') != policy.get('test_hashes')
                or worker.get('status') != 'completed' or saved_local.get('publication') != 'unpublished'
                or saved_local.get('receipt_path') != str(action/'final.json')
                or any(saved_local.get(k) != local.get(k) for k in ('status','base_sha','source_sha','candidate_ref','receipt_path'))):
            raise ValueError('source worker proof mismatch')
        test_hashes = policy.get('test_hashes'); verifiers = policy.get('verifier_hashes')
        node = prepared['node']
        if (not re.fullmatch(r'tests/[A-Za-z0-9_/-]+\.py(?:::[A-Za-z_][A-Za-z0-9_]*)+', node)
                or not isinstance(test_hashes, dict) or set(test_hashes) != {node.split('::')[0]}
                or not isinstance(verifiers, dict)
                or not {'scripts/check_ci_qualification.py', 'scripts/ci/execution_identity.py', 'pyproject.toml'} <= set(verifiers)):
            raise ValueError('source verifier policy mismatch')
        allowed = policy.get('allowed_paths')
        if (not isinstance(allowed, list) or not 1 <= len(allowed) <= 3 or len(set(allowed)) != len(allowed)
                or any(not isinstance(p, str) or not re.fullmatch(r'src/fdisbull/[A-Za-z0-9_/-]+\.py', p)
                       or any(token in p.lower() for token in ('test','checker','config','credential','secret'))
                       or 'ci' in p.lower().split('/') for p in allowed)
                or set(policy.get('source_hashes', {})) != set(allowed)):
            raise ValueError('source allowlist mismatch')
        # Any URL rewrite, credential or proxy setting can redirect or leak
        # scoped credentials; reject it instead of guessing precedence.
        config = self._run([GIT_BIN, '-C', str(worktree), 'config', '--get-regexp',
            r'^(url\..*\.(insteadof|pushinsteadof)|http\..*(extraheader|proxy|sslverify|sslcainfo|sslcapath)|credential\..*)$'],
            cwd=worktree, env=_env())
        if config['returncode'] != 1 or config['stdout']:
            raise RuntimeError('unsafe or unreadable Git configuration')
        def git(*args): return self._local_git(worktree, *args).decode('utf-8', 'strict').strip()
        if (git('rev-parse', 'HEAD') != new or git('branch', '--show-current') != ref
                or git('status', '--porcelain', '--untracked-files=all')
                or git('rev-parse', new+'^') != base
                or len(git('rev-list', '--parents', '-n', '1', new).split()) != 2
                or ('Recovery-Action-Key: '+key) not in git('log', '-1', '--format=%B').splitlines()):
            raise ValueError('candidate commit identity mismatch')
        changed = git('diff-tree', '--no-commit-id', '--name-only', '-r', new).splitlines()
        if not changed or len(changed) != len(set(changed)) or not set(changed) <= set(allowed):
            raise ValueError('candidate change outside allowlist')
        diff = self._local_git(worktree, 'diff', '--binary', base, new, '--', *changed)
        if not diff or len(diff) > 65536: raise ValueError('candidate diff exceeds bound')
        for group in ('test_hashes', 'verifier_hashes', 'source_hashes'):
            entries = policy.get(group)
            if not isinstance(entries, dict) or not entries: raise ValueError('protected hashes missing')
            for name, digest in entries.items():
                if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', name)
                        or name.startswith('/') or '..' in name.split('/') or not isinstance(digest, str)
                        or not re.fullmatch(r'[0-9a-f]{64}', digest)
                        or hashlib.sha256(self._local_git(worktree, 'show', base+':'+name)).hexdigest() != digest):
                    raise ValueError('protected Git blob differs')
                if group != 'source_hashes' and _digest(worktree/name) != digest:
                    raise ValueError('protected test or verifier changed')
        return {'event_key': event, 'key': key, 'base_sha': base, 'source_sha': new,
                'candidate_ref': ref, 'worktree': str(worktree), 'action_dir': str(action),
                'node': node, 'test_hashes': test_hashes}

    def _verification(self, proof, *, run):
        path = Path(proof['action_dir']) / 'source-verification.json'
        value = {k: proof[k] for k in ('event_key', 'key', 'base_sha', 'source_sha', 'candidate_ref', 'node', 'test_hashes')}
        value.update(status='passed', platform=platform.system(), interpreter=dict(PINNED_INTERPRETER),
                     linux_requalification_required=True)
        if path.exists() or path.is_symlink():
            if _read(path) != value: raise ValueError('source verification receipt conflicts')
            return str(path)
        if not run: raise RuntimeError('source verification proof unavailable')
        env = _env()
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTEST_ADDOPTS='-p no:cacheprovider')
        result = self._run([sys.executable, '-m', 'pytest', '-q', proof['node']],
                           cwd=proof['worktree'], env=env, timeout=120)
        output = result['stdout'].decode('utf-8', 'replace')
        if (result['returncode'] != 0 or not re.search(r'\b1 passed\b', output)
                or re.search(r'\b[1-9][0-9]* (?:failed|errors?|skipped)\b', output)):
            raise RuntimeError('candidate reproducer verification unavailable')
        # Recheck protected files and clean commit after the test, before proof.
        worktree = Path(proof['worktree'])
        for name, digest in proof['test_hashes'].items():
            if _digest(worktree/name) != digest: raise ValueError('test changed during verification')
        if self._local_git(worktree, 'status', '--porcelain', '--untracked-files=all').strip():
            raise ValueError('source changed during verification')
        return _write(path, value)

    def _credentials(self, worktree):
        credentials = {}
        for name, cmd in (('github', [GH_BIN, 'auth', 'token', '--hostname', 'github.com', '--user', 'seeker-cyber-maker', '--no-refresh']),
                          ('gitlab', [GLAB_BIN, 'config', 'get', 'token', '--host', 'gitlab.com'])):
            try:
                r = self._run(cmd, cwd=worktree, env=_env(), timeout=15)
            except RuntimeError:
                self._stop(name, 'provider_authentication_required')
            token = r['stdout'].strip()
            if (r['returncode'] != 0 or not token or len(token) > 4096 or b'\n' in token or b'\r' in token):
                self._stop(name, 'provider_authentication_required')
            try: credentials[name] = token.decode('ascii', 'strict')
            except UnicodeError: self._stop(name, 'provider_authentication_required')
        for name, cmd, variable in (
            ('github', [GH_BIN, 'api', '--hostname', 'github.com', '--include', 'user'], 'GH_TOKEN'),
            ('gitlab', [GLAB_BIN, 'api', '--hostname', 'gitlab.com', '--include', 'user'], 'GITLAB_TOKEN')):
            env = _env(); env[variable] = credentials[name]
            r = self._run(cmd, cwd=worktree, env=env, timeout=15)
            try: response = provider._parse(r['stdout'], False)
            except (ValueError, RuntimeError, UnicodeError):
                self._classify_failure(name, r)
                raise RuntimeError('publisher account unavailable') from None
            code, principal = response.get('http_status'), response.get('data')
            if code in (401, 403, 429): self._stop(name, 'provider_http_' + str(code))
            if r['returncode'] != 0 or code != 200:
                self._classify_failure(name, r)
                raise RuntimeError('publisher account unavailable')
            if (not isinstance(principal, dict)
                    or name == 'github' and principal.get('login') != 'seeker-cyber-maker'
                    or name == 'gitlab' and (type(principal.get('id')) is not int or principal['id'] != 43957127
                                             or principal.get('username') != 'TiGa-RCE')):
                self._stop(name, 'provider_account_mismatch')
        return credentials

    def _remote_env(self, name, token):
        env = _env()
        username = 'x-access-token' if name == 'github' else 'oauth2'
        basic = base64.b64encode((username + ':' + token).encode()).decode()
        domain = 'github.com' if name == 'github' else 'gitlab.com'
        pairs = [('core.hooksPath', '/dev/null'), ('core.fsmonitor', 'false'), ('credential.helper', ''),
                 ('http.followRedirects', 'false'), ('http.sslVerify', 'true'),
                 ('http.https://' + domain + '/.extraheader', 'Authorization: Basic ' + basic)]
        env['GIT_CONFIG_COUNT'] = str(len(pairs))
        for i, (key, value) in enumerate(pairs):
            env['GIT_CONFIG_KEY_'+str(i)] = key; env['GIT_CONFIG_VALUE_'+str(i)] = value
        return env

    def _remote(self, proof, name, token):
        ref = 'refs/heads/' + proof['candidate_ref']
        r = self._run([GIT_BIN, '-C', proof['worktree'], 'ls-remote', '--heads', REMOTES[name], ref],
                      cwd=proof['worktree'], env=self._remote_env(name, token), timeout=45)
        if r['returncode'] != 0:
            self._classify_failure(name, r)
            raise RuntimeError('remote readback unavailable')
        if not r['stdout'].strip(): return None
        if r['stdout'].decode('ascii', 'strict').strip() != proof['source_sha']+'\t'+ref:
            raise RuntimeError('remote candidate ref differs')
        return proof['source_sha']

    def _intent(self, proof, name):
        path = Path(proof['action_dir']) / ('publish-' + name + '-intent.json')
        value = {k: proof[k] for k in ('event_key', 'key', 'base_sha', 'source_sha', 'candidate_ref')}
        value.update(provider=name, remote=REMOTES[name])
        if path.exists() or path.is_symlink():
            if _read(path) != value: raise ValueError('publication intent conflicts')
            return False
        _write(path, value)
        return True

    def _result(self, proof):
        action_dir = Path(proof['action_dir'])
        result = {'verified': True, 'source_sha': proof['source_sha'], 'candidate_ref': proof['candidate_ref'],
                  'source_verification_sha256': _digest(action_dir/'source-verification.json')}
        for name in REMOTES:
            result[name] = {'verified': True, 'source_sha': proof['source_sha'], 'candidate_ref': proof['candidate_ref'],
                            'remote': REMOTES[name], 'principal': 'seeker-cyber-maker' if name == 'github' else 'TiGa-RCE',
                            'intent_sha256': _digest(action_dir/('publish-' + name + '-intent.json'))}
            if name == 'gitlab': result[name]['principal_id'] = 43957127
        path = Path(proof['action_dir']) / 'publication-readback.json'
        if path.exists():
            if _read(path) != result: raise ValueError('publication receipt conflicts')
        else: _write(path, result)
        return {**result, 'receipt_path': str(path)}

    def __call__(self, key, local):
        self.admit()
        proof = self._proof(key, local)
        self._verification(proof, run=True)
        if self._proof(key, local) != proof: raise RuntimeError('candidate changed during verification')
        credentials = self._credentials(proof['worktree'])  # Both accounts before either mutation.
        action_intent = Path(proof['action_dir']) / 'publication-intent.json'
        if action_intent.exists() or action_intent.is_symlink():
            raise RuntimeError('publication already attempted; reconcile only')
        _write(action_intent, {k: proof[k] for k in ('event_key', 'key', 'base_sha', 'source_sha', 'candidate_ref')})
        for name, url in REMOTES.items():
            if self._proof(key, local) != proof: raise RuntimeError('candidate changed before publication')
            created = self._intent(proof, name)
            present = self._remote(proof, name, credentials[name])
            if present is not None: continue
            if not created: raise RuntimeError('previous push outcome unknown; reconcile only')
            ref = 'refs/heads/' + proof['candidate_ref']
            options = ['--push-option=ci.skip'] if name == 'gitlab' else []
            r = self._run([GIT_BIN, '-C', proof['worktree'], 'push', *options, url, proof['source_sha']+':'+ref],
                          cwd=proof['worktree'], env=self._remote_env(name, credentials[name]), timeout=120)
            if r['returncode'] != 0:
                self._classify_failure(name, r)
                raise RuntimeError('candidate push outcome unknown')
            if self._remote(proof, name, credentials[name]) is None: raise RuntimeError('candidate push readback unavailable')
        return self._result(proof)

    def readback(self, key, local):
        self.admit()
        proof = self._proof(key, local)
        self._verification(proof, run=False)
        # Existing intents are mandatory: matching refs alone do not prove an action was attempted.
        expected_action = {k: proof[k] for k in ('event_key', 'key', 'base_sha', 'source_sha', 'candidate_ref')}
        if _read(Path(proof['action_dir'])/'publication-intent.json') != expected_action:
            raise ValueError('publication action intent mismatch')
        for name in REMOTES:
            path = Path(proof['action_dir']) / ('publish-' + name + '-intent.json')
            expected = {k: proof[k] for k in ('event_key', 'key', 'base_sha', 'source_sha', 'candidate_ref')}
            expected.update(provider=name, remote=REMOTES[name])
            if _read(path) != expected: raise ValueError('publication intent mismatch')
        credentials = self._credentials(proof['worktree'])
        for name in REMOTES:
            if self._remote(proof, name, credentials[name]) is None: raise RuntimeError('candidate ref not observed')
        return self._result(proof)
