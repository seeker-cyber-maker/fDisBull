"""The existing DOS session API transported into an owned offline QEMU guest."""
import base64
import hashlib
import json
from pathlib import Path

from .debugger import DebugSession, bounded
from .dosbox_rpc import DebuggerError
from .guest_assets import uploads
from .wine_rpc import WineQemuRPC


class DOSQemuRPC(WineQemuRPC):
    protocol='fdisbull-dosbox-qemu-1'
    agent_resource=None

    @staticmethod
    def runtime_resources():
        from .dos_runtime import resources
        return resources()

    def __init__(self,executable,game_dir,*,kernel,initramfs,files,target,boot_timeout_ms,on_spawn=None):
        super().__init__(executable,kernel,initramfs,boot_timeout_ms=boot_timeout_ms,on_spawn=on_spawn)
        try:
            self.started=self._bridge('dos.start',dict(files=files,target=target),timeout_ms=300000)
            self.capabilities=self.started['capabilities']
        except BaseException:self.close();raise

    def _bridge(self,method,params=None,**kwargs):return super().call(method,params,**kwargs)

    def call(self,method,params=None,timeout_ms=15000):
        params=dict(params or {})
        if method=='state.save':
            path=Path(params.pop('path'))
            if path.exists():raise ValueError('State output already exists')
            result=self._bridge('dos.save',dict(params=params),timeout_ms=150000)
            data=base64.b64decode(result['data_base64'],validate=True)
            if len(data)>64*1024*1024 or hashlib.sha256(data).hexdigest()!=result['sha256']:self.close();raise DebuggerError('State download budget/hash mismatch')
            with path.open('xb') as stream:stream.write(data)
            return result['native']
        if method=='state.load':
            path=Path(params.pop('path'))
            if path.is_symlink() or not path.is_file() or not 1<=path.stat().st_size<=64*1024*1024:raise ValueError('Invalid native DOS state input')
            data=path.read_bytes()
            return self._bridge('dos.load',dict(params=params,data_base64=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest()),timeout_ms=150000)
        result=self._bridge('dos.rpc',dict(method=method,params=params,timeout_ms=timeout_ms),timeout_ms=timeout_ms+15000)
        if 'rejected' in result:raise DebuggerError(result['rejected'])
        return result['native']


class DOSQemuSession(DebugSession):
    def __init__(self,project,executable,game_dir,*,kernel,initramfs,version=None,files=None,boot_timeout_ms=240000,_on_spawn=None):
        bounded(boot_timeout_ms,'boot_timeout_ms',1000,600000)
        self._transport_options=dict(kernel=kernel,initramfs=initramfs,files=uploads(project,game_dir,project.meta['filename'],files),
                                     target=project.meta['filename'],boot_timeout_ms=boot_timeout_ms,on_spawn=_on_spawn)
        super().__init__(project,executable,game_dir,version=version,_on_spawn=_on_spawn)

    def _open_rpc(self,executable,game_dir):return DOSQemuRPC(executable,game_dir,**self._transport_options)

    def _transport_metadata(self):
        return dict(backend='dosbox-qemu',runtime_profile='dosbox-qemu-real-normal-v1',runtime_inputs=self.rpc.inputs,
                    emulator_sha256=self.rpc.hello['emulator_sha256'],guest_kernel=self.rpc.hello['guest_kernel'],
                    target_pid=self.rpc.started['pid'],files=[dict(path=f['path'],sha256=f['sha256']) for f in self._transport_options['files']],
                    state_scope='DOSBox CPU/devices; guest files checked separately')

    def _disk_manifest(self):return self.rpc._bridge('dos.manifest')['files']

    def load_state(self,artifact):
        row=self.project.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?',(artifact,)).fetchone()
        if row is not None:
            saved=json.loads(row[0])
            for name,item in self.rpc.inputs.items():
                if saved.get('runtime_inputs',{}).get(name,{}).get('sha256')!=item['sha256']:
                    raise ValueError('State runtime compatibility mismatch: '+name)
        return super().load_state(artifact)
