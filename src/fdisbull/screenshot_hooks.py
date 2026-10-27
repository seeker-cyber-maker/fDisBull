"""Persistent, bounded screenshot preparation with exception-safe layer cleanup."""
import hashlib
import json
import time
import uuid


DDL='''
CREATE TABLE IF NOT EXISTS debug_screenshot_hooks(
 id TEXT PRIMARY KEY, version INTEGER NOT NULL REFERENCES versions(id),
 created TEXT NOT NULL, sha256 TEXT NOT NULL, document TEXT NOT NULL);
'''

READ_AND_LAYERS={'assert','memory','code','registers','status','layer-stack','layer-enable'}


def validate_configuration(configuration):
    from .debug_script import validate_script
    from .debugger import bounded
    if not isinstance(configuration,dict) or set(configuration)-{'suspend_layers','pre','post','timeout_ms','require_fresh_frame'}:
        raise ValueError('Unsupported screenshot hook configuration field')
    config=json.loads(json.dumps(configuration,allow_nan=False))
    config.setdefault('suspend_layers',[]);config.setdefault('pre',[]);config.setdefault('post',[])
    config.setdefault('timeout_ms',10000)
    layers=config['suspend_layers']
    if not isinstance(layers,list) or len(layers)>64 or any(not isinstance(i,str) for i in layers) or len(set(layers))!=len(layers):
        raise ValueError('suspend_layers requires at most 64 unique layer IDs')
    bounded(config['timeout_ms'],'screenshot hook timeout_ms',1,60000)
    for phase in ('pre','post'):
        if not isinstance(config[phase],list):raise ValueError('Screenshot hook steps must be lists')
        if not config[phase]:continue
        steps=validate_script(dict(format='fdisbull-script-1',steps=config[phase]))
        if len(steps)>100:raise ValueError('Screenshot hooks allow at most 100 expanded steps per phase')
        for step in steps:
            if step['op'] not in READ_AND_LAYERS|({'run','wait'} if phase=='pre' else set()):
                raise ValueError('Unsupported screenshot '+phase+' hook operation: '+step['op'])
            if step['op']=='run':
                if 'guest_ms' not in step or step.get('expect','guest_time')!='guest_time' or step.get('stop_on_hook',True) is not True:
                    raise ValueError('Screenshot pre-hook runs require guest_ms and stop on unexpected boundaries')
                step['stop_on_hook']=True
        # Store the fully validated/expanded route, including forced hook stops.
        config[phase]=steps
    config.setdefault('require_fresh_frame',bool(layers) or any(s['op'] in ('layer-stack','layer-enable') for s in config['pre']))
    if type(config['require_fresh_frame']) is not bool:raise ValueError('require_fresh_frame must be boolean')
    return config


class ScreenshotHookProjectMixin:
    def debug_screenshot_hooks(self,configuration=None,*,version=None):
        from .project import now
        v=self.version(version)['id']
        if configuration is not None:
            if self.meta['format']!='MZ':raise ValueError('Screenshot hooks currently support DOS sessions')
            config=validate_configuration(configuration)
            for layer in config['suspend_layers']:
                if self.debug_layer_info(layer)['version']!=v:raise ValueError('Screenshot hook layer belongs to another version')
            document=json.dumps(config,sort_keys=True,separators=(',',':'),allow_nan=False)
            with self.transaction(True):
                self.db.execute('INSERT INTO debug_screenshot_hooks VALUES (?,?,?,?,?)',
                    (uuid.uuid4().hex,v,now(),hashlib.sha256(document.encode()).hexdigest(),document))
        row=self.db.execute('SELECT * FROM debug_screenshot_hooks WHERE version=? ORDER BY rowid DESC LIMIT 1',(v,)).fetchone()
        if row is None:return dict(version=v,configured=False,configuration=None)
        if hashlib.sha256(row['document'].encode()).hexdigest()!=row['sha256']:
            raise ValueError('Stored screenshot hook hash mismatch')
        config=validate_configuration(json.loads(row['document']))
        return dict(id=row['id'],version=v,created=row['created'],sha256=row['sha256'],
                    configured=True,configuration=config)


class ScreenshotHookError(ValueError):
    def __init__(self,result):
        super().__init__('Screenshot hook workflow failed; see preserved pre/post/restore evidence')
        self.result=result


class ScreenshotHookSessionMixin:
    def screenshot_hooks(self,configuration=None):
        if getattr(self,'_screenshot_hooks_running',False):raise ValueError('Cannot reconfigure hooks during screenshot capture')
        return self.project.debug_screenshot_hooks(configuration,version=self.version['id'])

    def _capture_with_hooks(self,capture,*,hooks=True):
        from .debug_script import execute_script
        if type(hooks) is not bool:raise ValueError('hooks must be boolean')
        if not hooks or getattr(self,'_screenshot_hooks_running',False):
            return capture(dict(bypassed='explicit' if not hooks else 'nested-diagnostic'))
        policy=self.screenshot_hooks()
        config=policy['configuration']
        if not policy['configured'] or not (config['pre'] or config['post'] or config['suspend_layers'] or config['require_fresh_frame']):
            return capture(None)
        original=self.layers()['active']
        report=dict(attempt=uuid.uuid4().hex,policy=policy['id'],policy_sha256=policy['sha256'],
                    original_layers=original,pre=None,post=None,capture=None,restore=None,errors=[],ok=False)
        deadline=time.monotonic()+config['timeout_ms']/1000
        self._screenshot_hooks_running=True
        barrier_stack=list(original)
        def frame_barrier():
            try:report['before_frame_id']=self.frame_probe([])['frame_id']
            except ValueError as error:
                if 'No complete framebuffer' not in str(error):raise
                report['before_frame_id']=None
        def after_pre_step(step,result):
            nonlocal barrier_stack
            if step['op'] in ('layer-stack','layer-enable') and result['active']!=barrier_stack:
                barrier_stack=list(result['active'])
                if config['require_fresh_frame']:frame_barrier()
        def phase(name):
            if not config[name]:return
            remaining=int((deadline-time.monotonic())*1000)
            if remaining<1:raise TimeoutError('Screenshot hook script budget expired')
            result=execute_script(self,dict(format='fdisbull-script-1',steps=config[name]),timeout_ms=remaining,
                bindings={'capture':dict(original_layers=original,suspended_layers=config['suspend_layers'])},
                _after_step=after_pre_step if name=='pre' else None)
            report[name]=result
            if not result['ok']:raise ValueError('Screenshot '+name+' hook failed')
        try:
            report['require_fresh_frame']=config['require_fresh_frame']
            report['before_frame_id']=None
            if config['require_fresh_frame']:frame_barrier()
            suspended=set(config['suspend_layers'])
            wanted=[i for i in original if i not in suspended]
            if wanted!=original:self.layers(wanted)
            barrier_stack=list(wanted)
            phase('pre')
            if time.monotonic()>=deadline:raise TimeoutError('Screenshot hook script budget expired before capture')
            report['capture_layers']=self.layers()['active']
            report['capture']=capture({k:report[k] for k in ('attempt','policy','policy_sha256','original_layers','capture_layers',
                                                           'require_fresh_frame','before_frame_id')})
        except Exception as error:
            report['errors'].append(dict(phase='pre-or-capture',type=type(error).__name__,message=str(error)))
        finally:
            try:phase('post')
            except Exception as error:
                report['errors'].append(dict(phase='post',type=type(error).__name__,message=str(error)))
            try:
                if self.layers()['active']!=original:self.layers(original)
                report['restore']=dict(ok=True,active=self.layers()['active'])
            except Exception as error:
                report['errors'].append(dict(phase='restore',type=type(error).__name__,message=str(error)))
                report['restore']=dict(ok=False)
                # An uncertain cleanup must never leave a resumable owned session.
                self.close()
            finally:self._screenshot_hooks_running=False
        report['ok']=not report['errors']
        self._event('screenshot-hooks',report)
        if not report['ok']:raise ScreenshotHookError(report)
        return dict(report['capture'],screenshot_hooks=report)
