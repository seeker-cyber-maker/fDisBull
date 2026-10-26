"""Authored Wine/QEMU doctor, without a supplied target executable."""
import os
import pytest
from fdisbull.doctor import doctor


def test_real_wine_runtime_doctor(tmp_path):
    names=('FDISBULL_PE_QEMU','FDISBULL_PE_KERNEL','FDISBULL_PE_INITRAMFS')
    if any(not os.environ.get(n) for n in names):
        if os.environ.get('FDISBULL_REQUIRE_PE')=='1':pytest.fail('Supply PE QEMU runtime inputs')
        pytest.skip('Supply PE QEMU runtime inputs')
    qemu,kernel,runtime=(os.environ[n] for n in names)
    receipt=doctor(backend='wine-qemu',executable=qemu,kernel=kernel,initramfs=runtime,output=tmp_path/'evidence')
    assert receipt['status']=='passed',receipt
    assert receipt['native_state_restored'] is True
    assert receipt['temporal_promotion']['temporal']['view']=='execute'
    assert not any(p.suffix in ('.exe','.fdb','.sav','.gz') for p in (tmp_path/'evidence').rglob('*'))
