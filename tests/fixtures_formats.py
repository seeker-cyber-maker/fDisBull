"""Small, synthetic executable fixtures; never execute these byte sequences."""
import struct


def pe64() -> bytes:
    """PE32+ x86-64: entry calls a separately exported `helper` function."""
    data = bytearray(1024)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 240, 0x22)
    optional = 0x98
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<I", data, optional + 16, 0x1000)
    struct.pack_into("<Q", data, optional + 24, 0x140000000)
    struct.pack_into("<II", data, optional + 32, 0x1000, 0x200)
    struct.pack_into("<II", data, optional + 56, 0x2000, 0x200)
    struct.pack_into("<H", data, optional + 68, 3)
    struct.pack_into("<I", data, optional + 108, 16)
    struct.pack_into("<II", data, optional + 112, 0x1100, 0x80)
    section = optional + 240
    data[section:section + 8] = b".text\0\0\0"
    struct.pack_into("<IIII", data, section + 8, 0x200, 0x1000, 0x200, 0x200)
    struct.pack_into("<I", data, section + 36, 0x60000020)
    data[0x200:0x206] = bytes.fromhex("e80b000000c3")
    data[0x210] = 0xC3
    # IMAGE_EXPORT_DIRECTORY uses RVAs, including the function table.
    struct.pack_into("<IIHHIIIIIII", data, 0x300,
                     0, 0, 0, 0, 0x1158, 1, 1, 1, 0x1140, 0x1144, 0x1148)
    struct.pack_into("<I", data, 0x340, 0x1010)
    struct.pack_into("<I", data, 0x344, 0x1150)
    struct.pack_into("<H", data, 0x348, 0)
    data[0x350:0x357] = b"helper\0"
    data[0x358:0x360] = b"testdll\0"
    return bytes(data)


def macho_arm64() -> bytes:
    """Thin ARM64 Mach-O with __TEXT and LC_MAIN, entry calls entry+8."""
    data = bytearray(4096)
    struct.pack_into("<IIIIIIII", data, 0,
                     0xFEEDFACF, 0x100000C, 0, 2, 2, 96, 0, 0)
    struct.pack_into("<II16sQQQQIIII", data, 32,
                     0x19, 72, b"__TEXT", 0x100000000, 4096, 0, 4096, 5, 5, 0, 0)
    struct.pack_into("<IIQQ", data, 104, 0x80000028, 24, 0x100, 0)
    data[0x100:0x10C] = bytes.fromhex("02000094c0035fd6c0035fd6")
    return bytes(data)
