"""Installed, disposable native-QEMU core acceptance without a supplied OS."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import sys
import tempfile


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _boot_fixture():
    # BIOS enters at 7c00. Normalize CS:IP to 07c0:0006, initialize segments
    # and stack, print QF through VGA RAM, initialize [5000] to seven and loop.
    # This authored sector contains no DOS kernel, interrupt shim or hostcall.
    code = bytes.fromhex(
        'faea0600c00731c08ed88ed0bc007cb800b88ec031ffb8511fabb8461fab'
        '31c08ed8c70600500700b85713bb6824')
    loop = 0x7c00 + len(code)
    code += bytes.fromhex('ff06005090ebf9')
    return (code.ljust(510, b'\0') + b'\x55\xaa').ljust(1440 * 1024, b'\0'), loop


def doctor_qemu(*, executable, output=None, boot_timeout_ms=30000,
                qemu_transport='unix', qemu_firmware=None):
    """Qualify the native core on an authored boot sector, never DOS itself.

    All images, RAM and the private project are temporary. An explicit new
    output directory retains only a receipt, the authored trace and an optional
    PNG. A build without screendump can pass the core while graphics remains
    unavailable; that limitation is separate in the receipt.
    """
    from . import __version__
    destination = None
    if output is not None:
        destination = Path(output).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=False)
    report = dict(format='fdisbull-doctor-1', version=__version__, backend='qemu-dos',
                  status='running', python=platform.python_version(), platform=sys.platform,
                  architecture=platform.machine(), checks=[], artifacts={},
                  native_state_restored=False, guest_os_validation='not_run',
                  graphics=dict(status='not_run'),
                  scope='Authored bare-metal PC fixture; finite native core acceptance. '
                        'No DOS, QEMM, DESQview, Windows, game, checkpoint or timing-parity qualification.')
    spawned = []

    def step(name, action):
        check = dict(name=name, status='running')
        report['checks'].append(check)
        try:
            value = action()
        except Exception as error:
            check.update(status='failed', error=type(error).__name__ + ': ' + str(error))
            raise
        check['status'] = 'passed'
        return value

    try:
        def inputs():
            if qemu_transport not in ('unix', 'pipe'):
                raise ValueError('qemu_transport must be unix or pipe')
            if type(boot_timeout_ms) is not int or not 1 <= boot_timeout_ms <= 600000:
                raise ValueError('boot_timeout_ms must be an integer in 1..600000')
            with Path(executable).expanduser().open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest()
        report['input_sha256'] = {'executable': step('backend input admission', inputs)}
        from .dosbox_rpc import DebuggerError
        from .project import Project
        with tempfile.TemporaryDirectory(prefix='fdisbull-qemu-doctor-', dir='/tmp') as temporary:
            root = Path(temporary)
            binary = root / 'AUTHORED.img'
            raw, loop = _boot_fixture()
            binary.write_bytes(raw)
            report['authored_target_sha256'] = hashlib.sha256(raw).hexdigest()
            database = root / 'private.fdb'
            artifacts = {}
            with Project.create(database, binary, arch='x86', bits=32,
                                base=0x7c00, entry=0x7c00) as project:
                with step('launch native QEMU', lambda: project.debugger(
                        executable, root, backend='qemu-dos', boot_timeout_ms=boot_timeout_ms,
                        qemu_transport=qemu_transport, qemu_firmware=qemu_firmware,
                        _on_spawn=spawned.append)) as debug:
                    report['runtime_inputs'] = debug.vm.inputs
                    report['capabilities'] = dict(debug.capabilities)
                    report['observation_contract'] = debug.status()['semantics']

                    def reach_loop():
                        point = debug.breakpoint(loop)
                        stopped = debug.run(timeout_ms=min(boot_timeout_ms, 15000))
                        _require(stopped['outcome'] == 'breakpoint', 'Authored boot loop was not reached')
                        debug.delete_breakpoint(point['breakpoint_id'])
                        registers = debug.registers()
                        _require(registers['cpu_mode'] == 'real'
                                 and registers['address_state']['code_bits'] == 16
                                 and int(registers['registers']['cs'], 16) == 0x7c0
                                 and int(registers['instruction_pointer'], 16) == loop-0x7c00
                                 and int(registers['linear_pc'], 16) == loop,
                                 'Nonzero real-mode CS:IP was not observed correctly')
                        return registers
                    registers = step('native breakpoint and real-mode address context', reach_loop)

                    def edit():
                        for space in ('physical', 'virtual'):
                            _require(debug.memory(0x5000, length=2, space=space)['hex'] == '0700',
                                     'Authored counter was not initialized')
                        try:
                            debug.write_memory(0x5000, '2900', expected_hex='0800')
                        except DebuggerError:
                            pass
                        else:
                            raise RuntimeError('Stale memory guard was accepted')
                        _require(debug.registers()['linear_pc'] == hex(loop), 'Rejected edit advanced the CPU')
                        general = 'rax' if 'rax' in registers['registers'] else 'eax'
                        debug.write_registers({general: {'expected': 0x1357, 'value': 0x1234}})
                        _require(int(debug.registers()['registers'][general], 16) == 0x1234,
                                 'Register edit readback differs')
                        debug.write_memory(0x5000, '2900', expected_hex='0700')
                    step('guarded registers and physical/virtual memory', edit)

                    def trace():
                        artifact = debug.trace('trace.json', count=3, timeout_ms=5000)
                        _require(artifact['metadata']['complete'], 'Authored trace is incomplete')
                        _require(debug.memory(0x5000, length=2)['hex'] == '2a00',
                                 'The traced INC did not complete')
                        artifacts['trace.json'] = artifact['artifact']
                    step('bounded completed-step trace', trace)

                    def watch():
                        point = debug.breakpoint(0x5000, access='w', length=2)
                        stopped = debug.run(timeout_ms=1000)
                        _require(stopped['outcome'] == 'watchpoint'
                                 and point['breakpoint_id'] in stopped['session']['stop_reason']['breakpoint_ids'],
                                 'Native write watchpoint did not stop')
                        debug.delete_breakpoint(point['breakpoint_id'])
                    step('native data watchpoint', watch)

                    def timeout():
                        stopped = debug.run(timeout_ms=40)
                        _require(stopped['outcome'] == 'timeout' and stopped['timed_out']
                                 and debug.status()['state'] == 'stopped', 'Continue did not stop on its deadline')
                        _require(debug.step(timeout_ms=1000)['outcome'] == 'step',
                                 'Control could not step after the timeout')
                    step('bounded continue and post-timeout control', timeout)
                    if debug.capabilities.get('screenshot'):
                        frame = step('stored display surface', lambda: debug.screenshot('frame.png'))
                        artifacts['frame.png'] = frame['artifact']
                        report['graphics'] = dict(status='passed', scope='QEMU stored display surface; no frame-timing parity')
                    else:
                        report['graphics'] = dict(status='unavailable', reason='Selected QEMU does not advertise screendump')
            with Project(database) as reopened:
                def export():
                    for name, artifact in artifacts.items():
                        path = (destination or root) / name
                        reopened.debug_export(artifact, path)
                        data = path.read_bytes()
                        report['artifacts'][name] = dict(sha256=hashlib.sha256(data).hexdigest(),
                                                       bytes=len(data), retained=destination is not None)
                    trace = json.loads(((destination or root) / 'trace.json').read_text())
                    _require([event['bytes'] for event in trace['events']] == ['ff060050', '90', 'ebf9'],
                             'Stored trace is not the authored instruction sequence')
                    _require(all(event['observation']['instruction_completed'] is True for event in trace['events']),
                             'Stored trace does not establish completed instructions')
                    if 'frame.png' in artifacts:
                        from PIL import Image
                        with Image.open((destination or root) / 'frame.png') as image:
                            _require(image.format == 'PNG' and image.width > 0 and image.height > 0,
                                     'Stored screenshot is not a nonempty PNG')
                            image.verify()
                step('reopen project and export JSON/PNG evidence', export)
            step('source-image isolation', lambda: _require(
                hashlib.sha256(binary.read_bytes()).hexdigest() == report['authored_target_sha256'],
                'Authored source image changed'))
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        if not report['checks'] or report['checks'][-1]['status'] != 'failed':
            report['checks'].append(dict(name='acceptance assertions', status='failed',
                                         error=type(error).__name__ + ': ' + str(error)))
    finally:
        # The backend owns normal cleanup. Catch any remaining owned child even
        # after failed startup, and record forced cleanup as a failed check.
        leaked = [process for process in spawned if process.poll() is None]
        for process in leaked:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()
                process.wait(timeout=3)
        report['process_cleanup'] = dict(spawned=len(spawned), reaped=all(p.poll() is not None for p in spawned),
                                         forced=bool(leaked))
        if leaked:
            report['status'] = 'failed'
            report['checks'].append(dict(name='owned process cleanup', status='failed',
                                         error='Doctor had to reap a child left running by the backend'))
        elif spawned:
            report['checks'].append(dict(name='owned process cleanup', status='passed'))
    if destination:
        (destination / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    return report
