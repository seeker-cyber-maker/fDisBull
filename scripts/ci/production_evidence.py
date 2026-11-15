"""Verify and retain one production job export; never assert whole-release qualification."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET


def _load(name, filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


production=_load('recovery_production','recovery_production.py')
ovh=_load('ovh_export','ovh-export.py')
PROFILES={'ordinary':('ordinary.json',['artifacts/ordinary/tests.xml','artifacts/ordinary/required-contracts.xml']),
          'stable':('native-stable.json',['native-evidence/stable/tests.xml']),
          'layers':('native-layers.json',['native-evidence/layers/tests.xml']),
          'unified':('native-unified.json',['native-evidence/pe/tests.xml','native-evidence/unified/tests.xml'])}
ORDINARY={'ordinary-receipt','package-payloads','tests','required-contracts','core-wheel','player-wheel','sdist','tool-zip'}


def _digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def _regular(path):
    if any(p.is_symlink() for p in (path,*path.parents)) or not path.is_file():
        raise ValueError('missing or unsafe file')
    return path


def _read(path,limit=16*1024*1024):
    path=_regular(path)
    if path.stat().st_size>limit: raise ValueError('metadata exceeds bound')
    return json.loads(path.read_bytes())


def _closed(exported,inventory,files):
    if not isinstance(inventory,list) or not inventory or type(files) is not int or files!=len(inventory):
        raise ValueError('invalid inventory')
    seen={}
    for entry in inventory:
        if not isinstance(entry,dict) or set(entry)!={'path','size','sha256'}: raise ValueError('invalid inventory entry')
        name=entry['path']
        if (not isinstance(name,str) or not name or PurePosixPath(name).is_absolute()
                or '..' in PurePosixPath(name).parts or str(PurePosixPath(name))!=name or name in seen
                or type(entry['size']) is not int or entry['size']<0 or not isinstance(entry['sha256'],str)
                or not re.fullmatch('[0-9a-f]{64}',entry['sha256'])): raise ValueError('invalid inventory identity')
        item=_regular(exported/name)
        if item.stat().st_size!=entry['size'] or _digest(item)!=entry['sha256']: raise ValueError('inventory byte mismatch')
        seen[name]=entry
    actual=set()
    for item in exported.rglob('*'):
        if item.is_symlink(): raise ValueError('symlink in export')
        if item.is_file():actual.add(item.relative_to(exported).as_posix())
        elif not item.is_dir():raise ValueError('nonregular export')
    if actual!=set(seen):raise ValueError('inventory not closed')
    return seen


def _pytest_subtest_summary(path):
    path=_regular(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('junit pytest log too large')
    with path.open('rb') as stream:data=stream.read(16*1024*1024+1)
    if len(data)>16*1024*1024 or not data.endswith(b'\n'):
        raise ValueError('junit pytest terminal summary incomplete')
    try:lines=[line.strip().strip('=').strip() for line in data.decode('utf-8').splitlines() if line.strip()]
    except UnicodeError:raise ValueError('junit pytest log encoding invalid') from None
    pattern=re.compile(r'(?P<results>[0-9]+ [a-z]+(?: [a-z]+)?(?:, [0-9]+ [a-z]+(?: [a-z]+)?)*)'
                       r' in [0-9]+(?:\.[0-9]+)?s(?: \([0-9]+:[0-5][0-9](?::[0-5][0-9])?\))?')
    matches=[(index,match) for index,line in enumerate(lines) if (match:=pattern.fullmatch(line))]
    if len(matches)!=1 or matches[0][0]!=len(lines)-1:
        raise ValueError('junit pytest terminal summary missing or ambiguous')
    counts={}
    for item in matches[0][1]['results'].split(', '):
        value,label=item.split(' ',1)
        if label not in ('passed','skipped','subtests passed') or label in counts:
            raise ValueError('junit pytest terminal outcomes unsupported or failing')
        counts[label]=int(value)
    if counts.get('subtests passed',0)<=0:
        raise ValueError('junit passed subtest proof missing')
    return counts.get('passed',0),counts.get('skipped',0),counts['subtests passed']


def _junit(path,strict,*,summary_path=None):
    path=_regular(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('junit too large')
    root=ET.parse(path).getroot()
    suites=[root] if root.tag=='testsuite' else list(root.findall('testsuite')) if root.tag=='testsuites' else []
    if not suites: raise ValueError('junit suites missing')
    totals={k:0 for k in ('tests','failures','errors','skipped')}
    for suite in suites:
        for k in totals:
            value=suite.get(k,'0')
            if not re.fullmatch('[0-9]+',value): raise ValueError('invalid junit total')
            totals[k]+=int(value)
    if (totals['tests']<=0 or totals['failures'] or totals['errors'] or strict and totals['skipped']
            or root.findall('.//failure') or root.findall('.//error') or strict and root.findall('.//skipped')):
        raise ValueError('junit failed or missing')
    cases=root.findall('.//testcase')
    if len(cases)!=totals['tests']:
        # Pytest 9 counts passing subreports in tests, but reuses their parent
        # testcase node. XML alone cannot distinguish that from missing cases.
        # Only the ordinary caller may supply its already inventory-bound log.
        if (not cases or strict or summary_path is None or len(suites)!=1
                or any(suite.findall('.//testsuite') for suite in suites)
                or len(suites[0].findall('testcase'))!=len(cases)):
            raise ValueError('junit testcase count lacks independent subtest proof')
        passed,skipped,subtests=_pytest_subtest_summary(summary_path)
        skipped_cases=sum(case.find('skipped') is not None for case in cases)
        if (len(cases)!=passed+skipped or totals['tests']!=passed+skipped+subtests
                or totals['skipped']!=skipped or skipped_cases!=skipped
                or len(root.findall('.//skipped'))!=skipped_cases):
            raise ValueError('junit testcase or subtest counts disagree with terminal summary')
    return totals['tests']


def _reference(ref,inventory,exported,project_directory):
    path=ovh.reference_path(ref.get('path'),project_directory)
    entry=inventory.get(path)
    if (not entry or ref.get('sha256')!=entry['sha256']
            or 'size' in ref and ref['size']!=entry['size']): raise ValueError('reference mismatch')
    return path


def _identity(receipt,target,profile):
    if (receipt.get('status')!='passed' or receipt.get('profile')!=profile
            or receipt.get('source_commit')!=target['source_sha'] or receipt.get('job_name')!=target['job_name']):
        raise ValueError('profile receipt mismatch')
    if target['provider']=='gitlab':
        if (receipt.get('execution_origin','gitlab')!='gitlab' or str(receipt.get('pipeline_id'))!=target['pipeline_id']
                or str(receipt.get('job_id'))!=target['job_id']): raise ValueError('receipt execution mismatch')
    else:
        keys=('repository','run_id','run_attempt','job_id','runner_id','ref','control_sha')
        if receipt.get('execution_origin')!='github' or any(str(receipt.get(k))!=str(target[k]) for k in keys):
            raise ValueError('receipt execution mismatch')



def _provider_metadata(metadata,target,status):
    job=metadata.get('job')
    if not isinstance(job,dict): raise ValueError('canonical provider job missing')
    if target['provider']=='gitlab':
        pipe=metadata.get('pipeline')
        if (not isinstance(pipe,dict) or str(pipe.get('id'))!=target['pipeline_id']
                or str(pipe.get('project_id'))!=target['project_id'] or pipe.get('sha')!=target['source_sha']
                or pipe.get('ref')!=target['ref'] or str(job.get('id'))!=target['job_id']
                or job.get('name')!=target['job_name'] or job.get('status')!=status
                or job.get('ref')!=target['ref'] or (job.get('commit') or {}).get('id')!=target['source_sha']
                or str((job.get('runner') or {}).get('id'))!=target['runner_id']
                or str((job.get('pipeline') or {}).get('id'))!=target['pipeline_id']
                or str((job.get('pipeline') or {}).get('project_id'))!=target['project_id']
                or (job.get('pipeline') or {}).get('sha')!=target['source_sha']
                or (job.get('pipeline') or {}).get('ref')!=target['ref']):
            raise ValueError('canonical GitLab metadata mismatch')
    else:
        run=metadata.get('run')
        conclusions={'success'} if status=='success' else {'failure','timed_out'}
        if (not isinstance(run,dict) or str(run.get('id'))!=target['run_id']
                or str(run.get('run_attempt'))!=target['run_attempt'] or run.get('head_sha')!=target['control_sha']
                or run.get('head_branch')!=target['ref'].removeprefix('refs/heads/')
                or (run.get('repository') or {}).get('full_name')!=target['repository']
                or str(job.get('id'))!=target['job_id'] or str(job.get('run_id'))!=target['run_id']
                or job.get('name')!=target['job_name'] or job.get('head_sha')!=target['control_sha']
                or str(job.get('runner_id'))!=target['runner_id'] or job.get('status')!='completed'
                or job.get('conclusion') not in conclusions):
            raise ValueError('canonical GitHub metadata mismatch')


def _private_write(path,data):
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
    try:
        fd=os.open(str(path),flags,0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.read_bytes()!=data:
            raise ValueError('private receipt conflicts')
        return
    with os.fdopen(fd,'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    parent=os.open(str(path.parent),os.O_RDONLY)
    try:os.fsync(parent)
    finally:os.close(parent)


class ProductionEvidence:
    def __init__(self,export_root,private_root,profile,provider_capture):
        self.root=Path(export_root);self.private=Path(private_root)
        if profile not in PROFILES or not callable(provider_capture):raise ValueError('profile or capture missing')
        self.profile,self.provider_capture=profile,provider_capture

    def __call__(self,observation,required_artifacts):
        target=production.target({k:observation[k] for k in production.SCHEMAS[observation['provider']]})
        if target['provider'] not in ('gitlab','github') or observation.get('status') not in ('success','failed'):
            raise ValueError('unsupported terminal target')
        status=observation['status']
        names={'ordinary':'test-and-package','stable':'native-debugger-stable',
               'layers':'native-debugger-layers','unified':'native-unified'}
        expected_name='qualification' if target['provider']=='github' and self.profile=='ordinary' else names[self.profile]
        if target['job_name']!=expected_name or target['provider']=='github' and self.profile!='ordinary':
            raise ValueError('profile job mismatch')
        if not isinstance(required_artifacts,(list,tuple)) or not required_artifacts or len(set(required_artifacts))!=len(required_artifacts):
            raise ValueError('invalid artifact policy')
        if target['provider']=='gitlab':
            folder=self.root/target['pipeline_id']/target['job_id']
            ovh.verify_job_export(self.root,target['pipeline_id'],target['job_id'],target['source_sha'],target['job_name'],expected_job_status=status)
        else:
            folder=self.root/target['run_id']/target['run_attempt']/'qualification'/target['job_id']
        meta=_read(folder/'job.json');inventory_doc=_read(folder/'inventory.json')
        if target['provider']=='github':
            if (meta.get('schema')!='fdisbull-production-job-export-1' or meta.get('export_success') is not True
                    or meta.get('job_status')!=status or type(meta.get('qualification_exit_code')) is not int
                    or (meta['qualification_exit_code']==0)!=(status=='success')
                    or any(str(meta.get(k))!=str(target[k]) for k in target if k!='provider')):
                raise ValueError('github export identity mismatch')
            for name in ('candidate-start.json','caller-health.json','source-postcheck.json','inventory.json','qualification.log',
                         'system-preparation.json','system-preparation.log'):
                item=_regular(folder/name);record=meta.get(name)
                if (not isinstance(record,dict) or record.get('size')!=item.stat().st_size
                        or record.get('sha256')!=_digest(item)):raise ValueError('github control file mismatch')
            stage=meta.get('qualification_stage');preparation=_read(folder/'system-preparation.json')
            prep_status=preparation.get('status') if isinstance(preparation,dict) else None
            steps=preparation.get('steps') if isinstance(preparation,dict) else None
            if (stage not in ('policy-preflight','system-preparation','ordinary-tests')
                    or not isinstance(steps,list) or preparation.get('capture_limit_bytes')!=4*1024*1024
                    or (stage=='policy-preflight' and (prep_status!='skipped' or steps or status!='failed'))
                    or (stage=='system-preparation' and (prep_status!='failed' or not steps or status!='failed'))
                    or (stage=='ordinary-tests' and (prep_status!='passed' or not steps))):
                raise ValueError('qualification stage mismatch')
            start=_read(folder/'candidate-start.json')
            if (start.get('schema')!='fdisbull-github-candidate-start-1' or start.get('candidate_head')!=target['source_sha']
                    or start.get('control_head')!=target['control_sha']
                    or not isinstance(start.get('nonce'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',start['nonce'])
                    or any(str(start.get(k))!=str(target[k]) for k in target if k!='provider')):
                raise ValueError('github candidate binding mismatch')
            health=_read(folder/'caller-health.json')
            if not isinstance(health.get('target'),dict) or any(str(health['target'].get(k))!=str(target[k]) for k in target if k!='provider'):
                raise ValueError('github health identity mismatch')
        post=_read(folder/'source-postcheck.json')
        if (post.get('source_commit')!=target['source_sha'] or post.get('expected_source_commit')!=target['source_sha']
                or post.get('tracked_worktree_dirty') is not False or post.get('export_success') is not True):
            raise ValueError('source postcheck failed')
        exported=folder/'exported';inventory=_closed(exported,inventory_doc,meta.get('files'))
        if status=='failed':
            if target['provider']=='github':
                size=_regular(folder/'qualification.log').stat().st_size
                log=meta.get('log')
                if (size==0 or not isinstance(log,dict) or type(log.get('total_bytes')) is not int
                        or log.get('retained_bytes')!=size or log['total_bytes']<size
                        or type(log.get('truncated')) is not bool or log['truncated']!=(log['total_bytes']>size)):
                    raise ValueError('failed log missing or inconsistent')
            else:
                paths=('artifacts/ordinary/tests.log','artifacts/ordinary/required-contracts.log',
                       'artifacts/recovery/diagnostic.json','native-evidence/stable/tests.log',
                       'native-evidence/layers/tests.log','native-evidence/pe/tests.log','native-evidence/unified/tests.log')
                if not any(p in inventory and inventory[p]['size']>0 for p in paths):
                    raise ValueError('failed qualifier log or diagnostic missing')
        diagnostic=None
        diagnostic_path='artifacts/recovery/diagnostic.json'
        if status=='failed' and diagnostic_path in inventory:
            if target['provider']=='github' and meta.get('qualification_stage')!='policy-preflight':
                raise ValueError('diagnostic stage mismatch')
            diagnostic=_read(exported/diagnostic_path,limit=16384)
            if (not isinstance(diagnostic,dict)
                    or set(diagnostic)!={'kind','reason','input_key','expected_sha256','target'}
                    or diagnostic['target']!=target or diagnostic['kind'] not in ('infrastructure','source','blocked')
                    or any(not isinstance(diagnostic[k],str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',diagnostic[k])
                           for k in ('reason','input_key'))
                    or not isinstance(diagnostic['expected_sha256'],str)
                    or not re.fullmatch('[0-9a-f]{64}',diagnostic['expected_sha256'])):
                raise ValueError('diagnostic identity invalid')
        if (target['provider']=='github' and meta.get('qualification_stage')=='policy-preflight'
                and diagnostic is None):raise ValueError('preflight diagnostic missing')
        if status=='success':self._success(target,meta,exported,inventory,required_artifacts)
        capture=self.provider_capture(dict(observation))
        if (not isinstance(capture,dict) or capture.get('verified') is not True or capture.get('target')!=target
                or capture.get('job_status')!=status or not isinstance(capture.get('metadata'),dict)):
            raise ValueError('canonical provider capture unavailable')
        _provider_metadata(capture['metadata'],target,status)
        metadata=json.dumps(capture['metadata'],sort_keys=True,separators=(',',':')).encode()+b'\n'
        trace=capture.get('trace')
        if isinstance(trace,dict):
            if trace.get('encoding')!='base64':raise ValueError('invalid trace')
            try: raw=base64.b64decode(trace.get('data',''),validate=True)
            except (ValueError,TypeError):raise ValueError('invalid trace') from None
            if trace.get('size')!=len(raw) or trace.get('sha256')!=hashlib.sha256(raw).hexdigest():raise ValueError('trace mismatch')
            trace=raw
        if not isinstance(trace,bytes) or not trace or len(trace)>1024*1024 or len(metadata)>131072:
            raise ValueError('provider trace or metadata missing')
        self.private.mkdir(parents=True,exist_ok=True,mode=0o700)
        if any(p.is_symlink() for p in (self.private,*self.private.parents)) or self.private.stat().st_uid!=os.getuid() or self.private.stat().st_mode&0o077:
            raise ValueError('private state not protected')
        name=hashlib.sha256(json.dumps({'target':target,'status':status},sort_keys=True,separators=(',',':')).encode()).hexdigest()
        _private_write(self.private/(name+'.provider.json'),metadata)
        _private_write(self.private/(name+'.trace'),trace)
        receipt={'schema':'fdisbull-production-evidence-1','target':target,'job_status':status,
                 'export_job_sha256':_digest(folder/'job.json'),'inventory_sha256':_digest(folder/'inventory.json'),
                 'provider_metadata_sha256':hashlib.sha256(metadata).hexdigest(),'provider_trace_sha256':hashlib.sha256(trace).hexdigest()}
        receipt_path=self.private/(name+'.evidence.json')
        _private_write(receipt_path,(json.dumps(receipt,sort_keys=True,separators=(',',':'))+'\n').encode())
        result={'status':'export-verified','target':target,'job_status':status,'receipt_path':str(receipt_path),
                'host_export_verified':True,'closed_inventory_verified':True,'source_postcheck_verified':True,
                'provider_trace_verified':True}
        if diagnostic is not None:
            result.update(diagnostic=diagnostic,diagnostic_sha256=inventory[diagnostic_path]['sha256'])
        if status=='success':result.update(required_artifacts_verified=True,required_artifacts_receipt=str(receipt_path),verified_artifacts=list(required_artifacts))
        if target['provider']=='github':
            result['candidate_checkout']={k:target[k] for k in ('source_sha','control_sha','run_id','run_attempt','job_id')}
            result['candidate_checkout'].update(verified=True,receipt_path=str(receipt_path))
            result['failed_log_verified']=True
        return result

    def _success(self,target,meta,exported,inventory,required):
        filename,junits=PROFILES[self.profile];path='artifacts/receipts/'+filename
        if path not in inventory:raise ValueError('profile receipt missing')
        receipt=_read(exported/path);_identity(receipt,target,self.profile)
        tests=receipt.get('test_results');artifacts=receipt.get('artifacts')
        if (not isinstance(tests,list) or [x.get('path') for x in tests if isinstance(x,dict)]!=junits
                or not isinstance(artifacts,list) or not artifacts):raise ValueError('profile captures missing')
        for ref in [*tests,*artifacts]:
            if not isinstance(ref,dict) or not isinstance(ref.get('sha256'),str):raise ValueError('unhashed profile reference')
            _reference(ref,inventory,exported,meta.get('project_directory',''))
        for ref in ovh.references(receipt):_reference(ref,inventory,exported,meta.get('project_directory',''))
        for junit in junits:
            log='artifacts/ordinary/tests.log'
            summary=(exported/log if self.profile=='ordinary' and junit=='artifacts/ordinary/tests.xml'
                     and log in inventory else None)
            count=_junit(exported/junit,self.profile!='ordinary' or junit.endswith('required-contracts.xml'),summary_path=summary)
            if junit=='artifacts/ordinary/required-contracts.xml' and count!=26:
                raise ValueError('required contract count mismatch')
        if self.profile!='ordinary' and receipt.get('backend_identity',{}).get('source_commit')!=target['source_sha']:
            raise ValueError('native backend source mismatch')
        if self.profile=='ordinary':
            if set(required)!=ORDINARY:raise ValueError('ordinary artifact policy mismatch')
            payload_path='artifacts/receipts/package-payloads.json'
            if payload_path not in inventory:raise ValueError('package payload receipt missing')
            payload=_read(exported/payload_path)
            if payload.get('source_commit')!=target['source_sha'] or payload.get('tracked_worktree_dirty') is not False:
                raise ValueError('package payload identity mismatch')
            packages=payload.get('artifacts')
            if not isinstance(packages,dict) or set(packages)!={'core','player','sdist','tool'}:raise ValueError('package set mismatch')
            refs={x.get('path'):x for x in artifacts if isinstance(x,dict)}
            for item in packages.values():
                if not isinstance(item,dict) or not isinstance(item.get('name'),str) or '/' in item['name'] or item['name'] in ('','.','..'):
                    raise ValueError('package name invalid')
                name='dist/'+item['name'];entry=inventory.get(name)
                if (not entry or item.get('sha256')!=entry['sha256'] or item.get('size_bytes')!=entry['size']
                        or refs.get(name)!={'path':name,'sha256':entry['sha256'],'size':entry['size']}):raise ValueError('package byte mismatch')
        else:
            # Native logical IDs must map to actually verified receipt, JUnit, or output paths.
            allowed={path,*junits,*(_reference(x,inventory,exported,meta.get('project_directory','')) for x in artifacts)}
            if not set(required)<=allowed:raise ValueError('native artifact policy mismatch')
