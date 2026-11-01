"""Optional project-bound PE64 debugging with a user-supplied IDA 9.4 server."""
import base64
import hashlib
from pathlib import Path
import time

from iced_x86 import Decoder

from .dosbox_rpc import DebuggerError
from .wine_debugger import PEDebugSession
from .wine_rpc import WineQemuRPC


class IDAQemuRPC(WineQemuRPC):
    protocol = 'fdisbull-ida-wine-qemu-1'

    @staticmethod
    def runtime_resources():
        from .ida_runtime import resources
        return resources()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.capabilities.update(backend='ida-wine-qemu', remote_interface=31,
            save_states=False, execution_layers=False, code_layers=['ram'],data_watchpoints=False, batch_trace=True,
            watchpoint_mechanism='IDA hardware/page breakpoints; stop semantics recorded per hit',
            breakpoint_guest_code_writes=False, guest_register_filters=False,
            execution_breakpoint_mechanism='IDA page protections; exact-PC filtering; guest instruction bytes unchanged')
        self.capabilities.pop('execution_layer_mechanism', None)
        self.capabilities.pop('native_state_format', None)


class IDAPEDebugSession(PEDebugSession):
    rpc_type = IDAQemuRPC
    backend_name = 'ida-wine-qemu'
    script_operations = PEDebugSession.script_operations - {'branch','save-state','load-state','save-anchor-stone','load-anchor-stone',
        'delta-start','delta-record','delta-status','delta-rewind','delta-recover'}

    def __init__(self, project, executable, game_dir, *, remote_server, state=None, **kwargs):
        if state is not None:
            raise ValueError('IDA native-state reconnection is not yet qualified; use wine-qemu for states')
        path = Path(remote_server).expanduser().resolve(strict=True)
        if not path.is_file() or not 1 <= path.stat().st_size <= 32*1024*1024:
            raise ValueError('Expected a user-supplied win64_remote.exe, at most 32 MiB')
        data = path.read_bytes()
        if data[:2] != b'MZ':
            raise ValueError('Expected a Windows IDA remote-server executable')
        self.engine_start = {'remote_server':dict(sha256=hashlib.sha256(data).hexdigest(),
                                                 data_base64=base64.b64encode(data).decode())}
        super().__init__(project, executable, game_dir, **kwargs)
        # Persist only the identity, never the server binary in the project.
        self.engine_start = None

    def _configure_pe_layers(self, params):
        if params['execute']:
            raise ValueError('Execution-only layers are not yet supported by the IDA endpoint')
        return super()._configure_pe_layers(params)

    def _trace_native(self, count, deadline):
        self._layer_setup()
        if self._execution or self._pending_exec or self.watchpoints:
            return super()._trace_native(count, deadline)
        remaining = int((deadline-time.monotonic())*1000)
        if remaining <= 0:
            return dict(events=[],complete=False,session=self._timeout_state())
        result = self.call('trace-batch', dict(count=count, timeout_ms=remaining), timeout_ms=remaining+15000)
        events = result.get('events')
        if not isinstance(events,list) or len(events)>count or type(result.get('complete')) is not bool:
            raise DebuggerError('Invalid bounded IDA trace response')
        if result['complete'] != (len(events)==count):
            raise DebuggerError('IDA trace completion disagrees with completed instruction count')
        for event in events:
            raw = bytes.fromhex(event['bytes'])
            if not 1<=len(raw)<=15 or event['registers']['rip']!=event['address']:
                raise DebuggerError('Invalid IDA pre-instruction evidence')
            instruction = Decoder(64,raw,ip=int(event['address'],16)).decode()
            if instruction.is_invalid:
                raise DebuggerError('Completed IDA instruction could not be decoded')
            data = raw[:instruction.len].hex()
            event.update(bytes=data,ram_bytes=data,execution_bytes=data,
                         active_layers=list(self._layers),layer_generation=self._layer_generation)
        return result

    def breakpoint(self,address,*,cs=None,access='x',length=1,view='static'):
        if access!='x':
            raise ValueError('IDA data-watch semantics are not yet qualified; use wine-qemu for PE data watches')
        return super().breakpoint(address,cs=cs,access=access,length=length,view=view)

    def memory(self, *args, **kwargs):
        result=super().memory(*args,**kwargs)
        result['view']='guest RAM; execution breakpoints do not substitute code bytes'
        return result

    def layer_patch(self, name, address, *, expected_hex, data_hex, kind='ram', activate=True):
        if kind != 'ram':
            raise ValueError('The IDA endpoint currently supports RAM layers only')
        return super().layer_patch(name,address,expected_hex=expected_hex,data_hex=data_hex,kind=kind,activate=activate)

    def _not_qualified(self, *args, **kwargs):
        raise ValueError('IDA native states and execution-only layers are not yet qualified; use wine-qemu')

    save_state = load_state = branch = _not_qualified
