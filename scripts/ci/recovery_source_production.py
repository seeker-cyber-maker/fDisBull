"""One finite, receipt-backed source repair in a pre-admitted isolated worktree.

The CLI has no token-budget option; wall time and output are bounded instead.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

_spec = importlib.util.spec_from_file_location('recovery_source_legacy', Path(__file__).with_name('recovery_source.py'))
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)

CODEX = _legacy.CODEX


def _credential_free_environment():
    markers = ('API_KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'CREDENTIAL')
    return {key: value for key, value in os.environ.items()
            if not any(marker in key.upper() for marker in markers)}


def _hash(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or non-regular protected file')
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductionSourceRepair:
    def __init__(self, repo_root, state_dir, policy, *, runner=None, codex_bin=CODEX,
                 admission=None, publisher=None):
        self.repo = Path(repo_root).resolve()
        self.state_dir = Path(state_dir).resolve()
        if self.state_dir == self.repo or self.repo in self.state_dir.parents:
            raise ValueError('state must be outside worktree')
        self.policy = dict(policy)
        self.runner = runner or _legacy.run_command
        self.codex_bin, self.admission, self.publisher = codex_bin, admission, publisher
        self.sha = policy.get('source_sha')
        self.branch = policy.get('candidate_ref')
        self.allowed = policy.get('allowed_paths')
        self.tests = policy.get('test_hashes')
        self.verifiers = policy.get('verifier_hashes', {})
        self.argv = policy.get('reproducer_argv')
        self.max_diff = policy.get('max_diff_bytes')
        if not isinstance(self.sha,str) or not re.fullmatch('[0-9a-f]{40}',self.sha): raise ValueError('invalid base sha')
        if (not isinstance(self.branch,str) or not re.fullmatch(r'codex/[A-Za-z0-9_./-]{1,180}',self.branch)
                or '..' in self.branch or self.branch.endswith(('/', '.'))): raise ValueError('invalid repair branch')
        if (not isinstance(self.allowed,list) or not 1 <= len(self.allowed) <= 3 or len(set(self.allowed)) != len(self.allowed)
                or any(not isinstance(p,str) or not re.fullmatch(r'src/fdisbull/[A-Za-z0-9_/-]+\.(?:py|c|h)',p)
                       or '..' in p.split('/')
                       or any(token in p.lower() for token in ('test', 'checker', 'config', 'credential', 'secret'))
                       or 'ci' in p.lower().split('/') for p in self.allowed)):
            raise ValueError('invalid source allowlist')
        if (not isinstance(self.tests,dict) or not self.tests or any(
                not isinstance(p,str) or not re.fullmatch(r'tests/[A-Za-z0-9_/-]+\.py',p)
                or '..' in p.split('/') or not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h)
                for p,h in self.tests.items())): raise ValueError('invalid protected tests')
        if (not isinstance(self.verifiers,dict) or any(
                not isinstance(p,str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}',p)
                or p.startswith('/') or '..' in p.split('/') or p in self.allowed
                or not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h)
                for p,h in self.verifiers.items())): raise ValueError('invalid protected verifiers')
        if (not isinstance(self.argv,list) or len(self.argv)<5 or self.argv[:3] != ['python','-m','pytest']
                or any(not isinstance(x,str) for x in self.argv)
                or not any(x in ('-q','--maxfail=1') for x in self.argv[3:])): raise ValueError('invalid reproducer')
        nodes = [x for x in self.argv[3:] if x not in ('-q','--maxfail=1')]
        if not nodes or any(not re.fullmatch(r'tests/[A-Za-z0-9_/-]+\.py(?:::[A-Za-z_][A-Za-z0-9_]*)+',n)
                            or n.split('::')[0] not in self.tests for n in nodes): raise ValueError('invalid test node')
        if (not isinstance(self.max_diff,int) or isinstance(self.max_diff,bool) or not 1 <= self.max_diff <= 1024*1024):
            raise ValueError('invalid repair budgets')

    def _directory(self,key):
        if not isinstance(key,str) or not key or len(key)>500 or any(ord(c)<32 for c in key): raise ValueError('invalid key')
        return self.state_dir / ('source-' + hashlib.sha256(key.encode()).hexdigest())

    def _run(self,argv,*,timeout=30,env=None,input_bytes=None):
        result=self.runner(argv,cwd=str(self.repo),timeout=timeout,
                           env=_credential_free_environment() if env is None else env,
                           input_bytes=input_bytes)
        if (not isinstance(result,dict) or result.get('timed_out') is not False or result.get('overflow') is not False
                or not isinstance(result.get('stdout'),bytes) or not isinstance(result.get('stderr'),bytes)
                or not isinstance(result.get('returncode'),int)):
            raise RuntimeError('command outcome unknown')
        return result

    def _git(self,*args):
        r=self._run(['git',*args])
        if r['returncode'] != 0: raise RuntimeError('git failed')
        return r['stdout'].decode('utf-8','strict').strip()

    def _identity(self,sha,clean=True):
        if self._git('rev-parse','HEAD') != sha or self._git('branch','--show-current') != self.branch:
            raise RuntimeError('worktree identity mismatch')
        if clean and self._git('status','--porcelain','--untracked-files=all'):
            raise RuntimeError('worktree not clean')

    def _tests(self):
        for path,digest in {**self.tests,**self.verifiers}.items():
            target=self.repo/path
            if any(part.is_symlink() for part in [target,*target.parents] if part != self.repo and self.repo in part.parents):
                raise RuntimeError('protected path contains symlink')
            if _hash(target) != digest: raise RuntimeError('protected test or verifier changed')

    def _check(self):
        self._tests()
        env=dict(_credential_free_environment(), PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTEST_ADDOPTS='-p no:cacheprovider')
        result=self._run([sys.executable,*self.argv[1:]],timeout=120,env=env)
        self._tests()
        text=result['stdout'].decode('utf-8','replace')
        if result['returncode'] == 1 and re.search(r'\b[1-9][0-9]* failed\b', text) and not re.search(r'\b[1-9][0-9]* errors?\b', text): return 1
        if result['returncode'] == 0 and re.search(r'\b[1-9][0-9]* passed\b', text): return 0
        raise RuntimeError('reproducer outcome unknown')

    def __call__(self,key,payload,backend=None):
        directory=self._directory(key)
        self.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        directory.mkdir(mode=0o700,exist_ok=False)
        _legacy._json(directory/'intent.json',{'key':key,'source_sha':self.sha,'candidate_ref':self.branch})
        if payload.get('target',{}).get('source_sha') != self.sha: raise RuntimeError('target sha mismatch')
        if not callable(self.admission) or self.admission(self.repo,self.policy) is not True: raise RuntimeError('worktree admission missing')
        self._identity(self.sha)
        if self._check() != 1: raise RuntimeError('baseline did not reproduce a test failure')
        _legacy._json(directory/'baseline.json',{'exit_code':1,'test_hashes':self.tests})
        schema={'type':'object','properties':{'summary':{'type':'string'}},'required':['summary'],'additionalProperties':False}
        _legacy._json(directory/'schema.json',schema)
        argv=[self.codex_bin,'exec','--ignore-user-config','--sandbox','workspace-write','--json',
              '--output-schema',str(directory/'schema.json'),'--cd',str(self.repo),'-']
        prompt=('Repair the failing tests using only these source files: '+', '.join(self.allowed)+'. '
                'Do not edit tests, configuration or other files; do not commit, push or access network. '
                'The immutable reproducer is: '+ ' '.join(self.argv)+'. Return a short summary.\n')
        env=_credential_free_environment()
        try:
            result=self.runner(argv,cwd=str(self.repo),env=env,input_bytes=prompt.encode(),timeout=300)
            if (not isinstance(result,dict) or result.get('timed_out') is not False or result.get('overflow') is not False
                    or result.get('returncode') != 0 or not isinstance(result.get('stdout'),bytes)
                    or not isinstance(result.get('stderr'),bytes) or len(result['stdout']) > _legacy.LIMIT
                    or len(result['stderr']) > _legacy.LIMIT): raise RuntimeError('worker outcome unknown')
            events=[json.loads(line) for line in result['stdout'].splitlines()]
            if not any(isinstance(e,dict) and e.get('type')=='turn.completed' for e in events): raise RuntimeError('worker completion unknown')
            usage = {}
            for event in events:
                if isinstance(event,dict) and event.get('type') == 'turn.completed' and isinstance(event.get('usage'),dict):
                    usage = {k:v for k,v in event['usage'].items() if k in ('input_tokens','cached_input_tokens','output_tokens')
                             and isinstance(v,int) and not isinstance(v,bool) and v >= 0}
            _legacy._json(directory/'worker.json',{'status':'completed','event_count':len(events),'usage':usage,
                'stdout_sha256':hashlib.sha256(result['stdout']).hexdigest(),'stderr_bytes':len(result['stderr'])})
        except Exception:
            _legacy._json(directory/'worker.json',{'status':'unknown'})
            raise
        self._identity(self.sha,clean=False);self._tests()
        if self._git('diff','--cached','--name-only'): raise RuntimeError('unexpected staged files')
        status=self._git('status','--porcelain','--untracked-files=all').splitlines()
        changed=[]
        for row in status:
            row=row.lstrip()
            if not row.startswith('M '): raise RuntimeError('unexpected worktree change')
            changed.append(row[2:])
        if not changed or len(changed)>len(self.allowed) or not set(changed)<=set(self.allowed): raise RuntimeError('source allowlist violated')
        for p in changed:
            path=self.repo/p
            if (not path.is_file() or any(part.is_symlink() for part in [path,*path.parents]
                    if part != self.repo and self.repo in part.parents)): raise RuntimeError('invalid source file')
        diff=self._run(['git','diff','--binary','--',*changed])['stdout']
        if not diff or len(diff)>self.max_diff: raise RuntimeError('patch exceeds bound')
        if self._check() != 0: raise RuntimeError('repaired test failed')
        self._identity(self.sha,clean=False);self._tests()
        if self._git('diff','--cached','--name-only') or self._git('status','--porcelain','--untracked-files=all').splitlines() != status:
            raise RuntimeError('worktree changed during reproducer')
        if self._run(['git','diff','--binary','--',*changed])['stdout'] != diff:
            raise RuntimeError('patch changed during reproducer')
        self._git('add','--',*changed)
        if set(self._git('diff','--cached','--name-only').splitlines()) != set(changed): raise RuntimeError('staged patch mismatch')
        self._git('commit','-m','Repair CI regression\n\nRecovery-Action-Key: '+key,'--',*changed)
        new=self._git('rev-parse','HEAD')
        if not re.fullmatch('[0-9a-f]{40}',new) or new==self.sha: raise RuntimeError('invalid candidate')
        self._identity(new);self._tests()
        if self._git('rev-parse',new+'^') != self.sha or set(self._git('diff-tree','--no-commit-id','--name-only','-r',new).splitlines()) != set(changed):
            raise RuntimeError('candidate commit mismatch')
        local={'status':'completed','source_sha':new,'base_sha':self.sha,'candidate_ref':self.branch,
               'receipt_path':str(directory/'final.json'),'publication':'unpublished'}
        _legacy._json(directory/'local.json',local)
        if self.publisher is not None:
            publication=self.publisher(key,dict(local))
            if (not isinstance(publication,dict) or publication.get('verified') is not True
                    or not isinstance(publication.get('receipt_path'),str) or not publication['receipt_path']
                    or publication.get('source_sha') != new or publication.get('candidate_ref') != self.branch):
                raise RuntimeError('publication readback unknown')
            local['publication']=publication
        _legacy._json(directory/'final.json',local)
        return local

    def reconcile(self,key,payload,backend=None):
        try:
            directory=self._directory(key)
            intent=json.loads((directory/'intent.json').read_text())
            result=json.loads((directory/'final.json').read_text())
            if intent != {'key':key,'source_sha':self.sha,'candidate_ref':self.branch} or payload['target']['source_sha'] != self.sha:
                return None
            if result['status'] != 'completed' or result['base_sha'] != self.sha or result['candidate_ref'] != self.branch:
                return None
            self._identity(result['source_sha']);self._tests()
            if (self._git('rev-parse', result['source_sha']+'^') != self.sha
                    or ('Recovery-Action-Key: '+key) not in self._git('log','-1','--format=%B').splitlines()):
                return None
            return result
        except (OSError,ValueError,KeyError,RuntimeError):
            return None
