"""Opt-in native qualification of the authored Win16 GUI, never private games."""
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil

import pytest

from offline_windows_oracles import win16_profile

SPEC = importlib.util.spec_from_file_location('offline_native_verify', Path(__file__).parents[1] / 'scripts/verify_chat_offline_kit.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


def test_authored_win16_native_roundtrip(tmp_path):
    names = ('FDISBULL_NE_QEMU', 'FDISBULL_NE_KERNEL', 'FDISBULL_NE_INITRAMFS', 'FDISBULL_NE_AUTHORED_FIXTURE')
    if not all(os.environ.get(name) for name in names):
        if os.environ.get('FDISBULL_REQUIRE_NE_AUTHORED') == '1':
            pytest.fail('Authored Win16 native inputs are required')
        pytest.skip('Authored Win16 native inputs not supplied')
    qemu, kernel, initramfs, original = (Path(os.environ[name]).resolve(strict=True) for name in names)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    fixture = tmp_path / 'ORACLE.EXE'; shutil.copyfile(original, fixture)
    result = verify.verify_win16_authored(tmp_path / 'native.fdb', fixture, qemu, kernel, initramfs, win16_profile(fixture.read_bytes()))
    assert result['status'] == 'passed' and result['fixture_sha256'] == before
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
