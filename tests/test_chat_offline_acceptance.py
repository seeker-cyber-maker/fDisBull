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

    def screenshot(self, name, *, timeout_ms):
        from PIL import Image
        from fdisbull.wine_debugger import PEDebugSession
        inspect.signature(PEDebugSession.screenshot).bind(self, name, timeout_ms=timeout_ms)
        assert name == 'pe.png' and timeout_ms > 0
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
