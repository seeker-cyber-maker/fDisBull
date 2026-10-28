import importlib.util
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('offline_kit', Path(__file__).resolve().parents[1] / 'scripts/build_offline_kit.py')
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


def wheel(path, name, version):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr(f'{name}-{version}.dist-info/METADATA', f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n')


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
