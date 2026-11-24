"""Paired CONFIG.SYS initialization and character device I/O in FreeDOS.

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


HEADER = b"FDBSYS2"
FOOTER = b"END2"
CENSUS = struct.Struct("<BHHHH")
DOS_IO = struct.Struct("<BBHH8s")
DRIVER_INPUT = struct.Struct("<HBBHHH")


def _driver_census(directory, nasm, symbols):
    definitions = (
        f"%define INIT_MARKER {symbols['init_seen']}\n"
        f"%define INPUT_RECORD {symbols['read_request']}\n"
    )
    return assemble(directory, "device-census", definitions + r"""
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
    mov [driver_header],bx
    mov [driver_header+2],es
    jmp open_device
follow:
    les bx,[es:bx]
    loop next_device
    jmp output
absent:
    mov byte [state],0
open_device:
    mov dx,device_name
    mov ax,3d00h
    int 21h
    jc io_failed
    mov [handle],ax
    mov byte [io_stage],1
    mov bx,ax
    mov ax,4400h
    int 21h
    jc io_failed
    mov al,dl
    and al,80h             ; Distinguish a character device from a disk file.
    mov [device_bit],al
    jz observe_input
    or dl,20h              ; Raw mode: one INPUT packet and no Ctrl-Z handling.
    xor dh,dh
    mov ax,4401h
    int 21h
    jc io_failed
    mov byte [io_stage],2
    mov ah,3fh
    mov bx,[handle]
    mov cx,6               ; Expect a short four-byte response.
    mov dx,read_buffer
    int 21h
    jc io_failed
    mov [read_count],ax
    mov byte [io_stage],3
    mov ah,3eh
    mov bx,[handle]
    int 21h
    jc io_failed
    mov byte [io_stage],4
    jmp observe_input
io_failed:
    mov [dos_error],ax
observe_input:
    cmp byte [state],1
    jne output
    push ds
    lds si,[driver_header]
    add si,INPUT_RECORD
    push cs
    pop es
    mov di,input_record
    mov cx,(input_record_end-input_record)/2
    cld
    rep movsw
    pop ds
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
device_name:
    db 'FDBTEST$',0
handle:
    dw 0
driver_header:
    dd 0
report:
    db 'FDBSYS2'
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
io_stage:
    db 0
device_bit:
    db 0
dos_error:
    dw 0
read_count:
    dw 0
read_buffer:
    times 8 db 0a5h
input_record:
    times 10 db 0
input_record_end:
    db 'END2'
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
                if serial.is_file() and serial.read_bytes().endswith(FOOTER):
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
    expected_size = len(HEADER) + CENSUS.size + DOS_IO.size + DRIVER_INPUT.size + len(FOOTER)
    assert len(data) == expected_size and data.startswith(HEADER) and data.endswith(FOOTER), (
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
    read_request = symbols["read_request"]
    assert driver[read_request:read_request + DRIVER_INPUT.size] == bytes(DRIVER_INPUT.size)
    census = _driver_census(tmp_path, nasm, symbols)
    config = (b"DEVICE=A:\\FDBTEST.SYS\r\n" if enabled else b"") + BASELINE_CONFIG
    disk = prepare_dos_baseline(
        runtime["boot_image"], tmp_path / "driver.img", runtime["mcopy"], config=config,
        batch=BASELINE_BATCH + b"A:\\CENSUS.COM\r\n",
        extra_files={"FDBTEST.SYS": driver, "CENSUS.COM": census})
    if enabled:
        observations = (1, 0x8000, symbols["strategy"], symbols["interrupt"], 0xa55a)
        dos_io = (4, 0x80, 0, 4, b"\xa6\x00\x1a\x7f" + b"\xa5" * 4)
        driver_input = (1, 4, 0, 6, 4, 0x0100)
    else:
        observations = (0, 0, 0, 0, 0)
        dos_io = (0, 0, 2, 0, b"\xa5" * 8)  # DOS file-not-found on open.
        driver_input = (0, 0, 0, 0, 0, 0)
    expected = (HEADER + CENSUS.pack(*observations) + DOS_IO.pack(*dos_io)
                + DRIVER_INPUT.pack(*driver_input) + FOOTER)
    for qemu in (False, True):
        name = "qemu" if qemu else "dosbox-x"
        data = _boot_readback(tmp_path / name, runtime, disk, qemu=qemu)
        record_property(f"{name}_serial", data.hex())
        assert data == expected, name
    record_property("prepared_floppy_sha256", disk["prepared_sha256"])
    assert digest(disk["image"]) == disk["prepared_sha256"]
    assert digest(runtime["boot_image"]) == disk["source_sha256"]
