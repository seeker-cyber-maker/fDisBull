"""Authored FAT preparation tests; these do not establish DOS execution.

FDISBULL_QEMU_DOS_MCOPY selects an actual mcopy for the disk round trips. The
remaining tests exercise admission and injected external-process failures.
"""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from fdisbull.dos_process_image import prepare_process_disk
from fdisbull.qemm_runtime import _FATVolume


COM = bytes.fromhex('b82a4ccd21')
HELPER = bytes.fromhex('ebfe')
STARTUP = b'@echo off\r\nREM keep caller startup\r\nPATH=A:\\DOS'
CONFIG = b'DEVICE=\\DRIVER.SYS /KEEP\r\nFILES=40\r\n'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def authored_fat(files, *, bits=12, partition=False, full=False):
    """Build a small ordinary FAT volume independently of the staging code."""
    sectors, fat_sectors, root_count = (2880, 9, 224) if bits == 12 else (5200, 21, 512)
    root_sectors = (root_count * 32 + 511) // 512
    first_data = 1 + 2 * fat_sectors + root_sectors
    data = bytearray(sectors * 512)
    data[:3] = b'\xeb\x3c\x90'
    data[3:11] = b'FDBTEST '
    media = 0xf0 if bits == 12 and not partition else 0xf8
    struct.pack_into('<HBHBHHBHHHII', data, 11, 512, 1, 1, 2, root_count,
                     sectors, media, fat_sectors, 18, 2, 0, 0)
    data[510:512] = b'\x55\xaa'
    fat = bytearray(fat_sectors * 512)
    fat[:4 if bits == 16 else 3] = bytes([media, 255, 255, 255] if bits == 16 else [media, 255, 255])
    root_offset = (1 + 2 * fat_sectors) * 512
    next_cluster = 2

    def set_fat(cluster, value):
        if bits == 16:
            struct.pack_into('<H', fat, cluster * 2, value)
        else:
            offset = cluster + cluster // 2
            old = struct.unpack_from('<H', fat, offset)[0]
            struct.pack_into('<H', fat, offset, ((old & 15) | value << 4)
                             if cluster & 1 else ((old & 0xf000) | value))

    for index, (name, content) in enumerate(files.items()):
        count = max(1, (len(content) + 511) // 512)
        first_cluster = next_cluster
        for part in range(count):
            cluster = next_cluster
            next_cluster += 1
            set_fat(cluster, cluster + 1 if part + 1 < count else (0xfff if bits == 12 else 0xffff))
            offset = (first_data + cluster - 2) * 512
            piece = content[part * 512:(part + 1) * 512]
            data[offset:offset + len(piece)] = piece
        base, _, extension = name.upper().partition('.')
        entry = bytearray(32)
        entry[:11] = (base.ljust(8) + extension.ljust(3)).encode('ascii')
        entry[11] = 0x20
        struct.pack_into('<HI', entry, 26, first_cluster, len(content))
        offset = root_offset + index * 32
        data[offset:offset + 32] = entry
    if full:
        for cluster in range(next_cluster, sectors - first_data + 2):
            set_fat(cluster, 0xfff if bits == 12 else 0xffff)
    data[512:512 + len(fat)] = fat
    data[512 + len(fat):512 + 2 * len(fat)] = fat
    if not partition:
        return bytes(data)
    prefix = bytearray(2048 * 512)
    prefix[510:512] = b'\x55\xaa'
    prefix[446] = 0x80
    prefix[450] = 0x01 if bits == 12 else 0x06
    struct.pack_into('<II', prefix, 454, 2048, sectors)
    return bytes(prefix + data)


def inputs(tmp_path, *, files=None, program=COM, name='TARGET.COM', bits=12,
           partition=False, full=False):
    disk = tmp_path / 'caller-disk.img'
    original = authored_fat(files if files is not None else {
        'FDAUTO.BAT': STARTUP, 'CONFIG.SYS': CONFIG,
        'FDCONFIG.SYS': b'!DOS=HIGH\r\n', 'OTHER.DAT': b'caller-owned data',
    }, bits=bits, partition=partition, full=full)
    disk.write_bytes(original)
    source = tmp_path / name
    source.write_bytes(program)
    return disk, source, tmp_path / 'prepared.img', original


@pytest.fixture
def tool(tmp_path):
    """An explicit failing executable for tests that must refuse before/at it."""
    path = tmp_path / 'mcopy-failure'
    path.write_text('#!/bin/sh\nexit 73\n')
    path.chmod(0o700)
    return path


@pytest.fixture
def actual_mcopy():
    chosen = os.environ.get('FDISBULL_QEMU_DOS_MCOPY') or shutil.which('mcopy')
    if not chosen:
        if os.environ.get('FDISBULL_REQUIRE_QEMU_DOS_OS') == '1':
            pytest.fail('Supply FDISBULL_QEMU_DOS_MCOPY for required DOS disk staging acceptance')
        pytest.skip('Supply FDISBULL_QEMU_DOS_MCOPY for actual FAT/mcopy round trips')
    path = Path(chosen).expanduser().absolute()
    assert path.is_file() and os.access(path, os.X_OK)
    return path


@pytest.mark.parametrize('bits,partition', [(12, False), (12, True), (16, False), (16, True)])
def test_real_mcopy_preserves_source_config_and_original_startup(tmp_path, actual_mcopy, bits, partition):
    disk, source, target, original = inputs(tmp_path, bits=bits, partition=partition)
    result = prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=actual_mcopy)
    staged_bytes = target.read_bytes()
    staged = _FATVolume(staged_bytes)
    drive = 'A:' if bits == 12 and not partition else 'C:'
    assert disk.read_bytes() == original and source.read_bytes() == COM
    assert staged.read('\\TARGET.COM', maximum=100) == COM
    assert staged.read('\\FDBLOAD.COM', maximum=100) == HELPER
    expected_startup = STARTUP + b'\r\n' + drive.encode() + b'\\FDBLOAD.COM\r\n'
    assert staged.read('\\FDAUTO.BAT', maximum=65536) == expected_startup
    assert staged.read('\\CONFIG.SYS', maximum=65536) == CONFIG
    assert staged.read('\\FDCONFIG.SYS', maximum=65536) == b'!DOS=HIGH\r\n'
    assert staged.read('\\OTHER.DAT', maximum=100) == b'caller-owned data'
    assert result['original_boot_image']['sha256'] == sha(original)
    assert result['prepared_boot_image']['sha256'] == sha(staged_bytes)
    assert result['prepared_boot_image']['sha256'] != result['original_boot_image']['sha256']
    assert result['program']['source_sha256'] == sha(COM)
    assert result['helper']['sha256'] == sha(HELPER)
    assert result['startup']['before_sha256'] == sha(STARTUP)
    assert result['startup']['after_sha256'] == sha(expected_startup)
    assert result['startup']['original_bytes_preserved']
    assert result['volume'] == dict(format=f'FAT{bits}', offset=2048 * 512 if partition else 0,
                                    boot_device='floppy' if drive == 'A:' else 'ide', boot_drive=drive)
    assert result['mcopy']['path'] == str(actual_mcopy)
    assert result['mcopy']['sha256'] == sha(actual_mcopy.read_bytes())
    assert result['runtime_validation'] == 'not_run'
    assert target.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('fdisbull-dos-stage-*'))


def test_real_mz_alias_keeps_overlay_bytes(tmp_path, actual_mcopy):
    from test_dos_loader import mz_file
    program = mz_file(bytes.fromhex('b82a4ccd21') + bytes(27), overlay=b'original overlay bytes')
    disk, source, target, _ = inputs(tmp_path, program=program, name='long original program name.exe')
    result = prepare_process_disk(disk, source, sha(program), HELPER, target, mcopy=actual_mcopy)
    expected_name = 'FB' + sha(program)[:6].upper() + '.EXE'
    assert result['program']['guest_path'] == 'A:\\' + expected_name
    assert result['program']['image_format'] == 'MZ'
    assert _FATVolume(target.read_bytes()).read('\\' + expected_name, maximum=65536) == program
    assert source.read_bytes() == program


def test_real_mcopy_full_disk_refuses_and_removes_only_private_copy(tmp_path, actual_mcopy):
    disk, source, target, original = inputs(tmp_path, full=True)
    with pytest.raises(ValueError, match='mcopy failed'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=actual_mcopy)
    assert not target.exists()
    assert disk.read_bytes() == original and source.read_bytes() == COM


@pytest.mark.parametrize('name', ['FDBLOAD.COM', 'TARGET.COM', 'target.com'])
def test_existing_helper_or_target_refuses_before_mutation(tmp_path, tool, name):
    disk, source, target, original = inputs(tmp_path, files={'FDAUTO.BAT': STARTUP, name: b'keep me'})
    with pytest.raises(ValueError, match='already exists'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert disk.read_bytes() == original and not target.exists()


@pytest.mark.parametrize('path', ['../AUTO.BAT', 'A:FDAUTO.BAT', 'B:\\FDAUTO.BAT',
                                 '\\..\\AUTO.BAT', 'A:\\\\FDAUTO.BAT', '\\é.BAT',
                                 'AUTO&RUN.BAT', '%PATH%.BAT', '\\CONFIG.SYS'])
def test_unsafe_startup_selection_refuses_before_mutation(tmp_path, tool, path):
    disk, source, target, original = inputs(tmp_path)
    with pytest.raises(ValueError, match='pathname|boot volume|BAT'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool, startup_batch=path)
    assert disk.read_bytes() == original and not target.exists()


@pytest.mark.parametrize('path', ['A:\\SUB\\TARGET.COM', 'TARGET.EXE', 'X&Y.COM',
                                 'FDBLOAD.COM', 'X\n.COM'])
def test_unsafe_or_conflicting_target_name_refuses(tmp_path, tool, path):
    disk, source, target, _ = inputs(tmp_path)
    with pytest.raises(ValueError, match='pathname|extension|conflicts'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool, target_name=path)
    assert not target.exists()


@pytest.mark.parametrize('tail', [b'\x1a', b'\0', b'X' * 65536])
def test_unappendable_startup_refuses_without_rewriting_it(tmp_path, tool, tail):
    disk, source, target, original = inputs(tmp_path, files={'FDAUTO.BAT': tail})
    with pytest.raises(ValueError, match='startup|64 KiB'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert disk.read_bytes() == original and not target.exists()


def test_hash_mismatch_and_undeclared_binary_refuse(tmp_path, tool):
    disk, source, target, original = inputs(tmp_path, name='original.bin')
    with pytest.raises(ValueError, match='project SHA'):
        prepare_process_disk(disk, source, '0' * 64, HELPER, target, mcopy=tool, image_format='COM')
    with pytest.raises(ValueError, match='explicitly select'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert disk.read_bytes() == original and not target.exists()


def test_nonregular_source_is_rejected_before_opening_a_fifo(tmp_path, tool):
    disk, source, target, original = inputs(tmp_path)
    source.unlink()
    os.mkfifo(source)
    with pytest.raises(ValueError, match='regular file'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert disk.read_bytes() == original and not target.exists()


@pytest.mark.parametrize('symlink', [False, True])
def test_existing_destination_is_not_overwritten(tmp_path, tool, symlink):
    disk, source, target, original = inputs(tmp_path)
    if symlink:
        target.symlink_to(disk)
    else:
        target.write_bytes(b'previous caller output')
    with pytest.raises(FileExistsError):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert disk.read_bytes() == original
    assert target.is_symlink() if symlink else target.read_bytes() == b'previous caller output'


def test_mcopy_failure_does_not_change_original_inputs(tmp_path, tool):
    disk, source, target, original = inputs(tmp_path)
    with pytest.raises(ValueError, match='mcopy failed'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert not target.exists()
    assert disk.read_bytes() == original and source.read_bytes() == COM
    assert not list(tmp_path.glob('fdisbull-dos-stage-*'))


@pytest.mark.parametrize('which', ['source', 'disk', 'tool'])
def test_input_changed_during_external_copy_is_rejected(tmp_path, tool, monkeypatch, which):
    disk, source, target, _ = inputs(tmp_path)
    selected = {'source': source, 'disk': disk, 'tool': tool}[which]
    calls = []

    def change_input(command, **options):
        calls.append(command)
        if len(calls) == 1:
            selected.write_bytes(selected.read_bytes() + b'changed externally')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr('fdisbull.dos_process_image.subprocess.run', change_input)
    with pytest.raises(ValueError, match='changed during'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert calls and selected.read_bytes().endswith(b'changed externally')
    assert not target.exists()


def test_success_exit_without_staged_members_is_not_a_receipt(tmp_path, tool, monkeypatch):
    disk, source, target, original = inputs(tmp_path)
    monkeypatch.setattr('fdisbull.dos_process_image.subprocess.run',
                        lambda command, **options: subprocess.CompletedProcess(command, 0))
    with pytest.raises(ValueError, match='DOS image member'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert disk.read_bytes() == original and not target.exists()


def test_external_copy_cannot_silently_expand_the_disk(tmp_path, tool, monkeypatch):
    disk, source, target, original = inputs(tmp_path)

    def expand_output(command, **options):
        with target.open('ab') as stream:
            stream.write(b'not part of the original disk geometry')
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr('fdisbull.dos_process_image.subprocess.run', expand_output)
    with pytest.raises(ValueError, match='disk size'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert disk.read_bytes() == original and not target.exists()


def test_destination_replacement_is_preserved_on_failure(tmp_path, tool, monkeypatch):
    disk, source, target, original = inputs(tmp_path)
    foreign = tmp_path / 'foreign-file.img'
    foreign.write_bytes(b'concurrent caller replacement')

    def replace_output(command, **options):
        foreign.replace(target)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr('fdisbull.dos_process_image.subprocess.run', replace_output)
    with pytest.raises(ValueError, match='Owned DOS disk'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool)
    assert target.read_bytes() == b'concurrent caller replacement'
    assert disk.read_bytes() == original and source.read_bytes() == COM


@pytest.mark.parametrize('deadline', [float('nan'), float('inf'), True, 'later'])
def test_invalid_shared_deadline_is_refused_before_reading_inputs(tmp_path, deadline):
    with pytest.raises(ValueError, match='finite absolute monotonic'):
        prepare_process_disk(tmp_path / 'absent.img', tmp_path / 'absent.com',
                             sha(COM), HELPER, tmp_path / 'prepared.img',
                             mcopy='unused', deadline=deadline)


def test_expired_shared_deadline_cannot_open_inputs_or_create_output(tmp_path, monkeypatch):
    monkeypatch.setattr('fdisbull.dos_process_image.time.monotonic', lambda: 100)
    with pytest.raises(TimeoutError, match='preparation deadline'):
        prepare_process_disk(tmp_path / 'absent.img', tmp_path / 'absent.com',
                             sha(COM), HELPER, tmp_path / 'prepared.img',
                             mcopy='unused', deadline=100)
    assert not (tmp_path / 'prepared.img').exists()


def test_successive_copies_share_one_budget_and_keep_the_individual_cap(tmp_path, tool, monkeypatch):
    files = {'FDAUTO.BAT': STARTUP, 'CONFIG.SYS': CONFIG}
    disk, source, target, original = inputs(tmp_path, files=files)
    now, budgets = [100.0], []
    monkeypatch.setattr('fdisbull.dos_process_image.time.monotonic', lambda: now[0])

    def copy_member(command, **options):
        budgets.append(options['timeout'])
        # Build the resulting authored FAT independently; production readback
        # still has to verify every member and the preserved original startup.
        files[command[-1][3:]] = Path(command[-2]).read_bytes()
        target.write_bytes(authored_fat(files))
        now[0] += 6
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr('fdisbull.dos_process_image.subprocess.run', copy_member)
    receipt = prepare_process_disk(disk, source, sha(COM), HELPER, target,
                                   mcopy=tool, deadline=120)
    assert budgets == [15, 14, 8]
    assert receipt['runtime_validation'] == 'not_run'
    assert receipt['prepared_boot_image']['sha256'] == sha(target.read_bytes())
    assert disk.read_bytes() == original and source.read_bytes() == COM


def test_expiry_after_a_completed_copy_cannot_dispatch_the_next_member(tmp_path, tool, monkeypatch):
    disk, source, target, original = inputs(tmp_path)
    now, calls = [100.0], []
    monkeypatch.setattr('fdisbull.dos_process_image.time.monotonic', lambda: now[0])

    def late_copy(command, **options):
        calls.append(command)
        assert options['timeout'] == 1
        now[0] = 101
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr('fdisbull.dos_process_image.subprocess.run', late_copy)
    with pytest.raises(TimeoutError, match='preparation deadline'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target, mcopy=tool, deadline=101)
    assert len(calls) == 1 and not target.exists()
    assert disk.read_bytes() == original and source.read_bytes() == COM
    assert not list(tmp_path.glob('fdisbull-dos-stage-*'))


def test_timed_out_copy_is_not_retried_and_removes_only_owned_output(tmp_path, tool, monkeypatch):
    disk, source, target, original = inputs(tmp_path)
    monkeypatch.setattr('fdisbull.dos_process_image.time.monotonic', lambda: 100)
    calls = []

    def timed_out(command, **options):
        calls.append(command)
        assert options['timeout'] == .25
        raise subprocess.TimeoutExpired(command, options['timeout'])

    monkeypatch.setattr('fdisbull.dos_process_image.subprocess.run', timed_out)
    with pytest.raises(TimeoutError, match='mcopy deadline'):
        prepare_process_disk(disk, source, sha(COM), HELPER, target,
                             mcopy=tool, deadline=100.25)
    assert len(calls) == 1 and not target.exists()
    assert disk.read_bytes() == original and source.read_bytes() == COM
    assert not list(tmp_path.glob('fdisbull-dos-stage-*'))
