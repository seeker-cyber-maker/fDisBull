"""Independent authored programs for the native DOS process acceptance lane.

The DOS kernel and shell come from a caller-owned boot image. This module only
creates our test programs and an explicitly controlled private boot baseline.
Its image preparation is test setup, not evidence that arbitrary CONFIG.SYS
files or installed QEMM/DESQview configurations have been qualified.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import struct
import subprocess


BASELINE_MARKER = b"FDBSLICE=kept-before-loader"
BASELINE_CONFIG = (
    b"FILES=40\r\nBUFFERS=20\r\nLASTDRIVE=Z\r\n"
    b"SHELL=\\FREEDOS\\BIN\\COMMAND.COM \\FREEDOS\\BIN "
    b"/E:2048 /P=\\FDAUTO.BAT\r\n"
)
BASELINE_BATCH = (
    b"@echo off\r\n"
    b"REM FDISBULL SLICE2 BASELINE SENTINEL\r\n"
    b"SET FDBSLICE=kept-before-loader\r\n"
    b"PATH A:\\FREEDOS\\BIN\r\n"
    b"A:\r\nCD \\\r\n"
)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_image_files(image, staging, mcopy, files):
    """Write only declared authored files into an already-private test image."""
    staging = Path(staging)
    staging.mkdir()
    for name, data in files.items():
        if Path(name).name != name or not isinstance(data, bytes):
            raise ValueError("Fixture files require a root filename and bytes")
        path = staging / name
        with path.open("xb") as stream:
            stream.write(data)
        subprocess.run(
            [str(mcopy), "-i", str(image), "-o", str(path), "::" + name],
            check=True, capture_output=True, timeout=15,
        )


def prepare_dos_baseline(source, destination, mcopy, *, extra_files=None,
                         config=BASELINE_CONFIG, batch=BASELINE_BATCH):
    """Copy FreeDOS Floppy Edition and select its real COMMAND.COM explicitly.

    The production preparation path receives this disk as its original input.
    It must preserve this CONFIG.SYS and execute this existing startup batch
    before the appended loader command. An environment witness proves that the
    batch actually ran, rather than merely surviving as bytes on the disk.
    """
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.exists() or not source.is_file() or source == destination:
        raise ValueError("Choose an original DOS image and a new private copy")
    before = digest(source)
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst)
    files = {
        "FDCONFIG.SYS": config,
        "FDAUTO.BAT": batch,
        # A nested DOS EXEC must not be mistaken for the selected parent exit.
        "CHILD.COM": com_exit(37),
    }
    for name, data in (extra_files or {}).items():
        if name in files:
            raise ValueError("Extra fixture files cannot replace baseline files")
        files[name] = data
    write_image_files(destination, destination.parent / "baseline-files",
                      mcopy, files)
    if digest(source) != before:
        raise ValueError("Original FreeDOS image changed during fixture setup")
    return {
        "image": destination,
        "source_sha256": before,
        "prepared_sha256": digest(destination),
        "config": config,
        "batch": batch,
    }


def com_exit(code=37):
    """NOP is the untouched first instruction; DOS exits with a nonzero code."""
    if not 0 <= code <= 255:
        raise ValueError("Expected one DOS exit byte")
    return b"\x90\xb8" + struct.pack("<H", 0x4c00 | code) + b"\xcd\x21"


def maximum_com_exit(code=37):
    """Make both documented COM startup stack writes overlap nonzero source."""
    source = bytearray(com_exit(code).ljust(0xff00, b"\x90"))
    struct.pack_into("<HH", source, len(source) - 4, 0xbeef, 0xcafe)
    return bytes(source)


def mz_exit(*, high_load=False, stack_word=None):
    """Return an authored MZ and independent header/relocation expectations.

    Code lives at relative CS=2, IP=0. One relocation changes its data-segment
    immediate; a second changes an unrelated segment-valued word. The normal
    fixture has a distinct stack segment. The high-load variant requests
    minalloc=maxalloc=0 and keeps its stack inside its larger module.
    """
    module = bytearray(0x400 if high_load else 0x80)
    struct.pack_into("<H", module, 4, 2)
    code = bytes.fromhex(
        "90"                  # nop: the entry byte must remain unchanged
        "b80700"              # mov ax,7: segment immediate relocated by DOS
        "8ed8"                # mov ds,ax
        "c7060000efbe"        # mov word [0],beef: data at module offset 70h
        "b82a4c"              # mov ax,4c2a: normal exit, code 42
        "cd21"                # int 21h
    )
    module[0x20:0x20 + len(code)] = code
    relocations = [(2, 2), (4, 0)]
    relative_ss, sp = (0, 0x400) if high_load else (0x20, 0x180)
    if stack_word is not None:
        position = relative_ss * 16 + sp - 2
        if not (0 <= stack_word <= 0xffff and 0 <= position <= len(module) - 2):
            raise ValueError("The fixture stack word must lie inside its module")
        struct.pack_into("<H", module, position, stack_word)
    minalloc = maxalloc = 0 if high_load else 0x40
    header_size = 64
    total = header_size + len(module)
    header = bytearray(header_size)
    struct.pack_into(
        "<14H", header, 0,
        0x5a4d, total % 512, (total + 511) // 512,
        len(relocations), header_size // 16, minalloc, maxalloc,
        relative_ss, sp, 0, 0, 2, 0x1c, 0,
    )
    for index, pair in enumerate(relocations):
        struct.pack_into("<HH", header, 0x1c + 4 * index, *pair)
    return bytes(header + module), {
        "module": bytes(module), "module_size": len(module),
        "relative_cs": 2, "entry_ip": 0,
        "relative_ss": relative_ss, "sp": sp,
        "relocations": relocations, "written_offset": 0x70,
        "exit_code": 42, "high_load": high_load,
    }


def relocated_module(fixture, load_segment):
    """Expected DOS relocation loop, calculated from the authored fixture."""
    result = bytearray(fixture["module"])
    for offset, segment in fixture["relocations"]:
        position = segment * 16 + offset
        old = struct.unpack_from("<H", result, position)[0]
        struct.pack_into("<H", result, position, (old + load_segment) & 0xffff)
    return bytes(result)


def large_mz_exit():
    """Make an 80 KiB module whose final chunk has independently known bytes.

    The stack is in the extra allocation after the file-backed module, so no
    startup stack write can hide a missed or truncated module read.
    """
    source, fixture = mz_exit()
    module = bytearray(fixture["module"])
    module.extend((index * 37 + 11) & 0xff
                  for index in range(0x14000 - len(module)))
    tail = b"FDISBULL LARGE MZ FINAL CHUNK\x81\xa5\xfe\x7f"
    module[-len(tail):] = tail
    relative_ss = len(module) // 16
    header = bytearray(source[:64])
    total = len(header) + len(module)
    struct.pack_into("<HH", header, 2, total % 512, (total + 511) // 512)
    struct.pack_into("<H", header, 14, relative_ss)
    fixture.update(module=bytes(module), module_size=len(module),
                   relative_ss=relative_ss, tail=tail)
    return bytes(header + module), fixture


def resident_com(*, interrupt27=False, exit_code=37):
    """Keep a real DOS memory block and an independently readable INT 60h hook."""
    code = bytearray.fromhex("900e1f")  # nop; push cs; pop ds
    code += b"\xba\x00\x00"           # mov dx,handler (patched below)
    handler_fixup = 4
    code += bytes.fromhex("b86025cd21")  # DOS set vector 60h
    retain_fixup = len(code) + 1
    code += b"\xba\x00\x00"           # mov dx,retained length
    if interrupt27:
        code += b"\xcd\x27"           # legacy TSR: DX is a byte offset
    else:
        code += b"\xb8" + struct.pack("<H", 0x3100 | exit_code) + b"\xcd\x21"
    code += b"\xeb\xfe"               # returning unexpectedly must not exit
    handler_ip = 0x100 + len(code)
    handler = bytes.fromhex("b85b6acf")  # mov ax,6a5b; iret
    code += handler
    end_ip = 0x100 + len(code)
    paragraphs = (end_ip + 15) // 16
    struct.pack_into("<H", code, handler_fixup, handler_ip)
    struct.pack_into("<H", code, retain_fixup,
                     end_ip if interrupt27 else paragraphs)
    return bytes(code), {
        "interrupt": 0x60, "handler_ip": handler_ip, "handler": handler,
        "paragraphs": paragraphs, "exit_code": None if interrupt27 else exit_code,
    }


def assemble(directory, name, source, nasm):
    """Assemble our text only, placing source/listing/binary in a private test dir."""
    directory = Path(directory)
    assembly = directory / (name + ".asm")
    output = directory / (name + ".bin")
    listing = directory / (name + ".lst")
    assembly.write_text(source)
    subprocess.run(
        [str(nasm), "-f", "bin", "-l", str(listing), "-o", str(output),
         str(assembly)], check=True, capture_output=True, timeout=15,
    )
    return output.read_bytes()


def startup_probe(directory, nasm):
    """Capture the real PSP, tail, default FCBs, DTA and inherited environment."""
    code = assemble(directory, "startup-probe", r"""
bits 16
org 100h
    nop
    mov [report+4],ds
    mov [report+6],es
    mov [report+8],ss
    mov [report+10],sp
    mov ax,[2ch]
    mov [report+12],ax
    mov ax,[16h]
    mov [report+14],ax
    mov ah,2fh
    int 21h
    mov [report+16],es
    mov [report+18],bx
    mov ax,3000h
    int 21h
    mov [report+20],ax
    mov [report+22],bx
    push cs
    pop es
    cld
    mov si,80h
    mov di,report+32
    mov cx,128
    rep movsb
    mov si,5ch
    mov di,report+160
    mov cx,16
    rep movsb
    mov si,6ch
    mov di,report+176
    mov cx,16
    rep movsb
    mov ax,[2ch]
    push ds
    mov ds,ax
    xor si,si
    mov di,report+192
    mov cx,256
    mov bl,0ffh
copy_environment:
    lodsb
    stosb
    cmp al,0
    jne environment_nonzero
    cmp bl,0
    je environment_done
environment_nonzero:
    mov bl,al
    loop copy_environment
environment_done:
    pop ds
    mov word [report],5044h
    mov word [report+2],3252h
finished:
    nop
    mov ax,4c00h
    int 21h
    times 300h-($-$$+100h) db 0
report:
    times 448 db 0
    db 'SYM1'
    dw finished,report
""", nasm)
    if code[-8:-4] != b"SYM1":
        raise ValueError("Authored startup-probe symbol footer is missing")
    finished, report = struct.unpack_from("<HH", code, len(code) - 4)
    return code, {"finished_ip": finished, "report_ip": report, "report_size": 448}


def remapped_int20(directory, nasm):
    """INT 20h returns through our handler, then the selected process loops."""
    code = assemble(directory, "remapped-int20", r"""
bits 16
org 100h
    nop
    push cs
    pop ds
    mov dx,handler
    mov ax,2520h
    int 21h
    int 20h
    inc word [counter]
park:
    jmp park
handler:
    iret
counter:
    dw 0
    db 'SYM1'
    dw park,counter
""", nasm)
    if code[-8:-4] != b"SYM1":
        raise ValueError("Authored INT20 symbol footer is missing")
    park, counter = struct.unpack_from("<HH", code, len(code) - 4)
    return code, {"park_ip": park, "counter_ip": counter}


def nested_exec(directory, nasm):
    """EXEC CHILD.COM, publish its exit status, then exit the selected parent."""
    code = assemble(directory, "nested-exec", r"""
bits 16
org 100h
    nop
    push cs
    pop ds
    push cs
    pop es
    mov sp,800h
    mov bx,90h
    mov ah,4ah
    int 21h
    jc failed
    mov ax,ds
    mov [parameters+4],ax
    mov [parameters+8],ax
    mov [parameters+12],ax
    mov dx,filename
    mov bx,parameters
    mov ax,4b00h
    int 21h
    jc failed
    push cs
    pop ds
    mov ax,4d00h
    int 21h
    mov [child_status],ax
    mov word [marker],0beefh
after_child:
    nop
    mov ax,4c11h
    int 21h
failed:
    mov ax,4c7fh
    int 21h
parameters:
    dw 0,tail,0,5ch,0,6ch,0
tail:
    db 0,13
filename:
    db 'CHILD.COM',0
marker:
    dw 0
child_status:
    dw 0
    times 700h-($-$$) db 0
    db 'SYM1'
    dw after_child,marker,child_status
""", nasm)
    if code[-10:-6] != b"SYM1":
        raise ValueError("Authored EXEC symbol footer is missing")
    after_child, marker, child_status = struct.unpack_from("<HHH", code, len(code) - 6)
    return code, {"after_child_ip": after_child, "marker_ip": marker,
                  "child_status_ip": child_status}


def character_driver(directory, nasm):
    """A minimal authored character SYS driver with an observable INIT write.

    Successful registration does not qualify useful device I/O: commands other
    than INIT deliberately return the DOS unknown-command error. The marker is
    zero in the source and changes only when DOS submits its INIT request.
    """
    code = assemble(directory, "character-driver", r"""
bits 16
org 0
    dd 0ffffffffh
    dw 8000h
    dw strategy,interrupt
    db 'FDBTEST$'
request:
    dw 0,0
init_seen:
    dw 0
strategy:
    mov [cs:request],bx
    mov [cs:request+2],es
    retf
interrupt:
    push ax
    push bx
    push ds
    push es
    push cs
    pop ds
    les bx,[request]
    cmp byte [es:bx+2],0
    jne unsupported
    mov word [es:bx+0eh],resident_end
    mov ax,cs
    mov [es:bx+10h],ax
    mov word [init_seen],0a55ah
    mov word [es:bx+3],0100h
    jmp complete
unsupported:
    mov word [es:bx+3],8103h
complete:
    pop es
    pop ds
    pop bx
    pop ax
    retf
resident_end:
    db 'SYM1'
    dw strategy,interrupt,init_seen,resident_end
""", nasm)
    if code[-12:-8] != b"SYM1":
        raise ValueError("Authored character-driver symbol footer is missing")
    strategy, interrupt, marker, resident_end = struct.unpack_from(
        "<HHHH", code, len(code) - 8)
    return code, {"name": "FDBTEST$", "strategy": strategy, "interrupt": interrupt,
                  "init_seen": marker, "resident_end": resident_end}
