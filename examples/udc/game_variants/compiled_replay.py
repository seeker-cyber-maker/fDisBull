"""Execute qualified authored game slices as generator-owned host C.

This is a bounded example of host execution, not original-game recovery or a
proof of compiler correctness. Each native invocation is checked against the
contract's independent shared-IL reference for the actual input.
"""
from copy import deepcopy
import ctypes
import hashlib
from pathlib import Path
import platform
import subprocess
import tempfile

from fdisbull.udc_blueprint import validate_module_uil
from fdisbull.udc_c import generate_c
from fdisbull.udc_layers import _execute_uil, _validate_layer, digest
from fdisbull.udc_qualify import qualify_uil

from . import five_dice, tic_tac_toe


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _compiler(path):
    if not path:
        raise ValueError('host replay requires an explicit clang executable')
    try:
        compiler = Path(path).expanduser().resolve(strict=True)
        before = _hash(compiler.read_bytes())
        probe = subprocess.run([str(compiler), '--version'], capture_output=True,
                               text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('clang compiler probe failed') from exc
    version = probe.stdout.splitlines()
    if not version or 'clang' not in version[0].lower():
        raise ValueError('host replay requires clang')
    return compiler, before, version[0]


def replay_compiled(project, selection_id, game, *, c_compiler, status=None,
                    player=None, seed=None):
    """Execute a persisted C-UIL selection with per-call model comparisons."""
    system, machine = platform.system(), platform.machine().lower()
    if not ((system == 'Darwin' and machine in ('arm64', 'aarch64')) or
            (system == 'Linux' and machine in ('x86_64', 'amd64', 'arm64', 'aarch64'))):
        raise ValueError('unsupported host for compiled replay')
    if game == 'tic-tac-toe':
        if type(status) is not int or not 0 <= status <= 255 or type(player) is not int or not 0 <= player <= 255:
            raise ValueError('status and player must be u8')
        expected_contract = tic_tac_toe.contract()
    elif game == 'five-dice':
        if type(seed) is not int or not 0 <= seed <= 65535:
            raise ValueError('seed must be u16')
        expected_contract = five_dice.contract()
    else:
        raise ValueError('unknown authored game slice')
    selected = project.udl_selection_info(selection_id, full=True)['document']
    program = selected.get('program')
    if game == 'tic-tac-toe':
        if program != expected_contract['behavior']['program'] or 'terminal' not in selected['bindings']:
            raise ValueError('selection is not the authored terminal program')
        bindings = ['terminal']
    else:
        validate_module_uil(project, program)
        if set(program['variables']) != {'$seed', *(f'$face{i}' for i in range(1, 6))} or any(v['type'] != 'u16' for v in program['variables'].values()):
            raise ValueError('unsupported Five-Dice state')
        if any(node['op'] not in ('invoke', 'set', 'remainder', 'add') for node in program['body']):
            raise ValueError('unsupported Five-Dice node')
        bindings = [n['binding'] for n in program['body'] if n['op'] == 'invoke']
        if len(bindings) != 5:
            raise ValueError('Five-Dice replay requires five invocations')
    # Check every selected execution layer and its exact contract before any
    # compilation or call, including repeated bindings with distinct nodes.
    modules = {}
    for binding in dict.fromkeys(bindings):
        if binding not in selected['bindings']:
            raise ValueError('module UIL binding is unselected')
        layer_id = selected['bindings'][binding]
        layer = project.udl_layer_info(layer_id, full=True)['document']
        contract = _validate_layer(project, layer)
        if {k: v for k, v in contract.items() if k != 'author'} != expected_contract or layer.get('domain') or contract.get('effects'):
            raise ValueError('selected layer does not use the exact authored contract')
        impl = deepcopy(layer['implementation'])
        if impl['backend'] != 'c-uil':
            raise ValueError('compiled replay requires c-uil layers')
        for side in ('inputs', 'outputs'):
            canonical = {p: '$' + p for p in contract[side]}
            if impl.get(side, canonical) != canonical:
                raise ValueError('compiled replay requires canonical ports')
        output = '$' + next(iter(contract['outputs']))
        if impl.get('return') not in (None, output):
            raise ValueError('unsupported compiled return')
        proof = qualify_uil(contract, {**impl, 'backend': 'uil'})
        if proof['status'] != 'equivalent_under_contract':
            raise ValueError('selected layer lacks UIL equivalence: ' + proof['status'])
        impl.pop('inputs', None)
        impl.pop('outputs', None)
        impl['return'] = output
        impl['state_adapter'] = {'inputs': ['$' + p for p in sorted(contract['inputs'])],
                                 'outputs': [output]}
        source, _, _ = generate_c(impl)
        modules[binding] = {'layer': layer_id, 'contract': layer['contract'],
                            'proof': proof, 'source': source}
    if game == 'five-dice':
        for node in program['body']:
            if node['op'] == 'invoke' and node['contract'] != modules[node['binding']]['contract']:
                raise ValueError('module invocation contract differs from selected layer')
    compiler, compiler_hash, version = _compiler(c_compiler)
    with tempfile.TemporaryDirectory(prefix='fdisbull-host-replay-') as tmp:
        root = Path(tmp)
        libraries = {}
        for index, (binding, module) in enumerate(modules.items()):
            src = root / f'module-{index}.c'
            lib = root / f'module-{index}.so'
            src.write_text(module['source'], encoding='utf-8')
            command = [str(compiler), '-std=c11', '-O1', '-fPIC',
                       '-dynamiclib' if system == 'Darwin' else '-shared', str(src), '-o', str(lib)]
            try:
                result = subprocess.run(command, capture_output=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError('host C compilation failed') from exc
            if result.returncode:
                raise ValueError('host C compilation failed: ' + result.stderr.decode(errors='replace')[:2000])
            module['source_sha256'] = _hash(module['source'].encode())
            module['library_sha256'] = _hash(lib.read_bytes())
            libraries[binding] = ctypes.CDLL(str(lib))
            function = libraries[binding].udc_block
            function.argtypes = (ctypes.POINTER(ctypes.c_ushort), ctypes.POINTER(ctypes.c_ushort))
            function.restype = ctypes.c_ulonglong
            module['function'] = function
        if _hash(compiler.read_bytes()) != compiler_hash:
            raise ValueError('clang changed during compilation')
        calls = []
        def invoke(binding, inputs):
            module = modules[binding]
            expected = _execute_uil(expected_contract['behavior'], expected_contract, inputs)
            names = sorted(expected_contract['inputs'])
            input_words = (ctypes.c_ushort * len(names))(*(inputs[n] for n in names))
            output_words = (ctypes.c_ushort * 1)()
            returned = module['function'](input_words, output_words)
            outputs = {next(iter(expected_contract['outputs'])): output_words[0]}
            if returned >> 32 or returned != output_words[0] or outputs != expected['outputs'] or expected['events']:
                raise ValueError('compiled invocation differs from reference UIL')
            receipt = {'binding': binding, 'layer': module['layer'], 'contract': module['contract'],
                       'inputs': dict(inputs), 'outputs': outputs, 'expected': expected,
                       'comparison': 'matched_reference_uil', 'execution': 'host-compiled-c',
                       'source_sha256': module['source_sha256'], 'library_sha256': module['library_sha256']}
            calls.append(receipt)
            return outputs
        result = {'status': 'complete', 'complete': True, 'execution': 'host-compiled-c',
                  'selection': selection_id, 'calls': calls,
                  'compiler': {'sha256': compiler_hash, 'version': version},
                  'modules': {b: {k: m[k] for k in ('layer', 'contract', 'proof', 'source_sha256', 'library_sha256')} for b, m in modules.items()}}
        if game == 'tic-tac-toe':
            result['outputs'] = invoke('terminal', {'status': status, 'player': player})
        else:
            state = {name: declaration['initial'] for name, declaration in program['variables'].items()}
            state['$seed'] = seed
            def value(item):
                return state[item['var']] if isinstance(item, dict) else item
            visited = []
            for node in program['body']:
                visited.append(node['id'])
                op = node['op']
                if op == 'invoke':
                    outputs = invoke(node['binding'], {k: value(v) for k, v in node['inputs'].items()})
                    for port, var in node['outputs'].items():
                        state[var] = outputs[port]
                else:
                    var, operand = node['var'], value(node['value'])
                    if op == 'set':
                        if not 0 <= operand <= 65535:
                            raise ValueError('module set value outside u16')
                        state[var] = operand
                    elif op == 'add':
                        state[var] = (state[var] + operand) & 65535
                    elif op == 'remainder':
                        if operand == 0:
                            raise ValueError('zero unsigned remainder divisor')
                        state[var] %= operand
            result.update(state=state, visited=visited, events=[], uil_sha256=digest(program))
        return result
