#!/usr/bin/env python3
"""Fail-closed consumer acceptance of a relocated, complete offline kit.

Run with the kit's Python in a network namespace with only loopback, a read-only
kit, and an empty private writable workspace. Archive extraction is the caller's
responsibility; the archive hash is recorded independently in the receipt.
"""
import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import time
import socket
import struct
import subprocess
import sys
import stat
import zipfile
import tarfile


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def inventory(root):
    manifest_path = root / 'MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    entries = manifest['files']
    if not isinstance(entries, list) or not entries:
        raise ValueError('Manifest files must be a nonempty list')
    seen, roles = set(), {}
    for item in entries:
        name = item['destination']
        p = PurePosixPath(name)
        if not isinstance(name, str) or not name or p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')) or '\\' in name:
            raise ValueError('Unsafe manifest path')
        if name in seen:
            raise ValueError('Duplicate manifest path: ' + name)
        seen.add(name)
        path = root.joinpath(*p.parts)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('Missing, non-regular, or unsafe payload: ' + name)
        if type(item.get('size')) is not int or path.stat().st_size != item['size'] or digest(path) != item.get('sha256'):
            raise ValueError('Payload size/hash mismatch: ' + name)
        roles.setdefault(item.get('role'), []).append(path)
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Symlinks are not accepted: ' + str(path))
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(root).as_posix())
    if actual != seen:
        raise ValueError('Manifest inventory differs from payload')
    return manifest, roles


def required(roles, role):
    paths = roles.get(role, [])
    if len(paths) != 1:
        raise ValueError('Exactly one payload required for role: ' + role)
    return paths[0]


def verify_archive(archive, root):
    """Bind every extracted file to one safe, regular ZIP or tar member."""
    names = set()

    def validate(name, is_dir, is_file, size, stream_factory):
        name = name.rstrip('/') if is_dir else name
        parts = name.split('/')
        path = PurePosixPath(name)
        if not name or path.is_absolute() or any(p in ('', '.', '..') for p in parts) or '\\' in name:
            raise ValueError('Unsafe archive member')
        if name in names:
            raise ValueError('Duplicate archive member')
        names.add(name)
        if parts[0] != root.name:
            raise ValueError('Unexpected archive root')
        if is_dir:
            return
        if not is_file or len(parts) < 2:
            raise ValueError('Non-regular archive member')
        target = root.joinpath(*parts[1:])
        if not target.is_file() or target.is_symlink() or size != target.stat().st_size:
            raise ValueError('Archive member differs from extracted payload')
        h = hashlib.sha256()
        with stream_factory() as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        if h.hexdigest() != digest(target):
            raise ValueError('Archive member hash differs from extracted payload')

    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                mode = member.external_attr >> 16
                kind = stat.S_IFMT(mode)
                directory = member.is_dir()
                regular = kind in (0, stat.S_IFREG) and not directory
                if directory and kind not in (0, stat.S_IFDIR):
                    raise ValueError('Non-regular archive member')
                validate(member.filename, directory, regular, member.file_size,
                         lambda member=member: zipped.open(member))
    else:
        with tarfile.open(archive, 'r:*') as tar:
            for member in tar:
                validate(member.name, member.isdir(), member.isfile(), member.size,
                         lambda member=member: tar.extractfile(member))
    expected = {root.name + '/' + p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if not expected.issubset(names):
        raise ValueError('Extracted files absent from archive')


def private_library_path(root, path):
    return any(path.is_relative_to(root / prefix) for prefix in (
        'lib', 'python/lib/python3.13/site-packages', 'python/lib/python3.13/lib-dynload'))


def parse_loader_list(output, root):
    """Parse glibc ld.so --list output, rejecting unresolved or host paths."""
    libraries = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-fA-F]+\)', line):
            continue
        match = re.fullmatch(r'(\S+) => (\S+) \(0x[0-9a-fA-F]+\)', line)
        if match:
            name, path = match.groups()
            # glibc may print the executable's absolute PT_INTERP name while
            # resolving it to the explicitly selected private loader.
            if name == '/lib64/ld-linux-x86-64.so.2':
                if path != str(root / 'lib/ld-linux-x86-64.so.2'):
                    raise ValueError('Interpreter alias must resolve to the exact kit loader')
                name = 'ld-linux-x86-64.so.2'
            if '/' in name or name in libraries:
                raise ValueError('Invalid or duplicate loader dependency')
        else:
            match = re.fullmatch(r'(/\S+) \(0x[0-9a-fA-F]+\)', line)
            if not match:
                raise ValueError('Unrecognized or unresolved loader output: ' + line)
            path = match.group(1)
            name = Path(path).name
        resolved = Path(path).resolve()
        if not private_library_path(root, resolved) or not resolved.is_file():
            raise ValueError('Loader resolved dependency outside kit library paths: ' + path)
        if name in libraries and libraries[name] != resolved:
            raise ValueError('Conflicting loader dependency: ' + name)
        libraries[name] = resolved
    return libraries


def check_loader_closure(root, roles):
    loader = required(roles, 'loader')
    receipt = json.loads(required(roles, 'closure_receipt').read_text())
    if receipt.get('schema') != 'fdisbull-elf-closure-v1' or receipt.get('complete') is not True:
        raise ValueError('Invalid ELF closure receipt')
    objects = receipt.get('objects')
    if not isinstance(objects, list) or not objects:
        raise ValueError('Empty ELF closure receipt')
    files = {p.relative_to(root).as_posix() for paths in roles.values() for p in paths}
    actual_elf, headers = set(), {}
    entry_paths = {p.relative_to(root).as_posix() for role in ('python','loader','dosbox','qemu')
                   for p in roles.get(role, [])}
    firmware = {p.relative_to(root).as_posix() for p in roles.get('firmware', [])}
    for name in files:
        with (root / name).open('rb') as stream:
            header = stream.read(64)
        if header[:4] != b'\x7fELF':
            continue
        # QEMU's firmware directory includes guest-architecture ELF images. They
        # are hash-inventoried payloads, not host dynamic-loader dependencies.
        # Only a declared firmware file at this exact subtree is exempt.
        if name in firmware and name.startswith('native/qemu/share/qemu/'):
            continue
        actual_elf.add(name)
        headers[name] = header
    relocatable = {name for name, header in headers.items() if len(header) >= 20
        and int.from_bytes(header[16:18], 'big' if header[5:6] == b'\x02' else 'little') == 1}
    if relocatable & entry_paths:
        raise ValueError('Invalid or unexpected relocatable ELF entry role')
    seen = set()
    for obj in objects:
        name = obj.get('path')
        needed = obj.get('needed')
        if name not in actual_elf or name in seen or not isinstance(needed, dict):
            raise ValueError('Unknown, duplicate, or invalid closure object')
        seen.add(name)
        header = headers[name]
        if name in relocatable:
            # CPython's retained config object is ET_REL linker input, not a
            # loadable runtime object. Keep its hashed bytes without feeding it
            # to ld.so; no other relocatable payload receives this exemption.
            valid_build_object = (name == 'python/lib/python3.13/config-3.13-x86_64-linux-gnu/python.o'
                and not needed and name not in entry_paths and len(header) == 64
                and header[:7] == b'\x7fELF\x02\x01\x01'
                and header[16:24] == b'\x01\x00\x3e\x00\x01\x00\x00\x00'
                and header[24:40] == bytes(16) and header[52:58] == b'\x40\x00\x00\x00\x00\x00')
            if not valid_build_object:
                raise ValueError('Invalid or unexpected relocatable ELF payload: ' + name)
            continue
        for soname, target in needed.items():
            if not isinstance(soname, str) or not soname or '/' in soname or target not in actual_elf or not private_library_path(root, (root / target).resolve()) or PurePosixPath(target).name != soname:
                raise ValueError('Invalid declared dependency map')
        result = subprocess.run([str(loader), '--inhibit-cache', '--library-path', str(root / 'lib'), '--list', str(root / name)],
                                env={'PATH':str(root / 'bin')}, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError('Loader could not inspect ' + name + ': ' + result.stderr.strip())
        if result.stdout.strip() == 'statically linked':
            if needed:
                raise ValueError('Loader static result contradicts declared dependencies: ' + name)
            resolved = {}
        else:
            resolved = parse_loader_list(result.stdout, root)
        if any(path.relative_to(root).as_posix() not in actual_elf for path in resolved.values()):
            raise ValueError('Loader resolved an uninventoried or non-ELF library')
        for soname, target in needed.items():
            if resolved.get(soname) != (root / target).resolve():
                raise ValueError('Loader dependency differs from receipt: ' + name + ': ' + soname)
    if seen != actual_elf:
        raise ValueError('ELF closure does not cover every payload ELF')
    return len(seen)


def wait_for_pe_frame(debug, timeout_ms=15000):
    """Wait for the authored oracle's painted image while it remains stopped."""
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
        raise ValueError('Invalid frame readiness deadline')
    deadline = time.monotonic() + timeout_ms / 1000

    def remaining_ms():
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining < 1:
            raise ValueError('PE frame readiness deadline exceeded')
        return remaining

    while True:
        probe = debug.call('frame.probe', timeout_ms=remaining_ms())
        remaining_ms()
        if probe.get('available') is True:
            if not (type(probe.get('width')) is int and 1 <= probe['width'] <= 1920 and type(probe.get('height')) is int and 1 <= probe['height'] <= 1080):
                raise ValueError('Invalid PE frame dimensions')
            previous_deadline = getattr(debug, '_rpc_deadline', None)
            debug._rpc_deadline = min(deadline, previous_deadline) if previous_deadline is not None else deadline
            try:
                frame = debug.screenshot('pe.png')
            finally:
                debug._rpc_deadline = previous_deadline
            remaining_ms()
            row = debug.project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?', (frame['artifact'],)).fetchone()
            if row is None or hashlib.sha256(bytes(row['data'])).hexdigest() != row['sha256']:
                raise ValueError('Missing or corrupt PE screenshot artifact')
            from PIL import Image
            with Image.open(io.BytesIO(bytes(row['data']))) as image:
                extrema = image.convert('RGB').getextrema()
            remaining_ms()
            if any(low != high for low, high in extrema):
                return frame
        elif probe.get('available') is not False:
            raise ValueError('Invalid PE frame probe')
        # The oracle calls UpdateWindow before reaching its checkpoint. Never
        # resume the guest here: doing so would consume the intentional stop.
        time.sleep(min(0.1, remaining_ms() / 1000))


def confined(root, manifest):
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('Kit filesystem must be mounted read-only')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('Requires Linux x86-64')
    if {line.split(':', 1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:]} != {'lo'}:
        raise ValueError('Requires isolated network namespace with loopback only')
    if platform.python_version() != '3.13.5' or not Path(sys.executable).resolve().is_relative_to(root):
        raise ValueError('Must run bundled Python 3.13.5')
    if not Path(sys.prefix).resolve().is_relative_to(root):
        raise ValueError('Python prefix escaped kit')
    if os.environ.get('PYTHONHOME') != str(root / 'python'):
        raise ValueError('Python home is not bundled')
    for key in ('PYTHONPATH', 'LD_PRELOAD', 'LD_LIBRARY_PATH'):
        if os.environ.get(key):
            raise ValueError('Inherited environment could alter dependencies: ' + key)
    for item in sys.path:
        if not item or not Path(item).resolve().is_relative_to(root):
            raise ValueError('Python search path escaped kit')
    modules = ['fdisbull', 'fdisbull_player', 'z3', 'lief', 'PIL', 'capstone', 'iced_x86']
    optional = {'unicorn':'unicorn', 'dnfile':'dnfile', 'dncil':'dncil', 'pefile':'pefile', 'tree-sitter':'tree_sitter', 'tree-sitter-c':'tree_sitter_c', 'pycparser':'pycparser'}
    modules.extend(module for distribution, module in optional.items() if distribution in manifest.get('wheel_versions', {}))
    for name in modules:
        module = importlib.import_module(name)
        if not Path(module.__file__).resolve().is_relative_to(root):
            raise ValueError('Imported module outside kit: ' + name)
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) == 6 and fields[5].startswith('/'):
            mapped = Path(fields[5].removesuffix(' (deleted)')).resolve()
            if not mapped.is_relative_to(root):
                raise ValueError('Python mapped a file outside the kit: ' + str(mapped))



def windows_debugger(project, root, workspace, kernel, initramfs, *, full_windows=False):
    """Keep each included guest's explicit memory and cold-boot budget."""
    return project.debugger(root / 'bin/qemu', workspace, kernel=kernel, initramfs=initramfs,
                            memory_mib=8192 if full_windows else 4096, boot_timeout_ms=600000)


def verify_pe_oracle(project, root, workspace, kernel, initramfs, checkpoint, counter, *, full_windows=False):
    """Run the authored PE64 contract through the normal resource-bound guest."""
    with windows_debugger(project, root, workspace, kernel, initramfs, full_windows=full_windows) as debug:
        bp=debug.breakpoint(checkpoint)
        if not bp['bytes_verified'] or debug.run(timeout_ms=60000)['outcome'] != 'breakpoint': raise ValueError('PE breakpoint failed')
        if debug.memory(counter,length=4)['hex'] != '07000000': raise ValueError('PE memory failed')
        frame=wait_for_pe_frame(debug); trace=debug.trace('pe-trace.json',count=4,timeout_ms=20000)
        if not trace['metadata']['complete']: raise ValueError('PE trace incomplete')
        state=debug.save_state('pe.sav'); debug.click(80,80,mode_id=frame['metadata']['mode_id'])
        if debug.run(timeout_ms=30000)['outcome'] != 'breakpoint' or debug.memory(counter,length=4)['hex'] != '08000000': raise ValueError('PE click failed')
        debug.load_state(state['artifact'])
        if debug.memory(counter,length=4)['hex'] != '07000000': raise ValueError('PE native restore failed')
    return frame


def verify_windows_profiles(root, workspace, kernel, compact_runtime, windows_runtime, fixture):
    """Both delivered Wine images must execute; neither lane may be skipped."""
    from fdisbull.project import Project
    import lief
    binary=lief.PE.parse(str(fixture)); base=binary.optional_header.imagebase
    exports={entry.name:base+entry.address for entry in binary.get_export().entries}
    images={}
    for name, initramfs, full_windows in (('wine',compact_runtime,False), ('windows',windows_runtime,True)):
        private=workspace / name
        private.mkdir()
        # Each target/project/state belongs to its own writable consumer folder.
        pe=private/'oracle.exe';pe.write_bytes(fixture.read_bytes())
        with Project.create(private/'pe.fdb',pe) as project:
            project.analyze(start=exports['checkpoint'],max_instructions=64)
            images[name]=verify_pe_oracle(project,root,private,kernel,initramfs,
                                         exports['checkpoint'],exports['counter'],full_windows=full_windows)
    return images


def verify(root, workspace, archive):
    root, workspace, archive = root.resolve(), workspace.resolve(), archive.resolve()
    if root == workspace or root.is_relative_to(workspace) or workspace.is_relative_to(root):
        raise ValueError('Kit and workspace must be separate')
    if any(workspace.iterdir()):
        raise ValueError('Workspace must start empty')
    if archive.stat().st_size > 2_000_000_000:
        raise ValueError('Archive exceeds 2 GB limit')
    manifest, roles = inventory(root)
    verify_archive(archive, root)
    confined(root, manifest)
    for role in ('python', 'dosbox', 'qemu', 'kernel', 'runtime_base', 'runtime_recipe', 'runtime_preparer', 'windows_runtime_base', 'windows_runtime_recipe', 'pe_fixture'):
        required(roles, role)
    closure_objects = check_loader_closure(root, roles)
    for variable in ('HOME', 'TMPDIR', 'FDISBULL_TARGET_STORE', 'FDISBULL_OUTPUT_ARTIFACT_DIR'):
        os.environ[variable] = str(workspace / variable.lower())
        Path(os.environ[variable]).mkdir()
    os.environ['PATH'] = str(root / 'bin')
    preparer = required(roles, 'runtime_preparer')
    spec = importlib.util.spec_from_file_location('_chat_runtime_preparer', preparer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = module.prepare(root, workspace / 'runtime-cache')
    windows_runtime = Path(module.prepare_windows(root, workspace / 'windows-runtime-cache')).resolve(strict=True)
    if not windows_runtime.is_relative_to(workspace / 'windows-runtime-cache') or not windows_runtime.is_file():
        raise ValueError('Prepared Windows runtime escaped private cache')
    for profile in ('wine', 'dos'):
        path = Path(runtime[profile]).resolve(strict=True)
        if not path.is_relative_to(workspace / 'runtime-cache') or not path.is_file():
            raise ValueError('Prepared runtime escaped private cache')
    if Path(runtime['kernel']).resolve(strict=True) != required(roles, 'kernel'):
        raise ValueError('Prepared kernel differs from kit')
    from fdisbull.project import Project
    from fdisbull.proofs import check_equivalence
    from fdisbull_player import LiveSession, LocalRuntime
    import z3
    spec = {'format':'fdisbull-proof-1','scope':'authored offline acceptance','variables':{'x':8},'assumptions':[],
            'left':{'op':'add','args':[{'var':'x'},{'const':1,'width':8}]},'right':{'var':'x'}}
    if check_equivalence(spec)['status'] != 'counterexample': raise ValueError('Z3 counterexample missing')
    spec['right'] = spec['left']
    if check_equivalence(spec)['status'] != 'equivalent_under_assumptions': raise ValueError('Z3 equivalence missing')
    package={'format':'fdisbull-text-slice-1','state':{'count':0},'context':{'id':'room','title':'Room','description':'Fixture.'},'objects':[{'id':'lever','label':'lever','aliases':[],'description':'Lever.','verbs':['press']}], 'actions':[{'verb':'press','target':'lever','item':None,'steps':[{'ticks':1,'effects':[{'op':'add','key':'count','value':1}]}],'message':'Pressed.'}]}
    turn=LiveSession(LocalRuntime(package,workspace/'saves')).run_turn(['press lever'])
    resumed=LocalRuntime(package,workspace/'saves'); second=LiveSession(resumed).run_turn(['look'])
    if turn['checkpoint']['status'] != 'saved' or second['restore']['status'] != 'restored' or resumed.state['count'] != 1: raise ValueError('Player save/resume failed')
    cli = root / 'bin/fdisbull'
    if not cli.is_file(): raise ValueError('Missing bundled fdisbull entrypoint')
    for skill in ('fdisbull', 'write-gamefaqs-guide'):
        cmd=[str(cli),'agent-skill','--reference','SKILL.md']
        if skill != 'fdisbull': cmd += ['--skill',skill]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, timeout=30)
    code=bytes.fromhex('b81300cd100e1f30e4cd16a20001ebfe')+bytes(1024)
    header=bytearray(32);header[:2]=b'MZ';size=32+len(code)
    struct.pack_into('<13H',header,2,*[size%512,(size+511)//512,0,2,0,0xffff,0,0x400,0,0,0,0x1c,0])
    dos=workspace/'KEY.EXE';dos.write_bytes(header+code)
    with Project.create(workspace/'dos.fdb',dos) as project, project.debugger(root/'bin/dosbox',workspace) as debug:
        debug.run(guest_ms=100,timeout_ms=5000,fast_forward=True); state=debug.save_state('before.sav')
        debug.keyboard.press('a');debug.run(guest_ms=250,timeout_ms=5000,fast_forward=True)
        if debug.memory('1000:0100',length=1)['hex'] != '61': raise ValueError('DOS keyboard failed')
        dos_image=debug.screenshot('dos.png',hooks=False);debug.load_state(state['artifact'])
        if debug.memory('1000:0100',length=1)['hex'] != '00': raise ValueError('DOS restore failed')
    frames=verify_windows_profiles(root,workspace,required(roles,'kernel'),runtime['wine'],
                                  windows_runtime,required(roles,'pe_fixture'))
    return {'schema':'fdisbull-chat-consumer-verification-v1','status':'passed',
            'archive_sha256':digest(archive),'manifest_sha256':digest(root/'MANIFEST.json'),
            'source_commit':manifest.get('identities',{}).get('source_commit'),
            'test_source_commit':manifest.get('identities',{}).get('test_source_commit'),
            'runtime_sha256':{**{profile:digest(Path(runtime[profile])) for profile in ('wine','dos')},
                              'windows':digest(Path(windows_runtime))},
            'windows_native_qualification':{'status':'passed','scope':'authored PE64 oracle only',
                'memory_mib':8192,'pe32':'not-tested','win16':'not-tested',
                'checks':{name:True for name in ('breakpoint','memory','screenshot','trace','click','native_restore')},
                'screenshot_sha256':frames['windows']['sha256']},
            'elf_objects_checked':closure_objects,'python':platform.python_version(),
            'z3':z3.get_version_string(), 'network_interfaces':['lo'],
            'python_origin':'kit','python_mappings':'kit','loader_closure':'kit-lib',
            'skipped':0,'native_failures':0,
            'checks':{name:True for name in ('dos_screenshot','dos_keyboard','dos_restore',
                'pe_breakpoint','pe_memory','pe_screenshot','pe_click','pe_trace','pe_restore',
                'solver_counterexample','solver_equivalence','player_save','player_resume',
                'skill_fdisbull','skill_gamefaqs')},
            'dos_screenshot_sha256':dos_image['sha256'],'pe_screenshot_sha256':frames['wine']['sha256'],
            'profiles':['dos','wine','player','z3']}



def write_junit(path, error=None):
    import xml.etree.ElementTree as ET
    suite = ET.Element('testsuite', name='chat-offline-consumer', tests='1',
                       failures='1' if error is not None else '0', errors='0', skipped='0')
    case = ET.SubElement(suite, 'testcase', name='complete-offline-consumer')
    if error is not None:
        failure = ET.SubElement(case, 'failure', message=type(error).__name__)
        failure.text = str(error)
    ET.ElementTree(suite).write(path, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kit',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--junitxml',type=Path)
    a=p.parse_args()
    try:
        result=verify(a.kit,a.workspace,a.archive)
        a.output.write_text(json.dumps(result,indent=2)+'\n')
    except Exception as error:
        if a.junitxml: write_junit(a.junitxml,error)
        raise
    if a.junitxml: write_junit(a.junitxml)
    print(json.dumps(result))
