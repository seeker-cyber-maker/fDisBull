"""FreeDOS component selection and corruption guards (no guest required)."""
import hashlib
import json
from pathlib import Path

import pytest

from fdisbull import freedos_runtime as runtime


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def component(tmp_path,monkeypatch):
    root=tmp_path/'runtime';root.mkdir();(root/'source').mkdir()
    payloads={'system.img':b'authored-image','source/kernel.zip':b'kernel',
              'source/freecom.zip':b'freecom','NOTICE.md':b'notice','recipe.json':b'{}','build.py':b'build'}
    for name,data in payloads.items(): (root/name).write_bytes(data)
    monkeypatch.setitem(runtime.LOCK,'kernel',_sha(payloads['source/kernel.zip']))
    monkeypatch.setitem(runtime.LOCK,'freecom',_sha(payloads['source/freecom.zip']))
    manifest=dict(format=runtime.FORMAT,version=runtime.VERSION,
                  files={name:dict(size=len(data),sha256=_sha(data)) for name,data in payloads.items()})
    (root/'manifest.json').write_text(json.dumps(manifest))
    return root


def test_selection_explicit_and_environment(component,monkeypatch):
    monkeypatch.setenv('FDISBULL_FREEDOS_RUNTIME',str(component))
    found=runtime.resolve_runtime()
    assert found['root']==str(component) and found['image']==str(component/'system.img')
    assert runtime.runtime_info(component)['version']==runtime.VERSION


@pytest.mark.parametrize('name',runtime.REQUIRED)
def test_changed_component_is_refused(component,name):
    (component/name).write_bytes(b'changed')
    with pytest.raises(ValueError,match='identity'):
        runtime.resolve_runtime(component)


def test_replaced_source_even_with_updated_manifest_is_refused(component):
    path=component/'source/kernel.zip';path.write_bytes(b'other')
    manifest=json.loads((component/'manifest.json').read_text())
    manifest['files']['source/kernel.zip']=dict(size=5,sha256=_sha(b'other'))
    (component/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='locked release'):
        runtime.resolve_runtime(component)


def test_symlinked_component_member_is_refused(component,tmp_path):
    target=tmp_path/'external';target.write_bytes(b'authored-image')
    (component/'system.img').unlink();(component/'system.img').symlink_to(target)
    with pytest.raises(ValueError,match='symlinks'):
        runtime.resolve_runtime(component)


def test_bad_input_rejected_before_output_created(tmp_path):
    source=tmp_path/'bad';source.write_bytes(b'invalid')
    output=tmp_path/'output'
    with pytest.raises(ValueError,match='locked release'):
        runtime.prepare_runtime(source,source,source,output,mtools_dir=tmp_path)
    assert not output.exists()


def test_packaged_resources_match_recipe_and_load_from_zip(tmp_path):
    import subprocess
    import sys
    import zipfile

    source_root=Path(runtime.__file__).resolve().parents[2]
    expected={name:(source_root/'native/freedos-runtime'/name).read_bytes()
              for name in ('NOTICE.md','recipe.json')}
    assert runtime._recipe_files()==expected
    package=tmp_path/'wheel-like.zip'
    with zipfile.ZipFile(package,'w') as archive:
        archive.writestr('fdisbull/__init__.py','')
        archive.write(runtime.__file__,'fdisbull/freedos_runtime.py')
        archive.writestr('fdisbull/data/freedos-runtime-notice.txt',expected['NOTICE.md'])
        archive.writestr('fdisbull/data/freedos-runtime-recipe.json',expected['recipe.json'])
    code=('import sys,hashlib,json;sys.path.insert(0,sys.argv[1]);'
          'from fdisbull.freedos_runtime import _recipe_files;'
          'print(json.dumps({k:hashlib.sha256(v).hexdigest() for k,v in _recipe_files().items()}))')
    result=subprocess.run([sys.executable,'-I','-c',code,str(package)],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)=={name:_sha(data) for name,data in expected.items()}
