"""Authored, finite native-QEMU fixtures; no DOS or game bytes are included.

Images and COM files are created only in the caller's private test directory.
The boot sector exercises a nonzero real-mode code segment. The separate COM
probe must be loaded by a real DOS kernel and command interpreter; running the
boot sector alone is never evidence that DOS worked.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import struct
import subprocess


BOOT_BASE = 0x7c00
BOOT_SEGMENT = 0x07c0
COUNTER = 0x5000
PROBE_REPORT_ADDRESS = 0xb9f00  # An unused page of VGA text RAM, outside DOS RAM.
PROBE_REPORT_SIZE = 32
PROBE_MESSAGE = b'FDISBULL NATIVE DOS SERVICE PROBE'


def boot_fixture():
    """Return an authored boot image and independent instruction boundaries.

    The BIOS enters this sector at 7c00. A far jump normalizes CS:IP to
    07c0:0006, then the fixture writes QF to VGA text RAM, initializes a counter
    to seven and repeats INC/NOP/JMP with interrupts disabled. No DOS, disk
    writes, exception interception or custom QEMU opcode is involved.
    """
    code = bytearray.fromhex(
        'fa'              # cli
        'ea0600c007'      # jmp far 07c0:0006
        '31c0'            # xor ax,ax
        '8ed8'            # mov ds,ax
        '8ed0'            # mov ss,ax
        'bc007c'          # mov sp,7c00
        'b800b8'          # mov ax,b800
        '8ec0'            # mov es,ax
        '31ff'            # xor di,di
        'b8511f' 'ab'     # mov ax,1f51; stosw  (Q)
        'b8461f' 'ab'     # mov ax,1f46; stosw  (F)
        '31c0' '8ed8'     # xor ax,ax; mov ds,ax
        'c70600500700'    # mov word [5000],7
        'b85713'          # mov ax,1357
        'bb6824'          # mov bx,2468
    )
    loop = len(code)
    code += bytes.fromhex('ff06005090ebf9')  # inc word [5000]; nop; jmp inc
    sector = bytes(code).ljust(510, b'\0') + b'\x55\xaa'
    return sector.ljust(1440 * 1024, b'\0'), {
        'entry': BOOT_BASE,
        'loop': BOOT_BASE + loop,
        'loop_ip': loop,
        'segment': BOOT_SEGMENT,
        'counter': COUNTER,
        'trace_bytes': ['ff060050', '90', 'ebf9'],
    }


def dos_probe(nonce):
    """Return a COM probe using DOS version and text-output services.

    The probe copies its completed report to an otherwise unused VGA text page
    and parks in a two-byte loop. The test reads that report only at an observed
    stop at the reported CS:IP; a launch acknowledgement is not the witness.
    """
    if not isinstance(nonce, bytes) or len(nonce) != 16:
        raise ValueError('The authored DOS probe requires a 16-byte nonce')
    code = bytearray()
    fixups = []

    def emit(hex_bytes):
        code.extend(bytes.fromhex(hex_bytes))

    def address(name):
        fixups.append((len(code), name))
        code.extend(b'\0\0')

    emit('0e1f')             # push cs; pop ds
    emit('b80030cd21')       # mov ax,3000; int 21h (DOS version)
    emit('a3'); address('dos_ax')
    emit('891e'); address('dos_bx')
    emit('ba'); address('message')
    emit('b409cd21')         # mov ah,09; int 21h (print the $-terminated message)
    emit('8cc8a3'); address('cs')  # mov ax,cs; mov [report.cs],ax
    emit('b800b88ec0')       # mov ax,b800; mov es,ax
    emit('bf001f')           # mov di,1f00: unused VGA text-page memory
    emit('be'); address('report')
    emit('b91000fcf3a5')     # mov cx,16; cld; rep movsw
    wait = 0x100 + len(code)
    emit('ebfe')             # jmp $ (bounded host run will stop the machine)
    report = 0x100 + len(code)
    code += struct.pack('<4sHHHHHH16s', b'FQDO', 1, PROBE_REPORT_SIZE, 0, 0,
                        0, wait, nonce)
    message = 0x100 + len(code)
    code += PROBE_MESSAGE + b'\r\n$'
    offsets = dict(report=report, dos_ax=report+8, dos_bx=report+10,
                   cs=report+12, message=message)
    for offset, name in fixups:
        struct.pack_into('<H', code, offset, offsets[name])
    return bytes(code), {'wait_ip': wait, 'report_offset': report,
                         'sha256': hashlib.sha256(code).hexdigest()}


def prepare_freedos_image(source, destination, mcopy, nonce):
    """Copy a caller-supplied FreeDOS floppy and add the authored probe.

    This helper is deliberately confined to the test fixture. It is not a DOS
    loader implementation or an image-distribution/install path for the tool.
    The supplied image must contain \\FREEDOS\\BIN\\COMMAND.COM, as the 1.4
    Floppy Edition boot disk does. Only the private copy is changed.
    """
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.exists() or not source.is_file() or source == destination:
        raise ValueError('Choose an existing DOS input and a new private image')
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open('rb') as reader, destination.open('xb') as writer:
        shutil.copyfileobj(reader, writer)
    probe, probe_info = dos_probe(nonce)
    files = {
        'FDCONFIG.SYS': (
            b'FILES=40\r\nBUFFERS=20\r\nLASTDRIVE=Z\r\n'
            b'SHELL=\\FREEDOS\\BIN\\COMMAND.COM \\FREEDOS\\BIN '
            b'/E:2048 /P=\\FDAUTO.BAT\r\n'),
        'FDAUTO.BAT': b'@echo off\r\ncls\r\nA:\\FDBTEST.COM\r\n',
        'FDBTEST.COM': probe,
    }
    for name, data in files.items():
        path = destination.parent / name
        with path.open('xb') as writer:
            writer.write(data)
        subprocess.run([str(mcopy), '-i', str(destination), '-o', str(path), '::' + name],
                       check=True, capture_output=True, timeout=15)
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_sha256:
        raise ValueError('The supplied DOS image changed during test preparation')
    return dict(source_sha256=source_sha256,
                prepared_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                probe=probe_info)


def parse_dos_report(data):
    if not isinstance(data, bytes) or len(data) != PROBE_REPORT_SIZE:
        raise ValueError('Expected one complete authored DOS probe report')
    magic, version, size, dos_ax, dos_bx, cs, wait_ip, nonce = struct.unpack(
        '<4sHHHHHH16s', data)
    if (magic, version, size) != (b'FQDO', 1, PROBE_REPORT_SIZE):
        raise ValueError('The authored DOS probe has not published its report')
    return dict(dos_major=dos_ax & 0xff, dos_minor=dos_ax >> 8,
                dos_oem=dos_bx >> 8, cs=cs, wait_ip=wait_ip,
                nonce=nonce.hex(), linear_pc=cs * 16 + wait_ip)
