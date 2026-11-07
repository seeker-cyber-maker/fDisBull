"""Authored FAT/configuration fixtures; these tests do not boot DOS or QEMM."""
import copy
import hashlib
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest

from fdisbull.qemm_runtime import (admit_qemm_profile, prepare_qemm_config,
                                   prepare_qemm_profile, validate_qemm_config)


CONFIG = b'DEVICE=C:\\QEMM\\QEMM386.SYS RAM\r\nDOS=HIGH,UMB\r\nFILES=30\r\n'
FLOPPY_CONFIG = CONFIG.replace(b'C:\\', b'A:\\')


def authored_driver():
    # A synthetic header for profile admission, not an executable QEMM image.
    data = bytearray(128)
    data[:2] = b'MZ'
    struct.pack_into('<H', data, 8, 4)
    struct.pack_into('<IHHH8s', data, 64, 0xffffffff, 0x8000, 18, 18, b'QEMM386$')
    data[82:] = b'authored fixture, not QEMM'.ljust(len(data) - 82, b'\0')
    return bytes(data)


def fat_image(config=None, *, bits=12, partition=False):
    if config is None:
        config = FLOPPY_CONFIG if bits == 12 and not partition else CONFIG
    sectors, fat_sectors, root_count = (2880, 9, 224) if bits == 12 else (5200, 21, 512)
    root_sectors = (root_count * 32 + 511) // 512
    first_data = 1 + 2 * fat_sectors + root_sectors
    data = bytearray(sectors * 512)
    data[:3] = b'\xeb\x3c\x90'
    data[3:11] = b'AUTHORED'
    struct.pack_into('<HBHBHHBHHHII', data, 11, 512, 1, 1, 2, root_count,
                     sectors, 0xf8, fat_sectors, 63, 16, 0, 0)
    data[510:512] = b'\x55\xaa'
    fat = bytearray(fat_sectors * 512)
    fat[:4 if bits == 16 else 3] = b'\xf8\xff\xff\xff' if bits == 16 else b'\xf8\xff\xff'
    next_cluster = 2

    def set_fat(cluster, value):
        if bits == 16:
            struct.pack_into('<H', fat, cluster * 2, value)
        else:
            offset = cluster + cluster // 2
            old = struct.unpack_from('<H', fat, offset)[0]
            struct.pack_into('<H', fat, offset, ((old & 0x000f) | value << 4) if cluster & 1 else ((old & 0xf000) | value))

    def allocate(content):
        nonlocal next_cluster
        first = next_cluster
        count = max(1, (len(content) + 511) // 512)
        for index in range(count):
            cluster = next_cluster
            next_cluster += 1
            set_fat(cluster, cluster + 1 if index + 1 < count else (0xfff if bits == 12 else 0xffff))
            offset = (first_data + cluster - 2) * 512
            part = content[index * 512:(index + 1) * 512]
            data[offset:offset + len(part)] = part
        return first

    def entry(name, cluster, size, attr=0x20):
        result = bytearray(32)
        result[:11] = name
        result[11] = attr
        struct.pack_into('<HI', result, 26, cluster, size)
        return result

    config_cluster = allocate(config)
    driver = authored_driver()
    driver_cluster = allocate(driver)
    directory_cluster = allocate(entry(b'QEMM386 SYS', driver_cluster, len(driver)))
    root = (1 + 2 * fat_sectors) * 512
    data[root:root + 32] = entry(b'CONFIG  SYS', config_cluster, len(config))
    data[root + 32:root + 64] = entry(b'QEMM       ', directory_cluster, 0, 0x10)
    data[512:512 + len(fat)] = fat
    data[512 + len(fat):512 + len(fat) * 2] = fat
    if not partition:
        return bytes(data)
    prefix = bytearray(2048 * 512)
    prefix[510:512] = b'\x55\xaa'
    prefix[446] = 0x80
    prefix[450] = 0x01 if bits == 12 else 0x06
    struct.pack_into('<II', prefix, 454, 2048, sectors)
    return bytes(prefix + data)


@pytest.mark.parametrize('bits,partition', [(12, False), (12, True), (16, False), (16, True)])
def test_profile_reads_actual_config_driver_and_retains_unknown_runtime(tmp_path, bits, partition):
    image = tmp_path / 'private.img'
    original = fat_image(bits=bits, partition=partition)
    image.write_bytes(original)
    config = tmp_path / 'CONFIG.SYS'
    selected_config = FLOPPY_CONFIG if bits == 12 and not partition else CONFIG
    config.write_bytes(selected_config)
    driver = tmp_path / 'QEMM386.SYS'
    driver.write_bytes(authored_driver())
    result = prepare_qemm_profile(image, config_sys=config, driver_path=driver)
    assert result['volume']['format'] == f'FAT{bits}'
    assert result['volume']['offset'] == (2048 * 512 if partition else 0)
    assert result['config_sys']['sha256'] == hashlib.sha256(selected_config).hexdigest()
    assert result['qemm_driver']['sha256'] == hashlib.sha256(driver.read_bytes()).hexdigest()
    assert result['memory_manager']['configured'] == 'qemm'
    assert result['memory_manager']['observed'] == 'unknown'
    assert 'not proof' in result['limitations'][0]
    assert image.read_bytes() == original
    assert result['machine']['cpu'] == '486' and result['machine']['cpus'] == 1
    assert result['machine']['boot_device'] == ('floppy' if bits == 12 and not partition else 'ide')
    assert result['machine']['boot_drive'] == ('A:' if bits == 12 and not partition else 'C:')


@pytest.mark.parametrize('line', [
    r'DEVICE=C:\DOS\EMM386.EXE NOEMS',
    r'devicehigh = c:\dos\himem.sys',
    r'DEVICE=C:\JEMM\JEMM386.EXE',
    r'DEVICE=C:\DOS\JEMMEX.EXE',
    r'INSTALL=C:\BIN\DEVLOAD.EXE C:\DOS\EMM386.EXE',
    r'DEVICE=C:\386MAX\386MAX.SYS',
    r'DEVICE=C:\DOS\HIMEMX.EXE',
])
def test_conflicting_memory_managers_refuse_without_rewriting(line):
    config = CONFIG.decode() + line + '\r\n'
    with pytest.raises(ValueError, match='Competing memory manager'):
        validate_qemm_config(config)
    with pytest.raises(ValueError, match='Competing memory manager'):
        prepare_qemm_config(config)


@pytest.mark.parametrize('config,reason', [
    ('[menu]\r\nmenuitem=qemm\r\n' + CONFIG.decode(), 'unconditional'),
    (CONFIG.decode() + 'INCLUDE=OTHER\r\n', 'unconditional'),
    (CONFIG.decode() * 2, 'exactly one'),
    (r'DEVICEHIGH=C:\QEMM\QEMM386.SYS', 'DEVICEHIGH'),
    (r'DEVICEHIGH /L:1=C:\QEMM\QEMM386.SYS', 'DEVICEHIGH'),
    (r'DEVICE?=C:\QEMM\QEMM386.SYS', 'unconditional'),
    (r'INSTALL=DEVLOAD.EXE C:\QEMM\QEMM386.SYS', 'unconditional'),
    (r'DEVICE=D:\QEMM\QEMM386.SYS', 'boot volume'),
    (r'DEVICE=C:QEMM386.SYS', 'Drive-relative'),
    (r'DEVICE=C:\..\QEMM386.SYS', '8.3'),
    (CONFIG.decode() + '\x1aDEVICE=C:\\DOS\\EMM386.EXE', 'EOF'),
])
def test_ambiguous_driver_selection_refuses(config, reason):
    with pytest.raises(ValueError, match=reason):
        validate_qemm_config(config)


def test_preview_is_explicit_and_existing_options_survive():
    source = 'REM DEVICE=EMM386.EXE\nFILES=40\n'
    result = prepare_qemm_config(source, options='RAM NOEMS')
    assert result['config_sys'].startswith('DEVICE=C:\\QEMM\\QEMM386.SYS RAM NOEMS\r\n')
    assert result['applied_to_image'] is False
    assert 'REM DEVICE=EMM386.EXE' in result['config_sys']
    second = prepare_qemm_config(result['config_sys'], options='ST:M')
    assert second['config_sys'] == result['config_sys']
    assert second['validation']['driver']['options'] == 'RAM NOEMS'


def test_external_comparison_does_not_hide_different_image_config(tmp_path):
    image = tmp_path / 'private.img'
    image.write_bytes(fat_image())
    config = tmp_path / 'CONFIG.SYS'
    config.write_bytes(CONFIG + b'FILES=50\r\n')
    with pytest.raises(ValueError, match='does not match the member'):
        prepare_qemm_profile(image, config_sys=config)
    driver = tmp_path / 'QEMM386.SYS'
    driver.write_bytes(authored_driver() + b'changed')
    with pytest.raises(ValueError, match='does not match the member'):
        prepare_qemm_profile(image, driver_path=driver)


def test_profile_rechecks_image_and_discards_supplied_observation_claim(tmp_path):
    image = tmp_path / 'private.img'
    original = fat_image()
    image.write_bytes(original)
    profile = prepare_qemm_profile(image)
    injected = copy.deepcopy(profile)
    injected['memory_manager']['observed'] = 'enabled'
    assert admit_qemm_profile(injected, image)['memory_manager']['observed'] == 'unknown'
    assert admit_qemm_profile('qemm', image)['boot_image']['sha256'] == profile['boot_image']['sha256']
    image.write_bytes(original[:-1] + b'X')
    with pytest.raises(ValueError, match='input changed: boot_image'):
        admit_qemm_profile(profile, image)


@pytest.mark.parametrize('bits,partition,config,drive', [
    (12, False, CONFIG, 'A:'),
    (12, True, FLOPPY_CONFIG, 'C:'),
    (16, False, FLOPPY_CONFIG, 'C:'),
])
def test_explicit_driver_drive_must_match_the_actual_boot_device(tmp_path, bits, partition, config, drive):
    image = tmp_path / 'private.img'
    image.write_bytes(fat_image(config, bits=bits, partition=partition))
    with pytest.raises(ValueError, match='selected boot drive ' + drive):
        prepare_qemm_profile(image)


@pytest.mark.parametrize('path', [r'\QEMM\QEMM386.SYS', r'QEMM\QEMM386.SYS'])
@pytest.mark.parametrize('bits,drive', [(12, 'A:'), (16, 'C:')])
def test_relative_driver_paths_resolve_only_within_selected_boot_volume(tmp_path, path, bits, drive):
    image = tmp_path / 'private.img'
    image.write_bytes(fat_image(('DEVICE=' + path + ' RAM\r\n').encode(), bits=bits))
    result = prepare_qemm_profile(image)
    assert result['volume']['drive'] == drive
    assert result['qemm_driver']['guest_path'] == drive + r'\QEMM\QEMM386.SYS'
    assert result['config_sys']['guest_path'] == drive + r'\CONFIG.SYS'


def test_fat_copy_disagreement_and_cyclic_member_refuse(tmp_path):
    image = tmp_path / 'private.img'
    data = bytearray(fat_image())
    data[512 + 9 * 512 + 4] ^= 0x01
    image.write_bytes(data)
    with pytest.raises(ValueError, match='copies disagree'):
        prepare_qemm_profile(image)
    data = bytearray(fat_image(CONFIG.ljust(1024, b' ')))
    # The first CONFIG cluster is 2: point it to itself in both FAT copies.
    for offset in (512 + 3, 512 + 9 * 512 + 3):
        old = struct.unpack_from('<H', data, offset)[0]
        struct.pack_into('<H', data, offset, (old & 0xf000) | 2)
    image.write_bytes(data)
    with pytest.raises(ValueError, match='cyclic'):
        prepare_qemm_profile(image)


def test_fat32_and_missing_driver_header_are_not_accepted(tmp_path):
    image = tmp_path / 'private.img'
    data = bytearray(fat_image())
    struct.pack_into('<H', data, 17, 0)
    image.write_bytes(data)
    with pytest.raises(ValueError, match='FAT12/16'):
        prepare_qemm_profile(image)
    data = bytearray(fat_image())
    marker = data.index(b'QEMM386$')
    data[marker] = ord('X')
    image.write_bytes(data)
    with pytest.raises(ValueError, match='device header'):
        prepare_qemm_profile(image)


@pytest.mark.parametrize('boot_device,boot_order', [('ide', 'order=c'), ('floppy', 'order=a')])
def test_pinned_machine_copy_is_private_immutable_and_cleaned(tmp_path, monkeypatch, boot_device, boot_order):
    """Exercise process ownership/configuration with an authored non-QEMU peer."""
    from fdisbull import qemu_machine
    executable = tmp_path / 'authored-peer'
    executable.write_text(f'#!{sys.executable}\nimport sys,time\n'
                          'if sys.argv[1:] == ["--version"]: print("QEMU emulator version 9.2.4")\n'
                          'else: time.sleep(60)\n')
    executable.chmod(0o700)
    image = tmp_path / 'private.img'
    original = b'authored boot provenance'
    image.write_bytes(original)
    monkeypatch.setattr(qemu_machine, 'QemuControl', lambda *args: SimpleNamespace(close=lambda: None))
    machine = qemu_machine.QemuMachine(executable, boot_image=image, cpu_model='486', cpus=1,
                                       memory_mib=32, boot_image_sha256=hashlib.sha256(original).hexdigest(),
                                       boot_device=boot_device)
    temporary = Path(machine.temporary.name)
    try:
        assert machine.command[machine.command.index('-cpu') + 1] == '486'
        assert machine.command[machine.command.index('-nic') + 1] == 'none'
        assert 'snapshot=on' in machine.command[machine.command.index('-drive') + 1]
        assert f'if={boot_device}' in machine.command[machine.command.index('-drive') + 1]
        assert machine.command[machine.command.index('-boot') + 1] == boot_order
        private = temporary / 'boot-image.raw'
        assert private.read_bytes() == original
        image.write_bytes(b'changed caller image')
        assert private.read_bytes() == original
        assert machine.inputs['boot_image']['sha256'] == hashlib.sha256(original).hexdigest()
    finally:
        machine.close()
    assert machine.process.poll() is not None and not temporary.exists()


def test_pinned_identity_mismatch_never_spawns(tmp_path, monkeypatch):
    from fdisbull import qemu_machine
    executable = tmp_path / 'authored-peer'
    executable.write_text(f'#!{sys.executable}\nprint("QEMU emulator version 9.2.4")\n')
    executable.chmod(0o700)
    image = tmp_path / 'private.img'
    image.write_bytes(b'changed')
    spawned = []
    with pytest.raises(ValueError, match='changed after guest profile'):
        qemu_machine.QemuMachine(executable, boot_image=image, boot_image_sha256='0' * 64, on_spawn=spawned.append)
    assert spawned == []
