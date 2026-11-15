"""Authored INT33 consumer and private, pinned CuteMouse boot derivative.

The external driver is not a repository fixture. The FreeDOS 1.4 LiteUSB
package contains CTMouse 2.1b4 (GPLv2, according to APPINFO/CTMOUSE.LSM), its
notices and SOURCE/CTMOUSE/SOURCES.ZIP. Keep that package/source beside any
private native delivery; this module only accepts the exact tested executable.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import struct

from fdisbull.qemm_runtime import _FATVolume
from fdisbull.dos_process_image import _root_present
from support.dos_process_fixture import assemble, digest, write_image_files


CTMOUSE_SHA256 = '822cf550c9e19a22785722d2306aa08ede10ff20bfe931d5a81a15f77c5f363e'
CTMOUSE_SIZE = 5829
CTMOUSE_PACKAGE_SHA256 = 'dd378ddfe5b6948d3073c12acaf0ca31bf60d0898f1cd708b6858083a14a41c7'
LITE_IMAGE_SHA256 = 'f539d456b792594bc3ca59d4e0f4c23d4f1fee73370c1390b2da245400718d36'


def prepare_mouse_disk(source, destination, driver, mcopy):
    """Append PS/2-only driver startup to a new copy of a prepared baseline.

Preserve the entire existing FDAUTO prefix and both CONFIG files. The public
process launcher subsequently appends its loader after this driver command.
No source disk or selected component manifest is modified.
"""
    source, driver = Path(source).resolve(strict=True), Path(driver).resolve(strict=True)
    destination = Path(destination).absolute()
    if (not source.is_file() or not driver.is_file() or driver.stat().st_size != CTMOUSE_SIZE
            or digest(driver) != CTMOUSE_SHA256):
        raise ValueError('Native mouse witness requires the exact pinned CTMOUSE.EXE')
    if destination.exists() or source == destination:
        raise ValueError('Choose a new private mouse boot image')
    before = digest(source)
    volume = _FATVolume(source.read_bytes())
    batch = volume.read('\\FDAUTO.BAT', maximum=65536)
    configurations = {name: volume.read('\\' + name, maximum=65536)
                      for name in ('CONFIG.SYS', 'FDCONFIG.SYS')
                      if _root_present(volume, name)}
    command = ('\r\n' + volume.boot_drive + '\\CTMOUSE.EXE /P\r\n').encode('ascii')
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    write_image_files(destination, destination.parent / 'mouse-boot-files', mcopy,
                      {'CTMOUSE.EXE': driver.read_bytes(), 'FDAUTO.BAT': batch + command})
    copied = _FATVolume(destination.read_bytes())
    if (copied.read('\\FDAUTO.BAT', maximum=65536) != batch + command
            or copied.read('\\CTMOUSE.EXE', maximum=CTMOUSE_SIZE) != driver.read_bytes()
            or any(copied.read('\\' + name, maximum=65536) != data
                   for name, data in configurations.items())
            or digest(source) != before or digest(driver) != CTMOUSE_SHA256):
        raise ValueError('Private mouse boot derivative did not preserve its pinned inputs')
    return dict(image=destination, source_sha256=before, prepared_sha256=digest(destination),
                startup_prefix=batch, startup_command=command, driver_sha256=CTMOUSE_SHA256,
                driver_size=CTMOUSE_SIZE, driver_package_sha256=CTMOUSE_PACKAGE_SHA256,
                source_media_sha256=LITE_IMAGE_SHA256)


def int33_mouse(directory, nasm):
    """COM records actual driver motion counts/buttons through INT33.

The host supplies physical events and observes named stopped boundaries; the
guest performs all initialization, polling, state mutation and DOS termination.
The first phase expects a left press/release, then the second a right pair.
    Tests use individual +3 and +2 packets: the pinned driver's default 256
    sensitivity bypasses acceleration for absolute packet motion <=4. Its
    larger-packet adaptive gain also changes AX000Bh, not just cursor pixels.
No guest memory/register edits or fabricated mouse callbacks are used.
"""
    names = ('ready', 'first_pressed', 'checkpoint', 'second_pressed', 'done', 'failed',
             'report', 'report_end', 'installed', 'driver_buttons', 'vector_offset',
             'vector_segment', 'total_x', 'total_y', 'buttons', 'polls', 'stage')
    code = assemble(directory, 'int33-mouse', r'''
bits 16
org 100h
    nop
    push cs
    pop ds
    xor ax,ax
    mov es,ax
    mov ax,[es:33h*4]
    mov [vector_offset],ax
    mov ax,[es:33h*4+2]
    mov [vector_segment],ax
    or ax,[vector_offset]
    jz failed
    xor ax,ax
    int 33h
    mov [installed],ax
    mov [driver_buttons],bx
    cmp ax,0ffffh
    jne failed
    ; Clear any startup motion before the independent input interval.
    mov ax,0bh
    int 33h
ready:
    nop
first_loop:
    call sample
    test word [buttons],1
    jz first_loop
    mov word [stage],1
first_pressed:
    nop
first_release:
    call sample
    test word [buttons],1
    jnz first_release
    mov word [stage],2
checkpoint:
    nop
second_loop:
    call sample
    test word [buttons],2
    jz second_loop
    mov word [stage],3
second_pressed:
    nop
second_release:
    call sample
    test word [buttons],2
    jnz second_release
    mov word [stage],4
done:
    nop
    mov ax,4c2ah
    int 21h
failed:
    mov word [stage],0ffffh
    jmp failed
sample:
    ; Observe buttons before draining motion. A PS/2 IRQ between the two
    ; INT33 calls must not publish a new pressed boundary with old counters.
    ; CuteMouse updates packet motion before button status; seeing the new
    ; button therefore makes the subsequent motion read include that packet.
    mov ax,3
    int 33h
    mov [buttons],bx
    mov ax,0bh
    int 33h
    add [total_x],cx
    add [total_y],dx
    inc word [polls]
    ret
report:
    db 'I33M'
installed: dw 0
driver_buttons: dw 0
vector_offset: dw 0
vector_segment: dw 0
total_x: dw 0
total_y: dw 0
buttons: dw 0
polls: dw 0
stage: dw 0
report_end:
    db 'I33S'
    dw ready,first_pressed,checkpoint,second_pressed,done,failed
    dw report,report_end,installed,driver_buttons,vector_offset,vector_segment
    dw total_x,total_y,buttons,polls,stage
''', nasm)
    footer = 4 + 2 * len(names)
    if code[-footer:-footer + 4] != b'I33S':
        raise ValueError('Authored INT33 witness footer is missing')
    offsets = dict(zip(names, struct.unpack_from('<' + 'H' * len(names), code,
                                                len(code) - footer + 4), strict=True))
    offsets['report_size'] = offsets['report_end'] - offsets['report']
    return code, offsets
