import importlib.util
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('offline_kit', Path(__file__).resolve().parents[1] / 'scripts/build_offline_kit.py')
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


def wheel(path, name, version):
    with zipfile.ZipFile(path, 'w') as z:
        dist = name.replace('-', '_')
        z.writestr(f'{dist}-{version}.dist-info/METADATA', f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n')
        if name == 'fdisbull':
            guard_spec = importlib.util.spec_from_file_location('distribution_guard', Path(__file__).resolve().parents[1] / 'scripts/check_dist.py')
            guard = importlib.util.module_from_spec(guard_spec); guard_spec.loader.exec_module(guard)
            for item in {'__init__.py'} | guard.REQUIRED_PE_RESOURCES | guard.REQUIRED_KNOWLEDGE_RESOURCES:
                z.writestr('fdisbull/'+item, '')
        if name == 'fdisbull-player':
            for module in ('__init__.py','__main__.py','player.py','runtime.py','live.py','word16.py',
                           'game_intents.py','intent_runtime.py'):
                z.writestr('fdisbull_player/'+module, '')


def test_incompatible_wheel_rejected(tmp_path):
    path = tmp_path / 'pillow-12.0.0-cp312-cp312-manylinux_2_28_x86_64.whl'
    wheel(path, 'pillow', '12.0.0')
    with pytest.raises(ValueError, match='does not target'):
        kit.inspect_wheel(path, 'cp313')


def test_incompatible_abi_rejected(tmp_path):
    path = tmp_path / 'pillow-12.0.0-cp313-cp312-manylinux_2_28_x86_64.whl'
    wheel(path, 'pillow', '12.0.0')
    with pytest.raises(ValueError, match='does not target'):
        kit.inspect_wheel(path, 'cp313')


def test_wheel_filename_must_match_metadata(tmp_path):
    path = tmp_path / 'fdisbull-0.20.0-py3-none-any.whl'
    wheel(path, 'fdisbull', '0.19.0')
    with pytest.raises(ValueError, match='disagree'):
        kit.inspect_wheel(path, 'cp313')


def test_missing_z3_rejected_before_packaging(tmp_path):
    from argparse import Namespace
    for name, version in kit.REQUIRED.items():
        if name == 'z3-solver':
            continue
        dist = name.replace('-', '_')
        wheel(tmp_path / f'{dist}-{version}-py3-none-any.whl', name, version)
    wheel(tmp_path / 'pillow-12.0.0-py3-none-any.whl', 'pillow', '12.0.0')
    with pytest.raises(ValueError, match='z3-solver'):
        kit.build(Namespace(source_commit='a' * 40, python_tag='cp313', wheelhouse=str(tmp_path)))


def wheelhouse(path, *, omit=None, player_version=None):
    for name, version in kit.REQUIRED.items():
        if name == omit: continue
        if name == 'fdisbull-player' and player_version is not None: version = player_version
        wheel(path / f"{name.replace('-', '_')}-{version}-py3-none-any.whl",name,version)
    wheel(path / 'pillow-12.0.0-py3-none-any.whl','pillow','12.0.0')


def test_missing_player_rejected_before_packaging(tmp_path):
    from argparse import Namespace
    wheelhouse(tmp_path,omit='fdisbull-player')
    with pytest.raises(ValueError, match='fdisbull-player'):
        kit.build(Namespace(source_commit='a'*40,python_tag='cp313',wheelhouse=str(tmp_path)))


def test_mismatched_player_version_rejected_before_packaging(tmp_path):
    from argparse import Namespace
    wheelhouse(tmp_path,player_version='0.19.0')
    with pytest.raises(ValueError, match='fdisbull-player'):
        kit.build(Namespace(source_commit='a'*40,python_tag='cp313',wheelhouse=str(tmp_path)))


def test_player_wheel_cannot_include_core_package_or_arbitrary_data(tmp_path):
    player=tmp_path/f'fdisbull_player-{kit.VERSION}-py3-none-any.whl'
    wheel(player,'fdisbull-player',kit.VERSION)
    assert kit.inspect_wheel(player,'cp313') == ('fdisbull-player',kit.VERSION)
    with zipfile.ZipFile(player,'a') as archive:
        archive.writestr('fdisbull/__init__.py','unexpected')
    with pytest.raises(ValueError,match='unexpected package'):
        kit.inspect_wheel(player,'cp313')


def test_kit_naming_and_install_manifest_follow_project_version(tmp_path):
    from argparse import Namespace
    import hashlib
    import json
    import tarfile
    wheel_dir=tmp_path/'wheels';wheel_dir.mkdir();wheelhouse(wheel_dir)
    backend=tmp_path/'dosbox';backend.write_bytes(b'test backend')
    lib=tmp_path/'libSDL2_net.so.0';lib.write_bytes(b'test library')
    source=tmp_path/'source.tar'
    with tarfile.open(source,'w') as tar:
        notice=tmp_path/'notice';notice.write_text('test source')
        tar.add(notice,arcname='notice')
    manifest=tmp_path/'patch.json';manifest.write_text(json.dumps({'patch_sha256':'patch','baseline_commit':'upstream'}))
    receipt=tmp_path/'receipt.json';receipt.write_text(json.dumps({'source_commit':'a'*40,'backend_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),'patch_sha256':'patch','upstream_commit':'upstream'}))
    license_file=tmp_path/'license';license_file.write_text('test license')
    archive,companion=kit.build(Namespace(source_commit='a'*40,python_tag='cp313',wheelhouse=str(wheel_dir),
        backend=str(backend),sdl_lib=[str(lib)],source_companion=str(source),backend_receipt=str(receipt),
        patch_manifest=str(manifest),dosbox_license=str(license_file),sdl_license=str(license_file),output=str(tmp_path/'out')))
    assert archive.name == f'fdisbull-{kit.VERSION}-linux-x86_64-offline.tar.gz'
    assert companion.name == f'fdisbull-{kit.VERSION}-linux-x86_64-source-companion.tar'
    with tarfile.open(archive) as tar:
        prefix=f'fdisbull-{kit.VERSION}-linux-x86_64-offline/'
        manifest_data=json.load(tar.extractfile(prefix+'manifest.json'))
        installer=tar.extractfile(prefix+'install.sh').read().decode()
        requirements=tar.extractfile(prefix+'requirements.txt').read().decode()
    assert manifest_data['wheels']['fdisbull']['version']==kit.VERSION
    assert manifest_data['wheels']['fdisbull-player']['version']==kit.VERSION
    assert f'fdisbull-player=={kit.VERSION}' in requirements
    assert f'm.version("fdisbull-player") == "{kit.VERSION}"' in installer


def test_player_discovery_excludes_nested_build_artifacts(tmp_path):
    import tomllib
    from setuptools import find_namespace_packages
    root=Path(__file__).resolve().parents[1]
    config=tomllib.loads((root/'player/pyproject.toml').read_text())['tool']['setuptools']['packages']['find']
    for directory in ('fdisbull_player','build/lib/fdisbull_player','build/lib/build/lib/fdisbull_player','tests','examples'):
        (tmp_path/directory).mkdir(parents=True,exist_ok=True)
        (tmp_path/directory/'__init__.py').write_text('')
    discovered=find_namespace_packages(where=str(tmp_path),include=config['include'],exclude=config.get('exclude',[]))
    assert discovered==['fdisbull_player']
