"""Bounded standard-library reader for Windows NE executable metadata."""
import struct


def inspect_windows_ne(data):
    """Read bounded Windows NE image/segment facts, without executing the image."""
    if type(data) is not bytes or len(data)<64 or data[:2]!=b'MZ':
        raise ValueError('expected MZ with Windows NE header')
    offset=struct.unpack_from('<I',data,60)[0]
    if offset<64 or offset+64>len(data) or data[offset:offset+2]!=b'NE':
        raise ValueError('expected bounded Windows NE header')
    u16=lambda at:struct.unpack_from('<H',data,offset+at)[0]
    flags=u16(12);count=u16(28);alignment=u16(50)
    if data[offset+54]!=2 or flags&0x8000 or not count or alignment>16:
        raise ValueError('expected Windows NE executable, not a DLL or other target')
    table=offset+u16(34)
    if u16(34)<64 or table+count*8>len(data):raise ValueError('invalid NE segment table')
    segments=[]
    for index in range(count):
        sector,size,kind,allocated=struct.unpack_from('<4H',data,table+index*8)
        size=size or 65536;allocated=allocated or 65536
        start=sector<<alignment
        if not sector or start<table+count*8 or start+size>len(data) or allocated<size:
            raise ValueError('invalid NE segment payload/allocation')
        segments.append({'index':index+1,'file_offset':start,'file_bytes':size,
                         'minimum_allocation':allocated,'flags':kind,'data':bool(kind&1)})
    ip,cs,sp,ss=(u16(n) for n in (20,22,24,26))
    dgroup=u16(14)
    if not 1<=cs<=count or segments[cs-1]['data'] or ip>=segments[cs-1]['file_bytes']:
        raise ValueError('invalid NE code entry')
    if not 1<=ss<=count or not segments[ss-1]['data'] or not 1<=dgroup<=count or not segments[dgroup-1]['data']:
        raise ValueError('invalid NE stack/data group')
    # SP=0 represents the top of a64KB stack. The loader owns stack/heap growth.
    if sp and sp>65535:raise ValueError('invalid NE stack pointer')
    return {'format':'NE','target_os':'Windows','flags':flags,'entry':{'segment':cs,'offset':ip},
            'stack_segment':ss,'automatic_data_segment':dgroup,'stack_bytes':u16(18),
            'heap_bytes':u16(16),'expected_windows_version':u16(62),'segments':segments}
