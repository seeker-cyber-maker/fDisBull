"""Authored mixed/bound LE fixture bytes only; no loader implementation or original game data."""
import struct
from test_le_loader import le_file

def mixed_le(bridge_base=0x60000):
    flat = struct.pack('<BBhBH', 7, 0, 1, 1, 0)
    local16 = struct.pack('<BBhBH', 5, 0, 1, 2, 3)
    return le_file(data=b'\xb8\0\0\xc3', fixups=[flat, local16],
                   object_bases=(0x10000, bridge_base), object_flags=(0x2045, 0x1045))


def bound_le(application):
    """A declared 512-byte MZ, BW header, then an exact inner MZ at 1024."""
    prefix = bytearray(1024)
    struct.pack_into('<14H', prefix, 0, 0x5a4d, 0, 1, 0, 4, 0, 0xffff,
                     0, 32, 0, 0, 0, 64, 0)
    prefix[64] = 0xc3
    prefix[512:514] = b'BW'
    struct.pack_into('<I', prefix, 512 + 28, 1024)
    return bytes(prefix) + application


