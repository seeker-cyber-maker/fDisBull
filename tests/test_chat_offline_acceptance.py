"""Small fail-closed checks; native acceptance requires the isolated kit run."""
import hashlib
import importlib.util
import io
import inspect
import json
from pathlib import Path
import sqlite3
import tarfile

import pytest

spec = importlib.util.spec_from_file_location('chat_offline_acceptance', Path(__file__).parents[1] / 'scripts/verify_chat_offline_kit.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def kit(tmp_path):
    root = tmp_path / 'kit'; root.mkdir()
    (root / 'item').write_bytes(b'payload')
    entry = {'destination':'item','size':7,'sha256':hashlib.sha256(b'payload').hexdigest(),'role':'example'}
    (root / 'MANIFEST.json').write_text(json.dumps({'files':[entry]}))
    return root, entry


def test_inventory_checks_hash_size_and_complete_coverage(tmp_path):
    root, entry = kit(tmp_path)
    _, roles = verifier.inventory(root)
    assert verifier.required(roles, 'example') == root / 'item'
    with pytest.raises(ValueError, match='Exactly one'):
        verifier.required(roles, 'missing')
    (root / 'extra').write_bytes(b'x')
    with pytest.raises(ValueError, match='inventory'):
        verifier.inventory(root)
    (root / 'extra').unlink()
    (root / 'item').write_bytes(b'changed')
    with pytest.raises(ValueError, match='size/hash'):
        verifier.inventory(root)


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'a/../item', 'a//item', 'a\\item'])
def test_inventory_rejects_unsafe_paths(tmp_path, name):
    root, entry = kit(tmp_path); entry['destination'] = name
    (root / 'MANIFEST.json').write_text(json.dumps({'files':[entry]}))
    with pytest.raises(ValueError, match='Unsafe'):
        verifier.inventory(root)


def test_inventory_rejects_duplicates_and_symlinks(tmp_path):
    root, entry = kit(tmp_path)
    (root / 'MANIFEST.json').write_text(json.dumps({'files':[entry,entry]}))
    with pytest.raises(ValueError, match='Duplicate'):
        verifier.inventory(root)
    (root / 'MANIFEST.json').write_text(json.dumps({'files':[entry]}))
    (root / 'item').unlink(); (root / 'item').symlink_to('/etc/passwd')
    with pytest.raises(ValueError, match='unsafe'):
        verifier.inventory(root)


def test_archive_is_bound_to_extracted_files(tmp_path):
    root, _ = kit(tmp_path); archive = tmp_path / 'kit.tar'
    with tarfile.open(archive, 'w') as tar:
        tar.add(root, arcname=root.name)
    verifier.verify_archive(archive, root)
    (root / 'item').write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs'):
        verifier.verify_archive(archive, root)


def test_loader_list_parses_real_glibc_form_and_rejects_host_or_missing(tmp_path):
    root = tmp_path / 'kit'; lib = root / 'lib'; lib.mkdir(parents=True)
    (lib / 'libc.so.6').write_bytes(b'x'); (lib / 'ld-linux.so.2').write_bytes(b'x')
    output = f'''linux-vdso.so.1 (0x00007ff000)
        libc.so.6 => {lib}/libc.so.6 (0x00007aa000)
        {lib}/ld-linux.so.2 (0x00007bb000)
'''
    assert verifier.parse_loader_list(output, root)['libc.so.6'] == lib / 'libc.so.6'
    with pytest.raises(ValueError, match='outside kit'):
        verifier.parse_loader_list('libc.so.6 => /usr/lib/libc.so.6 (0x1234)', root)
    with pytest.raises(ValueError, match='unresolved'):
        verifier.parse_loader_list('libfoo.so => not found', root)


def interpreter_alias_kit(tmp_path):
    root=tmp_path/'kit';(root/'lib').mkdir(parents=True)
    loader=root/'lib/ld-linux-x86-64.so.2';loader.write_bytes(b'\x7fELFloader')
    return root,loader


def test_loader_list_normalizes_exact_private_interpreter_alias(tmp_path):
    root,loader=interpreter_alias_kit(tmp_path)
    line=f'/lib64/ld-linux-x86-64.so.2 => {loader} (0x00007fff0010)\n'
    assert verifier.parse_loader_list(line,root)=={'ld-linux-x86-64.so.2':loader}


@pytest.mark.parametrize('target', ['/lib64/ld-linux-x86-64.so.2','/usr/lib/ld-linux-x86-64.so.2'])
def test_loader_list_rejects_interpreter_alias_resolving_to_host(tmp_path,target):
    root,_=interpreter_alias_kit(tmp_path)
    with pytest.raises(ValueError,match='exact kit loader'):
        verifier.parse_loader_list(f'/lib64/ld-linux-x86-64.so.2 => {target} (0x1234)',root)


def test_loader_list_rejects_interpreter_alias_to_another_private_file(tmp_path):
    root,_=interpreter_alias_kit(tmp_path)
    other=root/'lib/other.so';other.write_bytes(b'\x7fELFother')
    with pytest.raises(ValueError,match='exact kit loader'):
        verifier.parse_loader_list(f'/lib64/ld-linux-x86-64.so.2 => {other} (0x1234)',root)


@pytest.mark.parametrize('alias', ['/lib/ld-linux-x86-64.so.2','/tmp/ld-linux-x86-64.so.2'])
def test_loader_list_rejects_other_absolute_dependency_names(tmp_path,alias):
    root,loader=interpreter_alias_kit(tmp_path)
    with pytest.raises(ValueError,match='Invalid or duplicate'):
        verifier.parse_loader_list(f'{alias} => {loader} (0x1234)',root)


@pytest.mark.parametrize('first', ['/lib64/ld-linux-x86-64.so.2','ld-linux-x86-64.so.2'])
def test_loader_list_rejects_duplicate_normalized_interpreter(tmp_path,first):
    root,loader=interpreter_alias_kit(tmp_path)
    output=f'{first} => {loader} (0x1234)\n/lib64/ld-linux-x86-64.so.2 => {loader} (0x5678)\n'
    with pytest.raises(ValueError,match='Invalid or duplicate'):
        verifier.parse_loader_list(output,root)


def static_loader_roles(tmp_path, *, with_dependency=False):
    root=tmp_path/'kit';(root/'lib').mkdir(parents=True)
    loader=root/'lib/ld-linux.so';loader.write_bytes(b'\x7fELFloader')
    objects=[{'path':'lib/ld-linux.so','needed':{}}]
    roles={'loader':[loader]}
    if with_dependency:
        library=root/'lib/libexample.so';library.write_bytes(b'\x7fELFlibrary')
        objects[0]['needed']={'libexample.so':'lib/libexample.so'}
        objects.append({'path':'lib/libexample.so','needed':{}})
        roles['payload']=[library]
    receipt=root/'closure.json';receipt.write_text(json.dumps({
        'schema':'fdisbull-elf-closure-v1','complete':True,'objects':objects}))
    roles['closure_receipt']=[receipt]
    return root,roles


@pytest.mark.parametrize('output', ['statically linked\n','\tstatically linked\n'])
def test_loader_closure_accepts_successful_exact_static_leaf(tmp_path, monkeypatch, output):
    from types import SimpleNamespace
    root,roles=static_loader_roles(tmp_path)
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**kw:
        SimpleNamespace(returncode=0,stdout=output,stderr=''))
    assert verifier.check_loader_closure(root,roles)==1


def test_loader_closure_rejects_static_result_with_declared_dependencies(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root,roles=static_loader_roles(tmp_path,with_dependency=True)
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**kw:
        SimpleNamespace(returncode=0,stdout='statically linked\n',stderr=''))
    with pytest.raises(ValueError,match='contradicts declared dependencies'):
        verifier.check_loader_closure(root,roles)


@pytest.mark.parametrize('output', ['statically linked\nextra output\n','extra output\nstatically linked\n'])
def test_loader_closure_rejects_mixed_static_output(tmp_path, monkeypatch, output):
    from types import SimpleNamespace
    root,roles=static_loader_roles(tmp_path)
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**kw:
        SimpleNamespace(returncode=0,stdout=output,stderr=''))
    with pytest.raises(ValueError,match='Unrecognized or unresolved'):
        verifier.check_loader_closure(root,roles)


def test_loader_closure_does_not_accept_failed_static_probe(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root,roles=static_loader_roles(tmp_path)
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**kw:
        SimpleNamespace(returncode=1,stdout='statically linked\n',stderr='inspection failed'))
    with pytest.raises(ValueError,match='Loader could not inspect'):
        verifier.check_loader_closure(root,roles)


def cpython_object_roles(tmp_path, *, name='python/lib/python3.13/config-3.13-x86_64-linux-gnu/python.o',
                         needed=False, entry_role=None, mutation=None):
    import struct
    root=tmp_path/'kit';(root/'lib').mkdir(parents=True)
    loader=root/'lib/ld-linux.so';loader.write_bytes(b'\x7fELFloader')
    build_object=root/name;build_object.parent.mkdir(parents=True,exist_ok=True)
    header=bytearray(64);header[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHIQQQIHHHHHH',header,16,1,62,1,0,0,7448,0,64,0,0,64,48,47)
    if mutation=='class':header[4]=1
    if mutation=='big-endian':
        header[5]=2
        struct.pack_into('>HHIQQQIHHHHHH',header,16,1,62,1,0,0,7448,0,64,0,0,64,48,47)
    for field,offset,format,value in (('machine',18,'<H',183),('entry',24,'<Q',1),
            ('program-offset',32,'<Q',64),('header-size',52,'<H',32),('program-count',56,'<H',1)):
        if mutation==field:struct.pack_into(format,header,offset,value)
    build_object.write_bytes(header+b'authored relocatable fixture')
    objects=[{'path':'lib/ld-linux.so','needed':{}},
             {'path':name,'needed':{'ld-linux.so':'lib/ld-linux.so'} if needed else {}}]
    receipt=root/'closure.json';receipt.write_text(json.dumps({
        'schema':'fdisbull-elf-closure-v1','complete':True,'objects':objects}))
    roles={'loader':[loader],'payload':[build_object],'closure_receipt':[receipt]}
    if entry_role=='loader':roles['loader']=[build_object];roles['payload']=[loader]
    elif entry_role:roles[entry_role]=[build_object]
    return root,roles


def test_loader_closure_retains_exact_cpython_link_object_without_loading_it(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root,roles=cpython_object_roles(tmp_path);inspected=[]
    def run(args,**kwargs):
        inspected.append(args[-1])
        return SimpleNamespace(returncode=0,stdout='statically linked\n',stderr='')
    monkeypatch.setattr(verifier.subprocess,'run',run)
    assert verifier.check_loader_closure(root,roles)==2
    assert inspected==[str(root/'lib/ld-linux.so')]


@pytest.mark.parametrize('options', [
    {'name':'python/lib/python3.13/other.o'}, {'needed':True},
    *({'entry_role':role} for role in ('python','loader','dosbox','qemu')),
    *({'mutation':field} for field in ('class','big-endian','machine','entry','program-offset','header-size','program-count'))])
def test_loader_closure_rejects_other_or_malformed_relocatable_payloads(tmp_path, monkeypatch, options):
    from types import SimpleNamespace
    root,roles=cpython_object_roles(tmp_path,**options)
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**kw:
        SimpleNamespace(returncode=0,stdout='statically linked\n',stderr=''))
    with pytest.raises(ValueError,match='Invalid or unexpected relocatable'):
        verifier.check_loader_closure(root,roles)


def test_closure_checks_actual_loader_output_and_declared_map(tmp_path, monkeypatch):
    root = tmp_path / 'kit'; (root / 'lib').mkdir(parents=True)
    loader = root / 'ld'; loader.write_bytes(b'\x7fELFloader')
    app = root / 'app'; app.write_bytes(b'\x7fELFapp')
    lib = root / 'lib/libc.so.6'; lib.write_bytes(b'\x7fELFlibrary')
    receipt = root / 'closure.json'
    receipt.write_text(json.dumps({'schema':'fdisbull-elf-closure-v1','complete':True,'objects':[{'path':'ld','needed':{}},{'path':'app','needed':{'libc.so.6':'lib/libc.so.6'}},{'path':'lib/libc.so.6','needed':{}}]}))
    roles = {'loader':[loader], 'closure_receipt':[receipt], 'other':[app,lib]}
    from types import SimpleNamespace
    def run(args, **kwargs):
        assert '--inhibit-cache' in args and '--list' in args
        return SimpleNamespace(returncode=0, stdout=f'libc.so.6 => {lib} (0x1234)\n', stderr='')
    monkeypatch.setattr(verifier.subprocess, 'run', run)
    assert verifier.check_loader_closure(root, roles) == 3
    receipt.write_text(receipt.read_text().replace('lib/libc.so.6', 'lib/missing.so'))
    with pytest.raises(ValueError, match='dependency map'):
        verifier.check_loader_closure(root, roles)


class OracleDebug:
    def __init__(self, images):
        from types import SimpleNamespace
        self.images = iter(images)
        db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE debug_artifacts (id INTEGER, data BLOB, sha256 TEXT)')
        self.project = SimpleNamespace(db=db)
        self.captures = 0

    def call(self, method, *, timeout_ms):
        assert method == 'frame.probe' and timeout_ms > 0
        return {'available':True, 'width':320, 'height':200}

    def screenshot(self, name, *, grid=False, grid_step=32, hooks=False):
        from PIL import Image
        from fdisbull.wine_debugger import PEDebugSession
        inspect.signature(PEDebugSession.screenshot).bind(self, name, grid=grid, grid_step=grid_step, hooks=hooks)
        assert name == 'pe.png' and self._rpc_deadline is not None
        painted = next(self.images)
        image = Image.new('RGB', (3, 3), 'black')
        if painted: image.putpixel((1, 1), (255, 160, 32))
        data = io.BytesIO(); image.save(data, format='PNG'); payload = data.getvalue()
        self.captures += 1
        self.project.db.execute('INSERT INTO debug_artifacts VALUES (?,?,?)',
                                (self.captures, payload, hashlib.sha256(payload).hexdigest()))
        return {'artifact':self.captures, 'metadata':{'mode_id':'oracle'}}

    def run(self, **kwargs):
        pytest.fail('A readiness poll must not resume the stopped oracle')


def test_oracle_wait_accepts_painted_artifact_without_running():
    debug = OracleDebug([True])
    assert verifier.wait_for_pe_frame(debug)['artifact'] == 1


def test_oracle_wait_polls_blank_then_returns_exact_painted_artifact(monkeypatch):
    monkeypatch.setattr(verifier.time, 'sleep', lambda _: None)
    debug = OracleDebug([False, True])
    assert verifier.wait_for_pe_frame(debug)['artifact'] == 2
    assert debug.captures == 2


def test_oracle_wait_fails_bounded_for_blank_frame(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(verifier.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(verifier.time, 'sleep', lambda seconds: now.__setitem__(0, now[0] + seconds))
    debug = OracleDebug([False] * 10)
    with pytest.raises(ValueError, match='deadline'):
        verifier.wait_for_pe_frame(debug, 250)
    assert 1 <= debug.captures <= 4
    with pytest.raises(ValueError, match='deadline'):
        verifier.wait_for_pe_frame(debug, 0)


@pytest.mark.parametrize('operation', ['call', 'screenshot'])
def test_oracle_wait_propagates_debugger_errors(operation):
    debug = OracleDebug([True])
    def failed(*args, **kwargs):
        raise RuntimeError('debugger stopped unexpectedly')
    setattr(debug, operation, failed)
    with pytest.raises(RuntimeError, match='stopped unexpectedly'):
        verifier.wait_for_pe_frame(debug)


def test_closure_rejects_omitted_elf_and_resolved_map_mismatch(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root = tmp_path / 'kit'; (root / 'lib').mkdir(parents=True)
    loader = root / 'ld'; loader.write_bytes(b'\x7fELFloader')
    app = root / 'app'; app.write_bytes(b'\x7fELFapp')
    library = root / 'lib/libc.so.6'; library.write_bytes(b'\x7fELFlibrary')
    other = root / 'lib/other.so'; other.write_bytes(b'\x7fELFlibrary')
    receipt = root / 'closure.json'
    base = {'schema':'fdisbull-elf-closure-v1','complete':True,'objects':[{'path':'ld','needed':{}}]}
    receipt.write_text(json.dumps(base))
    roles = {'loader':[loader], 'closure_receipt':[receipt], 'other':[app,library,other]}
    monkeypatch.setattr(verifier.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='', stderr=''))
    with pytest.raises(ValueError, match='cover every'):
        verifier.check_loader_closure(root, roles)
    base['objects'].append({'path':'app','needed':{'libc.so.6':'lib/libc.so.6'}})
    receipt.write_text(json.dumps(base))
    monkeypatch.setattr(verifier.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout=f'libc.so.6 => {other} (0x1234)\n', stderr=''))
    with pytest.raises(ValueError, match='differs from receipt'):
        verifier.check_loader_closure(root, roles)


def test_zip_archive_binds_payload_and_rejects_tamper(tmp_path):
    import zipfile
    root, _ = kit(tmp_path); archive = tmp_path / 'kit.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for p in root.iterdir():
            z.write(p, root.name + '/' + p.name)
    verifier.verify_archive(archive, root)
    (root / 'item').write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs'):
        verifier.verify_archive(archive, root)


@pytest.mark.parametrize('member', ['kit/../escape', '/kit/item', 'kit//item'])
def test_zip_rejects_unsafe_names(tmp_path, member):
    import zipfile
    root, _ = kit(tmp_path); archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr(member, b'data')
    with pytest.raises(ValueError, match='Unsafe'):
        verifier.verify_archive(archive, root)


def test_zip_rejects_symlink_and_duplicate(tmp_path):
    import stat
    import zipfile
    root, _ = kit(tmp_path); archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        link = zipfile.ZipInfo('kit/item'); link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, b'payload')
    with pytest.raises(ValueError, match='Non-regular'):
        verifier.verify_archive(archive, root)
    with pytest.warns(UserWarning, match='Duplicate'):
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('kit/item', b'payload'); z.writestr('kit/item', b'payload')
    with pytest.raises(ValueError, match='Duplicate'):
        verifier.verify_archive(archive, root)


def test_junit_records_success_and_failure(tmp_path):
    import xml.etree.ElementTree as ET
    output=tmp_path/'test.xml'
    verifier.write_junit(output)
    assert ET.parse(output).getroot().attrib['failures']=='0'
    verifier.write_junit(output, ValueError('native unavailable'))
    suite=ET.parse(output).getroot()
    assert suite.attrib['failures']=='1' and suite.find('testcase/failure').text=='native unavailable'


def test_closure_excludes_only_declared_qemu_firmware(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root=tmp_path/'kit';(root/'native/qemu/share/qemu').mkdir(parents=True)
    loader=root/'ld';loader.write_bytes(b'\x7fELFloader')
    foreign=root/'native/qemu/share/qemu/openbios-ppc';foreign.write_bytes(b'\x7fELF\x01foreign')
    receipt=root/'closure.json';receipt.write_text(json.dumps({'schema':'fdisbull-elf-closure-v1','complete':True,'objects':[{'path':'ld','needed':{}}]}))
    roles={'loader':[loader],'closure_receipt':[receipt],'firmware':[foreign]}
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**kw: SimpleNamespace(returncode=0,stdout='',stderr=''))
    assert verifier.check_loader_closure(root,roles)==1
    roles['firmware']=[];roles['other']=[foreign]
    with pytest.raises(ValueError,match='cover every'):
        verifier.check_loader_closure(root,roles)
    rogue=root/'other';rogue.write_bytes(b'\x7fELF\x01foreign')
    roles['other']=[];roles['firmware']=[rogue]
    with pytest.raises(ValueError,match='cover every'):
        verifier.check_loader_closure(root,roles)


def test_loader_closure_accepts_declared_private_vendor_elf(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root=tmp_path/'kit';vendor=root/'python/lib/python3.13/site-packages/pillow.libs';vendor.mkdir(parents=True)
    library=vendor/'libimage.so';library.write_bytes(b'\x7fELFvendor')
    loader=root/'ld';loader.write_bytes(b'\x7fELFloader')
    app=root/'app';app.write_bytes(b'\x7fELFapp')
    target=library.relative_to(root).as_posix();receipt=root/'closure.json'
    receipt.write_text(json.dumps({'schema':'fdisbull-elf-closure-v1','complete':True,'objects':[
        {'path':'ld','needed':{}},{'path':'app','needed':{'libimage.so':target}},{'path':target,'needed':{}}]}))
    roles={'loader':[loader],'closure_receipt':[receipt],'other':[app,library]}
    monkeypatch.setattr(verifier.subprocess,'run',lambda *a,**kw: SimpleNamespace(returncode=0,stdout=f'libimage.so => {library} (0x1234)\n',stderr=''))
    assert verifier.check_loader_closure(root,roles)==3


@pytest.mark.parametrize('full_windows,memory_mib', [(False,4096),(True,8192)])
def test_windows_consumer_reserves_memory_and_boot_budget(tmp_path, full_windows, memory_mib):
    class Project:
        def debugger(self, *args, **kwargs):
            self.args, self.kwargs = args, kwargs
            return 'session'
    project = Project()
    assert verifier.windows_debugger(project, tmp_path, tmp_path / 'work', tmp_path / 'kernel', tmp_path / 'wine', full_windows=full_windows) == 'session'
    assert project.args == (tmp_path / 'bin/qemu', tmp_path / 'work')
    assert project.kwargs == {'kernel': tmp_path / 'kernel', 'initramfs': tmp_path / 'wine',
                              'memory_mib': memory_mib, 'boot_timeout_ms': 600000}


def test_private_workspace_allows_real_project_creation_under_umask_022(tmp_path,monkeypatch):
    import os
    import stat
    from fdisbull.project import Project
    for name in ('HOME','TMPDIR','FDISBULL_TARGET_STORE','FDISBULL_OUTPUT_ARTIFACT_DIR'):
        monkeypatch.setenv(name,'inherited-value')
    workspace=tmp_path.resolve()/'consumer';workspace.mkdir()
    before=os.umask(0o022)
    try:
        paths=verifier.prepare_private_workspace(workspace)
        target=workspace/'AUTHORED.COM';target.write_bytes(b'\xcd\x20')
        with Project.create(workspace/'target.fdb',target,image='com') as project:
            assert project.meta['format']=='COM'
            assert project.regions(1)[0].data==b'\xcd\x20'
    finally:
        os.umask(before)
    assert set(paths)=={'HOME','TMPDIR','FDISBULL_TARGET_STORE','FDISBULL_OUTPUT_ARTIFACT_DIR'}
    for name,path in paths.items():
        assert os.environ[name]==str(path)
        assert stat.S_IMODE(path.stat().st_mode)==0o700


def test_private_workspace_refuses_existing_directory_without_chmod_or_reuse(tmp_path,monkeypatch):
    import os
    import stat
    for name in ('HOME','TMPDIR','FDISBULL_TARGET_STORE','FDISBULL_OUTPUT_ARTIFACT_DIR'):
        monkeypatch.setenv(name,'inherited-value')
    workspace=tmp_path/'consumer';workspace.mkdir()
    existing=workspace/'fdisbull_target_store';existing.mkdir(mode=0o755)
    # Set an intentional caller-owned mode, independently of the test runner's umask.
    existing.chmod(0o755);(existing/'keep').write_text('caller data')
    with pytest.raises(FileExistsError,match='already exists'):
        verifier.prepare_private_workspace(workspace)
    assert stat.S_IMODE(existing.stat().st_mode)==0o755
    assert (existing/'keep').read_text()=='caller data'
    assert list(workspace.iterdir())==[existing]
    assert all(os.environ[name]=='inherited-value' for name in
               ('HOME','TMPDIR','FDISBULL_TARGET_STORE','FDISBULL_OUTPUT_ARTIFACT_DIR'))


def test_dos_fixture_isolated_from_runtime_cache_preserves_real_manifest_guard(tmp_path,monkeypatch):
    from fdisbull.project import Project
    from fdisbull.debugger import DebugSession
    for name in ('HOME','TMPDIR','FDISBULL_TARGET_STORE','FDISBULL_OUTPUT_ARTIFACT_DIR'):
        monkeypatch.setenv(name,'inherited-value')
    workspace=tmp_path.resolve()/'consumer';workspace.mkdir()
    verifier.prepare_private_workspace(workspace)
    cache=workspace/'runtime-cache';cache.mkdir()
    # Sparse data reproduces the cache-size boundary without allocating bulk bytes.
    with (cache/'base.cpio.gz').open('xb') as stream:stream.truncate(256*1024*1024+1)
    directory,target=verifier.prepare_dos_fixture(workspace)
    with Project.create(directory/'dos.fdb',target) as project:
        assert project.meta['format']=='MZ'
        debug=DebugSession.__new__(DebugSession);debug.project=project
        debug.game_dir=workspace
        with pytest.raises(ValueError,match='Game directory exceeds state manifest budget'):
            debug._disk_manifest()
        debug.game_dir=directory
        assert debug._disk_manifest()==[{'path':'KEY.EXE','sha256':hashlib.sha256(target.read_bytes()).hexdigest()}]
    assert directory==workspace/'dos'


def windows_profile_fakes(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    class Project:
        def __init__(self, path, target):
            self.path, self.target = path, target
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def analyze(self, **kwargs):
            assert kwargs == {'start':0x401000,'max_instructions':64}
    fixture=tmp_path/'oracle.exe';fixture.write_bytes(b'authored fixture')
    binary=SimpleNamespace(optional_header=SimpleNamespace(imagebase=0x400000),
        get_export=lambda:SimpleNamespace(entries=[SimpleNamespace(name='checkpoint',address=0x1000),
                                                   SimpleNamespace(name='counter',address=0x2000)]))
    monkeypatch.setitem(sys.modules,'fdisbull.project',SimpleNamespace(Project=SimpleNamespace(create=Project)))
    monkeypatch.setitem(sys.modules,'lief',SimpleNamespace(PE=SimpleNamespace(parse=lambda path:binary)))
    return fixture


def test_windows_profiles_require_distinct_compact_and_full_native_workflows(tmp_path, monkeypatch):
    fixture=windows_profile_fakes(tmp_path,monkeypatch)
    work=tmp_path/'work';work.mkdir();seen=[]
    def oracle(project, root, workspace, kernel, initramfs, checkpoint, counter, *, full_windows):
        assert project.target.read_bytes()==fixture.read_bytes()
        assert project.target.parent==workspace and project.path.parent==workspace
        assert (checkpoint,counter)==(0x401000,0x402000)
        seen.append((workspace.name,initramfs,full_windows))
        return {'sha256':str(full_windows)}
    monkeypatch.setattr(verifier,'verify_pe_oracle',oracle)
    result=verifier.verify_windows_profiles(tmp_path,work,tmp_path/'kernel',tmp_path/'compact',tmp_path/'full',fixture)
    assert seen==[('wine',tmp_path/'compact',False),('windows',tmp_path/'full',True)]
    assert result=={'wine':{'sha256':'False'},'windows':{'sha256':'True'}}


def test_full_windows_native_failure_cannot_be_reported_as_compact_success(tmp_path, monkeypatch):
    fixture=windows_profile_fakes(tmp_path,monkeypatch)
    work=tmp_path/'work';work.mkdir();seen=[]
    def oracle(*args, full_windows):
        seen.append(full_windows)
        if full_windows: raise RuntimeError('full Windows guest failed')
        return {'sha256':'compact'}
    monkeypatch.setattr(verifier,'verify_pe_oracle',oracle)
    with pytest.raises(RuntimeError,match='full Windows guest failed'):
        verifier.verify_windows_profiles(tmp_path,work,tmp_path/'kernel',tmp_path/'compact',tmp_path/'full',fixture)
    assert seen==[False,True]


@pytest.mark.parametrize('restore_works', [True,False])
def test_pe_oracle_requires_actual_counter_restore(tmp_path, monkeypatch, restore_works):
    class Debug:
        value=7
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def breakpoint(self,address):
            assert address==0x401000
            return {'bytes_verified':True}
        def run(self,**kwargs): return {'outcome':'breakpoint'}
        def memory(self,address,*,length):
            assert address==0x402000 and length==4
            return {'hex':self.value.to_bytes(4,'little').hex()}
        def trace(self,name,*,count,timeout_ms):
            assert count==4
            return {'metadata':{'complete':True}}
        def save_state(self,name): return {'artifact':'saved'}
        def click(self,x,y,*,mode_id):
            assert (x,y,mode_id)==(80,80,'mode')
            self.value=8
        def load_state(self,artifact):
            assert artifact=='saved'
            if restore_works:self.value=7
    frame={'metadata':{'mode_id':'mode'},'sha256':'frame'}
    monkeypatch.setattr(verifier,'windows_debugger',lambda *a,**kw:Debug())
    monkeypatch.setattr(verifier,'wait_for_pe_frame',lambda debug:frame)
    def run():
        return verifier.verify_pe_oracle(None,tmp_path,tmp_path,tmp_path/'kernel',tmp_path/'full',
                                         0x401000,0x402000,full_windows=True)
    if restore_works: assert run()==frame
    else:
        with pytest.raises(ValueError,match='PE native restore failed'):run()
