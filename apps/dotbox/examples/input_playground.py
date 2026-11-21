#!/usr/bin/env python3
"""Build an authored tiny DOS graphics playground, without an assembler install.

Arrow keys or WASD move a green square. Escape exits. This fixture contains no
original game code/assets. Its simple 16-bit instruction emitter is limited to
this one program; the generated COM belongs in a private runtime directory.
"""

import argparse
from pathlib import Path
import struct


def program():
    code, labels, fixups = bytearray(), {}, []

    def emit(hex_bytes):
        code.extend(bytes.fromhex(hex_bytes))

    def label(name):
        labels[name] = len(code)

    def ref(opcode, target, *, absolute=False):
        emit(opcode)
        fixups.append((len(code), target, absolute))
        emit("00 00")

    emit("0e 1f fc b8 13 00 cd 10")  # DS=CS; cld; VGA mode 13h.
    ref("be", "title", absolute=True)
    label("print")
    emit("ac 84 c0")
    ref("0f 84", "ready")
    emit("b4 0e bb 0f 00 cd 10")
    ref("e9", "print")
    label("ready")
    emit("b8 00 a0 8e c0 bf a0 7d b0 0a")  # ES=A000; square at (160,100).
    ref("e8", "draw")
    label("poll")
    emit("b4 01 cd 16")
    ref("0f 84", "poll")
    emit("30 e4 cd 16 3c 1b")
    ref("0f 84", "quit")
    emit("50 b0 00")
    ref("e8", "draw")
    emit("58")
    for scan, ascii_key, target in ((0x4d, "d", "right"), (0x4b, "a", "left"),
                                   (0x48, "w", "up"), (0x50, "s", "down")):
        emit(f"80 fc {scan:02x}")
        ref("0f 84", target)
        emit(f"3c {ord(ascii_key):02x}")
        ref("0f 84", target)
    ref("e9", "redraw")
    for name, instruction in (("right", "83 c7 08"), ("left", "83 ef 08"),
                              ("up", "81 ef 00 0a"), ("down", "81 c7 00 0a")):
        label(name)
        emit(instruction)
        ref("e9", "redraw")
    label("redraw")
    emit("81 ff 60 ea")  # Keep the square inside the VGA segment/visible span.
    ref("0f 86", "in_range")
    emit("bf a0 7d")
    label("in_range")
    emit("b0 0a")
    ref("e8", "draw")
    ref("e9", "poll")
    label("draw")
    emit("50 53 51 57 bb 08 00")
    label("row")
    emit("b9 08 00 f3 aa 81 c7 38 01 4b")  # 8 pixels, then next 320px row.
    ref("0f 85", "row")
    emit("5f 59 5b 58 c3")
    label("quit")
    emit("b8 03 00 cd 10 b8 00 4c cd 21")
    label("title")
    code.extend(b"DOTBOX INPUT PLAYGROUND\r\nArrows/WASD move. Escape exits.\r\n\0")
    for offset, target, absolute in fixups:
        value = 0x100 + labels[target] if absolute else labels[target] - (offset + 2)
        code[offset:offset + 2] = struct.pack("<H", value & 0xffff)
    return bytes(code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New .COM file, kept outside Git")
    args = parser.parse_args()
    with args.output.open("xb") as output:
        output.write(program())
    print(f"Created authored playground: {len(program())} bytes")


if __name__ == "__main__":
    main()
