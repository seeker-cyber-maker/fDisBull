"""Owned DOSBox acceptance using authored COM code, enabled with an explicit agent."""
import os
from pathlib import Path
import struct
import pytest
from fdisbull.installer_probe import probe_installer


def test_native_queries_self_modification_and_cleanup(tmp_path):
    executable=os.environ.get('FDISBULL_INSTALLER_TEST_DOSBOX')
    if not executable:pytest.skip('explicit native DOSBox agent not selected')
    # DOS version; equipment list; conventional memory; video; mouse.
    code=bytearray.fromhex('b430cd21 cd11 cd12 b40fcd10 31c0cd33')
    target_offset=0x100+len(code)+7
    code+=b'\xc6\x06'+struct.pack('<H',target_offset)+b'\x90\xeb\x00'
    code+=b'\xcc\xb8\x00\x4c\xcd\x21'  # CC is changed to NOP before fetch.
    target=tmp_path/'PROBE.COM';target.write_bytes(code)
    report=probe_installer(target,tmp_path/'capture',executable=executable,max_fetches=10000,timeout_seconds=15)
    assert report['status'] in ('guest_exit','fetch_budget') and 'error' not in report
    assert report['owned_process_reaped'] and report['originals_unchanged']
    queries={q.get('name'):q for q in report['queries']}
    for name in ('dos-version','bios-equipment-list','bios-conventional-memory','video-state','mouse-reset-and-detect'):
        assert name in queries and queries[name]['completion']=='caller-successor-observed'
    candidates=report['changed_code_candidates']
    assert any(c['ip']==target_offset for c in candidates)
    assert not report['original_entry_established']
    assert target.read_bytes()==code
    with pytest.raises(FileExistsError):
        probe_installer(target,tmp_path/'capture',executable=executable,max_fetches=1)


def test_invalid_probe_budget_never_starts(tmp_path):
    with pytest.raises(ValueError,match='budget'):
        probe_installer(tmp_path/'absent.exe',tmp_path/'no-output',executable=tmp_path/'no-backend',max_fetches=True)
    assert not (tmp_path/'no-output').exists()


def test_native_explicit_boundary_capture(tmp_path):
    executable=os.environ.get('FDISBULL_INSTALLER_TEST_DOSBOX')
    if not executable:pytest.skip('explicit native DOSBox agent not selected')
    # Patch a byte, then stop before its fetch. No original-entry inference.
    code=bytes.fromhex('c606070190eb00ccb8004ccd21')
    target=tmp_path/'BOUND.COM';target.write_bytes(code)
    report=probe_installer(target,tmp_path/'capture',executable=executable,
        max_fetches=10000,timeout_seconds=15,stop_offset=7)
    assert report['status']=='selected_boundary',report
    assert (tmp_path/'capture/conventional-memory.bin').read_bytes()[7]==0x90
    assert report['owned_process_reaped'] and not report['rebuilt_runnable_executable']
