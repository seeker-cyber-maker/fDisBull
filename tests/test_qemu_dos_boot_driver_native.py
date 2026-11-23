"""Paired CONFIG.SYS device initialization on actual FreeDOS floppy boot.

Select both executables and original FreeDOS via the paired DOS environment.
This boots the operating system in DOSBox-X and QEMU without using either
backend's ordinary program-launch path.
"""
from pathlib import Path
import os
import shutil
import struct
import subprocess
import time

import pytest

from support.dos_process_fixture import (
    BASELINE_BATCH, BASELINE_CONFIG, assemble, character_driver, digest,
    prepare_dos_baseline,
)
from test_qemu_dosbox_parity_native import _native_inputs


def _driver_census(directory, nasm, marker_offset):
    return assemble(directory, "device-census", f"%define INIT_MARKER {marker_offset}\n" + r"""
bits 16
org 100h
    cld
    mov ah,52h
    int 21h
    push cs
    pop ds
    add bx,22h
    jc output
    cmp bx,0ffeeh
    ja output
    cmp dword [es:bx+10],'NUL '
    jne output
    cmp dword [es:bx+14],'    '
    jne output
    test word [es:bx+4],8000h
    jz output
    mov cx,64
next_device:
    cmp bx,0ffffh
    je absent
    cmp bx,0ffffh-INIT_MARKER-1
    ja output
    cmp dword [es:bx+10],'FDBT'
    jne follow
    cmp dword [es:bx+14],'EST$'
    jne follow
    mov byte [state],1
    mov ax,[es:bx+4]
    mov [attribute],ax
    mov ax,[es:bx+6]
    mov [strategy],ax
    mov ax,[es:bx+8]
    mov [interrupt],ax
    mov ax,[es:bx+INIT_MARKER]
    mov [marker],ax
    jmp output
follow:
    les bx,[es:bx]
    loop next_device
    jmp output
absent:
    mov byte [state],0
output:
    ; COM1, 9600 baud 8N1. The host bounds progress and reads the complete record.
    mov dx,3fbh
    mov al,80h
    out dx,al
    mov dx,3f8h
    mov al,12
    out dx,al
    inc dx
    xor al,al
    out dx,al
    mov dx,3fbh
    mov al,3
    out dx,al
    mov dx,3fch
    mov al,0bh
    out dx,al
    mov si,report
    mov cx,report_end-report
transmit:
    mov dx,3fdh
    in al,dx
    test al,20h
    jz transmit
    lodsb
    mov dx,3f8h
    out dx,al
    loop transmit
    mov ax,4c00h
    int 21h
report:
    db 'FDBSYS1'
state:
    db 2                   ; Incomplete or invalid chain unless observed below.
attribute:
    dw 0
strategy:
    dw 0
interrupt:
    dw 0
marker:
    dw 0
    db 'END1'
report_end:
""", nasm)


def _boot_command(directory, runtime, *, qemu):
    if qemu:
        command = [str(runtime["qemu"]), "-machine", "pc,accel=tcg", "-cpu", "486",
                   "-m", "32", "-smp", "1", "-display", "none", "-monitor", "none",
                   "-nic", "none", "-parallel", "none", "-serial", "file:serial.bin",
                   "-drive", "file=boot.img,if=floppy,format=raw,readonly=on",
                   "-boot", "order=a"]
        firmware = os.environ.get("FDISBULL_QEMU_DOS_FIRMWARE")
        if firmware:
            command.extend(("-L", str(Path(firmware).expanduser().resolve(strict=True))))
        return command

    # BOOT starts the floppy's real DOS kernel. A mounted host directory and
    # DOSBox-X's integrated DOS kernel do not process this guest configuration.
    (directory / "dosbox.conf").write_text(
        "[sdl]\noutput=surface\nshowmenu=false\n"
        "[dosbox]\nmemsize=32\nquit warning=false\n"
        "[cpu]\ncore=normal\ncycles=3000\n"
        "[mixer]\nnosound=true\n[midi]\nmididevice=none\n"
        "[serial]\nserial1=file file:serial.bin timeout:100\n"
        "[autoexec]\nboot :boot.img\n"
    )
    return [str(runtime["dosbox"]), "-conf", "dosbox.conf", "-nogui", "-nomenu"]


def _boot_readback(directory, runtime, disk, *, qemu):
    directory.mkdir()
    image = directory / "boot.img"
    shutil.copyfile(disk["image"], image)
    image.chmod(0o400)
    assert digest(image) == disk["prepared_sha256"]
    command = _boot_command(directory, runtime, qemu=qemu)
    serial = directory / "serial.bin"
    log = directory / "emulator.log"
    environment = {key: val for key, val in os.environ.items()
                   if not key.upper().startswith("DOSBOX_")}
    environment.update(SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy",
                       XDG_CONFIG_HOME=str(directory / "config"))
    with log.open("wb") as stream:
        process = subprocess.Popen(command, cwd=directory, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if serial.is_file() and serial.read_bytes().endswith(b"END1"):
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
    assert digest(image) == disk["prepared_sha256"]
    data = serial.read_bytes() if serial.is_file() else b""
    assert len(data) == 20 and data.startswith(b"FDBSYS1") and data.endswith(b"END1"), (
        data.hex(), process.returncode, log.read_text(errors="replace")[-3000:])
    return data


@pytest.mark.parametrize("enabled", [False, True], ids=["no-device-directive", "device-init"])
def test_paired_freedos_config_sys_initializes_authored_character_driver(tmp_path, enabled, record_property):
    runtime = _native_inputs()
    nasm = os.environ.get("NASM") or shutil.which("nasm")
    if not nasm:
        message = "Paired FreeDOS device boot requires NASM"
        if os.environ.get("FDISBULL_REQUIRE_QEMU_DOS_OS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    driver, symbols = character_driver(tmp_path, nasm)
    init = symbols["init_seen"]
    assert driver[init:init + 2] == b"\x00\x00"
    census = _driver_census(tmp_path, nasm, init)
    config = (b"DEVICE=A:\\FDBTEST.SYS\r\n" if enabled else b"") + BASELINE_CONFIG
    disk = prepare_dos_baseline(
        runtime["boot_image"], tmp_path / "driver.img", runtime["mcopy"], config=config,
        batch=BASELINE_BATCH + b"A:\\CENSUS.COM\r\n",
        extra_files={"FDBTEST.SYS": driver, "CENSUS.COM": census})
    observations = (
        (1, 0x8000, symbols["strategy"], symbols["interrupt"], 0xa55a) if enabled else (0, 0, 0, 0, 0)
    )
    expected = b"FDBSYS1" + struct.pack("<BHHHH", *observations) + b"END1"
    for qemu in (False, True):
        name = "qemu" if qemu else "dosbox-x"
        data = _boot_readback(tmp_path / name, runtime, disk, qemu=qemu)
        record_property(f"{name}_serial", data.hex())
        assert data == expected
    record_property("prepared_floppy_sha256", disk["prepared_sha256"])
    assert digest(disk["image"]) == disk["prepared_sha256"]
    assert digest(runtime["boot_image"]) == disk["source_sha256"]
