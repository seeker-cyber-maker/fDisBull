"""Apple LLDB command-script driver for one bounded fDisBull observation.

Imported inside LLDB only; communicates one JSON receipt to the host wrapper.
It never attaches, continues, changes registers or writes target memory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import lldb


_CONFIG_KEY = 'FDISBULL_LLDB_OBSERVATION_CONFIG'


def _stop_reason(thread):
    reason = thread.GetStopReason()
    names = {
        lldb.eStopReasonBreakpoint: 'breakpoint',
        lldb.eStopReasonSignal: 'signal',
        lldb.eStopReasonException: 'exception',
        lldb.eStopReasonWatchpoint: 'watchpoint',
        lldb.eStopReasonTrace: 'trace',
        lldb.eStopReasonPlanComplete: 'plan_complete',
        lldb.eStopReasonNone: 'none',
        lldb.eStopReasonInvalid: 'invalid',
    }
    return {'kind': names.get(reason, f'unknown_{reason}'),
            'description': thread.GetStopDescription(256) or None,
            'data': [thread.GetStopReasonDataAtIndex(index)
                     for index in range(min(thread.GetStopReasonDataCount(), 16))]}


def _filespec_path(spec):
    directory, filename = spec.GetDirectory(), spec.GetFilename()
    return str(Path(directory) / filename) if directory and filename else filename


def _main_image(target):
    executable = _filespec_path(target.GetExecutable())
    module = None
    for index in range(min(target.GetNumModules(), 4096)):
        candidate = target.GetModuleAtIndex(index)
        if _filespec_path(candidate.GetFileSpec()) == executable:
            module = candidate
            break
    if module is None and target.GetNumModules():
        module = target.GetModuleAtIndex(0)
    if module is None or not module.IsValid():
        return None
    header = module.GetObjectFileHeaderAddress()
    file_base = header.GetFileAddress() if header.IsValid() else lldb.LLDB_INVALID_ADDRESS
    load_base = header.GetLoadAddress(target) if header.IsValid() else lldb.LLDB_INVALID_ADDRESS
    if file_base == lldb.LLDB_INVALID_ADDRESS:
        file_base = None
    if load_base == lldb.LLDB_INVALID_ADDRESS:
        load_base = None
    sections = []
    for index in range(min(module.GetNumSections(), 64)):
        section = module.GetSectionAtIndex(index)
        address = section.GetLoadAddress(target)
        if address == lldb.LLDB_INVALID_ADDRESS:
            continue
        sections.append({'name': section.GetName(), 'load_address': address,
                         'file_address': section.GetFileAddress(), 'size': section.GetByteSize()})
    return {'path': _filespec_path(module.GetFileSpec()), 'uuid': module.GetUUIDString(),
            'file_base': file_base, 'load_base': load_base,
            'slide': load_base - file_base if load_base is not None and file_base is not None else None,
            'mapped_sections': sections}


def _registers(frame):
    result = {}
    allowed = {f'x{index}' for index in range(29)} | {'fp', 'lr', 'sp', 'pc', 'cpsr'}
    for group in frame.GetRegisters():
        for register in group:
            name = register.GetName()
            if name in allowed and name not in result:
                result[name] = register.GetValue()
        if len(result) >= len(allowed):
            break
    return result


def _memory(process, address, count):
    if not count:
        return {'status': 'not_requested'}
    error = lldb.SBError()
    data = process.ReadMemory(address, count, error)
    if not error.Success():
        return {'status': 'unavailable', 'reason': error.GetCString()}
    return {'status': 'ok', 'runtime_address': address, 'size': len(data), 'hex': data.hex()}


def _instructions(target, address, count):
    if not count:
        return {'status': 'not_requested'}
    try:
        decoded = target.ReadInstructions(target.ResolveLoadAddress(address), count)
        items = []
        for index in range(min(decoded.GetSize(), count)):
            instruction = decoded.GetInstructionAtIndex(index)
            items.append({'runtime_address': instruction.GetAddress().GetLoadAddress(target),
                          'mnemonic': instruction.GetMnemonic(target),
                          'operands': instruction.GetOperands(target),
                          'comment': instruction.GetComment(target) or None})
        return {'status': 'ok' if items else 'unavailable', 'instructions': items}
    except Exception as exc:
        return {'status': 'unavailable', 'reason': str(exc)}


def _observe(debugger, config):
    debugger.SetAsync(False)
    # LLDB otherwise commonly disables ASLR, which would hide the ordinary
    # runtime slide that the receipt is intended to preserve.
    settings = lldb.SBCommandReturnObject()
    debugger.GetCommandInterpreter().HandleCommand('settings set target.disable-aslr false', settings)
    if not settings.Succeeded():
        return {'status': 'error', 'reason': 'LLDB could not enable normal ASLR for the target'}
    target = debugger.CreateTargetWithFileAndArch(config['executable'], 'arm64')
    if not target or not target.IsValid():
        return {'status': 'unsupported', 'reason': 'LLDB could not create an arm64 target'}
    if not target.GetTriple().startswith('arm64'):
        return {'status': 'unsupported', 'reason': f'LLDB selected {target.GetTriple()}, not arm64'}
    breakpoint = target.BreakpointCreateByName(config['symbol'])
    if not breakpoint.IsValid() or breakpoint.GetNumLocations() == 0:
        return {'status': 'unresolved_breakpoint', 'reason': 'symbol did not resolve in the target before launch'}

    launch = lldb.SBLaunchInfo(config['argv'])
    launch.SetWorkingDirectory(str(Path(config['executable']).parent))
    launch.SetLaunchFlags(launch.GetLaunchFlags() & ~lldb.eLaunchFlagDisableASLR)
    # The LLDB subprocess receives a private config path for this command
    # script. The observed program must not inherit that path or any future
    # command-script credentials. Give it a separate, explicit environment.
    target_environment = [f'{key}={os.environ[key]}' for key in (
        'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER', 'SHELL',
    ) if key in os.environ]
    launch.SetEnvironmentEntries(target_environment, False)
    error = lldb.SBError()
    process = target.Launch(launch, error)
    if not error.Success() or not process or not process.IsValid():
        message = error.GetCString() or 'LLDB launch failed without a diagnostic'
        denied = any(token in message.lower() for token in
                     ('permission denied', 'operation not permitted', 'not allowed', 'not permitted'))
        return {'status': 'permission_denied' if denied else 'error', 'reason': message}
    try:
        runtime = {'pid': process.GetProcessID(), 'target_triple': target.GetTriple(),
                   'lldb_version': lldb.SBDebugger.GetVersionString(),
                   'process_state': lldb.SBDebugger.StateAsCString(process.GetState()),
                   'main_image': _main_image(target)}
        if process.GetState() == lldb.eStateExited:
            runtime['exit_status'] = process.GetExitStatus()
            return {'status': 'exited_without_breakpoint', 'runtime': runtime,
                    'reason': 'target exited before the requested breakpoint'}
        if process.GetState() != lldb.eStateStopped:
            return {'status': 'unexpected_stop', 'runtime': runtime,
                    'reason': 'target did not stop at a debugger-visible state'}
        threads = [process.GetThreadAtIndex(index) for index in range(min(process.GetNumThreads(), 64))]
        thread = next((item for item in threads if item.GetStopReason() == lldb.eStopReasonBreakpoint),
                      process.GetSelectedThread())
        if not thread or not thread.IsValid():
            return {'status': 'unexpected_stop', 'runtime': runtime, 'reason': 'no selected stop thread'}
        stop = _stop_reason(thread)
        frame = thread.GetFrameAtIndex(0)
        if not frame or not frame.IsValid():
            return {'status': 'unexpected_stop', 'runtime': runtime, 'stop_reason': stop,
                    'reason': 'stopped thread has no frame'}
        pc = frame.GetPC()
        address = target.ResolveLoadAddress(pc)
        main_image = runtime['main_image'] or {}
        module = address.GetModule() if address.IsValid() else None
        same_image = bool(module and module.IsValid() and main_image.get('uuid') and
                          module.GetUUIDString() == main_image['uuid'])
        runtime.update({'thread_id': thread.GetThreadID(), 'stop_reason': stop,
                        'pc_runtime': pc, 'pc_static_va': address.GetFileAddress() if same_image else None,
                        'registers': _registers(frame),
                        'memory': _memory(process, pc, config['memory_bytes']),
                        'disassembly': _instructions(target, pc, config['instruction_count'])})
        if stop['kind'] != 'breakpoint' or not stop['data'] or stop['data'][0] != breakpoint.GetID():
            return {'status': 'unexpected_stop', 'runtime': runtime,
                    'reason': 'target stopped for a reason other than the requested breakpoint'}
        return {'status': 'ok', 'runtime': runtime}
    finally:
        # LLDB owns this process because this script launched it. No attach path.
        if process.IsValid() and process.GetState() not in (lldb.eStateExited, lldb.eStateDetached):
            process.Kill()


def __lldb_init_module(debugger, internal_dict):
    config_path = os.environ.get(_CONFIG_KEY)
    if not config_path:
        return
    config = json.loads(Path(config_path).read_text(encoding='utf-8'))
    try:
        receipt = _observe(debugger, config)
    except Exception as exc:
        receipt = {'status': 'error', 'reason': f'LLDB Python observation failed: {type(exc).__name__}: {exc}'}
    Path(config['result_path']).write_text(json.dumps(receipt), encoding='utf-8')
